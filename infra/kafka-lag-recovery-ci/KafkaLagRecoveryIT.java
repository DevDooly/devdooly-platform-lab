package io.github.devdooly.platformlab.jobs.observation;

import java.time.Clock;
import java.time.Duration;
import java.util.ArrayList;
import java.util.HashSet;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.UUID;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.TimeUnit;
import org.apache.kafka.clients.admin.Admin;
import org.apache.kafka.clients.admin.ConsumerGroupDescription;
import org.apache.kafka.clients.admin.ListOffsetsOptions;
import org.apache.kafka.clients.admin.NewTopic;
import org.apache.kafka.clients.admin.OffsetSpec;
import org.apache.kafka.clients.consumer.ConsumerConfig;
import org.apache.kafka.clients.consumer.KafkaConsumer;
import org.apache.kafka.clients.consumer.OffsetAndMetadata;
import org.apache.kafka.clients.producer.KafkaProducer;
import org.apache.kafka.clients.producer.ProducerRecord;
import org.apache.kafka.common.GroupState;
import org.apache.kafka.common.GroupType;
import org.apache.kafka.common.IsolationLevel;
import org.apache.kafka.common.KafkaFuture;
import org.apache.kafka.common.TopicPartition;
import org.apache.kafka.common.Uuid;
import org.apache.kafka.common.serialization.StringDeserializer;
import org.apache.kafka.common.serialization.StringSerializer;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.Timeout;
import org.junit.jupiter.api.condition.EnabledIfSystemProperty;

/** Normal close/new client in a fresh owned broker; not a process crash, worker or HA test. */
@EnabledIfSystemProperty(named = "lab.kafka-lag.tests", matches = "true")
class KafkaLagRecoveryIT {
    private enum Phase {
        INPUT, CREATE_TOPIC, PRODUCE_INITIAL, INITIAL_CONSUME, INITIAL_COMMIT, INITIAL_OBSERVE,
        CLOSE_INITIAL, EMPTY_OBSERVE, PRODUCE_BACKLOG, BACKLOG_OBSERVE, RESUME_CONSUME,
        FINAL_COMMIT, FINAL_OBSERVE, CLOSE, DELETE_FIXTURE, COMPLETE
    }
    private enum Cause { ASSERTION, OBSERVATION, TIMEOUT, INTERRUPTED, KAFKA, UNEXPECTED }
    private static final class Trace {
        private Phase phase = Phase.INPUT;
        private Phase failedPhase;
        private Cause failedCause;
        private void record(Throwable error) {
            Cause classified = cause(error);
            if (classified == Cause.INTERRUPTED) { Thread.currentThread().interrupt(); }
            if (failedCause == null) { failedPhase = phase; failedCause = classified; }
        }
    }
    private record Member(String id, String instanceId, Set<TopicPartition> assignment) {}
    private record Selected(String cluster, Uuid topicId, Set<Integer> partitions, GroupState groupState,
            List<Member> members, long start, long lso, long committed) {}

