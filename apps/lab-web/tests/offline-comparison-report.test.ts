import assert from 'node:assert/strict';
import test from 'node:test';
import type { Outcome } from '../src/lib/api.ts';
import { createEventExport, eventExportJson, type EventExportInput } from '../src/lib/event-export.ts';
import { readOfflineEventBytes, type OfflineEventFile } from '../src/lib/offline-event-file.ts';
import { createOfflineComparisonReport, offlineComparisonReportJson, OFFLINE_COMPARISON_REPORT_FILENAME,
  type OfflineReportSelection } from '../src/lib/offline-comparison-report.ts';

// Synthetic local observations only. A report records the review conditions without authenticating the source files.
const row = (sequence: number, fields: Partial<Outcome> = {}): Outcome => ({ sequence, eventId: `event-${sequence}`, sensorId: 'sensor-a',
  eventTime: 'invalid-raw-time', value: 1, status: 'SUCCESS', reason: 'ACCEPTED', ...fields });
function file(name: string, outcomes: Outcome[], fields: Partial<EventExportInput> = {}): OfflineEventFile {
  const document = createEventExport({ runId: name, mode: 'recorded', observedAt: '2026-10-25T09:00:00+09:00', capturedAt: null,
    reportedInputCount: 100, filters: { status: 'ALL', query: '', reason: null }, outcomes, ...fields });
  return { name, byteLength: new TextEncoder().encode(eventExportJson(document)).byteLength, document };
}
const selection = (fields: Partial<OfflineReportSelection> = {}): OfflineReportSelection => ({ query: '', kind: 'all', limit: 20, ...fields });
const capturedAt = '2026-10-25T03:04:05.678Z';

test('all 25 matching groups are saved while the report separately records a 20-group display window', () => {
  const outcomes = Array.from({ length: 25 }, (_, sequence) => row(sequence));
  const report = createOfflineComparisonReport({ left: file('A.json', outcomes), right: file('B.json', [...outcomes].reverse()) },
    selection(), capturedAt);
  assert.equal(report.format, 'devdooly-offline-event-comparison-report'); assert.equal(report.schemaVersion, 1);
  assert.equal(report.capturedAt, capturedAt);
  assert.deepEqual(report.view, { query: '', kind: 'all', displayLimit: 20 });
  assert.deepEqual(report.counts, { totalGroups: 25, matchingGroups: 25, displayedGroups: 20 });
  assert.deepEqual(report.groups.map(group => group.sequence), Array.from({ length: 25 }, (_, index) => index));
  assert.equal(report.groups[24]!.left[0]!.eventId, 'event-24');
  assert.deepEqual(report.classifications, { ambiguous: 0, unobserved: 0, 'input-different': 0, 'verdict-different': 0, 'observed-equal': 25 });
});

test('raw current search and exact category form an AND filter without changing whole-comparison classifications', () => {
  const left = file('left.json', [row(0), row(0), row(1), row(2), row(3), row(4)]);
  const right = file('right.json', [row(0), row(2, { value: 2 }), row(3, { reason: 'OTHER' }), row(4)]);
  const report = createOfflineComparisonReport({ left, right }, selection({ query: '  EVENT-3  ', kind: 'verdict-different' }), capturedAt);
  assert.deepEqual(report.view, { query: '  EVENT-3  ', kind: 'verdict-different', displayLimit: 20 });
  assert.deepEqual(report.counts, { totalGroups: 5, matchingGroups: 1, displayedGroups: 1 });
  assert.deepEqual(report.classifications, { ambiguous: 1, unobserved: 1, 'input-different': 1, 'verdict-different': 1, 'observed-equal': 1 });
  assert.deepEqual(report.groups.map(group => group.sequence), [3]);
  assert.deepEqual(report.groups[0]!.inputDifferences, []); assert.deepEqual(report.groups[0]!.verdictDifferences, ['reason']);
  const excluded = createOfflineComparisonReport({ left, right }, selection({ query: 'event-2', kind: 'verdict-different' }), capturedAt);
  assert.deepEqual(excluded.groups, []); assert.equal(excluded.counts.totalGroups, 5);
  assert.deepEqual(excluded.counts, { totalGroups: 5, matchingGroups: 0, displayedGroups: 0 });
});

