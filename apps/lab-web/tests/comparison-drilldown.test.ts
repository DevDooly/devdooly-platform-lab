import assert from 'node:assert/strict';
import test from 'node:test';
import type { Outcome } from '../src/lib/api.ts';
import { comparisonEventPath } from '../src/lib/comparison-drilldown.ts';
import { filterEventOutcomes } from '../src/lib/event-search.ts';
import { parseEventShareSelection } from '../src/lib/event-share.ts';

const runId = 'lab-fixture-20261015-v2-deploy';
const parsedPath = (path: string | null) => {
  assert.ok(path);
  const url = new URL(path, 'https://example.invalid');
  assert.equal(url.origin, 'https://example.invalid');
  assert.equal(url.hash, '#lab');
  const parsed = parseEventShareSelection(url.search);
  assert.equal(parsed.kind, 'valid');
  return { url, selection: parsed.selection };
};

test('comparison drilldown targets the displayed run at root and configured subpath without preselecting a row', () => {
  for (const basePath of ['/', '/devdooly-platform-lab/', '/devdooly-platform-lab']) {
    const { url, selection } = parsedPath(comparisonEventPath(runId, basePath));
    assert.equal(url.pathname, basePath === '/' ? '/' : '/devdooly-platform-lab/');
    assert.deepEqual(selection, { runId, filters: { status: 'ALL', query: '', reason: null }, sequence: null });
    assert.deepEqual([...url.searchParams.keys()], ['labRun', 'labStatus', 'labQuery']);
  }
  assert.equal(parsedPath(comparisonEventPath('other-run', '/')).selection.runId, 'other-run');
});

test('failure drilldown roundtrips exact raw reasons, including empty, whitespace and URL delimiters', () => {
  for (const reason of ['', ' ', ' OUT_OF_RANGE ', '시간 + & # = ? % /\n🧪']) {
    const { selection } = parsedPath(comparisonEventPath(runId, '/devdooly-platform-lab/', { status: 'FAILED', reason }));
    assert.deepEqual(selection, { runId, filters: { status: 'FAILED', query: '', reason }, sequence: null });
  }
  const { url, selection } = parsedPath(comparisonEventPath(runId, '/', { status: 'FAILED' }));
  assert.equal(selection.filters.reason, null);
  assert.equal(url.searchParams.has('labReason'), false);
});

test('links enter the existing status-and-raw-reason filter without replacing counts or event identity', () => {
  const row = (sequence: number, status: Outcome['status'], reason: string): Outcome => ({
    sequence, eventId: 'same-id', sensorId: 'sensor-a', eventTime: 'raw-time', value: 120, status, reason,
  });
  const rows = [row(101, 'FAILED', ''), row(7, 'SUCCESS', ''), row(92, 'FAILED', ' '), row(0, 'FAILED', ''), row(3, 'FAILED', 'OUT_OF_RANGE')];
  rows.forEach(Object.freeze); Object.freeze(rows);
  const all = parsedPath(comparisonEventPath(runId, '/')).selection;
  const failed = parsedPath(comparisonEventPath(runId, '/', { status: 'FAILED' })).selection;
  const emptyReason = parsedPath(comparisonEventPath(runId, '/', { status: 'FAILED', reason: '' })).selection;
  assert.deepEqual(filterEventOutcomes(rows, all.filters), rows);
  assert.deepEqual(filterEventOutcomes(rows, failed.filters).map(row => row.sequence), [101, 92, 0, 3]);
  const selected = filterEventOutcomes(rows, emptyReason.filters);
  assert.deepEqual(selected.map(row => row.sequence), [101, 0]);
  assert.equal(selected[0], rows[0]);
  assert.equal(selected[1], rows[3]);
});

test('invalid IDs and unsafe destinations use the shared path rejection contract', () => {
  assert.equal(comparisonEventPath('../run', '/'), null);
  assert.equal(comparisonEventPath(runId, '//other.invalid/'), null);
  assert.equal(comparisonEventPath(runId, '/../'), null);
});
