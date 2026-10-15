package io.github.devdooly.platformlab.jobs.messaging;

import io.github.devdooly.platformlab.demo.SyntheticScenario;
import io.github.devdooly.platformlab.jobs.CanonicalSource;
import io.github.devdooly.platformlab.jobs.LabJobService;
import io.github.devdooly.platformlab.jobs.S3ClientFactory;
import io.github.devdooly.platformlab.jobs.S3RawSourceStore;
import io.github.devdooly.platformlab.jobs.SourceStagingService;
import io.github.devdooly.platformlab.jobs.VerifiedSourceReader;
import java.net.URI;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;
import java.time.Duration;
import java.time.ZoneId;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.Set;
import java.util.UUID;
import java.util.concurrent.TimeUnit;
import javax.sql.DataSource;
import org.apache.kafka.clients.admin.Admin;
import org.apache.kafka.clients.admin.AdminClientConfig;
import org.apache.kafka.clients.admin.NewTopic;
import org.apache.kafka.clients.admin.OffsetSpec;
import org.apache.kafka.clients.consumer.Consumer;
import org.apache.kafka.clients.producer.Producer;
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
 * Explicit real-service validation only: MariaDB, Garage and one disposable Kafka cluster.
 * Select -Dlab.kafka.tests=true -Dtest=KafkaRedeliveryIT -DargLine=-Duser.timezone=Asia/Seoul.
 * A forced kill is valid evidence only after the child writes its atomic boundary checkpoint.
 * No completeExport acknowledgement is fabricated; the test cleans only its own pending job.
 */
@SpringBootTest
@ActiveProfiles({"db-test", "worker"})
@EnabledIfSystemProperty(named = "lab.kafka.tests", matches = "true")
@TestInstance(TestInstance.Lifecycle.PER_CLASS)
class KafkaRedeliveryIT {
    private static final JsonMapper JSON = JsonMapper.builder().build();
    @Autowired LabJobService jobs;
    @Autowired JdbcTemplate jdbc;
    @Autowired DataSource dataSource;
    @Autowired PlatformTransactionManager transactionManager;
    private final byte[] bytes = CanonicalSource.fixtureBytes();
    private final List<Probe> probes = new ArrayList<>();
    private S3Client s3;
    private S3RawSourceStore sources;
    private Admin kafka;
    private String bootstrap;
    private String bucket;
    private String topic;
    private String group;
    private String runId;
    private String rawKey;
    private Path privateDirectory;

    @DynamicPropertySource
    static void requireDisposableDatabaseBeforeFlyway(DynamicPropertyRegistry registry) {
        registry.add("spring.datasource.url", KafkaRedeliveryIT::disposableDatabaseUrl);
        registry.add("spring.datasource.username", () -> required("DB_TEST_USERNAME"));
        registry.add("spring.datasource.password", () -> required("DB_TEST_PASSWORD"));
    }

    static String disposableDatabaseUrl() {
        String value = required("DB_TEST_URL");
        if (!value.matches("jdbc:mariadb://127\\.0\\.0\\.1:[0-9]{1,5}/platform_lab_kafka_it")) {
            throw new IllegalArgumentException("DB_TEST_URL requires the disposable platform_lab_kafka_it schema and numeric loopback, without query options");
        }
        requireValidPort(URI.create(value.substring("jdbc:".length())));
        return value;
    }

    static String guardedBootstrap() {
        String value = required("LAB_KAFKA_TEST_BOOTSTRAP");
        if (!value.matches("127\\.0\\.0\\.1:[0-9]{1,5}")) {
            throw new IllegalArgumentException("LAB_KAFKA_TEST_BOOTSTRAP requires one numeric loopback endpoint");
        }
        requireValidPort(URI.create("http://" + value));
        return value;
    }

    static URI guardedS3Endpoint() {
        String value = required("LAB_S3_TEST_ENDPOINT");
        if (!value.matches("http://127\\.0\\.0\\.1:[0-9]{1,5}/?")) {
            throw new IllegalArgumentException("LAB_S3_TEST_ENDPOINT requires a numeric loopback origin");
        }
        URI uri = URI.create(value); requireValidPort(uri); return uri;
    }

