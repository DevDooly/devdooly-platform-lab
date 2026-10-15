package io.github.devdooly.platformlab.jobs.observation;

import io.github.devdooly.platformlab.demo.SensorProcessor;
import io.github.devdooly.platformlab.jobs.CanonicalSource;
import io.github.devdooly.platformlab.jobs.LabJobService;
import io.github.devdooly.platformlab.jobs.exporting.ExportBundle;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.sql.Timestamp;
import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.util.Calendar;
import java.util.List;
import java.util.Set;
import java.util.TimeZone;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.TransactionDefinition;
import org.springframework.transaction.support.TransactionTemplate;

/** Bounded committed DB evidence only. No object-store probe, row lock or runtime startup. */
@Service
public class JobObservationService {
    public static final int MAX_JOBS = 20;
    public static final Duration HEARTBEAT_STALE_AFTER = Duration.ofSeconds(300);
    private static final Set<String> STATUSES = Set.of("NOT_STARTED", "RUNNING", "PAUSED_OPERATOR", "STOPPED");
    private static final Set<String> STAGES = Set.of("IDLE", "PUBLISH", "CONSUME", "EXPORT", "STOPPED");
    private static final Set<String> FAILURES = Set.of("PUBLISH_FAILED", "EXPORT_FAILED", "RUNTIME_FAILED", "INTERRUPTED", "LEASE_LOST",
        "INVALID_MESSAGE", "SOURCE_UNAVAILABLE", "SOURCE_INVALID", "JOB_REJECTED", "PROCESSING_FAILED", "OFFSET_COMMIT_FAILED",
        "POLL_FAILED", "OPERATOR_RESUME_REQUIRED", "RESOURCE_CLOSE_FAILED");

    public record Observation(int schemaVersion, String kind, Instant capturedAt, String environment, String sourceCommit,
                              boolean synthetic, String scope, boolean publicExecutionEnabled, Runtime runtime, Slot slot, List<Job> jobs) {
        public Observation { jobs = List.copyOf(jobs); }
    }
    public record Runtime(String status, String stage, String failureCode, Instant startedAt, Instant heartbeatAt,
                          Instant stoppedAt, String sourceCommit, boolean stale) {}
    public record Slot(String occupiedRunId) {}
    public record Counts(int input, int success, int failure, int duplicate, int pending) {}
    public record File(String sha256, int size) {}
    public record Files(File result, File failures) {}
    public record Job(String runId, String status, String exportStatus, Instant createdAt, Instant sourceVerifiedAt,
                      Instant queuedAt, Instant completedAt, Instant exportCompletedAt, Instant terminatedAt,
                      Counts counts, Files files, String fileEvidence) {}

    private final JdbcTemplate jdbc;
    private final TransactionTemplate snapshot;
    private final Clock clock;
    private final String environment;
    private final String sourceCommit;

    public JobObservationService(JdbcTemplate jdbc, PlatformTransactionManager manager, Clock clock,
            @Value("${lab.environment}") String environment, @Value("${lab.source-commit}") String sourceCommit) {
        this.jdbc = jdbc; this.clock = clock;
        this.environment = switch (environment) {
            case "local" -> "LOCAL"; case "test" -> "TEST"; case "isolated-lab" -> "ISOLATED_LAB";
            case "mini-pc" -> "MINI_PC"; default -> "UNKNOWN";
        };
        this.sourceCommit = commit(sourceCommit);
        this.snapshot = new TransactionTemplate(manager);
        this.snapshot.setReadOnly(true);
        this.snapshot.setIsolationLevel(TransactionDefinition.ISOLATION_REPEATABLE_READ);
        this.snapshot.setTimeout(10);
    }

    public Observation capture() {
        try {
            return snapshot.execute(ignored -> {
                List<RuntimeRow> runtimeRows = jdbc.query("SELECT status, stage, failure_code, started_at, heartbeat_at, stopped_at, source_commit FROM lab_runtime WHERE id = 1",
                    (rs, index) -> new RuntimeRow(rs.getString("status"), rs.getString("stage"), rs.getString("failure_code"),
                        instant(rs, "started_at"), instant(rs, "heartbeat_at"), instant(rs, "stopped_at"), rs.getString("source_commit")));
                require(runtimeRows.size() == 1);
                List<String> slots = jdbc.query("SELECT occupied_run_id FROM lab_job_slot WHERE id = 1", (rs, index) -> rs.getString(1));
                require(slots.size() == 1 && (slots.getFirst() == null || validRunId(slots.getFirst())));
                List<LabJobService.Job> rows = jdbc.query("""
                    SELECT run_id, scenario_version, source_sha256, source_size, status, export_status, created_at,
                        source_verified_at, queued_at, completed_at, export_completed_at, terminated_at
                    FROM lab_job ORDER BY created_at DESC, run_id DESC LIMIT ?
                    """, this::mapJob, MAX_JOBS);
                List<Job> jobs = rows.stream().map(this::observeJob).toList();
                Instant at = clock.instant();
                Runtime runtime = observeRuntime(runtimeRows.getFirst(), at);
                String scope = switch (this.environment) {
                    case "ISOLATED_LAB" -> "ISOLATED_LAB"; case "MINI_PC" -> "DEPLOYED_RUNTIME"; default -> "LOCAL_VALIDATION";
                };
                return new Observation(1, "job-observation", at, environment, sourceCommit, true, scope, false, runtime, new Slot(slots.getFirst()), jobs);
            });
        } catch (java.lang.RuntimeException invalidOrUnavailable) {
            // No raw SQL, connection address, stored input or exception text crosses HTTP.
            throw new ObservationUnavailableException();
        }
    }

