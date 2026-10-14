package io.github.devdooly.platformlab.jobs;

/** Internal durable-byte boundary; implementations must verify exact bytes before returning. */
@FunctionalInterface
public interface RawSourceStore {
    void storeAndVerify(LabJobService.Job job, byte[] rawNdjson);
}