    static String guardedBucket() {
        String value = required("LAB_S3_TEST_BUCKET");
        if (!value.matches("platform-lab-s3-test-[a-z0-9-]{1,42}")) {
            throw new IllegalArgumentException("Expected a dedicated platform-lab-s3-test- bucket");
        }
        return value;
    }

    static Admin admin(String bootstrap) {
        return Admin.create(Map.of(AdminClientConfig.BOOTSTRAP_SERVERS_CONFIG, bootstrap,
            AdminClientConfig.CLIENT_ID_CONFIG, "platform-lab-kafka-test-admin-" + UUID.randomUUID(),
            AdminClientConfig.REQUEST_TIMEOUT_MS_CONFIG, "5000",
            AdminClientConfig.DEFAULT_API_TIMEOUT_MS_CONFIG, "10000",
            AdminClientConfig.RETRIES_CONFIG, "2"));
    }

    static void requireExpectedCluster(Admin admin) throws Exception {
        String expected = required("LAB_KAFKA_TEST_CLUSTER_ID");
        if (!expected.matches("[A-Za-z0-9_-]{16,64}")) { throw new IllegalArgumentException("Invalid dedicated cluster ID"); }
        var cluster = admin.describeCluster();
        assertThat(cluster.clusterId().get(10, TimeUnit.SECONDS)).isEqualTo(expected);
        assertThat(cluster.nodes().get(10, TimeUnit.SECONDS)).hasSize(1);
    }

    @BeforeAll void requireActualIsolatedServices() throws Exception {
        disposableDatabaseUrl();
        try (var connection = dataSource.getConnection()) {
            assertThat(connection.getMetaData().getDatabaseProductName()).isEqualTo("MariaDB");
            assertThat(connection.getCatalog()).isEqualTo("platform_lab_kafka_it");
        }
        assertThat(Runtime.version().feature()).isEqualTo(21);
        assertThat(ZoneId.systemDefault()).isEqualTo(ZoneId.of("Asia/Seoul"));
        assertEmptyJobs();
        URI endpoint = guardedS3Endpoint();
        bucket = guardedBucket();
        bootstrap = guardedBootstrap();
        s3 = S3ClientFactory.createGarage(endpoint, "garage", StaticCredentialsProvider.create(
            AwsBasicCredentials.create(required("LAB_S3_TEST_ACCESS_KEY"), required("LAB_S3_TEST_SECRET_KEY"))));
        sources = new S3RawSourceStore(s3, bucket);
        kafka = admin(bootstrap);
        requireExpectedCluster(kafka);
        privateDirectory = Files.createTempDirectory("platform-lab-kafka-it-");
    }

    @BeforeEach void createOnlyUniqueTestTopicAndRun() throws Exception {
        runId = null; topic = null; group = null; rawKey = null;
        assertEmptyJobs();
        assertThat(probes).isEmpty();
        String unique = UUID.randomUUID().toString();
        runId = "kafka-it-" + unique;
        topic = "platform-lab-kafka-test-topic-" + unique;
        group = "platform-lab-kafka-test-group-" + unique;
        requireOwnedResourceName(topic); requireOwnedResourceName(group);
        rawKey = "raw/" + runId + "/" + CanonicalSource.validate(bytes).sha256() + ".ndjson";
        var newTopic = new NewTopic(topic, 1, (short) 1).configs(Map.of(
            "retention.ms", "3600000", "retention.bytes", "8388608", "max.message.bytes", "1024"));
        kafka.createTopics(List.of(newTopic)).all().get(10, TimeUnit.SECONDS);
        var description = kafka.describeTopics(List.of(topic)).allTopicNames().get(10, TimeUnit.SECONDS).get(topic);
        assertThat(description.partitions()).hasSize(1);
        assertThat(description.partitions().getFirst().replicas()).hasSize(1);
    }

