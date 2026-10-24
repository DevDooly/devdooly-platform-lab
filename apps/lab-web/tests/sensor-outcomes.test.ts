import assert from 'node:assert/strict';
import test from 'node:test';
import type { Outcome } from '../src/lib/api.ts';
import { sensorOutcomeSummary, selectSensorGroups } from '../src/lib/sensor-outcomes.ts';

// Synthetic display rows only. No sensor inventory, runtime execution or performance claim.
function row(sensorId: string, status: Outcome['status'] = 'SUCCESS', reason = 'ACCEPTED'): Outcome {
  return { sequence: 0, eventId: 'repeated-event', sensorId, eventTime: '2026-10-24T00:00:00Z', value: 1, status, reason };
}

test('an empty or partial observation represents only rows actually present', () => {
  assert.deepEqual(sensorOutcomeSummary([]), { availableOutcomes: 0, sensors: [] });
  const summary = sensorOutcomeSummary([row('only-observed')]);
  assert.equal(summary.availableOutcomes, 1);
  assert.deepEqual(summary.sensors, [{ sensorId: 'only-observed', total: 1, success: 1, failure: 0,
    duplicate: 0, pending: 0, failureRate: 0, failureReasons: [] }]);
});

test('all four statuses are counted without deduplicating repeated event IDs or sequences', () => {
  const input = [row('sensor-a'), row('sensor-a', 'FAILED', 'BAD'), row('sensor-a', 'DUPLICATE', 'BAD'),
    row('sensor-a', 'PENDING', 'BAD'), row('sensor-a', 'FAILED', 'BAD'), row('sensor-a')];
  const summary = sensorOutcomeSummary(input);
  assert.equal(summary.availableOutcomes, 6);
  const sensor = summary.sensors[0]!;
  assert.deepEqual([sensor.total, sensor.success, sensor.failure, sensor.duplicate, sensor.pending], [6, 2, 2, 1, 1]);
  assert.equal(sensor.success + sensor.failure + sensor.duplicate + sensor.pending, sensor.total);
  assert.equal(sensor.failureRate, 2 / 6 * 100);
  assert.deepEqual(sensor.failureReasons, [{ reason: 'BAD', count: 2 }]);
});

test('sensor IDs remain exact raw groups including whitespace, case, prefixes and object-like keys', () => {
  const ids = ['', ' ', 'sensor-1', 'sensor-10', 'Sensor-1', ' sensor-1 ', '__proto__', 'constructor', '한글/&?#'];
  const input = ids.map(sensorId => row(sensorId));
  input.push(row('sensor-1', 'FAILED', 'bad'));
  const summary = sensorOutcomeSummary(input);
  assert.deepEqual(summary.sensors.map(sensor => sensor.sensorId), ids);
  assert.equal(summary.sensors.length, ids.length);
  assert.equal(summary.sensors[2]!.total, 2);
  assert.equal(summary.sensors[2]!.failureRate, 50);
  assert.equal(summary.sensors[3]!.failureRate, 0);
});

test('failure reasons count FAILED rows only and preserve exact values and first encounter order per sensor', () => {
  const input = [row('A', 'SUCCESS', 'wrong'), row('A', 'FAILED', ''), row('A', 'FAILED', ' '),
    row('A', 'FAILED', 'BAD'), row('B', 'FAILED', 'BAD'), row('A', 'FAILED', 'bad'),
    row('A', 'DUPLICATE', 'wrong'), row('A', 'PENDING', 'wrong'), row('A', 'FAILED', '__proto__'),
    row('A', 'FAILED', ''), row('A', 'FAILED', 'constructor'), row('A', 'FAILED', '한글/&?#')];
  const summary = sensorOutcomeSummary(input);
  assert.deepEqual(summary.sensors[0]!.failureReasons, [
    { reason: '', count: 2 }, { reason: ' ', count: 1 }, { reason: 'BAD', count: 1 },
    { reason: 'bad', count: 1 }, { reason: '__proto__', count: 1 }, { reason: 'constructor', count: 1 },
    { reason: '한글/&?#', count: 1 },
  ]);
  assert.deepEqual(summary.sensors[1]!.failureReasons, [{ reason: 'BAD', count: 1 }]);
  for (const sensor of summary.sensors) assert.equal(sensor.failureReasons.reduce((sum, item) => sum + item.count, 0), sensor.failure);
});

