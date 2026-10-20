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
    private final RuntimeProgress progress;
    private final AtomicBoolean stopRequested = new AtomicBoolean();
    private final AtomicBoolean invoked = new AtomicBoolean();

    public ContinuousJobRunner(RuntimeStateStore states, RuntimeLease lease, Actions actions,
                               AutoCloseable resources, String sourceCommit, Duration pollTimeout, Duration idleDelay) {
        this(states, lease, actions, resources, sourceCommit, pollTimeout, idleDelay, RuntimeProgress.NONE);
    }

    public ContinuousJobRunner(RuntimeStateStore states, RuntimeLease lease, Actions actions,
                               AutoCloseable resources, String sourceCommit, Duration pollTimeout, Duration idleDelay,
                               RuntimeProgress progress) {
        this.states = Objects.requireNonNull(states); this.lease = Objects.requireNonNull(lease);
        this.actions = Objects.requireNonNull(actions); this.resources = Objects.requireNonNull(resources);
        RuntimeStateStore.validateCommit(sourceCommit); this.sourceCommit = sourceCommit;
        this.pollTimeout = bounded(pollTimeout); this.idleDelay = bounded(idleDelay);
        this.progress = Objects.requireNonNull(progress);
    }

    /** Safe from a shutdown hook; all client calls, including close, remain on the run thread. */
    public void requestStop() { stopRequested.set(true); progress.notReady(); }

    public State run() {
        if (!invoked.compareAndSet(false, true)) { throw new IllegalStateException("A runtime object may run only once"); }
        Stage stage = Stage.IDLE;
        boolean started = false;
        boolean paused = false;
        var failures = new Failures();
        State finalState = null;
        try {
            requireNoTransaction();
            states.start(lease, sourceCommit); started = true; progress.starting();
            while (!stopRequested.get()) {
                stage = Stage.EXPORT; states.stage(lease, stage); progress.committed(stage.name());
                boolean worked = actions.exportOne();
                if (stopRequested.get()) { break; }
                stage = Stage.PUBLISH; states.stage(lease, stage); progress.committed(stage.name());
                worked |= actions.publishOne();
                if (stopRequested.get()) { break; }
                stage = Stage.CONSUME; states.stage(lease, stage); progress.committed(stage.name());
                worked |= actions.receiveOne(pollTimeout);
                if (stopRequested.get()) { break; }
                stage = Stage.IDLE; states.stage(lease, stage); progress.committed(stage.name());
                if (!worked) { Thread.sleep(idleDelay.toMillis()); }
            }
        } catch (Exception failure) {
            if (failure instanceof InterruptedException) { Thread.currentThread().interrupt(); }
            // Invalidate local readiness before a possibly slow journal write, without skipping cleanup if a hook fails.
            try { progress.notReady(); }
            catch (RuntimeException progressFailure) { failures.ordinary("Runtime local progress could not be closed"); }
            catch (Error progressFailure) { failures.error(progressFailure); }
            if (started) {
                try { paused = pause(stage, failures.firstError == null ? failureCode(stage, failure) : FailureCode.RUNTIME_FAILED,
                    failures, "Runtime stopped without a verified journal update"); }
                catch (Error journalFailure) { failures.error(journalFailure); }
            } else { failures.terminal = safeStartupFailure(failure); }
        } catch (Error failure) {
            failures.error(failure);
        } finally {
            boolean progressFailed = false;
            try { progress.notReady(); }
            catch (RuntimeException progressFailure) {
                progressFailed = true; failures.ordinary("Runtime local progress could not be closed");
            } catch (Error progressFailure) { progressFailed = true; failures.error(progressFailure); }
            if (started && !paused && (failures.firstError != null || progressFailed)) {
                paused = pause(stage, FailureCode.RUNTIME_FAILED, failures, "Runtime stopped without a verified journal update");
            }
            try { resources.close(); }
            catch (Exception closeFailure) {
                if (started && !paused) {
                    paused = pause(Stage.STOPPED, FailureCode.RESOURCE_CLOSE_FAILED, failures, "Runtime resource close and journal update failed");
                } else if (!paused) { failures.ordinary("Runtime resources could not be closed"); }
            } catch (Error closeFailure) {
                failures.error(closeFailure);
                if (started && !paused) {
                    paused = pause(Stage.STOPPED, FailureCode.RESOURCE_CLOSE_FAILED, failures, "Runtime resource close and journal update failed");
                }
            }
            try { if (started && !paused && !failures.present()) { states.stop(lease); } }
            catch (RuntimeException journalFailure) { failures.ordinary("Runtime stopped without a verified final journal update"); }
            catch (Error journalFailure) { failures.error(journalFailure); }
            finally {
                try { if (!failures.present()) { finalState = states.read(); } }
                catch (RuntimeException readFailure) { failures.ordinary("Runtime final journal could not be read"); }
                catch (Error readFailure) { failures.error(readFailure); }
                finally {
                    try { lease.close(); }
                    catch (RuntimeException closeFailure) { failures.ordinary("Runtime owner could not be closed"); }
                    catch (Error closeFailure) { failures.error(closeFailure); }
                }
            }
        }
        if (failures.firstError != null) { throw failures.firstError; }
        if (failures.terminal != null) { throw failures.terminal; }
        return finalState;
    }

    private boolean pause(Stage stage, FailureCode code, Failures failures, String message) {
        if (failures.pauseAttempted) { return false; }
        failures.pauseAttempted = true;
        try { states.pause(lease, stage, code); return true; }
        catch (RuntimeException journalFailure) { failures.ordinary(message); }
        catch (Error journalFailure) { failures.error(journalFailure); }
        return false;
    }
    private static final class Failures {
        private Error firstError;
        private RuntimeException terminal;
        private boolean pauseAttempted;
        void error(Error failure) { if (firstError == null) { firstError = failure; } }
        void ordinary(String message) { if (terminal == null) { terminal = new IllegalStateException(message); } }
        boolean present() { return firstError != null || terminal != null; }
    }

    private static RuntimeException safeStartupFailure(Exception failure) {
        if (failure instanceof RuntimeStateStore.OperatorResumeRequiredException paused) { return paused; }
        if (failure instanceof RuntimeLease.LeaseLostException lost) { return lost; }
        return new IllegalStateException("Runtime startup was rejected");
    }
    private static FailureCode failureCode(Stage stage, Exception failure) {
        if (failure instanceof RuntimeLease.LeaseLostException) { return FailureCode.LEASE_LOST; }
        if (failure instanceof RuntimeProgress.ProgressUnavailableException) { return FailureCode.RUNTIME_FAILED; }
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
