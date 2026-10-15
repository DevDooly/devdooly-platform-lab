package io.github.devdooly.platformlab.jobs.runtime;

import io.github.devdooly.platformlab.jobs.runtime.health.RuntimeReadyProbe;
import io.github.devdooly.platformlab.jobs.runtime.health.RuntimeReadyProbe.Health;
import io.github.devdooly.platformlab.jobs.runtime.health.RuntimeReadyProbe.Identity;
import io.github.devdooly.platformlab.jobs.runtime.health.RuntimeReadyProbe.Record;
import java.io.IOException;
import java.nio.ByteBuffer;
import java.nio.channels.FileChannel;
import java.nio.file.Files;
import java.nio.file.LinkOption;
import java.nio.file.Path;
import java.nio.file.StandardCopyOption;
import java.nio.file.StandardOpenOption;
import java.nio.file.attribute.BasicFileAttributes;
import java.nio.file.attribute.PosixFilePermissions;
import java.util.Set;
import java.util.UUID;
import java.util.function.LongSupplier;

/** Explicit Linux worker opt-in. Records only real owning-thread stage progress. */
public final class LocalRuntimeProgress implements RuntimeProgress {
    private final Path path;
    private final Identity identity;
    private final String source;
    private final String podUid;
    private final long uid;
    private final LongSupplier bootClock;
    private final UUID instance = UUID.randomUUID();
    private boolean terminal;
    private boolean failed;

    public static RuntimeProgress fromEnvironment(String source) {
        String setting = System.getenv("LAB_RUNTIME_PROGRESS_FILE");
        if (setting == null) { return RuntimeProgress.NONE; }
        if (!setting.equals(RuntimeReadyProbe.FILE.toString()) || !System.getProperty("os.name").equals("Linux")) {
            throw new IllegalArgumentException("Only the fixed Linux worker progress file is allowed");
        }
        try {
            long pid = ProcessHandle.current().pid();
            if (pid != 1) { throw new IllegalArgumentException("Progress requires the container's PID 1 worker"); }
            return new LocalRuntimeProgress(RuntimeReadyProbe.FILE, RuntimeReadyProbe.linuxIdentity(pid),
                source, System.getenv("LAB_RUNTIME_POD_UID"), RuntimeReadyProbe.WORKER_UID, () -> {
                    try { return RuntimeReadyProbe.linuxUptimeNanos(); }
                    catch (IOException failure) { throw new RuntimeProgress.ProgressUnavailableException(); }
                });
        } catch (IOException failure) { throw new RuntimeProgress.ProgressUnavailableException(); }
    }

    LocalRuntimeProgress(Path path, Identity identity, String source, String podUid, long uid, LongSupplier bootClock) throws IOException {
        this.path = path; this.identity = identity; this.source = source; this.podUid = podUid; this.uid = uid; this.bootClock = bootClock;
        // Validate all bounded fields before touching the owned ephemeral directory.
        record(Health.STARTING, "STARTING");
        if (!Files.exists(path.getParent(), LinkOption.NOFOLLOW_LINKS)) {
            Files.createDirectory(path.getParent(), PosixFilePermissions.asFileAttribute(PosixFilePermissions.fromString("rwx------")));
            clearNewDirectoryInheritedSetgid(path.getParent(), uid);
        }
        RuntimeReadyProbe.privateDirectory(path.getParent(), uid);
        if (Files.exists(path, LinkOption.NOFOLLOW_LINKS)) { RuntimeReadyProbe.privateFile(path, uid); }
    }

    private static void clearNewDirectoryInheritedSetgid(Path directory, long expectedUid) throws IOException {
        var before = Files.readAttributes(directory, BasicFileAttributes.class, LinkOption.NOFOLLOW_LINKS);
        long owner = ((Number) Files.getAttribute(directory, "unix:uid", LinkOption.NOFOLLOW_LINKS)).longValue();
        int mode = ((Number) Files.getAttribute(directory, "unix:mode", LinkOption.NOFOLLOW_LINKS)).intValue() & 07777;
        if (!before.isDirectory() || before.fileKey() == null || owner != expectedUid || (mode != 0700 && mode != 02700)) {
            throw new IOException("New progress directory must be private and owned");
        }
        // A Kubernetes fsGroup emptyDir can inherit SGID despite mkdir's 0700 request.
        // Normalize only this newly created inode; existing directories stay fail-closed.
        if (mode == 02700) { Files.setAttribute(directory, "unix:mode", 0700, LinkOption.NOFOLLOW_LINKS); }
        var after = Files.readAttributes(directory, BasicFileAttributes.class, LinkOption.NOFOLLOW_LINKS);
        if (!before.fileKey().equals(after.fileKey()) || !after.isDirectory()) {
            throw new IOException("New progress directory identity changed");
        }
    }

    @Override public synchronized void starting() { if (!terminal) { publish(Health.STARTING, "STARTING"); } }
    @Override public synchronized void committed(String stage) {
        if (failed) { throw new RuntimeProgress.ProgressUnavailableException(); }
        if (!terminal) { publish(Health.READY, stage); }
    }
    @Override public synchronized void notReady() {
        if (terminal) { return; }
        terminal = true;
        try { publish(Health.NOT_READY, "STOPPED"); }
        catch (RuntimeException failure) {
            failed = true;
            try { RuntimeReadyProbe.privateFile(path, uid); Files.delete(path); }
            catch (IOException | RuntimeException ignored) { /* Expiry remains a bounded fallback if storage cannot be updated. */ }
        }
    }

    private Record record(Health health, String stage) {
        long now = bootClock.getAsLong();
        return new Record(instance, identity, podUid, source, health, stage, now,
            health == Health.READY ? Math.addExact(now, RuntimeReadyProbe.MAX_TTL_NANOS) : now);
    }

    private void publish(Health health, String stage) {
        Path temporary = path.resolveSibling("ready." + instance + ".tmp"); boolean created = false;
        try {
            RuntimeReadyProbe.privateDirectory(path.getParent(), uid);
            if (Files.exists(path, LinkOption.NOFOLLOW_LINKS)) { RuntimeReadyProbe.privateFile(path, uid); }
            byte[] raw = record(health, stage).bytes();
            try (FileChannel channel = FileChannel.open(temporary,
                    Set.of(StandardOpenOption.CREATE_NEW, StandardOpenOption.WRITE, LinkOption.NOFOLLOW_LINKS),
                    PosixFilePermissions.asFileAttribute(PosixFilePermissions.fromString("rw-------")))) {
                created = true; ByteBuffer bytes = ByteBuffer.wrap(raw);
                while (bytes.hasRemaining()) { channel.write(bytes); }
                channel.force(true);
            }
            Files.move(temporary, path, StandardCopyOption.ATOMIC_MOVE, StandardCopyOption.REPLACE_EXISTING);
            RuntimeReadyProbe.privateFile(path, uid);
        } catch (IOException | RuntimeException failure) {
            failed = true; throw new RuntimeProgress.ProgressUnavailableException();
        } finally {
            if (created) { try { Files.deleteIfExists(temporary); } catch (IOException ignored) { /* Own temp only. */ } }
        }
    }
}
