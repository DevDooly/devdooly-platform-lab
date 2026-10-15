package io.github.devdooly.platformlab.jobs.runtime;

import io.github.devdooly.platformlab.demo.SyntheticScenario;
import io.github.devdooly.platformlab.jobs.CanonicalSource;
import io.github.devdooly.platformlab.jobs.LabJobService;
import io.github.devdooly.platformlab.jobs.S3ClientFactory;
import io.github.devdooly.platformlab.jobs.S3RawSourceStore;
import io.github.devdooly.platformlab.jobs.SourceStagingService;
import io.github.devdooly.platformlab.jobs.exporting.ExportBundle;
import io.github.devdooly.platformlab.jobs.exporting.RuntimeProcessProbe;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;
import java.time.Duration;
import java.time.ZoneId;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.Set;
import java.util.UUID;
import java.util.concurrent.TimeUnit;
import java.util.function.BooleanSupplier;
import javax.sql.DataSource;
import org.apache.kafka.clients.admin.Admin;
import org.apache.kafka.clients.admin.AdminClientConfig;
import org.apache.kafka.clients.admin.NewTopic;
import org.apache.kafka.clients.admin.OffsetSpec;
import org.apache.kafka.common.TopicPartition;
import org.apache.kafka.common.errors.GroupIdNotFoundException;
import org.apache.kafka.common.errors.GroupNotEmptyException;
import org.apache.kafka.common.errors.RetriableException;
import org.apache.kafka.common.errors.UnknownTopicOrPartitionException;
import org.junit.jupiter.api.AfterAll;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.TestInstance;
import org.junit.jupiter.api.condition.EnabledIfSystemProperty;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.springframework.transaction.PlatformTransactionManager;
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
 * Opt-in REAL continuous-runtime validation, never selected by default verify.
 * Select -Dlab.runtime.tests=true -Dtest=ContinuousRuntimeIT
 * -DargLine=-Duser.timezone=Asia/Seoul against disposable MariaDB/Garage/Kafka.
 * Parent only admits owned jobs; child production runner dispatches, consumes and exports.
 */
@SpringBootTest
@ActiveProfiles({"db-test", "worker"})
@EnabledIfSystemProperty(named = "lab.runtime.tests", matches = "true")
@TestInstance(TestInstance.Lifecycle.PER_CLASS)
public class ContinuousRuntimeIT {
    private static final JsonMapper JSON = JsonMapper.builder().build();
    @Autowired LabJobService jobs;
    @Autowired JdbcTemplate jdbc;
    @Autowired DataSource dataSource;
    @Autowired PlatformTransactionManager transactionManager;
    private final byte[] source = CanonicalSource.fixtureBytes();
    private final Set<String> ownedRuns = new LinkedHashSet<>();
    private final List<Probe> probes = new ArrayList<>();
    private S3Client s3;
    private S3RawSourceStore raw;
    private Admin kafka;
    private String topic;
    private String group;
    private String bucket;
    private String sourceCommit;
    private Path privateDirectory;

    @DynamicPropertySource static void guardBeforeFlyway(DynamicPropertyRegistry registry) {
        registry.add("spring.datasource.url", ContinuousRuntimeIT::disposableDatabaseUrl);
        registry.add("spring.datasource.username", () -> required("DB_TEST_USERNAME"));
        registry.add("spring.datasource.password", () -> required("DB_TEST_PASSWORD"));
    }

