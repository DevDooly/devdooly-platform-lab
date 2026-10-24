import type { Outcome, OutcomeStatus } from './api.ts';

export interface EventSearchFilters {
  status: 'ALL' | OutcomeStatus;
  query: string;
  reason: string | null;
}

/** Filter already-read outcomes without changing their identity, order or reported fields. */
export function filterEventOutcomes(outcomes: readonly Outcome[], filters: EventSearchFilters): Outcome[] {
  const query = filters.query.trim().toLowerCase();
  return outcomes.filter(outcome => (filters.status === 'ALL' || outcome.status === filters.status)
    && (filters.reason === null || outcome.reason === filters.reason)
    && (query === '' || outcome.eventId.toLowerCase().includes(query) || outcome.sensorId.toLowerCase().includes(query)));
}

/** Raw reasons in first-seen order; an empty reason remains a selectable value. */
export function eventReasonOptions(outcomes: readonly Outcome[]): string[] {
  return [...new Set(outcomes.map(outcome => outcome.reason))];
}
