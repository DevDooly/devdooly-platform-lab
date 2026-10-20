package io.github.devdooly.platformlab.jobs.runtime;

import io.github.devdooly.platformlab.demo.SyntheticScenario;
import io.github.devdooly.platformlab.jobs.CanonicalSource;
import io.github.devdooly.platformlab.jobs.LabJobService;
import io.github.devdooly.platformlab.jobs.S3ClientFactory;
import io.github.devdooly.platformlab.jobs.S3RawSourceStore;
import io.github.devdooly.platformlab.jobs.SourceStagingService;
import java.nio.file.Files;
import java.nio.file.LinkOption;
import java.nio.file.Path;
import java.nio.file.attribute.PosixFilePermissions;
import java.sql.Connection;
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
import software.amazon.awssdk.core.sync.ResponseTransformer;
import software.amazon.awssdk.services.s3.S3Client;
import software.amazon.awssdk.services.s3.model.GetObjectRequest;
import software.amazon.awssdk.services.s3.model.GetObjectResponse;
import software.amazon.awssdk.services.s3.model.ListObjectsV2Request;
import tools.jackson.databind.JsonNode;
import tools.jackson.databind.json.JsonMapper;
import static org.assertj.core.api.Assertions.assertThat;

/** Real lease-session loss at an empty-export barrier; no pause, publish, repair or daemon recovery is invented. */
@SpringBootTest(properties = "logging.level.root=WARN")
@ActiveProfiles({"db-test", "worker"})
@EnabledIfSystemProperty(named = "lab.runtime-lease-loss.tests", matches = "true")
public class RuntimeLeaseLossIT {
    private static final JsonMapper JSON = JsonMapper.builder().build();
    private static final String DATABASE = "platform_lab_runtime_it";
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
    private DatabaseIdentity databaseIdentity;
    private long testDeadline;
    private boolean killAttempted;
    private FailurePhase failurePhase = FailurePhase.TEST_ENTRY;
    private enum FailurePhase {
        TEST_ENTRY, SERVICE_GUARDS, KAFKA_CREATE, COORDINATOR_READY, STAGE_INPUT,
        PRE_FAULT_INVARIANTS, START_DAEMON, LEASE_HELD_READY, CONTROL_IDENTITY,
        OWNER_RECHECK, KILL_CONNECTION, LOCK_RELEASE, KILL_ACK, CHILD_TERMINATED,
        FRESH_LEASE, FINAL_INVARIANTS, CLOSE_CLIENTS
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
    void lostNamedLockConnectionStopsBeforePublishWithoutInventedPause() throws Exception {
        testDeadline = System.nanoTime() + Duration.ofSeconds(400).toNanos();
        try {
            performExperiment();
            failurePhase = FailurePhase.CLOSE_CLIENTS; closeOwnedChildrenAndClients();
            remainingMillis(); emitSuccess();
        } catch (Throwable failure) {
            if (failure instanceof InterruptedException) { Thread.currentThread().interrupt(); }
            System.out.println("RUNTIME_LEASE_LOSS_RESULT {\"schemaVersion\":1,\"status\":\"FAIL\",\"failureCode\":\"VALIDATION_FAILED\",\"failurePhase\":\"" + failurePhase.name()
                + "\",\"failureKind\":\"" + failureKind(failure).name() + "\",\"failureSourceLine\":" + failureSourceLine(failure) + "}");
            throw new AssertionError("Runtime lease loss validation failed; inspect private diagnostics");
        } finally {
            try { closeOwnedChildrenAndClients(); }
            catch (Throwable failure) { throw new AssertionError("Owned child or client cleanup failed; inspect private diagnostics"); }
        }
    }

