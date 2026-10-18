package io.github.devdooly.platformlab.jobs.observation;

import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.time.ZoneOffset;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.Set;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicLong;
import java.util.concurrent.atomic.AtomicReference;
import java.util.function.LongSupplier;
import org.apache.kafka.clients.admin.AdminClientConfig;
import org.apache.kafka.clients.admin.Admin;
import org.apache.kafka.clients.admin.ListConsumerGroupOffsetsOptions;
import org.apache.kafka.clients.admin.ListConsumerGroupOffsetsResult;
import org.apache.kafka.clients.admin.ListConsumerGroupOffsetsSpec;
import org.apache.kafka.clients.admin.ListOffsetsOptions;
import org.apache.kafka.clients.admin.ListOffsetsResult;
import org.apache.kafka.clients.admin.DescribeClusterResult;
import org.apache.kafka.clients.admin.DescribeTopicsResult;
import org.apache.kafka.clients.admin.DescribeConsumerGroupsResult;
import org.apache.kafka.clients.admin.ConsumerGroupDescription;
import org.apache.kafka.clients.admin.TopicDescription;
import org.apache.kafka.clients.admin.MemberDescription;
import org.apache.kafka.clients.admin.MemberAssignment;
import org.apache.kafka.clients.consumer.OffsetAndMetadata;
import org.apache.kafka.common.GroupState;
import org.apache.kafka.common.GroupType;
import org.apache.kafka.common.IsolationLevel;
import org.apache.kafka.common.KafkaFuture;
import org.apache.kafka.common.Node;
import org.apache.kafka.common.TopicPartitionInfo;
import org.apache.kafka.common.TopicPartition;
import org.apache.kafka.common.Uuid;
import org.apache.kafka.common.internals.KafkaFutureImpl;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.Test;
import tools.jackson.databind.JsonNode;
import tools.jackson.databind.json.JsonMapper;
import static io.github.devdooly.platformlab.jobs.observation.KafkaObservationService.Code.*;
import static org.assertj.core.api.Assertions.*;
import static org.mockito.Mockito.*;

class KafkaObservationServiceTest {
    static final String CLUSTER = new Uuid(1, 2).toString(), TOPIC = "private-synthetic-topic", GROUP = "private-worker-group";
    static final Instant NOW = Instant.parse("2026-10-18T00:00:00Z");
    static final Clock CLOCK = Clock.fixed(NOW, ZoneOffset.UTC);
    private final List<KafkaObservationService> services = new ArrayList<>();

    static KafkaObservationSettings settings(boolean enabled) {
        return new KafkaObservationSettings(enabled, "isolated-lab", "a".repeat(40), "127.0.0.1:19092", TOPIC, GROUP, CLUSTER);
    }
    static ReadOnlyKafkaAdmin.Target target() {
        var member = new ReadOnlyKafkaAdmin.Member("private-member", null, Set.of(new TopicPartition(TOPIC, 0)));
        return new ReadOnlyKafkaAdmin.Target(CLUSTER, TOPIC, new Uuid(3, 4), Set.of(0),
            new ReadOnlyKafkaAdmin.Group(GROUP, GroupType.CLASSIC, GroupState.STABLE, false, List.of(member)));
    }
    KafkaObservationService service(KafkaObservationSettings settings, Clock clock, LongSupplier monotonic, ReadOnlyKafkaAdmin.Factory factory) {
        var service = new KafkaObservationService(settings, clock, monotonic, factory); services.add(service); return service;
    }
    KafkaObservationService service(FakeAdmin fake) { return service(settings(true), CLOCK, System::nanoTime, (settings, deadline, group) -> fake); }
    static void rejected(KafkaObservationService service, KafkaObservationService.Code expected) {
        assertThatThrownBy(service::capture).isInstanceOfSatisfying(KafkaObservationService.ObservationFailure.class,
            failure -> { assertThat(failure.code()).isEqualTo(expected); assertThat(failure.getCause()).isNull(); assertThat(failure.getStackTrace()).isEmpty(); });
    }
    @AfterEach void closeOwners() { services.forEach(KafkaObservationService::close); }

    @Test void disabledAndInvalidSettingsStartNoOwnerAndCreateNoClient() {
        var opens = new AtomicInteger();
        var disabled = service(new KafkaObservationSettings(false, "local", "unknown", "", "", "", ""), CLOCK, System::nanoTime,
            (settings, deadline, group) -> { opens.incrementAndGet(); return new FakeAdmin(); });
        rejected(disabled, NOT_CONFIGURED); assertThat(opens).hasValue(0); assertThat(disabled.ownerThreadsCreated()).isZero();
        for (String bootstrap : List.of("localhost:9092", "192.0.2.1:9092", "127.0.0.1:0", "127.0.0.1:65536", "http://127.0.0.1:9092", "127.0.0.1:9092,127.0.0.1:9093")) {
            var invalid = service(new KafkaObservationSettings(true, "isolated-lab", "a".repeat(40), bootstrap, TOPIC, GROUP, CLUSTER),
                CLOCK, System::nanoTime, (settings, deadline, group) -> { opens.incrementAndGet(); return new FakeAdmin(); });
            rejected(invalid, INVALID_CONFIGURATION); assertThat(invalid.ownerThreadsCreated()).isZero();
        }
        var invalidSource = service(new KafkaObservationSettings(true, "mini-pc", "unknown", "127.0.0.1:19092", TOPIC, GROUP, CLUSTER),
            CLOCK, System::nanoTime, (settings, deadline, group) -> { opens.incrementAndGet(); return new FakeAdmin(); });
        rejected(invalidSource, INVALID_CONFIGURATION); assertThat(opens).hasValue(0);
    }

