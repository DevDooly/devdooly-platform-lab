package io.github.devdooly.platformlab.demo;

import java.util.ArrayList;
import java.util.List;
import java.util.Locale;
import java.util.Random;

public final class SyntheticScenario {
    public static final long SEED = 42L;
    public static final String RUN_ID = "synthetic-v1-seed-42";
    public static final String NAME = "sensor-validation-v1";
    public static final String DESCRIPTION = "회사 데이터와 무관한 고정 seed 합성 데이터. 중복 ID, 잘못된 시간, 시간 역순, 범위 오류를 검증합니다.";
    public static final String MAXIMUM_NAME = "sensor-validation-v2";
    public static final int MAXIMUM_INPUTS = 1_000;
    public static final long MAXIMUM_SEED = 42L;
    public record Counts(int input, int success, int failure, int duplicate, int pending) {}
    private static final List<SensorEvent> MAXIMUM_EVENTS = maximumEvents();
    private SyntheticScenario() {}
    public static boolean supports(String scenario) { return NAME.equals(scenario) || MAXIMUM_NAME.equals(scenario); }
    public static long seed(String scenario) {
        if (NAME.equals(scenario)) { return SEED; }
        if (MAXIMUM_NAME.equals(scenario)) { return MAXIMUM_SEED; }
        throw new IllegalArgumentException("Unsupported synthetic scenario version");
    }
    public static Counts expectedCounts(String scenario) {
        if (NAME.equals(scenario)) { return new Counts(12, 7, 3, 2, 0); }
        if (MAXIMUM_NAME.equals(scenario)) { return new Counts(1_000, 500, 300, 200, 0); }
        throw new IllegalArgumentException("Unsupported synthetic scenario version");
    }
    public static List<SensorEvent> events(String scenario) {
        if (NAME.equals(scenario)) { return events(); }
        if (MAXIMUM_NAME.equals(scenario)) { return MAXIMUM_EVENTS; }
        throw new IllegalArgumentException("Unsupported synthetic scenario version");
    }
    /** 100 independent sensors, each with five successes, three failures and two duplicate IDs. */
    private static List<SensorEvent> maximumEvents() {
        var events = new ArrayList<SensorEvent>(MAXIMUM_INPUTS);
        for (int group = 0; group < 100; group++) {
            String prefix = String.format(Locale.ROOT, "max-%03d-", group);
            String sensor = String.format(Locale.ROOT, "max-sensor-%03d", group);
            events.add(event(prefix + "a", sensor, "2026-02-01T00:00:00Z", 25.0));
            events.add(event(prefix + "b", sensor, "2026-02-01T00:00:02Z", 26.0));
            events.add(event(prefix + "a", sensor, "2026-02-01T00:00:00Z", 25.0));
            events.add(event(prefix + "c", sensor, "not-a-timestamp", 30.0));
            events.add(event(prefix + "d", sensor, "2026-02-01T00:00:01Z", 30.0));
            events.add(event(prefix + "e", sensor, "2026-02-01T00:00:03Z", 120.0));
            events.add(event(prefix + "f", sensor, "2026-02-01T00:00:03Z", 27.0));
            events.add(event(prefix + "g", sensor, "2026-02-01T00:00:04Z", 28.0));
            events.add(event(prefix + "b", sensor, "2026-02-01T00:00:02Z", 26.0));
            events.add(event(prefix + "h", sensor, "2026-02-01T00:00:05Z", 29.0));
        }
        return List.copyOf(events);
    }
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
