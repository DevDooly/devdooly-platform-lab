package io.github.devdooly.platformlab.jobs;

import io.github.devdooly.platformlab.demo.SyntheticScenario;
import java.net.URI;
import java.util.HashSet;
import java.util.Set;
import java.util.UUID;
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
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.support.TransactionTemplate;
import software.amazon.awssdk.auth.credentials.AwsBasicCredentials;
import software.amazon.awssdk.auth.credentials.StaticCredentialsProvider;
import software.amazon.awssdk.core.sync.RequestBody;
import software.amazon.awssdk.services.s3.S3Client;
import software.amazon.awssdk.services.s3.model.DeleteObjectRequest;
import software.amazon.awssdk.services.s3.model.GetObjectRequest;
import software.amazon.awssdk.services.s3.model.HeadObjectRequest;
import software.amazon.awssdk.services.s3.model.ListObjectsV2Request;
import software.amazon.awssdk.services.s3.model.PutObjectRequest;
import static org.assertj.core.api.Assertions.*;
import static org.mockito.ArgumentMatchers.*;
import static org.mockito.Mockito.*;

/**
 * Explicit opt-in only against an already-created disposable Garage bucket on numeric loopback.
 * Run with -Dlab.s3.tests=true -Dtest=GarageRawSourceIT; default verify does not select *IT.
 * No production DB/bucket, bucket creation/deletion, list-all cleanup, or response checksum override; request compatibility is selected explicitly.
 */
@SpringBootTest(properties = "spring.datasource.url=jdbc:h2:mem:garage_raw_source_it;MODE=MariaDB;DATABASE_TO_LOWER=TRUE;DB_CLOSE_DELAY=-1")
@ActiveProfiles("test")
@EnabledIfSystemProperty(named = "lab.s3.tests", matches = "true")
@TestInstance(TestInstance.Lifecycle.PER_CLASS)
class GarageRawSourceIT {
    @Autowired LabJobService jobs;
    @Autowired JdbcTemplate jdbc;
    @Autowired PlatformTransactionManager transactionManager;
    private S3Client s3;
    private S3RawSourceStore store;
    private String bucket;
    private String runId;
    private final Set<String> ownedKeys = new HashSet<>();
    private final byte[] bytes = CanonicalSource.fixtureBytes();

    @BeforeAll void requireExplicitDisposableEnvironment() {
        String endpoint = required("LAB_S3_TEST_ENDPOINT");
        if (!endpoint.matches("http://127\\.0\\.0\\.1:[0-9]{1,5}/?")) {
            throw new IllegalArgumentException("LAB_S3_TEST_ENDPOINT must be http://127.0.0.1:<port>");
        }
        var endpointUri = URI.create(endpoint);
        if (endpointUri.getPort() < 1 || endpointUri.getPort() > 65535) {
            throw new IllegalArgumentException("Invalid disposable Garage port");
        }
        bucket = required("LAB_S3_TEST_BUCKET");
        if (!bucket.matches("platform-lab-s3-test-[a-z0-9-]{1,42}")) {
            throw new IllegalArgumentException("LAB_S3_TEST_BUCKET must use the dedicated platform-lab-s3-test- prefix");
        }
        s3 = S3ClientFactory.createGarage(endpointUri, "garage", StaticCredentialsProvider.create(
            AwsBasicCredentials.create(required("LAB_S3_TEST_ACCESS_KEY"), required("LAB_S3_TEST_SECRET_KEY"))));
        store = new S3RawSourceStore(s3, bucket);
    }

    @BeforeEach void ownUniqueRunPrefix() { runId = "s3-it-" + UUID.randomUUID(); }

    @Test void realSdkPutGetHeadListDeleteAndStoreRetryVerifyActualBytes() {
        var job = jobs.prepareSource(runId, SyntheticScenario.NAME, bytes);
        String key = own(job.sourceObjectKey());
        store.storeAndVerify(job, bytes);
        assertRemoteExact(job);
        assertThat(s3.headObject(HeadObjectRequest.builder().bucket(bucket).key(key).build()).contentLength())
            .isEqualTo((long) bytes.length);
        assertThat(s3.listObjectsV2(ListObjectsV2Request.builder().bucket(bucket).prefix("raw/" + runId + "/").build()).contents())
            .extracting(value -> value.key()).containsExactly(key);
        store.storeAndVerify(job, bytes);
        assertRemoteExact(job);
        s3.deleteObject(DeleteObjectRequest.builder().bucket(bucket).key(key).build());
        assertThat(s3.listObjectsV2(ListObjectsV2Request.builder().bucket(bucket).prefix("raw/" + runId + "/").build()).contents())
            .isEmpty();
    }

