package io.github.devdooly.platformlab.jobs;

import com.sun.net.httpserver.HttpServer;
import java.io.ByteArrayInputStream;
import java.net.InetSocketAddress;
import java.net.URI;
import java.time.Duration;
import java.time.Instant;
import java.util.concurrent.Executors;
import java.util.concurrent.atomic.AtomicInteger;
import org.junit.jupiter.api.Test;
import software.amazon.awssdk.auth.credentials.AwsBasicCredentials;
import software.amazon.awssdk.auth.credentials.StaticCredentialsProvider;
import software.amazon.awssdk.awscore.exception.AwsErrorDetails;
import software.amazon.awssdk.core.checksums.RequestChecksumCalculation;
import software.amazon.awssdk.core.exception.ApiCallTimeoutException;
import software.amazon.awssdk.core.exception.SdkException;
import software.amazon.awssdk.core.sync.RequestBody;
import software.amazon.awssdk.core.sync.ResponseTransformer;
import software.amazon.awssdk.http.AbortableInputStream;
import software.amazon.awssdk.retries.StandardRetryStrategy;
import software.amazon.awssdk.services.s3.S3Client;
import software.amazon.awssdk.services.s3.model.GetObjectRequest;
import software.amazon.awssdk.services.s3.model.GetObjectResponse;
import software.amazon.awssdk.services.s3.model.PutObjectRequest;
import software.amazon.awssdk.services.s3.model.S3Exception;
import static org.assertj.core.api.Assertions.*;
import static org.mockito.ArgumentMatchers.*;
import static org.mockito.Mockito.*;

class S3RawSourceStoreTest {
    private static final String BUCKET = "platform-lab-s3-test-unit";
    private final S3Client s3 = mock(S3Client.class);
    private final S3RawSourceStore store = new S3RawSourceStore(s3, BUCKET);
    private final byte[] bytes = CanonicalSource.fixtureBytes();
    private final LabJobService.Job job = job(bytes);

    @Test void missingObjectIsPutAndActualReadBackBytesAreVerified() {
        stubGets(error(404, "NoSuchKey"), response(bytes, bytes.length));
        store.storeAndVerify(job, bytes);
        var request = org.mockito.ArgumentCaptor.forClass(PutObjectRequest.class);
        var body = org.mockito.ArgumentCaptor.forClass(RequestBody.class);
        verify(s3).putObject(request.capture(), body.capture());
        assertThat(request.getValue().bucket()).isEqualTo(BUCKET);
        assertThat(request.getValue().key()).isEqualTo(job.sourceObjectKey());
        assertThat(request.getValue().contentLength()).isEqualTo((long) bytes.length);
        assertThat(body.getValue().contentStreamProvider().newStream()).hasBinaryContent(bytes);
        verify(s3, times(2)).getObject(any(GetObjectRequest.class), transformer());
        verifyNoMoreInteractions(s3);
    }

    @Test void existingExactObjectIsVerifiedWithoutPut() {
        stubGets(response(bytes, bytes.length));
        store.storeAndVerify(job, bytes);
        verify(s3).getObject(any(GetObjectRequest.class), transformer());
        verifyNoMoreInteractions(s3);
    }

    @Test void existingSameSizeCorruptedBytesAreNotOverwritten() {
        var corrupt = bytes.clone(); corrupt[1] ^= 1;
        stubGets(response(corrupt, bytes.length));
        assertThatThrownBy(() -> store.storeAndVerify(job, bytes)).isInstanceOf(S3RawSourceStore.SourceVerificationException.class);
        verify(s3).getObject(any(GetObjectRequest.class), transformer());
        verifyNoMoreInteractions(s3);
    }

    @Test void missingIsOnlyExactNoSuchKey404NotPermissionServerOrBucketErrors() {
        for (var failure : new S3Exception[] {error(403, "AccessDenied"), error(500, "InternalError"),
            error(404, "NoSuchBucket"), error(404, "Unknown"), error(400, "NoSuchKey")}) {
            reset(s3); stubGets(failure);
            assertThatThrownBy(() -> store.storeAndVerify(job, bytes)).isSameAs(failure);
            verify(s3).getObject(any(GetObjectRequest.class), transformer()); verifyNoMoreInteractions(s3);
        }
    }

    @Test void declaredOversizeTruncationAndUndeclaredOversizeFailClosed() {
        for (var response : java.util.List.of(
            response(new byte[0], CanonicalSource.MAX_BYTES + 1L),
            response(java.util.Arrays.copyOf(bytes, bytes.length - 1), bytes.length),
            response(new byte[CanonicalSource.MAX_BYTES + 1], bytes.length))) {
            reset(s3); stubGets(response);
            assertThatThrownBy(() -> store.storeAndVerify(job, bytes)).isInstanceOf(S3RawSourceStore.SourceVerificationException.class);
            verify(s3).getObject(any(GetObjectRequest.class), transformer()); verifyNoMoreInteractions(s3);
        }
    }

