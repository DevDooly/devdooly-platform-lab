package io.github.devdooly.platformlab.jobs.observation;

import java.time.Clock;
import java.time.Duration;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.UUID;
import java.util.concurrent.TimeUnit;
import org.apache.kafka.clients.admin.Admin;
import org.apache.kafka.clients.admin.NewTopic;
import org.apache.kafka.clients.admin.OffsetSpec;
import org.apache.kafka.clients.consumer.ConsumerConfig;
import org.apache.kafka.clients.consumer.KafkaConsumer;
import org.apache.kafka.clients.consumer.OffsetAndMetadata;
import org.apache.kafka.clients.producer.KafkaProducer;
import org.apache.kafka.clients.producer.ProducerRecord;
import org.apache.kafka.common.GroupState;
import org.apache.kafka.common.TopicPartition;
import org.apache.kafka.common.Uuid;
import org.apache.kafka.common.serialization.StringDeserializer;
import org.apache.kafka.common.serialization.StringSerializer;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.Timeout;
import org.junit.jupiter.api.condition.EnabledIfSystemProperty;
import static org.assertj.core.api.Assertions.*;

/** Explicit disposable broker only. No Mini PC, HTTP deployment, capacity or automatic CI execution. */
@EnabledIfSystemProperty(named = "lab.kafka-observation.tests", matches = "true")
class KafkaObservationIT {
    @Timeout(value = 180)
    @Test void realClassicGroupNoCommitPositiveZeroAndUncommittedTransactionProveReadOnlyLsoObservation() throws Exception {
        String bootstrap = required("LAB_KAFKA_OBSERVATION_TEST_BOOTSTRAP");
        assertThat(bootstrap).matches("127\\.0\\.0\\.1:[0-9]{1,5}");
        int port = Integer.parseInt(bootstrap.substring(bootstrap.lastIndexOf(':') + 1)); assertThat(port).isBetween(1024, 65535);
        assertThat(required("LAB_KAFKA_OBSERVATION_TEST_DISPOSABLE")).isEqualTo("true");
        String cluster = required("LAB_KAFKA_OBSERVATION_TEST_CLUSTER_ID");
        assertThat(Uuid.fromString(cluster)).isNotEqualTo(Uuid.ZERO_UUID);
        String source = required("SOURCE_COMMIT"); assertThat(source).matches("[a-f0-9]{40}");
        String suffix = UUID.randomUUID().toString();
        String topic = "platform-lab-kafka-observation-test-" + suffix, group = "platform-lab-kafka-observation-test-" + suffix;
        var partition = new TopicPartition(topic, 0);
        var driverProperties = new LinkedHashMap<String, Object>();
        driverProperties.put("bootstrap.servers", bootstrap); driverProperties.put("security.protocol", "PLAINTEXT");
        driverProperties.put("request.timeout.ms", 5000); driverProperties.put("default.api.timeout.ms", 10000);
        driverProperties.put("enable.metrics.push", false); driverProperties.put("metric.reporters", List.of());
        boolean created = false, passed = false;
        Admin driver = Admin.create(driverProperties);
        try {
            assertThat(driver.describeCluster().clusterId().get(10, TimeUnit.SECONDS)).isEqualTo(cluster);
            // Fresh UUID names only. The external reviewed runner must also prove this is a new owned broker.
            driver.createTopics(List.of(new NewTopic(topic, 1, (short) 1))).all().get(10, TimeUnit.SECONDS); created = true;
            var producerProperties = new LinkedHashMap<>(driverProperties);
            producerProperties.put("key.serializer", StringSerializer.class); producerProperties.put("value.serializer", StringSerializer.class);
            producerProperties.put("acks", "all"); producerProperties.put("enable.idempotence", true);
            var consumerProperties = new LinkedHashMap<>(driverProperties);
            consumerProperties.put(ConsumerConfig.GROUP_ID_CONFIG, group); consumerProperties.put(ConsumerConfig.GROUP_PROTOCOL_CONFIG, "classic");
            consumerProperties.put(ConsumerConfig.ENABLE_AUTO_COMMIT_CONFIG, false); consumerProperties.put(ConsumerConfig.ALLOW_AUTO_CREATE_TOPICS_CONFIG, false);
            consumerProperties.put(ConsumerConfig.AUTO_OFFSET_RESET_CONFIG, "earliest"); consumerProperties.put(ConsumerConfig.ISOLATION_LEVEL_CONFIG, "read_committed");
            consumerProperties.put(ConsumerConfig.KEY_DESERIALIZER_CLASS_CONFIG, StringDeserializer.class);
            consumerProperties.put(ConsumerConfig.VALUE_DESERIALIZER_CLASS_CONFIG, StringDeserializer.class);
            consumerProperties.put(ConsumerConfig.SESSION_TIMEOUT_MS_CONFIG, 10000);
            var settings = new KafkaObservationSettings(true, "isolated-lab", source, bootstrap, topic, group, cluster);
            var observer = new KafkaObservationService(settings, Clock.systemUTC());
            var producer = new KafkaProducer<String, String>(producerProperties);
            KafkaConsumer<String, String> consumer = null;
            try {
                consumer = new KafkaConsumer<>(consumerProperties);
                for (int index = 0; index < 3; index++) { producer.send(new ProducerRecord<>(topic, 0, "synthetic-" + index, "value-" + index)).get(10, TimeUnit.SECONDS); }
                consumer.subscribe(List.of(topic)); int received = 0;
                long until = System.nanoTime() + Duration.ofSeconds(30).toNanos();
                while (received < 3 && System.nanoTime() < until) { received += consumer.poll(Duration.ofMillis(250)).count(); }
                assertThat(received).isEqualTo(3); assertThat(consumer.assignment()).containsExactly(partition);
                var initialGroup = driver.describeConsumerGroups(Set.of(group)).all().get(10, TimeUnit.SECONDS).get(group);
                assertThat(initialGroup.groupState()).isEqualTo(GroupState.STABLE);
                String member = initialGroup.members().iterator().next().consumerId();
                var missing = observer.capture();
                assertThat(missing.commitState()).isEqualTo("NO_COMMIT"); assertThat(missing.committedOffset()).isNull(); assertThat(missing.lag()).isNull();
                assertThat(missing.readCommittedEndOffset()).isEqualTo(3);
                consumer.commitSync(Map.of(partition, new OffsetAndMetadata(1)), Duration.ofSeconds(10));
                var positive = observer.capture(); assertThat(positive.committedOffset()).isEqualTo(1L); assertThat(positive.lag()).isEqualTo(2L);
                assertThat(driver.listConsumerGroupOffsets(group).partitionsToOffsetAndMetadata().get(10, TimeUnit.SECONDS).get(partition).offset()).isEqualTo(1);
                consumer.commitSync(Map.of(partition, new OffsetAndMetadata(3)), Duration.ofSeconds(10));
                var zero = observer.capture(); assertThat(zero.commitState()).isEqualTo("OBSERVED"); assertThat(zero.lag()).isZero();
                var transactionalProperties = new LinkedHashMap<>(producerProperties);
                transactionalProperties.put("transactional.id", "platform-lab-kafka-observation-test-" + suffix);
                var transactional = new KafkaProducer<String, String>(transactionalProperties);
                try {
                    transactional.initTransactions(); transactional.beginTransaction();
                    try {
                        transactional.send(new ProducerRecord<>(topic, 0, "uncommitted-synthetic", "value")).get(10, TimeUnit.SECONDS);
                        var raw = driver.listOffsets(Map.of(partition, OffsetSpec.latest())).all().get(10, TimeUnit.SECONDS).get(partition).offset();
                        assertThat(raw).isGreaterThan(3);
                        var isolated = observer.capture(); assertThat(isolated.readCommittedEndOffset()).isEqualTo(3); assertThat(isolated.lag()).isZero();
                        assertThat(isolated.targetFingerprint()).isEqualTo(zero.targetFingerprint());
                    } finally { transactional.abortTransaction(); }
                } finally { transactional.close(Duration.ofSeconds(2)); }
                var after = driver.describeConsumerGroups(Set.of(group)).all().get(10, TimeUnit.SECONDS).get(group);
                assertThat(after.groupState()).isEqualTo(GroupState.STABLE);
                assertThat(after.members()).hasSize(1); assertThat(after.members().iterator().next().consumerId()).isEqualTo(member);
                assertThat(driver.listConsumerGroupOffsets(group).partitionsToOffsetAndMetadata().get(10, TimeUnit.SECONDS).get(partition).offset()).isEqualTo(3);
                assertThat(observer.ownerThreadsCreated()).isEqualTo(1); assertThat(observer.poisoned()).isFalse(); passed = true;
            } finally {
                try { if (consumer != null) { consumer.close(Duration.ofSeconds(2)); } }
                finally { try { producer.close(Duration.ofSeconds(2)); } finally { observer.close(); } }
            }
            // Delete only after the successful case and closed test consumer; failure leaves proof/data for the owned runner.
            if (passed) { driver.deleteConsumerGroups(Set.of(group)).all().get(10, TimeUnit.SECONDS); driver.deleteTopics(Set.of(topic)).all().get(10, TimeUnit.SECONDS); created = false; }
        } finally {
            driver.close(Duration.ofSeconds(1));
            // 'created' is intentionally not used for speculative cleanup after an unknown/failing create outcome.
            if (created && passed) { throw new AssertionError("Owned successful fixture cleanup was not confirmed"); }
        }
    }

    static String required(String name) {
        String value = System.getenv(name);
        if (value == null || value.isBlank()) { throw new IllegalStateException("Explicit disposable Kafka test configuration required"); }
        return value;
    }
}
