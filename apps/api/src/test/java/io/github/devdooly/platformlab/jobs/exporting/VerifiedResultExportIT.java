package io.github.devdooly.platformlab.jobs.exporting;

import io.github.devdooly.platformlab.demo.SyntheticScenario;
import io.github.devdooly.platformlab.jobs.CanonicalSource;
import io.github.devdooly.platformlab.jobs.LabJobService;
import io.github.devdooly.platformlab.jobs.S3ClientFactory;
import io.github.devdooly.platformlab.jobs.S3RawSourceStore;
import io.github.devdooly.platformlab.jobs.SourceStagingService;
import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Proxy;
import java.net.URI;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;
import java.security.MessageDigest;
import java.sql.SQLException;
import java.time.Duration;
import java.time.Instant;
import java.time.ZoneId;
import java.util.ArrayList;
import java.util.HexFormat;
import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.UUID;
import java.util.concurrent.TimeUnit;
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
import tools.jackson.databind.JsonNode;
import tools.jackson.databind.json.JsonMapper;
import static org.assertj.core.api.Assertions.*;

/**
 * Opt-in REAL MariaDB/Garage validation. Select -Dlab.export.tests=true
 * -Dtest=VerifiedResultExportIT -DargLine=-Duser.timezone=Asia/Seoul.
 * Default verify does not select *IT. No broker ACK or export completion is fabricated.
 * Every successful completion calls ResultExportService with actual S3 PUT/GET verification.
 */
@SpringBootTest
@ActiveProfiles({"db-test", "worker"})
@EnabledIfSystemProperty(named = "lab.export.tests", matches = "true")
@TestInstance(TestInstance.Lifecycle.PER_CLASS)
class VerifiedResultExportIT {
    private static final JsonMapper JSON = JsonMapper.builder().build();
    private static final String ROLLBACK_MARKER = "EXPORT_IT_FINAL_SLOT_RELEASE_ROLLBACK";
    @Autowired LabJobService jobs;
    @Autowired JdbcTemplate jdbc;
    @Autowired DataSource dataSource;
    @Autowired PlatformTransactionManager transactionManager;
    private final byte[] bytes = CanonicalSource.fixtureBytes();
    private final Set<String> ownedRuns = new LinkedHashSet<>();
    private final Set<String> ownedKeys = new LinkedHashSet<>();
    private final List<Probe> probes = new ArrayList<>();
    private final AtomicInteger exportPuts = new AtomicInteger();
    private S3Client s3;
    private S3RawSourceStore sources;
    private S3ResultExportStore store;
    private String bucket;
    private String runId;
    private String ownedTrigger;
    private ExportBundle bundle;
    private Path privateDirectory;

    @DynamicPropertySource
    static void requireDisposableDatabaseBeforeFlyway(DynamicPropertyRegistry registry) {
        // Guard executes while resolving the URL, before Flyway can contact any database.
        registry.add("spring.datasource.url", VerifiedResultExportIT::disposableDatabaseUrl);
        registry.add("spring.datasource.username", () -> required("DB_TEST_USERNAME"));
        registry.add("spring.datasource.password", () -> required("DB_TEST_PASSWORD"));
    }

    static String disposableDatabaseUrl() {
        String value = required("DB_TEST_URL");
        if (!value.matches("jdbc:mariadb://127\\.0\\.0\\.1:[0-9]{1,5}/platform_lab_export_it")) {
            throw new IllegalArgumentException("DB_TEST_URL requires platform_lab_export_it on numeric loopback without query options");
        }
        requireValidPort(URI.create(value.substring("jdbc:".length()))); return value;
    }

    static URI guardedS3Endpoint() {
        String value = required("LAB_S3_TEST_ENDPOINT");
        if (!value.matches("http://127\\.0\\.0\\.1:[0-9]{1,5}/?")) {
            throw new IllegalArgumentException("LAB_S3_TEST_ENDPOINT requires numeric loopback HTTP");
        }
        URI endpoint = URI.create(value); requireValidPort(endpoint); return endpoint;
    }

    static String guardedBucket() {
        String value = required("LAB_S3_TEST_BUCKET");
        if (!value.matches("platform-lab-s3-test-[a-z0-9-]{1,42}")) {
            throw new IllegalArgumentException("LAB_S3_TEST_BUCKET requires the dedicated platform-lab-s3-test- prefix");
        }
        return value;
    }

