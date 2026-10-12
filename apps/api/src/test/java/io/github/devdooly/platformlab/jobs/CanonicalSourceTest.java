package io.github.devdooly.platformlab.jobs;

import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.util.HexFormat;
import org.junit.jupiter.api.Test;
import static org.assertj.core.api.Assertions.*;

class CanonicalSourceTest {
    @Test void rawLineEndingsHaveDistinctHashesAndDefensiveCopies() throws Exception {
        byte[] raw = CanonicalSource.fixtureBytes();
        var source = CanonicalSource.validate(raw);
        assertThat(source.sha256()).isEqualTo(HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(raw)));
        var crlf = CanonicalSource.validate(new String(raw, StandardCharsets.UTF_8).replace("\n", "\r\n").getBytes(StandardCharsets.UTF_8));
        assertThat(crlf.sha256()).isNotEqualTo(source.sha256());
        assertThat(crlf.events()).isEqualTo(source.events());
        source.bytes()[0] = 0; raw[0] = 0;
        assertThat(source.bytes()[0]).isEqualTo((byte) '{');
    }
    @Test void strictJsonRejectsDuplicateKeysTrailingTokensWrongOrderAndInvalidUtf8() {
        String fixture = new String(CanonicalSource.fixtureBytes(), StandardCharsets.UTF_8);
        var invalid = new String[] {
            fixture.replaceFirst("\\{", "{\"eventId\":\"evt-001\","),
            fixture.replaceFirst("\\n", " {}\n"),
            fixture.replaceFirst("evt-001", "evt-002"),
            fixture.replaceFirst("\\{", "{\"extra\":0,")
        };
        for (String text : invalid) {
            assertThatThrownBy(() -> CanonicalSource.validate(text.getBytes(StandardCharsets.UTF_8))).isInstanceOf(IllegalArgumentException.class);
        }
        String[] lines = fixture.split("\n");
        String first = lines[0]; lines[0] = lines[1]; lines[1] = first;
        assertThatThrownBy(() -> CanonicalSource.validate((String.join("\n", lines) + "\n").getBytes(StandardCharsets.UTF_8)))
            .isInstanceOf(IllegalArgumentException.class);
        byte[] invalidUtf8 = CanonicalSource.fixtureBytes(); invalidUtf8[0] = (byte) 0xc0;
        assertThatThrownBy(() -> CanonicalSource.validate(invalidUtf8)).isInstanceOf(IllegalArgumentException.class);
    }
}
