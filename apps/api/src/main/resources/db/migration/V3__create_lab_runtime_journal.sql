CREATE TABLE lab_runtime (
    id INTEGER PRIMARY KEY,
    status VARCHAR(24) NOT NULL,
    stage VARCHAR(16) NOT NULL,
    failure_code VARCHAR(40),
    started_at TIMESTAMP(6),
    heartbeat_at TIMESTAMP(6),
    stopped_at TIMESTAMP(6),
    source_commit VARCHAR(40) NOT NULL,
    CONSTRAINT lab_runtime_singleton CHECK (id = 1),
    CONSTRAINT lab_runtime_status CHECK (status IN ('NOT_STARTED', 'RUNNING', 'PAUSED_OPERATOR', 'STOPPED')),
    CONSTRAINT lab_runtime_stage CHECK (stage IN ('IDLE', 'PUBLISH', 'CONSUME', 'EXPORT', 'STOPPED')),
    CONSTRAINT lab_runtime_failure CHECK (failure_code IS NULL OR failure_code IN (
        'PUBLISH_FAILED', 'EXPORT_FAILED', 'RUNTIME_FAILED', 'INTERRUPTED', 'LEASE_LOST', 'RESOURCE_CLOSE_FAILED',
        'INVALID_MESSAGE', 'SOURCE_UNAVAILABLE', 'SOURCE_INVALID', 'JOB_REJECTED', 'PROCESSING_FAILED',
        'OFFSET_COMMIT_FAILED', 'POLL_FAILED', 'OPERATOR_RESUME_REQUIRED')),
    CONSTRAINT lab_runtime_pause_reason CHECK (
        (status = 'PAUSED_OPERATOR' AND failure_code IS NOT NULL) OR
        (status <> 'PAUSED_OPERATOR' AND failure_code IS NULL))
);
INSERT INTO lab_runtime (id, status, stage, failure_code, started_at, heartbeat_at, stopped_at, source_commit)
VALUES (1, 'NOT_STARTED', 'IDLE', NULL, NULL, NULL, NULL, 'unknown');
