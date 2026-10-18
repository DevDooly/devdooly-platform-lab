package io.github.devdooly.platformlab.jobs.observation;

import java.io.ByteArrayInputStream;
import java.nio.file.Files;
import java.nio.file.LinkOption;
import java.nio.file.Path;
import java.time.Clock;
import java.time.Duration;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Properties;
import java.util.Set;
import java.util.UUID;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.TimeUnit;
import org.apache.kafka.clients.admin.Admin;
import org.apache.kafka.clients.admin.AlterConfigOp;
import org.apache.kafka.clients.admin.ConfigEntry;
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
import org.apache.kafka.common.TopicPartition;
import org.apache.kafka.common.Uuid;
import org.apache.kafka.common.acl.AccessControlEntry;
import org.apache.kafka.common.acl.AclBinding;
import org.apache.kafka.common.acl.AclBindingFilter;
import org.apache.kafka.common.acl.AclOperation;
import org.apache.kafka.common.acl.AclPermissionType;
import org.apache.kafka.common.config.ConfigResource;
import org.apache.kafka.common.errors.GroupAuthorizationException;
import org.apache.kafka.common.errors.SaslAuthenticationException;
import org.apache.kafka.common.errors.TopicAuthorizationException;
import org.apache.kafka.common.resource.PatternType;
import org.apache.kafka.common.resource.ResourcePattern;
import org.apache.kafka.common.resource.ResourceType;
import org.apache.kafka.common.serialization.StringDeserializer;
import org.apache.kafka.common.serialization.StringSerializer;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.Timeout;
import org.junit.jupiter.api.condition.EnabledIfSystemProperty;
import static io.github.devdooly.platformlab.jobs.observation.KafkaObservationService.Code.CLOSE_UNVERIFIED;
import static io.github.devdooly.platformlab.jobs.observation.KafkaObservationService.failure;

/** Synthetic SASL/ACL only. Production configuration and the existing IT remain unchanged. */
@EnabledIfSystemProperty(named = "lab.kafka-acl.tests", matches = "true")
class KafkaObservationAclIT {
    private enum Phase { INPUT, SETUP, BASELINE, OBSERVER, DENIED_RPCS, PRESERVATION, BAD_PASSWORD, CLOSE, COMPLETE }
    private enum FailureKind { ASSERTION, OBSERVATION, INTERRUPTED, UNEXPECTED }
    private enum Rpc { OTHER_TOPIC, OTHER_GROUP, ALTER_CONFIG, OFFSET_COMMIT, PRODUCE, BAD_PASSWORD }
    private enum CauseKind { TOPIC_AUTH, GROUP_AUTH, SASL_AUTH, TIMEOUT, OTHER, NONE }
    private enum SetupStep { NONE, ADMIN_CREATE, DESCRIBE_CLUSTER, CREATE_TOPICS, OTHER_GROUP_OFFSETS,
        OTHER_GROUP_DESCRIBE, CONSUMER_CONFIG, CONSUMER_CREATE, CONSUMER_JOIN, PRODUCER_CONFIG,
        PRODUCER_CREATE, PRODUCE_RECORDS, PRODUCER_CLOSE, INITIAL_COMMIT, ACL_PROFILE, CREATE_ACLS,
        DESCRIBE_ACLS, CONSUMER_CLOSE, DRIVER_CLOSE }
    private enum SetupCause { NONE, ASSERTION, GROUP_NOT_FOUND, COORDINATOR, NOT_CONTROLLER,
        AUTHORIZER_NOT_READY, AUTHORIZATION, AUTHENTICATION, CONFIGURATION, TIMEOUT, INTERRUPTED, OTHER }
    private static final class SetupTrace {
        private SetupStep current = SetupStep.NONE;
        private SetupStep firstStep = SetupStep.NONE;
        private SetupCause firstCause = SetupCause.NONE;
        private void record(Throwable error) {
            if (firstStep == SetupStep.NONE) {
                firstStep = current;
                firstCause = setupCause(error);
            }
        }
    }
    private record Credentials(String admin, String observer) {}
    private record SelectedState(String cluster, Uuid topicId, Set<Integer> partitions,
            GroupType type, GroupState state, boolean simple, String member, String instance,
            Set<TopicPartition> assignment, long start, long lso, long end, long committed, String retention) {}
    @FunctionalInterface private interface CheckedCall { void run() throws Exception; }

