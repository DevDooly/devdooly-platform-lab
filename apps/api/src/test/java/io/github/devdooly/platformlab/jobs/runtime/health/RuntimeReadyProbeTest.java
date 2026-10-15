package io.github.devdooly.platformlab.jobs.runtime.health;

import io.github.devdooly.platformlab.jobs.runtime.health.RuntimeReadyProbe.Health;
import io.github.devdooly.platformlab.jobs.runtime.health.RuntimeReadyProbe.Identity;
import io.github.devdooly.platformlab.jobs.runtime.health.RuntimeReadyProbe.Record;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.attribute.PosixFilePermissions;
import java.util.UUID;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.condition.EnabledOnOs;
import org.junit.jupiter.api.condition.OS;
import org.junit.jupiter.api.io.TempDir;
import static org.assertj.core.api.Assertions.*;

class RuntimeReadyProbeTest {
    private static final UUID INSTANCE = UUID.fromString("11111111-1111-1111-1111-111111111111");
    private static final UUID BOOT = UUID.fromString("22222222-2222-2222-2222-222222222222");
    private static final String POD = "33333333-3333-3333-3333-333333333333";
    private static final String SOURCE = "a".repeat(40);
    private static final Identity IDENTITY = new Identity(1, 12345, BOOT);
    private static final long NOW = 10_000_000_000L;
    private static final String GOLDEN = "1\n11111111-1111-1111-1111-111111111111\n1\n12345\n"
        + "22222222-2222-2222-2222-222222222222\n33333333-3333-3333-3333-333333333333\n"
        + "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa\nREADY\nEXPORT\n10000000000\n250000000000\n";

    private Record value(Health health, String stage) {
        return new Record(INSTANCE, IDENTITY, POD, SOURCE, health, stage, NOW,
            health == Health.READY ? NOW + RuntimeReadyProbe.MAX_TTL_NANOS : NOW);
    }

