package io.github.devdooly.platformlab.jobs.observation;

import java.io.InputStream;
import java.security.MessageDigest;
import java.time.Duration;
import java.util.ArrayList;
import java.util.HexFormat;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;
import java.util.function.LongSupplier;
import org.apache.kafka.clients.admin.Admin;
import org.apache.kafka.clients.admin.AdminClientConfig;
import org.apache.kafka.clients.admin.ConsumerGroupDescription;
import org.apache.kafka.clients.admin.DescribeClusterOptions;
import org.apache.kafka.clients.admin.DescribeConsumerGroupsOptions;
import org.apache.kafka.clients.admin.DescribeTopicsOptions;
import org.apache.kafka.clients.admin.ListConsumerGroupOffsetsOptions;
import org.apache.kafka.clients.admin.ListConsumerGroupOffsetsSpec;
import org.apache.kafka.clients.admin.ListOffsetsOptions;
import org.apache.kafka.clients.admin.ListOffsetsResult;
import org.apache.kafka.clients.admin.OffsetSpec;
import org.apache.kafka.clients.admin.TopicDescription;
import org.apache.kafka.clients.consumer.OffsetAndMetadata;
import org.apache.kafka.common.GroupState;
import org.apache.kafka.common.GroupType;
import org.apache.kafka.common.IsolationLevel;
import org.apache.kafka.common.KafkaFuture;
import org.apache.kafka.common.TopicPartition;
import org.apache.kafka.common.Uuid;
import org.apache.kafka.common.errors.GroupIdNotFoundException;
import org.apache.kafka.common.utils.AppInfoParser;
import static io.github.devdooly.platformlab.jobs.observation.KafkaObservationService.Code.*;
import static io.github.devdooly.platformlab.jobs.observation.KafkaObservationService.failure;

/** No create/alter/delete/commit/subscribe methods cross this read-only boundary. */
interface ReadOnlyKafkaAdmin {
    record Member(String id, String instanceId, Set<TopicPartition> assignments) {
        public Member { assignments = Set.copyOf(assignments); }
    }
    record Group(String id, GroupType type, GroupState state, boolean simple, List<Member> members) {
        public Group { members = List.copyOf(members); }
    }
    record Target(String clusterId, String topic, Uuid topicId, Set<Integer> partitions, Group group) {
        public Target { partitions = Set.copyOf(partitions); }
    }
    record Offsets(long start, long readCommittedEnd, Long committed) {}

    Target identity(Deadline deadline);
    Offsets offsets(Deadline deadline);
    /** Only the source-pinned, captured Admin I/O platform thread is verified; not all JVM resources. */
    boolean closeAndVerifyIoThread(Duration budget);

    @FunctionalInterface interface Factory {
        ReadOnlyKafkaAdmin open(KafkaObservationSettings settings, Deadline deadline, ThreadGroup ownerGroup);
    }

    enum RpcStage { DESCRIBE_CLUSTER, DESCRIBE_TOPIC, DESCRIBE_GROUP, LIST_COMMITTED, LIST_START, LIST_END }

    static void rpcFailureDiagnostic(RpcStage stage, ExecutionException unavailable) {
        try {
            if (stage == null || !"true".equals(System.getProperty("lab.kafka-observation.tests"))) { return; }
            Throwable cause = unavailable.getCause();
            Class<?> type = cause == null ? null : cause.getClass();
            String fixed = "UNCLASSIFIED_EXECUTION_FAILURE";
            if (type == org.apache.kafka.common.errors.TimeoutException.class) { fixed = "RPC_TIMEOUT"; }
            else if (type == org.apache.kafka.common.errors.UnsupportedVersionException.class) { fixed = "UNSUPPORTED_RPC_VERSION"; }
            else if (type == org.apache.kafka.common.errors.UnknownTopicOrPartitionException.class) { fixed = "TARGET_TOPIC_UNAVAILABLE"; }
            else if (type == org.apache.kafka.common.errors.CoordinatorNotAvailableException.class) { fixed = "GROUP_COORDINATOR_UNAVAILABLE"; }
            else if (type == org.apache.kafka.common.errors.NotCoordinatorException.class) { fixed = "GROUP_COORDINATOR_CHANGED"; }
            else if (type == GroupIdNotFoundException.class) { fixed = "GROUP_ID_NOT_FOUND"; }
            else if (type == org.apache.kafka.common.errors.GroupAuthorizationException.class) { fixed = "GROUP_AUTHORIZATION_DENIED"; }
            else if (type == org.apache.kafka.common.errors.TopicAuthorizationException.class) { fixed = "TOPIC_AUTHORIZATION_DENIED"; }
            else if (type == org.apache.kafka.common.errors.ClusterAuthorizationException.class) { fixed = "CLUSTER_AUTHORIZATION_DENIED"; }
            else if (type == org.apache.kafka.common.errors.DisconnectException.class) { fixed = "RPC_DISCONNECTED"; }
            else if (type == org.apache.kafka.common.errors.NetworkException.class) { fixed = "RPC_NETWORK_UNAVAILABLE"; }
            System.out.println("{\"kind\":\"KAFKA_OBSERVER_RPC_DIAGNOSTIC\",\"stage\":\"" + stage.name()
                + "\",\"failureKind\":\"" + fixed + "\"}");
        } catch (RuntimeException ignored) { /* Diagnostics never replace the original fixed observer failure. */ }
    }

