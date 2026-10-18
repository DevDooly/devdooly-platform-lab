package io.github.devdooly.examples.retention;

import java.time.Instant;
import java.util.EnumMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Optional;
import java.util.Set;

/**
 * One synthetic run, two synthetic object aliases, and serial immutable RAM transitions.
 * Returned action data never performs I/O. Atomic persistence and participation by all
 * writers/backups are model assumptions, not implemented database or storage guarantees.
 */
public final class RetentionProtocolModel {
    public static final String SCOPE = "SYNTHETIC_RAM_PROTOCOL_MODEL";
    public enum Phase { ACTIVE, TOMBSTONED, COMPLETE }
    public enum Knowledge { KNOWN_SAFE, BLOCKED, UNKNOWN }
    public enum ObjectAlias { RAW_SAMPLE, RESULT_SAMPLE }
    public enum Reference { ACTIVE_READER, RETRY_READER }
    public enum BackupPin { BASELINE, EVIDENCE }
    public enum IntentAlias { FIRST, OTHER }
    public enum ActionState { READY, IN_FLIGHT, UNKNOWN, ABSENT_CONFIRMED }
    public enum Observation { ABSENT_CONFIRMED, PRESENT_SAME_GENERATION, UNKNOWN }
    public enum Decision {
        APPLIED, REPLAY_NOOP, TOMBSTONED, ACTION_SELECTED, AWAITING_RESULT,
        RECONCILIATION_REQUIRED, COMPLETE, PROTECTED_REFERENCE, PROTECTED_BACKUP,
        ELIGIBILITY_BLOCKED, PLAN_STALE, REVISION_CHANGED, TARGET_CHANGED,
        RUN_CLOSED, RUN_NOT_TOMBSTONED, INTENT_MISMATCH, OUTCOME_BEFORE_ACTION,
        CONFLICTING_OBSERVATION
    }

    public record Target(ObjectAlias alias, long generation) {
        public Target {
            Objects.requireNonNull(alias);
            require(generation >= 1 && generation <= 1_000_000);
        }
    }

    public record Eligibility(Knowledge retention, Knowledge replayHorizon,
                              Knowledge outbox, Knowledge referenceCoverage) {
        public Eligibility {
            Objects.requireNonNull(retention); Objects.requireNonNull(replayHorizon);
            Objects.requireNonNull(outbox); Objects.requireNonNull(referenceCoverage);
        }
        private boolean safe() {
            return retention == Knowledge.KNOWN_SAFE && replayHorizon == Knowledge.KNOWN_SAFE
                && outbox == Knowledge.KNOWN_SAFE && referenceCoverage == Knowledge.KNOWN_SAFE;
        }
    }

    /** A proposal only. Even a fresh proposal is rechecked against the current snapshot. */
    public record Plan(long expectedRevision, List<Target> targets, Instant capturedAt, Instant expiresAt) {
        public Plan {
            require(expectedRevision >= 0);
            targets = checkedTargets(targets);
            Objects.requireNonNull(capturedAt); Objects.requireNonNull(expiresAt);
            require(expiresAt.equals(capturedAt.plusSeconds(300)));
        }
    }

    /** Identity is data: no URL, key, SQL, credentials or executable command is represented. */
    public record ActionId(IntentAlias intent, Target target) {
        public ActionId { Objects.requireNonNull(intent); Objects.requireNonNull(target); }
    }

    public static final class Snapshot {
        private final long revision;
        private final Phase phase;
        private final List<Target> targets;
        private final Eligibility eligibility;
        private final Set<Reference> references;
        private final Set<BackupPin> backupPins;
        private final IntentAlias intent;
        private final Map<ObjectAlias, ActionState> actions;