    @Test void independentGoldenRoundTripsAndReadyNeedsAnActualBoundary() {
        byte[] raw = GOLDEN.getBytes(StandardCharsets.US_ASCII);
        assertThat(value(Health.READY, "EXPORT").bytes()).isEqualTo(raw);
        var record = RuntimeReadyProbe.parse(raw);
        assertThat(RuntimeReadyProbe.ready(record, IDENTITY, POD, SOURCE, NOW)).isTrue();
    }
    @Test void absentPartialExtraMalformedAndOversizeRecordsFailClosed() {
        for (String input : new String[] {"", "1\n", GOLDEN + "extra\n", GOLDEN.replace("1\n", "2\n"),
                GOLDEN.replace("\nREADY\n", "\nRUNNING\n"), GOLDEN.replace("\nEXPORT\n", "\nUNKNOWN\n"),
                GOLDEN.replace("aaaaaaaa", "zzzzzzzz"), GOLDEN.replace("12345", "-12345"),
                GOLDEN.replace("\n1\n12345", "\n0\n12345"), GOLDEN.replace("12345", "0"),
                GOLDEN.replace("\n", "\r\n"), GOLDEN.replace("EXPORT", "EXPÖRT"),
                GOLDEN.replace("250000000000", "250000000001"), GOLDEN.replace("250000000000", "9999999999"),
                GOLDEN.substring(0, GOLDEN.length() - 1), "x".repeat(RuntimeReadyProbe.MAX_BYTES + 1)}) {
            assertThatThrownBy(() -> RuntimeReadyProbe.parse(input.getBytes(StandardCharsets.UTF_8))).isInstanceOf(RuntimeException.class);
        }
    }
    @Test void exactExpiryAndFutureProgressAreNotReady() {
        var record = value(Health.READY, "EXPORT");
        assertThat(RuntimeReadyProbe.ready(record, IDENTITY, POD, SOURCE, record.validUntilBootNanos() - 1)).isTrue();
        assertThat(RuntimeReadyProbe.ready(record, IDENTITY, POD, SOURCE, record.validUntilBootNanos())).isFalse();
        assertThat(RuntimeReadyProbe.ready(record, IDENTITY, POD, SOURCE, NOW - 1)).isFalse();
    }
    @Test void foreignPidAndRestartedPidOneCannotReuseOldRecord() {
        var record = value(Health.READY, "IDLE");
        assertThat(RuntimeReadyProbe.ready(record, new Identity(2, 12345, BOOT), POD, SOURCE, NOW)).isFalse();
        assertThat(RuntimeReadyProbe.ready(record, new Identity(1, 12346, BOOT), POD, SOURCE, NOW)).isFalse();
        assertThat(RuntimeReadyProbe.ready(record, new Identity(1, 12345, INSTANCE), POD, SOURCE, NOW)).isFalse();
    }
    @Test void foreignPodOrImageSourceIsNotReady() {
        var record = value(Health.READY, "CONSUME");
        assertThat(RuntimeReadyProbe.ready(record, IDENTITY, INSTANCE.toString(), SOURCE, NOW)).isFalse();
        assertThat(RuntimeReadyProbe.ready(record, IDENTITY, POD, "b".repeat(40), NOW)).isFalse();
        assertThatThrownBy(() -> RuntimeReadyProbe.ready(record, IDENTITY, null, SOURCE, NOW)).isInstanceOf(IllegalArgumentException.class);
    }
    @Test void startupPausedAndStoppedNeverClaimReady() {
        assertThat(RuntimeReadyProbe.ready(value(Health.STARTING, "STARTING"), IDENTITY, POD, SOURCE, NOW)).isFalse();
        assertThat(RuntimeReadyProbe.ready(value(Health.NOT_READY, "STOPPED"), IDENTITY, POD, SOURCE, NOW)).isFalse();
        assertThatThrownBy(() -> value(Health.READY, "STOPPED")).isInstanceOf(IllegalArgumentException.class);
        assertThatThrownBy(() -> value(Health.READY, "STARTING")).isInstanceOf(IllegalArgumentException.class);
    }
    @Test void bootClockPreservesNanosAndRejectsOverflowOrInvalidProcText() {
        assertThat(RuntimeReadyProbe.uptimeNanos("10.000000001 9.23\n")).isEqualTo(NOW + 1);
        assertThat(RuntimeReadyProbe.uptimeNanos("10.00 0.00\n")).isEqualTo(NOW);
        for (String text : new String[] {"-1.0 0.0", "10 0", "10.0 0.0 extra", "999999999999.0 0.0", "NaN 0.0"}) {
            assertThatThrownBy(() -> RuntimeReadyProbe.uptimeNanos(text)).isInstanceOf(RuntimeException.class);
        }
    }
    @Test void procIdentityUsesExactPidAndStartTicksDespiteSpacesInCommand() {
        String text = "1 (java process) R " + "0 ".repeat(18) + "12345 0";
        assertThat(RuntimeReadyProbe.startTicks(text, 1)).isEqualTo(12345);
        assertThatThrownBy(() -> RuntimeReadyProbe.startTicks(text, 2)).isInstanceOf(IllegalArgumentException.class);
        assertThatThrownBy(() -> RuntimeReadyProbe.startTicks("1 (java) R 0", 1)).isInstanceOf(IllegalArgumentException.class);
    }
    @Test @EnabledOnOs(OS.LINUX) void realFileRequiresExactModeOwnerAndNoSymlink(@TempDir Path directory) throws Exception {
        Path folder = Files.createDirectory(directory.resolve("private"), PosixFilePermissions.asFileAttribute(PosixFilePermissions.fromString("rwx------")));
        Path file = folder.resolve("ready"); Files.write(file, GOLDEN.getBytes(StandardCharsets.US_ASCII));
        Files.setPosixFilePermissions(file, PosixFilePermissions.fromString("rw-------"));
        long uid = ((Number) Files.getAttribute(file, "unix:uid")).longValue();
        assertThat(RuntimeReadyProbe.readPrivate(file, uid)).isEqualTo(value(Health.READY, "EXPORT"));
        assertThatThrownBy(() -> RuntimeReadyProbe.readPrivate(file, uid + 1)).isInstanceOf(IllegalArgumentException.class);
        Files.setPosixFilePermissions(file, PosixFilePermissions.fromString("rw-r--r--"));
        assertThatThrownBy(() -> RuntimeReadyProbe.readPrivate(file, uid)).isInstanceOf(IllegalArgumentException.class);
        Files.setPosixFilePermissions(file, PosixFilePermissions.fromString("rw-------"));
        Path link = folder.resolve("link"); Files.createSymbolicLink(link, file);
        assertThatThrownBy(() -> RuntimeReadyProbe.readPrivate(link, uid)).isInstanceOf(IllegalArgumentException.class);
    }
    @Test @EnabledOnOs(OS.LINUX) void realPartialAndMissingFilesNeverPass(@TempDir Path directory) throws Exception {
        Path folder = Files.createDirectory(directory.resolve("private"), PosixFilePermissions.asFileAttribute(PosixFilePermissions.fromString("rwx------")));
        long uid = ((Number) Files.getAttribute(folder, "unix:uid")).longValue(); Path file = folder.resolve("ready");
        assertThatThrownBy(() -> RuntimeReadyProbe.readPrivate(file, uid)).isInstanceOf(Exception.class);
        Files.writeString(file, "1\npartial"); Files.setPosixFilePermissions(file, PosixFilePermissions.fromString("rw-------"));
        assertThatThrownBy(() -> RuntimeReadyProbe.readPrivate(file, uid)).isInstanceOf(IllegalArgumentException.class);
    }
}