    @Test void realCoordinatorStagesAndRepeatPreservesQueuedAndCompletedMetadata() {
        var stage = new SourceStagingService(jobs, store);
        own("raw/" + runId + "/" + CanonicalSource.validate(bytes).sha256() + ".ndjson");
        var queued = stage.stage(runId, SyntheticScenario.NAME, bytes);
        assertThat(queued.status()).isEqualTo(LabJobService.Status.QUEUED);
        assertRemoteExact(queued);
        var dispatch = jdbc.queryForList("SELECT * FROM lab_outbox WHERE job_run_id = ? ORDER BY id", runId);
        assertThat(dispatch).hasSize(1);
        assertThat(stage.stage(runId, SyntheticScenario.NAME, bytes)).isEqualTo(queued);
        assertThat(jdbc.queryForList("SELECT * FROM lab_outbox WHERE job_run_id = ? ORDER BY id", runId)).isEqualTo(dispatch);
        var completed = jobs.process(runId, queued.sourceSha256());
        var all = jdbc.queryForList("SELECT * FROM lab_outbox WHERE job_run_id = ? ORDER BY id", runId);
        assertThat(stage.stage(runId, SyntheticScenario.NAME, bytes)).isEqualTo(completed);
        assertRemoteExact(completed);
        assertThat(jdbc.queryForList("SELECT * FROM lab_outbox WHERE job_run_id = ? ORDER BY id", runId)).isEqualTo(all);
    }

    @Test void realExistingCorruptionIsRetainedAndDbRemainsStagingWithoutDispatch() {
        var job = jobs.prepareSource(runId, SyntheticScenario.NAME, bytes);
        var corrupt = bytes.clone(); corrupt[1] ^= 1;
        var key = own(job.sourceObjectKey());
        s3.putObject(PutObjectRequest.builder().bucket(bucket).key(key).build(), RequestBody.fromBytes(corrupt));
        var stage = new SourceStagingService(jobs, store);
        assertThatThrownBy(() -> stage.stage(runId, SyntheticScenario.NAME, bytes))
            .isInstanceOf(S3RawSourceStore.SourceVerificationException.class);
        assertThat(s3.getObjectAsBytes(GetObjectRequest.builder().bucket(bucket).key(key).build()).asByteArray()).isEqualTo(corrupt);
        assertThat(jobs.get(runId)).isEqualTo(job);
        assertThat(jobs.pendingOutbox(100)).isEmpty();
        assertThat(jdbc.queryForObject("SELECT occupied_run_id FROM lab_job_slot WHERE id = 1", String.class)).isEqualTo(runId);
        // Only the test explicitly deletes its own deliberately corrupted fixture.
        s3.deleteObject(DeleteObjectRequest.builder().bucket(bucket).key(key).build());
        assertThat(stage.stage(runId, SyntheticScenario.NAME, bytes).status()).isEqualTo(LabJobService.Status.QUEUED);
    }

    @Test void realObjectSurvivesFailedDbMarkAndIsReverifiedOnRetry() {
        var spyJobs = spy(jobs);
        doThrow(new MarkUnavailable()).doCallRealMethod().when(spyJobs).markSourceVerified(eq(runId), anyString());
        var stage = new SourceStagingService(spyJobs, store);
        own("raw/" + runId + "/" + CanonicalSource.validate(bytes).sha256() + ".ndjson");
        assertThatThrownBy(() -> stage.stage(runId, SyntheticScenario.NAME, bytes)).isInstanceOf(MarkUnavailable.class);
        var staging = jobs.get(runId);
        assertThat(staging.status()).isEqualTo(LabJobService.Status.STAGING);
        assertThat(jobs.pendingOutbox(100)).isEmpty();
        assertRemoteExact(staging);
        var queued = stage.stage(runId, SyntheticScenario.NAME, bytes);
        assertThat(queued.createdAt()).isEqualTo(staging.createdAt());
        assertThat(queued.status()).isEqualTo(LabJobService.Status.QUEUED);
        assertRemoteExact(queued);
    }

