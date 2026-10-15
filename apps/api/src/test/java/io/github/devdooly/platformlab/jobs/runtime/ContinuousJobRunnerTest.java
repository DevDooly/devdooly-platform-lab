package io.github.devdooly.platformlab.jobs.runtime;

import io.github.devdooly.platformlab.jobs.messaging.DispatchWorker;
import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.time.ZoneOffset;
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicReference;
import org.apache.kafka.clients.consumer.Consumer;
import org.apache.kafka.clients.producer.Producer;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.support.TransactionSynchronizationManager;
import org.springframework.transaction.support.TransactionTemplate;
import static io.github.devdooly.platformlab.jobs.runtime.RuntimeStateStore.*;
import static org.assertj.core.api.Assertions.*;
import static org.mockito.Mockito.*;

@SpringBootTest(properties = "spring.datasource.url=jdbc:h2:mem:runtime_journal_tests;MODE=MariaDB;DATABASE_TO_LOWER=TRUE;DB_CLOSE_DELAY=-1")
@ActiveProfiles("test")
class ContinuousJobRunnerTest {
    private static final String SOURCE = "a".repeat(40);
    private static final Instant NOW = Instant.parse("2026-10-15T01:02:03.123456Z");
    @Autowired JdbcTemplate jdbc;
    @Autowired PlatformTransactionManager manager;
    @Autowired ApplicationContext context;
    private RuntimeStateStore states;

    @BeforeEach void resetOwnJournal() {
        jdbc.update("UPDATE lab_runtime SET status = 'NOT_STARTED', stage = 'IDLE', failure_code = NULL, started_at = NULL, heartbeat_at = NULL, stopped_at = NULL, source_commit = 'unknown' WHERE id = 1");
        states = new RuntimeStateStore(jdbc, Clock.fixed(NOW, ZoneOffset.UTC));
    }

    @Test void migrationIsInitiallyUnstartedAndDefaultHttpContextCreatesNoRunnerOrClients() {
        states.requireSchemaV3();
        assertThat(states.read()).isEqualTo(new State(Status.NOT_STARTED, Stage.IDLE, null, null, null, null, "unknown"));
        assertThat(context.getBeansOfType(ContinuousJobRunner.class)).isEmpty();
        assertThat(context.getBeansOfType(RuntimeLease.class)).isEmpty();
        assertThat(context.getBeansOfType(Producer.class)).isEmpty();
        assertThat(context.getBeansOfType(Consumer.class)).isEmpty();
    }

    @Test void oneOwningLoopContinuesAcrossThreeDeliveriesWithExportFirstAndClosesAfterStop() {
        var lease = new FakeLease(); var closes = new AtomicInteger(); var calls = new ArrayList<Stage>();
        var owner = new AtomicReference<ContinuousJobRunner>(); var deliveries = new AtomicInteger();
        var actions = new ContinuousJobRunner.Actions() {
            private void check(Stage stage) {
                assertThat(TransactionSynchronizationManager.isActualTransactionActive()).isFalse();
                assertThat(states.read().status()).isEqualTo(Status.RUNNING);
                assertThat(states.read().stage()).isEqualTo(stage); calls.add(stage);
            }
            @Override public boolean exportOne() { check(Stage.EXPORT); return deliveries.get() > 0; }
            @Override public boolean publishOne() { check(Stage.PUBLISH); return true; }
            @Override public boolean receiveOne(Duration timeout) {
                check(Stage.CONSUME); assertThat(timeout).isEqualTo(Duration.ofMillis(100));
                if (deliveries.incrementAndGet() == 3) { owner.get().requestStop(); } return true;
            }
        };
        var runner = runner(lease, actions, closes::incrementAndGet); owner.set(runner);
        assertThat(runner.run()).isEqualTo(new State(Status.STOPPED, Stage.STOPPED, null, NOW, NOW, NOW, SOURCE));
        assertThat(calls).containsExactly(Stage.EXPORT, Stage.PUBLISH, Stage.CONSUME,
            Stage.EXPORT, Stage.PUBLISH, Stage.CONSUME, Stage.EXPORT, Stage.PUBLISH, Stage.CONSUME);
        assertThat(deliveries.get()).isEqualTo(3); assertThat(closes.get()).isEqualTo(1); assertThat(lease.closed).isTrue();
        assertThatThrownBy(runner::run).isInstanceOf(IllegalStateException.class); assertThat(closes.get()).isEqualTo(1);
    }

    @Test void exportFailureIsPersistentRestartCannotRunAndOnlyExplicitOwnedResumeClearsIt() throws Exception {
        var lease = new FakeLease(); var closes = new AtomicInteger();
        var actions = mock(ContinuousJobRunner.Actions.class);
        when(actions.exportOne()).thenThrow(new IllegalStateException("private diagnostics are not journal fields"));
        assertThat(runner(lease, actions, closes::incrementAndGet).run().status()).isEqualTo(Status.PAUSED_OPERATOR);
        var paused = states.read();
        assertThat(paused.stage()).isEqualTo(Stage.EXPORT); assertThat(paused.failureCode()).isEqualTo(FailureCode.EXPORT_FAILED);
        assertThat(paused.stoppedAt()).isEqualTo(NOW); verify(actions, never()).receiveOne(any()); verify(actions, never()).publishOne();
        var restartLease = new FakeLease(); var restartActions = mock(ContinuousJobRunner.Actions.class);
        assertThatThrownBy(() -> runner(restartLease, restartActions, closes::incrementAndGet).run())
            .isInstanceOf(RuntimeStateStore.OperatorResumeRequiredException.class);
        verifyNoInteractions(restartActions); assertThat(states.read()).isEqualTo(paused);
        assertThat(closes.get()).isEqualTo(2); assertThat(restartLease.closed).isTrue();
        var resumeLease = new FakeLease(); states.resume(resumeLease);
        assertThat(resumeLease.checks).isEqualTo(1); assertThat(states.read().status()).isEqualTo(Status.STOPPED);
        assertThat(states.read().failureCode()).isNull();
        var resumed = runner(resumeLease, mock(ContinuousJobRunner.Actions.class), () -> {}); resumed.requestStop();
        assertThat(resumed.run().status()).isEqualTo(Status.STOPPED);
    }

