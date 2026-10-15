package io.github.devdooly.examples.window;

import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.time.Instant;
import java.time.ZoneOffset;
import java.util.ArrayList;
import java.util.Collections;
import java.util.HexFormat;
import java.util.List;
import java.util.Random;
import static io.github.devdooly.examples.window.WindowAnalysis.*;

/** Public independent synthetic inputs with closed-form expected results at every measured size. */
public final class SyntheticFixtures {
    private static final Instant START = Instant.parse("2026-10-15T00:00:00Z");
    public record Fixture(String profile, int size, long seed, Window window, List<Session> sessions, Metrics expected) {
        public Fixture { sessions = List.copyOf(sessions); }
        public String canonical() {
            var text = new StringBuilder("windowStart\t" + window.start() + "\nwindowEnd\t" + window.end() + "\nid\tstartedAt\tendedAt\tknownClockSkewNanos\n");
            for (var session : sessions) { text.append(session.id()).append('\t').append(session.startedAt()).append('\t').append(session.endedAt()).append('\t').append(session.knownClockSkewNanos()).append('\n'); }
            return text.toString();
        }
    }
    private SyntheticFixtures() {}
    public static Fixture create(String profile, int size) {
        require(("sparse".equals(profile) || "nested".equals(profile)) && size >= 1 && size <= MAX_SESSIONS, "A bounded public profile is required");
        var sessions = new ArrayList<Session>(); long seed = 20261015L + size + (profile.equals("nested") ? 1_000_000 : 0);
        for (int index = 0; index < size; index++) {
            long from = profile.equals("sparse") ? index * 17_000_000L + 1_000_000L : 0;
            long to = profile.equals("sparse") ? from + 11_000_000L : (index + 1) * 1_000_000L;
            long skew = (index % 5 - 2) * 1_000_000_000L;
            var offset = switch (index % 3) { case 0 -> ZoneOffset.ofHours(9); case 1 -> ZoneOffset.UTC; default -> ZoneOffset.ofHours(-4); };
            sessions.add(new Session("session-" + String.format(java.util.Locale.ROOT, "%05d", index),
                START.plusNanos(from + skew).atOffset(offset).toString(), START.plusNanos(to + skew).atOffset(offset).toString(), skew));
        }
        Collections.shuffle(sessions, new Random(seed));
        var expected = profile.equals("sparse") ? new Metrics(size * 11_000_000L, 1) : new Metrics(size * 1_000_000L, size);
        return new Fixture(profile, size, seed, new Window(START, START.plusSeconds(3600)), sessions, expected);
    }
    public static String sha256(String text) {
        try { return HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(text.getBytes(StandardCharsets.UTF_8))); }
        catch (java.security.NoSuchAlgorithmException impossible) { throw new IllegalStateException(impossible); }
    }
}