    @Test
    @EnabledIfSystemProperty(named = "lab.s3.persistence", matches = "before|after")
    void objectPersistsAcrossContainerRecreation() {
        var source = CanonicalSource.validate(bytes);
        var marker = new LabJobService.Job("s3-it-persistence-check", SyntheticScenario.NAME,
            source.sha256(), source.size(), LabJobService.Status.STAGING, LabJobService.ExportStatus.NOT_REQUESTED,
            java.time.Instant.parse("2026-01-01T00:00:00Z"), null, null, null, null, null);
        if ("before".equals(System.getProperty("lab.s3.persistence"))) {
            assertThatThrownBy(() -> s3.getObjectAsBytes(GetObjectRequest.builder()
                .bucket(bucket).key(marker.sourceObjectKey()).build()))
                .isInstanceOfSatisfying(software.amazon.awssdk.services.s3.model.S3Exception.class, failure -> {
                    assertThat(failure.statusCode()).isEqualTo(404);
                    assertThat(failure.awsErrorDetails()).isNotNull();
                    assertThat(failure.awsErrorDetails().errorCode()).isEqualTo("NoSuchKey");
                });
            store.storeAndVerify(marker, bytes);
            assertRemoteExact(marker);
            // Deliberately not registered in ownedKeys: the before phase must retain this marker.
        } else {
            // GET-only validation proves bytes survived independently of another PUT or DB state.
            assertRemoteExact(marker);
            s3.deleteObject(DeleteObjectRequest.builder().bucket(bucket).key(marker.sourceObjectKey()).build());
        }
    }

    @AfterEach void removeOnlyThisTestRunObjectsAndH2Rows() {
        if (s3 != null && runId != null) {
            String prefix = "raw/" + runId + "/";
            for (String key : ownedKeys) {
                if (!key.startsWith(prefix)) { throw new IllegalStateException("Refusing cleanup outside this test run"); }
                s3.deleteObject(DeleteObjectRequest.builder().bucket(bucket).key(key).build());
            }
            assertThat(s3.listObjectsV2(ListObjectsV2Request.builder().bucket(bucket).prefix(prefix).build()).contents()).isEmpty();
            ownedKeys.clear();
        }
        if (runId == null) { return; }
        new TransactionTemplate(transactionManager).executeWithoutResult(ignored -> {
            String occupied = jdbc.queryForObject("SELECT occupied_run_id FROM lab_job_slot WHERE id = 1 FOR UPDATE", String.class);
            if (occupied != null && !runId.equals(occupied)) { throw new IllegalStateException("Unexpected occupied test slot"); }
            if (occupied != null) { jdbc.update("UPDATE lab_job_slot SET occupied_run_id = NULL WHERE id = 1"); }
            jdbc.update("DELETE FROM lab_outbox WHERE job_run_id = ?", runId);
            jdbc.update("DELETE FROM demo_outcome WHERE run_id = ?", runId);
            jdbc.update("DELETE FROM demo_run WHERE id = ?", runId);
            jdbc.update("DELETE FROM lab_job WHERE run_id = ?", runId);
        });
    }

    @AfterAll void closeExplicitClient() { if (s3 != null) { s3.close(); } }

    private void assertRemoteExact(LabJobService.Job job) {
        byte[] actual = s3.getObjectAsBytes(GetObjectRequest.builder().bucket(bucket).key(job.sourceObjectKey()).build()).asByteArray();
        assertThat(actual).isEqualTo(bytes);
        var verified = CanonicalSource.validate(actual);
        assertThat(verified.size()).isEqualTo(job.sourceSize());
        assertThat(verified.sha256()).isEqualTo(job.sourceSha256());
    }
    private String own(String key) { ownedKeys.add(key); return key; }
    private static String required(String name) {
        var value = System.getenv(name);
        if (value == null || value.isBlank()) { throw new IllegalArgumentException(name + " is required for explicit disposable S3 validation"); }
        return value;
    }
    private static class MarkUnavailable extends RuntimeException {}
}
