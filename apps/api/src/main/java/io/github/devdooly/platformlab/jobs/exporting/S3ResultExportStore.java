package io.github.devdooly.platformlab.jobs.exporting;

import java.util.Objects;
import org.springframework.transaction.IllegalTransactionStateException;
import org.springframework.transaction.support.TransactionSynchronizationManager;
import software.amazon.awssdk.core.exception.SdkClientException;
import software.amazon.awssdk.core.sync.RequestBody;
import software.amazon.awssdk.core.sync.ResponseTransformer;
import software.amazon.awssdk.services.s3.S3Client;
import software.amazon.awssdk.services.s3.model.GetObjectRequest;
import software.amazon.awssdk.services.s3.model.GetObjectResponse;
import software.amazon.awssdk.services.s3.model.PutObjectRequest;
import software.amazon.awssdk.services.s3.model.S3Exception;

/** Existing conflicts are never replaced or deleted. This is not a distributed writer lock/WORM. */
public final class S3ResultExportStore implements ResultExportStore {
    private final S3Client s3;
    private final String bucket;
    public S3ResultExportStore(S3Client s3, String bucket) {
        this.s3 = Objects.requireNonNull(s3);
        if (bucket == null || !bucket.matches("[a-z0-9][a-z0-9.-]{1,61}[a-z0-9]") || bucket.contains("..")) {
            throw new IllegalArgumentException("An explicit DNS-compatible bucket name is required");
        }
        this.bucket = bucket;
    }
    @Override public void storeAndVerify(ExportBundle.Document document) {
        if (TransactionSynchronizationManager.isActualTransactionActive()) {
            throw new IllegalTransactionStateException("Export storage I/O must not run inside a database transaction");
        }
        Objects.requireNonNull(document);
        if (verify(document, true)) { return; }
        s3.putObject(PutObjectRequest.builder().bucket(bucket).key(document.key()).contentType("application/json")
            .contentLength((long) document.size()).build(), RequestBody.fromBytes(document.bytes()));
        verify(document, false);
    }
    private boolean verify(ExportBundle.Document expected, boolean allowMissing) {
        try {
            ResponseTransformer<GetObjectResponse, byte[]> transformer = (response, input) -> {
                Long declared = response.contentLength();
                if (declared == null || declared != expected.size() || declared > ExportBundle.MAX_DOCUMENT_BYTES) {
                    input.abort(); throw new ExportVerificationException("Stored export declared size differs");
                }
                byte[] actual = input.readNBytes(ExportBundle.MAX_DOCUMENT_BYTES + 1);
                if (actual.length != declared || actual.length > ExportBundle.MAX_DOCUMENT_BYTES) {
                    input.abort(); throw new ExportVerificationException("Stored export body size differs");
                }
                return actual;
            };
            byte[] actual = s3.getObject(GetObjectRequest.builder().bucket(bucket).key(expected.key()).build(), transformer);
            if (!expected.matches(actual)) { throw new ExportVerificationException("Stored export bytes or SHA-256 differ"); }
            return true;
        } catch (S3Exception failure) {
            if (allowMissing && failure.statusCode() == 404 && failure.awsErrorDetails() != null
                && "NoSuchKey".equals(failure.awsErrorDetails().errorCode())) { return false; }
            throw failure;
        } catch (SdkClientException failure) {
            for (Throwable cause = failure.getCause(); cause != null; cause = cause.getCause()) {
                if (cause instanceof ExportVerificationException invalid) { throw invalid; }
            }
            throw failure;
        }
    }
    public static final class ExportVerificationException extends IllegalStateException {
        public ExportVerificationException(String message) { super(message); }
    }
}
