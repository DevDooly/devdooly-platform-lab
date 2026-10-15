package io.github.devdooly.examples.window;

/** Deterministic public fixture fingerprints; this CLI does no timed work. */
public final class FixtureManifest {
    private FixtureManifest() {}
    public static void main(String[] args) {
        if (args.length != 0) { throw new IllegalArgumentException("No arguments are accepted"); }
        System.out.println("profile\tsize\tseed\trawSha256\tnormalizedSha256\tresultSha256\tcoveredNanos\tpeakConcurrentSessions");
        for (var profile : new String[]{"sparse", "nested"}) {
            for (int size : new int[]{128, 512, 2048, 4096}) {
                var fixture = SyntheticFixtures.create(profile, size);
                var input = UtcNormalizer.normalize(fixture.window(), fixture.sessions());
                if (!fixture.expected().equals(QuadraticBoundaryScan.analyze(input)) || !fixture.expected().equals(SweepLineAnalysis.analyze(input))) {
                    throw new IllegalStateException("Fixture verification failed");
                }
                var normalized = new StringBuilder("windowNanos=" + input.windowNanos() + "\n");
                for (var session : input.sessions()) { normalized.append(session.id()).append('\t').append(session.startNanos()).append('\t').append(session.endNanos()).append('\n'); }
                System.out.printf(java.util.Locale.ROOT, "%s\t%d\t%d\t%s\t%s\t%s\t%d\t%d%n", profile, size, fixture.seed(),
                    SyntheticFixtures.sha256(fixture.canonical()), SyntheticFixtures.sha256(normalized.toString()),
                    SyntheticFixtures.sha256(fixture.expected().canonical()), fixture.expected().coveredNanos(), fixture.expected().peakConcurrentSessions());
            }
        }
    }
}
