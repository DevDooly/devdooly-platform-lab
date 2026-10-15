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
        Exception first = null;
        for (AutoCloseable resource : resources) {
            try { resource.close(); }
            catch (Exception failure) { if (first == null) { first = failure; } }
        }
        if (first != null) { throw new IllegalStateException("One or more runtime resources failed to close"); }
    }
}