    @Test void successfulResponseHasExactEighteenFieldsAndNoPrivateIdentity() throws Exception {
        var fake = new FakeAdmin(); fake.offsets = new ReadOnlyKafkaAdmin.Offsets(0, 7, 3L);
        var observer = service(fake); var result = observer.capture();
        assertThat(result.lag()).isEqualTo(4L); assertThat(result.committedOffset()).isEqualTo(3L);
        assertThat(result.environment()).isEqualTo("ISOLATED_LAB"); assertThat(result.scope()).isEqualTo("ISOLATED_KAFKA");
        assertThat(result.captureStartedAt()).isEqualTo(NOW); assertThat(result.capturedAt()).isEqualTo(NOW);
        assertThat(result.consistency()).isEqualTo("BOUNDED_SEQUENTIAL_READ"); assertThat(result.publicExecutionEnabled()).isFalse();
        var json = JsonMapper.builder().findAndAddModules().build();
        JsonNode value = json.valueToTree(result);
        Set<String> fields = new java.util.HashSet<>(); value.propertyNames().forEach(fields::add);
        assertThat(fields).containsExactlyInAnyOrder("schemaVersion", "kind", "synthetic", "environment", "scope", "publicExecutionEnabled",
            "sourceCommit", "captureStartedAt", "capturedAt", "consistency", "targetFingerprint", "groupState", "partition", "commitState",
            "logStartOffset", "readCommittedEndOffset", "committedOffset", "lag");
        assertThat(json.writeValueAsString(result)).doesNotContain(CLUSTER, TOPIC, GROUP, "private-member", "127.0.0.1", "bootstrap", "password");
        assertThat(fake.identities).hasValue(2); assertThat(fake.offsetReads).hasValue(1); assertThat(fake.closes).hasValue(1);
        assertThat(observer.ownerThreadsCreated()).isEqualTo(1); assertThat(observer.poisoned()).isFalse();
        observer.capture(); assertThat(observer.ownerThreadsCreated()).isEqualTo(1);
    }

    @Test void noCommitStaysNullEvenWhenEndIsZeroAndActualCommittedZeroIsDifferent() {
        var fake = new FakeAdmin(); fake.offsets = new ReadOnlyKafkaAdmin.Offsets(0, 0, null);
        var observer = service(fake); var missing = observer.capture();
        assertThat(missing.commitState()).isEqualTo("NO_COMMIT"); assertThat(missing.committedOffset()).isNull(); assertThat(missing.lag()).isNull();
        fake.offsets = new ReadOnlyKafkaAdmin.Offsets(0, 0, 0L); var zero = observer.capture();
        assertThat(zero.commitState()).isEqualTo("OBSERVED"); assertThat(zero.committedOffset()).isZero(); assertThat(zero.lag()).isZero();
    }

    @Test void emptyClassicGroupIsValidButWrongTypeStateAssignmentOrMemberCountIsNot() {
        var empty = new FakeAdmin(); empty.before = new ReadOnlyKafkaAdmin.Target(CLUSTER, TOPIC, new Uuid(3, 4), Set.of(0),
            new ReadOnlyKafkaAdmin.Group(GROUP, GroupType.CLASSIC, GroupState.EMPTY, false, List.of())); empty.after = empty.before;
        assertThat(service(empty).capture().groupState()).isEqualTo("EMPTY");
        var valid = target();
        var wrongGroups = List.of(
            new ReadOnlyKafkaAdmin.Group(GROUP, GroupType.CONSUMER, GroupState.STABLE, false, valid.group().members()),
            new ReadOnlyKafkaAdmin.Group(GROUP, GroupType.CLASSIC, GroupState.PREPARING_REBALANCE, false, List.of()),
            new ReadOnlyKafkaAdmin.Group(GROUP, GroupType.CLASSIC, GroupState.EMPTY, false, valid.group().members()),
            new ReadOnlyKafkaAdmin.Group(GROUP, GroupType.CLASSIC, GroupState.STABLE, false, List.of()),
            new ReadOnlyKafkaAdmin.Group(GROUP, GroupType.CLASSIC, GroupState.STABLE, true, valid.group().members()),
            new ReadOnlyKafkaAdmin.Group(GROUP, GroupType.CLASSIC, GroupState.STABLE, false,
                List.of(new ReadOnlyKafkaAdmin.Member("member", null, Set.of(new TopicPartition("another-private-topic", 0))))));
        for (var group : wrongGroups) {
            var fake = new FakeAdmin(); fake.before = new ReadOnlyKafkaAdmin.Target(CLUSTER, TOPIC, valid.topicId(), Set.of(0), group);
            rejected(service(fake), GROUP_UNSTABLE); assertThat(fake.offsetReads).hasValue(0); assertThat(fake.closes).hasValue(1);
        }
    }