    @Test void killedPublisherAfterActualAckCausesTwoRecordsButOneUnchangedBusinessResult() throws Exception {
        LabJobService.Job queued = stage();
        Probe publisher = startProbe("publisher-ack");
        JsonNode checkpoint = awaitCheckpoint(publisher, "PUBLISHER_ACKED_BEFORE_OUTBOX_ACK");
        assertThat(checkpoint.get("offset").asLong()).isZero();
        assertThat(checkpoint.get("activeTransaction").asBoolean()).isFalse();
        assertQueuedUnprocessed(queued);
        assertThat(jobs.pendingOutbox(100)).hasSize(1);
        assertThat(jobs.pendingOutbox(100).getFirst().eventType()).isEqualTo(LabJobService.EventType.DISPATCH);
        assertThat(jobs.pendingOutbox(100).getFirst().status()).isEqualTo(LabJobService.OutboxStatus.PENDING);
        forceKillReadyProbe(publisher);
        assertQueuedUnprocessed(queued);
        assertThat(jobs.pendingOutbox(100)).hasSize(1);

        publishNormally();
        assertThat(logEnd()).isEqualTo(2L);
        Consumer<String, String> consumer = KafkaClientFactory.consumer(bootstrap, group);
        try {
            var worker = new DispatchWorker(jobs, verifiedReader(), consumer, topic);
            var first = awaitDelivery(worker);
            assertDelivery(first, 0, false);
            assertCompleteTwelveRows();
            Snapshot completed = snapshot();
            var replay = awaitDelivery(worker);
            assertDelivery(replay, 1, true);
            assertSnapshot(completed);
            assertCommittedAndLag(2);
            evidence("publisher-ack-kill", 1, 2, 1);
        } finally { consumer.close(Duration.ofSeconds(5)); }
    }

    @Test void killedWorkerAfterDbCommitRedeliversWithoutChangingCompletedRowsOrTimes() throws Exception {
        stage(); publishNormally();
        Probe workerProbe = startProbe("worker-after-db");
        JsonNode checkpoint = awaitCheckpoint(workerProbe, "WORKER_DB_COMMITTED_BEFORE_OFFSET");
        assertThat(checkpoint.get("offset").asLong()).isZero();
        assertThat(checkpoint.get("activeTransaction").asBoolean()).isFalse();
        assertThat(checkpoint.get("runRows").asLong()).isEqualTo(1L);
        assertThat(checkpoint.get("outcomeRows").asLong()).isEqualTo(12L);
        assertCompleteTwelveRows();
        Snapshot completed = snapshot();
        assertThat(committedOffset()).isEmpty();
        forceKillReadyProbe(workerProbe);
        assertSnapshot(completed);

        Consumer<String, String> consumer = KafkaClientFactory.consumer(bootstrap, group);
        try {
            var replay = awaitDelivery(new DispatchWorker(jobs, verifiedReader(), consumer, topic));
            assertDelivery(replay, 0, true);
            assertSnapshot(completed);
            assertCommittedAndLag(1);
            evidence("worker-after-db-kill", 1, 1, 1);
        } finally { consumer.close(Duration.ofSeconds(5)); }
    }

    @Test void killedWorkerInsideRealUncommittedSqlRollsBackThenRedeliveryCommitsOneBatch() throws Exception {
        LabJobService.Job queued = stage(); publishNormally();
        Probe workerProbe = startProbe("worker-before-dbcommit");
        JsonNode checkpoint = awaitCheckpoint(workerProbe, "WORKER_SQL_COMPLETE_BEFORE_DB_COMMIT");
        assertThat(checkpoint.get("activeTransaction").asBoolean()).isTrue();
        assertThat(checkpoint.get("runRows").asLong()).isEqualTo(1L);
        assertThat(checkpoint.get("outcomeRows").asLong()).isEqualTo(12L);
        assertThat(committedOffset()).isEmpty();
        forceKillReadyProbe(workerProbe);
        assertQueuedUnprocessed(queued);
        assertThat(committedOffset()).isEmpty();

        Consumer<String, String> consumer = KafkaClientFactory.consumer(bootstrap, group);
        try {
            var delivery = awaitDelivery(new DispatchWorker(jobs, verifiedReader(), consumer, topic));
            assertDelivery(delivery, 0, false);
            assertCompleteTwelveRows();
            assertCommittedAndLag(1);
            evidence("worker-before-dbcommit-kill", 1, 1, 0);
        } finally { consumer.close(Duration.ofSeconds(5)); }
    }

