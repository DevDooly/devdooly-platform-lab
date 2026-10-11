package io.github.devdooly.platformlab.demo;

import jakarta.persistence.*;

@Entity @Table(name = "demo_outcome")
public class DemoOutcome {
    @Id @GeneratedValue(strategy = GenerationType.IDENTITY) Long id;
    @Column(nullable = false, length = 80) String runId;
    @Column(name = "input_sequence", nullable = false) int sequence;
    @Column(length = 80) String eventId;
    @Column(length = 80) String sensorId;
    @Column(length = 100) String eventTime;
    @Column(name = "sensor_value") Double value;
    @Enumerated(EnumType.STRING) @Column(nullable = false, length = 20) SensorProcessor.Status status;
    @Enumerated(EnumType.STRING) @Column(nullable = false, length = 40) SensorProcessor.Reason reason;
    protected DemoOutcome() {}
    DemoOutcome(String run, SensorProcessor.Outcome outcome) {
        runId = run; sequence = outcome.sequence(); eventId = outcome.eventId(); sensorId = outcome.sensorId();
        eventTime = outcome.eventTime(); value = outcome.value(); status = outcome.status(); reason = outcome.reason();
    }
    SensorProcessor.Outcome view() { return new SensorProcessor.Outcome(sequence, eventId, sensorId, eventTime, value, status, reason); }
}
