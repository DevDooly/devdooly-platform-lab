package io.github.devdooly.platformlab.jobs;

import java.time.Duration;
import java.time.Instant;

/**
 * Unwired pure candidate for the NEW database-admission branch only.
 * It neither establishes measurement provenance nor reserves physical storage.
 * Existing-run identity/source checks belong to the database before this call.
 */
public final class ResourceAdmissionPolicy {
    // Reviewed CanonicalSource and ExportBundle caps; not operational capacity settings.
    public static final int MAX_SOURCE_BYTES = 1_048_576;
    public static final int MAX_EVENTS = 1_000;
    public static final int MAX_EXPORT_DOCUMENT_BYTES = 4_194_304;

    public enum Storage { DATABASE, GARAGE }
    public enum Coverage { UNKNOWN, INDEPENDENT_SELECTED_WRITE_BUDGET }
    public enum Decision {
        STORAGE_ESTIMATE_FITS, INVALID_INPUT, INVALID_POLICY, INVALID_CAPACITY,
        INVALID_CAPACITY_SCOPE, DATABASE_CAPACITY_UNKNOWN, GARAGE_CAPACITY_UNKNOWN,
        FUTURE_OBSERVATION, STALE_OBSERVATION, ESTIMATE_OVERFLOW, RESERVE_OVERFLOW,
        DATABASE_BUDGET_EXCEEDED, GARAGE_BUDGET_EXCEEDED
    }

    /** Coverage is a required upstream contract, not a fact verified by this record. */
    public record Snapshot(Storage storage, Coverage coverage, Instant observedAt, long availableBytes) {}
    /** Values must come from server-validated CanonicalSource, never a retry assertion. */
    public record Input(int sourceBytes, int eventCount, Snapshot database, Snapshot garage) {}
    /** All coefficients require independent evidence for the selected storage footprint. */
    public record Bounds(long databaseFixedBytes, long databaseSourceFactor, long databaseOutcomeBound,
                         long garagePayloadFactor, long garageObjectOverheadBound) {}
    /** No production defaults; reserve and observation age are explicitly supplied. */
    public record Policy(Duration maxSnapshotAge, long databaseReserveBytes, long garageReserveBytes, Bounds bounds) {}

    private ResourceAdmissionPolicy() {}

    /** FIT is only this estimate check; slot, source, cooldown and commit checks still apply. */
    public static Decision evaluateNewAdmission(Input input, Policy policy, Instant now) {
        if (input == null || now == null || input.sourceBytes() < 1 || input.sourceBytes() > MAX_SOURCE_BYTES
            || input.eventCount() < 1 || input.eventCount() > MAX_EVENTS) {
            return Decision.INVALID_INPUT;
        }
        if (!validPolicy(policy)) { return Decision.INVALID_POLICY; }
        Decision database = validateSnapshot(input.database(), Storage.DATABASE, policy.maxSnapshotAge(), now);
        if (database != null) { return database; }
        Decision garage = validateSnapshot(input.garage(), Storage.GARAGE, policy.maxSnapshotAge(), now);
        if (garage != null) { return garage; }

        long databaseEstimate;
        long garageEstimate;
        try {
            Bounds bounds = policy.bounds();
            databaseEstimate = Math.addExact(bounds.databaseFixedBytes(), Math.addExact(
                Math.multiplyExact((long) input.sourceBytes(), bounds.databaseSourceFactor()),
                Math.multiplyExact((long) input.eventCount(), bounds.databaseOutcomeBound())));
            long allPayloadCaps = Math.addExact((long) input.sourceBytes(), 2L * MAX_EXPORT_DOCUMENT_BYTES);
            garageEstimate = Math.addExact(Math.multiplyExact(allPayloadCaps, bounds.garagePayloadFactor()),
                Math.multiplyExact(3L, bounds.garageObjectOverheadBound()));
        } catch (ArithmeticException overflow) {
            return Decision.ESTIMATE_OVERFLOW;
        }
        long databaseRequired;
        long garageRequired;
        try {
            databaseRequired = Math.addExact(policy.databaseReserveBytes(), databaseEstimate);
            garageRequired = Math.addExact(policy.garageReserveBytes(), garageEstimate);
        } catch (ArithmeticException overflow) {
            return Decision.RESERVE_OVERFLOW;
        }
        if (input.database().availableBytes() < databaseRequired) { return Decision.DATABASE_BUDGET_EXCEEDED; }
        if (input.garage().availableBytes() < garageRequired) { return Decision.GARAGE_BUDGET_EXCEEDED; }
        return Decision.STORAGE_ESTIMATE_FITS;
    }

    private static boolean validPolicy(Policy policy) {
        if (policy == null || policy.maxSnapshotAge() == null || policy.maxSnapshotAge().isNegative()
            || policy.maxSnapshotAge().isZero() || policy.databaseReserveBytes() < 0
            || policy.garageReserveBytes() < 0 || policy.bounds() == null) { return false; }
        Bounds bounds = policy.bounds();
        return bounds.databaseFixedBytes() > 0 && bounds.databaseSourceFactor() > 0
            && bounds.databaseOutcomeBound() > 0 && bounds.garagePayloadFactor() > 0
            && bounds.garageObjectOverheadBound() > 0;
    }

    private static Decision validateSnapshot(Snapshot snapshot, Storage expected, Duration maxAge, Instant now) {
        if (snapshot == null || snapshot.coverage() == Coverage.UNKNOWN) {
            return expected == Storage.DATABASE ? Decision.DATABASE_CAPACITY_UNKNOWN : Decision.GARAGE_CAPACITY_UNKNOWN;
        }
        if (snapshot.storage() != expected) { return Decision.INVALID_CAPACITY_SCOPE; }
        if (snapshot.coverage() == null || snapshot.observedAt() == null || snapshot.availableBytes() < 0) {
            return Decision.INVALID_CAPACITY;
        }
        if (snapshot.observedAt().isAfter(now)) { return Decision.FUTURE_OBSERVATION; }
        if (Duration.between(snapshot.observedAt(), now).compareTo(maxAge) > 0) { return Decision.STALE_OBSERVATION; }
        return null;
    }
}
