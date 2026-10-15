package io.github.devdooly.platformlab.jobs.runtime;

import java.sql.ResultSet;
import java.sql.SQLException;
import java.sql.Timestamp;
import java.time.Clock;
import java.time.Instant;
import java.time.temporal.ChronoUnit;
import java.util.Calendar;
import java.util.Objects;
import java.util.TimeZone;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.transaction.IllegalTransactionStateException;
import org.springframework.transaction.support.TransactionSynchronizationManager;

/** Explicit DB journal. Neither a component nor an autonomous runner. Mutations require process ownership. */
public final class RuntimeStateStore {
    public enum Status { NOT_STARTED, RUNNING, PAUSED_OPERATOR, STOPPED }
    public enum Stage { IDLE, PUBLISH, CONSUME, EXPORT, STOPPED }
    public enum FailureCode {
        PUBLISH_FAILED, EXPORT_FAILED, RUNTIME_FAILED, INTERRUPTED, LEASE_LOST, RESOURCE_CLOSE_FAILED,
        INVALID_MESSAGE, SOURCE_UNAVAILABLE, SOURCE_INVALID, JOB_REJECTED, PROCESSING_FAILED,
        OFFSET_COMMIT_FAILED, POLL_FAILED, OPERATOR_RESUME_REQUIRED
    }
    public record State(Status status, Stage stage, FailureCode failureCode, Instant startedAt,
                        Instant heartbeatAt, Instant stoppedAt, String sourceCommit) {}
    private final JdbcTemplate jdbc;
    private final Clock clock;

    public RuntimeStateStore(JdbcTemplate jdbc, Clock clock) {
        this.jdbc = Objects.requireNonNull(jdbc); this.clock = Objects.requireNonNull(clock);
    }

    public State read() {
        return jdbc.queryForObject("SELECT status, stage, failure_code, started_at, heartbeat_at, stopped_at, source_commit FROM lab_runtime WHERE id = 1", (rows, index) -> {
            String failure = rows.getString("failure_code");
            return new State(Status.valueOf(rows.getString("status")), Stage.valueOf(rows.getString("stage")),
                failure == null ? null : FailureCode.valueOf(failure), instant(rows, "started_at"),
                instant(rows, "heartbeat_at"), instant(rows, "stopped_at"), rows.getString("source_commit"));
        });
    }

    /** Run and resume commands require an API-migrated V3 schema; they never apply migrations themselves. */
    public void requireSchemaV3() {
        Integer count = jdbc.queryForObject("SELECT COUNT(*) FROM flyway_schema_history WHERE version = '3' AND success = TRUE", Integer.class);
        if (count == null || count != 1 || read() == null) { throw new IllegalStateException("A successfully migrated V3 runtime schema is required"); }
    }

    public void start(RuntimeLease lease, String sourceCommit) {
        requireOwner(lease); validateCommit(sourceCommit); Instant now = now();
        int changed = update("UPDATE lab_runtime SET status = 'RUNNING', stage = 'IDLE', failure_code = NULL, started_at = ?, heartbeat_at = ?, stopped_at = NULL, source_commit = ? WHERE id = 1 AND status <> 'PAUSED_OPERATOR'",
            now, now, sourceCommit);
        if (changed != 1) { throw new OperatorResumeRequiredException(); }
    }

    public void stage(RuntimeLease lease, Stage stage) {
        requireOwner(lease); Objects.requireNonNull(stage);
        if (stage == Stage.STOPPED) { throw new IllegalArgumentException("Use stop for a final runtime state"); }
        requireUpdated(update("UPDATE lab_runtime SET stage = ?, heartbeat_at = ? WHERE id = 1 AND status = 'RUNNING'", stage.name(), now()));
    }

    public void pause(RuntimeLease lease, Stage stage, FailureCode code) {
        requireOwner(lease); Objects.requireNonNull(stage); Objects.requireNonNull(code); Instant now = now();
        requireUpdated(update("UPDATE lab_runtime SET status = 'PAUSED_OPERATOR', stage = ?, failure_code = ?, heartbeat_at = ?, stopped_at = ? WHERE id = 1 AND status = 'RUNNING'",
            stage.name(), code.name(), now, now));
    }

    public void stop(RuntimeLease lease) {
        requireOwner(lease); Instant now = now();
        requireUpdated(update("UPDATE lab_runtime SET status = 'STOPPED', stage = 'STOPPED', failure_code = NULL, heartbeat_at = ?, stopped_at = ? WHERE id = 1 AND status = 'RUNNING'", now, now));
    }

    /** Clearing a persisted pause is a separate, serialized operator action; no Kafka/S3 work is performed. */
    public void resume(RuntimeLease lease) {
        requireOwner(lease); Instant now = now();
        requireUpdated(update("UPDATE lab_runtime SET status = 'STOPPED', stage = 'STOPPED', failure_code = NULL, heartbeat_at = ?, stopped_at = ? WHERE id = 1 AND status = 'PAUSED_OPERATOR'", now, now));
    }

    private static void requireOwner(RuntimeLease lease) {
        if (TransactionSynchronizationManager.isActualTransactionActive()) {
            throw new IllegalTransactionStateException("Runtime journal mutations must not join an outer database transaction");
        }
        Objects.requireNonNull(lease).verifyHeld();
    }
    public static void validateCommit(String commit) {
        if (commit == null || (!commit.equals("unknown") && !commit.matches("[a-f0-9]{40}"))) {
            throw new IllegalArgumentException("Source commit must be unknown or a complete lowercase Git SHA");
        }
    }
    private static void requireUpdated(int changed) { if (changed != 1) { throw new IllegalStateException("Runtime journal state does not permit this transition"); } }
    private Instant now() { return clock.instant().truncatedTo(ChronoUnit.MICROS); }
    private int update(String sql, Object... values) {
        return jdbc.update(sql, statement -> {
            for (int index = 0; index < values.length; index++) {
                Object value = values[index];
                if (value instanceof Instant instant) { statement.setTimestamp(index + 1, Timestamp.from(instant), utc()); }
                else { statement.setObject(index + 1, value); }
            }
        });
    }
    private static Instant instant(ResultSet rows, String name) throws SQLException {
        Timestamp at = rows.getTimestamp(name, utc()); return at == null ? null : at.toInstant();
    }
    private static Calendar utc() { return Calendar.getInstance(TimeZone.getTimeZone("UTC")); }
    public static final class OperatorResumeRequiredException extends IllegalStateException {
        public OperatorResumeRequiredException() { super("The runtime is persistently paused; an explicit operator resume is required"); }
    }
}
