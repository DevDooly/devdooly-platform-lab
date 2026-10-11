CREATE TABLE demo_run (
    id VARCHAR(80) PRIMARY KEY,
    name VARCHAR(160) NOT NULL,
    scenario VARCHAR(80) NOT NULL,
    seed BIGINT NOT NULL,
    input_count INTEGER NOT NULL,
    success_count INTEGER NOT NULL,
    failure_count INTEGER NOT NULL,
    duplicate_count INTEGER NOT NULL,
    pending_count INTEGER NOT NULL,
    started_at TIMESTAMP(6) NOT NULL,
    completed_at TIMESTAMP(6) NOT NULL,
    CONSTRAINT demo_run_totals CHECK (input_count = success_count + failure_count + duplicate_count + pending_count)
);
CREATE TABLE demo_outcome (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    run_id VARCHAR(80) NOT NULL,
    input_sequence INTEGER NOT NULL,
    event_id VARCHAR(80),
    sensor_id VARCHAR(80),
    event_time VARCHAR(100),
    sensor_value DOUBLE,
    status VARCHAR(20) NOT NULL,
    reason VARCHAR(40) NOT NULL,
    CONSTRAINT outcome_run_fk FOREIGN KEY (run_id) REFERENCES demo_run(id),
    CONSTRAINT outcome_sequence UNIQUE (run_id, input_sequence)
);
CREATE INDEX demo_run_started_idx ON demo_run(started_at);
