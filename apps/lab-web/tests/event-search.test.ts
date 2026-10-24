import assert from 'node:assert/strict';
import test from 'node:test';
import { readFileSync } from 'node:fs';
import type { Outcome } from '../src/lib/api.ts';
import { eventReasonOptions, filterEventOutcomes, type EventSearchFilters } from '../src/lib/event-search.ts';

// Existing public V1 expected data; these tests never create or publish a runtime result.
const fixture = JSON.parse(readFileSync(new URL('../src/data/snapshot.json', import.meta.url), 'utf8'));
const outcomes: Outcome[] = fixture.detail.outcomes;
const all: EventSearchFilters = { status: 'ALL', query: '', reason: null };
const sequences = (rows: Outcome[]) => rows.map(row => row.sequence);

test('event search keeps the existing V1 status classifications and input order', () => {
  assert.deepEqual(sequences(filterEventOutcomes(outcomes, all)), [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12]);
  for (const [status, expected] of [
    ['SUCCESS', [1, 2, 3, 8, 9, 10, 12]], ['FAILED', [5, 6, 7]], ['DUPLICATE', [4, 11]], ['PENDING', []],
  ] as const) assert.deepEqual(sequences(filterEventOutcomes(outcomes, { ...all, status })), expected);
});

test('event search combines status, literal ID or sensor text and exact reason with AND', () => {
  assert.deepEqual(sequences(filterEventOutcomes(outcomes, { status: 'FAILED', query: 'sensor-a', reason: 'OUT_OF_ORDER' })), [6]);
  assert.deepEqual(sequences(filterEventOutcomes(outcomes, { status: 'FAILED', query: 'sensor-b', reason: 'OUT_OF_RANGE' })), [7]);
  assert.deepEqual(filterEventOutcomes(outcomes, { status: 'SUCCESS', query: 'sensor-b', reason: 'OUT_OF_RANGE' }), []);
  assert.deepEqual(filterEventOutcomes(outcomes, { ...all, query: 'OUT_OF_ORDER' }), [], 'Search covers IDs, not the separate reason field');
});

test('event search retains separately addressable rows with the same event ID', () => {
  const repeated = filterEventOutcomes(outcomes, { ...all, query: 'evt-003' });
  assert.deepEqual(sequences(repeated), [3, 4]);
  assert.equal(repeated[0], outcomes[2]); assert.equal(repeated[1], outcomes[3]);
  assert.deepEqual(sequences(filterEventOutcomes(outcomes, { ...all, query: 'evt-001' })), [1, 11]);
  assert.deepEqual(sequences(filterEventOutcomes(outcomes, { status: 'DUPLICATE', query: 'evt-003', reason: 'DUPLICATE_EVENT_ID' })), [4]);
});

test('event search trims the query and ignores case while treating regex symbols literally', () => {
  const rows = [{ ...outcomes[0]!, eventId: 'Mixed[1].*+?', sensorId: 'SENSOR_(A)' },
    { ...outcomes[1]!, eventId: 'plain', sensorId: 'sensor-b' }];
  for (const query of ['  mIXed[1].*+? \n', '[1].*+', '.*', '[', ' sensor_(a) ']) {
    const result = filterEventOutcomes(rows, { ...all, query });
    assert.equal(result.length, 1, query); assert.equal(result[0], rows[0]);
  }
  assert.deepEqual(filterEventOutcomes(rows, { ...all, query: '^plain$' }), []);
  assert.deepEqual(filterEventOutcomes(rows, { ...all, query: ' \t\n ' }), rows);
});

test('event reason options retain first-seen raw unknown and empty strings as distinct filters', () => {
  const rows = ['FUTURE_REASON', '', 'OUT_OF_RANGE', 'FUTURE_REASON', ' future_reason ']
    .map((reason, index) => ({ ...outcomes[0]!, sequence: index + 1, reason }));
  assert.deepEqual(eventReasonOptions(rows), ['FUTURE_REASON', '', 'OUT_OF_RANGE', ' future_reason ']);
  assert.deepEqual(sequences(filterEventOutcomes(rows, { ...all, reason: '' })), [2]);
  assert.deepEqual(sequences(filterEventOutcomes(rows, { ...all, reason: 'FUTURE_REASON' })), [1, 4]);
  assert.deepEqual(filterEventOutcomes(rows, { ...all, reason: 'future_reason' }), []);
  assert.deepEqual(sequences(filterEventOutcomes(rows, { ...all, reason: ' future_reason ' })), [5]);
  assert.deepEqual(filterEventOutcomes(rows, all), rows);
});

test('event search handles empty results and preserves frozen source objects and raw fields', () => {
  const rows = structuredClone(outcomes); rows.forEach(Object.freeze); Object.freeze(rows);
  const before = JSON.stringify(rows);
  const filters = Object.freeze({ ...all });
  const result = filterEventOutcomes(rows, filters);
  assert.notEqual(result, rows); result.forEach((row, index) => assert.equal(row, rows[index]));
  eventReasonOptions(rows);
  assert.deepEqual(filterEventOutcomes(rows, { ...all, query: 'not-present' }), []);
  assert.deepEqual(filterEventOutcomes([], all), []); assert.deepEqual(eventReasonOptions([]), []);
  assert.equal(rows[4]!.eventTime, 'not-a-timestamp'); assert.equal(rows[6]!.value, 120);
  assert.equal(JSON.stringify(rows), before); assert.deepEqual(filters, all);
});

test('event search finds the last row and final sensor of a 1000-row synthetic result', () => {
  // Search-size input only; this does not claim a new Java execution or reproduce a runtime trace.
  const rows = Array.from({ length: 1000 }, (_, index) => ({ ...outcomes[0]!, sequence: index + 1,
    eventId: index === 999 ? 'max-099-h' : `bulk-${index}`, sensorId: `max-sensor-${String(Math.floor(index / 10)).padStart(3, '0')}` }));
  const last = filterEventOutcomes(rows, { status: 'SUCCESS', query: ' MAX-099-H ', reason: 'ACCEPTED' });
  assert.equal(last.length, 1); assert.equal(last[0], rows[999]); assert.equal(last[0]!.sequence, 1000);
  assert.deepEqual(sequences(filterEventOutcomes(rows, { ...all, query: 'max-sensor-099' })), [991, 992, 993, 994, 995, 996, 997, 998, 999, 1000]);
  assert.equal(rows.length, 1000); assert.equal(rows[0]!.sequence, 1);
});