    @Test
    @Timeout(180)
    void closedConsumerBacklogIsRecoveredByNewConsumerFromCommittedOffset() {
        Trace trace = new Trace();
        long deadline = System.nanoTime() + Duration.ofSeconds(150).toNanos();
        Admin driver = null;
        KafkaProducer<String, String> producer = null;
        KafkaConsumer<String, String> first = null;
        KafkaConsumer<String, String> resumed = null;
        KafkaObservationService observer = null;
        try {
            check("true".equals(required("LAB_KAFKA_LAG_TEST_DISPOSABLE")));
            String bootstrap = required("LAB_KAFKA_LAG_TEST_BOOTSTRAP");
            check("127.0.0.1:19092".equals(bootstrap));
            String cluster = required("LAB_KAFKA_LAG_TEST_CLUSTER_ID");
            check(!Uuid.ZERO_UUID.equals(Uuid.fromString(cluster)));
            String source = required("SOURCE_COMMIT");
            check(source.matches("[a-f0-9]{40}"));
            ReadOnlyKafkaAdmin.KafkaAdminAdapter.verifyLibrary();
            String suffix = UUID.randomUUID().toString();
            String topic = "platform-lab-lag-topic-" + suffix;
            String group = "platform-lab-lag-group-" + suffix;
            TopicPartition partition = new TopicPartition(topic, 0);
            Map<String, Object> base = properties(bootstrap);
            driver = Admin.create(base);
            check(cluster.equals(await(driver.describeCluster().clusterId(), deadline)));
            trace.phase = Phase.CREATE_TOPIC;
            await(driver.createTopics(List.of(new NewTopic(topic, 1, (short) 1))).all(), deadline);
            producer = new KafkaProducer<>(producerProperties(base));
            var settings = new KafkaObservationSettings(true, "isolated-lab", source, bootstrap, topic, group, cluster);
            observer = new KafkaObservationService(settings, Clock.systemUTC());

            trace.phase = Phase.PRODUCE_INITIAL;
            produce(producer, topic, 0, 12, deadline);
            trace.phase = Phase.INITIAL_CONSUME;
            first = new KafkaConsumer<>(consumerProperties(base, group, "earliest"));
            first.subscribe(List.of(topic));
            consumeExact(first, partition, 0, 4, deadline);
            check(first.assignment().equals(Set.of(partition)));
            long initialPosition = first.position(partition, budget(deadline, 10000));
            check(initialPosition == 4);
            trace.phase = Phase.INITIAL_COMMIT;
            first.commitSync(Map.of(partition, new OffsetAndMetadata(initialPosition)), budget(deadline, 10000));
            trace.phase = Phase.INITIAL_OBSERVE;
            String fingerprint = observeReadOnly(observer, driver, cluster, topic, group, partition,
                GroupState.STABLE, 12, 4, 8, deadline).targetFingerprint();

            trace.phase = Phase.CLOSE_INITIAL;
            KafkaConsumer<String, String> closingFirst = first;
            first = null; // One close attempt only, including when close itself fails.
            closingFirst.close(Duration.ofSeconds(2));
            trace.phase = Phase.EMPTY_OBSERVE;
            awaitEmpty(driver, group, deadline);
            var empty = observeReadOnly(observer, driver, cluster, topic, group, partition,
                GroupState.EMPTY, 12, 4, 8, deadline);
            check(fingerprint.equals(empty.targetFingerprint()));

            trace.phase = Phase.PRODUCE_BACKLOG;
            produce(producer, topic, 12, 6, deadline);
            trace.phase = Phase.BACKLOG_OBSERVE;
            var backlog = observeReadOnly(observer, driver, cluster, topic, group, partition,
                GroupState.EMPTY, 18, 4, 14, deadline);
            check(fingerprint.equals(backlog.targetFingerprint()));

            trace.phase = Phase.RESUME_CONSUME;
            // A separate client must use the group's committed offset. No seek, reset or manual assignment.
            resumed = new KafkaConsumer<>(consumerProperties(base, group, "none"));
            resumed.subscribe(List.of(topic));
            consumeExact(resumed, partition, 4, 14, deadline);
            check(resumed.assignment().equals(Set.of(partition)));
            long finalPosition = resumed.position(partition, budget(deadline, 10000));
            check(finalPosition == 18);
            trace.phase = Phase.FINAL_COMMIT;
            resumed.commitSync(Map.of(partition, new OffsetAndMetadata(finalPosition)), budget(deadline, 10000));
            trace.phase = Phase.FINAL_OBSERVE;
            var recovered = observeReadOnly(observer, driver, cluster, topic, group, partition,
                GroupState.STABLE, 18, 18, 0, deadline);
            check(fingerprint.equals(recovered.targetFingerprint()));
            check(observer.ownerThreadsCreated() == 1 && !observer.poisoned());

            trace.phase = Phase.CLOSE;
            KafkaConsumer<String, String> closingResumed = resumed;
            resumed = null;
            closingResumed.close(Duration.ofSeconds(2));
            KafkaProducer<String, String> closingProducer = producer;
            producer = null;
            closingProducer.close(Duration.ofSeconds(2));
            KafkaObservationService closingObserver = observer;
            observer = null;
            closingObserver.close();
            // Only a successful case with both consumers closed can delete its unique fixtures.
            trace.phase = Phase.DELETE_FIXTURE;
            awaitEmpty(driver, group, deadline);
            await(driver.deleteConsumerGroups(Set.of(group)).all(), deadline);
            await(driver.deleteTopics(Set.of(topic)).all(), deadline);
            trace.phase = Phase.CLOSE;
            Admin closingDriver = driver;
            driver = null;
            closingDriver.close(Duration.ofSeconds(1));
            remainingMillis(deadline, 1);
            trace.phase = Phase.COMPLETE;
        } catch (Throwable error) {
            trace.record(error);
        } finally {
            trace.phase = Phase.CLOSE;
            // On failure, close returned clients once; the runner owns broker/network cleanup.
            // Unknown or unsuccessful fixtures are never adopted or deleted here.
            if (resumed != null) {
                try { resumed.close(Duration.ofSeconds(2)); } catch (Throwable error) { trace.record(error); }
            }
            if (first != null) {
                try { first.close(Duration.ofSeconds(2)); } catch (Throwable error) { trace.record(error); }
            }
            if (producer != null) {
                try { producer.close(Duration.ofSeconds(2)); } catch (Throwable error) { trace.record(error); }
            }
            if (observer != null) {
                try { observer.close(); } catch (Throwable error) { trace.record(error); }
            }
            if (driver != null) {
                try { driver.close(Duration.ofSeconds(1)); } catch (Throwable error) { trace.record(error); }
            }
        }
        if (trace.failedCause != null) {
            System.out.println("KAFKA_LAG_RECOVERY_FAILURE {\"schemaVersion\":1,\"status\":\"FAILED\",\"phase\":\""
                + trace.failedPhase.name() + "\",\"cause\":\"" + trace.failedCause.name() + "\"}");
            throw new AssertionError("KAFKA_LAG_FIXED_FAILURE_" + trace.failedPhase.name() + "_" + trace.failedCause.name());
        }
        System.out.println("KAFKA_LAG_RECOVERY_RESULT {\"schemaVersion\":1,\"status\":\"PASS\",\"initialProcessed\":4,"
            + "\"initialEndOffset\":12,\"initialCommittedOffset\":4,\"initialLag\":8,\"emptyGroupObserved\":true,"
            + "\"additionalProduced\":6,\"backlogEndOffset\":18,\"backlogCommittedOffset\":4,\"backlogLag\":14,"
            + "\"resumedProcessed\":14,\"resumedFirstOffset\":4,\"resumedLastOffset\":17,"
            + "\"finalCommittedOffset\":18,\"finalLag\":0,\"targetStable\":true}");
    }

