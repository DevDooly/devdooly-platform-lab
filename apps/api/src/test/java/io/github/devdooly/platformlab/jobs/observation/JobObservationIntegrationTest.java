package io.github.devdooly.platformlab.jobs.observation;

import io.github.devdooly.platformlab.demo.SyntheticScenario;
import io.github.devdooly.platformlab.jobs.LabJobService;
import io.github.devdooly.platformlab.jobs.exporting.ExportBundle;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.sql.Timestamp;
import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;
import java.util.Calendar;
import java.util.HashSet;
import java.util.Set;
import java.util.TimeZone;
import org.apache.kafka.clients.consumer.Consumer;
import org.apache.kafka.clients.producer.Producer;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.context.ApplicationContext;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.transaction.PlatformTransactionManager;
import software.amazon.awssdk.services.s3.S3Client;
import tools.jackson.databind.JsonNode;
import tools.jackson.databind.json.JsonMapper;
import static org.assertj.core.api.Assertions.*;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT, properties = {
    "spring.datasource.url=jdbc:h2:mem:job_observation_tests;MODE=MariaDB;DATABASE_TO_LOWER=TRUE;DB_CLOSE_DELAY=-1",
    "lab.source-commit=unknown", "lab.environment=test"
})
@ActiveProfiles("test")
class JobObservationIntegrationTest {
    @Autowired JdbcTemplate jdbc;
    @Autowired LabJobService jobs;
    @Autowired PlatformTransactionManager transactions;
    @Autowired ApplicationContext context;
    @LocalServerPort int port;
    private final HttpClient client = HttpClient.newHttpClient();
    private final JsonMapper json = JsonMapper.builder().build();

    @BeforeEach void cleanOwnedDatabase() {
        jdbc.update("UPDATE lab_job_slot SET occupied_run_id = NULL WHERE id = 1");
        jdbc.update("DELETE FROM lab_outbox"); jdbc.update("DELETE FROM lab_job");
        jdbc.update("DELETE FROM demo_outcome"); jdbc.update("DELETE FROM demo_run");
        jdbc.update("UPDATE lab_runtime SET status = 'NOT_STARTED', stage = 'IDLE', failure_code = NULL, started_at = NULL, heartbeat_at = NULL, stopped_at = NULL, source_commit = 'unknown' WHERE id = 1");
        io.github.devdooly.platformlab.jobs.AdmissionTestFixtures.makeEligible(jdbc);
    }

    @Test void defaultHttpDoesNotCreateKafkaS3OrRuntimeAndHasNoPublicWrite() throws Exception {
        String before = jdbc.queryForObject("SELECT status FROM lab_runtime WHERE id = 1", String.class);
        var response = get(); var document = json.readTree(response.body());
        assertThat(response.statusCode()).isEqualTo(200);
        assertThat(response.headers().firstValue("Cache-Control")).contains("no-store");
        assertThat(document.get("runtime").get("status").asText()).isEqualTo("NOT_STARTED");
        assertThat(document.get("jobs").size()).isZero(); assertThat(document.get("slot").get("occupiedRunId").isNull()).isTrue();
        assertThat(document.get("capturedAt").asText()).endsWith("Z");
        assertThat(document.get("sourceCommit").asText()).isEqualTo("unknown");
        assertThat(document.get("environment").asText()).isEqualTo("TEST");
        assertThat(document.get("scope").asText()).isEqualTo("LOCAL_VALIDATION");
        assertThat(document.get("publicExecutionEnabled").asBoolean()).isFalse();
        assertThat(context.getBeansOfType(Producer.class)).isEmpty();
        assertThat(context.getBeansOfType(Consumer.class)).isEmpty();
        assertThat(context.getBeansOfType(S3Client.class)).isEmpty();
        var post = client.send(HttpRequest.newBuilder(uri()).POST(HttpRequest.BodyPublishers.ofString("{}")).build(), HttpResponse.BodyHandlers.ofString());
        assertThat(post.statusCode()).isEqualTo(405);
        assertThat(jdbc.queryForObject("SELECT status FROM lab_runtime WHERE id = 1", String.class)).isEqualTo(before);
        assertThat(jdbc.queryForObject("SELECT COUNT(*) FROM lab_job", Long.class)).isZero();
        assertKeys(document, "schemaVersion", "kind", "capturedAt", "environment", "sourceCommit", "synthetic", "scope", "publicExecutionEnabled", "runtime", "slot", "jobs");
        assertKeys(document.get("runtime"), "status", "stage", "failureCode", "startedAt", "heartbeatAt", "stoppedAt", "sourceCommit", "stale");
        assertKeys(document.get("slot"), "occupiedRunId");
    }

