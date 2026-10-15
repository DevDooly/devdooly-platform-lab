package io.github.devdooly.platformlab.jobs.exporting;

import io.github.devdooly.platformlab.demo.SyntheticScenario;
import io.github.devdooly.platformlab.jobs.CanonicalSource;
import io.github.devdooly.platformlab.jobs.LabJobService;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.concurrent.atomic.AtomicInteger;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.transaction.IllegalTransactionStateException;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.support.TransactionSynchronizationManager;
import org.springframework.transaction.support.TransactionTemplate;
import tools.jackson.databind.json.JsonMapper;
import static org.assertj.core.api.Assertions.*;
import static org.mockito.ArgumentMatchers.*;
import static org.mockito.Mockito.*;

@SpringBootTest(properties = "spring.datasource.url=jdbc:h2:mem:result_export_tests;MODE=MariaDB;DATABASE_TO_LOWER=TRUE;DB_CLOSE_DELAY=-1")
@ActiveProfiles("test")
class ResultExportIntegrationTest {
    private static final String RUN = "export-integration";
    private static final String NEXT = "export-integration-next";
    @Autowired LabJobService jobs;
    @Autowired JdbcTemplate jdbc;
    @Autowired PlatformTransactionManager manager;

    @org.junit.jupiter.api.BeforeEach void resetOwnAdmissionClock() {
        io.github.devdooly.platformlab.jobs.AdmissionTestFixtures.makeEligible(jdbc);
    }

    @AfterEach void cleanOwnRows() {
        new TransactionTemplate(manager).executeWithoutResult(ignored -> {
            var owner = jdbc.queryForObject("SELECT occupied_run_id FROM lab_job_slot WHERE id = 1 FOR UPDATE", String.class);
            assertThat(owner).isIn(null, RUN, NEXT);
            jdbc.update("UPDATE lab_job_slot SET occupied_run_id = NULL WHERE id = 1");
            for (String run : List.of(RUN, NEXT)) {
                jdbc.update("DELETE FROM lab_outbox WHERE job_run_id = ?", run);
                jdbc.update("DELETE FROM demo_outcome WHERE run_id = ?", run);
                jdbc.update("DELETE FROM demo_run WHERE id = ?", run);
                jdbc.update("DELETE FROM lab_job WHERE run_id = ?", run);
            }
        });
    }

    @Test void bothVerifiedDocumentsPrecedeAtomicAcknowledgementAndSlotRelease() {
        var before = completed(CanonicalSource.fixtureBytes()); var resultRows = businessRows();
        var verified = new ArrayList<ExportBundle.Document>();
        var service = new ResultExportService(jobs, document -> {
            assertThat(TransactionSynchronizationManager.isActualTransactionActive()).isFalse();
            assertPending(before); verified.add(document);
        }, ignored -> assertPending(before), bundle -> {
            assertPending(before); assertThat(verified).containsExactly(bundle.result(), bundle.failures());
        });
        var after = service.export(RUN, before.sourceSha256());
        assertThat(after.exportStatus()).isEqualTo(LabJobService.ExportStatus.EXPORTED);
        assertThat(after.exportCompletedAt()).isNotNull(); assertThat(owner()).isNull();
        assertThat(exportOutbox()).containsEntry("status", "ACKNOWLEDGED");
        assertThat(businessRows()).isEqualTo(resultRows);
        assertThat(verified.get(0).key()).contains("/result-v1-");
        assertThat(verified.get(1).key()).contains("/failures-v1-");
    }

    @Test void partialFailureRetainsPendingResultAndRetryReusesTheFirstDocument() {
        var before = completed(CanonicalSource.fixtureBytes()); var rows = businessRows();
        var objects = new HashMap<String, byte[]>(); var calls = new AtomicInteger(); var puts = new AtomicInteger();
        ResultExportStore store = document -> {
            assertThat(TransactionSynchronizationManager.isActualTransactionActive()).isFalse();
            if (calls.incrementAndGet() == 2) { throw new StorageUnavailable(); }
            if (!objects.containsKey(document.key())) { objects.put(document.key(), document.bytes()); puts.incrementAndGet(); }
            assertThat(document.matches(objects.get(document.key()))).isTrue();
        };
        var service = new ResultExportService(jobs, store);
        assertThatThrownBy(() -> service.export(RUN, before.sourceSha256())).isInstanceOf(StorageUnavailable.class);
        assertPending(before); assertThat(objects).hasSize(1); assertThat(businessRows()).isEqualTo(rows);
        service.export(RUN, before.sourceSha256());
        assertThat(puts.get()).isEqualTo(2); assertThat(objects).hasSize(2); assertThat(owner()).isNull();
    }

    @Test void firstObjectFailureDoesNotAcknowledgeAnything() {
        var before = completed(CanonicalSource.fixtureBytes()); var calls = new AtomicInteger();
        var service = new ResultExportService(jobs, document -> { calls.incrementAndGet(); throw new StorageUnavailable(); });
        assertThatThrownBy(() -> service.export(RUN, before.sourceSha256())).isInstanceOf(StorageUnavailable.class);
        assertPending(before); assertThat(calls.get()).isEqualTo(1);
    }

