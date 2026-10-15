package io.github.devdooly.platformlab.jobs;

import io.github.devdooly.platformlab.demo.DemoService;
import io.github.devdooly.platformlab.demo.SensorProcessor;
import io.github.devdooly.platformlab.demo.SyntheticScenario;
import java.nio.charset.StandardCharsets;
import java.time.Instant;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.concurrent.Callable;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.transaction.IllegalTransactionStateException;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.support.TransactionTemplate;
import static org.assertj.core.api.Assertions.*;

abstract class LabJobContractTests {
    private static final String RUN = "foundation-job-a";
    private static final String OTHER = "foundation-job-b";
    @Autowired LabJobService jobs;
    @Autowired DemoService demos;
    @Autowired JdbcTemplate jdbc;
    @Autowired PlatformTransactionManager transactionManager;
    private List<Map<String, Object>> seedRun;
    private List<Map<String, Object>> seedOutcomes;

    @BeforeEach void preserveSeedAndRemoveOnlyOwnPreviousFixtures() {
        cleanFixtures();
        AdmissionTestFixtures.makeEligible(jdbc);
        demos.ensureSample();
        seedRun = jdbc.queryForList("SELECT * FROM demo_run WHERE id = ?", SyntheticScenario.RUN_ID);
        seedOutcomes = jdbc.queryForList("SELECT * FROM demo_outcome WHERE run_id = ? ORDER BY input_sequence", SyntheticScenario.RUN_ID);
        assertThat(seedRun).hasSize(1); assertThat(seedOutcomes).hasSize(12);
    }

    @AfterEach void seedAndItsOriginalTimesRemainUnchanged() {
        if (seedRun != null) {
            assertThat(jdbc.queryForList("SELECT * FROM demo_run WHERE id = ?", SyntheticScenario.RUN_ID)).isEqualTo(seedRun);
            assertThat(jdbc.queryForList("SELECT * FROM demo_outcome WHERE run_id = ? ORDER BY input_sequence", SyntheticScenario.RUN_ID)).isEqualTo(seedOutcomes);
        }
        cleanFixtures();
    }

    @Test void prepareIsIdempotentAndRetainsImmutableOriginalBytes() {
        byte[] original = CanonicalSource.fixtureBytes();
        byte[] source = original.clone();
        var prepared = jobs.prepareSource(RUN, SyntheticScenario.NAME, source);
        source[0] = 0;
        assertThat(prepared.status()).isEqualTo(LabJobService.Status.STAGING);
        assertThat(prepared.exportStatus()).isEqualTo(LabJobService.ExportStatus.NOT_REQUESTED);
        assertThat(prepared.sourceObjectKey()).isEqualTo("raw/" + RUN + "/" + prepared.sourceSha256() + ".ndjson");
        assertThat(jobs.prepareSource(RUN, SyntheticScenario.NAME, original)).isEqualTo(prepared);
        assertThat(jdbc.queryForObject("SELECT source_bytes FROM lab_job WHERE run_id = ?", byte[].class, RUN)).isEqualTo(original);
        assertThat(jdbc.queryForObject("SELECT COUNT(*) FROM lab_job", Long.class)).isEqualTo(1);
        assertThat(jobs.pendingOutbox(100)).isEmpty();
    }

    @Test void sameRunWithDifferentValidRawBytesConflictsWithoutChangingMetadata() {
        var prepared = prepare();
        byte[] alternate = (" " + new String(CanonicalSource.fixtureBytes(), StandardCharsets.UTF_8)).getBytes(StandardCharsets.UTF_8);
        assertThat(CanonicalSource.validate(alternate).sha256()).isNotEqualTo(prepared.sourceSha256());
        assertThatThrownBy(() -> jobs.prepareSource(RUN, SyntheticScenario.NAME, alternate)).isInstanceOf(LabJobService.SourceConflictException.class);
        assertThat(jobs.get(RUN)).isEqualTo(prepared);
        assertThat(jobs.pendingOutbox(100)).isEmpty();
    }

