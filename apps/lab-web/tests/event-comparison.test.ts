import assert from 'node:assert/strict';
import test from 'node:test';
import type { Outcome } from '../src/lib/api.ts';
import { compareSensorOutcomes } from '../src/lib/sensor-comparison.ts';
import { compareEventOutcomes, selectEventComparisons, type EventComparisonKind, type EventComparisonRow } from '../src/lib/event-comparison.ts';

// Synthetic reported rows. Even equal fields do not prove original input bytes or a common code version.
function outcome(sequence: number, fields: Partial<Outcome> = {}): Outcome {
  return { sequence, eventId: `event-${sequence}`, sensorId: 'sensor-a', eventTime: '2026-10-25T00:00:00Z',
    value: 1, status: 'SUCCESS', reason: 'ACCEPTED', ...fields };
}
const sequences = (rows: readonly EventComparisonRow[]) => rows.map(row => row.sequence);
const kinds: EventComparisonKind[] = ['ambiguous', 'unobserved', 'input-different', 'verdict-different', 'observed-equal'];

test('event differences expose swapped values and judgments hidden by equal aggregate and sensor counts', () => {
  const left = [outcome(0, { value: 10 }), outcome(1, { value: 110, status: 'FAILED', reason: 'OUT_OF_RANGE' })];
  const right = [outcome(0, { value: 110, status: 'FAILED', reason: 'OUT_OF_RANGE' }), outcome(1, { value: 10 })];
  const sensor = compareSensorOutcomes(left, right).rows[0]!;
  assert.equal(sensor.different, false);
  assert.deepEqual(sensor.left?.failureReasons, sensor.right?.failureReasons);
  const result = compareEventOutcomes(left, right);
  assert.deepEqual(result.rows.map(row => [row.sequence, row.kind, row.inputDifferences, row.verdictDifferences]), [
    [0, 'input-different', ['value'], ['status', 'reason']],
    [1, 'input-different', ['value'], ['status', 'reason']],
  ]);
  assert.equal(result.counts['input-different'], 2); assert.equal(result.counts['verdict-different'], 0);
});

test('matching reported input fields with status or reason differences become verdict differences', () => {
  const left = [outcome(0), outcome(1), outcome(2)];
  const right = [outcome(0, { status: 'PENDING' }), outcome(1, { reason: 'OTHER' }),
    outcome(2, { status: 'DUPLICATE', reason: 'REPEATED_ID' })];
  const result = compareEventOutcomes(left, right);
  assert.deepEqual(result.rows.map(row => row.kind), ['verdict-different', 'verdict-different', 'verdict-different']);
  assert.deepEqual(result.rows.map(row => row.inputDifferences), [[], [], []]);
  assert.deepEqual(result.rows.map(row => row.verdictDifferences), [['status'], ['reason'], ['status', 'reason']]);
  assert.equal(result.counts['verdict-different'], 3);
});

test('raw event ID, sensor ID, time string and value changes are reported in field order', () => {
  const result = compareEventOutcomes([outcome(4)], [outcome(4, {
    eventId: 'EVENT-4 ', sensorId: ' Sensor-a', eventTime: '2026-10-25T09:00:00+09:00', value: null,
  })]);
  assert.equal(result.rows[0]!.kind, 'input-different');
  assert.deepEqual(result.rows[0]!.inputDifferences, ['eventId', 'sensorId', 'eventTime', 'value']);
  assert.deepEqual(result.rows[0]!.verdictDifferences, []);
});

test('null values compare literally and stay distinct from zero without inventing original input', () => {
  const result = compareEventOutcomes([outcome(0, { value: null }), outcome(1, { value: null }), outcome(2, { value: 0 })],
    [outcome(0, { value: null }), outcome(1, { value: 0 }), outcome(2, { value: null })]);
  assert.deepEqual(result.rows.map(row => [row.kind, row.inputDifferences]), [
    ['observed-equal', []], ['input-different', ['value']], ['input-different', ['value']],
  ]);
  assert.equal(result.rows[0]!.left[0]!.value, null); assert.equal(result.rows[0]!.right[0]!.value, null);
});