        private Snapshot(long revision, Phase phase, List<Target> targets, Eligibility eligibility,
                         Set<Reference> references, Set<BackupPin> backupPins, IntentAlias intent,
                         Map<ObjectAlias, ActionState> actions) {
            require(revision >= 0);
            this.revision = revision; this.phase = Objects.requireNonNull(phase);
            this.targets = checkedTargets(targets); this.eligibility = Objects.requireNonNull(eligibility);
            this.references = Set.copyOf(references); this.backupPins = Set.copyOf(backupPins);
            this.intent = intent; this.actions = Map.copyOf(actions);
            if (phase == Phase.ACTIVE) {
                require(intent == null && actions.isEmpty());
            } else {
                require(intent != null && references.isEmpty() && backupPins.isEmpty());
                require(this.actions.keySet().equals(Set.of(ObjectAlias.RAW_SAMPLE, ObjectAlias.RESULT_SAMPLE)));
                require(phase != Phase.COMPLETE || this.actions.values().stream()
                    .allMatch(value -> value == ActionState.ABSENT_CONFIRMED));
            }
        }
        public long revision() { return revision; }
        public Phase phase() { return phase; }
        public List<Target> targets() { return targets; }
        public Eligibility eligibility() { return eligibility; }
        public Set<Reference> references() { return references; }
        public Set<BackupPin> backupPins() { return backupPins; }
        public Optional<IntentAlias> intent() { return Optional.ofNullable(intent); }
        public Map<ObjectAlias, ActionState> actions() { return actions; }
    }

    public record Transition(Snapshot state, Decision decision, Optional<ActionId> selectedAction) {
        public Transition {
            Objects.requireNonNull(state); Objects.requireNonNull(decision); Objects.requireNonNull(selectedAction);
            require(selectedAction.isPresent() == (decision == Decision.ACTION_SELECTED));
        }
    }

    private RetentionProtocolModel() { }

    /** Starts an independent synthetic scenario, not a registration or reopening of a real run. */
    public static Snapshot initial(List<Target> targets, Eligibility eligibility) {
        return new Snapshot(0, Phase.ACTIVE, targets, eligibility, Set.of(), Set.of(), null, Map.of());
    }

    public static Plan propose(Snapshot state, Instant capturedAt) {
        require(state.phase == Phase.ACTIVE);
        return new Plan(state.revision, state.targets, capturedAt, capturedAt.plusSeconds(300));
    }

    public static Transition addReference(Snapshot state, Reference reference) {
        return referenceChange(state, reference, true);
    }
    public static Transition removeReference(Snapshot state, Reference reference) {
        return referenceChange(state, reference, false);
    }
    private static Transition referenceChange(Snapshot state, Reference reference, boolean add) {
        Objects.requireNonNull(reference);
        if (state.phase != Phase.ACTIVE) return result(state, Decision.RUN_CLOSED);
        var values = new java.util.HashSet<>(state.references);
        boolean changed = add ? values.add(reference) : values.remove(reference);
        return changed ? result(copy(state, state.phase, values, state.backupPins, state.intent, state.actions), Decision.APPLIED)
            : result(state, Decision.REPLAY_NOOP);
    }

    public static Transition addBackupPin(Snapshot state, BackupPin pin) {
        return pinChange(state, pin, true);
    }
    public static Transition removeBackupPin(Snapshot state, BackupPin pin) {
        return pinChange(state, pin, false);
    }
    private static Transition pinChange(Snapshot state, BackupPin pin, boolean add) {
        Objects.requireNonNull(pin);
        if (state.phase != Phase.ACTIVE) return result(state, Decision.RUN_CLOSED);
        var values = new java.util.HashSet<>(state.backupPins);
        boolean changed = add ? values.add(pin) : values.remove(pin);
        return changed ? result(copy(state, state.phase, state.references, values, state.intent, state.actions), Decision.APPLIED)
            : result(state, Decision.REPLAY_NOOP);
    }

    /** Tombstone and intent become visible together in this single serial RAM transition. */
    public static Transition tombstone(Snapshot state, Plan plan, Instant now, IntentAlias intent) {
        Objects.requireNonNull(plan); Objects.requireNonNull(now); Objects.requireNonNull(intent);
        if (state.phase != Phase.ACTIVE) return result(state, Decision.RUN_CLOSED);
        if (now.isBefore(plan.capturedAt) || now.isAfter(plan.expiresAt)) return result(state, Decision.PLAN_STALE);
        if (state.revision != plan.expectedRevision) return result(state, Decision.REVISION_CHANGED);
        if (!state.targets.equals(plan.targets)) return result(state, Decision.TARGET_CHANGED);
        if (!state.eligibility.safe()) return result(state, Decision.ELIGIBILITY_BLOCKED);
        if (!state.references.isEmpty()) return result(state, Decision.PROTECTED_REFERENCE);
        if (!state.backupPins.isEmpty()) return result(state, Decision.PROTECTED_BACKUP);
        var actions = new EnumMap<ObjectAlias, ActionState>(ObjectAlias.class);
        state.targets.forEach(target -> actions.put(target.alias, ActionState.READY));
        return result(copy(state, Phase.TOMBSTONED, Set.of(), Set.of(), intent, actions), Decision.TOMBSTONED);
    }