    @Test void invalidAdmissionCannotReserveSlotOrInsertJobOrOutbox() {
        var valid = CanonicalSource.fixtureBytes();
        var badSources = new ArrayList<byte[]>();
        badSources.add(new byte[0]); badSources.add(new byte[CanonicalSource.MAX_BYTES + 1]);
        badSources.add("{}\n".getBytes(StandardCharsets.UTF_8));
        badSources.add(new String(valid, StandardCharsets.UTF_8).replace("not-a-timestamp", "2026-01-01T00:01:00Z").getBytes(StandardCharsets.UTF_8));
        badSources.add(new String(valid, StandardCharsets.UTF_8).replaceFirst("evt-001", "evt-999").getBytes(StandardCharsets.UTF_8));
        badSources.add((new String(valid, StandardCharsets.UTF_8) + "\n").getBytes(StandardCharsets.UTF_8));
        for (byte[] source : badSources) {
            assertThatThrownBy(() -> jobs.prepareSource(RUN, SyntheticScenario.NAME, source)).isInstanceOf(IllegalArgumentException.class);
        }
        for (String id : List.of(SyntheticScenario.RUN_ID, "x".repeat(81), "Foundation", "../escape", "")) {
            assertThatThrownBy(() -> jobs.prepareSource(id, SyntheticScenario.NAME, valid)).isInstanceOf(IllegalArgumentException.class);
        }
        assertThatThrownBy(() -> jobs.prepareSource(RUN, "unsupported-version", valid)).isInstanceOf(IllegalArgumentException.class);
        assertNoJobsOrOutbox();
    }

    @Test void exactByteLimitIsAcceptedAndOverflowRejected() {
        byte[] fixture = CanonicalSource.fixtureBytes();
        byte[] maximum = (" ".repeat(CanonicalSource.MAX_BYTES - fixture.length)
            + new String(fixture, StandardCharsets.UTF_8)).getBytes(StandardCharsets.UTF_8);
        assertThat(maximum).hasSize(CanonicalSource.MAX_BYTES);
        assertThat(jobs.prepareSource(RUN, SyntheticScenario.NAME, maximum).sourceSize()).isEqualTo(CanonicalSource.MAX_BYTES);
        assertThatThrownBy(() -> jobs.prepareSource(OTHER, SyntheticScenario.NAME, new byte[CanonicalSource.MAX_BYTES + 1]))
            .isInstanceOf(IllegalArgumentException.class);
        assertThat(jdbc.queryForObject("SELECT COUNT(*) FROM lab_job", Long.class)).isEqualTo(1);
    }

    @Test void sourceVerificationAndDispatchIntentCommitTogetherAndAreIdempotent() {
        var prepared = prepare();
        assertThatThrownBy(() -> jobs.markSourceVerified(RUN, "0".repeat(64))).isInstanceOf(LabJobService.SourceConflictException.class);
        assertThat(jobs.get(RUN)).isEqualTo(prepared); assertThat(jobs.pendingOutbox(100)).isEmpty();
        var queued = jobs.markSourceVerified(RUN, prepared.sourceSha256());
        assertThat(queued.status()).isEqualTo(LabJobService.Status.QUEUED);
        assertThat(queued.sourceVerifiedAt()).isEqualTo(queued.queuedAt());
        assertThat(queued.completedAt()).isNull();
        var outbox = jobs.pendingOutbox(100);
        assertThat(outbox).hasSize(1);
        assertThat(outbox.getFirst().eventType()).isEqualTo(LabJobService.EventType.DISPATCH);
        assertThat(outbox.getFirst().sourceSha256()).isEqualTo(prepared.sourceSha256());
        assertThat(jobs.markSourceVerified(RUN, prepared.sourceSha256())).isEqualTo(queued);
        assertThat(jobs.pendingOutbox(100)).isEqualTo(outbox);
    }

    @Test void outerTransactionFailureRollsBackSourceVerificationAndDispatchIntent() {
        var prepared = prepare();
        assertThatThrownBy(() -> new TransactionTemplate(transactionManager).execute(ignored -> {
            jobs.markSourceVerified(RUN, prepared.sourceSha256());
            assertThat(jobs.pendingOutbox(100)).hasSize(1);
            throw new IntentionalRollback();
        })).isInstanceOf(IntentionalRollback.class);
        assertThat(jobs.get(RUN)).isEqualTo(prepared);
        assertThat(jobs.pendingOutbox(100)).isEmpty();
    }