    private static KafkaObservationService.Observation observeReadOnly(KafkaObservationService observer, Admin driver,
            String cluster, String topic, String group, TopicPartition partition, GroupState state,
            long end, long committed, long lag, long deadline) throws Exception {
        Selected before = selected(driver, cluster, topic, group, partition, deadline);
        check(before.groupState() == state && before.members().size() == (state == GroupState.EMPTY ? 0 : 1)
            && before.start() == 0 && before.lso() == end && before.committed() == committed);
        var observed = observer.capture();
        remainingMillis(deadline, 1);
        check("OBSERVED".equals(observed.commitState()) && state.name().equals(observed.groupState())
            && observed.partition() == 0 && observed.logStartOffset() == 0 && observed.readCommittedEndOffset() == end
            && Long.valueOf(committed).equals(observed.committedOffset()) && Long.valueOf(lag).equals(observed.lag())
            && observed.targetFingerprint() != null && observed.targetFingerprint().matches("[a-f0-9]{64}"));
        check(before.equals(selected(driver, cluster, topic, group, partition, deadline)));
        check(observer.ownerThreadsCreated() == 1 && !observer.poisoned());
        return observed;
    }

    private static Selected selected(Admin driver, String cluster, String topic, String group,
            TopicPartition partition, long deadline) throws Exception {
        check(cluster.equals(await(driver.describeCluster().clusterId(), deadline)));
        var topics = await(driver.describeTopics(Set.of(topic)).allTopicNames(), deadline);
        check(topics.keySet().equals(Set.of(topic)));
        var description = topics.get(topic);
        check(description != null && !description.isInternal() && !Uuid.ZERO_UUID.equals(description.topicId())
            && description.partitions().size() == 1 && description.partitions().getFirst().partition() == 0);
        ConsumerGroupDescription membership = group(driver, group, deadline);
        check(membership.groupState() == GroupState.STABLE || membership.groupState() == GroupState.EMPTY);
        var members = new ArrayList<Member>();
        for (var member : membership.members()) {
            check(member.consumerId() != null && !member.consumerId().isBlank() && member.groupInstanceId() != null
                && member.assignment() != null && member.assignment().topicPartitions().equals(Set.of(partition)));
            members.add(new Member(member.consumerId(), member.groupInstanceId().orElse(null),
                Set.copyOf(member.assignment().topicPartitions())));
        }
        check(members.size() == (membership.groupState() == GroupState.EMPTY ? 0 : 1));
        long start = await(driver.listOffsets(Map.of(partition, OffsetSpec.earliest()),
            new ListOffsetsOptions(IsolationLevel.READ_COMMITTED)).all(), deadline).get(partition).offset();
        long lso = await(driver.listOffsets(Map.of(partition, OffsetSpec.latest()),
            new ListOffsetsOptions(IsolationLevel.READ_COMMITTED)).all(), deadline).get(partition).offset();
        var offsets = await(driver.listConsumerGroupOffsets(group).partitionsToOffsetAndMetadata(), deadline);
        check(offsets.keySet().equals(Set.of(partition)) && offsets.get(partition) != null);
        return new Selected(cluster, description.topicId(), Set.of(0), membership.groupState(),
            List.copyOf(members), start, lso, offsets.get(partition).offset());
    }