    private void performExperiment() throws Exception {
        failurePhase = FailurePhase.SERVICE_GUARDS;
        requireEmptyDedicatedSchemaAndPristinePolicy();
        assertThat(CanonicalSource.validate(SyntheticScenario.NAME, source).events()).hasSize(12);
        sourceCommit = ContinuousRuntimeIT.guardedSourceCommit(); bucket = ContinuousRuntimeIT.guardedBucket();
        privateDirectory = RuntimeLeaseLossProbe.controlDirectory();
        try (var files = Files.list(privateDirectory)) { assertThat(files.toList()).isEmpty(); }
        s3 = S3ClientFactory.createGarage(ContinuousRuntimeIT.guardedS3Endpoint(), "garage", StaticCredentialsProvider.create(
            AwsBasicCredentials.create(ContinuousRuntimeIT.required("LAB_S3_TEST_ACCESS_KEY"), ContinuousRuntimeIT.required("LAB_S3_TEST_SECRET_KEY"))));
        raw = new S3RawSourceStore(s3, bucket);
        var emptyBucket = s3.listObjectsV2(ListObjectsV2Request.builder().bucket(bucket).maxKeys(8).build());
        assertThat(emptyBucket.isTruncated()).isFalse(); assertThat(emptyBucket.contents()).isEmpty();
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
        failurePhase = FailurePhase.COORDINATOR_READY; requireInitiallyEmptyGroup();

        failurePhase = FailurePhase.STAGE_INPUT;
        String run = "runtime-it-" + UUID.randomUUID(); ContinuousRuntimeIT.requireOwnedRun(run);
        var queued = new SourceStagingService(jobs, raw).stage(run, SyntheticScenario.NAME, source);
        assertThat(queued.status()).isEqualTo(LabJobService.Status.QUEUED);
        assertThat(queued.exportStatus()).isEqualTo(LabJobService.ExportStatus.NOT_REQUESTED);
        assertSourceUnchanged(run); Remote rawBefore = remote(queued.sourceObjectKey());
        failurePhase = FailurePhase.PRE_FAULT_INVARIANTS;
        var businessBefore = businessSnapshot(); assertPreserved(run, businessBefore, rawBefore);
        assertNoKafkaProgress(); assertOwnedKafkaTargetUnchanged();

        failurePhase = FailurePhase.START_DAEMON;
        Child child = startProbe(run);
        failurePhase = FailurePhase.LEASE_HELD_READY;
        JsonNode ready = awaitReady(child);
        long capturedId = ready.get("leaseConnectionId").longValue();
        String capturedUser = ready.get("leaseCurrentUser").asText();
        Map<String, Object> journalBefore = journalSnapshot();
        assertRunningExportJournal(journalBefore);
        assertThat(businessSnapshot()).isEqualTo(businessBefore);
        assertThat(child.process().isAlive()).isTrue();
        killCapturedLeaseOnce(child, capturedId, capturedUser);
        failurePhase = FailurePhase.KILL_ACK;
        assertThat(child.process().isAlive()).isTrue();
        RuntimeLeaseLossProbe.writeKillAcknowledgement(child.folder());
        failurePhase = FailurePhase.CHILD_TERMINATED;
        awaitExited(child, 90); assertTerminalExit(child);
        assertThat(journalSnapshot()).isEqualTo(journalBefore);
        assertRunningExportJournal(journalSnapshot());
        assertPreserved(run, businessBefore, rawBefore); assertNoKafkaProgress();

        failurePhase = FailurePhase.FRESH_LEASE;
        // Only after old process exit and the real client/context/lease-close receipt. No state mutations or new daemon.
        assertThat(child.process().isAlive()).isFalse(); assertTerminalExit(child);
        assertLockAbsent();
        try (var fresh = MariaDbRuntimeLease.acquire(dataSource)) { fresh.verifyHeld(); }
        assertLockAbsent(); assertThat(journalSnapshot()).isEqualTo(journalBefore);
        failurePhase = FailurePhase.FINAL_INVARIANTS;
        assertThat(killAttempted).isTrue(); assertThat(children).hasSize(1);
        assertThat(children).allSatisfy(owned -> assertThat(owned.process().isAlive()).isFalse());
        assertPreserved(run, businessBefore, rawBefore); assertNoKafkaProgress();
        assertOwnedKafkaTargetUnchanged(); assertDatabaseTargetUnchanged();
        assertThat(journalSnapshot()).isEqualTo(journalBefore); assertRunningExportJournal(journalSnapshot());
        remainingMillis();
    }