    @Test void queuedPendingExportedEvidenceComesFromCommittedDbAndNeverExposesDocumentBytesOrKeys() throws Exception {
        var prepared = jobs.prepareSource("observe-one", SyntheticScenario.NAME, sourceBytes());
        jobs.markSourceVerified(prepared.runId(), prepared.sourceSha256());
        var queued = json.readTree(get().body()).get("jobs").get(0);
        assertThat(queued.get("status").asText()).isEqualTo("QUEUED");
        assertThat(queued.get("counts").isNull()).isTrue(); assertThat(queued.get("files").isNull()).isTrue();
        jobs.process(prepared.runId(), prepared.sourceSha256());
        var expected = ExportBundle.from(jobs.exportSnapshot(prepared.runId(), prepared.sourceSha256()));
        var pending = json.readTree(get().body()); var pendingJob = pending.get("jobs").get(0);
        assertThat(pendingJob.get("fileEvidence").asText()).isEqualTo("EXPECTED_FROM_DB");
        assertThat(pendingJob.get("files").get("result").get("sha256").asText()).isEqualTo(expected.result().sha256());
        assertThat(pendingJob.get("files").get("failures").get("size").asInt()).isEqualTo(expected.failures().size());
        assertThat(pendingJob.get("counts").get("input").asInt()).isEqualTo(12);
        assertThat(pending.get("slot").get("occupiedRunId").asText()).isEqualTo(prepared.runId());
        // This test drives the internal acknowledgement boundary; actual storage verification belongs to opt-in IT.
        jobs.completeExport(prepared.runId(), prepared.sourceSha256());
        var exportedResponse = get(); var exported = json.readTree(exportedResponse.body()); var job = exported.get("jobs").get(0);
        assertThat(job.get("fileEvidence").asText()).isEqualTo("VERIFIED_AT_EXPORT_COMMIT");
        assertThat(job.get("exportCompletedAt").isNull()).isFalse();
        assertThat(job.get("files")).isEqualTo(pendingJob.get("files"));
        assertThat(exported.get("slot").get("occupiedRunId").isNull()).isTrue();
        assertThat(exportedResponse.body()).doesNotContain("source_bytes", "sourceSha256", "objectKey", "bucket", "rawLine", "sensorId", "eventId", "password", "endpoint");
        assertKeys(job, "runId", "status", "exportStatus", "createdAt", "sourceVerifiedAt", "queuedAt", "completedAt", "exportCompletedAt", "terminatedAt", "counts", "files", "fileEvidence");
        assertKeys(job.get("files"), "result", "failures");
        assertKeys(job.get("files").get("result"), "sha256", "size");
        assertKeys(job.get("counts"), "input", "success", "failure", "duplicate", "pending");
    }

    @Test void cancelledCompletedJobDoesNotClaimVerifiedFilesAndNextSlotOwnerRemainsVisible() throws Exception {
        var job = jobs.prepareSource("observe-cancel", SyntheticScenario.NAME, sourceBytes());
        jobs.markSourceVerified(job.runId(), job.sourceSha256()); jobs.process(job.runId(), job.sourceSha256()); jobs.terminate(job.runId(), job.sourceSha256());
        io.github.devdooly.platformlab.jobs.AdmissionTestFixtures.makeEligible(jdbc);
        jobs.prepareSource("observe-next", SyntheticScenario.NAME, sourceBytes());
        var document = json.readTree(get().body());
        assertThat(document.get("slot").get("occupiedRunId").asText()).isEqualTo("observe-next");
        JsonNode cancelled = null;
        for (JsonNode row : document.get("jobs")) { if (row.get("runId").asText().equals(job.runId())) cancelled = row; }
        assertThat(cancelled).isNotNull(); assertThat(cancelled.get("exportStatus").asText()).isEqualTo("CANCELLED");
        assertThat(cancelled.get("files").isNull()).isTrue(); assertThat(cancelled.get("fileEvidence").asText()).isEqualTo("NOT_AVAILABLE");
        assertThat(cancelled.get("counts").get("failure").asInt()).isEqualTo(3);
    }

    @Test void latestListIsBoundedAndDoesNotMutatePastJobRows() throws Exception {
        for (int index = 0; index < 23; index++) {
            io.github.devdooly.platformlab.jobs.AdmissionTestFixtures.makeEligible(jdbc);
            var job = jobs.prepareSource("observe-bounded-" + String.format("%02d", index), SyntheticScenario.NAME, sourceBytes());
            jobs.terminate(job.runId(), job.sourceSha256());
        }
        var response = json.readTree(get().body());
        assertThat(response.get("jobs").size()).isEqualTo(20);
        assertThat(jdbc.queryForObject("SELECT COUNT(*) FROM lab_job", Long.class)).isEqualTo(23);
        assertThat(jdbc.queryForObject("SELECT COUNT(*) FROM lab_job WHERE status = 'TERMINATED'", Long.class)).isEqualTo(23);
    }