    @Test void processPersistsAllTwelveIndependentExpectedOutcomesAndExportIntentOnce() {
        var queued = queue();
        var completed = jobs.process(RUN, queued.sourceSha256());
        assertThat(completed.status()).isEqualTo(LabJobService.Status.COMPLETED);
        assertThat(completed.exportStatus()).isEqualTo(LabJobService.ExportStatus.PENDING);
        assertThat(demos.detail(RUN).get("completedAt")).isEqualTo(completed.completedAt());
        assertThat(jdbc.queryForObject("""
            SELECT CASE WHEN j.completed_at = d.completed_at THEN 1 ELSE 0 END
            FROM lab_job j JOIN demo_run d ON d.id = j.run_id WHERE j.run_id = ?
            """, Integer.class, RUN)).isEqualTo(1);
        assertExpectedResult(RUN);
        var run = jdbc.queryForList("SELECT * FROM demo_run WHERE id = ?", RUN);
        var outcomes = jdbc.queryForList("SELECT * FROM demo_outcome WHERE run_id = ? ORDER BY input_sequence", RUN);
        var outbox = jdbc.queryForList("SELECT * FROM lab_outbox WHERE job_run_id = ? ORDER BY id", RUN);
        assertThat(outbox).hasSize(2);
        assertThat(jobs.pendingOutbox(100)).extracting(LabJobService.Outbox::eventType)
            .containsExactly(LabJobService.EventType.DISPATCH, LabJobService.EventType.EXPORT);
        assertThatThrownBy(() -> jobs.prepareSource(OTHER, SyntheticScenario.NAME, CanonicalSource.fixtureBytes()))
            .isInstanceOf(LabJobService.SlotBusyException.class);
        assertThat(jobs.process(RUN, queued.sourceSha256())).isEqualTo(completed);
        assertThat(jdbc.queryForList("SELECT * FROM demo_run WHERE id = ?", RUN)).isEqualTo(run);
        assertThat(jdbc.queryForList("SELECT * FROM demo_outcome WHERE run_id = ? ORDER BY input_sequence", RUN)).isEqualTo(outcomes);
        assertThat(jdbc.queryForList("SELECT * FROM lab_outbox WHERE job_run_id = ? ORDER BY id", RUN)).isEqualTo(outbox);
        assertThatThrownBy(() -> jobs.process(RUN, "0".repeat(64))).isInstanceOf(LabJobService.SourceConflictException.class);
        assertThat(jobs.get(RUN)).isEqualTo(completed);
    }

    @Test void processingBeforeSourceVerificationCannotWriteResults() {
        var prepared = prepare();
        assertThatThrownBy(() -> jobs.process(RUN, prepared.sourceSha256())).isInstanceOf(LabJobService.JobStateException.class);
        assertThat(jobs.get(RUN)).isEqualTo(prepared);
        assertThat(jdbc.queryForObject("SELECT COUNT(*) FROM demo_run WHERE id = ?", Long.class, RUN)).isZero();
        assertThat(jobs.pendingOutbox(100)).isEmpty();
    }

    @Test void outerTransactionFailureRollsBackResultsCompletionAndExportIntent() {
        var queued = queue();
        var before = jdbc.queryForList("SELECT * FROM lab_outbox WHERE job_run_id = ? ORDER BY id", RUN);
        assertThatThrownBy(() -> new TransactionTemplate(transactionManager).execute(ignored -> {
            jobs.process(RUN, queued.sourceSha256());
            assertThat(jdbc.queryForObject("SELECT COUNT(*) FROM demo_outcome WHERE run_id = ?", Long.class, RUN)).isEqualTo(12);
            throw new IntentionalRollback();
        })).isInstanceOf(IntentionalRollback.class);
        assertThat(jobs.get(RUN)).isEqualTo(queued);
        assertThat(jdbc.queryForObject("SELECT COUNT(*) FROM demo_run WHERE id = ?", Long.class, RUN)).isZero();
        assertThat(jdbc.queryForObject("SELECT COUNT(*) FROM demo_outcome WHERE run_id = ?", Long.class, RUN)).isZero();
        assertThat(jdbc.queryForList("SELECT * FROM lab_outbox WHERE job_run_id = ? ORDER BY id", RUN)).isEqualTo(before);
        assertThat(jdbc.queryForObject("SELECT occupied_run_id FROM lab_job_slot WHERE id = 1", String.class)).isEqualTo(RUN);
        jobs.process(RUN, queued.sourceSha256());
        assertExpectedResult(RUN);
    }

