package io.github.devdooly.platformlab.jobs.runtime;

import io.github.devdooly.platformlab.jobs.LabJobService;
import io.github.devdooly.platformlab.jobs.exporting.ResultExportService;
import io.github.devdooly.platformlab.jobs.messaging.DispatchPublisher;
import io.github.devdooly.platformlab.jobs.messaging.DispatchWorker;
import java.time.Duration;
import java.util.Objects;

/** The production actions shared by the explicit CLI and isolated process verification. */
public final class JobRuntimeActions implements ContinuousJobRunner.Actions {
    private final LabJobService jobs;
    private final DispatchPublisher publisher;
    private final DispatchWorker worker;
    private final ResultExportService exporter;
    public JobRuntimeActions(LabJobService jobs, DispatchPublisher publisher, DispatchWorker worker, ResultExportService exporter) {
        this.jobs = Objects.requireNonNull(jobs); this.publisher = Objects.requireNonNull(publisher);
        this.worker = Objects.requireNonNull(worker); this.exporter = Objects.requireNonNull(exporter);
    }
    @Override public boolean exportOne() {
        var pending = jobs.pendingOutbox(100).stream().filter(event -> event.eventType() == LabJobService.EventType.EXPORT).findFirst();
        if (pending.isEmpty()) { return false; }
        var event = pending.get(); exporter.export(event.runId(), event.sourceSha256()); return true;
    }
    @Override public boolean publishOne() throws Exception { return publisher.publishOne().isPresent(); }
    @Override public boolean receiveOne(Duration pollTimeout) { return worker.receiveOne(pollTimeout).isPresent(); }
}
