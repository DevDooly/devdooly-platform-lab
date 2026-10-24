import type { Outcome } from './api.ts';
import { filterEventOutcomes, type EventSearchFilters } from './event-search.ts';
import { isComparisonRunId } from './run-comparison.ts';

export interface EventShareSelection {
  runId: string;
  filters: EventSearchFilters;
  sequence: number | null;
}

export type EventShareParseResult =
  | { kind: 'absent' }
  | { kind: 'invalid' }
  | { kind: 'valid'; selection: EventShareSelection };

const keys = ['labRun', 'labStatus', 'labQuery', 'labReason', 'labEvent'] as const;
const statuses = new Set(['ALL', 'SUCCESS', 'FAILED', 'DUPLICATE', 'PENDING']);

/** Other page parameters can coexist; only this feature's namespace is interpreted. */
export function parseEventShareSelection(search: string): EventShareParseResult {
  const params = new URLSearchParams(search);
  const namespacedKeys = [...params.keys()].filter(key => key.startsWith('lab'));
  if (namespacedKeys.length === 0) return { kind: 'absent' };
  if (namespacedKeys.some(key => !keys.some(known => known === key))
    || keys.some(key => params.getAll(key).length > 1)
    || ['labRun', 'labStatus', 'labQuery'].some(key => params.getAll(key).length !== 1)) return { kind: 'invalid' };
  const runId = params.get('labRun');
  const status = params.get('labStatus');
  const rawSequence = params.get('labEvent');
  if (!isComparisonRunId(runId) || status === null || !statuses.has(status)
    || (rawSequence !== null && (!/^(0|[1-9]\d*)$/.test(rawSequence) || !Number.isSafeInteger(Number(rawSequence))))) return { kind: 'invalid' };
  return { kind: 'valid', selection: {
    runId,
    filters: { status: status as EventSearchFilters['status'], query: params.get('labQuery')!, reason: params.get('labReason') },
    sequence: rawSequence === null ? null : Number(rawSequence),
  } };
}

/** Share selection only, never an endpoint, response timestamp or frozen result. */
export function eventSharePath(selection: EventShareSelection, basePath = '/'): string | null {
  const { runId, filters, sequence } = selection;
  if (!isComparisonRunId(runId) || !statuses.has(filters.status) || typeof filters.query !== 'string'
    || (filters.reason !== null && typeof filters.reason !== 'string')
    || (sequence !== null && (!Number.isSafeInteger(sequence) || sequence < 0))) return null;
  if (!/^\/(?:[a-z0-9._~-]+\/)*[a-z0-9._~-]*$/i.test(basePath)
    || basePath.split('/').some(part => part === '.' || part === '..')) return null;
  const params = new URLSearchParams({ labRun: runId, labStatus: filters.status, labQuery: filters.query });
  if (filters.reason !== null) params.set('labReason', filters.reason);
  if (sequence !== null) params.set('labEvent', String(sequence));
  return basePath.replace(/\/$/, '') + '/?' + params.toString() + '#lab';
}

/** Resolve by reported sequence in the requested run, without selecting a replacement row. */
export function resolveEventShareSelection(selection: EventShareSelection, outcomes: readonly Outcome[]): {
  sequence: number | null; eventState: 'none' | 'selected' | 'missing' | 'filtered';
} {
  if (selection.sequence === null) return { sequence: null, eventState: 'none' };
  const row = outcomes.find(outcome => outcome.sequence === selection.sequence);
  if (!row) return { sequence: null, eventState: 'missing' };
  return filterEventOutcomes([row], selection.filters).length === 1
    ? { sequence: row.sequence, eventState: 'selected' }
    : { sequence: null, eventState: 'filtered' };
}
