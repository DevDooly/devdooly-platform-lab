package io.github.devdooly.platformlab.jobs;

import io.github.devdooly.platformlab.demo.DemoService;
import io.github.devdooly.platformlab.demo.SyntheticScenario;
import java.nio.charset.StandardCharsets;
import java.time.Clock;
import java.time.Instant;
import java.time.ZoneId;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;
import javax.sql.DataSource;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.ValueSource;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.dao.DataAccessException;
import org.springframework.dao.DataIntegrityViolationException;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.core.PreparedStatementSetter;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.support.TransactionTemplate;
import static org.assertj.core.api.Assertions.*;
import static org.mockito.ArgumentMatchers.*;
import static org.mockito.Mockito.*;

/** Shared H2 syntax/default behavior and opt-in real MariaDB transaction contract. */
abstract class AdmissionCooldownContractTests {
    protected static final String FIRST = "admission-contract-first", NEXT = "admission-contract-next";
    @Autowired protected LabJobService jobs;
    @Autowired protected JdbcTemplate jdbc;
    @Autowired protected PlatformTransactionManager manager;
    @Autowired protected DataSource dataSource;
    @Autowired protected DemoService demos;
    protected final byte[] bytes = CanonicalSource.fixtureBytes();
    protected final List<String> runs = new ArrayList<>();
    protected boolean preserveFailure;
    @org.junit.jupiter.api.extension.RegisterExtension
    final org.junit.jupiter.api.extension.AfterTestExecutionCallback keepFailedFixture = context -> {
        if (context.getExecutionException().isPresent()) { preserveFailure = true; }
    };

    @BeforeEach void ownEmptyDisposableFixture() {
        org.junit.jupiter.api.Assumptions.assumeFalse(preserveFailure, "Failed isolated fixture is preserved; no blind cleanup or retry");
        assertThat(jdbc.queryForObject("SELECT COUNT(*) FROM lab_job", Long.class)).isZero();
        assertThat(jdbc.queryForObject("SELECT occupied_run_id FROM lab_job_slot WHERE id=1", String.class)).isNull();
        AdmissionTestFixtures.makeEligible(jdbc);
        runs.clear();
    }

    @AfterEach void removeOnlyOwnedFixtureRowsAndRestoreDefaultPolicy() {
        if (preserveFailure) { return; }
        new TransactionTemplate(manager).executeWithoutResult(ignored -> {
            String owner = jdbc.queryForObject("SELECT occupied_run_id FROM lab_job_slot WHERE id=1 FOR UPDATE", String.class);
            if (owner != null && !runs.contains(owner)) { throw new IllegalStateException("Unexpected test slot owner"); }
            if (owner != null) { jdbc.update("UPDATE lab_job_slot SET occupied_run_id=NULL WHERE id=1"); }
            for (String run : runs) {
                jdbc.update("DELETE FROM lab_outbox WHERE job_run_id=?", run);
                jdbc.update("DELETE FROM demo_outcome WHERE run_id=?", run);
                jdbc.update("DELETE FROM demo_run WHERE id=?", run);
                jdbc.update("DELETE FROM lab_job WHERE run_id=?", run);
            }
            jdbc.update("UPDATE lab_admission_policy SET cooldown_seconds=30,last_admitted_at=NULL,next_admission_at=NULL WHERE id=1");
        });
    }

    @Test void migrationStartsWithOneUnchargedThirtySecondPolicyAndAdmissionUsesDbTime() {
        assertThat(policy()).containsEntry("id", 1).containsEntry("cooldown_seconds", 30)
            .containsEntry("last_admitted_at", null).containsEntry("next_admission_at", null);
        var prepared = jobs.prepareSource(own(FIRST), SyntheticScenario.NAME, bytes);
        assertThat(prepared.status()).isEqualTo(LabJobService.Status.STAGING);
        assertThat(jdbc.queryForObject("SELECT TIMESTAMPDIFF(MICROSECOND,last_admitted_at,next_admission_at) FROM lab_admission_policy WHERE id=1", Long.class))
            .isEqualTo(30_000_000L);
        assertThat(jdbc.queryForObject("SELECT CASE WHEN last_admitted_at<=CURRENT_TIMESTAMP(6) AND next_admission_at>CURRENT_TIMESTAMP(6) THEN 1 ELSE 0 END FROM lab_admission_policy WHERE id=1", Integer.class))
            .isEqualTo(1);
        assertThat(jobs.pendingOutbox(100)).isEmpty();
    }

