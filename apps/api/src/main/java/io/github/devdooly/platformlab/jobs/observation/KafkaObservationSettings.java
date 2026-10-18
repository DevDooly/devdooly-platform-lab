package io.github.devdooly.platformlab.jobs.observation;

import io.github.devdooly.platformlab.jobs.LabClientEndpoints;
import org.apache.kafka.common.Uuid;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

/** Fixed server settings only. Disabled configuration never opens a Kafka client. */
@Component
public final class KafkaObservationSettings {
    private final boolean enabled;
    private final String environment, sourceCommit, bootstrap, topic, group, expectedClusterId;

    public KafkaObservationSettings(@Value("${lab.kafka-observation.enabled:false}") boolean enabled,
            @Value("${lab.environment:local}") String environment,
            @Value("${lab.source-commit:unknown}") String sourceCommit,
            @Value("${lab.kafka-observation.bootstrap:}") String bootstrap,
            @Value("${lab.kafka-observation.topic:}") String topic,
            @Value("${lab.kafka-observation.group:}") String group,
            @Value("${lab.kafka-observation.expected-cluster-id:}") String expectedClusterId) {
        this.enabled = enabled; this.environment = environment; this.sourceCommit = sourceCommit;
        this.bootstrap = bootstrap; this.topic = topic; this.group = group; this.expectedClusterId = expectedClusterId;
    }

    public boolean enabled() { return enabled; }
    String environment() { return environment; }
    String sourceCommit() { return sourceCommit; }
    String bootstrap() { return bootstrap; }
    String topic() { return topic; }
    String group() { return group; }
    String expectedClusterId() { return expectedClusterId; }

    void validate() {
        try {
            if (!enabled || !("mini-pc".equals(environment) || "isolated-lab".equals(environment))
                    || sourceCommit == null || !sourceCommit.matches("[a-f0-9]{40}")
                    || topic == null || !topic.matches("[a-zA-Z0-9][a-zA-Z0-9._-]{0,248}")
                    || group == null || !group.matches("[a-zA-Z0-9][a-zA-Z0-9._-]{0,127}")
                    || expectedClusterId == null || !expectedClusterId.matches("[a-zA-Z0-9_-]{22}")) {
                throw new IllegalArgumentException();
            }
            LabClientEndpoints.requireKafkaBootstrap(bootstrap);
            Uuid id = Uuid.fromString(expectedClusterId);
            if (Uuid.ZERO_UUID.equals(id) || !id.toString().equals(expectedClusterId)) { throw new IllegalArgumentException(); }
        } catch (RuntimeException invalid) {
            throw new IllegalArgumentException("Invalid Kafka observation configuration");
        }
    }

    @Override public String toString() { return "KafkaObservationSettings[values withheld]"; }
}
