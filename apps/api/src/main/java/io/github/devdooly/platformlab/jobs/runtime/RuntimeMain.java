package io.github.devdooly.platformlab.jobs.runtime;

import io.github.devdooly.platformlab.PlatformLabApplication;
import io.github.devdooly.platformlab.jobs.LabJobService;
import io.github.devdooly.platformlab.jobs.S3ClientFactory;
import io.github.devdooly.platformlab.jobs.S3RawSourceStore;
import io.github.devdooly.platformlab.jobs.SourceStagingService;
import io.github.devdooly.platformlab.jobs.exporting.ResultExportService;
import io.github.devdooly.platformlab.jobs.exporting.S3ResultExportStore;
import io.github.devdooly.platformlab.jobs.messaging.DispatchPublisher;
import io.github.devdooly.platformlab.jobs.messaging.DispatchWorker;
import io.github.devdooly.platformlab.jobs.messaging.KafkaClientFactory;
import java.net.URI;
import java.time.Clock;
import java.time.Duration;
import java.util.ArrayList;
import java.util.Map;
import org.apache.kafka.clients.producer.Producer;
import org.apache.kafka.clients.consumer.Consumer;
import software.amazon.awssdk.services.s3.S3Client;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import javax.sql.DataSource;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.WebApplicationType;
import org.springframework.core.env.MapPropertySource;
import org.springframework.jdbc.core.JdbcTemplate;
import software.amazon.awssdk.auth.credentials.AwsBasicCredentials;
import software.amazon.awssdk.auth.credentials.StaticCredentialsProvider;

/** Explicit console mode. Default API startup creates no clients, owner lock, runner, or scheduler. */
public final class RuntimeMain {
    private RuntimeMain() {}
    public static boolean isRuntimeCommand(String[] args) {
        for (String arg : args) { if (arg.startsWith("--lab-runtime")) { return true; } }
        return false;
    }

    public static void run(String[] args) {
        if (args.length != 1 || (!args[0].equals("--lab-runtime=run") && !args[0].equals("--lab-runtime=resume") && !args[0].equals("--lab-runtime=stage"))) {
            throw new IllegalArgumentException("Use only --lab-runtime=run, --lab-runtime=resume or --lab-runtime=stage; connection settings belong in environment variables");
        }
        boolean resume = args[0].equals("--lab-runtime=resume");
        var application = new SpringApplication(PlatformLabApplication.class);
        application.setWebApplicationType(WebApplicationType.NONE);
        application.setAdditionalProfiles("worker");
        application.setRegisterShutdownHook(false);
        application.addInitializers(context -> context.getEnvironment().getPropertySources().addFirst(
            new MapPropertySource("explicit-runtime-safety", Map.of(
                "spring.flyway.enabled", false, "spring.main.web-application-type", "none",
                "spring.sql.init.mode", "never", "spring.jpa.hibernate.ddl-auto", "validate"))));
        try (var context = application.run()) {
            var states = new RuntimeStateStore(context.getBean(JdbcTemplate.class), context.getBean(Clock.class));
            states.requireSchemaV4();
            if (args[0].equals("--lab-runtime=stage")) {
                if (states.read().status() == RuntimeStateStore.Status.PAUSED_OPERATOR) {
                    throw new RuntimeStateStore.OperatorResumeRequiredException();
                }
                stageFixture(states, context.getBean(LabJobService.class)); return;
            }
            var dataSource = context.getBean(DataSource.class);
            try (var lease = MariaDbRuntimeLease.acquire(dataSource)) {
                if (resume) {
                    states.resume(lease); System.out.println("RUNTIME_OPERATOR_RESUME_RECORDED"); return;
                }
                if (states.read().status() == RuntimeStateStore.Status.PAUSED_OPERATOR) {
                    throw new RuntimeStateStore.OperatorResumeRequiredException();
                }
                runOwned(states, lease, context.getBean(LabJobService.class));
            }
        } catch (RuntimeStateStore.OperatorResumeRequiredException | RuntimeLease.LeaseUnavailableException | LabJobService.AdmissionCooldownException rejected) {
            throw rejected;
        } catch (RuntimeException failure) {
            // Private connection values and credentials must not be added to console diagnostics.
            throw new IllegalStateException("Explicit runtime command failed; inspect the private host diagnostics");
        }
    }

    private static void stageFixture(RuntimeStateStore states, LabJobService jobs) {
        String runId = required("LAB_RUNTIME_STAGE_RUN_ID"); FixedFixtureStager.validateRunId(runId);
        String scenarioVersion = FixedFixtureStager.scenarioFromSetting(System.getenv("LAB_RUNTIME_STAGE_SCENARIO"));
        URI endpoint = URI.create(required("LAB_RUNTIME_S3_ENDPOINT"));
        String region = required("LAB_RUNTIME_S3_REGION"), bucket = required("LAB_RUNTIME_S3_BUCKET");
        var credentials = StaticCredentialsProvider.create(AwsBasicCredentials.create(
            required("LAB_RUNTIME_S3_ACCESS_KEY_ID"), required("LAB_RUNTIME_S3_SECRET_ACCESS_KEY")));
        // Staging uses only DB admission and raw-object credentials. It neither acquires the runtime lock
        // nor creates Kafka/export clients, so an already-running worker may process the admitted job.
        try (var s3 = S3ClientFactory.createGarage(endpoint, region, credentials)) {
            var stager = new FixedFixtureStager(states, new SourceStagingService(jobs, new S3RawSourceStore(s3, bucket)));
            var job = stager.stage(runId, scenarioVersion);
            System.out.println("RUNTIME_FIXTURE_STAGED " + job.runId() + " " + job.status().name() + " INPUTS_"
                + io.github.devdooly.platformlab.demo.SyntheticScenario.expectedCounts(scenarioVersion).input());
        }
    }

