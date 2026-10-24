import assert from 'node:assert/strict';
import test from 'node:test';
import type { Outcome } from '../src/lib/api.ts';
import { eventSharePath, parseEventShareSelection, resolveEventShareSelection, type EventShareSelection } from '../src/lib/event-share.ts';

const selection: EventShareSelection = { runId: 'lab-fixture-20261015-v2-deploy', filters: { status: 'ALL', query: '', reason: null }, sequence: null };
const search = (value: EventShareSelection) => new URL(eventSharePath(value)!, 'https://example.invalid').search;
const row = (sequence: number, status: Outcome['status'], reason: string): Outcome => ({ sequence, eventId: 'same-id',
  sensorId: 'sensor-a', eventTime: 'not-a-time', value: 120, status, reason });

test('event share roundtrip preserves raw text and encodes delimiters as values', () => {
  const original: EventShareSelection = { ...selection, filters: { status: 'FAILED', query: '  한글 + & # =\n', reason: ' 이유 + & # = ' }, sequence: 1000 };
  const path = eventSharePath(original, '/devdooly-platform-lab/');
  assert.ok(path?.startsWith('/devdooly-platform-lab/?labRun='));
  const url = new URL(path!, 'https://example.invalid');
  assert.equal(url.hash, '#lab');
  assert.deepEqual(parseEventShareSelection(url.search), { kind: 'valid', selection: original });
  assert.deepEqual([...url.searchParams.keys()], ['labRun', 'labStatus', 'labQuery', 'labReason', 'labEvent']);
});

test('event share distinguishes absent reason and event from empty reason and zero sequence', () => {
  assert.deepEqual(parseEventShareSelection(search(selection)), { kind: 'valid', selection });
  const empty = { ...selection, filters: { ...selection.filters, reason: '' }, sequence: 0 };
  assert.deepEqual(parseEventShareSelection(search(empty)), { kind: 'valid', selection: empty });
  assert.ok(!search(selection).includes('labReason'));
  assert.ok(search(empty).includes('labReason=&labEvent=0'));
  const maximum = { ...selection, sequence: Number.MAX_SAFE_INTEGER };
  assert.deepEqual(parseEventShareSelection(search(maximum)), { kind: 'valid', selection: maximum });
});

test('unrelated evidence parameters coexist without becoming shared request parameters', () => {
  assert.deepEqual(parseEventShareSelection('?q=worker&status=failed&q=api'), { kind: 'absent' });
  const parsed = parseEventShareSelection('?q=worker&status=failed&' + search(selection).slice(1));
  assert.deepEqual(parsed, { kind: 'valid', selection });
  assert.equal(eventSharePath(selection), '/?labRun=lab-fixture-20261015-v2-deploy&labStatus=ALL&labQuery=#lab');
  assert.equal(eventSharePath(selection, '/devdooly-platform-lab'), eventSharePath(selection, '/devdooly-platform-lab/'));
});

test('partial selections, duplicate feature keys and unknown lab keys are invalid', () => {
  const valid = search(selection);
  for (const suffix of ['&labRun=other', '&labStatus=SUCCESS', '&labQuery=', '&labReason=x&labReason=y', '&labEvent=1&labEvent=2', '&labEndpoint=https://other.invalid', '&labFuture=']) {
    assert.deepEqual(parseEventShareSelection(valid + suffix), { kind: 'invalid' }, suffix);
  }
  for (const input of ['?labRun=run', '?labStatus=ALL&labQuery=', '?labQuery=', '?labReason=', '?labEvent=0', '?labFuture=']) {
    assert.deepEqual(parseEventShareSelection(input), { kind: 'invalid' }, input);
  }
});

test('IDs, statuses and sequence grammar reject ambiguous or unsafe values', () => {
  const valid = new URLSearchParams(search(selection));
  for (const [key, values] of [
    ['labRun', ['', 'Upper', '../run', 'a/b', 'a'.repeat(81), ' bad', 'https://x.invalid']],
    ['labStatus', ['', 'all', 'success', 'UNKNOWN', 'SUCCESS ']],
    ['labEvent', ['', '-1', '+1', '01', '1.0', '1e2', ' 1', 'NaN', 'Infinity', '9007199254740992']],
  ] as const) for (const value of values) {
    const params = new URLSearchParams(valid); params.set(key, value);
    assert.deepEqual(parseEventShareSelection(params.toString()), { kind: 'invalid' }, `${key}=${value}`);
  }
  for (const status of ['ALL', 'SUCCESS', 'FAILED', 'DUPLICATE', 'PENDING'] as const) {
    const value = { ...selection, filters: { ...selection.filters, status } };
    assert.deepEqual(parseEventShareSelection(search(value)), { kind: 'valid', selection: value });
  }
  const longest = { ...selection, runId: 'a'.repeat(80) };
  assert.deepEqual(parseEventShareSelection(search(longest)), { kind: 'valid', selection: longest });
});