    @BeforeAll void requireRealIsolatedServicesAndEmptyJobState() throws Exception {
        assertThat(Runtime.version().feature()).isEqualTo(21);
        assertThat(ZoneId.systemDefault()).isEqualTo(ZoneId.of("Asia/Seoul"));
        try (var connection = dataSource.getConnection()) {
            assertThat(connection.getMetaData().getDatabaseProductName()).isEqualTo("MariaDB");
            assertThat(connection.getCatalog()).isEqualTo("platform_lab_export_it");
        }
        assertEmptyJobs();
        assertThat(jdbc.queryForObject("SELECT COUNT(*) FROM information_schema.TRIGGERS WHERE TRIGGER_SCHEMA = DATABASE()", Long.class)).isZero();
        bucket = guardedBucket();
        s3 = S3ClientFactory.createGarage(guardedS3Endpoint(), "garage", StaticCredentialsProvider.create(
            AwsBasicCredentials.create(required("LAB_S3_TEST_ACCESS_KEY"), required("LAB_S3_TEST_SECRET_KEY"))));
        sources = new S3RawSourceStore(s3, bucket);
        // Counts actual SDK PUTs while forwarding every operation to the real Garage client.
        S3Client counted = (S3Client) Proxy.newProxyInstance(S3Client.class.getClassLoader(), new Class<?>[]{S3Client.class},
            (proxy, method, arguments) -> {
                if (method.getName().equals("putObject")) { exportPuts.incrementAndGet(); }
                try { return method.invoke(s3, arguments); }
                catch (InvocationTargetException failure) { throw failure.getCause(); }
            });
        store = new S3ResultExportStore(counted, bucket);
        privateDirectory = Files.createTempDirectory("platform-lab-export-it-");
    }

    @BeforeEach void chooseUniqueOwnedRunAndRequireCleanState() {
        assertEmptyJobs();
        assertThat(ownedRuns).isEmpty(); assertThat(ownedKeys).isEmpty(); assertThat(probes).isEmpty();
        assertThat(ownedTrigger).isNull(); exportPuts.set(0); bundle = null;
        runId = "export-it-" + UUID.randomUUID(); ownedRuns.add(runId);
    }

    @Test void actualResultAndFailuresAreVerifiedBeforeReleaseAndRepeatsCannotReleaseNextJobsSlot() throws Exception {
        LabJobService.Job completed = prepareCompleted();
        Snapshot before = snapshot(); AtomicInteger verified = new AtomicInteger();
        var coordinator = observingCoordinator(verified);
        LabJobService.Job exported = coordinator.export(runId, completed.sourceSha256());
        assertExportedAndSlotFree(exported);
        assertBusinessUnchanged(before); assertActualDocumentsAndFailureReasons();
        assertThat(verified.get()).isEqualTo(2); assertThat(exportPuts.get()).isEqualTo(2);
        Snapshot after = snapshot(); var objects = objectSnapshot();
        assertThat(coordinator.export(runId, completed.sourceSha256())).isEqualTo(exported);
        assertSnapshot(after); assertObjectSnapshot(objects);
        assertThat(verified.get()).isEqualTo(4); assertThat(exportPuts.get()).isEqualTo(2);
        evidence("verified-export-and-repeat", 0, 2, true);

        String nextRun = "export-it-" + UUID.randomUUID(); ownedRuns.add(nextRun);
        // A real new source upload/admission proves the previous slot was released.
        ownRawKey(nextRun);
        var next = new SourceStagingService(jobs, sources).stage(nextRun, SyntheticScenario.NAME, bytes);
        assertThat(next.status()).isEqualTo(LabJobService.Status.QUEUED);
        var nextRows = jdbc.queryForList("SELECT * FROM lab_outbox WHERE job_run_id = ? ORDER BY id", nextRun);
        assertThat(coordinator.export(runId, completed.sourceSha256())).isEqualTo(exported);
        assertThat(jobs.get(nextRun)).isEqualTo(next);
        assertThat(jdbc.queryForList("SELECT * FROM lab_outbox WHERE job_run_id = ? ORDER BY id", nextRun)).isEqualTo(nextRows);
        assertThat(slotOwner()).isEqualTo(nextRun); assertThat(exportPuts.get()).isEqualTo(2);
        assertBusinessUnchanged(after);
        assertThat(jobs.get(runId)).isEqualTo(after.job()); assertThat(outbox()).isEqualTo(after.outbox());
        assertObjectSnapshot(objects);
        System.out.println("EXPORT_EVIDENCE {\"case\":\"exported-repeat-preserves-next-slot\",\"newJobAdmitted\":true,\"newSlotOwnerPreserved\":true,\"additionalExportPuts\":0}");
    }

