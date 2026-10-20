package io.github.devdooly.platformlab.jobs.messaging;

import io.github.devdooly.platformlab.PlatformLabApplication;
import io.github.devdooly.platformlab.jobs.LabJobService;
import io.github.devdooly.platformlab.jobs.S3ClientFactory;
import io.github.devdooly.platformlab.jobs.S3RawSourceStore;
import io.github.devdooly.platformlab.jobs.exporting.ResultExportService;
import io.github.devdooly.platformlab.jobs.exporting.S3ResultExportStore;
import io.github.devdooly.platformlab.jobs.runtime.ContinuousJobRunner;
import io.github.devdooly.platformlab.jobs.runtime.ContinuousRuntimeIT;
import io.github.devdooly.platformlab.jobs.runtime.JobRuntimeActions;
import io.github.devdooly.platformlab.jobs.runtime.MariaDbRuntimeLease;
import io.github.devdooly.platformlab.jobs.runtime.RuntimeResources;
import io.github.devdooly.platformlab.jobs.runtime.RuntimeStateStore;
import java.nio.ByteBuffer;
import java.nio.channels.FileChannel;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.LinkOption;
import java.nio.file.Path;
import java.nio.file.StandardCopyOption;
import java.nio.file.StandardOpenOption;
import java.nio.file.attribute.BasicFileAttributes;
import java.nio.file.attribute.PosixFilePermissions;
import java.time.Clock;
import java.time.Duration;
import java.time.ZoneId;
import java.util.Arrays;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.Set;
import java.util.TreeMap;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicInteger;
import javax.sql.DataSource;
import org.apache.kafka.clients.consumer.Consumer;
import org.apache.kafka.clients.producer.Producer;
import org.springframework.boot.WebApplicationType;
import org.springframework.boot.builder.SpringApplicationBuilder;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.core.env.MapPropertySource;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.transaction.support.TransactionSynchronizationManager;
import software.amazon.awssdk.auth.credentials.AwsBasicCredentials;
import software.amazon.awssdk.auth.credentials.StaticCredentialsProvider;
import software.amazon.awssdk.services.s3.S3Client;
import tools.jackson.databind.JsonNode;
import tools.jackson.databind.json.JsonMapper;

/** Test-only real clients/loop. The sole fault seam waits before the original real offset commit. */
public final class OffsetCommitRecoveryProbe {
    private static final JsonMapper JSON = JsonMapper.builder().build();
    private static final Map<String, String> CONTROL_PHASES = Map.of(
        "post-db-commit-ready.json", "POST_DB_COMMIT_READY", "broker-paused-ack.json", "BROKER_PAUSED",
        "paused-observed.json", "PAUSED_OBSERVED", "broker-unpaused-ack.json", "BROKER_UNPAUSED");
    private static final Set<String> PRIVATE_FILES = Set.of("fault-exit.json", "recovery-exit.json", "recovery-stop.request");
    private OffsetCommitRecoveryProbe() {}

