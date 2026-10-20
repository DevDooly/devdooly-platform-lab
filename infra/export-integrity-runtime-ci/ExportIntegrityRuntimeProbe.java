package io.github.devdooly.platformlab.jobs.messaging;

import io.github.devdooly.platformlab.PlatformLabApplication;
import io.github.devdooly.platformlab.jobs.LabJobService;
import io.github.devdooly.platformlab.jobs.S3ClientFactory;
import io.github.devdooly.platformlab.jobs.S3RawSourceStore;
import io.github.devdooly.platformlab.jobs.exporting.ResultExportService;
import io.github.devdooly.platformlab.jobs.exporting.ResultExportStore;
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

/** Test-only observer. Every storage operation and runtime action delegates to production code. */
public final class ExportIntegrityRuntimeProbe {
    private static final JsonMapper JSON = JsonMapper.builder().build();
    private static final Set<String> FILES = Set.of("checkpoint.json", "stop.request", "exit.json");
    private static final int MAX_PRIVATE_BYTES = 16384;
    private ExportIntegrityRuntimeProbe() {}

    public static void main(String[] arguments) {
        String phase = "INPUT";
        try {
            check(arguments.length == 7 && "daemon".equals(arguments[0]));
            String topic = arguments[1], group = arguments[2], run = arguments[6];
            ContinuousRuntimeIT.requireOwnedName(topic); ContinuousRuntimeIT.requireOwnedName(group);
            ContinuousRuntimeIT.requireOwnedRun(run);
            Path checkpoint = privatePath(Path.of(arguments[3]), "checkpoint.json");
            Path stop = privatePath(Path.of(arguments[4]), "stop.request");
            Path exit = privatePath(Path.of(arguments[5]), "exit.json");
            check(checkpoint.getParent().equals(stop.getParent()) && stop.getParent().equals(exit.getParent()));
            check(!Files.exists(checkpoint, LinkOption.NOFOLLOW_LINKS)
                && !Files.exists(stop, LinkOption.NOFOLLOW_LINKS) && !Files.exists(exit, LinkOption.NOFOLLOW_LINKS));
            String database = ContinuousRuntimeIT.disposableDatabaseUrl();
            String bootstrap = ContinuousRuntimeIT.guardedBootstrap();
            var endpoint = ContinuousRuntimeIT.guardedS3Endpoint();
            String bucket = ContinuousRuntimeIT.guardedBucket(), source = ContinuousRuntimeIT.guardedSourceCommit();
            binding();
            check(Runtime.version().feature() == 21 && ZoneId.systemDefault().equals(ZoneId.of("Asia/Seoul")));
            long deadline = System.nanoTime() + Duration.ofSeconds(240).toNanos();
            var closed = new AtomicInteger();
            var verificationFailures = new AtomicInteger();
            var replays = new AtomicInteger();
            RuntimeStateStore.State finalState;
            phase = "CONTEXT";
            try (ConfigurableApplicationContext context = new SpringApplicationBuilder(PlatformLabApplication.class)
                    .web(WebApplicationType.NONE).profiles("db-test", "worker").properties("logging.level.root=WARN")
                    .initializers(application -> application.getEnvironment().getPropertySources().addFirst(new MapPropertySource(
                        "guarded-export-integrity-probe", Map.of("spring.datasource.url", database,
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
                        check(jobs.get(run).status() == LabJobService.Status.COMPLETED);
                        var actualStore = new S3ResultExportStore(actualS3, bucket);
                        ResultExportStore observedStore = document -> {
                            // The deliberately corrupt fixture must cause the real delegate's own exception.
                            // This observer neither synthesizes a storage failure nor repairs an object.
                            try { actualStore.storeAndVerify(document); }
                            catch (S3ResultExportStore.ExportVerificationException failure) {
                                verificationFailures.incrementAndGet();
                                throw failure;
                            }
                        };
                        var worker = new DispatchWorker(jobs, new S3RawSourceStore(actualS3, bucket), actualConsumer, topic, delivery -> {
                            check(!TransactionSynchronizationManager.isActualTransactionActive()
                                && run.equals(delivery.runId()) && delivery.partition() == 0 && delivery.offset() == 0
                                && delivery.nextOffset() == 1 && delivery.replay());
                            // Observe the actual completed delivery. The parent separately proves the real commit.
                            check(replays.incrementAndGet() == 1);
                        });
                        var delegated = new JobRuntimeActions(jobs, new DispatchPublisher(jobs, actualProducer, topic), worker,
                            new ResultExportService(jobs, observedStore));
                        var ready = new AtomicBoolean();
                        ContinuousJobRunner.Actions actions = new ContinuousJobRunner.Actions() {
                            @Override public boolean exportOne() {
                                if (ready.compareAndSet(false, true)) {
                                    var current = states.read();
                                    check(current.status() == RuntimeStateStore.Status.RUNNING
                                        && current.stage() == RuntimeStateStore.Stage.EXPORT);
                                    writePrivate(checkpoint, control("RUNNER_READY"));
                                }
                                return delegated.exportOne();
                            }
                            @Override public boolean publishOne() throws Exception { return delegated.publishOne(); }
                            @Override public boolean receiveOne(Duration timeout) { return delegated.receiveOne(timeout); }
                        };
                        var runner = new ContinuousJobRunner(states, lease, actions, resources, source,
                            Duration.ofMillis(500), Duration.ofMillis(500));
                        var finished = new AtomicBoolean();
                        var watcherFailed = new AtomicBoolean();
                        Thread watcher = new Thread(() -> {
                            try {
                                while (!finished.get()) {
                                    if (System.nanoTime() >= deadline) { watcherFailed.set(true); runner.requestStop(); return; }
                                    if (Files.exists(stop, LinkOption.NOFOLLOW_LINKS)) {
                                        check(Arrays.equals(readRaw(stop), canonical(control("STOP_REQUESTED"))));
                                        runner.requestStop(); return;
                                    }
                                    Thread.sleep(50);
                                }
                            } catch (InterruptedException interrupted) {
                                if (!finished.get()) { watcherFailed.set(true); runner.requestStop(); }
                            } catch (Throwable unverified) { watcherFailed.set(true); runner.requestStop(); }
                        }, "owned-export-integrity-stop-watcher");
                        watcher.setDaemon(true); watcher.start();
                        phase = "RUNNING";
                        try { finalState = runner.run(); }
                        finally { finished.set(true); watcher.interrupt(); watcher.join(1000); }
                        check(!watcher.isAlive() && !watcherFailed.get() && closed.get() == 7);
                        if (finalState.status() == RuntimeStateStore.Status.PAUSED_OPERATOR) {
                            check(finalState.stage() == RuntimeStateStore.Stage.EXPORT
                                && finalState.failureCode() == RuntimeStateStore.FailureCode.EXPORT_FAILED
                                && verificationFailures.get() == 1 && replays.get() == 0);
                        } else {
                            check(finalState.status() == RuntimeStateStore.Status.STOPPED
                                && finalState.stage() == RuntimeStateStore.Stage.STOPPED && finalState.failureCode() == null
                                && verificationFailures.get() == 0 && replays.get() == 1);
                        }
                        phase = "CLOSE";
                    } finally {
                        if (resources != null) { resources.close(); }
                        else {
                            try { if (consumer != null) { consumer.close(Duration.ofSeconds(10)); } }
                            finally { try { if (producer != null) { producer.close(Duration.ofSeconds(10)); } }
                                finally { if (s3 != null) { s3.close(); } } }
                        }
                    }
                }
            }
            // The private exit record is published only after clients, lease and Spring context closed.
            check(closed.get() == 7 && System.nanoTime() < deadline);
            var result = new LinkedHashMap<String, Object>(control("DAEMON_EXITED"));
            result.put("resourcesClosed", true); result.put("runtimeStatus", finalState.status().name());
            result.put("runtimeStage", finalState.stage().name());
            result.put("failureCode", finalState.failureCode() == null ? null : finalState.failureCode().name());
            result.put("verificationFailures", verificationFailures.get()); result.put("completedReplays", replays.get());
            writePrivate(exit, result);
        } catch (Throwable failure) {
            if (failure instanceof InterruptedException || failure instanceof org.apache.kafka.common.errors.InterruptException) {
                Thread.currentThread().interrupt();
            }
            System.out.println("EXPORT_INTEGRITY_RUNTIME_PROBE_FAILURE {\"phase\":\"" + phase + "\",\"cause\":\"UNVERIFIED\"}");
            throw new AssertionError("EXPORT_INTEGRITY_RUNTIME_PROBE_FIXED_FAILURE_" + phase);
        }
    }

    public static Path controlDirectory() {
        try {
            check("/owned/api/target/export-integrity-control".equals(required("EXPORT_CONTROL_DIR")));
            Path directory = Path.of("/owned/api/target/export-integrity-control");
            for (Path selected = directory; selected != null && selected.startsWith("/owned/api"); selected = selected.getParent()) {
                check(!Files.isSymbolicLink(selected));
            }
            check(Files.isDirectory(directory, LinkOption.NOFOLLOW_LINKS)
                && Files.getPosixFilePermissions(directory, LinkOption.NOFOLLOW_LINKS).equals(PosixFilePermissions.fromString("rwx------")));
            long uid = ((Number) Files.getAttribute(directory, "unix:uid", LinkOption.NOFOLLOW_LINKS)).longValue();
            long stagedUid = ((Number) Files.getAttribute(Path.of("/owned/api/pom.xml"), "unix:uid", LinkOption.NOFOLLOW_LINKS)).longValue();
            check(uid > 0 && uid == stagedUid);
            binding();
            return directory;
        } catch (Exception unverified) { throw controlFailure(); }
    }

    private static Map<String, Object> binding() {
        String nonce = required("EXPORT_CONTROL_NONCE"), runId = required("EXPORT_CONTROL_RUN_ID");
        check(nonce.matches("[a-f0-9]{32}") && runId.matches("[0-9]{1,18}"));
        return Map.of("schemaVersion", 1, "sourceCommit", ContinuousRuntimeIT.guardedSourceCommit(), "runId", runId, "nonce", nonce);
    }

    private static Map<String, Object> control(String phase) {
        check(Set.of("RUNNER_READY", "STOP_REQUESTED", "DAEMON_EXITED").contains(phase));
        var value = new LinkedHashMap<String, Object>(binding()); value.put("phase", phase); return value;
    }

    private static Path childDirectory(Path folder) throws Exception {
        Path directory = folder.toAbsolutePath().normalize();
        check(folder.equals(directory) && directory.getParent().equals(controlDirectory())
            && directory.getFileName().toString().matches("daemon-[a-f0-9-]{36}")
            && Files.isDirectory(directory, LinkOption.NOFOLLOW_LINKS) && !Files.isSymbolicLink(directory)
            && Files.getPosixFilePermissions(directory, LinkOption.NOFOLLOW_LINKS).equals(PosixFilePermissions.fromString("rwx------"))
            && Files.getAttribute(directory, "unix:uid", LinkOption.NOFOLLOW_LINKS).equals(
                Files.getAttribute(controlDirectory(), "unix:uid", LinkOption.NOFOLLOW_LINKS)));
        return directory;
    }

    private static Path privatePath(Path path, String name) {
        try {
            check(FILES.contains(name) && path.isAbsolute() && path.equals(path.normalize())
                && path.getFileName().toString().equals(name));
            childDirectory(path.getParent()); return path;
        } catch (Exception unverified) { throw controlFailure(); }
    }

    public static void writeStop(Path childFolder) {
        try { writePrivate(childDirectory(childFolder).resolve("stop.request"), control("STOP_REQUESTED")); }
        catch (Exception unverified) { throw controlFailure(); }
    }

    public static JsonNode readPrivate(Path path) {
        check(Set.of("checkpoint.json", "exit.json").contains(path.getFileName().toString()));
        try {
            byte[] raw = readRaw(path); JsonNode value = JSON.readTree(raw); check(value.isObject());
            var sorted = new TreeMap<String, JsonNode>(); value.properties().forEach(entry -> sorted.put(entry.getKey(), entry.getValue()));
            check(Arrays.equals(raw, canonical(sorted))); // Reject duplicate fields and noncanonical private JSON.
            return value;
        } catch (Exception unverified) { throw controlFailure(); }
    }

    private static byte[] readRaw(Path path) {
        try {
            privatePath(path, path.getFileName().toString());
            BasicFileAttributes parentBefore = Files.readAttributes(path.getParent(), BasicFileAttributes.class, LinkOption.NOFOLLOW_LINKS);
            BasicFileAttributes before = Files.readAttributes(path, BasicFileAttributes.class, LinkOption.NOFOLLOW_LINKS);
            check(before.isRegularFile() && before.fileKey() != null && before.size() > 0 && before.size() <= MAX_PRIVATE_BYTES
                && Files.getPosixFilePermissions(path, LinkOption.NOFOLLOW_LINKS).equals(PosixFilePermissions.fromString("rw-------"))
                && ((Number) Files.getAttribute(path, "unix:nlink", LinkOption.NOFOLLOW_LINKS)).longValue() == 1
                && Files.getAttribute(path, "unix:uid", LinkOption.NOFOLLOW_LINKS).equals(
                    Files.getAttribute(controlDirectory(), "unix:uid", LinkOption.NOFOLLOW_LINKS)));
            byte[] raw;
            try (var input = Files.newInputStream(path, StandardOpenOption.READ, LinkOption.NOFOLLOW_LINKS)) {
                raw = input.readNBytes(MAX_PRIVATE_BYTES + 1);
            }
            BasicFileAttributes after = Files.readAttributes(path, BasicFileAttributes.class, LinkOption.NOFOLLOW_LINKS);
            BasicFileAttributes parentAfter = Files.readAttributes(path.getParent(), BasicFileAttributes.class, LinkOption.NOFOLLOW_LINKS);
            check(raw.length == before.size() && after.isRegularFile() && before.size() == after.size()
                && before.fileKey().equals(after.fileKey()) && before.lastModifiedTime().equals(after.lastModifiedTime())
                && parentBefore.fileKey() != null && parentBefore.fileKey().equals(parentAfter.fileKey()));
            privatePath(path, path.getFileName().toString());
            check(Files.getPosixFilePermissions(path, LinkOption.NOFOLLOW_LINKS).equals(PosixFilePermissions.fromString("rw-------"))
                && ((Number) Files.getAttribute(path, "unix:nlink", LinkOption.NOFOLLOW_LINKS)).longValue() == 1
                && Files.getAttribute(path, "unix:uid", LinkOption.NOFOLLOW_LINKS).equals(
                    Files.getAttribute(controlDirectory(), "unix:uid", LinkOption.NOFOLLOW_LINKS)));
            return raw;
        } catch (Exception unverified) { throw controlFailure(); }
    }

    private static byte[] canonical(Map<String, ?> fields) {
        return (JSON.writeValueAsString(new TreeMap<>(fields)) + "\n").getBytes(StandardCharsets.UTF_8);
    }

    private static void writePrivate(Path path, Map<String, Object> value) {
        try {
            privatePath(path, path.getFileName().toString()); byte[] raw = canonical(value);
            check(raw.length > 0 && raw.length <= MAX_PRIVATE_BYTES);
            Path pending = path.resolveSibling(path.getFileName() + ".pending");
            check(!Files.exists(path, LinkOption.NOFOLLOW_LINKS) && !Files.exists(pending, LinkOption.NOFOLLOW_LINKS));
            try (FileChannel output = FileChannel.open(pending, Set.of(StandardOpenOption.CREATE_NEW, StandardOpenOption.WRITE,
                    LinkOption.NOFOLLOW_LINKS), PosixFilePermissions.asFileAttribute(PosixFilePermissions.fromString("rw-------")))) {
                ByteBuffer bytes = ByteBuffer.wrap(raw);
                while (bytes.hasRemaining()) { output.write(bytes); }
                output.force(true);
            }
            check(!Files.exists(path, LinkOption.NOFOLLOW_LINKS));
            Files.move(pending, path, StandardCopyOption.ATOMIC_MOVE);
            check(Arrays.equals(readRaw(path), raw));
        } catch (Exception unverified) { throw controlFailure(); }
    }

    private static String required(String name) {
        String value = System.getenv(name); check(value != null && !value.isBlank()); return value;
    }
    private static IllegalStateException controlFailure() { return new IllegalStateException("EXPORT_INTEGRITY_CONTROL_UNVERIFIED"); }
    private static void check(boolean value) { if (!value) { throw new AssertionError("EXPORT_INTEGRITY_PROBE_ASSERTION"); } }
}
