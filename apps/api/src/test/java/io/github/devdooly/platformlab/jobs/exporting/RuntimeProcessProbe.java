package io.github.devdooly.platformlab.jobs.exporting;

import io.github.devdooly.platformlab.PlatformLabApplication;
import io.github.devdooly.platformlab.jobs.LabJobService;
import io.github.devdooly.platformlab.jobs.S3ClientFactory;
import io.github.devdooly.platformlab.jobs.S3RawSourceStore;
import io.github.devdooly.platformlab.jobs.messaging.DispatchPublisher;
import io.github.devdooly.platformlab.jobs.messaging.DispatchWorker;
import io.github.devdooly.platformlab.jobs.messaging.KafkaClientFactory;
import io.github.devdooly.platformlab.jobs.runtime.ContinuousJobRunner;
import io.github.devdooly.platformlab.jobs.runtime.ContinuousRuntimeIT;
import io.github.devdooly.platformlab.jobs.runtime.JobRuntimeActions;
import io.github.devdooly.platformlab.jobs.runtime.MariaDbRuntimeLease;
import io.github.devdooly.platformlab.jobs.runtime.RuntimeStateStore;
import io.github.devdooly.platformlab.jobs.runtime.RuntimeResources;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardCopyOption;
import java.nio.file.StandardOpenOption;
import java.time.Clock;
import java.time.Duration;
import java.time.ZoneId;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.locks.LockSupport;
import javax.sql.DataSource;
import org.springframework.boot.WebApplicationType;
import org.springframework.boot.builder.SpringApplicationBuilder;
import org.springframework.boot.web.server.context.WebServerApplicationContext;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.core.env.MapPropertySource;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.transaction.support.TransactionSynchronizationManager;
import software.amazon.awssdk.auth.credentials.AwsBasicCredentials;
import software.amazon.awssdk.auth.credentials.StaticCredentialsProvider;
import software.amazon.awssdk.services.s3.model.GetObjectRequest;
import tools.jackson.databind.json.JsonMapper;

/** Opt-in real-process helper: production loop/actions, local readiness files and one export fault seam only. */
public final class RuntimeProcessProbe {
    private static final JsonMapper JSON = JsonMapper.builder().build();
    private RuntimeProcessProbe() {}

