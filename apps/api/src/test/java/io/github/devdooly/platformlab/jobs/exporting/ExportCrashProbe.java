package io.github.devdooly.platformlab.jobs.exporting;

import io.github.devdooly.platformlab.PlatformLabApplication;
import io.github.devdooly.platformlab.jobs.LabJobService;
import io.github.devdooly.platformlab.jobs.S3ClientFactory;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardCopyOption;
import java.nio.file.StandardOpenOption;
import java.time.Duration;
import java.time.ZoneId;
import java.util.Map;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.locks.LockSupport;
import javax.sql.DataSource;
import org.springframework.boot.WebApplicationType;
import org.springframework.boot.builder.SpringApplicationBuilder;
import org.springframework.core.env.MapPropertySource;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.transaction.support.TransactionSynchronizationManager;
import software.amazon.awssdk.auth.credentials.AwsBasicCredentials;
import software.amazon.awssdk.auth.credentials.StaticCredentialsProvider;
import software.amazon.awssdk.services.s3.S3Client;
import software.amazon.awssdk.services.s3.model.GetObjectRequest;

/** Child JVM for the opt-in real export IT. No HTTP server or scheduler is started. */
public final class ExportCrashProbe {
    private ExportCrashProbe() {}

    public static void main(String[] args) throws Exception {
        if (args.length != 3) { throw new IllegalArgumentException("Expected mode, private checkpoint and run ID"); }
        String mode = args[0], runId = args[2];
        if (!mode.equals("after-first") && !mode.equals("before-db")) { throw new IllegalArgumentException("Unknown crash probe mode"); }
        VerifiedResultExportIT.requireOwnedRun(runId);
        Path checkpoint = Path.of(args[1]).toAbsolutePath().normalize();
        if (!checkpoint.getFileName().toString().equals("checkpoint.json") || Files.exists(checkpoint)) {
            throw new IllegalArgumentException("Checkpoint must be a fresh private checkpoint.json");
        }
        // Resolve all guards before creating the Spring context/Flyway connection.
        String databaseUrl = VerifiedResultExportIT.disposableDatabaseUrl();
        var endpoint = VerifiedResultExportIT.guardedS3Endpoint();
        String bucket = VerifiedResultExportIT.guardedBucket();
        if (Runtime.version().feature() != 21 || !ZoneId.of("Asia/Seoul").equals(ZoneId.systemDefault())) {
            throw new IllegalStateException("Probe requires Java 21 and Asia/Seoul timezone");
        }
        try (var context = new SpringApplicationBuilder(PlatformLabApplication.class)
                .web(WebApplicationType.NONE).profiles("db-test", "worker")
                .properties("logging.level.root=WARN")
                .initializers(applicationContext -> applicationContext.getEnvironment().getPropertySources()
                    .addFirst(new MapPropertySource("guarded-disposable-export-probe-database", Map.of(
                        "spring.datasource.url", databaseUrl,
                        "spring.datasource.username", VerifiedResultExportIT.required("DB_TEST_USERNAME"),
                        "spring.datasource.password", VerifiedResultExportIT.required("DB_TEST_PASSWORD")))))
                .run()) {
            try (var connection = context.getBean(DataSource.class).getConnection()) {
                if (!"MariaDB".equals(connection.getMetaData().getDatabaseProductName())
                    || !"platform_lab_export_it".equals(connection.getCatalog())) {
                    throw new IllegalStateException("Probe requires the disposable MariaDB schema");
                }
            }
            LabJobService jobs = context.getBean(LabJobService.class);
            JdbcTemplate jdbc = context.getBean(JdbcTemplate.class);
            var job = jobs.get(runId);
            if (job.status() != LabJobService.Status.COMPLETED || job.exportStatus() != LabJobService.ExportStatus.PENDING) {
                throw new IllegalStateException("Probe requires the parent's prepared pending export");
            }
            ExportBundle bundle = ExportBundle.from(jobs.exportSnapshot(runId, job.sourceSha256()));
            try (S3Client s3 = S3ClientFactory.createGarage(endpoint, "garage", StaticCredentialsProvider.create(
                    AwsBasicCredentials.create(VerifiedResultExportIT.required("LAB_S3_TEST_ACCESS_KEY"),
                        VerifiedResultExportIT.required("LAB_S3_TEST_SECRET_KEY"))))) {
                var store = new S3ResultExportStore(s3, bucket); var verified = new AtomicInteger();
                var exporter = new ResultExportService(jobs, store, document -> {
                    requireOutsideTransaction();
                    byte[] actual = s3.getObjectAsBytes(GetObjectRequest.builder().bucket(bucket).key(document.key()).build()).asByteArray();
                    if (!java.util.Arrays.equals(actual, document.bytes())) { throw new IllegalStateException("Probe object differs from its expected document"); }
                    int count = verified.incrementAndGet();
                    if (mode.equals("after-first") && count == 1) {
                        if (!document.key().equals(bundle.result().key())) { throw new IllegalStateException("First verified file must be the result"); }
                        requirePendingState(jobs, jdbc, runId);
                        checkpointAndPark(checkpoint, mode, runId, "FIRST_OBJECT_VERIFIED_BEFORE_SECOND", count);
                    }
                }, ignored -> {
                    requireOutsideTransaction();
                    if (verified.get() != 2) { throw new IllegalStateException("Both objects must have been independently verified"); }
                    requirePendingState(jobs, jdbc, runId);
                    if (mode.equals("before-db")) {
                        checkpointAndPark(checkpoint, mode, runId, "BOTH_OBJECTS_VERIFIED_BEFORE_DB_ACK", verified.get());
                    }
                });
                exporter.export(runId, job.sourceSha256());
                throw new IllegalStateException("Export probe unexpectedly returned without parking at its selected boundary");
            }
        }
    }

