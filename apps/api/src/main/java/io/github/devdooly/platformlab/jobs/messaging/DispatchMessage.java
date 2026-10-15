package io.github.devdooly.platformlab.jobs.messaging;

import io.github.devdooly.platformlab.demo.SyntheticScenario;
import io.github.devdooly.platformlab.jobs.LabJobService;
import java.util.Objects;
import tools.jackson.core.StreamReadFeature;
import tools.jackson.core.json.JsonFactory;
import tools.jackson.databind.DeserializationFeature;
import tools.jackson.databind.json.JsonMapper;

/** Small, versioned run-batch envelope; the source object key comes from the immutable DB job. */
public record DispatchMessage(int schemaVersion, String runId, String scenarioVersion, String sourceSha256) {
    public static final int VERSION = 1;
    public static final int MAX_BYTES = 1024;
    private static final JsonMapper JSON = JsonMapper.builder(JsonFactory.builder()
        .enable(StreamReadFeature.STRICT_DUPLICATE_DETECTION).build())
        .enable(DeserializationFeature.FAIL_ON_TRAILING_TOKENS).build();

    public DispatchMessage {
        if (schemaVersion != VERSION || runId == null || !runId.matches("[a-z0-9][a-z0-9._-]{0,79}")
            || !SyntheticScenario.supports(scenarioVersion)
            || sourceSha256 == null || !sourceSha256.matches("[0-9a-f]{64}")) {
            throw new IllegalArgumentException("Unsupported dispatch envelope");
        }
    }

    public static DispatchMessage from(LabJobService.Job job) {
        Objects.requireNonNull(job, "job");
        return new DispatchMessage(VERSION, job.runId(), job.scenarioVersion(), job.sourceSha256());
    }

    public String encode() {
        // Constructor validation restricts every string to unescaped ASCII identifiers.
        return "{\"schemaVersion\":" + VERSION + ",\"runId\":\"" + runId + "\",\"scenarioVersion\":\""
            + scenarioVersion + "\",\"sourceSha256\":\"" + sourceSha256 + "\"}";
    }

    public static DispatchMessage decode(String input) {
        if (input == null || input.isEmpty() || input.length() > MAX_BYTES
            || input.chars().anyMatch(character -> character > 0x7f)) {
            throw new IllegalArgumentException("Dispatch must be at most 1024 ASCII JSON bytes");
        }
        try {
            var node = JSON.readTree(input);
            if (node == null || !node.isObject() || node.size() != 4
                || node.get("schemaVersion") == null || !node.get("schemaVersion").isIntegralNumber()
                || !node.get("schemaVersion").canConvertToInt()
                || node.get("runId") == null || !node.get("runId").isTextual()
                || node.get("scenarioVersion") == null || !node.get("scenarioVersion").isTextual()
                || node.get("sourceSha256") == null || !node.get("sourceSha256").isTextual()) {
                throw new IllegalArgumentException("Dispatch must contain exactly four correctly typed fields");
            }
            return new DispatchMessage(node.get("schemaVersion").asInt(), node.get("runId").asText(),
                node.get("scenarioVersion").asText(), node.get("sourceSha256").asText());
        } catch (IllegalArgumentException failure) { throw failure; }
        catch (Exception failure) { throw new IllegalArgumentException("Dispatch must be strict JSON", failure); }
    }
}
