package io.github.devdooly.platformlab.jobs.messaging;

import io.github.devdooly.platformlab.jobs.CanonicalSource;
import io.github.devdooly.platformlab.jobs.LabJobService;
import io.github.devdooly.platformlab.jobs.S3RawSourceStore;
import io.github.devdooly.platformlab.jobs.VerifiedSourceReader;
import java.time.Duration;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Optional;
import java.util.Set;
import org.apache.kafka.clients.consumer.Consumer;
import org.apache.kafka.clients.consumer.ConsumerRecord;
import org.apache.kafka.clients.consumer.OffsetAndMetadata;
import org.apache.kafka.common.TopicPartition;
import org.springframework.transaction.IllegalTransactionStateException;
import org.springframework.transaction.support.TransactionSynchronizationManager;

/** Explicit, single-threaded one-record worker; no bean, scheduler, auto retry or public API. */
public final class DispatchWorker {
    public record Delivery(String topic, int partition, long offset, String runId, boolean replay, long nextOffset) {}
    public enum FailureCode {
        INVALID_MESSAGE, SOURCE_UNAVAILABLE, SOURCE_INVALID, JOB_REJECTED,
        PROCESSING_FAILED, OFFSET_COMMIT_FAILED, POLL_FAILED, OPERATOR_RESUME_REQUIRED
    }
    public static final class DeliveryPausedException extends IllegalStateException {
        private final FailureCode code;
        DeliveryPausedException(FailureCode code, Throwable cause) { super("Delivery paused: " + code, cause); this.code = code; }
        public FailureCode code() { return code; }
    }
    private final LabJobService jobs;
    private final VerifiedSourceReader sources;
    private final Consumer<String, String> consumer;
    private final String topic;
    private final java.util.function.Consumer<Delivery> afterDbCommit;
    private boolean paused;

    public DispatchWorker(LabJobService jobs, VerifiedSourceReader sources, Consumer<String, String> consumer, String topic) {
        this(jobs, sources, consumer, topic, ignored -> {});
    }

    // Package-private seam for process-termination experiments only; never application configuration.
    DispatchWorker(LabJobService jobs, VerifiedSourceReader sources, Consumer<String, String> consumer,
                   String topic, java.util.function.Consumer<Delivery> afterDbCommit) {
        this.jobs = Objects.requireNonNull(jobs);
        this.sources = Objects.requireNonNull(sources);
        this.consumer = Objects.requireNonNull(consumer);
        if (topic == null || !topic.matches("[a-zA-Z0-9._-]{1,249}") || topic.equals(".") || topic.equals("..")) {
            throw new IllegalArgumentException("An explicit Kafka topic is required");
        }
        this.topic = topic;
        this.afterDbCommit = Objects.requireNonNull(afterDbCommit);
        consumer.subscribe(List.of(topic));
    }

    public boolean isPaused() { return paused; }

    public Optional<Delivery> receiveOne(Duration pollTimeout) {
        if (TransactionSynchronizationManager.isActualTransactionActive()) {
            throw new IllegalTransactionStateException("Kafka receive must run outside a database transaction");
        }
        if (paused) { throw new DeliveryPausedException(FailureCode.OPERATOR_RESUME_REQUIRED, null); }
        if (pollTimeout == null || pollTimeout.isNegative() || pollTimeout.compareTo(Duration.ofSeconds(5)) > 0) {
            throw new IllegalArgumentException("Poll timeout must be between zero and five seconds");
        }
        org.apache.kafka.clients.consumer.ConsumerRecords<String, String> records;
        try { records = consumer.poll(pollTimeout); }
        catch (RuntimeException failure) { throw stop(FailureCode.POLL_FAILED, failure, null); }
        if (records.isEmpty()) { return Optional.empty(); }
        if (records.count() != 1) { throw stop(FailureCode.INVALID_MESSAGE, null, records.iterator().next()); }
        ConsumerRecord<String, String> record = records.iterator().next();
        DispatchMessage message;
        try {
            if (!topic.equals(record.topic()) || record.partition() != 0 || record.offset() < 0 || record.offset() == Long.MAX_VALUE) {
                throw new IllegalArgumentException("Unexpected Kafka record coordinates");
            }
            message = DispatchMessage.decode(record.value());
            if (!message.runId().equals(record.key())) { throw new IllegalArgumentException("Kafka key differs from job identity"); }
        } catch (RuntimeException failure) { throw stop(FailureCode.INVALID_MESSAGE, failure, record); }

        LabJobService.Job job;
        try {
            job = jobs.get(message.runId());
            if (!message.sourceSha256().equals(job.sourceSha256()) || !message.scenarioVersion().equals(job.scenarioVersion())
                || (job.status() != LabJobService.Status.QUEUED && job.status() != LabJobService.Status.COMPLETED)
                || job.terminatedAt() != null) {
                throw new IllegalStateException("Job metadata does not authorize this delivery");
            }
        } catch (RuntimeException failure) { throw stop(FailureCode.JOB_REJECTED, failure, record); }
        try {
            byte[] raw = sources.readAndVerify(job);
            var verified = CanonicalSource.validate(raw);
            if (verified.size() != job.sourceSize() || !verified.sha256().equals(job.sourceSha256())) {
                throw new IllegalArgumentException("Retrieved source differs from admitted metadata");
            }
        } catch (S3RawSourceStore.SourceVerificationException | IllegalArgumentException failure) {
            throw stop(FailureCode.SOURCE_INVALID, failure, record);
        } catch (RuntimeException failure) { throw stop(FailureCode.SOURCE_UNAVAILABLE, failure, record); }

        var delivery = new Delivery(record.topic(), record.partition(), record.offset(), job.runId(),
            job.status() == LabJobService.Status.COMPLETED, record.offset() + 1);
        try {
            // The immutable DB source is independently checked by process(); S3 verification used the same SHA above.
            var completed = jobs.process(job.runId(), job.sourceSha256());
            if (completed.status() != LabJobService.Status.COMPLETED) { throw new IllegalStateException("Processing did not complete"); }
            afterDbCommit.accept(delivery);
        } catch (RuntimeException failure) { throw stop(FailureCode.PROCESSING_FAILED, failure, record); }
        try {
            consumer.commitSync(Map.of(new TopicPartition(record.topic(), record.partition()),
                new OffsetAndMetadata(delivery.nextOffset())), Duration.ofSeconds(10));
        } catch (RuntimeException failure) { throw stop(FailureCode.OFFSET_COMMIT_FAILED, failure, record); }
        return Optional.of(delivery);
    }

    private DeliveryPausedException stop(FailureCode code, Throwable cause, ConsumerRecord<String, String> record) {
        paused = true;
        if (record != null) {
            try { consumer.seek(new TopicPartition(record.topic(), record.partition()), record.offset()); }
            catch (RuntimeException ignored) { /* Fail closed even if a disconnected consumer cannot rewind locally. */ }
        }
        try { consumer.pause(consumer.assignment()); }
        catch (RuntimeException ignored) { /* The paused flag forbids any later poll on this worker. */ }
        if (cause instanceof org.apache.kafka.common.errors.InterruptException) { Thread.currentThread().interrupt(); }
        return new DeliveryPausedException(code, cause);
    }
}
