package io.github.devdooly.platformlab.jobs;

import io.github.devdooly.platformlab.demo.DemoService;
import io.github.devdooly.platformlab.demo.SyntheticScenario;
import io.github.devdooly.platformlab.jobs.exporting.ResultExportService;
import io.github.devdooly.platformlab.jobs.exporting.S3ResultExportStore;
import java.net.URI;
import java.nio.file.Files;
import java.nio.file.Path;
import java.sql.Connection;
import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Set;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;
import org.junit.jupiter.api.AfterAll;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.TestInstance;
import org.junit.jupiter.api.condition.EnabledIfSystemProperty;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.DataSourceTransactionManager;
import org.springframework.jdbc.datasource.SingleConnectionDataSource;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.springframework.transaction.support.TransactionTemplate;
import software.amazon.awssdk.auth.credentials.AwsBasicCredentials;
import software.amazon.awssdk.auth.credentials.StaticCredentialsProvider;
import software.amazon.awssdk.services.s3.S3Client;
import software.amazon.awssdk.services.s3.model.DeleteObjectRequest;
import software.amazon.awssdk.services.s3.model.GetObjectRequest;
import software.amazon.awssdk.services.s3.model.ListObjectsV2Request;
import static org.assertj.core.api.Assertions.*;

/** Explicit opt-in real MariaDB/Garage contract, not an HTTP or production capacity test.
 * -Dlab.admission.tests=true -Dtest=AdmissionCooldownIT; fresh platform_lab_admission_it only.
 */
@SpringBootTest
@ActiveProfiles({"db-test", "worker"})
@EnabledIfSystemProperty(named = "lab.admission.tests", matches = "true")
@TestInstance(TestInstance.Lifecycle.PER_CLASS)
public class AdmissionCooldownIT extends AdmissionCooldownContractTests {
    private S3Client s3;
    private S3RawSourceStore raw;
    private String bucket;
    private final Set<String> keys = new LinkedHashSet<>();

    @DynamicPropertySource static void requireIsolatedDatabaseBeforeFlyway(DynamicPropertyRegistry registry) {
        registry.add("spring.datasource.url", AdmissionRestartProbe::guardedUrl);
        registry.add("spring.datasource.username", () -> AdmissionRestartProbe.required("DB_TEST_USERNAME"));
        registry.add("spring.datasource.password", () -> AdmissionRestartProbe.required("DB_TEST_PASSWORD"));
    }
    @BeforeAll void requireActualDisposableServices() throws Exception {
        try (var connection = dataSource.getConnection()) {
            assertThat(connection.getMetaData().getDatabaseProductName()).isEqualTo("MariaDB");
            assertThat(connection.getCatalog()).isEqualTo("platform_lab_admission_it");
        }
        assertThat(jdbc.queryForObject("SELECT COUNT(*) FROM lab_job", Long.class)).isZero();
        assertThat(jdbc.queryForObject("SELECT COUNT(*) FROM information_schema.TRIGGERS WHERE TRIGGER_SCHEMA=DATABASE()", Long.class)).isZero();
        for (String version : List.of("1", "2", "3", "4")) {
            assertThat(jdbc.queryForObject("SELECT COUNT(*) FROM flyway_schema_history WHERE version=? AND success=1", Integer.class, version)).isEqualTo(1);
        }
        String endpoint = AdmissionRestartProbe.required("LAB_S3_TEST_ENDPOINT");
        if (!endpoint.matches("http://127\\.0\\.0\\.1:[0-9]{1,5}/?")) { throw new IllegalArgumentException("Numeric loopback Garage is required"); }
        URI uri = URI.create(endpoint);
        if (uri.getPort() < 1 || uri.getPort() > 65535) { throw new IllegalArgumentException("Invalid Garage port"); }
        bucket = AdmissionRestartProbe.required("LAB_S3_TEST_BUCKET");
        if (!bucket.matches("platform-lab-s3-test-[a-z0-9-]{1,42}")) { throw new IllegalArgumentException("Dedicated synthetic bucket is required"); }
        s3 = S3ClientFactory.createGarage(uri, "garage", StaticCredentialsProvider.create(AwsBasicCredentials.create(
            AdmissionRestartProbe.required("LAB_S3_TEST_ACCESS_KEY"), AdmissionRestartProbe.required("LAB_S3_TEST_SECRET_KEY"))));
        raw = new S3RawSourceStore(s3, bucket);
    }

