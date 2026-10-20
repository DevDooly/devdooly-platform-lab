package io.github.devdooly.platformlab.jobs.runtime;

import io.github.devdooly.platformlab.demo.SyntheticScenario;
import io.github.devdooly.platformlab.jobs.CanonicalSource;
import io.github.devdooly.platformlab.jobs.LabJobService;
import io.github.devdooly.platformlab.jobs.S3ClientFactory;
import io.github.devdooly.platformlab.jobs.S3RawSourceStore;
import io.github.devdooly.platformlab.jobs.SourceStagingService;
import io.github.devdooly.platformlab.jobs.exporting.RuntimeProcessProbe;
import io.github.devdooly.platformlab.jobs.messaging.DispatchMessage;
import io.github.devdooly.platformlab.jobs.messaging.DispatchPublisher;
import io.github.devdooly.platformlab.jobs.messaging.KafkaClientFactory;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.LinkOption;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;
import java.nio.file.attribute.BasicFileAttributes;
import java.nio.file.attribute.PosixFilePermissions;
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
import org.apache.kafka.clients.consumer.ConsumerRecord;
import org.apache.kafka.clients.producer.ProducerRecord;
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
import software.amazon.awssdk.services.s3.model.ListObjectsV2Request;
import tools.jackson.core.StreamReadFeature;
import tools.jackson.core.json.JsonFactory;
import tools.jackson.databind.DeserializationFeature;
import tools.jackson.databind.JsonNode;
import tools.jackson.databind.json.JsonMapper;
import static org.assertj.core.api.Assertions.assertThat;

