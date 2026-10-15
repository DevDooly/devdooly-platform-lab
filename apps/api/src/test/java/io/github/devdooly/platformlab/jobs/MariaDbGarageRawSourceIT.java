package io.github.devdooly.platformlab.jobs;

import io.github.devdooly.platformlab.demo.SyntheticScenario;
import java.net.URI;
import java.sql.SQLException;
import java.time.ZoneId;
import java.util.HashSet;
import java.util.Set;
import java.util.UUID;
import java.util.concurrent.atomic.AtomicInteger;
import javax.sql.DataSource;
import org.junit.jupiter.api.AfterAll;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.TestInstance;
import org.junit.jupiter.api.condition.EnabledIfSystemProperty;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.dao.DataAccessException;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.support.TransactionSynchronizationManager;
import org.springframework.transaction.support.TransactionTemplate;
import software.amazon.awssdk.auth.credentials.AwsBasicCredentials;
import software.amazon.awssdk.auth.credentials.StaticCredentialsProvider;
import software.amazon.awssdk.core.sync.RequestBody;
import software.amazon.awssdk.services.s3.S3Client;
import software.amazon.awssdk.services.s3.model.DeleteObjectRequest;
import software.amazon.awssdk.services.s3.model.GetObjectRequest;
import software.amazon.awssdk.services.s3.model.ListObjectsV2Request;
import software.amazon.awssdk.services.s3.model.PutObjectRequest;
import static org.assertj.core.api.Assertions.*;

/**
 * Explicit opt-in against disposable MariaDB and Garage through numeric loopback endpoints.
 * Select with -Dlab.s3.database.tests=true -Dtest=MariaDbGarageRawSourceIT
 * and -DargLine=-Duser.timezone=Asia/Seoul. Default verify does not select *IT.
 * The pre-created database user needs TRIGGER only in its dedicated schema.
 */
@SpringBootTest
@ActiveProfiles({"db-test", "worker"})
@EnabledIfSystemProperty(named = "lab.s3.database.tests", matches = "true")
@TestInstance(TestInstance.Lifecycle.PER_CLASS)
class MariaDbGarageRawSourceIT {
    private static final String ROLLBACK_MARKER = "S3DB_IT_DISPATCH_AFTER_QUEUED";
    private static final String WRONG_STATE_MARKER = "S3DB_IT_EXPECTED_QUEUED_NOT_VISIBLE";
    @Autowired LabJobService jobs;
    @Autowired JdbcTemplate jdbc;
    @Autowired DataSource dataSource;
    @Autowired PlatformTransactionManager transactionManager;
    private final byte[] bytes = CanonicalSource.fixtureBytes();
    private final Set<String> ownedKeys = new HashSet<>();
    private S3Client s3;
    private S3RawSourceStore store;
    private String bucket;
    private String runId;
    private String ownedTrigger;

    @DynamicPropertySource
    static void requireDisposableDatabaseBeforeFlyway(DynamicPropertyRegistry registry) {
        registry.add("spring.datasource.url", MariaDbGarageRawSourceIT::disposableDatabaseUrl);
        registry.add("spring.datasource.username", () -> required("DB_TEST_USERNAME"));
        registry.add("spring.datasource.password", () -> required("DB_TEST_PASSWORD"));
    }

    private static String disposableDatabaseUrl() {
        String url = required("DB_TEST_URL");
        if (!url.matches("jdbc:mariadb://127\\.0\\.0\\.1:[0-9]{1,5}/platform_lab_s3_it(?:_fresh)?")) {
            throw new IllegalArgumentException("DB_TEST_URL must target platform_lab_s3_it or _fresh on a numeric loopback port without query options");
        }
        var uri = URI.create(url.substring("jdbc:".length()));
        if (uri.getPort() < 1 || uri.getPort() > 65535) {
            throw new IllegalArgumentException("Invalid disposable MariaDB port");
        }
        return url;
    }

