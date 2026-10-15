package io.github.devdooly.examples.window;

import java.time.Duration;
import java.time.Instant;
import java.util.HashSet;
import java.util.List;

/** Independent synthetic model. A session is an observation session, not a unique physical sensor. */
public final class WindowAnalysis {
    public static final int MAX_SESSIONS = 4096;
    public static final long MAX_WINDOW_NANOS = Duration.ofHours(1).toNanos();
    public static final long MAX_CLOCK_SKEW_NANOS = Duration.ofMinutes(5).toNanos();
    private WindowAnalysis() {}

    public record Window(Instant start, Instant end) {
        public Window {
            require(start != null && end != null && end.isAfter(start), "A positive UTC window is required");
            require(Duration.between(start, end).compareTo(Duration.ofHours(1)) <= 0, "Window must not exceed one hour");
        }
        public long durationNanos() { return Duration.between(start, end).toNanos(); }
    }

    /** Known skew = recorded clock - reference clock. This is supplied synthetic calibration, not an estimator. */
    public record Session(String id, String startedAt, String endedAt, long knownClockSkewNanos) {}

    public record NormalizedSession(String id, long startNanos, long endNanos) {
        public NormalizedSession {
            require(validId(id), "A bounded lowercase ASCII session ID is required");
            require(startNanos >= 0 && endNanos > startNanos && endNanos <= MAX_WINDOW_NANOS, "A bounded nonempty clipped interval is required");
        }
    }

    public record NormalizedInput(long windowNanos, List<NormalizedSession> sessions) {
        public NormalizedInput {
            require(windowNanos > 0 && windowNanos <= MAX_WINDOW_NANOS && sessions != null && sessions.size() <= MAX_SESSIONS, "Bounded normalized input is required");
            var ids = new HashSet<String>();
            for (var session : sessions) {
                require(session != null && session.endNanos() <= windowNanos && ids.add(session.id()), "Unique nonnull intervals inside the window are required");
            }
            sessions = List.copyOf(sessions);
        }
    }

    public record Metrics(long coveredNanos, int peakConcurrentSessions) {
        public Metrics {
            require(coveredNanos >= 0 && coveredNanos <= MAX_WINDOW_NANOS && peakConcurrentSessions >= 0 && peakConcurrentSessions <= MAX_SESSIONS, "Bounded metrics are required");
        }
        public String canonical() { return "coveredNanos=" + coveredNanos + "\npeakConcurrentSessions=" + peakConcurrentSessions + "\n"; }
    }

    static boolean validId(String id) { return id != null && id.matches("[a-z0-9][a-z0-9-]{0,63}"); }
    static void require(boolean condition, String message) { if (!condition) { throw new IllegalArgumentException(message); } }
}
