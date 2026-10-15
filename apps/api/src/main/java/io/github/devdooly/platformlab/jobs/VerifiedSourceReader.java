package io.github.devdooly.platformlab.jobs;

/** GET-only source retrieval; absence or corruption must never recreate the object. */
@FunctionalInterface
public interface VerifiedSourceReader {
    byte[] readAndVerify(LabJobService.Job job);
}