    record Deadline(long endNanos, LongSupplier clock) {
        long remainingNanos() {
            long remaining = endNanos - clock.getAsLong();
            if (remaining <= 0 || Thread.currentThread().isInterrupted()) { throw failure(CAPTURE_TIMEOUT); }
            return remaining;
        }
        int remainingMillis() {
            long nanos = remainingNanos();
            return (int) Math.min(Integer.MAX_VALUE, Math.max(1, (nanos + 999_999) / 1_000_000));
        }
        <T> T await(KafkaFuture<T> future) { return await(future, null); }
        <T> T await(KafkaFuture<T> future, RpcStage stage) {
            if (future == null) { throw failure(KAFKA_UNAVAILABLE); }
            try { return future.get(remainingNanos(), TimeUnit.NANOSECONDS); }
            catch (InterruptedException interrupted) { Thread.currentThread().interrupt(); throw failure(CAPTURE_TIMEOUT); }
            catch (TimeoutException timeout) { throw failure(CAPTURE_TIMEOUT); }
            catch (ExecutionException unavailable) {
                rpcFailureDiagnostic(stage, unavailable);
                if (unavailable.getCause() instanceof GroupIdNotFoundException) { throw failure(GROUP_UNAVAILABLE); }
                throw failure(KAFKA_UNAVAILABLE);
            }
        }
    }

    static Factory factory() {
        return (settings, deadline, ownerGroup) -> {
            deadline.remainingNanos();
            KafkaAdminAdapter.verifyLibrary();
            deadline.remainingNanos();
            // Admin.create includes synchronous DNS. The service's single owner/caller deadline contains it.
            Admin admin;
            try { admin = Admin.create(KafkaAdminAdapter.properties(settings)); }
            catch (Throwable constructorFailed) {
                // No returned client/reference means partial constructor cleanup is unverified.
                throw failure(CLOSE_UNVERIFIED);
            }
            KafkaAdminAdapter adapter;
            try { adapter = new KafkaAdminAdapter(admin, settings, ownerGroup); }
            catch (Throwable referenceUnverified) {
                // A returned client must not escape cleanup when ownership-reference discovery fails.
                try { admin.close(Duration.ofMillis(500)); }
                catch (Throwable ignored) { /* One attempt only; no verified I/O reference is available. */ }
                throw failure(CLOSE_UNVERIFIED);
            }
            try { deadline.remainingNanos(); return adapter; }
            catch (KafkaObservationService.ObservationFailure late) {
                // Never issue an RPC after a late constructor. This is one bounded cleanup attempt only.
                boolean ended;
                try { ended = adapter.closeAndVerifyIoThread(Duration.ofSeconds(1)); }
                catch (Throwable unverified) { ended = false; }
                if (!ended) { throw failure(CLOSE_UNVERIFIED); }
                throw late;
            }
        };
    }

    final class KafkaAdminAdapter implements ReadOnlyKafkaAdmin {
        static final String CLIENT_ID = "devdooly-kafka-observer";
        static final String IO_THREAD_NAME = "kafka-admin-client-thread | " + CLIENT_ID;
        private static final Map<String, String> CLASS_PINS = Map.of(
            "org/apache/kafka/clients/admin/KafkaAdminClient.class", "04075af560b37e4ed19603dcc5229ee2ec1c64e8a045c086a149f85ccc72aa0d",
            "org/apache/kafka/common/utils/KafkaThread.class", "bf8d68235a6e6508a5a1b54079f39c91cd103db81a056b851f7a9c7dd0fa3d6d",
            "org/apache/kafka/clients/admin/internals/ListConsumerGroupOffsetsHandler.class", "68ab0ea783042d1c4134382d69332f22c951dca90d2ad8f0a74d5ffe4bd92397",
            "org/apache/kafka/clients/admin/internals/ListOffsetsHandler.class", "5d31c6800562fe66517671e3ae6863f264c8c881e190c08e68e1af645d39bd03");
        private final Admin admin;
        private final KafkaObservationSettings settings;
        private final TopicPartition partition;
        private final Thread owner, ioThread;