    @Test void corruptRawSourcePausesWithoutOffsetCommitAndFreshWorkerRecoversAfterExplicitFixtureRepair() throws Exception {
        LabJobService.Job queued = stage(); publishNormally();
        byte[] corrupt = bytes.clone(); corrupt[1] ^= 1;
        s3.putObject(PutObjectRequest.builder().bucket(bucket).key(rawKey).build(), RequestBody.fromBytes(corrupt));
        Consumer<String, String> consumer = KafkaClientFactory.consumer(bootstrap, group);
        try {
            var worker = new DispatchWorker(jobs, verifiedReader(), consumer, topic);
            var failure = awaitPaused(worker);
            assertThat(failure.code().name()).isEqualTo("SOURCE_INVALID");
            assertThat(worker.isPaused()).isTrue();
            assertThatThrownBy(() -> worker.receiveOne(Duration.ofMillis(10)))
                .isInstanceOf(DispatchWorker.DeliveryPausedException.class);
            assertQueuedUnprocessed(queued);
            assertThat(committedOffset()).isEmpty();
            assertThat(s3.getObjectAsBytes(GetObjectRequest.builder().bucket(bucket).key(rawKey).build()).asByteArray()).isEqualTo(corrupt);
            // The adapter is GET-only. Only this test restores its own deliberately damaged fixture.
            s3.putObject(PutObjectRequest.builder().bucket(bucket).key(rawKey).build(), RequestBody.fromBytes(bytes));
        } finally { consumer.close(Duration.ofSeconds(5)); }
        Consumer<String, String> recoveredConsumer = KafkaClientFactory.consumer(bootstrap, group);
        try {
            var delivery = awaitDelivery(new DispatchWorker(jobs, verifiedReader(), recoveredConsumer, topic));
            assertDelivery(delivery, 0, false);
            assertCompleteTwelveRows();
            assertCommittedAndLag(1);
            evidence("source-invalid-pause-recovery", 0, 1, 0);
        } finally { recoveredConsumer.close(Duration.ofSeconds(5)); }
    }

    private LabJobService.Job stage() {
        var queued = new SourceStagingService(jobs, sources).stage(runId, SyntheticScenario.NAME, bytes);
        assertThat(queued.status()).isEqualTo(LabJobService.Status.QUEUED);
        assertThat(sources.readAndVerify(queued)).isEqualTo(bytes);
        return queued;
    }

    private VerifiedSourceReader verifiedReader() {
        return job -> {
            assertThat(TransactionSynchronizationManager.isActualTransactionActive()).isFalse();
            byte[] actual = sources.readAndVerify(job);
            assertThat(actual).isEqualTo(bytes);
            return actual;
        };
    }

    private void publishNormally() throws Exception {
        Producer<String, String> producer = KafkaClientFactory.producer(bootstrap);
        try {
            var published = new DispatchPublisher(jobs, producer, topic).publishOne().orElseThrow();
            assertThat(published.topic()).isEqualTo(topic);
            assertThat(published.partition()).isZero();
            assertThat(jobs.pendingOutbox(100)).noneMatch(event -> event.eventType() == LabJobService.EventType.DISPATCH);
        } finally { producer.close(Duration.ofSeconds(5)); }
    }

    private DispatchWorker.Delivery awaitDelivery(DispatchWorker worker) throws Exception {
        long deadline = System.nanoTime() + Duration.ofSeconds(60).toNanos();
        while (System.nanoTime() < deadline) {
            var received = worker.receiveOne(Duration.ofSeconds(1));
            if (received.isPresent()) { return received.orElseThrow(); }
        }
        throw new AssertionError("No delivery arrived before the bounded test deadline");
    }

