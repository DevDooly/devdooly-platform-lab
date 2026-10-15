package io.github.devdooly.platformlab.demo;

import java.time.Clock;
import java.time.Instant;
import java.util.*;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.transaction.annotation.Propagation;

@Service
public class DemoService {
    private final DemoRunRepository runs;
    private final DemoOutcomeRepository outcomes;
    private final Clock clock;
    public DemoService(DemoRunRepository runs, DemoOutcomeRepository outcomes, Clock clock) { this.runs = runs; this.outcomes = outcomes; this.clock = clock; }

    @Transactional
    public void ensureSample() {
        if (runs.existsById(SyntheticScenario.RUN_ID)) { return; }
        var started = clock.instant();
        var result = new SensorProcessor().process(SyntheticScenario.events());
        persistProcessedRun(SyntheticScenario.RUN_ID, "합성 센서 품질 검증", SyntheticScenario.NAME,
            SyntheticScenario.SEED, result, started, clock.instant());
    }

    /** Persist one complete result inside the caller's job transaction. */
    @Transactional(propagation = Propagation.MANDATORY)
    public void persistProcessedRun(String runId, String runName, String scenarioVersion, long seed,
                                    SensorProcessor.Result result, Instant started, Instant completed) {
        runs.saveAndFlush(new DemoRun(runId, runName, scenarioVersion, seed, result, started, completed));
        outcomes.saveAllAndFlush(result.outcomes().stream().map(outcome -> new DemoOutcome(runId, outcome)).toList());
    }

    @Transactional(readOnly = true)
    public Map<String, Object> list() {
        return Map.of("items", runs.findTop20ByOrderByStartedAtDesc().stream().map(this::summary).toList(), "observedAt", clock.instant());
    }

    @Transactional(readOnly = true)
    public Map<String, Object> detail(String id) {
        var run = runs.findById(id).orElseThrow(RunNotFoundException::new);
        var result = new LinkedHashMap<>(summary(run));
        var views = outcomes.findByRunIdOrderBySequence(id).stream().map(DemoOutcome::view).toList();
        var reasons = new TreeMap<String, Integer>();
        views.stream().filter(view -> view.status() == SensorProcessor.Status.FAILED).forEach(view -> reasons.merge(view.reason().name(), 1, Integer::sum));
        result.put("scenario", run.scenario); result.put("description", SyntheticScenario.DESCRIPTION);
        result.put("outcomes", views);
        result.put("series", views.stream().filter(view -> view.status() == SensorProcessor.Status.SUCCESS)
            .map(view -> Map.of("eventTime", view.eventTime(), "sensorId", view.sensorId(), "value", view.value())).toList());
        result.put("failureReasons", reasons.entrySet().stream().map(entry -> Map.of("reason", entry.getKey(), "count", entry.getValue())).toList());
        result.put("observedAt", clock.instant());
        return result;
    }
    private Map<String, Object> summary(DemoRun run) {
        var result = new LinkedHashMap<String, Object>();
        result.put("id", run.id); result.put("name", run.name); result.put("status", "COMPLETED"); result.put("synthetic", true); result.put("seed", run.seed);
        result.put("inputCount", run.inputCount); result.put("successCount", run.successCount); result.put("failureCount", run.failureCount);
        result.put("duplicateCount", run.duplicateCount); result.put("pendingCount", run.pendingCount);
        result.put("startedAt", run.startedAt); result.put("completedAt", run.completedAt);
        return result;
    }
    public static class RunNotFoundException extends RuntimeException {}
}
