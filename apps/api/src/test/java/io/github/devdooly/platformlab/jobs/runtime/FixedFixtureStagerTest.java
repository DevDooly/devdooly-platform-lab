package io.github.devdooly.platformlab.jobs.runtime;

import io.github.devdooly.platformlab.jobs.CanonicalSource;
import io.github.devdooly.platformlab.jobs.LabJobService;
import io.github.devdooly.platformlab.jobs.RawSourceStore;
import io.github.devdooly.platformlab.jobs.SourceStagingService;
import java.time.Clock;
import java.util.List;
import java.util.concurrent.atomic.AtomicInteger;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.transaction.support.TransactionSynchronizationManager;
import static org.assertj.core.api.Assertions.*;

@SpringBootTest(properties = "spring.datasource.url=jdbc:h2:mem:fixed_fixture_stage_tests;MODE=MariaDB;DATABASE_TO_LOWER=TRUE;DB_CLOSE_DELAY=-1")
@ActiveProfiles({"test", "worker"})
class FixedFixtureStagerTest {
    private static final String FIRST = "lab-fixture-command-first", NEXT = "lab-fixture-command-next";
    @Autowired LabJobService jobs;
    @Autowired JdbcTemplate jdbc;
    private RuntimeStateStore states;
    private final RuntimeLease testOwner = new RuntimeLease() {
        @Override public void verifyHeld() {}
        @Override public void close() {}
    };
    @BeforeEach void resetOwnJournal() {
        states = new RuntimeStateStore(jdbc, Clock.systemUTC());
        jdbc.update("UPDATE lab_runtime SET status='NOT_STARTED',stage='IDLE',failure_code=NULL,source_commit='unknown',started_at=NULL,heartbeat_at=NULL,stopped_at=NULL WHERE id=1");
    }
    @AfterEach void removeOnlyOwnFixtures() {
        String occupied = jdbc.queryForObject("SELECT occupied_run_id FROM lab_job_slot WHERE id=1", String.class);
        assertThat(occupied).isIn(null, FIRST, NEXT);
        jdbc.update("UPDATE lab_job_slot SET occupied_run_id=NULL WHERE id=1");
        for (String run : List.of(FIRST, NEXT)) {
            jdbc.update("DELETE FROM lab_outbox WHERE job_run_id=?", run);
            jdbc.update("DELETE FROM lab_job WHERE run_id=?", run);
        }
    }

    @Test void stagesFixedTwelveInputsWhileWorkerRunsWithoutChangingRuntimeJournalOrProcessingResults() {
        states.start(testOwner, "a".repeat(40)); var journal = states.read(); var calls = new AtomicInteger();
        var stager = stager((job, bytes) -> {
            assertThat(TransactionSynchronizationManager.isActualTransactionActive()).isFalse();
            assertThat(job.status()).isEqualTo(LabJobService.Status.STAGING);
            assertThat(bytes).isEqualTo(CanonicalSource.fixtureBytes());
            assertThat(CanonicalSource.validate(bytes).events()).hasSize(12); calls.incrementAndGet();
        });
        var job = stager.stage(FIRST);
        assertThat(job.status()).isEqualTo(LabJobService.Status.QUEUED);
        assertThat(job.exportStatus()).isEqualTo(LabJobService.ExportStatus.NOT_REQUESTED);
        assertThat(job.completedAt()).isNull(); assertThat(calls.get()).isEqualTo(1);
        assertThat(states.read()).isEqualTo(journal);
        assertThat(jdbc.queryForObject("SELECT occupied_run_id FROM lab_job_slot WHERE id=1", String.class)).isEqualTo(FIRST);
        assertThat(jdbc.queryForObject("SELECT COUNT(*) FROM lab_outbox WHERE job_run_id=? AND event_type='DISPATCH' AND status='PENDING'", Long.class, FIRST)).isEqualTo(1L);
        assertThat(jdbc.queryForObject("SELECT COUNT(*) FROM demo_run WHERE id=?", Long.class, FIRST)).isZero();
    }

    @Test void secondAdmissionIsRejectedBeforeStorageAndRepeatOfFirstDoesNotChangeAdmissionTimesOrJournal() {
        var writes = new AtomicInteger(); var stager = stager((job, bytes) -> writes.incrementAndGet());
        var first = stager.stage(FIRST); var journal = states.read();
        assertThatThrownBy(() -> stager.stage(NEXT)).isInstanceOf(LabJobService.SlotBusyException.class);
        assertThat(writes.get()).isEqualTo(1); assertThat(stager.stage(FIRST)).isEqualTo(first);
        assertThat(states.read()).isEqualTo(journal); assertThat(jdbc.queryForObject("SELECT COUNT(*) FROM lab_job", Long.class)).isEqualTo(1L);
    }

    @Test void failedRawVerificationRetainsStagingSlotWithoutDispatchAndCanRetryExactFixedSource() {
        var calls = new AtomicInteger(); var stager = stager((job, bytes) -> {
            if (calls.incrementAndGet() == 1) { throw new IllegalStateException("raw verification unavailable"); }
            assertThat(bytes).isEqualTo(CanonicalSource.fixtureBytes());
        });
        assertThatThrownBy(() -> stager.stage(FIRST)).isInstanceOf(IllegalStateException.class);
        var staging = jobs.get(FIRST); assertThat(staging.status()).isEqualTo(LabJobService.Status.STAGING);
        assertThat(jdbc.queryForObject("SELECT COUNT(*) FROM lab_outbox WHERE job_run_id=?", Long.class, FIRST)).isZero();
        var queued = stager.stage(FIRST);
        assertThat(queued.status()).isEqualTo(LabJobService.Status.QUEUED);
        assertThat(queued.createdAt()).isEqualTo(staging.createdAt()); assertThat(queued.sourceSha256()).isEqualTo(staging.sourceSha256());
        assertThat(calls.get()).isEqualTo(2);
    }

    @Test void pausedRuntimeAndForeignRunIdsCannotAdmitRowsOrTouchStorage() {
        var calls = new AtomicInteger(); var stager = stager((job, bytes) -> calls.incrementAndGet());
        for (String id : new String[]{"synthetic-v1-seed-42", "foreign-run", "lab-fixture-", "lab-fixture-Uppercase", "lab-fixture-" + "a".repeat(69)}) {
            assertThatThrownBy(() -> stager.stage(id)).isInstanceOf(IllegalArgumentException.class);
        }
        assertThatThrownBy(() -> stager.stage(null)).isInstanceOf(IllegalArgumentException.class);
        states.start(testOwner, "unknown"); states.pause(testOwner, RuntimeStateStore.Stage.EXPORT, RuntimeStateStore.FailureCode.EXPORT_FAILED);
        var paused = states.read();
        assertThatThrownBy(() -> stager.stage(FIRST)).isInstanceOf(RuntimeStateStore.OperatorResumeRequiredException.class);
        assertThat(states.read()).isEqualTo(paused); assertThat(calls.get()).isZero();
        assertThat(jdbc.queryForObject("SELECT COUNT(*) FROM lab_job", Long.class)).isZero();
        assertThat(jdbc.queryForObject("SELECT occupied_run_id FROM lab_job_slot WHERE id=1", String.class)).isNull();
    }
    private FixedFixtureStager stager(RawSourceStore raw) { return new FixedFixtureStager(states, new SourceStagingService(jobs, raw)); }
}
