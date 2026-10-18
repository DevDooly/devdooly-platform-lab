package io.github.devdooly.platformlab.jobs.observation;

import jakarta.annotation.PreDestroy;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.util.HexFormat;
import java.util.Set;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.Semaphore;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.function.LongSupplier;
import org.apache.kafka.common.GroupState;
import org.apache.kafka.common.GroupType;
import org.apache.kafka.common.TopicPartition;
import org.apache.kafka.common.Uuid;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.stereotype.Service;

/** Separate broker observation. No DB access, worker startup, readiness dependency or public execution. */
@Service
public final class KafkaObservationService {
    static final long MAX_OFFSET = 9_007_199_254_740_991L;
    static final Duration READ_BUDGET = Duration.ofSeconds(3), CLOSE_BUDGET = Duration.ofSeconds(1);
    public enum Code {
        NOT_CONFIGURED, INVALID_CONFIGURATION, CAPTURE_BUSY, OBSERVER_POISONED, CAPTURE_TIMEOUT,
        KAFKA_UNAVAILABLE, TARGET_UNVERIFIED, GROUP_UNAVAILABLE, GROUP_UNSTABLE,
        OFFSETS_UNVERIFIED, CLOCK_UNVERIFIED, CLOSE_UNVERIFIED
    }
    public static final class ObservationFailure extends RuntimeException {
        private final Code code;
        private ObservationFailure(Code code) { super(code.name(), null, false, false); this.code = code; }
        public Code code() { return code; }
    }
    static ObservationFailure failure(Code code) { return new ObservationFailure(code); }

    public record Observation(int schemaVersion, String kind, boolean synthetic, String environment, String scope,
            boolean publicExecutionEnabled, String sourceCommit, Instant captureStartedAt, Instant capturedAt,
            String consistency, String targetFingerprint, String groupState, int partition, String commitState,
            long logStartOffset, long readCommittedEndOffset, Long committedOffset, Long lag) {}

    private final KafkaObservationSettings settings;
    private final Clock clock;
    private final LongSupplier monotonic;
    private final ReadOnlyKafkaAdmin.Factory factory;
    private final ThreadGroup ownerGroup = new ThreadGroup("platform-lab-kafka-observation-owner");
    private final AtomicInteger ownerThreads = new AtomicInteger();
    private final ExecutorService owner;
    private final Semaphore singleFlight = new Semaphore(1);
    private final AtomicBoolean poisoned = new AtomicBoolean();

    @Autowired public KafkaObservationService(KafkaObservationSettings settings, Clock clock) {
        this(settings, clock, System::nanoTime, ReadOnlyKafkaAdmin.factory());
    }

    KafkaObservationService(KafkaObservationSettings settings, Clock clock, LongSupplier monotonic, ReadOnlyKafkaAdmin.Factory factory) {
        this.settings = settings; this.clock = clock; this.monotonic = monotonic; this.factory = factory;
        // Executor creation starts no thread. Only the first enabled capture may create this one platform owner.
        this.owner = Executors.newSingleThreadExecutor(task -> {
            if (ownerThreads.incrementAndGet() != 1) { poisoned.set(true); throw failure(Code.OBSERVER_POISONED); }
            Thread thread = new Thread(ownerGroup, task, "platform-lab-kafka-observation-owner");
            thread.setDaemon(true); return thread;
        });
    }

    public Observation capture() {
        if (!settings.enabled()) { throw failure(Code.NOT_CONFIGURED); }
        try { settings.validate(); } catch (RuntimeException invalid) { throw failure(Code.INVALID_CONFIGURATION); }
        if (poisoned.get()) { throw failure(Code.OBSERVER_POISONED); }
        if (!singleFlight.tryAcquire()) { throw failure(Code.CAPTURE_BUSY); }
        Future<Observation> task = null;
        try {
            if (poisoned.get()) { throw failure(Code.OBSERVER_POISONED); }
            long start = monotonic.getAsLong();
            var readDeadline = new ReadOnlyKafkaAdmin.Deadline(start + READ_BUDGET.toNanos(), monotonic);
            var callerDeadline = new ReadOnlyKafkaAdmin.Deadline(start + READ_BUDGET.plus(CLOSE_BUDGET).toNanos(), monotonic);
            Instant started = clock.instant();
            task = owner.submit(() -> captureOwned(readDeadline, started));
            Observation observation = task.get(callerDeadline.remainingNanos(), TimeUnit.NANOSECONDS);
            callerDeadline.remainingNanos();
            if (poisoned.get()) { throw failure(Code.OBSERVER_POISONED); }
            return observation;
        } catch (InterruptedException interrupted) {
            quarantine(task); Thread.currentThread().interrupt(); throw failure(Code.CAPTURE_TIMEOUT);
        } catch (TimeoutException timeout) {
            quarantine(task); throw failure(Code.CAPTURE_TIMEOUT);
        } catch (ExecutionException failed) {
            if (failed.getCause() instanceof ObservationFailure fixed) { throw fixed; }
            throw failure(Code.KAFKA_UNAVAILABLE);
        } catch (ObservationFailure fixed) {
            if (fixed.code() == Code.CAPTURE_TIMEOUT) { quarantine(task); }
            throw fixed;
        } catch (RuntimeException failed) {
            quarantine(task); throw failure(Code.OBSERVER_POISONED);
        } finally { singleFlight.release(); }
    }