    @Test void putSucceededButGetFailedLeavesObjectForVerificationOnlyRetry() {
        stubGets(error(404, "NoSuchKey"), error(500, "InternalError"), response(bytes, bytes.length));
        assertThatThrownBy(() -> store.storeAndVerify(job, bytes)).isInstanceOf(S3Exception.class);
        store.storeAndVerify(job, bytes);
        verify(s3, times(3)).getObject(any(GetObjectRequest.class), transformer());
        verify(s3).putObject(any(PutObjectRequest.class), any(RequestBody.class));
        verifyNoMoreInteractions(s3);
    }

    @Test void invalidOrMetadataMismatchNeverTouchesS3() {
        assertThatThrownBy(() -> store.storeAndVerify(job, new byte[CanonicalSource.MAX_BYTES + 1])).isInstanceOf(IllegalArgumentException.class);
        assertThatThrownBy(() -> store.storeAndVerify(job, "{}".getBytes(java.nio.charset.StandardCharsets.UTF_8))).isInstanceOf(IllegalArgumentException.class);
        var alternate = (" " + new String(bytes, java.nio.charset.StandardCharsets.UTF_8)).getBytes(java.nio.charset.StandardCharsets.UTF_8);
        assertThatThrownBy(() -> store.storeAndVerify(job, alternate)).isInstanceOf(S3RawSourceStore.SourceVerificationException.class);
        verifyNoInteractions(s3);
    }

    @Test void clientConstructionRequiresExplicitCredentialsAndSafeEndpointWithoutNetwork() {
        var credentials = StaticCredentialsProvider.create(AwsBasicCredentials.create("test-access", "test-secret"));
        for (String unsafe : java.util.List.of("http://example.com:9000", "http://192.0.2.10:9000",
            "http://localhost:9000", "file:///tmp/s3", "https://user:password@example.com", "https://example.com/s3",
            "https://example.com?secret=x")) {
            assertThatThrownBy(() -> S3ClientFactory.create(URI.create(unsafe), "garage", credentials)).isInstanceOf(IllegalArgumentException.class);
        }
        assertThatThrownBy(() -> S3ClientFactory.create(URI.create("https://example.com"), "garage", null)).isInstanceOf(NullPointerException.class);
        assertThatThrownBy(() -> S3ClientFactory.create(URI.create("https://example.com"), " ", credentials)).isInstanceOf(IllegalArgumentException.class);
        try (var client = S3ClientFactory.create(URI.create("http://127.0.0.1:9999"), "garage", credentials);
             var garage = S3ClientFactory.createGarage(URI.create("http://127.0.0.1:9999"), "garage", credentials)) {
            assertThat(client.serviceClientConfiguration().region().id()).isEqualTo("garage");
            assertThat(client.serviceClientConfiguration().overrideConfiguration().apiCallTimeout()).contains(Duration.ofSeconds(30));
            assertThat(client.serviceClientConfiguration().overrideConfiguration().apiCallAttemptTimeout()).contains(Duration.ofSeconds(10));
            assertThat(client.serviceClientConfiguration().overrideConfiguration().retryStrategy()).get()
                .isInstanceOfSatisfying(StandardRetryStrategy.class, strategy -> assertThat(strategy.maxAttempts()).isEqualTo(3));
            assertThat(garage.serviceClientConfiguration().requestChecksumCalculation()).isEqualTo(RequestChecksumCalculation.WHEN_REQUIRED);
            assertThat(garage.serviceClientConfiguration().responseChecksumValidation())
                .isEqualTo(client.serviceClientConfiguration().responseChecksumValidation());
        }
    }

    @Test void invalidTimeoutOrderingFailsBeforeClientConstruction() {
        assertThatThrownBy(() -> new S3ClientFactory.Timeouts(Duration.ofSeconds(1), Duration.ofSeconds(2),
            Duration.ofSeconds(1), Duration.ofSeconds(1))).isInstanceOf(IllegalArgumentException.class);
        assertThatThrownBy(() -> new S3ClientFactory.Timeouts(Duration.ofSeconds(5), Duration.ofSeconds(2),
            Duration.ZERO, Duration.ofSeconds(1))).isInstanceOf(IllegalArgumentException.class);
    }