test('rows align by numeric sequence and sort gaps, zero and large positions without sorting sources', () => {
  const large = Number.MAX_SAFE_INTEGER;
  const left = [outcome(10), outcome(0), outcome(large), outcome(2)];
  const right = [outcome(large), outcome(5), outcome(10), outcome(0)];
  const result = compareEventOutcomes(left, right);
  assert.deepEqual(sequences(result.rows), [0, 2, 5, 10, large]);
  assert.equal(result.leftCount, 4); assert.equal(result.rightCount, 4);
  assert.deepEqual(left.map(row => row.sequence), [10, 0, large, 2]);
  assert.deepEqual(right.map(row => row.sequence), [large, 5, 10, 0]);
  assert.equal(result.rows[1]!.kind, 'unobserved'); assert.equal(result.rows[2]!.kind, 'unobserved');
});

test('duplicate event IDs at different positions stay separate and moved IDs are never rematched', () => {
  const result = compareEventOutcomes([outcome(0, { eventId: 'repeated' }), outcome(1, { eventId: 'repeated' }),
    outcome(2, { eventId: 'moved' })], [outcome(1, { eventId: 'repeated' }), outcome(3, { eventId: 'moved' })]);
  assert.deepEqual(result.rows.map(row => [row.sequence, row.kind]), [
    [0, 'unobserved'], [1, 'observed-equal'], [2, 'unobserved'], [3, 'unobserved'],
  ]);
  assert.equal(result.counts.ambiguous, 0); assert.equal(result.counts.unobserved, 3);
});

test('duplicate sequences on either or both sides are ambiguous and retain every original row in source order', () => {
  const a0 = outcome(0), a0Again = outcome(0), a2 = outcome(2), a2Again = outcome(2, { value: 2 });
  const b1 = outcome(1), b1Again = outcome(1, { value: 9 }), b2 = outcome(2), b2Again = outcome(2);
  const left = [a2Again, a0, a2, a0Again, outcome(1)];
  const right = [b2, b1Again, b2Again, b1, outcome(0)];
  const result = compareEventOutcomes(left, right);
  assert.deepEqual(result.rows.map(row => row.kind), ['ambiguous', 'ambiguous', 'ambiguous']);
  assert.deepEqual(result.rows.map(row => [row.inputDifferences, row.verdictDifferences]), [[null, null], [null, null], [null, null]]);
  assert.deepEqual(result.rows.map(row => [row.left.length, row.right.length]), [[2, 1], [1, 2], [2, 2]]);
  assert.equal(result.rows[0]!.left[0], a0); assert.equal(result.rows[0]!.left[1], a0Again);
  assert.equal(result.rows[1]!.right[0], b1Again); assert.equal(result.rows[1]!.right[1], b1);
  assert.equal(result.rows[2]!.left[0], a2Again); assert.equal(result.rows[2]!.left[1], a2);
  assert.equal(result.leftCount, 5); assert.equal(result.rightCount, 5); assert.equal(result.counts.ambiguous, 3);
});

test('even repeated references at a sequence missing on the other side are ambiguous before unobserved', () => {
  const repeated = outcome(0);
  const result = compareEventOutcomes([repeated, repeated], [outcome(1), outcome(1)]);
  assert.deepEqual(result.rows.map(row => [row.sequence, row.kind, row.left.length, row.right.length]), [
    [0, 'ambiguous', 2, 0], [1, 'ambiguous', 0, 2],
  ]);
  assert.equal(result.rows[0]!.left[0], repeated); assert.equal(result.rows[0]!.left[1], repeated);
  assert.deepEqual(result.counts, { ambiguous: 2, unobserved: 0, 'input-different': 0, 'verdict-different': 0, 'observed-equal': 0 });
});

test('one observed row without a partner stays unobserved with null differences and an empty side', () => {
  const a = outcome(1), b = outcome(2);
  const result = compareEventOutcomes([a], [b]);
  assert.deepEqual(result.rows, [
    { sequence: 1, left: [a], right: [], kind: 'unobserved', inputDifferences: null, verdictDifferences: null },
    { sequence: 2, left: [], right: [b], kind: 'unobserved', inputDifferences: null, verdictDifferences: null },
  ]);
  assert.equal(result.rows[0]!.left[0], a); assert.equal(result.rows[1]!.right[0], b);
});

