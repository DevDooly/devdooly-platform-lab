package io.github.devdooly.platformlab.jobs.runtime;

import io.github.devdooly.platformlab.jobs.runtime.health.RuntimeReadyProbe;
import io.github.devdooly.platformlab.jobs.runtime.health.RuntimeReadyProbe.Health;
import io.github.devdooly.platformlab.jobs.runtime.health.RuntimeReadyProbe.Identity;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.UUID;
import java.util.concurrent.atomic.AtomicLong;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.condition.EnabledOnOs;
import org.junit.jupiter.api.condition.OS;
import org.junit.jupiter.api.io.TempDir;
import static org.assertj.core.api.Assertions.*;

@EnabledOnOs(OS.LINUX)
class LocalRuntimeProgressTest {
    private static final String SOURCE = "a".repeat(40), POD = "33333333-3333-3333-3333-333333333333";
    private static final Identity IDENTITY = new Identity(1, 12345, UUID.fromString("22222222-2222-2222-2222-222222222222"));
    private LocalRuntimeProgress create(Path directory, AtomicLong clock) throws Exception {
        long uid = ((Number) Files.getAttribute(directory, "unix:uid")).longValue();
        return new LocalRuntimeProgress(directory.resolve("private/ready"), IDENTITY, SOURCE, POD, uid, clock::get);
    }
    private RuntimeReadyProbe.Record read(Path path) throws Exception {
        return RuntimeReadyProbe.readPrivate(path, ((Number) Files.getAttribute(path, "unix:uid")).longValue());
    }
    @Test void writesStartThenRealProgressAndLatchesStop(@TempDir Path directory) throws Exception {
        var clock = new AtomicLong(10_000_000_000L); var progress = create(directory, clock); Path file = directory.resolve("private/ready");
        progress.starting(); assertThat(read(file).health()).isEqualTo(Health.STARTING);
        progress.committed("EXPORT"); assertThat(RuntimeReadyProbe.ready(read(file), IDENTITY, POD, SOURCE, clock.get())).isTrue();
        progress.notReady(); progress.committed("IDLE"); progress.starting();
        assertThat(read(file).health()).isEqualTo(Health.NOT_READY);
    }
    @Test void eachBoundaryRefreshesBootTimeWithoutBackgroundThread(@TempDir Path directory) throws Exception {
        var clock = new AtomicLong(10_000_000_000L); var progress = create(directory, clock); Path file = directory.resolve("private/ready");
        progress.committed("PUBLISH"); var first = read(file); byte[] before = Files.readAllBytes(file);
        clock.addAndGet(1_000_000_000L); assertThat(Files.readAllBytes(file)).isEqualTo(before);
        progress.committed("CONSUME"); var next = read(file);
        assertThat(next.instanceId()).isEqualTo(first.instanceId()); assertThat(next.writtenBootNanos()).isEqualTo(clock.get());
    }
    @Test void newInstanceStartsNotReadyEvenWhenOldOwnedFileExists(@TempDir Path directory) throws Exception {
        var clock = new AtomicLong(10_000_000_000L); var old = create(directory, clock); Path file = directory.resolve("private/ready");
        old.committed("IDLE"); var previous = read(file);
        var replacement = create(directory, clock); replacement.starting();
        assertThat(read(file).instanceId()).isNotEqualTo(previous.instanceId()); assertThat(read(file).health()).isEqualTo(Health.STARTING);
    }
    @Test void stopBeforeFirstCommitCannotBecomeReady(@TempDir Path directory) throws Exception {
        var progress = create(directory, new AtomicLong(10_000_000_000L)); Path file = directory.resolve("private/ready");
        progress.notReady(); progress.starting(); progress.committed("EXPORT");
        assertThat(read(file).health()).isEqualTo(Health.NOT_READY);
    }
    @Test void failedClockInvalidatesOldRecordAndPreventsFurtherProgress(@TempDir Path directory) throws Exception {
        var clock = new AtomicLong(10_000_000_000L); var progress = create(directory, clock); Path file = directory.resolve("private/ready");
        progress.committed("IDLE"); clock.set(-1);
        assertThatThrownBy(() -> progress.committed("EXPORT")).isInstanceOf(RuntimeProgress.ProgressUnavailableException.class);
        progress.notReady(); assertThat(Files.exists(file)).isFalse();
        assertThatThrownBy(() -> progress.committed("IDLE")).isInstanceOf(RuntimeProgress.ProgressUnavailableException.class);
    }
}
