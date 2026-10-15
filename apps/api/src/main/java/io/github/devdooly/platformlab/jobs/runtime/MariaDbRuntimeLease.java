package io.github.devdooly.platformlab.jobs.runtime;

import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.sql.Connection;
import java.sql.SQLException;
import java.util.HexFormat;
import java.util.Objects;
import javax.sql.DataSource;
import org.springframework.transaction.IllegalTransactionStateException;
import org.springframework.transaction.support.TransactionSynchronizationManager;

/** A dedicated non-transaction connection owns one MariaDB named lock until close. */
public final class MariaDbRuntimeLease implements RuntimeLease {
    private final Connection connection;
    private final String name;
    private boolean closed;

    private MariaDbRuntimeLease(Connection connection, String name) { this.connection = connection; this.name = name; }

    public static MariaDbRuntimeLease acquire(DataSource dataSource) {
        requireNoTransaction();
        Connection connection = null;
        try {
            connection = Objects.requireNonNull(dataSource).getConnection();
            if (!connection.getMetaData().getDatabaseProductName().equals("MariaDB") || !connection.getAutoCommit()) {
                throw new RuntimeLease.LeaseUnavailableException();
            }
            String catalog = connection.getCatalog();
            if (catalog == null || catalog.isBlank()) { throw new RuntimeLease.LeaseUnavailableException(); }
            String name = lockName(catalog);
            try (var statement = connection.prepareStatement("SELECT GET_LOCK(?, 0)")) {
                statement.setQueryTimeout(3); statement.setString(1, name);
                try (var rows = statement.executeQuery()) {
                    if (!rows.next() || rows.getInt(1) != 1 || rows.wasNull()) {
                        throw new RuntimeLease.LeaseUnavailableException();
                    }
                }
            }
            return new MariaDbRuntimeLease(connection, name);
        } catch (SQLException | RuntimeException failure) {
            if (connection != null) { try { connection.close(); } catch (SQLException ignored) {} }
            // Do not attach JDBC details: connection errors can include private addresses or user names.
            throw new RuntimeLease.LeaseUnavailableException();
        }
    }

    public static String lockName(String catalog) {
        if (catalog == null || catalog.isBlank()) { throw new IllegalArgumentException("An explicit database catalog is required"); }
        try {
            return "platform-lab-runtime:" + HexFormat.of().formatHex(
                MessageDigest.getInstance("SHA-256").digest(catalog.getBytes(StandardCharsets.UTF_8))).substring(0, 24);
        } catch (java.security.NoSuchAlgorithmException impossible) { throw new IllegalStateException(impossible); }
    }

    @Override public void verifyHeld() {
        requireNoTransaction();
        if (closed) { throw new RuntimeLease.LeaseLostException(); }
        try (var statement = connection.prepareStatement("SELECT IS_USED_LOCK(?), CONNECTION_ID()")) {
            statement.setQueryTimeout(3); statement.setString(1, name);
            try (var rows = statement.executeQuery()) {
                if (!rows.next()) { throw new RuntimeLease.LeaseLostException(); }
                long owner = rows.getLong(1); boolean absent = rows.wasNull();
                if (absent || owner != rows.getLong(2)) { throw new RuntimeLease.LeaseLostException(); }
            }
        } catch (SQLException failure) { throw new RuntimeLease.LeaseLostException(); }
    }

    @Override public void close() {
        if (closed) { return; }
        closed = true;
        try (var statement = connection.prepareStatement("SELECT RELEASE_LOCK(?)")) {
            statement.setQueryTimeout(3); statement.setString(1, name); statement.executeQuery().close();
        } catch (SQLException ignored) {
            // Do not return a possibly lock-owning physical connection to a pool after a failed RELEASE.
            try { connection.abort(Runnable::run); } catch (SQLException abortFailure) {}
        } finally { try { connection.close(); } catch (SQLException ignored) {} }
    }

    private static void requireNoTransaction() {
        if (TransactionSynchronizationManager.isActualTransactionActive()) {
            throw new IllegalTransactionStateException("Runtime ownership must not run inside a database transaction");
        }
    }
}
