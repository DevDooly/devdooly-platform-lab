package io.github.devdooly.platformlab.jobs;

import java.util.Objects;
import org.springframework.transaction.IllegalTransactionStateException;
import org.springframework.transaction.support.TransactionSynchronizationManager;

/**
 * Explicit internal coordinator, intentionally not a bean, controller, scheduler or worker.
 * Each LabJobService transaction finishes before external I/O starts; only verified bytes may
 * cause the final short DB transaction to create DISPATCH intent.
 */
public final class SourceStagingService {
    private final LabJobService jobs;
    private final RawSourceStore sources;

    public SourceStagingService(LabJobService jobs, RawSourceStore sources) {
        this.jobs = Objects.requireNonNull(jobs);
        this.sources = Objects.requireNonNull(sources);
    }

    public LabJobService.Job stage(String runId, String scenarioVersion, byte[] rawNdjson) {
        if (TransactionSynchronizationManager.isActualTransactionActive()) {
            throw new IllegalTransactionStateException("Source staging must not run inside an outer database transaction");
        }
        // Clone/validate before DB admission so caller mutation cannot change the bytes later.
        var source = CanonicalSource.validate(scenarioVersion, rawNdjson);
        var prepared = jobs.prepareSource(runId, scenarioVersion, source.bytes());
        if (prepared.status() == LabJobService.Status.TERMINATED || prepared.terminatedAt() != null) {
            throw new LabJobService.JobStateException();
        }
        sources.storeAndVerify(prepared, source.bytes());
        return jobs.markSourceVerified(runId, source.sha256());
    }
}
