import { boundedObservationText, discardObservationBody, InvalidObservationBody } from './observation-response-body.ts';
/** Public platform snapshot v1. No management endpoints or free-form errors. */
export const PLATFORM_STALE_AFTER_MS = 2 * 60 * 60 * 1000;
export const PLATFORM_ERROR_CODES = [
  'NONE', 'GITHUB_STATUS_UNAVAILABLE', 'ARGO_UNAVAILABLE', 'WORKLOADS_UNAVAILABLE',
  'AUTHENTICATION_FAILED', 'TIMEOUT', 'INVALID_OBSERVATION', 'COLLECTION_FAILED',
] as const;
export type PlatformErrorCode = typeof PLATFORM_ERROR_CODES[number];
export type PlatformAttempt =
  | { attemptedAt: string; status: 'success'; errorCode: 'NONE' }
  | { attemptedAt: string; status: 'failure'; errorCode: Exclude<PlatformErrorCode, 'NONE'> };
export interface JenkinsObservation {
  sourceCommit: string;
  statusId: number;
  state: 'pending' | 'success' | 'failure' | 'error';
  createdAt: string;
  buildNumber: number;
  issuer: 'DevDooly' | 'devdooly-platform-lab-ops[bot]';
}
export interface ArgoObservation {
  revision: string;
  sync: 'Synced' | 'OutOfSync' | 'Unknown';
  health: 'Healthy' | 'Progressing' | 'Degraded' | 'Suspended' | 'Missing' | 'Unknown';
}
export type WorkloadObservation =
  | { component: 'api' | 'web'; desired: number; ready: number; image: string }
  | { component: 'database'; desired: number; ready: number };
export interface PlatformSuccess {
  capturedAt: string;
  collectorVersion: '1';
  mainCommit: string;
  jenkins: JenkinsObservation | null;
  argo: ArgoObservation;
  workloads: WorkloadObservation[];
  /** API Deployment template source annotation; not a JVM source query. */
  deploymentSourceCommit: string;
}
export interface PlatformObservationRecord {
  schemaVersion: 1;
  kind: 'platform-observation';
  latestAttempt: PlatformAttempt;
  lastSuccess: PlatformSuccess | null;
}

export const MAX_PLATFORM_OBSERVATION_BYTES = 16 * 1024;
const sha = (value: unknown): value is string => typeof value === 'string' && /^[a-f0-9]{40}$/.test(value);
const object = (value: unknown): value is Record<string, unknown> => typeof value === 'object' && value !== null && !Array.isArray(value);
const exact = (value: Record<string, unknown>, keys: readonly string[]) => Object.keys(value).length === keys.length && keys.every(key => Object.hasOwn(value, key));
const integer = (value: unknown, min: number, max: number): value is number => typeof value === 'number' && Number.isSafeInteger(value) && value >= min && value <= max;
const oneOf = (value: unknown, choices: readonly string[]): value is string => typeof value === 'string' && choices.includes(value);

/** Strict calendar validation and nanosecond ordering, without Date.parse normalization. */
function utcNanoseconds(value: unknown): bigint | null {
  if (typeof value !== 'string') return null;
  const match = /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2}):(\d{2})(?:\.(\d{1,9}))?Z$/.exec(value);
  if (!match) return null;
  const [year, month, day, hour, minute, second] = match.slice(1, 7).map(Number);
  if (year! < 1 || month! < 1 || month! > 12 || day! < 1 || day! > 31 || hour! > 23 || minute! > 59 || second! > 59) return null;
  const date = new Date(0);
  date.setUTCFullYear(year!, month! - 1, day!);
  date.setUTCHours(hour!, minute!, second!, 0);
  if (date.getUTCFullYear() !== year || date.getUTCMonth() !== month! - 1 || date.getUTCDate() !== day) return null;
  return BigInt(date.getTime()) * 1_000_000n + BigInt((match[7] || '').padEnd(9, '0'));
}