    public static String disposableDatabaseUrl() {
        String value = required("DB_TEST_URL");
        if (!value.matches("jdbc:mariadb://127\\.0\\.0\\.1:[0-9]{1,5}/platform_lab_runtime_it")) {
            throw new IllegalArgumentException("Requires disposable platform_lab_runtime_it on numeric loopback, without query options");
        }
        validPort(URI.create(value.substring("jdbc:".length()))); return value;
    }
    public static URI guardedS3Endpoint() {
        String value = required("LAB_S3_TEST_ENDPOINT");
        if (!value.matches("http://127\\.0\\.0\\.1:[0-9]{1,5}/?")) { throw new IllegalArgumentException("Requires numeric loopback S3 HTTP"); }
        URI endpoint = URI.create(value); validPort(endpoint); return endpoint;
    }
    public static String guardedBootstrap() {
        String value = required("LAB_KAFKA_TEST_BOOTSTRAP");
        if (!value.matches("127\\.0\\.0\\.1:[0-9]{1,5}")) { throw new IllegalArgumentException("Requires one numeric loopback Kafka endpoint"); }
        validPort(URI.create("http://" + value)); return value;
    }
    public static String guardedBucket() {
        String value = required("LAB_S3_TEST_BUCKET");
        if (!value.matches("platform-lab-s3-test-[a-z0-9-]{1,42}")) { throw new IllegalArgumentException("Requires dedicated test bucket prefix"); }
        return value;
    }
    public static void requireOwnedName(String value) {
        if (value == null || !value.matches("platform-lab-runtime-test-(?:topic|group)-[a-f0-9-]{36}")) {
            throw new IllegalArgumentException("Requires a UUID under the dedicated runtime test prefix");
        }
    }
    public static void requireOwnedRun(String value) {
        if (value == null || !value.matches("runtime-it-[a-f0-9-]{36}")) { throw new IllegalArgumentException("Requires an owned runtime run"); }
    }
    public static String required(String name) {
        String value = System.getenv(name);
        if (value == null || value.isBlank()) { throw new IllegalArgumentException(name + " required for disposable runtime test"); }
        return value;
    }
    public static String guardedSourceCommit() {
        String value = required("SOURCE_COMMIT");
        if (!value.matches("[a-f0-9]{40}")) { throw new IllegalArgumentException("Actual committed source identity is required"); }
        return value;
    }
    private static void validPort(URI value) {
        if (value.getPort() < 1 || value.getPort() > 65535) { throw new IllegalArgumentException("Invalid loopback port"); }
    }
    public static Admin admin() {
        return Admin.create(Map.of(AdminClientConfig.BOOTSTRAP_SERVERS_CONFIG, guardedBootstrap(),
            AdminClientConfig.CLIENT_ID_CONFIG, "platform-lab-runtime-test-admin-" + UUID.randomUUID(),
            AdminClientConfig.REQUEST_TIMEOUT_MS_CONFIG, "5000", AdminClientConfig.DEFAULT_API_TIMEOUT_MS_CONFIG, "10000",
            AdminClientConfig.RETRIES_CONFIG, "2"));
    }
    public static void requireExpectedCluster(Admin client) throws Exception {
        String expected = required("LAB_KAFKA_TEST_CLUSTER_ID");
        if (!expected.matches("[A-Za-z0-9_-]{16,64}")) { throw new IllegalArgumentException("Invalid dedicated cluster identity"); }
        var cluster = client.describeCluster();
        assertThat(cluster.clusterId().get(10, TimeUnit.SECONDS)).isEqualTo(expected);
        assertThat(cluster.nodes().get(10, TimeUnit.SECONDS)).hasSize(1);
    }

    @BeforeAll void requireActualServicesAndEmptyDedicatedSchema() throws Exception {
        assertThat(Runtime.version().feature()).isEqualTo(21);
        assertThat(ZoneId.systemDefault()).isEqualTo(ZoneId.of("Asia/Seoul"));
        try (var connection = dataSource.getConnection()) {
            assertThat(connection.getMetaData().getDatabaseProductName()).isEqualTo("MariaDB");
            assertThat(connection.getCatalog()).isEqualTo("platform_lab_runtime_it");
        }
        assertEmptyJobs();
        assertThat(jdbc.queryForObject("SELECT COUNT(*) FROM information_schema.TRIGGERS WHERE TRIGGER_SCHEMA = DATABASE()", Long.class)).isZero();
        for (String version : List.of("1", "2", "3")) {
            assertThat(jdbc.queryForObject("SELECT COUNT(*) FROM flyway_schema_history WHERE version = ? AND success = 1", Long.class, version)).isEqualTo(1L);
        }
        sourceCommit = guardedSourceCommit(); bucket = guardedBucket();
        s3 = S3ClientFactory.createGarage(guardedS3Endpoint(), "garage", StaticCredentialsProvider.create(
            AwsBasicCredentials.create(required("LAB_S3_TEST_ACCESS_KEY"), required("LAB_S3_TEST_SECRET_KEY"))));
        raw = new S3RawSourceStore(s3, bucket); kafka = admin(); requireExpectedCluster(kafka);
        privateDirectory = Files.createTempDirectory("platform-lab-runtime-it-");
    }

