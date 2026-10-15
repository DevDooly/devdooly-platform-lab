package io.github.devdooly.examples.window;

import java.time.Instant;
import java.time.ZoneOffset;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Collections;
import java.util.List;
import java.util.Random;
import org.junit.jupiter.api.Test;
import static io.github.devdooly.examples.window.WindowAnalysis.*;
import static org.junit.jupiter.api.Assertions.*;

class WindowAnalysisTest {
    private static final Instant ORIGIN = Instant.parse("2026-10-15T00:00:00Z");
    private static final Window TINY = new Window(ORIGIN, ORIGIN.plusNanos(64));

    @Test void emptyIsZero() { check(List.of(), new Metrics(0, 0)); }
    @Test void adjacentSessionsDoNotOverlapAtEqualEndpoint() { check(List.of(raw("a", 0, 10), raw("b", 10, 20)), new Metrics(20, 1)); }
    @Test void nestedSessionsCountObservationSessions() { check(List.of(raw("a", 0, 30), raw("b", 10, 20), raw("c", 12, 18)), new Metrics(30, 3)); }
    @Test void sameTimeEndsAndStartsAreAggregated() { check(List.of(raw("a", 0, 10), raw("b", 0, 10), raw("c", 10, 20), raw("d", 10, 20)), new Metrics(20, 2)); }
    @Test void clipsBothEndsAndIgnoresOutsideSessions() { check(List.of(raw("a", -10, 5), raw("b", 60, 80), raw("c", -20, 0), raw("d", 64, 90)), new Metrics(9, 1)); }
    @Test void nanosecondResolutionHasNoRounding() { check(List.of(raw("a", 0, 1), raw("b", 1, 2)), new Metrics(2, 1)); }
    @Test void simultaneousEqualIntervalsHaveOneUnion() { check(List.of(raw("a", 1, 3), raw("b", 1, 3)), new Metrics(2, 2)); }

    @Test void inputOffsetLossIsAnExplicitSeparateRegression() {
        var window = new Window(ORIGIN, ORIGIN.plusSeconds(60));
        var sessions = List.of(new Session("seoul", "2026-10-15T09:00:00+09:00", "2026-10-15T09:00:10+09:00", 0));
        assertEquals(new Metrics(10_000_000_000L, 1), SweepLineAnalysis.analyze(UtcNormalizer.normalize(window, sessions)));
        assertEquals(new Metrics(0, 0), SweepLineAnalysis.analyze(DeliberatelyBrokenUtcNormalizer.normalize(window, sessions)));
    }
    @Test void sameLocalClockDifferentOffsetsRepresentDifferentInstants() {
        var window = new Window(ORIGIN, ORIGIN.plusSeconds(3600));
        var sessions = List.of(new Session("a", "2026-10-15T00:00:00Z", "2026-10-15T00:00:01Z", 0),
            new Session("b", "2026-10-15T00:00:00+09:00", "2026-10-15T00:00:01+09:00", 0));
        assertEquals(new Metrics(1_000_000_000L, 1), SweepLineAnalysis.analyze(UtcNormalizer.normalize(window, sessions)));
    }
    @Test void knownPositiveAndNegativeSkewAreSubtracted() {
        check(List.of(encoded("a", 2, 8, 100, ZoneOffset.ofHours(9)), encoded("b", 4, 10, -100, ZoneOffset.ofHours(-4))), new Metrics(8, 2));
    }
    @Test void skewBoundaryAndDayCrossingAreSupported() {
        check(List.of(encoded("a", 1, 3, MAX_CLOCK_SKEW_NANOS, ZoneOffset.ofHours(-4)), encoded("b", 3, 5, -MAX_CLOCK_SKEW_NANOS, ZoneOffset.ofHours(9))), new Metrics(4, 1));
    }
    @Test void timelineOrderingRatherThanLocalClockOrderingControlsValidation() {
        var window = new Window(ORIGIN, ORIGIN.plusSeconds(3600));
        var session = new Session("a", "2026-10-15T09:00:00+09:00", "2026-10-15T00:00:01Z", 0);
        assertEquals(new Metrics(1_000_000_000L, 1), SweepLineAnalysis.analyze(UtcNormalizer.normalize(window, List.of(session))));
    }

