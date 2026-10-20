import assert from 'node:assert/strict';
import { createServer } from 'node:http';
import { test } from 'node:test';
import { JOB_HEARTBEAT_STALE_AFTER_MS, JOB_RECORD_STALE_AFTER_MS, MAX_JOB_OBSERVATION_BYTES, jobObservationView, loadJobObservation, validateJobObservation } from '../src/lib/job-observation.ts';
import type { JobObservation, JobObservationRecord } from '../src/lib/job-observation.ts';
import { boundedObservationText } from '../src/lib/observation-response-body.ts';

// Test-only DTOs. These are never published or used as a successful UI fallback.
function record(): JobObservationRecord {
  return { schemaVersion: 1, kind: 'job-observation', capturedAt: '2026-10-15T10:00:00.123456789Z', environment: 'ISOLATED_LAB', sourceCommit: 'a'.repeat(40), synthetic: true,
    scope: 'ISOLATED_LAB', publicExecutionEnabled: false,
    runtime: { status: 'NOT_STARTED', stage: 'IDLE', failureCode: null, startedAt: null, heartbeatAt: null, stoppedAt: null, sourceCommit: 'unknown', stale: false },
    slot: { occupiedRunId: null }, jobs: [] };
}
function completed(): JobObservation {
  return { runId: 'test-job-one', status: 'COMPLETED', exportStatus: 'PENDING', createdAt: '2026-10-15T09:00:00Z', sourceVerifiedAt: '2026-10-15T09:00:01Z', queuedAt: '2026-10-15T09:00:01Z',
    completedAt: '2026-10-15T09:00:02Z', exportCompletedAt: null, terminatedAt: null, counts: { input: 12, success: 7, failure: 3, duplicate: 2, pending: 0 },
    files: { result: { sha256: 'b'.repeat(64), size: 4500 }, failures: { sha256: 'c'.repeat(64), size: 2200 } }, fileEvidence: 'EXPECTED_FROM_DB' };
}
function running(): JobObservationRecord {
  const value = record(); value.runtime = { status: 'RUNNING', stage: 'CONSUME', failureCode: null, startedAt: '2026-10-15T09:59:00Z', heartbeatAt: value.capturedAt, stoppedAt: null, sourceCommit: 'a'.repeat(40), stale: false }; return value;
}