    @Test void finalDbFailureLeavesBothObjectsAndPendingSlotForVerificationOnlyRetry() {
        var before = completed(CanonicalSource.fixtureBytes()); var rows = businessRows();
        var spyJobs = spy(jobs); var objects = new HashMap<String, byte[]>(); var puts = new AtomicInteger();
        doThrow(new DbUnavailable()).doCallRealMethod().when(spyJobs).completeExport(RUN, before.sourceSha256());
        var service = new ResultExportService(spyJobs, document -> {
            if (!objects.containsKey(document.key())) { objects.put(document.key(), document.bytes()); puts.incrementAndGet(); }
            assertThat(document.matches(objects.get(document.key()))).isTrue();
        });
        assertThatThrownBy(() -> service.export(RUN, before.sourceSha256())).isInstanceOf(DbUnavailable.class);
        assertPending(before); assertThat(objects).hasSize(2); assertThat(businessRows()).isEqualTo(rows);
        service.export(RUN, before.sourceSha256()); assertThat(puts.get()).isEqualTo(2); assertThat(owner()).isNull();
    }

    @Test void exportedReplayVerifiesAgainWithoutChangingTimesOutboxOrTheNextJobsSlot() {
        var before = completed(CanonicalSource.fixtureBytes()); var verified = new AtomicInteger();
        var service = new ResultExportService(jobs, document -> verified.incrementAndGet());
        var exported = service.export(RUN, before.sourceSha256()); var outbox = exportOutbox(); var rows = businessRows();
        io.github.devdooly.platformlab.jobs.AdmissionTestFixtures.makeEligible(jdbc);
        var next = jobs.prepareSource(NEXT, SyntheticScenario.NAME, CanonicalSource.fixtureBytes());
        assertThat(service.export(RUN, before.sourceSha256())).isEqualTo(exported);
        assertThat(owner()).isEqualTo(NEXT); assertThat(jobs.get(NEXT)).isEqualTo(next);
        assertThat(exportOutbox()).isEqualTo(outbox); assertThat(businessRows()).isEqualTo(rows);
        assertThat(verified.get()).isEqualTo(4);
        var missing = new ResultExportService(jobs, document -> { throw new StorageUnavailable(); });
        assertThatThrownBy(() -> missing.export(RUN, before.sourceSha256())).isInstanceOf(StorageUnavailable.class);
        assertThat(jobs.get(RUN)).isEqualTo(exported); assertThat(owner()).isEqualTo(NEXT);
    }

    @Test void terminationDuringExternalIoRejectsFinalAckAndNeverReleasesTheNextSlot() {
        var before = completed(CanonicalSource.fixtureBytes()); var rows = businessRows(); var calls = new AtomicInteger();
        var service = new ResultExportService(jobs, document -> {
            assertThat(TransactionSynchronizationManager.isActualTransactionActive()).isFalse();
            if (calls.incrementAndGet() == 1) {
                jobs.terminate(RUN, before.sourceSha256());
                io.github.devdooly.platformlab.jobs.AdmissionTestFixtures.makeEligible(jdbc);
                jobs.prepareSource(NEXT, SyntheticScenario.NAME, CanonicalSource.fixtureBytes());
            }
        });
        assertThatThrownBy(() -> service.export(RUN, before.sourceSha256())).isInstanceOf(LabJobService.JobStateException.class);
        assertThat(owner()).isEqualTo(NEXT); assertThat(jobs.get(RUN).exportStatus()).isEqualTo(LabJobService.ExportStatus.CANCELLED);
        assertThat(jobs.get(RUN).exportCompletedAt()).isNull(); assertThat(exportOutbox()).containsEntry("status", "CANCELLED");
        assertThat(businessRows()).isEqualTo(rows);
    }

    @Test void outerTransactionWrongHashIncompleteAndTerminatedJobsAreRefusedBeforeStorage() {
        var store = mock(ResultExportStore.class); var service = new ResultExportService(jobs, store);
        var before = completed(CanonicalSource.fixtureBytes());
        assertThatThrownBy(() -> new TransactionTemplate(manager).execute(ignored -> service.export(RUN, before.sourceSha256())))
            .isInstanceOf(IllegalTransactionStateException.class);
        assertThatThrownBy(() -> service.export(RUN, "0".repeat(64))).isInstanceOf(LabJobService.SourceConflictException.class);
        jobs.terminate(RUN, before.sourceSha256());
        assertThatThrownBy(() -> service.export(RUN, before.sourceSha256())).isInstanceOf(LabJobService.JobStateException.class);
        io.github.devdooly.platformlab.jobs.AdmissionTestFixtures.makeEligible(jdbc);
        var next = jobs.prepareSource(NEXT, SyntheticScenario.NAME, CanonicalSource.fixtureBytes());
        assertThatThrownBy(() -> service.export(NEXT, next.sourceSha256())).isInstanceOf(LabJobService.JobStateException.class);
        verifyNoInteractions(store);
    }

