package io.github.devdooly.platformlab.jobs;

import io.github.devdooly.platformlab.demo.DemoService;
import io.github.devdooly.platformlab.demo.SensorProcessor;
import io.github.devdooly.platformlab.demo.SyntheticScenario;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.sql.Timestamp;
import java.time.Clock;
import java.time.Instant;
import java.time.temporal.ChronoUnit;
import java.util.List;
import java.util.Objects;
import java.util.Calendar;
import java.util.TimeZone;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.support.TransactionTemplate;

/**
 * Internal administrator/adapter boundary; intentionally has no HTTP controller or scheduler.
 * Source verification, broker publication and export confirmation must be performed by future
 * external adapters before calling the corresponding acknowledgement methods. These methods
 * alone do not prove that an object store or broker exists.
 */
@Service
public class LabJobService {
    public enum Status { STAGING, QUEUED, COMPLETED, TERMINATED }
    public enum ExportStatus { NOT_REQUESTED, PENDING, EXPORTED, CANCELLED }
    public enum EventType { DISPATCH, EXPORT }
    public enum OutboxStatus { PENDING, ACKNOWLEDGED, CANCELLED }
    public record Job(String runId, String scenarioVersion, String sourceSha256, int sourceSize,
                      Status status, ExportStatus exportStatus, Instant createdAt,
                      Instant sourceVerifiedAt, Instant queuedAt, Instant completedAt,
                      Instant exportCompletedAt, Instant terminatedAt) {
        public String sourceObjectKey() { return "raw/" + runId + "/" + sourceSha256 + ".ndjson"; }
    }
    public record Outbox(long id, String runId, EventType eventType, String sourceSha256,
                         OutboxStatus status, Instant createdAt, Instant acknowledgedAt) {}

    /** A bounded, committed DB snapshot. Export I/O must start only after this transaction ends. */
    public record ExportRun(String scenario, long seed, int inputCount, int successCount,
                            int failureCount, int duplicateCount, int pendingCount,
                            Instant startedAt, Instant completedAt) {}
    public record ExportSnapshot(Job job, byte[] sourceBytes, ExportRun run,
                                 List<SensorProcessor.Outcome> outcomes) {
        public ExportSnapshot { sourceBytes = sourceBytes.clone(); outcomes = List.copyOf(outcomes); }
        @Override public byte[] sourceBytes() { return sourceBytes.clone(); }
    }

    private final JdbcTemplate jdbc;
    private final TransactionTemplate tx;
    private final DemoService demos;
    private final Clock clock;

    public LabJobService(JdbcTemplate jdbc, PlatformTransactionManager manager, DemoService demos, Clock clock) {
        this.jdbc = jdbc; this.tx = new TransactionTemplate(manager); this.demos = demos; this.clock = clock;
    }

    public Job prepareSource(String runId, String scenarioVersion, byte[] rawNdjson) {
        validateRunId(runId);
        var source = CanonicalSource.validate(scenarioVersion, rawNdjson);
        return tx.execute(ignored -> {
            String occupied = lockSlot();
            Job existing = findLocked(runId);
            if (existing != null) {
                requireHash(existing, source.sha256());
                if (!existing.scenarioVersion().equals(scenarioVersion)
                    || !source.matches(jdbc.queryForObject("SELECT source_bytes FROM lab_job WHERE run_id = ?", byte[].class, runId))) {
                    throw new SourceConflictException();
                }
                return existing;
            }
            if (occupied != null) { throw new SlotBusyException(); }
            if (jdbc.queryForObject("SELECT COUNT(*) FROM demo_run WHERE id = ?", Long.class, runId) != 0) {
                throw new SourceConflictException();
            }
            update("""
                INSERT INTO lab_job (run_id, scenario_version, source_sha256, source_bytes, source_size,
                    status, export_status, created_at) VALUES (?, ?, ?, ?, ?, 'STAGING', 'NOT_REQUESTED', ?)
                """, runId, scenarioVersion, source.sha256(), source.bytes(), source.size(), timestamp(now()));
            update("UPDATE lab_job_slot SET occupied_run_id = ? WHERE id = 1", runId);
            return requireLocked(runId);
        });
    }

