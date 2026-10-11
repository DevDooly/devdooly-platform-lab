package io.github.devdooly.platformlab.demo;

import java.util.*;
import org.junit.jupiter.api.Test;
import static org.assertj.core.api.Assertions.*;

class SensorProcessorTest {
    private final SensorProcessor processor = new SensorProcessor();
    @Test void fixedScenarioHasIndependentExpectedOutcomes() {
        var result = processor.process(SyntheticScenario.events());
        assertThat(result.inputCount()).isEqualTo(12);
        assertThat(result.successCount()).isEqualTo(8);
        assertThat(result.failureCount()).isEqualTo(3);
        assertThat(result.duplicateCount()).isEqualTo(2);
        assertThat(result.pendingCount()).isZero();
        assertThat(result.outcomes()).extracting(outcome -> outcome.status().name()).containsExactly(
            "SUCCESS", "SUCCESS", "SUCCESS", "DUPLICATE", "FAILED", "FAILED", "FAILED", "SUCCESS", "SUCCESS", "SUCCESS", "DUPLICATE", "SUCCESS");
        assertThat(result.outcomes().get(4).reason()).isEqualTo(SensorProcessor.Reason.INVALID_TIMESTAMP);
        assertThat(result.outcomes().get(5).reason()).isEqualTo(SensorProcessor.Reason.OUT_OF_ORDER);
        assertThat(result.outcomes().get(6).reason()).isEqualTo(SensorProcessor.Reason.OUT_OF_RANGE);
    }
    @Test void invalidStructureDoesNotConsumeEventId() {
        var result = processor.process(Arrays.asList(null, event("a", "", "2026-01-01T00:00:00Z", 10.0), event("a", "s", "2026-01-01T00:00:00Z", 10.0)));
        assertThat(result.successCount()).isEqualTo(1); assertThat(result.failureCount()).isEqualTo(2); assertThat(result.duplicateCount()).isZero();
    }
    @Test void invalidTimeDoesConsumeEventIdAndDoesNotAdvanceWatermark() {
        var result = processor.process(List.of(event("a", "s", "bad", 10.0), event("a", "s", "2026-01-01T00:00:00Z", 10.0), event("b", "s", "2026-01-01T00:00:00Z", 10.0)));
        assertThat(result.outcomes()).extracting(SensorProcessor.Outcome::reason).containsExactly(SensorProcessor.Reason.INVALID_TIMESTAMP, SensorProcessor.Reason.DUPLICATE_EVENT_ID, SensorProcessor.Reason.ACCEPTED);
    }
    @Test void timestampsUseInstantRatherThanLocalTimeAndEqualInstantsAreAllowed() {
        var result = processor.process(List.of(event("a", "s", "2026-01-01T09:00:00+09:00", 0.0), event("b", "s", "2026-01-01T00:00:00Z", 100.0)));
        assertThat(result.successCount()).isEqualTo(2);
    }
    @Test void rangeFailureCannotAdvanceSensorTime() {
        var result = processor.process(List.of(event("a", "s", "2026-01-01T02:00:00Z", 101.0), event("b", "s", "2026-01-01T01:00:00Z", 20.0)));
        assertThat(result.outcomes().get(1).status()).isEqualTo(SensorProcessor.Status.SUCCESS);
    }
    @Test void sensorsKeepIndependentWatermarks() {
        var result = processor.process(List.of(event("a", "s1", "2026-01-01T02:00:00Z", 20.0), event("b", "s2", "2026-01-01T01:00:00Z", 20.0)));
        assertThat(result.successCount()).isEqualTo(2);
    }
    @Test void rejectsMissingNonFiniteAndNegativeValues() {
        var result = processor.process(List.of(event("a", "s", "2026-01-01T00:00:00Z", null), event("b", "s", "2026-01-01T00:00:00Z", Double.NaN), event("c", "s", "2026-01-01T00:00:00Z", Double.POSITIVE_INFINITY), event("d", "s", "2026-01-01T00:00:00Z", -1.0)));
        assertThat(result.failureCount()).isEqualTo(4); assertThat(result.successCount()).isZero();
    }
    @Test void emptyBatchIsValidAndAccountedFor() {
        var result = processor.process(List.of()); assertThat(result.inputCount()).isZero(); assertThat(result.outcomes()).isEmpty();
    }
    @Test void seedProducesIdenticalEventsOnEveryInvocation() { assertThat(SyntheticScenario.events()).isEqualTo(SyntheticScenario.events()); }
    private SensorEvent event(String id, String sensor, String time, Double value) { return new SensorEvent(id, sensor, time, value); }
}
