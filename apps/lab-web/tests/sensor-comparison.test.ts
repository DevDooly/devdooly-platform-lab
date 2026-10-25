import assert from 'node:assert/strict';
import test from 'node:test';
import type { Outcome } from '../src/lib/api.ts';
import { compareSensorOutcomes, selectSensorComparisons, type SensorComparisonRow } from '../src/lib/sensor-comparison.ts';

// Synthetic observation rows only. These comparisons do not establish sensor inventory or runtime changes.
function row(sensorId: string, status: Outcome['status'] = 'SUCCESS', reason = 'ACCEPTED'): Outcome {
  return { sequence: 0, eventId: 'repeated-event', sensorId, eventTime: '2026-10-25T00:00:00Z', value: 1, status, reason };
}
function sensorRows(sensorId: string, total: number, failures: number): Outcome[] {
  return Array.from({ length: total }, (_, index) => row(sensorId, index < failures ? 'FAILED' : 'SUCCESS', index < failures ? 'BAD' : 'ACCEPTED'));
}
const ids = (rows: readonly SensorComparisonRow[]) => rows.map(row => row.sensorId);

test('per-sensor differences reveal moved failures despite equal overall totals and failure reasons', () => {
  const comparison = compareSensorOutcomes([row('A', 'FAILED', 'BAD'), row('A'), row('B'), row('B')],
    [row('A'), row('A'), row('B', 'FAILED', 'BAD'), row('B')]);
  assert.equal(comparison.left.availableOutcomes, comparison.right.availableOutcomes);
  assert.equal(comparison.left.sensors.reduce((sum, group) => sum + group.failure, 0), 1);
  assert.equal(comparison.right.sensors.reduce((sum, group) => sum + group.failure, 0), 1);
  assert.deepEqual(comparison.left.sensors.flatMap(group => group.failureReasons), [{ reason: 'BAD', count: 1 }]);
  assert.deepEqual(comparison.right.sensors.flatMap(group => group.failureReasons), [{ reason: 'BAD', count: 1 }]);
  assert.deepEqual(comparison.rows.map(group => [group.sensorId, group.delta, group.failureRateDelta, group.different]), [
    ['A', { total: 0, success: 1, failure: -1, duplicate: 0, pending: 0 }, -50, true],
    ['B', { total: 0, success: -1, failure: 1, duplicate: 0, pending: 0 }, 50, true],
  ]);
  assert.equal(comparison.rows[0]!.left, comparison.left.sensors[0]);
  assert.equal(comparison.rows[0]!.right, comparison.right.sensors[0]);
});

test('raw sensor union keeps A first-seen order followed by B-only order, without normalizing object-like IDs', () => {
  const firstIds = ['', ' ', 'sensor-1', 'Sensor-1', '__proto__', 'constructor', ' sensor-1 ', 'sensor-10'];
  const secondIds = ['constructor', 'Sensor-1', 'B-only', '', '한글/&?#', ' '];
  const comparison = compareSensorOutcomes(firstIds.map(id => row(id)), secondIds.map(id => row(id)));
  assert.deepEqual(ids(comparison.rows), [...firstIds, 'B-only', '한글/&?#']);
  assert.equal(comparison.rows.length, 10);
  assert.equal(comparison.rows[0]!.right?.sensorId, '');
  assert.equal(comparison.rows[1]!.right?.sensorId, ' ');
  assert.equal(comparison.rows[2]!.right, null);
  assert.equal(comparison.rows[3]!.right?.sensorId, 'Sensor-1');
  assert.equal(comparison.rows[4]!.left?.total, 1);
  assert.equal(comparison.rows[8]!.left, null);
});