    private static ConsumerGroupDescription group(Admin driver, String group, long deadline) throws Exception {
        var groups = await(driver.describeConsumerGroups(Set.of(group)).all(), deadline);
        check(groups.keySet().equals(Set.of(group)));
        var description = groups.get(group);
        check(description != null && group.equals(description.groupId()) && description.type() == GroupType.CLASSIC
            && !description.isSimpleConsumerGroup() && description.members() != null);
        return description;
    }

    private static void awaitEmpty(Admin driver, String group, long deadline) throws Exception {
        long until = Math.min(deadline, System.nanoTime() + Duration.ofSeconds(30).toNanos());
        // Bounded state observation only: an RPC error aborts; no failed call or test is retried.
        while (true) {
            var description = group(driver, group, until);
            if (description.groupState() == GroupState.EMPTY) { check(description.members().isEmpty()); return; }
            TimeUnit.MILLISECONDS.sleep(remainingMillis(until, 100));
        }
    }

    private static void produce(KafkaProducer<String, String> producer, String topic, int first, int count,
            long deadline) throws Exception {
        for (int index = first; index < first + count; index++) {
            remainingMillis(deadline, 1);
            var future = producer.send(new ProducerRecord<>(topic, 0, "synthetic-" + index, "value-" + index));
            var metadata = future.get(remainingMillis(deadline, 10000), TimeUnit.MILLISECONDS);
            remainingMillis(deadline, 1);
            check(topic.equals(metadata.topic()) && metadata.partition() == 0 && metadata.offset() == index);
        }
    }

    private static void consumeExact(KafkaConsumer<String, String> consumer, TopicPartition partition,
            int first, int count, long deadline) throws Exception {
        long until = Math.min(deadline, System.nanoTime() + Duration.ofSeconds(30).toNanos());
        Set<Long> offsets = new HashSet<>();
        Set<String> keys = new HashSet<>(), values = new HashSet<>();
        int received = 0;
        while (received < count) {
            var records = consumer.poll(budget(until, 250));
            remainingMillis(until, 1);
            for (var record : records) {
                long expected = (long) first + received;
                check(received < count && partition.topic().equals(record.topic()) && record.partition() == partition.partition()
                    && record.offset() == expected && ("synthetic-" + expected).equals(record.key())
                    && ("value-" + expected).equals(record.value())
                    && offsets.add(record.offset()) && keys.add(record.key()) && values.add(record.value()));
                received++;
            }
        }
        check(received == count && offsets.size() == count && keys.size() == count && values.size() == count
            && offsets.contains((long) first) && offsets.contains((long) first + count - 1));
    }

