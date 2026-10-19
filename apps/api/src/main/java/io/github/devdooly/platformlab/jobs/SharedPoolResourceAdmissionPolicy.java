package io.github.devdooly.platformlab.jobs;

import java.time.Duration;
import java.time.Instant;
import io.github.devdooly.platformlab.jobs.ResourceAdmissionPolicy.Bounds;

/**
 * Unwired shared-pool arithmetic candidate. It establishes no reader provenance,
 * physical reservation, writer exclusion, admission fence or authoritative clock.
 * Existing-run source/identity checks must return before this NEW-admission call.
 */
public final class SharedPoolResourceAdmissionPolicy {
    public enum Scope { UNKNOWN, SHARED_DATABASE_GARAGE_POOL, INDEPENDENT_DOMAIN }
    public enum Accounting { UNKNOWN, VERIFIED_DISJOINT_UNREFLECTED_REMAINDERS }
    public enum Decision {
        SHARED_ESTIMATE_FITS, INVALID_INPUT, INVALID_POLICY, INVALID_CAPACITY_SCOPE,
        INVALID_CAPACITY, CAPACITY_UNKNOWN, ACCOUNTING_UNKNOWN, FUTURE_OBSERVATION,
        STALE_OBSERVATION, ARITHMETIC_OVERFLOW, SHARED_BYTES_BUDGET_EXCEEDED,
        GARAGE_OBJECT_SLOTS_EXCEEDED
    }

    /**
     * One selected pool, never duplicated domain free values. Null numeric fields
     * are UNKNOWN, not zero. Free already excludes reflected usage; charge holds
     * only verified UNREFLECTED remainders of earlier admissions. Reserve, charge
     * and other-writer allowance must be disjoint. Available object slots must
     * already account for quota/usage and earlier unreflected object charges.
     * Scope/accounting are required upstream contracts, not proofs made here.
     */
    public record Snapshot(Scope scope, Accounting accounting, Instant observedAt,
                           Long freeBytes, Long unreflectedChargeBytes,
                           Long otherWriterAllowanceBytes, Long availableObjectSlots) {}
    /** CanonicalSource bytes/events must be validated by the server, not retry claims. */
    public record Input(int sourceBytes, int eventCount, Snapshot pool) {}
    /** Explicit reviewed coefficients only; no operational defaults or per-domain reserves. */
    public record Policy(Duration maxSnapshotAge, long commonReserveBytes, Bounds bounds) {}

    private SharedPoolResourceAdmissionPolicy() {}

    /** FIT is only this estimate check. Caller supplies now AFTER all admission locks. */
    public static Decision evaluateNewAdmission(Input input, Policy policy, Instant now) {
        if (input == null || now == null || input.sourceBytes() < 1
            || input.sourceBytes() > ResourceAdmissionPolicy.MAX_SOURCE_BYTES
            || input.eventCount() < 1 || input.eventCount() > ResourceAdmissionPolicy.MAX_EVENTS) {
            return Decision.INVALID_INPUT;
        }
        if (!validPolicy(policy)) { return Decision.INVALID_POLICY; }
        Snapshot pool = input.pool();
        if (pool == null || pool.scope() == Scope.UNKNOWN) { return Decision.CAPACITY_UNKNOWN; }
        if (pool.scope() != Scope.SHARED_DATABASE_GARAGE_POOL) { return Decision.INVALID_CAPACITY_SCOPE; }
        if (pool.accounting() != Accounting.VERIFIED_DISJOINT_UNREFLECTED_REMAINDERS) {
            return Decision.ACCOUNTING_UNKNOWN;
        }
        if (pool.freeBytes() == null || pool.unreflectedChargeBytes() == null
            || pool.otherWriterAllowanceBytes() == null || pool.availableObjectSlots() == null) {
            return Decision.CAPACITY_UNKNOWN;
        }
        if (pool.observedAt() == null || pool.freeBytes() < 0 || pool.unreflectedChargeBytes() < 0
            || pool.otherWriterAllowanceBytes() < 0 || pool.availableObjectSlots() < 0) {
            return Decision.INVALID_CAPACITY;
        }
        if (pool.observedAt().isAfter(now)) { return Decision.FUTURE_OBSERVATION; }
        if (Duration.between(pool.observedAt(), now).compareTo(policy.maxSnapshotAge()) > 0) {
            return Decision.STALE_OBSERVATION;
        }

        long combinedEstimate;
        long reserveAndEarlierCharges;
        try {
            Bounds bounds = policy.bounds();
            long databaseEstimate = Math.addExact(bounds.databaseFixedBytes(), Math.addExact(
                Math.multiplyExact((long) input.sourceBytes(), bounds.databaseSourceFactor()),
                Math.multiplyExact((long) input.eventCount(), bounds.databaseOutcomeBound())));
            long allPayloadCaps = Math.addExact((long) input.sourceBytes(),
                2L * ResourceAdmissionPolicy.MAX_EXPORT_DOCUMENT_BYTES);
            long garageEstimate = Math.addExact(Math.multiplyExact(allPayloadCaps, bounds.garagePayloadFactor()),
                Math.multiplyExact(3L, bounds.garageObjectOverheadBound()));
            combinedEstimate = Math.addExact(databaseEstimate, garageEstimate);
            reserveAndEarlierCharges = Math.addExact(policy.commonReserveBytes(),
                Math.addExact(pool.unreflectedChargeBytes(), pool.otherWriterAllowanceBytes()));
        } catch (ArithmeticException overflow) {
            return Decision.ARITHMETIC_OVERFLOW;
        }
        if (pool.freeBytes() < reserveAndEarlierCharges) { return Decision.SHARED_BYTES_BUDGET_EXCEEDED; }
        long headroom = pool.freeBytes() - reserveAndEarlierCharges;
        if (combinedEstimate > headroom) { return Decision.SHARED_BYTES_BUDGET_EXCEEDED; }
        if (pool.availableObjectSlots() < 3) { return Decision.GARAGE_OBJECT_SLOTS_EXCEEDED; }
        return Decision.SHARED_ESTIMATE_FITS;
    }

    private static boolean validPolicy(Policy policy) {
        if (policy == null || policy.maxSnapshotAge() == null || policy.maxSnapshotAge().isNegative()
            || policy.maxSnapshotAge().isZero() || policy.commonReserveBytes() < 0 || policy.bounds() == null) {
            return false;
        }
        Bounds bounds = policy.bounds();
        return bounds.databaseFixedBytes() > 0 && bounds.databaseSourceFactor() > 0
            && bounds.databaseOutcomeBound() > 0 && bounds.garagePayloadFactor() > 0
            && bounds.garageObjectOverheadBound() > 0;
    }
}