    @Test void exportedSlotIsFreeButDifferentRunIsRejectedBeforeStorageAndAllRowsStayExact() {
        var first = jobs.prepareSource(own(FIRST), SyntheticScenario.NAME, bytes);
        jobs.markSourceVerified(FIRST, first.sourceSha256()); jobs.process(FIRST, first.sourceSha256());
        var exported = jobs.completeExport(FIRST, first.sourceSha256());
        var before = snapshot(); var storage = mock(RawSourceStore.class);
        assertThatThrownBy(() -> new SourceStagingService(jobs, storage).stage(own(NEXT), SyntheticScenario.NAME, bytes))
            .isInstanceOf(LabJobService.AdmissionCooldownException.class).hasMessage("ADMISSION_COOLDOWN");
        assertThat(jobs.prepareSource(FIRST, SyntheticScenario.NAME, bytes)).isEqualTo(exported);
        assertThat(snapshot()).isEqualTo(before); verifyNoInteractions(storage);
        assertThat(jdbc.queryForObject("SELECT occupied_run_id FROM lab_job_slot WHERE id=1", String.class)).isNull();
        assertNoRows(NEXT);
    }

    @Test void stagingIoFailureChargesOnceAndExactRetryDoesNotSpendAnotherAdmission() {
        var calls = new AtomicInteger();
        var staging = new SourceStagingService(jobs, (job, source) -> {
            if (calls.incrementAndGet() == 1) { throw new StorageUnavailable(); }
        });
        own(FIRST);
        assertThatThrownBy(() -> staging.stage(FIRST, SyntheticScenario.NAME, bytes)).isInstanceOf(StorageUnavailable.class);
        var charged = policy(); var created = jobs.get(FIRST).createdAt();
        assertThat(jobs.pendingOutbox(100)).isEmpty();
        var queued = staging.stage(FIRST, SyntheticScenario.NAME, bytes);
        assertThat(queued.createdAt()).isEqualTo(created); assertThat(policy()).isEqualTo(charged);
        assertThat(staging.stage(FIRST, SyntheticScenario.NAME, bytes)).isEqualTo(queued);
        assertThat(policy()).isEqualTo(charged); assertThat(calls.get()).isEqualTo(3);
        assertThat(jobs.pendingOutbox(100)).hasSize(1);
    }

    @Test void exactReplayConflictAndOccupiedSlotTakeTheirExistingOrderWithoutChangingGate() {
        var first = jobs.prepareSource(own(FIRST), SyntheticScenario.NAME, bytes); var charged = policy();
        var storage = mock(RawSourceStore.class); var staging = new SourceStagingService(jobs, storage);
        byte[] different = (" " + new String(bytes, StandardCharsets.UTF_8)).getBytes(StandardCharsets.UTF_8);
        assertThatThrownBy(() -> staging.stage(FIRST, SyntheticScenario.NAME, different)).isInstanceOf(LabJobService.SourceConflictException.class);
        assertThatThrownBy(() -> staging.stage(own(NEXT), SyntheticScenario.NAME, bytes)).isInstanceOf(LabJobService.SlotBusyException.class);
        assertThat(jobs.prepareSource(FIRST, SyntheticScenario.NAME, bytes)).isEqualTo(first);
        assertThat(policy()).isEqualTo(charged); assertNoRows(NEXT); verifyNoInteractions(storage);
    }

    @Test void invalidInputNeverChargesPolicyOrReservesSlotOrTouchesStorage() {
        var before = policy(); var storage = mock(RawSourceStore.class); var staging = new SourceStagingService(jobs, storage);
        for (byte[] invalid : List.of(new byte[0], new byte[CanonicalSource.MAX_BYTES + 1], new byte[]{0})) {
            assertThatThrownBy(() -> staging.stage(own(FIRST), SyntheticScenario.NAME, invalid)).isInstanceOf(IllegalArgumentException.class);
        }
        assertThatThrownBy(() -> staging.stage("../private", SyntheticScenario.NAME, bytes)).isInstanceOf(IllegalArgumentException.class);
        assertThatThrownBy(() -> staging.stage(FIRST, "unknown", bytes)).isInstanceOf(IllegalArgumentException.class);
        assertThat(policy()).isEqualTo(before); assertNoRows(FIRST); verifyNoInteractions(storage);
        assertThat(jdbc.queryForObject("SELECT occupied_run_id FROM lab_job_slot WHERE id=1", String.class)).isNull();
    }

    @Test void outerRollbackRestoresAdmissionDatesJobSlotAndOutboxTogether() {
        var before = policy(); own(FIRST);
        assertThatThrownBy(() -> new TransactionTemplate(manager).execute(ignored -> {
            jobs.prepareSource(FIRST, SyntheticScenario.NAME, bytes);
            assertThat(policy().get("last_admitted_at")).isNotNull();
            throw new IntentionalRollback();
        })).isInstanceOf(IntentionalRollback.class);
        assertThat(policy()).isEqualTo(before); assertNoRows(FIRST);
        assertThat(jdbc.queryForObject("SELECT occupied_run_id FROM lab_job_slot WHERE id=1", String.class)).isNull();
        assertThat(jobs.prepareSource(FIRST, SyntheticScenario.NAME, bytes).status()).isEqualTo(LabJobService.Status.STAGING);
    }