    @Test void dispatchAcknowledgementIsIdempotentAndDoesNotFreeAdmissionSlot() {
        var queued = queue();
        assertThat(jobs.acknowledgeDispatch(RUN, queued.sourceSha256())).isEqualTo(queued);
        var first = jdbc.queryForList("SELECT * FROM lab_outbox WHERE job_run_id = ?", RUN);
        jobs.acknowledgeDispatch(RUN, queued.sourceSha256());
        assertThat(jdbc.queryForList("SELECT * FROM lab_outbox WHERE job_run_id = ?", RUN)).isEqualTo(first);
        assertThat(jobs.pendingOutbox(100)).isEmpty();
        assertThatThrownBy(() -> jobs.prepareSource(OTHER, SyntheticScenario.NAME, CanonicalSource.fixtureBytes())).isInstanceOf(LabJobService.SlotBusyException.class);
    }

    @Test void onlyConfirmedCompletedExportReleasesSlotAndRepeatPreservesTimes() {
        var queued = queue();
        assertThatThrownBy(() -> jobs.completeExport(RUN, queued.sourceSha256())).isInstanceOf(LabJobService.JobStateException.class);
        jobs.process(RUN, queued.sourceSha256());
        var exported = jobs.completeExport(RUN, queued.sourceSha256());
        assertThat(exported.exportStatus()).isEqualTo(LabJobService.ExportStatus.EXPORTED);
        assertThat(exported.exportCompletedAt()).isNotNull();
        assertThat(jobs.completeExport(RUN, queued.sourceSha256())).isEqualTo(exported);
        AdmissionTestFixtures.makeEligible(jdbc); // This test concerns export replay and the next slot.
        assertThat(jobs.prepareSource(OTHER, SyntheticScenario.NAME, CanonicalSource.fixtureBytes()).status()).isEqualTo(LabJobService.Status.STAGING);
        assertThat(jobs.prepareSource(RUN, SyntheticScenario.NAME, CanonicalSource.fixtureBytes())).isEqualTo(exported);
        assertExpectedResult(RUN);
    }

    @Test void explicitQueuedTerminationCancelsPendingIntentAndDoesNotClaimExport() {
        var queued = queue();
        var stopped = jobs.terminate(RUN, queued.sourceSha256());
        assertThat(stopped.status()).isEqualTo(LabJobService.Status.TERMINATED);
        assertThat(stopped.exportStatus()).isEqualTo(LabJobService.ExportStatus.NOT_REQUESTED);
        assertThat(stopped.exportCompletedAt()).isNull();
        assertThat(jobs.pendingOutbox(100)).isEmpty();
        assertThat(jdbc.queryForObject("SELECT status FROM lab_outbox WHERE job_run_id = ?", String.class, RUN)).isEqualTo("CANCELLED");
        assertThatThrownBy(() -> jobs.process(RUN, queued.sourceSha256())).isInstanceOf(LabJobService.JobStateException.class);
        assertThat(jobs.terminate(RUN, queued.sourceSha256())).isEqualTo(stopped);
        AdmissionTestFixtures.makeEligible(jdbc); // Explicit independent next-job fixture.
        jobs.prepareSource(OTHER, SyntheticScenario.NAME, CanonicalSource.fixtureBytes());
    }

