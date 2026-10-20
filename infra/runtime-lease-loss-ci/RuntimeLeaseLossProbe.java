package io.github.devdooly.platformlab.jobs.runtime;

import io.github.devdooly.platformlab.PlatformLabApplication;
import io.github.devdooly.platformlab.jobs.LabJobService;
import io.github.devdooly.platformlab.jobs.S3ClientFactory;
import io.github.devdooly.platformlab.jobs.S3RawSourceStore;
import io.github.devdooly.platformlab.jobs.exporting.ResultExportService;
import io.github.devdooly.platformlab.jobs.exporting.S3ResultExportStore;
import io.github.devdooly.platformlab.jobs.messaging.DispatchPublisher;
import io.github.devdooly.platformlab.jobs.messaging.DispatchWorker;
import io.github.devdooly.platformlab.jobs.messaging.KafkaClientFactory;
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
import java.sql.Connection;
import java.sql.SQLException;
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
import org.springframework.jdbc.datasource.DelegatingDataSource;
import software.amazon.awssdk.auth.credentials.AwsBasicCredentials;
import software.amazon.awssdk.auth.credentials.StaticCredentialsProvider;
import software.amazon.awssdk.services.s3.S3Client;
import tools.jackson.databind.JsonNode;
import tools.jackson.databind.json.JsonMapper;

/** Test-only boundary observer. The lease connection, SQL checks and SDK actions are real delegates. */
public final class RuntimeLeaseLossProbe {
    private static final JsonMapper JSON = JsonMapper.builder().build();
    private static final Set<String> FILES = Set.of("ready.json", "kill-ack.json", "exit.json");
    private static final int MAX_PRIVATE_BYTES = 16384;
    private RuntimeLeaseLossProbe() {}

