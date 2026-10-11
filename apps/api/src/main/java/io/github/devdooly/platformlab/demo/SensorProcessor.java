package io.github.devdooly.platformlab.demo;

import java.time.Instant;
import java.time.format.DateTimeParseException;
import java.util.*;

public final class SensorProcessor {
    public enum Status { SUCCESS, FAILED, DUPLICATE }
    public enum Reason { ACCEPTED, INVALID_INPUT, DUPLICATE_EVENT_ID, INVALID_TIMESTAMP, OUT_OF_ORDER, OUT_OF_RANGE }
    public record Outcome(int sequence, String eventId, String sensorId, String eventTime, Double value, Status status, Reason reason) {}
    public record Result(List<Outcome> outcomes, int inputCount, int successCount, int failureCount, int duplicateCount, int pendingCount) {
        public Result {
            outcomes = List.copyOf(outcomes);
            if (inputCount != successCount + failureCount + duplicateCount + pendingCount) {
                throw new IllegalArgumentException("Input accounting invariant violated");
            }
        }
    }

    public Result process(List<SensorEvent> events) {
        Objects.requireNonNull(events, "events");
        var seen = new HashSet<String>();
        var latestSuccess = new HashMap<String, Instant>();
        var outcomes = new ArrayList<Outcome>();
        int successes = 0, failures = 0, duplicates = 0;
        for (int index = 0; index < events.size(); index++) {
            var event = events.get(index);
            Reason reason;
            if (event == null || blank(event.eventId()) || blank(event.sensorId()) || event.value() == null || !Double.isFinite(event.value())) {
                reason = Reason.INVALID_INPUT;
            } else if (!seen.add(event.eventId())) {
                reason = Reason.DUPLICATE_EVENT_ID;
            } else {
                reason = validateTimeAndRange(event, latestSuccess);
            }
            Status status;
            if (reason == Reason.ACCEPTED) { status = Status.SUCCESS; successes++; }
            else if (reason == Reason.DUPLICATE_EVENT_ID) { status = Status.DUPLICATE; duplicates++; }
            else { status = Status.FAILED; failures++; }
            outcomes.add(new Outcome(index + 1, event == null ? null : event.eventId(), event == null ? null : event.sensorId(),
                event == null ? null : event.eventTime(), event == null || event.value() == null || !Double.isFinite(event.value()) ? null : event.value(), status, reason));
        }
        return new Result(outcomes, events.size(), successes, failures, duplicates, 0);
    }

    private Reason validateTimeAndRange(SensorEvent event, Map<String, Instant> latestSuccess) {
        final Instant time;
        try { time = Instant.parse(event.eventTime()); }
        catch (DateTimeParseException | NullPointerException ex) { return Reason.INVALID_TIMESTAMP; }
        if (event.value() < 0 || event.value() > 100) { return Reason.OUT_OF_RANGE; }
        var previous = latestSuccess.get(event.sensorId());
        if (previous != null && time.isBefore(previous)) { return Reason.OUT_OF_ORDER; }
        latestSuccess.put(event.sensorId(), time);
        return Reason.ACCEPTED;
    }
    private boolean blank(String text) { return text == null || text.isBlank(); }
}
