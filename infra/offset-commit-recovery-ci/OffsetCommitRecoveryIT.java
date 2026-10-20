package io.github.devdooly.platformlab.jobs.runtime;

import io.github.devdooly.platformlab.demo.SyntheticScenario;
import io.github.devdooly.platformlab.jobs.AdmissionTestFixtures;
import io.github.devdooly.platformlab.jobs.CanonicalSource;
import io.github.devdooly.platformlab.jobs.LabJobService;
import io.github.devdooly.platformlab.jobs.S3ClientFactory;
import io.github.devdooly.platformlab.jobs.S3RawSourceStore;
import io.github.devdooly.platformlab.jobs.SourceStagingService;
import io.github.devdooly.platformlab.jobs.exporting.ExportBundle;
import io.github.devdooly.platformlab.jobs.exporting.RuntimeProcessProbe;
import io.github.devdooly.platformlab.jobs.messaging.OffsetCommitRecoveryProbe;
import java.nio.ByteBuffer;
import java.nio.channels.FileChannel;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.LinkOption;
import java.nio.file.Path;
import java.nio.file.StandardCopyOption;
import java.nio.file.StandardOpenOption;
import java.nio.file.attribute.PosixFilePermissions;
import java.time.Duration;
import java.time.ZoneId;
import java.util.ArrayList;
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
import software.amazon.awssdk.services.s3.S3Client;
import software.amazon.awssdk.services.s3.model.GetObjectRequest;
import software.amazon.awssdk.services.s3.model.ListObjectsV2Request;
import tools.jackson.databind.JsonNode;
import tools.jackson.databind.json.JsonMapper;
import static org.assertj.core.api.Assertions.assertThat;

/** Opt-in parent for one owned broker-pause experiment; never changes a persisted pause or offset itself. */
@SpringBootTest(properties = "logging.level.root=WARN")
@ActiveProfiles({"db-test", "worker"})
@EnabledIfSystemProperty(named = "lab.offset-recovery.tests", matches = "true")
public class OffsetCommitRecoveryIT {
    private static final JsonMapper JSON = JsonMapper.builder().build();
    private static final Set<String> EXIT_KEYS = Set.of("schemaVersion", "sourceCommit", "runId", "nonce", "phase",
        "resourcesClosed", "runtimeStatus", "runtimeStage", "failureCode", "completedReplays");
    @Autowired LabJobService jobs;
    @Autowired JdbcTemplate jdbc;
    @Autowired DataSource dataSource;
    private final List<Child> children = new ArrayList<>();
    private final byte[] source = CanonicalSource.fixtureBytes();
    private S3Client s3;
    private Admin kafka;
    private String sourceCommit;
    private String bucket;
    private String topic;
    private String group;
    private String clusterId;
    private Uuid topicId;
    private Path privateDirectory;
    private FailurePhase failurePhase = FailurePhase.TEST_ENTRY;
    private enum FailurePhase {
        TEST_ENTRY, SERVICE_GUARDS, KAFKA_CREATE, STAGE_INPUT, START_FAULT, WAIT_DB_COMMIT,
        CHECK_PENDING, WAIT_FAULT_EXIT, CHECK_PERSISTED_PAUSE, WAIT_UNPAUSE,
        OBSERVE_COMMIT, RUN_REFUSAL, OPERATOR_RESUME, START_RECOVERY, VERIFY_EXPORT,
        VERIFY_FINAL_OFFSET, STOP_RECOVERY, FINAL_INVARIANTS, CLOSE_CLIENTS
    }
    private enum FailureKind {
        ASSERTION, INTERRUPTED, SQL, GROUP_NOT_FOUND, UNKNOWN_TOPIC,
        COORDINATOR_NOT_AVAILABLE, COORDINATOR_LOAD_IN_PROGRESS, NOT_COORDINATOR,
        TIMEOUT, KAFKA_OTHER, OTHER
    }

