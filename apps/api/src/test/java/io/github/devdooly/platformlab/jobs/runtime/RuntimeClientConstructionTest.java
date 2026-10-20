package io.github.devdooly.platformlab.jobs.runtime;

import io.github.devdooly.platformlab.jobs.S3ClientFactory;
import io.github.devdooly.platformlab.jobs.messaging.KafkaClientFactory;
import java.net.URI;
import java.time.Duration;
import org.apache.kafka.clients.consumer.Consumer;
import org.apache.kafka.clients.producer.Producer;
import org.junit.jupiter.api.Test;
import org.mockito.MockedStatic;
import software.amazon.awssdk.auth.credentials.StaticCredentialsProvider;
import software.amazon.awssdk.services.s3.S3Client;
import static org.assertj.core.api.Assertions.*;
import static org.mockito.Mockito.*;

/** Static factories are replaced before invocation; no S3, Kafka, DB or Spring context is started. */
@SuppressWarnings("unchecked")
class RuntimeClientConstructionTest {
    private static final URI ENDPOINT = URI.create("http://127.0.0.1:19000");
    private static final String REGION = "synthetic-region", BOOTSTRAP = "127.0.0.1:19092", GROUP = "synthetic-group";
    private static final Duration CLOSE_TIMEOUT = Duration.ofSeconds(10);
    private final StaticCredentialsProvider credentials = mock(StaticCredentialsProvider.class);
    private final S3Client s3 = mock(S3Client.class);
    private final Producer<String, String> producer = mock(Producer.class);
    private final Consumer<String, String> consumer = mock(Consumer.class);

    private void s3Returns(MockedStatic<S3ClientFactory> factory) {
        factory.when(() -> S3ClientFactory.createGarage(ENDPOINT, REGION, credentials)).thenReturn(s3);
    }
    private void producerReturns(MockedStatic<KafkaClientFactory> factory) {
        factory.when(() -> KafkaClientFactory.producer(BOOTSTRAP)).thenReturn(producer);
    }
    private RuntimeMain.Clients open() { return RuntimeMain.openClients(ENDPOINT, REGION, credentials, BOOTSTRAP, GROUP); }

    @Test void producerConstructionErrorClosesTheAlreadyReturnedS3ClientAndPropagatesTheSameError() {
        var error = new AssertionError("private producer construction detail");
        try (var s3Factory = mockStatic(S3ClientFactory.class); var kafkaFactory = mockStatic(KafkaClientFactory.class)) {
            s3Returns(s3Factory);
            kafkaFactory.when(() -> KafkaClientFactory.producer(BOOTSTRAP)).thenThrow(error);
            assertThatThrownBy(this::open).isSameAs(error);
            verify(s3, times(1)).close(); verifyNoMoreInteractions(s3); verifyNoInteractions(producer, consumer);
            kafkaFactory.verify(() -> KafkaClientFactory.consumerForRuntime(BOOTSTRAP, GROUP), never());
            assertThat(error.getCause()).isNull(); assertThat(error.getSuppressed()).isEmpty();
        }
    }

    @Test void consumerConstructionErrorClosesOnlyReturnedClientsInReverseOrder() {
        var error = new AssertionError("private consumer construction detail");
        try (var s3Factory = mockStatic(S3ClientFactory.class); var kafkaFactory = mockStatic(KafkaClientFactory.class)) {
            s3Returns(s3Factory); producerReturns(kafkaFactory);
            kafkaFactory.when(() -> KafkaClientFactory.consumerForRuntime(BOOTSTRAP, GROUP)).thenThrow(error);
            assertThatThrownBy(this::open).isSameAs(error);
            var order = inOrder(producer, s3); order.verify(producer).close(CLOSE_TIMEOUT); order.verify(s3).close();
            verifyNoMoreInteractions(producer, s3); verifyNoInteractions(consumer);
            assertThat(error.getSuppressed()).isEmpty();
        }
    }

    @Test void constructionErrorRemainsPrimaryAfterBothErrorAndOrdinaryCleanupFailures() {
        var original = new AssertionError("private construction detail");
        var cleanup = new AssertionError("private producer close detail");
        doThrow(cleanup).when(producer).close(CLOSE_TIMEOUT);
        doThrow(new IllegalStateException("private S3 close detail")).when(s3).close();
        try (var s3Factory = mockStatic(S3ClientFactory.class); var kafkaFactory = mockStatic(KafkaClientFactory.class)) {
            s3Returns(s3Factory); producerReturns(kafkaFactory);
            kafkaFactory.when(() -> KafkaClientFactory.consumerForRuntime(BOOTSTRAP, GROUP)).thenThrow(original);
            assertThatThrownBy(this::open).isSameAs(original);
            var order = inOrder(producer, s3); order.verify(producer).close(CLOSE_TIMEOUT); order.verify(s3).close();
            verifyNoMoreInteractions(producer, s3); verifyNoInteractions(consumer);
            assertThat(original.getCause()).isNull(); assertThat(original.getSuppressed()).isEmpty();
            assertThat(cleanup.getSuppressed()).isEmpty();
        }
    }