    public static void main(String[] arguments) {
        String phase = "INPUT";
        try {
            check(arguments.length == 4);
            String mode = arguments[0], topic = arguments[1], group = arguments[2], run = arguments[3];
            check(Set.of("fault", "recover").contains(mode));
            ContinuousRuntimeIT.requireOwnedName(topic); ContinuousRuntimeIT.requireOwnedName(group);
            ContinuousRuntimeIT.requireOwnedRun(run);
            String database = ContinuousRuntimeIT.disposableDatabaseUrl();
            String bootstrap = ContinuousRuntimeIT.guardedBootstrap();
            var endpoint = ContinuousRuntimeIT.guardedS3Endpoint();
            String bucket = ContinuousRuntimeIT.guardedBucket(), source = ContinuousRuntimeIT.guardedSourceCommit();
            controlDirectory(); binding();
            check(Runtime.version().feature() == 21 && ZoneId.systemDefault().equals(ZoneId.of("Asia/Seoul")));
            check(!controlExists(mode.equals("fault") ? "fault-exit.json" : "recovery-exit.json"));
            long deadline = System.nanoTime() + Duration.ofSeconds(240).toNanos();
            RuntimeStateStore.State finalState;
            AtomicInteger closed = new AtomicInteger(), replays = new AtomicInteger();
            phase = "CONTEXT";
            try (ConfigurableApplicationContext context = new SpringApplicationBuilder(PlatformLabApplication.class)
                    .web(WebApplicationType.NONE).profiles("db-test", "worker").properties("logging.level.root=WARN")
                    .initializers(application -> application.getEnvironment().getPropertySources().addFirst(new MapPropertySource(
                        "guarded-offset-recovery-probe", Map.of("spring.datasource.url", database,
                            "spring.datasource.username", ContinuousRuntimeIT.required("DB_TEST_USERNAME"),
                            "spring.datasource.password", ContinuousRuntimeIT.required("DB_TEST_PASSWORD"),
                            "spring.flyway.enabled", "false", "spring.sql.init.mode", "never",
                            "spring.jpa.hibernate.ddl-auto", "validate", "lab.environment", "isolated-lab",
                            "lab.source-commit", source))))
                    .run()) {
                DataSource dataSource = context.getBean(DataSource.class);
                try (var connection = dataSource.getConnection()) {
                    check("MariaDB".equals(connection.getMetaData().getDatabaseProductName())
                        && "platform_lab_runtime_it".equals(connection.getCatalog()));
                }
                var jdbc = context.getBean(JdbcTemplate.class);
                var states = new RuntimeStateStore(jdbc, Clock.systemUTC()); states.requireSchemaV4();
                try (var lease = MariaDbRuntimeLease.acquire(dataSource)) {
                    check(states.read().status() != RuntimeStateStore.Status.PAUSED_OPERATOR);
                    try (var admin = ContinuousRuntimeIT.admin()) { ContinuousRuntimeIT.requireExpectedCluster(admin); }
                    phase = "CLIENTS";
                    Producer<String, String> producer = null;
                    Consumer<String, String> consumer = null;
                    S3Client s3 = null;
                    RuntimeResources resources = null;
                    try {
                        producer = KafkaClientFactory.producer(bootstrap);
                        consumer = KafkaClientFactory.consumerForRuntime(bootstrap, group);
                        s3 = S3ClientFactory.createGarage(endpoint, "garage", StaticCredentialsProvider.create(AwsBasicCredentials.create(
                            ContinuousRuntimeIT.required("LAB_S3_TEST_ACCESS_KEY"), ContinuousRuntimeIT.required("LAB_S3_TEST_SECRET_KEY"))));
                        final Producer<String, String> actualProducer = producer;
                        final Consumer<String, String> actualConsumer = consumer;
                        final S3Client actualS3 = s3;
                        resources = new RuntimeResources(
                            () -> { actualConsumer.close(Duration.ofSeconds(10)); closed.getAndUpdate(value -> value | 1); },
                            () -> { actualProducer.close(Duration.ofSeconds(10)); closed.getAndUpdate(value -> value | 2); },
                            () -> { actualS3.close(); closed.getAndUpdate(value -> value | 4); });
                        LabJobService jobs = context.getBean(LabJobService.class);
                        java.util.function.Consumer<DispatchWorker.Delivery> boundary = delivery -> {
                            if (!mode.equals("fault")) { return; }
                            check(!TransactionSynchronizationManager.isActualTransactionActive()
                                && run.equals(delivery.runId()) && delivery.partition() == 0 && delivery.offset() == 0
                                && delivery.nextOffset() == 1 && !delivery.replay());
                            var job = jobs.get(run);
                            check(job.status() == LabJobService.Status.COMPLETED
                                && job.exportStatus() == LabJobService.ExportStatus.PENDING
                                && run.equals(jdbc.queryForObject("SELECT occupied_run_id FROM lab_job_slot WHERE id=1", String.class)));
                            writeControl("post-db-commit-ready.json", "POST_DB_COMMIT_READY");
                            // Returning normally is essential: a callback exception is PROCESSING_FAILED,
                            // while this test requires the original commitSync itself to fail.
                            awaitControl("broker-paused-ack.json", "BROKER_PAUSED",
                                Math.min(deadline, System.nanoTime() + Duration.ofSeconds(90).toNanos()));
                        };
                        var worker = new DispatchWorker(jobs, new S3RawSourceStore(actualS3, bucket), actualConsumer, topic, boundary);
                        var delegated = new JobRuntimeActions(jobs, new DispatchPublisher(jobs, actualProducer, topic), worker,
                            new ResultExportService(jobs, new S3ResultExportStore(actualS3, bucket)));
                        ContinuousJobRunner.Actions actions = new ContinuousJobRunner.Actions() {
                            @Override public boolean exportOne() { return delegated.exportOne(); }
                            @Override public boolean publishOne() throws Exception { return delegated.publishOne(); }
                            @Override public boolean receiveOne(Duration timeout) {
                                if (mode.equals("fault")) { return delegated.receiveOne(timeout); }
                                // Same real receive, once. Only observe its returned completed replay.
                                var received = worker.receiveOne(timeout);
                                if (received.isEmpty()) { return false; }
                                var delivery = received.orElseThrow();
                                check(run.equals(delivery.runId()) && delivery.offset() == 0 && delivery.nextOffset() == 1
                                    && delivery.replay() && replays.incrementAndGet() == 1);
                                return true;
                            }
                        };
                        var runner = new ContinuousJobRunner(states, lease, actions, resources, source,
                            Duration.ofMillis(500), Duration.ofMillis(500));
                        AtomicBoolean finished = new AtomicBoolean(), watcherFailed = new AtomicBoolean();
                        Thread watcher = new Thread(() -> {
                            try {
                                while (!finished.get()) {
                                    if (System.nanoTime() >= deadline) { watcherFailed.set(true); runner.requestStop(); return; }
                                    if (mode.equals("recover") && controlExists("recovery-stop.request")) {
                                        check(Arrays.equals(readRaw("recovery-stop.request"), "stop\n".getBytes(StandardCharsets.US_ASCII)));
                                        runner.requestStop(); return;
                                    }
                                    Thread.sleep(50);
                                }
                            } catch (InterruptedException interrupted) {
                                if (!finished.get()) { watcherFailed.set(true); runner.requestStop(); }
                            } catch (Throwable unverified) { watcherFailed.set(true); runner.requestStop(); }
                        }, "owned-offset-recovery-stop-watcher");
                        watcher.setDaemon(true); watcher.start();
                        phase = "RUNNING";
                        try { finalState = runner.run(); }
                        finally { finished.set(true); watcher.interrupt(); watcher.join(1000); }
                        check(!watcher.isAlive() && !watcherFailed.get() && closed.get() == 7);
                        if (mode.equals("fault")) {
                            check(finalState.status() == RuntimeStateStore.Status.PAUSED_OPERATOR
                                && finalState.stage() == RuntimeStateStore.Stage.CONSUME
                                && finalState.failureCode() == RuntimeStateStore.FailureCode.OFFSET_COMMIT_FAILED);
                        } else {
                            check(finalState.status() == RuntimeStateStore.Status.STOPPED
                                && finalState.stage() == RuntimeStateStore.Stage.STOPPED && finalState.failureCode() == null
                                && replays.get() >= 0 && replays.get() <= 1);
                        }
                        phase = "CLOSE";
                    } finally {
                        if (resources != null) { resources.close(); }
                        else {
                            // Constructor failure still closes every returned partial client once.
                            try { if (consumer != null) { consumer.close(Duration.ofSeconds(10)); } }
                            finally { try { if (producer != null) { producer.close(Duration.ofSeconds(10)); } }
                                finally { if (s3 != null) { s3.close(); } } }
                        }
                    }
                }
            }
            // Publish only after clients, DB lease and Spring context have closed successfully.
            check(closed.get() == 7 && System.nanoTime() < deadline);
            var result = new LinkedHashMap<String, Object>(binding());
            result.put("phase", mode.equals("fault") ? "FAULT_CHILD_EXITED" : "RECOVERY_CHILD_EXITED");
            result.put("resourcesClosed", true); result.put("runtimeStatus", finalState.status().name());
            result.put("runtimeStage", finalState.stage().name());
            result.put("failureCode", finalState.failureCode() == null ? null : finalState.failureCode().name());
            result.put("completedReplays", replays.get());
            writePrivate(mode.equals("fault") ? "fault-exit.json" : "recovery-exit.json", result);
        } catch (Throwable failure) {
            if (failure instanceof InterruptedException || failure instanceof org.apache.kafka.common.errors.InterruptException) {
                Thread.currentThread().interrupt();
            }
            System.out.println("OFFSET_COMMIT_RECOVERY_PROBE_FAILURE {\"phase\":\"" + phase + "\",\"cause\":\"UNVERIFIED\"}");
            throw new AssertionError("OFFSET_COMMIT_RECOVERY_PROBE_FIXED_FAILURE_" + phase);
        }
    }