    @Test void workerFailureUsesFixedCodeAndNeverCallsExportAgainOrAutomaticallyRetries() throws Exception {
        var actions = mock(ContinuousJobRunner.Actions.class); var failure = mock(DispatchWorker.DeliveryPausedException.class);
        when(failure.code()).thenReturn(DispatchWorker.FailureCode.SOURCE_INVALID);
        when(actions.receiveOne(any())).thenThrow(failure);
        var state = runner(new FakeLease(), actions, () -> {}).run();
        assertThat(state.status()).isEqualTo(Status.PAUSED_OPERATOR); assertThat(state.stage()).isEqualTo(Stage.CONSUME);
        assertThat(state.failureCode()).isEqualTo(FailureCode.SOURCE_INVALID);
        verify(actions, times(1)).exportOne(); verify(actions, times(1)).publishOne(); verify(actions, times(1)).receiveOne(any());
    }

    @Test void lostOwnershipStopsBeforeNextIoAndCannotOverwriteTheJournalWithPauseOrStopped() throws Exception {
        var lease = new FakeLease(); var actions = mock(ContinuousJobRunner.Actions.class); var closes = new AtomicInteger();
        when(actions.exportOne()).thenAnswer(ignored -> { lease.lost = true; return false; });
        assertThatThrownBy(() -> runner(lease, actions, closes::incrementAndGet).run()).isInstanceOf(IllegalStateException.class);
        assertThat(states.read().status()).isEqualTo(Status.RUNNING); assertThat(states.read().stage()).isEqualTo(Stage.EXPORT);
        verify(actions, never()).publishOne(); verify(actions, never()).receiveOne(any());
        assertThat(closes.get()).isEqualTo(1); assertThat(lease.closed).isTrue();
    }

    @Test void resourceCloseFailurePersistsPauseAndStillReleasesOwner() {
        var lease = new FakeLease();
        var runner = runner(lease, mock(ContinuousJobRunner.Actions.class), () -> { throw new IllegalStateException("private detail"); });
        runner.requestStop(); var state = runner.run();
        assertThat(state.status()).isEqualTo(Status.PAUSED_OPERATOR); assertThat(state.stage()).isEqualTo(Stage.STOPPED);
        assertThat(state.failureCode()).isEqualTo(FailureCode.RESOURCE_CLOSE_FAILED); assertThat(lease.closed).isTrue();
    }

    @Test void invalidConfigurationAndOuterTransactionCannotStartOrRunIo() {
        var actions = mock(ContinuousJobRunner.Actions.class); var lease = new FakeLease();
        assertThatThrownBy(() -> new ContinuousJobRunner(states, lease, actions, () -> {}, "short", Duration.ofMillis(100), Duration.ofMillis(100)))
            .isInstanceOf(IllegalArgumentException.class);
        assertThatThrownBy(() -> new ContinuousJobRunner(states, lease, actions, () -> {}, SOURCE, Duration.ZERO, Duration.ofMillis(100)))
            .isInstanceOf(IllegalArgumentException.class);
        new TransactionTemplate(manager).executeWithoutResult(ignored ->
            assertThatThrownBy(() -> runner(lease, actions, () -> {}).run()).isInstanceOf(IllegalStateException.class));
        verifyNoInteractions(actions); assertThat(states.read().status()).isEqualTo(Status.NOT_STARTED); assertThat(lease.closed).isTrue();
    }

    @Test void resumeRequiresPausedStateAndVerifiedOwnership() {
        assertThatThrownBy(() -> states.resume(new FakeLease())).isInstanceOf(IllegalStateException.class);
        var lease = new FakeLease(); states.start(lease, SOURCE); states.pause(lease, Stage.PUBLISH, FailureCode.PUBLISH_FAILED);
        var paused = states.read(); lease.lost = true;
        assertThatThrownBy(() -> states.resume(lease)).isInstanceOf(RuntimeLease.LeaseLostException.class);
        assertThat(states.read()).isEqualTo(paused);
    }

    private ContinuousJobRunner runner(RuntimeLease lease, ContinuousJobRunner.Actions actions, AutoCloseable resources) {
        return new ContinuousJobRunner(states, lease, actions, resources, SOURCE, Duration.ofMillis(100), Duration.ofMillis(100));
    }
    private static final class FakeLease implements RuntimeLease {
        boolean closed; boolean lost; int checks;
        @Override public void verifyHeld() { checks++; if (closed || lost) { throw new RuntimeLease.LeaseLostException(); } }
        @Override public void close() { closed = true; }
    }
}
