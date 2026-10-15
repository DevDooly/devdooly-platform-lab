package io.github.devdooly.platformlab.jobs;

import io.github.devdooly.platformlab.demo.SyntheticScenario;
import java.io.ByteArrayInputStream;
import java.time.Instant;
import org.junit.jupiter.api.Test;
import software.amazon.awssdk.core.sync.RequestBody;
import software.amazon.awssdk.core.sync.ResponseTransformer;
import software.amazon.awssdk.http.AbortableInputStream;
import software.amazon.awssdk.services.s3.S3Client;
import software.amazon.awssdk.services.s3.model.GetObjectRequest;
import software.amazon.awssdk.services.s3.model.GetObjectResponse;
import software.amazon.awssdk.services.s3.model.PutObjectRequest;
import static org.assertj.core.api.Assertions.*;
import static org.mockito.ArgumentMatchers.*;
import static org.mockito.Mockito.*;

class MaximumS3RawSourceStoreTest {
    @Test void maximumScenarioUsesAdmittedVersionForBothWriteVerificationAndGetOnlyRead() throws Exception {
        byte[] bytes = CanonicalSource.fixtureBytes(SyntheticScenario.MAXIMUM_NAME);
        var source = CanonicalSource.validate(SyntheticScenario.MAXIMUM_NAME, bytes);
        var job = job(SyntheticScenario.MAXIMUM_NAME, source);
        var s3 = mock(S3Client.class); var store = new S3RawSourceStore(s3, "maximum-unit-bucket");
        when(s3.getObject(any(GetObjectRequest.class), org.mockito.ArgumentMatchers.<ResponseTransformer<GetObjectResponse, byte[]>>any()))
            .thenAnswer(invocation -> {
                ResponseTransformer<GetObjectResponse, byte[]> transform = invocation.getArgument(1);
                return transform.transform(GetObjectResponse.builder().contentLength((long) bytes.length).build(), AbortableInputStream.create(new ByteArrayInputStream(bytes)));
            });
        store.storeAndVerify(job, bytes); assertThat(store.readAndVerify(job)).isEqualTo(bytes);
        verify(s3, times(2)).getObject(any(GetObjectRequest.class), org.mockito.ArgumentMatchers.<ResponseTransformer<GetObjectResponse, byte[]>>any());
        verify(s3, never()).putObject(any(PutObjectRequest.class), any(RequestBody.class));
        assertThatThrownBy(() -> store.storeAndVerify(job("sensor-validation-v1", source), bytes)).isInstanceOf(IllegalArgumentException.class);
        verifyNoMoreInteractions(s3);
    }

    private LabJobService.Job job(String scenario, CanonicalSource source) {
        return new LabJobService.Job("maximum-s3-unit", scenario, source.sha256(), source.size(), LabJobService.Status.STAGING,
            LabJobService.ExportStatus.NOT_REQUESTED, Instant.parse("2026-01-01T00:00:00Z"), null, null, null, null, null);
    }
}