    @Test
    @Timeout(180)
    void describeOnlyPrincipalObservesAndRejectsSelectedRpcs() {
        Phase phase = Phase.INPUT;
        SetupTrace setup = new SetupTrace();
        try {
            check("true".equals(required("LAB_KAFKA_ACL_TEST_DISPOSABLE")));
            String bootstrap = required("LAB_KAFKA_ACL_TEST_BOOTSTRAP");
            check("127.0.0.1:19092".equals(bootstrap));
            String source = required("SOURCE_COMMIT");
            check(source.matches("[a-f0-9]{40}"));
            String cluster = required("LAB_KAFKA_ACL_TEST_CLUSTER_ID");
            check(!Uuid.ZERO_UUID.equals(Uuid.fromString(cluster)));
            Credentials credentials = credentials();
            ReadOnlyKafkaAdmin.KafkaAdminAdapter.verifyLibrary();
            String suffix = UUID.randomUUID().toString();
            String topic = "platform-lab-acl-topic-" + suffix, otherTopic = "platform-lab-acl-other-" + suffix;
            String group = "platform-lab-acl-group-" + suffix, otherGroup = "platform-lab-acl-other-group-" + suffix;
            TopicPartition partition = new TopicPartition(topic, 0), otherPartition = new TopicPartition(otherTopic, 0);
            ConfigResource config = new ConfigResource(ConfigResource.Type.TOPIC, topic);
            Map<String, Object> adminProperties = properties(bootstrap, "acl_admin", credentials.admin());
            phase = Phase.SETUP;
            setup.current = SetupStep.ADMIN_CREATE;
            Admin driver = Admin.create(adminProperties);
            try {
                setup.current = SetupStep.DESCRIBE_CLUSTER;
                check(cluster.equals(driver.describeCluster().clusterId().get(10, TimeUnit.SECONDS)));
                setup.current = SetupStep.CREATE_TOPICS;
                driver.createTopics(List.of(new NewTopic(topic, 1, (short) 1).configs(Map.of("retention.ms", "86400000")),
                    new NewTopic(otherTopic, 1, (short) 1))).all().get(10, TimeUnit.SECONDS);
                setup.current = SetupStep.CONSUMER_CONFIG;
                Map<String, Object> consumerProperties = new LinkedHashMap<>(adminProperties);
                consumerProperties.put(ConsumerConfig.GROUP_ID_CONFIG, group);
                consumerProperties.put(ConsumerConfig.GROUP_PROTOCOL_CONFIG, "classic");
                consumerProperties.put(ConsumerConfig.ENABLE_AUTO_COMMIT_CONFIG, false);
                consumerProperties.put(ConsumerConfig.ALLOW_AUTO_CREATE_TOPICS_CONFIG, false);
                consumerProperties.put(ConsumerConfig.AUTO_OFFSET_RESET_CONFIG, "earliest");
                consumerProperties.put(ConsumerConfig.KEY_DESERIALIZER_CLASS_CONFIG, StringDeserializer.class);
                consumerProperties.put(ConsumerConfig.VALUE_DESERIALIZER_CLASS_CONFIG, StringDeserializer.class);
                consumerProperties.put(ConsumerConfig.SESSION_TIMEOUT_MS_CONFIG, 10000);
                consumerProperties.put(ConsumerConfig.HEARTBEAT_INTERVAL_MS_CONFIG, 1000);
                consumerProperties.put(ConsumerConfig.MAX_POLL_INTERVAL_MS_CONFIG, 300000);
                setup.current = SetupStep.CONSUMER_CREATE;
                KafkaConsumer<String, String> fixture = new KafkaConsumer<>(consumerProperties);
                try {
                    setup.current = SetupStep.CONSUMER_JOIN;
                    fixture.subscribe(List.of(topic));
                    long joinDeadline = System.nanoTime() + Duration.ofSeconds(30).toNanos();
                    while (fixture.assignment().isEmpty() && System.nanoTime() < joinDeadline) {
                        check(fixture.poll(Duration.ofMillis(250)).isEmpty());
                    }
                    check(fixture.assignment().equals(Set.of(partition)));
                    // Foreground poll ends here. The pinned classic client's heartbeat thread remains active.
                    // max.poll.interval is longer than the whole 180-second method; drift is never retried.
                    setup.current = SetupStep.PRODUCER_CONFIG;
                    Map<String, Object> producerProperties = producerProperties(adminProperties);
                    setup.current = SetupStep.PRODUCER_CREATE;
                    KafkaProducer<String, String> producer = new KafkaProducer<>(producerProperties);
                    try {
                        setup.current = SetupStep.PRODUCE_RECORDS;
                        for (int index = 0; index < 3; index++) {
                            producer.send(new ProducerRecord<>(topic, 0, "synthetic-" + index, "value-" + index))
                                .get(10, TimeUnit.SECONDS);
                        }
                    } catch (Throwable error) {
                        setup.record(error);
                        throw error;
                    } finally {
                        setup.current = SetupStep.PRODUCER_CLOSE;
                        producer.close(Duration.ofSeconds(2));
                    }
                    setup.current = SetupStep.INITIAL_COMMIT;
                    fixture.commitSync(Map.of(partition, new OffsetAndMetadata(1)), Duration.ofSeconds(10));
                    setup.current = SetupStep.OTHER_GROUP_OFFSETS;
                    driver.alterConsumerGroupOffsets(otherGroup, Map.of(otherPartition, new OffsetAndMetadata(0)))
                        .all().get(10, TimeUnit.SECONDS);
                    setup.current = SetupStep.OTHER_GROUP_DESCRIBE;
                    check(driver.describeConsumerGroups(Set.of(otherGroup)).all().get(10, TimeUnit.SECONDS).containsKey(otherGroup));
                    setup.current = SetupStep.ACL_PROFILE;
                    Set<AclBinding> profile = Set.of(
                        describe(ResourceType.CLUSTER, "kafka-cluster"),
                        describe(ResourceType.TOPIC, topic), describe(ResourceType.GROUP, group));
                    setup.current = SetupStep.CREATE_ACLS;
                    driver.createAcls(profile).all().get(10, TimeUnit.SECONDS);
                    setup.current = SetupStep.DESCRIBE_ACLS;
                    check(Set.copyOf(driver.describeAcls(AclBindingFilter.ANY).values().get(10, TimeUnit.SECONDS)).equals(profile));
                    phase = Phase.BASELINE;
                    setup.current = SetupStep.NONE;
                    SelectedState before = selected(driver, cluster, topic, group, partition, config);
                    check(before.start() == 0 && before.lso() == 3 && before.end() == 3 && before.committed() == 1
                        && "86400000".equals(before.retention()));
                    KafkaObservationSettings settings = new KafkaObservationSettings(true, "isolated-lab", source,
                        bootstrap, topic, group, cluster);
                    KafkaObservationService observer = new KafkaObservationService(settings, Clock.systemUTC(),
                        System::nanoTime, saslFactory(credentials.observer()));
                    try {
                        phase = Phase.OBSERVER;
                        var observed = observer.capture();
                        check(observed.logStartOffset() == 0 && observed.readCommittedEndOffset() == 3
                            && Long.valueOf(1).equals(observed.committedOffset()) && Long.valueOf(2).equals(observed.lag())
                            && "STABLE".equals(observed.groupState()) && "OBSERVED".equals(observed.commitState())
                            && observer.ownerThreadsCreated() == 1 && !observer.poisoned());
                    } finally { observer.close(); }
                    phase = Phase.DENIED_RPCS;
                    Map<String, Object> readProperties = properties(bootstrap, "acl_observer", credentials.observer());
                    Admin reader = Admin.create(readProperties);
                    try {
                        denied(Rpc.OTHER_TOPIC, () -> reader.describeTopics(Set.of(otherTopic)).allTopicNames().get(10, TimeUnit.SECONDS), TopicAuthorizationException.class);
                        denied(Rpc.OTHER_GROUP, () -> reader.describeConsumerGroups(Set.of(otherGroup)).all().get(10, TimeUnit.SECONDS), GroupAuthorizationException.class);
                        denied(Rpc.ALTER_CONFIG, () -> reader.incrementalAlterConfigs(Map.of(config, List.of(new AlterConfigOp(
                            new ConfigEntry("retention.ms", "60000"), AlterConfigOp.OpType.SET)))).all().get(10, TimeUnit.SECONDS), TopicAuthorizationException.class);
                        denied(Rpc.OFFSET_COMMIT, () -> reader.alterConsumerGroupOffsets(group, Map.of(partition, new OffsetAndMetadata(2)))
                            .all().get(10, TimeUnit.SECONDS), GroupAuthorizationException.class);
                        KafkaProducer<String, String> deniedProducer = new KafkaProducer<>(producerProperties(readProperties));
                        try {
                            denied(Rpc.PRODUCE, () -> deniedProducer.send(new ProducerRecord<>(topic, 0, "denied-synthetic", "value"))
                                .get(10, TimeUnit.SECONDS), TopicAuthorizationException.class);
                        } finally { deniedProducer.close(Duration.ofSeconds(2)); }
                    } finally { reader.close(Duration.ofSeconds(1)); }
                    phase = Phase.PRESERVATION;
                    check(before.equals(selected(driver, cluster, topic, group, partition, config)));
                    check(Set.copyOf(driver.describeAcls(AclBindingFilter.ANY).values().get(10, TimeUnit.SECONDS)).equals(profile));
                    phase = Phase.BAD_PASSWORD;
                    String secret = credentials.observer();
                    String wrong = (secret.charAt(0) == '0' ? "1" : "0") + secret.substring(1);
                    Admin unauthenticated = Admin.create(properties(bootstrap, "acl_observer", wrong));
                    try {
                        denied(Rpc.BAD_PASSWORD, () -> unauthenticated.describeCluster().clusterId().get(10, TimeUnit.SECONDS), SaslAuthenticationException.class);
                    } finally { unauthenticated.close(Duration.ofSeconds(1)); }
                    phase = Phase.CLOSE;
                } catch (Throwable error) {
                    if (phase == Phase.SETUP) { setup.record(error); }
                    throw error;
                } finally {
                    if (phase == Phase.SETUP) { setup.current = SetupStep.CONSUMER_CLOSE; }
                    fixture.close(Duration.ofSeconds(2));
                }
            } catch (Throwable error) {
                if (phase == Phase.SETUP) { setup.record(error); }
                throw error;
            } finally {
                if (phase == Phase.SETUP) { setup.current = SetupStep.DRIVER_CLOSE; }
                driver.close(Duration.ofSeconds(1));
            }
            phase = Phase.COMPLETE;
            System.out.println("{\"kind\":\"KAFKA_ACL_SELECTED_ASSERTIONS\",\"phase\":\"COMPLETE\",\"describeProfile\":true,\"deniedRpcs\":5,\"badPasswordRejected\":true,\"selectedStatePreserved\":true}");
        } catch (Throwable error) {
            if (phase == Phase.SETUP) { setup.record(error); }
            FailureKind kind = error instanceof AssertionError ? FailureKind.ASSERTION
                : error instanceof KafkaObservationService.ObservationFailure ? FailureKind.OBSERVATION
                : error instanceof InterruptedException ? FailureKind.INTERRUPTED : FailureKind.UNEXPECTED;
            if (error instanceof InterruptedException) { Thread.currentThread().interrupt(); }
            System.out.println("{\"kind\":\"KAFKA_ACL_SELECTED_ASSERTIONS\",\"phase\":\"" + phase.name()
                + "\",\"failureKind\":\"" + kind.name()
                + "\",\"setupStep\":\"" + setup.firstStep.name()
                + "\",\"setupCauseKind\":\"" + setup.firstCause.name() + "\"}");
            throw new AssertionError("KAFKA_ACL_FIXED_FAILURE_" + phase.name() + "_" + kind.name());
        }
    }