    private Observation captureOwned(ReadOnlyKafkaAdmin.Deadline deadline, Instant started) {
        ReadOnlyKafkaAdmin admin = null;
        ReadOnlyKafkaAdmin.Target before = null;
        ReadOnlyKafkaAdmin.Offsets offsets = null;
        ObservationFailure problem = null;
        try {
            deadline.remainingNanos();
            admin = factory.open(settings, deadline, ownerGroup);
            if (admin == null) { throw failure(Code.CLOSE_UNVERIFIED); }
            // The constructor may have finished after the caller deadline. Never issue an RPC in that case.
            deadline.remainingNanos();
            before = admin.identity(deadline); validateTarget(before);
            offsets = admin.offsets(deadline); validateOffsets(offsets);
            var after = admin.identity(deadline); validateTarget(after);
            if (!before.equals(after)) { throw failure(Code.TARGET_UNVERIFIED); }
            deadline.remainingNanos();
        } catch (ObservationFailure fixed) { problem = fixed; }
        catch (Throwable unavailable) { problem = failure(Code.KAFKA_UNAVAILABLE); }
        finally {
            if (admin != null) {
                boolean ended = false;
                try { ended = admin.closeAndVerifyIoThread(CLOSE_BUDGET); }
                catch (Throwable unverified) { /* Fixed failure only; retain no provider exception. */ }
                if (!ended) { poisoned.set(true); problem = failure(Code.CLOSE_UNVERIFIED); }
            }
        }
        if (problem != null) {
            if (problem.code() == Code.CLOSE_UNVERIFIED || problem.code() == Code.CAPTURE_TIMEOUT) { poisoned.set(true); }
            throw problem;
        }
        if (poisoned.get()) { throw failure(Code.OBSERVER_POISONED); }
        Instant captured = clock.instant();
        if (captured.isBefore(started) || Duration.between(started, captured).compareTo(READ_BUDGET.plus(CLOSE_BUDGET)) > 0) {
            throw failure(Code.CLOCK_UNVERIFIED);
        }
        String environment = "mini-pc".equals(settings.environment()) ? "MINI_PC" : "ISOLATED_LAB";
        return new Observation(1, "kafka-observation", true, environment,
            environment.equals("MINI_PC") ? "DEPLOYED_KAFKA" : "ISOLATED_KAFKA", false, settings.sourceCommit(), started, captured,
            "BOUNDED_SEQUENTIAL_READ", targetFingerprint(before, settings.group()), before.group().state().name(), 0,
            offsets.committed() == null ? "NO_COMMIT" : "OBSERVED", offsets.start(), offsets.readCommittedEnd(), offsets.committed(),
            offsets.committed() == null ? null : offsets.readCommittedEnd() - offsets.committed());
    }

    private void validateTarget(ReadOnlyKafkaAdmin.Target target) {
        if (target == null || !settings.expectedClusterId().equals(target.clusterId()) || !settings.topic().equals(target.topic())
                || target.topicId() == null || Uuid.ZERO_UUID.equals(target.topicId()) || !target.partitions().equals(Set.of(0))) {
            throw failure(Code.TARGET_UNVERIFIED);
        }
        var group = target.group();
        if (group == null || !settings.group().equals(group.id())) { throw failure(Code.GROUP_UNAVAILABLE); }
        if (group.type() != GroupType.CLASSIC || group.simple() || (group.state() != GroupState.STABLE && group.state() != GroupState.EMPTY)) {
            throw failure(Code.GROUP_UNSTABLE);
        }
        if (group.state() == GroupState.EMPTY) {
            if (!group.members().isEmpty()) { throw failure(Code.GROUP_UNSTABLE); }
        } else if (group.members().size() != 1 || group.members().getFirst().id() == null || group.members().getFirst().id().isEmpty()
                || !group.members().getFirst().assignments().equals(Set.of(new TopicPartition(settings.topic(), 0)))) {
            throw failure(Code.GROUP_UNSTABLE);
        }
    }

    static void validateOffsets(ReadOnlyKafkaAdmin.Offsets offsets) {
        if (offsets == null || offsets.start() < 0 || offsets.readCommittedEnd() < offsets.start() || offsets.readCommittedEnd() > MAX_OFFSET
                || (offsets.committed() != null && (offsets.committed() < offsets.start() || offsets.committed() > offsets.readCommittedEnd()))) {
            throw failure(Code.OFFSETS_UNVERIFIED);
        }
    }

    static String targetFingerprint(ReadOnlyKafkaAdmin.Target target, String group) {
        try {
            String canonical = "{\"clusterId\":\"" + target.clusterId() + "\",\"group\":\"" + group
                + "\",\"partition\":0,\"schemaVersion\":1,\"topicUuid\":\"" + target.topicId() + "\"}";
            return HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(canonical.getBytes(StandardCharsets.UTF_8)));
        } catch (Exception unavailable) { throw failure(Code.TARGET_UNVERIFIED); }
    }

    private void quarantine(Future<?> task) {
        poisoned.set(true);
        if (task != null) { task.cancel(true); }
        owner.shutdownNow();
    }
    int ownerThreadsCreated() { return ownerThreads.get(); }
    boolean poisoned() { return poisoned.get(); }
    @PreDestroy public void close() { poisoned.set(true); owner.shutdownNow(); }
}
