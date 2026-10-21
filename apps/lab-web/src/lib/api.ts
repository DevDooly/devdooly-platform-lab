import { isPublicReadPath } from './public-api-base.ts';
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

export type LiveFailureKind = 'HTTP_REJECTED' | 'INVALID_RESPONSE' | 'REQUEST_ABORTED' | 'NETWORK_UNVERIFIED' | 'OTHER';
export interface LiveFailure { kind: LiveFailureKind; httpStatus: number | null; }
class LabReadError extends Error {
  readonly failure: LiveFailure;
  constructor(message: string, kind: LiveFailureKind, status: number | null = null) {
    super(message);
    this.failure = kind === 'HTTP_REJECTED' && (!Number.isInteger(status) || status === null || status < 100 || status > 599)
      ? { kind: 'OTHER', httpStatus: null }
      : { kind, httpStatus: kind === 'HTTP_REJECTED' ? status : null };
  }
}
// Only this projection crosses into source selection and UI; never forward an exception.
export function liveFailureOf(error: unknown): LiveFailure {
  if (error instanceof LabReadError) return { ...error.failure };
  return { kind: error instanceof TypeError ? 'NETWORK_UNVERIFIED' : 'OTHER', httpStatus: null };
}
export function describeLiveFailure(failure: LiveFailure): string {
  switch (failure.kind) {
    case 'HTTP_REJECTED': return `실시간 Lab 연결 불가: HTTP 응답 오류(${failure.httpStatus})`;
    case 'INVALID_RESPONSE': return '실시간 Lab 연결 불가: 응답 형식 또는 실행 ID를 확인하지 못했습니다.';
    case 'REQUEST_ABORTED': return '실시간 Lab 연결 불가: 요청이 중단되었습니다.';
    case 'NETWORK_UNVERIFIED': return '실시간 Lab 연결 불가: 네트워크 요청을 완료하지 못했습니다. 원인은 확인되지 않았습니다.';
    default: return '실시간 Lab 연결 불가';
  }
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
  // The page validates public configuration; retain the generic integration/smoke transport.
  if (base === 'invalid-public-api-base' || !isPublicReadPath(path)) throw new LabReadError('공개 조회 주소를 확인할 수 없습니다.', 'OTHER');
  const url = `${base.replace(/\/$/, '')}${path}`;
  try {
    const response = await fetch(url, { signal, headers: { Accept: 'application/json' }, cache: 'no-store', credentials: 'omit', redirect: 'error' });
    if (!response.ok) throw new LabReadError(`API 응답 ${response.status}`, 'HTTP_REJECTED', response.status);
    try { return await response.json(); }
    catch (error) {
      if (error instanceof SyntaxError) throw new LabReadError('API 응답 형식을 확인할 수 없습니다.', 'INVALID_RESPONSE');
      throw error;
    }
  } catch (error) {
    // Preserve an observed HTTP/JSON failure even if the caller aborts afterwards.
    if (error instanceof LabReadError) throw error;
    if (signal?.aborted) throw new LabReadError('실시간 Lab 연결 불가', 'REQUEST_ABORTED');
    if (error instanceof TypeError) throw error;
    throw new LabReadError('실시간 Lab 연결 불가', 'OTHER');
  }
}
export async function fetchRun(base: string, id: string, signal?: AbortSignal): Promise<RunDetail> {
  const detail = await getJson(base, `/demo/runs/${encodeURIComponent(id)}`, signal);
  if (!isRunDetail(detail) || detail.id !== id) throw new LabReadError('실행 결과 형식을 확인할 수 없습니다.', 'INVALID_RESPONSE');
  return detail;
}
export async function fetchLab(base: string, signal?: AbortSignal, preferredId?: string): Promise<LabData> {
  const [runsPayload, summary, releasePayload] = await Promise.all([
    getJson(base, '/demo/runs', signal), getJson(base, '/platform/summary', signal), getJson(base, '/platform/releases', signal),
  ]);
  if (!object(runsPayload) || !Array.isArray(runsPayload.items) || !runsPayload.items.every(isRun) || !timestamp(runsPayload.observedAt)) throw new LabReadError('실행 목록 형식을 확인할 수 없습니다.', 'INVALID_RESPONSE');
  if (!isSummary(summary) || !object(releasePayload) || !Array.isArray(releasePayload.items) || !releasePayload.items.every(isRelease) || !timestamp(releasePayload.observedAt)) throw new LabReadError('플랫폼 응답 형식을 확인할 수 없습니다.', 'INVALID_RESPONSE');
  const runs = runsPayload.items;
  const selected = runs.find(run => run.id === preferredId) || runs[0];
  if (!selected) throw new LabReadError('아직 저장된 실행 결과가 없습니다.', 'OTHER');
  const detail = await fetchRun(base, selected.id, signal);
  return { runs, detail, summary, releases: releasePayload.items, observedAt: summary.observedAt };
}
