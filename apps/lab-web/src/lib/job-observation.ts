import { boundedObservationText, discardObservationBody, InvalidObservationBody } from './observation-response-body.ts';
/** Separate, strict job observation v1. No storage addresses, keys, inputs or free-form errors. */
export const JOB_RECORD_STALE_AFTER_MS = 2 * 60 * 60 * 1000;
export const JOB_HEARTBEAT_STALE_AFTER_MS = 5 * 60 * 1000;
export const MAX_JOB_OBSERVATION_BYTES = 128 * 1024;
export const RUNTIME_FAILURE_CODES = ['PUBLISH_FAILED', 'EXPORT_FAILED', 'RUNTIME_FAILED', 'INTERRUPTED', 'LEASE_LOST', 'INVALID_MESSAGE', 'SOURCE_UNAVAILABLE', 'SOURCE_INVALID', 'JOB_REJECTED', 'PROCESSING_FAILED', 'OFFSET_COMMIT_FAILED', 'POLL_FAILED', 'OPERATOR_RESUME_REQUIRED', 'RESOURCE_CLOSE_FAILED'] as const;
export type RuntimeFailureCode = typeof RUNTIME_FAILURE_CODES[number];
export interface JobRuntimeObservation {
  status: 'NOT_STARTED' | 'RUNNING' | 'PAUSED_OPERATOR' | 'STOPPED';
  stage: 'IDLE' | 'PUBLISH' | 'CONSUME' | 'EXPORT' | 'STOPPED';
  failureCode: RuntimeFailureCode | null;
  startedAt: string | null; heartbeatAt: string | null; stoppedAt: string | null;
  sourceCommit: string; stale: boolean;
}
export interface JobCounts { input: number; success: number; failure: number; duplicate: number; pending: number; }
export interface JobFile { sha256: string; size: number; }
export interface JobObservation {
  runId: string; status: 'STAGING' | 'QUEUED' | 'COMPLETED' | 'TERMINATED';
  exportStatus: 'NOT_REQUESTED' | 'PENDING' | 'EXPORTED' | 'CANCELLED';
  createdAt: string; sourceVerifiedAt: string | null; queuedAt: string | null; completedAt: string | null;
  exportCompletedAt: string | null; terminatedAt: string | null;
  counts: JobCounts | null; files: { result: JobFile; failures: JobFile } | null;
  fileEvidence: 'NOT_AVAILABLE' | 'EXPECTED_FROM_DB' | 'VERIFIED_AT_EXPORT_COMMIT';
}
export interface JobObservationRecord {
  schemaVersion: 1; kind: 'job-observation'; capturedAt: string;
  environment: 'LOCAL' | 'TEST' | 'ISOLATED_LAB' | 'MINI_PC' | 'UNKNOWN';
  sourceCommit: string; synthetic: true; scope: 'LOCAL_VALIDATION' | 'ISOLATED_LAB' | 'DEPLOYED_RUNTIME';
  publicExecutionEnabled: false; runtime: JobRuntimeObservation;
  slot: { occupiedRunId: string | null }; jobs: JobObservation[];
}
const object = (value: unknown): value is Record<string, unknown> => typeof value === 'object' && value !== null && !Array.isArray(value);
const exact = (value: Record<string, unknown>, keys: readonly string[]) => Object.keys(value).length === keys.length && keys.every(key => Object.hasOwn(value, key));
const oneOf = (value: unknown, values: readonly string[]): value is string => typeof value === 'string' && values.includes(value);
const integer = (value: unknown, min: number, max: number): value is number => typeof value === 'number' && Number.isSafeInteger(value) && value >= min && value <= max;
const commit = (value: unknown): value is string => typeof value === 'string' && (value === 'unknown' || /^[a-f0-9]{40}$/.test(value));
const runId = (value: unknown): value is string => typeof value === 'string' && /^[a-z0-9][a-z0-9._-]{0,79}$/.test(value);
const hash = (value: unknown): value is string => typeof value === 'string' && /^[a-f0-9]{64}$/.test(value);

