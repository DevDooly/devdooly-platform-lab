package io.github.devdooly.platformlab.jobs.messaging;

import io.github.devdooly.platformlab.PlatformLabApplication;
import io.github.devdooly.platformlab.jobs.LabJobService;
import io.github.devdooly.platformlab.jobs.S3ClientFactory;
import io.github.devdooly.platformlab.jobs.S3RawSourceStore;
import io.github.devdooly.platformlab.jobs.VerifiedSourceReader;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardCopyOption;
import java.nio.file.StandardOpenOption;
import java.time.Duration;
import java.time.ZoneId;
import java.util.Map;
import java.util.concurrent.locks.LockSupport;
import javax.sql.DataSource;
import org.apache.kafka.clients.consumer.Consumer;
import org.apache.kafka.clients.producer.Producer;
import org.apache.kafka.clients.producer.RecordMetadata;
import org.springframework.boot.WebApplicationType;
import org.springframework.boot.builder.SpringApplicationBuilder;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.core.env.MapPropertySource;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.support.TransactionSynchronizationManager;
import org.springframework.transaction.support.TransactionTemplate;
import software.amazon.awssdk.auth.credentials.AwsBasicCredentials;
import software.amazon.awssdk.auth.credentials.StaticCredentialsProvider;
import software.amazon.awssdk.services.s3.S3Client;
import static org.mockito.ArgumentMatchers.*;
import static org.mockito.Mockito.*;

/** Child JVM used only by the opt-in KafkaRedeliveryIT. It never hosts HTTP or runs a scheduler. */
public final class KafkaCrashProbe {
    private KafkaCrashProbe() {}

