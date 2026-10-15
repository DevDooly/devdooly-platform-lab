CREATE TABLE lab_job (
    run_id VARCHAR(80) PRIMARY KEY,
    scenario_version VARCHAR(80) NOT NULL,
    source_sha256 CHAR(64) NOT NULL,
    source_bytes LONGBLOB NOT NULL,
    source_size INTEGER NOT NULL,
    status VARCHAR(20) NOT NULL,
    export_status VARCHAR(20) NOT NULL,
    created_at TIMESTAMP(6) NOT NULL,
    source_verified_at TIMESTAMP(6),
    queued_at TIMESTAMP(6),
    completed_at TIMESTAMP(6),
    export_completed_at TIMESTAMP(6),
    terminated_at TIMESTAMP(6),
    CONSTRAINT lab_job_source_size CHECK (source_size > 0 AND source_size <= 1048576),
    CONSTRAINT lab_job_status CHECK (status IN ('STAGING', 'QUEUED', 'COMPLETED', 'TERMINATED')),
    CONSTRAINT lab_job_export_status CHECK (export_status IN ('NOT_REQUESTED', 'PENDING', 'EXPORTED', 'CANCELLED'))
);

CREATE TABLE lab_job_slot (
    id INTEGER PRIMARY KEY,
    occupied_run_id VARCHAR(80),
    CONSTRAINT lab_job_single_slot CHECK (id = 1),
    CONSTRAINT lab_job_slot_fk FOREIGN KEY (occupied_run_id) REFERENCES lab_job(run_id)
);
INSERT INTO lab_job_slot (id, occupied_run_id) VALUES (1, NULL);

CREATE TABLE lab_outbox (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    job_run_id VARCHAR(80) NOT NULL,
    event_type VARCHAR(20) NOT NULL,
    source_sha256 CHAR(64) NOT NULL,
    status VARCHAR(20) NOT NULL,
    created_at TIMESTAMP(6) NOT NULL,
    acknowledged_at TIMESTAMP(6),
    CONSTRAINT lab_outbox_job_fk FOREIGN KEY (job_run_id) REFERENCES lab_job(run_id),
    CONSTRAINT lab_outbox_one_event UNIQUE (job_run_id, event_type),
    CONSTRAINT lab_outbox_type CHECK (event_type IN ('DISPATCH', 'EXPORT')),
    CONSTRAINT lab_outbox_status CHECK (status IN ('PENDING', 'ACKNOWLEDGED', 'CANCELLED'))
);
CREATE INDEX lab_outbox_pending_idx ON lab_outbox(status, id);