    @Test void wrongClusterTopicUuidPartitionOrGroupCannotProduceOffsets() {
        var valid = target();
        for (var bad : List.of(
                new ReadOnlyKafkaAdmin.Target(new Uuid(8, 9).toString(), TOPIC, valid.topicId(), Set.of(0), valid.group()),
                new ReadOnlyKafkaAdmin.Target(CLUSTER, "other-topic", valid.topicId(), Set.of(0), valid.group()),
                new ReadOnlyKafkaAdmin.Target(CLUSTER, TOPIC, Uuid.ZERO_UUID, Set.of(0), valid.group()),
                new ReadOnlyKafkaAdmin.Target(CLUSTER, TOPIC, valid.topicId(), Set.of(0, 1), valid.group()))) {
            var fake = new FakeAdmin(); fake.before = bad; rejected(service(fake), TARGET_UNVERIFIED);
            assertThat(fake.offsetReads).hasValue(0); assertThat(fake.closes).hasValue(1);
        }
        var wrongGroup = new FakeAdmin(); wrongGroup.before = new ReadOnlyKafkaAdmin.Target(CLUSTER, TOPIC, valid.topicId(), Set.of(0),
            new ReadOnlyKafkaAdmin.Group("other-group", GroupType.CLASSIC, GroupState.EMPTY, false, List.of()));
        rejected(service(wrongGroup), GROUP_UNAVAILABLE);
    }

    @Test void explicitTopicUuidAndMembershipMustStayEqualAcrossTheReadWindow() {
        var fake = new FakeAdmin(); var original = target();
        fake.after = new ReadOnlyKafkaAdmin.Target(CLUSTER, TOPIC, new Uuid(7, 8), Set.of(0), original.group());
        rejected(service(fake), TARGET_UNVERIFIED); assertThat(fake.closes).hasValue(1);
        var changed = new FakeAdmin(); changed.after = new ReadOnlyKafkaAdmin.Target(CLUSTER, TOPIC, original.topicId(), Set.of(0),
            new ReadOnlyKafkaAdmin.Group(GROUP, GroupType.CLASSIC, GroupState.STABLE, false,
                List.of(new ReadOnlyKafkaAdmin.Member("new-private-member", null, Set.of(new TopicPartition(TOPIC, 0))))));
        rejected(service(changed), TARGET_UNVERIFIED);
    }

    @Test void invalidOffsetRangesAndUnsafeIntegersFailWithoutClampingOrZeroFallback() {
        for (var offsets : List.of(new ReadOnlyKafkaAdmin.Offsets(-1, 0, null), new ReadOnlyKafkaAdmin.Offsets(4, 3, null),
                new ReadOnlyKafkaAdmin.Offsets(4, 7, 3L), new ReadOnlyKafkaAdmin.Offsets(0, 7, 8L),
                new ReadOnlyKafkaAdmin.Offsets(0, 7, -1L), new ReadOnlyKafkaAdmin.Offsets(0, KafkaObservationService.MAX_OFFSET + 1, null))) {
            var fake = new FakeAdmin(); fake.offsets = offsets; rejected(service(fake), OFFSETS_UNVERIFIED); assertThat(fake.closes).hasValue(1);
        }
    }

    @Test void exactRawNullIsNoCommitButEmptyExtraAndMissingPartitionResponsesFail() {
        var tp = new TopicPartition(TOPIC, 0); var none = new HashMap<TopicPartition, OffsetAndMetadata>(); none.put(tp, null);
        assertThat(ReadOnlyKafkaAdmin.KafkaAdminAdapter.committedOffset(none, tp)).isNull();
        assertThat(ReadOnlyKafkaAdmin.KafkaAdminAdapter.committedOffset(Map.of(tp, new OffsetAndMetadata(0)), tp)).isZero();
        for (Map<TopicPartition, OffsetAndMetadata> invalid : List.<Map<TopicPartition, OffsetAndMetadata>>of(Map.of(),
                Map.of(new TopicPartition(TOPIC, 1), new OffsetAndMetadata(0)),
                Map.of(tp, new OffsetAndMetadata(0), new TopicPartition(TOPIC, 1), new OffsetAndMetadata(0)))) {
            assertThatThrownBy(() -> ReadOnlyKafkaAdmin.KafkaAdminAdapter.committedOffset(invalid, tp))
                .isInstanceOfSatisfying(KafkaObservationService.ObservationFailure.class, failure -> assertThat(failure.code()).isEqualTo(OFFSETS_UNVERIFIED));
        }
        assertThatThrownBy(() -> ReadOnlyKafkaAdmin.KafkaAdminAdapter.exactOffset(Map.of(), tp)).isInstanceOf(KafkaObservationService.ObservationFailure.class);
    }

