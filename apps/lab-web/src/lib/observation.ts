import { fetchLab, isRelease, isRun, isRunDetail, isSummary, liveFailureOf } from './api.ts';
import type { LabData, LiveFailure } from './api.ts';

export interface ObservationRecord {
  schemaVersion: 1;
  kind: 'observed';
  capturedAt: string;
  provenance: { environment: 'mini-pc'; sourceCommit: string; collectorVersion: '1'; evidenceUrl?: string };
  data: LabData;
}
export type SourceMode = 'live' | 'recorded' | 'fixture';
export interface SourceSelection { mode: SourceMode; data: LabData; observation: ObservationRecord | null; }
const object = (value: unknown): value is Record<string, unknown> => typeof value === 'object' && value !== null;
const onlyKeys = (value: Record<string, unknown>, keys: string[]) => Object.keys(value).every(key => keys.includes(key));
const utc = (value: unknown): value is string => typeof value === 'string' && /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?Z$/.test(value) && !Number.isNaN(Date.parse(value));
const runKeys = ['id', 'name', 'status', 'synthetic', 'seed', 'inputCount', 'successCount', 'failureCount', 'duplicateCount', 'pendingCount', 'startedAt', 'completedAt'];
function publicEvidenceUrl(value: unknown): boolean {
  if (typeof value !== 'string') return false;
  try {
    const url = new URL(value);
    return url.protocol === 'https:' && !url.username && !url.password && !url.search
      && (url.hostname === 'github.com' || url.hostname === 'devdooly.github.io');
  } catch { return false; }
}
export function isObservationRecord(value: unknown): value is ObservationRecord {
  if (!object(value) || !onlyKeys(value, ['schemaVersion', 'kind', 'capturedAt', 'provenance', 'data']) || value.schemaVersion !== 1 || value.kind !== 'observed' || !utc(value.capturedAt)) return false;
  const provenance = value.provenance;
  if (!object(provenance) || !onlyKeys(provenance, ['environment', 'sourceCommit', 'collectorVersion', 'evidenceUrl'])
    || provenance.environment !== 'mini-pc' || provenance.collectorVersion !== '1'
    || typeof provenance.sourceCommit !== 'string' || !/^[a-f0-9]{40}$/.test(provenance.sourceCommit)
    || ('evidenceUrl' in provenance && !publicEvidenceUrl(provenance.evidenceUrl))) return false;
  const data = value.data;
  if (!object(data) || !onlyKeys(data, ['runs', 'detail', 'summary', 'releases', 'observedAt']) || !utc(data.observedAt)
    || !Array.isArray(data.runs) || !data.runs.length || data.runs.length > 20
    || !data.runs.every(run => isRun(run) && object(run) && onlyKeys(run, runKeys))
    || !isRunDetail(data.detail) || !object(data.detail) || !onlyKeys(data.detail, [...runKeys, 'observedAt', 'scenario', 'description', 'outcomes', 'series', 'failureReasons'])
    || !isSummary(data.summary) || !object(data.summary) || !onlyKeys(data.summary, ['service', 'status', 'environment', 'sourceCommit', 'synthetic', 'publicExecutionEnabled', 'components', 'observedAt'])
    || !Array.isArray(data.releases) || !data.releases.length || !data.releases.every(release => isRelease(release) && object(release) && onlyKeys(release, ['service', 'version', 'sourceCommit', 'imageDigest', 'deploymentStatus', 'startedAt']))) return false;
  const detail = data.detail;
  if (!detail.outcomes.every(row => onlyKeys(row as unknown as Record<string, unknown>, ['sequence', 'eventId', 'sensorId', 'eventTime', 'value', 'status', 'reason']))
    || !detail.series.every(point => onlyKeys(point as unknown as Record<string, unknown>, ['eventTime', 'sensorId', 'value']))
    || !detail.failureReasons.every(reason => onlyKeys(reason as unknown as Record<string, unknown>, ['reason', 'count']))
    || !data.summary.components.every(component => onlyKeys(component as unknown as Record<string, unknown>, ['name', 'status', 'detail']))) return false;
  if (data.summary.sourceCommit !== provenance.sourceCommit || data.summary.publicExecutionEnabled !== false
    || data.summary.synthetic !== true || !data.releases.some(release => release.service === 'api' && release.sourceCommit === provenance.sourceCommit)) return false;
  if (detail.id !== 'synthetic-v1-seed-42' || detail.scenario !== 'sensor-validation-v1' || detail.seed !== 42 || !detail.synthetic
    || detail.inputCount !== 12 || detail.successCount !== 7 || detail.failureCount !== 3 || detail.duplicateCount !== 2 || detail.pendingCount !== 0) return false;
  const listed = data.runs.find(run => run.id === detail.id);
  if (!listed || !runKeys.every(key => listed[key as keyof typeof listed] === detail[key as keyof typeof detail])) return false;
  const expected = [['SUCCESS', 'ACCEPTED'], ['SUCCESS', 'ACCEPTED'], ['SUCCESS', 'ACCEPTED'], ['DUPLICATE', 'DUPLICATE_EVENT_ID'], ['FAILED', 'INVALID_TIMESTAMP'], ['FAILED', 'OUT_OF_ORDER'], ['FAILED', 'OUT_OF_RANGE'], ['SUCCESS', 'ACCEPTED'], ['SUCCESS', 'ACCEPTED'], ['SUCCESS', 'ACCEPTED'], ['DUPLICATE', 'DUPLICATE_EVENT_ID'], ['SUCCESS', 'ACCEPTED']];
  if (detail.outcomes.length !== expected.length || !detail.outcomes.every((row, index) => row.sequence === index + 1 && row.status === expected[index]?.[0] && row.reason === expected[index]?.[1])) return false;
  if (detail.failureReasons.length !== 3 || !['INVALID_TIMESTAMP', 'OUT_OF_ORDER', 'OUT_OF_RANGE'].every(reason => detail.failureReasons.some(item => item.reason === reason && item.count === 1))) return false;
  const successes = detail.outcomes.filter(row => row.status === 'SUCCESS');
  if (detail.series.length !== successes.length || !detail.series.every((point, index) => {
    const row = successes[index]; return row && point.eventTime === row.eventTime && point.sensorId === row.sensorId && point.value === row.value;
  })) return false;
  const timestamps = [data.observedAt, data.summary.observedAt, detail.observedAt, ...data.runs.flatMap(run => [run.startedAt, run.completedAt]), ...data.releases.map(release => release.startedAt)];
  return timestamps.every(time => utc(time) && Date.parse(time) <= Date.parse(value.capturedAt as string));
}
export function selectDataSource(live: LabData | null, observation: ObservationRecord | null, fixture: LabData): SourceSelection {
  if (live) return { mode: 'live', data: live, observation: null };
  if (observation) return { mode: 'recorded', data: observation.data, observation };
  return { mode: 'fixture', data: fixture, observation: null };
}
export async function fetchObservation(url: string, signal?: AbortSignal): Promise<ObservationRecord | null> {
  const response = await fetch(url, { signal, headers: { Accept: 'application/json' }, cache: 'no-store' });
  if (response.status === 404) return null;
  if (!response.ok) throw new Error(`관측 기록 응답 ${response.status}`);
  const payload: unknown = await response.json();
  if (!isObservationRecord(payload)) throw new Error('관측 기록의 형식 또는 출처를 확인할 수 없습니다.');
  return payload;
}
export async function loadLabSources(options: {
  apiBase: string; observationUrl: string; fixture: LabData; signal?: AbortSignal;
  preferredId?: string; previousObservation?: ObservationRecord | null;
}): Promise<SourceSelection & { cachedObservation: ObservationRecord | null; liveFailure: LiveFailure | null }> {
  const observationSignal = options.signal ? AbortSignal.any([options.signal, AbortSignal.timeout(3000)]) : AbortSignal.timeout(3000);
  const [liveResult, observationResult] = await Promise.allSettled([
    fetchLab(options.apiBase, options.signal, options.preferredId), fetchObservation(options.observationUrl, observationSignal),
  ]);
  const candidates = [observationResult.status === 'fulfilled' ? observationResult.value : null, options.previousObservation || null].filter((record): record is ObservationRecord => record !== null);
  const record = candidates.sort((left, right) => Date.parse(right.capturedAt) - Date.parse(left.capturedAt))[0] || null;
  // Promise.all reports the first observed live-query failure, not a system root cause.
  return { ...selectDataSource(liveResult.status === 'fulfilled' ? liveResult.value : null, record, options.fixture), cachedObservation: record,
    liveFailure: liveResult.status === 'rejected' ? liveFailureOf(liveResult.reason) : null };
}
