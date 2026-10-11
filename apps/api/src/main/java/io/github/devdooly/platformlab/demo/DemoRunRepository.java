package io.github.devdooly.platformlab.demo;

import java.util.List;
import org.springframework.data.jpa.repository.JpaRepository;

public interface DemoRunRepository extends JpaRepository<DemoRun, String> {
    List<DemoRun> findTop20ByOrderByStartedAtDesc();
}