    @Test void failedJobInsertRollsBackPreviouslyUpdatedGateAndCannotCallStorage() {
        var before = policy(); var brokenJdbc = spy(jdbc);
        doThrow(new DataIntegrityViolationException("isolated job insert failure"))
            .when(brokenJdbc).update(argThat((String sql) -> sql.contains("INSERT INTO lab_job (")), any(PreparedStatementSetter.class));
        var brokenJobs = new LabJobService(brokenJdbc, manager, demos, Clock.systemUTC()); var storage = mock(RawSourceStore.class);
        assertThatThrownBy(() -> new SourceStagingService(brokenJobs, storage).stage(own(FIRST), SyntheticScenario.NAME, bytes))
            .isInstanceOf(DataIntegrityViolationException.class);
        assertThat(policy()).isEqualTo(before); assertNoRows(FIRST); verifyNoInteractions(storage);
        assertThat(jdbc.queryForObject("SELECT occupied_run_id FROM lab_job_slot WHERE id=1", String.class)).isNull();
    }

    @Test void terminationAndNewServiceWithDifferentApplicationClockCannotResetDurableGate() {
        var prepared = jobs.prepareSource(own(FIRST), SyntheticScenario.NAME, bytes);
        jobs.terminate(FIRST, prepared.sourceSha256()); var before = snapshot();
        var recreated = new LabJobService(new JdbcTemplate(dataSource), manager, demos,
            Clock.fixed(Instant.parse("2040-01-01T00:00:00Z"), ZoneId.of("Asia/Seoul")));
        assertThatThrownBy(() -> recreated.prepareSource(own(NEXT), SyntheticScenario.NAME, bytes)).isInstanceOf(LabJobService.AdmissionCooldownException.class);
        assertThat(snapshot()).isEqualTo(before); assertNoRows(NEXT);
    }

    @Test void missingPolicyFailsClosedAndDatabaseRejectsInvalidConfiguration() {
        var before = policy(); var storage = mock(RawSourceStore.class); own(FIRST);
        assertThatThrownBy(() -> new TransactionTemplate(manager).execute(ignored -> {
            jdbc.update("DELETE FROM lab_admission_policy WHERE id=1");
            return jobs.prepareSource(FIRST, SyntheticScenario.NAME, bytes);
        })).isInstanceOf(IllegalStateException.class).hasMessage("Singleton admission policy is missing");
        for (int bad : List.of(0, 3601)) {
            assertThatThrownBy(() -> jdbc.update("UPDATE lab_admission_policy SET cooldown_seconds=? WHERE id=1", bad)).isInstanceOf(DataAccessException.class);
        }
        assertThatThrownBy(() -> jdbc.update("UPDATE lab_admission_policy SET last_admitted_at=CURRENT_TIMESTAMP(6),next_admission_at=NULL WHERE id=1"))
            .isInstanceOf(DataAccessException.class);
        assertThat(policy()).isEqualTo(before); assertNoRows(FIRST); verifyNoInteractions(storage);
    }

    @Test void configuredBoundedPeriodIsReadFromDatabaseWithoutAProcessOverride() {
        for (int allowed : List.of(1, 3600)) {
            jdbc.update("UPDATE lab_admission_policy SET cooldown_seconds=? WHERE id=1", allowed);
            assertThat(((Number) policy().get("cooldown_seconds")).intValue()).isEqualTo(allowed);
        }
        jdbc.update("UPDATE lab_admission_policy SET cooldown_seconds=37 WHERE id=1");
        jobs.prepareSource(own(FIRST), SyntheticScenario.NAME, bytes);
        assertThat(jdbc.queryForObject("SELECT TIMESTAMPDIFF(MICROSECOND,last_admitted_at,next_admission_at) FROM lab_admission_policy WHERE id=1", Long.class))
            .isEqualTo(37_000_000L);
    }

    @Test void legacyDemoRunConflictRejectsBeforeGateOrStorageEvenWithoutAJobRow() {
        own(FIRST);
        new TransactionTemplate(manager).executeWithoutResult(ignored -> demos.persistProcessedRun(FIRST, "existing fixture", SyntheticScenario.NAME,
            SyntheticScenario.SEED, new io.github.devdooly.platformlab.demo.SensorProcessor().process(SyntheticScenario.events()), Instant.now(), Instant.now()));
        var before = snapshot(); var storage = mock(RawSourceStore.class);
        assertThatThrownBy(() -> new SourceStagingService(jobs, storage).stage(FIRST, SyntheticScenario.NAME, bytes))
            .isInstanceOf(LabJobService.SourceConflictException.class);
        assertThat(snapshot()).isEqualTo(before); assertNoRows(FIRST); verifyNoInteractions(storage);
    }