        KafkaAdminAdapter(Admin admin, KafkaObservationSettings settings, ThreadGroup ownerGroup) {
            this.admin = admin; this.settings = settings;
            this.partition = new TopicPartition(settings.topic(), 0);
            this.owner = Thread.currentThread();
            this.ioThread = ownedIoThread(ownerGroup, owner);
        }

        static Map<String, Object> properties(KafkaObservationSettings settings) {
            var properties = new LinkedHashMap<String, Object>();
            properties.put(AdminClientConfig.BOOTSTRAP_SERVERS_CONFIG, settings.bootstrap());
            properties.put(AdminClientConfig.SECURITY_PROTOCOL_CONFIG, "PLAINTEXT");
            properties.put(AdminClientConfig.CLIENT_ID_CONFIG, CLIENT_ID);
            properties.put(AdminClientConfig.REQUEST_TIMEOUT_MS_CONFIG, 1000);
            properties.put(AdminClientConfig.DEFAULT_API_TIMEOUT_MS_CONFIG, 3000);
            properties.put(AdminClientConfig.RETRIES_CONFIG, 0);
            properties.put(AdminClientConfig.ENABLE_METRICS_PUSH_CONFIG, false);
            properties.put(AdminClientConfig.METRIC_REPORTER_CLASSES_CONFIG, List.of());
            return Map.copyOf(properties);
        }

        static void verifyLibrary() {
            try {
                if (!"4.2.1".equals(AppInfoParser.getVersion())) { throw failure(INVALID_CONFIGURATION); }
                for (var pin : CLASS_PINS.entrySet()) {
                    try (InputStream input = Admin.class.getResourceAsStream("/" + pin.getKey())) {
                        if (input == null) { throw failure(INVALID_CONFIGURATION); }
                        byte[] bytes = input.readNBytes(262_145);
                        if (bytes.length == 0 || bytes.length > 262_144 || !pin.getValue().equals(
                                HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(bytes)))) {
                            throw failure(INVALID_CONFIGURATION);
                        }
                    }
                }
            } catch (KafkaObservationService.ObservationFailure fixed) { throw fixed; }
            catch (Exception unavailable) { throw failure(INVALID_CONFIGURATION); }
        }

        @Override public Target identity(Deadline deadline) {
            requireOwner();
            String clusterId = deadline.await(admin.describeCluster(
                new DescribeClusterOptions().timeoutMs(deadline.remainingMillis())).clusterId(), RpcStage.DESCRIBE_CLUSTER);
            Map<String, TopicDescription> topicMap = deadline.await(admin.describeTopics(Set.of(settings.topic()),
                new DescribeTopicsOptions().timeoutMs(deadline.remainingMillis())).allTopicNames(), RpcStage.DESCRIBE_TOPIC);
            Map<String, ConsumerGroupDescription> groupMap = deadline.await(admin.describeConsumerGroups(Set.of(settings.group()),
                new DescribeConsumerGroupsOptions().timeoutMs(deadline.remainingMillis())).all(), RpcStage.DESCRIBE_GROUP);
            if (topicMap == null || !topicMap.keySet().equals(Set.of(settings.topic())) || topicMap.get(settings.topic()) == null) {
                throw failure(TARGET_UNVERIFIED);
            }
            if (groupMap == null || !groupMap.keySet().equals(Set.of(settings.group())) || groupMap.get(settings.group()) == null) {
                throw failure(GROUP_UNAVAILABLE);
            }
            TopicDescription topic = topicMap.get(settings.topic());
            ConsumerGroupDescription group = groupMap.get(settings.group());
            if (topic.isInternal() || topic.partitions() == null || topic.partitions().size() != 1) { throw failure(TARGET_UNVERIFIED); }
            var members = new ArrayList<Member>();
            if (group.members() == null || group.members().size() > 1) { throw failure(GROUP_UNSTABLE); }
            for (var member : group.members()) {
                if (member == null || member.consumerId() == null || member.groupInstanceId() == null
                        || member.assignment() == null || member.assignment().topicPartitions() == null) { throw failure(GROUP_UNSTABLE); }
                members.add(new Member(member.consumerId(), member.groupInstanceId().orElse(null), member.assignment().topicPartitions()));
            }
            return new Target(clusterId, topic.name(), topic.topicId(), Set.of(topic.partitions().getFirst().partition()),
                new Group(group.groupId(), group.type(), group.groupState(), group.isSimpleConsumerGroup(), members));
        }