/** Reject normalized dates and compare all allowed nanosecond precision. */
function utcNs(value: unknown): bigint | null {
  if (typeof value !== 'string') return null;
  const match = /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2}):(\d{2})(?:\.(\d{1,9}))?Z$/.exec(value);
  if (!match) return null;
  const [year, month, day, hour, minute, second] = match.slice(1, 7).map(Number);
  if (year! < 1 || month! < 1 || month! > 12 || day! < 1 || day! > 31 || hour! > 23 || minute! > 59 || second! > 59) return null;
  const date = new Date(0); date.setUTCFullYear(year!, month! - 1, day!); date.setUTCHours(hour!, minute!, second!, 0);
  if (date.getUTCFullYear() !== year || date.getUTCMonth() !== month! - 1 || date.getUTCDate() !== day) return null;
  return BigInt(date.getTime()) * 1_000_000n + BigInt((match[7] || '').padEnd(9, '0'));
}
const time = (value: unknown): value is string => utcNs(value) !== null;
const nullableTime = (value: unknown): value is string | null => value === null || time(value);
const beforeOrEqual = (a: string, b: string) => utcNs(a)! <= utcNs(b)!;

function isRuntime(value: unknown): value is JobRuntimeObservation {
  if (!object(value) || !exact(value, ['status', 'stage', 'failureCode', 'startedAt', 'heartbeatAt', 'stoppedAt', 'sourceCommit', 'stale'])
    || !oneOf(value.status, ['NOT_STARTED', 'RUNNING', 'PAUSED_OPERATOR', 'STOPPED']) || !oneOf(value.stage, ['IDLE', 'PUBLISH', 'CONSUME', 'EXPORT', 'STOPPED'])
    || !(value.failureCode === null || oneOf(value.failureCode, RUNTIME_FAILURE_CODES)) || !commit(value.sourceCommit) || typeof value.stale !== 'boolean'
    || !nullableTime(value.startedAt) || !nullableTime(value.heartbeatAt) || !nullableTime(value.stoppedAt)) return false;
  if (value.status === 'NOT_STARTED') return value.stage === 'IDLE' && value.failureCode === null && value.startedAt === null && value.heartbeatAt === null && value.stoppedAt === null && !value.stale;
  if (value.startedAt === null || value.heartbeatAt === null) return false;
  if (value.status === 'RUNNING') return value.stage !== 'STOPPED' && value.failureCode === null && value.stoppedAt === null;
  if (value.stoppedAt === null || value.stale) return false;
  return value.status === 'STOPPED' ? value.stage === 'STOPPED' && value.failureCode === null
    : (value.stage !== 'STOPPED' || value.failureCode === 'RESOURCE_CLOSE_FAILED') && value.failureCode !== null;
}
function isFile(value: unknown): value is JobFile {
  return object(value) && exact(value, ['sha256', 'size']) && hash(value.sha256) && integer(value.size, 1, 4_194_304);
}
function isCounts(value: unknown): value is JobCounts {
  return object(value) && exact(value, ['input', 'success', 'failure', 'duplicate', 'pending'])
    && ['input', 'success', 'failure', 'duplicate', 'pending'].every(key => integer(value[key], 0, 1000))
    && value.input === Number(value.success) + Number(value.failure) + Number(value.duplicate) + Number(value.pending);
}
function isJob(value: unknown): value is JobObservation {
  if (!object(value) || !exact(value, ['runId', 'status', 'exportStatus', 'createdAt', 'sourceVerifiedAt', 'queuedAt', 'completedAt', 'exportCompletedAt', 'terminatedAt', 'counts', 'files', 'fileEvidence'])
    || !runId(value.runId) || !oneOf(value.status, ['STAGING', 'QUEUED', 'COMPLETED', 'TERMINATED'])
    || !oneOf(value.exportStatus, ['NOT_REQUESTED', 'PENDING', 'EXPORTED', 'CANCELLED'])
    || !time(value.createdAt) || !nullableTime(value.sourceVerifiedAt) || !nullableTime(value.queuedAt) || !nullableTime(value.completedAt)
    || !nullableTime(value.exportCompletedAt) || !nullableTime(value.terminatedAt) || !(value.counts === null || isCounts(value.counts))
    || !oneOf(value.fileEvidence, ['NOT_AVAILABLE', 'EXPECTED_FROM_DB', 'VERIFIED_AT_EXPORT_COMMIT'])) return false;
  if (value.files !== null && (!object(value.files) || !exact(value.files, ['result', 'failures']) || !isFile(value.files.result) || !isFile(value.files.failures))) return false;
  if ((value.sourceVerifiedAt === null) !== (value.queuedAt === null)) return false;
  if (value.sourceVerifiedAt !== null && (value.sourceVerifiedAt !== value.queuedAt || !beforeOrEqual(value.createdAt, value.sourceVerifiedAt))) return false;
  if (value.completedAt !== null && (value.queuedAt === null || !beforeOrEqual(value.queuedAt, value.completedAt))) return false;
  if (value.exportCompletedAt !== null && (value.completedAt === null || !beforeOrEqual(value.completedAt, value.exportCompletedAt))) return false;
  if (value.terminatedAt !== null && !beforeOrEqual(value.completedAt || value.createdAt, value.terminatedAt)) return false;
  if (value.status === 'COMPLETED') {
    if (value.completedAt === null || value.counts === null) return false;
    if (value.exportStatus === 'PENDING') return value.files !== null && value.fileEvidence === 'EXPECTED_FROM_DB' && value.exportCompletedAt === null && value.terminatedAt === null;
    if (value.exportStatus === 'EXPORTED') return value.files !== null && value.fileEvidence === 'VERIFIED_AT_EXPORT_COMMIT' && value.exportCompletedAt !== null && value.terminatedAt === null;
    return value.exportStatus === 'CANCELLED' && value.files === null && value.fileEvidence === 'NOT_AVAILABLE' && value.exportCompletedAt === null && value.terminatedAt !== null;
  }
  if (value.completedAt !== null || value.exportCompletedAt !== null || value.exportStatus !== 'NOT_REQUESTED' || value.counts !== null || value.files !== null || value.fileEvidence !== 'NOT_AVAILABLE') return false;
  if (value.status === 'TERMINATED') return value.terminatedAt !== null;
  return value.terminatedAt === null && (value.status === 'STAGING' ? value.queuedAt === null : value.queuedAt !== null);
}

