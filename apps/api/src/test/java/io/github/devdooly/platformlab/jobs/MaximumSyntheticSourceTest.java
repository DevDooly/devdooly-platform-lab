package io.github.devdooly.platformlab.jobs;

import io.github.devdooly.platformlab.demo.SensorProcessor;
import io.github.devdooly.platformlab.demo.SyntheticScenario;
import java.nio.charset.StandardCharsets;
import java.util.Arrays;
import org.junit.jupiter.api.Test;
import static org.assertj.core.api.Assertions.*;
import static org.mockito.Mockito.*;

class MaximumSyntheticSourceTest {
    @Test void versionOneRawBytesRemainIdenticalToThePreChangeFingerprint() {
        var source = CanonicalSource.validate(CanonicalSource.fixtureBytes());
        assertThat(source.size()).isEqualTo(1100);
        assertThat(source.sha256()).isEqualTo("39ba10d8c47dce790f3ccc9c9134fea593d6de31f1f3a7992ca61d9f554da3b5");
        assertThat(source.scenarioVersion()).isEqualTo("sensor-validation-v1");
        assertThat(source.events()).hasSize(12);
    }

    @Test void thousandEventsHaveIndependentOrderedExpectedOutcomesForEverySensorGroup() {
        var source = CanonicalSource.validate(SyntheticScenario.MAXIMUM_NAME, CanonicalSource.fixtureBytes(SyntheticScenario.MAXIMUM_NAME));
        var result = new SensorProcessor().process(source.events());
        assertThat(result.inputCount()).isEqualTo(1000); assertThat(result.successCount()).isEqualTo(500);
        assertThat(result.failureCount()).isEqualTo(300); assertThat(result.duplicateCount()).isEqualTo(200); assertThat(result.pendingCount()).isZero();
        assertThat(source.events()).isSameAs(source.events());
        assertThat(source.events().stream().map(event -> event.sensorId()).distinct()).hasSize(100);
        for (int group = 0; group < 100; group++) {
            assertThat(result.outcomes().subList(group * 10, group * 10 + 10)).extracting(SensorProcessor.Outcome::reason).containsExactly(
                SensorProcessor.Reason.ACCEPTED, SensorProcessor.Reason.ACCEPTED, SensorProcessor.Reason.DUPLICATE_EVENT_ID,
                SensorProcessor.Reason.INVALID_TIMESTAMP, SensorProcessor.Reason.OUT_OF_ORDER, SensorProcessor.Reason.OUT_OF_RANGE,
                SensorProcessor.Reason.ACCEPTED, SensorProcessor.Reason.ACCEPTED, SensorProcessor.Reason.DUPLICATE_EVENT_ID, SensorProcessor.Reason.ACCEPTED);
        }
        assertThatThrownBy(() -> source.events().clear()).isInstanceOf(UnsupportedOperationException.class);
        assertThat(CanonicalSource.fixtureBytes(SyntheticScenario.MAXIMUM_NAME)).isEqualTo(source.bytes());
    }

    @Test void exactOneMiBOfAllowedJsonWhitespaceIsAcceptedButOneExtraByteIsRejected() {
        byte[] canonical = CanonicalSource.fixtureBytes(SyntheticScenario.MAXIMUM_NAME);
        byte[] padded = new byte[CanonicalSource.MAX_BYTES];
        Arrays.fill(padded, (byte) ' '); System.arraycopy(canonical, 0, padded, padded.length - canonical.length, canonical.length);
        var source = CanonicalSource.validate(SyntheticScenario.MAXIMUM_NAME, padded);
        assertThat(source.size()).isEqualTo(1_048_576); assertThat(source.events()).hasSize(1000);
        assertThatThrownBy(() -> CanonicalSource.validate(SyntheticScenario.MAXIMUM_NAME, Arrays.copyOf(padded, padded.length + 1)))
            .isInstanceOf(IllegalArgumentException.class);
    }

    @Test void countOverflowScenarioMismatchAndPrivateChangesFailBeforeAdmissionOrStorage() {
        byte[] raw = CanonicalSource.fixtureBytes(SyntheticScenario.MAXIMUM_NAME);
        String text = new String(raw, StandardCharsets.UTF_8);
        byte[] thousandOne = (text + text.substring(0, text.indexOf('\n') + 1)).getBytes(StandardCharsets.UTF_8);
        var jobs = mock(LabJobService.class); var storage = mock(RawSourceStore.class); var staging = new SourceStagingService(jobs, storage);
        for (byte[] invalid : new byte[][]{thousandOne, new byte[CanonicalSource.MAX_BYTES + 1], CanonicalSource.fixtureBytes(),
            text.replaceFirst("max-sensor-000", "private-sensor").getBytes(StandardCharsets.UTF_8)}) {
            assertThatThrownBy(() -> staging.stage("maximum-invalid", SyntheticScenario.MAXIMUM_NAME, invalid)).isInstanceOf(IllegalArgumentException.class);
        }
        assertThatThrownBy(() -> staging.stage("maximum-invalid", "sensor-validation-v3", raw)).isInstanceOf(IllegalArgumentException.class);
        assertThatThrownBy(() -> CanonicalSource.validate(raw)).isInstanceOf(IllegalArgumentException.class);
        verifyNoInteractions(jobs, storage);
    }
}