    private static SetupCause setupCause(Throwable error) {
        Throwable cause = error;
        for (int depth = 0; depth < 3; depth++) {
            boolean wrapper = cause instanceof ExecutionException
                || cause.getClass() == org.apache.kafka.common.KafkaException.class;
            if (!wrapper || cause.getCause() == null) { break; }
            cause = cause.getCause();
        }
        if (cause instanceof AssertionError) { return SetupCause.ASSERTION; }
        if (cause instanceof InterruptedException) { return SetupCause.INTERRUPTED; }
        if (cause instanceof java.util.concurrent.TimeoutException) { return SetupCause.TIMEOUT; }
        // Class names are compared only to fixed literals; no exception name or message is exported.
        return switch (cause.getClass().getName()) {
            case "org.apache.kafka.common.errors.GroupIdNotFoundException" -> SetupCause.GROUP_NOT_FOUND;
            case "org.apache.kafka.common.errors.CoordinatorNotAvailableException",
                 "org.apache.kafka.common.errors.CoordinatorLoadInProgressException",
                 "org.apache.kafka.common.errors.NotCoordinatorException" -> SetupCause.COORDINATOR;
            case "org.apache.kafka.common.errors.NotControllerException" -> SetupCause.NOT_CONTROLLER;
            case "org.apache.kafka.common.errors.AuthorizerNotReadyException" -> SetupCause.AUTHORIZER_NOT_READY;
            case "org.apache.kafka.common.errors.TopicAuthorizationException",
                 "org.apache.kafka.common.errors.GroupAuthorizationException",
                 "org.apache.kafka.common.errors.ClusterAuthorizationException" -> SetupCause.AUTHORIZATION;
            case "org.apache.kafka.common.errors.SaslAuthenticationException",
                 "org.apache.kafka.common.errors.UnsupportedSaslMechanismException" -> SetupCause.AUTHENTICATION;
            case "org.apache.kafka.common.config.ConfigException",
                 "org.apache.kafka.common.errors.InvalidConfigurationException",
                 "java.lang.IllegalArgumentException" -> SetupCause.CONFIGURATION;
            case "org.apache.kafka.common.errors.TimeoutException" -> SetupCause.TIMEOUT;
            default -> SetupCause.OTHER;
        };
    }

