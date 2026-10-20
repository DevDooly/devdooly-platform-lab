package io.github.devdooly.platformlab.jobs.runtime;

import io.github.devdooly.platformlab.demo.SyntheticScenario;
import io.github.devdooly.platformlab.jobs.CanonicalSource;
import io.github.devdooly.platformlab.jobs.LabJobService;
import io.github.devdooly.platformlab.jobs.S3ClientFactory;
import io.github.devdooly.platformlab.jobs.S3RawSourceStore;
import io.github.devdooly.platformlab.jobs.SourceStagingService;
import io.github.devdooly.platformlab.jobs.exporting.ExportBundle;
import io.github.devdooly.platformlab.jobs.exporting.RuntimeProcessProbe;
import io.github.devdooly.platformlab.jobs.messaging.DispatchPublisher;
import io.github.devdooly.platformlab.jobs.messaging.ExportIntegrityRuntimeProbe;
import io.github.devdooly.platformlab.jobs.messaging.KafkaClientFactory;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.LinkOption;
import java.nio.file.Path;
import java.nio.file.attribute.PosixFilePermissions;
import java.security.MessageDigest;
import java.time.Duration;
import java.time.ZoneId;
import java.util.ArrayList;
import java.util.HexFormat;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.Set;
import java.util.UUID;
import java.util.concurrent.TimeUnit;
import java.util.function.BooleanSupplier;
import javax.sql.DataSource;
import org.apache.kafka.clients.admin.Admin;
import org.apache.kafka.clients.admin.ListOffsetsOptions;
import org.apache.kafka.clients.admin.NewTopic;
import org.apache.kafka.clients.admin.OffsetSpec;
import org.apache.kafka.common.IsolationLevel;
import org.apache.kafka.common.TopicPartition;
import org.apache.kafka.common.Uuid;
import org.apache.kafka.common.errors.GroupIdNotFoundException;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.Timeout;
import org.junit.jupiter.api.condition.EnabledIfSystemProperty;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import software.amazon.awssdk.auth.credentials.AwsBasicCredentials;
import software.amazon.awssdk.auth.credentials.StaticCredentialsProvider;
import software.amazon.awssdk.core.sync.RequestBody;
import software.amazon.awssdk.core.sync.ResponseTransformer;
import software.amazon.awssdk.services.s3.S3Client;
import software.amazon.awssdk.services.s3.model.DeleteObjectRequest;
import software.amazon.awssdk.services.s3.model.GetObjectRequest;
import software.amazon.awssdk.services.s3.model.GetObjectResponse;
import software.amazon.awssdk.services.s3.model.ListObjectsV2Request;
import software.amazon.awssdk.services.s3.model.PutObjectRequest;
import software.amazon.awssdk.services.s3.model.S3Exception;
import tools.jackson.databind.JsonNode;
import tools.jackson.databind.json.JsonMapper;
import static org.assertj.core.api.Assertions.assertThat;

/** One opt-in isolated export-integrity experiment. Fixture processing is a direct DB call, never a claimed consumer delivery. */
@SpringBootTest(properties = "logging.level.root=WARN")
@ActiveProfiles({"db-test", "worker"})
@EnabledIfSystemProperty(named = "lab.export-integrity.tests", matches = "true")
public class ExportIntegrityRuntimeIT {
    private static final JsonMapper JSON = JsonMapper.builder().build();
    private static final Set<String> COMMON_KEYS = Set.of("schemaVersion", "sourceCommit", "runId", "nonce", "phase");
    private static final Set<String> EXIT_KEYS = Set.of("schemaVersion", "sourceCommit", "runId", "nonce", "phase",
        "resourcesClosed", "runtimeStatus", "runtimeStage", "failureCode", "verificationFailures", "completedReplays");
    @Autowired LabJobService jobs;
    @Autowired JdbcTemplate jdbc;
    @Autowired DataSource dataSource;
    private final byte[] source = CanonicalSource.fixtureBytes();
    private final List<Child> children = new ArrayList<>();
    private S3Client s3;
    private S3RawSourceStore raw;
    private Admin kafka;
    private String sourceCommit;
    private String bucket;
    private String topic;
    private String group;
    private String clusterId;
    private Uuid topicId;
    private Path privateDirectory;
    private long testDeadline;
    private Map<String, Object> admissionBaseline;
    private FailurePhase failurePhase = FailurePhase.TEST_ENTRY;
    private enum FailurePhase {
        TEST_ENTRY, SERVICE_GUARDS, KAFKA_CREATE, COORDINATOR_READY, STAGE_INPUT, DISPATCH_ACK,
        DIRECT_DB_FIXTURE, CORRUPT_FIXTURE, FIRST_DAEMON, FIRST_PAUSE, FIRST_RUN_REFUSAL,
        UNREPAIRED_RESUME, SECOND_DAEMON, SECOND_PAUSE, SECOND_RUN_REFUSAL, EXPLICIT_REPAIR,
        REPAIRED_RESUME, START_RECOVERY, VERIFY_EXPORT, VERIFY_FINAL_OFFSET, STOP_RECOVERY,
        FINAL_INVARIANTS, CLOSE_CLIENTS
    }
    private enum FailureKind {
        ASSERTION, INTERRUPTED, SQL, GROUP_NOT_FOUND, UNKNOWN_TOPIC,
        COORDINATOR_NOT_AVAILABLE, COORDINATOR_LOAD_IN_PROGRESS, NOT_COORDINATOR,
        TIMEOUT, KAFKA_OTHER, OTHER
    }

