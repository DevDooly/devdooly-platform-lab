package io.github.devdooly.platformlab.jobs.exporting;

import io.github.devdooly.platformlab.demo.SensorProcessor;
import io.github.devdooly.platformlab.demo.SyntheticScenario;
import io.github.devdooly.platformlab.jobs.CanonicalSource;
import io.github.devdooly.platformlab.jobs.LabJobService;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.HexFormat;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import tools.jackson.databind.json.JsonMapper;

/** Versioned deterministic documents, built only from a committed persisted snapshot. */
public record ExportBundle(String runId, String sourceSha256, Document result, Document failures) {
    public static final int SCHEMA_VERSION = 1;
    public static final String PROCESSOR_VERSION = "sensor-processor-v1";
    public static final int MAX_DOCUMENT_BYTES = 4_194_304;
    private static final JsonMapper JSON = JsonMapper.builder().build();

    public record Document(String key, byte[] bytes, String sha256) {
        public Document {
            Objects.requireNonNull(bytes, "Document bytes required");
            bytes = bytes.clone();
            if (bytes.length == 0 || bytes.length > MAX_DOCUMENT_BYTES || sha256 == null
                || !sha256.matches("[a-f0-9]{64}") || !sha256.equals(hash(bytes)) || key == null
                || !key.matches("result/[a-z0-9][a-z0-9._-]{0,79}/sensor-validation-v(?:1|2)/[a-f0-9]{64}/(?:result|failures)-v1-[a-f0-9]{64}\\.json")
                || !key.endsWith("-v1-" + sha256 + ".json")) {
                throw new IllegalArgumentException("Invalid bounded content-addressed export document");
            }
        }
        @Override public byte[] bytes() { return bytes.clone(); }
        public int size() { return bytes.length; }
        public boolean matches(byte[] actual) {
            return actual != null && actual.length == bytes.length && sha256.equals(hash(actual)) && Arrays.equals(bytes, actual);
        }
    }

    public static ExportBundle from(LabJobService.ExportSnapshot snapshot) {
        Objects.requireNonNull(snapshot);
        var job = snapshot.job(); var run = snapshot.run();
        var source = CanonicalSource.validate(job.scenarioVersion(), snapshot.sourceBytes());
        var expected = SyntheticScenario.expectedCounts(job.scenarioVersion());
        if (job.status() != LabJobService.Status.COMPLETED || job.terminatedAt() != null
            || (job.exportStatus() != LabJobService.ExportStatus.PENDING && job.exportStatus() != LabJobService.ExportStatus.EXPORTED)
            || !SyntheticScenario.supports(job.scenarioVersion()) || !job.scenarioVersion().equals(run.scenario())
            || run.seed() != SyntheticScenario.seed(job.scenarioVersion()) || !source.sha256().equals(job.sourceSha256()) || source.size() != job.sourceSize()
            || job.createdAt() == null || job.sourceVerifiedAt() == null || job.queuedAt() == null
            || job.completedAt() == null || run.startedAt() == null || run.completedAt() == null
            || run.completedAt().isBefore(run.startedAt()) || !job.completedAt().equals(run.completedAt())
            || run.inputCount() != expected.input() || run.successCount() != expected.success() || run.failureCount() != expected.failure()
            || run.duplicateCount() != expected.duplicate() || run.pendingCount() != expected.pending() || snapshot.outcomes().size() != run.inputCount()) {
            throw new ExportValidationException("Persisted export snapshot is not a complete admitted result");
        }
        String[] lines = new String(source.bytes(), StandardCharsets.UTF_8).split("\\r?\\n", -1);
        var failures = new ArrayList<Map<String, Object>>();
        int successes = 0, failed = 0, duplicates = 0;
        for (int index = 0; index < snapshot.outcomes().size(); index++) {
            var outcome = snapshot.outcomes().get(index); var event = source.events().get(index);
            if (outcome.sequence() != index + 1 || !Objects.equals(outcome.eventId(), event.eventId())
                || !Objects.equals(outcome.sensorId(), event.sensorId()) || !Objects.equals(outcome.eventTime(), event.eventTime())
                || !Objects.equals(outcome.value(), event.value()) || outcome.status() == null || outcome.reason() == null
                || ((outcome.status() == SensorProcessor.Status.SUCCESS) != (outcome.reason() == SensorProcessor.Reason.ACCEPTED))
                || ((outcome.status() == SensorProcessor.Status.DUPLICATE) != (outcome.reason() == SensorProcessor.Reason.DUPLICATE_EVENT_ID))) {
                throw new ExportValidationException("Persisted ordered outcome differs from its original input");
            }
            switch (outcome.status()) {
                case SUCCESS -> successes++;
                case DUPLICATE -> duplicates++;
                case FAILED -> {
                    failed++;
                    var failure = new LinkedHashMap<String, Object>();
                    failure.put("sequence", outcome.sequence()); failure.put("status", outcome.status().name());
                    failure.put("reason", outcome.reason().name());
                    failure.put("input", JSON.readValue(lines[index], LinkedHashMap.class));
                    failure.put("rawLine", lines[index]); failures.add(failure);
                }
            }
        }
        if (successes != run.successCount() || failed != run.failureCount() || duplicates != run.duplicateCount()) {
            throw new ExportValidationException("Persisted counts differ from the ordered outcomes");
        }
        var resultBody = header(snapshot, "result"); resultBody.put("outcomes", snapshot.outcomes());
        var failureBody = header(snapshot, "failures"); failureBody.put("failures", failures);
        return new ExportBundle(job.runId(), job.sourceSha256(), document(job, "result", resultBody), document(job, "failures", failureBody));
    }

    private static LinkedHashMap<String, Object> header(LabJobService.ExportSnapshot snapshot, String kind) {
        var job = snapshot.job(); var run = snapshot.run(); var body = new LinkedHashMap<String, Object>();
        body.put("schemaVersion", SCHEMA_VERSION); body.put("processorVersion", PROCESSOR_VERSION); body.put("kind", kind);
        body.put("runId", job.runId()); body.put("scenarioVersion", job.scenarioVersion()); body.put("sourceSha256", job.sourceSha256());
        body.put("sourceSize", job.sourceSize()); body.put("synthetic", true); body.put("seed", run.seed());
        body.put("jobCreatedAt", job.createdAt().toString()); body.put("sourceVerifiedAt", job.sourceVerifiedAt().toString());
        body.put("queuedAt", job.queuedAt().toString()); body.put("processingStartedAt", run.startedAt().toString());
        body.put("processingCompletedAt", run.completedAt().toString());
        var counts = new LinkedHashMap<String, Object>();
        counts.put("input", run.inputCount()); counts.put("success", run.successCount()); counts.put("failure", run.failureCount());
        counts.put("duplicate", run.duplicateCount()); counts.put("pending", run.pendingCount()); body.put("counts", counts);
        return body;
    }
    private static Document document(LabJobService.Job job, String kind, Map<String, Object> body) {
        byte[] bytes = JSON.writeValueAsBytes(body); String digest = hash(bytes);
        return new Document("result/" + job.runId() + "/" + job.scenarioVersion() + "/" + job.sourceSha256()
            + "/" + kind + "-v1-" + digest + ".json", bytes, digest);
    }
    private static String hash(byte[] bytes) {
        try { return HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(bytes)); }
        catch (NoSuchAlgorithmException impossible) { throw new IllegalStateException(impossible); }
    }
    public static final class ExportValidationException extends IllegalStateException {
        public ExportValidationException(String message) { super(message); }
    }
}
