package io.github.devdooly.examples.window;

import java.util.TreeSet;
import static io.github.devdooly.examples.window.WindowAnalysis.*;

/** Correct reference implementation: every elementary segment scans every session, O(n^2). */
public final class QuadraticBoundaryScan {
    private QuadraticBoundaryScan() {}
    public static Metrics analyze(NormalizedInput input) {
        require(input != null, "Normalized input is required");
        var boundaries = new TreeSet<Long>(); boundaries.add(0L); boundaries.add(input.windowNanos());
        for (var session : input.sessions()) { boundaries.add(session.startNanos()); boundaries.add(session.endNanos()); }
        Long previous = null; long covered = 0; int peak = 0;
        for (long boundary : boundaries) {
            if (previous != null) {
                int active = 0;
                for (var session : input.sessions()) {
                    if (session.startNanos() <= previous && session.endNanos() > previous) { active++; }
                }
                if (active > 0) { covered += boundary - previous; }
                peak = Math.max(peak, active);
            }
            previous = boundary;
        }
        return new Metrics(covered, peak);
    }
}
