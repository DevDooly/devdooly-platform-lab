package io.github.devdooly.examples.window;

import java.time.OffsetDateTime;
import java.time.ZoneOffset;
import java.util.List;
import static io.github.devdooly.examples.window.WindowAnalysis.*;

/** Intentionally incorrect public teaching fixture; never used by the benchmark or production ETL. */
public final class DeliberatelyBrokenUtcNormalizer {
    private DeliberatelyBrokenUtcNormalizer() {}
    public static NormalizedInput normalize(Window window, List<Session> sessions) {
        // BUG: discarding the supplied offset changes the instant before assigning UTC.
        return UtcNormalizer.normalizeUsing(window, sessions,
            text -> OffsetDateTime.parse(text).toLocalDateTime().toInstant(ZoneOffset.UTC));
    }
}