    /** Caller must first verify durable external source bytes/hash; no S3 adapter is wired yet. */
    public Job markSourceVerified(String runId, String sourceSha256) {
        return tx.execute(ignored -> {
            lockSlot();
            Job job = requireLocked(runId); requireHash(job, sourceSha256);
            if (job.status() == Status.QUEUED || job.status() == Status.COMPLETED) { return job; }
            requireState(job.status() == Status.STAGING);
            requireOccupied(runId);
            Instant at = now();
            update("UPDATE lab_job SET status = 'QUEUED', source_verified_at = ?, queued_at = ? WHERE run_id = ?",
                timestamp(at), timestamp(at), runId);
            insertOutbox(job, EventType.DISPATCH, at);
            return requireLocked(runId);
        });
    }

    /** One whole admitted ordered batch is committed with at most 1,000 outcomes and EXPORT intent. */
    public Job process(String runId, String sourceSha256) {
        return tx.execute(ignored -> {
            lockSlot();
            Job job = requireLocked(runId); requireHash(job, sourceSha256);
            if (job.status() == Status.COMPLETED) { return job; }
            requireState(job.status() == Status.QUEUED);
            requireOccupied(runId);
            var source = CanonicalSource.validate(job.scenarioVersion(), jdbc.queryForObject("SELECT source_bytes FROM lab_job WHERE run_id = ?", byte[].class, runId));
            requireHash(job, source.sha256());
            if (source.size() != job.sourceSize()) { throw new SourceConflictException(); }
            Instant started = now();
            var result = new SensorProcessor().process(source.events());
            Instant completed = now();
            demos.persistProcessedRun(runId, "합성 센서 품질 검증", job.scenarioVersion(), SyntheticScenario.seed(job.scenarioVersion()), result, started, completed);
            update("UPDATE lab_job SET status = 'COMPLETED', export_status = 'PENDING', completed_at = ? WHERE run_id = ?",
                timestamp(completed), runId);
            insertOutbox(job, EventType.EXPORT, completed);
            return requireLocked(runId);
        });
    }

    /** Call only after the broker has acknowledged publication; no publisher is wired yet. */
    public Job acknowledgeDispatch(String runId, String sourceSha256) {
        return tx.execute(ignored -> {
            lockSlot();
            Job job = requireLocked(runId); requireHash(job, sourceSha256);
            requireState(job.status() == Status.QUEUED || job.status() == Status.COMPLETED);
            acknowledgeOutbox(runId, EventType.DISPATCH, now());
            return job;
        });
    }

    /** Short consistent snapshot; never performs external storage I/O. */
    public ExportSnapshot exportSnapshot(String runId, String sourceSha256) {
        return tx.execute(ignored -> {
            lockSlot();
            Job job = requireLocked(runId); requireHash(job, sourceSha256);
            requireState(job.status() == Status.COMPLETED && job.terminatedAt() == null
                && (job.exportStatus() == ExportStatus.PENDING || job.exportStatus() == ExportStatus.EXPORTED));
            if (job.exportStatus() == ExportStatus.PENDING) { requireOccupied(runId); }
            String expectedOutbox = job.exportStatus() == ExportStatus.PENDING ? "PENDING" : "ACKNOWLEDGED";
            requireState(jdbc.queryForObject("SELECT COUNT(*) FROM lab_outbox WHERE job_run_id = ? AND event_type = 'EXPORT' AND source_sha256 = ? AND status = ?",
                Long.class, runId, sourceSha256, expectedOutbox) == 1);
            Integer storedSize = jdbc.queryForObject("SELECT OCTET_LENGTH(source_bytes) FROM lab_job WHERE run_id = ?", Integer.class, runId);
            requireState(storedSize != null && storedSize > 0 && storedSize <= CanonicalSource.MAX_BYTES && storedSize == job.sourceSize());
            byte[] source = jdbc.queryForObject("SELECT source_bytes FROM lab_job WHERE run_id = ?", byte[].class, runId);
            List<ExportRun> runs = jdbc.query("SELECT * FROM demo_run WHERE id = ?", (rs, row) -> new ExportRun(
                rs.getString("scenario"), rs.getLong("seed"), rs.getInt("input_count"), rs.getInt("success_count"),
                rs.getInt("failure_count"), rs.getInt("duplicate_count"), rs.getInt("pending_count"),
                instant(rs, "started_at"), instant(rs, "completed_at")), runId);
            requireState(runs.size() == 1);
            List<SensorProcessor.Outcome> outcomes = jdbc.query("SELECT * FROM demo_outcome WHERE run_id = ? ORDER BY input_sequence LIMIT 1001", (rs, row) ->
                new SensorProcessor.Outcome(rs.getInt("input_sequence"), rs.getString("event_id"), rs.getString("sensor_id"),
                    rs.getString("event_time"), rs.getObject("sensor_value", Double.class),
                    SensorProcessor.Status.valueOf(rs.getString("status")), SensorProcessor.Reason.valueOf(rs.getString("reason"))), runId);
            return new ExportSnapshot(job, source, runs.getFirst(), outcomes);
        });
    }