function isJenkins(value: unknown): value is JenkinsObservation {
  return object(value) && exact(value, ['sourceCommit', 'statusId', 'state', 'createdAt', 'buildNumber', 'issuer'])
    && sha(value.sourceCommit) && integer(value.statusId, 1, Number.MAX_SAFE_INTEGER)
    && oneOf(value.state, ['pending', 'success', 'failure', 'error']) && utcNanoseconds(value.createdAt) !== null
    && integer(value.buildNumber, 1, 2_147_483_647)
    && oneOf(value.issuer, ['DevDooly', 'devdooly-platform-lab-ops[bot]']);
}
function isArgo(value: unknown): value is ArgoObservation {
  return object(value) && exact(value, ['revision', 'sync', 'health']) && sha(value.revision)
    && oneOf(value.sync, ['Synced', 'OutOfSync', 'Unknown'])
    && oneOf(value.health, ['Healthy', 'Progressing', 'Degraded', 'Suspended', 'Missing', 'Unknown']);
}
function isWorkload(value: unknown): value is WorkloadObservation {
  if (!object(value) || !oneOf(value.component, ['api', 'web', 'database'])
    || !integer(value.desired, 0, 10) || !integer(value.ready, 0, 10)) return false;
  if (value.component === 'database') return exact(value, ['component', 'desired', 'ready']);
  return exact(value, ['component', 'desired', 'ready', 'image']) && typeof value.image === 'string'
    && new RegExp(`^ghcr\\.io/devdooly/devdooly-platform-lab-${value.component}@sha256:[a-f0-9]{64}$`).test(value.image);
}
function isSuccess(value: unknown): value is PlatformSuccess {
  if (!object(value) || !exact(value, ['capturedAt', 'collectorVersion', 'mainCommit', 'jenkins', 'argo', 'workloads', 'deploymentSourceCommit'])
    || utcNanoseconds(value.capturedAt) === null || value.collectorVersion !== '1' || !sha(value.mainCommit)
    || !sha(value.deploymentSourceCommit) || !isArgo(value.argo)
    || !Array.isArray(value.workloads) || value.workloads.length !== 3 || !value.workloads.every(isWorkload)) return false;
  const workloads = value.workloads;
  if (!['api', 'web', 'database'].every(component => workloads.filter(item => item.component === component).length === 1)) return false;
  if (value.jenkins === null) return true;
  return isJenkins(value.jenkins) && value.jenkins.sourceCommit === value.mainCommit
    && utcNanoseconds(value.jenkins.createdAt)! <= utcNanoseconds(value.capturedAt)!;
}

/** Pure allowlist validator shared by the browser and trusted publishing tools. */
export function validatePlatformObservation(document: unknown): document is PlatformObservationRecord {
  if (!object(document) || !exact(document, ['schemaVersion', 'kind', 'latestAttempt', 'lastSuccess'])
    || document.schemaVersion !== 1 || document.kind !== 'platform-observation') return false;
  const attempt = document.latestAttempt;
  if (!object(attempt) || !exact(attempt, ['attemptedAt', 'status', 'errorCode'])
    || utcNanoseconds(attempt.attemptedAt) === null || !oneOf(attempt.status, ['success', 'failure'])
    || !oneOf(attempt.errorCode, PLATFORM_ERROR_CODES)) return false;
  if (document.lastSuccess !== null && !isSuccess(document.lastSuccess)) return false;
  if (attempt.status === 'success') return attempt.errorCode === 'NONE' && document.lastSuccess !== null
    && document.lastSuccess.capturedAt === attempt.attemptedAt;
  return attempt.errorCode !== 'NONE' && (document.lastSuccess === null
    || utcNanoseconds(document.lastSuccess.capturedAt)! <= utcNanoseconds(attempt.attemptedAt)!);
}

export type BrowserObservationError = 'NOT_PUBLISHED' | 'HTTP_ERROR' | 'NETWORK_ERROR' | 'INVALID_RECORD' | 'ABORTED' | 'OLDER_RECORD' | 'CONFLICTING_RECORD';
export interface PlatformObservationLoad {
  record: PlatformObservationRecord | null;
  browserError: BrowserObservationError | null;
  retainedPrevious: boolean;
}

/** JSON object key order is not evidence of a different capture. Array order remains significant. */
function sameContent(left: unknown, right: unknown): boolean {
  if (left === right) return true;
  if (Array.isArray(left) || Array.isArray(right)) return Array.isArray(left) && Array.isArray(right)
    && left.length === right.length && left.every((item, index) => sameContent(item, right[index]));
  if (!object(left) || !object(right)) return false;
  const keys = Object.keys(left);
  return keys.length === Object.keys(right).length && keys.every(key => Object.hasOwn(right, key) && sameContent(left[key], right[key]));
}

