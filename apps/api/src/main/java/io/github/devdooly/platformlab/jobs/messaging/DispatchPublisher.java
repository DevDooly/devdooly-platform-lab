package io.github.devdooly.platformlab.jobs.messaging;

import io.github.devdooly.platformlab.jobs.LabJobService;
import java.util.Objects;
import java.util.Optional;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;
import org.apache.kafka.clients.producer.Producer;
import org.apache.kafka.clients.producer.ProducerRecord;
import org.apache.kafka.clients.producer.RecordMetadata;
import org.springframework.transaction.IllegalTransactionStateException;
import org.springframework.transaction.support.TransactionSynchronizationManager;

/**
 * Explicit one-record outbox adapter. A crash after broker ACK and before DB acknowledgement
 * leaves a pending intent for replay; consumers must therefore tolerate duplicate delivery.
 */
public final class DispatchPublisher {
    private final LabJobService jobs;
    private final Producer<String, String> producer;
    private final String topic;
    private final java.util.function.Consumer<RecordMetadata> afterAck;

    public DispatchPublisher(LabJobService jobs, Producer<String, String> producer, String topic) {
        this(jobs, producer, topic, ignored -> {});
    }

    DispatchPublisher(LabJobService jobs, Producer<String, String> producer, String topic,
                      java.util.function.Consumer<RecordMetadata> afterAck) {
        this.jobs = Objects.requireNonNull(jobs, "jobs");
        this.producer = Objects.requireNonNull(producer, "producer");
        this.afterAck = Objects.requireNonNull(afterAck, "afterAck");
        if (topic == null || !topic.matches("[a-zA-Z0-9._-]{1,249}") || topic.equals(".") || topic.equals("..")) {
            throw new IllegalArgumentException("A valid explicit Kafka topic is required");
        }
        this.topic = topic;
    }

    public Optional<RecordMetadata> publishOne() throws InterruptedException, ExecutionException, TimeoutException {
        if (TransactionSynchronizationManager.isActualTransactionActive()) {
            throw new IllegalTransactionStateException("Kafka publication must run outside a database transaction");
        }
        var candidate = jobs.pendingOutbox(100).stream()
            .filter(event -> event.eventType() == LabJobService.EventType.DISPATCH).findFirst();
        if (candidate.isEmpty()) { return Optional.empty(); }
        var intent = candidate.get();
        var job = jobs.get(intent.runId());
        if (intent.status() != LabJobService.OutboxStatus.PENDING
            || !Objects.equals(intent.runId(), job.runId())
            || !Objects.equals(intent.sourceSha256(), job.sourceSha256())
            || (job.status() != LabJobService.Status.QUEUED && job.status() != LabJobService.Status.COMPLETED)
            || job.terminatedAt() != null) {
            throw new IllegalStateException("Dispatch intent no longer matches an active queued or completed job");
        }
        String payload = DispatchMessage.from(job).encode();
        final RecordMetadata metadata;
        try {
            metadata = producer.send(new ProducerRecord<>(topic, 0, job.runId(), payload)).get(15, TimeUnit.SECONDS);
        } catch (InterruptedException failure) {
            Thread.currentThread().interrupt();
            throw failure;
        }
        if (metadata == null || !topic.equals(metadata.topic()) || metadata.partition() != 0 || !metadata.hasOffset()) {
            throw new IllegalStateException("Broker acknowledgement does not match the requested topic and partition");
        }
        afterAck.accept(metadata);
        jobs.acknowledgeDispatch(job.runId(), job.sourceSha256());
        return Optional.of(metadata);
    }
}
