package io.github.devdooly.platformlab.jobs;

import io.github.devdooly.platformlab.demo.SyntheticScenario;
import java.util.concurrent.atomic.AtomicInteger;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.transaction.IllegalTransactionStateException;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.support.TransactionSynchronizationManager;
import org.springframework.transaction.support.TransactionTemplate;
import static org.assertj.core.api.Assertions.*;
import static org.mockito.ArgumentMatchers.*;
import static org.mockito.Mockito.*;

@SpringBootTest(properties = "spring.datasource.url=jdbc:h2:mem:source_staging_tests;MODE=MariaDB;DATABASE_TO_LOWER=TRUE;DB_CLOSE_DELAY=-1")
@ActiveProfiles("test")
class SourceStagingIntegrationTest {
    private static final String RUN = "staging-integration";
    @Autowired LabJobService jobs;
    @Autowired JdbcTemplate jdbc;
    @Autowired PlatformTransactionManager transactionManager;
    @Autowired ApplicationContext context;
    private final byte[] bytes = CanonicalSource.fixtureBytes();

    @AfterEach void cleanOwnFixtures() {
        new TransactionTemplate(transactionManager).executeWithoutResult(ignored -> {
            var occupied = jdbc.queryForObject("SELECT occupied_run_id FROM lab_job_slot WHERE id = 1 FOR UPDATE", String.class);
            if (occupied != null && !RUN.equals(occupied)) { throw new IllegalStateException("Unexpected occupied test slot"); }
            jdbc.update("UPDATE lab_job_slot SET occupied_run_id = NULL WHERE id = 1");
            jdbc.update("DELETE FROM lab_outbox WHERE job_run_id = ?", RUN);
            jdbc.update("DELETE FROM demo_outcome WHERE run_id = ?", RUN);
            jdbc.update("DELETE FROM demo_run WHERE id = ?", RUN);
            jdbc.update("DELETE FROM lab_job WHERE run_id = ?", RUN);
        });
    }

    @Test void storageFailureKeepsCommittedStagingSlotAndNoDispatch() {
        var calls = new AtomicInteger();
        var stage = new SourceStagingService(jobs, (job, source) -> {
            calls.incrementAndGet();
            assertThat(TransactionSynchronizationManager.isActualTransactionActive()).isFalse();
            assertThat(jobs.get(RUN)).isEqualTo(job);
            throw new StorageUnavailable();
        });
        assertThatThrownBy(() -> stage.stage(RUN, SyntheticScenario.NAME, bytes)).isInstanceOf(StorageUnavailable.class);
        assertStagingWithoutDispatch(); assertThat(calls.get()).isEqualTo(1);
    }

    @Test void successfulRetryPreservesCreationAndQueuedRepeatPreservesVerificationAndOutbox() {
        var failFirst = new AtomicInteger();
        var stage = new SourceStagingService(jobs, (job, source) -> {
            assertThat(TransactionSynchronizationManager.isActualTransactionActive()).isFalse();
            assertThat(source).isEqualTo(bytes);
            if (failFirst.getAndIncrement() == 0) { throw new StorageUnavailable(); }
        });
        assertThatThrownBy(() -> stage.stage(RUN, SyntheticScenario.NAME, bytes)).isInstanceOf(StorageUnavailable.class);
        var prepared = jobs.get(RUN);
        var queued = stage.stage(RUN, SyntheticScenario.NAME, bytes);
        assertThat(queued.createdAt()).isEqualTo(prepared.createdAt());
        assertThat(queued.status()).isEqualTo(LabJobService.Status.QUEUED);
        var outbox = jdbc.queryForList("SELECT * FROM lab_outbox WHERE job_run_id = ?", RUN);
        assertThat(outbox).hasSize(1);
        assertThat(stage.stage(RUN, SyntheticScenario.NAME, bytes)).isEqualTo(queued);
        assertThat(jdbc.queryForList("SELECT * FROM lab_outbox WHERE job_run_id = ?", RUN)).isEqualTo(outbox);
        assertThat(failFirst.get()).isEqualTo(3);
    }

    @Test void completedRepeatStillVerifiesObjectAndLeavesAllDbTimesAndOutboxUnchanged() {
        var calls = new AtomicInteger();
        var stage = new SourceStagingService(jobs, (job, source) -> calls.incrementAndGet());
        var queued = stage.stage(RUN, SyntheticScenario.NAME, bytes);
        var completed = jobs.process(RUN, queued.sourceSha256());
        var before = jdbc.queryForList("SELECT * FROM lab_outbox WHERE job_run_id = ? ORDER BY id", RUN);
        assertThat(stage.stage(RUN, SyntheticScenario.NAME, bytes)).isEqualTo(completed);
        assertThat(jdbc.queryForList("SELECT * FROM lab_outbox WHERE job_run_id = ? ORDER BY id", RUN)).isEqualTo(before);
        assertThat(calls.get()).isEqualTo(2);
    }

    @Test void failedDbMarkAfterExternalVerificationCanRetryWithoutDiscardingBytes() {
        var spyJobs = spy(jobs);
        doThrow(new MarkUnavailable()).doCallRealMethod().when(spyJobs).markSourceVerified(eq(RUN), anyString());
        var storedBytes = new java.util.HashMap<String, byte[]>();
        var writes = new AtomicInteger();
        var stage = new SourceStagingService(spyJobs, (job, source) -> {
            if (!storedBytes.containsKey(job.sourceObjectKey())) {
                storedBytes.put(job.sourceObjectKey(), source.clone()); writes.incrementAndGet();
            }
            assertThat(storedBytes.get(job.sourceObjectKey())).isEqualTo(source);
        });
        assertThatThrownBy(() -> stage.stage(RUN, SyntheticScenario.NAME, bytes)).isInstanceOf(MarkUnavailable.class);
        assertStagingWithoutDispatch();
        assertThat(storedBytes).hasSize(1);
        assertThat(stage.stage(RUN, SyntheticScenario.NAME, bytes).status()).isEqualTo(LabJobService.Status.QUEUED);
        assertThat(writes.get()).isEqualTo(1);
    }

