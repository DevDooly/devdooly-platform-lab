package io.github.devdooly.platformlab.jobs.observation;

import org.springframework.http.CacheControl;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

/** Public GET only; never starts workers or contacts Kafka/S3. */
@RestController
@RequestMapping("/api/jobs/observation")
public class JobObservationController {
    private final JobObservationService observations;
    public JobObservationController(JobObservationService observations) { this.observations = observations; }
    @GetMapping
    public ResponseEntity<JobObservationService.Observation> get() {
        return ResponseEntity.ok().cacheControl(CacheControl.noStore()).body(observations.capture());
    }
    public record Error(int schemaVersion, String kind, String code) {}
    @ExceptionHandler(JobObservationService.ObservationUnavailableException.class)
    public ResponseEntity<Error> unavailable() {
        return ResponseEntity.status(HttpStatus.SERVICE_UNAVAILABLE).cacheControl(CacheControl.noStore())
            .body(new Error(1, "job-observation-error", "OBSERVATION_UNAVAILABLE"));
    }
}