    @Test void deliberateSecondFileStorageFailureRetainsPendingSlotAndRetryReusesFirstRealObject() throws Exception {
        LabJobService.Job completed = prepareCompleted(); Snapshot before = snapshot();
        AtomicInteger beforeDb = new AtomicInteger();
        ResultExportStore failSecond = document -> {
            if (document.key().equals(bundle.failures().key())) { throw new DeliberateStorageFailure(); }
            store.storeAndVerify(document); assertRemoteDocument(document);
        };
        var failing = new ResultExportService(jobs, failSecond, document -> assertNoActiveTransaction(), ignored -> beforeDb.incrementAndGet());
        assertThatThrownBy(() -> failing.export(runId, completed.sourceSha256())).isInstanceOf(DeliberateStorageFailure.class);
        assertSnapshot(before); assertPendingAndOccupied(); assertThat(beforeDb.get()).isZero();
        assertThat(exportPuts.get()).isEqualTo(1);
        ObjectState first = remote(bundle.result().key());
        assertThat(remoteKeys("result/" + runId + "/")).containsExactly(bundle.result().key());
        var exported = observingCoordinator(new AtomicInteger()).export(runId, completed.sourceSha256());
        assertExportedAndSlotFree(exported); assertBusinessUnchanged(before); assertActualDocumentsAndFailureReasons();
        assertRemoteUnchanged(bundle.result().key(), first); assertThat(exportPuts.get()).isEqualTo(2);
        evidence("second-file-storage-failure-retry", 0, 2, true);
    }

    @Test void sameSizeCorruptExistingResultIsNeverOverwrittenAndExplicitOwnedFixtureRemovalAllowsRetry() throws Exception {
        LabJobService.Job completed = prepareCompleted(); Snapshot before = snapshot();
        byte[] corrupt = bundle.result().bytes(); corrupt[0] ^= 1;
        s3.putObject(PutObjectRequest.builder().bucket(bucket).key(bundle.result().key()).build(), RequestBody.fromBytes(corrupt));
        assertThatThrownBy(() -> observingCoordinator(new AtomicInteger()).export(runId, completed.sourceSha256()))
            .isInstanceOf(RuntimeException.class);
        assertSnapshot(before); assertPendingAndOccupied(); assertThat(exportPuts.get()).isZero();
        assertThat(remote(bundle.result().key()).bytes()).isEqualTo(corrupt);
        assertThat(remoteKeys("result/" + runId + "/")).containsExactly(bundle.result().key());
        // Only the test removes its own deliberately damaged fixture. The adapter does not repair or overwrite it.
        s3.deleteObject(DeleteObjectRequest.builder().bucket(bucket).key(bundle.result().key()).build());
        var exported = observingCoordinator(new AtomicInteger()).export(runId, completed.sourceSha256());
        assertExportedAndSlotFree(exported); assertBusinessUnchanged(before); assertActualDocumentsAndFailureReasons();
        assertThat(exportPuts.get()).isEqualTo(2); evidence("corrupt-existing-object-explicit-repair", 0, 2, true);
    }

