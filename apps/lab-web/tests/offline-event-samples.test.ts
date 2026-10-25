import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import test from 'node:test';
import { compareEventOutcomes } from '../src/lib/event-comparison.ts';
import { createOfflineComparisonReport, offlineComparisonReportJson } from '../src/lib/offline-comparison-report.ts';
import { MAX_OFFLINE_FILE_BYTES, MAX_OFFLINE_OUTCOMES, readOfflineEventBytes, type OfflineEventFile } from '../src/lib/offline-event-file.ts';

// These deliberately authored fixture judgments illustrate categories; they are not a worker execution trace.
async function sample(name: string): Promise<OfflineEventFile> {
  const bytes = await readFile(new URL(`../public/examples/${name}`, import.meta.url));
  const result = readOfflineEventBytes(bytes);
  assert.equal(result.ok, true, `${name} must pass the same reader as a user-selected saved export`);
  if (!result.ok) assert.fail(result.code);
  assert.ok(bytes.byteLength < MAX_OFFLINE_FILE_BYTES);
  assert.ok(result.document.outcomes.length <= MAX_OFFLINE_OUTCOMES);
  return { name, byteLength: bytes.byteLength, document: result.document };
}
const pair = async () => ({ left: await sample('offline-events-a-v1.json'), right: await sample('offline-events-b-v2.json') });

test('actual static sample bytes pass the existing reader as small version 1 and 2 fixtures with nullable observation metadata', async () => {
  const { left, right } = await pair();
  assert.equal(left.document.schemaVersion, 1); assert.equal(right.document.schemaVersion, 2);
  assert.deepEqual(left.document.source, { runId: 'offline-sample-a', mode: 'fixture', observedAt: null, capturedAt: null });
  assert.deepEqual(right.document.source, { runId: 'offline-sample-b', mode: 'fixture', observedAt: null, capturedAt: null });
  assert.deepEqual(left.document.filters, { status: 'ALL', query: '', reason: null });
  assert.deepEqual(right.document.filters, { status: 'ALL', query: '', reason: null, sensorId: 'sample-sensor' });
  assert.deepEqual(left.document.counts, { reportedInputCount: 6, availableOutcomes: 6, matchedOutcomes: 6 });
  assert.deepEqual(right.document.counts, { reportedInputCount: 6, availableOutcomes: 4, matchedOutcomes: 4 });
  for (const file of [left, right]) for (const outcome of file.document.outcomes) {
    assert.equal(outcome.sensorId, 'sample-sensor'); assert.equal(outcome.eventTime, '2000-01-01T00:00:00Z');
  }
});

test('sample observations produce the five hand-authored categories and retain every ambiguous candidate in source order', async () => {
  const { left, right } = await pair();
  const comparison = compareEventOutcomes(left.document.outcomes, right.document.outcomes);
  assert.equal(comparison.leftCount, 6); assert.equal(comparison.rightCount, 4);
  assert.deepEqual(comparison.rows.map(row => [row.sequence, row.kind, row.inputDifferences, row.verdictDifferences]), [
    [1, 'observed-equal', [], []],
    [2, 'verdict-different', [], ['status', 'reason']],
    [3, 'input-different', ['value'], ['status', 'reason']],
    [4, 'unobserved', null, null],
    [5, 'ambiguous', null, null],
  ]);
  assert.deepEqual(comparison.counts, { ambiguous: 1, unobserved: 1, 'input-different': 1, 'verdict-different': 1, 'observed-equal': 1 });
  assert.deepEqual(comparison.rows[1]!.left.map(row => [row.value, row.status, row.reason]), [[30, 'SUCCESS', 'ACCEPTED']]);
  assert.deepEqual(comparison.rows[1]!.right.map(row => [row.value, row.status, row.reason]), [[30, 'FAILED', 'SYNTHETIC_REVIEW']]);
  assert.deepEqual(comparison.rows[2]!.left.map(row => [row.value, row.status, row.reason]), [[120, 'FAILED', 'OUT_OF_RANGE']]);
  assert.deepEqual(comparison.rows[2]!.right.map(row => [row.value, row.status, row.reason]), [[40, 'SUCCESS', 'ACCEPTED']]);
  assert.deepEqual(comparison.rows[3]!.left.map(row => row.eventId), ['sample-004']);
  assert.deepEqual(comparison.rows[3]!.right, []);
  assert.deepEqual(comparison.rows[4]!.left.map(row => [row.eventId, row.value]), [['sample-005-a', 50], ['sample-005-b', 51]]);
  assert.deepEqual(comparison.rows[4]!.right.map(row => [row.eventId, row.value]), [['sample-005-a', 50]]);
  assert.equal(comparison.rows[4]!.left[0], left.document.outcomes[4]);
  assert.equal(comparison.rows[4]!.left[1], left.document.outcomes[5]);
});

test('existing report creation saves all five groups and preserves partial source counts separately from the review format', async () => {
  const files = await pair();
  const report = createOfflineComparisonReport(files, { query: '', kind: 'all', limit: 20 }, '2026-10-25T00:00:00Z');
  assert.deepEqual(report.counts, { totalGroups: 5, matchingGroups: 5, displayedGroups: 5 });
  assert.equal(report.groups.length, 5); assert.equal(report.groups[4]!.left.length, 2);
  assert.deepEqual(report.files.left.counts, { reportedInputCount: 6, availableOutcomes: 6, matchedOutcomes: 6 });
  assert.deepEqual(report.files.right.counts, { reportedInputCount: 6, availableOutcomes: 4, matchedOutcomes: 4 });
  for (const side of ['left', 'right'] as const) {
    assert.equal(report.files[side].name, files[side].name); assert.equal(report.files[side].byteLength, files[side].byteLength);
    assert.deepEqual(report.files[side].source, files[side].document.source);
    assert.deepEqual(report.files[side].filters, files[side].document.filters);
    assert.equal(report.files[side].storedOutcomeCount, side === 'left' ? 6 : 4);
  }
  const reportText = offlineComparisonReportJson(report);
  assert.deepEqual(JSON.parse(reportText), report);
  assert.equal(report.format, 'devdooly-offline-event-comparison-report');
  assert.deepEqual(readOfflineEventBytes(new TextEncoder().encode(reportText)), { ok: false, code: 'INVALID_DOCUMENT' });
});