    @BeforeAll void requireRealIsolatedServicesAndEmptyJobState() throws Exception {
        try (var connection = dataSource.getConnection()) {
            assertThat(connection.getMetaData().getDatabaseProductName()).isEqualTo("MariaDB");
            assertThat(connection.getCatalog()).isIn("platform_lab_s3_it", "platform_lab_s3_it_fresh");
        }
        assertThat(ZoneId.systemDefault()).isEqualTo(ZoneId.of("Asia/Seoul"));
        assertEmptyJobState();
        assertThat(jdbc.queryForObject("""
            SELECT COUNT(*) FROM information_schema.TRIGGERS
            WHERE TRIGGER_SCHEMA = DATABASE() AND EVENT_OBJECT_TABLE = 'lab_outbox'
            """, Long.class)).isZero();

        String endpoint = required("LAB_S3_TEST_ENDPOINT");
        if (!endpoint.matches("http://127\\.0\\.0\\.1:[0-9]{1,5}/?")) {
            throw new IllegalArgumentException("LAB_S3_TEST_ENDPOINT must be http://127.0.0.1:<port>");
        }
        var uri = URI.create(endpoint);
        if (uri.getPort() < 1 || uri.getPort() > 65535) { throw new IllegalArgumentException("Invalid disposable Garage port"); }
        bucket = required("LAB_S3_TEST_BUCKET");
        if (!bucket.matches("platform-lab-s3-test-[a-z0-9-]{1,42}")) {
            throw new IllegalArgumentException("LAB_S3_TEST_BUCKET must use the dedicated platform-lab-s3-test- prefix");
        }
        s3 = S3ClientFactory.createGarage(uri, "garage", StaticCredentialsProvider.create(
            AwsBasicCredentials.create(required("LAB_S3_TEST_ACCESS_KEY"), required("LAB_S3_TEST_SECRET_KEY"))));
        store = new S3RawSourceStore(s3, bucket);
    }

    @BeforeEach void requireCleanStateAndChooseUniqueOwnedRun() {
        runId = null;
        assertEmptyJobState();
        assertThat(ownedKeys).isEmpty();
        assertThat(ownedTrigger).isNull();
        runId = "s3db-it-" + UUID.randomUUID();
    }

    @Test void verifiedSourceAndDispatchCommitTogetherAndAllRepeatMetadataRemainsUnchanged() {
        var externalCalls = new AtomicInteger();
        var staging = coordinator(externalCalls);
        ownSourceKey();
        var queued = staging.stage(runId, SyntheticScenario.NAME, bytes);
        assertQueuedWithSingleDispatch(queued);
        assertRemoteExact(queued);
        var queuedOutbox = jdbc.queryForList("SELECT * FROM lab_outbox WHERE job_run_id = ? ORDER BY id", runId);
        assertThat(staging.stage(runId, SyntheticScenario.NAME, bytes)).isEqualTo(queued);
        assertThat(jdbc.queryForList("SELECT * FROM lab_outbox WHERE job_run_id = ? ORDER BY id", runId)).isEqualTo(queuedOutbox);

        var completed = jobs.process(runId, queued.sourceSha256());
        assertThat(completed.status()).isEqualTo(LabJobService.Status.COMPLETED);
        assertThat(completed.exportStatus()).isEqualTo(LabJobService.ExportStatus.PENDING);
        assertExpectedTwelveOutcomes();
        var result = jdbc.queryForList("SELECT * FROM demo_run WHERE id = ?", runId);
        var outcomes = jdbc.queryForList("SELECT * FROM demo_outcome WHERE run_id = ? ORDER BY input_sequence", runId);
        var outbox = jdbc.queryForList("SELECT * FROM lab_outbox WHERE job_run_id = ? ORDER BY id", runId);
        assertThat(outbox).hasSize(2);
        assertThat(staging.stage(runId, SyntheticScenario.NAME, bytes)).isEqualTo(completed);
        assertRemoteExact(completed);
        assertThat(jdbc.queryForList("SELECT * FROM demo_run WHERE id = ?", runId)).isEqualTo(result);
        assertThat(jdbc.queryForList("SELECT * FROM demo_outcome WHERE run_id = ? ORDER BY input_sequence", runId)).isEqualTo(outcomes);
        assertThat(jdbc.queryForList("SELECT * FROM lab_outbox WHERE job_run_id = ? ORDER BY id", runId)).isEqualTo(outbox);
        assertThat(jdbc.queryForObject("SELECT occupied_run_id FROM lab_job_slot WHERE id = 1", String.class)).isEqualTo(runId);
        assertThat(externalCalls.get()).isEqualTo(3);
    }