/** Match Pages publication: independently retain the latest attempt and latest success from validated records. */
function mergePlatformRecords(previous: PlatformObservationRecord | null, incoming: PlatformObservationRecord): PlatformObservationLoad {
  if (!previous) return { record: incoming, browserError: null, retainedPrevious: false };
  const failed = (browserError: BrowserObservationError): PlatformObservationLoad => ({ record: previous, browserError, retainedPrevious: true });
  const beforeAttempt = utcNanoseconds(previous.latestAttempt.attemptedAt)!;
  const afterAttempt = utcNanoseconds(incoming.latestAttempt.attemptedAt)!;
  const beforeSuccess = previous.lastSuccess ? utcNanoseconds(previous.lastSuccess.capturedAt)! : null;
  const afterSuccess = incoming.lastSuccess ? utcNanoseconds(incoming.lastSuccess.capturedAt)! : null;
  if (afterAttempt === beforeAttempt && !sameContent(previous.latestAttempt, incoming.latestAttempt)
    || beforeSuccess !== null && afterSuccess === beforeSuccess && !sameContent(previous.lastSuccess, incoming.lastSuccess)) {
    return failed('CONFLICTING_RECORD');
  }
  const newerSuccess = afterSuccess !== null && (beforeSuccess === null || afterSuccess > beforeSuccess);
  const keepAttempt = afterAttempt < beforeAttempt;
  const keepSuccess = beforeSuccess !== null && (afterSuccess === null || afterSuccess < beforeSuccess);
  if (afterAttempt <= beforeAttempt && !newerSuccess) {
    if (keepAttempt || keepSuccess) return failed('OLDER_RECORD');
    return { record: previous, browserError: null, retainedPrevious: false };
  }
  if (!keepAttempt && !keepSuccess) return { record: incoming, browserError: null, retainedPrevious: false };
  return { record: { ...incoming, latestAttempt: keepAttempt ? previous.latestAttempt : incoming.latestAttempt,
    lastSuccess: keepSuccess ? previous.lastSuccess : incoming.lastSuccess }, browserError: null, retainedPrevious: true };
}

/** Failed browser fetches keep an already validated record; collector failures are valid payloads. */
export async function loadPlatformObservation(options: {
  url: string; previousRecord?: PlatformObservationRecord | null; signal?: AbortSignal; fetcher?: typeof fetch;
}): Promise<PlatformObservationLoad> {
  const previous = validatePlatformObservation(options.previousRecord) ? options.previousRecord : null;
  const failed = (browserError: BrowserObservationError): PlatformObservationLoad => ({ record: previous, browserError, retainedPrevious: previous !== null });
  try {
    const response = await (options.fetcher || fetch)(options.url, { signal: options.signal, headers: { Accept: 'application/json' }, cache: 'no-store', credentials: 'omit' });
    if (!response.ok) {
      discardObservationBody(response);
      return failed(response.status === 404 ? 'NOT_PUBLISHED' : 'HTTP_ERROR');
    }
    const text = await boundedObservationText(response, MAX_PLATFORM_OBSERVATION_BYTES);
    let payload: unknown;
    try { payload = JSON.parse(text); } catch { return failed('INVALID_RECORD'); }
    if (!validatePlatformObservation(payload)) return failed('INVALID_RECORD');
    return mergePlatformRecords(previous, payload);
  } catch (error) {
    return failed(options.signal?.aborted ? 'ABORTED'
      : error instanceof InvalidObservationBody ? 'INVALID_RECORD' : 'NETWORK_ERROR');
  }
}

export interface PlatformObservationView {
  collectorFailed: boolean;
  hasSuccess: boolean;
  freshness: 'absent' | 'within-window' | 'stale' | 'clock-check';
}
export function platformObservationView(record: PlatformObservationRecord | null, nowMs: number): PlatformObservationView {
  const collectorFailed = record?.latestAttempt.status === 'failure';
  const success = record?.lastSuccess;
  const attempted = record ? Date.parse(record.latestAttempt.attemptedAt) : null;
  if (!success) return { collectorFailed, hasSuccess: false, freshness: attempted !== null && (!Number.isFinite(nowMs) || attempted > nowMs) ? 'clock-check' : 'absent' };
  const captured = Date.parse(success.capturedAt);
  const freshness = !Number.isFinite(nowMs) || Math.max(captured, attempted!) > nowMs ? 'clock-check'
    : nowMs - captured > PLATFORM_STALE_AFTER_MS ? 'stale' : 'within-window';
  return { collectorFailed, hasSuccess: true, freshness };
}