    private DispatchWorker.DeliveryPausedException awaitPaused(DispatchWorker worker) throws Exception {
        long deadline = System.nanoTime() + Duration.ofSeconds(60).toNanos();
        while (System.nanoTime() < deadline) {
            try { worker.receiveOne(Duration.ofSeconds(1)); }
            catch (DispatchWorker.DeliveryPausedException failure) { return failure; }
        }
        throw new AssertionError("Expected a paused invalid-source delivery");
    }

    private void assertDelivery(DispatchWorker.Delivery delivery, long offset, boolean replay) {
        assertThat(delivery.topic()).isEqualTo(topic);
        assertThat(delivery.partition()).isZero();
        assertThat(delivery.offset()).isEqualTo(offset);
        assertThat(delivery.nextOffset()).isEqualTo(offset + 1);
        assertThat(delivery.runId()).isEqualTo(runId);
        assertThat(delivery.replay()).isEqualTo(replay);
    }

    private Probe startProbe(String mode) throws Exception {
        Path folder = Files.createDirectory(privateDirectory.resolve(mode + "-" + UUID.randomUUID()));
        Path checkpoint = folder.resolve("checkpoint.json");
        Path log = folder.resolve("child.log");
        String classpath = System.getProperty("surefire.test.class.path");
        if (classpath == null || classpath.isBlank()) { classpath = System.getProperty("java.class.path"); }
        String binary = System.getProperty("os.name").startsWith("Windows") ? "java.exe" : "java";
        Path java = Path.of(System.getProperty("java.home"), "bin", binary);
        var child = new ProcessBuilder(java.toString(), "-Duser.timezone=Asia/Seoul", "-cp", classpath,
            KafkaCrashProbe.class.getName(), mode, topic, group, checkpoint.toString(), runId)
            .redirectErrorStream(true).redirectOutput(log.toFile()).start();
        var probe = new Probe(child, checkpoint, log, mode);
        probes.add(probe); return probe;
    }

    private JsonNode awaitCheckpoint(Probe probe, String expectedPhase) throws Exception {
        long deadline = System.nanoTime() + Duration.ofSeconds(90).toNanos();
        while (System.nanoTime() < deadline) {
            if (Files.isRegularFile(probe.checkpoint())) {
                var checkpoint = JSON.readTree(Files.readString(probe.checkpoint(), StandardCharsets.UTF_8));
                assertThat(checkpoint.get("mode").asText()).isEqualTo(probe.mode());
                assertThat(checkpoint.get("phase").asText()).isEqualTo(expectedPhase);
                assertThat(checkpoint.get("runId").asText()).isEqualTo(runId);
                assertThat(checkpoint.get("topic").asText()).isEqualTo(topic);
                assertThat(checkpoint.get("partition").asInt()).isZero();
                assertThat(probe.process().isAlive()).isTrue();
                return checkpoint;
            }
            if (!probe.process().isAlive()) {
                throw new AssertionError("Crash probe exited before its atomic checkpoint; inspect its private temporary log");
            }
            Thread.sleep(100);
        }
        throw new AssertionError("Crash probe did not reach its real boundary checkpoint within 90 seconds");
    }

    private void forceKillReadyProbe(Probe probe) throws Exception {
        assertThat(Files.isRegularFile(probe.checkpoint())).isTrue();
        assertThat(probe.process().isAlive()).isTrue();
        probe.process().destroyForcibly();
        assertThat(probe.process().waitFor(10, TimeUnit.SECONDS)).isTrue();
        assertThat(probe.process().isAlive()).isFalse();
        assertThat(probe.process().exitValue()).isNotZero();
    }

    private Optional<Long> committedOffset() throws Exception {
        try {
            var offsets = kafka.listConsumerGroupOffsets(group).partitionsToOffsetAndMetadata().get(10, TimeUnit.SECONDS);
            var offset = offsets.get(new TopicPartition(topic, 0));
            return offset == null ? Optional.empty() : Optional.of(offset.offset());
        } catch (java.util.concurrent.ExecutionException failure) {
            if (failure.getCause() instanceof GroupIdNotFoundException) { return Optional.empty(); }
            throw failure;
        }
    }