    @Test void corruptedExistingObjectKeepsStagingAndSlotUntilExplicitFixtureRemovalAndRetry() {
        var prepared = jobs.prepareSource(runId, SyntheticScenario.NAME, bytes);
        String key = ownSourceKey();
        var corrupt = bytes.clone();
        corrupt[1] ^= 1;
        s3.putObject(PutObjectRequest.builder().bucket(bucket).key(key).build(), RequestBody.fromBytes(corrupt));
        var staging = coordinator(new AtomicInteger());

        assertThatThrownBy(() -> staging.stage(runId, SyntheticScenario.NAME, bytes))
            .isInstanceOf(S3RawSourceStore.SourceVerificationException.class);
        assertStagingUnchanged(prepared);
        assertThat(s3.getObjectAsBytes(GetObjectRequest.builder().bucket(bucket).key(key).build()).asByteArray()).isEqualTo(corrupt);
        // Only this test deletes its own intentionally corrupted object; the adapter never repairs it by overwriting.
        s3.deleteObject(DeleteObjectRequest.builder().bucket(bucket).key(key).build());
        var queued = staging.stage(runId, SyntheticScenario.NAME, bytes);
        assertThat(queued.createdAt()).isEqualTo(prepared.createdAt());
        assertQueuedWithSingleDispatch(queued);
        assertRemoteExact(queued);
    }

    @Test void dispatchInsertSignalAfterQueuedUpdateRollsBackOnlyDatabaseAndSameObjectRetryRecovers() {
        var prepared = jobs.prepareSource(runId, SyntheticScenario.NAME, bytes);
        ownSourceKey();
        var staging = coordinator(new AtomicInteger());
        String trigger = "s3db_it_fail_" + UUID.randomUUID().toString().replace("-", "");
        ownedTrigger = trigger;
        try {
            // A trigger sees the earlier UPDATE in this transaction. The success marker is raised only
            // if that row is already QUEUED, proving failure occurred after the UPDATE rather than before entry.
            jdbc.execute("""
                CREATE TRIGGER %s BEFORE INSERT ON lab_outbox FOR EACH ROW
                BEGIN
                    DECLARE observed_state VARCHAR(20);
                    IF NEW.job_run_id = '%s' AND NEW.event_type = 'DISPATCH' THEN
                        SELECT status INTO observed_state FROM lab_job WHERE run_id = NEW.job_run_id;
                        IF observed_state IS NULL OR observed_state <> 'QUEUED' THEN
                            SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = '%s';
                        END IF;
                        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = '%s';
                    END IF;
                END
                """.formatted(quotedTrigger(trigger), runId, WRONG_STATE_MARKER, ROLLBACK_MARKER));

            Throwable failure = catchThrowable(() -> staging.stage(runId, SyntheticScenario.NAME, bytes));
            assertThat(failure).isInstanceOf(DataAccessException.class);
            assertThat(hasExpectedSqlSignal(failure)).isTrue();
            assertThat(failure).hasStackTraceContaining(ROLLBACK_MARKER);
            assertStagingUnchanged(prepared);
            assertRemoteExact(prepared);
        } finally {
            dropOwnedTrigger();
        }
        var queued = staging.stage(runId, SyntheticScenario.NAME, bytes);
        assertThat(queued.createdAt()).isEqualTo(prepared.createdAt());
        assertQueuedWithSingleDispatch(queued);
        assertRemoteExact(queued);
    }

    /** The wrapper observes committed metadata before and after every real external storage operation. */
    private SourceStagingService coordinator(AtomicInteger calls) {
        return new SourceStagingService(jobs, (job, source) -> {
            assertThat(TransactionSynchronizationManager.isActualTransactionActive()).isFalse();
            assertThat(jobs.get(runId)).isEqualTo(job);
            var outboxBefore = jdbc.queryForList("SELECT * FROM lab_outbox WHERE job_run_id = ? ORDER BY id", runId);
            if (job.status() == LabJobService.Status.STAGING) {
                assertThat(outboxBefore).isEmpty();
                assertThat(job.sourceVerifiedAt()).isNull();
                assertThat(job.queuedAt()).isNull();
            }
            calls.incrementAndGet();
            store.storeAndVerify(job, source);
            assertRemoteExact(job);
            assertThat(TransactionSynchronizationManager.isActualTransactionActive()).isFalse();
            assertThat(jobs.get(runId)).isEqualTo(job);
            assertThat(jdbc.queryForList("SELECT * FROM lab_outbox WHERE job_run_id = ? ORDER BY id", runId)).isEqualTo(outboxBefore);
        });
    }