    /** Call only after durable result export has been independently verified. */
    public Job completeExport(String runId, String sourceSha256) {
        return tx.execute(ignored -> {
            lockSlot();
            Job job = requireLocked(runId); requireHash(job, sourceSha256);
            requireState(job.status() == Status.COMPLETED);
            if (job.exportStatus() == ExportStatus.EXPORTED) { return job; }
            requireState(job.exportStatus() == ExportStatus.PENDING && job.terminatedAt() == null);
            requireOccupied(runId);
            Instant at = now();
            acknowledgeOutbox(runId, EventType.EXPORT, at);
            update("UPDATE lab_job SET export_status = 'EXPORTED', export_completed_at = ? WHERE run_id = ?", timestamp(at), runId);
            update("UPDATE lab_job_slot SET occupied_run_id = NULL WHERE id = 1");
            return requireLocked(runId);
        });
    }

    /** Explicit operator termination releases the slot without claiming a successful export. */
    public Job terminate(String runId, String sourceSha256) {
        return tx.execute(ignored -> {
            lockSlot();
            Job job = requireLocked(runId); requireHash(job, sourceSha256);
            if (job.terminatedAt() != null) { return job; }
            requireState(job.exportStatus() != ExportStatus.EXPORTED);
            requireOccupied(runId);
            Instant at = now();
            update("""
                UPDATE lab_job SET status = ?, export_status = ?, terminated_at = ? WHERE run_id = ?
                """, job.status() == Status.COMPLETED ? "COMPLETED" : "TERMINATED",
                job.status() == Status.COMPLETED ? "CANCELLED" : "NOT_REQUESTED", timestamp(at), runId);
            update("UPDATE lab_outbox SET status = 'CANCELLED', acknowledged_at = ? WHERE job_run_id = ? AND status = 'PENDING'", timestamp(at), runId);
            update("UPDATE lab_job_slot SET occupied_run_id = NULL WHERE id = 1");
            return requireLocked(runId);
        });
    }

    public Job get(String runId) {
        validateRunId(runId);
        List<Job> rows = jdbc.query("SELECT * FROM lab_job WHERE run_id = ?", this::mapJob, runId);
        if (rows.isEmpty()) { throw new JobNotFoundException(); }
        return rows.getFirst();
    }

    public List<Outbox> pendingOutbox(int limit) {
        if (limit < 1 || limit > 100) { throw new IllegalArgumentException("Outbox limit must be 1 to 100"); }
        return jdbc.query("SELECT * FROM lab_outbox WHERE status = 'PENDING' ORDER BY id LIMIT ?", this::mapOutbox, limit);
    }