test('an unobserved side stays null while observed zero-failure groups have real zero differences', () => {
  const comparison = compareSensorOutcomes([row('observed-zero'), row('A-only')], [row('observed-zero'), row('B-only', 'FAILED')]);
  const [observed, aOnly, bOnly] = comparison.rows;
  assert.deepEqual(observed!.delta, { total: 0, success: 0, failure: 0, duplicate: 0, pending: 0 });
  assert.equal(observed!.failureRateDelta, 0); assert.equal(observed!.different, false);
  assert.equal(aOnly!.left?.failure, 0); assert.equal(aOnly!.right, null);
  assert.equal(bOnly!.left, null); assert.equal(bOnly!.right?.failure, 1);
  for (const missing of [aOnly!, bOnly!]) {
    assert.equal(missing.delta, null); assert.equal(missing.failureRateDelta, null); assert.equal(missing.different, true);
  }
});

test('every repeated outcome is counted and total plus all four status deltas use B minus A', () => {
  const repeated = row('A');
  const comparison = compareSensorOutcomes([repeated, repeated, row('A', 'DUPLICATE'), row('A', 'PENDING')],
    [row('A'), row('A', 'FAILED'), row('A', 'DUPLICATE'), row('A', 'DUPLICATE')]);
  assert.equal(comparison.left.availableOutcomes, 4); assert.equal(comparison.right.availableOutcomes, 4);
  assert.equal(comparison.rows[0]!.left?.success, 2);
  assert.deepEqual(comparison.rows[0]!.delta, { total: 0, success: -1, failure: 1, duplicate: 1, pending: -1 });
  assert.equal(comparison.rows[0]!.different, true);
});

test('rate differences use each observed sensor denominator without rounding or dividing by run totals', () => {
  const comparison = compareSensorOutcomes([...sensorRows('A', 3, 1), ...sensorRows('unrelated', 20, 20)],
    [...sensorRows('A', 7, 2), ...sensorRows('unrelated', 1, 0)]);
  const a = comparison.rows[0]!;
  assert.equal(a.left?.failureRate, 1 / 3 * 100); assert.equal(a.right?.failureRate, 2 / 7 * 100);
  assert.equal(a.failureRateDelta, 2 / 7 * 100 - 1 / 3 * 100);
  assert.notEqual(a.failureRateDelta, Math.round(a.failureRateDelta! * 100) / 100);
  assert.equal(a.delta?.total, 4); assert.equal(a.delta?.failure, 1);
  assert.ok(a.failureRateDelta! < 0, 'More failures can have a lower observed failure rate');
});

test('reason, event identity, time and value changes alone do not become count differences', () => {
  const a = row('A', 'FAILED', 'OLD_REASON'), b = { ...a, reason: 'NEW_REASON', eventId: 'other-event', eventTime: 'not-a-time', value: null };
  const comparison = compareSensorOutcomes([a], [b]);
  const sensor = comparison.rows[0]!;
  assert.equal(sensor.different, false); assert.equal(sensor.failureRateDelta, 0);
  assert.notDeepEqual(sensor.left?.failureReasons, sensor.right?.failureReasons);
  assert.deepEqual(selectSensorComparisons(comparison.rows, { query: '', differencesOnly: true }), []);
});

test('local trimmed case-insensitive literal sensor search combines with differences-only and excludes event IDs and reasons', () => {
  const left = [row('Sensor-[A]'), row('sensor-[a]-same'), row('other', 'FAILED', 'Sensor-[A]')];
  left[2]!.eventId = 'Sensor-[A]';
  const right = [row('Sensor-[A]', 'FAILED'), row('sensor-[a]-same'), row('other', 'FAILED', 'Sensor-[A]')];
  const comparison = compareSensorOutcomes(left, right);
  assert.deepEqual(ids(selectSensorComparisons(comparison.rows, { query: '  SENSOR-[a]  ', differencesOnly: false })), ['Sensor-[A]', 'sensor-[a]-same']);
  assert.deepEqual(ids(selectSensorComparisons(comparison.rows, { query: '  SENSOR-[a]  ', differencesOnly: true })), ['Sensor-[A]']);
  assert.deepEqual(selectSensorComparisons(comparison.rows, { query: '^Sensor', differencesOnly: false }), []);
  assert.deepEqual(ids(selectSensorComparisons(comparison.rows, { query: ' \t\n ', differencesOnly: false })), ids(comparison.rows));
  assert.deepEqual(selectSensorComparisons(comparison.rows, { query: 'missing', differencesOnly: true }), []);
});

