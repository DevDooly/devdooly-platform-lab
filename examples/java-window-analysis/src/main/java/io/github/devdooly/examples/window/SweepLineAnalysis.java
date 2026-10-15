package io.github.devdooly.examples.window;

import java.util.TreeMap;
import static io.github.devdooly.examples.window.WindowAnalysis.*;

/** Correct ordered endpoint aggregation: O(n log n) time and O(n) extra memory. */
public final class SweepLineAnalysis {
    private SweepLineAnalysis() {}
    public static Metrics analyze(NormalizedInput input) {
        require(input != null, "Normalized input is required");
        var deltas = new TreeMap<Long, Integer>();
        for (var session : input.sessions()) {
            deltas.merge(session.startNanos(), 1, Integer::sum);
            deltas.merge(session.endNanos(), -1, Integer::sum);
        }
        long previous = 0, covered = 0; int active = 0, peak = 0;
        for (var boundary : deltas.entrySet()) {
            if (active > 0) { covered += boundary.getKey() - previous; }
            // Aggregate all starts/ends at this instant before observing the next half-open segment.
            active += boundary.getValue(); peak = Math.max(peak, active); previous = boundary.getKey();
        }
        if (active != 0) { throw new IllegalStateException("Balanced normalized endpoint invariant failed"); }
        return new Metrics(covered, peak);
    }
}