    private static Map<String, Object> properties(String bootstrap) {
        var value = new LinkedHashMap<String, Object>();
        value.put("bootstrap.servers", bootstrap); value.put("security.protocol", "PLAINTEXT");
        value.put("request.timeout.ms", 3000); value.put("default.api.timeout.ms", 10000); value.put("retries", 1);
        value.put("enable.metrics.push", false); value.put("metric.reporters", List.of());
        return value;
    }

    private static Map<String, Object> producerProperties(Map<String, Object> base) {
        var value = new LinkedHashMap<>(base);
        value.put("key.serializer", StringSerializer.class); value.put("value.serializer", StringSerializer.class);
        value.put("acks", "all"); value.put("enable.idempotence", false); value.put("retries", 0);
        value.put("delivery.timeout.ms", 8000); value.put("max.block.ms", 8000);
        return value;
    }

    private static Map<String, Object> consumerProperties(Map<String, Object> base, String group, String reset) {
        check("earliest".equals(reset) || "none".equals(reset));
        var value = new LinkedHashMap<>(base);
        value.remove("retries");
        value.put(ConsumerConfig.GROUP_ID_CONFIG, group); value.put(ConsumerConfig.GROUP_PROTOCOL_CONFIG, "classic");
        value.put(ConsumerConfig.ENABLE_AUTO_COMMIT_CONFIG, false); value.put(ConsumerConfig.ALLOW_AUTO_CREATE_TOPICS_CONFIG, false);
        value.put(ConsumerConfig.AUTO_OFFSET_RESET_CONFIG, reset); value.put(ConsumerConfig.MAX_POLL_RECORDS_CONFIG, 4);
        value.put(ConsumerConfig.ISOLATION_LEVEL_CONFIG, "read_committed");
        value.put(ConsumerConfig.KEY_DESERIALIZER_CLASS_CONFIG, StringDeserializer.class);
        value.put(ConsumerConfig.VALUE_DESERIALIZER_CLASS_CONFIG, StringDeserializer.class);
        value.put(ConsumerConfig.SESSION_TIMEOUT_MS_CONFIG, 10000); value.put(ConsumerConfig.HEARTBEAT_INTERVAL_MS_CONFIG, 1000);
        value.put(ConsumerConfig.MAX_POLL_INTERVAL_MS_CONFIG, 300000);
        return value;
    }

    private static <T> T await(KafkaFuture<T> future, long deadline) throws Exception {
        T result = future.get(remainingMillis(deadline, 10000), TimeUnit.MILLISECONDS);
        remainingMillis(deadline, 1);
        return result;
    }

    private static Duration budget(long deadline, int maximumMillis) throws java.util.concurrent.TimeoutException {
        return Duration.ofMillis(remainingMillis(deadline, maximumMillis));
    }

    private static int remainingMillis(long deadline, int maximumMillis) throws java.util.concurrent.TimeoutException {
        long remaining = deadline - System.nanoTime();
        if (remaining <= 0) { throw new java.util.concurrent.TimeoutException(); }
        return (int) Math.max(1, Math.min(maximumMillis, TimeUnit.NANOSECONDS.toMillis(remaining)));
    }

    private static Cause cause(Throwable error) {
        Throwable current = error;
        for (int depth = 0; depth < 3; depth++) {
            if ((current instanceof ExecutionException || current.getClass() == org.apache.kafka.common.KafkaException.class)
                    && current.getCause() != null) { current = current.getCause(); }
            else { break; }
        }
        if (current instanceof AssertionError) { return Cause.ASSERTION; }
        if (current instanceof KafkaObservationService.ObservationFailure) { return Cause.OBSERVATION; }
        if (current instanceof InterruptedException || current instanceof org.apache.kafka.common.errors.InterruptException) {
            return Cause.INTERRUPTED;
        }
        if (current instanceof java.util.concurrent.TimeoutException
                || current instanceof org.apache.kafka.common.errors.TimeoutException) { return Cause.TIMEOUT; }
        if (current instanceof org.apache.kafka.common.KafkaException) { return Cause.KAFKA; }
        return Cause.UNEXPECTED;
    }

    private static String required(String key) {
        String value = System.getenv(key); check(value != null && !value.isBlank()); return value;
    }

    private static void check(boolean value) { if (!value) { throw new AssertionError("KAFKA_LAG_FIXED_ASSERTION"); } }
}