    @Test void pendingSingleFlightRejectsAnotherCaptureWithoutCreatingAnotherClient() throws Exception {
        var entered = new CountDownLatch(1); var release = new CountDownLatch(1); var opens = new AtomicInteger(); var fake = new FakeAdmin();
        var observer = service(settings(true), CLOCK, System::nanoTime, (settings, deadline, group) -> {
            opens.incrementAndGet(); entered.countDown(); await(release); return fake;
        });
        var first = CompletableFuture.supplyAsync(observer::capture);
        try { assertThat(entered.await(2, TimeUnit.SECONDS)).isTrue(); rejected(observer, CAPTURE_BUSY); assertThat(opens).hasValue(1); }
        finally { release.countDown(); }
        assertThat(first.get(2, TimeUnit.SECONDS).lag()).isZero(); assertThat(fake.closes).hasValue(1);
    }

    @Test void lateConstructorMakesNoRpcAndPoisonPreventsFutureClientCreation() {
        var nanos = new AtomicLong(); var fake = new FakeAdmin(); var opens = new AtomicInteger();
        var observer = service(settings(true), CLOCK, nanos::get, (settings, deadline, group) -> {
            opens.incrementAndGet(); nanos.set(Duration.ofSeconds(3).toNanos()); return fake;
        });
        rejected(observer, CAPTURE_TIMEOUT); assertThat(fake.identities).hasValue(0); assertThat(fake.offsetReads).hasValue(0);
        assertThat(fake.closes).hasValue(1); assertThat(observer.poisoned()).isTrue();
        rejected(observer, OBSERVER_POISONED); assertThat(opens).hasValue(1);
    }

    @Test void outerDeadlineQuarantinesUninterruptibleCreationAndDiscardsLateResult() throws Exception {
        var entered = new CountDownLatch(1); var release = new CountDownLatch(1); var cleaned = new CountDownLatch(1);
        var calls = new AtomicInteger(); var clockReads = new AtomicInteger(); var fake = new FakeAdmin() {
            @Override public boolean closeAndVerifyIoThread(Duration budget) { boolean result = super.closeAndVerifyIoThread(budget); cleaned.countDown(); return result; }
        };
        LongSupplier monotonic = () -> {
            if (!Thread.currentThread().getName().equals("platform-lab-kafka-observation-owner") && clockReads.incrementAndGet() > 1) {
                await(entered); return Duration.ofSeconds(4).toNanos();
            }
            return 0;
        };
        var observer = service(settings(true), CLOCK, monotonic, (settings, deadline, group) -> {
            calls.incrementAndGet(); entered.countDown();
            boolean interrupted = false;
            while (true) { try { release.await(); break; } catch (InterruptedException ignored) { interrupted = true; } }
            if (interrupted) { Thread.currentThread().interrupt(); }
            return fake;
        });
        try { rejected(observer, CAPTURE_TIMEOUT); rejected(observer, OBSERVER_POISONED); assertThat(calls).hasValue(1); }
        finally { release.countDown(); }
        assertThat(cleaned.await(2, TimeUnit.SECONDS)).isTrue(); assertThat(fake.identities).hasValue(0);
    }

    @Test void unverifiedCloseNeverPublishesSuccessOrCreatesAReplacementClient() {
        var fake = new FakeAdmin(); fake.closeVerified = false; var opens = new AtomicInteger();
        var observer = service(settings(true), CLOCK, System::nanoTime, (settings, deadline, group) -> { opens.incrementAndGet(); return fake; });
        rejected(observer, CLOSE_UNVERIFIED); rejected(observer, OBSERVER_POISONED); assertThat(opens).hasValue(1);
        assertThat(fake.closes).hasValue(1);
    }

    @Test void failedProviderExceptionHasOnlyFixedCodeAndNoRawCause() {
        var fake = new FakeAdmin() { @Override public Target identity(Deadline deadline) { throw new IllegalStateException("PRIVATE_KAFKA_CANARY endpoint/password"); } };
        var observer = service(fake);
        assertThatThrownBy(observer::capture).isInstanceOfSatisfying(KafkaObservationService.ObservationFailure.class, failure -> {
            assertThat(failure.code()).isEqualTo(KAFKA_UNAVAILABLE); assertThat(failure.getMessage()).isEqualTo("KAFKA_UNAVAILABLE");
            assertThat(failure.getCause()).isNull(); assertThat(failure.getStackTrace()).isEmpty(); assertThat(failure.getSuppressed()).isEmpty();
        });
        assertThat(fake.closes).hasValue(1);
    }

    @Test void reversedOrOverlongWallClockWindowFailsAndFingerprintChangesWithTarget() {
        var instants = new AtomicInteger();
        Clock reversed = new Clock() {
            @Override public java.time.ZoneId getZone() { return ZoneOffset.UTC; }
            @Override public Clock withZone(java.time.ZoneId zone) { return this; }
            @Override public Instant instant() { return instants.getAndIncrement() == 0 ? NOW : NOW.minusNanos(1); }
        };
        var fake = new FakeAdmin(); rejected(service(settings(true), reversed, System::nanoTime, (settings, deadline, group) -> fake), CLOCK_UNVERIFIED);
        var forwardReads = new AtomicInteger();
        Clock overlong = new Clock() {
            @Override public java.time.ZoneId getZone() { return ZoneOffset.UTC; }
            @Override public Clock withZone(java.time.ZoneId zone) { return this; }
            @Override public Instant instant() { return forwardReads.getAndIncrement() == 0 ? NOW : NOW.plusSeconds(4).plusNanos(1); }
        };
        rejected(service(settings(true), overlong, System::nanoTime, (settings, deadline, group) -> new FakeAdmin()), CLOCK_UNVERIFIED);
        var current = target(); var newUuid = new ReadOnlyKafkaAdmin.Target(CLUSTER, TOPIC, new Uuid(9, 10), Set.of(0), current.group());
        String fingerprint = KafkaObservationService.targetFingerprint(current, GROUP);
        assertThat(fingerprint).matches("[a-f0-9]{64}");
        assertThat(fingerprint).isNotEqualTo(KafkaObservationService.targetFingerprint(newUuid, GROUP));
        assertThat(fingerprint).isNotEqualTo(KafkaObservationService.targetFingerprint(current, "other-group"));
    }

