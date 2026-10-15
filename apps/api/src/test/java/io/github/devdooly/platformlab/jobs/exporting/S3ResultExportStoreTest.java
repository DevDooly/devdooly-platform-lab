package io.github.devdooly.platformlab.jobs.exporting;

import java.io.ByteArrayInputStream;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.util.Arrays;
import java.util.HexFormat;
import java.util.concurrent.atomic.AtomicInteger;
import org.junit.jupiter.api.Test;
import software.amazon.awssdk.awscore.exception.AwsErrorDetails;
import software.amazon.awssdk.core.exception.SdkClientException;
import software.amazon.awssdk.core.sync.RequestBody;
import software.amazon.awssdk.core.sync.ResponseTransformer;
import software.amazon.awssdk.http.AbortableInputStream;
import software.amazon.awssdk.services.s3.S3Client;
import software.amazon.awssdk.services.s3.model.GetObjectRequest;
import software.amazon.awssdk.services.s3.model.GetObjectResponse;
import software.amazon.awssdk.services.s3.model.PutObjectRequest;
import software.amazon.awssdk.services.s3.model.S3Exception;
import static org.assertj.core.api.Assertions.*;
import static org.mockito.ArgumentMatchers.*;
import static org.mockito.Mockito.*;

class S3ResultExportStoreTest {
    private static final String BUCKET = "platform-lab-s3-test-export-unit";
    private final S3Client s3 = mock(S3Client.class);
    private final S3ResultExportStore store = new S3ResultExportStore(s3, BUCKET);
    private final byte[] bytes = "{\"schemaVersion\":1}".getBytes(StandardCharsets.UTF_8);
    private final ExportBundle.Document document = document(bytes);