    public static Path controlDirectory() {
        try {
            String raw = required("OFFSET_CONTROL_DIR");
            check("/owned/api/target/offset-control".equals(raw));
            Path directory = Path.of(raw);
            check(Files.isDirectory(directory, LinkOption.NOFOLLOW_LINKS) && !Files.isSymbolicLink(directory)
                && Files.getPosixFilePermissions(directory, LinkOption.NOFOLLOW_LINKS).equals(PosixFilePermissions.fromString("rwx------")));
            long uid = ((Number) Files.getAttribute(directory, "unix:uid", LinkOption.NOFOLLOW_LINKS)).longValue();
            long stagedUid = ((Number) Files.getAttribute(Path.of("/owned/api/pom.xml"), "unix:uid", LinkOption.NOFOLLOW_LINKS)).longValue();
            check(uid == stagedUid && uid > 0);
            return directory;
        } catch (Exception unverified) { throw controlFailure(); }
    }

    private static Map<String, Object> binding() {
        String source = ContinuousRuntimeIT.guardedSourceCommit(), nonce = required("OFFSET_CONTROL_NONCE"), run = required("OFFSET_CONTROL_RUN_ID");
        check(nonce.matches("[a-f0-9]{32}") && run.matches("[0-9]{1,18}"));
        return Map.of("schemaVersion", 1, "sourceCommit", source, "runId", run, "nonce", nonce);
    }

