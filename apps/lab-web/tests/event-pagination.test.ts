import assert from 'node:assert/strict';
import test from 'node:test';
import type { Outcome } from '../src/lib/api.ts';
import { EVENT_PAGE_SIZES, eventPage, eventPageForSequence } from '../src/lib/event-pagination.ts';
import { createEventExport } from '../src/lib/event-export.ts';
import { filterEventOutcomes } from '../src/lib/event-search.ts';

// Synthetic display input only; no runtime execution or throughput claim.
function rows(length: number): Outcome[] {
  return Array.from({ length }, (_, index) => ({
    sequence: index, eventId: `event-${index}`, sensorId: 'sensor-a',
    eventTime: '2026-10-24T00:00:00Z', value: index,
    status: 'SUCCESS', reason: 'ACCEPTED',
  }));
}

test('empty and exact-page results have accurate counts and one-based positions', () => {
  assert.deepEqual(EVENT_PAGE_SIZES, [25, 50, 100]);
  assert.deepEqual(eventPage([], 4, 25), { rows: [], index: 0, totalPages: 0, total: 0, start: 0, end: 0 });
  const input = rows(25);
  assert.deepEqual(eventPage(input, 0, 25), { rows: input, index: 0, totalPages: 1, total: 25, start: 1, end: 25 });
});

test('a 26-row result keeps its final row on a second page', () => {
  const input = rows(26);
  const first = eventPage(input, 0, 25);
  const second = eventPage(input, 1, 25);
  assert.equal(first.rows.length, 25);
  assert.deepEqual(second, { rows: [input[25]], index: 1, totalPages: 2, total: 26, start: 26, end: 26 });
  assert.equal(second.rows[0], input[25]);
});

test('1000 rows can be traversed completely at every offered page size', () => {
  const input = rows(1000);
  for (const size of EVENT_PAGE_SIZES) {
    const count = 1000 / size;
    const final = eventPage(input, count - 1, size);
    assert.equal(final.index, count - 1);
    assert.equal(final.totalPages, count);
    assert.equal(final.start, 1001 - size);
    assert.equal(final.end, 1000);
    assert.equal(final.rows.length, size);
    assert.equal(final.rows.at(-1), input[999]);
    const visited = Array.from({ length: count }, (_, page) => eventPage(input, page, size).rows).flat();
    assert.deepEqual(visited, input);
    visited.forEach((row, index) => assert.equal(row, input[index]));
  }
});

test('page indexes clamp to available bounds and invalid numeric indexes start at zero', () => {
  const input = rows(26);
  for (const requested of [-1, -100, 0]) assert.equal(eventPage(input, requested, 25).index, 0);
  for (const requested of [1, 2, 100, Number.MAX_SAFE_INTEGER]) assert.equal(eventPage(input, requested, 25).index, 1);
  for (const requested of [NaN, Infinity, -Infinity, 0.5, 1.5, -0.5]) {
    const page = eventPage(input, requested, 25);
    assert.equal(page.index, 0); assert.equal(page.rows[0], input[0]);
  }
});

test('paging preserves sparse sequence order, duplicate event IDs, row references and frozen inputs', () => {
  const input = rows(30).map((row, index) => Object.freeze({ ...row, sequence: 200 - index * 3, eventId: 'repeated-id' }));
  Object.freeze(input);
  const before = JSON.stringify(input);
  const first = eventPage(input, 0, 25);
  const final = eventPage(input, 1, 25);
  assert.notEqual(first.rows, input);
  assert.equal(first.rows[0], input[0]); assert.equal(final.rows[0], input[25]);
  assert.deepEqual(final.rows.map(row => row.sequence), [125, 122, 119, 116, 113]);
  assert.deepEqual([final.start, final.end], [26, 30]);
  assert.equal(JSON.stringify(input), before);
});

test('selected sequence navigation uses the filtered position, including zero and a late page', () => {
  const input = rows(1000);
  assert.equal(eventPageForSequence(input, 0, 25), 0);
  assert.equal(eventPageForSequence(input, 25, 25), 1);
  assert.equal(eventPageForSequence(input, 999, 25), 39);
  assert.equal(eventPageForSequence(input, 999, 50), 19);
  assert.equal(eventPageForSequence(input, 999, 100), 9);
  assert.equal(eventPageForSequence(input, null, 25), null);
  assert.equal(eventPageForSequence(input, 1000, 25), null);
  assert.equal(eventPageForSequence([], 0, 25), null);
  const sparse = [input[999]!, input[0]!, input[25]!].map(row => ({ ...row, eventId: 'same-id' }));
  assert.equal(eventPageForSequence(sparse, 999, 25), 0);
  assert.equal(eventPageForSequence(sparse, 25, 25), 0);
});

test('paging a filtered result does not narrow search export to the visible page', () => {
  const input = rows(100).map((row, index) => ({ ...row, sensorId: index % 2 === 0 ? 'chosen' : 'other' }));
  const filters = { status: 'ALL' as const, query: 'chosen', reason: null };
  const filtered = filterEventOutcomes(input, filters);
  const visible = eventPage(filtered, 1, 25);
  assert.deepEqual([visible.total, visible.start, visible.end], [50, 26, 50]);
  assert.equal(visible.rows[0], input[50]);
  assert.equal(eventPageForSequence(filtered, 98, 25), 1);
  assert.equal(eventPageForSequence(filtered, 99, 25), null);
  const exported = createEventExport({ runId: 'synthetic-display', mode: 'fixture', observedAt: null,
    capturedAt: null, reportedInputCount: 100, filters, outcomes: input });
  assert.equal(exported.counts.matchedOutcomes, 50);
  assert.equal(exported.outcomes.length, 50);
  assert.deepEqual(exported.outcomes.map(row => row.sequence), filtered.map(row => row.sequence));
});