    @Test void exactPinnedClientAndAdminPropertiesDisableReportersMetricsPushAndBoundRetries() {
        assertThatCode(ReadOnlyKafkaAdmin.KafkaAdminAdapter::verifyLibrary).doesNotThrowAnyException();
        var values = ReadOnlyKafkaAdmin.KafkaAdminAdapter.properties(settings(true));
        assertThat(values).containsEntry(AdminClientConfig.ENABLE_METRICS_PUSH_CONFIG, false)
            .containsEntry(AdminClientConfig.METRIC_REPORTER_CLASSES_CONFIG, List.of()).containsEntry(AdminClientConfig.RETRIES_CONFIG, 1)
            .containsEntry(AdminClientConfig.CLIENT_ID_CONFIG, ReadOnlyKafkaAdmin.KafkaAdminAdapter.CLIENT_ID);
        assertThat(values.keySet()).doesNotContain("group.id", "key.serializer", "value.serializer", "sasl.jaas.config");
        assertThatCode(() -> new AdminClientConfig(values)).doesNotThrowAnyException();
        assertThat(new ReadOnlyKafkaAdmin.Deadline(0, () -> 0).endNanos()).isZero();
        assertThatThrownBy(() -> new ReadOnlyKafkaAdmin.Deadline(0, () -> 0).remainingMillis()).isInstanceOf(KafkaObservationService.ObservationFailure.class);
    }

    @Test void realAdapterUsesExactPartitionRequireStableAndReadCommittedWithoutConsumerOperations() throws Exception {
        Admin admin = mock(Admin.class);
        inOwnedGroup(() -> {
            var release = new CountDownLatch(1); Thread io = startIo(Thread.currentThread().getThreadGroup(), ReadOnlyKafkaAdmin.KafkaAdminAdapter.IO_THREAD_NAME, release);
            var tp = new TopicPartition(TOPIC, 0);
            var committed = mock(ListConsumerGroupOffsetsResult.class);
            when(committed.all()).thenReturn(KafkaFuture.completedFuture(Map.of(GROUP, Map.of(tp, new OffsetAndMetadata(1)))));
            when(admin.listConsumerGroupOffsets(anyMap(), any(ListConsumerGroupOffsetsOptions.class))).thenAnswer(call -> {
                Map<String, ListConsumerGroupOffsetsSpec> groups = call.getArgument(0);
                assertThat(groups.keySet()).containsExactly(GROUP); assertThat(groups.get(GROUP).topicPartitions()).containsExactly(tp);
                ListConsumerGroupOffsetsOptions options = call.getArgument(1); assertThat(options.requireStable()).isTrue();
                return committed;
            });
            var reads = new AtomicInteger();
            when(admin.listOffsets(anyMap(), any(ListOffsetsOptions.class))).thenAnswer(call -> {
                Map<TopicPartition, ?> partitions = call.getArgument(0); assertThat(partitions.keySet()).containsExactly(tp);
                ListOffsetsOptions options = call.getArgument(1); assertThat(options.isolationLevel()).isEqualTo(IsolationLevel.READ_COMMITTED);
                long offset = reads.getAndIncrement() == 0 ? 0 : 3;
                return new ListOffsetsResult(Map.of(tp, KafkaFuture.completedFuture(new ListOffsetsResult.ListOffsetsResultInfo(offset, -1, Optional.empty()))));
            });
            doAnswer(call -> { assertThat(((Duration) call.getArgument(0)).toMillis()).isBetween(1L, 500L); release.countDown(); return null; }).when(admin).close(any(Duration.class));
            var adapter = new ReadOnlyKafkaAdmin.KafkaAdminAdapter(admin, settings(true), Thread.currentThread().getThreadGroup());
            try {
                var offsets = adapter.offsets(new ReadOnlyKafkaAdmin.Deadline(System.nanoTime() + Duration.ofSeconds(3).toNanos(), System::nanoTime));
                assertThat(offsets).isEqualTo(new ReadOnlyKafkaAdmin.Offsets(0, 3, 1L));
                assertThat(adapter.closeAndVerifyIoThread(Duration.ofSeconds(1))).isTrue(); assertThat(io.isAlive()).isFalse();
                verify(admin).listConsumerGroupOffsets(anyMap(), any(ListConsumerGroupOffsetsOptions.class));
                verify(admin, times(2)).listOffsets(anyMap(), any(ListOffsetsOptions.class)); verify(admin).close(any(Duration.class));
                verifyNoMoreInteractions(admin);
            } finally { release.countDown(); io.join(Duration.ofSeconds(1)); }
        });
    }