    private String lockSlot() {
        List<String> rows = jdbc.query("SELECT occupied_run_id FROM lab_job_slot WHERE id = 1 FOR UPDATE", (rs, index) -> rs.getString(1));
        if (rows.size() != 1) { throw new IllegalStateException("Singleton admission slot is missing"); }
        return rows.getFirst();
    }
    private void requireOccupied(String runId) {
        if (!runId.equals(jdbc.queryForObject("SELECT occupied_run_id FROM lab_job_slot WHERE id = 1", String.class))) {
            throw new IllegalStateException("Job does not own the admission slot");
        }
    }
    private Job findLocked(String runId) {
        List<Job> rows = jdbc.query("SELECT * FROM lab_job WHERE run_id = ? FOR UPDATE", this::mapJob, runId);
        return rows.isEmpty() ? null : rows.getFirst();
    }
    private Job requireLocked(String runId) {
        validateRunId(runId);
        Job job = findLocked(runId);
        if (job == null) { throw new JobNotFoundException(); }
        return job;
    }
    private void insertOutbox(Job job, EventType type, Instant at) {
        update("INSERT INTO lab_outbox (job_run_id, event_type, source_sha256, status, created_at) VALUES (?, ?, ?, 'PENDING', ?)",
            job.runId(), type.name(), job.sourceSha256(), timestamp(at));
    }
    private void acknowledgeOutbox(String runId, EventType type, Instant at) {
        int changed = update("UPDATE lab_outbox SET status = 'ACKNOWLEDGED', acknowledged_at = ? WHERE job_run_id = ? AND event_type = ? AND status = 'PENDING'",
            timestamp(at), runId, type.name());
        if (changed == 0 && jdbc.queryForObject("SELECT COUNT(*) FROM lab_outbox WHERE job_run_id = ? AND event_type = ? AND status = 'ACKNOWLEDGED'", Long.class, runId, type.name()) != 1) {
            throw new IllegalStateException("Outbox event is absent or cancelled");
        }
    }
    private Job mapJob(ResultSet rs, int row) throws SQLException {
        return new Job(rs.getString("run_id"), rs.getString("scenario_version"), rs.getString("source_sha256"), rs.getInt("source_size"),
            Status.valueOf(rs.getString("status")), ExportStatus.valueOf(rs.getString("export_status")), instant(rs, "created_at"),
            instant(rs, "source_verified_at"), instant(rs, "queued_at"), instant(rs, "completed_at"), instant(rs, "export_completed_at"), instant(rs, "terminated_at"));
    }
    private Outbox mapOutbox(ResultSet rs, int row) throws SQLException {
        return new Outbox(rs.getLong("id"), rs.getString("job_run_id"), EventType.valueOf(rs.getString("event_type")), rs.getString("source_sha256"),
            OutboxStatus.valueOf(rs.getString("status")), instant(rs, "created_at"), instant(rs, "acknowledged_at"));
    }
    private static void validateRunId(String runId) {
        if (runId == null || !runId.matches("[a-z0-9][a-z0-9._-]{0,79}") || SyntheticScenario.RUN_ID.equals(runId)) {
            throw new IllegalArgumentException("Run ID must be lowercase ASCII, at most 80 characters, and must not be the seed ID");
        }
    }
    private static void requireHash(Job job, String sourceSha256) {
        if (!Objects.equals(job.sourceSha256(), sourceSha256)) { throw new SourceConflictException(); }
    }
    private static void requireState(boolean valid) { if (!valid) { throw new JobStateException(); } }
    private Instant now() { return clock.instant().truncatedTo(ChronoUnit.MICROS); }
    private static Timestamp timestamp(Instant at) { return Timestamp.from(at); }
    private static Instant instant(ResultSet rs, String column) throws SQLException {
        Timestamp value = rs.getTimestamp(column, utcCalendar()); return value == null ? null : value.toInstant();
    }
    /** Match Hibernate's explicit UTC timestamp mapping regardless of the JVM default zone. */
    private int update(String sql, Object... parameters) {
        return jdbc.update(sql, statement -> {
            for (int index = 0; index < parameters.length; index++) {
                Object value = parameters[index];
                if (value instanceof Timestamp at) { statement.setTimestamp(index + 1, at, utcCalendar()); }
                else if (value instanceof byte[] bytes) { statement.setBytes(index + 1, bytes); }
                else { statement.setObject(index + 1, value); }
            }
        });
    }
    private static Calendar utcCalendar() { return Calendar.getInstance(TimeZone.getTimeZone("UTC")); }
    public static class SourceConflictException extends RuntimeException {}
    public static class SlotBusyException extends RuntimeException {}
    public static class JobNotFoundException extends RuntimeException {}
    public static class JobStateException extends RuntimeException {}
}
