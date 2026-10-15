package io.github.devdooly.examples.window;

import java.time.DateTimeException;
import java.time.Duration;
import java.time.Instant;
import java.time.OffsetDateTime;
import java.util.ArrayList;
import java.util.HashSet;
import java.util.List;
import java.util.function.Function;
import static io.github.devdooly.examples.window.WindowAnalysis.*;

public final class UtcNormalizer {
    private UtcNormalizer() {}
    public static NormalizedInput normalize(Window window, List<Session> sessions) {
        return normalizeUsing(window, sessions, text -> OffsetDateTime.parse(text).toInstant());
    }

    // Package-private only to keep the deliberately broken demonstration separate.
    static NormalizedInput normalizeUsing(Window window, List<Session> sessions, Function<String, Instant> parser) {
        require(window != null && sessions != null && sessions.size() <= MAX_SESSIONS, "A window and at most 4096 sessions are required");
        var ids = new HashSet<String>(); var clipped = new ArrayList<NormalizedSession>();
        for (var session : sessions) {
            require(session != null && validId(session.id()) && ids.add(session.id()), "Unique nonnull session IDs are required");
            long skew = session.knownClockSkewNanos();
            require(skew >= -MAX_CLOCK_SKEW_NANOS && skew <= MAX_CLOCK_SKEW_NANOS, "Known clock skew must be within five minutes");
            Instant start, end;
            try {
                start = parser.apply(timestamp(session.startedAt())).minusNanos(skew);
                end = parser.apply(timestamp(session.endedAt())).minusNanos(skew);
            } catch (DateTimeException failure) {
                throw new IllegalArgumentException("An explicit valid ISO offset timestamp and representable correction are required");
            }
            require(end.isAfter(start), "Session end must be after start on the UTC timeline");
            if (!end.isAfter(window.start()) || !start.isBefore(window.end())) { continue; }
            Instant from = start.isBefore(window.start()) ? window.start() : start;
            Instant to = end.isAfter(window.end()) ? window.end() : end;
            clipped.add(new NormalizedSession(session.id(), Duration.between(window.start(), from).toNanos(), Duration.between(window.start(), to).toNanos()));
        }
        return new NormalizedInput(window.durationNanos(), clipped);
    }

    private static String timestamp(String value) {
        require(value != null && value.length() <= 48 && value.matches(".*(?:Z|[+-][0-9]{2}:[0-9]{2})"), "Timestamp must include Z or an explicit numeric offset");
        return value;
    }
}
