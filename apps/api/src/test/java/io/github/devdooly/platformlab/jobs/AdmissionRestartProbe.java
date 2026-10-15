package io.github.devdooly.platformlab.jobs;

import io.github.devdooly.platformlab.demo.DemoService;
import io.github.devdooly.platformlab.demo.SyntheticScenario;
import java.time.Clock;
import java.util.concurrent.atomic.AtomicInteger;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.DataSourceTransactionManager;
import org.springframework.jdbc.datasource.DriverManagerDataSource;

/** Fresh JVM with no Spring bootstrap, Flyway, Kafka, HTTP or external storage calls. */
public final class AdmissionRestartProbe {
    private AdmissionRestartProbe() {}
    static String guardedUrl() {
        String value = required("DB_TEST_URL");
        if (!value.matches("jdbc:mariadb://127\\.0\\.0\\.1:[0-9]{1,5}/platform_lab_admission_it")) {
            throw new IllegalArgumentException("Only the dedicated disposable numeric-loopback admission schema is allowed");
        }
        return value;
    }
    static String required(String name) {
        String value = System.getenv(name);
        if (value == null || value.isBlank()) { throw new IllegalArgumentException("Missing guarded admission test setting"); }
        return value;
    }
    public static void main(String[] args) {
        int exit = 1;
        try {
            if (args.length != 1 || !args[0].matches("admission-contract-[a-z0-9-]{1,55}")) { throw new IllegalArgumentException("Owned run is required"); }
            var source = new DriverManagerDataSource(guardedUrl(), required("DB_TEST_USERNAME"), required("DB_TEST_PASSWORD"));
            try (var connection = source.getConnection()) {
                if (!connection.getMetaData().getDatabaseProductName().equals("MariaDB") || !connection.getCatalog().equals("platform_lab_admission_it")) {
                    throw new IllegalStateException("Wrong disposable database");
                }
            }
            var jdbc = new JdbcTemplate(source);
            var jobs = new LabJobService(jdbc, new DataSourceTransactionManager(source), new DemoService(null, null, Clock.systemUTC()), Clock.systemUTC());
            var calls = new AtomicInteger();
            try {
                new SourceStagingService(jobs, (job, raw) -> calls.incrementAndGet()).stage(args[0], SyntheticScenario.NAME, CanonicalSource.fixtureBytes());
                System.out.println("UNEXPECTED_ADMISSION");
            } catch (LabJobService.AdmissionCooldownException expected) {
                if (calls.get() != 0) { throw new IllegalStateException("Rejected attempt touched storage"); }
                System.out.println("ADMISSION_COOLDOWN NO_STORAGE_CALLS"); exit = 0;
            }
        } catch (Exception failure) { System.out.println("ADMISSION_PROBE_FAILED"); }
        System.exit(exit);
    }
}