    private static FailureKind failureKind(Throwable original) {
        Throwable failure = original;
        var seen = java.util.Collections.newSetFromMap(new java.util.IdentityHashMap<Throwable, Boolean>());
        for (int depth = 0; depth < 8; depth++) {
            if (!seen.add(failure)) { return FailureKind.OTHER; }
            if (!(failure instanceof java.util.concurrent.ExecutionException)
                    && !(failure instanceof java.util.concurrent.CompletionException)) { break; }
            Throwable cause = failure.getCause();
            if (cause == null) { return FailureKind.OTHER; }
            failure = cause;
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
        if (failure instanceof java.util.concurrent.TimeoutException
                || failure instanceof org.apache.kafka.common.errors.TimeoutException) { return FailureKind.TIMEOUT; }
        if (failure instanceof org.apache.kafka.common.KafkaException) { return FailureKind.KAFKA_OTHER; }
        return FailureKind.OTHER;
    }

    private static Integer failureSourceLine(Throwable failure) {
        StackTraceElement[] frames = failure.getStackTrace();
        for (int index = 0; index < Math.min(frames.length, 64); index++) {
            StackTraceElement frame = frames[index];
            String ownClass = OffsetCommitRecoveryIT.class.getName();
            if ((frame.getClassName().equals(ownClass) || frame.getClassName().startsWith(ownClass + "$"))
                    && "OffsetCommitRecoveryIT.java".equals(frame.getFileName())
                    && frame.getLineNumber() > 0 && frame.getLineNumber() <= 10000) {
                return frame.getLineNumber();
            }
        }
        return null;
    }

    @DynamicPropertySource static void guardBeforeFlyway(DynamicPropertyRegistry registry) {
        // Guard every destination before Spring/Flyway opens the first connection.
        ContinuousRuntimeIT.disposableDatabaseUrl(); ContinuousRuntimeIT.guardedS3Endpoint();
        ContinuousRuntimeIT.guardedBootstrap(); ContinuousRuntimeIT.guardedBucket(); ContinuousRuntimeIT.guardedSourceCommit();
        registry.add("spring.datasource.url", ContinuousRuntimeIT::disposableDatabaseUrl);
        registry.add("spring.datasource.username", () -> ContinuousRuntimeIT.required("DB_TEST_USERNAME"));
        registry.add("spring.datasource.password", () -> ContinuousRuntimeIT.required("DB_TEST_PASSWORD"));
    }

    @Test
    @Timeout(value = 420, unit = TimeUnit.SECONDS)
    void realBrokerPausePersistsCommitFailureAndExplicitResumeRecovers() throws Exception {
        try {
            Result result = performExperiment();
            failurePhase = FailurePhase.CLOSE_CLIENTS;
            closeOwnedChildrenAndClients();
            emitSuccess(result.postUnpause(), result.completedReplays());
        } catch (Throwable failure) {
            if (failure instanceof InterruptedException) { Thread.currentThread().interrupt(); }
            System.out.println("OFFSET_COMMIT_RECOVERY_RESULT {\"schemaVersion\":1,\"status\":\"FAIL\",\"failureCode\":\"VALIDATION_FAILED\",\"failurePhase\":\"" + failurePhase.name()
                + "\",\"failureKind\":\"" + failureKind(failure).name() + "\",\"failureSourceLine\":" + failureSourceLine(failure) + "}");
            // Exception text and assertions can contain raw rows, addresses and local file names.
            throw new AssertionError("Offset commit recovery validation failed; inspect private test diagnostics");
        } finally {
            try { closeOwnedChildrenAndClients(); }
            catch (Throwable failure) { throw new AssertionError("Owned child or client cleanup failed; inspect private diagnostics"); }
        }
    }

    private Result performExperiment() throws Exception {
        failurePhase = FailurePhase.SERVICE_GUARDS;
        requireEmptyDedicatedSchema();
        sourceCommit = ContinuousRuntimeIT.guardedSourceCommit(); bucket = ContinuousRuntimeIT.guardedBucket();
        privateDirectory = OffsetCommitRecoveryProbe.controlDirectory();
        try (var files = Files.list(privateDirectory)) { assertThat(files.toList()).isEmpty(); }
        s3 = S3ClientFactory.createGarage(ContinuousRuntimeIT.guardedS3Endpoint(), "garage", StaticCredentialsProvider.create(
            AwsBasicCredentials.create(ContinuousRuntimeIT.required("LAB_S3_TEST_ACCESS_KEY"),
                ContinuousRuntimeIT.required("LAB_S3_TEST_SECRET_KEY"))));
        kafka = ContinuousRuntimeIT.admin(); ContinuousRuntimeIT.requireExpectedCluster(kafka);
        failurePhase = FailurePhase.KAFKA_CREATE;
        clusterId = kafka.describeCluster().clusterId().get(10, TimeUnit.SECONDS);
        assertThat(clusterId).isEqualTo(ContinuousRuntimeIT.required("LAB_KAFKA_TEST_CLUSTER_ID"));
        String identity = UUID.randomUUID().toString();
        topic = "platform-lab-runtime-test-topic-" + identity; group = "platform-lab-runtime-test-group-" + identity;
        ContinuousRuntimeIT.requireOwnedName(topic); ContinuousRuntimeIT.requireOwnedName(group);
        kafka.createTopics(List.of(new NewTopic(topic, 1, (short) 1).configs(Map.of(
            "retention.ms", "3600000", "retention.bytes", "8388608", "max.message.bytes", "1024")))).all().get(10, TimeUnit.SECONDS);
        var actualTopic = kafka.describeTopics(List.of(topic)).allTopicNames().get(10, TimeUnit.SECONDS).get(topic);
        assertThat(actualTopic.partitions()).hasSize(1); assertThat(actualTopic.partitions().getFirst().replicas()).hasSize(1);
        topicId = actualTopic.topicId(); assertThat(topicId).isNotEqualTo(Uuid.ZERO_UUID);
        assertThat(readCommittedEnd()).isZero(); assertThat(committedOffset()).isEmpty();
        failurePhase = FailurePhase.STAGE_INPUT;
        AdmissionTestFixtures.makeEligible(jdbc);
        String run = "runtime-it-" + UUID.randomUUID(); ContinuousRuntimeIT.requireOwnedRun(run);
        var admitted = new SourceStagingService(jobs, new S3RawSourceStore(s3, bucket)).stage(run, SyntheticScenario.NAME, source);
        assertThat(admitted.status()).isEqualTo(LabJobService.Status.QUEUED);
        assertThat(admitted.exportStatus()).isEqualTo(LabJobService.ExportStatus.NOT_REQUESTED);
        assertSourceUnchanged(run); assertThat(remoteKeys(run)).isEmpty();

        failurePhase = FailurePhase.START_FAULT;
        Child fault = startProbe("fault", run);
        failurePhase = FailurePhase.WAIT_DB_COMMIT;
        OffsetCommitRecoveryProbe.awaitControl("post-db-commit-ready.json", "POST_DB_COMMIT_READY", deadline(90));
        failurePhase = FailurePhase.CHECK_PENDING;
        assertThat(fault.process().isAlive()).isTrue();
        assertCompletedPending(run); assertCounts(run);
        var business = businessSnapshot();
        var expected = bundle(run);
        assertThat(expected.result().bytes()).isNotEmpty(); assertThat(expected.failures().bytes()).isNotEmpty();
        assertThat(remoteKeys(run)).isEmpty(); assertSourceUnchanged(run);

        // The external owner pauses only its broker after POST_DB_COMMIT_READY. No Kafka calls until its unpause ACK.
        failurePhase = FailurePhase.WAIT_FAULT_EXIT;
        awaitExited(fault, false, 90);
        failurePhase = FailurePhase.CHECK_PERSISTED_PAUSE;
        var faultExit = readExit("fault-exit.json", "FAULT_CHILD_EXITED", "PAUSED_OPERATOR", "CONSUME", "OFFSET_COMMIT_FAILED");
        assertThat(faultExit.get("completedReplays").asInt()).isZero();
        assertPaused(); assertCompletedPending(run); assertCounts(run);
        assertThat(businessSnapshot()).isEqualTo(business); assertBundleUnchanged(run, expected); assertSourceUnchanged(run);
        assertLeaseAvailable();
        OffsetCommitRecoveryProbe.writeControl("paused-observed.json", "PAUSED_OBSERVED");
        failurePhase = FailurePhase.WAIT_UNPAUSE;
        OffsetCommitRecoveryProbe.awaitControl("broker-unpaused-ack.json", "BROKER_UNPAUSED", deadline(90));
        failurePhase = FailurePhase.OBSERVE_COMMIT;
        Optional<Long> postUnpause = committedOffset();
        if (postUnpause.isPresent()) { assertThat(postUnpause.orElseThrow()).isEqualTo(1L); }
        assertThat(readCommittedEnd()).isEqualTo(1L);
        assertPaused();

        failurePhase = FailurePhase.RUN_REFUSAL;
        var paused = journalSnapshot();
        Child refused = startOriginalCli("cli-run"); awaitExited(refused, true, 45);
        assertThat(Files.readString(refused.log(), StandardCharsets.UTF_8))
            .contains("RuntimeStateStore$OperatorResumeRequiredException");
        assertThat(Files.exists(refused.checkpoint(), LinkOption.NOFOLLOW_LINKS)).isFalse();
        assertThat(journalSnapshot()).isEqualTo(paused); assertThat(businessSnapshot()).isEqualTo(business);
        assertCompletedPending(run); assertSourceUnchanged(run); assertLeaseAvailable();
        failurePhase = FailurePhase.OPERATOR_RESUME;
        Child resume = startOriginalCli("resume"); awaitExited(resume, false, 45);
        assertJournal("STOPPED", "STOPPED", null); assertLeaseAvailable();
        var resumed = journalSnapshot();
        assertThat(resumed.get("started_at")).isEqualTo(paused.get("started_at"));
        assertThat(resumed.get("source_commit")).isEqualTo(paused.get("source_commit"));
        assertThat(resumed.get("stopped_at")).isNotNull(); assertThat(resumed.get("heartbeat_at")).isNotNull();
        assertThat(resumed.get("stopped_at")).isNotEqualTo(paused.get("stopped_at"));
        assertThat(resumed.get("heartbeat_at")).isEqualTo(resumed.get("stopped_at"));
        assertThat(businessSnapshot()).isEqualTo(business); assertCompletedPending(run); assertSourceUnchanged(run);

        failurePhase = FailurePhase.START_RECOVERY;
        Child recovery = startProbe("recover", run);
        failurePhase = FailurePhase.VERIFY_EXPORT;
        await(() -> jobs.get(run).exportStatus() == LabJobService.ExportStatus.EXPORTED,
            "verified export after explicit resume", Duration.ofSeconds(90));
        assertThat(recovery.process().isAlive()).isTrue();
        assertExported(run, expected); assertThat(businessSnapshot()).isEqualTo(business); assertSourceUnchanged(run);
        failurePhase = FailurePhase.VERIFY_FINAL_OFFSET;
        awaitFinalOffset(recovery);
        failurePhase = FailurePhase.STOP_RECOVERY;
        Path stopFile = privateDirectory.resolve("recovery-stop.request");
        Path pendingStop = privateDirectory.resolve("recovery-stop.pending-" + UUID.randomUUID());
        assertThat(Files.exists(stopFile, LinkOption.NOFOLLOW_LINKS)).isFalse();
        try (var stop = FileChannel.open(pendingStop,
                Set.of(StandardOpenOption.CREATE_NEW, StandardOpenOption.WRITE),
                PosixFilePermissions.asFileAttribute(PosixFilePermissions.fromString("rw-------")))) {
            var bytes = ByteBuffer.wrap("stop\n".getBytes(StandardCharsets.US_ASCII));
            while (bytes.hasRemaining()) { stop.write(bytes); }
            stop.force(true);
        }
        assertThat(Files.exists(stopFile, LinkOption.NOFOLLOW_LINKS)).isFalse();
        Files.move(pendingStop, stopFile, StandardCopyOption.ATOMIC_MOVE);
        awaitExited(recovery, false, 45);
        var recoveredExit = readExit("recovery-exit.json", "RECOVERY_CHILD_EXITED", "STOPPED", "STOPPED", null);
        int replays = recoveredExit.get("completedReplays").asInt(); assertThat(replays).isBetween(0, 1);
        failurePhase = FailurePhase.FINAL_INVARIANTS;
        assertJournal("STOPPED", "STOPPED", null); assertLeaseAvailable();
        assertExported(run, expected); assertThat(businessSnapshot()).isEqualTo(business); assertSourceUnchanged(run);
        assertThat(committedOffset()).contains(1L); assertThat(readCommittedEnd()).isEqualTo(1L);
        assertOwnedKafkaTargetUnchanged();
        // Whole owned schema/bucket/topic/group are destroyed by the outer runner; never reset a journal or offset here.
        return new Result(postUnpause, replays);
    }

    private void requireEmptyDedicatedSchema() throws Exception {
        assertThat(Runtime.version().feature()).isEqualTo(21);
        assertThat(ZoneId.systemDefault()).isEqualTo(ZoneId.of("Asia/Seoul"));
        try (var connection = dataSource.getConnection()) {
            assertThat(connection.getMetaData().getDatabaseProductName()).isEqualTo("MariaDB");
            assertThat(connection.getCatalog()).isEqualTo("platform_lab_runtime_it");
        }
        for (String table : List.of("lab_job", "lab_outbox", "demo_run", "demo_outcome")) {
            assertThat(jdbc.queryForObject("SELECT COUNT(*) FROM " + table, Long.class)).isZero();
        }
        assertThat(jdbc.queryForObject("SELECT COUNT(*) FROM lab_job_slot", Long.class)).isEqualTo(1L);
        assertThat(slotOwner()).isNull();
        assertThat(jdbc.queryForObject("SELECT COUNT(*) FROM information_schema.TRIGGERS WHERE TRIGGER_SCHEMA = DATABASE()", Long.class)).isZero();
        for (String version : List.of("1", "2", "3", "4")) {
            assertThat(jdbc.queryForObject("SELECT COUNT(*) FROM flyway_schema_history WHERE version=? AND success=1", Long.class, version)).isEqualTo(1L);
        }
        assertThat(jdbc.queryForObject("SELECT COUNT(*) FROM flyway_schema_history WHERE success=0", Long.class)).isZero();
        assertJournal("NOT_STARTED", "IDLE", null); assertLeaseAvailable();
    }

    private Child startProbe(String mode, String run) throws Exception {
        return startChild(mode, OffsetCommitRecoveryProbe.class.getName(), List.of(mode, topic, group, run));
    }

    private Child startOriginalCli(String mode) throws Exception {
        Path folder = Files.createDirectory(privateDirectory.resolve(mode + "-" + UUID.randomUUID()));
        return startChild(mode, RuntimeProcessProbe.class.getName(), List.of(mode, topic, group,
            folder.resolve("checkpoint.json").toString(), folder.resolve("stop.request").toString(),
            folder.resolve("exit.json").toString(), "-"), folder);
    }

    private Child startChild(String mode, String main, List<String> arguments) throws Exception {
        return startChild(mode, main, arguments, Files.createDirectory(privateDirectory.resolve(mode + "-" + UUID.randomUUID())));
    }

    private Child startChild(String mode, String main, List<String> arguments, Path folder) throws Exception {
        String classpath = System.getProperty("surefire.test.class.path", System.getProperty("java.class.path"));
        Path java = Path.of(System.getProperty("java.home"), "bin", System.getProperty("os.name").startsWith("Windows") ? "java.exe" : "java");
        var command = new ArrayList<>(List.of(java.toString(), "-Xmx256m", "-Duser.timezone=Asia/Seoul", "-cp", classpath, main));
        command.addAll(arguments); Path log = folder.resolve("child.log");
        var builder = new ProcessBuilder(command).redirectErrorStream(true).redirectOutput(log.toFile());
        var environment = builder.environment();
        environment.put("DB_URL", ContinuousRuntimeIT.disposableDatabaseUrl());
        environment.put("DB_USERNAME", ContinuousRuntimeIT.required("DB_TEST_USERNAME"));
        environment.put("DB_PASSWORD", ContinuousRuntimeIT.required("DB_TEST_PASSWORD"));
        environment.put("LAB_ENVIRONMENT", "isolated-lab");
        environment.put("LAB_RUNTIME_KAFKA_BOOTSTRAP", ContinuousRuntimeIT.guardedBootstrap());
        environment.put("LAB_RUNTIME_KAFKA_TOPIC", topic); environment.put("LAB_RUNTIME_KAFKA_GROUP", group);
        environment.put("LAB_RUNTIME_S3_ENDPOINT", ContinuousRuntimeIT.guardedS3Endpoint().toString());
        environment.put("LAB_RUNTIME_S3_REGION", "garage"); environment.put("LAB_RUNTIME_S3_BUCKET", bucket);
        environment.put("LAB_RUNTIME_S3_ACCESS_KEY_ID", ContinuousRuntimeIT.required("LAB_S3_TEST_ACCESS_KEY"));
        environment.put("LAB_RUNTIME_S3_SECRET_ACCESS_KEY", ContinuousRuntimeIT.required("LAB_S3_TEST_SECRET_KEY"));
        var child = new Child(builder.start(), folder.resolve("checkpoint.json"), log, mode); children.add(child); return child;
    }

    private static void awaitExited(Child child, boolean failureExpected, int seconds) throws Exception {
        assertThat(child.process().waitFor(seconds, TimeUnit.SECONDS)).isTrue();
        assertThat(child.process().isAlive()).isFalse();
        if (failureExpected) { assertThat(child.process().exitValue()).isNotZero(); }
        else { assertThat(child.process().exitValue()).isZero(); }
    }

    private JsonNode readExit(String filename, String phase, String status, String stage, String failure) throws Exception {
        var value = OffsetCommitRecoveryProbe.readPrivate(filename);
        var names = new java.util.HashSet<String>(); value.properties().forEach(entry -> names.add(entry.getKey()));
        assertThat(names).isEqualTo(EXIT_KEYS);
        assertThat(value.get("schemaVersion").isIntegralNumber()).isTrue(); assertThat(value.get("schemaVersion").asInt()).isEqualTo(1);
        assertThat(value.get("schemaVersion").toString()).isEqualTo("1");
        for (String name : List.of("sourceCommit", "runId", "nonce", "phase", "runtimeStatus", "runtimeStage")) {
            assertThat(value.get(name).isString()).isTrue();
        }
        assertThat(value.get("sourceCommit").asText()).isEqualTo(sourceCommit);
        assertThat(value.get("runId").asText()).isEqualTo(OffsetCommitRecoveryProbe.required("OFFSET_CONTROL_RUN_ID"));
        assertThat(value.get("nonce").asText()).isEqualTo(OffsetCommitRecoveryProbe.required("OFFSET_CONTROL_NONCE"));
        assertThat(value.get("phase").asText()).isEqualTo(phase);
        assertThat(value.get("resourcesClosed").isBoolean()).isTrue(); assertThat(value.get("resourcesClosed").asBoolean()).isTrue();
        assertThat(value.get("runtimeStatus").asText()).isEqualTo(status); assertThat(value.get("runtimeStage").asText()).isEqualTo(stage);
        if (failure == null) { assertThat(value.get("failureCode").isNull()).isTrue(); }
        else { assertThat(value.get("failureCode").isString()).isTrue(); assertThat(value.get("failureCode").asText()).isEqualTo(failure); }
        assertThat(value.get("completedReplays").isIntegralNumber()).isTrue();
        assertThat(value.get("completedReplays").toString()).isIn("0", "1");
        return value;
    }

    private void assertPaused() { assertJournal("PAUSED_OPERATOR", "CONSUME", "OFFSET_COMMIT_FAILED"); }
    private Map<String, Object> journalSnapshot() { return jdbc.queryForMap("SELECT * FROM lab_runtime WHERE id=1"); }
    private void assertJournal(String status, String stage, String failure) {
        var value = journalSnapshot(); assertThat(value.get("status")).isEqualTo(status);
        assertThat(value.get("stage")).isEqualTo(stage); assertThat(value.get("failure_code")).isEqualTo(failure);
    }
    private String slotOwner() { return jdbc.queryForObject("SELECT occupied_run_id FROM lab_job_slot WHERE id=1", String.class); }
    private void assertLeaseAvailable() { try (var lease = MariaDbRuntimeLease.acquire(dataSource)) { lease.verifyHeld(); } }
    private void assertCompletedPending(String run) {
        var job = jobs.get(run); assertThat(job.status()).isEqualTo(LabJobService.Status.COMPLETED);
        assertThat(job.exportStatus()).isEqualTo(LabJobService.ExportStatus.PENDING); assertThat(job.exportCompletedAt()).isNull();
        assertThat(slotOwner()).isEqualTo(run);
        assertOutbox(run, false);
    }
    private List<List<Map<String, Object>>> businessSnapshot() {
        return List.of(jdbc.queryForList("SELECT * FROM demo_run ORDER BY id"),
            jdbc.queryForList("SELECT * FROM demo_outcome ORDER BY run_id,input_sequence"),
            jdbc.queryForList("SELECT run_id,scenario_version,source_sha256,source_size,status,created_at,source_verified_at,queued_at,completed_at,terminated_at FROM lab_job ORDER BY run_id"),
            jdbc.queryForList("SELECT * FROM lab_outbox WHERE event_type='DISPATCH' ORDER BY id"),
            jdbc.queryForList("SELECT id,job_run_id,event_type,source_sha256,created_at FROM lab_outbox WHERE event_type='EXPORT' ORDER BY id"));
    }
    private void assertCounts(String run) {
        var value = jdbc.queryForMap("SELECT input_count,success_count,failure_count,duplicate_count,pending_count FROM demo_run WHERE id=?", run);
        int[] expected = {12, 7, 3, 2, 0}; int index = 0;
        for (String key : List.of("input_count", "success_count", "failure_count", "duplicate_count", "pending_count")) {
            assertThat(((Number) value.get(key)).intValue()).isEqualTo(expected[index++]);
        }
        assertThat(jdbc.queryForObject("SELECT COUNT(*) FROM demo_run", Long.class)).isEqualTo(1L);
        assertThat(jdbc.queryForObject("SELECT COUNT(*) FROM demo_outcome WHERE run_id=?", Long.class, run)).isEqualTo(12L);
    }
    private ExportBundle bundle(String run) { return ExportBundle.from(jobs.exportSnapshot(run, jobs.get(run).sourceSha256())); }
    private void assertBundleUnchanged(String run, ExportBundle expected) {
        var actual = bundle(run);
        assertThat(actual.result().key()).isEqualTo(expected.result().key());
        assertThat(actual.failures().key()).isEqualTo(expected.failures().key());
        assertThat(actual.result().bytes()).isEqualTo(expected.result().bytes());
        assertThat(actual.failures().bytes()).isEqualTo(expected.failures().bytes());
        assertThat(actual.result().sha256()).isEqualTo(expected.result().sha256());
        assertThat(actual.failures().sha256()).isEqualTo(expected.failures().sha256());
    }
    private void assertSourceUnchanged(String run) {
        byte[] databaseBytes = jdbc.queryForObject("SELECT source_bytes FROM lab_job WHERE run_id=?", byte[].class, run);
        assertThat(databaseBytes).isEqualTo(source);
        byte[] rawBytes = s3.getObjectAsBytes(GetObjectRequest.builder().bucket(bucket).key(jobs.get(run).sourceObjectKey()).build()).asByteArray();
        assertThat(rawBytes).isEqualTo(source);
    }
    private List<String> remoteKeys(String run) {
        var page = s3.listObjectsV2(ListObjectsV2Request.builder().bucket(bucket).prefix("result/" + run + "/").build());
        assertThat(page.isTruncated()).isFalse(); return page.contents().stream().map(object -> object.key()).sorted().toList();
    }
    private void assertExported(String run, ExportBundle expected) {
        var job = jobs.get(run); assertThat(job.status()).isEqualTo(LabJobService.Status.COMPLETED);
        assertThat(job.exportStatus()).isEqualTo(LabJobService.ExportStatus.EXPORTED); assertThat(job.exportCompletedAt()).isNotNull();
        assertThat(slotOwner()).isNull(); assertCounts(run); assertBundleUnchanged(run, expected);
        for (var document : List.of(expected.result(), expected.failures())) {
            byte[] actual = s3.getObjectAsBytes(GetObjectRequest.builder().bucket(bucket).key(document.key()).build()).asByteArray();
            assertThat(actual).isEqualTo(document.bytes()); assertThat(document.matches(actual)).isTrue();
        }
        assertThat(remoteKeys(run)).containsExactlyInAnyOrder(expected.result().key(), expected.failures().key());
        assertOutbox(run, true);
    }

    private void assertOutbox(String run, boolean exported) {
        var rows = jdbc.queryForList("SELECT event_type,status,acknowledged_at FROM lab_outbox WHERE job_run_id=? ORDER BY event_type", run);
        assertThat(rows).hasSize(2);
        var dispatch = rows.getFirst(); assertThat(dispatch.get("event_type")).isEqualTo("DISPATCH");
        assertThat(dispatch.get("status")).isEqualTo("ACKNOWLEDGED"); assertThat(dispatch.get("acknowledged_at")).isNotNull();
        var export = rows.getLast(); assertThat(export.get("event_type")).isEqualTo("EXPORT");
        assertThat(export.get("status")).isEqualTo(exported ? "ACKNOWLEDGED" : "PENDING");
        if (exported) { assertThat(export.get("acknowledged_at")).isNotNull(); }
        else { assertThat(export.get("acknowledged_at")).isNull(); }
        assertThat(jdbc.queryForObject("SELECT COUNT(*) FROM lab_outbox", Long.class)).isEqualTo(2L);
    }

    private void assertOwnedKafkaTargetUnchanged() throws Exception {
        ContinuousRuntimeIT.requireExpectedCluster(kafka);
        assertThat(kafka.describeCluster().clusterId().get(10, TimeUnit.SECONDS)).isEqualTo(clusterId);
        var actual = kafka.describeTopics(List.of(topic)).allTopicNames().get(10, TimeUnit.SECONDS).get(topic);
        assertThat(actual.topicId()).isEqualTo(topicId); assertThat(actual.partitions()).hasSize(1);
        assertThat(actual.partitions().getFirst().partition()).isZero();
        assertThat(actual.partitions().getFirst().replicas()).hasSize(1);
    }

    private Optional<Long> committedOffset() throws Exception {
        try {
            var value = kafka.listConsumerGroupOffsets(group).partitionsToOffsetAndMetadata().get(10, TimeUnit.SECONDS);
            assertThat(value.keySet()).allMatch(partition -> partition.equals(new TopicPartition(topic, 0)));
            var offset = value.get(new TopicPartition(topic, 0)); return offset == null ? Optional.empty() : Optional.of(offset.offset());
        } catch (java.util.concurrent.ExecutionException failure) {
            if (failure.getCause() instanceof GroupIdNotFoundException) { return Optional.empty(); } throw failure;
        }
    }
    private long readCommittedEnd() throws Exception {
        var partition = new TopicPartition(topic, 0);
        return kafka.listOffsets(Map.of(partition, OffsetSpec.latest()), new ListOffsetsOptions(IsolationLevel.READ_COMMITTED))
            .all().get(10, TimeUnit.SECONDS).get(partition).offset();
    }
    private void awaitFinalOffset(Child recovery) throws Exception {
        long bound = deadline(45);
        while (System.nanoTime() < bound) {
            assertThat(recovery.process().isAlive()).isTrue();
            var offset = committedOffset();
            if (offset.isPresent()) {
                assertThat(offset.orElseThrow()).isEqualTo(1L);
                assertThat(readCommittedEnd()).isEqualTo(1L); return;
            }
            Thread.sleep(100);
        }
        throw new AssertionError("Bounded final offset observation failed");
    }
    private static long deadline(int seconds) { return System.nanoTime() + Duration.ofSeconds(seconds).toNanos(); }
    private static void await(BooleanSupplier condition, String description, Duration duration) throws Exception {
        long bound = System.nanoTime() + duration.toNanos();
        while (System.nanoTime() < bound) { if (condition.getAsBoolean()) { return; } Thread.sleep(100); }
        throw new AssertionError("Bounded wait failed: " + description);
    }
    private static void emitSuccess(Optional<Long> postUnpause, int replays) {
        var value = new LinkedHashMap<String, Object>();
        value.put("schemaVersion", 1); value.put("status", "PASS"); value.put("fixtureInput", 12);
        value.put("successCount", 7); value.put("failureCount", 3); value.put("duplicateCount", 2); value.put("pendingCount", 0);
        value.put("dbCommitBeforeFault", true); value.put("pausePersisted", true); value.put("pauseCode", "OFFSET_COMMIT_FAILED");
        value.put("runRefusedUnchanged", true); value.put("operatorResumeRecorded", true);
        value.put("postUnpauseCommitState", postUnpause.isEmpty() ? "NO_COMMIT" : "OBSERVED");
        value.put("postUnpauseCommittedOffset", postUnpause.orElse(null)); value.put("readCommittedEndOffset", 1);
        value.put("completedReplays", replays); value.put("businessRowsAndTimesUnchanged", true); value.put("exported", true);
        value.put("verifiedExportFiles", 2); value.put("slotFree", true); value.put("finalCommittedOffset", 1); value.put("finalLag", 0);
        value.put("childResourcesClosed", true);
        System.out.println("OFFSET_COMMIT_RECOVERY_RESULT " + JSON.writeValueAsString(value));
    }
    private void closeOwnedChildrenAndClients() throws Exception {
        boolean interrupted = Thread.interrupted(); boolean allClosed = true;
        try {
            // Signal every owned child before waiting, including when the JUnit deadline interrupted the parent.
            for (var child : children) { if (child.process().isAlive()) { child.process().destroyForcibly(); } }
            for (var child : children) {
                try { allClosed &= child.process().waitFor(10, TimeUnit.SECONDS); }
                catch (InterruptedException failure) { interrupted = true; allClosed = false; }
            }
            try { if (kafka != null) { kafka.close(Duration.ofSeconds(5)); kafka = null; } }
            finally { if (s3 != null) { s3.close(); s3 = null; } }
        } finally {
            if (interrupted) { Thread.currentThread().interrupt(); }
        }
        if (!allClosed) { throw new AssertionError("An owned child did not terminate during bounded cleanup"); }
    }
    private record Result(Optional<Long> postUnpause, int completedReplays) {}
    private record Child(Process process, Path checkpoint, Path log, String mode) {}
}
