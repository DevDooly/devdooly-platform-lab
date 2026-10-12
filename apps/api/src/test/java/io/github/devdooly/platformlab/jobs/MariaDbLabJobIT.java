package io.github.devdooly.platformlab.jobs;

import javax.sql.DataSource;
import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.TestInstance;
import org.junit.jupiter.api.condition.EnabledIfSystemProperty;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import static org.assertj.core.api.Assertions.assertThat;

/** Explicit opt-in against a disposable MariaDB database; not a production database. */
@SpringBootTest
@ActiveProfiles({"db-test", "worker"})
@EnabledIfSystemProperty(named = "lab.database.tests", matches = "true")
@TestInstance(TestInstance.Lifecycle.PER_CLASS)
class MariaDbLabJobIT extends LabJobContractTests {
    @Autowired DataSource dataSource;
    @DynamicPropertySource static void requireDisposableDatabaseUrlBeforeFlyway(DynamicPropertyRegistry registry) {
        registry.add("spring.datasource.url", () -> {
            String url = System.getenv("DB_TEST_URL");
            if (url == null || !url.matches("jdbc:mariadb://127\\.0\\.0\\.1:[0-9]+/platform_lab_foundation(?:_fresh)?(?:\\?.*)?")) {
                throw new IllegalArgumentException("DB_TEST_URL must target a disposable foundation database on a loopback port");
            }
            return url;
        });
    }
    @BeforeAll void requireRealMariaDb() throws Exception {
        try (var connection = dataSource.getConnection()) {
            assertThat(connection.getMetaData().getDatabaseProductName()).isEqualTo("MariaDB");
            assertThat(connection.getCatalog()).contains("foundation");
        }
    }
}