    @Test void noSuchKeyCreatesJsonAndVerifiesItsEntireBody() throws Exception {
        stub(error(404, "NoSuchKey"), body(bytes, bytes.length)); store.storeAndVerify(document);
        var request = org.mockito.ArgumentCaptor.forClass(PutObjectRequest.class); var body = org.mockito.ArgumentCaptor.forClass(RequestBody.class);
        verify(s3).putObject(request.capture(), body.capture());
        assertThat(request.getValue().key()).isEqualTo(document.key()); assertThat(request.getValue().bucket()).isEqualTo(BUCKET);
        assertThat(request.getValue().contentType()).isEqualTo("application/json");
        assertThat(request.getValue().contentLength()).isEqualTo((long) bytes.length);
        assertThat(body.getValue().contentStreamProvider().newStream()).hasBinaryContent(bytes);
        verify(s3, times(2)).getObject(any(GetObjectRequest.class), transformer()); verifyNoMoreInteractions(s3);
    }
    @Test void existingExactDocumentIsGetOnly() {
        stub(body(bytes, bytes.length)); store.storeAndVerify(document);
        verify(s3).getObject(any(GetObjectRequest.class), transformer()); verifyNoMoreInteractions(s3);
    }
    @Test void existingConflictIsNeverOverwrittenOrDeleted() {
        byte[] corrupt = bytes.clone(); corrupt[2] ^= 1; stub(body(corrupt, bytes.length));
        assertThatThrownBy(() -> store.storeAndVerify(document)).isInstanceOf(S3ResultExportStore.ExportVerificationException.class);
        verify(s3).getObject(any(GetObjectRequest.class), transformer()); verifyNoMoreInteractions(s3);
    }
    @Test void onlyNoSuchKey404MayCreateAnObject() {
        for (var failure : new S3Exception[] {error(404, "NoSuchBucket"), error(404, "AccessDenied"), error(403, "AccessDenied"), error(500, "InternalError"), error(400, "NoSuchKey")}) {
            reset(s3); stub(failure);
            assertThatThrownBy(() -> store.storeAndVerify(document)).isSameAs(failure);
            verify(s3).getObject(any(GetObjectRequest.class), transformer()); verifyNoMoreInteractions(s3);
        }
    }
    @Test void missingLengthOversizeTruncatedAndLongBodiesFailClosed() {
        for (var reply : java.util.List.of(body(bytes, null), body(bytes, (long) ExportBundle.MAX_DOCUMENT_BYTES + 1),
            body(Arrays.copyOf(bytes, bytes.length - 1), bytes.length), body(Arrays.copyOf(bytes, bytes.length + 1), bytes.length))) {
            reset(s3); stub(reply);
            assertThatThrownBy(() -> store.storeAndVerify(document)).isInstanceOf(S3ResultExportStore.ExportVerificationException.class);
            verify(s3).getObject(any(GetObjectRequest.class), transformer()); verifyNoMoreInteractions(s3);
        }
    }
    @Test void readBackFailureAfterPutCanRetryWithoutSecondPut() {
        stub(error(404, "NoSuchKey"), error(500, "InternalError"), body(bytes, bytes.length));
        assertThatThrownBy(() -> store.storeAndVerify(document)).isInstanceOf(S3Exception.class);
        store.storeAndVerify(document);
        verify(s3, times(3)).getObject(any(GetObjectRequest.class), transformer());
        verify(s3).putObject(any(PutObjectRequest.class), any(RequestBody.class)); verifyNoMoreInteractions(s3);
    }
    @Test void sdkWrappedVerificationFailureRetainsDeterministicErrorContract() {
        var cause = new S3ResultExportStore.ExportVerificationException("bad size");
        stub(SdkClientException.builder().message("managed transform").cause(cause).build());
        assertThatThrownBy(() -> store.storeAndVerify(document)).isSameAs(cause);
        verify(s3).getObject(any(GetObjectRequest.class), transformer()); verifyNoMoreInteractions(s3);
    }
    @Test void invalidBoundsHashAndKeyAreRefusedBeforeNetwork() {
        assertThatThrownBy(() -> new ExportBundle.Document(document.key(), new byte[0], document.sha256())).isInstanceOf(IllegalArgumentException.class);
        assertThatThrownBy(() -> new ExportBundle.Document(document.key(), new byte[ExportBundle.MAX_DOCUMENT_BYTES + 1], document.sha256())).isInstanceOf(IllegalArgumentException.class);
        assertThatThrownBy(() -> new ExportBundle.Document(document.key(), bytes, "0".repeat(64))).isInstanceOf(IllegalArgumentException.class);
        assertThatThrownBy(() -> new ExportBundle.Document("../escape", bytes, document.sha256())).isInstanceOf(IllegalArgumentException.class);
        assertThatThrownBy(() -> new S3ResultExportStore(s3, "bad/bucket")).isInstanceOf(IllegalArgumentException.class);
        verifyNoInteractions(s3);
    }
    @Test void directStorageInvocationAlsoRefusesAmbientDatabaseTransaction() {
        org.springframework.transaction.support.TransactionSynchronizationManager.setActualTransactionActive(true);
        try {
            assertThatThrownBy(() -> store.storeAndVerify(document)).isInstanceOf(org.springframework.transaction.IllegalTransactionStateException.class);
            verifyNoInteractions(s3);
        } finally { org.springframework.transaction.support.TransactionSynchronizationManager.setActualTransactionActive(false); }
    }
    private void stub(Object... replies) {
        var index = new AtomicInteger();
        when(s3.getObject(any(GetObjectRequest.class), transformer())).thenAnswer(invocation -> {
            Object reply = replies[index.getAndIncrement()]; if (reply instanceof RuntimeException failure) { throw failure; }
            var stored = (StoredBody) reply; ResponseTransformer<GetObjectResponse, byte[]> transform = invocation.getArgument(1);
            assertThat(transform.needsConnectionLeftOpen()).isFalse();
            return transform.transform(GetObjectResponse.builder().contentLength(stored.declared()).build(), AbortableInputStream.create(new ByteArrayInputStream(stored.bytes())));
        });
    }
    private record StoredBody(byte[] bytes, Long declared) {}
    private static StoredBody body(byte[] bytes, long declared) { return new StoredBody(bytes, declared); }
    private static StoredBody body(byte[] bytes, Long declared) { return new StoredBody(bytes, declared); }
    private static ResponseTransformer<GetObjectResponse, byte[]> transformer() { return any(); }
    private static S3Exception error(int status, String code) { return (S3Exception) S3Exception.builder().statusCode(status).awsErrorDetails(AwsErrorDetails.builder().errorCode(code).build()).build(); }
    private static ExportBundle.Document document(byte[] bytes) {
        try {
            String hash = HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(bytes));
            return new ExportBundle.Document("result/export-unit/sensor-validation-v1/" + "a".repeat(64) + "/result-v1-" + hash + ".json", bytes, hash);
        } catch (Exception failure) { throw new IllegalStateException(failure); }
    }
}
