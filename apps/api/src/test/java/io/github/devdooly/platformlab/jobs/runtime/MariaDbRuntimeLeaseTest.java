package io.github.devdooly.platformlab.jobs.runtime;

import java.sql.Connection;
import java.sql.DatabaseMetaData;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.util.concurrent.Executor;
import javax.sql.DataSource;
import org.junit.jupiter.api.Test;
import static org.assertj.core.api.Assertions.*;
import static org.mockito.ArgumentMatchers.*;
import static org.mockito.Mockito.*;

class MariaDbRuntimeLeaseTest {
    @Test void heldSessionMustMatchOwnerAndEveryResourceIsClosedOnRelease() throws Exception {
        var fixture = new Fixture(); var lease = MariaDbRuntimeLease.acquire(fixture.dataSource);
        lease.verifyHeld(); lease.close(); lease.close();
        verify(fixture.acquire).setString(1, MariaDbRuntimeLease.lockName("unit_runtime"));
        verify(fixture.check).setQueryTimeout(3); verify(fixture.release).executeQuery(); verify(fixture.connection, times(1)).close();
        assertThatThrownBy(lease::verifyHeld).isInstanceOf(RuntimeLease.LeaseLostException.class);
    }

    @Test void competingOwnerAndH2AreRejectedWithoutReturningAnOwnedRuntime() throws Exception {
        var fixture = new Fixture(); when(fixture.acquireRows.getInt(1)).thenReturn(0);
        assertThatThrownBy(() -> MariaDbRuntimeLease.acquire(fixture.dataSource)).isInstanceOf(RuntimeLease.LeaseUnavailableException.class);
        verify(fixture.connection).close();
        var h2 = new Fixture(); when(h2.metadata.getDatabaseProductName()).thenReturn("H2");
        assertThatThrownBy(() -> MariaDbRuntimeLease.acquire(h2.dataSource)).isInstanceOf(RuntimeLease.LeaseUnavailableException.class);
        verify(h2.acquire, never()).executeQuery(); verify(h2.connection).close();
    }

    @Test void wrongOwnerAndBrokenConnectionFailClosed() throws Exception {
        var fixture = new Fixture(); var lease = MariaDbRuntimeLease.acquire(fixture.dataSource);
        when(fixture.checkRows.getLong(1)).thenReturn(8L);
        assertThatThrownBy(lease::verifyHeld).isInstanceOf(RuntimeLease.LeaseLostException.class);
        when(fixture.check.executeQuery()).thenThrow(new SQLException("private address"));
        assertThatThrownBy(lease::verifyHeld).isInstanceOf(RuntimeLease.LeaseLostException.class).hasMessageNotContaining("private");
        lease.close(); verify(fixture.connection).close();
    }

    @Test void failedReleaseAbortsPhysicalSessionBeforeReturningPooledConnection() throws Exception {
        var fixture = new Fixture(); var lease = MariaDbRuntimeLease.acquire(fixture.dataSource);
        when(fixture.release.executeQuery()).thenThrow(new SQLException("release failed"));
        lease.close(); var order = inOrder(fixture.connection);
        order.verify(fixture.connection).abort(any(Executor.class)); order.verify(fixture.connection).close();
    }

    private static final class Fixture {
        final DataSource dataSource = mock(DataSource.class);
        final Connection connection = mock(Connection.class);
        final DatabaseMetaData metadata = mock(DatabaseMetaData.class);
        final PreparedStatement acquire = mock(PreparedStatement.class), check = mock(PreparedStatement.class), release = mock(PreparedStatement.class);
        final ResultSet acquireRows = mock(ResultSet.class), checkRows = mock(ResultSet.class), releaseRows = mock(ResultSet.class);
        Fixture() throws Exception {
            when(dataSource.getConnection()).thenReturn(connection); when(connection.getMetaData()).thenReturn(metadata);
            when(metadata.getDatabaseProductName()).thenReturn("MariaDB"); when(connection.getAutoCommit()).thenReturn(true);
            when(connection.getCatalog()).thenReturn("unit_runtime");
            when(connection.prepareStatement("SELECT GET_LOCK(?, 0)")).thenReturn(acquire);
            when(connection.prepareStatement("SELECT IS_USED_LOCK(?), CONNECTION_ID()")).thenReturn(check);
            when(connection.prepareStatement("SELECT RELEASE_LOCK(?)")).thenReturn(release);
            when(acquire.executeQuery()).thenReturn(acquireRows); when(acquireRows.next()).thenReturn(true); when(acquireRows.getInt(1)).thenReturn(1);
            when(check.executeQuery()).thenReturn(checkRows); when(checkRows.next()).thenReturn(true);
            when(checkRows.getLong(1)).thenReturn(9L); when(checkRows.getLong(2)).thenReturn(9L);
            when(release.executeQuery()).thenReturn(releaseRows);
        }
    }
}
