import assert from 'node:assert/strict';
import { test } from 'node:test';
import { formatJobLifecycleInterval, jobLifecycle } from '../src/lib/job-lifecycle.ts';
import type { JobObservation } from '../src/lib/job-observation.ts';

// Test-only accepted DTO states; no successful fallback is created for the site.
function staging(): JobObservation {
  return { runId: 'lifecycle-test', status: 'STAGING', exportStatus: 'NOT_REQUESTED',
    createdAt: '2026-10-24T10:00:00.123456789Z', sourceVerifiedAt: null, queuedAt: null,
    completedAt: null, exportCompletedAt: null, terminatedAt: null,
    counts: null, files: null, fileEvidence: 'NOT_AVAILABLE' };
}
function queued(): JobObservation {
  return { ...staging(), status: 'QUEUED', sourceVerifiedAt: '2026-10-24T10:00:01.000000001Z', queuedAt: '2026-10-24T10:00:01.000000001Z' };
}
function completed(): JobObservation {
  return { ...queued(), status: 'COMPLETED', exportStatus: 'PENDING', completedAt: '2026-10-24T10:00:03.000000009Z',
    counts: { input: 12, success: 7, failure: 3, duplicate: 2, pending: 0 },
    files: { result: { sha256: 'a'.repeat(64), size: 700 }, failures: { sha256: 'b'.repeat(64), size: 300 } }, fileEvidence: 'EXPECTED_FROM_DB' };
}
function exported(): JobObservation {
  return { ...completed(), exportStatus: 'EXPORTED', exportCompletedAt: '2026-10-24T10:00:04.123456789Z', fileEvidence: 'VERIFIED_AT_EXPORT_COMMIT' };
}
function freeze(value: unknown): void {
  if (value && typeof value === 'object') { Object.values(value).forEach(freeze); Object.freeze(value); }
}

test('staging and queued show exactly the recorded steps, without pending or successful stages', () => {
  const created = jobLifecycle(staging());
  assert.deepEqual(created.steps, [
    { id: 'created', at: '2026-10-24T10:00:00.123456789Z', recorded: true },
    { id: 'verified-queued', at: null, recorded: false },
    { id: 'completed', at: null, recorded: false },
    { id: 'exported', at: null, recorded: false },
  ]);
  assert.equal(created.exportCancelled, false);
  assert.deepEqual(created.intervals, [
    { id: 'queued-completed', from: null, to: null, nanoseconds: null },
    { id: 'completed-exported', from: null, to: null, nanoseconds: null },
  ]);
  const waiting = jobLifecycle(queued());
  assert.deepEqual(waiting.steps.map(step => step.recorded), [true, true, false, false]);
  assert.equal(waiting.steps[1]!.at, '2026-10-24T10:00:01.000000001Z');
  assert.equal(waiting.intervals[0].nanoseconds, null);
  assert.equal(waiting.intervals[0].from, '2026-10-24T10:00:01.000000001Z');
});

test('completed pending export has a processing interval and no export completion record', () => {
  const value = jobLifecycle(completed());
  assert.deepEqual(value.steps.map(step => step.recorded), [true, true, true, false]);
  assert.deepEqual(value.intervals, [
    { id: 'queued-completed', from: '2026-10-24T10:00:01.000000001Z', to: '2026-10-24T10:00:03.000000009Z', nanoseconds: 2_000_000_008n },
    { id: 'completed-exported', from: '2026-10-24T10:00:03.000000009Z', to: null, nanoseconds: null },
  ]);
  assert.equal(value.exportCancelled, false);
});

test('exported records both exact intervals and keeps every original timestamp', () => {
  const job = exported(); const value = jobLifecycle(job);
  assert.deepEqual(value.steps.map(step => step.at), [job.createdAt, job.queuedAt, job.completedAt, job.exportCompletedAt]);
  assert.deepEqual(value.steps.map(step => step.recorded), [true, true, true, true]);
  assert.equal(value.intervals[0].nanoseconds, 2_000_000_008n);
  assert.equal(value.intervals[1].nanoseconds, 1_123_456_780n);
  assert.equal(formatJobLifecycleInterval(value.intervals[1].nanoseconds), '1.12345678초');
});