    @Test void actualDatabaseSignalAtFinalSlotReleaseRollsBackExportAckWhileBothVerifiedObjectsSurvive() throws Exception {
        LabJobService.Job completed = prepareCompleted(); Snapshot before = snapshot();
        ownedTrigger = "export_it_fail_" + UUID.randomUUID().toString().replace("-", "");
        jdbc.execute("""
            CREATE TRIGGER %s BEFORE UPDATE ON lab_job_slot FOR EACH ROW
            BEGIN
                DECLARE observed_export VARCHAR(20);
                DECLARE observed_ack VARCHAR(20);
                IF OLD.occupied_run_id = '%s' AND NEW.occupied_run_id IS NULL THEN
                    SELECT export_status INTO observed_export FROM lab_job WHERE run_id = OLD.occupied_run_id;
                    SELECT status INTO observed_ack FROM lab_outbox WHERE job_run_id = OLD.occupied_run_id AND event_type = 'EXPORT';
                    IF observed_export <> 'EXPORTED' OR observed_ack <> 'ACKNOWLEDGED' THEN
                        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'EXPORT_IT_EXPECTED_PRIOR_SQL_MISSING';
                    END IF;
                    SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = '%s';
                END IF;
            END
            """.formatted(quotedTrigger(ownedTrigger), runId, ROLLBACK_MARKER));
        AtomicInteger beforeDb = new AtomicInteger();
        var failing = new ResultExportService(jobs, store, document -> assertNoActiveTransaction(), ignored -> {
            assertNoActiveTransaction(); assertActualDocumentsAndFailureReasons();
            assertSnapshot(before); beforeDb.incrementAndGet();
        });
        try {
            Throwable failure = catchThrowable(() -> failing.export(runId, completed.sourceSha256()));
            assertThat(failure).isInstanceOf(DataAccessException.class);
            assertThat(hasExpectedSqlSignal(failure)).isTrue();
            assertThat(beforeDb.get()).isEqualTo(1); assertThat(exportPuts.get()).isEqualTo(2);
            assertSnapshot(before); assertPendingAndOccupied(); assertActualDocumentsAndFailureReasons();
        } finally { dropOwnedTrigger(); }
        var objects = objectSnapshot();
        var exported = observingCoordinator(new AtomicInteger()).export(runId, completed.sourceSha256());
        assertExportedAndSlotFree(exported); assertBusinessUnchanged(before); assertObjectSnapshot(objects);
        assertThat(exportPuts.get()).isEqualTo(2); evidence("database-ack-slot-release-rollback-retry", 0, 2, true);
    }

    @Test void forciblyKilledExporterAfterFirstRealObjectVerificationRecoversFromFreshJvmBoundary() throws Exception {
        assertKilledExporterRecovers("after-first", "FIRST_OBJECT_VERIFIED_BEFORE_SECOND", 1, 1);
    }

    @Test void forciblyKilledExporterAfterBothRealObjectsVerificationBeforeDbAckReverifiesAndRecovers() throws Exception {
        assertKilledExporterRecovers("before-db", "BOTH_OBJECTS_VERIFIED_BEFORE_DB_ACK", 2, 0);
    }

    private void assertKilledExporterRecovers(String mode, String phase, int expectedObjects, int expectedParentPuts) throws Exception {
        LabJobService.Job completed = prepareCompleted(); Snapshot before = snapshot();
        Probe probe = startProbe(mode); JsonNode checkpoint = awaitCheckpoint(probe, phase);
        assertThat(checkpoint.get("activeTransaction").asBoolean()).isFalse();
        assertThat(checkpoint.get("objectsVerified").asInt()).isEqualTo(expectedObjects);
        assertSnapshot(before); assertPendingAndOccupied();
        var present = objectSnapshotForPresent(expectedObjects); forceKillReadyProbe(probe);
        assertSnapshot(before); assertPendingAndOccupied();
        var exported = observingCoordinator(new AtomicInteger()).export(runId, completed.sourceSha256());
        assertExportedAndSlotFree(exported); assertBusinessUnchanged(before); assertActualDocumentsAndFailureReasons();
        for (var entry : present.entrySet()) { assertRemoteUnchanged(entry.getKey(), entry.getValue()); }
        assertThat(exportPuts.get()).isEqualTo(expectedParentPuts);
        evidence(mode.equals("after-first") ? "exporter-first-object-kill-recovery" : "exporter-both-objects-before-db-kill-recovery", 1, 2, true);
    }

    private LabJobService.Job prepareCompleted() {
        ownRawKey(runId);
        var queued = new SourceStagingService(jobs, sources).stage(runId, SyntheticScenario.NAME, bytes);
        assertThat(sources.readAndVerify(queued)).isEqualTo(bytes);
        var completed = jobs.process(runId, queued.sourceSha256());
        assertThat(completed.status()).isEqualTo(LabJobService.Status.COMPLETED);
        assertThat(completed.exportStatus()).isEqualTo(LabJobService.ExportStatus.PENDING);
        bundle = ExportBundle.from(jobs.exportSnapshot(runId, completed.sourceSha256()));
        ownedKeys.add(bundle.result().key()); ownedKeys.add(bundle.failures().key());
        assertPendingAndOccupied(); return completed;
    }

    private ResultExportService observingCoordinator(AtomicInteger verified) {
        return new ResultExportService(jobs, store, document -> {
            assertNoActiveTransaction(); assertRemoteDocument(document); verified.incrementAndGet();
        }, ignored -> {
            assertNoActiveTransaction(); assertActualDocumentsAndFailureReasons();
            // Exported retries may run while another job owns the slot. No completion state changes before this hook.
            assertThat(jobs.get(runId).exportStatus()).isIn(LabJobService.ExportStatus.PENDING, LabJobService.ExportStatus.EXPORTED);
        });
    }