    private long logEnd() throws Exception {
        var partition = new TopicPartition(topic, 0);
        return kafka.listOffsets(Map.of(partition, OffsetSpec.latest())).all().get(10, TimeUnit.SECONDS).get(partition).offset();
    }

    private void assertCommittedAndLag(long expectedEnd) throws Exception {
        long end = logEnd();
        long committed = committedOffset().orElseThrow();
        assertThat(end).isEqualTo(expectedEnd);
        assertThat(committed).isEqualTo(expectedEnd);
        assertThat(end - committed).isZero();
    }

    private void assertQueuedUnprocessed(LabJobService.Job expected) {
        assertThat(jobs.get(runId)).isEqualTo(expected);
        assertThat(expected.status()).isEqualTo(LabJobService.Status.QUEUED);
        assertThat(jdbc.queryForObject("SELECT source_bytes FROM lab_job WHERE run_id = ?", byte[].class, runId)).isEqualTo(bytes);
        assertThat(jdbc.queryForObject("SELECT COUNT(*) FROM lab_outbox WHERE job_run_id = ?", Long.class, runId)).isEqualTo(1L);
        assertThat(jdbc.queryForObject("SELECT COUNT(*) FROM lab_outbox WHERE job_run_id = ? AND event_type = 'EXPORT'", Long.class, runId)).isZero();
        assertThat(jdbc.queryForObject("SELECT COUNT(*) FROM demo_run WHERE id = ?", Long.class, runId)).isZero();
        assertThat(jdbc.queryForObject("SELECT COUNT(*) FROM demo_outcome WHERE run_id = ?", Long.class, runId)).isZero();
        assertThat(jdbc.queryForObject("SELECT occupied_run_id FROM lab_job_slot WHERE id = 1", String.class)).isEqualTo(runId);
    }

    private void assertCompleteTwelveRows() {
        var job = jobs.get(runId);
        assertThat(job.status()).isEqualTo(LabJobService.Status.COMPLETED);
        assertThat(job.exportStatus()).isEqualTo(LabJobService.ExportStatus.PENDING);
        assertThat(job.exportCompletedAt()).isNull();
        assertThat(jdbc.queryForObject("SELECT COUNT(*) FROM demo_run WHERE id = ?", Long.class, runId)).isEqualTo(1L);
        var run = jdbc.queryForMap("SELECT * FROM demo_run WHERE id = ?", runId);
        assertThat(((Number) run.get("input_count")).intValue()).isEqualTo(12);
        assertThat(((Number) run.get("success_count")).intValue()).isEqualTo(7);
        assertThat(((Number) run.get("failure_count")).intValue()).isEqualTo(3);
        assertThat(((Number) run.get("duplicate_count")).intValue()).isEqualTo(2);
        assertThat(((Number) run.get("pending_count")).intValue()).isZero();
        assertThat(jdbc.queryForObject("SELECT COUNT(*) FROM demo_outcome WHERE run_id = ?", Long.class, runId)).isEqualTo(12L);
        assertThat(jdbc.queryForObject("SELECT COUNT(*) FROM lab_outbox WHERE job_run_id = ?", Long.class, runId)).isEqualTo(2L);
        assertThat(jdbc.queryForObject("SELECT occupied_run_id FROM lab_job_slot WHERE id = 1", String.class)).isEqualTo(runId);
    }

    private Snapshot snapshot() {
        return new Snapshot(jobs.get(runId),
            jdbc.queryForObject("SELECT source_bytes FROM lab_job WHERE run_id = ?", byte[].class, runId),
            jdbc.queryForList("SELECT * FROM lab_outbox WHERE job_run_id = ? ORDER BY id", runId),
            jdbc.queryForList("SELECT * FROM demo_run WHERE id = ?", runId),
            jdbc.queryForList("SELECT * FROM demo_outcome WHERE run_id = ? ORDER BY input_sequence", runId),
            jdbc.queryForObject("SELECT occupied_run_id FROM lab_job_slot WHERE id = 1", String.class));
    }