    @DynamicPropertySource static void guardBeforeFlyway(DynamicPropertyRegistry registry) {
        ContinuousRuntimeIT.disposableDatabaseUrl(); ContinuousRuntimeIT.guardedS3Endpoint();
        ContinuousRuntimeIT.guardedBootstrap(); ContinuousRuntimeIT.guardedBucket(); ContinuousRuntimeIT.guardedSourceCommit();
        registry.add("spring.datasource.url", ContinuousRuntimeIT::disposableDatabaseUrl);
        registry.add("spring.datasource.username", () -> ContinuousRuntimeIT.required("DB_TEST_USERNAME"));
        registry.add("spring.datasource.password", () -> ContinuousRuntimeIT.required("DB_TEST_PASSWORD"));
    }

    @Test
    @Timeout(value = 420, unit = TimeUnit.SECONDS)
    void corruptPendingExportPersistsPauseUntilExplicitRepairAndResume() throws Exception {
        testDeadline = System.nanoTime() + Duration.ofSeconds(400).toNanos();
        try {
            performExperiment();
            failurePhase = FailurePhase.CLOSE_CLIENTS;
            closeOwnedChildrenAndClients();
            remainingMillis();
            emitSuccess();
        } catch (Throwable failure) {
            if (failure instanceof InterruptedException) { Thread.currentThread().interrupt(); }
            System.out.println("EXPORT_INTEGRITY_RUNTIME_RESULT {\"schemaVersion\":1,\"status\":\"FAIL\",\"failureCode\":\"VALIDATION_FAILED\",\"failurePhase\":\"" + failurePhase.name()
                + "\",\"failureKind\":\"" + failureKind(failure).name() + "\",\"failureSourceLine\":" + failureSourceLine(failure) + "}");
            throw new AssertionError("Export integrity runtime validation failed; inspect private diagnostics");
        } finally {
            try { closeOwnedChildrenAndClients(); }
            catch (Throwable failure) { throw new AssertionError("Owned child or client cleanup failed; inspect private diagnostics"); }
        }
    }