test('zero matches and empty files retain their metadata and full classification counts without fabricated rows', () => {
  const pair = { left: file('a.json', [row(8)]), right: file('b.json', [row(8)]) };
  const noMatches = createOfflineComparisonReport(pair, selection({ query: 'no-match' }), capturedAt);
  assert.deepEqual(noMatches.groups, []); assert.deepEqual(noMatches.counts, { totalGroups: 1, matchingGroups: 0, displayedGroups: 0 });
  assert.equal(noMatches.classifications['observed-equal'], 1); assert.equal(noMatches.files.left.storedOutcomeCount, 1);
  const empty = createOfflineComparisonReport({ left: file('empty-a.json', []), right: file('empty-b.json', []) }, selection(), capturedAt);
  assert.deepEqual(empty.groups, []); assert.deepEqual(empty.counts, { totalGroups: 0, matchingGroups: 0, displayedGroups: 0 });
  assert.deepEqual(empty.classifications, { ambiguous: 0, unobserved: 0, 'input-different': 0, 'verdict-different': 0, 'observed-equal': 0 });
  assert.equal(empty.files.left.name, 'empty-a.json'); assert.equal(empty.files.right.storedOutcomeCount, 0);
});

test('all ambiguous candidates retain their source order and raw fields even when the display limit is zero', () => {
  const a1 = row(8, { eventId: 'repeated', value: null }), a2 = row(8, { eventId: 'repeated', value: 0, status: 'DUPLICATE' });
  const b1 = row(8, { sensorId: 'Sensor-A', reason: '' }), b2 = row(8, { sensorId: ' Sensor-A ', value: -4 });
  const report = createOfflineComparisonReport({ left: file('a.json', [a2, a1]), right: file('b.json', [b1, b2]) },
    selection({ kind: 'ambiguous', limit: 0 }), capturedAt);
  assert.deepEqual(report.counts, { totalGroups: 1, matchingGroups: 1, displayedGroups: 0 });
  assert.deepEqual(report.groups, [{ sequence: 8, left: [a2, a1], right: [b1, b2],
    inputDifferences: null, verdictDifferences: null, kind: 'ambiguous' }]);
  assert.equal(report.groups[0]!.left[0]!.value, 0); assert.equal(report.groups[0]!.left[1]!.value, null);
});

test('missing positions and differing inputs preserve empty sides, null differences and raw invalid event times', () => {
  const a0 = row(0, { eventTime: '', value: null }), a5 = row(5, { eventTime: 'not-a-date' });
  const b5 = row(5, { value: 0, status: 'FAILED', reason: 'OUT_OF_RANGE' }), b10 = row(10);
  const report = createOfflineComparisonReport({ left: file('a.json', [a5, a0]), right: file('b.json', [b10, b5]) }, selection(), capturedAt);
  assert.deepEqual(report.groups.map(group => [group.sequence, group.kind]), [[0, 'unobserved'], [5, 'input-different'], [10, 'unobserved']]);
  assert.deepEqual(report.groups[0]!.right, []); assert.equal(report.groups[0]!.inputDifferences, null);
  assert.equal(report.groups[0]!.left[0]!.eventTime, ''); assert.equal(report.groups[0]!.left[0]!.value, null);
  assert.deepEqual(report.groups[1]!.inputDifferences, ['eventTime', 'value']);
  assert.deepEqual(report.groups[1]!.verdictDifferences, ['status', 'reason']);
  assert.deepEqual(report.groups[2]!.left, []); assert.equal(report.groups[2]!.verdictDifferences, null);
});

test('file context remains separate from current view with raw timestamps, original counts and schema-specific filters', () => {
  const left = file('../<A>.json', [row(9, { eventId: 'shared', reason: '' }), row(1)], {
    runId: ' arbitrary/id? ', mode: 'fixture', observedAt: null, capturedAt: 'Sun, 25 Oct 2026 00:00:00 GMT',
    reportedInputCount: 0, filters: { status: 'ALL', query: 'SHARED ', reason: '' },
  });
  const right = file('B\n한글.json', [row(9, { sensorId: '', eventId: 'shared', reason: '' }), row(2)], {
    mode: 'live', observedAt: '2026-10-25T09:00:00+09:00', capturedAt: null,
    reportedInputCount: 800, filters: { status: 'ALL', query: '', reason: null, sensorId: '' },
  });
  const report = createOfflineComparisonReport({ left, right }, selection({ query: ' shared ', kind: 'input-different', limit: 40 }), capturedAt);
  assert.deepEqual(report.files.left, { name: left.name, byteLength: left.byteLength, schemaVersion: 1,
    source: { runId: ' arbitrary/id? ', mode: 'fixture', observedAt: null, capturedAt: 'Sun, 25 Oct 2026 00:00:00 GMT' },
    filters: { status: 'ALL', query: 'SHARED ', reason: '' },
    counts: { reportedInputCount: 0, availableOutcomes: 2, matchedOutcomes: 1 }, storedOutcomeCount: 1 });
  assert.deepEqual(report.files.right, { name: right.name, byteLength: right.byteLength, schemaVersion: 2,
    source: right.document.source, filters: { status: 'ALL', query: '', reason: null, sensorId: '' },
    counts: { reportedInputCount: 800, availableOutcomes: 2, matchedOutcomes: 1 }, storedOutcomeCount: 1 });
  assert.equal(Object.hasOwn(report.files.left.filters, 'sensorId'), false);
  assert.deepEqual(report.view, { query: ' shared ', kind: 'input-different', displayLimit: 40 });
  assert.deepEqual(report.counts, { totalGroups: 1, matchingGroups: 1, displayedGroups: 1 });
});

