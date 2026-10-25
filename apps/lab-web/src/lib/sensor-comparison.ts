import type { Outcome } from './api.ts';
import { sensorOutcomeSummary, type SensorOutcomeGroup, type SensorOutcomeSummary } from './sensor-outcomes.ts';

export interface SensorComparisonRow {
  sensorId: string;
  left: SensorOutcomeGroup | null;
  right: SensorOutcomeGroup | null;
  /** B minus A; unavailable when either observation has no rows for this raw ID. */
  delta: { total: number; success: number; failure: number; duplicate: number; pending: number } | null;
  /** Percentage-point difference, B minus A, using each side's own observed sensor total. */
  failureRateDelta: number | null;
  /** Presence or outcome-count difference only; reasons, values and times are not compared. */
  different: boolean;
}

export interface SensorComparison {
  left: SensorOutcomeSummary;
  right: SensorOutcomeSummary;
  rows: SensorComparisonRow[];
}

export type SensorComparisonOrder = 'first' | 'failure-delta' | 'failure-rate-delta';

/** Compare already-read observations by raw sensor ID without inferring an unobserved sensor's counts. */
export function compareSensorOutcomes(leftOutcomes: readonly Outcome[], rightOutcomes: readonly Outcome[]): SensorComparison {
  const left = sensorOutcomeSummary(leftOutcomes), right = sensorOutcomeSummary(rightOutcomes);
  const leftById = new Map(left.sensors.map(group => [group.sensorId, group]));
  const rightById = new Map(right.sensors.map(group => [group.sensorId, group]));
  const ids = new Set([...leftById.keys(), ...rightById.keys()]);
  const rows = [...ids].map(sensorId => {
    const a = leftById.get(sensorId) ?? null, b = rightById.get(sensorId) ?? null;
    const delta = a && b ? { total: b.total - a.total, success: b.success - a.success,
      failure: b.failure - a.failure, duplicate: b.duplicate - a.duplicate, pending: b.pending - a.pending } : null;
    return { sensorId, left: a, right: b, delta,
      failureRateDelta: a && b ? b.failureRate - a.failureRate : null,
      different: delta === null || Object.values(delta).some(value => value !== 0) };
  });
  return { left, right, rows };
}

/** Local raw-ID text search and absolute-difference ordering; first-seen order breaks ties. */
export function selectSensorComparisons(rows: readonly SensorComparisonRow[], options: {
  query: string; differencesOnly: boolean; order?: SensorComparisonOrder;
}): SensorComparisonRow[] {
  const query = options.query.trim().toLowerCase();
  const selected = rows.filter(row => (!options.differencesOnly || row.different) && row.sensorId.toLowerCase().includes(query));
  if (options.order === 'failure-delta' || options.order === 'failure-rate-delta') {
    const value = options.order === 'failure-delta'
      ? (row: SensorComparisonRow) => row.delta?.failure ?? null
      : (row: SensorComparisonRow) => row.failureRateDelta;
    selected.sort((a, b) => {
      const first = value(a), second = value(b);
      if (first === null) return second === null ? 0 : 1;
      if (second === null) return -1;
      return Math.abs(second) - Math.abs(first);
    });
  }
  return selected;
}
