package io.github.devdooly.platformlab.jobs.messaging;

import java.util.LinkedHashMap;
import java.util.Map;
import java.util.regex.Pattern;
import org.apache.kafka.clients.CommonClientConfigs;
import org.apache.kafka.clients.consumer.Consumer;
import org.apache.kafka.clients.consumer.ConsumerConfig;
import org.apache.kafka.clients.consumer.KafkaConsumer;
import org.apache.kafka.clients.producer.KafkaProducer;
import org.apache.kafka.clients.producer.Producer;
import org.apache.kafka.clients.producer.ProducerConfig;
import org.apache.kafka.common.serialization.StringDeserializer;
import org.apache.kafka.common.serialization.StringSerializer;

/** Explicit opt-in clients for a loopback-only isolated PLAINTEXT lab, never application beans. */
public final class KafkaClientFactory {
    private static final Pattern LOOPBACK = Pattern.compile("127\\.0\\.0\\.1:([0-9]{1,5})");
    private KafkaClientFactory() {}

    public static Producer<String, String> producer(String bootstrap) {
        return new KafkaProducer<>(producerProperties(bootstrap));
    }

    public static Consumer<String, String> consumer(String bootstrap, String group) {
        return new KafkaConsumer<>(consumerProperties(bootstrap, group));
    }

    static Map<String, Object> producerProperties(String bootstrap) {
        var properties = baseProperties(bootstrap);
        properties.put(ProducerConfig.KEY_SERIALIZER_CLASS_CONFIG, StringSerializer.class);
        properties.put(ProducerConfig.VALUE_SERIALIZER_CLASS_CONFIG, StringSerializer.class);
        properties.put(ProducerConfig.ACKS_CONFIG, "all");
        properties.put(ProducerConfig.ENABLE_IDEMPOTENCE_CONFIG, true);
        properties.put(ProducerConfig.MAX_IN_FLIGHT_REQUESTS_PER_CONNECTION, 1);
        properties.put(ProducerConfig.RETRIES_CONFIG, 3);
        properties.put(ProducerConfig.REQUEST_TIMEOUT_MS_CONFIG, 5000);
        properties.put(ProducerConfig.DELIVERY_TIMEOUT_MS_CONFIG, 15000);
        properties.put(ProducerConfig.MAX_BLOCK_MS_CONFIG, 5000);
        return Map.copyOf(properties);
    }

    static Map<String, Object> consumerProperties(String bootstrap, String group) {
        if (group == null || !group.matches("[a-zA-Z0-9][a-zA-Z0-9._-]{0,127}")) {
            throw new IllegalArgumentException("An explicit bounded ASCII consumer group is required");
        }
        var properties = baseProperties(bootstrap);
        properties.put(ConsumerConfig.GROUP_ID_CONFIG, group);
        properties.put(ConsumerConfig.GROUP_PROTOCOL_CONFIG, "classic");
        properties.put(ConsumerConfig.ALLOW_AUTO_CREATE_TOPICS_CONFIG, false);
        properties.put(ConsumerConfig.KEY_DESERIALIZER_CLASS_CONFIG, StringDeserializer.class);
        properties.put(ConsumerConfig.VALUE_DESERIALIZER_CLASS_CONFIG, StringDeserializer.class);
        properties.put(ConsumerConfig.ENABLE_AUTO_COMMIT_CONFIG, false);
        properties.put(ConsumerConfig.MAX_POLL_RECORDS_CONFIG, 1);
        properties.put(ConsumerConfig.AUTO_OFFSET_RESET_CONFIG, "earliest");
        properties.put(ConsumerConfig.ISOLATION_LEVEL_CONFIG, "read_committed");
        properties.put(ConsumerConfig.SESSION_TIMEOUT_MS_CONFIG, 10000);
        properties.put(ConsumerConfig.HEARTBEAT_INTERVAL_MS_CONFIG, 3000);
        properties.put(ConsumerConfig.DEFAULT_API_TIMEOUT_MS_CONFIG, 10000);
        properties.put(ConsumerConfig.REQUEST_TIMEOUT_MS_CONFIG, 10000);
        properties.put(ConsumerConfig.MAX_POLL_INTERVAL_MS_CONFIG, 120000);
        return Map.copyOf(properties);
    }

    private static LinkedHashMap<String, Object> baseProperties(String bootstrap) {
        var match = bootstrap == null ? null : LOOPBACK.matcher(bootstrap);
        if (match == null || !match.matches() || Integer.parseInt(match.group(1)) < 1
            || Integer.parseInt(match.group(1)) > 65535) {
            throw new IllegalArgumentException("This isolated lab requires one explicit 127.0.0.1 bootstrap port");
        }
        var properties = new LinkedHashMap<String, Object>();
        properties.put(CommonClientConfigs.BOOTSTRAP_SERVERS_CONFIG, bootstrap);
        properties.put(CommonClientConfigs.SECURITY_PROTOCOL_CONFIG, "PLAINTEXT");
        return properties;
    }
}
