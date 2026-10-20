package io.github.devdooly.platformlab.jobs.runtime;

import java.util.List;
import java.util.Objects;
import java.util.concurrent.atomic.AtomicBoolean;

/** Closes every supplied resource, in supplied order, even if an earlier close failed. */
public final class RuntimeResources implements AutoCloseable {
    private final List<AutoCloseable> resources;
    private final AtomicBoolean closed = new AtomicBoolean();
    public RuntimeResources(AutoCloseable... resources) { this.resources = List.of(resources); this.resources.forEach(Objects::requireNonNull); }
    @Override public void close() throws Exception {
        if (!closed.compareAndSet(false, true)) { return; }
        boolean failed = false;
        Error firstError = null;
        for (AutoCloseable resource : resources) {
            try { resource.close(); }
            catch (Exception failure) { failed = true; }
            catch (Error failure) { if (firstError == null) { firstError = failure; } }
        }
        // Preserve the first Error itself, without attaching later private failures as suppressed data.
        if (firstError != null) { throw firstError; }
        if (failed) { throw new IllegalStateException("One or more runtime resources failed to close"); }
    }
}