    @Test void realObjectsHaveOneWinnerAndFreeSlotCooldownLosersHaveZeroRawObjectsOrOutbox() throws Exception {
        var calls = new AtomicInteger();
        var staging = new SourceStagingService(jobs, (job, source) -> {
            keys.add(job.sourceObjectKey()); calls.incrementAndGet(); raw.storeAndVerify(job, source);
        });
        var results = together(8, index -> staging.stage(runs.get(index), SyntheticScenario.NAME, bytes));
        var winner = results.stream().filter(LabJobService.Job.class::isInstance).map(LabJobService.Job.class::cast).findFirst().orElseThrow();
        assertThat(results.stream().filter(LabJobService.SlotBusyException.class::isInstance)).hasSize(7);
        assertThat(calls.get()).isEqualTo(1);
        assertThat(s3.getObjectAsBytes(GetObjectRequest.builder().bucket(bucket).key(winner.sourceObjectKey()).build()).asByteArray()).isEqualTo(bytes);
        for (String run : runs) { if (!run.equals(winner.runId())) { assertNoRows(run); assertThat(rawKeys(run)).isEmpty(); } }
        jobs.process(winner.runId(), winner.sourceSha256());
        var bundle = io.github.devdooly.platformlab.jobs.exporting.ExportBundle.from(jobs.exportSnapshot(winner.runId(), winner.sourceSha256()));
        keys.add(bundle.result().key()); keys.add(bundle.failures().key());
        new ResultExportService(jobs, new S3ResultExportStore(s3, bucket)).export(winner.runId(), winner.sourceSha256());
        String rejected = own(NEXT); var before = snapshot();
        assertThatThrownBy(() -> staging.stage(rejected, SyntheticScenario.NAME, bytes)).isInstanceOf(LabJobService.AdmissionCooldownException.class);
        assertThat(rawKeys(rejected)).isEmpty(); assertNoRows(rejected); assertThat(snapshot()).isEqualTo(before); assertThat(calls.get()).isEqualTo(1);
        assertThat(rawKeys(winner.runId())).containsExactly(winner.sourceObjectKey());
    }

    @Test void exactMicrosecondBeforeAtAndAfterDeadlineUseMariaDbSessionClockOnly() throws Exception {
        try (Connection connection = dataSource.getConnection()) {
            var one = new SingleConnectionDataSource(connection, true); var sql = new JdbcTemplate(one);
            var isolated = new LabJobService(sql, new DataSourceTransactionManager(one), new DemoService(null, null, Clock.systemUTC()),
                Clock.fixed(Instant.parse("2040-01-01T00:00:00Z"), java.time.ZoneOffset.UTC));
            try {
                sql.update("UPDATE lab_admission_policy SET last_admitted_at=FROM_UNIXTIME(1760000000.123456-30),next_admission_at=FROM_UNIXTIME(1760000000.123456) WHERE id=1");
                sql.execute("SET timestamp=1760000000.123455");
                assertThat(sql.queryForObject("SELECT UNIX_TIMESTAMP(CURRENT_TIMESTAMP(6))", java.math.BigDecimal.class)).isEqualByComparingTo("1760000000.123455");
                assertThatThrownBy(() -> isolated.prepareSource(own(FIRST), SyntheticScenario.NAME, bytes)).isInstanceOf(LabJobService.AdmissionCooldownException.class);
                sql.execute("SET timestamp=1760000000.123456");
                var admitted = isolated.prepareSource(FIRST, SyntheticScenario.NAME, bytes);
                assertThat(sql.queryForObject("SELECT UNIX_TIMESTAMP(last_admitted_at) FROM lab_admission_policy WHERE id=1", java.math.BigDecimal.class)).isEqualByComparingTo("1760000000.123456");
                isolated.terminate(FIRST, admitted.sourceSha256());
                sql.execute("SET timestamp=1760000030.123457");
                assertThat(isolated.prepareSource(own(NEXT), SyntheticScenario.NAME, bytes).status()).isEqualTo(LabJobService.Status.STAGING);
                assertThat(sql.queryForObject("SELECT UNIX_TIMESTAMP(last_admitted_at) FROM lab_admission_policy WHERE id=1", java.math.BigDecimal.class)).isEqualByComparingTo("1760000030.123457");
            } finally { sql.execute("SET timestamp=DEFAULT"); }
        }
    }

