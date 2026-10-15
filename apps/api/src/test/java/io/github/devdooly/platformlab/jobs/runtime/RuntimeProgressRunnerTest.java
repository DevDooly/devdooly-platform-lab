package io.github.devdooly.platformlab.jobs.runtime;

import java.time.Clock;
import java.time.Duration;
import java.util.ArrayList;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicReference;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.transaction.support.TransactionSynchronizationManager;
import static io.github.devdooly.platformlab.jobs.runtime.RuntimeStateStore.*;
import static org.assertj.core.api.Assertions.*;
import static org.mockito.Mockito.*;

@SpringBootTest(properties = "spring.datasource.url=jdbc:h2:mem:runtime_progress_tests;MODE=MariaDB;DATABASE_TO_LOWER=TRUE;DB_CLOSE_DELAY=-1")
@ActiveProfiles("test")
class RuntimeProgressRunnerTest {
    private static final String SOURCE = "a".repeat(40);
    @Autowired JdbcTemplate jdbc;
    private RuntimeStateStore states;
    @BeforeEach void reset() {
        jdbc.update("UPDATE lab_runtime SET status='NOT_STARTED',stage='IDLE',failure_code=NULL,started_at=NULL,heartbeat_at=NULL,stopped_at=NULL,source_commit='unknown' WHERE id=1");
        states = new RuntimeStateStore(jdbc, Clock.systemUTC());
    }
    private ContinuousJobRunner runner(Lease lease, ContinuousJobRunner.Actions actions, AutoCloseable close, RuntimeProgress progress) {
        return new ContinuousJobRunner(states, lease, actions, close, SOURCE, Duration.ofMillis(100), Duration.ofMillis(100), progress);
    }
    @Test void callbacksFollowCommittedJournalAndStopIsNotReadyBeforeResourceClose() throws Exception {
        var stages = new ArrayList<String>(); var ready = new AtomicBoolean(); var owner = new AtomicReference<ContinuousJobRunner>();
        RuntimeProgress progress = new RuntimeProgress() {
            @Override public void starting() { assertThat(states.read().status()).isEqualTo(Status.RUNNING); }
            @Override public void committed(String stage) {
                assertThat(TransactionSynchronizationManager.isActualTransactionActive()).isFalse();
                assertThat(states.read().status()).isEqualTo(Status.RUNNING); assertThat(states.read().stage().name()).isEqualTo(stage);
                stages.add(stage); ready.set(true);
            }
            @Override public void notReady() { ready.set(false); }
        };
        var calls = new AtomicInteger(); var actions = mock(ContinuousJobRunner.Actions.class);
        when(actions.exportOne()).thenAnswer(ignored -> { if (calls.incrementAndGet() == 2) { owner.get().requestStop(); } return false; });
        var run = runner(new Lease(), actions, () -> assertThat(ready).isFalse(), progress); owner.set(run);
        assertThat(run.run().status()).isEqualTo(Status.STOPPED);
        assertThat(stages).containsExactly("EXPORT", "PUBLISH", "CONSUME", "IDLE", "EXPORT"); assertThat(ready).isFalse();
    }
    @Test void progressFailurePausesWithFixedRuntimeCodeBeforeAnyExternalIo() {
        var progress = mock(RuntimeProgress.class); doThrow(new RuntimeProgress.ProgressUnavailableException()).when(progress).committed("EXPORT");
        var actions = mock(ContinuousJobRunner.Actions.class); var lease = new Lease();
        var result = runner(lease, actions, () -> {}, progress).run();
        assertThat(result.status()).isEqualTo(Status.PAUSED_OPERATOR); assertThat(result.failureCode()).isEqualTo(FailureCode.RUNTIME_FAILED);
        verifyNoInteractions(actions); verify(progress, atLeastOnce()).notReady(); assertThat(lease.closed).isTrue();
    }
    @Test void lostOwnershipNeverPublishesAHealthyNextStage() throws Exception {
        var progress = mock(RuntimeProgress.class); var actions = mock(ContinuousJobRunner.Actions.class); var lease = new Lease();
        when(actions.exportOne()).thenAnswer(ignored -> { lease.lost = true; return false; });
        assertThatThrownBy(() -> runner(lease, actions, () -> {}, progress).run()).isInstanceOf(IllegalStateException.class);
        verify(progress).committed("EXPORT"); verify(progress, never()).committed("PUBLISH"); verify(progress, atLeastOnce()).notReady();
        assertThat(states.read().stage()).isEqualTo(Stage.EXPORT);
    }
    @Test void persistedPauseCannotPublishStartOrProgressOnRestart() {
        var lease = new Lease(); states.start(lease, SOURCE); states.pause(lease, Stage.EXPORT, FailureCode.EXPORT_FAILED);
        var progress = mock(RuntimeProgress.class); var actions = mock(ContinuousJobRunner.Actions.class);
        assertThatThrownBy(() -> runner(new Lease(), actions, () -> {}, progress).run()).isInstanceOf(RuntimeStateStore.OperatorResumeRequiredException.class);
        verify(progress, never()).starting(); verify(progress, never()).committed(any()); verifyNoInteractions(actions);
        assertThat(states.read().status()).isEqualTo(Status.PAUSED_OPERATOR);
    }
    private static final class Lease implements RuntimeLease {
        boolean lost, closed;
        @Override public void verifyHeld() { if (lost || closed) { throw new RuntimeLease.LeaseLostException(); } }
        @Override public void close() { closed = true; }
    }
}
