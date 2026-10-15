package io.github.devdooly.platformlab.jobs.runtime;

/** A process owner check, not a fencing token for Kafka or object-store writes. */
public interface RuntimeLease extends AutoCloseable {
    void verifyHeld();
    @Override void close();

    final class LeaseUnavailableException extends IllegalStateException {
        public LeaseUnavailableException() { super("A runtime owner already exists or the database lock is unavailable"); }
    }
    final class LeaseLostException extends IllegalStateException {
        public LeaseLostException() { super("Runtime database ownership could not be verified"); }
    }
}