    @BeforeEach void createOwnedTopicAndResetOnlyDisposableJournal() throws Exception {
        assertEmptyJobs(); assertThat(probes).isEmpty(); assertThat(ownedRuns).isEmpty();
        resetDisposableJournal();
        io.github.devdooly.platformlab.jobs.AdmissionTestFixtures.makeEligible(jdbc);
        String id = UUID.randomUUID().toString();
        topic = "platform-lab-runtime-test-topic-" + id; group = "platform-lab-runtime-test-group-" + id;
        requireOwnedName(topic); requireOwnedName(group);
        kafka.createTopics(List.of(new NewTopic(topic, 1, (short) 1).configs(Map.of(
            "retention.ms", "3600000", "retention.bytes", "8388608", "max.message.bytes", "1024")))).all().get(10, TimeUnit.SECONDS);
        var actual = kafka.describeTopics(List.of(topic)).allTopicNames().get(10, TimeUnit.SECONDS).get(topic);
        assertThat(actual.partitions()).hasSize(1); assertThat(actual.partitions().getFirst().replicas()).hasSize(1);
    }

    @Test void sameDaemonAutomaticallyCompletesTwoIndependentlyAdmittedJobsAndReadApiObservesGracefulStop() throws Exception {
        Probe api = startProbe("api", null); JsonNode apiReady = awaitCheckpoint(api, "API_READY");
        URI observationUri = URI.create("http://127.0.0.1:" + apiReady.get("port").asInt() + "/api/jobs/observation");
        JsonNode baseline = getObservation(observationUri);
        assertThat(baseline.get("jobs").isEmpty()).isTrue();
        assertThat(baseline.at("/runtime/status").asText()).isEqualTo("NOT_STARTED");
        assertThat(journalStatus()).isEqualTo("NOT_STARTED");
        assertLeaseAvailable(); assertThat(logEnd()).isZero(); assertThat(committedOffset()).isEmpty();
        Probe daemon = startProbe("daemon", null); awaitCheckpoint(daemon, "RUNNER_READY");
        String first = stageNewRun(); awaitExported(first); assertFiles(first); assertCounts(first);
        assertThat(daemon.process().isAlive()).isTrue(); assertThat(slotOwner()).isNull();
        String second = stageNewRun(); awaitExported(second); assertFiles(second); assertCounts(second);
        assertThat(daemon.process().isAlive()).isTrue(); assertThat(slotOwner()).isNull();
        assertCommittedAndLag(2);
        var before = businessSnapshot();
        JsonNode observed = getObservation(observationUri); assertObservedJobs(observed, 2, "RUNNING");
        assertThat(businessSnapshot()).isEqualTo(before);
        stopGracefully(daemon); assertThat(journalStatus()).isEqualTo("STOPPED");
        assertLeaseAvailable();
        JsonNode stopped = getObservation(observationUri); assertObservedJobs(stopped, 2, "STOPPED");
        assertThat(businessSnapshot()).isEqualTo(before);
        String recorded = System.getProperty("lab.runtime.observation.file");
        if (recorded != null && !recorded.isBlank()) {
            Files.writeString(Path.of(recorded), JSON.writeValueAsString(stopped) + "\n", StandardCharsets.UTF_8,
                StandardOpenOption.CREATE_NEW, StandardOpenOption.WRITE);
        }
        stopGracefully(api);
        evidence("sequential-jobs-http-and-graceful-stop", 2, 0, 4, "STOPPED", true, true);
    }

    @Test void killedRealRunnerAfterFirstVerifiedExportObjectRestartsAndCompletesWithoutBusinessChanges() throws Exception {
        String run = stageNewRun(); Probe interrupted = startProbe("first-export", run);
        JsonNode checkpoint = awaitCheckpoint(interrupted, "FIRST_EXPORT_OBJECT_VERIFIED");
        assertThat(checkpoint.get("activeTransaction").asBoolean()).isFalse();
        assertThat(checkpoint.get("objectsVerified").asInt()).isEqualTo(1);
        assertThat(jobs.get(run).status()).isEqualTo(LabJobService.Status.COMPLETED);
        assertThat(jobs.get(run).exportStatus()).isEqualTo(LabJobService.ExportStatus.PENDING);
        assertThat(slotOwner()).isEqualTo(run); assertThat(journalStatus()).isEqualTo("RUNNING");
        assertThat(journalStage()).isEqualTo("EXPORT"); assertCommittedAndLag(1);
        var bundle = bundle(run); assertRemote(bundle.result());
        assertThat(remoteKeys(run)).containsExactly(bundle.result().key());
        var before = businessSnapshot();
        forceKillAtCheckpoint(interrupted);
        assertThat(journalStatus()).isEqualTo("RUNNING");
        Probe restarted = startProbe("daemon", null); awaitCheckpoint(restarted, "RUNNER_READY");
        awaitExported(run); assertFiles(run); assertCounts(run); assertCommittedAndLag(1);
        assertThat(businessSnapshot()).isEqualTo(before);
        stopGracefully(restarted); assertLeaseAvailable();
        evidence("forced-kill-first-export-and-restart", 1, 1, 2, "STOPPED", false, true);
    }