    private Job observeJob(LabJobService.Job job) {
        require(validRunId(job.runId()) && job.createdAt() != null);
        switch (job.status()) {
            case STAGING -> require(job.exportStatus() == LabJobService.ExportStatus.NOT_REQUESTED && job.queuedAt() == null
                && job.sourceVerifiedAt() == null && job.completedAt() == null && job.exportCompletedAt() == null && job.terminatedAt() == null);
            case QUEUED -> require(job.exportStatus() == LabJobService.ExportStatus.NOT_REQUESTED && job.queuedAt() != null
                && job.sourceVerifiedAt() != null && job.completedAt() == null && job.exportCompletedAt() == null && job.terminatedAt() == null);
            case COMPLETED -> require(job.queuedAt() != null && job.sourceVerifiedAt() != null && job.completedAt() != null
                && ((job.exportStatus() == LabJobService.ExportStatus.PENDING && job.exportCompletedAt() == null && job.terminatedAt() == null)
                    || (job.exportStatus() == LabJobService.ExportStatus.EXPORTED && job.exportCompletedAt() != null && job.terminatedAt() == null)
                    || (job.exportStatus() == LabJobService.ExportStatus.CANCELLED && job.exportCompletedAt() == null && job.terminatedAt() != null)));
            case TERMINATED -> require(job.exportStatus() == LabJobService.ExportStatus.NOT_REQUESTED && job.completedAt() == null
                && job.exportCompletedAt() == null && job.terminatedAt() != null);
        }
        List<LabJobService.ExportRun> runs = jdbc.query("SELECT scenario, seed, input_count, success_count, failure_count, duplicate_count, pending_count, started_at, completed_at FROM demo_run WHERE id = ?",
            (rs, index) -> new LabJobService.ExportRun(rs.getString("scenario"), rs.getLong("seed"), rs.getInt("input_count"), rs.getInt("success_count"),
                rs.getInt("failure_count"), rs.getInt("duplicate_count"), rs.getInt("pending_count"), instant(rs, "started_at"), instant(rs, "completed_at")), job.runId());
        require(runs.size() <= 1);
        Counts counts = null; Files files = null; String evidence = "NOT_AVAILABLE";
        if (job.status() == LabJobService.Status.COMPLETED) {
            require(runs.size() == 1);
            var run = runs.getFirst();
            counts = new Counts(run.inputCount(), run.successCount(), run.failureCount(), run.duplicateCount(), run.pendingCount());
            require(counts.input() >= 0 && counts.input() <= 1000 && counts.success() >= 0 && counts.success() <= 1000 && counts.failure() >= 0 && counts.failure() <= 1000
                && counts.duplicate() >= 0 && counts.duplicate() <= 1000 && counts.pending() >= 0 && counts.pending() <= 1000
                && counts.input() == counts.success() + counts.failure() + counts.duplicate() + counts.pending());
            if (job.terminatedAt() == null && (job.exportStatus() == LabJobService.ExportStatus.PENDING || job.exportStatus() == LabJobService.ExportStatus.EXPORTED)) {
                String expected = job.exportStatus() == LabJobService.ExportStatus.EXPORTED ? "ACKNOWLEDGED" : "PENDING";
                require(jdbc.queryForObject("SELECT COUNT(*) FROM lab_outbox WHERE job_run_id = ? AND event_type = 'EXPORT' AND source_sha256 = ? AND status = ?", Long.class,
                    job.runId(), job.sourceSha256(), expected) == 1);
                Integer storedSize = jdbc.queryForObject("SELECT OCTET_LENGTH(source_bytes) FROM lab_job WHERE run_id = ?", Integer.class, job.runId());
                require(storedSize != null && storedSize > 0 && storedSize <= CanonicalSource.MAX_BYTES && storedSize == job.sourceSize());
                byte[] source = jdbc.queryForObject("SELECT source_bytes FROM lab_job WHERE run_id = ?", byte[].class, job.runId());
                List<SensorProcessor.Outcome> outcomes = jdbc.query("SELECT input_sequence, event_id, sensor_id, event_time, sensor_value, status, reason FROM demo_outcome WHERE run_id = ? ORDER BY input_sequence LIMIT 1001",
                    (rs, index) -> new SensorProcessor.Outcome(rs.getInt("input_sequence"), rs.getString("event_id"), rs.getString("sensor_id"), rs.getString("event_time"),
                        rs.getObject("sensor_value", Double.class), SensorProcessor.Status.valueOf(rs.getString("status")), SensorProcessor.Reason.valueOf(rs.getString("reason"))), job.runId());
                ExportBundle bundle = ExportBundle.from(new LabJobService.ExportSnapshot(job, source, run, outcomes));
                files = new Files(new File(bundle.result().sha256(), bundle.result().size()), new File(bundle.failures().sha256(), bundle.failures().size()));
                evidence = job.exportStatus() == LabJobService.ExportStatus.EXPORTED ? "VERIFIED_AT_EXPORT_COMMIT" : "EXPECTED_FROM_DB";
            }
        } else { require(runs.isEmpty()); }
        return new Job(job.runId(), job.status().name(), job.exportStatus().name(), job.createdAt(), job.sourceVerifiedAt(), job.queuedAt(), job.completedAt(),
            job.exportCompletedAt(), job.terminatedAt(), counts, files, evidence);
    }