export function validateJobObservation(value: unknown): value is JobObservationRecord {
  if (!object(value) || !exact(value, ['schemaVersion', 'kind', 'capturedAt', 'environment', 'sourceCommit', 'synthetic', 'scope', 'publicExecutionEnabled', 'runtime', 'slot', 'jobs'])
    || value.schemaVersion !== 1 || value.kind !== 'job-observation' || !time(value.capturedAt) || !commit(value.sourceCommit)
    || !oneOf(value.environment, ['LOCAL', 'TEST', 'ISOLATED_LAB', 'MINI_PC', 'UNKNOWN']) || value.synthetic !== true || value.publicExecutionEnabled !== false
    || !oneOf(value.scope, ['LOCAL_VALIDATION', 'ISOLATED_LAB', 'DEPLOYED_RUNTIME']) || !isRuntime(value.runtime)
    || !object(value.slot) || !exact(value.slot, ['occupiedRunId']) || !(value.slot.occupiedRunId === null || runId(value.slot.occupiedRunId))
    || !Array.isArray(value.jobs) || value.jobs.length > 20 || !value.jobs.every(isJob)) return false;
  const expectedScope = value.environment === 'ISOLATED_LAB' ? 'ISOLATED_LAB' : value.environment === 'MINI_PC' ? 'DEPLOYED_RUNTIME' : 'LOCAL_VALIDATION';
  if (value.scope !== expectedScope || new Set(value.jobs.map(job => job.runId)).size !== value.jobs.length) return false;
  // A snapshot cannot conceal an already old heartbeat behind a fresh capture time.
  if (value.runtime.status === 'RUNNING') {
    const heartbeat = utcNs(value.runtime.heartbeatAt)!; const captured = utcNs(value.capturedAt)!;
    const stale = heartbeat > captured || captured - heartbeat > BigInt(JOB_HEARTBEAT_STALE_AFTER_MS) * 1_000_000n;
    if (value.runtime.stale !== stale) return false;
  }
  return value.jobs.every(job => [job.createdAt, job.sourceVerifiedAt, job.queuedAt, job.completedAt, job.exportCompletedAt, job.terminatedAt]
    .every(at => at === null || beforeOrEqual(at, value.capturedAt as string)));
}

