package io.github.devdooly.platformlab.jobs.runtime;

import io.github.devdooly.platformlab.demo.SyntheticScenario;
import io.github.devdooly.platformlab.jobs.CanonicalSource;
import io.github.devdooly.platformlab.jobs.LabJobService;
import io.github.devdooly.platformlab.jobs.SourceStagingService;
import java.util.Objects;

/** Internal one-shot admission for an allowlisted fixed synthetic fixture; no file, URL, count or payload. */
public final class FixedFixtureStager {
    private final RuntimeStateStore states;
    private final SourceStagingService sources;
    public FixedFixtureStager(RuntimeStateStore states, SourceStagingService sources) {
        this.states = Objects.requireNonNull(states); this.sources = Objects.requireNonNull(sources);
    }

    public LabJobService.Job stage(String runId) { return stage(runId, SyntheticScenario.NAME); }

    public LabJobService.Job stage(String runId, String scenarioVersion) {
        validateRunId(runId);
        scenarioVersion = scenarioFromSetting(scenarioVersion);
        if (states.read().status() == RuntimeStateStore.Status.PAUSED_OPERATOR) {
            throw new RuntimeStateStore.OperatorResumeRequiredException();
        }
        return sources.stage(runId, scenarioVersion, CanonicalSource.fixtureBytes(scenarioVersion));
    }
    public static String scenarioFromSetting(String setting) {
        if (setting == null) { return SyntheticScenario.NAME; }
        if (!SyntheticScenario.supports(setting)) { throw new IllegalArgumentException("Staging scenario must be an allowlisted fixed synthetic version"); }
        return setting;
    }
    public static void validateRunId(String runId) {
        if (runId == null || !runId.matches("lab-fixture-[a-z0-9][a-z0-9._-]{0,67}")) {
            throw new IllegalArgumentException("Fixture staging requires an explicit lab-fixture- run ID of at most 80 lowercase ASCII characters");
        }
    }
}
