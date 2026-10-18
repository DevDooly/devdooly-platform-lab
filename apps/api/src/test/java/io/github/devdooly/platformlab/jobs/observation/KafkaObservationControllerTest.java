package io.github.devdooly.platformlab.jobs.observation;

import jakarta.servlet.ReadListener;
import jakarta.servlet.ServletInputStream;
import jakarta.servlet.http.HttpServletRequest;
import java.net.InetSocketAddress;
import java.net.URI;
import java.net.Socket;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.time.Instant;
import java.util.HashSet;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Set;
import java.util.concurrent.atomic.AtomicInteger;
import org.apache.kafka.clients.admin.Admin;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.context.ApplicationContext;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import tools.jackson.databind.JsonNode;
import tools.jackson.databind.json.JsonMapper;
import static org.assertj.core.api.Assertions.*;
import static org.mockito.Mockito.*;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT, properties = {
    "spring.datasource.url=jdbc:h2:mem:kafka_observation_controller;MODE=MariaDB;DATABASE_TO_LOWER=TRUE;DB_CLOSE_DELAY=-1",
    "lab.source-commit=aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa", "lab.environment=test"
})
@ActiveProfiles("test")
class KafkaObservationControllerTest {
    @MockitoBean KafkaObservationService observations;
    @Autowired KafkaObservationSettings settings;
    @Autowired JdbcTemplate jdbc;
    @Autowired ApplicationContext context;
    @LocalServerPort int port;
    private final HttpClient client = HttpClient.newHttpClient();
    private final JsonMapper json = JsonMapper.builder().build();

    @BeforeEach void defaultUnavailable() {
        reset(observations);
        doThrow(KafkaObservationService.failure(KafkaObservationService.Code.NOT_CONFIGURED)).when(observations).capture();
    }
    URI uri(String suffix) { return URI.create("http://127.0.0.1:" + port + "/api/kafka/observation" + suffix); }
    HttpResponse<String> send(HttpRequest request) throws Exception { return client.send(request, HttpResponse.BodyHandlers.ofString()); }
    static Set<String> keys(JsonNode node) { var keys = new HashSet<String>(); node.propertyNames().forEach(keys::add); return keys; }

    @Test void defaultIsDisabledAndEveryFixedFailureIsNoStoreWithExactThreeFields() throws Exception {
        assertThat(settings.enabled()).isFalse(); assertThat(context.getBeansOfType(Admin.class)).isEmpty();
        for (var code : KafkaObservationService.Code.values()) {
            doThrow(KafkaObservationService.failure(code)).when(observations).capture();
            var response = send(HttpRequest.newBuilder(uri("")).GET().build());
            assertThat(response.statusCode()).as("fixed failure %s", code).isEqualTo(503);
            assertThat(response.headers().firstValue("Cache-Control")).contains("no-store");
            var value = json.readTree(response.body());
            assertThat(keys(value)).containsExactlyInAnyOrder("schemaVersion", "kind", "code");
            assertThat(value.get("schemaVersion").asInt()).isEqualTo(1);
            assertThat(value.get("kind").asText()).isEqualTo("kafka-observation-error");
            assertThat(value.get("code").asText()).isEqualTo(code.name());
            assertThat(response.body()).doesNotContain("bootstrap", "topic", "password", "trace", "exception", "127.0.0.1");
        }
    }

