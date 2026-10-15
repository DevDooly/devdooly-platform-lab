package io.github.devdooly.platformlab.jobs.runtime.health;

import java.io.IOException;
import java.nio.ByteBuffer;
import java.nio.channels.SeekableByteChannel;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.LinkOption;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;
import java.nio.file.attribute.BasicFileAttributes;
import java.util.Set;
import java.util.UUID;

/** Tiny Java-stdlib-only exec probe. Never starts Spring, a DB client, or a listener. */
public final class RuntimeReadyProbe {
    public static final Path FILE = Path.of("/tmp/lab-runtime/ready");
    public static final int MAX_BYTES = 2048;
    public static final long MAX_TTL_NANOS = 240_000_000_000L;
    public static final long WORKER_UID = 10001;
    private static final LinkOption NOFOLLOW = LinkOption.NOFOLLOW_LINKS;
    private static final Set<String> STAGES = Set.of("STARTING", "EXPORT", "PUBLISH", "CONSUME", "IDLE", "STOPPED");
    private RuntimeReadyProbe() {}

    public enum Health { STARTING, READY, NOT_READY }
    public record Identity(long pid, long startTicks, UUID bootId) {
        public Identity { require(pid > 0 && startTicks > 0 && bootId != null); }
    }
    public record Record(UUID instanceId, Identity process, String podUid, String sourceCommit,
                         Health health, String stage, long writtenBootNanos, long validUntilBootNanos) {
        public Record {
            require(instanceId != null && process != null && health != null);
            require(validUuid(podUid) && validSource(sourceCommit) && STAGES.contains(stage));
            require(writtenBootNanos >= 0 && validUntilBootNanos >= writtenBootNanos
                && validUntilBootNanos - writtenBootNanos <= MAX_TTL_NANOS);
            require(health != Health.READY || (!Set.of("STARTING", "STOPPED").contains(stage)
                && validUntilBootNanos > writtenBootNanos));
            require(health == Health.READY || validUntilBootNanos == writtenBootNanos);
        }
        public byte[] bytes() {
            String value = "1\n" + instanceId + "\n" + process.pid() + "\n" + process.startTicks() + "\n"
                + process.bootId() + "\n" + podUid + "\n" + sourceCommit + "\n" + health + "\n" + stage + "\n"
                + writtenBootNanos + "\n" + validUntilBootNanos + "\n";
            byte[] raw = value.getBytes(StandardCharsets.US_ASCII); require(raw.length <= MAX_BYTES); return raw;
        }
    }

    public static Record parse(byte[] bytes) {
        require(bytes.length > 0 && bytes.length <= MAX_BYTES);
        for (byte value : bytes) { require(value == '\n' || (value >= 32 && value <= 126)); }
        String[] fields = new String(bytes, StandardCharsets.US_ASCII).split("\n", -1);
        require(fields.length == 12 && fields[0].equals("1") && fields[11].isEmpty());
        require(validUuid(fields[1]) && validUuid(fields[4]));
        return new Record(UUID.fromString(fields[1]), new Identity(number(fields[2]), number(fields[3]), UUID.fromString(fields[4])),
            fields[5], fields[6], Health.valueOf(fields[7]), fields[8], number(fields[9]), number(fields[10]));
    }

    public static boolean ready(Record value, Identity current, String expectedPodUid, String expectedSource, long nowBootNanos) {
        require(validUuid(expectedPodUid) && validSource(expectedSource) && nowBootNanos >= 0);
        return value.health() == Health.READY && current.pid() == 1 && value.process().equals(current)
            && value.podUid().equals(expectedPodUid) && value.sourceCommit().equals(expectedSource)
            && value.writtenBootNanos() <= nowBootNanos && nowBootNanos < value.validUntilBootNanos();
    }

    public static long uptimeNanos(String text) {
        require(text != null && text.length() <= 128);
        String[] values = text.strip().split(" +");
        require(values.length == 2 && values[0].matches("[0-9]{1,12}\\.[0-9]{1,9}")
            && values[1].matches("[0-9]{1,15}\\.[0-9]{1,9}"));
        String[] parts = values[0].split("\\.");
        return Math.addExact(Math.multiplyExact(number(parts[0]), 1_000_000_000L),
            number(parts[1] + "0".repeat(9 - parts[1].length())));
    }