    @Test void deterministicFailureDocumentContainsOriginalFailedLinesAndNoVolatileFields() {
        String[] lines = new String(CanonicalSource.fixtureBytes(), StandardCharsets.UTF_8).split("\n");
        lines[4] = "  " + lines[4] + "\t";
        byte[] source = (String.join("\r\n", lines) + "\r\n").getBytes(StandardCharsets.UTF_8);
        var before = completed(source); var bundle = ExportBundle.from(jobs.exportSnapshot(RUN, before.sourceSha256()));
        var json = JsonMapper.builder().build(); var result = json.readTree(bundle.result().bytes()); var failures = json.readTree(bundle.failures().bytes());
        assertThat(result.get("outcomes").size()).isEqualTo(12); assertThat(failures.get("failures").size()).isEqualTo(3);
        assertThat(failures.get("failures").get(0).get("rawLine").asText()).isEqualTo(lines[4]);
        assertThat(failures.get("failures").get(0).get("input").get("eventTime").asText()).isEqualTo("not-a-timestamp");
        assertThat(failures.get("failures").get(0).get("reason").asText()).isEqualTo("INVALID_TIMESTAMP");
        assertThat(failures.get("failures").get(1).get("reason").asText()).isEqualTo("OUT_OF_ORDER");
        assertThat(failures.get("failures").get(2).get("reason").asText()).isEqualTo("OUT_OF_RANGE");
        assertThat(new String(bundle.result().bytes(), StandardCharsets.UTF_8)).doesNotContain("observedAt", "exportCompletedAt");
        new ResultExportService(jobs, ignored -> {}).export(RUN, before.sourceSha256());
        var repeat = ExportBundle.from(jobs.exportSnapshot(RUN, before.sourceSha256()));
        assertThat(repeat.result().bytes()).isEqualTo(bundle.result().bytes());
        assertThat(repeat.failures().bytes()).isEqualTo(bundle.failures().bytes());
        assertThat(repeat.result().key()).isEqualTo(bundle.result().key());
        var leaked = repeat.failures().bytes(); leaked[0] ^= 1;
        assertThat(repeat.failures().bytes()).isEqualTo(bundle.failures().bytes());
    }

    @Test void fullAdmittedRawBoundOnAFailedLineStillHasABoundedLosslessExport() {
        byte[] fixture = CanonicalSource.fixtureBytes();
        String[] lines = new String(fixture, StandardCharsets.UTF_8).split("\n");
        lines[4] = " ".repeat(CanonicalSource.MAX_BYTES - fixture.length) + lines[4];
        byte[] padded = (String.join("\n", lines) + "\n").getBytes(StandardCharsets.UTF_8);
        assertThat(padded).hasSize(CanonicalSource.MAX_BYTES);
        var job = completed(padded); var bundle = ExportBundle.from(jobs.exportSnapshot(RUN, job.sourceSha256()));
        assertThat(bundle.failures().size()).isGreaterThan(CanonicalSource.MAX_BYTES).isLessThan(ExportBundle.MAX_DOCUMENT_BYTES);
        assertThat(JsonMapper.builder().build().readTree(bundle.failures().bytes()).get("failures").get(0).get("rawLine").asText()).isEqualTo(lines[4]);
    }

    @Test void inconsistentPersistedRowsFailBeforeNetworkOrSlotRelease() {
        var before = completed(CanonicalSource.fixtureBytes()); var store = mock(ResultExportStore.class);
        jdbc.update("UPDATE demo_outcome SET event_time = 'corrupted' WHERE run_id = ? AND input_sequence = 5", RUN);
        assertThatThrownBy(() -> new ResultExportService(jobs, store).export(RUN, before.sourceSha256()))
            .isInstanceOf(ExportBundle.ExportValidationException.class);
        assertPending(before); verifyNoInteractions(store);
    }

    private LabJobService.Job completed(byte[] source) {
        var prepared = jobs.prepareSource(RUN, SyntheticScenario.NAME, source);
        jobs.markSourceVerified(RUN, prepared.sourceSha256()); jobs.acknowledgeDispatch(RUN, prepared.sourceSha256());
        return jobs.process(RUN, prepared.sourceSha256());
    }
    private String owner() { return jdbc.queryForObject("SELECT occupied_run_id FROM lab_job_slot WHERE id = 1", String.class); }
    private Map<String, Object> exportOutbox() { return jdbc.queryForMap("SELECT * FROM lab_outbox WHERE job_run_id = ? AND event_type = 'EXPORT'", RUN); }
    private List<List<Map<String, Object>>> businessRows() {
        return List.of(jdbc.queryForList("SELECT * FROM demo_run WHERE id = ?", RUN), jdbc.queryForList("SELECT * FROM demo_outcome WHERE run_id = ? ORDER BY input_sequence", RUN));
    }
    private void assertPending(LabJobService.Job before) {
        assertThat(jobs.get(RUN)).isEqualTo(before); assertThat(owner()).isEqualTo(RUN);
        assertThat(exportOutbox()).containsEntry("status", "PENDING").containsEntry("acknowledged_at", null);
    }
    private static class StorageUnavailable extends RuntimeException {}
    private static class DbUnavailable extends RuntimeException {}
}