    /** Reusing a saved model snapshot is resume. In-flight/unknown actions are never reissued. */
    public static Transition nextAction(Snapshot state, IntentAlias intent) {
        Objects.requireNonNull(intent);
        if (state.phase == Phase.ACTIVE) return result(state, Decision.RUN_NOT_TOMBSTONED);
        if (state.intent != intent) return result(state, Decision.INTENT_MISMATCH);
        if (state.phase == Phase.COMPLETE) return result(state, Decision.COMPLETE);
        if (state.actions.containsValue(ActionState.UNKNOWN)) return result(state, Decision.RECONCILIATION_REQUIRED);
        if (state.actions.containsValue(ActionState.IN_FLIGHT)) return result(state, Decision.AWAITING_RESULT);
        for (Target target : state.targets) {
            if (state.actions.get(target.alias) == ActionState.READY) {
                var actions = new EnumMap<>(state.actions);
                actions.put(target.alias, ActionState.IN_FLIGHT);
                return new Transition(copy(state, state.phase, state.references, state.backupPins, intent, actions),
                    Decision.ACTION_SELECTED, Optional.of(new ActionId(intent, target)));
            }
        }
        throw new IllegalStateException("INVALID_MODEL_STATE");
    }

    /** A supplied synthetic observation, not an HTTP response or independently verified receipt. */
    public static Transition observe(Snapshot state, ActionId action, Observation observation) {
        Objects.requireNonNull(action); Objects.requireNonNull(observation);
        if (state.phase == Phase.ACTIVE) return result(state, Decision.RUN_NOT_TOMBSTONED);
        if (state.intent != action.intent) return result(state, Decision.INTENT_MISMATCH);
        if (!state.targets.contains(action.target)) return result(state, Decision.TARGET_CHANGED);
        ActionState current = state.actions.get(action.target.alias);
        if (current == ActionState.READY) return result(state, Decision.OUTCOME_BEFORE_ACTION);
        if (current == ActionState.ABSENT_CONFIRMED) {
            return result(state, observation == Observation.ABSENT_CONFIRMED
                ? Decision.REPLAY_NOOP : Decision.CONFLICTING_OBSERVATION);
        }
        if (observation != Observation.ABSENT_CONFIRMED && current == ActionState.UNKNOWN)
            return result(state, Decision.RECONCILIATION_REQUIRED);
        var actions = new EnumMap<>(state.actions);
        actions.put(action.target.alias, observation == Observation.ABSENT_CONFIRMED
            ? ActionState.ABSENT_CONFIRMED : ActionState.UNKNOWN);
        boolean complete = actions.values().stream().allMatch(value -> value == ActionState.ABSENT_CONFIRMED);
        return result(copy(state, complete ? Phase.COMPLETE : Phase.TOMBSTONED,
            state.references, state.backupPins, state.intent, actions),
            complete ? Decision.COMPLETE : observation == Observation.ABSENT_CONFIRMED
                ? Decision.APPLIED : Decision.RECONCILIATION_REQUIRED);
    }

    private static Snapshot copy(Snapshot old, Phase phase, Set<Reference> references,
                                 Set<BackupPin> pins, IntentAlias intent, Map<ObjectAlias, ActionState> actions) {
        return new Snapshot(Math.incrementExact(old.revision), phase, old.targets, old.eligibility,
            references, pins, intent, actions);
    }
    private static Transition result(Snapshot state, Decision decision) {
        return new Transition(state, decision, Optional.empty());
    }
    private static List<Target> checkedTargets(List<Target> values) {
        List<Target> targets = List.copyOf(values);
        require(targets.size() == 2 && targets.stream().map(Target::alias).distinct().count() == 2);
        return targets;
    }
    private static void require(boolean valid) {
        if (!valid) throw new IllegalArgumentException("INVALID_MODEL_INPUT");
    }
}