test('failure rate uses each sensor observed count and does not imply reported input coverage', () => {
  const input = [row('A', 'FAILED'), row('A'), row('A'), row('B', 'FAILED'), row('B', 'DUPLICATE'), row('C', 'FAILED')];
  const summary = sensorOutcomeSummary(input);
  assert.deepEqual(summary.sensors.map(sensor => [sensor.sensorId, sensor.total, sensor.failureRate]), [
    ['A', 3, 1 / 3 * 100], ['B', 2, 50], ['C', 1, 100],
  ]);
  assert.equal(summary.sensors.reduce((sum, sensor) => sum + sensor.total, 0), summary.availableOutcomes);
});

test('local query is a trimmed case-insensitive sensor ID partial match and never searches event IDs or reasons', () => {
  const input = [row('sensor-1'), row('sensor-10'), row('SENSOR-1'), row('other', 'FAILED', 'sensor-1')];
  input[3]!.eventId = 'sensor-1';
  const groups = sensorOutcomeSummary(input).sensors;
  assert.deepEqual(selectSensorGroups(groups, '  SeNsOr-1  ', 'first').map(group => group.sensorId), ['sensor-1', 'sensor-10', 'SENSOR-1']);
  assert.deepEqual(selectSensorGroups(groups, '  ', 'first'), groups);
  assert.deepEqual(selectSensorGroups(groups, 'absent', 'first'), []);
  const symbols = sensorOutcomeSummary([row('[abc]'), row('abc'), row('센서 A')]).sensors;
  assert.deepEqual(selectSensorGroups(symbols, '[abc]', 'first').map(group => group.sensorId), ['[abc]']);
  assert.deepEqual(selectSensorGroups(symbols, '센서', 'first').map(group => group.sensorId), ['센서 A']);
});

test('failure count and failure rate sorts descend with first-seen ties retained', () => {
  const groups = sensorOutcomeSummary([
    row('first', 'FAILED'), row('first'), row('first'), row('first'),
    row('second', 'FAILED'), row('second'), row('third', 'FAILED'), row('third'),
    row('fourth', 'FAILED'), row('fourth', 'FAILED'), row('fourth'), row('fourth'),
    row('fifth'),
  ]).sensors;
  assert.deepEqual(selectSensorGroups(groups, '', 'first').map(group => group.sensorId), ['first', 'second', 'third', 'fourth', 'fifth']);
  assert.deepEqual(selectSensorGroups(groups, '', 'failure-count').map(group => group.sensorId), ['fourth', 'first', 'second', 'third', 'fifth']);
  assert.deepEqual(selectSensorGroups(groups, '', 'failure-rate').map(group => group.sensorId), ['second', 'third', 'fourth', 'first', 'fifth']);
  assert.deepEqual(selectSensorGroups(groups, 'i', 'failure-rate').map(group => group.sensorId), ['third', 'first', 'fifth']);
});

test('grouping and selecting preserve frozen source rows, groups and reason arrays', () => {
  const input = Object.freeze([Object.freeze(row('B', 'FAILED', 'bad')), Object.freeze(row('A'))]);
  const before = JSON.stringify(input);
  const summary = sensorOutcomeSummary(input);
  summary.sensors.forEach(group => { group.failureReasons.forEach(Object.freeze); Object.freeze(group.failureReasons); Object.freeze(group); });
  Object.freeze(summary.sensors);
  const groupsBefore = JSON.stringify(summary.sensors);
  for (const order of ['first', 'failure-count', 'failure-rate'] as const) {
    const selected = selectSensorGroups(summary.sensors, '', order);
    assert.notEqual(selected, summary.sensors);
    selected.forEach(group => assert.equal(group, summary.sensors.find(original => original.sensorId === group.sensorId)));
  }
  assert.equal(JSON.stringify(input), before);
  assert.equal(JSON.stringify(summary.sensors), groupsBefore);
});