    private void performExperiment() throws Exception {
        failurePhase = FailurePhase.SERVICE_GUARDS;
        requireEmptyDedicatedSchemaAndPristinePolicy();
        sourceCommit = ContinuousRuntimeIT.guardedSourceCommit(); bucket = ContinuousRuntimeIT.guardedBucket();
        privateDirectory = ExportIntegrityRuntimeProbe.controlDirectory();
        try (var files = Files.list(privateDirectory)) { assertThat(files.toList()).isEmpty(); }
        s3 = S3ClientFactory.createGarage(ContinuousRuntimeIT.guardedS3Endpoint(), "garage", StaticCredentialsProvider.create(
            AwsBasicCredentials.create(ContinuousRuntimeIT.required("LAB_S3_TEST_ACCESS_KEY"), ContinuousRuntimeIT.required("LAB_S3_TEST_SECRET_KEY"))));
        raw = new S3RawSourceStore(s3, bucket);
        kafka = ContinuousRuntimeIT.admin(); ContinuousRuntimeIT.requireExpectedCluster(kafka);
        failurePhase = FailurePhase.KAFKA_CREATE;
        clusterId = kafka.describeCluster().clusterId().get(rpcMillis(), TimeUnit.MILLISECONDS);
        assertThat(clusterId).isEqualTo(ContinuousRuntimeIT.required("LAB_KAFKA_TEST_CLUSTER_ID"));
        String identity = UUID.randomUUID().toString();
        topic = "platform-lab-runtime-test-topic-" + identity; group = "platform-lab-runtime-test-group-" + identity;
        ContinuousRuntimeIT.requireOwnedName(topic); ContinuousRuntimeIT.requireOwnedName(group);
        kafka.createTopics(List.of(new NewTopic(topic, 1, (short) 1).configs(Map.of(
            "retention.ms", "3600000", "retention.bytes", "8388608", "max.message.bytes", "1024")))).all().get(rpcMillis(), TimeUnit.MILLISECONDS);
        var actual = kafka.describeTopics(List.of(topic)).allTopicNames().get(rpcMillis(), TimeUnit.MILLISECONDS).get(topic);
        assertThat(actual.partitions()).hasSize(1); assertThat(actual.partitions().getFirst().partition()).isZero();
        assertThat(actual.partitions().getFirst().replicas()).hasSize(1); topicId = actual.topicId();
        assertThat(topicId).isNotEqualTo(Uuid.ZERO_UUID); assertThat(readCommittedEnd()).isZero();
        failurePhase = FailurePhase.COORDINATOR_READY;
        requireInitiallyEmptyGroup();

        failurePhase = FailurePhase.STAGE_INPUT;
        String run = "runtime-it-" + UUID.randomUUID(); ContinuousRuntimeIT.requireOwnedRun(run);
        var queued = new SourceStagingService(jobs, raw).stage(run, SyntheticScenario.NAME, source);
        assertThat(queued.status()).isEqualTo(LabJobService.Status.QUEUED);
        assertThat(queued.exportStatus()).isEqualTo(LabJobService.ExportStatus.NOT_REQUESTED);
        assertThat(raw.readAndVerify(queued)).isEqualTo(source); assertSourceUnchanged(run);
        failurePhase = FailurePhase.DISPATCH_ACK;
        var producer = KafkaClientFactory.producer(ContinuousRuntimeIT.guardedBootstrap());
        try {
            var published = new DispatchPublisher(jobs, producer, topic).publishOne().orElseThrow();
            assertThat(published.topic()).isEqualTo(topic); assertThat(published.partition()).isZero(); assertThat(published.offset()).isZero();
        } finally { producer.close(Duration.ofSeconds(10)); }
        assertThat(readCommittedEnd()).isEqualTo(1L); assertThat(committedOffset()).isEmpty();
        assertDispatchAcknowledged(run);
        failurePhase = FailurePhase.DIRECT_DB_FIXTURE;
        // This is actual fixture DB processing; no consumer has received this one broker message yet.
        var completed = jobs.process(run, queued.sourceSha256());
        assertThat(completed.status()).isEqualTo(LabJobService.Status.COMPLETED);
        assertCompletedPending(run); assertCounts(run);
        var expected = bundle(run); assertThat(remoteKeys(run)).isEmpty();
        admissionBaseline = jdbc.queryForMap("SELECT * FROM lab_admission_policy WHERE id=1");
        var business = businessSnapshot();

        failurePhase = FailurePhase.CORRUPT_FIXTURE;
        byte[] corrupt = expected.result().bytes(); corrupt[0] ^= 1;
        assertThat(corrupt).hasSameSizeAs(expected.result().bytes());
        assertThat(hash(corrupt)).isNotEqualTo(expected.result().sha256());
        String corruptKey = expected.result().key(); assertThat(corruptKey).startsWith("result/" + run + "/");
        s3.putObject(PutObjectRequest.builder().bucket(bucket).key(corruptKey).contentType("application/json").build(), RequestBody.fromBytes(corrupt));
        var corruptObject = remote(corruptKey);
        assertThat(corruptObject.bytes()).isEqualTo(corrupt); assertThat(corruptObject.size()).isEqualTo((long) expected.result().size());
        assertThat(expected.result().matches(corruptObject.bytes())).isFalse();
        assertThat(remoteKeys(run)).containsExactly(corruptKey); requireMissing(expected.failures().key());
        assertPreserved(run, business, expected); assertNoConsumerProgress();

        failurePhase = FailurePhase.FIRST_DAEMON;
        Child first = startDaemon(run); awaitReady(first); awaitExited(first, false, 75);
        failurePhase = FailurePhase.FIRST_PAUSE;
        assertDaemonExit(first, true); assertPaused(); assertLeaseAvailable();
        assertCorruptPending(run, business, expected, corruptObject); assertNoConsumerProgress();
        failurePhase = FailurePhase.FIRST_RUN_REFUSAL;
        assertRunRefused(run, business, expected, corruptObject);
        failurePhase = FailurePhase.UNREPAIRED_RESUME;
        resumeOriginal();
        assertCorruptPending(run, business, expected, corruptObject); assertNoConsumerProgress();

        failurePhase = FailurePhase.SECOND_DAEMON;
        Child second = startDaemon(run); awaitReady(second); awaitExited(second, false, 75);
        failurePhase = FailurePhase.SECOND_PAUSE;
        assertDaemonExit(second, true); assertPaused(); assertLeaseAvailable();
        assertCorruptPending(run, business, expected, corruptObject); assertNoConsumerProgress();
        failurePhase = FailurePhase.SECOND_RUN_REFUSAL;
        assertRunRefused(run, business, expected, corruptObject);

        failurePhase = FailurePhase.EXPLICIT_REPAIR;
        assertThat(children).allSatisfy(child -> assertThat(child.process().isAlive()).isFalse());
        assertPaused(); assertLeaseAvailable();
        assertCorruptPending(run, business, expected, corruptObject); assertNoConsumerProgress();
        ContinuousRuntimeIT.requireOwnedRun(run);
        assertThat(expected.result().key()).isEqualTo(corruptKey); assertThat(hash(remote(corruptKey).bytes())).isEqualTo(hash(corrupt));
        // Only the parent fixture deletes its exact deliberately damaged key. Production code performs no repair.
        s3.deleteObject(DeleteObjectRequest.builder().bucket(bucket).key(corruptKey).build());
        requireMissing(corruptKey); requireMissing(expected.failures().key()); assertThat(remoteKeys(run)).isEmpty();
        assertPreserved(run, business, expected); assertCompletedPending(run);
        failurePhase = FailurePhase.REPAIRED_RESUME;
        resumeOriginal(); assertPreserved(run, business, expected);

        failurePhase = FailurePhase.START_RECOVERY;
        Child recovery = startDaemon(run); awaitReady(recovery);
        failurePhase = FailurePhase.VERIFY_EXPORT;
        await(() -> { assertThat(recovery.process().isAlive()).isTrue(); return jobs.get(run).exportStatus() == LabJobService.ExportStatus.EXPORTED; }, 75);
        assertExported(run, expected); assertPreserved(run, business, expected);
        failurePhase = FailurePhase.VERIFY_FINAL_OFFSET;
        awaitFinalCommit(recovery);
        failurePhase = FailurePhase.STOP_RECOVERY;
        ExportIntegrityRuntimeProbe.writeStop(recovery.folder()); awaitExited(recovery, false, 45);
        assertDaemonExit(recovery, false); assertJournal("STOPPED", "STOPPED", null); assertLeaseAvailable();
        failurePhase = FailurePhase.FINAL_INVARIANTS;
        assertExported(run, expected); assertPreserved(run, business, expected);
        assertThat(readCommittedEnd()).isEqualTo(1L); assertThat(committedOffset()).contains(1L);
        assertOwnedKafkaTargetUnchanged();
    }