    @Test void voidCloseReturningWhileTheOwnedIoThreadLivesIsUnverified() throws Exception {
        Admin admin = mock(Admin.class);
        inOwnedGroup(() -> {
            var release = new CountDownLatch(1); Thread io = startIo(Thread.currentThread().getThreadGroup(), ReadOnlyKafkaAdmin.KafkaAdminAdapter.IO_THREAD_NAME, release);
            var adapter = new ReadOnlyKafkaAdmin.KafkaAdminAdapter(admin, settings(true), Thread.currentThread().getThreadGroup());
            try {
                assertThat(adapter.closeAndVerifyIoThread(Duration.ofMillis(20))).isFalse(); assertThat(io.isAlive()).isTrue();
                verify(admin).close(argThat(duration -> duration.toMillis() >= 1));
            } finally { release.countDown(); assertThat(io.join(Duration.ofSeconds(1))).isTrue(); }
        });
    }

    @Test void eachNextRemoteReadWaitsForThePreviousFutureToComplete() throws Exception {
        Admin admin = mock(Admin.class);
        var clusterWait = new CountDownLatch(1); var topicWait = new CountDownLatch(1);
        var commitWait = new CountDownLatch(1); var startWait = new CountDownLatch(1);
        var clusterFuture = new TrackingFuture<String>(clusterWait);
        var topicFuture = new TrackingFuture<Map<String, org.apache.kafka.clients.admin.TopicDescription>>(topicWait);
        var commitFuture = new TrackingFuture<Map<String, Map<TopicPartition, OffsetAndMetadata>>>(commitWait);
        var startFuture = new TrackingFuture<Map<TopicPartition, ListOffsetsResult.ListOffsetsResultInfo>>(startWait);
        var tp = new TopicPartition(TOPIC, 0);
        var clusterResult = mock(DescribeClusterResult.class); when(clusterResult.clusterId()).thenReturn(clusterFuture);
        when(admin.describeCluster(any(org.apache.kafka.clients.admin.DescribeClusterOptions.class))).thenReturn(clusterResult);
        var topicResult = mock(DescribeTopicsResult.class); when(topicResult.allTopicNames()).thenReturn(topicFuture);
        when(admin.describeTopics(anyCollection(), any(org.apache.kafka.clients.admin.DescribeTopicsOptions.class))).thenReturn(topicResult);
        var member = new MemberDescription("private-member", Optional.empty(), "private-client", "private-host", new MemberAssignment(Set.of(tp)));
        var description = new ConsumerGroupDescription(GROUP, false, List.of(member), "range", GroupType.CLASSIC, GroupState.STABLE,
            Node.noNode(), Set.of(), Optional.empty(), Optional.empty());
        when(admin.describeConsumerGroups(anyCollection(), any(org.apache.kafka.clients.admin.DescribeConsumerGroupsOptions.class)))
            .thenReturn(new DescribeConsumerGroupsResult(Map.of(GROUP, KafkaFuture.completedFuture(description))));
        var commitResult = mock(ListConsumerGroupOffsetsResult.class); when(commitResult.all()).thenReturn(commitFuture);
        when(admin.listConsumerGroupOffsets(anyMap(), any(ListConsumerGroupOffsetsOptions.class))).thenReturn(commitResult);
        var startResult = mock(ListOffsetsResult.class); when(startResult.all()).thenReturn(startFuture);
        var endResult = new ListOffsetsResult(Map.of(tp, KafkaFuture.completedFuture(new ListOffsetsResult.ListOffsetsResultInfo(3, -1, Optional.empty()))));
        var offsetCalls = new AtomicInteger();
        when(admin.listOffsets(anyMap(), any(ListOffsetsOptions.class))).thenAnswer(call -> offsetCalls.incrementAndGet() == 1 ? startResult : endResult);
        var partitionInfo = new TopicPartitionInfo(0, Node.noNode(), List.of(), List.of());
        var topicMap = Map.of(TOPIC, new TopicDescription(TOPIC, false, List.of(partitionInfo), Set.of(), new Uuid(3, 4)));
        var commitMap = Map.of(GROUP, Map.of(tp, new OffsetAndMetadata(1)));
        var startMap = Map.of(tp, new ListOffsetsResult.ListOffsetsResultInfo(0, -1, Optional.empty()));
        var running = CompletableFuture.runAsync(() -> {
            try {
                inOwnedGroup(() -> {
                    var release = new CountDownLatch(1);
                    Thread io = startIo(Thread.currentThread().getThreadGroup(), ReadOnlyKafkaAdmin.KafkaAdminAdapter.IO_THREAD_NAME, release);
                    doAnswer(call -> { release.countDown(); return null; }).when(admin).close(any(Duration.class));
                    var adapter = new ReadOnlyKafkaAdmin.KafkaAdminAdapter(admin, settings(true), Thread.currentThread().getThreadGroup());
                    try {
                        // Generous fixture clock only. The production service still owns its unchanged 3s/4s budgets.
                        var deadline = new ReadOnlyKafkaAdmin.Deadline(System.nanoTime() + Duration.ofSeconds(10).toNanos(), System::nanoTime);
                        assertThat(adapter.identity(deadline).topicId()).isEqualTo(new Uuid(3, 4));
                        assertThat(adapter.offsets(deadline)).isEqualTo(new ReadOnlyKafkaAdmin.Offsets(0, 3, 1L));
                        assertThat(adapter.closeAndVerifyIoThread(Duration.ofSeconds(1))).isTrue();
                    } finally { release.countDown(); io.join(Duration.ofSeconds(1)); }
                });
            } catch (Exception failure) { throw new java.util.concurrent.CompletionException(failure); }
        });
        try {
            assertThat(clusterWait.await(2, TimeUnit.SECONDS)).isTrue();
            verify(admin, never()).describeTopics(anyCollection(), any(org.apache.kafka.clients.admin.DescribeTopicsOptions.class));
            verify(admin, never()).describeConsumerGroups(anyCollection(), any(org.apache.kafka.clients.admin.DescribeConsumerGroupsOptions.class));
            clusterFuture.complete(CLUSTER);
            assertThat(topicWait.await(2, TimeUnit.SECONDS)).isTrue();
            verify(admin, never()).describeConsumerGroups(anyCollection(), any(org.apache.kafka.clients.admin.DescribeConsumerGroupsOptions.class));
            topicFuture.complete(topicMap);
            assertThat(commitWait.await(2, TimeUnit.SECONDS)).isTrue();
            verify(admin, never()).listOffsets(anyMap(), any(ListOffsetsOptions.class));
            commitFuture.complete(commitMap);
            assertThat(startWait.await(2, TimeUnit.SECONDS)).isTrue(); assertThat(offsetCalls).hasValue(1);
            startFuture.complete(startMap);
            running.get(3, TimeUnit.SECONDS); assertThat(offsetCalls).hasValue(2);
        } finally {
            clusterFuture.complete(CLUSTER); topicFuture.complete(topicMap); commitFuture.complete(commitMap); startFuture.complete(startMap);
            running.handle((ignored, failure) -> null).get(3, TimeUnit.SECONDS);
        }
    }