test('share path stays on configured site root and rejects unsafe base paths and invalid selections', () => {
  for (const base of ['', '//evil.invalid/', 'https://evil.invalid/', '/../', '/a/../b/', '/./', '/%2e%2e/', '/a?x=', '/a#hash', '/a\\b/', '/a//b/']) {
    assert.equal(eventSharePath(selection, base), null, base);
  }
  for (const value of [
    { ...selection, runId: '../other' }, { ...selection, sequence: -1 }, { ...selection, sequence: 1.5 },
    { ...selection, sequence: Number.MAX_SAFE_INTEGER + 1 }, { ...selection, sequence: Number.NaN },
    { ...selection, filters: { ...selection.filters, status: 'UNKNOWN' } },
    { ...selection, filters: { ...selection.filters, query: null } },
    { ...selection, filters: { ...selection.filters, reason: 4 } },
  ]) assert.equal(eventSharePath(value as EventShareSelection), null);
});

test('event selection uses reported sequence rather than ID, array index or first matching row', () => {
  const rows = [row(0, 'SUCCESS', ''), row(1000, 'FAILED', 'OUT_OF_RANGE'), row(5, 'DUPLICATE', 'DUPLICATE_EVENT_ID')];
  assert.deepEqual(resolveEventShareSelection(selection, rows), { sequence: null, eventState: 'none' });
  assert.deepEqual(resolveEventShareSelection({ ...selection, sequence: 0 }, rows), { sequence: 0, eventState: 'selected' });
  assert.deepEqual(resolveEventShareSelection({ ...selection, sequence: 1000 }, rows), { sequence: 1000, eventState: 'selected' });
  assert.deepEqual(resolveEventShareSelection({ ...selection, sequence: 1 }, rows), { sequence: null, eventState: 'missing' });
  assert.deepEqual(resolveEventShareSelection({ ...selection, sequence: 1000 }, []), { sequence: null, eventState: 'missing' });
});

test('shared filters use existing AND semantics and never reveal an excluded selected event', () => {
  const rows = [row(1000, 'FAILED', 'OUT_OF_RANGE')];
  const target = { ...selection, sequence: 1000 };
  assert.deepEqual(resolveEventShareSelection({ ...target, filters: { status: 'FAILED', query: ' SAME-ID ', reason: 'OUT_OF_RANGE' } }, rows), { sequence: 1000, eventState: 'selected' });
  for (const filters of [
    { ...selection.filters, status: 'SUCCESS' as const }, { ...selection.filters, query: 'no-match' },
    { ...selection.filters, reason: '' }, { ...selection.filters, reason: 'out_of_range' },
  ]) assert.deepEqual(resolveEventShareSelection({ ...target, filters }, rows), { sequence: null, eventState: 'filtered' });
  const raw = JSON.stringify(rows); rows.forEach(Object.freeze); Object.freeze(rows);
  resolveEventShareSelection(target, rows);
  assert.equal(JSON.stringify(rows), raw); assert.equal(rows[0]!.value, 120); assert.equal(rows[0]!.eventTime, 'not-a-time');
});

test('optional exact sensor keeps legacy shared URLs byte-for-byte and their three-field filter shape', () => {
  const legacy: EventShareSelection = { ...selection, filters: { status: 'FAILED', query: ' sensor-a ', reason: 'OUT_OF_RANGE' }, sequence: 5 };
  const expected = '/devdooly-platform-lab/?labRun=lab-fixture-20261015-v2-deploy&labStatus=FAILED&labQuery=+sensor-a+&labReason=OUT_OF_RANGE&labEvent=5#lab';
  assert.equal(eventSharePath(legacy, '/devdooly-platform-lab/'), expected);
  for (const sensorId of [null, undefined]) {
    assert.equal(eventSharePath({ ...legacy, filters: { ...legacy.filters, sensorId } }, '/devdooly-platform-lab/'), expected);
  }
  const parsed = parseEventShareSelection(new URL(expected, 'https://example.invalid').search);
  assert.deepEqual(parsed, { kind: 'valid', selection: legacy });
  assert.ok(parsed.kind === 'valid');
  assert.deepEqual(Object.keys(parsed.selection.filters), ['status', 'query', 'reason']);
});

