package io.github.devdooly.platformlab.platform;

import java.time.Clock;
import java.time.Instant;
import java.util.*;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.web.bind.annotation.*;

@RestController @RequestMapping("/api/platform")
public class PlatformController {
    private final JdbcTemplate jdbc;
    private final Clock clock;
    private final String environment;
    private final String sourceCommit;
    private final String imageDigest;
    private final String databaseLabel;
    private final Instant startedAt;
    public PlatformController(JdbcTemplate jdbc, Clock clock, @Value("${lab.environment}") String environment,
            @Value("${lab.source-commit}") String sourceCommit, @Value("${lab.image-digest}") String imageDigest,
            @Value("${lab.database-label}") String databaseLabel) {
        this.jdbc = jdbc; this.clock = clock; this.environment = environment; this.sourceCommit = sourceCommit;
        this.imageDigest = imageDigest; this.databaseLabel = databaseLabel; this.startedAt = clock.instant();
    }
    @GetMapping("/summary") public Map<String, Object> summary() {
        boolean databaseUp;
        try { databaseUp = Integer.valueOf(1).equals(jdbc.queryForObject("SELECT 1", Integer.class)); }
        catch (RuntimeException ex) { databaseUp = false; }
        return Map.of("service", "devdooly-platform-lab-api", "status", databaseUp ? "UP" : "DEGRADED", "environment", environment,
            "sourceCommit", sourceCommit, "synthetic", true, "publicExecutionEnabled", false,
            "components", List.of(component("API", "RUNNING", "Spring Boot 조회 API"), component("DATABASE", databaseUp ? "RUNNING" : "UNAVAILABLE", databaseLabel),
                component("JENKINS", "NOT_CONFIGURED", "실제 CI 연결 전"), component("ARGO_CD", "NOT_CONFIGURED", "실제 CD 연결 전"),
                component("KUBERNETES", "NOT_CONFIGURED", "서버 구성 전"), component("KAFKA", "PLANNED", "4단계"), component("S3", "PLANNED", "4단계")),
            "observedAt", clock.instant());
    }
    @GetMapping("/releases") public Map<String, Object> releases() {
        var runtime = new LinkedHashMap<String, Object>();
        runtime.put("service", "api"); runtime.put("version", "0.1.0"); runtime.put("sourceCommit", sourceCommit);
        runtime.put("imageDigest", imageDigest.isBlank() ? null : imageDigest);
        runtime.put("deploymentStatus", "local".equals(environment) || "test".equals(environment) ? "LOCAL_RUNTIME" : "RUNTIME_ONLY");
        runtime.put("startedAt", startedAt);
        return Map.of("items", List.of(runtime), "observedAt", clock.instant());
    }
    private Map<String, String> component(String name, String status, String detail) { return Map.of("name", name, "status", status, "detail", detail); }
}
