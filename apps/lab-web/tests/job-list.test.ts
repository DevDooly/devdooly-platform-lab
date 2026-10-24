import assert from 'node:assert/strict';
import { test } from 'node:test';
import { DEFAULT_JOB_FILTERS, filterObservedJobs } from '../src/lib/job-list.ts';
import { validateJobObservation } from '../src/lib/job-observation.ts';
import type { JobObservation, JobObservationRecord } from '../src/lib/job-observation.ts';

// Accepted test-only DTOs cover the six legal job/export state combinations.
function jobs(): JobObservation[] {
  const staging: JobObservation = { runId: 'stage.alpha_01', status: 'STAGING', exportStatus: 'NOT_REQUESTED',
    createdAt: '2026-10-25T01:00:00Z', sourceVerifiedAt: null, queuedAt: null, completedAt: null,
    exportCompletedAt: null, terminatedAt: null, counts: null, files: null, fileEvidence: 'NOT_AVAILABLE' };
  const queued: JobObservation = { ...staging, runId: 'queue-alpha-01', status: 'QUEUED',
    sourceVerifiedAt: '2026-10-25T01:00:01Z', queuedAt: '2026-10-25T01:00:01Z' };
  const pending: JobObservation = { ...queued, runId: 'done.alpha_01', status: 'COMPLETED', exportStatus: 'PENDING',
    completedAt: '2026-10-25T01:00:02Z', counts: { input: 1, success: 1, failure: 0, duplicate: 0, pending: 0 },
    files: { result: { sha256: 'a'.repeat(64), size: 2 }, failures: { sha256: 'b'.repeat(64), size: 2 } },
    fileEvidence: 'EXPECTED_FROM_DB' };
  return [staging, queued, pending,
    { ...pending, runId: 'done-alpha_02', exportStatus: 'EXPORTED', exportCompletedAt: '2026-10-25T01:00:03Z', fileEvidence: 'VERIFIED_AT_EXPORT_COMMIT' },
    { ...pending, runId: 'done-cancel_03', exportStatus: 'CANCELLED', terminatedAt: '2026-10-25T01:00:03Z', files: null, fileEvidence: 'NOT_AVAILABLE' },
    { ...queued, runId: 'term-alpha_04', status: 'TERMINATED', terminatedAt: '2026-10-25T01:00:03Z' },
  ];
}

function freeze(value: unknown): void {
  if (value && typeof value === 'object') { Object.values(value).forEach(freeze); Object.freeze(value); }
}

test('default filters preserve all six accepted state records and their original order', () => {
  const source = jobs();
  const record: JobObservationRecord = { schemaVersion: 1, kind: 'job-observation', capturedAt: '2026-10-25T01:00:04Z',
    environment: 'TEST', sourceCommit: 'unknown', synthetic: true, scope: 'LOCAL_VALIDATION', publicExecutionEnabled: false,
    runtime: { status: 'NOT_STARTED', stage: 'IDLE', failureCode: null, startedAt: null, heartbeatAt: null,
      stoppedAt: null, sourceCommit: 'unknown', stale: false }, slot: { occupiedRunId: null }, jobs: source };
  assert.equal(validateJobObservation(record), true);
  assert.deepEqual(DEFAULT_JOB_FILTERS, { query: '', status: 'ALL', exportStatus: 'ALL' });
  const result = filterObservedJobs(source, DEFAULT_JOB_FILTERS);
  assert.deepEqual(result, source);
  assert.notEqual(result, source);
  result.forEach((job, index) => assert.equal(job, source[index]));
});

test('run ID search ignores outer whitespace and query case, and permits partial matches', () => {
  const source = jobs();
  assert.deepEqual(filterObservedJobs(source, { ...DEFAULT_JOB_FILTERS, query: '  ALPHA_0\t' }).map(job => job.runId),
    ['stage.alpha_01', 'done.alpha_01', 'done-alpha_02', 'term-alpha_04']);
  assert.deepEqual(filterObservedJobs(source, { ...DEFAULT_JOB_FILTERS, query: ' \t\n' }), source);
});

test('punctuation and internal whitespace stay literal rather than regex or token search', () => {
  const source = jobs();
  assert.deepEqual(filterObservedJobs(source, { ...DEFAULT_JOB_FILTERS, query: '.' }).map(job => job.runId),
    ['stage.alpha_01', 'done.alpha_01']);
  assert.deepEqual(filterObservedJobs(source, { ...DEFAULT_JOB_FILTERS, query: '-alpha_' }).map(job => job.runId),
    ['done-alpha_02', 'term-alpha_04']);
  for (const query of ['.*', 'done|queue', 'done alpha', 'alpha 01', 'missing']) {
    assert.deepEqual(filterObservedJobs(source, { ...DEFAULT_JOB_FILTERS, query }), [], query);
  }
});

test('job and export state filters remain distinct and combine with the ID query using AND', () => {
  const source = jobs();
  assert.deepEqual(filterObservedJobs(source, { ...DEFAULT_JOB_FILTERS, status: 'COMPLETED' }).map(job => job.runId),
    ['done.alpha_01', 'done-alpha_02', 'done-cancel_03']);
  assert.deepEqual(filterObservedJobs(source, { ...DEFAULT_JOB_FILTERS, exportStatus: 'NOT_REQUESTED' }).map(job => job.runId),
    ['stage.alpha_01', 'queue-alpha-01', 'term-alpha_04']);
  assert.deepEqual(filterObservedJobs(source, { query: 'ALPHA', status: 'COMPLETED', exportStatus: 'EXPORTED' }).map(job => job.runId),
    ['done-alpha_02']);
  assert.deepEqual(filterObservedJobs(source, { query: '', status: 'STAGING', exportStatus: 'EXPORTED' }), []);
  assert.deepEqual(filterObservedJobs(source, { query: 'alpha', status: 'COMPLETED', exportStatus: 'CANCELLED' }), []);
});

test('empty input and frozen source records and filters remain unchanged', () => {
  const source = jobs(); const before = structuredClone(source);
  const filters = { query: ' done ', status: 'COMPLETED', exportStatus: 'ALL' } as const;
  const filtersBefore = { ...filters };
  freeze(source); freeze(filters);
  const result = filterObservedJobs(source, filters);
  assert.deepEqual(result.map(job => job.runId), ['done.alpha_01', 'done-alpha_02', 'done-cancel_03']);
  assert.equal(result[0], source[2]); assert.equal(result[1], source[3]); assert.equal(result[2], source[4]);
  assert.deepEqual(source, before); assert.deepEqual(filters, filtersBefore);
  assert.deepEqual(filterObservedJobs(Object.freeze([]), DEFAULT_JOB_FILTERS), []);
});
