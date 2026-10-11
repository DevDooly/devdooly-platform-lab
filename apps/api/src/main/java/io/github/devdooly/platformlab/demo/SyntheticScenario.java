package io.github.devdooly.platformlab.demo;

import java.util.List;
import java.util.Random;

public final class SyntheticScenario {
    public static final long SEED = 42L;
    public static final String RUN_ID = "synthetic-v1-seed-42";
    public static final String NAME = "sensor-validation-v1";
    public static final String DESCRIPTION = "회사 데이터와 무관한 고정 seed 합성 데이터. 중복 ID, 잘못된 시간, 시간 역순, 범위 오류를 검증합니다.";
    private SyntheticScenario() {}
    public static List<SensorEvent> events() {
        var random = new Random(SEED);
        return List.of(
            event("evt-001", "sensor-a", "2026-01-01T00:00:00Z", value(random)),
            event("evt-002", "sensor-b", "2026-01-01T00:00:00Z", value(random)),
            event("evt-003", "sensor-a", "2026-01-01T00:01:00Z", value(random)),
            event("evt-003", "sensor-a", "2026-01-01T00:01:00Z", 30.0),
            event("evt-004", "sensor-a", "not-a-timestamp", 30.0),
            event("evt-005", "sensor-a", "2026-01-01T00:00:30Z", 30.0),
            event("evt-006", "sensor-b", "2026-01-01T00:01:00Z", 120.0),
            event("evt-007", "sensor-b", "2026-01-01T00:01:00Z", value(random)),
            event("evt-008", "sensor-a", "2026-01-01T00:02:00Z", value(random)),
            event("evt-009", "sensor-b", "2026-01-01T00:02:00Z", value(random)),
            event("evt-001", "sensor-a", "2026-01-01T00:00:00Z", 30.0),
            event("evt-010", "sensor-a", "2026-01-01T00:03:00Z", value(random))
        );
    }
    private static SensorEvent event(String id, String sensor, String time, double value) { return new SensorEvent(id, sensor, time, value); }
    private static double value(Random random) { return 20.0 + random.nextInt(101) / 10.0; }
}