    private void requireEmptyDedicatedSchemaAndPristinePolicy() throws Exception {
        assertThat(Runtime.version().feature()).isEqualTo(21); assertThat(ZoneId.systemDefault()).isEqualTo(ZoneId.of("Asia/Seoul"));
        try (var connection = dataSource.getConnection()) {
            assertThat(connection.getMetaData().getDatabaseProductName()).isEqualTo("MariaDB");
            assertThat(connection.getCatalog()).isEqualTo("platform_lab_runtime_it");
        }
        for (String table : List.of("lab_job", "lab_outbox", "demo_run", "demo_outcome")) {
            assertThat(jdbc.queryForObject("SELECT COUNT(*) FROM " + table, Long.class)).isZero();
        }
        assertThat(jdbc.queryForObject("SELECT COUNT(*) FROM lab_job_slot", Long.class)).isEqualTo(1L); assertThat(slotOwner()).isNull();
        assertThat(jdbc.queryForObject("SELECT COUNT(*) FROM information_schema.TRIGGERS WHERE TRIGGER_SCHEMA=DATABASE()", Long.class)).isZero();
        for (String version : List.of("1", "2", "3", "4")) {
            assertThat(jdbc.queryForObject("SELECT COUNT(*) FROM flyway_schema_history WHERE version=? AND success=1", Long.class, version)).isEqualTo(1L);
        }
        assertThat(jdbc.queryForObject("SELECT COUNT(*) FROM flyway_schema_history WHERE success=0", Long.class)).isZero();
        assertThat(jdbc.queryForObject("SELECT COUNT(*) FROM lab_admission_policy", Long.class)).isEqualTo(1L);
        var policy = jdbc.queryForMap("SELECT * FROM lab_admission_policy WHERE id=1");
        assertThat(((Number) policy.get("id")).intValue()).isEqualTo(1);
        assertThat(((Number) policy.get("cooldown_seconds")).intValue()).isEqualTo(30);
        assertThat(policy.get("last_admitted_at")).isNull(); assertThat(policy.get("next_admission_at")).isNull();
        assertJournal("NOT_STARTED", "IDLE", null); assertLeaseAvailable();
        var initial = journalSnapshot();
        assertThat(initial.get("started_at")).isNull(); assertThat(initial.get("heartbeat_at")).isNull(); assertThat(initial.get("stopped_at")).isNull();
    }

    private Child startDaemon(String run) throws Exception {
        Path folder = freshChildFolder("daemon");
        return startChild(ExportIntegrityRuntimeProbe.class.getName(), List.of("daemon", topic, group,
            folder.resolve("checkpoint.json").toString(), folder.resolve("stop.request").toString(), folder.resolve("exit.json").toString(), run), folder);
    }
    private Child startOriginalCli(String mode) throws Exception {
        Path folder = freshChildFolder(mode);
        return startChild(RuntimeProcessProbe.class.getName(), List.of(mode, topic, group,
            folder.resolve("checkpoint.json").toString(), folder.resolve("stop.request").toString(), folder.resolve("exit.json").toString(), "-"), folder);
    }
    private Path freshChildFolder(String prefix) throws Exception {
        remainingMillis();
        return Files.createDirectory(privateDirectory.resolve(prefix + "-" + UUID.randomUUID()),
            PosixFilePermissions.asFileAttribute(PosixFilePermissions.fromString("rwx------")));
    }
    private Child startChild(String main, List<String> arguments, Path folder) throws Exception {
        String classpath = System.getProperty("surefire.test.class.path", System.getProperty("java.class.path"));
        Path java = Path.of(System.getProperty("java.home"), "bin", System.getProperty("os.name").startsWith("Windows") ? "java.exe" : "java");
        var command = new ArrayList<>(List.of(java.toString(), "-Xmx256m", "-Duser.timezone=Asia/Seoul", "-cp", classpath, main)); command.addAll(arguments);
        Path log = folder.resolve("child.log"); var builder = new ProcessBuilder(command).redirectErrorStream(true).redirectOutput(log.toFile());
        var environment = builder.environment();
        environment.put("DB_URL", ContinuousRuntimeIT.disposableDatabaseUrl()); environment.put("DB_USERNAME", ContinuousRuntimeIT.required("DB_TEST_USERNAME"));
        environment.put("DB_PASSWORD", ContinuousRuntimeIT.required("DB_TEST_PASSWORD")); environment.put("LAB_ENVIRONMENT", "isolated-lab");
        environment.put("LAB_RUNTIME_KAFKA_BOOTSTRAP", ContinuousRuntimeIT.guardedBootstrap()); environment.put("LAB_RUNTIME_KAFKA_TOPIC", topic); environment.put("LAB_RUNTIME_KAFKA_GROUP", group);
        environment.put("LAB_RUNTIME_S3_ENDPOINT", ContinuousRuntimeIT.guardedS3Endpoint().toString()); environment.put("LAB_RUNTIME_S3_REGION", "garage");
        environment.put("LAB_RUNTIME_S3_BUCKET", bucket); environment.put("LAB_RUNTIME_S3_ACCESS_KEY_ID", ContinuousRuntimeIT.required("LAB_S3_TEST_ACCESS_KEY"));
        environment.put("LAB_RUNTIME_S3_SECRET_ACCESS_KEY", ContinuousRuntimeIT.required("LAB_S3_TEST_SECRET_KEY"));
        remainingMillis(); var child = new Child(builder.start(), folder, log); children.add(child); return child;
    }
    private void awaitReady(Child child) throws Exception {
        await(() -> Files.exists(child.folder().resolve("checkpoint.json"), LinkOption.NOFOLLOW_LINKS) || !child.process().isAlive(), 45);
        var value = ExportIntegrityRuntimeProbe.readPrivate(child.folder().resolve("checkpoint.json"));
        assertExactKeys(value, COMMON_KEYS); assertCommon(value, "RUNNER_READY");
    }
    private void awaitExited(Child child, boolean failureExpected, int seconds) throws Exception {
        assertThat(child.process().waitFor(Math.min(remainingMillis(), seconds * 1000L), TimeUnit.MILLISECONDS)).isTrue();
        assertThat(child.process().isAlive()).isFalse();
        if (failureExpected) { assertThat(child.process().exitValue()).isNotZero(); } else { assertThat(child.process().exitValue()).isZero(); }
    }
    private void assertDaemonExit(Child child, boolean paused) throws Exception {
        var value = ExportIntegrityRuntimeProbe.readPrivate(child.folder().resolve("exit.json"));
        assertExactKeys(value, EXIT_KEYS); assertCommon(value, "DAEMON_EXITED");
        assertThat(value.get("resourcesClosed").isBoolean()).isTrue(); assertThat(value.get("resourcesClosed").asBoolean()).isTrue();
        for (String key : List.of("runtimeStatus", "runtimeStage")) { assertThat(value.get(key).isString()).isTrue(); }
        assertThat(value.get("runtimeStatus").asText()).isEqualTo(paused ? "PAUSED_OPERATOR" : "STOPPED");
        assertThat(value.get("runtimeStage").asText()).isEqualTo(paused ? "EXPORT" : "STOPPED");
        if (paused) { assertThat(value.get("failureCode").isString()).isTrue(); assertThat(value.get("failureCode").asText()).isEqualTo("EXPORT_FAILED"); }
        else { assertThat(value.get("failureCode").isNull()).isTrue(); }
        for (String key : List.of("verificationFailures", "completedReplays")) { assertThat(value.get(key).isIntegralNumber()).isTrue(); }
        assertThat(value.get("verificationFailures").toString()).isEqualTo(paused ? "1" : "0");
        assertThat(value.get("completedReplays").toString()).isEqualTo(paused ? "0" : "1");
    }
    private void assertCommon(JsonNode value, String phase) {
        assertThat(value.get("schemaVersion").isIntegralNumber()).isTrue(); assertThat(value.get("schemaVersion").toString()).isEqualTo("1");
        for (String key : List.of("sourceCommit", "runId", "nonce", "phase")) { assertThat(value.get(key).isString()).isTrue(); }
        assertThat(value.get("sourceCommit").asText()).isEqualTo(sourceCommit);
        assertThat(value.get("runId").asText()).isEqualTo(ContinuousRuntimeIT.required("EXPORT_CONTROL_RUN_ID"));
        assertThat(value.get("nonce").asText()).isEqualTo(ContinuousRuntimeIT.required("EXPORT_CONTROL_NONCE"));
        assertThat(value.get("phase").asText()).isEqualTo(phase);
    }
    private static void assertExactKeys(JsonNode value, Set<String> expected) {
        assertThat(value.isObject()).isTrue(); var keys = new java.util.HashSet<String>(); value.properties().forEach(entry -> keys.add(entry.getKey()));
        assertThat(keys).isEqualTo(expected);
    }
    private void assertRunRefused(String run, List<List<Map<String, Object>>> business, ExportBundle expected, Remote corrupt) throws Exception {
        var paused = journalSnapshot(); assertPaused(); assertLeaseAvailable();
        Child refused = startOriginalCli("cli-run"); awaitExited(refused, true, 40);
        assertThat(Files.isRegularFile(refused.log(), LinkOption.NOFOLLOW_LINKS)).isTrue(); assertThat(Files.size(refused.log())).isLessThanOrEqualTo(1_048_576L);
        assertThat(Files.readString(refused.log(), StandardCharsets.UTF_8)).contains("RuntimeStateStore$OperatorResumeRequiredException");
        assertThat(Files.exists(refused.folder().resolve("checkpoint.json"), LinkOption.NOFOLLOW_LINKS)).isFalse();
        assertThat(journalSnapshot()).isEqualTo(paused); assertLeaseAvailable();
        assertCorruptPending(run, business, expected, corrupt); assertNoConsumerProgress();
    }
    private void resumeOriginal() throws Exception {
        var paused = journalSnapshot(); assertPaused(); assertLeaseAvailable();
        Child resume = startOriginalCli("resume"); awaitExited(resume, false, 40);
        assertJournal("STOPPED", "STOPPED", null); assertLeaseAvailable(); var resumed = journalSnapshot();
        assertThat(resumed.get("started_at")).isEqualTo(paused.get("started_at")); assertThat(resumed.get("source_commit")).isEqualTo(paused.get("source_commit"));
        assertThat(resumed.get("stopped_at")).isNotNull(); assertThat(resumed.get("stopped_at")).isNotEqualTo(paused.get("stopped_at"));
        assertThat(resumed.get("heartbeat_at")).isEqualTo(resumed.get("stopped_at"));
    }

