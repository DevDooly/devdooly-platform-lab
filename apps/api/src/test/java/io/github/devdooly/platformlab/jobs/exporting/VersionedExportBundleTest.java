package io.github.devdooly.platformlab.jobs.exporting;

import io.github.devdooly.platformlab.demo.SensorProcessor;
import io.github.devdooly.platformlab.demo.SyntheticScenario;
import io.github.devdooly.platformlab.jobs.CanonicalSource;
import io.github.devdooly.platformlab.jobs.LabJobService;
import java.nio.charset.StandardCharsets;
import java.time.Instant;
import org.junit.jupiter.api.Test;
import tools.jackson.databind.json.JsonMapper;
import static org.assertj.core.api.Assertions.*;

class VersionedExportBundleTest {
    @Test void versionOneDocumentsAndKeysKeepThePreChangeFingerprints() {
        var bundle = ExportBundle.from(snapshot("sensor-validation-v1", CanonicalSource.fixtureBytes()));
        assertThat(bundle.result().size()).isEqualTo(2327);
        assertThat(bundle.result().sha256()).isEqualTo("813e57b26ef428bc393048505bb7dad28e3e4fafa47288cc57e613768b8b2753");
        assertThat(bundle.failures().size()).isEqualTo(1386);
        assertThat(bundle.failures().sha256()).isEqualTo("851acc7b4ff43c868288b6b58e27b6a6df10aac3160dffc48e58075c251aeab4");
        assertThat(bundle.result().key()).isEqualTo("result/compatibility-v1/sensor-validation-v1/39ba10d8c47dce790f3ccc9c9134fea593d6de31f1f3a7992ca61d9f554da3b5/result-v1-813e57b26ef428bc393048505bb7dad28e3e4fafa47288cc57e613768b8b2753.json");
        assertThat(bundle.failures().key()).endsWith("/failures-v1-851acc7b4ff43c868288b6b58e27b6a6df10aac3160dffc48e58075c251aeab4.json");
    }

    @Test void maximumScenarioProducesVersionOneDocumentsWithThousandOrderedOutcomesAndThreeHundredFailures() {
        var bundle = ExportBundle.from(snapshot(SyntheticScenario.MAXIMUM_NAME, CanonicalSource.fixtureBytes(SyntheticScenario.MAXIMUM_NAME)));
        var json = JsonMapper.builder().build(); var result = json.readTree(bundle.result().bytes()); var failures = json.readTree(bundle.failures().bytes());
        assertThat(result.get("schemaVersion").asInt()).isEqualTo(1);
        assertThat(result.get("scenarioVersion").asText()).isEqualTo("sensor-validation-v2");
        assertThat(result.get("outcomes").size()).isEqualTo(1000); assertThat(failures.get("failures").size()).isEqualTo(300);
        assertThat(result.get("counts").get("success").asInt()).isEqualTo(500);
        assertThat(result.get("counts").get("duplicate").asInt()).isEqualTo(200);
        assertThat(bundle.result().key()).contains("/sensor-validation-v2/").contains("/result-v1-");
        assertThat(bundle.result().size()).isLessThan(ExportBundle.MAX_DOCUMENT_BYTES);
        assertThat(bundle.failures().size()).isLessThan(ExportBundle.MAX_DOCUMENT_BYTES);
    }

    @Test void exactlyOneMiBSourceOnFailedLineExportsLosslesslyBelowFourMiB() {
        byte[] raw = CanonicalSource.fixtureBytes(SyntheticScenario.MAXIMUM_NAME);
        String[] lines = new String(raw, StandardCharsets.UTF_8).split("\n");
        lines[3] = " ".repeat(CanonicalSource.MAX_BYTES - raw.length) + lines[3];
        byte[] padded = (String.join("\n", lines) + "\n").getBytes(StandardCharsets.UTF_8);
        assertThat(padded).hasSize(CanonicalSource.MAX_BYTES);
        var bundle = ExportBundle.from(snapshot(SyntheticScenario.MAXIMUM_NAME, padded));
        assertThat(bundle.failures().size()).isGreaterThan(lines[3].length()).isLessThan(ExportBundle.MAX_DOCUMENT_BYTES);
        var failures = JsonMapper.builder().build().readTree(bundle.failures().bytes());
        assertThat(failures.get("failures").get(0).get("rawLine").asText()).isEqualTo(lines[3]);
    }

    private LabJobService.ExportSnapshot snapshot(String scenario, byte[] raw) {
        var source = CanonicalSource.validate(scenario, raw); var result = new SensorProcessor().process(source.events());
        var created = Instant.parse("2026-01-02T00:00:00Z"); var verified = created.plusSeconds(1);
        var started = created.plusSeconds(2); var completed = created.plusSeconds(3);
        var job = new LabJobService.Job("compatibility-v1", scenario, source.sha256(), source.size(),
            LabJobService.Status.COMPLETED, LabJobService.ExportStatus.PENDING, created, verified, verified, completed, null, null);
        var run = new LabJobService.ExportRun(scenario, SyntheticScenario.seed(scenario), result.inputCount(), result.successCount(), result.failureCount(), result.duplicateCount(), 0, started, completed);
        return new LabJobService.ExportSnapshot(job, raw, run, result.outcomes());
    }
}
