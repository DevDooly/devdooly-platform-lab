package io.github.devdooly.platformlab.jobs.runtime;

import java.util.ArrayList;
import java.util.List;
import org.junit.jupiter.api.Test;
import static org.assertj.core.api.Assertions.*;

class RuntimeResourcesTest {
    @Test void closeAttemptsEveryResourceOnceInOrderAndDoesNotExposeFailureDetails() throws Exception {
        var closed = new ArrayList<String>();
        var resources = new RuntimeResources(() -> { closed.add("consumer"); throw new Exception("private credential"); },
            () -> closed.add("producer"), () -> closed.add("object store"));
        assertThatThrownBy(resources::close).isInstanceOf(IllegalStateException.class).hasMessageNotContaining("credential").hasCause(null);
        resources.close(); assertThat(closed).containsExactly("consumer", "producer", "object store");
    }

    @Test void stageScenarioSettingIsAnExactAllowlistWithLegacyDefault() {
        assertThat(FixedFixtureStager.scenarioFromSetting(null)).isEqualTo("sensor-validation-v1");
        assertThat(FixedFixtureStager.scenarioFromSetting("sensor-validation-v1")).isEqualTo("sensor-validation-v1");
        assertThat(FixedFixtureStager.scenarioFromSetting("sensor-validation-v2")).isEqualTo("sensor-validation-v2");
        for (String invalid : new String[]{"", " sensor-validation-v2", "sensor-validation-v3", "1000", "file:///private/input", "https://example.com/input"}) {
            assertThatThrownBy(() -> FixedFixtureStager.scenarioFromSetting(invalid)).isInstanceOf(IllegalArgumentException.class);
        }
    }

    @Test void consoleRoutingRequiresAnExplicitRuntimeArgument() {
        assertThat(RuntimeMain.isRuntimeCommand(new String[0])).isFalse();
        assertThat(RuntimeMain.isRuntimeCommand(new String[]{"--server.port=8080"})).isFalse();
        assertThat(RuntimeMain.isRuntimeCommand(new String[]{"--lab-runtime=run"})).isTrue();
        assertThat(RuntimeMain.isRuntimeCommand(new String[]{"--lab-runtime=stage"})).isTrue();
        assertThatThrownBy(() -> RuntimeMain.run(new String[]{"--lab-runtime=stage", "--source-file=private.csv"}))
            .isInstanceOf(IllegalArgumentException.class);
        assertThatThrownBy(() -> RuntimeMain.run(new String[]{"--lab-runtime=wrong"})).isInstanceOf(IllegalArgumentException.class);
        assertThatThrownBy(() -> RuntimeMain.run(new String[]{"--lab-runtime=run", "--spring.flyway.enabled=true"}))
            .isInstanceOf(IllegalArgumentException.class);
    }
}
