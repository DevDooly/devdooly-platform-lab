package io.github.devdooly.examples.retention;

import java.time.Instant;
import java.util.ArrayList;
import java.util.List;

import org.junit.jupiter.api.Test;

import static io.github.devdooly.examples.retention.RetentionProtocolModel.*;
import static org.junit.jupiter.api.Assertions.*;

class RetentionProtocolModelTest {
    private static final Instant NOW = Instant.parse("2026-10-18T00:00:00Z");
    private static final Target RAW = new Target(ObjectAlias.RAW_SAMPLE, 1);
    private static final Target RESULT = new Target(ObjectAlias.RESULT_SAMPLE, 1);
    private static final Eligibility SAFE = new Eligibility(Knowledge.KNOWN_SAFE, Knowledge.KNOWN_SAFE,
        Knowledge.KNOWN_SAFE, Knowledge.KNOWN_SAFE);

    private static Snapshot active() { return initial(List.of(RAW, RESULT), SAFE); }
    private static Snapshot prepared() {
        Snapshot state = active();
        Transition transition = tombstone(state, propose(state, NOW), NOW, IntentAlias.FIRST);
        assertEquals(Decision.TOMBSTONED, transition.decision());
        assertTrue(transition.selectedAction().isEmpty());
        return transition.state();
    }
    private static void unchanged(Snapshot state, Transition transition, Decision decision) {
        assertSame(state, transition.state());
        assertEquals(decision, transition.decision());
        assertTrue(transition.selectedAction().isEmpty());
    }

    @Test
    void staleProposalAndReferenceAbaCannotAuthorizeTombstone() {
        Snapshot state = active();
        Plan plan = propose(state, NOW);
        assertEquals(Decision.TOMBSTONED,
            tombstone(state, plan, NOW.plusSeconds(300), IntentAlias.FIRST).decision());
        unchanged(state, tombstone(state, plan, NOW.plusSeconds(300).plusNanos(1), IntentAlias.FIRST), Decision.PLAN_STALE);
        unchanged(state, tombstone(state, plan, NOW.minusNanos(1), IntentAlias.FIRST), Decision.PLAN_STALE);

        Snapshot referenced = addReference(state, Reference.ACTIVE_READER).state();
        Snapshot released = removeReference(referenced, Reference.ACTIVE_READER).state();
        assertTrue(state.references().isEmpty());
        assertTrue(released.references().isEmpty());
        assertEquals(state.revision() + 2, released.revision());
        unchanged(released, tombstone(released, plan, NOW, IntentAlias.FIRST), Decision.REVISION_CHANGED);

        Plan wrongGeneration = new Plan(state.revision(),
            List.of(RAW, new Target(ObjectAlias.RESULT_SAMPLE, 2)), NOW, NOW.plusSeconds(300));
        unchanged(state, tombstone(state, wrongGeneration, NOW, IntentAlias.FIRST), Decision.TARGET_CHANGED);
        var mutableTargets = new ArrayList<>(List.of(RAW, RESULT));
        Snapshot copied = initial(mutableTargets, SAFE);
        mutableTargets.clear();
        assertEquals(List.of(RAW, RESULT), copied.targets());
    }