    @Test void successPublishesOnlyTheEighteenFieldBrokerContract() throws Exception {
        var now = Instant.parse("2026-10-18T00:00:00Z");
        var record = new KafkaObservationService.Observation(1, "kafka-observation", true, "ISOLATED_LAB", "ISOLATED_KAFKA", false,
            "a".repeat(40), now, now.plusMillis(20), "BOUNDED_SEQUENTIAL_READ", "b".repeat(64), "STABLE", 0, "NO_COMMIT", 0, 3, null, null);
        doReturn(record).when(observations).capture();
        var response = send(HttpRequest.newBuilder(uri("")).GET().build());
        assertThat(response.statusCode()).isEqualTo(200); assertThat(response.headers().firstValue("Cache-Control")).contains("no-store");
        var value = json.readTree(response.body());
        assertThat(keys(value)).containsExactlyInAnyOrder("schemaVersion", "kind", "synthetic", "environment", "scope", "publicExecutionEnabled",
            "sourceCommit", "captureStartedAt", "capturedAt", "consistency", "targetFingerprint", "groupState", "partition", "commitState",
            "logStartOffset", "readCommittedEndOffset", "committedOffset", "lag");
        assertThat(value.get("committedOffset").isNull()).isTrue(); assertThat(value.get("lag").isNull()).isTrue();
        assertThat(value.get("capturedAt").asText()).endsWith("Z");
    }

    @Test void targetQueryAndBodyAreRejectedBeforeServiceAndPostHasNoExecutionRoute() throws Exception {
        for (var fixture : List.of(
            Map.entry("nonempty target query", HttpRequest.newBuilder(uri("?bootstrap=PRIVATE_TARGET_CANARY")).GET().build()),
            Map.entry("JSON request body", HttpRequest.newBuilder(uri("")).header("Content-Type", "application/json")
                .method("GET", HttpRequest.BodyPublishers.ofString("{\"group\":\"PRIVATE_TARGET_CANARY\"}")).build())
        )) {
            clearInvocations(observations);
            var response = send(fixture.getValue());
            assertThat(response.statusCode()).as(fixture.getKey()).isEqualTo(400);
            assertThat(response.headers().firstValue("Cache-Control")).as(fixture.getKey()).contains("no-store");
            assertThat(json.readTree(response.body()).get("code").asText()).as(fixture.getKey()).isEqualTo("INVALID_CONFIGURATION");
            assertThat(response.body()).doesNotContain("PRIVATE_TARGET_CANARY"); verifyNoInteractions(observations);
        }
        // JDK 21 Http1Request.getPathAndQuery omits an empty raw query from its wire request target.
        // Send the exact trailing '?' ourselves so this assertion actually tests an empty query.
        clearInvocations(observations);
        String emptyQueryHeaders = sendRawEmptyQueryHeaders();
        assertThat(emptyQueryHeaders.lines().findFirst().orElseThrow()).as("raw HTTP/1.1 empty query")
            .startsWith("HTTP/1.1 400 ");
        assertThat(emptyQueryHeaders.toLowerCase(Locale.ROOT)).as("raw empty query cache control")
            .contains("\r\ncache-control: no-store");
        verifyNoInteractions(observations);
        clearInvocations(observations);
        assertThat(send(HttpRequest.newBuilder(uri("")).POST(HttpRequest.BodyPublishers.ofString("{}")).build()).statusCode())
            .as("POST has no execution route").isEqualTo(405);
        verifyNoInteractions(observations);
    }

    @Test void brokerUnavailableDoesNotChangeJobV1DatabaseJournalOrReadiness() throws Exception {
        long jobs = jdbc.queryForObject("SELECT COUNT(*) FROM lab_job", Long.class);
        String journal = jdbc.queryForObject("SELECT status FROM lab_runtime WHERE id = 1", String.class);
        doThrow(KafkaObservationService.failure(KafkaObservationService.Code.KAFKA_UNAVAILABLE)).when(observations).capture();
        assertThat(send(HttpRequest.newBuilder(uri("")).GET().build()).statusCode()).isEqualTo(503);
        var jobUri = URI.create("http://127.0.0.1:" + port + "/api/jobs/observation");
        var job = send(HttpRequest.newBuilder(jobUri).GET().build()); assertThat(job.statusCode()).isEqualTo(200);
        var body = json.readTree(job.body());
        assertThat(keys(body)).containsExactlyInAnyOrder("schemaVersion", "kind", "capturedAt", "environment", "sourceCommit", "synthetic", "scope", "publicExecutionEnabled", "runtime", "slot", "jobs");
        assertThat(body.get("kind").asText()).isEqualTo("job-observation"); assertThat(body.get("schemaVersion").asInt()).isEqualTo(1);
        assertThat(jdbc.queryForObject("SELECT COUNT(*) FROM lab_job", Long.class)).isEqualTo(jobs);
        assertThat(jdbc.queryForObject("SELECT status FROM lab_runtime WHERE id = 1", String.class)).isEqualTo(journal);
        var ready = URI.create("http://127.0.0.1:" + port + "/actuator/health/readiness");
        assertThat(send(HttpRequest.newBuilder(ready).GET().build()).statusCode()).isEqualTo(200);
    }

