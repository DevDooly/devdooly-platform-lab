import type { Outcome } from './api.ts';

export interface SensorOutcomeGroup {
  sensorId: string;
  total: number;
  success: number;
  failure: number;
  duplicate: number;
  pending: number;
  /** Percentage of this sensor's observed outcome rows, not reported run input. */
  failureRate: number;
  failureReasons: { reason: string; count: number }[];
}

export interface SensorOutcomeSummary {
  availableOutcomes: number;
  sensors: SensorOutcomeGroup[];
}

export type SensorGroupOrder = 'first' | 'failure-count' | 'failure-rate';

/** Group already-read rows by exact raw sensor ID, retaining every observed row. */
export function sensorOutcomeSummary(outcomes: readonly Outcome[]): SensorOutcomeSummary {
  const sensors = new Map<string, { group: SensorOutcomeGroup; reasons: Map<string, number> }>();
  for (const outcome of outcomes) {
    let sensor = sensors.get(outcome.sensorId);
    if (!sensor) {
      sensor = { group: { sensorId: outcome.sensorId, total: 0, success: 0, failure: 0,
        duplicate: 0, pending: 0, failureRate: 0, failureReasons: [] }, reasons: new Map() };
      sensors.set(outcome.sensorId, sensor);
    }
    sensor.group.total++;
    switch (outcome.status) {
      case 'SUCCESS': sensor.group.success++; break;
      case 'FAILED':
        sensor.group.failure++;
        sensor.reasons.set(outcome.reason, (sensor.reasons.get(outcome.reason) ?? 0) + 1);
        break;
      case 'DUPLICATE': sensor.group.duplicate++; break;
      case 'PENDING': sensor.group.pending++; break;
    }
  }
  return { availableOutcomes: outcomes.length, sensors: [...sensors.values()].map(({ group, reasons }) => ({
    ...group,
    failureRate: group.failure / group.total * 100,
    failureReasons: [...reasons].map(([reason, count]) => ({ reason, count })),
  })) };
}

/** Local sensor-name search and ordering; neither alters event filters or source rows. */
export function selectSensorGroups(groups: readonly SensorOutcomeGroup[], query: string, order: SensorGroupOrder): SensorOutcomeGroup[] {
  const normalizedQuery = query.trim().toLowerCase();
  const selected = groups.filter(group => group.sensorId.toLowerCase().includes(normalizedQuery));
  if (order === 'failure-count') selected.sort((a, b) => b.failure - a.failure);
  if (order === 'failure-rate') selected.sort((a, b) => b.failureRate - a.failureRate);
  return selected;
}
