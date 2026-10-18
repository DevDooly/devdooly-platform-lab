package io.github.devdooly.platformlab.jobs;

import java.time.Duration;
import java.time.Instant;
import io.github.devdooly.platformlab.jobs.ResourceAdmissionPolicy.Bounds;
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static io.github.devdooly.platformlab.jobs.SharedPoolResourceAdmissionPolicy.*;

/** Hand-calculated synthetic budgets only; no real reader, defaults or reservation. */
class SharedPoolResourceAdmissionPolicyTest {
    private static final Instant NOW = Instant.parse("2026-10-19T00:00:00Z");
    private static final Bounds BOUNDS = new Bounds(5, 2, 3, 2, 7);
    private static final Policy POLICY = new Policy(Duration.ofSeconds(2), 11, BOUNDS);
    // Source10/events2: DB31, Garage16,777,257; combined16,777,288.
    // Common reserve11 + earlier UNREFLECTED charge7 + other-writer allowance5 => free16,777,311.
    private static final long EXACT_FREE = 16_777_311;

    @Test void individuallyFittingDomainsCanStillExceedOneSharedPool() {
        long sharedFree = 16_777_270;
        var independent = new ResourceAdmissionPolicy.Input(10, 2,
            new ResourceAdmissionPolicy.Snapshot(ResourceAdmissionPolicy.Storage.DATABASE,
                ResourceAdmissionPolicy.Coverage.INDEPENDENT_SELECTED_WRITE_BUDGET, NOW, sharedFree),
            new ResourceAdmissionPolicy.Snapshot(ResourceAdmissionPolicy.Storage.GARAGE,
                ResourceAdmissionPolicy.Coverage.INDEPENDENT_SELECTED_WRITE_BUDGET, NOW, sharedFree));
        var oldPolicy = new ResourceAdmissionPolicy.Policy(Duration.ofSeconds(2), 11, 13, BOUNDS);
        // This old arithmetic result does NOT establish that duplicated free has a valid independent scope.
        assertEquals(ResourceAdmissionPolicy.Decision.STORAGE_ESTIMATE_FITS,
            ResourceAdmissionPolicy.evaluateNewAdmission(independent, oldPolicy, NOW));
        assertEquals(Decision.SHARED_BYTES_BUDGET_EXCEEDED, decide(pool(sharedFree, 0L, 0L, 3L, NOW)));
    }

    @Test void keepsOneReserveAtExactEqualityAndRejectsOneByteLess() {
        assertEquals(Decision.SHARED_ESTIMATE_FITS, decide(pool(EXACT_FREE, 7L, 5L, 3L, NOW)));
        assertEquals(Decision.SHARED_BYTES_BUDGET_EXCEEDED, decide(pool(EXACT_FREE - 1, 7L, 5L, 3L, NOW)));
        // All values KNOWN: common reserve11 alone exceeds free10; this is shortage, not UNKNOWN.
        assertEquals(Decision.SHARED_BYTES_BUDGET_EXCEEDED, decide(pool(10L, 0L, 0L, 3L, NOW)));
    }

    @Test void countsOnlyUnreflectedRemaindersAndDoesNotSubtractUsedBytesAgain() {
        // Free16,777,299 already excludes earlier reflected writes. No used-bytes subtraction input exists.
        assertEquals(Decision.SHARED_ESTIMATE_FITS, decide(pool(16_777_299L, 0L, 0L, 3L, NOW)));
        // An earlier remaining charge7 needs exactly seven additional free bytes.
        assertEquals(Decision.SHARED_ESTIMATE_FITS, decide(pool(16_777_306L, 7L, 0L, 3L, NOW)));
        assertEquals(Decision.SHARED_BYTES_BUDGET_EXCEEDED, decide(pool(16_777_299L, 7L, 0L, 3L, NOW)));
        assertEquals(Decision.ACCOUNTING_UNKNOWN, decide(new Snapshot(Scope.SHARED_DATABASE_GARAGE_POOL,
            Accounting.UNKNOWN, NOW, EXACT_FREE, 0L, 0L, 3L)));
    }

    @Test void requiresThreeKnownGarageObjectSlotsApartFromBytes() {
        assertEquals(Decision.SHARED_ESTIMATE_FITS, decide(pool(EXACT_FREE, 7L, 5L, 3L, NOW)));
        assertEquals(Decision.GARAGE_OBJECT_SLOTS_EXCEEDED, decide(pool(EXACT_FREE, 7L, 5L, 2L, NOW)));
        assertEquals(Decision.CAPACITY_UNKNOWN, decide(pool(EXACT_FREE, 7L, 5L, null, NOW)));
        assertEquals(Decision.INVALID_CAPACITY, decide(pool(EXACT_FREE, 7L, 5L, -1L, NOW)));
    }

