package io.github.devdooly.platformlab.jobs.exporting;

/** Return only after a full bounded GET matches this document's bytes, size and SHA-256. */
@FunctionalInterface
public interface ResultExportStore {
    void storeAndVerify(ExportBundle.Document document);
}