    private void assertSnapshot(Snapshot expected) {
        Snapshot actual = snapshot();
        assertThat(actual.job()).isEqualTo(expected.job());
        assertThat(actual.sourceBytes()).isEqualTo(expected.sourceBytes());
        assertThat(actual.outbox()).isEqualTo(expected.outbox());
        assertThat(actual.runs()).isEqualTo(expected.runs());
        assertThat(actual.outcomes()).isEqualTo(expected.outcomes());
        assertThat(actual.slot()).isEqualTo(expected.slot());
    }

    private void evidence(String caseName, int forcedKills, int successfulParentDeliveries, int completedReplays) throws Exception {
        long end = logEnd(), offset = committedOffset().orElseThrow();
        String json = "{\"case\":\"" + caseName + "\",\"forcedKills\":" + forcedKills
            + ",\"successfulParentDeliveries\":" + successfulParentDeliveries + ",\"completedReplaysObserved\":" + completedReplays + ",\"logEnd\":" + end
            + ",\"committedOffset\":" + offset + ",\"lag\":" + (end - offset)
            + ",\"runRows\":" + jdbc.queryForObject("SELECT COUNT(*) FROM demo_run WHERE id = ?", Long.class, runId)
            + ",\"outcomeRows\":" + jdbc.queryForObject("SELECT COUNT(*) FROM demo_outcome WHERE run_id = ?", Long.class, runId) + "}\n";
        System.out.print("KAFKA_EVIDENCE " + json);
        String evidencePath = System.getProperty("lab.kafka.evidence.file");
        if (evidencePath != null && !evidencePath.isBlank()) {
            Files.writeString(Path.of(evidencePath), json, StandardCharsets.UTF_8,
                StandardOpenOption.CREATE, StandardOpenOption.APPEND, StandardOpenOption.WRITE);
        }
    }

    private void assertEmptyJobs() {
        assertThat(jdbc.queryForObject("SELECT COUNT(*) FROM lab_job", Long.class)).isZero();
        assertThat(jdbc.queryForObject("SELECT COUNT(*) FROM lab_outbox", Long.class)).isZero();
        assertThat(jdbc.queryForObject("SELECT COUNT(*) FROM lab_job_slot", Long.class)).isEqualTo(1L);
        assertThat(jdbc.queryForObject("SELECT occupied_run_id FROM lab_job_slot WHERE id = 1", String.class)).isNull();
    }

    @AfterEach void stopOnlyOwnedChildrenAndDeleteOnlyOwnedResources() throws Exception {
        if (runId == null) { return; }
        for (Probe probe : probes) {
            if (probe.process().isAlive()) {
                probe.process().destroyForcibly();
                assertThat(probe.process().waitFor(10, TimeUnit.SECONDS)).isTrue();
            }
        }
        probes.clear();
        try {
            if (group != null) { deleteGroupBounded(); }
            if (topic != null) { deleteTopicBounded(); }
            if (s3 != null && rawKey != null) {
                String prefix = "raw/" + runId + "/";
                if (!rawKey.startsWith(prefix)) { throw new IllegalStateException("Refusing cleanup outside the owned raw prefix"); }
                s3.deleteObject(DeleteObjectRequest.builder().bucket(bucket).key(rawKey).build());
                assertThat(s3.listObjectsV2(ListObjectsV2Request.builder().bucket(bucket).prefix(prefix).build()).contents()).isEmpty();
            }
        } finally {
            new TransactionTemplate(transactionManager).executeWithoutResult(ignored -> {
                String occupied = jdbc.queryForObject("SELECT occupied_run_id FROM lab_job_slot WHERE id = 1 FOR UPDATE", String.class);
                if (occupied != null && !runId.equals(occupied)) { throw new IllegalStateException("Unexpected occupied job slot"); }
                assertThat(jdbc.queryForObject("SELECT COUNT(*) FROM lab_job WHERE run_id <> ?", Long.class, runId)).isZero();
                assertThat(jdbc.queryForObject("SELECT COUNT(*) FROM lab_outbox WHERE job_run_id <> ?", Long.class, runId)).isZero();
                if (occupied != null) { jdbc.update("UPDATE lab_job_slot SET occupied_run_id = NULL WHERE id = 1"); }
                jdbc.update("DELETE FROM lab_outbox WHERE job_run_id = ?", runId);
                jdbc.update("DELETE FROM demo_outcome WHERE run_id = ?", runId);
                jdbc.update("DELETE FROM demo_run WHERE id = ?", runId);
                jdbc.update("DELETE FROM lab_job WHERE run_id = ?", runId);
            });
            assertEmptyJobs();
        }
    }

