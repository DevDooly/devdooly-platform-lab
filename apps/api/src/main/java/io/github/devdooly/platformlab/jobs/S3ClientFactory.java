package io.github.devdooly.platformlab.jobs;

import java.net.URI;
import java.time.Duration;
import java.util.Objects;
import software.amazon.awssdk.auth.credentials.AwsCredentialsProvider;
import software.amazon.awssdk.core.checksums.RequestChecksumCalculation;
import software.amazon.awssdk.http.apache5.Apache5HttpClient;
import software.amazon.awssdk.regions.Region;
import software.amazon.awssdk.retries.StandardRetryStrategy;
import software.amazon.awssdk.services.s3.S3Client;
import software.amazon.awssdk.services.s3.S3Configuration;

/** Explicit construction only: no default credential chain, metadata lookup, or application wiring. */
public final class S3ClientFactory {
    public record Timeouts(Duration apiCall, Duration attempt, Duration connect, Duration read) {
        public Timeouts {
            for (Duration value : new Duration[] {apiCall, attempt, connect, read}) {
                if (value == null || value.isZero() || value.isNegative()) {
                    throw new IllegalArgumentException("S3 timeouts must be positive");
                }
            }
            if (attempt.compareTo(apiCall) > 0 || connect.compareTo(attempt) > 0 || read.compareTo(attempt) > 0) {
                throw new IllegalArgumentException("S3 transport timeouts must fit the attempt and API call limits");
            }
        }
        public static Timeouts boundedDefaults() {
            return new Timeouts(Duration.ofSeconds(30), Duration.ofSeconds(10),
                Duration.ofSeconds(3), Duration.ofSeconds(8));
        }
    }

    private S3ClientFactory() {}

    public static S3Client create(URI endpoint, String region, AwsCredentialsProvider credentials) {
        return create(endpoint, region, credentials, Timeouts.boundedDefaults());
    }

    /** Standard SDK checksum policies remain unchanged. */
    public static S3Client create(URI endpoint, String region, AwsCredentialsProvider credentials, Timeouts timeouts) {
        return build(endpoint, region, credentials, timeouts, false);
    }

    public static S3Client createGarage(URI endpoint, String region, AwsCredentialsProvider credentials) {
        return createGarage(endpoint, region, credentials, Timeouts.boundedDefaults());
    }

    /**
     * Explicit Garage compatibility choice after the default streaming-checksum PUT failed.
     * Only optional request checksums change; response checksum validation stays at the SDK default.
     */
    public static S3Client createGarage(URI endpoint, String region, AwsCredentialsProvider credentials, Timeouts timeouts) {
        return build(endpoint, region, credentials, timeouts, true);
    }

    private static S3Client build(URI endpoint, String region, AwsCredentialsProvider credentials,
                                 Timeouts timeouts, boolean garageCompatibility) {
        validateEndpoint(endpoint);
        if (region == null || region.isBlank()) { throw new IllegalArgumentException("An explicit S3 region is required"); }
        Objects.requireNonNull(credentials, "An explicit credentials provider is required");
        Objects.requireNonNull(timeouts, "Explicit timeouts are required");
        var builder = S3Client.builder().endpointOverride(endpoint).region(Region.of(region))
            .credentialsProvider(credentials)
            .serviceConfiguration(S3Configuration.builder().pathStyleAccessEnabled(true).build())
            .httpClientBuilder(Apache5HttpClient.builder()
                .connectionTimeout(timeouts.connect()).socketTimeout(timeouts.read()))
            .overrideConfiguration(override -> override.apiCallTimeout(timeouts.apiCall())
                .apiCallAttemptTimeout(timeouts.attempt())
                .retryStrategy(StandardRetryStrategy.builder().maxAttempts(3).build()));
        if (garageCompatibility) { builder.requestChecksumCalculation(RequestChecksumCalculation.WHEN_REQUIRED); }
        return builder.build();
    }

    static void validateEndpoint(URI endpoint) {
        if (endpoint == null || !endpoint.isAbsolute() || endpoint.getHost() == null
            || endpoint.getUserInfo() != null || endpoint.getQuery() != null || endpoint.getFragment() != null
            || (endpoint.getRawPath() != null && !endpoint.getRawPath().isEmpty() && !endpoint.getRawPath().equals("/"))) {
            throw new IllegalArgumentException("S3 endpoint must be an absolute origin without credentials, query, or path");
        }
        boolean https = "https".equalsIgnoreCase(endpoint.getScheme());
        boolean loopbackHttp = "http".equalsIgnoreCase(endpoint.getScheme())
            && ("127.0.0.1".equals(endpoint.getHost()) || "[::1]".equals(endpoint.getHost()) || "::1".equals(endpoint.getHost()));
        boolean serviceHttp = "http".equalsIgnoreCase(endpoint.getScheme())
            && LabClientEndpoints.isKubernetesService(endpoint.getHost()) && endpoint.getPort() > 0;
        if (!https && !loopbackHttp && !serviceHttp) {
            throw new IllegalArgumentException("S3 endpoint requires HTTPS, numeric-loopback HTTP, or explicit-port Kubernetes service HTTP");
        }
        if (endpoint.getPort() == 0 || endpoint.getPort() < -1 || endpoint.getPort() > 65535) {
            throw new IllegalArgumentException("S3 endpoint has an invalid port");
        }
    }
}