    @Test void aCleanupErrorAfterAnOrdinaryConstructionAndCloseFailureIsStillFatal() {
        var fatal = new AssertionError("private S3 close detail");
        doThrow(new IllegalArgumentException("private producer close detail")).when(producer).close(CLOSE_TIMEOUT);
        doThrow(fatal).when(s3).close();
        try (var s3Factory = mockStatic(S3ClientFactory.class); var kafkaFactory = mockStatic(KafkaClientFactory.class)) {
            s3Returns(s3Factory); producerReturns(kafkaFactory);
            kafkaFactory.when(() -> KafkaClientFactory.consumerForRuntime(BOOTSTRAP, GROUP))
                .thenThrow(new IllegalStateException("private consumer construction detail"));
            assertThatThrownBy(this::open).isSameAs(fatal);
            var order = inOrder(producer, s3); order.verify(producer).close(CLOSE_TIMEOUT); order.verify(s3).close();
            verifyNoMoreInteractions(producer, s3); verifyNoInteractions(consumer);
            assertThat(fatal.getCause()).isNull(); assertThat(fatal.getSuppressed()).isEmpty();
        }
    }

    @Test void theFirstCleanupErrorWinsWhenOrdinaryConstructionFailureIsFollowedByTwoErrors() {
        var first = new AssertionError("private producer close detail");
        var later = new AssertionError("private S3 close detail");
        doThrow(first).when(producer).close(CLOSE_TIMEOUT); doThrow(later).when(s3).close();
        try (var s3Factory = mockStatic(S3ClientFactory.class); var kafkaFactory = mockStatic(KafkaClientFactory.class)) {
            s3Returns(s3Factory); producerReturns(kafkaFactory);
            kafkaFactory.when(() -> KafkaClientFactory.consumerForRuntime(BOOTSTRAP, GROUP))
                .thenThrow(new IllegalStateException("private consumer construction detail"));
            assertThatThrownBy(this::open).isSameAs(first);
            var order = inOrder(producer, s3); order.verify(producer).close(CLOSE_TIMEOUT); order.verify(s3).close();
            verifyNoMoreInteractions(producer, s3); verifyNoInteractions(consumer);
            assertThat(first.getCause()).isNull(); assertThat(first.getSuppressed()).isEmpty();
        }
    }

    @Test void ordinaryConstructionAndCleanupFailuresExposeOnlyTheFixedCauseFreeConstructionMessage() {
        doThrow(new IllegalStateException("private producer close detail")).when(producer).close(CLOSE_TIMEOUT);
        doThrow(new IllegalArgumentException("private S3 close detail")).when(s3).close();
        try (var s3Factory = mockStatic(S3ClientFactory.class); var kafkaFactory = mockStatic(KafkaClientFactory.class)) {
            s3Returns(s3Factory); producerReturns(kafkaFactory);
            kafkaFactory.when(() -> KafkaClientFactory.consumerForRuntime(BOOTSTRAP, GROUP))
                .thenThrow(new IllegalArgumentException("private consumer connection detail"));
            assertThatThrownBy(this::open).isExactlyInstanceOf(IllegalStateException.class)
                .hasMessage("Runtime clients could not be constructed").hasCause(null)
                .satisfies(failure -> assertThat(failure.getSuppressed()).isEmpty());
            var order = inOrder(producer, s3); order.verify(producer).close(CLOSE_TIMEOUT); order.verify(s3).close();
            verifyNoMoreInteractions(producer, s3); verifyNoInteractions(consumer);
        }
    }

    @Test void successfulConstructionClosesConsumerProducerAndS3OnceEvenWhenOuterCloseRepeats() {
        try (var s3Factory = mockStatic(S3ClientFactory.class); var kafkaFactory = mockStatic(KafkaClientFactory.class)) {
            s3Returns(s3Factory); producerReturns(kafkaFactory);
            kafkaFactory.when(() -> KafkaClientFactory.consumerForRuntime(BOOTSTRAP, GROUP)).thenReturn(consumer);
            var clients = open();
            assertThat(clients.s3()).isSameAs(s3); assertThat(clients.producer()).isSameAs(producer); assertThat(clients.consumer()).isSameAs(consumer);
            clients.close(); clients.close();
            var order = inOrder(consumer, producer, s3);
            order.verify(consumer).close(CLOSE_TIMEOUT); order.verify(producer).close(CLOSE_TIMEOUT); order.verify(s3).close();
            verifyNoMoreInteractions(consumer, producer, s3);
            s3Factory.verify(() -> S3ClientFactory.createGarage(ENDPOINT, REGION, credentials), times(1));
            kafkaFactory.verify(() -> KafkaClientFactory.producer(BOOTSTRAP), times(1));
            kafkaFactory.verify(() -> KafkaClientFactory.consumerForRuntime(BOOTSTRAP, GROUP), times(1));
        }
    }
}