    private void requireEmptyDedicatedSchemaAndPristinePolicy() throws Exception {
        assertThat(Runtime.version().feature()).isEqualTo(21); assertThat(ZoneId.systemDefault()).isEqualTo(ZoneId.of("Asia/Seoul"));
        assertThat(ContinuousRuntimeIT.required("DB_TEST_USERNAME")).isEqualTo("runtimeit");
        jdbc.setQueryTimeout(3);
        try (var connection = dataSource.getConnection()) {
            requireGuardedConnection(connection); var observed = connectionObservation(connection);
            assertThat(observed.owner()).isNull(); databaseIdentity = observed.identity();
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
        assertThat(jdbc.queryForObject("SELECT COUNT(*) FROM lab_runtime", Long.class)).isEqualTo(1L);
        var initial = journalSnapshot();
        assertThat(initial.get("status")).isEqualTo("NOT_STARTED"); assertThat(initial.get("stage")).isEqualTo("IDLE");
        assertThat(initial.get("failure_code")).isNull(); assertThat(initial.get("source_commit")).isEqualTo("unknown");
        assertThat(initial.get("started_at")).isNull(); assertThat(initial.get("heartbeat_at")).isNull(); assertThat(initial.get("stopped_at")).isNull();
        try (var lease = MariaDbRuntimeLease.acquire(dataSource)) { lease.verifyHeld(); }
        assertLockAbsent(); remainingMillis();
    }

    private Child startProbe(String run) throws Exception {
        Path folder = Files.createDirectory(privateDirectory.resolve("daemon-" + UUID.randomUUID()),
            PosixFilePermissions.asFileAttribute(PosixFilePermissions.fromString("rwx------")));
        Path log = Files.createFile(folder.resolve("child.log"), PosixFilePermissions.asFileAttribute(PosixFilePermissions.fromString("rw-------")));
        String classpath = System.getProperty("surefire.test.class.path", System.getProperty("java.class.path"));
        Path java = Path.of(System.getProperty("java.home"), "bin", "java");
        var command = List.of(java.toString(), "-Xmx256m", "-Duser.timezone=Asia/Seoul", "-cp", classpath,
            RuntimeLeaseLossProbe.class.getName(), "daemon", topic, group, folder.resolve("ready.json").toString(),
            folder.resolve("kill-ack.json").toString(), folder.resolve("exit.json").toString(), run);
        var builder = new ProcessBuilder(command).redirectErrorStream(true).redirectOutput(log.toFile());
        builder.environment().put("DB_URL", ContinuousRuntimeIT.disposableDatabaseUrl());
        builder.environment().put("DB_USERNAME", ContinuousRuntimeIT.required("DB_TEST_USERNAME"));
        builder.environment().put("DB_PASSWORD", ContinuousRuntimeIT.required("DB_TEST_PASSWORD"));
        builder.environment().put("LAB_ENVIRONMENT", "isolated-lab");
        remainingMillis(); var child = new Child(builder.start(), folder); children.add(child); return child;
    }
    private JsonNode awaitReady(Child child) throws Exception {
        Path path = child.folder().resolve("ready.json");
        long deadline = Math.min(testDeadline, System.nanoTime() + Duration.ofSeconds(90).toNanos());
        while (!Files.exists(path, LinkOption.NOFOLLOW_LINKS)) {
            assertThat(child.process().isAlive()).isTrue(); requireBefore(deadline);
            TimeUnit.NANOSECONDS.sleep(Math.min(Duration.ofMillis(100).toNanos(), Math.max(1, deadline - System.nanoTime())));
        }
        assertThat(child.process().isAlive()).isTrue();
        JsonNode value = RuntimeLeaseLossProbe.readPrivate(path);
        assertBoundControl(value, "LEASE_HELD_READY", Set.of("schemaVersion", "sourceCommit", "runId", "nonce", "phase",
            "leaseConnectionId", "leaseCurrentUser", "emptyExportObserved"));
        var id = value.get("leaseConnectionId");
        assertThat(id.isIntegralNumber()).isTrue(); assertThat(id.canConvertToLong()).isTrue(); assertThat(id.longValue()).isPositive();
        var user = value.get("leaseCurrentUser"); assertThat(user.isString()).isTrue();
        assertThat(user.asText()).startsWith("runtimeit@").hasSizeBetween(1, 256).doesNotContain("\r", "\n");
        assertTrue(value, "emptyExportObserved"); requireBefore(deadline); return value;
    }
    private void awaitExited(Child child, int seconds) throws Exception {
        long deadline = Math.min(testDeadline, System.nanoTime() + Duration.ofSeconds(seconds).toNanos());
        long left = deadline - System.nanoTime();
        assertThat(left).isPositive(); assertThat(child.process().waitFor(left, TimeUnit.NANOSECONDS)).isTrue();
        assertThat(child.process().isAlive()).isFalse(); assertThat(child.process().exitValue()).isZero(); requireBefore(deadline);
    }
    private void assertTerminalExit(Child child) throws Exception {
        assertThat(child.process().isAlive()).isFalse(); assertThat(child.process().exitValue()).isZero();
        var value = RuntimeLeaseLossProbe.readPrivate(child.folder().resolve("exit.json"));
        assertBoundControl(value, "LEASE_LOSS_TERMINATED", Set.of("schemaVersion", "sourceCommit", "runId", "nonce", "phase",
            "actualLeaseLostObserved", "nextStageRejected", "publisherCalls", "receiverCalls", "emptyExportObserved",
            "resourcesClosed", "springContextClosed", "progressNotReady", "terminalCode", "leaseCloseReturned"));
        for (String key : List.of("actualLeaseLostObserved", "nextStageRejected", "emptyExportObserved", "resourcesClosed",
            "springContextClosed", "progressNotReady", "leaseCloseReturned")) { assertTrue(value, key); }
        for (String key : List.of("publisherCalls", "receiverCalls")) {
            assertThat(value.get(key).isIntegralNumber()).isTrue(); assertThat(value.get(key).canConvertToLong()).isTrue();
            assertThat(value.get(key).longValue()).isZero();
        }
        assertThat(value.get("terminalCode").isString()).isTrue();
        assertThat(value.get("terminalCode").asText()).isEqualTo("RUNTIME_JOURNAL_UPDATE_UNVERIFIED");
        remainingMillis();
    }
    private void assertBoundControl(JsonNode value, String phase, Set<String> expected) {
        assertThat(value.isObject()).isTrue(); var keys = new java.util.HashSet<String>();
        value.properties().forEach(entry -> keys.add(entry.getKey())); assertThat(keys).isEqualTo(expected);
        assertThat(value.get("schemaVersion").isIntegralNumber()).isTrue(); assertThat(value.get("schemaVersion").canConvertToLong()).isTrue();
        assertThat(value.get("schemaVersion").longValue()).isEqualTo(1L);
        for (String key : List.of("sourceCommit", "runId", "nonce", "phase")) { assertThat(value.get(key).isString()).isTrue(); }
        assertThat(value.get("sourceCommit").asText()).isEqualTo(sourceCommit);
        assertThat(value.get("runId").asText()).isEqualTo(ContinuousRuntimeIT.required("LEASE_CONTROL_RUN_ID"));
        assertThat(value.get("nonce").asText()).isEqualTo(ContinuousRuntimeIT.required("LEASE_CONTROL_NONCE"));
        assertThat(value.get("phase").asText()).isEqualTo(phase);
    }
    private static void assertTrue(JsonNode value, String key) {
        assertThat(value.get(key).isBoolean()).isTrue(); assertThat(value.get(key).asBoolean()).isTrue();
    }

    private void killCapturedLeaseOnce(Child child, long capturedId, String capturedUser) throws Exception {
        assertThat(capturedId).isPositive(); assertThat(killAttempted).isFalse();
        failurePhase = FailurePhase.CONTROL_IDENTITY;
        // No arbitrary target: the same fresh guarded server, account and fixed catalog, on one distinct control connection.
        try (var connection = dataSource.getConnection()) {
            requireGuardedConnection(connection);
            var control = connectionObservation(connection);
            assertThat(control.identity()).isEqualTo(databaseIdentity);
            assertThat(control.identity().currentUser()).isEqualTo(capturedUser);
            assertThat(control.connectionId()).isNotEqualTo(capturedId);
            assertThat(control.owner()).isEqualTo(capturedId);
            assertThat(child.process().isAlive()).isTrue();
            ContinuousRuntimeIT.disposableDatabaseUrl();
            assertThat(ContinuousRuntimeIT.guardedSourceCommit()).isEqualTo(sourceCommit);
            failurePhase = FailurePhase.OWNER_RECHECK;
            // Immediate read on this same control connection, after all other preconditions, immediately before the sole KILL.
            var immediatelyBefore = connectionObservation(connection);
            assertThat(immediatelyBefore.identity()).isEqualTo(databaseIdentity);
            assertThat(immediatelyBefore.connectionId()).isEqualTo(control.connectionId()).isNotEqualTo(capturedId);
            assertThat(immediatelyBefore.identity().currentUser()).isEqualTo(capturedUser);
            assertThat(immediatelyBefore.owner()).isEqualTo(capturedId);
            remainingMillis(); assertThat(child.process().isAlive()).isTrue();
            failurePhase = FailurePhase.KILL_CONNECTION;
            try (var statement = connection.createStatement()) {
                statement.setQueryTimeout(sqlTimeoutSeconds()); killAttempted = true;
                // Positive decimal captured ID only. No KILL QUERY/USER, privilege changes, retry or alternate target.
                statement.execute("KILL CONNECTION " + Long.toString(capturedId));
            }
            failurePhase = FailurePhase.LOCK_RELEASE;
            long deadline = Math.min(testDeadline, System.nanoTime() + Duration.ofSeconds(10).toNanos());
            while (true) {
                var observed = connectionObservation(connection);
                assertThat(observed.identity()).isEqualTo(databaseIdentity);
                assertThat(observed.connectionId()).isEqualTo(control.connectionId());
                if (observed.owner() == null) { requireBefore(deadline); break; }
                // A new owner is never accepted as eventual release of this trial's captured session.
                assertThat(observed.owner()).isEqualTo(capturedId); requireBefore(deadline);
                TimeUnit.NANOSECONDS.sleep(Math.min(Duration.ofMillis(50).toNanos(), Math.max(1, deadline - System.nanoTime())));
            }
        }
        remainingMillis();
    }
    private void requireGuardedConnection(Connection connection) throws Exception {
        ContinuousRuntimeIT.disposableDatabaseUrl();
        assertThat(connection.getMetaData().getDatabaseProductName()).isEqualTo("MariaDB");
        assertThat(connection.getCatalog()).isEqualTo(DATABASE); assertThat(connection.getAutoCommit()).isTrue();
    }
    private ConnectionObservation connectionObservation(Connection connection) throws Exception {
        try (var statement = connection.prepareStatement("SELECT CONNECTION_ID(), CURRENT_USER(), DATABASE(), @@server_id, @@hostname, IS_USED_LOCK(?)")) {
            statement.setQueryTimeout(sqlTimeoutSeconds()); statement.setString(1, MariaDbRuntimeLease.lockName(DATABASE));
            try (var rows = statement.executeQuery()) {
                assertThat(rows.next()).isTrue(); long id = rows.getLong(1); assertThat(rows.wasNull()).isFalse(); assertThat(id).isPositive();
                String user = rows.getString(2), database = rows.getString(3);
                long serverId = rows.getLong(4); assertThat(rows.wasNull()).isFalse(); assertThat(serverId).isNotNegative();
                String hostname = rows.getString(5); long lockOwner = rows.getLong(6); Long owner = rows.wasNull() ? null : lockOwner;
                assertThat(user).startsWith("runtimeit@").hasSizeBetween(1, 256).doesNotContain("\r", "\n");
                assertThat(database).isEqualTo(DATABASE); assertThat(hostname).isNotBlank().hasSizeLessThanOrEqualTo(256);
                if (owner != null) { assertThat(owner).isPositive(); }
                assertThat(rows.next()).isFalse(); remainingMillis();
                return new ConnectionObservation(id, new DatabaseIdentity(user, database, serverId, hostname), owner);
            }
        }
    }
    private void assertDatabaseTargetUnchanged() throws Exception {
        try (var connection = dataSource.getConnection()) {
            requireGuardedConnection(connection); var observed = connectionObservation(connection);
            assertThat(observed.identity()).isEqualTo(databaseIdentity); assertThat(observed.owner()).isNull();
        }
    }
    private void assertLockAbsent() throws Exception {
        try (var connection = dataSource.getConnection()) {
            requireGuardedConnection(connection); var observed = connectionObservation(connection);
            if (databaseIdentity != null) { assertThat(observed.identity()).isEqualTo(databaseIdentity); }
            assertThat(observed.owner()).isNull();
        }
    }
    private int sqlTimeoutSeconds() { return (int) Math.max(1, Math.min(3, (remainingMillis() + 999) / 1000)); }

    private List<List<Map<String, Object>>> businessSnapshot() {
        var result = new ArrayList<List<Map<String, Object>>>();
        for (String sql : List.of("SELECT * FROM lab_job ORDER BY run_id", "SELECT * FROM lab_job_slot ORDER BY id",
            "SELECT * FROM lab_outbox ORDER BY id", "SELECT * FROM lab_admission_policy ORDER BY id",
            "SELECT * FROM demo_run ORDER BY id", "SELECT * FROM demo_outcome ORDER BY run_id,input_sequence")) {
            var rows = new ArrayList<Map<String, Object>>();
            for (var row : jdbc.queryForList(sql)) {
                var normalized = new LinkedHashMap<String, Object>();
                row.forEach((key, value) -> normalized.put(key, value instanceof byte[] bytes ? HexFormat.of().formatHex(bytes) : value));
                rows.add(normalized);
            }
            result.add(rows);
        }
        remainingMillis(); return result;
    }
    private void assertPreserved(String run, List<List<Map<String, Object>>> baseline, Remote rawBefore) {
        assertThat(businessSnapshot()).isEqualTo(baseline);
        var job = jobs.get(run); assertThat(job.status()).isEqualTo(LabJobService.Status.QUEUED);
        assertThat(job.exportStatus()).isEqualTo(LabJobService.ExportStatus.NOT_REQUESTED);
        assertThat(job.completedAt()).isNull(); assertThat(job.exportCompletedAt()).isNull(); assertThat(job.terminatedAt()).isNull();
        assertThat(job.sourceVerifiedAt()).isNotNull(); assertThat(job.queuedAt()).isNotNull(); assertThat(slotOwner()).isEqualTo(run);
        assertThat(jdbc.queryForObject("SELECT COUNT(*) FROM lab_job", Long.class)).isEqualTo(1L);
        assertThat(jdbc.queryForObject("SELECT COUNT(*) FROM demo_run", Long.class)).isZero();
        assertThat(jdbc.queryForObject("SELECT COUNT(*) FROM demo_outcome", Long.class)).isZero();
        assertThat(jdbc.queryForObject("SELECT COUNT(*) FROM lab_outbox WHERE event_type='EXPORT'", Long.class)).isZero();
        assertThat(jdbc.queryForObject("SELECT COUNT(*) FROM lab_outbox", Long.class)).isEqualTo(1L);
        var dispatch = jdbc.queryForMap("SELECT * FROM lab_outbox WHERE job_run_id=? AND event_type='DISPATCH'", run);
        assertThat(dispatch.get("status")).isEqualTo("PENDING"); assertThat(dispatch.get("acknowledged_at")).isNull();
        assertThat(dispatch.get("source_sha256")).isEqualTo(job.sourceSha256()); assertSourceUnchanged(run);
        Remote rawAfter = remote(job.sourceObjectKey());
        assertThat(rawAfter.bytes()).isEqualTo(rawBefore.bytes()); assertThat(rawAfter.size()).isEqualTo(rawBefore.size());
        assertThat(rawAfter.etag()).isEqualTo(rawBefore.etag()); assertThat(rawAfter.modifiedAt()).isEqualTo(rawBefore.modifiedAt());
        var objects = s3.listObjectsV2(ListObjectsV2Request.builder().bucket(bucket).maxKeys(8).build());
        assertThat(objects.isTruncated()).isFalse(); assertThat(objects.contents()).hasSize(1);
        assertThat(objects.contents().getFirst().key()).isEqualTo(job.sourceObjectKey()); remainingMillis();
    }
    private void assertSourceUnchanged(String run) {
        assertThat(jdbc.queryForObject("SELECT source_bytes FROM lab_job WHERE run_id=?", byte[].class, run)).isEqualTo(source);
        byte[] actual = raw.readAndVerify(jobs.get(run)); assertThat(actual).isEqualTo(source);
        var canonical = CanonicalSource.validate(SyntheticScenario.NAME, actual);
        assertThat(canonical.size()).isEqualTo(source.length); assertThat(canonical.sha256()).isEqualTo(jobs.get(run).sourceSha256());
        remainingMillis();
    }
    private Remote remote(String key) {
        ResponseTransformer<GetObjectResponse, Remote> bounded = (response, input) -> {
            Long declared = response.contentLength();
            if (declared == null || declared < 1 || declared > CanonicalSource.MAX_BYTES) {
                input.abort(); throw new AssertionError("Owned raw object declared length is invalid");
            }
            byte[] bytes = input.readNBytes(CanonicalSource.MAX_BYTES + 1);
            if (bytes.length != declared || bytes.length > CanonicalSource.MAX_BYTES) {
                input.abort(); throw new AssertionError("Owned raw object actual length is invalid");
            }
            return new Remote(bytes, declared, response.eTag(), response.lastModified());
        };
        remainingMillis(); var observed = s3.getObject(GetObjectRequest.builder().bucket(bucket).key(key).build(), bounded);
        assertThat(observed.bytes()).isEqualTo(source); assertThat(observed.size()).isEqualTo((long) source.length);
        assertThat(observed.etag()).isNotBlank(); assertThat(observed.modifiedAt()).isNotNull(); remainingMillis(); return observed;
    }
    private Map<String, Object> journalSnapshot() { return jdbc.queryForMap("SELECT * FROM lab_runtime WHERE id=1"); }
    private void assertRunningExportJournal(Map<String, Object> journal) {
        assertThat(journal.get("status")).isEqualTo("RUNNING"); assertThat(journal.get("stage")).isEqualTo("EXPORT");
        assertThat(journal.get("failure_code")).isNull(); assertThat(journal.get("source_commit")).isEqualTo(sourceCommit);
        assertThat(journal.get("started_at")).isNotNull(); assertThat(journal.get("heartbeat_at")).isNotNull(); assertThat(journal.get("stopped_at")).isNull();
    }
    private String slotOwner() { return jdbc.queryForObject("SELECT occupied_run_id FROM lab_job_slot WHERE id=1", String.class); }

    private void requireInitiallyEmptyGroup() throws Exception {
        // Startup readiness only, before the fixture: a single pending RPC and one shared 45-second bound.
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
            } finally { if (!future.isDone()) { future.cancel(false); } }
            remaining = bound - System.nanoTime();
            if (remaining <= 0) { throw new java.util.concurrent.TimeoutException("Initial coordinator readiness deadline exceeded"); }
            TimeUnit.NANOSECONDS.sleep(Math.min(Duration.ofMillis(250).toNanos(), remaining));
        }
    }
    private Optional<Long> committedOffset() throws Exception {
        try {
            var actual = kafka.listConsumerGroupOffsets(group).partitionsToOffsetAndMetadata().get(rpcMillis(), TimeUnit.MILLISECONDS);
            var partition = new TopicPartition(topic, 0); assertThat(actual.keySet()).allMatch(partition::equals);
            var offset = actual.get(partition); remainingMillis(); return offset == null ? Optional.empty() : Optional.of(offset.offset());
        } catch (java.util.concurrent.ExecutionException failure) {
            if (failure.getCause() instanceof GroupIdNotFoundException) { remainingMillis(); return Optional.empty(); } throw failure;
        }
    }
    private long readCommittedEnd() throws Exception {
        var partition = new TopicPartition(topic, 0);
        var actual = kafka.listOffsets(Map.of(partition, OffsetSpec.latest()), new ListOffsetsOptions(IsolationLevel.READ_COMMITTED))
            .all().get(rpcMillis(), TimeUnit.MILLISECONDS).get(partition);
        assertThat(actual).isNotNull(); remainingMillis(); return actual.offset();
    }
    private void assertNoKafkaProgress() throws Exception { assertThat(readCommittedEnd()).isZero(); assertThat(committedOffset()).isEmpty(); }
    private void assertOwnedKafkaTargetUnchanged() throws Exception {
        assertThat(kafka.describeCluster().clusterId().get(rpcMillis(), TimeUnit.MILLISECONDS)).isEqualTo(clusterId);
        assertThat(kafka.describeCluster().nodes().get(rpcMillis(), TimeUnit.MILLISECONDS)).hasSize(1);
        var actual = kafka.describeTopics(List.of(topic)).allTopicNames().get(rpcMillis(), TimeUnit.MILLISECONDS).get(topic);
        assertThat(actual.topicId()).isEqualTo(topicId); assertThat(actual.partitions()).hasSize(1);
        assertThat(actual.partitions().getFirst().partition()).isZero(); assertThat(actual.partitions().getFirst().replicas()).hasSize(1); remainingMillis();
    }
    private long remainingMillis() {
        long nanos = testDeadline - System.nanoTime(); if (nanos <= 0) { throw new AssertionError("Parent experiment deadline exhausted"); }
        return Math.max(1, TimeUnit.NANOSECONDS.toMillis(nanos));
    }
    private long rpcMillis() { return Math.min(10_000, remainingMillis()); }
    private void requireBefore(long deadline) {
        remainingMillis(); if (System.nanoTime() >= deadline) { throw new AssertionError("Observed phase completed after its deadline"); }
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
        StackTraceElement[] frames = failure.getStackTrace(); String own = RuntimeLeaseLossIT.class.getName();
        for (int index = 0; index < Math.min(frames.length, 64); index++) {
            var frame = frames[index];
            if ((frame.getClassName().equals(own) || frame.getClassName().startsWith(own + "$")) && "RuntimeLeaseLossIT.java".equals(frame.getFileName())
                && frame.getLineNumber() > 0 && frame.getLineNumber() <= 10000) { return frame.getLineNumber(); }
        }
        return null;
    }
    private static void emitSuccess() {
        var value = new LinkedHashMap<String, Object>(); value.put("schemaVersion", 1); value.put("status", "PASS");
        value.put("fixtureInput", 12); value.put("jobStatus", "QUEUED"); value.put("exportStatus", "NOT_REQUESTED");
        value.put("businessRuns", 0); value.put("businessOutcomes", 0); value.put("exportOutboxEntries", 0);
        value.put("dispatchStatus", "PENDING"); value.put("slotOccupied", true); value.put("emptyExportObserved", true);
        value.put("leaseSessionCaptured", true); value.put("controlIdentityMatched", true); value.put("ownerMatchedBeforeKill", true);
        value.put("ownedLeaseConnectionKilled", true); value.put("lockAbsentAfterKill", true); value.put("actualLeaseLostObserved", true);
        value.put("nextStageRejected", true); value.put("publisherCalls", 0); value.put("receiverCalls", 0); value.put("staleJournalUnchanged", true);
        value.put("journalStatus", "RUNNING"); value.put("journalStage", "EXPORT"); value.put("journalFailureCode", null);
        value.put("queuedJobUnchanged", true); value.put("sourceAndRawUnchanged", true); value.put("dispatchPendingUnchanged", true);
        value.put("readCommittedEndOffset", 0); value.put("commitState", "NO_COMMIT"); value.put("committedOffset", null);
        value.put("childResourcesClosed", true); value.put("springContextClosed", true); value.put("oldChildExited", true);
        value.put("freshLeaseAcquiredAfterExit", true); value.put("targetStable", true);
        System.out.println("RUNTIME_LEASE_LOSS_RESULT " + JSON.writeValueAsString(value));
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
    private record Child(Process process, Path folder) {}
    private record DatabaseIdentity(String currentUser, String database, long serverId, String hostname) {}
    private record ConnectionObservation(long connectionId, DatabaseIdentity identity, Long owner) {}
    private record Remote(byte[] bytes, Long size, String etag, java.time.Instant modifiedAt) {}
}
