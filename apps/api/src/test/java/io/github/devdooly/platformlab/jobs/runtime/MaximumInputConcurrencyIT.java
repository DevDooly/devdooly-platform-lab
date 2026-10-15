package io.github.devdooly.platformlab.jobs.runtime;

import io.github.devdooly.platformlab.demo.SyntheticScenario;
import io.github.devdooly.platformlab.jobs.CanonicalSource;
import io.github.devdooly.platformlab.jobs.LabJobService;
import io.github.devdooly.platformlab.jobs.S3ClientFactory;
import io.github.devdooly.platformlab.jobs.S3RawSourceStore;
import io.github.devdooly.platformlab.jobs.SourceStagingService;
import io.github.devdooly.platformlab.jobs.exporting.ExportBundle;
import io.github.devdooly.platformlab.jobs.exporting.ResultExportService;
import io.github.devdooly.platformlab.jobs.exporting.RuntimeProcessProbe;
import io.github.devdooly.platformlab.jobs.exporting.S3ResultExportStore;
import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Proxy;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;
import java.security.MessageDigest;
import java.time.Duration;
import java.time.ZoneId;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.HexFormat;
import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.Set;
import java.util.UUID;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.CyclicBarrier;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicReference;
import java.util.function.BooleanSupplier;
import javax.sql.DataSource;
import org.apache.kafka.clients.admin.Admin;
import org.apache.kafka.clients.admin.NewTopic;
import org.apache.kafka.clients.admin.OffsetSpec;
import org.apache.kafka.clients.consumer.ConsumerConfig;
import org.apache.kafka.clients.consumer.KafkaConsumer;
import org.apache.kafka.common.TopicPartition;
import org.apache.kafka.common.errors.GroupIdNotFoundException;
import org.apache.kafka.common.errors.GroupNotEmptyException;
import org.apache.kafka.common.errors.RetriableException;
import org.apache.kafka.common.errors.UnknownTopicOrPartitionException;
import org.apache.kafka.common.serialization.ByteArrayDeserializer;
import org.junit.jupiter.api.AfterAll;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.TestInstance;
import org.junit.jupiter.api.condition.EnabledIfSystemProperty;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.ValueSource;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
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
 * Opt-in real MariaDB/Kafka/Garage functional boundaries; no production capacity claim.
 * -Dlab.maximum.tests=true -Dtest=MaximumInputConcurrencyIT
 * -DargLine=-Duser.timezone=Asia/Seoul. Reuses unchanged numeric-loopback/schema guards.
 */
@SpringBootTest
@ActiveProfiles({"db-test", "worker"})
@EnabledIfSystemProperty(named = "lab.maximum.tests", matches = "true")
@TestInstance(TestInstance.Lifecycle.PER_CLASS)
public class MaximumInputConcurrencyIT {
    private static final JsonMapper JSON = JsonMapper.builder().build();
    private static final String V2 = "sensor-validation-v2";
    @Autowired LabJobService jobs;
    @Autowired JdbcTemplate jdbc;
    @Autowired DataSource dataSource;
    @Autowired PlatformTransactionManager transactionManager;
    private final Set<String> ownedRuns = new LinkedHashSet<>();
    private final List<Probe> children = new ArrayList<>();
    private S3Client s3;
    private S3RawSourceStore raw;
    private Admin kafka;
    private String topic, group, bucket, commit;
    private Path privateDirectory;
    private boolean casePassed;
    private boolean failurePreserved;

    @DynamicPropertySource static void guardBeforeFlyway(DynamicPropertyRegistry registry) {
        registry.add("spring.datasource.url", ContinuousRuntimeIT::disposableDatabaseUrl);
        registry.add("spring.datasource.username", () -> ContinuousRuntimeIT.required("DB_TEST_USERNAME"));
        registry.add("spring.datasource.password", () -> ContinuousRuntimeIT.required("DB_TEST_PASSWORD"));
    }