    private void assertActualDocumentsAndFailureReasons() {
        assertRemoteDocument(bundle.result()); assertRemoteDocument(bundle.failures());
        JsonNode result = JSON.readTree(remote(bundle.result().key()).bytes());
        JsonNode failures = JSON.readTree(remote(bundle.failures().key()).bytes());
        assertThat(result.get("runId").asText()).isEqualTo(runId);
        assertThat(failures.get("runId").asText()).isEqualTo(runId);
        assertThat(result.get("sourceSha256").asText()).isEqualTo(jobs.get(runId).sourceSha256());
        assertThat(failures.get("sourceSha256").asText()).isEqualTo(jobs.get(runId).sourceSha256());
        JsonNode counts = result.get("counts");
        assertThat(counts.get("input").asInt()).isEqualTo(12);
        assertThat(counts.get("success").asInt()).isEqualTo(7);
        assertThat(counts.get("failure").asInt()).isEqualTo(3);
        assertThat(counts.get("duplicate").asInt()).isEqualTo(2);
        assertThat(counts.get("pending").asInt()).isZero();
        assertThat(failures.get("counts")).isEqualTo(counts);
        JsonNode resultRows = result.get("outcomes"), failureRows = failures.get("failures");
        assertThat(resultRows.size()).isEqualTo(12); assertThat(failureRows.size()).isEqualTo(3);
        String[] lines = new String(bytes, StandardCharsets.UTF_8).split("\\n");
        String[] reasons = {"INVALID_TIMESTAMP", "OUT_OF_ORDER", "OUT_OF_RANGE"};
        for (int index = 0; index < 3; index++) {
            JsonNode failure = failureRows.get(index); int sequence = index + 5;
            assertThat(failure.get("sequence").asInt()).isEqualTo(sequence);
            assertThat(failure.get("reason").asText()).isEqualTo(reasons[index]);
            assertThat(failure.get("rawLine").asText()).isEqualTo(lines[sequence - 1]);
            assertThat(failure.get("input")).isEqualTo(JSON.readTree(lines[sequence - 1]));
        }
        for (int index = 0; index < 12; index++) { assertThat(resultRows.get(index).get("sequence").asInt()).isEqualTo(index + 1); }
    }

