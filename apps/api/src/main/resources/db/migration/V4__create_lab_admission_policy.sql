CREATE TABLE lab_admission_policy (
    id INTEGER PRIMARY KEY,
    cooldown_seconds INTEGER NOT NULL,
    last_admitted_at TIMESTAMP(6),
    next_admission_at TIMESTAMP(6),
    CONSTRAINT lab_admission_singleton CHECK (id = 1),
    CONSTRAINT lab_admission_cooldown CHECK (cooldown_seconds BETWEEN 1 AND 3600),
    CONSTRAINT lab_admission_times CHECK (
        (last_admitted_at IS NULL AND next_admission_at IS NULL) OR
        (last_admitted_at IS NOT NULL AND next_admission_at IS NOT NULL AND next_admission_at > last_admitted_at))
);
INSERT INTO lab_admission_policy (id, cooldown_seconds, last_admitted_at, next_admission_at)
VALUES (1, 30, NULL, NULL);