test('accepts distinct committed job and export states without treating expected files as verified', () => {
  const value = record();
  assert.equal(validateJobObservation(value), true);
  value.jobs = [completed()]; value.slot.occupiedRunId = value.jobs[0]!.runId;
  assert.equal(validateJobObservation(value), true);
  value.jobs[0] = { ...completed(), exportStatus: 'EXPORTED', exportCompletedAt: '2026-10-15T09:00:03Z', fileEvidence: 'VERIFIED_AT_EXPORT_COMMIT' }; value.slot.occupiedRunId = null;
  assert.equal(validateJobObservation(value), true);
  value.jobs[0] = { ...completed(), exportStatus: 'CANCELLED', terminatedAt: '2026-10-15T09:00:03Z', files: null, fileEvidence: 'NOT_AVAILABLE' };
  assert.equal(validateJobObservation(value), true);
  value.jobs[0] = { ...completed(), status: 'QUEUED', exportStatus: 'NOT_REQUESTED', completedAt: null, counts: null, files: null, fileEvidence: 'NOT_AVAILABLE' };
  assert.equal(validateJobObservation(value), true);
  value.jobs[0] = { ...value.jobs[0]!, status: 'STAGING', sourceVerifiedAt: null, queuedAt: null };
  assert.equal(validateJobObservation(value), true);
  value.jobs[0] = { ...value.jobs[0]!, status: 'TERMINATED', terminatedAt: '2026-10-15T09:00:03Z' };
  assert.equal(validateJobObservation(value), true);
});
test('rejects unknown private fields at every envelope/runtime/job/file/count boundary', () => {
  const value = record(); value.jobs = [completed()];
  for (const change of [
    { ...value, secret: 'test-private' }, { ...value, runtime: { ...value.runtime, host: 'test-private' } },
    { ...value, slot: { ...value.slot, token: 'test-private' } }, { ...value, jobs: [{ ...completed(), sourceBytes: 'test-private' }] },
    { ...value, jobs: [{ ...completed(), counts: { ...completed().counts!, internal: 1 } }] },
    { ...value, jobs: [{ ...completed(), files: { ...completed().files!, bucket: 'test-private' } }] },
    { ...value, jobs: [{ ...completed(), files: { ...completed().files!, result: { ...completed().files!.result, key: 'test-private' } } }] },
  ]) assert.equal(validateJobObservation(change), false);
});
test('rejects invalid counts/hash/size/states and inconsistent export acknowledgement times', () => {
  const value = record();
  for (const job of [
    { ...completed(), counts: { ...completed().counts!, input: 13 } }, { ...completed(), counts: { ...completed().counts!, success: -1 } },
    { ...completed(), files: { ...completed().files!, result: { sha256: 'B'.repeat(64), size: 4 } } },
    { ...completed(), files: { ...completed().files!, result: { sha256: 'b'.repeat(64), size: 4_194_305 } } },
    { ...completed(), files: { ...completed().files!, result: { sha256: 'b'.repeat(64), size: 1.5 } } },
    { ...completed(), fileEvidence: 'VERIFIED_AT_EXPORT_COMMIT' }, { ...completed(), exportStatus: 'EXPORTED' },
    { ...completed(), exportStatus: 'CANCELLED' }, { ...completed(), status: 'RUNNING' },
    { ...completed(), queuedAt: '2026-10-15T09:00:00Z' }, { ...completed(), completedAt: '2026-10-15T08:59:59Z' },
  ]) assert.equal(validateJobObservation({ ...value, jobs: [job] }), false);
});
test('validates real UTC calendar and nanosecond ordering, bounded lists and fixed environment scope', () => {
  const value = record();
  for (const capturedAt of ['2026-02-30T10:00:00Z', '2026-10-15T24:00:00Z', '2026-10-15T10:00:60Z', '2026-10-15T10:00:00+00:00', '0000-01-01T00:00:00Z', '2026-10-15T10:00:00.1234567890Z']) assert.equal(validateJobObservation({ ...value, capturedAt }), false);
  assert.equal(validateJobObservation({ ...value, jobs: [{ ...completed(), createdAt: '2026-10-15T10:00:00.123456790Z' }] }), false);
  assert.equal(validateJobObservation({ ...value, jobs: [completed(), completed()] }), false);
  assert.equal(validateJobObservation({ ...value, jobs: Array.from({ length: 21 }, (_, index) => ({ ...completed(), runId: `test-job-${index}` })) }), false);
  assert.equal(validateJobObservation({ ...value, environment: 'MINI_PC' }), false);
  assert.equal(validateJobObservation({ ...value, environment: 'a-private-host' }), false);
  assert.equal(validateJobObservation({ ...value, publicExecutionEnabled: true }), false);
});
test('runtime failure status is separate from stale heartbeat and rejects free-form errors', () => {
  const value = running(); assert.equal(validateJobObservation(value), true);
  const captured = Date.parse(value.capturedAt);
  assert.equal(jobObservationView(value, captured).heartbeat, 'recent-signal');
  assert.equal(jobObservationView(value, captured + JOB_HEARTBEAT_STALE_AFTER_MS).heartbeat, 'recent-signal');
  assert.equal(jobObservationView(value, captured + JOB_HEARTBEAT_STALE_AFTER_MS + 1).heartbeat, 'stale-signal');
  assert.equal(jobObservationView(value, captured + JOB_RECORD_STALE_AFTER_MS + 1).freshness, 'stale');
  assert.equal(jobObservationView(value, captured - 1).freshness, 'clock-check');
  assert.equal(jobObservationView(value, Number.NaN).heartbeat, 'clock-check');
  const paused: JobObservationRecord = { ...value, runtime: { ...value.runtime, status: 'PAUSED_OPERATOR', stage: 'EXPORT', failureCode: 'EXPORT_FAILED', stoppedAt: value.capturedAt } };
  assert.equal(validateJobObservation(paused), true);
  assert.equal(jobObservationView(paused, captured).heartbeat, 'not-running');
  assert.equal(validateJobObservation({ ...paused, runtime: { ...paused.runtime, stage: 'STOPPED', failureCode: 'RESOURCE_CLOSE_FAILED' } }), true);
  assert.equal(validateJobObservation({ ...paused, runtime: { ...paused.runtime, stage: 'STOPPED', failureCode: 'EXPORT_FAILED' } }), false);
  assert.equal(validateJobObservation({ ...paused, runtime: { ...paused.runtime, failureCode: 'private raw exception' } }), false);
  assert.equal(validateJobObservation({ ...value, runtime: { ...value.runtime, heartbeatAt: '2026-10-15T09:00:00Z' } }), false);
  assert.equal(validateJobObservation({ ...value, runtime: { ...value.runtime, heartbeatAt: '2026-10-15T09:00:00Z', stale: true } }), true);
  assert.equal(validateJobObservation({ ...value, runtime: { ...value.runtime, failureCode: 'EXPORT_FAILED' } }), false);
});
test('loader keeps last good fields and original capture time across HTTP/network/contract failures', async () => {
  const previous = record(); previous.jobs = [completed()];
  for (const [fetcher, expected] of [
    [async () => new Response('', { status: 404 }), 'NOT_CONFIGURED'],
    [async () => new Response('private error', { status: 503 }), 'HTTP_ERROR'],
    [async () => { throw new Error('private error'); }, 'NETWORK_ERROR'],
    [async () => new Response('{bad-json'), 'INVALID_RECORD'],
    [async () => new Response(JSON.stringify({ ...previous, token: 'private marker' })), 'INVALID_RECORD'],
    [async () => new Response(' '.repeat(MAX_JOB_OBSERVATION_BYTES + 1)), 'INVALID_RECORD'],
  ] as const) {
    const result = await loadJobObservation({ url: '/jobs', previousRecord: previous, fetcher });
    assert.equal(result.browserError, expected); assert.equal(result.retainedPrevious, true); assert.equal(result.record, previous);
    assert.equal(result.record!.capturedAt, previous.capturedAt); assert.equal(JSON.stringify(result).includes('private'), false);
  }
});
test('missing/aborted first lookup remains unobserved and a regressed response cannot replace last good record', async () => {
  const controller = new AbortController(); controller.abort();
  const aborted = await loadJobObservation({ url: '/jobs', signal: controller.signal, fetcher: async () => { throw new Error('aborted'); } });
  assert.deepEqual(aborted, { record: null, browserError: 'ABORTED', retainedPrevious: false });
  assert.deepEqual(jobObservationView(null, Date.now()), { freshness: 'absent', heartbeat: 'unobserved' });
  const previous = record(); const old = { ...previous, capturedAt: '2026-10-15T10:00:00.123456788Z' };
  const regressed = await loadJobObservation({ url: '/jobs', previousRecord: previous, fetcher: async () => new Response(JSON.stringify(old)) });
  assert.equal(regressed.browserError, 'OLDER_RECORD'); assert.equal(regressed.record, previous);
  const invalidPrevious = { ...previous, managementUrl: 'private' } as JobObservationRecord;
  const invalid = await loadJobObservation({ url: '/jobs', previousRecord: invalidPrevious, fetcher: async () => new Response('', { status: 404 }) });
  assert.equal(invalid.record, null); assert.equal(invalid.retainedPrevious, false);
});
test('actual HTTP loads only the selected public route and sends no authentication or cookies', async () => {
  const value = record(); value.jobs = [completed()];
  const server = createServer((request, response) => {
    assert.equal(request.url, '/base/observations/jobs.latest.json'); assert.equal(request.headers.authorization, undefined); assert.equal(request.headers.cookie, undefined);
    response.setHeader('Content-Type', 'application/json'); response.end(JSON.stringify(value));
  });
  await new Promise<void>(resolve => server.listen(0, '127.0.0.1', resolve));
  try {
    const address = server.address(); assert.ok(address && typeof address !== 'string');
    const result = await loadJobObservation({ url: `http://127.0.0.1:${address.port}/base/observations/jobs.latest.json` });
    assert.equal(result.browserError, null); assert.deepEqual(result.record, value);
  } finally { await new Promise<void>((resolve, reject) => server.close(error => error ? reject(error) : resolve())); }
});

