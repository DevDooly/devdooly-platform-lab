package io.github.devdooly.platformlab.jobs.messaging;

import io.github.devdooly.platformlab.jobs.LabJobService;
import java.time.Instant;
import java.util.List;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;
import org.apache.kafka.clients.producer.MockProducer;
import org.apache.kafka.clients.producer.Producer;
import org.apache.kafka.clients.producer.ProducerRecord;
import org.apache.kafka.clients.producer.RecordMetadata;
import org.apache.kafka.common.TopicPartition;
import org.apache.kafka.common.serialization.StringSerializer;
import org.junit.jupiter.api.Test;
import org.springframework.transaction.IllegalTransactionStateException;
import org.springframework.transaction.support.TransactionSynchronizationManager;
import static org.assertj.core.api.Assertions.*;
import static org.mockito.ArgumentMatchers.*;
import static org.mockito.Mockito.*;

@SuppressWarnings("unchecked")
class DispatchPublisherTest {
    private static final String TOPIC = "foundation-dispatch";
    private static final String RUN = "foundation-kafka-job";
    private static final String HASH = "a".repeat(64);
    private static final Instant AT = Instant.parse("2026-10-15T00:00:00Z");

    @Test void manualBrokerAckPrecedesFaultBoundaryAndDatabaseAcknowledgement() throws Exception {
        var jobs = queuedJobs();
        try (var producer = new SignallingProducer(); var executor = Executors.newSingleThreadExecutor()) {
            var publisher = new DispatchPublisher(jobs, producer, TOPIC, metadata -> {
                assertThat(metadata.topic()).isEqualTo(TOPIC);
                verify(jobs, never()).acknowledgeDispatch(anyString(), anyString());
            });
            var published = executor.submit(publisher::publishOne);
            assertThat(producer.sent.await(5, TimeUnit.SECONDS)).isTrue();
            verify(jobs, never()).acknowledgeDispatch(anyString(), anyString());
            assertThat(published.isDone()).isFalse();
            assertThat(producer.completeNext()).isTrue();
            assertThat(published.get(5, TimeUnit.SECONDS)).isPresent();
            verify(jobs).acknowledgeDispatch(RUN, HASH);
            assertThat(producer.history()).hasSize(1);
            var record = producer.history().getFirst();
            assertThat(record.topic()).isEqualTo(TOPIC); assertThat(record.partition()).isZero();
            assertThat(record.key()).isEqualTo(RUN);
            assertThat(DispatchMessage.decode(record.value())).isEqualTo(DispatchMessage.from(job(LabJobService.Status.QUEUED)));
        }
    }

    @Test void acknowledgedSendThenFaultLeavesIntentPendingForDuplicateReplay() throws Exception {
        var jobs = queuedJobs();
        try (var producer = new MockProducer<String, String>(true, null, new StringSerializer(), new StringSerializer())) {
            var faulty = new DispatchPublisher(jobs, producer, TOPIC, ignored -> { throw new IntentionalCrashBoundary(); });
            assertThatThrownBy(faulty::publishOne).isInstanceOf(IntentionalCrashBoundary.class);
            verify(jobs, never()).acknowledgeDispatch(anyString(), anyString());
            assertThat(new DispatchPublisher(jobs, producer, TOPIC).publishOne()).isPresent();
            assertThat(producer.history()).hasSize(2);
            verify(jobs).acknowledgeDispatch(RUN, HASH);
        }
    }

    @Test void timeoutAndBrokerFailureDoNotAcknowledgeDatabaseIntent() throws Exception {
        for (Exception failure : new Exception[] {new TimeoutException("ack timeout"), new ExecutionException(new IllegalStateException("broker rejected"))}) {
            var jobs = queuedJobs();
            Producer<String, String> producer = mock(Producer.class);
            Future<RecordMetadata> ack = mock(Future.class);
            when(producer.send(any(ProducerRecord.class))).thenReturn(ack);
            when(ack.get(15, TimeUnit.SECONDS)).thenThrow(failure);
            assertThatThrownBy(new DispatchPublisher(jobs, producer, TOPIC)::publishOne).isSameAs(failure);
            verify(jobs, never()).acknowledgeDispatch(anyString(), anyString());
        }
    }

    @Test void interruptionRestoresFlagAndDoesNotAcknowledgeDatabaseIntent() throws Exception {
        var jobs = queuedJobs();
        Producer<String, String> producer = mock(Producer.class);
        Future<RecordMetadata> ack = mock(Future.class);
        when(producer.send(any(ProducerRecord.class))).thenReturn(ack);
        when(ack.get(15, TimeUnit.SECONDS)).thenThrow(new InterruptedException("interrupted"));
        try {
            assertThatThrownBy(new DispatchPublisher(jobs, producer, TOPIC)::publishOne).isInstanceOf(InterruptedException.class);
            assertThat(Thread.currentThread().isInterrupted()).isTrue();
            verify(jobs, never()).acknowledgeDispatch(anyString(), anyString());
        } finally { Thread.interrupted(); }
    }