    @Test void outerTransactionIsRefusedBeforeDbOrStorage() {
        var sources = mock(RawSourceStore.class); var stage = new SourceStagingService(jobs, sources);
        assertThatThrownBy(() -> new TransactionTemplate(transactionManager).execute(ignored ->
            stage.stage(RUN, SyntheticScenario.NAME, bytes))).isInstanceOf(IllegalTransactionStateException.class);
        assertEmpty(); verifyNoInteractions(sources);
    }

    @Test void invalidSourceRunOrScenarioNeverReservesDbOrCallsStorage() {
        var sources = mock(RawSourceStore.class); var stage = new SourceStagingService(jobs, sources);
        for (byte[] bad : java.util.List.of(new byte[0], new byte[CanonicalSource.MAX_BYTES + 1], new byte[] {0})) {
            assertThatThrownBy(() -> stage.stage(RUN, SyntheticScenario.NAME, bad)).isInstanceOf(IllegalArgumentException.class);
        }
        assertThatThrownBy(() -> stage.stage("../escape", SyntheticScenario.NAME, bytes)).isInstanceOf(IllegalArgumentException.class);
        assertThatThrownBy(() -> stage.stage(RUN, "other", bytes)).isInstanceOf(IllegalArgumentException.class);
        assertEmpty(); verifyNoInteractions(sources);
    }

    @Test void terminatedStagingAndCompletedJobsAreRefusedBeforeNetwork() {
        var prepared = jobs.prepareSource(RUN, SyntheticScenario.NAME, bytes);
        jobs.terminate(RUN, prepared.sourceSha256());
        var sources = mock(RawSourceStore.class); var stage = new SourceStagingService(jobs, sources);
        assertThatThrownBy(() -> stage.stage(RUN, SyntheticScenario.NAME, bytes)).isInstanceOf(LabJobService.JobStateException.class);
        verifyNoInteractions(sources);
        cleanOwnFixtures();
        prepared = jobs.prepareSource(RUN, SyntheticScenario.NAME, bytes);
        jobs.markSourceVerified(RUN, prepared.sourceSha256()); jobs.process(RUN, prepared.sourceSha256());
        jobs.terminate(RUN, prepared.sourceSha256());
        assertThatThrownBy(() -> stage.stage(RUN, SyntheticScenario.NAME, bytes)).isInstanceOf(LabJobService.JobStateException.class);
        verifyNoInteractions(sources);
    }

    @Test void invalidSourceDoesNotInvokeEitherDbServiceOrStorageBoundary() {
        var mockJobs = mock(LabJobService.class);
        var sources = mock(RawSourceStore.class);
        var stage = new SourceStagingService(mockJobs, sources);
        for (byte[] bad : java.util.List.of(new byte[0], new byte[CanonicalSource.MAX_BYTES + 1], new byte[] {0})) {
            assertThatThrownBy(() -> stage.stage(RUN, SyntheticScenario.NAME, bad)).isInstanceOf(IllegalArgumentException.class);
        }
        verifyNoInteractions(mockJobs, sources);
    }

    @Test void baselineApplicationDoesNotCreateAnyStorageClientOrCoordinatorBean() {
        assertThat(context.getBeansOfType(software.amazon.awssdk.services.s3.S3Client.class)).isEmpty();
        assertThat(context.getBeansOfType(RawSourceStore.class)).isEmpty();
        assertThat(context.getBeansOfType(SourceStagingService.class)).isEmpty();
        assertThat(context.getBeansOfType(VerifiedSourceReader.class)).isEmpty();
        assertThat(context.getBeansOfType(io.github.devdooly.platformlab.jobs.exporting.ResultExportStore.class)).isEmpty();
        assertThat(context.getBeansOfType(io.github.devdooly.platformlab.jobs.exporting.ResultExportService.class)).isEmpty();
        assertThat(context.getBeansOfType(org.apache.kafka.clients.producer.Producer.class)).isEmpty();
        assertThat(context.getBeansOfType(org.apache.kafka.clients.consumer.Consumer.class)).isEmpty();
        assertThat(context.getBeansOfType(io.github.devdooly.platformlab.jobs.messaging.DispatchPublisher.class)).isEmpty();
        assertThat(context.getBeansOfType(io.github.devdooly.platformlab.jobs.messaging.DispatchWorker.class)).isEmpty();
    }

    private void assertStagingWithoutDispatch() {
        var job = jobs.get(RUN);
        assertThat(job.status()).isEqualTo(LabJobService.Status.STAGING);
        assertThat(job.sourceVerifiedAt()).isNull(); assertThat(job.queuedAt()).isNull();
        assertThat(jdbc.queryForObject("SELECT occupied_run_id FROM lab_job_slot WHERE id = 1", String.class)).isEqualTo(RUN);
        assertThat(jobs.pendingOutbox(100)).isEmpty();
    }
    private void assertEmpty() {
        assertThat(jdbc.queryForObject("SELECT COUNT(*) FROM lab_job", Long.class)).isZero();
        assertThat(jobs.pendingOutbox(100)).isEmpty();
        assertThat(jdbc.queryForObject("SELECT occupied_run_id FROM lab_job_slot WHERE id = 1", String.class)).isNull();
    }
    private static class StorageUnavailable extends RuntimeException {}
    private static class MarkUnavailable extends RuntimeException {}
}