export type JobBrowserError = 'NOT_CONFIGURED' | 'HTTP_ERROR' | 'NETWORK_ERROR' | 'INVALID_RECORD' | 'ABORTED' | 'OLDER_RECORD' | 'CONFLICTING_RECORD';
export interface JobObservationLoad { record: JobObservationRecord | null; browserError: JobBrowserError | null; retainedPrevious: boolean; }

/** Match immutable capture evidence without treating object key order as a change. */
function sameJobContent(left: unknown, right: unknown): boolean {
  if (left === right) return true;
  // Closed-schema validation has already limited UTC strings to timestamp fields.
  if (typeof left === 'string' && typeof right === 'string') {
    const instant = utcNs(left);
    return instant !== null && instant === utcNs(right);
  }
  if (Array.isArray(left) || Array.isArray(right)) return Array.isArray(left) && Array.isArray(right)
    && left.length === right.length && left.every((item, index) => sameJobContent(item, right[index]));
  if (!object(left) || !object(right)) return false;
  const keys = Object.keys(left);
  return keys.length === Object.keys(right).length && keys.every(key => Object.hasOwn(right, key) && sameJobContent(left[key], right[key]));
}

export async function loadJobObservation(options: { url: string; previousRecord?: JobObservationRecord | null; signal?: AbortSignal; fetcher?: typeof fetch; rejectRedirects?: boolean }): Promise<JobObservationLoad> {
  const previous = validateJobObservation(options.previousRecord) ? options.previousRecord : null;
  const failed = (browserError: JobBrowserError): JobObservationLoad => ({ record: previous, browserError, retainedPrevious: previous !== null });
  try {
    const response = await (options.fetcher || fetch)(options.url, { headers: { Accept: 'application/json' }, signal: options.signal, cache: 'no-store', credentials: 'omit', ...(options.rejectRedirects ? { redirect: 'error' as const } : {}) });
    if (!response.ok) {
      discardObservationBody(response);
      return failed(response.status === 404 ? 'NOT_CONFIGURED' : 'HTTP_ERROR');
    }
    const text = await boundedObservationText(response, MAX_JOB_OBSERVATION_BYTES);
    let record: unknown; try { record = JSON.parse(text); } catch { return failed('INVALID_RECORD'); }
    if (!validateJobObservation(record)) return failed('INVALID_RECORD');
    if (previous && utcNs(record.capturedAt)! < utcNs(previous.capturedAt)!) return failed('OLDER_RECORD');
    if (previous && utcNs(record.capturedAt) === utcNs(previous.capturedAt)) {
      if (!sameJobContent(previous, record)) return failed('CONFLICTING_RECORD');
      return { record: previous, browserError: null, retainedPrevious: false };
    }
    return { record, browserError: null, retainedPrevious: false };
  } catch (error) { return failed(options.signal?.aborted ? 'ABORTED'
    : error instanceof InvalidObservationBody ? 'INVALID_RECORD' : 'NETWORK_ERROR'); }
}
export function jobObservationView(record: JobObservationRecord | null, nowMs: number): { freshness: 'absent' | 'within-window' | 'stale' | 'clock-check'; heartbeat: 'unobserved' | 'recent-signal' | 'stale-signal' | 'not-running' | 'clock-check' } {
  if (!record) return { freshness: 'absent', heartbeat: 'unobserved' };
  const captured = Date.parse(record.capturedAt);
  const freshness = !Number.isFinite(nowMs) || captured > nowMs ? 'clock-check' : nowMs - captured > JOB_RECORD_STALE_AFTER_MS ? 'stale' : 'within-window';
  const runtime = record.runtime;
  if (runtime.status !== 'RUNNING') return { freshness, heartbeat: runtime.status === 'NOT_STARTED' ? 'unobserved' : 'not-running' };
  const heartbeatAt = Date.parse(runtime.heartbeatAt!);
  const heartbeatAfterCapture = utcNs(runtime.heartbeatAt)! > utcNs(record.capturedAt)!;
  return { freshness, heartbeat: heartbeatAfterCapture || !Number.isFinite(nowMs) || heartbeatAt > nowMs ? 'clock-check' : runtime.stale || nowMs - heartbeatAt > JOB_HEARTBEAT_STALE_AFTER_MS ? 'stale-signal' : 'recent-signal' };
}
