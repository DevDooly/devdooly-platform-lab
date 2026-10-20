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

    @Test void actionErrorPersistsFixedPauseClosesResourcesAndPropagatesTheOriginalError() throws Exception {
        var lease = new FakeLease(); var closes = new AtomicInteger();
        var actions = mock(ContinuousJobRunner.Actions.class); var error = new AssertionError("private action detail");
        when(actions.exportOne()).thenThrow(error);
        assertThatThrownBy(() -> runner(lease, actions, closes::incrementAndGet).run()).isSameAs(error);
        assertThat(states.read()).isEqualTo(new State(Status.PAUSED_OPERATOR, Stage.EXPORT, FailureCode.RUNTIME_FAILED, NOW, NOW, NOW, SOURCE));
        verify(actions, never()).publishOne(); verify(actions, never()).receiveOne(any());
        assertThat(closes.get()).isEqualTo(1); assertThat(lease.closes).isEqualTo(1);
        assertThat(error.getSuppressed()).isEmpty();
    }

    @Test void ordinaryActionFailureStillInvalidatesLocalReadinessBeforeTheJournalWrite() {
        var lease = new FakeLease(); var journal = spy(states); var notReady = new AtomicInteger();
        var actions = mock(ContinuousJobRunner.Actions.class); when(actions.exportOne()).thenThrow(new IllegalStateException("private action"));
        var progress = new RuntimeProgress() { @Override public void notReady() { notReady.incrementAndGet(); } };
        doAnswer(invocation -> { assertThat(notReady.get()).isEqualTo(1); return invocation.callRealMethod(); })
            .when(journal).pause(any(), any(), any());
        var runner = new ContinuousJobRunner(journal, lease, actions, () -> {}, SOURCE, Duration.ofMillis(100), Duration.ofMillis(100), progress);
        assertThat(runner.run().failureCode()).isEqualTo(FailureCode.EXPORT_FAILED);
        assertThat(notReady.get()).isEqualTo(2); assertThat(lease.closes).isEqualTo(1);
    }

    @Test void bodyErrorSurvivesJournalResourceAndLeaseErrorsWithoutNormalStoppedOrAnImplicitJournalRetry() throws Exception {
        var lease = new FakeLease(); lease.closeError = new AssertionError("private lease detail");
        var journal = spy(states); var journalError = new AssertionError("private journal detail");
        doThrow(journalError).when(journal).pause(any(), any(), any());
        var actions = mock(ContinuousJobRunner.Actions.class); var original = new AssertionError("private body detail");
        when(actions.exportOne()).thenThrow(original);
        var closed = new ArrayList<String>();
        var resources = new RuntimeResources(() -> { closed.add("consumer"); throw new AssertionError("private close detail"); },
            () -> closed.add("producer"), () -> { closed.add("store"); throw new IllegalStateException("private exception"); });
        var runner = new ContinuousJobRunner(journal, lease, actions, resources, SOURCE, Duration.ofMillis(100), Duration.ofMillis(100));
        assertThatThrownBy(runner::run).isSameAs(original);
        assertThat(states.read()).isEqualTo(new State(Status.RUNNING, Stage.EXPORT, null, NOW, NOW, null, SOURCE));
        verify(journal, times(1)).pause(any(), eq(Stage.EXPORT), eq(FailureCode.RUNTIME_FAILED));
        verify(journal, never()).stop(any()); verify(journal, never()).read();
        verify(actions, never()).publishOne(); verify(actions, never()).receiveOne(any());
        assertThat(closed).containsExactly("consumer", "producer", "store"); assertThat(lease.closes).isEqualTo(1);
        assertThat(original.getSuppressed()).isEmpty(); assertThat(original.getCause()).isNull();
    }

    @Test void ordinaryPauseWriteFailureWithBodyErrorPreservesStaleJournalAndStillClosesEverything() throws Exception {
        var lease = new FakeLease(); var journal = spy(states); var closes = new AtomicInteger();
        doThrow(new IllegalStateException("private SQL detail")).when(journal).pause(any(), any(), any());
        var actions = mock(ContinuousJobRunner.Actions.class); var original = new AssertionError("private body detail");
        when(actions.exportOne()).thenThrow(original);
        var runner = new ContinuousJobRunner(journal, lease, actions, closes::incrementAndGet, SOURCE, Duration.ofMillis(100), Duration.ofMillis(100));
        assertThatThrownBy(runner::run).isSameAs(original);
        assertThat(states.read().status()).isEqualTo(Status.RUNNING); assertThat(states.read().stage()).isEqualTo(Stage.EXPORT);
        verify(journal, times(1)).pause(any(), any(), any()); verify(journal, never()).stop(any());
        assertThat(closes.get()).isEqualTo(1); assertThat(lease.closes).isEqualTo(1); assertThat(original.getSuppressed()).isEmpty();
    }

    @Test void resourceOnlyErrorPersistsCloseFailureAttemptsAllClientsAndPropagatesTheSameError() throws Exception {
        var lease = new FakeLease(); var closed = new ArrayList<String>(); var error = new AssertionError("private close detail");
        var resources = new RuntimeResources(() -> { closed.add("consumer"); throw error; },
            () -> closed.add("producer"), () -> closed.add("store"));
        var actions = mock(ContinuousJobRunner.Actions.class); var runner = runner(lease, actions, resources); runner.requestStop();
        assertThatThrownBy(runner::run).isSameAs(error);
        assertThat(states.read()).isEqualTo(new State(Status.PAUSED_OPERATOR, Stage.STOPPED, FailureCode.RESOURCE_CLOSE_FAILED, NOW, NOW, NOW, SOURCE));
        assertThat(closed).containsExactly("consumer", "producer", "store"); assertThat(lease.closes).isEqualTo(1);
        verifyNoInteractions(actions); assertThat(error.getSuppressed()).isEmpty();
    }

    @Test void laterCloseErrorDoesNotReplaceTheAlreadyPersistedOrdinaryActionFailure() throws Exception {
        var lease = new FakeLease(); var actions = mock(ContinuousJobRunner.Actions.class); var closes = new AtomicInteger();
        when(actions.exportOne()).thenThrow(new IllegalStateException("private ordinary action detail"));
        var error = new AssertionError("private close detail");
        assertThatThrownBy(() -> runner(lease, actions, () -> { closes.incrementAndGet(); throw error; }).run()).isSameAs(error);
        assertThat(states.read().status()).isEqualTo(Status.PAUSED_OPERATOR);
        assertThat(states.read().failureCode()).isEqualTo(FailureCode.EXPORT_FAILED);
        assertThat(closes.get()).isEqualTo(1); assertThat(lease.closes).isEqualTo(1); assertThat(error.getSuppressed()).isEmpty();
    }

    @Test void startupProgressErrorCannotRunAnActionOrSkipResourceAndLeaseClose() {
        var lease = new FakeLease(); var actions = mock(ContinuousJobRunner.Actions.class); var closes = new AtomicInteger();
        var notReady = new AtomicInteger(); var error = new AssertionError("private progress detail");
        var progress = new RuntimeProgress() {
            @Override public void starting() { throw error; }
            @Override public void notReady() { notReady.incrementAndGet(); }
        };
        var runner = new ContinuousJobRunner(states, lease, actions, closes::incrementAndGet, SOURCE, Duration.ofMillis(100), Duration.ofMillis(100), progress);
        assertThatThrownBy(runner::run).isSameAs(error);
        assertThat(states.read()).isEqualTo(new State(Status.PAUSED_OPERATOR, Stage.IDLE, FailureCode.RUNTIME_FAILED, NOW, NOW, NOW, SOURCE));
        verifyNoInteractions(actions); assertThat(notReady.get()).isEqualTo(1);
        assertThat(closes.get()).isEqualTo(1); assertThat(lease.closes).isEqualTo(1);
    }

    @Test void evenAThrowingTerminalProgressHookCannotSkipCleanupOrRecordNormalStopped() {
        var lease = new FakeLease(); var actions = mock(ContinuousJobRunner.Actions.class); var closes = new AtomicInteger();
        var notReady = new AtomicInteger(); var error = new AssertionError("private terminal progress detail");
        var progress = new RuntimeProgress() {
            @Override public void notReady() { if (notReady.incrementAndGet() == 2) { throw error; } }
        };
        var runner = new ContinuousJobRunner(states, lease, actions, closes::incrementAndGet, SOURCE, Duration.ofMillis(100), Duration.ofMillis(100), progress);
        runner.requestStop(); assertThatThrownBy(runner::run).isSameAs(error);
        assertThat(states.read()).isEqualTo(new State(Status.PAUSED_OPERATOR, Stage.IDLE, FailureCode.RUNTIME_FAILED, NOW, NOW, NOW, SOURCE));
        verifyNoInteractions(actions); assertThat(notReady.get()).isEqualTo(2);
        assertThat(closes.get()).isEqualTo(1); assertThat(lease.closes).isEqualTo(1);
    }

    @Test void journalErrorWhileHandlingAnOrdinaryActionFailureIsNotSwallowedOrRetried() throws Exception {
        var lease = new FakeLease(); var journal = spy(states); var closes = new AtomicInteger();
        var error = new AssertionError("private journal detail"); doThrow(error).when(journal).pause(any(), any(), any());
        var actions = mock(ContinuousJobRunner.Actions.class); when(actions.exportOne()).thenThrow(new IllegalStateException("private action"));
        var runner = new ContinuousJobRunner(journal, lease, actions, closes::incrementAndGet, SOURCE, Duration.ofMillis(100), Duration.ofMillis(100));
        assertThatThrownBy(runner::run).isSameAs(error);
        assertThat(states.read().status()).isEqualTo(Status.RUNNING); assertThat(states.read().stage()).isEqualTo(Stage.EXPORT);
        verify(journal, times(1)).pause(any(), any(), any()); verify(journal, never()).stop(any());
        assertThat(closes.get()).isEqualTo(1); assertThat(lease.closes).isEqualTo(1);
    }

    @Test void startAndFinalStopErrorsStillAttemptResourceAndLeaseCloseWithoutInventingAState() {
        for (boolean atStart : List.of(true, false)) {
            resetOwnJournal();
            var lease = new FakeLease(); var journal = spy(states); var closes = new AtomicInteger();
            var error = new AssertionError("private journal detail");
            if (atStart) { doThrow(error).when(journal).start(any(), any()); }
            else { doThrow(error).when(journal).stop(any()); }
            var actions = mock(ContinuousJobRunner.Actions.class);
            var runner = new ContinuousJobRunner(journal, lease, actions, closes::incrementAndGet, SOURCE, Duration.ofMillis(100), Duration.ofMillis(100));
            runner.requestStop(); assertThatThrownBy(runner::run).isSameAs(error);
            assertThat(states.read().status()).isEqualTo(atStart ? Status.NOT_STARTED : Status.RUNNING);
            verifyNoInteractions(actions); assertThat(closes.get()).isEqualTo(1); assertThat(lease.closes).isEqualTo(1);
        }
    }

    @Test void finalReadErrorIsPropagatedAfterSuccessfulStopAndLeaseIsStillClosed() {
        var lease = new FakeLease(); var journal = spy(states); var closes = new AtomicInteger();
        var error = new AssertionError("private read detail"); doThrow(error).when(journal).read();
        var actions = mock(ContinuousJobRunner.Actions.class);
        var runner = new ContinuousJobRunner(journal, lease, actions, closes::incrementAndGet, SOURCE, Duration.ofMillis(100), Duration.ofMillis(100));
        runner.requestStop(); assertThatThrownBy(runner::run).isSameAs(error);
        assertThat(states.read().status()).isEqualTo(Status.STOPPED);
        verify(journal, times(1)).stop(lease); verifyNoInteractions(actions);
        assertThat(closes.get()).isEqualTo(1); assertThat(lease.closes).isEqualTo(1);
    }

    @Test void firstLeaseCloseErrorIsPropagatedWithoutAddingPrivateDiagnostics() {
        var lease = new FakeLease(); var error = new AssertionError("private lease detail"); lease.closeError = error;
        var closes = new AtomicInteger(); var actions = mock(ContinuousJobRunner.Actions.class);
        var runner = runner(lease, actions, closes::incrementAndGet); runner.requestStop();
        assertThatThrownBy(runner::run).isSameAs(error);
        assertThat(states.read().status()).isEqualTo(Status.STOPPED); verifyNoInteractions(actions);
        assertThat(closes.get()).isEqualTo(1); assertThat(lease.closes).isEqualTo(1);
        assertThat(error.getSuppressed()).isEmpty(); assertThat(error.getCause()).isNull();
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
        boolean closed; boolean lost; int checks; int closes; Error closeError;
        @Override public void verifyHeld() { checks++; if (closed || lost) { throw new RuntimeLease.LeaseLostException(); } }
        @Override public void close() { closes++; closed = true; if (closeError != null) { throw closeError; } }
    }
}