    public static void main(String[] args) throws Exception {
        if (args.length != 5) { throw new IllegalArgumentException("Expected mode, topic, group, checkpoint and run ID"); }
        String mode = args[0], topic = args[1], group = args[2], runId = args[4];
        Path checkpoint = Path.of(args[3]).toAbsolutePath().normalize();
        KafkaRedeliveryIT.requireOwnedResourceName(topic);
        KafkaRedeliveryIT.requireOwnedResourceName(group);
        if (!runId.matches("kafka-it-[a-f0-9-]{36}")) { throw new IllegalArgumentException("Invalid owned run ID"); }
        if (!checkpoint.getFileName().toString().equals("checkpoint.json") || Files.exists(checkpoint)) {
            throw new IllegalArgumentException("Checkpoint must be a fresh private checkpoint.json");
        }
        String databaseUrl = KafkaRedeliveryIT.disposableDatabaseUrl();
        String bootstrap = KafkaRedeliveryIT.guardedBootstrap();
        var endpoint = KafkaRedeliveryIT.guardedS3Endpoint();
        String bucket = KafkaRedeliveryIT.guardedBucket();
        String accessKey = KafkaRedeliveryIT.required("LAB_S3_TEST_ACCESS_KEY");
        String secretKey = KafkaRedeliveryIT.required("LAB_S3_TEST_SECRET_KEY");
        if (Runtime.version().feature() != 21 || !ZoneId.of("Asia/Seoul").equals(ZoneId.systemDefault())) {
            throw new IllegalStateException("Probe requires Asia/Seoul JVM timezone");
        }
        try (var context = new SpringApplicationBuilder(PlatformLabApplication.class)
                .web(WebApplicationType.NONE).profiles("db-test", "worker")
                .properties("logging.level.root=WARN")
                .initializers(applicationContext -> applicationContext.getEnvironment().getPropertySources()
                    .addFirst(new MapPropertySource("guarded-disposable-kafka-probe-database", Map.of(
                        "spring.datasource.url", databaseUrl,
                        "spring.datasource.username", KafkaRedeliveryIT.required("DB_TEST_USERNAME"),
                        "spring.datasource.password", KafkaRedeliveryIT.required("DB_TEST_PASSWORD")))))
                .run()) {
            try (var connection = context.getBean(DataSource.class).getConnection()) {
                if (!"MariaDB".equals(connection.getMetaData().getDatabaseProductName())
                    || !"platform_lab_kafka_it".equals(connection.getCatalog())) {
                    throw new IllegalStateException("Probe requires the disposable MariaDB schema");
                }
            }
            try (var admin = KafkaRedeliveryIT.admin(bootstrap)) {
                KafkaRedeliveryIT.requireExpectedCluster(admin);
            }
            LabJobService jobs = context.getBean(LabJobService.class);
            JdbcTemplate jdbc = context.getBean(JdbcTemplate.class);
            if (!runId.equals(jobs.get(runId).runId())) { throw new IllegalStateException("Expected prepared probe run"); }
            if ("publisher-ack".equals(mode)) {
                Producer<String, String> producer = KafkaClientFactory.producer(bootstrap);
                try {
                    new DispatchPublisher(jobs, producer, topic, metadata -> {
                        if (TransactionSynchronizationManager.isActualTransactionActive()) {
                            throw new IllegalStateException("Broker ACK hook unexpectedly has an active database transaction");
                        }
                        checkpointAndPark(checkpoint, mode, runId, "PUBLISHER_ACKED_BEFORE_OUTBOX_ACK",
                            metadata.topic(), metadata.partition(), metadata.offset(),
                            TransactionSynchronizationManager.isActualTransactionActive(), 0, 0);
                    })
                        .publishOne().orElseThrow(() -> new IllegalStateException("Expected one pending DISPATCH"));
                    throw new IllegalStateException("Publisher hook did not park");
                } finally { producer.close(Duration.ofSeconds(5)); }
            }
            if (!"worker-after-db".equals(mode) && !"worker-before-dbcommit".equals(mode)) {
                throw new IllegalArgumentException("Unknown crash probe mode");
            }
            try (S3Client s3 = S3ClientFactory.createGarage(endpoint, "garage", StaticCredentialsProvider.create(
                    AwsBasicCredentials.create(accessKey, secretKey)))) {
                var store = new S3RawSourceStore(s3, bucket);
                VerifiedSourceReader reader = job -> {
                    if (TransactionSynchronizationManager.isActualTransactionActive()) {
                        throw new IllegalStateException("S3 GET must not run in a database transaction");
                    }
                    return store.readAndVerify(job);
                };
                LabJobService workerJobs = jobs;
                if ("worker-before-dbcommit".equals(mode)) {
                    workerJobs = spy(jobs);
                    var outer = new TransactionTemplate(context.getBean(PlatformTransactionManager.class));
                    doAnswer(invocation -> outer.execute(status -> {
                        final LabJobService.Job processed;
                        try { processed = (LabJobService.Job) invocation.callRealMethod(); }
                        catch (RuntimeException | Error failure) { throw failure; }
                        catch (Throwable failure) { throw new IllegalStateException("Real job processing failed", failure); }
                        if (!TransactionSynchronizationManager.isActualTransactionActive()
                            || processed.status() != LabJobService.Status.COMPLETED) {
                            throw new IllegalStateException("Expected real SQL work inside the uncommitted transaction");
                        }
                        long runs = jdbc.queryForObject("SELECT COUNT(*) FROM demo_run WHERE id = ?", Long.class, runId);
                        long outcomes = jdbc.queryForObject("SELECT COUNT(*) FROM demo_outcome WHERE run_id = ?", Long.class, runId);
                        if (runs != 1 || outcomes != 12) { throw new IllegalStateException("Real uncommitted result rows are missing"); }
                        checkpointAndPark(checkpoint, mode, runId, "WORKER_SQL_COMPLETE_BEFORE_DB_COMMIT",
                            topic, 0, -1, true, runs, outcomes);
                        return processed;
                    })).when(workerJobs).process(eq(runId), anyString());
                }
                Consumer<String, String> consumer = KafkaClientFactory.consumer(bootstrap, group);
                try {
                    DispatchWorker worker = "worker-after-db".equals(mode)
                        ? new DispatchWorker(workerJobs, reader, consumer, topic, delivery -> {
                            if (TransactionSynchronizationManager.isActualTransactionActive()) {
                                throw new IllegalStateException("After-DB hook still has an active transaction");
                            }
                            long runs = jdbc.queryForObject("SELECT COUNT(*) FROM demo_run WHERE id = ?", Long.class, runId);
                            long outcomes = jdbc.queryForObject("SELECT COUNT(*) FROM demo_outcome WHERE run_id = ?", Long.class, runId);
                            if (runs != 1 || outcomes != 12 || jobs.get(runId).status() != LabJobService.Status.COMPLETED) {
                                throw new IllegalStateException("Committed result checkpoint is incomplete");
                            }
                            checkpointAndPark(checkpoint, mode, runId, "WORKER_DB_COMMITTED_BEFORE_OFFSET",
                                delivery.topic(), delivery.partition(), delivery.offset(), false, runs, outcomes);
                        })
                        : new DispatchWorker(workerJobs, reader, consumer, topic);
                    while (true) { worker.receiveOne(Duration.ofSeconds(1)); }
                } finally { consumer.close(Duration.ofSeconds(5)); }
            }
        }
    }

    private static void checkpointAndPark(Path destination, String mode, String runId, String phase,
                                          String topic, int partition, long offset, boolean activeTransaction,
                                          long runs, long outcomes) {
        String json = "{\"mode\":\"" + mode + "\",\"runId\":\"" + runId + "\",\"phase\":\"" + phase
            + "\",\"topic\":\"" + topic + "\",\"partition\":" + partition + ",\"offset\":" + offset
            + ",\"activeTransaction\":" + activeTransaction + ",\"runRows\":" + runs
            + ",\"outcomeRows\":" + outcomes + "}\n";
        Path pending = destination.resolveSibling("checkpoint.pending-" + ProcessHandle.current().pid());
        try {
            Files.writeString(pending, json, StandardCharsets.UTF_8, StandardOpenOption.CREATE_NEW, StandardOpenOption.WRITE);
            Files.move(pending, destination, StandardCopyOption.ATOMIC_MOVE);
        } catch (Exception failure) {
            throw new IllegalStateException("Could not persist the atomic crash checkpoint", failure);
        }
        // The parent must observe the completed atomic checkpoint before forcibly terminating this JVM.
        while (true) { LockSupport.parkNanos(Duration.ofSeconds(1).toNanos()); }
    }
}
