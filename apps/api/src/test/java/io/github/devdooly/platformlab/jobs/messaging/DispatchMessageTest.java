package io.github.devdooly.platformlab.jobs.messaging;

import org.junit.jupiter.api.Test;
import static org.assertj.core.api.Assertions.*;

class DispatchMessageTest {
    private static final DispatchMessage MESSAGE = new DispatchMessage(1, "foundation-kafka-job", "sensor-validation-v1", "a".repeat(64));

    @Test void roundTripAndAsciiByteLimitUseOnlyTheFourAllowedFields() {
        assertThat(DispatchMessage.decode(MESSAGE.encode())).isEqualTo(MESSAGE);
        String exactlyLimit = " ".repeat(DispatchMessage.MAX_BYTES - MESSAGE.encode().length()) + MESSAGE.encode();
        assertThat(DispatchMessage.decode(exactlyLimit)).isEqualTo(MESSAGE);
        assertThatThrownBy(() -> DispatchMessage.decode(" " + exactlyLimit)).isInstanceOf(IllegalArgumentException.class);
        assertThat(MESSAGE.encode()).doesNotContain("sourceObjectKey", "sourceBytes");
    }

    @Test void rejectsUnknownDuplicateMissingFieldsAndIncorrectJsonTypesBeforeUse() {
        String json = MESSAGE.encode();
        for (String invalid : new String[] {
            json.replaceFirst("\\{", "{\"schemaVersion\":1,"),
            json.replaceFirst("\\{", "{\"extra\":0,"),
            json.replace("\"schemaVersion\":1,", ""),
            json.replace("\"schemaVersion\":1", "\"schemaVersion\":1.0"),
            json.replace("\"schemaVersion\":1", "\"schemaVersion\":\"1\""),
            json.replace("\"schemaVersion\":1", "\"schemaVersion\":2147483648"),
            json.replace("\"foundation-kafka-job\"", "null"),
            json.replace("\"foundation-kafka-job\"", "1"),
            json + " {}", "[" + json + "]", "", "null", json + "\u00a0"
        }) {
            assertThatThrownBy(() -> DispatchMessage.decode(invalid)).isInstanceOf(IllegalArgumentException.class);
        }
        assertThatThrownBy(() -> DispatchMessage.decode(null)).isInstanceOf(IllegalArgumentException.class);
    }

    @Test void rejectsUnsupportedVersionScenarioRunIdAndNoncanonicalHash() {
        String json = MESSAGE.encode();
        for (String invalid : new String[] {
            json.replace("\"schemaVersion\":1", "\"schemaVersion\":2"),
            json.replace("sensor-validation-v1", "sensor-validation-v2"),
            json.replace("foundation-kafka-job", "UpperCase"),
            json.replace("foundation-kafka-job", "../escape"),
            json.replace("foundation-kafka-job", "a".repeat(81)),
            json.replace("foundation-kafka-job", ""),
            json.replace("a".repeat(64), "A".repeat(64)),
            json.replace("a".repeat(64), "a".repeat(63))
        }) {
            assertThatThrownBy(() -> DispatchMessage.decode(invalid)).isInstanceOf(IllegalArgumentException.class);
        }
    }
}