test('created report is detached from later file, metadata, outcome and selection edits in both directions', () => {
  const left = file('a.json', [row(0), row(0, { value: null }), row(1)]);
  const right = file('b.json', [row(0), row(1, { reason: 'OTHER' })]);
  const selected = selection(); const pair = { left, right };
  const report = createOfflineComparisonReport(pair, selected, capturedAt);
  const before = offlineComparisonReportJson(report);
  left.name = 'replacement'; left.byteLength = 0; left.document.source.runId = 'changed';
  left.document.source.observedAt = null; left.document.filters.query = 'changed'; left.document.counts.availableOutcomes = 999;
  left.document.outcomes[0]!.eventId = 'changed'; left.document.outcomes[1]!.value = 200; left.document.outcomes.push(row(99));
  right.document.outcomes[1]!.reason = 'changed'; selected.query = 'next-query'; selected.kind = 'unobserved'; selected.limit = 200;
  pair.right = file('new-pair.json', []);
  assert.equal(offlineComparisonReportJson(report), before);
  report.files.right.filters.query = 'report-only'; report.groups[0]!.left[0]!.sensorId = 'report-only';
  report.groups[1]!.verdictDifferences!.push('status');
  assert.equal(right.document.filters.query, ''); assert.equal(left.document.outcomes[0]!.sensorId, 'sensor-a');
  assert.equal(right.document.outcomes[1]!.status, 'SUCCESS');
});

test('snapshot keeps numeric negative zero while native JSON serializes it as zero rather than restoring original bytes', () => {
  const report = createOfflineComparisonReport({ left: file('negative-zero.json', [row(0, { value: -0 })]),
    right: file('zero.json', [row(0, { value: 0 })]) }, selection(), capturedAt);
  assert.equal(Object.is(report.groups[0]!.left[0]!.value, -0), true);
  assert.equal(report.groups[0]!.kind, 'observed-equal');
  const parsed = JSON.parse(offlineComparisonReportJson(report));
  assert.equal(Object.is(parsed.groups[0].left[0].value, -0), false);
  assert.equal(parsed.groups[0].left[0].value, 0);
});

test('frozen file context and selection stay unchanged while report JSON round-trips raw strings and all matching groups', () => {
  const pair = { left: file('=left\n"한글".json', [row(2, { eventId: '\ud800', sensorId: '<script>', value: null })]),
    right: file('right.json', [row(2, { eventId: '\ud800', sensorId: '<script>', value: 0 })]) };
  const selected = selection({ query: '  <SCRIPT> ', limit: 20 });
  const before = JSON.stringify({ pair, selected });
  function freeze(value: object): void { for (const nested of Object.values(value)) if (typeof nested === 'object' && nested !== null) freeze(nested); Object.freeze(value); }
  freeze(pair); freeze(selected);
  const report = createOfflineComparisonReport(pair, selected, capturedAt);
  const text = offlineComparisonReportJson(report);
  assert.ok(text.endsWith('\n')); assert.match(text, /\n  "format": "devdooly-offline-event-comparison-report",/);
  assert.deepEqual(JSON.parse(text), report); assert.equal(JSON.stringify({ pair, selected }), before);
  assert.equal(report.groups[0]!.left[0]!.eventId, '\ud800'); assert.equal(report.groups[0]!.right[0]!.value, 0);
  assert.equal(OFFLINE_COMPARISON_REPORT_FILENAME, 'devdooly-event-comparison-report.json');
  assert.deepEqual(readOfflineEventBytes(new TextEncoder().encode(text)), { ok: false, code: 'INVALID_DOCUMENT' });
});
