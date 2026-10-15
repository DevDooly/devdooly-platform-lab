package io.github.devdooly.platformlab.jobs;

import java.sql.SQLException;
import org.springframework.jdbc.core.ConnectionCallback;
import org.springframework.jdbc.core.JdbcTemplate;

/** Explicit clock-state reset for owned disposable test databases only; never production code. */
public final class AdmissionTestFixtures {
    private AdmissionTestFixtures() {}
    public static void makeEligible(JdbcTemplate jdbc) {
        jdbc.execute((ConnectionCallback<Void>) connection -> {
            String url = connection.getMetaData().getURL();
            if (!url.startsWith("jdbc:h2:mem:") && !url.matches(
                "jdbc:mariadb://127\\.0\\.0\\.1:[0-9]{1,5}/platform_lab_(?:foundation(?:_fresh)?|s3_it(?:_fresh)?|runtime_it|admission_it)(?:\\?.*)?")
                && !url.matches("jdbc:mariadb://127\\.0\\.0\\.1:[0-9]{1,5}/platform_lab_export_it")) {
                throw new SQLException("Admission test fixture requires an owned disposable database");
            }
            return null;
        });
        if (jdbc.queryForObject("SELECT occupied_run_id FROM lab_job_slot WHERE id=1", String.class) != null) {
            throw new IllegalStateException("Test fixture must not reset an occupied admission slot");
        }
        if (jdbc.update("UPDATE lab_admission_policy SET last_admitted_at=NULL, next_admission_at=NULL WHERE id=1 AND cooldown_seconds=30") != 1) {
            throw new IllegalStateException("Expected the unchanged default 30-second test policy");
        }
    }
}