test('job byte ceiling is enforced while reading and the excess stream is cancelled without replacing memory', { timeout: 1000 }, async () => {
  const previous = record();
  const json = new TextEncoder().encode(JSON.stringify(previous));
  const exact = new Uint8Array(MAX_JOB_OBSERVATION_BYTES).fill(0x20); exact.set(json);
  const accepted = await loadJobObservation({ url: '/jobs', previousRecord: previous,
    fetcher: async () => new Response(new ReadableStream<Uint8Array>({
      start(controller) { controller.enqueue(exact.subarray(0, 300)); controller.enqueue(exact.subarray(300)); controller.close(); },
    })) });
  assert.equal(accepted.browserError, null); assert.deepEqual(accepted.record, previous);

  let pulls = 0; let cancellations = 0;
  const rejected = await loadJobObservation({ url: '/jobs', previousRecord: previous,
    fetcher: async () => new Response(new ReadableStream<Uint8Array>({
      pull(controller) {
        pulls++;
        if (pulls === 1) controller.enqueue(exact);
        else if (pulls === 2) controller.enqueue(new Uint8Array([0x20]));
        else throw new Error('PRIVATE_UNREAD_CANARY');
      },
      cancel() { cancellations++; return new Promise<void>(() => {}); },
    }, { highWaterMark: 0 })) });
  assert.equal(pulls, 2); assert.equal(cancellations, 1);
  assert.equal(rejected.browserError, 'INVALID_RECORD'); assert.equal(rejected.record, previous);
  assert.equal(rejected.retainedPrevious, true); assert.equal(rejected.record?.capturedAt, previous.capturedAt);
  assert.ok(!JSON.stringify(rejected).includes('PRIVATE_'));
});

