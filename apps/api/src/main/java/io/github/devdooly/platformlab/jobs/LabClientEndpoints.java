package io.github.devdooly.platformlab.jobs;

import java.util.regex.Pattern;

/** Configuration validation only; service DNS does not replace ClusterIP/network access policy. */
public final class LabClientEndpoints {
    private static final String LABEL = "[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?";
    private static final Pattern SERVICE = Pattern.compile(LABEL + "\\." + LABEL + "\\.svc\\.cluster\\.local");
    private static final Pattern PORT = Pattern.compile("[0-9]{1,5}");
    private LabClientEndpoints() {}

    /** Only full, lowercase service.namespace.svc.cluster.local origins are internal plaintext candidates. */
    public static boolean isKubernetesService(String host) {
        return host != null && SERVICE.matcher(host).matches();
    }

    public static void requireKafkaBootstrap(String bootstrap) {
        int colon = bootstrap == null ? -1 : bootstrap.lastIndexOf(':');
        if (colon < 1) { throw invalidBootstrap(); }
        String host = bootstrap.substring(0, colon), port = bootstrap.substring(colon + 1);
        if ((!host.equals("127.0.0.1") && !isKubernetesService(host)) || !PORT.matcher(port).matches()) {
            throw invalidBootstrap();
        }
        int number = Integer.parseInt(port);
        if (number < 1 || number > 65535) { throw invalidBootstrap(); }
    }
    private static IllegalArgumentException invalidBootstrap() {
        return new IllegalArgumentException("Kafka requires one explicit numeric-loopback or full Kubernetes service DNS host and port");
    }
}