    @Test void outerDatabaseTransactionIsRejectedBeforeReadingOrSending() {
        var jobs = mock(LabJobService.class);
        Producer<String, String> producer = mock(Producer.class);
        try {
            TransactionSynchronizationManager.setActualTransactionActive(true);
            assertThatThrownBy(new DispatchPublisher(jobs, producer, TOPIC)::publishOne).isInstanceOf(IllegalTransactionStateException.class);
            verifyNoInteractions(jobs, producer);
        } finally { TransactionSynchronizationManager.setActualTransactionActive(false); }
    }

    @Test void exportOnlyPendingIntentsAreNotPublishedToDispatchTopic() throws Exception {
        var jobs = mock(LabJobService.class);
        when(jobs.pendingOutbox(100)).thenReturn(List.of(intent(LabJobService.EventType.EXPORT, HASH)));
        Producer<String, String> producer = mock(Producer.class);
        assertThat(new DispatchPublisher(jobs, producer, TOPIC).publishOne()).isEmpty();
        verify(jobs, never()).get(anyString()); verifyNoInteractions(producer);
    }

    @Test void mismatchedHashAndUnqueuedJobCannotReachBroker() {
        for (LabJobService.Status status : List.of(LabJobService.Status.STAGING, LabJobService.Status.TERMINATED)) {
            var jobs = queuedJobs(); when(jobs.get(RUN)).thenReturn(job(status));
            Producer<String, String> producer = mock(Producer.class);
            assertThatThrownBy(new DispatchPublisher(jobs, producer, TOPIC)::publishOne).isInstanceOf(IllegalStateException.class);
            verifyNoInteractions(producer); verify(jobs, never()).acknowledgeDispatch(anyString(), anyString());
        }
        var jobs = queuedJobs(); when(jobs.pendingOutbox(100)).thenReturn(List.of(intent(LabJobService.EventType.DISPATCH, "b".repeat(64))));
        Producer<String, String> producer = mock(Producer.class);
        assertThatThrownBy(new DispatchPublisher(jobs, producer, TOPIC)::publishOne).isInstanceOf(IllegalStateException.class);
        verifyNoInteractions(producer); verify(jobs, never()).acknowledgeDispatch(anyString(), anyString());
    }

    @Test void ackForWrongTopicPartitionOrWithoutOffsetCannotAcknowledgeIntent() {
        for (RecordMetadata metadata : List.of(metadata("wrong-topic", 0, 0), metadata(TOPIC, 1, 0), metadata(TOPIC, 0, -1))) {
            var jobs = queuedJobs(); Producer<String, String> producer = mock(Producer.class);
            when(producer.send(any(ProducerRecord.class))).thenReturn(CompletableFuture.completedFuture(metadata));
            assertThatThrownBy(new DispatchPublisher(jobs, producer, TOPIC)::publishOne).isInstanceOf(IllegalStateException.class);
            verify(jobs, never()).acknowledgeDispatch(anyString(), anyString());
        }
    }

    @Test void invalidTopicIsRejectedBeforeAnyIo() {
        for (String topic : new String[] {"", ".", "..", "bad/topic", "a".repeat(250)}) {
            assertThatThrownBy(() -> new DispatchPublisher(mock(LabJobService.class), mock(Producer.class), topic)).isInstanceOf(IllegalArgumentException.class);
        }
    }

    private static LabJobService queuedJobs() {
        var jobs = mock(LabJobService.class);
        when(jobs.pendingOutbox(100)).thenReturn(List.of(intent(LabJobService.EventType.DISPATCH, HASH)));
        when(jobs.get(RUN)).thenReturn(job(LabJobService.Status.QUEUED));
        return jobs;
    }
    private static LabJobService.Job job(LabJobService.Status status) {
        return new LabJobService.Job(RUN, "sensor-validation-v1", HASH, 123, status, LabJobService.ExportStatus.NOT_REQUESTED,
            AT, AT, AT, null, null, null);
    }
    private static LabJobService.Outbox intent(LabJobService.EventType type, String hash) {
        return new LabJobService.Outbox(1, RUN, type, hash, LabJobService.OutboxStatus.PENDING, AT, null);
    }
    private static RecordMetadata metadata(String topic, int partition, long offset) {
        return new RecordMetadata(new TopicPartition(topic, partition), offset, 0, AT.toEpochMilli(), 0, 0);
    }
    private static class IntentionalCrashBoundary extends RuntimeException {}
    private static class SignallingProducer extends MockProducer<String, String> {
        final CountDownLatch sent = new CountDownLatch(1);
        SignallingProducer() { super(false, null, new StringSerializer(), new StringSerializer()); }
        @Override public synchronized Future<RecordMetadata> send(ProducerRecord<String, String> record) {
            Future<RecordMetadata> future = super.send(record); sent.countDown(); return future;
        }
    }
}
