package io.github.devdooly.examples.window;

import java.util.concurrent.TimeUnit;
import org.openjdk.jmh.annotations.Benchmark;
import org.openjdk.jmh.annotations.BenchmarkMode;
import org.openjdk.jmh.annotations.Fork;
import org.openjdk.jmh.annotations.Level;
import org.openjdk.jmh.annotations.Measurement;
import org.openjdk.jmh.annotations.Mode;
import org.openjdk.jmh.annotations.OutputTimeUnit;
import org.openjdk.jmh.annotations.Param;
import org.openjdk.jmh.annotations.Scope;
import org.openjdk.jmh.annotations.Setup;
import org.openjdk.jmh.annotations.State;
import org.openjdk.jmh.annotations.Threads;
import org.openjdk.jmh.annotations.Warmup;
import static io.github.devdooly.examples.window.WindowAnalysis.*;

/** Exactly one complete analysis per invocation. Parsing and correctness checks are outside timing. */
@State(Scope.Thread)
@BenchmarkMode(Mode.AverageTime)
@OutputTimeUnit(TimeUnit.MICROSECONDS)
@Threads(1)
@Fork(value = 3, jvmArgs = {"-Xms256m", "-Xmx256m", "-XX:+UseG1GC", "-Duser.timezone=Asia/Seoul"})
@Warmup(iterations = 2, time = 500, timeUnit = TimeUnit.MILLISECONDS)
@Measurement(iterations = 5, time = 500, timeUnit = TimeUnit.MILLISECONDS)
public class WindowBenchmark {
    @Param({"128", "512", "2048", "4096"}) public int size;
    @Param({"sparse", "nested"}) public String profile;
    // Non-final benchmark state: JMH consumes each returned Metrics, with no internal timed loop.
    public NormalizedInput input;

    @Setup(Level.Trial)
    public void setup() {
        var fixture = SyntheticFixtures.create(profile, size);
        input = UtcNormalizer.normalize(fixture.window(), fixture.sessions());
        if (!fixture.expected().equals(QuadraticBoundaryScan.analyze(input))
            || !fixture.expected().equals(SweepLineAnalysis.analyze(input))) {
            throw new IllegalStateException("Closed-form synthetic fixture verification failed");
        }
    }

    @Benchmark public Metrics quadratic() { return QuadraticBoundaryScan.analyze(input); }
    @Benchmark public Metrics sweep() { return SweepLineAnalysis.analyze(input); }
}