    @ParameterizedTest @ValueSource(ints = {2, 8})
    void concurrentDifferentRunsHaveOneAdmissionAndOnlyWinnerCanCallStorage(int count) throws Exception {
        var calls = new AtomicInteger(); var staging = new SourceStagingService(jobs, (job, source) -> calls.incrementAndGet());
        var attempts = together(count, index -> staging.stage(runs.get(index), SyntheticScenario.NAME, bytes));
        assertThat(attempts.stream().filter(LabJobService.Job.class::isInstance)).hasSize(1);
        assertThat(attempts.stream().filter(LabJobService.SlotBusyException.class::isInstance)).hasSize(count - 1);
        assertThat(calls.get()).isEqualTo(1);
        assertThat(jdbc.queryForObject("SELECT COUNT(*) FROM lab_job", Long.class)).isEqualTo(1);
        assertThat(jdbc.queryForObject("SELECT COUNT(*) FROM lab_outbox", Long.class)).isEqualTo(1);
        for (String run : runs) {
            if (!run.equals(jdbc.queryForObject("SELECT occupied_run_id FROM lab_job_slot WHERE id=1", String.class))) { assertNoRows(run); }
        }
    }

    @ParameterizedTest @ValueSource(ints = {2, 8})
    void parallelAttemptsAfterSlotReleaseAllRejectDuringCooldownWithZeroStorageCalls(int count) throws Exception {
        var first = jobs.prepareSource(own(FIRST), SyntheticScenario.NAME, bytes); jobs.terminate(FIRST, first.sourceSha256());
        var before = snapshot(); var storage = mock(RawSourceStore.class); var staging = new SourceStagingService(jobs, storage);
        var attempts = together(count, index -> staging.stage(runs.get(index + 1), SyntheticScenario.NAME, bytes));
        assertThat(attempts).allMatch(LabJobService.AdmissionCooldownException.class::isInstance);
        assertThat(snapshot()).isEqualTo(before); verifyNoInteractions(storage);
    }

    protected List<Object> together(int count, java.util.function.IntFunction<?> action) throws Exception {
        for (int index = 0; index < count; index++) { own("admission-contract-parallel-" + index); }
        var ready = new CountDownLatch(count); var start = new CountDownLatch(1);
        try (var pool = Executors.newFixedThreadPool(count)) {
            var futures = new ArrayList<java.util.concurrent.Future<Object>>();
            for (int index = 0; index < count; index++) {
                int selected = index;
                futures.add(pool.submit(() -> {
                    ready.countDown(); if (!start.await(10, TimeUnit.SECONDS)) { throw new IllegalStateException("Test start timed out"); }
                    try { return action.apply(selected); } catch (RuntimeException failure) { return failure; }
                }));
            }
            assertThat(ready.await(10, TimeUnit.SECONDS)).isTrue(); start.countDown();
            var results = new ArrayList<Object>(); for (var future : futures) { results.add(future.get(20, TimeUnit.SECONDS)); }
            return results;
        }
    }
    protected String own(String run) { if (!runs.contains(run)) { runs.add(run); } return run; }
    protected Map<String, Object> policy() { return jdbc.queryForMap("SELECT * FROM lab_admission_policy WHERE id=1"); }
    protected List<?> snapshot() {
        return List.of(policy(), normalizedJobs(),
            jdbc.queryForList("SELECT * FROM lab_outbox ORDER BY id"), jdbc.queryForList("SELECT * FROM lab_job_slot"),
            jdbc.queryForList("SELECT * FROM demo_run ORDER BY id"), jdbc.queryForList("SELECT * FROM demo_outcome ORDER BY run_id,input_sequence"));
    }
    private List<Map<String, Object>> normalizedJobs() {
        var rows = jdbc.queryForList("SELECT * FROM lab_job ORDER BY run_id");
        for (var row : rows) { row.replaceAll((key, value) -> value instanceof byte[] raw ? java.util.HexFormat.of().formatHex(raw) : value); }
        return rows;
    }
    protected void assertNoRows(String run) {
        assertThat(jdbc.queryForObject("SELECT COUNT(*) FROM lab_job WHERE run_id=?", Long.class, run)).isZero();
        assertThat(jdbc.queryForObject("SELECT COUNT(*) FROM lab_outbox WHERE job_run_id=?", Long.class, run)).isZero();
    }
    private static final class StorageUnavailable extends RuntimeException {}
    private static final class IntentionalRollback extends RuntimeException {}
}
