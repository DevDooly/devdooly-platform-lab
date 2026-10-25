import assert from 'node:assert/strict';
import test from 'node:test';
import type { Outcome } from '../src/lib/api.ts';
import { filterEventOutcomes } from '../src/lib/event-search.ts';
import { parseEventShareSelection } from '../src/lib/event-share.ts';
import { jobEventLinks } from '../src/lib/job-event-navigation.ts';
import type { JobObservation, JobObservationRecord } from '../src/lib/job-observation.ts';

const deployed = { environment: 'MINI_PC', scope: 'DEPLOYED_RUNTIME' } as const;
function staging(): JobObservation {
  return { runId: 'job-navigation.fixture_01', status: 'STAGING', exportStatus: 'NOT_REQUESTED',
    createdAt: '2026-10-25T01:00:00Z', sourceVerifiedAt: null, queuedAt: null, completedAt: null,
    exportCompletedAt: null, terminatedAt: null, counts: null, files: null, fileEvidence: 'NOT_AVAILABLE' };
}
function queued(): JobObservation {
  return { ...staging(), status: 'QUEUED', sourceVerifiedAt: '2026-10-25T01:00:01Z', queuedAt: '2026-10-25T01:00:01Z' };
}
function completed(): JobObservation {
  return { ...queued(), status: 'COMPLETED', exportStatus: 'PENDING', completedAt: '2026-10-25T01:00:02Z',
    counts: { input: 4, success: 1, failure: 2, duplicate: 1, pending: 0 },
    files: { result: { sha256: 'a'.repeat(64), size: 600 }, failures: { sha256: 'b'.repeat(64), size: 300 } },
    fileEvidence: 'EXPECTED_FROM_DB' };
}
function parsePath(path: string | null) {
  assert.ok(path);
  const url = new URL(path, 'https://example.invalid');
  assert.equal(url.origin, 'https://example.invalid');
  assert.equal(url.hash, '#lab');
  const parsed = parseEventShareSelection(url.search);
  assert.equal(parsed.kind, 'valid');
  return { url, selection: parsed.selection };
}
function freeze(value: unknown): void {
  if (value && typeof value === 'object') { Object.values(value).forEach(freeze); Object.freeze(value); }
}

test('job links restore the displayed run and actual all/failed event filters at root and a Pages subpath', () => {
  const job = completed();
  const row = (sequence: number, status: Outcome['status'], reason: string): Outcome => ({
    sequence, eventId: 'same-event', sensorId: 'sensor-a', eventTime: 'raw-time', value: 120, status, reason,
  });
  const rows = [row(8, 'FAILED', ''), row(2, 'SUCCESS', ''), row(10, 'FAILED', 'OUT_OF_RANGE'), row(11, 'DUPLICATE', '')];
  for (const basePath of ['/', '/devdooly-platform-lab/', '/devdooly-platform-lab']) {
    const links = jobEventLinks(job, deployed, basePath);
    assert.ok(links);
    const all = parsePath(links.all); const failed = parsePath(links.failed);
    assert.equal(all.url.pathname, basePath === '/' ? '/' : '/devdooly-platform-lab/');
    assert.equal(failed.url.pathname, all.url.pathname);
    assert.deepEqual(all.selection, { runId: job.runId, filters: { status: 'ALL', query: '', reason: null }, sequence: null });
    assert.deepEqual(failed.selection, { runId: job.runId, filters: { status: 'FAILED', query: '', reason: null }, sequence: null });
    assert.deepEqual(filterEventOutcomes(rows, all.selection.filters), rows);
    assert.deepEqual(filterEventOutcomes(rows, failed.selection.filters).map(item => item.sequence), [8, 10]);
  }
});

test('DB-completed results remain navigable while export is pending, verified, or cancelled', () => {
  const pending = completed();
  const exported: JobObservation = { ...pending, exportStatus: 'EXPORTED', exportCompletedAt: '2026-10-25T01:00:03Z', fileEvidence: 'VERIFIED_AT_EXPORT_COMMIT' };
  const cancelled: JobObservation = { ...pending, exportStatus: 'CANCELLED', terminatedAt: '2026-10-25T01:00:03Z', files: null, fileEvidence: 'NOT_AVAILABLE' };
  for (const job of [pending, exported, cancelled]) {
    const links = jobEventLinks(job, deployed, '/');
    assert.ok(links, job.exportStatus);
    assert.equal(parsePath(links.all).selection.runId, job.runId);
    assert.ok(links.failed, job.exportStatus);
  }
});

test('zero reported failures keeps all events available without offering a failure link', () => {
  const job = { ...completed(), counts: { input: 4, success: 3, failure: 0, duplicate: 1, pending: 0 } };
  const links = jobEventLinks(job, deployed, '/');
  assert.ok(links);
  assert.equal(links.failed, null);
  assert.equal(parsePath(links.all).selection.filters.status, 'ALL');
});

test('preprocessing states, termination before completion, and missing counts do not imply stored results', () => {
  const terminated: JobObservation = { ...queued(), status: 'TERMINATED', terminatedAt: '2026-10-25T01:00:03Z' };
  for (const job of [staging(), queued(), terminated, { ...completed(), counts: null }]) {
    assert.equal(jobEventLinks(job, deployed, '/'), null, job.status);
  }
});

test('all other environment/scope combinations cannot address the deployed runtime by an unrelated job ID', () => {
  const environments: JobObservationRecord['environment'][] = ['LOCAL', 'TEST', 'ISOLATED_LAB', 'MINI_PC', 'UNKNOWN'];
  const scopes: JobObservationRecord['scope'][] = ['LOCAL_VALIDATION', 'ISOLATED_LAB', 'DEPLOYED_RUNTIME'];
  for (const environment of environments) for (const scope of scopes) {
    if (environment === deployed.environment && scope === deployed.scope) continue;
    assert.equal(jobEventLinks(completed(), { environment, scope }, '/'), null, `${environment}/${scope}`);
  }
});

test('invalid IDs and unsafe destinations are rejected by the existing shared link contract', () => {
  for (const runId of ['', '../run', 'run/other', 'a'.repeat(81)]) {
    assert.equal(jobEventLinks({ ...completed(), runId }, deployed, '/'), null, runId);
  }
  for (const basePath of ['https://other.invalid/', '//other.invalid/', '/../', '/app/../', '/app?target=other']) {
    assert.equal(jobEventLinks(completed(), deployed, basePath), null, basePath);
  }
});

test('link generation leaves nested job records and observation context unchanged', () => {
  const job = completed(); const context = { ...deployed };
  const before = structuredClone({ job, context });
  freeze(job); freeze(context);
  assert.ok(jobEventLinks(job, context, '/'));
  assert.deepEqual({ job, context }, before);
});
