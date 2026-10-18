package io.github.devdooly.platformlab.jobs.observation;

import jakarta.servlet.http.HttpServletRequest;
import org.springframework.http.CacheControl;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

/** Separate opt-in GET. No request chooses a broker, topic, group or mutation. */
@RestController
@RequestMapping("/api/kafka/observation")
public final class KafkaObservationController {
    private final KafkaObservationService observations;
    public KafkaObservationController(KafkaObservationService observations) { this.observations = observations; }
    @GetMapping public ResponseEntity<?> get(HttpServletRequest request) {
        if (unsupportedEntity(request)) {
            return ResponseEntity.badRequest().cacheControl(CacheControl.noStore()).body(new Error(1, "kafka-observation-error", KafkaObservationService.Code.INVALID_CONFIGURATION));
        }
        return ResponseEntity.ok().cacheControl(CacheControl.noStore()).body(observations.capture());
    }
    private static boolean unsupportedEntity(HttpServletRequest request) {
        try {
            if (request.getQueryString() != null || request.getContentLengthLong() != 0 && request.getContentLengthLong() != -1
                    || request.getHeader("Transfer-Encoding") != null || request.getContentType() != null) { return true; }
            // Tomcat 11.0.24 distinguishes no entity from pending/queued HTTP/2 DATA without reading it.
            // Never read(), isReady(), or wait for an unknown-length request body.
            return !request.getInputStream().isFinished();
        } catch (Exception unavailable) { return true; }
    }
    public record Error(int schemaVersion, String kind, KafkaObservationService.Code code) {}
    @ExceptionHandler(KafkaObservationService.ObservationFailure.class)
    public ResponseEntity<Error> unavailable(KafkaObservationService.ObservationFailure failure) {
        return ResponseEntity.status(HttpStatus.SERVICE_UNAVAILABLE).cacheControl(CacheControl.noStore())
            .body(new Error(1, "kafka-observation-error", failure.code()));
    }
}