    @BeforeAll void requireIsolatedServices() throws Exception {
        assertThat(Runtime.version().feature()).isEqualTo(21);
        assertThat(ZoneId.systemDefault()).isEqualTo(ZoneId.of("Asia/Seoul"));
        try (var connection = dataSource.getConnection()) {
            assertThat(connection.getMetaData().getDatabaseProductName()).isEqualTo("MariaDB");
            assertThat(connection.getCatalog()).isEqualTo("platform_lab_runtime_it");
        }
        assertEmpty();
        for (String version : List.of("1", "2", "3")) {
            assertThat(jdbc.queryForObject("SELECT COUNT(*) FROM flyway_schema_history WHERE version=? AND success=1", Long.class, version)).isEqualTo(1L);
        }
        assertThat(jdbc.queryForObject("SELECT COUNT(*) FROM information_schema.TRIGGERS WHERE TRIGGER_SCHEMA=DATABASE()", Long.class)).isZero();
        commit = ContinuousRuntimeIT.guardedSourceCommit(); bucket = ContinuousRuntimeIT.guardedBucket();
        s3 = S3ClientFactory.createGarage(ContinuousRuntimeIT.guardedS3Endpoint(), "garage", StaticCredentialsProvider.create(
            AwsBasicCredentials.create(ContinuousRuntimeIT.required("LAB_S3_TEST_ACCESS_KEY"), ContinuousRuntimeIT.required("LAB_S3_TEST_SECRET_KEY"))));
        raw = new S3RawSourceStore(s3, bucket); kafka = ContinuousRuntimeIT.admin(); ContinuousRuntimeIT.requireExpectedCluster(kafka);
        privateDirectory = Files.createTempDirectory("platform-lab-maximum-it-");
    }

    @BeforeEach void freshOwnedTopicAndEmptySchema() throws Exception {
        org.junit.jupiter.api.Assumptions.assumeFalse(failurePreserved, "Earlier isolated failure is preserved for operator inspection; no blind retry");
        casePassed = false;
        assertEmpty(); assertThat(ownedRuns).isEmpty(); assertThat(children).isEmpty();
        try (var lease = MariaDbRuntimeLease.acquire(dataSource)) { lease.verifyHeld(); }
        jdbc.update("UPDATE lab_runtime SET status='NOT_STARTED',stage='IDLE',failure_code=NULL,source_commit='unknown',started_at=NULL,heartbeat_at=NULL,stopped_at=NULL WHERE id=1");
        String id = UUID.randomUUID().toString();
        topic = "platform-lab-runtime-test-topic-" + id; group = "platform-lab-runtime-test-group-" + id;
        ContinuousRuntimeIT.requireOwnedName(topic); ContinuousRuntimeIT.requireOwnedName(group);
        kafka.createTopics(List.of(new NewTopic(topic, 1, (short) 1).configs(Map.of(
            "retention.ms", "3600000", "retention.bytes", "8388608", "max.message.bytes", "1024")))).all().get(10, TimeUnit.SECONDS);
    }

    @Test void exactOneMiBMaximumCompletesThreeTimesThroughSameRealDaemonAndPreservesLegacyV1() throws Exception {
        byte[] maximum = maximumBytes();
        Probe api = start("api"); JsonNode ready = checkpoint(api, "API_READY");
        URI observation = URI.create("http://127.0.0.1:" + ready.get("port").asInt() + "/api/jobs/observation");
        Probe daemon = start("daemon"); checkpoint(daemon, "RUNNER_READY");
        String legacy = newRun(); stage(legacy, SyntheticScenario.NAME, CanonicalSource.fixtureBytes());
        awaitExported(legacy); assertCounts(legacy, false); assertObjects(legacy, CanonicalSource.fixtureBytes(), false);
        String legacySnapshot = snapshot(legacy);
        var pointers = new LinkedHashMap<String, String>(); pointers.put(legacy, SyntheticScenario.NAME);
        for (int repeat = 0; repeat < 3; repeat++) {
            String run = newRun(); stage(run, V2, maximum); awaitExported(run);
            assertCounts(run, true); assertObjects(run, maximum, true);
            assertThat(snapshot(legacy)).isEqualTo(legacySnapshot); assertThat(daemon.process().isAlive()).isTrue();
            pointers.put(run, V2);
        }
        assertOffsets(4); assertPointersWithoutGroupCommit(pointers);
        JsonNode observed = getObservation(observation);
        assertThat(observed.get("jobs").size()).isEqualTo(4);
        for (var value : observed.get("jobs")) {
            boolean max = !value.get("runId").asText().equals(legacy);
            assertThat(value.get("status").asText()).isEqualTo("COMPLETED");
            assertThat(value.get("exportStatus").asText()).isEqualTo("EXPORTED");
            assertThat(value.get("fileEvidence").asText()).isEqualTo("VERIFIED_AT_EXPORT_COMMIT");
            assertThat(value.at("/counts/input").asInt()).isEqualTo(max ? 1000 : 12);
            assertThat(value.at("/counts/success").asInt()).isEqualTo(max ? 500 : 7);
            assertThat(value.at("/counts/failure").asInt()).isEqualTo(max ? 300 : 3);
            assertThat(value.at("/counts/duplicate").asInt()).isEqualTo(max ? 200 : 2);
            assertThat(value.at("/counts/pending").asInt()).isZero();
        }
        assertThat(observed.at("/slot/occupiedRunId").isNull()).isTrue();
        assertThat(jdbc.queryForObject("SELECT COUNT(*) FROM demo_outcome", Long.class)).isEqualTo(3012L);
        stop(daemon); stop(api);
        evidence("exact-one-mib-three-maximum-runs-plus-legacy", 4, 0, 8, maximum.length);
    }