test('exact sensor shares roundtrip raw empty, whitespace, case, delimiters and Unicode without changing other filters', () => {
  for (const sensorId of ['', ' ', 'SENSOR-A', ' sensor-a ', '센서 + & # = / ? %\n', 'sensor-😀']) {
    const original = { ...selection, filters: { status: 'FAILED' as const, query: ' MIXED ', reason: '', sensorId }, sequence: 0 };
    const path = eventSharePath(original, '/devdooly-platform-lab/');
    assert.ok(path);
    const url = new URL(path, 'https://example.invalid');
    assert.equal(url.searchParams.get('labSensor'), sensorId);
    assert.deepEqual(parseEventShareSelection(url.search), { kind: 'valid', selection: original });
    assert.deepEqual([...url.searchParams.keys()], ['labRun', 'labStatus', 'labQuery', 'labReason', 'labSensor', 'labEvent']);
  }
  const empty = search({ ...selection, filters: { ...selection.filters, sensorId: '' } });
  assert.ok(empty.endsWith('&labSensor='));
  assert.deepEqual(parseEventShareSelection(search(selection) + '&labSensor'), {
    kind: 'valid', selection: { ...selection, filters: { ...selection.filters, sensorId: '' } },
  });
});

test('exact sensor namespace rejects duplicate keys and share generation refuses lossy UTF-16 conversion', () => {
  for (const suffix of ['&labSensor=x&labSensor=y', '&labSensor=&labSensor=', '&labSensor=x&labSensor', '&lab%53ensor=x&labSensor=y']) {
    assert.deepEqual(parseEventShareSelection(search(selection) + suffix), { kind: 'invalid' });
  }
  for (const sensorId of ['\ud800', '\udfff', 'prefix\ud800suffix', '\udc00\ud800', 1, false, {}]) {
    assert.equal(eventSharePath({ ...selection, filters: { ...selection.filters, sensorId } } as EventShareSelection), null);
  }
  // A real replacement character is valid; it must not be confused with a normalized lone surrogate.
  const replacement = { ...selection, filters: { ...selection.filters, sensorId: '\ufffd' } };
  assert.deepEqual(parseEventShareSelection(search(replacement)), { kind: 'valid', selection: replacement });
});

test('shared sequence resolution uses exact sensor and existing AND filters without replacing an excluded row', () => {
  const rows = [
    { ...row(1, 'FAILED', 'OUT_OF_RANGE'), sensorId: 'sensor-1' },
    { ...row(2, 'FAILED', 'OUT_OF_RANGE'), sensorId: 'sensor-10', eventId: 'sensor-1-event' },
    { ...row(3, 'SUCCESS', 'ACCEPTED'), sensorId: '' },
  ];
  rows.forEach(Object.freeze); Object.freeze(rows);
  const before = JSON.stringify(rows);
  const target = { ...selection, filters: { ...selection.filters, sensorId: 'sensor-1' }, sequence: 1 };
  assert.deepEqual(resolveEventShareSelection(target, rows), { sequence: 1, eventState: 'selected' });
  assert.deepEqual(resolveEventShareSelection({ ...target, sequence: 2 }, rows), { sequence: null, eventState: 'filtered' });
  assert.deepEqual(resolveEventShareSelection({ ...target, sequence: 999 }, rows), { sequence: null, eventState: 'missing' });
  for (const filters of [{ ...target.filters, query: 'no-match' }, { ...target.filters, reason: '' }, { ...target.filters, status: 'SUCCESS' as const }]) {
    assert.deepEqual(resolveEventShareSelection({ ...target, filters }, rows), { sequence: null, eventState: 'filtered' });
  }
  assert.deepEqual(resolveEventShareSelection({ ...target, sequence: 3, filters: { ...selection.filters, sensorId: '' } }, rows), { sequence: 3, eventState: 'selected' });
  assert.equal(JSON.stringify(rows), before);
});