    private static Path file(String name) {
        check(CONTROL_PHASES.containsKey(name) || PRIVATE_FILES.contains(name));
        return controlDirectory().resolve(name);
    }

    public static boolean controlExists(String name) { return Files.exists(file(name), LinkOption.NOFOLLOW_LINKS); }

    public static void writeControl(String name, String phase) {
        check(phase.equals(CONTROL_PHASES.get(name)));
        writeBytes(name, canonicalControl(phase));
    }

    public static void awaitControl(String name, String phase, long deadlineNanos) {
        check(phase.equals(CONTROL_PHASES.get(name)));
        byte[] expected = canonicalControl(phase);
        while (System.nanoTime() < deadlineNanos) {
            if (controlExists(name)) { check(Arrays.equals(readRaw(name), expected)); return; }
            try { Thread.sleep(50); }
            catch (InterruptedException interrupted) { Thread.currentThread().interrupt(); throw controlFailure(); }
        }
        throw controlFailure();
    }

    private static byte[] canonicalControl(String phase) {
        var fields = binding();
        String value = "{\"nonce\":\"" + fields.get("nonce") + "\",\"phase\":\"" + phase
            + "\",\"runId\":\"" + fields.get("runId") + "\",\"schemaVersion\":1,\"sourceCommit\":\""
            + fields.get("sourceCommit") + "\"}\n";
        return value.getBytes(StandardCharsets.US_ASCII);
    }

