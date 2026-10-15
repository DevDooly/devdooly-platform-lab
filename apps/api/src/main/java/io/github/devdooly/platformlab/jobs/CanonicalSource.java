package io.github.devdooly.platformlab.jobs;

import io.github.devdooly.platformlab.demo.SensorEvent;
import io.github.devdooly.platformlab.demo.SyntheticScenario;
import java.nio.ByteBuffer;
import java.nio.charset.CharacterCodingException;
import java.nio.charset.CodingErrorAction;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.Arrays;
import java.util.HexFormat;
import java.util.List;
import tools.jackson.core.StreamReadFeature;
import tools.jackson.core.json.JsonFactory;
import tools.jackson.databind.DeserializationFeature;
import tools.jackson.databind.json.JsonMapper;

/** Strict allowlist of versioned ordered public synthetic fixtures; no arbitrary caller data. */
public final class CanonicalSource {
    public static final int MAX_BYTES = 1_048_576;
    public static final int MAX_EVENTS = 1_000;
    private static final JsonMapper JSON = JsonMapper.builder(JsonFactory.builder()
        .enable(StreamReadFeature.STRICT_DUPLICATE_DETECTION).build())
        .enable(DeserializationFeature.FAIL_ON_TRAILING_TOKENS).build();
    private final byte[] bytes;
    private final String sha256;
    private final String scenarioVersion;
    private final List<SensorEvent> events;

    private CanonicalSource(byte[] bytes, String scenarioVersion, List<SensorEvent> events) {
        this.bytes = bytes; this.scenarioVersion = scenarioVersion; this.events = List.copyOf(events);
        try { this.sha256 = HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(bytes)); }
        catch (NoSuchAlgorithmException impossible) { throw new IllegalStateException(impossible); }
    }

    /** Legacy overload stays V1-only rather than inferring a different fixture from caller bytes. */
    public static CanonicalSource validate(byte[] input) { return validate(SyntheticScenario.NAME, input); }

    public static CanonicalSource validate(String scenarioVersion, byte[] input) {
        if (!SyntheticScenario.supports(scenarioVersion)) { throw new IllegalArgumentException("Unsupported synthetic scenario version"); }
        if (input == null || input.length == 0 || input.length > MAX_BYTES) {
            throw new IllegalArgumentException("Source must contain 1 to 1048576 bytes");
        }
        byte[] bytes = input.clone();
        final String text;
        try {
            text = StandardCharsets.UTF_8.newDecoder().onMalformedInput(CodingErrorAction.REPORT)
                .onUnmappableCharacter(CodingErrorAction.REPORT).decode(ByteBuffer.wrap(bytes)).toString();
        } catch (CharacterCodingException ex) { throw new IllegalArgumentException("Source must be UTF-8 NDJSON", ex); }
        String[] split = text.split("\\r?\\n", -1);
        int count = split.length - (split[split.length - 1].isEmpty() ? 1 : 0);
        List<SensorEvent> expected = SyntheticScenario.events(scenarioVersion);
        if (count > MAX_EVENTS || count != expected.size()) { throw new IllegalArgumentException("Source must match the selected bounded ordered synthetic fixture"); }
        for (int index = 0; index < count; index++) {
            try {
                var node = JSON.readTree(split[index]);
                var event = expected.get(index);
                if (node == null || !node.isObject() || node.size() != 4
                    || node.get("eventId") == null || !node.get("eventId").isTextual()
                    || node.get("sensorId") == null || !node.get("sensorId").isTextual()
                    || node.get("eventTime") == null || !node.get("eventTime").isTextual()
                    || node.get("value") == null || !node.get("value").isNumber()
                    || !event.eventId().equals(node.get("eventId").asText())
                    || !event.sensorId().equals(node.get("sensorId").asText())
                    || !event.eventTime().equals(node.get("eventTime").asText())
                    || Double.compare(event.value(), node.get("value").asDouble()) != 0) {
                    throw new IllegalArgumentException("Source differs from the selected ordered synthetic fixture");
                }
            } catch (IllegalArgumentException ex) { throw ex; }
            catch (Exception ex) { throw new IllegalArgumentException("Source must be strict NDJSON", ex); }
        }
        return new CanonicalSource(bytes, scenarioVersion, expected);
    }

    public static byte[] fixtureBytes() { return fixtureBytes(SyntheticScenario.NAME); }

    public static byte[] fixtureBytes(String scenarioVersion) {
        var text = new StringBuilder();
        for (var event : SyntheticScenario.events(scenarioVersion)) { text.append(JSON.writeValueAsString(event)).append('\n'); }
        return text.toString().getBytes(StandardCharsets.UTF_8);
    }

    public byte[] bytes() { return bytes.clone(); }
    public String sha256() { return sha256; }
    public int size() { return bytes.length; }
    public boolean matches(byte[] other) { return Arrays.equals(bytes, other); }
    public String scenarioVersion() { return scenarioVersion; }
    public List<SensorEvent> events() { return events; }
}