test('cancelled export stays explicitly cancelled and missing export verification never becomes success', () => {
  const job: JobObservation = { ...completed(), exportStatus: 'CANCELLED', terminatedAt: '2026-10-24T10:00:05Z', files: null, fileEvidence: 'NOT_AVAILABLE' };
  const value = jobLifecycle(job);
  assert.equal(value.exportCancelled, true);
  assert.deepEqual(value.steps[3], { id: 'exported', at: null, recorded: false });
  assert.deepEqual(value.steps[4], { id: 'terminated', at: '2026-10-24T10:00:05Z', recorded: true });
  assert.equal(value.intervals[1].nanoseconds, null);
  assert.equal(formatJobLifecycleInterval(value.intervals[1].nanoseconds), '미기록');
  assert.equal(value.intervals[0].nanoseconds, 2_000_000_008n);
});

test('termination before or after queue records only known phases, with no completion interval', () => {
  for (const basis of [staging(), queued()]) {
    const value = jobLifecycle({ ...basis, status: 'TERMINATED', terminatedAt: '2026-10-24T10:00:05Z' });
    assert.deepEqual(value.steps.map(step => step.recorded), [true, basis.queuedAt !== null, false, false, true]);
    assert.equal(value.exportCancelled, false);
    assert.deepEqual(value.intervals.map(interval => interval.nanoseconds), [null, null]);
    assert.equal(value.steps[4]!.at, '2026-10-24T10:00:05Z');
  }
});

test('nanosecond boundary and UTC year rollover retain a one-nanosecond difference', () => {
  const job: JobObservation = { ...exported(), createdAt: '2026-12-31T23:59:58Z',
    sourceVerifiedAt: '2026-12-31T23:59:59.999999999Z', queuedAt: '2026-12-31T23:59:59.999999999Z',
    completedAt: '2027-01-01T00:00:00Z', exportCompletedAt: '2027-01-01T00:00:00.000000001Z' };
  const value = jobLifecycle(job);
  assert.deepEqual(value.intervals.map(interval => interval.nanoseconds), [1n, 1n]);
  assert.equal(formatJobLifecycleInterval(value.intervals[0].nanoseconds), '0.000000001초');
  assert.equal(value.intervals[0].from, '2026-12-31T23:59:59.999999999Z');
  assert.equal(value.intervals[0].to, '2027-01-01T00:00:00Z');
});

test('same instants with different fractional padding are recorded zero, distinct from missing', () => {
  const job: JobObservation = { ...exported(), sourceVerifiedAt: '2026-10-24T10:00:01.123Z', queuedAt: '2026-10-24T10:00:01.123Z',
    completedAt: '2026-10-24T10:00:01.123000000Z', exportCompletedAt: '2026-10-24T10:00:01.123000Z' };
  const value = jobLifecycle(job);
  assert.deepEqual(value.intervals.map(interval => interval.nanoseconds), [0n, 0n]);
  assert.equal(formatJobLifecycleInterval(value.intervals[0].nanoseconds), '0초');
  assert.equal(formatJobLifecycleInterval(null), '미기록');
  assert.equal(value.steps[2]!.at, '2026-10-24T10:00:01.123000000Z');
  assert.equal(value.steps[3]!.at, '2026-10-24T10:00:01.123000Z');
});

test('exact seconds formatting does not round or pass through floating point', () => {
  assert.equal(formatJobLifecycleInterval(1_000_000_000n), '1초');
  assert.equal(formatJobLifecycleInterval(1_100_000_000n), '1.1초');
  assert.equal(formatJobLifecycleInterval(999_999_999n), '0.999999999초');
  assert.equal(formatJobLifecycleInterval(9_007_199_254_740_993n), '9007199.254740993초');
});

test('frozen input is untouched and failed-event counts do not redefine lifecycle records', () => {
  const job = exported(); const before = structuredClone(job); freeze(job);
  const value = jobLifecycle(job);
  assert.deepEqual(job, before);
  const allFailed: JobObservation = { ...before, counts: { input: 12, success: 0, failure: 12, duplicate: 0, pending: 0 } };
  assert.deepEqual(jobLifecycle(allFailed), value);
  assert.equal(value.exportCancelled, false);
  assert.equal(value.steps[3]!.recorded, true);
});