    @Test
    void pinsReferencesAndUnknownKnowledgeProtectBeforeIntentAndLateActorsAreRejectedAfterward() {
        Snapshot state = active();
        Plan beforePin = propose(state, NOW);
        Snapshot pinned = addBackupPin(state, BackupPin.BASELINE).state();
        unchanged(pinned, tombstone(pinned, beforePin, NOW, IntentAlias.FIRST), Decision.REVISION_CHANGED);
        unchanged(pinned, tombstone(pinned, propose(pinned, NOW), NOW, IntentAlias.FIRST), Decision.PROTECTED_BACKUP);
        Snapshot referenced = addReference(state, Reference.RETRY_READER).state();
        unchanged(referenced, tombstone(referenced, propose(referenced, NOW), NOW, IntentAlias.FIRST), Decision.PROTECTED_REFERENCE);
        assertTrue(state.references().isEmpty()); assertTrue(state.backupPins().isEmpty());

        for (Knowledge unsafe : List.of(Knowledge.BLOCKED, Knowledge.UNKNOWN)) {
            for (Eligibility eligibility : List.of(
                new Eligibility(unsafe, Knowledge.KNOWN_SAFE, Knowledge.KNOWN_SAFE, Knowledge.KNOWN_SAFE),
                new Eligibility(Knowledge.KNOWN_SAFE, unsafe, Knowledge.KNOWN_SAFE, Knowledge.KNOWN_SAFE),
                new Eligibility(Knowledge.KNOWN_SAFE, Knowledge.KNOWN_SAFE, unsafe, Knowledge.KNOWN_SAFE),
                new Eligibility(Knowledge.KNOWN_SAFE, Knowledge.KNOWN_SAFE, Knowledge.KNOWN_SAFE, unsafe))) {
                Snapshot unknown = initial(List.of(RAW, RESULT), eligibility);
                unchanged(unknown, tombstone(unknown, propose(unknown, NOW), NOW, IntentAlias.FIRST), Decision.ELIGIBILITY_BLOCKED);
                assertTrue(unknown.intent().isEmpty()); assertTrue(unknown.actions().isEmpty());
            }
        }

        Snapshot releasedPin = removeBackupPin(pinned, BackupPin.BASELINE).state();
        Snapshot closed = tombstone(releasedPin, propose(releasedPin, NOW), NOW, IntentAlias.FIRST).state();
        assertEquals(Phase.TOMBSTONED, closed.phase());
        assertEquals(IntentAlias.FIRST, closed.intent().orElseThrow());
        assertEquals(2, closed.actions().size());
        unchanged(closed, addReference(closed, Reference.ACTIVE_READER), Decision.RUN_CLOSED);
        unchanged(closed, addBackupPin(closed, BackupPin.EVIDENCE), Decision.RUN_CLOSED);
        assertEquals(List.of(RAW, RESULT), closed.targets());
    }

    @Test
    void partialAbsenceAndUnknownOutcomeStayClosedAndNeverAutomaticallyRetry() {
        Snapshot closed = prepared();
        Transition raw = nextAction(closed, IntentAlias.FIRST);
        Snapshot rawAbsent = observe(raw.state(), raw.selectedAction().orElseThrow(), Observation.ABSENT_CONFIRMED).state();
        Transition result = nextAction(rawAbsent, IntentAlias.FIRST);
        ActionId resultAction = result.selectedAction().orElseThrow();
        Snapshot uncertain = observe(result.state(), resultAction, Observation.UNKNOWN).state();
        assertEquals(Phase.TOMBSTONED, uncertain.phase());
        assertEquals(ActionState.ABSENT_CONFIRMED, uncertain.actions().get(ObjectAlias.RAW_SAMPLE));
        assertEquals(ActionState.UNKNOWN, uncertain.actions().get(ObjectAlias.RESULT_SAMPLE));
        unchanged(uncertain, nextAction(uncertain, IntentAlias.FIRST), Decision.RECONCILIATION_REQUIRED);
        unchanged(uncertain, observe(uncertain, resultAction, Observation.PRESENT_SAME_GENERATION), Decision.RECONCILIATION_REQUIRED);
        unchanged(uncertain, observe(uncertain, resultAction, Observation.UNKNOWN), Decision.RECONCILIATION_REQUIRED);
        unchanged(uncertain, addReference(uncertain, Reference.RETRY_READER), Decision.RUN_CLOSED);
        unchanged(uncertain, addBackupPin(uncertain, BackupPin.BASELINE), Decision.RUN_CLOSED);
    }

