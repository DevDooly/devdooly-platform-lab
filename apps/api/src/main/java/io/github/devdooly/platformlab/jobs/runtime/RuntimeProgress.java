package io.github.devdooly.platformlab.jobs.runtime;

/** Optional process-local progress. No network, database ownership, or background heartbeat. */
public interface RuntimeProgress extends AutoCloseable {
    RuntimeProgress NONE = new RuntimeProgress() {};
    default void starting() {}
    /** Called only after the owning thread's stage/journal commit has completed. */
    default void committed(String stage) {}
    /** Must not throw from a shutdown hook; terminal state is latched for this instance. */
    default void notReady() {}
    @Override default void close() { notReady(); }

    final class ProgressUnavailableException extends IllegalStateException {
        public ProgressUnavailableException() { super("Process-local runtime progress is unavailable"); }
    }
}
