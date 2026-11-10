package io.github.devdooly.platformlab.jobs;

import java.time.Duration;
import java.time.Instant;
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static io.github.devdooly.platformlab.jobs.ResourceAdmissionPolicy.*;

/** Synthetic policy arithmetic only; no database, storage reader or production thresholds. */
class ResourceAdmissionPolicyTest {
    private static final Instant NOW = Instant.parse("2026-10-18T00:00:00Z");
    private static final Bounds SYNTHETIC_BOUNDS = new Bounds(5, 2, 3, 2, 7);
    private static final Policy SYNTHETIC_POLICY = new Policy(Duration.ofSeconds(2), 11, 13, SYNTHETIC_BOUNDS);
    // Independent expected arithmetic: DB 5+10*2+2*3 + reserve11 =42.
    // Garage (10+2*4194304)*2+3*7 + reserve13 =16777270.
    private static final long DB_REQUIRED = 42, GARAGE_REQUIRED = 16_777_270;

    @Test void requiresBothStorageBudgetsAndKeepsReserveAtTheExactBoundary() {
        assertEquals(Decision.STORAGE_ESTIMATE_FITS, decide(input(DB_REQUIRED, GARAGE_REQUIRED)));
        assertEquals(Decision.DATABASE_BUDGET_EXCEEDED, decide(input(DB_REQUIRED - 1, Long.MAX_VALUE)));
        assertEquals(Decision.GARAGE_BUDGET_EXCEEDED, decide(input(Long.MAX_VALUE, GARAGE_REQUIRED - 1)));
        Input swapped = new Input(10, 2, snapshot(Storage.GARAGE, DB_REQUIRED, NOW), snapshot(Storage.DATABASE, GARAGE_REQUIRED, NOW));
        assertEquals(Decision.INVALID_CAPACITY_SCOPE, decide(swapped));
        assertEquals(Decision.INVALID_CAPACITY, decide(input(-1, GARAGE_REQUIRED)));
    }

    @Test void rejectsMissingIncompleteFutureAndStaleMeasurements() {
        Snapshot db = snapshot(Storage.DATABASE, DB_REQUIRED, NOW);
        Snapshot garage = snapshot(Storage.GARAGE, GARAGE_REQUIRED, NOW);
        assertEquals(Decision.DATABASE_CAPACITY_UNKNOWN, decide(new Input(10, 2, null, garage)));
        assertEquals(Decision.GARAGE_CAPACITY_UNKNOWN, decide(new Input(10, 2, db, null)));
        assertEquals(Decision.DATABASE_CAPACITY_UNKNOWN, decide(new Input(10, 2,
            new Snapshot(Storage.DATABASE, Coverage.UNKNOWN, NOW, Long.MAX_VALUE), garage)));
        assertEquals(Decision.GARAGE_CAPACITY_UNKNOWN, decide(new Input(10, 2, db,
            new Snapshot(Storage.GARAGE, Coverage.UNKNOWN, NOW, Long.MAX_VALUE))));
        assertEquals(Decision.FUTURE_OBSERVATION, decide(new Input(10, 2, snapshot(Storage.DATABASE, DB_REQUIRED, NOW.plusNanos(1)), garage)));
        assertEquals(Decision.STORAGE_ESTIMATE_FITS, decide(new Input(10, 2, snapshot(Storage.DATABASE, DB_REQUIRED, NOW.minusSeconds(2)), garage)));
        assertEquals(Decision.STALE_OBSERVATION, decide(new Input(10, 2, db, snapshot(Storage.GARAGE, GARAGE_REQUIRED, NOW.minusSeconds(2).minusNanos(1)))));
        assertEquals(Decision.INVALID_CAPACITY, decide(new Input(10, 2, new Snapshot(Storage.DATABASE, Coverage.INDEPENDENT_SELECTED_WRITE_BUDGET, null, DB_REQUIRED), garage)));
    }

    @Test void rejectsOutOfRangeInputsInvalidPoliciesAndArithmeticOverflow() {
        Input valid = input(Long.MAX_VALUE, Long.MAX_VALUE);
        assertEquals(Decision.STORAGE_ESTIMATE_FITS, decide(new Input(1_048_576, 1_000, valid.database(), valid.garage())));
        assertEquals(Decision.INVALID_INPUT, decide(null));
        assertEquals(Decision.INVALID_INPUT, evaluateNewAdmission(valid, SYNTHETIC_POLICY, null));
        for (int bytes : new int[]{-1, 0, 1_048_577}) {
            assertEquals(Decision.INVALID_INPUT, decide(new Input(bytes, 2, valid.database(), valid.garage())));
        }
        for (int events : new int[]{-1, 0, 1_001}) {
            assertEquals(Decision.INVALID_INPUT, decide(new Input(10, events, valid.database(), valid.garage())));
        }
        for (Policy invalid : new Policy[]{null,
            new Policy(Duration.ZERO, 11, 13, SYNTHETIC_BOUNDS),
            new Policy(Duration.ofNanos(-1), 11, 13, SYNTHETIC_BOUNDS),
            new Policy(Duration.ofSeconds(2), -1, 13, SYNTHETIC_BOUNDS),
            new Policy(Duration.ofSeconds(2), 11, 13, null),
            new Policy(Duration.ofSeconds(2), 11, 13, new Bounds(5, 0, 3, 2, 7))}) {
            assertEquals(Decision.INVALID_POLICY, evaluateNewAdmission(valid, invalid, NOW));
        }
        for (Bounds overflow : new Bounds[]{
            new Bounds(5, Long.MAX_VALUE, 3, 2, 7),
            new Bounds(Long.MAX_VALUE, 2, 3, 2, 7),
            new Bounds(5, 2, 3, Long.MAX_VALUE, 7),
            new Bounds(5, 2, 3, 2, Long.MAX_VALUE)}) {
            assertEquals(Decision.ESTIMATE_OVERFLOW, evaluateNewAdmission(valid, new Policy(Duration.ofSeconds(2), 11, 13, overflow), NOW));
        }
        assertEquals(Decision.RESERVE_OVERFLOW, evaluateNewAdmission(valid, new Policy(Duration.ofSeconds(2), Long.MAX_VALUE, 13, SYNTHETIC_BOUNDS), NOW));
        assertEquals(Decision.RESERVE_OVERFLOW, evaluateNewAdmission(valid, new Policy(Duration.ofSeconds(2), 11, Long.MAX_VALUE, SYNTHETIC_BOUNDS), NOW));
    }

    private static Snapshot snapshot(Storage storage, long available, Instant at) {
        return new Snapshot(storage, Coverage.INDEPENDENT_SELECTED_WRITE_BUDGET, at, available);
    }
    private static Input input(long database, long garage) {
        return new Input(10, 2, snapshot(Storage.DATABASE, database, NOW), snapshot(Storage.GARAGE, garage, NOW));
    }
    private static Decision decide(Input input) {
        return evaluateNewAdmission(input, SYNTHETIC_POLICY, NOW);
    }
}