    private void deleteGroupBounded() throws Exception {
        requireOwnedResourceName(group);
        long deadline = System.nanoTime() + Duration.ofSeconds(35).toNanos();
        while (true) {
            try { kafka.deleteConsumerGroups(List.of(group)).all().get(5, TimeUnit.SECONDS); return; }
            catch (java.util.concurrent.ExecutionException failure) {
                if (failure.getCause() instanceof GroupIdNotFoundException) { return; }
                if (!(failure.getCause() instanceof GroupNotEmptyException)
                    && !(failure.getCause() instanceof RetriableException)) { throw failure; }
            } catch (java.util.concurrent.TimeoutException timeout) {
                if (System.nanoTime() >= deadline) { throw timeout; }
            }
            if (System.nanoTime() >= deadline) { throw new AssertionError("Owned consumer group did not empty before cleanup deadline"); }
            Thread.sleep(250);
        }
    }

    private void deleteTopicBounded() throws Exception {
        requireOwnedResourceName(topic);
        long deadline = System.nanoTime() + Duration.ofSeconds(25).toNanos();
        while (true) {
            try { kafka.deleteTopics(List.of(topic)).all().get(5, TimeUnit.SECONDS); break; }
            catch (java.util.concurrent.ExecutionException failure) {
                if (failure.getCause() instanceof UnknownTopicOrPartitionException) { break; }
                if (!(failure.getCause() instanceof RetriableException)) { throw failure; }
            } catch (java.util.concurrent.TimeoutException timeout) {
                if (System.nanoTime() >= deadline) { throw timeout; }
            }
            if (System.nanoTime() >= deadline) { throw new AssertionError("Owned topic was not deleted before cleanup deadline"); }
            Thread.sleep(250);
        }
        while (System.nanoTime() < deadline) {
            Set<String> names = kafka.listTopics().names().get(5, TimeUnit.SECONDS);
            if (!names.contains(topic)) { return; }
            Thread.sleep(250);
        }
        throw new AssertionError("Owned topic still exists after bounded cleanup");
    }

    @AfterAll void closeExplicitClients() {
        if (kafka != null) { kafka.close(Duration.ofSeconds(5)); }
        if (s3 != null) { s3.close(); }
        // Private checkpoint/child logs deliberately remain in the OS temporary directory for failure diagnosis.
    }

    static void requireOwnedResourceName(String value) {
        if (value == null || !value.matches("platform-lab-kafka-test-(?:topic|group)-[a-f0-9-]{36}")) {
            throw new IllegalArgumentException("Expected a UUID resource under the dedicated Kafka test prefix");
        }
    }
    private static void requireValidPort(URI uri) {
        if (uri.getPort() < 1 || uri.getPort() > 65535) { throw new IllegalArgumentException("Invalid numeric loopback test port"); }
    }
    static String required(String name) {
        String value = System.getenv(name);
        if (value == null || value.isBlank()) { throw new IllegalArgumentException(name + " is required for the isolated Kafka test"); }
        return value;
    }
    private record Probe(Process process, Path checkpoint, Path log, String mode) {}
    private record Snapshot(LabJobService.Job job, byte[] sourceBytes, List<Map<String, Object>> outbox,
                            List<Map<String, Object>> runs, List<Map<String, Object>> outcomes, String slot) {}
}
