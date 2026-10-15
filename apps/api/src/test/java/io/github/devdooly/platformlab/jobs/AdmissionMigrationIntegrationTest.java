package io.github.devdooly.platformlab.jobs;

import io.github.devdooly.platformlab.jobs.runtime.RuntimeStateStore;
import java.time.Clock;
import java.util.ArrayList;
import java.util.List;
import java.util.UUID;
import org.flywaydb.core.Flyway;
import org.junit.jupiter.api.Test;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.SingleConnectionDataSource;
import static org.assertj.core.api.Assertions.*;

class AdmissionMigrationIntegrationTest {
    private final List<SingleConnectionDataSource> databases = new ArrayList<>();
    @org.junit.jupiter.api.AfterEach void closeOwnedConnections() { databases.forEach(SingleConnectionDataSource::destroy); }
    @Test void v3UpgradePreservesEveryOldTableRowAndDoesNotRetroactivelyChargeExistingJobs() {
        var source = database(); var sql = new JdbcTemplate(source);
        Flyway.configure().dataSource(source).target("3").load().migrate();
        byte[] raw = CanonicalSource.fixtureBytes(); String hash = CanonicalSource.validate(raw).sha256();
        sql.update("INSERT INTO demo_run (id,name,scenario,seed,input_count,success_count,failure_count,duplicate_count,pending_count,started_at,completed_at) VALUES ('admission-upgrade-existing','existing','sensor-validation-v1',42,1,1,0,0,0,CURRENT_TIMESTAMP(6),CURRENT_TIMESTAMP(6))");
        sql.update("INSERT INTO demo_outcome (run_id,input_sequence,event_id,sensor_id,event_time,sensor_value,status,reason) VALUES ('admission-upgrade-existing',1,'evt-001','sensor-a','2026-01-01T00:00:00Z',21.5,'SUCCESS','ACCEPTED')");
        sql.update("INSERT INTO lab_job (run_id,scenario_version,source_sha256,source_bytes,source_size,status,export_status,created_at) VALUES ('admission-upgrade-existing','sensor-validation-v1',?,?,?,'STAGING','NOT_REQUESTED',CURRENT_TIMESTAMP(6))", hash, raw, raw.length);
        sql.update("UPDATE lab_job_slot SET occupied_run_id='admission-upgrade-existing' WHERE id=1");
        var journal = new RuntimeStateStore(sql, Clock.systemUTC()); journal.requireSchemaV3();
        assertThatThrownBy(journal::requireSchemaV4).isInstanceOf(IllegalStateException.class).hasMessageContaining("V4");
        var tables = List.of("demo_run", "demo_outcome", "lab_job", "lab_outbox", "lab_job_slot", "lab_runtime");
        var before = snapshot(sql, tables); var history = sql.queryForList("SELECT * FROM flyway_schema_history ORDER BY installed_rank");
        var migrated = Flyway.configure().dataSource(source).load().migrate();
        assertThat(migrated.migrationsExecuted).isEqualTo(1); journal.requireSchemaV4();
        assertThat(snapshot(sql, tables)).isEqualTo(before);
        assertThat(sql.queryForList("SELECT * FROM flyway_schema_history WHERE installed_rank<=3 ORDER BY installed_rank")).isEqualTo(history);
        assertThat(sql.queryForObject("SELECT last_admitted_at FROM lab_admission_policy WHERE id=1", java.sql.Timestamp.class)).isNull();
        assertThat(sql.queryForObject("SELECT source_bytes FROM lab_job WHERE run_id='admission-upgrade-existing'", byte[].class)).isEqualTo(raw);
        assertThat(Flyway.configure().dataSource(source).load().migrate().migrationsExecuted).isZero();
        assertThat(snapshot(sql, tables)).isEqualTo(before);
    }

    @Test void emptyDatabaseAndRepeatedStartupKeepExactlyOneDefaultPolicy() {
        var source = database(); var sql = new JdbcTemplate(source); var flyway = Flyway.configure().dataSource(source).load();
        assertThat(flyway.migrate().migrationsExecuted).isEqualTo(4);
        var before = sql.queryForList("SELECT * FROM lab_admission_policy");
        assertThat(before).hasSize(1); assertThat(before.getFirst()).containsEntry("cooldown_seconds", 30).containsEntry("next_admission_at", null);
        assertThat(flyway.migrate().migrationsExecuted).isZero();
        assertThat(sql.queryForList("SELECT * FROM lab_admission_policy")).isEqualTo(before);
        new RuntimeStateStore(sql, Clock.systemUTC()).requireSchemaV4();
    }

    private SingleConnectionDataSource database() {
        // Keep the migration session alive: H2 2.4 constant-set CHECK expressions retain it.
        var source = new SingleConnectionDataSource("jdbc:h2:mem:admission_migration_" + UUID.randomUUID().toString().replace("-", "")
            + ";MODE=MariaDB;DATABASE_TO_LOWER=TRUE;DB_CLOSE_DELAY=-1", "sa", "", true);
        databases.add(source); return source;
    }
    private static List<?> snapshot(JdbcTemplate sql, List<String> tables) {
        var result = new ArrayList<>();
        for (String table : tables) {
            var rows = sql.queryForList("SELECT * FROM " + table);
            for (var row : rows) { row.replaceAll((key, value) -> value instanceof byte[] raw ? java.util.HexFormat.of().formatHex(raw) : value); }
            result.add(rows);
        }
        return result;
    }
}