    private Runtime observeRuntime(RuntimeRow row, Instant at) {
        require(STATUSES.contains(row.status()) && STAGES.contains(row.stage()) && (row.failureCode() == null || FAILURES.contains(row.failureCode())));
        require(row.sourceCommit() != null && row.sourceCommit().equals(commit(row.sourceCommit())));
        switch (row.status()) {
            case "NOT_STARTED" -> require(row.stage().equals("IDLE") && row.failureCode() == null && row.startedAt() == null && row.heartbeatAt() == null && row.stoppedAt() == null);
            case "RUNNING" -> require(!row.stage().equals("STOPPED") && row.failureCode() == null && row.startedAt() != null && row.heartbeatAt() != null && row.stoppedAt() == null);
            case "PAUSED_OPERATOR" -> require((!row.stage().equals("STOPPED") || "RESOURCE_CLOSE_FAILED".equals(row.failureCode()))
                && row.failureCode() != null && row.startedAt() != null && row.heartbeatAt() != null && row.stoppedAt() != null);
            case "STOPPED" -> require(row.stage().equals("STOPPED") && row.failureCode() == null && row.startedAt() != null && row.heartbeatAt() != null && row.stoppedAt() != null);
            default -> throw new IllegalStateException("Invalid runtime state");
        }
        boolean stale = row.status().equals("RUNNING") && (row.heartbeatAt() == null || row.heartbeatAt().isAfter(at)
            || Duration.between(row.heartbeatAt(), at).compareTo(HEARTBEAT_STALE_AFTER) > 0);
        return new Runtime(row.status(), row.stage(), row.failureCode(), row.startedAt(), row.heartbeatAt(), row.stoppedAt(), row.sourceCommit(), stale);
    }
    private LabJobService.Job mapJob(ResultSet rs, int index) throws SQLException {
        return new LabJobService.Job(rs.getString("run_id"), rs.getString("scenario_version"), rs.getString("source_sha256"), rs.getInt("source_size"),
            LabJobService.Status.valueOf(rs.getString("status")), LabJobService.ExportStatus.valueOf(rs.getString("export_status")), instant(rs, "created_at"),
            instant(rs, "source_verified_at"), instant(rs, "queued_at"), instant(rs, "completed_at"), instant(rs, "export_completed_at"), instant(rs, "terminated_at"));
    }
    private record RuntimeRow(String status, String stage, String failureCode, Instant startedAt, Instant heartbeatAt, Instant stoppedAt, String sourceCommit) {}
    private static boolean validRunId(String value) { return value != null && value.matches("[a-z0-9][a-z0-9._-]{0,79}"); }
    private static String commit(String value) { return value != null && value.matches("[a-f0-9]{40}") ? value : "unknown"; }
    private static void require(boolean valid) { if (!valid) throw new IllegalStateException("Invalid observation state"); }
    private static Instant instant(ResultSet rs, String column) throws SQLException {
        Timestamp value = rs.getTimestamp(column, Calendar.getInstance(TimeZone.getTimeZone("UTC"))); return value == null ? null : value.toInstant();
    }
    public static final class ObservationUnavailableException extends java.lang.RuntimeException {}
}