    @Test void staleHeartbeatDoesNotRewritePersistedRunningStateAndFailureCodesAreAllowlisted() {
        Instant now = Instant.parse("2026-10-15T10:00:00Z");
        writeRuntime("RUNNING", "CONSUME", null, now.minusSeconds(301));
        var service = new JobObservationService(jdbc, transactions, Clock.fixed(now, ZoneOffset.UTC), "isolated-lab", "a".repeat(40));
        var stale = service.capture();
        assertThat(stale.runtime().stale()).isTrue(); assertThat(stale.runtime().status()).isEqualTo("RUNNING");
        assertThat(stale.scope()).isEqualTo("ISOLATED_LAB");
        writeRuntime("RUNNING", "EXPORT", null, now.minusSeconds(300));
        assertThat(service.capture().runtime().stale()).isFalse();
        writeRuntime("PAUSED_OPERATOR", "STOPPED", "RESOURCE_CLOSE_FAILED", now);
        assertThat(service.capture().runtime().failureCode()).isEqualTo("RESOURCE_CLOSE_FAILED");
        writeRuntime("PAUSED_OPERATOR", "EXPORT", "EXPORT_FAILED", now);
        assertThat(service.capture().runtime().failureCode()).isEqualTo("EXPORT_FAILED");
        assertThat(service.capture().runtime().stale()).isFalse();
    }

    @Test void invalidPersistedSnapshotReturnsFixed503WithoutRawErrorOrFakeSuccess() throws Exception {
        var job = jobs.prepareSource("observe-invalid", SyntheticScenario.NAME, sourceBytes());
        jobs.markSourceVerified(job.runId(), job.sourceSha256()); jobs.process(job.runId(), job.sourceSha256());
        jdbc.update("UPDATE demo_outcome SET event_id = 'private-test-marker' WHERE run_id = ? AND input_sequence = 1", job.runId());
        var response = get(); var body = json.readTree(response.body());
        assertThat(response.statusCode()).isEqualTo(503);
        assertKeys(body, "schemaVersion", "kind", "code");
        assertThat(body.get("code").asText()).isEqualTo("OBSERVATION_UNAVAILABLE");
        assertThat(response.body()).doesNotContain("private-test-marker", "source_bytes", "SELECT", "jdbc", "capturedAt", "files");
        assertThat(jobs.get(job.runId()).exportStatus()).isEqualTo(LabJobService.ExportStatus.PENDING);
        assertThat(jdbc.queryForObject("SELECT occupied_run_id FROM lab_job_slot WHERE id = 1", String.class)).isEqualTo(job.runId());
    }

    @Test void invalidRuntimeRelationsFailClosedWithoutRewritingJournal() throws Exception {
        jdbc.update("UPDATE lab_runtime SET status = 'RUNNING', stage = 'CONSUME' WHERE id = 1");
        var response = get();
        assertThat(response.statusCode()).isEqualTo(503);
        assertThat(json.readTree(response.body()).get("code").asText()).isEqualTo("OBSERVATION_UNAVAILABLE");
        assertThat(jdbc.queryForObject("SELECT status FROM lab_runtime WHERE id = 1", String.class)).isEqualTo("RUNNING");
        assertThat(jdbc.queryForObject("SELECT heartbeat_at FROM lab_runtime WHERE id = 1", Timestamp.class)).isNull();
    }

    @Test void oversizedStoredSourceIsRejectedBeforeBuildingFileEvidence() throws Exception {
        var job = jobs.prepareSource("observe-oversize", SyntheticScenario.NAME, sourceBytes());
        jobs.markSourceVerified(job.runId(), job.sourceSha256()); jobs.process(job.runId(), job.sourceSha256());
        jdbc.update("UPDATE lab_job SET source_bytes = ? WHERE run_id = ?", new byte[1_048_577], job.runId());
        var response = get();
        assertThat(response.statusCode()).isEqualTo(503);
        assertThat(response.body()).doesNotContain("files", "source_bytes", "capturedAt");
        assertThat(jobs.get(job.runId()).exportStatus()).isEqualTo(LabJobService.ExportStatus.PENDING);
    }

    private void writeRuntime(String status, String stage, String failureCode, Instant heartbeat) {
        jdbc.update("UPDATE lab_runtime SET status = ?, stage = ?, failure_code = ?, started_at = ?, heartbeat_at = ?, stopped_at = ?, source_commit = ? WHERE id = 1", ps -> {
            var utc = Calendar.getInstance(TimeZone.getTimeZone("UTC"));
            ps.setString(1, status); ps.setString(2, stage); ps.setString(3, failureCode);
            ps.setTimestamp(4, Timestamp.from(heartbeat.minusSeconds(10)), utc); ps.setTimestamp(5, Timestamp.from(heartbeat), utc);
            ps.setTimestamp(6, failureCode == null ? null : Timestamp.from(heartbeat), utc); ps.setString(7, "a".repeat(40));
        });
    }
    private static byte[] sourceBytes() { return SyntheticScenario.events().stream().map(event -> JsonMapper.builder().build().writeValueAsString(event))
        .collect(java.util.stream.Collectors.joining("\n", "", "\n")).getBytes(StandardCharsets.UTF_8); }
    private static void assertKeys(JsonNode node, String... keys) {
        Set<String> actual = new HashSet<>(); node.propertyNames().forEach(actual::add); assertThat(actual).containsExactlyInAnyOrder(keys);
    }
    private URI uri() { return URI.create("http://127.0.0.1:" + port + "/api/jobs/observation"); }
    private HttpResponse<String> get() throws Exception { return client.send(HttpRequest.newBuilder(uri()).GET().build(), HttpResponse.BodyHandlers.ofString()); }
}