test('absolute failure count and rate sorts put comparable zeros before missing sides and keep first-seen ties', () => {
  const comparison = compareSensorOutcomes([
    row('only-A'), ...sensorRows('first', 4, 0), ...sensorRows('second', 2, 1), ...sensorRows('third', 10, 0),
    ...sensorRows('fourth', 2, 1), row('zero'),
  ], [
    ...sensorRows('third', 10, 2), ...sensorRows('fourth', 2, 0), ...sensorRows('first', 4, 1),
    ...sensorRows('second', 2, 0), row('zero'), row('only-B'),
  ]);
  assert.deepEqual(ids(selectSensorComparisons(comparison.rows, { query: '', differencesOnly: false, order: 'first' })),
    ['only-A', 'first', 'second', 'third', 'fourth', 'zero', 'only-B']);
  assert.deepEqual(ids(selectSensorComparisons(comparison.rows, { query: '', differencesOnly: false, order: 'failure-delta' })),
    ['third', 'first', 'second', 'fourth', 'zero', 'only-A', 'only-B']);
  assert.deepEqual(ids(selectSensorComparisons(comparison.rows, { query: '', differencesOnly: false, order: 'failure-rate-delta' })),
    ['second', 'fourth', 'first', 'third', 'zero', 'only-A', 'only-B']);
  assert.deepEqual(ids(selectSensorComparisons(comparison.rows, { query: 'i', differencesOnly: true, order: 'failure-delta' })),
    ['third', 'first']);
});

test('empty observations stay empty without fabricated comparable zero rows', () => {
  assert.deepEqual(compareSensorOutcomes([], []), { left: { availableOutcomes: 0, sensors: [] }, right: { availableOutcomes: 0, sensors: [] }, rows: [] });
  assert.deepEqual(selectSensorComparisons([], { query: '', differencesOnly: false }), []);
  const comparison = compareSensorOutcomes([], [row('only-B')]);
  assert.equal(comparison.left.availableOutcomes, 0);
  assert.equal(comparison.rows[0]!.left, null); assert.equal(comparison.rows[0]!.delta, null);
});

test('comparison and selection preserve frozen sources and return original group and row references', () => {
  const left = Object.freeze([Object.freeze(row('B', 'FAILED', 'BAD')), Object.freeze(row('A'))]);
  const right = Object.freeze([Object.freeze(row('A')), Object.freeze(row('B'))]);
  const before = JSON.stringify({ left, right });
  const comparison = compareSensorOutcomes(left, right);
  for (const summary of [comparison.left, comparison.right]) {
    for (const group of summary.sensors) {
      group.failureReasons.forEach(Object.freeze); Object.freeze(group.failureReasons); Object.freeze(group);
    }
    Object.freeze(summary.sensors); Object.freeze(summary);
  }
  for (const row of comparison.rows) { if (row.delta) Object.freeze(row.delta); Object.freeze(row); }
  Object.freeze(comparison.rows); Object.freeze(comparison);
  const comparisonBefore = JSON.stringify(comparison);
  for (const order of ['first', 'failure-delta', 'failure-rate-delta'] as const) {
    const options = Object.freeze({ query: '', differencesOnly: false, order });
    const selected = selectSensorComparisons(comparison.rows, options);
    assert.notEqual(selected, comparison.rows);
    for (const row of selected) assert.equal(row, comparison.rows.find(original => original.sensorId === row.sensorId));
  }
  assert.equal(JSON.stringify({ left, right }), before); assert.equal(JSON.stringify(comparison), comparisonBefore);
});