test('bounded response decoding joins split UTF-8 bytes and rejects malformed UTF-8 as an invalid job record', async () => {
  const text = '{"synthetic":"한글"}'; const bytes = new TextEncoder().encode(text);
  const split = bytes.indexOf(0xed) + 1;
  assert.ok(split > 0 && split < bytes.length);
  const decoded = await boundedObservationText(new Response(new ReadableStream<Uint8Array>({
    start(controller) { controller.enqueue(bytes.subarray(0, split)); controller.enqueue(bytes.subarray(split)); controller.close(); },
  })), bytes.length);
  assert.equal(decoded, text);
  const previous = record();
  const rejected = await loadJobObservation({ url: '/jobs', previousRecord: previous,
    fetcher: async () => new Response(new Uint8Array([0xc3, 0x28])) });
  assert.equal(rejected.browserError, 'INVALID_RECORD'); assert.equal(rejected.record, previous);
  assert.equal(rejected.record?.capturedAt, previous.capturedAt);
});

test('unused job HTTP error bodies are cancelled without awaiting a provider cancellation promise', { timeout: 1000 }, async () => {
  const previous = record();
  for (const [status, error] of [[404, 'NOT_CONFIGURED'], [503, 'HTTP_ERROR']] as const) {
    let cancellations = 0;
    const result = await loadJobObservation({ url: '/jobs', previousRecord: previous,
      fetcher: async () => new Response(new ReadableStream<Uint8Array>({
        cancel() { cancellations++; return new Promise<void>(() => {}); },
      }), { status }) });
    assert.equal(cancellations, 1); assert.equal(result.browserError, error);
    assert.equal(result.record, previous); assert.equal(result.retainedPrevious, true);
    assert.equal(result.record?.capturedAt, previous.capturedAt);
  }
});

test('job stream transport failure keeps its existing network error and the prior observation', async () => {
  const previous = record();
  const result = await loadJobObservation({ url: '/jobs', previousRecord: previous,
    fetcher: async () => new Response(new ReadableStream<Uint8Array>({
      start(controller) { controller.error(new Error('PRIVATE_STREAM_FAILURE')); },
    })) });
  assert.equal(result.browserError, 'NETWORK_ERROR'); assert.equal(result.record, previous);
  assert.equal(result.record?.capturedAt, previous.capturedAt);
  assert.ok(!JSON.stringify(result).includes('PRIVATE_STREAM_FAILURE'));
});
