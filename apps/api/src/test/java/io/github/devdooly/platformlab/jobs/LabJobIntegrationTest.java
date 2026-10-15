package io.github.devdooly.platformlab.jobs;

import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.ActiveProfiles;

@SpringBootTest(properties = "spring.datasource.url=jdbc:h2:mem:job_foundation_tests;MODE=MariaDB;DATABASE_TO_LOWER=TRUE;DB_CLOSE_DELAY=-1")
@ActiveProfiles("test")
class LabJobIntegrationTest extends LabJobContractTests {}
