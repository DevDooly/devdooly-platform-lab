package io.github.devdooly.platformlab.jobs.messaging;

import org.apache.kafka.clients.consumer.ConsumerConfig;
import org.apache.kafka.clients.producer.ProducerConfig;
import org.junit.jupiter.api.Test;
import static org.assertj.core.api.Assertions.*;

class KafkaClientFactoryTest {
    @Test void producerUsesBoundedAcknowledgedIdempotentPublication() {
        var properties = KafkaClientFactory.producerProperties("127.0.0.1:19092");
        assertThat(properties).containsEntry("security.protocol", "PLAINTEXT")
            .containsEntry("bootstrap.servers", "127.0.0.1:19092")
            .containsEntry(ProducerConfig.ACKS_CONFIG, "all")
            .containsEntry(ProducerConfig.ENABLE_IDEMPOTENCE_CONFIG, true)
            .containsEntry(ProducerConfig.MAX_IN_FLIGHT_REQUESTS_PER_CONNECTION, 1)
            .containsEntry(ProducerConfig.RETRIES_CONFIG, 3)
            .containsEntry(ProducerConfig.REQUEST_TIMEOUT_MS_CONFIG, 5000)
            .containsEntry(ProducerConfig.DELIVERY_TIMEOUT_MS_CONFIG, 15000)
            .containsEntry(ProducerConfig.MAX_BLOCK_MS_CONFIG, 5000);
        // Kafka itself also validates the combined configuration without opening a client.
        assertThatCode(() -> new ProducerConfig(properties)).doesNotThrowAnyException();
    }

    @Test void consumerCannotAutoCommitAndProcessesOneBatchAtATime() {
        var properties = KafkaClientFactory.consumerProperties("127.0.0.1:19092", "foundation-worker");
        assertThat(properties).containsEntry("security.protocol", "PLAINTEXT")
            .containsEntry(ConsumerConfig.GROUP_ID_CONFIG, "foundation-worker")
            .containsEntry(ConsumerConfig.ENABLE_AUTO_COMMIT_CONFIG, false)
            .containsEntry(ConsumerConfig.MAX_POLL_RECORDS_CONFIG, 1)
            .containsEntry(ConsumerConfig.AUTO_OFFSET_RESET_CONFIG, "earliest")
            .containsEntry(ConsumerConfig.ISOLATION_LEVEL_CONFIG, "read_committed")
            .containsEntry(ConsumerConfig.SESSION_TIMEOUT_MS_CONFIG, 10000)
            .containsEntry(ConsumerConfig.HEARTBEAT_INTERVAL_MS_CONFIG, 3000)
            .containsEntry(ConsumerConfig.DEFAULT_API_TIMEOUT_MS_CONFIG, 10000)
            .containsEntry(ConsumerConfig.REQUEST_TIMEOUT_MS_CONFIG, 10000)
            .containsEntry(ConsumerConfig.MAX_POLL_INTERVAL_MS_CONFIG, 120000);
        assertThatCode(() -> new ConsumerConfig(properties)).doesNotThrowAnyException();
    }

    @Test void rejectsImplicitExternalAndInvalidBootstrapAddressesAndConsumerGroups() {
        for (String address : new String[] {"", "localhost:9092", "192.0.2.1:9092", "127.0.0.1:0", "127.0.0.1:65536",
            "127.0.0.1:9092,127.0.0.1:9093", "http://127.0.0.1:9092", "127.0.0.1:9092 "}) {
            assertThatThrownBy(() -> KafkaClientFactory.producerProperties(address)).isInstanceOf(IllegalArgumentException.class);
        }
        assertThatThrownBy(() -> KafkaClientFactory.producerProperties(null)).isInstanceOf(IllegalArgumentException.class);
        for (String group : new String[] {"", " ", "a".repeat(129), "worker/group"}) {
            assertThatThrownBy(() -> KafkaClientFactory.consumerProperties("127.0.0.1:9092", group)).isInstanceOf(IllegalArgumentException.class);
        }
        assertThatThrownBy(() -> KafkaClientFactory.consumerProperties("127.0.0.1:9092", null)).isInstanceOf(IllegalArgumentException.class);
    }
}
