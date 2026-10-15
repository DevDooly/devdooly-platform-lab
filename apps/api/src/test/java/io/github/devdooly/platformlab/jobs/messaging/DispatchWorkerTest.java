package io.github.devdooly.platformlab.jobs.messaging;

import io.github.devdooly.platformlab.jobs.*;
import java.time.Duration;
import java.time.Instant;
import java.util.List;
import java.util.Map;
import java.util.Set;
import org.apache.kafka.clients.consumer.*;
import org.apache.kafka.common.TopicPartition;
import org.junit.jupiter.api.Test;
import org.springframework.transaction.support.TransactionSynchronizationManager;
import static org.assertj.core.api.Assertions.*;
import static org.mockito.ArgumentMatchers.*;
import static org.mockito.Mockito.*;

@SuppressWarnings("unchecked")
class DispatchWorkerTest {
    private static final String TOPIC="lab.sensor-runs.v1", RUN="worker-test";
    private static final TopicPartition TP=new TopicPartition(TOPIC,0);
    private final byte[] bytes=CanonicalSource.fixtureBytes();
    private final LabJobService jobs=mock(LabJobService.class);
    private final VerifiedSourceReader sources=mock(VerifiedSourceReader.class);
    private final Consumer<String,String> consumer=mock(Consumer.class);
    private LabJobService.Job job(LabJobService.Status status) {
        return new LabJobService.Job(RUN,"sensor-validation-v1",CanonicalSource.validate(bytes).sha256(),bytes.length,
            status,LabJobService.ExportStatus.PENDING,Instant.EPOCH,Instant.EPOCH,Instant.EPOCH,
            status==LabJobService.Status.COMPLETED?Instant.EPOCH:null,null,null);
    }
    private DispatchWorker worker(LabJobService.Status status) {
        var admitted=job(status);
        when(jobs.get(RUN)).thenReturn(admitted);
        when(jobs.process(RUN,admitted.sourceSha256())).thenReturn(job(LabJobService.Status.COMPLETED));
        when(sources.readAndVerify(admitted)).thenReturn(bytes);
        when(consumer.assignment()).thenReturn(Set.of(TP));
        when(consumer.poll(any(Duration.class))).thenReturn(new ConsumerRecords<>(Map.of(TP,List.of(
            new ConsumerRecord<>(TOPIC,0,7,RUN,DispatchMessage.from(admitted).encode())))));
        return new DispatchWorker(jobs,sources,consumer,TOPIC);
    }
    @Test void sourceVerificationAndDbCompletionPrecedeOnlyThisRecordsNextOffset() {
        var delivery=worker(LabJobService.Status.QUEUED).receiveOne(Duration.ofMillis(1)).orElseThrow();
        assertThat(delivery.replay()).isFalse(); assertThat(delivery.nextOffset()).isEqualTo(8);
        var ordered=inOrder(sources,jobs,consumer);
        ordered.verify(sources).readAndVerify(job(LabJobService.Status.QUEUED));
        ordered.verify(jobs).process(RUN,job(LabJobService.Status.QUEUED).sourceSha256());
        ordered.verify(consumer).commitSync(Map.of(TP,new OffsetAndMetadata(8)),Duration.ofSeconds(10));
    }
    @Test void completedDeliveryStillVerifiesSourceAndMarksReplayWithoutInventingAResult() {
        var delivery=worker(LabJobService.Status.COMPLETED).receiveOne(Duration.ZERO).orElseThrow();
        assertThat(delivery.replay()).isTrue();
        verify(sources).readAndVerify(job(LabJobService.Status.COMPLETED));
        verify(jobs).process(RUN,job(LabJobService.Status.COMPLETED).sourceSha256());
    }
    @Test void sourceFailureRewindsPausesAndForbidsFurtherPollOrOffsetCommit() {
        var worker=worker(LabJobService.Status.QUEUED);
        when(sources.readAndVerify(any())).thenThrow(new S3RawSourceStore.SourceVerificationException("fixture corruption"));
        assertThatThrownBy(()->worker.receiveOne(Duration.ZERO)).isInstanceOfSatisfying(DispatchWorker.DeliveryPausedException.class,
            failure->assertThat(failure.code()).isEqualTo(DispatchWorker.FailureCode.SOURCE_INVALID));
        assertThat(worker.isPaused()).isTrue(); verify(consumer).seek(TP,7); verify(consumer).pause(Set.of(TP));
        assertThatThrownBy(()->worker.receiveOne(Duration.ZERO)).isInstanceOfSatisfying(DispatchWorker.DeliveryPausedException.class,
            failure->assertThat(failure.code()).isEqualTo(DispatchWorker.FailureCode.OPERATOR_RESUME_REQUIRED));
        verify(consumer,times(1)).poll(any(Duration.class)); verify(jobs,never()).process(anyString(),anyString());
        verify(consumer,never()).commitSync(anyMap(),any(Duration.class));
    }
    @Test void commitFailurePreservesCompletedDbEffectAndDoesNotPollPastFailedDelivery() {
        var worker=worker(LabJobService.Status.QUEUED);
        doThrow(new org.apache.kafka.common.errors.TimeoutException("fixture timeout"))
            .when(consumer).commitSync(anyMap(),any(Duration.class));
        assertThatThrownBy(()->worker.receiveOne(Duration.ZERO)).isInstanceOfSatisfying(DispatchWorker.DeliveryPausedException.class,
            failure->assertThat(failure.code()).isEqualTo(DispatchWorker.FailureCode.OFFSET_COMMIT_FAILED));
        assertThat(worker.isPaused()).isTrue(); verify(jobs).process(anyString(),anyString());
        verify(jobs,never()).terminate(anyString(),anyString()); verify(jobs,never()).completeExport(anyString(),anyString());
    }
    @Test void invalidKeyOrUnexpectedPollBatchDoesNotReachStorageOrDbProcessing() {
        var worker=worker(LabJobService.Status.QUEUED);
        var record=new ConsumerRecord<>(TOPIC,0,7,"wrong-key",DispatchMessage.from(job(LabJobService.Status.QUEUED)).encode());
        when(consumer.poll(any(Duration.class))).thenReturn(new ConsumerRecords<>(Map.of(TP,List.of(record))));
        assertThatThrownBy(()->worker.receiveOne(Duration.ZERO)).isInstanceOf(DispatchWorker.DeliveryPausedException.class);
        verifyNoInteractions(sources); verify(jobs,never()).process(anyString(),anyString());
        verify(consumer,never()).commitSync(anyMap(),any(Duration.class));
        var otherConsumer=mock(Consumer.class);
        when(otherConsumer.poll(any(Duration.class))).thenReturn(new ConsumerRecords<>(Map.of(TP,List.of(record,record))));
        assertThatThrownBy(()->new DispatchWorker(jobs,sources,otherConsumer,TOPIC).receiveOne(Duration.ZERO))
            .isInstanceOf(DispatchWorker.DeliveryPausedException.class);
        verifyNoInteractions(sources);
    }
    @Test void outerDbTransactionIsRejectedBeforePolling() {
        var worker=worker(LabJobService.Status.QUEUED);
        TransactionSynchronizationManager.setActualTransactionActive(true);
        try { assertThatThrownBy(()->worker.receiveOne(Duration.ZERO)).isInstanceOf(org.springframework.transaction.IllegalTransactionStateException.class); }
        finally { TransactionSynchronizationManager.setActualTransactionActive(false); }
        verify(consumer,never()).poll(any(Duration.class));
    }
}