    private void assertQueuedWithSingleDispatch(LabJobService.Job queued) {
        assertThat(queued.status()).isEqualTo(LabJobService.Status.QUEUED);
        assertThat(queued.sourceVerifiedAt()).isNotNull().isEqualTo(queued.queuedAt());
        assertThat(queued.completedAt()).isNull();
        var events = jobs.pendingOutbox(100);
        assertThat(events).hasSize(1);
        var dispatch = events.getFirst();
        assertThat(dispatch.runId()).isEqualTo(runId);
        assertThat(dispatch.eventType()).isEqualTo(LabJobService.EventType.DISPATCH);
        assertThat(dispatch.sourceSha256()).isEqualTo(queued.sourceSha256());
        assertThat(dispatch.status()).isEqualTo(LabJobService.OutboxStatus.PENDING);
        assertThat(dispatch.createdAt()).isEqualTo(queued.queuedAt());
        assertThat(dispatch.acknowledgedAt()).isNull();
        assertThat(jdbc.queryForObject("SELECT COUNT(*) FROM lab_outbox WHERE job_run_id = ?", Long.class, runId)).isEqualTo(1L);
        assertThat(jdbc.queryForObject("SELECT source_bytes FROM lab_job WHERE run_id = ?", byte[].class, runId)).isEqualTo(bytes);
        assertThat(jdbc.queryForObject("SELECT occupied_run_id FROM lab_job_slot WHERE id = 1", String.class)).isEqualTo(runId);
    }

    private void assertStagingUnchanged(LabJobService.Job prepared) {
        assertThat(prepared.status()).isEqualTo(LabJobService.Status.STAGING);
        assertThat(jobs.get(runId)).isEqualTo(prepared);
        assertThat(jdbc.queryForObject("SELECT source_bytes FROM lab_job WHERE run_id = ?", byte[].class, runId)).isEqualTo(bytes);
        assertThat(jdbc.queryForObject("SELECT COUNT(*) FROM lab_outbox", Long.class)).isZero();
        assertThat(jdbc.queryForObject("SELECT occupied_run_id FROM lab_job_slot WHERE id = 1", String.class)).isEqualTo(runId);
        assertThat(jdbc.queryForObject("SELECT COUNT(*) FROM demo_run WHERE id = ?", Long.class, runId)).isZero();
        assertThat(jdbc.queryForObject("SELECT COUNT(*) FROM demo_outcome WHERE run_id = ?", Long.class, runId)).isZero();
    }

    private void assertExpectedTwelveOutcomes() {
        var run = jdbc.queryForMap("SELECT * FROM demo_run WHERE id = ?", runId);
        assertThat(((Number) run.get("input_count")).intValue()).isEqualTo(12);
        assertThat(((Number) run.get("success_count")).intValue()).isEqualTo(7);
        assertThat(((Number) run.get("failure_count")).intValue()).isEqualTo(3);
        assertThat(((Number) run.get("duplicate_count")).intValue()).isEqualTo(2);
        assertThat(((Number) run.get("pending_count")).intValue()).isZero();
        assertThat(jdbc.queryForObject("""
            SELECT CASE WHEN j.completed_at = d.completed_at THEN 1 ELSE 0 END
            FROM lab_job j JOIN demo_run d ON d.id = j.run_id WHERE j.run_id = ?
            """, Integer.class, runId)).isEqualTo(1);
        var outcomes = jdbc.queryForList("SELECT * FROM demo_outcome WHERE run_id = ? ORDER BY input_sequence", runId);
        assertThat(outcomes).hasSize(12);
        assertThat(outcomes).extracting(row -> row.get("status")).containsExactly(
            "SUCCESS", "SUCCESS", "SUCCESS", "DUPLICATE", "FAILED", "FAILED", "FAILED",
            "SUCCESS", "SUCCESS", "SUCCESS", "DUPLICATE", "SUCCESS");
        assertThat(outcomes).extracting(row -> row.get("reason")).containsExactly(
            "ACCEPTED", "ACCEPTED", "ACCEPTED", "DUPLICATE_EVENT_ID", "INVALID_TIMESTAMP", "OUT_OF_ORDER",
            "OUT_OF_RANGE", "ACCEPTED", "ACCEPTED", "ACCEPTED", "DUPLICATE_EVENT_ID", "ACCEPTED");
    }