    @Test void wrongNameAndAdditionalChildrenCannotBeClaimedAsTheOwnedAdminIoThread() throws Exception {
        inOwnedGroup(() -> {
            ThreadGroup group = Thread.currentThread().getThreadGroup(); var release = new CountDownLatch(1);
            Thread wrong = startIo(group, "other-thread", release);
            try { assertThat(ReadOnlyKafkaAdmin.KafkaAdminAdapter.ownedIoThread(group, Thread.currentThread())).isNull(); }
            finally { release.countDown(); wrong.join(Duration.ofSeconds(1)); }
            var releaseMore = new CountDownLatch(1); Thread exact = startIo(group, ReadOnlyKafkaAdmin.KafkaAdminAdapter.IO_THREAD_NAME, releaseMore);
            Thread extra = startIo(group, "unverified-extra-child", releaseMore);
            try { assertThat(ReadOnlyKafkaAdmin.KafkaAdminAdapter.ownedIoThread(group, Thread.currentThread())).isNull(); }
            finally { releaseMore.countDown(); exact.join(Duration.ofSeconds(1)); extra.join(Duration.ofSeconds(1)); }
        });
    }

    static Thread startIo(ThreadGroup group, String name, CountDownLatch release) {
        var started = new CountDownLatch(1);
        Thread thread = new Thread(group, () -> {
            started.countDown();
            try { if (!release.await(10, TimeUnit.SECONDS)) { throw new AssertionError("Owned I/O test thread timed out"); } }
            catch (InterruptedException interrupted) { Thread.currentThread().interrupt(); }
        }, name); thread.setDaemon(true); thread.start(); await(started); return thread;
    }
    @FunctionalInterface interface OwnedAction { void run() throws Exception; }
    @Test void rpcDiagnosticRequiresExactExplicitTestFlagAndKeepsFixedFailure() {
        String property = "lab.kafka-observation.tests", previous = System.getProperty(property);
        java.io.PrintStream original = System.out;
        var bytes = new java.io.ByteArrayOutputStream();
        try (var output = new java.io.PrintStream(bytes, true, java.nio.charset.StandardCharsets.UTF_8)) {
            System.setOut(output);
            for (String value : new String[] {null, "false", "TRUE", " true"}) {
                if (value == null) { System.clearProperty(property); } else { System.setProperty(property, value); }
                bytes.reset();
                failingDiagnosticRpc(new org.apache.kafka.common.errors.TimeoutException("PRIVATE_RPC_CANARY endpoint/password"),
                    ReadOnlyKafkaAdmin.RpcStage.DESCRIBE_CLUSTER, KAFKA_UNAVAILABLE);
                assertThat(bytes.toString(java.nio.charset.StandardCharsets.UTF_8)).isEmpty();
            }
        } finally {
            System.setOut(original);
            if (previous == null) { System.clearProperty(property); } else { System.setProperty(property, previous); }
        }
    }

