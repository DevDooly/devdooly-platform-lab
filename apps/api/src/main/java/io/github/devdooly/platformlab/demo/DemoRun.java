package io.github.devdooly.platformlab.demo;

import jakarta.persistence.*;
import java.time.Instant;

@Entity @Table(name = "demo_run")
public class DemoRun {
    @Id @Column(length = 80) String id;
    @Column(nullable = false, length = 160) String name;
    @Column(nullable = false, length = 80) String scenario;
    @Column(nullable = false) long seed;
    @Column(nullable = false) int inputCount;
    @Column(nullable = false) int successCount;
    @Column(nullable = false) int failureCount;
    @Column(nullable = false) int duplicateCount;
    @Column(nullable = false) int pendingCount;
    @Column(nullable = false) Instant startedAt;
    @Column(nullable = false) Instant completedAt;
    protected DemoRun() {}
    DemoRun(SensorProcessor.Result result, Instant started, Instant completed) {
        id = SyntheticScenario.RUN_ID; name = "합성 센서 품질 검증"; scenario = SyntheticScenario.NAME; seed = SyntheticScenario.SEED;
        inputCount = result.inputCount(); successCount = result.successCount(); failureCount = result.failureCount();
        duplicateCount = result.duplicateCount(); pendingCount = result.pendingCount(); startedAt = started; completedAt = completed;
    }
}
