package io.github.devdooly.platformlab.jobs.runtime;

import io.github.devdooly.platformlab.jobs.messaging.DispatchWorker;
import java.time.Duration;
import java.util.Objects;
import java.util.concurrent.atomic.AtomicBoolean;
import org.springframework.transaction.IllegalTransactionStateException;
import org.springframework.transaction.support.TransactionSynchronizationManager;
import static io.github.devdooly.platformlab.jobs.runtime.RuntimeStateStore.*;

/** One owning thread performs bounded I/O; process restart never clears a persisted operator pause. */
public final class ContinuousJobRunner {
    public interface Actions {
        boolean exportOne();
        boolean publishOne() throws Exception;
        boolean receiveOne(Duration pollTimeout);
    }
    private final RuntimeStateStore states;
    private final RuntimeLease lease;
    private final Actions actions;
    private final AutoCloseable resources;
    private final String sourceCommit;
    private final Duration pollTimeout;
    private final Duration idleDelay;
    private final AtomicBoolean stopRequested = new AtomicBoolean();
    private final AtomicBoolean invoked = new AtomicBoolean();

    public ContinuousJobRunner(RuntimeStateStore states, RuntimeLease lease, Actions actions,
                               AutoCloseable resources, String sourceCommit, Duration pollTimeout, Duration idleDelay) {
        this.states = Objects.requireNonNull(states); this.lease = Objects.requireNonNull(lease);
        this.actions = Objects.requireNonNull(actions); this.resources = Objects.requireNonNull(resources);
        RuntimeStateStore.validateCommit(sourceCommit); this.sourceCommit = sourceCommit;
        this.pollTimeout = bounded(pollTimeout); this.idleDelay = bounded(idleDelay);
    }

    /** Safe from a shutdown hook; all client calls, including close, remain on the run thread. */
    public void requestStop() { stopRequested.set(true); }

    public State run() {
        if (!invoked.compareAndSet(false, true)) { throw new IllegalStateException("A runtime object may run only once"); }
        Stage stage = Stage.IDLE;
        boolean started = false;
        boolean paused = false;
        RuntimeException terminal = null;
        State finalState = null;
        try {
            requireNoTransaction();
            states.start(lease, sourceCommit); started = true;
            while (!stopRequested.get()) {
                stage = Stage.EXPORT; states.stage(lease, stage);
                boolean worked = actions.exportOne();
                if (stopRequested.get()) { break; }
                stage = Stage.PUBLISH; states.stage(lease, stage);
                worked |= actions.publishOne();
                if (stopRequested.get()) { break; }
                stage = Stage.CONSUME; states.stage(lease, stage);
                worked |= actions.receiveOne(pollTimeout);
                if (stopRequested.get()) { break; }
                stage = Stage.IDLE; states.stage(lease, stage);
                if (!worked) { Thread.sleep(idleDelay.toMillis()); }
            }
        } catch (Exception failure) {
            if (failure instanceof InterruptedException) { Thread.currentThread().interrupt(); }
            if (started) {
                try { states.pause(lease, stage, failureCode(stage, failure)); paused = true; }
                catch (RuntimeException journalFailure) { terminal = new IllegalStateException("Runtime stopped without a verified journal update"); }
            } else { terminal = safeStartupFailure(failure); }
        } finally {
            try { resources.close(); }
            catch (Exception closeFailure) {
                if (started && !paused) {
                    try { states.pause(lease, Stage.STOPPED, FailureCode.RESOURCE_CLOSE_FAILED); paused = true; }
                    catch (RuntimeException journalFailure) { terminal = new IllegalStateException("Runtime resource close and journal update failed"); }
                } else if (terminal == null && !paused) { terminal = new IllegalStateException("Runtime resources could not be closed"); }
            }
            try { if (started && !paused && terminal == null) { states.stop(lease); } }
            catch (RuntimeException journalFailure) { terminal = new IllegalStateException("Runtime stopped without a verified final journal update"); }
            finally {
                try { if (terminal == null) { finalState = states.read(); } }
                catch (RuntimeException readFailure) { terminal = new IllegalStateException("Runtime final journal could not be read"); }
                finally { lease.close(); }
            }
        }
        if (terminal != null) { throw terminal; }
        return finalState;
    }

    private static RuntimeException safeStartupFailure(Exception failure) {
        if (failure instanceof RuntimeStateStore.OperatorResumeRequiredException paused) { return paused; }
        if (failure instanceof RuntimeLease.LeaseLostException lost) { return lost; }
        return new IllegalStateException("Runtime startup was rejected");
    }
    private static FailureCode failureCode(Stage stage, Exception failure) {
        if (failure instanceof RuntimeLease.LeaseLostException) { return FailureCode.LEASE_LOST; }
        if (failure instanceof InterruptedException || Thread.currentThread().isInterrupted()) { return FailureCode.INTERRUPTED; }
        if (failure instanceof DispatchWorker.DeliveryPausedException delivery) { return FailureCode.valueOf(delivery.code().name()); }
        return switch (stage) {
            case EXPORT -> FailureCode.EXPORT_FAILED;
            case PUBLISH -> FailureCode.PUBLISH_FAILED;
            default -> FailureCode.RUNTIME_FAILED;
        };
    }
    private static Duration bounded(Duration value) {
        if (value == null || value.compareTo(Duration.ofMillis(100)) < 0 || value.compareTo(Duration.ofSeconds(5)) > 0) {
            throw new IllegalArgumentException("Runtime poll and idle durations must be between 100 ms and 5 seconds");
        }
        return value;
    }
    private static void requireNoTransaction() {
        if (TransactionSynchronizationManager.isActualTransactionActive()) {
            throw new IllegalTransactionStateException("Continuous runtime must not join a database transaction");
        }
    }
}
