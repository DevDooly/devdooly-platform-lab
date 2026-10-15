package io.github.devdooly.platformlab.jobs;

import java.net.URI;
import org.junit.jupiter.api.Test;
import static org.assertj.core.api.Assertions.*;

class LabClientEndpointsTest {
    @Test void acceptsOnlyFullBoundedLowercaseKubernetesServiceDnsLabels() {
        for (String host : new String[]{"kafka.platform-lab.svc.cluster.local", "garage.lab.svc.cluster.local",
            "a".repeat(63) + "." + "b".repeat(63) + ".svc.cluster.local"}) {
            assertThat(LabClientEndpoints.isKubernetesService(host)).isTrue();
        }
        for (String host : new String[]{"kafka", "kafka.lab", "kafka.lab.svc", "kafka.lab.svc.cluster.local.",
            "kafka.lab.svc.cluster.local.attacker.example", "kafka.extra.lab.svc.cluster.local", "Kafka.lab.svc.cluster.local",
            "-kafka.lab.svc.cluster.local", "kafka-.lab.svc.cluster.local", "kafka._lab.svc.cluster.local",
            "a".repeat(64) + ".lab.svc.cluster.local", "kafka..svc.cluster.local", "localhost", "192.0.2.1"}) {
            assertThat(LabClientEndpoints.isKubernetesService(host)).as(host).isFalse();
        }
        assertThat(LabClientEndpoints.isKubernetesService(null)).isFalse();
    }

    @Test void kafkaRejectsSchemesListsPublicHostsAndInvalidPortsBeforeClientConstruction() {
        for (String address : new String[]{"127.0.0.1:9092", "kafka.platform-lab.svc.cluster.local:9092"}) {
            assertThatCode(() -> LabClientEndpoints.requireKafkaBootstrap(address)).doesNotThrowAnyException();
        }
        for (String address : new String[]{"kafka.lab.svc.cluster.local", "kafka.lab.svc.cluster.local:0", "kafka.lab.svc.cluster.local:65536",
            "kafka.lab.svc.cluster.local:9092,second.lab.svc.cluster.local:9092", "http://kafka.lab.svc.cluster.local:9092",
            "kafka.lab.svc.cluster.local:9092/path", "user@kafka.lab.svc.cluster.local:9092", "kafka.lab.svc.cluster.local:9092 ",
            "kafka.example.com:9092", "192.0.2.28:9092", "localhost:9092", "kafka.lab.svc.cluster.local:+9092"}) {
            assertThatThrownBy(() -> LabClientEndpoints.requireKafkaBootstrap(address)).as(address).isInstanceOf(IllegalArgumentException.class);
        }
        assertThatThrownBy(() -> LabClientEndpoints.requireKafkaBootstrap(null)).isInstanceOf(IllegalArgumentException.class);
    }

    @Test void s3InternalHttpRequiresFullServiceOriginAndExplicitValidPort() {
        for (String endpoint : new String[]{"http://garage.platform-lab.svc.cluster.local:3900", "http://garage.lab.svc.cluster.local:3900/",
            "http://127.0.0.1:3900", "https://object.example.com"}) {
            assertThatCode(() -> S3ClientFactory.validateEndpoint(URI.create(endpoint))).doesNotThrowAnyException();
        }
        for (String endpoint : new String[]{"http://garage.lab.svc.cluster.local", "http://garage.lab.svc.cluster.local:0",
            "http://garage.lab.svc.cluster.local:65536", "http://garage.lab.svc.cluster.local:3900/bucket",
            "http://user:secret@garage.lab.svc.cluster.local:3900", "http://garage.lab.svc.cluster.local:3900?secret=x",
            "http://garage.lab.svc.cluster.local:3900#fragment", "http://garage.lab.svc.cluster.local.attacker.example:3900",
            "http://garage.lab.svc:3900", "http://garage:3900", "http://192.0.2.28:3900", "http://object.example.com:3900"}) {
            assertThatThrownBy(() -> S3ClientFactory.validateEndpoint(URI.create(endpoint))).as(endpoint).isInstanceOf(IllegalArgumentException.class);
        }
    }
}