    public static long startTicks(String text, long expectedPid) {
        require(text != null && text.length() <= 4096);
        int open = text.indexOf('('), close = text.lastIndexOf(')');
        require(open > 0 && close > open && text.substring(0, open).strip().equals(Long.toString(expectedPid)));
        String[] fields = text.substring(close + 1).strip().split(" +");
        require(fields.length >= 20);
        long ticks = number(fields[19]); require(ticks > 0); return ticks;
    }

    public static Identity linuxIdentity(long pid) throws IOException {
        require(pid > 0);
        String boot = boundedText(Path.of("/proc/sys/kernel/random/boot_id"), 128).strip(); require(validUuid(boot));
        return new Identity(pid, startTicks(boundedText(Path.of("/proc/" + pid + "/stat"), 4096), pid), UUID.fromString(boot));
    }

    public static long linuxUptimeNanos() throws IOException { return uptimeNanos(boundedText(Path.of("/proc/uptime"), 128)); }

    private static String boundedText(Path path, int maximum) throws IOException {
        try (var stream = Files.newInputStream(path)) {
            byte[] raw = stream.readNBytes(maximum + 1); require(raw.length > 0 && raw.length <= maximum);
            return new String(raw, StandardCharsets.US_ASCII);
        }
    }

    public static void privateDirectory(Path path, long expectedUid) throws IOException {
        require(path.isAbsolute() && path.normalize().equals(path) && path.toRealPath().equals(path)
            && Files.isDirectory(path, NOFOLLOW) && !Files.isSymbolicLink(path));
        require(((Number) Files.getAttribute(path, "unix:uid", NOFOLLOW)).longValue() == expectedUid
            && (((Number) Files.getAttribute(path, "unix:mode", NOFOLLOW)).intValue() & 07777) == 0700);
    }

    public static void privateFile(Path path, long expectedUid) throws IOException {
        require(Files.isRegularFile(path, NOFOLLOW) && !Files.isSymbolicLink(path));
        require(((Number) Files.getAttribute(path, "unix:uid", NOFOLLOW)).longValue() == expectedUid
            && (((Number) Files.getAttribute(path, "unix:mode", NOFOLLOW)).intValue() & 07777) == 0600);
    }

    public static Record readPrivate(Path path, long expectedUid) throws IOException {
        privateDirectory(path.getParent(), expectedUid); privateFile(path, expectedUid);
        BasicFileAttributes before = Files.readAttributes(path, BasicFileAttributes.class, NOFOLLOW);
        require(before.size() > 0 && before.size() <= MAX_BYTES);
        ByteBuffer buffer = ByteBuffer.allocate(MAX_BYTES + 1);
        try (SeekableByteChannel channel = Files.newByteChannel(path, Set.of(StandardOpenOption.READ, NOFOLLOW))) {
            while (buffer.hasRemaining() && channel.read(buffer) >= 0) { /* bounded by MAX_BYTES + 1 */ }
        }
        BasicFileAttributes after = Files.readAttributes(path, BasicFileAttributes.class, NOFOLLOW);
        require(before.fileKey() != null && before.fileKey().equals(after.fileKey()) && before.size() == after.size()
            && before.lastModifiedTime().equals(after.lastModifiedTime()) && buffer.position() == before.size());
        privateFile(path, expectedUid);
        byte[] raw = new byte[buffer.position()]; buffer.flip(); buffer.get(raw); return parse(raw);
    }

    public static void main(String[] args) {
        boolean valid = false;
        try {
            require(args.length == 0);
            String source = System.getenv("SOURCE_COMMIT"), pod = System.getenv("LAB_RUNTIME_POD_UID");
            valid = ready(readPrivate(FILE, WORKER_UID), linuxIdentity(1), pod, source, linuxUptimeNanos());
        } catch (Exception failure) { /* No private paths, contents or exceptions reach kubelet output. */ }
        System.exit(valid ? 0 : 1);
    }

    private static boolean validSource(String value) { return value != null && value.matches("[a-f0-9]{40}"); }
    private static boolean validUuid(String value) { return value != null && value.matches("[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}"); }
    private static long number(String value) { require(value.matches("[0-9]{1,19}")); return Long.parseLong(value); }
    private static void require(boolean value) { if (!value) { throw new IllegalArgumentException("Invalid process-local progress record"); } }
}