    @Test void corruptRawPersistsOperatorPauseAcrossRestartAndExplicitResumeCompletesOnlyAfterFixtureRepair() throws Exception {
        String run = stageNewRun(); var queued = jobs.get(run);
        byte[] corrupt = source.clone(); corrupt[1] ^= 1;
        s3.putObject(PutObjectRequest.builder().bucket(bucket).key(queued.sourceObjectKey()).build(), RequestBody.fromBytes(corrupt));
        Probe daemon = startProbe("daemon", null); awaitCheckpoint(daemon, "RUNNER_READY");
        await(() -> journalStatus().equals("PAUSED_OPERATOR"), "durable operator pause", Duration.ofSeconds(75));
        awaitExited(daemon, false);
        assertThat(journalFailure()).isEqualTo("SOURCE_INVALID");
        assertThat(jobs.get(run).status()).isEqualTo(LabJobService.Status.QUEUED);
        assertThat(slotOwner()).isEqualTo(run); assertThat(committedOffset()).isEmpty();
        assertThat(logEnd()).isEqualTo(1); assertThat(jdbc.queryForObject("SELECT COUNT(*) FROM demo_run", Long.class)).isZero();
        var paused = journalSnapshot(); var before = businessSnapshot();
        Probe refused = startProbe("cli-run", null); awaitExited(refused, true);
        assertThat(Files.readString(refused.log(), StandardCharsets.UTF_8).contains("RuntimeStateStore$OperatorResumeRequiredException")).isTrue();
        assertThat(Files.exists(refused.checkpoint())).isFalse();
        assertThat(journalSnapshot()).isEqualTo(paused); assertThat(businessSnapshot()).isEqualTo(before);
        assertThat(committedOffset()).isEmpty(); assertThat(slotOwner()).isEqualTo(run);
        assertThat(s3.getObjectAsBytes(GetObjectRequest.builder().bucket(bucket).key(queued.sourceObjectKey()).build()).asByteArray()).isEqualTo(corrupt);
        // Test fixture repair is explicit; the production raw reader never PUTs a replacement.
        s3.putObject(PutObjectRequest.builder().bucket(bucket).key(queued.sourceObjectKey()).build(), RequestBody.fromBytes(source));
        Probe resume = startProbe("resume", null); awaitExited(resume, false);
        assertThat(journalStatus()).isEqualTo("STOPPED"); assertThat(journalFailure()).isNull();
        Probe recovered = startProbe("daemon", null); awaitCheckpoint(recovered, "RUNNER_READY");
        awaitExported(run); assertFiles(run); assertCounts(run); assertCommittedAndLag(1);
        stopGracefully(recovered); assertLeaseAvailable();
        evidence("durable-pause-refused-restart-explicit-resume", 1, 0, 2, "STOPPED", false, true);
    }

    @Test void competingDaemonCannotAcquireRealDatabaseLockOrReplaceActiveJournalAndOwnerStillProcesses() throws Exception {
        Probe owner = startProbe("daemon", null); awaitCheckpoint(owner, "RUNNER_READY");
        Object started = journalSnapshot().get("started_at");
        Probe contender = startProbe("cli-run", null); awaitExited(contender, true);
        assertThat(Files.readString(contender.log(), StandardCharsets.UTF_8).contains("RuntimeLease$LeaseUnavailableException")).isTrue();
        assertThat(Files.exists(contender.checkpoint())).isFalse();
        assertThat(owner.process().isAlive()).isTrue(); assertThat(journalStatus()).isEqualTo("RUNNING");
        assertThat(journalSnapshot().get("started_at")).isEqualTo(started);
        String run = stageNewRun(); awaitExported(run); assertFiles(run); assertCounts(run); assertCommittedAndLag(1);
        assertThat(owner.process().isAlive()).isTrue(); stopGracefully(owner); assertLeaseAvailable();
        evidence("competing-daemon-refused-real-db-lock", 1, 0, 2, "STOPPED", false, true);
    }