    private static void requirePendingState(LabJobService jobs, JdbcTemplate jdbc, String runId) {
        var job = jobs.get(runId);
        if (job.exportStatus() != LabJobService.ExportStatus.PENDING || job.exportCompletedAt() != null
            || !runId.equals(jdbc.queryForObject("SELECT occupied_run_id FROM lab_job_slot WHERE id = 1", String.class))
            || !"PENDING".equals(jdbc.queryForObject("SELECT status FROM lab_outbox WHERE job_run_id = ? AND event_type = 'EXPORT'", String.class, runId))) {
            throw new IllegalStateException("Pre-ack checkpoint lost its pending export or owned slot");
        }
        if (jdbc.queryForObject("SELECT COUNT(*) FROM demo_run WHERE id = ?", Long.class, runId) != 1
            || jdbc.queryForObject("SELECT COUNT(*) FROM demo_outcome WHERE run_id = ?", Long.class, runId) != 12) {
            throw new IllegalStateException("Expected one committed run with twelve outcomes");
        }
    }

    private static void requireOutsideTransaction() {
        if (TransactionSynchronizationManager.isActualTransactionActive()) {
            throw new IllegalStateException("External verification must be outside a database transaction");
        }
    }

    private static void checkpointAndPark(Path destination, String mode, String runId, String phase, int objectsVerified) {
        boolean active = TransactionSynchronizationManager.isActualTransactionActive();
        String json = "{\"mode\":\"" + mode + "\",\"runId\":\"" + runId + "\",\"phase\":\"" + phase
            + "\",\"objectsVerified\":" + objectsVerified + ",\"activeTransaction\":" + active + "}\n";
        Path pending = destination.resolveSibling("checkpoint.pending-" + ProcessHandle.current().pid());
        try {
            Files.writeString(pending, json, StandardCharsets.UTF_8, StandardOpenOption.CREATE_NEW, StandardOpenOption.WRITE);
            Files.move(pending, destination, StandardCopyOption.ATOMIC_MOVE);
        } catch (Exception failure) { throw new IllegalStateException("Could not persist atomic export checkpoint", failure); }
        // Only the parent, after observing this checkpoint and pending DB state, kills the child JVM.
        while (true) { LockSupport.parkNanos(Duration.ofSeconds(1).toNanos()); }
    }
}
