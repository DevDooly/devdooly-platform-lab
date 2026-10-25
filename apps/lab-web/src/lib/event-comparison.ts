import type { Outcome } from './api.ts';

export type EventComparisonKind = 'ambiguous' | 'unobserved' | 'input-different' | 'verdict-different' | 'observed-equal';

export interface EventComparisonRow {
  sequence: number;
  left: Outcome[];
  right: Outcome[];
  inputDifferences: ('eventId' | 'sensorId' | 'eventTime' | 'value')[] | null;
  verdictDifferences: ('status' | 'reason')[] | null;
  kind: EventComparisonKind;
}

const inputFields = ['eventId', 'sensorId', 'eventTime', 'value'] as const;
const verdictFields = ['status', 'reason'] as const;

function bySequence(outcomes: readonly Outcome[]): Map<number, Outcome[]> {
  const groups = new Map<number, Outcome[]>();
  for (const outcome of outcomes) {
    const group = groups.get(outcome.sequence);
    if (group) group.push(outcome);
    else groups.set(outcome.sequence, [outcome]);
  }
  return groups;
}

/** Align observed positions only; matching reported fields do not establish original-input identity. */
export function compareEventOutcomes(left: readonly Outcome[], right: readonly Outcome[]): {
  rows: EventComparisonRow[];
  leftCount: number;
  rightCount: number;
  counts: Record<EventComparisonKind, number>;
} {
  const a = bySequence(left), b = bySequence(right);
  const counts: Record<EventComparisonKind, number> = {
    ambiguous: 0, unobserved: 0, 'input-different': 0, 'verdict-different': 0, 'observed-equal': 0,
  };
  const sequences = [...new Set([...a.keys(), ...b.keys()])].sort((first, second) => first - second);
  const rows = sequences.map((sequence): EventComparisonRow => {
    const leftRows = a.get(sequence) ?? [], rightRows = b.get(sequence) ?? [];
    let inputDifferences: EventComparisonRow['inputDifferences'] = null;
    let verdictDifferences: EventComparisonRow['verdictDifferences'] = null;
    let kind: EventComparisonKind;
    if (leftRows.length > 1 || rightRows.length > 1) kind = 'ambiguous';
    else if (leftRows.length === 0 || rightRows.length === 0) kind = 'unobserved';
    else {
      const first = leftRows[0]!, second = rightRows[0]!;
      inputDifferences = inputFields.filter(field => first[field] !== second[field]);
      verdictDifferences = verdictFields.filter(field => first[field] !== second[field]);
      kind = inputDifferences.length > 0 ? 'input-different'
        : verdictDifferences.length > 0 ? 'verdict-different' : 'observed-equal';
    }
    counts[kind] += 1;
    return { sequence, left: leftRows, right: rightRows, inputDifferences, verdictDifferences, kind };
  });
  return { rows, leftCount: left.length, rightCount: right.length, counts };
}

/** Local literal ID search and category selection preserve the comparison's order and row references. */
export function selectEventComparisons(rows: readonly EventComparisonRow[], options: {
  query: string;
  kind: 'all' | EventComparisonKind;
}): EventComparisonRow[] {
  const query = options.query.trim().toLowerCase();
  return rows.filter(row => (options.kind === 'all' || row.kind === options.kind)
    && [...row.left, ...row.right].some(outcome => outcome.eventId.toLowerCase().includes(query)
      || outcome.sensorId.toLowerCase().includes(query)));
}