    @ParameterizedTest @ValueSource(ints = {2, 8})
    void parallelDistinctInternalAdmissionsHaveOneWinnerAndNoLosingRawObjects(int cohort) throws Exception {
        byte[] bytes = CanonicalSource.fixtureBytes(V2);
        var barrier = new CyclicBarrier(cohort + 1);
        var admitted = new CountDownLatch(1); var conflicts = new CountDownLatch(cohort - 1); var allowStorage = new CountDownLatch(1);
        var winner = new AtomicReference<String>(); var externalCalls = new AtomicInteger();
        var staging = new SourceStagingService(jobs, (job, source) -> {
            assertThat(TransactionSynchronizationManager.isActualTransactionActive()).isFalse();
            assertThat(winner.compareAndSet(null, job.runId())).isTrue(); externalCalls.incrementAndGet(); admitted.countDown();
            try { assertThat(allowStorage.await(45, TimeUnit.SECONDS)).isTrue(); }
            catch (InterruptedException error) { Thread.currentThread().interrupt(); throw new IllegalStateException(error); }
            raw.storeAndVerify(job, source);
        });
        var runs = new ArrayList<String>(); for (int index = 0; index < cohort; index++) { runs.add(newRun()); }
        var pool = Executors.newFixedThreadPool(cohort);
        var futures = new ArrayList<java.util.concurrent.Future<Attempt>>();
        try {
            for (String run : runs) {
                futures.add(pool.submit(() -> {
                    barrier.await(15, TimeUnit.SECONDS);
                    try { staging.stage(run, V2, bytes); return new Attempt(run, true); }
                    catch (LabJobService.SlotBusyException expected) { conflicts.countDown(); return new Attempt(run, false); }
                }));
            }
            barrier.await(15, TimeUnit.SECONDS); assertThat(admitted.await(30, TimeUnit.SECONDS)).isTrue();
            assertThat(conflicts.await(30, TimeUnit.SECONDS)).isTrue();
            assertThat(externalCalls.get()).isEqualTo(1); assertThat(slot()).isEqualTo(winner.get());
            assertThat(jobs.get(winner.get()).status()).isEqualTo(LabJobService.Status.STAGING);
            assertThat(jdbc.queryForObject("SELECT COUNT(*) FROM lab_job", Long.class)).isEqualTo(1L);
            assertThat(jdbc.queryForObject("SELECT COUNT(*) FROM lab_outbox", Long.class)).isZero();
            for (String run : runs) { assertThat(keys("raw/" + run + "/")).isEmpty(); }
            allowStorage.countDown();
            var attempts = new ArrayList<Attempt>(); for (var future : futures) { attempts.add(future.get(45, TimeUnit.SECONDS)); }
            assertThat(attempts.stream().filter(Attempt::accepted).count()).isEqualTo(1);
            for (Attempt attempt : attempts) {
                if (!attempt.accepted()) {
                    assertThat(jdbc.queryForObject("SELECT COUNT(*) FROM lab_job WHERE run_id=?", Long.class, attempt.run())).isZero();
                    assertThat(jdbc.queryForObject("SELECT COUNT(*) FROM lab_outbox WHERE job_run_id=?", Long.class, attempt.run())).isZero();
                    assertThat(keys("raw/" + attempt.run() + "/")).isEmpty();
                }
            }
        } finally {
            allowStorage.countDown(); pool.shutdownNow(); assertThat(pool.awaitTermination(45, TimeUnit.SECONDS)).isTrue();
        }
        Probe daemon = start("daemon"); checkpoint(daemon, "RUNNER_READY"); awaitExported(winner.get());
        assertCounts(winner.get(), true); assertObjects(winner.get(), bytes, true); assertOffsets(1); stop(daemon);
        evidence("parallel-distinct-internal-admission-" + cohort, 1, cohort - 1, 2, bytes.length);
    }