    public static void main(String[] arguments) {
        String phase = "INPUT";
        try {
            check(arguments.length == 7 && "daemon".equals(arguments[0]));
            String topic = arguments[1], group = arguments[2], run = arguments[6];
            ContinuousRuntimeIT.requireOwnedName(topic); ContinuousRuntimeIT.requireOwnedName(group);
            ContinuousRuntimeIT.requireOwnedRun(run);
            Path ready = privatePath(Path.of(arguments[3]), "ready.json");
            Path acknowledgement = privatePath(Path.of(arguments[4]), "kill-ack.json");
            Path exit = privatePath(Path.of(arguments[5]), "exit.json");
            check(ready.getParent().equals(acknowledgement.getParent()) && acknowledgement.getParent().equals(exit.getParent()));
            for (Path path : new Path[] {ready, acknowledgement, exit}) { check(!Files.exists(path, LinkOption.NOFOLLOW_LINKS)); }
            String database = ContinuousRuntimeIT.disposableDatabaseUrl();
            String bootstrap = ContinuousRuntimeIT.guardedBootstrap();
            var endpoint = ContinuousRuntimeIT.guardedS3Endpoint();
            String bucket = ContinuousRuntimeIT.guardedBucket(), source = ContinuousRuntimeIT.guardedSourceCommit();
            check("runtimeit".equals(ContinuousRuntimeIT.required("DB_TEST_USERNAME")));
            binding();
            check(Runtime.version().feature() == 21 && ZoneId.systemDefault().equals(ZoneId.of("Asia/Seoul")));
            long deadline = System.nanoTime() + Duration.ofSeconds(240).toNanos();
            var closed = new AtomicInteger(); var publisherCalls = new AtomicInteger(); var receiverCalls = new AtomicInteger();
            var emptyExport = new AtomicBoolean(); var gateReleased = new AtomicBoolean();
            var readyPublished = new AtomicBoolean(); var progressReady = new AtomicBoolean();
            var leaseLost = new AtomicBoolean(); var leaseCloseReturned = new AtomicBoolean();
            var expectedTerminal = new AtomicBoolean();
            phase = "CONTEXT";
            try (ConfigurableApplicationContext context = new SpringApplicationBuilder(PlatformLabApplication.class)
                    .web(WebApplicationType.NONE).profiles("db-test", "worker").properties("logging.level.root=WARN")
                    .initializers(application -> application.getEnvironment().getPropertySources().addFirst(new MapPropertySource(
                        "guarded-runtime-lease-loss-probe", Map.of("spring.datasource.url", database,
                            "spring.datasource.username", ContinuousRuntimeIT.required("DB_TEST_USERNAME"),
                            "spring.datasource.password", ContinuousRuntimeIT.required("DB_TEST_PASSWORD"),
                            "spring.flyway.enabled", "false", "spring.sql.init.mode", "never",
                            "spring.jpa.hibernate.ddl-auto", "validate", "lab.environment", "isolated-lab",
                            "lab.source-commit", source))))
                    .run()) {
                DataSource dataSource = context.getBean(DataSource.class);
                var jdbc = context.getBean(JdbcTemplate.class);
                var states = new RuntimeStateStore(jdbc, Clock.systemUTC()); states.requireSchemaV4();
                var capture = new CapturingDataSource(dataSource);
                try (var actualLease = MariaDbRuntimeLease.acquire(capture)) {
                    check(capture.borrowed.get() == 1 && capture.connectionId > 0 && capture.currentUser != null
                        && states.read().status() != RuntimeStateStore.Status.PAUSED_OPERATOR);
                    RuntimeLease observedLease = new RuntimeLease() {
                        @Override public void verifyHeld() {
                            try { actualLease.verifyHeld(); }
                            catch (RuntimeLease.LeaseLostException failure) {
                                // Observe the real delegate exception, never synthesize ownership loss.
                                if (gateReleased.get()) { leaseLost.set(true); }
                                throw failure;
                            }
                        }
                        @Override public void close() { actualLease.close(); leaseCloseReturned.set(true); }
                    };
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
                        check(jobs.get(run).status() == LabJobService.Status.QUEUED
                            && jobs.get(run).exportStatus() == LabJobService.ExportStatus.NOT_REQUESTED);
                        var delegated = new JobRuntimeActions(jobs, new DispatchPublisher(jobs, actualProducer, topic),
                            new DispatchWorker(jobs, new S3RawSourceStore(actualS3, bucket), actualConsumer, topic),
                            new ResultExportService(jobs, new S3ResultExportStore(actualS3, bucket)));
                        ContinuousJobRunner.Actions actions = new ContinuousJobRunner.Actions() {
                            @Override public boolean exportOne() {
                                // All real work for this empty export action has completed before the fault barrier.
                                boolean worked = delegated.exportOne();
                                check(!worked && emptyExport.compareAndSet(false, true));
                                var current = states.read();
                                check(current.status() == RuntimeStateStore.Status.RUNNING
                                    && current.stage() == RuntimeStateStore.Stage.EXPORT && current.failureCode() == null);
                                var fields = new LinkedHashMap<String, Object>(control("LEASE_HELD_READY"));
                                fields.put("leaseConnectionId", capture.connectionId);
                                fields.put("leaseCurrentUser", capture.currentUser); fields.put("emptyExportObserved", true);
                                writePrivate(ready, fields); readyPublished.set(true);
                                long until = Math.min(deadline, System.nanoTime() + Duration.ofSeconds(60).toNanos());
                                try {
                                    while (!Files.exists(acknowledgement, LinkOption.NOFOLLOW_LINKS)) {
                                        check(System.nanoTime() < until); Thread.sleep(50);
                                    }
                                    check(Arrays.equals(readRaw(acknowledgement), canonical(control("LEASE_CONNECTION_KILLED"))));
                                    check(System.nanoTime() < until);
                                } catch (InterruptedException interrupted) {
                                    Thread.currentThread().interrupt(); throw new IllegalStateException("LEASE_CONTROL_INTERRUPTED");
                                }
                                gateReleased.set(true);
                                return worked;
                            }
                            @Override public boolean publishOne() throws Exception {
                                publisherCalls.incrementAndGet(); return delegated.publishOne();
                            }
                            @Override public boolean receiveOne(Duration timeout) {
                                receiverCalls.incrementAndGet(); return delegated.receiveOne(timeout);
                            }
                        };
                        // This observes the production callback contract, not a live HTTP readiness endpoint.
                        RuntimeProgress progress = new RuntimeProgress() {
                            @Override public void starting() { progressReady.set(false); }
                            @Override public void committed(String stage) { progressReady.set(true); }
                            @Override public void notReady() { progressReady.set(false); }
                        };
                        var runner = new ContinuousJobRunner(states, observedLease, actions, resources, source,
                            Duration.ofMillis(500), Duration.ofMillis(500), progress);
                        phase = "RUNNING";
                        try { runner.run(); }
                        catch (IllegalStateException failure) {
                            check(leaseLost.get() && "Runtime stopped without a verified journal update".equals(failure.getMessage()));
                            expectedTerminal.set(true);
                        }
                        check(expectedTerminal.get() && readyPublished.get() && gateReleased.get()
                            && leaseLost.get() && leaseCloseReturned.get() && emptyExport.get()
                            && publisherCalls.get() == 0 && receiverCalls.get() == 0
                            && !progressReady.get() && closed.get() == 7 && System.nanoTime() < deadline);
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
            // Publish only after actual SDK, lease and Spring context close have returned.
            check(expectedTerminal.get() && closed.get() == 7 && leaseCloseReturned.get() && !progressReady.get()
                && publisherCalls.get() == 0 && receiverCalls.get() == 0 && System.nanoTime() < deadline);
            var result = new LinkedHashMap<String, Object>(control("LEASE_LOSS_TERMINATED"));
            result.put("actualLeaseLostObserved", true); result.put("nextStageRejected", true);
            result.put("publisherCalls", publisherCalls.get()); result.put("receiverCalls", receiverCalls.get());
            result.put("emptyExportObserved", true); result.put("resourcesClosed", true);
            result.put("springContextClosed", true); result.put("progressNotReady", true);
            result.put("terminalCode", "RUNTIME_JOURNAL_UPDATE_UNVERIFIED"); result.put("leaseCloseReturned", true);
            writePrivate(exit, result);
        } catch (Throwable failure) {
            if (failure instanceof InterruptedException || failure instanceof org.apache.kafka.common.errors.InterruptException) {
                Thread.currentThread().interrupt();
            }
            System.out.println("RUNTIME_LEASE_LOSS_PROBE_FAILURE {\"phase\":\"" + phase + "\",\"cause\":\"UNVERIFIED\"}");
            throw new AssertionError("RUNTIME_LEASE_LOSS_PROBE_FIXED_FAILURE_" + phase);
        }
    }

    /** Exactly one real connection is returned unchanged to the production lease implementation. */
    private static final class CapturingDataSource extends DelegatingDataSource {
        final AtomicInteger borrowed = new AtomicInteger();
        long connectionId;
        String currentUser;
        CapturingDataSource(DataSource delegate) { super(delegate); }
        @Override public Connection getConnection() throws SQLException {
            check(borrowed.incrementAndGet() == 1);
            Connection connection = super.getConnection(); boolean verified = false;
            try {
                check("MariaDB".equals(connection.getMetaData().getDatabaseProductName()) && connection.getAutoCommit()
                    && "platform_lab_runtime_it".equals(connection.getCatalog()));
                try (var query = connection.prepareStatement("SELECT CONNECTION_ID(), CURRENT_USER(), DATABASE()")) {
                    query.setQueryTimeout(3);
                    try (var rows = query.executeQuery()) {
                        check(rows.next()); long actual = rows.getLong(1); check(!rows.wasNull() && actual > 0);
                        String user = rows.getString(2), catalog = rows.getString(3);
                        check(user != null && user.startsWith("runtimeit@") && user.length() <= 256
                            && !user.contains("\n") && !user.contains("\r") && "platform_lab_runtime_it".equals(catalog)
                            && !rows.next());
                        connectionId = actual; currentUser = user;
                    }
                }
                verified = true; return connection;
            } finally { if (!verified) { connection.close(); } }
        }
        @Override public Connection getConnection(String username, String password) throws SQLException {
            throw new SQLException("LEASE_CAPTURE_REQUIRES_SINGLE_DEFAULT_CONNECTION");
        }
    }

    public static Path controlDirectory() {
        try {
            check("/owned/api/target/runtime-lease-loss-control".equals(required("LEASE_CONTROL_DIR")));
            Path directory = Path.of("/owned/api/target/runtime-lease-loss-control");
            for (Path selected = directory; selected != null && selected.startsWith("/owned/api"); selected = selected.getParent()) {
                check(!Files.isSymbolicLink(selected));
            }
            check(Files.isDirectory(directory, LinkOption.NOFOLLOW_LINKS)
                && Files.getPosixFilePermissions(directory, LinkOption.NOFOLLOW_LINKS).equals(PosixFilePermissions.fromString("rwx------")));
            long uid = ((Number) Files.getAttribute(directory, "unix:uid", LinkOption.NOFOLLOW_LINKS)).longValue();
            long stagedUid = ((Number) Files.getAttribute(Path.of("/owned/api/pom.xml"), "unix:uid", LinkOption.NOFOLLOW_LINKS)).longValue();
            check(uid > 0 && uid == stagedUid); binding(); return directory;
        } catch (Exception unverified) { throw controlFailure(); }
    }

    private static Map<String, Object> binding() {
        String nonce = required("LEASE_CONTROL_NONCE"), runId = required("LEASE_CONTROL_RUN_ID");
        check(nonce.matches("[a-f0-9]{32}") && runId.matches("[0-9]{1,18}"));
        return Map.of("schemaVersion", 1, "sourceCommit", ContinuousRuntimeIT.guardedSourceCommit(), "runId", runId, "nonce", nonce);
    }
    private static Map<String, Object> control(String phase) {
        check(Set.of("LEASE_HELD_READY", "LEASE_CONNECTION_KILLED", "LEASE_LOSS_TERMINATED").contains(phase));
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
                && path.getFileName().toString().equals(name)); childDirectory(path.getParent()); return path;
        } catch (Exception unverified) { throw controlFailure(); }
    }
    public static void writeKillAcknowledgement(Path childFolder) {
        try { writePrivate(childDirectory(childFolder).resolve("kill-ack.json"), control("LEASE_CONNECTION_KILLED")); }
        catch (Exception unverified) { throw controlFailure(); }
    }
    public static JsonNode readPrivate(Path path) {
        check(Set.of("ready.json", "exit.json").contains(path.getFileName().toString()));
        try {
            byte[] raw = readRaw(path); JsonNode value = JSON.readTree(raw); check(value.isObject());
            var sorted = new TreeMap<String, JsonNode>(); value.properties().forEach(entry -> sorted.put(entry.getKey(), entry.getValue()));
            check(Arrays.equals(raw, canonical(sorted))); return value;
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
                ByteBuffer bytes = ByteBuffer.wrap(raw); while (bytes.hasRemaining()) { output.write(bytes); } output.force(true);
            }
            check(!Files.exists(path, LinkOption.NOFOLLOW_LINKS)); Files.move(pending, path, StandardCopyOption.ATOMIC_MOVE);
            check(Arrays.equals(readRaw(path), raw));
        } catch (Exception unverified) { throw controlFailure(); }
    }
    private static String required(String name) {
        String value = System.getenv(name); check(value != null && !value.isBlank()); return value;
    }
    private static IllegalStateException controlFailure() { return new IllegalStateException("RUNTIME_LEASE_LOSS_CONTROL_UNVERIFIED"); }
    private static void check(boolean value) { if (!value) { throw new AssertionError("RUNTIME_LEASE_LOSS_PROBE_ASSERTION"); } }
}