    private static SelectedState selected(Admin admin, String cluster, String topic, String group,
            TopicPartition partition, ConfigResource config) throws Exception {
        check(cluster.equals(admin.describeCluster().clusterId().get(10, TimeUnit.SECONDS)));
        var description = admin.describeTopics(Set.of(topic)).allTopicNames().get(10, TimeUnit.SECONDS).get(topic);
        var membership = admin.describeConsumerGroups(Set.of(group)).all().get(10, TimeUnit.SECONDS).get(group);
        check(description != null && !description.isInternal() && !Uuid.ZERO_UUID.equals(description.topicId())
            && description.partitions().size() == 1 && description.partitions().getFirst().partition() == 0);
        check(membership != null && membership.type() == GroupType.CLASSIC && membership.groupState() == GroupState.STABLE
            && !membership.isSimpleConsumerGroup() && membership.members().size() == 1);
        var member = membership.members().iterator().next();
        check(member.consumerId() != null && !member.consumerId().isBlank() && member.groupInstanceId() != null
            && member.assignment().topicPartitions().equals(Set.of(partition)));
        long start = admin.listOffsets(Map.of(partition, OffsetSpec.earliest())).all().get(10, TimeUnit.SECONDS).get(partition).offset();
        long end = admin.listOffsets(Map.of(partition, OffsetSpec.latest())).all().get(10, TimeUnit.SECONDS).get(partition).offset();
        long lso = admin.listOffsets(Map.of(partition, OffsetSpec.latest()), new ListOffsetsOptions(IsolationLevel.READ_COMMITTED))
            .all().get(10, TimeUnit.SECONDS).get(partition).offset();
        var offsets = admin.listConsumerGroupOffsets(group).partitionsToOffsetAndMetadata().get(10, TimeUnit.SECONDS);
        check(offsets.keySet().equals(Set.of(partition)) && offsets.get(partition) != null);
        String retention = admin.describeConfigs(Set.of(config)).all().get(10, TimeUnit.SECONDS).get(config).get("retention.ms").value();
        check(retention != null);
        return new SelectedState(cluster, description.topicId(), Set.of(0), membership.type(), membership.groupState(),
            membership.isSimpleConsumerGroup(), member.consumerId(), member.groupInstanceId().orElse(null),
            Set.copyOf(member.assignment().topicPartitions()), start, lso, end, offsets.get(partition).offset(), retention);
    }