    @Test void invalidCountAndByteOverflowHaveNoAdmissionOrStorageSideEffects() throws Exception {
        byte[] exact = maximumBytes(); byte[] overflowBytes = Arrays.copyOf(exact, exact.length + 1);
        overflowBytes[exact.length - 1] = ' '; overflowBytes[exact.length] = '\n';
        byte[] fixture = CanonicalSource.fixtureBytes(V2);
        int firstLine = new String(fixture, StandardCharsets.UTF_8).indexOf('\n') + 1;
        byte[] overflowCount = Arrays.copyOf(fixture, fixture.length + firstLine);
        System.arraycopy(fixture, 0, overflowCount, fixture.length, firstLine);
        var calls = new AtomicInteger();
        var staging = new SourceStagingService(jobs, (job, bytes) -> { calls.incrementAndGet(); raw.storeAndVerify(job, bytes); });
        for (byte[] invalid : List.of(overflowCount, overflowBytes)) {
            String run = newRun();
            assertThatThrownBy(() -> staging.stage(run, V2, invalid)).isInstanceOf(IllegalArgumentException.class);
            assertThat(keys("raw/" + run + "/")).isEmpty(); assertEmpty();
        }
        String mismatch = newRun();
        assertThatThrownBy(() -> staging.stage(mismatch, SyntheticScenario.NAME, fixture)).isInstanceOf(IllegalArgumentException.class);
        assertThat(calls.get()).isZero(); assertEmpty(); assertThat(logEnd()).isZero(); assertThat(offset()).isEmpty();
        evidence("overflow-1001-and-one-mib-plus-one-rejected-before-io", 0, 3, 0, overflowBytes.length);
    }

    @Test void sameRunReplayNeverOverwritesObservedConflictOrReleasesAnotherRunsSlot() throws Exception {
        byte[] bytes = CanonicalSource.fixtureBytes(V2);
        var putCalls = new AtomicInteger(); var ioCalls = new AtomicInteger();
        S3Client counting = (S3Client) Proxy.newProxyInstance(S3Client.class.getClassLoader(), new Class<?>[]{S3Client.class}, (proxy, method, arguments) -> {
            if (method.getName().equals("putObject")) { putCalls.incrementAndGet(); }
            if (Set.of("getObject", "putObject", "deleteObject").contains(method.getName())) { ioCalls.incrementAndGet(); }
            try { return method.invoke(s3, arguments); }
            catch (InvocationTargetException error) { throw error.getCause(); }
        });
        var staging = new SourceStagingService(jobs, new S3RawSourceStore(counting, bucket));
        String first = newRun(); var queued = staging.stage(first, V2, bytes); String pending = snapshot(first);
        assertThat(putCalls.get()).isEqualTo(1);
        assertThat(staging.stage(first, V2, bytes)).isEqualTo(queued); assertThat(snapshot(first)).isEqualTo(pending);
        assertThat(putCalls.get()).isEqualTo(1);
        byte[] changed = Arrays.copyOf(bytes, bytes.length + 1); changed[bytes.length - 1] = ' '; changed[bytes.length] = '\n';
        int previousIo = ioCalls.get();
        assertThatThrownBy(() -> staging.stage(first, V2, changed)).isInstanceOf(LabJobService.SourceConflictException.class);
        assertThat(ioCalls.get()).isEqualTo(previousIo); assertThat(snapshot(first)).isEqualTo(pending);
        byte[] corrupt = bytes.clone(); corrupt[0] ^= 1;
        s3.putObject(PutObjectRequest.builder().bucket(bucket).key(queued.sourceObjectKey()).build(), RequestBody.fromBytes(corrupt));
        assertThatThrownBy(() -> staging.stage(first, V2, bytes)).isInstanceOf(S3RawSourceStore.SourceVerificationException.class);
        assertThat(putCalls.get()).isEqualTo(1); assertThat(snapshot(first)).isEqualTo(pending);
        assertThat(get(queued.sourceObjectKey())).isEqualTo(corrupt);
        // Explicit disposable fixture repair; the application never repairs the observed conflict.
        s3.putObject(PutObjectRequest.builder().bucket(bucket).key(queued.sourceObjectKey()).build(), RequestBody.fromBytes(bytes));
        Probe firstDaemon = start("daemon"); checkpoint(firstDaemon, "RUNNER_READY"); awaitExported(first); stop(firstDaemon);
        assertObjects(first, bytes, true); String exported = snapshot(first);
        String second = newRun(); stage(second, V2, bytes); String next = snapshot(second);
        assertThat(staging.stage(first, V2, bytes).exportStatus()).isEqualTo(LabJobService.ExportStatus.EXPORTED);
        new ResultExportService(jobs, new S3ResultExportStore(s3, bucket)).export(first, queued.sourceSha256());
        assertThat(slot()).isEqualTo(second); assertThat(snapshot(second)).isEqualTo(next); assertThat(snapshot(first)).isEqualTo(exported);
        assertThat(keys("result/" + second + "/")).isEmpty(); assertOffsets(1);
        Probe nextDaemon = start("daemon"); checkpoint(nextDaemon, "RUNNER_READY"); awaitExported(second);
        assertObjects(second, bytes, true); assertOffsets(2); stop(nextDaemon);
        evidence("same-run-replay-conflict-and-next-slot-preservation", 2, 1, 4, bytes.length);
    }

