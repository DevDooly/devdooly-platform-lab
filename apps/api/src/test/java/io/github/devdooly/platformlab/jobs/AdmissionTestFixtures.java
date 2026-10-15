package io.github.devdooly.platformlab.jobs;

import java.sql.SQLException;
import java.util.HashSet;
import java.util.regex.Pattern;
import org.springframework.jdbc.core.ConnectionCallback;
import org.springframework.jdbc.core.JdbcTemplate;

/** Explicit clock-state reset for owned disposable test databases only; never production code. */
public final class AdmissionTestFixtures {
    private AdmissionTestFixtures() {}
    public static void makeEligible(JdbcTemplate jdbc) {
        jdbc.execute((ConnectionCallback<Void>) connection -> {
            String url = connection.getMetaData().getURL();
            if (!url.startsWith("jdbc:h2:mem:") && !url.matches(
                "jdbc:mariadb://127\\.0\\.0\\.1:[0-9]{1,5}/platform_lab_(?:foundation(?:_fresh)?|s3_it(?:_fresh)?|runtime_it|admission_it)(?:\\?.*)?")
                && !(ownedExportMetadataUrl(url) && "platform_lab_export_it".equals(connection.getCatalog()))) {
                throw new SQLException("Admission test fixture requires an owned disposable database");
            }
            return null;
        });
        if (jdbc.queryForObject("SELECT occupied_run_id FROM lab_job_slot WHERE id=1", String.class) != null) {
            throw new IllegalStateException("Test fixture must not reset an occupied admission slot");
        }
        if (jdbc.update("UPDATE lab_admission_policy SET last_admitted_at=NULL, next_admission_at=NULL WHERE id=1 AND cooldown_seconds=30") != 1) {
            throw new IllegalStateException("Expected the unchanged default 30-second test policy");
        }
    }

    private static boolean ownedExportMetadataUrl(String url) {
        if (url.length() > 16384) { return false; }
        int query = url.indexOf('?');
        String base = query < 0 ? url : url.substring(0, query);
        var target = Pattern.compile("jdbc:mariadb://127\\.0\\.0\\.1:([0-9]{1,5})/platform_lab_export_it").matcher(base);
        if (!target.matches()) { return false; }
        int port = Integer.parseInt(target.group(1));
        if (port < 1 || port > 65535) { return false; }
        if (query < 0) { return true; }
        // Connector/J 3.5.10 getURL() rebuilds even separately supplied credentials.
        // Do not accept arbitrary database/connection options or decode credential values.
        var keys = new HashSet<String>();
        for (String pair : url.substring(query + 1).split("&", -1)) {
            int equals = pair.indexOf('=');
            if (equals < 1 || equals == pair.length() - 1) { return false; }
            String key = pair.substring(0, equals);
            if ((!key.equals("user") && !key.equals("password")) || !keys.add(key)) { return false; }
            for (int i = equals + 1; i < pair.length(); i++) {
                char value = pair.charAt(i);
                if (value < 33 || value > 126 || value == '#') { return false; }
                if (value == '%') {
                    if (i + 2 >= pair.length() || pair.charAt(i + 1) > 127 || pair.charAt(i + 2) > 127
                        || Character.digit(pair.charAt(i + 1), 16) < 0 || Character.digit(pair.charAt(i + 2), 16) < 0) { return false; }
                    i += 2;
                }
            }
        }
        return !keys.isEmpty();
    }
}