    private void assertRemoteDocument(ExportBundle.Document document) {
        ObjectState actual = remote(document.key());
        assertThat(actual.bytes()).isEqualTo(document.bytes());
        assertThat(actual.size()).isEqualTo(document.size());
        try { assertThat(HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(actual.bytes()))).isEqualTo(document.sha256()); }
        catch (java.security.NoSuchAlgorithmException impossible) { throw new IllegalStateException(impossible); }
    }

    private ObjectState remote(String key) {
        var actual = s3.getObjectAsBytes(GetObjectRequest.builder().bucket(bucket).key(key).build());
        return new ObjectState(actual.asByteArray(), actual.response().contentLength(), actual.response().eTag(), actual.response().lastModified());
    }

    private Map<String, ObjectState> objectSnapshot() { return objectSnapshotForPresent(2); }
    private Map<String, ObjectState> objectSnapshotForPresent(int count) {
        var result = new LinkedHashMap<String, ObjectState>();
        result.put(bundle.result().key(), remote(bundle.result().key()));
        if (count == 2) { result.put(bundle.failures().key(), remote(bundle.failures().key())); }
        assertThat(remoteKeys("result/" + runId + "/")).containsExactlyInAnyOrderElementsOf(result.keySet());
        return result;
    }
    private void assertObjectSnapshot(Map<String, ObjectState> expected) {
        assertThat(remoteKeys("result/" + runId + "/")).containsExactlyInAnyOrderElementsOf(expected.keySet());
        for (var entry : expected.entrySet()) { assertRemoteUnchanged(entry.getKey(), entry.getValue()); }
    }
    private void assertRemoteUnchanged(String key, ObjectState expected) {
        ObjectState actual = remote(key); assertThat(actual.bytes()).isEqualTo(expected.bytes());
        assertThat(actual.size()).isEqualTo(expected.size()); assertThat(actual.etag()).isEqualTo(expected.etag());
        assertThat(actual.modifiedAt()).isEqualTo(expected.modifiedAt());
    }
    private List<String> remoteKeys(String prefix) {
        var listing = s3.listObjectsV2(ListObjectsV2Request.builder().bucket(bucket).prefix(prefix).build());
        assertThat(listing.isTruncated()).isFalse();
        return listing.contents().stream().map(item -> item.key()).toList();
    }

    private void assertExportedAndSlotFree(LabJobService.Job exported) {
        assertThat(exported.exportStatus()).isEqualTo(LabJobService.ExportStatus.EXPORTED);
        assertThat(exported.exportCompletedAt()).isNotNull(); assertThat(slotOwner()).isNull();
        assertThat(jdbc.queryForObject("SELECT status FROM lab_outbox WHERE job_run_id = ? AND event_type = 'EXPORT'", String.class, runId)).isEqualTo("ACKNOWLEDGED");
        assertThat(jdbc.queryForObject("SELECT CASE WHEN o.acknowledged_at = j.export_completed_at THEN 1 ELSE 0 END FROM lab_outbox o JOIN lab_job j ON j.run_id = o.job_run_id WHERE o.job_run_id = ? AND o.event_type = 'EXPORT'", Integer.class, runId)).isEqualTo(1);
    }
    private void assertPendingAndOccupied() {
        var job = jobs.get(runId); assertThat(job.status()).isEqualTo(LabJobService.Status.COMPLETED);
        assertThat(job.exportStatus()).isEqualTo(LabJobService.ExportStatus.PENDING); assertThat(job.exportCompletedAt()).isNull();
        assertThat(slotOwner()).isEqualTo(runId);
        assertThat(jdbc.queryForObject("SELECT status FROM lab_outbox WHERE job_run_id = ? AND event_type = 'EXPORT'", String.class, runId)).isEqualTo("PENDING");
        assertThat(jdbc.queryForObject("SELECT acknowledged_at FROM lab_outbox WHERE job_run_id = ? AND event_type = 'EXPORT'", java.sql.Timestamp.class, runId)).isNull();
        String rejectedRun = "export-it-" + UUID.randomUUID();
        assertThatThrownBy(() -> jobs.prepareSource(rejectedRun, SyntheticScenario.NAME, bytes))
            .isInstanceOf(LabJobService.SlotBusyException.class);
        assertThat(jdbc.queryForObject("SELECT COUNT(*) FROM lab_job WHERE run_id = ?", Long.class, rejectedRun)).isZero();
    }
    private String slotOwner() { return jdbc.queryForObject("SELECT occupied_run_id FROM lab_job_slot WHERE id = 1", String.class); }
    private List<Map<String, Object>> outbox() { return jdbc.queryForList("SELECT * FROM lab_outbox WHERE job_run_id = ? ORDER BY id", runId); }
    private Snapshot snapshot() {
        return new Snapshot(jobs.get(runId), jdbc.queryForObject("SELECT source_bytes FROM lab_job WHERE run_id = ?", byte[].class, runId), outbox(),
            jdbc.queryForList("SELECT * FROM demo_run WHERE id = ?", runId),
            jdbc.queryForList("SELECT * FROM demo_outcome WHERE run_id = ? ORDER BY input_sequence", runId), slotOwner());
    }
    private void assertSnapshot(Snapshot expected) {
        assertThat(jobs.get(runId)).isEqualTo(expected.job()); assertThat(outbox()).isEqualTo(expected.outbox());
        assertThat(slotOwner()).isEqualTo(expected.slot()); assertBusinessUnchanged(expected);
    }
    private void assertBusinessUnchanged(Snapshot expected) {
        var actual = snapshot(); assertThat(actual.sourceBytes()).isEqualTo(expected.sourceBytes());
        assertThat(actual.runs()).isEqualTo(expected.runs()); assertThat(actual.outcomes()).isEqualTo(expected.outcomes());
        assertThat(actual.job().createdAt()).isEqualTo(expected.job().createdAt());
        assertThat(actual.job().sourceVerifiedAt()).isEqualTo(expected.job().sourceVerifiedAt());
        assertThat(actual.job().queuedAt()).isEqualTo(expected.job().queuedAt());
        assertThat(actual.job().completedAt()).isEqualTo(expected.job().completedAt());
        assertThat(sources.readAndVerify(actual.job())).isEqualTo(bytes);
        assertThat(jdbc.queryForObject("SELECT COUNT(*) FROM demo_run WHERE id = ?", Long.class, runId)).isEqualTo(1);
        assertThat(jdbc.queryForObject("SELECT COUNT(*) FROM demo_outcome WHERE run_id = ?", Long.class, runId)).isEqualTo(12);
    }

    private Probe startProbe(String mode) throws Exception {
        Path folder = Files.createDirectory(privateDirectory.resolve(mode + "-" + UUID.randomUUID()));
        Path checkpoint = folder.resolve("checkpoint.json"), log = folder.resolve("child.log");
        String classpath = System.getProperty("surefire.test.class.path");
        if (classpath == null || classpath.isBlank()) { classpath = System.getProperty("java.class.path"); }
        String binary = System.getProperty("os.name").startsWith("Windows") ? "java.exe" : "java";
        var child = new ProcessBuilder(Path.of(System.getProperty("java.home"), "bin", binary).toString(),
            "-Duser.timezone=Asia/Seoul", "-cp", classpath, ExportCrashProbe.class.getName(), mode, checkpoint.toString(), runId)
            .redirectErrorStream(true).redirectOutput(log.toFile()).start();
        var probe = new Probe(child, checkpoint, mode); probes.add(probe); return probe;
    }
    private JsonNode awaitCheckpoint(Probe probe, String expectedPhase) throws Exception {
        long deadline = System.nanoTime() + Duration.ofSeconds(90).toNanos();
        while (System.nanoTime() < deadline) {
            if (Files.isRegularFile(probe.checkpoint())) {
                var checkpoint = JSON.readTree(Files.readString(probe.checkpoint(), StandardCharsets.UTF_8));
                assertThat(checkpoint.get("mode").asText()).isEqualTo(probe.mode());
                assertThat(checkpoint.get("phase").asText()).isEqualTo(expectedPhase);
                assertThat(checkpoint.get("runId").asText()).isEqualTo(runId);
                assertThat(probe.process().isAlive()).isTrue(); return checkpoint;
            }
            if (!probe.process().isAlive()) { throw new AssertionError("Export probe exited before atomic checkpoint; inspect private temporary child log"); }
            Thread.sleep(100);
        }
        throw new AssertionError("Export probe did not reach its real boundary within 90 seconds");
    }
    private void forceKillReadyProbe(Probe probe) throws Exception {
        assertThat(Files.isRegularFile(probe.checkpoint())).isTrue(); assertThat(probe.process().isAlive()).isTrue();
        probe.process().destroyForcibly(); assertThat(probe.process().waitFor(10, TimeUnit.SECONDS)).isTrue();
        assertThat(probe.process().isAlive()).isFalse(); assertThat(probe.process().exitValue()).isNotZero();
    }

    private void evidence(String caseName, int forcedKills, int objectsVerified, boolean exported) throws Exception {
        String json = "{\"case\":\"" + caseName + "\",\"forcedKills\":" + forcedKills
            + ",\"objectsVerified\":" + objectsVerified + ",\"runRows\":" + jdbc.queryForObject("SELECT COUNT(*) FROM demo_run WHERE id = ?", Long.class, runId)
            + ",\"outcomeRows\":" + jdbc.queryForObject("SELECT COUNT(*) FROM demo_outcome WHERE run_id = ?", Long.class, runId)
            + ",\"exported\":" + exported + ",\"slotFree\":" + (slotOwner() == null)
            + ",\"resultSize\":" + remote(bundle.result().key()).size()
            + ",\"resultSha256\":\"" + bundle.result().sha256() + "\",\"failuresSize\":" + remote(bundle.failures().key()).size()
            + ",\"failuresSha256\":\"" + bundle.failures().sha256() + "\"}\n";
        System.out.print("EXPORT_EVIDENCE " + json);
        String evidencePath = System.getProperty("lab.export.evidence.file");
        if (evidencePath != null && !evidencePath.isBlank()) {
            Files.writeString(Path.of(evidencePath), json, StandardCharsets.UTF_8, StandardOpenOption.CREATE, StandardOpenOption.APPEND, StandardOpenOption.WRITE);
        }
    }

    private String ownRawKey(String id) {
        requireOwnedRun(id); String key = "raw/" + id + "/" + CanonicalSource.validate(bytes).sha256() + ".ndjson";
        ownedKeys.add(key); return key;
    }
    private void assertEmptyJobs() {
        assertThat(jdbc.queryForObject("SELECT COUNT(*) FROM lab_job", Long.class)).isZero();
        assertThat(jdbc.queryForObject("SELECT COUNT(*) FROM lab_outbox", Long.class)).isZero();
        assertThat(jdbc.queryForObject("SELECT COUNT(*) FROM lab_job_slot", Long.class)).isEqualTo(1);
        assertThat(slotOwner()).isNull();
    }

    @AfterEach void removeOnlyOwnedChildrenTriggerObjectsAndDatabaseRows() throws Exception {
        if (runId == null) { return; }
        for (Probe probe : probes) {
            if (probe.process().isAlive()) {
                probe.process().destroyForcibly(); assertThat(probe.process().waitFor(10, TimeUnit.SECONDS)).isTrue();
            }
        }
        probes.clear(); dropOwnedTrigger();
        try {
            if (s3 != null) {
                for (String key : ownedKeys) {
                    boolean owned = ownedRuns.stream().anyMatch(id -> key.startsWith("raw/" + id + "/") || key.startsWith("result/" + id + "/"));
                    if (!owned) { throw new IllegalStateException("Refusing cleanup outside owned UUID run prefixes"); }
                    s3.deleteObject(DeleteObjectRequest.builder().bucket(bucket).key(key).build());
                }
                for (String id : ownedRuns) {
                    assertThat(remoteKeys("raw/" + id + "/")).isEmpty(); assertThat(remoteKeys("result/" + id + "/")).isEmpty();
                }
                ownedKeys.clear();
            }
        } finally {
            new TransactionTemplate(transactionManager).executeWithoutResult(ignored -> {
                String occupied = jdbc.queryForObject("SELECT occupied_run_id FROM lab_job_slot WHERE id = 1 FOR UPDATE", String.class);
                if (occupied != null && !ownedRuns.contains(occupied)) { throw new IllegalStateException("Unexpected occupied test slot"); }
                var remaining = jdbc.queryForList("SELECT run_id FROM lab_job", String.class);
                assertThat(ownedRuns).containsAll(remaining);
                if (occupied != null) { jdbc.update("UPDATE lab_job_slot SET occupied_run_id = NULL WHERE id = 1"); }
                for (String id : ownedRuns) {
                    requireOwnedRun(id);
                    jdbc.update("DELETE FROM lab_outbox WHERE job_run_id = ?", id);
                    jdbc.update("DELETE FROM demo_outcome WHERE run_id = ?", id);
                    jdbc.update("DELETE FROM demo_run WHERE id = ?", id);
                    jdbc.update("DELETE FROM lab_job WHERE run_id = ?", id);
                }
            });
            ownedRuns.clear(); assertEmptyJobs();
        }
    }

    private void dropOwnedTrigger() {
        if (ownedTrigger != null) { jdbc.execute("DROP TRIGGER IF EXISTS " + quotedTrigger(ownedTrigger)); ownedTrigger = null; }
    }
    private static String quotedTrigger(String value) {
        if (!value.matches("export_it_fail_[a-f0-9]{32}")) { throw new IllegalArgumentException("Invalid owned trigger"); }
        return "`" + value + "`";
    }
    private static boolean hasExpectedSqlSignal(Throwable failure) {
        for (Throwable cause = failure; cause != null; cause = cause.getCause()) {
            if (cause instanceof SQLException sql && "45000".equals(sql.getSQLState())
                && sql.getMessage() != null && sql.getMessage().contains(ROLLBACK_MARKER)) { return true; }
        }
        return false;
    }
    @AfterAll void closeExplicitClient() { if (s3 != null) { s3.close(); } }
    static void requireOwnedRun(String value) {
        if (value == null || !value.matches("export-it-[a-f0-9-]{36}")) { throw new IllegalArgumentException("Expected dedicated UUID export test run"); }
    }
    private static void requireValidPort(URI uri) {
        if (uri.getPort() < 1 || uri.getPort() > 65535) { throw new IllegalArgumentException("Invalid numeric loopback test port"); }
    }
    static String required(String name) {
        String value = System.getenv(name);
        if (value == null || value.isBlank()) { throw new IllegalArgumentException(name + " is required for the isolated export test"); }
        return value;
    }
    private static void assertNoActiveTransaction() { assertThat(TransactionSynchronizationManager.isActualTransactionActive()).isFalse(); }
    private static final class DeliberateStorageFailure extends RuntimeException {}
    private record Probe(Process process, Path checkpoint, String mode) {}
    private record ObjectState(byte[] bytes, long size, String etag, Instant modifiedAt) {}
    private record Snapshot(LabJobService.Job job, byte[] sourceBytes, List<Map<String, Object>> outbox,
                            List<Map<String, Object>> runs, List<Map<String, Object>> outcomes, String slot) {}
}
