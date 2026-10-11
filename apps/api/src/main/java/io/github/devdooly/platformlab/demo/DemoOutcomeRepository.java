package io.github.devdooly.platformlab.demo;

import java.util.List;
import org.springframework.data.jpa.repository.JpaRepository;

public interface DemoOutcomeRepository extends JpaRepository<DemoOutcome, Long> {
    List<DemoOutcome> findByRunIdOrderBySequence(String runId);
}