    public static void main(String[] arguments) throws Exception {
        if (arguments.length != 7) { throw new IllegalArgumentException("Expected mode, topic, group, checkpoint, stop, exit and run"); }
        String mode = arguments[0], topic = arguments[1], group = arguments[2], run = arguments[6];
        if (!java.util.Set.of("daemon", "api", "resume", "cli-run", "first-export").contains(mode)) { throw new IllegalArgumentException("Unknown runtime probe mode"); }
        ContinuousRuntimeIT.requireOwnedName(topic); ContinuousRuntimeIT.requireOwnedName(group);
        if (mode.equals("first-export")) { ContinuousRuntimeIT.requireOwnedRun(run); }
        Path checkpoint = freshPrivateFile(arguments[3], "checkpoint.json");
        Path stop = freshPrivateFile(arguments[4], "stop.request"); Path exit = freshPrivateFile(arguments[5], "exit.json");
        if (!checkpoint.getParent().equals(stop.getParent()) || !stop.getParent().equals(exit.getParent())) {
            throw new IllegalArgumentException("All local control files must share the owned private directory");
        }
        // Guards precede Spring context resolution, Flyway and every service connection.
        String database = ContinuousRuntimeIT.disposableDatabaseUrl();
        String bootstrap = ContinuousRuntimeIT.guardedBootstrap();
        var endpoint = ContinuousRuntimeIT.guardedS3Endpoint(); String bucket = ContinuousRuntimeIT.guardedBucket();
        String commit = ContinuousRuntimeIT.guardedSourceCommit();
        if (Runtime.version().feature() != 21 || !ZoneId.systemDefault().equals(ZoneId.of("Asia/Seoul"))) {
            throw new IllegalStateException("Real runtime probe requires Java 21 and Asia/Seoul");
        }
        if (mode.equals("resume") || mode.equals("cli-run")) {
            // Parent supplies only the already-guarded DB_URL credentials. This exercises the real explicit CLI.
            if (!database.equals(System.getenv("DB_URL"))) { throw new IllegalStateException("Resume CLI DB must match the guarded schema"); }
            PlatformLabApplication.main(new String[]{mode.equals("resume") ? "--lab-runtime=resume" : "--lab-runtime=run"}); return;
        }
        boolean api = mode.equals("api");
        try (ConfigurableApplicationContext context = new SpringApplicationBuilder(PlatformLabApplication.class)
                .web(api ? WebApplicationType.SERVLET : WebApplicationType.NONE).profiles("db-test", "worker")
                .properties("logging.level.root=WARN")
                .initializers(application -> application.getEnvironment().getPropertySources().addFirst(new MapPropertySource(
                    "guarded-runtime-probe", Map.of("spring.datasource.url", database,
                        "spring.datasource.username", ContinuousRuntimeIT.required("DB_TEST_USERNAME"),
                        "spring.datasource.password", ContinuousRuntimeIT.required("DB_TEST_PASSWORD"),
                        "spring.flyway.enabled", "false", "lab.environment", "isolated-lab", "lab.source-commit", commit,
                        "server.address", "127.0.0.1", "server.port", "0"))))
                .run()) {
            var dataSource = context.getBean(DataSource.class);
            try (var connection = dataSource.getConnection()) {
                if (!connection.getMetaData().getDatabaseProductName().equals("MariaDB") || !connection.getCatalog().equals("platform_lab_runtime_it")) {
                    throw new IllegalStateException("Only the dedicated disposable MariaDB schema is allowed");
                }
            }
            var jdbc = context.getBean(JdbcTemplate.class);
            var states = new RuntimeStateStore(jdbc, Clock.systemUTC()); states.requireSchemaV3();
            if (api) {
                int port = ((WebServerApplicationContext) context).getWebServer().getPort();
                atomic(checkpoint, Map.of("phase", "API_READY", "mode", mode, "port", port));
                while (!Files.exists(stop)) { Thread.sleep(50); }
                context.close(); atomic(exit, Map.of("resourcesClosed", true)); return;
            }
            // Ownership precedes all clients and all journal changes. A refused contender cannot replace the active journal.
            try (var lease = MariaDbRuntimeLease.acquire(dataSource)) {
                if (states.read().status() == RuntimeStateStore.Status.PAUSED_OPERATOR) {
                    throw new RuntimeStateStore.OperatorResumeRequiredException();
                }
                try (var admin = ContinuousRuntimeIT.admin()) { ContinuousRuntimeIT.requireExpectedCluster(admin); }
                var producer = KafkaClientFactory.producer(bootstrap);
                var consumer = KafkaClientFactory.consumerForRuntime(bootstrap, group);
                var s3 = S3ClientFactory.createGarage(endpoint, "garage", StaticCredentialsProvider.create(AwsBasicCredentials.create(
                    ContinuousRuntimeIT.required("LAB_S3_TEST_ACCESS_KEY"), ContinuousRuntimeIT.required("LAB_S3_TEST_SECRET_KEY"))));
                var closed = new AtomicInteger();
                AutoCloseable resources = new RuntimeResources(
                    () -> { consumer.close(Duration.ofSeconds(10)); closed.getAndUpdate(value -> value | 1); },
                    () -> { producer.close(Duration.ofSeconds(10)); closed.getAndUpdate(value -> value | 2); },
                    () -> { s3.close(); closed.getAndUpdate(value -> value | 4); });
                var jobs = context.getBean(LabJobService.class); var verified = new AtomicInteger();
                var exporter = new ResultExportService(jobs, new S3ResultExportStore(s3, bucket), document -> {
                    if (!mode.equals("first-export")) { return; }
                    if (TransactionSynchronizationManager.isActualTransactionActive()) { throw new IllegalStateException("Export callback still in a transaction"); }
                    if (!document.key().startsWith("result/" + run + "/")) { throw new IllegalStateException("Export callback received an unowned run"); }
                    byte[] actual = s3.getObjectAsBytes(GetObjectRequest.builder().bucket(bucket).key(document.key()).build()).asByteArray();
                    if (!document.matches(actual)) { throw new IllegalStateException("Actual export bytes differ at the crash boundary"); }
                    if (verified.incrementAndGet() == 1) {
                        var job = jobs.get(run);
                        if (job.status() != LabJobService.Status.COMPLETED || job.exportStatus() != LabJobService.ExportStatus.PENDING
                            || !run.equals(jdbc.queryForObject("SELECT occupied_run_id FROM lab_job_slot WHERE id=1", String.class))) {
                            throw new IllegalStateException("The crash checkpoint must retain the completed job's pending export slot");
                        }
                        atomic(checkpoint, Map.of("phase", "FIRST_EXPORT_OBJECT_VERIFIED", "mode", mode, "runId", run,
                            "objectsVerified", 1, "activeTransaction", TransactionSynchronizationManager.isActualTransactionActive()));
                        while (true) { LockSupport.parkNanos(Duration.ofSeconds(1).toNanos()); }
                    }
                }, ignored -> {});
                var delegated = new JobRuntimeActions(jobs, new DispatchPublisher(jobs, producer, topic),
                    new DispatchWorker(jobs, new S3RawSourceStore(s3, bucket), consumer, topic), exporter);
                var ready = new AtomicBoolean();
                ContinuousJobRunner.Actions actualActions = new ContinuousJobRunner.Actions() {
                    @Override public boolean exportOne() {
                        if (mode.equals("daemon") && ready.compareAndSet(false, true)) {
                            if (states.read().status() != RuntimeStateStore.Status.RUNNING) { throw new IllegalStateException("No persisted running journal at readiness"); }
                            atomic(checkpoint, Map.of("phase", "RUNNER_READY", "mode", mode));
                        }
                        return delegated.exportOne();
                    }
                    @Override public boolean publishOne() throws Exception { return delegated.publishOne(); }
                    @Override public boolean receiveOne(Duration timeout) { return delegated.receiveOne(timeout); }
                };
                var runner = new ContinuousJobRunner(states, lease, actualActions, resources, commit, Duration.ofMillis(500), Duration.ofMillis(500));
                var finished = new AtomicBoolean();
                Thread stopWatcher = new Thread(() -> {
                    while (!finished.get()) {
                        if (Files.exists(stop)) { runner.requestStop(); return; }
                        try { Thread.sleep(50); } catch (InterruptedException interrupted) { return; }
                    }
                }, "owned-runtime-test-stop-watcher");
                stopWatcher.setDaemon(true); stopWatcher.start();
                try {
                    RuntimeStateStore.State result = runner.run();
                    if (closed.get() != 7) { throw new IllegalStateException("Runtime did not close all three actual clients"); }
                    atomic(exit, Map.of("resourcesClosed", true, "runtimeStatus", result.status().name()));
                } finally { finished.set(true); stopWatcher.interrupt(); stopWatcher.join(1000); }
            }
        }
    }

    private static Path freshPrivateFile(String value, String name) {
        Path file = Path.of(value).toAbsolutePath().normalize();
        if (!file.getFileName().toString().equals(name) || Files.exists(file) || !Files.isDirectory(file.getParent())) {
            throw new IllegalArgumentException("Requires a fresh file in the owned private temporary directory");
        }
        return file;
    }
    private static void atomic(Path destination, Map<String, Object> fields) {
        Path pending = destination.resolveSibling(destination.getFileName() + ".pending-" + ProcessHandle.current().pid());
        try {
            Files.writeString(pending, JSON.writeValueAsString(new LinkedHashMap<>(fields)) + "\n", StandardCharsets.UTF_8,
                StandardOpenOption.CREATE_NEW, StandardOpenOption.WRITE);
            Files.move(pending, destination, StandardCopyOption.ATOMIC_MOVE);
        } catch (Exception failure) { throw new IllegalStateException("Could not persist the owned atomic runtime checkpoint"); }
    }
}
