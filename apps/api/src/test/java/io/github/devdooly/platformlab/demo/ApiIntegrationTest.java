package io.github.devdooly.platformlab.demo;

import java.net.URI;
import java.net.http.*;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.test.context.ActiveProfiles;
import tools.jackson.databind.JsonNode;
import tools.jackson.databind.json.JsonMapper;
import static org.assertj.core.api.Assertions.*;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@ActiveProfiles("test")
class ApiIntegrationTest {
    @LocalServerPort int port;
    @Autowired DemoService demos;
    @Autowired DemoRunRepository runs;
    @Autowired DemoOutcomeRepository outcomes;
    private final HttpClient client = HttpClient.newHttpClient();
    private final JsonMapper json = JsonMapper.builder().build();
    @Test void listAndDetailExposePersistedCountsAndSevenChartPoints() throws Exception {
        var list = get("/api/demo/runs");
        assertThat(list.statusCode()).isEqualTo(200);
        var items = json.readTree(list.body()).get("items");
        assertThat(items.size()).isEqualTo(1); assertThat(items.get(0).get("inputCount").asInt()).isEqualTo(12);
        var detail = json.readTree(get("/api/demo/runs/" + SyntheticScenario.RUN_ID).body());
        assertThat(detail.get("successCount").asInt()).isEqualTo(7); assertThat(detail.get("failureCount").asInt()).isEqualTo(3);
        assertThat(detail.get("duplicateCount").asInt()).isEqualTo(2); assertThat(detail.get("pendingCount").asInt()).isZero();
        assertThat(detail.get("outcomes").size()).isEqualTo(12); assertThat(detail.get("series").size()).isEqualTo(7);
        assertThat(detail.get("failureReasons").size()).isEqualTo(3); assertThat(detail.get("synthetic").asBoolean()).isTrue();
        assertThat(detail.get("observedAt").asText()).endsWith("Z");
    }
    @Test void bootstrapIsIdempotent() {
        long runCount = runs.count(), outcomeCount = outcomes.count();
        demos.ensureSample(); demos.ensureSample();
        assertThat(runs.count()).isEqualTo(runCount); assertThat(outcomes.count()).isEqualTo(outcomeCount); assertThat(outcomeCount).isEqualTo(12);
    }
    @Test void unknownRunReturnsStructured404() throws Exception {
        var response = get("/api/demo/runs/missing"); assertThat(response.statusCode()).isEqualTo(404);
        assertThat(json.readTree(response.body()).get("code").asText()).isEqualTo("RUN_NOT_FOUND");
    }
    @Test void publicPostCannotCreateRuns() throws Exception {
        var response = client.send(HttpRequest.newBuilder(uri("/api/demo/runs")).POST(HttpRequest.BodyPublishers.ofString("{}")).header("Content-Type", "application/json").build(), HttpResponse.BodyHandlers.ofString());
        assertThat(response.statusCode()).isEqualTo(405); assertThat(runs.count()).isEqualTo(1);
    }
    @Test void summaryDoesNotInventCiOrDeploymentState() throws Exception {
        JsonNode summary = json.readTree(get("/api/platform/summary").body());
        assertThat(summary.get("sourceCommit").asText()).isEqualTo("unknown"); assertThat(summary.get("publicExecutionEnabled").asBoolean()).isFalse();
        for (var component : summary.get("components")) {
            if (java.util.Set.of("JENKINS", "ARGO_CD", "KUBERNETES").contains(component.get("name").asText())) { assertThat(component.get("status").asText()).isEqualTo("NOT_CONFIGURED"); }
        }
        assertThat(summary.toString()).contains("H2 (local validation only)");
        var release = json.readTree(get("/api/platform/releases").body()).get("items").get(0);
        assertThat(release.get("deploymentStatus").asText()).isEqualTo("LOCAL_RUNTIME"); assertThat(release.get("imageDigest").isNull()).isTrue();
    }
    @Test void healthAndReadinessCheckDatabase() throws Exception {
        assertThat(get("/actuator/health").statusCode()).isEqualTo(200);
        assertThat(json.readTree(get("/actuator/health/readiness").body()).get("status").asText()).isEqualTo("UP");
    }
    private URI uri(String path) { return URI.create("http://127.0.0.1:" + port + path); }
    private HttpResponse<String> get(String path) throws Exception { return client.send(HttpRequest.newBuilder(uri(path)).GET().build(), HttpResponse.BodyHandlers.ofString()); }
}