    private static byte[] maximumBytes() {
        String[] lines = new String(CanonicalSource.fixtureBytes(V2), StandardCharsets.UTF_8).split("\n");
        assertThat(lines).hasSize(1000);
        int original = Arrays.stream(lines).mapToInt(line -> line.getBytes(StandardCharsets.UTF_8).length + 1).sum();
        int remaining = 1_048_576 - original; assertThat(remaining).isPositive();
        var padded = new StringBuilder(1_048_576);
        for (int index = 0; index < lines.length; index++) {
            int spaces = remaining / lines.length + (index < remaining % lines.length ? 1 : 0);
            assertThat(lines[index].length() + spaces).isLessThan(4096);
            padded.append(lines[index]).append(" ".repeat(spaces)).append('\n');
        }
        byte[] result = padded.toString().getBytes(StandardCharsets.UTF_8);
        assertThat(result).hasSize(1_048_576); assertThat(CanonicalSource.validate(V2, result).events()).hasSize(1000);
        return result;
    }
    private String newRun() { String run = "maximum-it-" + UUID.randomUUID(); ownedRuns.add(run); return run; }
    private void stage(String run, String scenario, byte[] bytes) {
        assertThat(new SourceStagingService(jobs, raw).stage(run, scenario, bytes).status()).isEqualTo(LabJobService.Status.QUEUED);
    }
    private void awaitExported(String run) throws Exception {
        await(() -> jobs.get(run).exportStatus() == LabJobService.ExportStatus.EXPORTED, Duration.ofSeconds(120));
        assertThat(slot()).isNull(); assertThat(jdbc.queryForObject("SELECT COUNT(*) FROM lab_outbox WHERE job_run_id=? AND status='ACKNOWLEDGED'", Long.class, run)).isEqualTo(2L);
    }
    private void assertCounts(String run, boolean maximum) {
        var row = jdbc.queryForMap("SELECT input_count,success_count,failure_count,duplicate_count,pending_count FROM demo_run WHERE id=?", run);
        assertThat(((Number) row.get("input_count")).intValue()).isEqualTo(maximum ? 1000 : 12);
        assertThat(((Number) row.get("success_count")).intValue()).isEqualTo(maximum ? 500 : 7);
        assertThat(((Number) row.get("failure_count")).intValue()).isEqualTo(maximum ? 300 : 3);
        assertThat(((Number) row.get("duplicate_count")).intValue()).isEqualTo(maximum ? 200 : 2);
        assertThat(((Number) row.get("pending_count")).intValue()).isZero();
        assertThat(jdbc.queryForObject("SELECT COUNT(*) FROM demo_outcome WHERE run_id=?", Long.class, run)).isEqualTo(maximum ? 1000L : 12L);
    }
    private void assertObjects(String run, byte[] source, boolean maximum) throws Exception {
        var job = jobs.get(run); assertThat(get(job.sourceObjectKey())).isEqualTo(source);
        assertThat(job.sourceSize()).isEqualTo(source.length); assertThat(job.sourceSha256()).isEqualTo(hash(source));
        var bundle = ExportBundle.from(jobs.exportSnapshot(run, job.sourceSha256()));
        assertThat(keys("raw/" + run + "/")).containsExactly(job.sourceObjectKey());
        assertThat(keys("result/" + run + "/")).containsExactlyInAnyOrder(bundle.result().key(), bundle.failures().key());
        for (var document : List.of(bundle.result(), bundle.failures())) {
            byte[] actual = get(document.key()); assertThat(actual).isEqualTo(document.bytes());
            assertThat(actual.length).isBetween(1, 4_194_304); assertThat(hash(actual)).isEqualTo(document.sha256());
            JsonNode body = JSON.readTree(actual);
            assertThat(body.get("runId").asText()).isEqualTo(run); assertThat(body.get("sourceSha256").asText()).isEqualTo(hash(source));
            assertThat(body.get("scenarioVersion").asText()).isEqualTo(maximum ? V2 : SyntheticScenario.NAME);
            assertThat(body.at("/counts/input").asInt()).isEqualTo(maximum ? 1000 : 12);
            assertThat(body.at("/counts/success").asInt()).isEqualTo(maximum ? 500 : 7);
            assertThat(body.at("/counts/failure").asInt()).isEqualTo(maximum ? 300 : 3);
            assertThat(body.at("/counts/duplicate").asInt()).isEqualTo(maximum ? 200 : 2);
            assertThat(body.at("/counts/pending").asInt()).isZero();
            if (body.get("kind").asText().equals("result")) { assertThat(body.get("outcomes").size()).isEqualTo(maximum ? 1000 : 12); }
            else { assertThat(body.get("kind").asText()).isEqualTo("failures"); assertThat(body.get("failures").size()).isEqualTo(maximum ? 300 : 3); }
        }
    }
    private byte[] get(String key) { return s3.getObjectAsBytes(GetObjectRequest.builder().bucket(bucket).key(key).build()).asByteArray(); }
    private List<String> keys(String prefix) {
        var page = s3.listObjectsV2(ListObjectsV2Request.builder().bucket(bucket).prefix(prefix).build());
        assertThat(page.isTruncated()).isFalse(); return page.contents().stream().map(value -> value.key()).sorted().toList();
    }
    private String snapshot(String run) throws Exception {
        return JSON.writeValueAsString(List.of(jdbc.queryForList("SELECT * FROM demo_run WHERE id=?", run),
            jdbc.queryForList("SELECT * FROM demo_outcome WHERE run_id=? ORDER BY input_sequence", run),
            jdbc.queryForList("SELECT run_id,scenario_version,source_sha256,HEX(source_bytes) AS source_hex,source_size,status,export_status,created_at,source_verified_at,queued_at,completed_at,export_completed_at,terminated_at FROM lab_job WHERE run_id=?", run),
            jdbc.queryForList("SELECT * FROM lab_outbox WHERE job_run_id=? ORDER BY id", run)));
    }
    private JsonNode getObservation(URI uri) throws Exception {
        var response = HttpClient.newBuilder().connectTimeout(Duration.ofSeconds(5)).build().send(
            HttpRequest.newBuilder(uri).timeout(Duration.ofSeconds(10)).GET().build(), HttpResponse.BodyHandlers.ofString(StandardCharsets.UTF_8));
        assertThat(response.statusCode()).isEqualTo(200); var body = JSON.readTree(response.body());
        assertThat(body.get("sourceCommit").asText()).isEqualTo(commit); assertThat(body.get("scope").asText()).isEqualTo("ISOLATED_LAB");
        assertThat(body.get("publicExecutionEnabled").asBoolean()).isFalse(); return body;
    }
    private void assertPointersWithoutGroupCommit(Map<String, String> expected) throws Exception {
        var partition = new TopicPartition(topic, 0);
        try (var consumer = new KafkaConsumer<byte[], byte[]>(Map.of(ConsumerConfig.BOOTSTRAP_SERVERS_CONFIG, ContinuousRuntimeIT.guardedBootstrap(),
            ConsumerConfig.ENABLE_AUTO_COMMIT_CONFIG, "false", ConsumerConfig.ALLOW_AUTO_CREATE_TOPICS_CONFIG, "false"), new ByteArrayDeserializer(), new ByteArrayDeserializer())) {
            consumer.assign(List.of(partition)); consumer.seekToBeginning(List.of(partition));
            var seen = new LinkedHashSet<String>(); long deadline = System.nanoTime() + Duration.ofSeconds(15).toNanos();
            while (seen.size() < expected.size() && System.nanoTime() < deadline) {
                for (var record : consumer.poll(Duration.ofMillis(250))) {
                    assertThat(record.value().length).isLessThanOrEqualTo(1024);
                    String run = new String(record.key(), StandardCharsets.US_ASCII); assertThat(seen.add(run)).isTrue();
                    var pointer = JSON.readTree(record.value()); assertThat(pointer.get("runId").asText()).isEqualTo(run);
                    assertThat(pointer.get("scenarioVersion").asText()).isEqualTo(expected.get(run));
                    assertThat(pointer.get("sourceSha256").asText()).isEqualTo(jobs.get(run).sourceSha256());
                }
            }
            assertThat(seen).containsExactlyInAnyOrderElementsOf(expected.keySet());
        }
        assertOffsets(expected.size());
    }
    private Probe start(String mode) throws Exception {
        Path folder = Files.createDirectory(privateDirectory.resolve(mode + "-" + UUID.randomUUID()));
        Path checkpoint = folder.resolve("checkpoint.json"), stop = folder.resolve("stop.request"), exit = folder.resolve("exit.json"), log = folder.resolve("child.log");
        String cp = System.getProperty("surefire.test.class.path", System.getProperty("java.class.path"));
        Path java = Path.of(System.getProperty("java.home"), "bin", System.getProperty("os.name").startsWith("Windows") ? "java.exe" : "java");
        var builder = new ProcessBuilder(java.toString(), "-Duser.timezone=Asia/Seoul", "-cp", cp, RuntimeProcessProbe.class.getName(),
            mode, topic, group, checkpoint.toString(), stop.toString(), exit.toString(), "-").redirectErrorStream(true).redirectOutput(log.toFile());
        builder.environment().put("DB_URL", ContinuousRuntimeIT.disposableDatabaseUrl());
        builder.environment().put("DB_USERNAME", ContinuousRuntimeIT.required("DB_TEST_USERNAME")); builder.environment().put("DB_PASSWORD", ContinuousRuntimeIT.required("DB_TEST_PASSWORD"));
        builder.environment().put("LAB_ENVIRONMENT", "isolated-lab");
        builder.environment().put("LAB_RUNTIME_KAFKA_BOOTSTRAP", ContinuousRuntimeIT.guardedBootstrap()); builder.environment().put("LAB_RUNTIME_KAFKA_TOPIC", topic); builder.environment().put("LAB_RUNTIME_KAFKA_GROUP", group);
        builder.environment().put("LAB_RUNTIME_S3_ENDPOINT", ContinuousRuntimeIT.guardedS3Endpoint().toString()); builder.environment().put("LAB_RUNTIME_S3_REGION", "garage"); builder.environment().put("LAB_RUNTIME_S3_BUCKET", bucket);
        builder.environment().put("LAB_RUNTIME_S3_ACCESS_KEY_ID", ContinuousRuntimeIT.required("LAB_S3_TEST_ACCESS_KEY")); builder.environment().put("LAB_RUNTIME_S3_SECRET_ACCESS_KEY", ContinuousRuntimeIT.required("LAB_S3_TEST_SECRET_KEY"));
        var probe = new Probe(builder.start(), checkpoint, stop, exit, log, mode); children.add(probe); return probe;
    }
    private JsonNode checkpoint(Probe child, String expected) throws Exception {
        await(() -> Files.isRegularFile(child.checkpoint()) || !child.process().isAlive(), Duration.ofSeconds(100));
        assertThat(child.process().isAlive()).as("real child readiness; inspect private child.log on failure").isTrue();
        var value = JSON.readTree(Files.readString(child.checkpoint())); assertThat(value.get("phase").asText()).isEqualTo(expected); return value;
    }
    private void stop(Probe child) throws Exception {
        Files.writeString(child.stop(), "stop\n", StandardCharsets.US_ASCII, StandardOpenOption.CREATE_NEW);
        assertThat(child.process().waitFor(100, TimeUnit.SECONDS)).isTrue(); assertThat(child.process().exitValue()).isZero();
        assertThat(JSON.readTree(Files.readString(child.exit())).get("resourcesClosed").asBoolean()).isTrue();
    }
    private Optional<Long> offset() throws Exception {
        try { var value = kafka.listConsumerGroupOffsets(group).partitionsToOffsetAndMetadata().get(10, TimeUnit.SECONDS).get(new TopicPartition(topic, 0)); return value == null ? Optional.empty() : Optional.of(value.offset()); }
        catch (java.util.concurrent.ExecutionException failure) { if (failure.getCause() instanceof GroupIdNotFoundException) { return Optional.empty(); } throw failure; }
    }
    private long logEnd() throws Exception { var part = new TopicPartition(topic, 0); return kafka.listOffsets(Map.of(part, OffsetSpec.latest())).all().get(10, TimeUnit.SECONDS).get(part).offset(); }
    private void assertOffsets(long expected) throws Exception { assertThat(logEnd()).isEqualTo(expected); assertThat(offset()).contains(expected); }
    private String slot() { return jdbc.queryForObject("SELECT occupied_run_id FROM lab_job_slot WHERE id=1", String.class); }
    private void assertEmpty() {
        for (String table : List.of("lab_job", "lab_outbox", "demo_run", "demo_outcome")) { assertThat(jdbc.queryForObject("SELECT COUNT(*) FROM " + table, Long.class)).isZero(); }
        assertThat(slot()).isNull();
    }
    private static String hash(byte[] bytes) throws Exception { return HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(bytes)); }
    private static void await(BooleanSupplier value, Duration bound) throws Exception {
        long end = System.nanoTime() + bound.toNanos(); while (System.nanoTime() < end) { if (value.getAsBoolean()) { return; } Thread.sleep(100); }
        throw new AssertionError("Bounded isolated wait expired");
    }
    private void evidence(String name, int completed, int rejected, int files, int sourceBytes) throws Exception {
        var value = new LinkedHashMap<String, Object>(); value.put("case", name); value.put("sourceCommit", commit);
        value.put("scope", "ISOLATED_FUNCTIONAL_BOUNDARIES"); value.put("completedRuns", completed); value.put("rejectedAdmissions", rejected);
        value.put("verifiedExportFiles", files); value.put("sourceBytes", sourceBytes); value.put("outcomeRows", jdbc.queryForObject("SELECT COUNT(*) FROM demo_outcome", Long.class));
        value.put("logEnd", logEnd()); value.put("committedOffset", offset().orElse(0L)); value.put("slotFree", slot() == null);
        value.put("productionThroughputOrCapacityProven", false);
        String encoded = JSON.writeValueAsString(value) + "\n"; System.out.print("MAXIMUM_EVIDENCE " + encoded);
        String file = System.getProperty("lab.maximum.evidence.file");
        if (file != null && !file.isBlank()) { Files.writeString(Path.of(file), encoded, StandardCharsets.UTF_8, StandardOpenOption.CREATE, StandardOpenOption.APPEND); }
        casePassed = true;
    }
    @AfterEach void cleanupOwnedDisposableResourcesOnly() throws Exception {
        if (failurePreserved) { return; }
        for (var child : children) { if (child.process().isAlive()) { child.process().destroyForcibly(); assertThat(child.process().waitFor(10, TimeUnit.SECONDS)).isTrue(); } }
        if (!casePassed) {
            // Stop only this test's child processes. Keep all isolated SQL, raw/export objects,
            // topic and group for explicit diagnosis; subsequent cases must not retry or clean them.
            failurePreserved = true;
            var details = new LinkedHashMap<String, Object>();
            details.put("sourceCommit", commit); details.put("topic", topic); details.put("group", group);
            details.put("ownedRuns", List.copyOf(ownedRuns));
            details.put("childLogs", children.stream().map(value -> value.log().toString()).toList());
            Files.writeString(privateDirectory.resolve("failure-resources.json"), JSON.writeValueAsString(details),
                StandardCharsets.UTF_8, StandardOpenOption.CREATE_NEW);
            System.out.println("MAXIMUM_FAILURE_RESOURCES_PRESERVED " + JSON.writeValueAsString(Map.of(
                "scope", "ISOLATED_FUNCTIONAL_BOUNDARIES", "ownedRuns", ownedRuns.size(), "automaticRetry", false)));
            return;
        }
        children.clear();
        if (group != null) {
            ContinuousRuntimeIT.requireOwnedName(group); long deadline = System.nanoTime() + Duration.ofSeconds(35).toNanos();
            while (true) {
                try { kafka.deleteConsumerGroups(List.of(group)).all().get(5, TimeUnit.SECONDS); break; }
                catch (java.util.concurrent.ExecutionException failure) {
                    if (failure.getCause() instanceof GroupIdNotFoundException) { break; }
                    if (!(failure.getCause() instanceof GroupNotEmptyException) && !(failure.getCause() instanceof RetriableException)) { throw failure; }
                }
                assertThat(System.nanoTime()).isLessThan(deadline); Thread.sleep(250);
            }
        }
        if (topic != null) {
            ContinuousRuntimeIT.requireOwnedName(topic);
            try { kafka.deleteTopics(List.of(topic)).all().get(10, TimeUnit.SECONDS); }
            catch (java.util.concurrent.ExecutionException failure) { if (!(failure.getCause() instanceof UnknownTopicOrPartitionException)) { throw failure; } }
        }
        for (String run : ownedRuns) {
            assertThat(run).matches("maximum-it-[a-f0-9-]{36}");
            for (String prefix : List.of("raw/" + run + "/", "result/" + run + "/")) {
                for (String key : keys(prefix)) { assertThat(key).startsWith(prefix); s3.deleteObject(DeleteObjectRequest.builder().bucket(bucket).key(key).build()); }
                assertThat(keys(prefix)).isEmpty();
            }
        }
        new TransactionTemplate(transactionManager).executeWithoutResult(ignored -> {
            String occupied = jdbc.queryForObject("SELECT occupied_run_id FROM lab_job_slot WHERE id=1 FOR UPDATE", String.class);
            if (occupied != null && !ownedRuns.contains(occupied)) { throw new IllegalStateException("Refusing unowned slot cleanup"); }
            assertThat(ownedRuns).containsAll(jdbc.queryForList("SELECT run_id FROM lab_job", String.class));
            if (occupied != null) { jdbc.update("UPDATE lab_job_slot SET occupied_run_id=NULL WHERE id=1"); }
            for (String run : ownedRuns) {
                jdbc.update("DELETE FROM lab_outbox WHERE job_run_id=?", run); jdbc.update("DELETE FROM demo_outcome WHERE run_id=?", run);
                jdbc.update("DELETE FROM demo_run WHERE id=?", run); jdbc.update("DELETE FROM lab_job WHERE run_id=?", run);
            }
        });
        ownedRuns.clear(); group = null; topic = null; assertEmpty();
        try (var lease = MariaDbRuntimeLease.acquire(dataSource)) { lease.verifyHeld(); }
    }
    @AfterAll void closeClients() { if (kafka != null) { kafka.close(Duration.ofSeconds(5)); } if (s3 != null) { s3.close(); } }
    private record Attempt(String run, boolean accepted) {}
    private record Probe(Process process, Path checkpoint, Path stop, Path exit, Path log, String mode) {}
}