    @Test void contenderWaitingForSlotEvaluatesFreshDatabaseClockAfterLockRelease() throws Exception {
        jdbc.update("UPDATE lab_admission_policy SET last_admitted_at=TIMESTAMPADD(SECOND,-28,CURRENT_TIMESTAMP(6)),next_admission_at=TIMESTAMPADD(SECOND,2,CURRENT_TIMESTAMP(6)) WHERE id=1");
        var locked = new CountDownLatch(1); var release = new CountDownLatch(1); var attempted = new CountDownLatch(1);
        own(FIRST);
        try (var pool = Executors.newFixedThreadPool(2)) {
            var holder = pool.submit(() -> new TransactionTemplate(manager).executeWithoutResult(ignored -> {
                jdbc.queryForObject("SELECT id FROM lab_job_slot WHERE id=1 FOR UPDATE", Integer.class); locked.countDown();
                try { if (!release.await(10, TimeUnit.SECONDS)) { throw new IllegalStateException("Test lock timed out"); } }
                catch (InterruptedException failure) { Thread.currentThread().interrupt(); throw new IllegalStateException("Test interrupted"); }
            }));
            assertThat(locked.await(5, TimeUnit.SECONDS)).isTrue();
            assertThat(jdbc.queryForObject("SELECT CASE WHEN CURRENT_TIMESTAMP(6)<next_admission_at THEN 1 ELSE 0 END FROM lab_admission_policy WHERE id=1", Integer.class)).isEqualTo(1);
            var contender = pool.submit(() -> { attempted.countDown(); return jobs.prepareSource(FIRST, SyntheticScenario.NAME, bytes); });
            assertThat(attempted.await(5, TimeUnit.SECONDS)).isTrue(); assertThat(contender.isDone()).isFalse();
            long deadline = System.nanoTime() + Duration.ofSeconds(6).toNanos();
            try {
                while (jdbc.queryForObject("SELECT CASE WHEN CURRENT_TIMESTAMP(6)>next_admission_at THEN 1 ELSE 0 END FROM lab_admission_policy WHERE id=1", Integer.class) != 1) {
                    assertThat(System.nanoTime()).isLessThan(deadline); Thread.sleep(20);
                }
            } finally { release.countDown(); }
            holder.get(5, TimeUnit.SECONDS);
            assertThat(contender.get(5, TimeUnit.SECONDS).status()).isEqualTo(LabJobService.Status.STAGING);
        } finally { release.countDown(); }
    }

    @Test void aFreshJvmRejectsFromPersistedCooldownWithoutCallingStorage() throws Exception {
        var first = jobs.prepareSource(own(FIRST), SyntheticScenario.NAME, bytes); jobs.terminate(FIRST, first.sourceSha256());
        var before = snapshot(); own(NEXT);
        Path directory = Files.createTempDirectory("platform-lab-admission-it-"); Path log = directory.resolve("fresh-jvm.log");
        String cp = System.getProperty("surefire.test.class.path", System.getProperty("java.class.path"));
        var process = new ProcessBuilder(Path.of(System.getProperty("java.home"), "bin", "java").toString(), "-Duser.timezone=Asia/Seoul", "-cp", cp, AdmissionRestartProbe.class.getName(), NEXT)
            .redirectErrorStream(true).redirectOutput(log.toFile()).start();
        try {
            assertThat(process.waitFor(15, TimeUnit.SECONDS)).isTrue(); assertThat(process.exitValue()).isZero();
            assertThat(Files.readString(log)).contains("ADMISSION_COOLDOWN NO_STORAGE_CALLS").doesNotContain("UNEXPECTED_ADMISSION", "PROBE_FAILED");
            assertThat(snapshot()).isEqualTo(before); assertNoRows(NEXT); assertThat(rawKeys(NEXT)).isEmpty();
        } finally {
            if (process.isAlive()) { process.destroy(); if (!process.waitFor(5, TimeUnit.SECONDS)) { preserveFailure = true; } }
        }
    }

    private List<String> rawKeys(String run) {
        return s3.listObjectsV2(ListObjectsV2Request.builder().bucket(bucket).prefix("raw/" + run + "/").maxKeys(2).build())
            .contents().stream().map(value -> value.key()).toList();
    }
    @AfterEach void removeOnlyOwnedActualObjectsAfterPassingCase() {
        if (preserveFailure || s3 == null) { return; }
        for (String key : keys) { s3.deleteObject(DeleteObjectRequest.builder().bucket(bucket).key(key).build()); }
        keys.clear();
    }
    @AfterAll void closeActualObjectClient() { if (s3 != null) { s3.close(); } }
}