    private void assertRemoteExact(LabJobService.Job job) {
        var remote = s3.getObjectAsBytes(GetObjectRequest.builder().bucket(bucket).key(job.sourceObjectKey()).build());
        byte[] actual = remote.asByteArray();
        assertThat(actual).isEqualTo(bytes);
        assertThat(remote.response().contentLength()).isEqualTo((long) job.sourceSize());
        var verified = CanonicalSource.validate(actual);
        assertThat(verified.size()).isEqualTo(job.sourceSize());
        assertThat(verified.sha256()).isEqualTo(job.sourceSha256());
    }

    private String ownSourceKey() {
        String key = "raw/" + runId + "/" + CanonicalSource.validate(bytes).sha256() + ".ndjson";
        ownedKeys.add(key);
        return key;
    }

    private void assertEmptyJobState() {
        assertThat(jdbc.queryForObject("SELECT COUNT(*) FROM lab_job", Long.class)).isZero();
        assertThat(jdbc.queryForObject("SELECT COUNT(*) FROM lab_outbox", Long.class)).isZero();
        assertThat(jdbc.queryForObject("SELECT COUNT(*) FROM lab_job_slot", Long.class)).isEqualTo(1L);
        assertThat(jdbc.queryForObject("SELECT occupied_run_id FROM lab_job_slot WHERE id = 1", String.class)).isNull();
    }

    @AfterEach void removeOnlyOwnedTriggerObjectsAndRunRows() {
        if (runId == null) { return; }
        try {
            dropOwnedTrigger();
            String prefix = "raw/" + runId + "/";
            if (s3 != null) {
                for (String key : ownedKeys) {
                    if (!key.startsWith(prefix)) { throw new IllegalStateException("Refusing cleanup outside this test run"); }
                    s3.deleteObject(DeleteObjectRequest.builder().bucket(bucket).key(key).build());
                }
                assertThat(s3.listObjectsV2(ListObjectsV2Request.builder().bucket(bucket).prefix(prefix).build()).contents()).isEmpty();
                ownedKeys.clear();
            }
        } finally {
            new TransactionTemplate(transactionManager).executeWithoutResult(ignored -> {
                String occupied = jdbc.queryForObject("SELECT occupied_run_id FROM lab_job_slot WHERE id = 1 FOR UPDATE", String.class);
                if (occupied != null && !runId.equals(occupied)) { throw new IllegalStateException("Unexpected occupied test slot"); }
                assertThat(jdbc.queryForObject("SELECT COUNT(*) FROM lab_job WHERE run_id <> ?", Long.class, runId)).isZero();
                assertThat(jdbc.queryForObject("SELECT COUNT(*) FROM lab_outbox WHERE job_run_id <> ?", Long.class, runId)).isZero();
                if (occupied != null) { jdbc.update("UPDATE lab_job_slot SET occupied_run_id = NULL WHERE id = 1"); }
                jdbc.update("DELETE FROM lab_outbox WHERE job_run_id = ?", runId);
                jdbc.update("DELETE FROM demo_outcome WHERE run_id = ?", runId);
                jdbc.update("DELETE FROM demo_run WHERE id = ?", runId);
                jdbc.update("DELETE FROM lab_job WHERE run_id = ?", runId);
            });
            assertEmptyJobState();
        }
    }

    private void dropOwnedTrigger() {
        if (ownedTrigger != null) {
            jdbc.execute("DROP TRIGGER IF EXISTS " + quotedTrigger(ownedTrigger));
            ownedTrigger = null;
        }
    }

    private static String quotedTrigger(String name) {
        if (!name.matches("s3db_it_fail_[a-f0-9]{32}")) { throw new IllegalArgumentException("Invalid owned trigger identifier"); }
        return "`" + name + "`";
    }

    private static boolean hasExpectedSqlSignal(Throwable failure) {
        for (Throwable cause = failure; cause != null; cause = cause.getCause()) {
            if (cause instanceof SQLException sql && "45000".equals(sql.getSQLState())
                && sql.getMessage() != null && sql.getMessage().contains(ROLLBACK_MARKER)) {
                return true;
            }
        }
        return false;
    }

    @AfterAll void closeExplicitClient() { if (s3 != null) { s3.close(); } }

    private static String required(String name) {
        String value = System.getenv(name);
        if (value == null || value.isBlank()) { throw new IllegalArgumentException(name + " is required for disposable MariaDB/Garage validation"); }
        return value;
    }
}