    private void assertPaused() { assertJournal("PAUSED_OPERATOR", "EXPORT", "EXPORT_FAILED"); }
    private Map<String, Object> journalSnapshot() { return jdbc.queryForMap("SELECT * FROM lab_runtime WHERE id=1"); }
    private void assertJournal(String status, String stage, String failure) {
        var actual = journalSnapshot(); assertThat(actual.get("status")).isEqualTo(status); assertThat(actual.get("stage")).isEqualTo(stage); assertThat(actual.get("failure_code")).isEqualTo(failure);
    }
    private String slotOwner() { return jdbc.queryForObject("SELECT occupied_run_id FROM lab_job_slot WHERE id=1", String.class); }
    private void assertLeaseAvailable() { try (var lease = MariaDbRuntimeLease.acquire(dataSource)) { lease.verifyHeld(); } }
    private void assertCompletedPending(String run) {
        var job = jobs.get(run); assertThat(job.status()).isEqualTo(LabJobService.Status.COMPLETED); assertThat(job.exportStatus()).isEqualTo(LabJobService.ExportStatus.PENDING);
        assertThat(job.exportCompletedAt()).isNull(); assertThat(slotOwner()).isEqualTo(run); assertOutbox(run, false);
    }
    private List<List<Map<String, Object>>> businessSnapshot() {
        return List.of(jdbc.queryForList("SELECT * FROM demo_run ORDER BY id"), jdbc.queryForList("SELECT * FROM demo_outcome ORDER BY run_id,input_sequence"),
            jdbc.queryForList("SELECT run_id,scenario_version,source_sha256,source_size,status,created_at,source_verified_at,queued_at,completed_at,terminated_at FROM lab_job ORDER BY run_id"),
            jdbc.queryForList("SELECT * FROM lab_outbox WHERE event_type='DISPATCH' ORDER BY id"),
            jdbc.queryForList("SELECT id,job_run_id,event_type,source_sha256,created_at FROM lab_outbox WHERE event_type='EXPORT' ORDER BY id"));
    }
    private void assertCounts(String run) {
        var actual = jdbc.queryForMap("SELECT input_count,success_count,failure_count,duplicate_count,pending_count FROM demo_run WHERE id=?", run);
        int[] expected = {12, 7, 3, 2, 0}; int index = 0;
        for (String key : List.of("input_count", "success_count", "failure_count", "duplicate_count", "pending_count")) { assertThat(((Number) actual.get(key)).intValue()).isEqualTo(expected[index++]); }
        assertThat(jdbc.queryForObject("SELECT COUNT(*) FROM demo_run", Long.class)).isEqualTo(1L);
        assertThat(jdbc.queryForObject("SELECT COUNT(*) FROM demo_outcome", Long.class)).isEqualTo(12L);
    }
    private ExportBundle bundle(String run) { return ExportBundle.from(jobs.exportSnapshot(run, jobs.get(run).sourceSha256())); }
    private void assertPreserved(String run, List<List<Map<String, Object>>> business, ExportBundle expected) {
        assertThat(businessSnapshot()).isEqualTo(business); assertThat(jdbc.queryForMap("SELECT * FROM lab_admission_policy WHERE id=1")).isEqualTo(admissionBaseline);
        assertCounts(run); assertSourceUnchanged(run); var actual = bundle(run);
        for (var pair : List.of(List.of(actual.result(), expected.result()), List.of(actual.failures(), expected.failures()))) {
            assertThat(pair.getFirst().key()).isEqualTo(pair.getLast().key()); assertThat(pair.getFirst().bytes()).isEqualTo(pair.getLast().bytes());
            assertThat(pair.getFirst().sha256()).isEqualTo(pair.getLast().sha256());
        }
    }
    private void assertSourceUnchanged(String run) {
        assertThat(jdbc.queryForObject("SELECT source_bytes FROM lab_job WHERE run_id=?", byte[].class, run)).isEqualTo(source);
        assertThat(raw.readAndVerify(jobs.get(run))).isEqualTo(source);
    }
    private void assertDispatchAcknowledged(String run) {
        var row = jdbc.queryForMap("SELECT * FROM lab_outbox WHERE job_run_id=? AND event_type='DISPATCH'", run);
        assertThat(row.get("status")).isEqualTo("ACKNOWLEDGED"); assertThat(row.get("acknowledged_at")).isNotNull();
    }
    private void assertOutbox(String run, boolean exported) {
        assertDispatchAcknowledged(run);
        var row = jdbc.queryForMap("SELECT status,acknowledged_at FROM lab_outbox WHERE job_run_id=? AND event_type='EXPORT'", run);
        assertThat(row.get("status")).isEqualTo(exported ? "ACKNOWLEDGED" : "PENDING");
        if (exported) { assertThat(row.get("acknowledged_at")).isNotNull(); assertThat(row.get("acknowledged_at")).isEqualTo(jdbc.queryForMap("SELECT export_completed_at FROM lab_job WHERE run_id=?", run).get("export_completed_at")); }
        else { assertThat(row.get("acknowledged_at")).isNull(); }
        assertThat(jdbc.queryForObject("SELECT COUNT(*) FROM lab_outbox", Long.class)).isEqualTo(2L);
    }
    private List<String> remoteKeys(String run) {
        var result = s3.listObjectsV2(ListObjectsV2Request.builder().bucket(bucket).prefix("result/" + run + "/").build());
        assertThat(result.isTruncated()).isFalse(); return result.contents().stream().map(object -> object.key()).sorted().toList();
    }
    private Remote remote(String key) {
        ResponseTransformer<GetObjectResponse, Remote> bounded = (response, input) -> {
            Long declared = response.contentLength();
            if (declared == null || declared < 0 || declared > ExportBundle.MAX_DOCUMENT_BYTES) {
                input.abort(); throw new IllegalStateException("Owned object declared size is outside the bounded contract");
            }
            byte[] bytes = input.readNBytes(ExportBundle.MAX_DOCUMENT_BYTES + 1);
            if (bytes.length != declared || bytes.length > ExportBundle.MAX_DOCUMENT_BYTES) {
                input.abort(); throw new IllegalStateException("Owned object actual size differs from its bounded declaration");
            }
            return new Remote(bytes, declared, response.eTag(), response.lastModified());
        };
        return s3.getObject(GetObjectRequest.builder().bucket(bucket).key(key).build(), bounded);
    }
    private void requireMissing(String key) {
        try { remote(key); }
        catch (S3Exception failure) {
            assertThat(failure.statusCode()).isEqualTo(404); assertThat(failure.awsErrorDetails()).isNotNull();
            assertThat(failure.awsErrorDetails().errorCode()).isEqualTo("NoSuchKey"); return;
        }
        throw new AssertionError("Owned fixture key unexpectedly exists");
    }
    private void assertCorruptPending(String run, List<List<Map<String, Object>>> business, ExportBundle expected, Remote corrupt) {
        assertCompletedPending(run); assertPreserved(run, business, expected);
        var actual = remote(expected.result().key()); assertThat(actual.bytes()).isEqualTo(corrupt.bytes()); assertThat(hash(actual.bytes())).isEqualTo(hash(corrupt.bytes()));
        assertThat(actual.size()).isEqualTo(corrupt.size()); assertThat(actual.etag()).isEqualTo(corrupt.etag()); assertThat(actual.modifiedAt()).isEqualTo(corrupt.modifiedAt());
        assertThat(remoteKeys(run)).containsExactly(expected.result().key()); requireMissing(expected.failures().key());
    }
    private void assertExported(String run, ExportBundle expected) {
        var job = jobs.get(run); assertThat(job.status()).isEqualTo(LabJobService.Status.COMPLETED); assertThat(job.exportStatus()).isEqualTo(LabJobService.ExportStatus.EXPORTED);
        assertThat(job.exportCompletedAt()).isNotNull(); assertThat(slotOwner()).isNull(); assertOutbox(run, true);
        for (var document : List.of(expected.result(), expected.failures())) {
            var actual = remote(document.key()); assertThat(actual.bytes()).isEqualTo(document.bytes()); assertThat(actual.size()).isEqualTo((long) document.size());
            assertThat(hash(actual.bytes())).isEqualTo(document.sha256()); assertThat(document.matches(actual.bytes())).isTrue();
        }
        assertThat(remoteKeys(run)).containsExactlyInAnyOrder(expected.result().key(), expected.failures().key());
    }