    @Test void independentlyGeneratedTinyGridOracleCoversOffsetsSkewClippingAndTies() {
        var random = new Random(20261015);
        for (int trial = 0; trial < 2000; trial++) {
            int count = random.nextInt(33); var sessions = new ArrayList<Session>();
            int[] grid = new int[64];
            for (int id = 0; id < count; id++) {
                int from = random.nextInt(97) - 16;
                int to = from + 1 + random.nextInt(40);
                // Oracle sees true integer endpoints before timestamp serialization; it never calls normalization.
                for (int tick = 0; tick < grid.length; tick++) { if (from <= tick && tick < to) { grid[tick]++; } }
                long skew = random.nextInt(2001) - 1000;
                var offset = switch (random.nextInt(3)) { case 0 -> ZoneOffset.UTC; case 1 -> ZoneOffset.ofHours(9); default -> ZoneOffset.ofHours(-4); };
                sessions.add(encoded("s" + id, from, to, skew, offset));
            }
            long covered = Arrays.stream(grid).filter(value -> value > 0).count();
            int peak = Arrays.stream(grid).max().orElse(0);
            check(sessions, new Metrics(covered, peak));
            Collections.shuffle(sessions, random);
            check(sessions, new Metrics(covered, peak));
        }
    }
    @Test void largeFixturesHaveIndependentClosedFormResultsAndStableInputs() {
        for (var profile : new String[]{"sparse", "nested"}) {
            for (int size : new int[]{128, 512, 2048, 4096}) {
                var fixture = SyntheticFixtures.create(profile, size);
                var before = fixture.canonical(); var input = UtcNormalizer.normalize(fixture.window(), fixture.sessions());
                assertEquals(fixture.expected(), QuadraticBoundaryScan.analyze(input));
                assertEquals(fixture.expected(), SweepLineAnalysis.analyze(input));
                assertEquals(before, fixture.canonical());
                assertEquals(before, SyntheticFixtures.create(profile, size).canonical());
                assertThrows(UnsupportedOperationException.class, () -> input.sessions().add(new NormalizedSession("x", 0, 1)));
            }
        }
    }
    @Test void windowRejectsNullNonpositiveAndOverOneHourBeforeNanosecondConversion() {
        assertThrows(IllegalArgumentException.class, () -> new Window(null, ORIGIN));
        assertThrows(IllegalArgumentException.class, () -> new Window(ORIGIN, null));
        assertThrows(IllegalArgumentException.class, () -> new Window(ORIGIN, ORIGIN));
        assertThrows(IllegalArgumentException.class, () -> new Window(ORIGIN, ORIGIN.minusNanos(1)));
        assertThrows(IllegalArgumentException.class, () -> new Window(ORIGIN, ORIGIN.plusSeconds(3600).plusNanos(1)));
        assertThrows(IllegalArgumentException.class, () -> new Window(Instant.MIN, Instant.MAX));
        assertEquals(MAX_WINDOW_NANOS, new Window(ORIGIN, ORIGIN.plusSeconds(3600)).durationNanos());
    }
    @Test void inputRejectsNullTooManyDuplicateOrInvalidIds() {
        assertThrows(IllegalArgumentException.class, () -> UtcNormalizer.normalize(null, List.of()));
        assertThrows(IllegalArgumentException.class, () -> UtcNormalizer.normalize(TINY, null));
        assertThrows(IllegalArgumentException.class, () -> UtcNormalizer.normalize(TINY, Arrays.asList((Session) null)));
        assertThrows(IllegalArgumentException.class, () -> UtcNormalizer.normalize(TINY, Collections.nCopies(MAX_SESSIONS + 1, raw("a", 0, 1))));
        assertThrows(IllegalArgumentException.class, () -> UtcNormalizer.normalize(TINY, List.of(raw("a", 0, 1), raw("a", 1, 2))));
        for (var id : new String[]{"", "a/b", "A", "x".repeat(65)}) { assertThrows(IllegalArgumentException.class, () -> UtcNormalizer.normalize(TINY, List.of(raw(id, 0, 1)))); }
        assertThrows(IllegalArgumentException.class, () -> UtcNormalizer.normalize(TINY, List.of(raw(null, 0, 1))));
    }
    @Test void rejectsAmbiguousMalformedNullEqualAndReversedTimestamps() {
        for (var value : Arrays.asList(null, "", "2026-10-15T00:00:00", "badZ", "2026-10-15T00:00:00+25:00", "x".repeat(49) + "Z")) {
            var session = new Session("a", value, ORIGIN.plusNanos(1).toString(), 0);
            assertThrows(IllegalArgumentException.class, () -> UtcNormalizer.normalize(TINY, List.of(session)));
        }
        assertThrows(IllegalArgumentException.class, () -> UtcNormalizer.normalize(TINY, List.of(new Session("a", ORIGIN.toString(), null, 0))));
        assertThrows(IllegalArgumentException.class, () -> UtcNormalizer.normalize(TINY, List.of(raw("a", 1, 1))));
        assertThrows(IllegalArgumentException.class, () -> UtcNormalizer.normalize(TINY, List.of(raw("a", 2, 1))));
    }
    @Test void rejectsClockSkewOutsideBoundsIncludingLongMinValue() {
        for (long skew : new long[]{MAX_CLOCK_SKEW_NANOS + 1, -MAX_CLOCK_SKEW_NANOS - 1, Long.MIN_VALUE, Long.MAX_VALUE}) {
            assertThrows(IllegalArgumentException.class, () -> UtcNormalizer.normalize(TINY, List.of(new Session("a", ORIGIN.toString(), ORIGIN.plusNanos(1).toString(), skew))));
        }
    }
    @Test void normalizedModelRejectsBadBoundsAndDuplicateIds() {
        assertThrows(IllegalArgumentException.class, () -> new NormalizedSession("a", -1, 1));
        assertThrows(IllegalArgumentException.class, () -> new NormalizedSession("a", 1, 1));
        assertThrows(IllegalArgumentException.class, () -> new NormalizedSession("a", 0, MAX_WINDOW_NANOS + 1));
        assertThrows(IllegalArgumentException.class, () -> new NormalizedInput(0, List.of()));
        assertThrows(IllegalArgumentException.class, () -> new NormalizedInput(1, List.of(new NormalizedSession("a", 0, 2))));
        assertThrows(IllegalArgumentException.class, () -> new NormalizedInput(2, List.of(new NormalizedSession("a", 0, 1), new NormalizedSession("a", 1, 2))));
        assertThrows(IllegalArgumentException.class, () -> new NormalizedInput(2, Arrays.asList((NormalizedSession) null)));
        assertThrows(IllegalArgumentException.class, () -> QuadraticBoundaryScan.analyze(null));
        assertThrows(IllegalArgumentException.class, () -> SweepLineAnalysis.analyze(null));
    }
    @Test void fixturesRejectUnknownNullAndUnboundedRequests() {
        assertThrows(IllegalArgumentException.class, () -> SyntheticFixtures.create(null, 1));
        assertThrows(IllegalArgumentException.class, () -> SyntheticFixtures.create("unknown", 1));
        assertThrows(IllegalArgumentException.class, () -> SyntheticFixtures.create("sparse", 0));
        assertThrows(IllegalArgumentException.class, () -> SyntheticFixtures.create("sparse", MAX_SESSIONS + 1));
    }

    private static void check(List<Session> sessions, Metrics expected) {
        var input = UtcNormalizer.normalize(TINY, sessions);
        assertEquals(expected, QuadraticBoundaryScan.analyze(input));
        assertEquals(expected, SweepLineAnalysis.analyze(input));
    }
    private static Session raw(String id, long start, long end) { return encoded(id, start, end, 0, ZoneOffset.UTC); }
    private static Session encoded(String id, long start, long end, long skew, ZoneOffset offset) {
        return new Session(id, ORIGIN.plusNanos(start + skew).atOffset(offset).toString(), ORIGIN.plusNanos(end + skew).atOffset(offset).toString(), skew);
    }
}