test('empty observations do not fabricate rows and category counts count aligned positions rather than source rows', () => {
  assert.deepEqual(compareEventOutcomes([], []), { rows: [], leftCount: 0, rightCount: 0,
    counts: { ambiguous: 0, unobserved: 0, 'input-different': 0, 'verdict-different': 0, 'observed-equal': 0 } });
  const left = [outcome(0), outcome(0), outcome(1), outcome(2), outcome(3), outcome(4)];
  const right = [outcome(0), outcome(2, { value: 2 }), outcome(3, { reason: 'OTHER' }), outcome(4)];
  const result = compareEventOutcomes(left, right);
  assert.deepEqual(result.counts, { ambiguous: 1, unobserved: 1, 'input-different': 1, 'verdict-different': 1, 'observed-equal': 1 });
  assert.equal(Object.values(result.counts).reduce((sum, count) => sum + count, 0), result.rows.length);
  assert.equal(result.leftCount, 6); assert.equal(result.rightCount, 4);
});

test('literal trimmed case-insensitive ID search reaches either side and every ambiguous member', () => {
  const result = compareEventOutcomes([
    outcome(0, { eventId: 'left-[a]' }), outcome(1, { sensorId: 'left-sensor' }),
    outcome(2, { eventId: 'ordinary' }), outcome(2, { sensorId: 'Ambiguous-[A]' }),
    outcome(3, { reason: 'hidden-[a]', eventTime: '[a]' }),
  ], [outcome(0, { eventId: 'right-[A]' }), outcome(1, { sensorId: 'right-[a]' })]);
  assert.deepEqual(sequences(selectEventComparisons(result.rows, { query: '  [A]  ', kind: 'all' })), [0, 1, 2]);
  assert.deepEqual(sequences(selectEventComparisons(result.rows, { query: '  ambiguous-[a]  ', kind: 'all' })), [2]);
  assert.deepEqual(sequences(selectEventComparisons(result.rows, { query: 'right-[a]', kind: 'input-different' })), [0, 1]);
  assert.deepEqual(sequences(selectEventComparisons(result.rows, { query: ' [a] ', kind: 'ambiguous' })), [2]);
  assert.deepEqual(selectEventComparisons(result.rows, { query: '^left', kind: 'all' }), []);
  assert.deepEqual(selectEventComparisons(result.rows, { query: 'hidden-[a]', kind: 'all' }), []);
  assert.deepEqual(selectEventComparisons(result.rows, { query: 'missing', kind: 'all' }), []);
});

test('blank search keeps each category and exact kind selection never merges input and verdict differences', () => {
  const result = compareEventOutcomes([outcome(0), outcome(0), outcome(1), outcome(2), outcome(3), outcome(4)],
    [outcome(0), outcome(2, { value: 2, reason: 'OTHER' }), outcome(3, { reason: 'OTHER' }), outcome(4)]);
  assert.deepEqual(sequences(selectEventComparisons(result.rows, { query: ' \t\n ', kind: 'all' })), [0, 1, 2, 3, 4]);
  for (const [index, kind] of kinds.entries()) {
    const selected = selectEventComparisons(result.rows, { query: '', kind });
    assert.deepEqual(sequences(selected), [index]); assert.equal(selected[0], result.rows[index]);
  }
  assert.deepEqual(selectEventComparisons([], { query: '', kind: 'all' }), []);
});

test('comparison and filtering do not mutate frozen inputs, groups, row references or options', () => {
  const left = Object.freeze([Object.freeze(outcome(9)), Object.freeze(outcome(2)), Object.freeze(outcome(2, { eventId: 'extra' }))]);
  const right = Object.freeze([Object.freeze(outcome(9, { reason: 'OTHER' })), Object.freeze(outcome(0))]);
  const before = JSON.stringify({ left, right });
  const result = compareEventOutcomes(left, right);
  assert.equal(result.rows[2]!.left[0], left[0]); assert.equal(result.rows[2]!.right[0], right[0]);
  for (const row of result.rows) {
    Object.freeze(row.left); Object.freeze(row.right);
    if (row.inputDifferences) Object.freeze(row.inputDifferences);
    if (row.verdictDifferences) Object.freeze(row.verdictDifferences);
    Object.freeze(row);
  }
  Object.freeze(result.rows); Object.freeze(result.counts); Object.freeze(result);
  const resultBefore = JSON.stringify(result);
  for (const kind of ['all', ...kinds] as const) {
    const options = Object.freeze({ query: '', kind });
    const selected = selectEventComparisons(result.rows, options);
    assert.notEqual(selected, result.rows);
    for (const row of selected) assert.equal(row, result.rows.find(original => original.sequence === row.sequence));
  }
  assert.equal(JSON.stringify({ left, right }), before); assert.equal(JSON.stringify(result), resultBefore);
});