    private void requireInitiallyEmptyGroup() throws Exception {
        // Readiness only before the fixture: one pending future, request timeout, and one shared outer bound.
        long bound = Math.min(testDeadline, System.nanoTime() + Duration.ofSeconds(45).toNanos());
        while (true) {
            long remaining = bound - System.nanoTime();
            int rpcMillis = (int) Math.min(10000L, TimeUnit.NANOSECONDS.toMillis(remaining));
            if (rpcMillis < 1) { throw new java.util.concurrent.TimeoutException("Initial coordinator readiness deadline exceeded"); }
            var options = new org.apache.kafka.clients.admin.ListConsumerGroupOffsetsOptions().timeoutMs(rpcMillis);
            var future = kafka.listConsumerGroupOffsets(group, options).partitionsToOffsetAndMetadata();
            try {
                remaining = bound - System.nanoTime();
                if (remaining <= 0) { throw new java.util.concurrent.TimeoutException("Initial coordinator readiness deadline exceeded"); }
                var value = future.get(remaining, TimeUnit.NANOSECONDS);
                assertThat(value.keySet()).allMatch(partition -> partition.equals(new TopicPartition(topic, 0)));
                assertThat(value.get(new TopicPartition(topic, 0))).isNull();
                if (System.nanoTime() >= bound) { throw new java.util.concurrent.TimeoutException("Initial coordinator readiness deadline exceeded"); }
                remainingMillis(); return;
            } catch (Exception failure) {
                FailureKind kind = failureKind(failure);
                if (kind == FailureKind.INTERRUPTED) { Thread.currentThread().interrupt(); }
                if (kind == FailureKind.GROUP_NOT_FOUND && System.nanoTime() < bound) { remainingMillis(); return; }
                boolean startupTransient = kind == FailureKind.TIMEOUT || kind == FailureKind.COORDINATOR_NOT_AVAILABLE
                    || kind == FailureKind.COORDINATOR_LOAD_IN_PROGRESS || kind == FailureKind.NOT_COORDINATOR;
                if (!startupTransient || System.nanoTime() >= bound) { throw failure; }
            } finally {
                if (!future.isDone()) { future.cancel(false); }
            }
            remaining = bound - System.nanoTime();
            if (remaining <= 0) { throw new java.util.concurrent.TimeoutException("Initial coordinator readiness deadline exceeded"); }
            TimeUnit.NANOSECONDS.sleep(Math.min(Duration.ofMillis(250).toNanos(), remaining));
        }
    }
    private Optional<Long> committedOffset() throws Exception {
        try {
            var actual = kafka.listConsumerGroupOffsets(group).partitionsToOffsetAndMetadata().get(rpcMillis(), TimeUnit.MILLISECONDS);
            var partition = new TopicPartition(topic, 0); assertThat(actual.keySet()).allMatch(partition::equals);
            var offset = actual.get(partition); return offset == null ? Optional.empty() : Optional.of(offset.offset());
        } catch (java.util.concurrent.ExecutionException failure) {
            if (failure.getCause() instanceof GroupIdNotFoundException) { return Optional.empty(); } throw failure;
        }
    }
    private long readCommittedEnd() throws Exception {
        var partition = new TopicPartition(topic, 0);
        return kafka.listOffsets(Map.of(partition, OffsetSpec.latest()), new ListOffsetsOptions(IsolationLevel.READ_COMMITTED))
            .all().get(rpcMillis(), TimeUnit.MILLISECONDS).get(partition).offset();
    }
    private void assertNoConsumerProgress() throws Exception { assertThat(readCommittedEnd()).isEqualTo(1L); assertThat(committedOffset()).isEmpty(); }
    private void awaitFinalCommit(Child recovery) throws Exception {
        long deadline = Math.min(testDeadline, System.nanoTime() + Duration.ofSeconds(45).toNanos());
        while (System.nanoTime() < deadline) {
            assertThat(recovery.process().isAlive()).isTrue(); var offset = committedOffset();
            if (offset.isPresent()) {
                assertThat(offset.orElseThrow()).isEqualTo(1L); assertThat(readCommittedEnd()).isEqualTo(1L);
                requireBefore(deadline); return;
            }
            Thread.sleep(Math.min(100, remainingMillis()));
        }
        throw new AssertionError("Completed replay did not commit the sole message before the deadline");
    }
    private void assertOwnedKafkaTargetUnchanged() throws Exception {
        assertThat(kafka.describeCluster().clusterId().get(rpcMillis(), TimeUnit.MILLISECONDS)).isEqualTo(clusterId);
        assertThat(kafka.describeCluster().nodes().get(rpcMillis(), TimeUnit.MILLISECONDS)).hasSize(1);
        var actual = kafka.describeTopics(List.of(topic)).allTopicNames().get(rpcMillis(), TimeUnit.MILLISECONDS).get(topic);
        assertThat(actual.topicId()).isEqualTo(topicId); assertThat(actual.partitions()).hasSize(1);
        assertThat(actual.partitions().getFirst().partition()).isZero(); assertThat(actual.partitions().getFirst().replicas()).hasSize(1);
    }
    private long remainingMillis() {
        long nanos = testDeadline - System.nanoTime(); if (nanos <= 0) { throw new AssertionError("Parent experiment deadline exhausted"); }
        return Math.max(1, TimeUnit.NANOSECONDS.toMillis(nanos));
    }
    private long rpcMillis() { return Math.min(10_000, remainingMillis()); }
    private void requireBefore(long deadline) {
        remainingMillis();
        if (System.nanoTime() >= deadline) { throw new AssertionError("Observed phase completed after its deadline"); }
    }
    private void await(BooleanSupplier condition, int seconds) throws Exception {
        long deadline = Math.min(testDeadline, System.nanoTime() + Duration.ofSeconds(seconds).toNanos());
        while (System.nanoTime() < deadline) {
            if (condition.getAsBoolean()) { requireBefore(deadline); return; }
            Thread.sleep(Math.min(100, remainingMillis()));
        }
        throw new AssertionError("Owned child did not reach its bounded observed state");
    }
    private static String hash(byte[] value) {
        try { return HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(value)); }
        catch (java.security.NoSuchAlgorithmException impossible) { throw new IllegalStateException("SHA-256 unavailable"); }
    }
    private static FailureKind failureKind(Throwable original) {
        Throwable failure = original; var seen = java.util.Collections.newSetFromMap(new java.util.IdentityHashMap<Throwable, Boolean>());
        for (int depth = 0; depth < 8; depth++) {
            if (!seen.add(failure)) { return FailureKind.OTHER; }
            if (!(failure instanceof java.util.concurrent.ExecutionException) && !(failure instanceof java.util.concurrent.CompletionException)) { break; }
            Throwable cause = failure.getCause(); if (cause == null) { return FailureKind.OTHER; } failure = cause;
            if (depth == 7) { return FailureKind.OTHER; }
        }
        if (failure instanceof AssertionError) { return FailureKind.ASSERTION; }
        if (failure instanceof InterruptedException) { return FailureKind.INTERRUPTED; }
        if (failure instanceof java.sql.SQLException) { return FailureKind.SQL; }
        if (failure instanceof GroupIdNotFoundException) { return FailureKind.GROUP_NOT_FOUND; }
        if (failure instanceof org.apache.kafka.common.errors.UnknownTopicOrPartitionException) { return FailureKind.UNKNOWN_TOPIC; }
        if (failure instanceof org.apache.kafka.common.errors.CoordinatorNotAvailableException) { return FailureKind.COORDINATOR_NOT_AVAILABLE; }
        if (failure instanceof org.apache.kafka.common.errors.CoordinatorLoadInProgressException) { return FailureKind.COORDINATOR_LOAD_IN_PROGRESS; }
        if (failure instanceof org.apache.kafka.common.errors.NotCoordinatorException) { return FailureKind.NOT_COORDINATOR; }
        if (failure instanceof java.util.concurrent.TimeoutException || failure instanceof org.apache.kafka.common.errors.TimeoutException) { return FailureKind.TIMEOUT; }
        if (failure instanceof org.apache.kafka.common.KafkaException) { return FailureKind.KAFKA_OTHER; }
        return FailureKind.OTHER;
    }
    private static Integer failureSourceLine(Throwable failure) {
        StackTraceElement[] frames = failure.getStackTrace(); String own = ExportIntegrityRuntimeIT.class.getName();
        for (int index = 0; index < Math.min(frames.length, 64); index++) {
            var frame = frames[index];
            if ((frame.getClassName().equals(own) || frame.getClassName().startsWith(own + "$")) && "ExportIntegrityRuntimeIT.java".equals(frame.getFileName())
                && frame.getLineNumber() > 0 && frame.getLineNumber() <= 10000) { return frame.getLineNumber(); }
        }
        return null;
    }
    private static void emitSuccess() {
        var value = new LinkedHashMap<String, Object>(); value.put("schemaVersion", 1); value.put("status", "PASS");
        value.put("fixtureInput", 12); value.put("successCount", 7); value.put("failureCount", 3); value.put("duplicateCount", 2); value.put("pendingCount", 0);
        value.put("directDatabaseFixture", true); value.put("dispatchBrokerAck", true); value.put("sameSizeCorruption", true); value.put("verificationFailureObserved", true);
        value.put("pausePersisted", true); value.put("pauseCode", "EXPORT_FAILED"); value.put("runRefusedUnchanged", true); value.put("unrepairedResumeRepaused", true);
        value.put("corruptObjectUnchanged", true); value.put("explicitOwnedFixtureDeleted", true); value.put("verifiedExportFiles", 2); value.put("completedReplays", 1);
        value.put("finalEndOffset", 1); value.put("finalCommittedOffset", 1); value.put("finalLag", 0); value.put("businessRowsAndTimesUnchanged", true);
        value.put("sourceAndRawUnchanged", true); value.put("dispatchAndExportIdentityUnchanged", true); value.put("exported", true); value.put("slotFree", true);
        value.put("childResourcesClosed", true); value.put("targetStable", true);
        System.out.println("EXPORT_INTEGRITY_RUNTIME_RESULT " + JSON.writeValueAsString(value));
    }
    private void closeOwnedChildrenAndClients() throws Exception {
        boolean interrupted = Thread.interrupted(); boolean closed = true;
        long cleanupDeadline = System.nanoTime() + Duration.ofSeconds(15).toNanos();
        try {
            for (var child : children) { if (child.process().isAlive()) { child.process().destroyForcibly(); } }
            for (var child : children) {
                long left = Math.max(0, cleanupDeadline - System.nanoTime());
                try { closed &= child.process().waitFor(Math.min(Duration.ofSeconds(10).toNanos(), left), TimeUnit.NANOSECONDS); }
                catch (InterruptedException failure) { interrupted = true; closed = false; }
            }
            try { if (kafka != null) { kafka.close(Duration.ofSeconds(5)); kafka = null; } }
            finally { if (s3 != null) { s3.close(); s3 = null; } }
        } finally { if (interrupted) { Thread.currentThread().interrupt(); } }
        if (!closed) { throw new AssertionError("Owned child did not terminate during bounded cleanup"); }
    }
    private record Child(Process process, Path folder, Path log) {}
    private record Remote(byte[] bytes, Long size, String etag, java.time.Instant modifiedAt) {}
}
