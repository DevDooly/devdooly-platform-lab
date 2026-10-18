export type OutcomeStatus = 'SUCCESS' | 'FAILED' | 'DUPLICATE' | 'PENDING';
export interface Run {
  id: string; name: string; status: string; synthetic: boolean; seed: number;
  inputCount: number; successCount: number; failureCount: number; duplicateCount: number; pendingCount: number;
  startedAt: string | null; completedAt: string | null;
}
export interface Outcome {
  sequence: number; eventId: string; sensorId: string; eventTime: string; value: number | null;
  status: OutcomeStatus; reason: string;
}
export interface Point { eventTime: string; sensorId: string; value: number; }
export interface RunDetail extends Run {
  observedAt: string | null; scenario: string; description: string;
  outcomes: Outcome[]; series: Point[]; failureReasons: { reason: string; count: number }[];
}
export interface Component { name: string; status: string; detail: string; }
export interface Summary {
  service: string; status: string; environment: string; sourceCommit: string; synthetic: boolean;
  publicExecutionEnabled: boolean; components: Component[]; observedAt: string | null;
}
export interface Release {
  service: string; version: string; sourceCommit: string; imageDigest: string | null;
  deploymentStatus: string; startedAt: string | null;
}
export interface LabData {
  runs: Run[]; detail: RunDetail; summary: Summary; releases: Release[];
  observedAt: string | null; capturedAt?: string; snapshotNote?: string;
}

const object = (value: unknown): value is Record<string, unknown> => typeof value === 'object' && value !== null;
const text = (value: unknown): value is string => typeof value === 'string';
const count = (value: unknown): value is number => typeof value === 'number' && Number.isSafeInteger(value) && value >= 0;
const timestamp = (value: unknown): value is string => text(value) && !Number.isNaN(Date.parse(value));
export function isRun(value: unknown): value is Run {
  if (!object(value)) return false;
  return text(value.id) && text(value.name) && text(value.status) && typeof value.synthetic === 'boolean' && count(value.seed)
    && ['inputCount', 'successCount', 'failureCount', 'duplicateCount', 'pendingCount'].every(key => count(value[key]))
    && value.inputCount === Number(value.successCount) + Number(value.failureCount) + Number(value.duplicateCount) + Number(value.pendingCount)
    && timestamp(value.startedAt) && timestamp(value.completedAt);
}
export function isRunDetail(value: unknown): value is RunDetail {
  if (!isRun(value) || !object(value)) return false;
  return text(value.scenario) && text(value.description) && timestamp(value.observedAt)
    && Array.isArray(value.series) && value.series.every(point => object(point) && timestamp(point.eventTime) && text(point.sensorId) && typeof point.value === 'number' && Number.isFinite(point.value))
    && Array.isArray(value.outcomes) && value.outcomes.every(row => object(row) && count(row.sequence) && text(row.eventId) && text(row.sensorId) && text(row.eventTime) && (row.value === null || (typeof row.value === 'number' && Number.isFinite(row.value))) && ['SUCCESS', 'FAILED', 'DUPLICATE', 'PENDING'].includes(String(row.status)) && text(row.reason))
    && Array.isArray(value.failureReasons) && value.failureReasons.every(reason => object(reason) && text(reason.reason) && count(reason.count));
}
export function isSummary(value: unknown): value is Summary {
  return object(value) && text(value.service) && text(value.status) && text(value.environment) && text(value.sourceCommit)
    && typeof value.synthetic === 'boolean' && typeof value.publicExecutionEnabled === 'boolean' && timestamp(value.observedAt)
    && Array.isArray(value.components) && value.components.every(component => object(component) && text(component.name) && text(component.status) && text(component.detail));
}
export function isRelease(value: unknown): value is Release {
  return object(value) && text(value.service) && text(value.version) && text(value.sourceCommit)
    && (value.imageDigest === null || text(value.imageDigest)) && text(value.deploymentStatus) && timestamp(value.startedAt);
}
export async function getJson(base: string, path: string, signal?: AbortSignal): Promise<unknown> {
  const response = await fetch(`${base.replace(/\/$/, '')}${path}`, { signal, headers: { Accept: 'application/json' }, cache: 'no-store', credentials: 'omit', redirect: 'error' });
  if (!response.ok) throw new Error(`API 응답 ${response.status}`);
  return response.json();
}
export async function fetchRun(base: string, id: string, signal?: AbortSignal): Promise<RunDetail> {
  const detail = await getJson(base, `/demo/runs/${encodeURIComponent(id)}`, signal);
  if (!isRunDetail(detail)) throw new Error('실행 결과 형식을 확인할 수 없습니다.');
  return detail;
}
export async function fetchLab(base: string, signal?: AbortSignal, preferredId?: string): Promise<LabData> {
  const [runsPayload, summary, releasePayload] = await Promise.all([
    getJson(base, '/demo/runs', signal), getJson(base, '/platform/summary', signal), getJson(base, '/platform/releases', signal),
  ]);
  if (!object(runsPayload) || !Array.isArray(runsPayload.items) || !runsPayload.items.every(isRun) || !timestamp(runsPayload.observedAt)) throw new Error('실행 목록 형식을 확인할 수 없습니다.');
  if (!isSummary(summary) || !object(releasePayload) || !Array.isArray(releasePayload.items) || !releasePayload.items.every(isRelease) || !timestamp(releasePayload.observedAt)) throw new Error('플랫폼 응답 형식을 확인할 수 없습니다.');
  const runs = runsPayload.items;
  const selected = runs.find(run => run.id === preferredId) || runs[0];
  if (!selected) throw new Error('아직 저장된 실행 결과가 없습니다.');
  const detail = await fetchRun(base, selected.id, signal);
  return { runs, detail, summary, releases: releasePayload.items, observedAt: summary.observedAt };
}