    public static JsonNode readPrivate(String name) {
        check(Set.of("fault-exit.json", "recovery-exit.json").contains(name));
        try { return JSON.readTree(readRaw(name)); }
        catch (Exception unverified) { throw controlFailure(); }
    }

    private static byte[] readRaw(String name) {
        try {
            Path path = file(name);
            BasicFileAttributes before = Files.readAttributes(path, BasicFileAttributes.class, LinkOption.NOFOLLOW_LINKS);
            check(before.isRegularFile() && before.size() > 0 && before.size() <= 4096
                && Files.getPosixFilePermissions(path, LinkOption.NOFOLLOW_LINKS).equals(PosixFilePermissions.fromString("rw-------"))
                && ((Number) Files.getAttribute(path, "unix:nlink", LinkOption.NOFOLLOW_LINKS)).longValue() == 1
                && Files.getAttribute(path, "unix:uid", LinkOption.NOFOLLOW_LINKS).equals(
                    Files.getAttribute(controlDirectory(), "unix:uid", LinkOption.NOFOLLOW_LINKS)));
            byte[] raw;
            try (var input = Files.newInputStream(path, StandardOpenOption.READ, LinkOption.NOFOLLOW_LINKS)) { raw = input.readNBytes(4097); }
            BasicFileAttributes after = Files.readAttributes(path, BasicFileAttributes.class, LinkOption.NOFOLLOW_LINKS);
            check(raw.length == before.size() && before.size() == after.size() && before.fileKey().equals(after.fileKey())
                && before.lastModifiedTime().equals(after.lastModifiedTime()) && after.isRegularFile());
            return raw;
        } catch (Exception unverified) { throw controlFailure(); }
    }

    private static void writePrivate(String name, Map<String, Object> value) {
        try { writeBytes(name, (JSON.writeValueAsString(new TreeMap<>(value)) + "\n").getBytes(StandardCharsets.UTF_8)); }
        catch (Exception unverified) { throw controlFailure(); }
    }

    private static void writeBytes(String name, byte[] raw) {
        try {
            check(raw.length > 0 && raw.length <= 4096);
            Path destination = file(name), pending = destination.resolveSibling(name + ".pending");
            check(!Files.exists(destination, LinkOption.NOFOLLOW_LINKS) && !Files.exists(pending, LinkOption.NOFOLLOW_LINKS));
            try (FileChannel output = FileChannel.open(pending, Set.of(StandardOpenOption.CREATE_NEW, StandardOpenOption.WRITE,
                    LinkOption.NOFOLLOW_LINKS), PosixFilePermissions.asFileAttribute(PosixFilePermissions.fromString("rw-------")))) {
                ByteBuffer bytes = ByteBuffer.wrap(raw);
                while (bytes.hasRemaining()) { output.write(bytes); }
                output.force(true);
            }
            // Each bound phase has one writer and a fresh name in this private directory.
            Files.move(pending, destination, StandardCopyOption.ATOMIC_MOVE);
            check(Arrays.equals(readRaw(name), raw));
        } catch (Exception unverified) { throw controlFailure(); }
    }

    public static String required(String name) {
        String value = System.getenv(name); check(value != null && !value.isBlank()); return value;
    }

    private static IllegalStateException controlFailure() { return new IllegalStateException("OFFSET_RECOVERY_CONTROL_UNVERIFIED"); }
    private static void check(boolean value) { if (!value) { throw new AssertionError("OFFSET_RECOVERY_PROBE_ASSERTION"); } }
}