    @Test void rpcDiagnosticExportsOnlyKnownExactCauseEnumAndSuppressesUnknownPrivateValues() {
        String property = "lab.kafka-observation.tests", previous = System.getProperty(property);
        java.io.PrintStream original = System.out;
        var bytes = new java.io.ByteArrayOutputStream();
        try (var output = new java.io.PrintStream(bytes, true, java.nio.charset.StandardCharsets.UTF_8)) {
            System.setOut(output); System.setProperty(property, "true");
            Throwable[] causes = {new org.apache.kafka.common.errors.TimeoutException("PRIVATE_RPC_CANARY"),
                new org.apache.kafka.common.errors.UnsupportedVersionException("PRIVATE_RPC_CANARY"),
                new org.apache.kafka.common.errors.GroupIdNotFoundException("PRIVATE_RPC_CANARY"),
                new IllegalStateException("PRIVATE_RPC_CANARY endpoint/password"),
                new org.apache.kafka.common.errors.TimeoutException("PRIVATE_RPC_CANARY") {}};
            String[] kinds = {"RPC_TIMEOUT", "UNSUPPORTED_RPC_VERSION", "GROUP_ID_NOT_FOUND",
                "UNCLASSIFIED_EXECUTION_FAILURE", "UNCLASSIFIED_EXECUTION_FAILURE"};
            for (int index = 0; index < causes.length; index++) {
                bytes.reset();
                failingDiagnosticRpc(causes[index], ReadOnlyKafkaAdmin.RpcStage.LIST_COMMITTED,
                    index == 2 ? GROUP_UNAVAILABLE : KAFKA_UNAVAILABLE);
                String actual = bytes.toString(java.nio.charset.StandardCharsets.UTF_8);
                assertThat(actual).isEqualTo("{\"kind\":\"KAFKA_OBSERVER_RPC_DIAGNOSTIC\",\"stage\":\"LIST_COMMITTED\",\"failureKind\":\""
                    + kinds[index] + "\"}" + System.lineSeparator());
                assertThat(actual).doesNotContain("PRIVATE_", "Exception", "endpoint", "password");
            }
            bytes.reset();
            failingDiagnosticRpc(new IllegalStateException("PRIVATE_RPC_CANARY"), null, KAFKA_UNAVAILABLE);
            assertThat(bytes.toString(java.nio.charset.StandardCharsets.UTF_8)).isEmpty();
        } finally {
            System.setOut(original);
            if (previous == null) { System.clearProperty(property); } else { System.setProperty(property, previous); }
        }
    }

    static void failingDiagnosticRpc(Throwable cause, ReadOnlyKafkaAdmin.RpcStage stage, KafkaObservationService.Code expected) {
        var future = new KafkaFutureImpl<Void>(); future.completeExceptionally(cause);
        assertThatThrownBy(() -> new ReadOnlyKafkaAdmin.Deadline(10_000_000_000L, () -> 0).await(future, stage))
            .isInstanceOfSatisfying(KafkaObservationService.ObservationFailure.class, fixed -> {
                assertThat(fixed.code()).isEqualTo(expected); assertThat(fixed.getCause()).isNull(); assertThat(fixed.getStackTrace()).isEmpty();
            });
    }

    static final class TrackingFuture<T> extends KafkaFutureImpl<T> {
        private final CountDownLatch waiting;
        TrackingFuture(CountDownLatch waiting) { this.waiting = waiting; }
        @Override public T get(long timeout, TimeUnit unit) throws InterruptedException, java.util.concurrent.ExecutionException, java.util.concurrent.TimeoutException {
            waiting.countDown(); return super.get(timeout, unit);
        }
    }
    static void inOwnedGroup(OwnedAction action) throws Exception {
        var result = new AtomicReference<Throwable>(); var complete = new CountDownLatch(1);
        Thread owner = new Thread(new ThreadGroup("kafka-observation-unit-owned"), () -> {
            try { action.run(); } catch (Throwable failure) { result.set(failure); } finally { complete.countDown(); }
        }, "unit-owner"); owner.setDaemon(true); owner.start();
        assertThat(complete.await(15, TimeUnit.SECONDS)).isTrue(); assertThat(owner.join(Duration.ofSeconds(1))).isTrue();
        if (result.get() != null) { throw new AssertionError("Owned unit action failed", result.get()); }
    }

    static void await(CountDownLatch latch) {
        try { if (!latch.await(2, TimeUnit.SECONDS)) { throw new AssertionError("Owned test barrier timed out"); } }
        catch (InterruptedException interrupted) { Thread.currentThread().interrupt(); throw new AssertionError("Owned test interrupted"); }
    }
    static class FakeAdmin implements ReadOnlyKafkaAdmin {
        final AtomicInteger identities = new AtomicInteger(), offsetReads = new AtomicInteger(), closes = new AtomicInteger();
        Target before = target(), after = before;
        Offsets offsets = new Offsets(0, 0, 0L);
        boolean closeVerified = true;
        @Override public Target identity(Deadline deadline) { return identities.getAndIncrement() == 0 ? before : after; }
        @Override public Offsets offsets(Deadline deadline) { offsetReads.incrementAndGet(); return offsets; }
        @Override public boolean closeAndVerifyIoThread(Duration budget) { closes.incrementAndGet(); return closeVerified; }
    }
}