    @Test void explicitCompletedTerminationPreservesResultsAndRecordsCancelledExport() {
        var queued = queue();
        var completed = jobs.process(RUN, queued.sourceSha256());
        var stopped = jobs.terminate(RUN, queued.sourceSha256());
        assertThat(stopped.status()).isEqualTo(LabJobService.Status.COMPLETED);
        assertThat(stopped.completedAt()).isEqualTo(completed.completedAt());
        assertThat(stopped.exportStatus()).isEqualTo(LabJobService.ExportStatus.CANCELLED);
        assertThat(stopped.exportCompletedAt()).isNull();
        assertThatThrownBy(() -> jobs.completeExport(RUN, queued.sourceSha256())).isInstanceOf(LabJobService.JobStateException.class);
        assertThat(jobs.process(RUN, queued.sourceSha256())).isEqualTo(stopped);
        assertExpectedResult(RUN);
        AdmissionTestFixtures.makeEligible(jdbc); // Explicit independent next-job fixture.
        jobs.prepareSource(OTHER, SyntheticScenario.NAME, CanonicalSource.fixtureBytes());
    }

    @Test void concurrentDifferentRunsAdmitExactlyOneJobUsingDatabaseSlotLock() throws Exception {
        var results = together(() -> jobs.prepareSource(RUN, SyntheticScenario.NAME, CanonicalSource.fixtureBytes()),
            () -> jobs.prepareSource(OTHER, SyntheticScenario.NAME, CanonicalSource.fixtureBytes()));
        assertThat(results.stream().filter(LabJobService.Job.class::isInstance)).hasSize(1);
        assertThat(results.stream().filter(LabJobService.SlotBusyException.class::isInstance)).hasSize(1);
        assertThat(jdbc.queryForObject("SELECT COUNT(*) FROM lab_job", Long.class)).isEqualTo(1);
        assertThat(jdbc.queryForObject("SELECT occupied_run_id FROM lab_job_slot WHERE id = 1", String.class)).isIn(RUN, OTHER);
        assertThat(jobs.pendingOutbox(100)).isEmpty();
    }

    @Test void concurrentSameRunRetriesProduceOneImmutableJob() throws Exception {
        var results = together(() -> jobs.prepareSource(RUN, SyntheticScenario.NAME, CanonicalSource.fixtureBytes()),
            () -> jobs.prepareSource(RUN, SyntheticScenario.NAME, CanonicalSource.fixtureBytes()));
        assertThat(results).allMatch(LabJobService.Job.class::isInstance);
        assertThat(results.getFirst()).isEqualTo(results.getLast());
        assertThat(jdbc.queryForObject("SELECT COUNT(*) FROM lab_job", Long.class)).isEqualTo(1);
    }

    @Test void concurrentBatchRedeliveryPersistsOneRunAndOneExportIntent() throws Exception {
        var queued = queue();
        var results = together(() -> jobs.process(RUN, queued.sourceSha256()), () -> jobs.process(RUN, queued.sourceSha256()));
        assertThat(results).allMatch(LabJobService.Job.class::isInstance);
        assertThat(results.getFirst()).isEqualTo(results.getLast());
        assertExpectedResult(RUN);
        assertThat(jdbc.queryForObject("SELECT COUNT(*) FROM demo_run WHERE id = ?", Long.class, RUN)).isEqualTo(1);
        assertThat(jdbc.queryForObject("SELECT COUNT(*) FROM lab_outbox WHERE job_run_id = ? AND event_type = 'EXPORT'", Long.class, RUN)).isEqualTo(1);
    }

    @Test void demoResultPersistenceRequiresExistingTransaction() {
        var at = Instant.now();
        assertThatThrownBy(() -> demos.persistProcessedRun(RUN, "test", SyntheticScenario.NAME, 42,
            new SensorProcessor().process(SyntheticScenario.events()), at, at))
            .isInstanceOf(IllegalTransactionStateException.class);
        assertNoJobsOrOutbox();
    }