    @Test
    void redeliveryAndResumeKeepExactIntentTargetGenerationAndDoNotReissueConfirmedOrInflightActions() {
        Snapshot closed = prepared();
        Transition raw = nextAction(closed, IntentAlias.FIRST);
        ActionId rawAction = raw.selectedAction().orElseThrow();
        assertEquals(new ActionId(IntentAlias.FIRST, RAW), rawAction);
        unchanged(raw.state(), nextAction(raw.state(), IntentAlias.FIRST), Decision.AWAITING_RESULT);
        unchanged(raw.state(), nextAction(raw.state(), IntentAlias.OTHER), Decision.INTENT_MISMATCH);
        unchanged(raw.state(), observe(raw.state(), new ActionId(IntentAlias.OTHER, RAW), Observation.ABSENT_CONFIRMED), Decision.INTENT_MISMATCH);
        unchanged(raw.state(), observe(raw.state(), new ActionId(IntentAlias.FIRST,
            new Target(ObjectAlias.RAW_SAMPLE, 2)), Observation.ABSENT_CONFIRMED), Decision.TARGET_CHANGED);

        Snapshot savedModelState = observe(raw.state(), rawAction, Observation.ABSENT_CONFIRMED).state();
        unchanged(savedModelState, observe(savedModelState, rawAction, Observation.ABSENT_CONFIRMED), Decision.REPLAY_NOOP);
        // A supplied immutable snapshot models resume; no durable storage or JVM crash is exercised.
        Transition resumed = nextAction(savedModelState, IntentAlias.FIRST);
        assertEquals(new ActionId(IntentAlias.FIRST, RESULT), resumed.selectedAction().orElseThrow());
        assertEquals(ActionState.ABSENT_CONFIRMED, resumed.state().actions().get(ObjectAlias.RAW_SAMPLE));
        assertEquals(ActionState.IN_FLIGHT, resumed.state().actions().get(ObjectAlias.RESULT_SAMPLE));
        assertEquals(ActionState.READY, savedModelState.actions().get(ObjectAlias.RESULT_SAMPLE));
    }

    @Test
    void completionNeedsBothExactAbsenceObservationsAndKeepsTheTombstoneAfterCompletion() {
        Snapshot closed = prepared();
        unchanged(closed, observe(closed, new ActionId(IntentAlias.FIRST, RAW), Observation.ABSENT_CONFIRMED), Decision.OUTCOME_BEFORE_ACTION);
        Transition raw = nextAction(closed, IntentAlias.FIRST);
        Snapshot rawAbsent = observe(raw.state(), raw.selectedAction().orElseThrow(), Observation.ABSENT_CONFIRMED).state();
        assertEquals(Phase.TOMBSTONED, rawAbsent.phase());
        unchanged(rawAbsent, observe(rawAbsent, new ActionId(IntentAlias.FIRST, RESULT), Observation.ABSENT_CONFIRMED), Decision.OUTCOME_BEFORE_ACTION);
        Transition result = nextAction(rawAbsent, IntentAlias.FIRST);
        ActionId resultAction = result.selectedAction().orElseThrow();
        Snapshot waiting = observe(result.state(), resultAction, Observation.PRESENT_SAME_GENERATION).state();
        assertEquals(Phase.TOMBSTONED, waiting.phase());
        Transition complete = observe(waiting, resultAction, Observation.ABSENT_CONFIRMED);
        assertEquals(Decision.COMPLETE, complete.decision());
        assertTrue(complete.selectedAction().isEmpty());
        assertEquals(Phase.COMPLETE, complete.state().phase());
        assertTrue(complete.state().actions().values().stream().allMatch(value -> value == ActionState.ABSENT_CONFIRMED));
        assertEquals(IntentAlias.FIRST, complete.state().intent().orElseThrow());
        assertEquals(List.of(RAW, RESULT), complete.state().targets());
        unchanged(complete.state(), nextAction(complete.state(), IntentAlias.FIRST), Decision.COMPLETE);
        unchanged(complete.state(), observe(complete.state(), resultAction, Observation.ABSENT_CONFIRMED), Decision.REPLAY_NOOP);
        unchanged(complete.state(), observe(complete.state(), resultAction, Observation.PRESENT_SAME_GENERATION), Decision.CONFLICTING_OBSERVATION);
        unchanged(complete.state(), addReference(complete.state(), Reference.ACTIVE_READER), Decision.RUN_CLOSED);
        unchanged(complete.state(), addBackupPin(complete.state(), BackupPin.EVIDENCE), Decision.RUN_CLOSED);
    }
}