    private String stageNewRun() {
        io.github.devdooly.platformlab.jobs.AdmissionTestFixtures.makeEligible(jdbc); // This test verifies runtime behavior, not elapsed admission cooldown.
        String run = "runtime-it-" + UUID.randomUUID(); requireOwnedRun(run); ownedRuns.add(run);
        var admitted = new SourceStagingService(jobs, raw).stage(run, SyntheticScenario.NAME, source);
        assertThat(admitted.status()).isEqualTo(LabJobService.Status.QUEUED); return run;
    }
    private void awaitExported(String run) throws Exception {
        await(() -> jobs.get(run).exportStatus() == LabJobService.ExportStatus.EXPORTED,
            "automatic verified export", Duration.ofSeconds(90));
        var job = jobs.get(run);
        assertThat(job.status()).isEqualTo(LabJobService.Status.COMPLETED); assertThat(job.exportCompletedAt()).isNotNull();
        assertThat(slotOwner()).isNull();
        assertThat(jdbc.queryForObject("SELECT COUNT(*) FROM lab_outbox WHERE job_run_id = ? AND status = 'ACKNOWLEDGED'", Long.class, run)).isEqualTo(2L);
    }
    private ExportBundle bundle(String run) { return ExportBundle.from(jobs.exportSnapshot(run, jobs.get(run).sourceSha256())); }
    private void assertFiles(String run) {
        var bundle = bundle(run); assertRemote(bundle.result()); assertRemote(bundle.failures());
        assertThat(remoteKeys(run)).containsExactlyInAnyOrder(bundle.result().key(), bundle.failures().key());
        assertThat(JSON.readTree(bundle.result().bytes()).get("outcomes").size()).isEqualTo(12);
        assertThat(JSON.readTree(bundle.failures().bytes()).get("failures").size()).isEqualTo(3);
    }
    private void assertRemote(ExportBundle.Document document) {
        byte[] actual = s3.getObjectAsBytes(GetObjectRequest.builder().bucket(bucket).key(document.key()).build()).asByteArray();
        assertThat(document.matches(actual)).isTrue(); assertThat(actual).isEqualTo(document.bytes());
    }
    private List<String> remoteKeys(String run) {
        return s3.listObjectsV2(ListObjectsV2Request.builder().bucket(bucket).prefix("result/" + run + "/").build()).contents()
            .stream().map(object -> object.key()).sorted().toList();
    }
    private void assertCounts(String run) {
        var actual = jdbc.queryForMap("SELECT input_count, success_count, failure_count, duplicate_count, pending_count FROM demo_run WHERE id = ?", run);
        assertThat(((Number) actual.get("input_count")).intValue()).isEqualTo(12);
        assertThat(((Number) actual.get("success_count")).intValue()).isEqualTo(7);
        assertThat(((Number) actual.get("failure_count")).intValue()).isEqualTo(3);
        assertThat(((Number) actual.get("duplicate_count")).intValue()).isEqualTo(2);
        assertThat(((Number) actual.get("pending_count")).intValue()).isZero();
        assertThat(jdbc.queryForObject("SELECT COUNT(*) FROM demo_outcome WHERE run_id = ?", Long.class, run)).isEqualTo(12L);
    }
    private List<List<Map<String, Object>>> businessSnapshot() {
        return List.of(jdbc.queryForList("SELECT * FROM demo_run ORDER BY id"), jdbc.queryForList("SELECT * FROM demo_outcome ORDER BY run_id,input_sequence"));
    }
    private JsonNode getObservation(URI uri) throws Exception {
        var client = HttpClient.newBuilder().connectTimeout(Duration.ofSeconds(5)).build();
        var response = client.send(HttpRequest.newBuilder(uri).timeout(Duration.ofSeconds(10)).GET().build(), HttpResponse.BodyHandlers.ofString(StandardCharsets.UTF_8));
        assertThat(response.statusCode()).isEqualTo(200);
        var body = JSON.readTree(response.body());
        assertThat(body.get("schemaVersion").asInt()).isEqualTo(1); assertThat(body.get("kind").asText()).isEqualTo("job-observation");
        assertThat(body.get("scope").asText()).isEqualTo("ISOLATED_LAB"); assertThat(body.get("environment").asText()).isEqualTo("ISOLATED_LAB");
        assertThat(body.get("sourceCommit").asText()).isEqualTo(sourceCommit); assertThat(body.get("publicExecutionEnabled").asBoolean()).isFalse();
        assertThat(body.get("synthetic").asBoolean()).isTrue(); assertThat(body.get("capturedAt").asText()).isNotBlank();
        return body;
    }
    private void assertObservedJobs(JsonNode body, int count, String runtimeStatus) {
        assertThat(body.at("/runtime/status").asText()).isEqualTo(runtimeStatus);
        assertThat(body.at("/runtime/sourceCommit").asText()).isEqualTo(sourceCommit);
        assertThat(body.at("/slot/occupiedRunId").isNull()).isTrue(); assertThat(body.get("jobs").size()).isEqualTo(count);
        for (var job : body.get("jobs")) {
            assertThat(ownedRuns).contains(job.get("runId").asText());
            assertThat(job.get("status").asText()).isEqualTo("COMPLETED"); assertThat(job.get("exportStatus").asText()).isEqualTo("EXPORTED");
            assertThat(job.get("fileEvidence").asText()).isEqualTo("VERIFIED_AT_EXPORT_COMMIT");
            assertThat(job.at("/counts/input").asInt()).isEqualTo(12); assertThat(job.at("/counts/failure").asInt()).isEqualTo(3);
            var expected = bundle(job.get("runId").asText());
            assertThat(job.at("/files/result/sha256").asText()).isEqualTo(expected.result().sha256());
            assertThat(job.at("/files/result/size").asInt()).isEqualTo(expected.result().size());
            assertThat(job.at("/files/failures/sha256").asText()).isEqualTo(expected.failures().sha256());
            assertThat(job.at("/files/failures/size").asInt()).isEqualTo(expected.failures().size());
        }
    }
    private Probe startProbe(String mode, String run) throws Exception {
        Path folder = Files.createDirectory(privateDirectory.resolve(mode + "-" + UUID.randomUUID()));
        Path checkpoint = folder.resolve("checkpoint.json"), stop = folder.resolve("stop.request"), exit = folder.resolve("exit.json"), log = folder.resolve("child.log");
        String cp = System.getProperty("surefire.test.class.path", System.getProperty("java.class.path"));
        Path java = Path.of(System.getProperty("java.home"), "bin", System.getProperty("os.name").startsWith("Windows") ? "java.exe" : "java");
        var command = new ProcessBuilder(java.toString(), "-Duser.timezone=Asia/Seoul", "-cp", cp, RuntimeProcessProbe.class.getName(),
            mode, topic, group, checkpoint.toString(), stop.toString(), exit.toString(), run == null ? "-" : run)
            .redirectErrorStream(true).redirectOutput(log.toFile());
        command.environment().put("DB_URL", disposableDatabaseUrl());
        command.environment().put("DB_USERNAME", required("DB_TEST_USERNAME"));
        command.environment().put("DB_PASSWORD", required("DB_TEST_PASSWORD"));
        command.environment().put("LAB_ENVIRONMENT", "isolated-lab");
        command.environment().put("LAB_RUNTIME_KAFKA_BOOTSTRAP", guardedBootstrap());
        command.environment().put("LAB_RUNTIME_KAFKA_TOPIC", topic); command.environment().put("LAB_RUNTIME_KAFKA_GROUP", group);
        command.environment().put("LAB_RUNTIME_S3_ENDPOINT", guardedS3Endpoint().toString());
        command.environment().put("LAB_RUNTIME_S3_REGION", "garage"); command.environment().put("LAB_RUNTIME_S3_BUCKET", bucket);
        command.environment().put("LAB_RUNTIME_S3_ACCESS_KEY_ID", required("LAB_S3_TEST_ACCESS_KEY"));
        command.environment().put("LAB_RUNTIME_S3_SECRET_ACCESS_KEY", required("LAB_S3_TEST_SECRET_KEY"));
        var child = command.start();
        var probe = new Probe(child, checkpoint, stop, exit, log, mode); probes.add(probe); return probe;
    }
    private JsonNode awaitCheckpoint(Probe probe, String phase) throws Exception {
        long deadline = System.nanoTime() + Duration.ofSeconds(100).toNanos();
        while (System.nanoTime() < deadline) {
            if (Files.isRegularFile(probe.checkpoint())) {
                var value = JSON.readTree(Files.readString(probe.checkpoint(), StandardCharsets.UTF_8));
                assertThat(value.get("phase").asText()).isEqualTo(phase);
                assertThat(value.get("mode").asText()).isEqualTo(probe.mode()); assertThat(probe.process().isAlive()).isTrue(); return value;
            }
            if (!probe.process().isAlive()) { throw new AssertionError("Runtime child exited before real readiness; inspect private child.log"); }
            Thread.sleep(100);
        }
        throw new AssertionError("Child did not reach its real bounded readiness checkpoint");
    }
    private void stopGracefully(Probe probe) throws Exception {
        assertThat(probe.process().isAlive()).isTrue(); Files.writeString(probe.stop(), "stop\n", StandardCharsets.US_ASCII, StandardOpenOption.CREATE_NEW);
        awaitExited(probe, false); assertThat(Files.isRegularFile(probe.exit())).isTrue();
        var exit = JSON.readTree(Files.readString(probe.exit(), StandardCharsets.UTF_8));
        assertThat(exit.get("resourcesClosed").asBoolean()).isTrue();
    }
    private void awaitExited(Probe probe, boolean requireFailure) throws Exception {
        assertThat(probe.process().waitFor(100, TimeUnit.SECONDS)).isTrue();
        assertThat(probe.process().isAlive()).isFalse();
        if (requireFailure) { assertThat(probe.process().exitValue()).isNotZero(); }
        else { assertThat(probe.process().exitValue()).isZero(); }
    }
    private void forceKillAtCheckpoint(Probe probe) throws Exception {
        assertThat(Files.isRegularFile(probe.checkpoint())).isTrue(); assertThat(probe.process().isAlive()).isTrue();
        probe.process().destroyForcibly(); assertThat(probe.process().waitFor(10, TimeUnit.SECONDS)).isTrue();
        assertThat(probe.process().exitValue()).isNotZero();
    }
    private Optional<Long> committedOffset() throws Exception {
        try {
            var offsets = kafka.listConsumerGroupOffsets(group).partitionsToOffsetAndMetadata().get(10, TimeUnit.SECONDS);
            var value = offsets.get(new TopicPartition(topic, 0)); return value == null ? Optional.empty() : Optional.of(value.offset());
        } catch (java.util.concurrent.ExecutionException failure) {
            if (failure.getCause() instanceof GroupIdNotFoundException) { return Optional.empty(); } throw failure;
        }
    }
    private long logEnd() throws Exception {
        var partition = new TopicPartition(topic, 0);
        return kafka.listOffsets(Map.of(partition, OffsetSpec.latest())).all().get(10, TimeUnit.SECONDS).get(partition).offset();
    }
    private void assertCommittedAndLag(long expected) throws Exception {
        assertThat(logEnd()).isEqualTo(expected); assertThat(committedOffset()).contains(expected);
    }
    private static void await(BooleanSupplier condition, String description, Duration bound) throws Exception {
        long deadline = System.nanoTime() + bound.toNanos();
        while (System.nanoTime() < deadline) { if (condition.getAsBoolean()) { return; } Thread.sleep(100); }
        throw new AssertionError("Bounded wait failed: " + description);
    }
    private void evidence(String name, int runs, int forcedKills, int files, String status, boolean http, boolean cleanedClients) throws Exception {
        long end = logEnd(), offset = committedOffset().orElseThrow();
        var value = new LinkedHashMap<String, Object>(); value.put("case", name); value.put("sourceCommit", sourceCommit);
        value.put("completedRuns", runs); value.put("forcedKills", forcedKills); value.put("verifiedFiles", files);
        value.put("logEnd", end); value.put("committedOffset", offset); value.put("lag", end - offset);
        value.put("outcomeRows", jdbc.queryForObject("SELECT COUNT(*) FROM demo_outcome", Long.class));
        value.put("runtimeStatus", status); value.put("slotFree", slotOwner() == null); value.put("actualHttpGet", http);
        value.put("gracefulResourcesClosed", cleanedClients);
        String json = JSON.writeValueAsString(value) + "\n"; System.out.print("RUNTIME_EVIDENCE " + json);
        String path = System.getProperty("lab.runtime.evidence.file");
        if (path != null && !path.isBlank()) { Files.writeString(Path.of(path), json, StandardCharsets.UTF_8, StandardOpenOption.CREATE, StandardOpenOption.APPEND); }
    }
    private String slotOwner() { return jdbc.queryForObject("SELECT occupied_run_id FROM lab_job_slot WHERE id = 1", String.class); }
    private void assertEmptyJobs() {
        for (String table : List.of("lab_job", "lab_outbox", "demo_run", "demo_outcome")) {
            assertThat(jdbc.queryForObject("SELECT COUNT(*) FROM " + table, Long.class)).isZero();
        }
        assertThat(jdbc.queryForObject("SELECT COUNT(*) FROM lab_job_slot", Long.class)).isEqualTo(1L); assertThat(slotOwner()).isNull();
    }