/** Actual malformed record, durable fail-stop and explicit unrepaired resume. No message repair or skip. */
@SpringBootTest(properties = "logging.level.root=WARN")
@ActiveProfiles({"db-test", "worker"})
@EnabledIfSystemProperty(named = "lab.invalid-message.tests", matches = "true")
public class InvalidMessageRuntimeIT {
    private static final JsonMapper JSON = JsonMapper.builder(JsonFactory.builder()
        .enable(StreamReadFeature.STRICT_DUPLICATE_DETECTION).build())
        .enable(DeserializationFeature.FAIL_ON_TRAILING_TOKENS).build();
    private static final String MALFORMED = "{\"runId\":";
    private static final String CONTROL = "/owned/api/target/invalid-message-control";
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
    private FailurePhase failurePhase = FailurePhase.TEST_ENTRY;
    private enum FailurePhase {
        TEST_ENTRY, SERVICE_GUARDS, KAFKA_CREATE, COORDINATOR_READY, MALFORMED_ACK,
        STAGE_INPUT, DISPATCH_ACK, FIRST_DAEMON, FIRST_PAUSE, FIRST_RUN_REFUSAL,
        OPERATOR_RESUME, SECOND_DAEMON, SECOND_PAUSE, SECOND_RUN_REFUSAL,
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
    void malformedFirstRecordPersistsPauseAndUnrepairedResumeRepauses() throws Exception {
        testDeadline = System.nanoTime() + Duration.ofSeconds(400).toNanos();
        try {
            performExperiment();
            failurePhase = FailurePhase.CLOSE_CLIENTS;
            closeOwnedChildrenAndClients();
            remainingMillis();
            emitSuccess();
        } catch (Throwable failure) {
            if (failure instanceof InterruptedException) { Thread.currentThread().interrupt(); }
            System.out.println("INVALID_MESSAGE_RUNTIME_RESULT {\"schemaVersion\":1,\"status\":\"FAIL\",\"failureCode\":\"VALIDATION_FAILED\",\"failurePhase\":\"" + failurePhase.name()
                + "\",\"failureKind\":\"" + failureKind(failure).name() + "\",\"failureSourceLine\":" + failureSourceLine(failure) + "}");
            throw new AssertionError("Invalid message runtime validation failed; inspect private diagnostics");
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
        privateDirectory = controlDirectory();
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

        failurePhase = FailurePhase.MALFORMED_ACK;
        var invalidProducer = KafkaClientFactory.producer(ContinuousRuntimeIT.guardedBootstrap());
        try {
            var ack = invalidProducer.send(new ProducerRecord<>(topic, 0, "invalid-fixture", MALFORMED))
                .get(Math.min(15_000, remainingMillis()), TimeUnit.MILLISECONDS);
            assertThat(ack.topic()).isEqualTo(topic); assertThat(ack.partition()).isZero();
            assertThat(ack.hasOffset()).isTrue(); assertThat(ack.offset()).isZero();
        } finally { invalidProducer.close(Duration.ofSeconds(10)); }
        assertThat(readCommittedEnd()).isEqualTo(1L); assertThat(committedOffset()).isEmpty();

        failurePhase = FailurePhase.STAGE_INPUT;
        String run = "runtime-it-" + UUID.randomUUID(); ContinuousRuntimeIT.requireOwnedRun(run);
        var queued = new SourceStagingService(jobs, raw).stage(run, SyntheticScenario.NAME, source);
        assertThat(queued.status()).isEqualTo(LabJobService.Status.QUEUED);
        assertThat(queued.exportStatus()).isEqualTo(LabJobService.ExportStatus.NOT_REQUESTED);
        assertSourceUnchanged(run);
        failurePhase = FailurePhase.DISPATCH_ACK;
        var publisher = KafkaClientFactory.producer(ContinuousRuntimeIT.guardedBootstrap());
        try {
            var ack = new DispatchPublisher(jobs, publisher, topic).publishOne().orElseThrow();
            assertThat(ack.topic()).isEqualTo(topic); assertThat(ack.partition()).isZero();
            assertThat(ack.hasOffset()).isTrue(); assertThat(ack.offset()).isEqualTo(1L);
        } finally { publisher.close(Duration.ofSeconds(10)); }
        assertDispatchAcknowledged(run); assertNoConsumerProgress();
        observeExactlyTwoRecords(run); // assign-only observer closes before either real worker starts.
        assertNoConsumerProgress();
        var baseline = businessSnapshot(); assertPreserved(run, baseline);

        failurePhase = FailurePhase.FIRST_DAEMON;
        Child first = startProbe("daemon"); awaitReady(first); awaitExited(first, false, 75);
        failurePhase = FailurePhase.FIRST_PAUSE;
        assertDaemonExit(first); assertPaused(); assertLeaseAvailable();
        assertPreserved(run, baseline); assertNoConsumerProgress();
        failurePhase = FailurePhase.FIRST_RUN_REFUSAL;
        assertRunRefused(run, baseline);
        failurePhase = FailurePhase.OPERATOR_RESUME;
        resumeOriginal(); assertPreserved(run, baseline); assertNoConsumerProgress();

        failurePhase = FailurePhase.SECOND_DAEMON;
        Child second = startProbe("daemon"); awaitReady(second); awaitExited(second, false, 75);
        failurePhase = FailurePhase.SECOND_PAUSE;
        assertDaemonExit(second); assertPaused(); assertLeaseAvailable();
        assertPreserved(run, baseline); assertNoConsumerProgress();
        failurePhase = FailurePhase.SECOND_RUN_REFUSAL;
        assertRunRefused(run, baseline);
        failurePhase = FailurePhase.FINAL_INVARIANTS;
        assertThat(children).allSatisfy(child -> assertThat(child.process().isAlive()).isFalse());
        assertPaused(); assertPreserved(run, baseline); assertNoConsumerProgress();
        assertOwnedKafkaTargetUnchanged(); assertLeaseAvailable();
    }

    private void observeExactlyTwoRecords(String run) throws Exception {
        String observerGroup = "platform-lab-runtime-test-group-" + UUID.randomUUID();
        ContinuousRuntimeIT.requireOwnedName(observerGroup);
        var observer = KafkaClientFactory.consumerForRuntime(ContinuousRuntimeIT.guardedBootstrap(), observerGroup);
        long bound = Math.min(testDeadline, System.nanoTime() + Duration.ofSeconds(30).toNanos());
        try {
            var partition = new TopicPartition(topic, 0);
            observer.assign(List.of(partition));
            // This changes only this unjoined observer's local position, never a committed group offset.
            observer.seek(partition, 0L);
            var records = new ArrayList<ConsumerRecord<String, String>>();
            while (records.size() < 2 && System.nanoTime() < bound) {
                long left = Math.min(500, TimeUnit.NANOSECONDS.toMillis(bound - System.nanoTime()));
                if (left < 1) { break; }
                observer.poll(Duration.ofMillis(left)).forEach(records::add);
                assertThat(records.size()).isLessThanOrEqualTo(2);
            }
            requireBefore(bound); assertThat(records).hasSize(2);
            var malformed = records.getFirst(); var normal = records.getLast();
            assertThat(malformed.topic()).isEqualTo(topic); assertThat(malformed.partition()).isZero();
            assertThat(malformed.offset()).isZero(); assertThat(malformed.key()).isEqualTo("invalid-fixture");
            assertThat(malformed.value()).isEqualTo(MALFORMED);
            assertThat(normal.topic()).isEqualTo(topic); assertThat(normal.partition()).isZero();
            assertThat(normal.offset()).isEqualTo(1L); assertThat(normal.key()).isEqualTo(run);
            assertThat(DispatchMessage.decode(normal.value())).isEqualTo(DispatchMessage.from(jobs.get(run)));
            assertThat(observer.subscription()).isEmpty(); assertThat(observer.assignment()).containsExactly(partition);
        } finally { observer.close(Duration.ofSeconds(10)); }
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


    private Child startProbe(String mode) throws Exception {
        assertThat(Set.of("daemon", "cli-run", "resume")).contains(mode);
        Path folder = Files.createDirectory(privateDirectory.resolve(mode + "-" + UUID.randomUUID()),
            PosixFilePermissions.asFileAttribute(PosixFilePermissions.fromString("rwx------")));
        String classpath = System.getProperty("surefire.test.class.path", System.getProperty("java.class.path"));
        Path java = Path.of(System.getProperty("java.home"), "bin", "java");
        var command = new ArrayList<>(List.of(java.toString(), "-Xmx256m", "-Duser.timezone=Asia/Seoul", "-cp", classpath,
            RuntimeProcessProbe.class.getName(), mode, topic, group, folder.resolve("checkpoint.json").toString(),
            folder.resolve("stop.request").toString(), folder.resolve("exit.json").toString(), "-"));
        Path log = folder.resolve("child.log");
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
        remainingMillis(); var child = new Child(builder.start(), folder, log); children.add(child); return child;
    }

    private void awaitReady(Child child) throws Exception {
        await(() -> Files.exists(child.folder().resolve("checkpoint.json"), LinkOption.NOFOLLOW_LINKS) || !child.process().isAlive(), 45);
        var value = privateJson(child.folder().resolve("checkpoint.json"));
        assertExactKeys(value, Set.of("phase", "mode"));
        assertThat(value.get("phase").isString()).isTrue(); assertThat(value.get("phase").asText()).isEqualTo("RUNNER_READY");
        assertThat(value.get("mode").isString()).isTrue(); assertThat(value.get("mode").asText()).isEqualTo("daemon");
    }
    private void awaitExited(Child child, boolean failureExpected, int seconds) throws Exception {
        assertThat(child.process().waitFor(Math.min(remainingMillis(), seconds * 1000L), TimeUnit.MILLISECONDS)).isTrue();
        assertThat(child.process().isAlive()).isFalse();
        if (failureExpected) { assertThat(child.process().exitValue()).isNotZero(); }
        else { assertThat(child.process().exitValue()).isZero(); }
        remainingMillis();
    }
    private void assertDaemonExit(Child child) throws Exception {
        assertThat(child.process().isAlive()).isFalse(); assertThat(child.process().exitValue()).isZero();
        var value = privateJson(child.folder().resolve("exit.json"));
        assertExactKeys(value, Set.of("resourcesClosed", "runtimeStatus"));
        assertThat(value.get("resourcesClosed").isBoolean()).isTrue(); assertThat(value.get("resourcesClosed").asBoolean()).isTrue();
        assertThat(value.get("runtimeStatus").isString()).isTrue();
        assertThat(value.get("runtimeStatus").asText()).isEqualTo("PAUSED_OPERATOR");
    }
    private static void assertExactKeys(JsonNode value, Set<String> expected) {
        assertThat(value.isObject()).isTrue(); var keys = new java.util.HashSet<String>();
        value.properties().forEach(entry -> keys.add(entry.getKey())); assertThat(keys).isEqualTo(expected);
    }
    private void assertRunRefused(String run, List<List<Map<String, Object>>> baseline) throws Exception {
        var paused = journalSnapshot(); assertPaused(); assertLeaseAvailable();
        Child refused = startProbe("cli-run"); awaitExited(refused, true, 40);
        byte[] log = privateBytes(refused.log(), 1_048_576);
        assertThat(new String(log, StandardCharsets.UTF_8)).contains("RuntimeStateStore$OperatorResumeRequiredException");
        assertThat(Files.exists(refused.folder().resolve("checkpoint.json"), LinkOption.NOFOLLOW_LINKS)).isFalse();
        assertThat(Files.exists(refused.folder().resolve("exit.json"), LinkOption.NOFOLLOW_LINKS)).isFalse();
        assertThat(journalSnapshot()).isEqualTo(paused); assertLeaseAvailable();
        assertPreserved(run, baseline); assertNoConsumerProgress();
    }
    private void resumeOriginal() throws Exception {
        var paused = journalSnapshot(); assertPaused(); assertLeaseAvailable();
        Child resume = startProbe("resume"); awaitExited(resume, false, 40);
        assertJournal("STOPPED", "STOPPED", null); assertLeaseAvailable(); var resumed = journalSnapshot();
        assertThat(resumed.get("started_at")).isEqualTo(paused.get("started_at"));
        assertThat(resumed.get("source_commit")).isEqualTo(paused.get("source_commit"));
        assertThat(resumed.get("stopped_at")).isNotNull(); assertThat(resumed.get("stopped_at")).isNotEqualTo(paused.get("stopped_at"));
        assertThat(resumed.get("heartbeat_at")).isEqualTo(resumed.get("stopped_at"));
        assertThat(Files.exists(resume.folder().resolve("checkpoint.json"), LinkOption.NOFOLLOW_LINKS)).isFalse();
        assertThat(Files.exists(resume.folder().resolve("exit.json"), LinkOption.NOFOLLOW_LINKS)).isFalse();
    }
    private void assertPaused() {
        assertJournal("PAUSED_OPERATOR", "CONSUME", "INVALID_MESSAGE"); var value = journalSnapshot();
        assertThat(value.get("source_commit")).isEqualTo(sourceCommit);
        assertThat(value.get("started_at")).isNotNull(); assertThat(value.get("stopped_at")).isNotNull();
        assertThat(value.get("heartbeat_at")).isEqualTo(value.get("stopped_at"));
    }
    private Map<String, Object> journalSnapshot() { return jdbc.queryForMap("SELECT * FROM lab_runtime WHERE id=1"); }
    private void assertJournal(String status, String stage, String failure) {
        var actual = journalSnapshot(); assertThat(actual.get("status")).isEqualTo(status);
        assertThat(actual.get("stage")).isEqualTo(stage); assertThat(actual.get("failure_code")).isEqualTo(failure);
    }
    private String slotOwner() { return jdbc.queryForObject("SELECT occupied_run_id FROM lab_job_slot WHERE id=1", String.class); }
    private void assertLeaseAvailable() { try (var lease = MariaDbRuntimeLease.acquire(dataSource)) { lease.verifyHeld(); } }

    private List<List<Map<String, Object>>> businessSnapshot() {
        var result = new ArrayList<List<Map<String, Object>>>();
        // Exact row contents and timestamps; BLOB bytes become deterministic private hex for Map equality.
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
        return result;
    }
    private void assertPreserved(String run, List<List<Map<String, Object>>> baseline) {
        assertThat(businessSnapshot()).isEqualTo(baseline);
        var job = jobs.get(run); assertThat(job.status()).isEqualTo(LabJobService.Status.QUEUED);
        assertThat(job.exportStatus()).isEqualTo(LabJobService.ExportStatus.NOT_REQUESTED);
        assertThat(job.completedAt()).isNull(); assertThat(job.exportCompletedAt()).isNull(); assertThat(job.terminatedAt()).isNull();
        assertThat(job.sourceVerifiedAt()).isNotNull(); assertThat(job.queuedAt()).isNotNull();
        assertThat(slotOwner()).isEqualTo(run);
        assertThat(jdbc.queryForObject("SELECT COUNT(*) FROM lab_job", Long.class)).isEqualTo(1L);
        assertThat(jdbc.queryForObject("SELECT COUNT(*) FROM demo_run", Long.class)).isZero();
        assertThat(jdbc.queryForObject("SELECT COUNT(*) FROM demo_outcome", Long.class)).isZero();
        assertThat(jdbc.queryForObject("SELECT COUNT(*) FROM lab_outbox WHERE event_type='EXPORT'", Long.class)).isZero();
        assertDispatchAcknowledged(run); assertSourceUnchanged(run);
        var result = s3.listObjectsV2(ListObjectsV2Request.builder().bucket(bucket).prefix("result/").build());
        assertThat(result.isTruncated()).isFalse(); assertThat(result.contents()).isEmpty();
    }
    private void assertDispatchAcknowledged(String run) {
        assertThat(jdbc.queryForObject("SELECT COUNT(*) FROM lab_outbox", Long.class)).isEqualTo(1L);
        var row = jdbc.queryForMap("SELECT * FROM lab_outbox WHERE job_run_id=? AND event_type='DISPATCH'", run);
        assertThat(row.get("status")).isEqualTo("ACKNOWLEDGED"); assertThat(row.get("acknowledged_at")).isNotNull();
        assertThat(row.get("source_sha256")).isEqualTo(jobs.get(run).sourceSha256());
    }
    private void assertSourceUnchanged(String run) {
        assertThat(jdbc.queryForObject("SELECT source_bytes FROM lab_job WHERE run_id=?", byte[].class, run)).isEqualTo(source);
        assertThat(raw.readAndVerify(jobs.get(run))).isEqualTo(source);
    }
    private void assertNoConsumerProgress() throws Exception {
        assertThat(readCommittedEnd()).isEqualTo(2L); assertThat(committedOffset()).isEmpty();
    }

    private Path controlDirectory() throws Exception {
        assertThat(ContinuousRuntimeIT.required("INVALID_CONTROL_DIR")).isEqualTo(CONTROL);
        assertThat(ContinuousRuntimeIT.required("INVALID_CONTROL_NONCE")).matches("[a-f0-9]{32}");
        assertThat(ContinuousRuntimeIT.required("INVALID_CONTROL_RUN_ID")).matches("[0-9]{1,18}");
        Path directory = Path.of(CONTROL);
        for (Path selected = directory; selected != null && selected.startsWith("/owned/api"); selected = selected.getParent()) {
            assertThat(Files.isSymbolicLink(selected)).isFalse();
        }
        assertThat(Files.isDirectory(directory, LinkOption.NOFOLLOW_LINKS)).isTrue();
        assertThat(Files.getPosixFilePermissions(directory, LinkOption.NOFOLLOW_LINKS)).isEqualTo(PosixFilePermissions.fromString("rwx------"));
        long uid = ((Number) Files.getAttribute(directory, "unix:uid", LinkOption.NOFOLLOW_LINKS)).longValue();
        long stagedUid = ((Number) Files.getAttribute(Path.of("/owned/api/pom.xml"), "unix:uid", LinkOption.NOFOLLOW_LINKS)).longValue();
        assertThat(uid).isPositive(); assertThat(uid).isEqualTo(stagedUid); return directory;
    }
    private void requireChildFolder(Path folder) throws Exception {
        assertThat(folder.isAbsolute()).isTrue(); assertThat(folder).isEqualTo(folder.normalize());
        assertThat(folder.getParent()).isEqualTo(privateDirectory);
        assertThat(folder.getFileName().toString()).matches("(?:daemon|cli-run|resume)-[a-f0-9-]{36}");
        assertThat(Files.isSymbolicLink(folder)).isFalse(); assertThat(Files.isDirectory(folder, LinkOption.NOFOLLOW_LINKS)).isTrue();
        assertThat(Files.getPosixFilePermissions(folder, LinkOption.NOFOLLOW_LINKS)).isEqualTo(PosixFilePermissions.fromString("rwx------"));
        assertThat(Files.getAttribute(folder, "unix:uid", LinkOption.NOFOLLOW_LINKS)).isEqualTo(
            Files.getAttribute(privateDirectory, "unix:uid", LinkOption.NOFOLLOW_LINKS));
    }
    private JsonNode privateJson(Path path) throws Exception {
        assertThat(Set.of("checkpoint.json", "exit.json")).contains(path.getFileName().toString());
        return JSON.readTree(privateBytes(path, 1024));
    }
    private byte[] privateBytes(Path path, int maximum) throws Exception {
        requireChildFolder(path.getParent());
        assertThat(Set.of("checkpoint.json", "exit.json", "child.log")).contains(path.getFileName().toString());
        assertThat(path.isAbsolute()).isTrue(); assertThat(path).isEqualTo(path.normalize());
        BasicFileAttributes before = Files.readAttributes(path, BasicFileAttributes.class, LinkOption.NOFOLLOW_LINKS);
        BasicFileAttributes parentBefore = Files.readAttributes(path.getParent(), BasicFileAttributes.class, LinkOption.NOFOLLOW_LINKS);
        requirePrivateFile(path, before, maximum);
        byte[] bytes;
        try (var input = Files.newInputStream(path, StandardOpenOption.READ, LinkOption.NOFOLLOW_LINKS)) {
            bytes = input.readNBytes(maximum + 1);
        }
        BasicFileAttributes after = Files.readAttributes(path, BasicFileAttributes.class, LinkOption.NOFOLLOW_LINKS);
        BasicFileAttributes parentAfter = Files.readAttributes(path.getParent(), BasicFileAttributes.class, LinkOption.NOFOLLOW_LINKS);
        requirePrivateFile(path, after, maximum); requireChildFolder(path.getParent());
        assertThat((long) bytes.length).isEqualTo(before.size()); assertThat(after.size()).isEqualTo(before.size());
        assertThat(after.fileKey()).isEqualTo(before.fileKey()); assertThat(after.lastModifiedTime()).isEqualTo(before.lastModifiedTime());
        assertThat(parentBefore.fileKey()).isNotNull(); assertThat(parentAfter.fileKey()).isEqualTo(parentBefore.fileKey());
        return bytes;
    }
    private void requirePrivateFile(Path path, BasicFileAttributes attributes, int maximum) throws Exception {
        assertThat(attributes.isRegularFile()).isTrue(); assertThat(attributes.fileKey()).isNotNull();
        assertThat(attributes.size()).isPositive().isLessThanOrEqualTo(maximum);
        assertThat(Files.isSymbolicLink(path)).isFalse();
        assertThat(((Number) Files.getAttribute(path, "unix:nlink", LinkOption.NOFOLLOW_LINKS)).longValue()).isEqualTo(1L);
        assertThat(Files.getAttribute(path, "unix:uid", LinkOption.NOFOLLOW_LINKS)).isEqualTo(
            Files.getAttribute(privateDirectory, "unix:uid", LinkOption.NOFOLLOW_LINKS));
        // The immutable original Probe writes atomic files with its real process umask, normally 0644 or 0600.
        var permissions = Files.getPosixFilePermissions(path, LinkOption.NOFOLLOW_LINKS);
        assertThat(permissions.equals(PosixFilePermissions.fromString("rw-------"))
            || permissions.equals(PosixFilePermissions.fromString("rw-r--r--"))).isTrue();
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
        StackTraceElement[] frames = failure.getStackTrace(); String own = InvalidMessageRuntimeIT.class.getName();
        for (int index = 0; index < Math.min(frames.length, 64); index++) {
            var frame = frames[index];
            if ((frame.getClassName().equals(own) || frame.getClassName().startsWith(own + "$")) && "InvalidMessageRuntimeIT.java".equals(frame.getFileName())
                && frame.getLineNumber() > 0 && frame.getLineNumber() <= 10000) { return frame.getLineNumber(); }
        }
        return null;
    }

    private static void emitSuccess() {
        var value = new LinkedHashMap<String, Object>(); value.put("schemaVersion", 1); value.put("status", "PASS");
        value.put("fixtureInput", 12); value.put("malformedRecordAck", true); value.put("malformedOffset", 0);
        value.put("dispatchBrokerAck", true); value.put("dispatchOffset", 1); value.put("firstPausePersisted", true);
        value.put("pauseCode", "INVALID_MESSAGE"); value.put("runtimeStage", "CONSUME"); value.put("firstRunRefusedUnchanged", true);
        value.put("operatorResumeRecorded", true); value.put("unrepairedResumeRepaused", true); value.put("secondRunRefusedUnchanged", true);
        value.put("queuedJobUnchanged", true); value.put("jobStatus", "QUEUED"); value.put("exportStatus", "NOT_REQUESTED");
        value.put("businessRuns", 0); value.put("businessOutcomes", 0); value.put("exportOutboxEntries", 0);
        value.put("slotOccupied", true); value.put("sourceAndRawUnchanged", true); value.put("dispatchAckUnchanged", true);
        value.put("firstCommitState", "NO_COMMIT"); value.put("firstCommittedOffset", null);
        value.put("secondCommitState", "NO_COMMIT"); value.put("secondCommittedOffset", null); value.put("readCommittedEndOffset", 2);
        value.put("childResourcesClosed", true); value.put("targetStable", true); value.put("automaticRepairPerformed", false);
        System.out.println("INVALID_MESSAGE_RUNTIME_RESULT " + JSON.writeValueAsString(value));
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

}