    private static AclBinding describe(ResourceType type, String name) {
        return new AclBinding(new ResourcePattern(type, name, PatternType.LITERAL),
            new AccessControlEntry("User:acl_observer", "*", AclOperation.DESCRIBE, AclPermissionType.ALLOW));
    }

    private static Map<String, Object> properties(String bootstrap, String user, String password) {
        Map<String, Object> value = new LinkedHashMap<>();
        value.put("bootstrap.servers", bootstrap);
        value.put("security.protocol", "SASL_PLAINTEXT"); value.put("sasl.mechanism", "PLAIN");
        value.put("sasl.jaas.config", jaas(user, password));
        value.put("request.timeout.ms", 3000); value.put("default.api.timeout.ms", 10000); value.put("retries", 0);
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

    private static ReadOnlyKafkaAdmin.Factory saslFactory(String password) {
        return (settings, deadline, ownerGroup) -> {
            deadline.remainingNanos();
            ReadOnlyKafkaAdmin.KafkaAdminAdapter.verifyLibrary();
            deadline.remainingNanos();
            var values = new LinkedHashMap<>(ReadOnlyKafkaAdmin.KafkaAdminAdapter.properties(settings));
            values.put("security.protocol", "SASL_PLAINTEXT"); values.put("sasl.mechanism", "PLAIN");
            values.put("sasl.jaas.config", jaas("acl_observer", password));
            Admin admin;
            try { admin = Admin.create(values); }
            catch (Throwable constructorFailed) { throw failure(CLOSE_UNVERIFIED); }
            ReadOnlyKafkaAdmin.KafkaAdminAdapter adapter;
            try { adapter = new ReadOnlyKafkaAdmin.KafkaAdminAdapter(admin, settings, ownerGroup); }
            catch (Throwable referenceUnverified) {
                try { admin.close(Duration.ofMillis(500)); } catch (Throwable ignored) { }
                throw failure(CLOSE_UNVERIFIED);
            }
            try { deadline.remainingNanos(); return adapter; }
            catch (KafkaObservationService.ObservationFailure late) {
                boolean ended;
                try { ended = adapter.closeAndVerifyIoThread(Duration.ofSeconds(1)); }
                catch (Throwable unverified) { ended = false; }
                if (!ended) { throw failure(CLOSE_UNVERIFIED); }
                throw late;
            }
        };
    }

    private static Credentials credentials() throws Exception {
        Path file = Path.of("/owned/api/target/owned-acl-credentials.properties");
        check(Files.isRegularFile(file, LinkOption.NOFOLLOW_LINKS) && Files.size(file) > 0 && Files.size(file) <= 4096);
        byte[] raw = Files.readAllBytes(file);
        check(raw.length <= 4096);
        Properties values = new Properties();
        values.load(new ByteArrayInputStream(raw));
        check(values.stringPropertyNames().equals(Set.of("admin.username", "admin.password", "observer.username", "observer.password"))
            && "acl_admin".equals(values.getProperty("admin.username")) && "acl_observer".equals(values.getProperty("observer.username")));
        String admin = values.getProperty("admin.password"), observer = values.getProperty("observer.password");
        check(admin.matches("[a-f0-9]{64}") && observer.matches("[a-f0-9]{64}") && !admin.equals(observer));
        java.util.Arrays.fill(raw, (byte) 0);
        return new Credentials(admin, observer);
    }

    private static String jaas(String user, String password) {
        check(("acl_admin".equals(user) || "acl_observer".equals(user)) && password.matches("[a-f0-9]{64}"));
        return "org.apache.kafka.common.security.plain.PlainLoginModule required username=\"" + user + "\" password=\"" + password + "\";";
    }

    private static void denied(Rpc rpc, CheckedCall call, Class<? extends Throwable> expected) throws Exception {
        try { call.run(); }
        catch (Exception rejected) {
            if (rejected instanceof InterruptedException) { Thread.currentThread().interrupt(); }
            Throwable cause = rejected instanceof ExecutionException ? rejected.getCause() : rejected;
            CauseKind kind = causeKind(cause);
            boolean exact = rejected instanceof ExecutionException && cause != null && cause.getClass() == expected;
            rpcDiagnostic(rpc, exact ? "DENIED" : "WRONG_FAILURE", kind);
            check(exact);
            return;
        }
        rpcDiagnostic(rpc, "UNEXPECTED_SUCCESS", CauseKind.NONE);
        throw new AssertionError("EXPECTED_EXACT_DENIAL");
    }

    private static CauseKind causeKind(Throwable cause) {
        if (cause == null) { return CauseKind.OTHER; }
        if (cause.getClass() == TopicAuthorizationException.class) { return CauseKind.TOPIC_AUTH; }
        if (cause.getClass() == GroupAuthorizationException.class) { return CauseKind.GROUP_AUTH; }
        if (cause.getClass() == SaslAuthenticationException.class) { return CauseKind.SASL_AUTH; }
        if (cause instanceof java.util.concurrent.TimeoutException || cause instanceof org.apache.kafka.common.errors.TimeoutException) {
            return CauseKind.TIMEOUT;
        }
        return CauseKind.OTHER;
    }

    private static void rpcDiagnostic(Rpc rpc, String outcome, CauseKind kind) {
        check(rpc != null && kind != null && Set.of("DENIED", "WRONG_FAILURE", "UNEXPECTED_SUCCESS").contains(outcome));
        System.out.println("{\"kind\":\"KAFKA_ACL_RPC_ASSERTION\",\"rpc\":\"" + rpc.name()
            + "\",\"outcome\":\"" + outcome + "\",\"causeKind\":\"" + kind.name() + "\"}");
    }

    private static String required(String key) {
        String value = System.getenv(key); check(value != null && !value.isBlank()); return value;
    }

    private static void check(boolean value) { if (!value) { throw new AssertionError("KAFKA_ACL_FIXED_ASSERTION"); } }
}