        @Override public Offsets offsets(Deadline deadline) {
            requireOwner();
            Map<String, Map<TopicPartition, OffsetAndMetadata>> commitMap = deadline.await(admin.listConsumerGroupOffsets(
                Map.of(settings.group(), new ListConsumerGroupOffsetsSpec().topicPartitions(Set.of(partition))),
                new ListConsumerGroupOffsetsOptions().requireStable(true).timeoutMs(deadline.remainingMillis())).all(), RpcStage.LIST_COMMITTED);
            if (commitMap == null || !commitMap.keySet().equals(Set.of(settings.group()))) { throw failure(OFFSETS_UNVERIFIED); }
            Long offset = committedOffset(commitMap.get(settings.group()), partition);
            long start = exactOffset(deadline.await(admin.listOffsets(Map.of(partition, OffsetSpec.earliest()),
                new ListOffsetsOptions(IsolationLevel.READ_COMMITTED).timeoutMs(deadline.remainingMillis())).all(), RpcStage.LIST_START), partition);
            long end = exactOffset(deadline.await(admin.listOffsets(Map.of(partition, OffsetSpec.latest()),
                new ListOffsetsOptions(IsolationLevel.READ_COMMITTED).timeoutMs(deadline.remainingMillis())).all(), RpcStage.LIST_END), partition);
            return new Offsets(start, end, offset);
        }

        static Long committedOffset(Map<TopicPartition, OffsetAndMetadata> raw, TopicPartition expected) {
            // 4.2.1 represents NO_COMMIT as exact {tp:null}; a missing key may conceal a partition error.
            if (raw == null || !raw.keySet().equals(Set.of(expected))) { throw failure(OFFSETS_UNVERIFIED); }
            OffsetAndMetadata metadata = raw.get(expected);
            return metadata == null ? null : metadata.offset();
        }

        static long exactOffset(Map<TopicPartition, ListOffsetsResult.ListOffsetsResultInfo> raw, TopicPartition expected) {
            if (raw == null || !raw.keySet().equals(Set.of(expected)) || raw.get(expected) == null) { throw failure(OFFSETS_UNVERIFIED); }
            return raw.get(expected).offset();
        }

        private void requireOwner() {
            if (Thread.currentThread() != owner || ioThread == null) { throw failure(CLOSE_UNVERIFIED); }
        }

        static Thread ownedIoThread(ThreadGroup group, Thread owner) {
            if (group == null || owner.isVirtual() || owner.getThreadGroup() != group) { return null; }
            Thread[] threads = new Thread[16];
            int count = group.enumerate(threads, false);
            if (count >= threads.length) { return null; }
            Thread found = null;
            for (int index = 0; index < count; index++) {
                Thread thread = threads[index];
                if (thread == owner) { continue; }
                if (thread == null || found != null || thread.isVirtual() || !thread.isAlive()
                        || thread.getThreadGroup() != group || !IO_THREAD_NAME.equals(thread.getName())) { return null; }
                found = thread;
            }
            return found;
        }

        @Override public boolean closeAndVerifyIoThread(Duration budget) {
            if (Thread.currentThread() != owner || budget == null || budget.isNegative() || budget.toNanos() < 2_000_000) { return false; }
            long until = System.nanoTime() + Math.min(Duration.ofSeconds(1).toNanos(), budget.toNanos());
            // Positive whole milliseconds only: Kafka 4.2.1 join(0) could wait forever.
            long closeMillis = Math.max(1, Math.min(500, (until - System.nanoTime()) / 2_000_000));
            admin.close(Duration.ofMillis(closeMillis));
            if (ioThread == null || Thread.currentThread().isInterrupted()) { return false; }
            long remaining = until - System.nanoTime();
            if (remaining <= 0) { return false; }
            try {
                return ioThread.join(Duration.ofNanos(remaining)) && !ioThread.isAlive() && !Thread.currentThread().isInterrupted();
            } catch (InterruptedException interrupted) { Thread.currentThread().interrupt(); return false; }
        }
    }
}
