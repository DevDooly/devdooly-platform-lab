package io.github.devdooly.platformlab.jobs;

import java.util.Objects;
import software.amazon.awssdk.core.exception.SdkClientException;
import software.amazon.awssdk.core.sync.RequestBody;
import software.amazon.awssdk.core.sync.ResponseTransformer;
import software.amazon.awssdk.services.s3.S3Client;
import software.amazon.awssdk.services.s3.model.GetObjectRequest;
import software.amazon.awssdk.services.s3.model.GetObjectResponse;
import software.amazon.awssdk.services.s3.model.PutObjectRequest;
import software.amazon.awssdk.services.s3.model.S3Exception;

/**
 * Full-byte, size and SHA-256 verification for a bounded raw object.
 * This is not a conditional create, distributed writer lock, or WORM guarantee. Concurrent
 * legitimate retries for one admitted run may PUT the same bytes; other writers are excluded
 * by operational policy. An observed conflicting object is never overwritten or deleted here.
 */
public final class S3RawSourceStore implements RawSourceStore, VerifiedSourceReader {
    private final S3Client s3;
    private final String bucket;

    public S3RawSourceStore(S3Client s3, String bucket) {
        this.s3 = Objects.requireNonNull(s3, "S3 client is required");
        if (bucket == null || !bucket.matches("[a-z0-9][a-z0-9.-]{1,61}[a-z0-9]")
            || bucket.contains("..")) {
            throw new IllegalArgumentException("An explicit DNS-compatible bucket name is required");
        }
        this.bucket = bucket;
    }

    @Override
    public void storeAndVerify(LabJobService.Job job, byte[] rawNdjson) {
        Objects.requireNonNull(job, "Prepared job is required");
        if (job.runId() == null || !job.runId().matches("[a-z0-9][a-z0-9._-]{0,79}")) {
            throw new IllegalArgumentException("Invalid raw object run ID");
        }
        var source = CanonicalSource.validate(job.scenarioVersion(), rawNdjson);
        if (source.size() != job.sourceSize() || !source.sha256().equals(job.sourceSha256())) {
            throw new SourceVerificationException("Prepared source metadata differs from the supplied bytes");
        }
        String key = job.sourceObjectKey();
        if (readAndVerify(key, source, true)) { return; }
        // A failed read-back leaves this object available for a later verification-only retry.
        s3.putObject(PutObjectRequest.builder().bucket(bucket).key(key)
            .contentType("application/x-ndjson").contentLength((long) source.size()).build(),
            RequestBody.fromBytes(source.bytes()));
        readAndVerify(key, source, false);
    }

    /** Bounded GET only: a missing or invalid source is never replaced using DB or fixture bytes. */
    @Override
    public byte[] readAndVerify(LabJobService.Job job) {
        Objects.requireNonNull(job, "Admitted job is required");
        if (job.runId() == null || !job.runId().matches("[a-z0-9][a-z0-9._-]{0,79}")
            || job.sourceSha256() == null || !job.sourceSha256().matches("[a-f0-9]{64}")
            || !io.github.devdooly.platformlab.demo.SyntheticScenario.supports(job.scenarioVersion())
            || job.sourceSize() < 1 || job.sourceSize() > CanonicalSource.MAX_BYTES) {
            throw new IllegalArgumentException("Invalid admitted source metadata");
        }
        try {
            ResponseTransformer<GetObjectResponse, byte[]> boundedBody = (response, input) -> {
                Long declared = response.contentLength();
                if (declared == null || declared != job.sourceSize() || declared > CanonicalSource.MAX_BYTES) {
                    input.abort();
                    throw new SourceVerificationException("Stored source declared size differs from admitted metadata");
                }
                byte[] actual = input.readNBytes(CanonicalSource.MAX_BYTES + 1);
                if (actual.length != declared || actual.length > CanonicalSource.MAX_BYTES) {
                    input.abort();
                    throw new SourceVerificationException("Stored source actual size differs from admitted metadata");
                }
                return actual;
            };
            byte[] actual = s3.getObject(GetObjectRequest.builder().bucket(bucket).key(job.sourceObjectKey()).build(), boundedBody);
            final CanonicalSource verified;
            try { verified = CanonicalSource.validate(job.scenarioVersion(), actual); }
            catch (IllegalArgumentException invalid) { throw new SourceVerificationException("Stored source is not the admitted scenario", invalid); }
            if (verified.size() != job.sourceSize() || !verified.sha256().equals(job.sourceSha256())) {
                throw new SourceVerificationException("Stored source hash differs from admitted metadata");
            }
            return verified.bytes();
        } catch (SdkClientException failure) {
            for (Throwable cause = failure.getCause(); cause != null; cause = cause.getCause()) {
                if (cause instanceof SourceVerificationException invalid) { throw invalid; }
            }
            throw failure;
        }
    }

    private boolean readAndVerify(String key, CanonicalSource expected, boolean allowMissing) {
        try {
            // Managed transformation includes the entire bounded body read in the SDK API deadline.
            ResponseTransformer<GetObjectResponse, byte[]> boundedBody = (response, input) -> {
                Long declaredSize = response.contentLength();
                if (declaredSize == null || declaredSize < 0 || declaredSize > CanonicalSource.MAX_BYTES
                    || declaredSize != expected.size()) {
                    input.abort();
                    throw new SourceVerificationException("Stored object declared size differs from the prepared source");
                }
                byte[] actual = input.readNBytes(CanonicalSource.MAX_BYTES + 1);
                if (actual.length > CanonicalSource.MAX_BYTES || actual.length != declaredSize) {
                    input.abort();
                    throw new SourceVerificationException("Stored object actual size differs from the prepared source");
                }
                return actual;
            };
            byte[] actual = s3.getObject(GetObjectRequest.builder().bucket(bucket).key(key).build(), boundedBody);
            if (!expected.matches(actual)) {
                throw new SourceVerificationException("Stored object bytes differ from the prepared source");
            }
            var verified = CanonicalSource.validate(expected.scenarioVersion(), actual);
            if (!verified.sha256().equals(expected.sha256()) || verified.size() != expected.size()) {
                throw new SourceVerificationException("Stored object hash differs from the prepared source");
            }
            return true;
        } catch (S3Exception failure) {
            if (allowMissing && failure.statusCode() == 404 && failure.awsErrorDetails() != null
                && "NoSuchKey".equals(failure.awsErrorDetails().errorCode())) {
                return false;
            }
            throw failure;
        } catch (SdkClientException failure) {
            // SDK wraps transformer exceptions; retain our deterministic validation-error contract.
            for (Throwable cause = failure.getCause(); cause != null; cause = cause.getCause()) {
                if (cause instanceof SourceVerificationException invalid) { throw invalid; }
            }
            throw failure;
        }
    }

    public static final class SourceVerificationException extends IllegalStateException {
        public SourceVerificationException(String message) { super(message); }
        public SourceVerificationException(String message, Throwable cause) { super(message, cause); }
    }
}