    @Test void rejectsUnknownScopeAccountingFutureAndStaleObservations() {
        assertEquals(Decision.CAPACITY_UNKNOWN, decide(null));
        assertEquals(Decision.CAPACITY_UNKNOWN, decide(new Snapshot(Scope.UNKNOWN,
            Accounting.VERIFIED_DISJOINT_UNREFLECTED_REMAINDERS, NOW, EXACT_FREE, 7L, 5L, 3L)));
        assertEquals(Decision.INVALID_CAPACITY_SCOPE, decide(new Snapshot(Scope.INDEPENDENT_DOMAIN,
            Accounting.VERIFIED_DISJOINT_UNREFLECTED_REMAINDERS, NOW, EXACT_FREE, 7L, 5L, 3L)));
        assertEquals(Decision.CAPACITY_UNKNOWN, decide(pool(null, 7L, 5L, 3L, NOW)));
        assertEquals(Decision.CAPACITY_UNKNOWN, decide(pool(EXACT_FREE, null, 5L, 3L, NOW)));
        assertEquals(Decision.CAPACITY_UNKNOWN, decide(pool(EXACT_FREE, 7L, null, 3L, NOW)));
        assertEquals(Decision.INVALID_CAPACITY, decide(pool(EXACT_FREE, 7L, 5L, 3L, null)));
        assertEquals(Decision.FUTURE_OBSERVATION, decide(pool(EXACT_FREE, 7L, 5L, 3L, NOW.plusNanos(1))));
        assertEquals(Decision.SHARED_ESTIMATE_FITS, decide(pool(EXACT_FREE, 7L, 5L, 3L, NOW.minusSeconds(2))));
        assertEquals(Decision.STALE_OBSERVATION, decide(pool(EXACT_FREE, 7L, 5L, 3L, NOW.minusSeconds(2).minusNanos(1))));
    }

    @Test void rejectsInvalidInputsPoliciesAndEachSharedArithmeticOverflow() {
        Input valid = new Input(10, 2, pool(Long.MAX_VALUE, 0L, 0L, 3L, NOW));
        assertEquals(Decision.INVALID_INPUT, evaluateNewAdmission(null, POLICY, NOW));
        assertEquals(Decision.INVALID_INPUT, evaluateNewAdmission(valid, POLICY, null));
        assertEquals(Decision.INVALID_INPUT, evaluateNewAdmission(new Input(0, 2, valid.pool()), POLICY, NOW));
        assertEquals(Decision.INVALID_INPUT, evaluateNewAdmission(new Input(1_048_577, 2, valid.pool()), POLICY, NOW));
        assertEquals(Decision.INVALID_INPUT, evaluateNewAdmission(new Input(10, 1_001, valid.pool()), POLICY, NOW));
        assertEquals(Decision.SHARED_ESTIMATE_FITS, evaluateNewAdmission(new Input(1_048_576, 1_000, valid.pool()), POLICY, NOW));
        assertEquals(Decision.INVALID_POLICY, evaluateNewAdmission(valid, null, NOW));
        assertEquals(Decision.INVALID_POLICY, evaluateNewAdmission(valid, new Policy(Duration.ZERO, 11, BOUNDS), NOW));
        assertEquals(Decision.INVALID_POLICY, evaluateNewAdmission(valid, new Policy(Duration.ofSeconds(2), -1, BOUNDS), NOW));
        assertEquals(Decision.INVALID_POLICY, evaluateNewAdmission(valid,
            new Policy(Duration.ofSeconds(2), 11, new Bounds(5, 0, 3, 2, 7)), NOW));
        // DB fits long (MAX-14), Garage8,388,621 fits long; their shared sum overflows.
        assertEquals(Decision.ARITHMETIC_OVERFLOW, evaluateNewAdmission(valid,
            new Policy(Duration.ofSeconds(2), 11, new Bounds(Long.MAX_VALUE - 26, 1, 1, 1, 1)), NOW));
        assertEquals(Decision.ARITHMETIC_OVERFLOW, evaluateNewAdmission(valid,
            new Policy(Duration.ofSeconds(2), 11, new Bounds(5, Long.MAX_VALUE, 3, 2, 7)), NOW));
        assertEquals(Decision.ARITHMETIC_OVERFLOW, decide(pool(Long.MAX_VALUE, Long.MAX_VALUE, 1L, 3L, NOW)));
        assertEquals(Decision.ARITHMETIC_OVERFLOW, decide(pool(Long.MAX_VALUE, Long.MAX_VALUE, 0L, 3L, NOW)));
    }

    private static Snapshot pool(Long free, Long unreflected, Long otherWriters, Long objectSlots, Instant observedAt) {
        return new Snapshot(Scope.SHARED_DATABASE_GARAGE_POOL,
            Accounting.VERIFIED_DISJOINT_UNREFLECTED_REMAINDERS, observedAt, free, unreflected, otherWriters, objectSlots);
    }
    private static Decision decide(Snapshot pool) {
        return evaluateNewAdmission(new Input(10, 2, pool), POLICY, NOW);
    }
}