    private static void runOwned(RuntimeStateStore states, RuntimeLease lease, LabJobService jobs) {
        String sourceCommit = System.getenv().getOrDefault("SOURCE_COMMIT", "unknown");
        RuntimeStateStore.validateCommit(sourceCommit);
        String bootstrap = required("LAB_RUNTIME_KAFKA_BOOTSTRAP");
        String topic = required("LAB_RUNTIME_KAFKA_TOPIC");
        String group = required("LAB_RUNTIME_KAFKA_GROUP");
        String bucket = required("LAB_RUNTIME_S3_BUCKET");
        URI endpoint = URI.create(required("LAB_RUNTIME_S3_ENDPOINT"));
        String region = required("LAB_RUNTIME_S3_REGION");
        var credentials = StaticCredentialsProvider.create(AwsBasicCredentials.create(
            required("LAB_RUNTIME_S3_ACCESS_KEY_ID"), required("LAB_RUNTIME_S3_SECRET_ACCESS_KEY")));
        // Client construction and close occur on the same owning thread as all worker actions.
        try (var progress = LocalRuntimeProgress.fromEnvironment(sourceCommit)) {
            progress.starting();
            try (var clients = openClients(endpoint, region, credentials, bootstrap, group)) {
            var actions = new JobRuntimeActions(jobs, new DispatchPublisher(jobs, clients.producer(), topic),
                new DispatchWorker(jobs, new S3RawSourceStore(clients.s3(), bucket), clients.consumer(), topic),
                new ResultExportService(jobs, new S3ResultExportStore(clients.s3(), bucket)));
            var resources = clients.resources();
            var runner = new ContinuousJobRunner(states, lease, actions, resources, sourceCommit,
                Duration.ofMillis(500), Duration.ofMillis(500), progress);
            var closed = new CountDownLatch(1);
            var hook = new Thread(() -> {
                runner.requestStop();
                try { closed.await(240, TimeUnit.SECONDS); }
                catch (InterruptedException failure) { Thread.currentThread().interrupt(); }
            }, "lab-runtime-stop-request");
            Runtime.getRuntime().addShutdownHook(hook);
            try {
                var result = runner.run();
                System.out.println("RUNTIME_EXIT " + result.status().name() + " " + result.stage().name()
                    + " " + (result.failureCode() == null ? "NONE" : result.failureCode().name()));
                if (result.status() == RuntimeStateStore.Status.PAUSED_OPERATOR) {
                    throw new RuntimeStateStore.OperatorResumeRequiredException();
                }
            } finally {
                closed.countDown();
                try { Runtime.getRuntime().removeShutdownHook(hook); }
                catch (IllegalStateException shutdownAlreadyRunning) { /* The registered hook is already waiting for completion. */ }
            }
            }
        }
    }

    private record Clients(S3Client s3, Producer<String, String> producer, Consumer<String, String> consumer,
                           RuntimeResources resources) implements AutoCloseable {
        @Override public void close() { closeResources(resources); }
    }

    private static Clients openClients(URI endpoint, String region, StaticCredentialsProvider credentials,
                                       String bootstrap, String group) {
        var partial = new ArrayList<AutoCloseable>();
        try {
            var s3 = S3ClientFactory.createGarage(endpoint, region, credentials); partial.add(s3);
            var producer = KafkaClientFactory.producer(bootstrap); partial.add(() -> producer.close(Duration.ofSeconds(10)));
            var consumer = KafkaClientFactory.consumerForRuntime(bootstrap, group); partial.add(() -> consumer.close(Duration.ofSeconds(10)));
            return new Clients(s3, producer, consumer, new RuntimeResources(
                () -> consumer.close(Duration.ofSeconds(10)), () -> producer.close(Duration.ofSeconds(10)), s3::close));
        } catch (RuntimeException failure) {
            java.util.Collections.reverse(partial);
            closeResources(new RuntimeResources(partial.toArray(AutoCloseable[]::new)));
            throw new IllegalStateException("Runtime clients could not be constructed");
        }
    }

    private static void closeResources(RuntimeResources resources) {
        try { resources.close(); }
        catch (Exception failure) { throw new IllegalStateException("Runtime resources could not be closed"); }
    }

    private static String required(String name) {
        String value = System.getenv(name);
        if (value == null || value.isBlank()) { throw new IllegalArgumentException("Missing required runtime setting: " + name); }
        return value;
    }
}