    // Runtime SQL names are deliberately local to this owned schema; never reset an operator's deployment.
    private Map<String, Object> journalSnapshot() { return jdbc.queryForMap("SELECT * FROM lab_runtime WHERE id = 1"); }
    private String journalStatus() { return (String) journalSnapshot().get("status"); }
    private String journalStage() { return (String) journalSnapshot().get("stage"); }
    private String journalFailure() { return (String) journalSnapshot().get("failure_code"); }
    private void resetDisposableJournal() {
        disposableDatabaseUrl(); assertLeaseAvailable();
        jdbc.update("UPDATE lab_runtime SET status='NOT_STARTED',stage='IDLE',failure_code=NULL,source_commit='unknown',started_at=NULL,heartbeat_at=NULL,stopped_at=NULL WHERE id=1");
    }
    private void assertLeaseAvailable() {
        try (var lease = MariaDbRuntimeLease.acquire(dataSource)) { lease.verifyHeld(); }
    }

    @AfterEach void cleanOnlyOwnedChildrenAndFixtures() throws Exception {
        for (var probe : probes) {
            if (probe.process().isAlive()) { probe.process().destroyForcibly(); assertThat(probe.process().waitFor(10, TimeUnit.SECONDS)).isTrue(); }
        }
        probes.clear();
        if (group != null) { deleteGroup(); }
        if (topic != null) { deleteTopic(); }
        for (String run : ownedRuns) {
            requireOwnedRun(run);
            for (String prefix : List.of("raw/" + run + "/", "result/" + run + "/")) {
                var page = s3.listObjectsV2(ListObjectsV2Request.builder().bucket(bucket).prefix(prefix).build());
                assertThat(page.isTruncated()).isFalse(); assertThat(page.contents().size()).isLessThanOrEqualTo(3);
                for (var object : page.contents()) {
                    assertThat(object.key()).startsWith(prefix);
                    s3.deleteObject(DeleteObjectRequest.builder().bucket(bucket).key(object.key()).build());
                }
                assertThat(s3.listObjectsV2(ListObjectsV2Request.builder().bucket(bucket).prefix(prefix).build()).contents()).isEmpty();
            }
        }
        new TransactionTemplate(transactionManager).executeWithoutResult(ignored -> {
            String occupied = jdbc.queryForObject("SELECT occupied_run_id FROM lab_job_slot WHERE id = 1 FOR UPDATE", String.class);
            if (occupied != null && !ownedRuns.contains(occupied)) { throw new IllegalStateException("Refusing to release an unowned slot"); }
            var rows = jdbc.queryForList("SELECT run_id FROM lab_job", String.class);
            assertThat(ownedRuns).containsAll(rows);
            if (occupied != null) { jdbc.update("UPDATE lab_job_slot SET occupied_run_id=NULL WHERE id=1"); }
            for (String run : ownedRuns) {
                jdbc.update("DELETE FROM lab_outbox WHERE job_run_id=?", run); jdbc.update("DELETE FROM demo_outcome WHERE run_id=?", run);
                jdbc.update("DELETE FROM demo_run WHERE id=?", run); jdbc.update("DELETE FROM lab_job WHERE run_id=?", run);
            }
        });
        ownedRuns.clear(); topic = null; group = null; assertEmptyJobs(); assertLeaseAvailable();
    }
    private void deleteGroup() throws Exception {
        requireOwnedName(group); long deadline = System.nanoTime() + Duration.ofSeconds(35).toNanos();
        while (true) {
            try { kafka.deleteConsumerGroups(List.of(group)).all().get(5, TimeUnit.SECONDS); return; }
            catch (java.util.concurrent.ExecutionException failure) {
                if (failure.getCause() instanceof GroupIdNotFoundException) { return; }
                if (!(failure.getCause() instanceof GroupNotEmptyException) && !(failure.getCause() instanceof RetriableException)) { throw failure; }
            }
            if (System.nanoTime() >= deadline) { throw new AssertionError("Owned group cleanup timed out"); } Thread.sleep(250);
        }
    }
    private void deleteTopic() throws Exception {
        requireOwnedName(topic);
        try { kafka.deleteTopics(List.of(topic)).all().get(10, TimeUnit.SECONDS); }
        catch (java.util.concurrent.ExecutionException failure) { if (!(failure.getCause() instanceof UnknownTopicOrPartitionException)) { throw failure; } }
        long deadline = System.nanoTime() + Duration.ofSeconds(25).toNanos();
        while (System.nanoTime() < deadline) {
            if (!kafka.listTopics().names().get(5, TimeUnit.SECONDS).contains(topic)) { return; } Thread.sleep(250);
        }
        throw new AssertionError("Owned topic cleanup timed out");
    }
    @AfterAll void closeParentClients() {
        if (kafka != null) { kafka.close(Duration.ofSeconds(5)); } if (s3 != null) { s3.close(); }
    }
    private record Probe(Process process, Path checkpoint, Path stop, Path exit, Path log, String mode) {}
}