    @Test void managedBodyReadTimesOutForContinuousSlowDripBeforeWholeObjectArrives() throws Exception {
        var sent = new AtomicInteger();
        var requests = new AtomicInteger();
        var server = HttpServer.create(new InetSocketAddress("127.0.0.1", 0), 0);
        try (var executor = Executors.newVirtualThreadPerTaskExecutor()) {
            server.setExecutor(executor);
            server.createContext("/", exchange -> {
                requests.incrementAndGet();
                try (exchange) {
                    exchange.getResponseHeaders().add("Content-Type", "application/x-ndjson");
                    exchange.sendResponseHeaders(200, bytes.length);
                    for (byte value : bytes) {
                        exchange.getResponseBody().write(value);
                        exchange.getResponseBody().flush();
                        sent.incrementAndGet();
                        Thread.sleep(100);
                    }
                } catch (java.io.IOException ignored) {
                    // Expected when the managed SDK deadline aborts the response.
                } catch (InterruptedException interrupted) { Thread.currentThread().interrupt(); }
            });
            server.start();
            var timeouts = new S3ClientFactory.Timeouts(Duration.ofMillis(1500), Duration.ofMillis(1500),
                Duration.ofMillis(500), Duration.ofSeconds(1));
            var credentials = StaticCredentialsProvider.create(AwsBasicCredentials.create("test-access", "test-secret"));
            try (var client = S3ClientFactory.create(URI.create("http://127.0.0.1:" + server.getAddress().getPort()), "garage", credentials, timeouts)) {
                long started = System.nanoTime();
                Throwable failure = catchThrowable(() -> new S3RawSourceStore(client, BUCKET).storeAndVerify(job, bytes));
                long elapsedMillis = Duration.ofNanos(System.nanoTime() - started).toMillis();
                assertThat(failure).isInstanceOf(SdkException.class);
                assertThat(hasCause(failure, ApiCallTimeoutException.class)).isTrue();
                assertThat(elapsedMillis).isBetween(1000L, 4000L);
                assertThat(sent.get()).isBetween(2, 40);
                assertThat(requests.get()).isEqualTo(1);
            } finally { server.stop(0); executor.shutdownNow(); }
        }
    }

    @Test void workerReadIsGetOnlyAndReturnsVerifiedSourceBytes() {
        stubGets(response(bytes, bytes.length));
        assertThat(store.readAndVerify(job)).isEqualTo(bytes);
        verify(s3).getObject(any(GetObjectRequest.class), transformer());
        verifyNoMoreInteractions(s3);
    }

    @Test void workerMissingSourceNeverRecreatesIt() {
        stubGets(error(404, "NoSuchKey"));
        assertThatThrownBy(() -> store.readAndVerify(job)).isInstanceOf(S3Exception.class);
        verify(s3).getObject(any(GetObjectRequest.class), transformer());
        verifyNoMoreInteractions(s3);
    }

    @Test void workerCorruptSourceNeverOverwritesIt() {
        var corrupt = bytes.clone(); corrupt[1] ^= 1;
        stubGets(response(corrupt, bytes.length));
        assertThatThrownBy(() -> store.readAndVerify(job)).isInstanceOf(S3RawSourceStore.SourceVerificationException.class);
        verify(s3).getObject(any(GetObjectRequest.class), transformer());
        verifyNoMoreInteractions(s3);
    }

    private void stubGets(Object... replies) {
        var next = new AtomicInteger();
        when(s3.getObject(any(GetObjectRequest.class), transformer())).thenAnswer(invocation -> {
            Object reply = replies[next.getAndIncrement()];
            if (reply instanceof RuntimeException failure) { throw failure; }
            var response = (StoredResponse) reply;
            ResponseTransformer<GetObjectResponse, byte[]> transformer = invocation.getArgument(1);
            assertThat(transformer.needsConnectionLeftOpen()).isFalse();
            return transformer.transform(GetObjectResponse.builder().contentLength(response.declaredSize()).build(),
                AbortableInputStream.create(new ByteArrayInputStream(response.body())));
        });
    }
    private static ResponseTransformer<GetObjectResponse, byte[]> transformer() { return any(); }
    private record StoredResponse(byte[] body, long declaredSize) {}
    private static StoredResponse response(byte[] body, long declaredSize) { return new StoredResponse(body, declaredSize); }
    private static boolean hasCause(Throwable failure, Class<? extends Throwable> type) {
        for (Throwable cause = failure; cause != null; cause = cause.getCause()) {
            if (type.isInstance(cause)) { return true; }
        }
        return false;
    }
    static S3Exception error(int status, String code) {
        var builder = S3Exception.builder(); builder.statusCode(status).awsErrorDetails(AwsErrorDetails.builder().errorCode(code).build()); return (S3Exception) builder.build();
    }
    static LabJobService.Job job(byte[] bytes) {
        var source = CanonicalSource.validate(bytes);
        return new LabJobService.Job("staging-unit", io.github.devdooly.platformlab.demo.SyntheticScenario.NAME,
            source.sha256(), source.size(), LabJobService.Status.STAGING, LabJobService.ExportStatus.NOT_REQUESTED,
            Instant.parse("2026-01-01T00:00:00Z"), null, null, null, null, null);
    }
}
