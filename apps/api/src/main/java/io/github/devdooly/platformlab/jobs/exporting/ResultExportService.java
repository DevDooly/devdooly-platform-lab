package io.github.devdooly.platformlab.jobs.exporting;

import io.github.devdooly.platformlab.jobs.LabJobService;
import java.util.Objects;
import java.util.function.Consumer;
import org.springframework.transaction.IllegalTransactionStateException;
import org.springframework.transaction.support.TransactionSynchronizationManager;

/** Explicit internal coordinator only. Two verified documents precede the final short DB ack. */
public final class ResultExportService {
    private final LabJobService jobs;
    private final ResultExportStore store;
    private final Consumer<ExportBundle.Document> afterDocumentVerified;
    private final Consumer<ExportBundle> beforeDbCompletion;
    public ResultExportService(LabJobService jobs, ResultExportStore store) {
        this(jobs, store, ignored -> {}, ignored -> {});
    }
    ResultExportService(LabJobService jobs, ResultExportStore store,
                        Consumer<ExportBundle.Document> afterDocumentVerified, Consumer<ExportBundle> beforeDbCompletion) {
        this.jobs = Objects.requireNonNull(jobs); this.store = Objects.requireNonNull(store);
        this.afterDocumentVerified = Objects.requireNonNull(afterDocumentVerified);
        this.beforeDbCompletion = Objects.requireNonNull(beforeDbCompletion);
    }
    public LabJobService.Job export(String runId, String sourceSha256) {
        if (TransactionSynchronizationManager.isActualTransactionActive()) {
            throw new IllegalTransactionStateException("Result export must not run inside an outer database transaction");
        }
        var bundle = ExportBundle.from(jobs.exportSnapshot(runId, sourceSha256));
        // An EXPORTED replay also verifies both objects; DB timestamps and a later job slot stay unchanged.
        store.storeAndVerify(bundle.result()); afterDocumentVerified.accept(bundle.result());
        store.storeAndVerify(bundle.failures()); afterDocumentVerified.accept(bundle.failures());
        beforeDbCompletion.accept(bundle);
        return jobs.completeExport(runId, sourceSha256);
    }
}