    private LabJobService.Job prepare() { return jobs.prepareSource(RUN, SyntheticScenario.NAME, CanonicalSource.fixtureBytes()); }
    private LabJobService.Job queue() { var job = prepare(); return jobs.markSourceVerified(RUN, job.sourceSha256()); }
    private void assertNoJobsOrOutbox() {
        assertThat(jdbc.queryForObject("SELECT COUNT(*) FROM lab_job", Long.class)).isZero();
        assertThat(jdbc.queryForObject("SELECT COUNT(*) FROM lab_outbox", Long.class)).isZero();
        assertThat(jdbc.queryForObject("SELECT occupied_run_id FROM lab_job_slot WHERE id = 1", String.class)).isNull();
    }
    private void assertExpectedResult(String runId) {
        var run = jdbc.queryForMap("SELECT * FROM demo_run WHERE id = ?", runId);
        assertThat(((Number) run.get("input_count")).intValue()).isEqualTo(12);
        assertThat(((Number) run.get("success_count")).intValue()).isEqualTo(7);
        assertThat(((Number) run.get("failure_count")).intValue()).isEqualTo(3);
        assertThat(((Number) run.get("duplicate_count")).intValue()).isEqualTo(2);
        assertThat(((Number) run.get("pending_count")).intValue()).isZero();
        var rows = jdbc.queryForList("SELECT * FROM demo_outcome WHERE run_id = ? ORDER BY input_sequence", runId);
        assertThat(rows).hasSize(12);
        assertThat(rows).extracting(row -> row.get("status")).containsExactly("SUCCESS", "SUCCESS", "SUCCESS", "DUPLICATE",
            "FAILED", "FAILED", "FAILED", "SUCCESS", "SUCCESS", "SUCCESS", "DUPLICATE", "SUCCESS");
        assertThat(rows).extracting(row -> row.get("reason")).containsExactly("ACCEPTED", "ACCEPTED", "ACCEPTED", "DUPLICATE_EVENT_ID",
            "INVALID_TIMESTAMP", "OUT_OF_ORDER", "OUT_OF_RANGE", "ACCEPTED", "ACCEPTED", "ACCEPTED", "DUPLICATE_EVENT_ID", "ACCEPTED");
        assertThat(rows).extracting(row -> ((Number) row.get("input_sequence")).intValue()).containsExactly(1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12);
        assertThat(rows.get(4).get("event_time")).isEqualTo("not-a-timestamp");
        assertThat(rows).extracting(row -> row.get("event_id")).containsExactly("evt-001", "evt-002", "evt-003", "evt-003", "evt-004",
            "evt-005", "evt-006", "evt-007", "evt-008", "evt-009", "evt-001", "evt-010");
    }
    private List<Object> together(Callable<?> first, Callable<?> second) throws Exception {
        var ready = new CountDownLatch(2);
        var start = new CountDownLatch(1);
        try (var pool = Executors.newFixedThreadPool(2)) {
            var tasks = List.of(first, second).stream().map(task -> pool.submit(() -> {
                ready.countDown();
                if (!start.await(10, TimeUnit.SECONDS)) { throw new IllegalStateException("Concurrent start timed out"); }
                try { return (Object) task.call(); } catch (RuntimeException failure) { return failure; }
            })).toList();
            assertThat(ready.await(10, TimeUnit.SECONDS)).isTrue(); start.countDown();
            return List.of(tasks.getFirst().get(20, TimeUnit.SECONDS), tasks.getLast().get(20, TimeUnit.SECONDS));
        }
    }
    private void cleanFixtures() {
        new TransactionTemplate(transactionManager).executeWithoutResult(ignored -> {
            String occupied = jdbc.queryForObject("SELECT occupied_run_id FROM lab_job_slot WHERE id = 1 FOR UPDATE", String.class);
            if (occupied != null && !occupied.startsWith("foundation-")) {
                throw new IllegalStateException("Refusing to modify another job's occupied slot; use a disposable test database");
            }
            if (occupied != null) { jdbc.update("UPDATE lab_job_slot SET occupied_run_id = NULL WHERE id = 1"); }
            jdbc.update("DELETE FROM lab_outbox WHERE job_run_id LIKE 'foundation-%'");
            jdbc.update("DELETE FROM demo_outcome WHERE run_id LIKE 'foundation-%'");
            jdbc.update("DELETE FROM demo_run WHERE id LIKE 'foundation-%'");
            jdbc.update("DELETE FROM lab_job WHERE run_id LIKE 'foundation-%'");
        });
    }
    private static class IntentionalRollback extends RuntimeException {}
}