    @Test void unknownLengthPendingBodyIsRejectedWithoutReadingOrWaiting() throws Exception {
        var request = mock(HttpServletRequest.class);
        when(request.getContentLengthLong()).thenReturn(-1L);
        when(request.getInputStream()).thenReturn(new ServletInputStream() {
            @Override public boolean isFinished() { return false; }
            @Override public boolean isReady() { throw new AssertionError("No body readiness wait"); }
            @Override public void setReadListener(ReadListener listener) { throw new AssertionError("No async body listener"); }
            @Override public int read() { throw new AssertionError("No body read"); }
        });
        clearInvocations(observations);
        var result = new KafkaObservationController(observations).get(request);
        assertThat(result.getStatusCode().value()).isEqualTo(400); verifyNoInteractions(observations);
    }

    @Test void zeroLengthUnfinishedEntityCreatesNoClientAndFinishedEmptyEntityUsesTheNormalPath() throws Exception {
        var opens = new AtomicInteger();
        var observer = new KafkaObservationService(KafkaObservationServiceTest.settings(true), KafkaObservationServiceTest.CLOCK,
            System::nanoTime, (fixed, deadline, group) -> { opens.incrementAndGet(); return new KafkaObservationServiceTest.FakeAdmin(); });
        var controller = new KafkaObservationController(observer);
        var request = mock(HttpServletRequest.class); when(request.getContentLengthLong()).thenReturn(0L);
        try {
            when(request.getInputStream()).thenReturn(entityStream(false));
            assertThat(controller.get(request).getStatusCode().value()).isEqualTo(400);
            assertThat(opens).hasValue(0); assertThat(observer.ownerThreadsCreated()).isZero();
            when(request.getInputStream()).thenReturn(entityStream(true));
            assertThat(controller.get(request).getStatusCode().value()).isEqualTo(200); assertThat(opens).hasValue(1);
        } finally { observer.close(); }
    }

    private String sendRawEmptyQueryHeaders() throws Exception {
        try (var socket = new Socket()) {
            socket.connect(new InetSocketAddress("127.0.0.1", port), 2000);
            socket.setSoTimeout(2000);
            String request = "GET /api/kafka/observation? HTTP/1.1\r\nHost: 127.0.0.1:" + port +
                "\r\nConnection: close\r\n\r\n";
            socket.getOutputStream().write(request.getBytes(StandardCharsets.US_ASCII));
            socket.getOutputStream().flush();
            byte[] wire = socket.getInputStream().readNBytes(8193);
            assertThat(wire.length).as("bounded raw empty-query response").isLessThanOrEqualTo(8192);
            String response = new String(wire, StandardCharsets.ISO_8859_1);
            int headersEnd = response.indexOf("\r\n\r\n");
            assertThat(headersEnd).as("complete raw empty-query response headers").isGreaterThanOrEqualTo(0);
            return response.substring(0, headersEnd);
        }
    }

    private static ServletInputStream entityStream(boolean finished) {
        return new ServletInputStream() {
            @Override public boolean isFinished() { return finished; }
            @Override public boolean isReady() { throw new AssertionError("No body readiness wait"); }
            @Override public void setReadListener(ReadListener listener) { throw new AssertionError("No async body listener"); }
            @Override public int read() { throw new AssertionError("No body read"); }
        };
    }
}
