package io.github.devdooly.platformlab.jobs;

import java.sql.Connection;
import java.sql.DatabaseMetaData;
import java.sql.SQLException;
import org.junit.jupiter.api.Test;
import org.springframework.jdbc.core.ConnectionCallback;
import org.springframework.jdbc.core.JdbcTemplate;
import static org.assertj.core.api.Assertions.*;
import static org.mockito.ArgumentMatchers.*;
import static org.mockito.Mockito.*;

class AdmissionTestFixturesTest {
    private static final String SLOT = "SELECT occupied_run_id FROM lab_job_slot WHERE id=1";
    private static final String RESET = "UPDATE lab_admission_policy SET last_admitted_at=NULL, next_admission_at=NULL WHERE id=1 AND cooldown_seconds=30";

    private JdbcTemplate jdbcAt(String url) throws SQLException {
        var metadata = mock(DatabaseMetaData.class);
        when(metadata.getURL()).thenReturn(url);
        var connection = mock(Connection.class);
        when(connection.getMetaData()).thenReturn(metadata);
        var jdbc = mock(JdbcTemplate.class);
        when(jdbc.execute(org.mockito.ArgumentMatchers.<ConnectionCallback<Void>>any())).thenAnswer(invocation -> {
            ConnectionCallback<Void> callback = invocation.getArgument(0);
            return callback.doInConnection(connection);
        });
        when(jdbc.update(RESET)).thenReturn(1);
        return jdbc;
    }

    @Test void exactOwnedExportDatabaseResetsOnlyTheDefaultAdmissionClock() throws Exception {
        var jdbc = jdbcAt("jdbc:mariadb://127.0.0.1:3306/platform_lab_export_it");
        AdmissionTestFixtures.makeEligible(jdbc);
        verify(jdbc).queryForObject(SLOT, String.class);
        verify(jdbc).update(RESET);
        verifyNoMoreInteractions(ignoreStubs(jdbc));
    }

    @Test void productionRemoteAndLookalikeDatabasesAreRejectedBeforeSql() throws Exception {
        for (String url : new String[]{
            "jdbc:mariadb://127.0.0.1:3306/platform_lab",
            "jdbc:mariadb://10.0.0.5:3306/platform_lab_export_it",
            "jdbc:mariadb://localhost:3306/platform_lab_export_it",
            "jdbc:mariadb://127.0.0.1:3306/platform_lab_export_it_fresh",
            "jdbc:mariadb://127.0.0.1:3306/platform_lab_export_it?databaseTerm=SCHEMA"
        }) {
            var jdbc = jdbcAt(url);
            assertThatThrownBy(() -> AdmissionTestFixtures.makeEligible(jdbc)).isInstanceOf(SQLException.class);
            verify(jdbc, never()).queryForObject(anyString(), eq(String.class));
            verify(jdbc, never()).update(anyString());
        }
    }

    @Test void occupiedExportSlotIsNeverReset() throws Exception {
        var jdbc = jdbcAt("jdbc:mariadb://127.0.0.1:3310/platform_lab_export_it");
        when(jdbc.queryForObject(SLOT, String.class)).thenReturn("still-running");
        assertThatThrownBy(() -> AdmissionTestFixtures.makeEligible(jdbc))
            .isInstanceOf(IllegalStateException.class).hasMessageContaining("occupied");
        verify(jdbc, never()).update(anyString());
    }

    @Test void missingOrChangedDefaultPolicyDoesNotBecomeAnEligibleFixture() throws Exception {
        var jdbc = jdbcAt("jdbc:mariadb://127.0.0.1:3310/platform_lab_export_it");
        when(jdbc.update(RESET)).thenReturn(0);
        assertThatThrownBy(() -> AdmissionTestFixtures.makeEligible(jdbc))
            .isInstanceOf(IllegalStateException.class).hasMessageContaining("30-second");
        verify(jdbc).update(RESET);
    }

    @Test void existingOwnedFixtureProfilesStillWork() throws Exception {
        for (String url : new String[]{"jdbc:h2:mem:fixture-guard", "jdbc:mariadb://127.0.0.1:3310/platform_lab_foundation",
            "jdbc:mariadb://127.0.0.1:3310/platform_lab_s3_it_fresh", "jdbc:mariadb://127.0.0.1:3310/platform_lab_runtime_it"}) {
            var jdbc = jdbcAt(url);
            AdmissionTestFixtures.makeEligible(jdbc);
            verify(jdbc).update(RESET);
        }
    }
}
