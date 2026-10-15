package io.github.devdooly.platformlab.jobs;

import com.sun.net.httpserver.HttpServer;
import io.github.devdooly.platformlab.jobs.exporting.ExportBundle;
import io.github.devdooly.platformlab.jobs.exporting.S3ResultExportStore;
import java.net.InetSocketAddress;
import java.net.URI;
import java.security.MessageDigest;
import java.time.Duration;
import java.util.HexFormat;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;
import org.junit.jupiter.api.Test;
import software.amazon.awssdk.auth.credentials.AwsBasicCredentials;
import software.amazon.awssdk.auth.credentials.StaticCredentialsProvider;
import software.amazon.awssdk.core.exception.ApiCallTimeoutException;
import software.amazon.awssdk.core.exception.SdkException;
import software.amazon.awssdk.services.s3.S3Client;
import static org.assertj.core.api.Assertions.*;

/** Real loopback responses continuously arrive inside the socket inactivity timeout. */
class S3ManagedReadDeadlineTest {
    private static final String BUCKET = "platform-lab-s3-test-deadline";
    private static final S3ClientFactory.Timeouts TIMEOUTS = new S3ClientFactory.Timeouts(
        Duration.ofMillis(1500), Duration.ofMillis(1500), Duration.ofMillis(500), Duration.ofSeconds(1));

    @Test void workerGetAbortsSlowBodyWithoutRetryAndSameClientCanReadAgain() throws Exception {
        byte[] bytes = CanonicalSource.fixtureBytes();
        var job = S3RawSourceStoreTest.job(bytes);
        assertBoundedAbort(bytes, false, client -> new S3RawSourceStore(client, BUCKET).readAndVerify(job));
    }

    @Test void garageExportGetAbortsSlowBodyWithoutPutAndSameClientCanVerifyAgain() throws Exception {
        byte[] bytes = ("{\"synthetic\":true,\"padding\":\"" + "x".repeat(1100) + "\"}")
            .getBytes(java.nio.charset.StandardCharsets.UTF_8);
        String hash = HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(bytes));
        var document = new ExportBundle.Document("result/deadline-unit/sensor-validation-v1/" + "a".repeat(64)
            + "/result-v1-" + hash + ".json", bytes, hash);
        assertBoundedAbort(bytes, true, client -> new S3ResultExportStore(client, BUCKET).storeAndVerify(document));
    }

    private static void assertBoundedAbort(byte[] bytes, boolean garage, ReadOperation read) throws Exception {
        var requests = new AtomicInteger();
        var sent = new AtomicInteger();
        var writes = new AtomicInteger();
        var dripFinished = new CountDownLatch(1);
        var server = HttpServer.create(new InetSocketAddress("127.0.0.1", 0), 0);
        try (var executor = Executors.newVirtualThreadPerTaskExecutor();
             var safety = Executors.newSingleThreadScheduledExecutor()) {
            server.setExecutor(executor);
            server.createContext("/", exchange -> {
                int request = requests.incrementAndGet();
                try (exchange) {
                    if (!"GET".equals(exchange.getRequestMethod())) {
                        writes.incrementAndGet(); exchange.sendResponseHeaders(405, -1); return;
                    }
                    exchange.getResponseHeaders().add("Content-Type", "application/octet-stream");
                    exchange.sendResponseHeaders(200, bytes.length);
                    if (request > 1) { exchange.getResponseBody().write(bytes); return; }
                    try {
                        for (byte value : bytes) {
                            exchange.getResponseBody().write(value);
                            exchange.getResponseBody().flush();
                            sent.incrementAndGet();
                            Thread.sleep(100);
                        }
                    } finally { dripFinished.countDown(); }
                } catch (java.io.IOException expected) {
                    // The client must close the first response before the entire body arrives.
                } catch (InterruptedException interrupted) { Thread.currentThread().interrupt(); }
            });
            server.start();
            // Test-only failsafe: a regression fails the strict four-second assertion, then
            // this independent server stop prevents another 110-second test body drain.
            safety.schedule(() -> server.stop(0), 8, TimeUnit.SECONDS);
            var endpoint = URI.create("http://127.0.0.1:" + server.getAddress().getPort());
            var credentials = StaticCredentialsProvider.create(AwsBasicCredentials.create("test-access", "test-secret"));
            try (var client = garage ? S3ClientFactory.createGarage(endpoint, "garage", credentials, TIMEOUTS)
                                     : S3ClientFactory.create(endpoint, "garage", credentials, TIMEOUTS)) {
                long started = System.nanoTime();
                Throwable failure = catchThrowable(() -> read.run(client));
                long elapsedMillis = Duration.ofNanos(System.nanoTime() - started).toMillis();
                assertThat(failure).isInstanceOf(SdkException.class);
                assertThat(hasCause(failure, ApiCallTimeoutException.class)).isTrue();
                assertThat(elapsedMillis).isBetween(1000L, 4000L);
                assertThat(sent.get()).isBetween(2, 40);
                assertThat(requests.get()).isEqualTo(1);
                assertThat(writes.get()).isZero();
                assertThat(dripFinished.await(2, TimeUnit.SECONDS)).as("first response was actually disconnected").isTrue();
                assertThatCode(() -> read.run(client)).doesNotThrowAnyException();
                assertThat(requests.get()).isEqualTo(2);
                assertThat(writes.get()).isZero();
            } finally { server.stop(0); executor.shutdownNow(); safety.shutdownNow(); }
        }
    }

    private static boolean hasCause(Throwable failure, Class<? extends Throwable> type) {
        for (Throwable cause = failure; cause != null; cause = cause.getCause()) {
            if (type.isInstance(cause)) { return true; }
        }
        return false;
    }
    @FunctionalInterface private interface ReadOperation { void run(S3Client client); }
}
