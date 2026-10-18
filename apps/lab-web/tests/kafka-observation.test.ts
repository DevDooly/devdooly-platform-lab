import assert from 'node:assert/strict';
import test from 'node:test';
import { mkdtempSync, readFileSync, rmSync, rmdirSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { dirname, join } from 'node:path';
import { spawnSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import ts from 'typescript';
import { KAFKA_ERROR_CODES, KAFKA_STALE_AFTER_MS, MAX_KAFKA_OBSERVATION_BYTES, kafkaObservationView, kafkaUtcNs,
  loadKafkaObservation, parseKafkaObservation, parseKafkaObservationError, safeKafkaObservationUrl, validateKafkaObservation } from '../src/lib/kafka-observation.ts';
import type { KafkaObservation } from '../src/lib/kafka-observation.ts';

// Explicit synthetic test input only. No observations/kafka.latest.json is created or used as a default record.
const now = Date.UTC(2026, 9, 18, 12, 0, 10);
const sample = (): KafkaObservation => ({ schemaVersion: 1, kind: 'kafka-observation', synthetic: true,
  environment: 'MINI_PC', scope: 'DEPLOYED_KAFKA', publicExecutionEnabled: false, sourceCommit: 'a'.repeat(40),
  captureStartedAt: '2026-10-18T12:00:00Z', capturedAt: '2026-10-18T12:00:02Z', consistency: 'BOUNDED_SEQUENTIAL_READ',
  targetFingerprint: 'b'.repeat(64), groupState: 'STABLE', partition: 0, commitState: 'OBSERVED',
  logStartOffset: 0, readCommittedEndOffset: 8, committedOffset: 8, lag: 0 });
const encoded = (value: unknown) => JSON.stringify(value);
const fetcher = (value: unknown, status = 200): typeof fetch => async () => new Response(typeof value === 'string' ? value : encoded(value), { status });
const url = '/devdooly-platform-lab/observations/kafka.latest.json';

test('Kafka success uses exactly 18 fields and distinguishes observed zero from no commit', () => {
  const zero = parseKafkaObservation(encoded(sample()), now); assert.ok(zero); assert.equal(Object.keys(zero).length, 18);
  assert.equal(zero.committedOffset, 8); assert.equal(zero.lag, 0);
  const none = sample(); none.commitState = 'NO_COMMIT'; none.committedOffset = null; none.lag = null;
  assert.ok(parseKafkaObservation(encoded(none), now));
  assert.equal(parseKafkaObservation(encoded({ ...none, committedOffset: 0, lag: 0 }), now), null);
  const isolated = { ...sample(), environment: 'ISOLATED_LAB', scope: 'ISOLATED_KAFKA', groupState: 'EMPTY' };
  assert.ok(parseKafkaObservation(encoded(isolated), now));
  assert.equal(parseKafkaObservation(encoded({ ...isolated, scope: 'DEPLOYED_KAFKA' }), now), null);
  assert.equal(parseKafkaObservation(encoded({ ...sample(), scope: 'ISOLATED_KAFKA' }), now), null);
});

test('source reader rejects duplicate escaped keys, private extras, nested values and noninteger JSON lexemes', () => {
  const raw = encoded(sample());
  for (const text of [raw.replace('"lag":0', '"lag":0,"lag":0'), raw.replace('"lag":0', '"lag":0,"\\u006cag":0'),
    raw.replace('"lag":0', '"lag":NaN'), raw.replace('"lag":0', '"lag":Infinity'), raw.replace('"lag":0', '"lag":1e309'),
    raw.replace('"lag":0', '"lag":0.0'), raw.replace('"lag":0', '"lag":0e0'), raw.replace('"lag":0', '"lag":-0'),
    raw.replace('"lag":0', '"lag":9007199254740990.5'), raw.replace('"lag":0', '"lag":{}'),
    raw.replace('"lag":0', '"lag":[]'), raw.replace('"lag":0', '"lag":0,'), raw + ' null', '\uFEFF' + raw,
    encoded({ ...sample(), rawTopic: 'SYNTHETIC_PRIVATE_CANARY' }), encoded({ ...sample(), rawError: 'SYNTHETIC_PRIVATE_CANARY' })]) {
    assert.equal(parseKafkaObservation(text, now), null);
  }
  assert.ok(parseKafkaObservation(raw.replace('"lag":0', '"\\u006cag":0'), now));
  for (const value of [null, [], {}, true, 1]) assert.equal(parseKafkaObservation(value, now), null);
});

test('Kafka source ingress accepts exactly 8KiB and rejects the next UTF-8 byte', () => {
  const raw = encoded(sample()); const padding = MAX_KAFKA_OBSERVATION_BYTES - Buffer.byteLength(raw);
  assert.ok(parseKafkaObservation(raw + ' '.repeat(padding), now));
  assert.equal(parseKafkaObservation(raw + ' '.repeat(padding + 1), now), null);
  assert.equal(parseKafkaObservation(raw + ' '.repeat(padding - 1) + '가', now), null);
});

test('UTC precision, real calendar dates, four-second capture and nanosecond future boundaries are exact', () => {
  for (let digits = 0; digits <= 9; digits++) {
    const fraction = digits ? '.' + '1'.repeat(digits) : '';
    assert.notEqual(kafkaUtcNs('2026-10-18T12:00:02' + fraction + 'Z'), null);
  }
  assert.notEqual(kafkaUtcNs('2024-02-29T00:00:00Z'), null);
  for (const value of ['2026-02-29T00:00:00Z', '2026-04-31T00:00:00Z', '2026-13-01T00:00:00Z',
    '2026-10-18T24:00:00Z', '2026-10-18T12:60:00Z', '2026-10-18T12:00:60Z', '2026-10-18T12:00:02.Z',
    '2026-10-18T12:00:02.1234567890Z', '2026-10-18T12:00:02+00:00', '2026-10-18T12:00:02z']) assert.equal(kafkaUtcNs(value), null);
  assert.ok(parseKafkaObservation(encoded({ ...sample(), capturedAt: '2026-10-18T12:00:04Z' }), now));
  assert.equal(parseKafkaObservation(encoded({ ...sample(), capturedAt: '2026-10-18T12:00:04.000000001Z' }), now), null);
  assert.equal(parseKafkaObservation(encoded({ ...sample(), captureStartedAt: '2026-10-18T12:00:03Z' }), now), null);
  assert.ok(parseKafkaObservation(encoded({ ...sample(), captureStartedAt: '2026-10-18T12:00:09Z', capturedAt: '2026-10-18T12:00:10Z' }), now));
  assert.equal(parseKafkaObservation(encoded({ ...sample(), captureStartedAt: '2026-10-18T12:00:09Z', capturedAt: '2026-10-18T12:00:10.000000001Z' }), now), null);
  assert.equal(parseKafkaObservation(encoded(sample()), NaN), null);
});

test('safe offset integers and start, LSO, commit, lag relations reject boolean coercion and impossible ranges', () => {
  const max = Number.MAX_SAFE_INTEGER;
  assert.ok(parseKafkaObservation(encoded({ ...sample(), logStartOffset: max, readCommittedEndOffset: max, committedOffset: max }), now));
  for (const key of ['logStartOffset', 'readCommittedEndOffset', 'committedOffset', 'lag']) {
    for (const value of [true, false, -1, 0.5, max + 1, '0', null]) assert.equal(parseKafkaObservation(encoded({ ...sample(), [key]: value }), now), null);
  }
  for (const changed of [{ logStartOffset: 9 }, { readCommittedEndOffset: 7 }, { committedOffset: 9 }, { committedOffset: 7, lag: 0 },
    { logStartOffset: 4, committedOffset: 3, lag: 5 }]) assert.equal(parseKafkaObservation(encoded({ ...sample(), ...changed }), now), null);
});

test('fixed scope and source fields never admit worker claims or raw identity and errors', () => {
  for (const [key, value] of [['schemaVersion', true], ['partition', false], ['partition', 1], ['synthetic', false],
    ['publicExecutionEnabled', true], ['sourceCommit', 'unknown'], ['sourceCommit', 'A'.repeat(40)],
    ['targetFingerprint', 'b'.repeat(63)], ['consistency', 'ATOMIC'], ['groupState', 'DEAD'], ['commitState', 'UNKNOWN']]) {
    assert.equal(parseKafkaObservation(encoded({ ...sample(), [key as string]: value }), now), null);
  }
  for (const key of ['clusterId', 'topicUuid', 'group', 'members', 'bootstrapServers', 'credentials', 'workerAlive', 'rawError']) {
    assert.equal(parseKafkaObservation(encoded({ ...sample(), [key]: 'SYNTHETIC_PRIVATE_CANARY' }), now), null);
  }
});

test('Kafka failures accept only exact fixed-code envelopes and reject duplicate or provider text', () => {
  for (const code of KAFKA_ERROR_CODES) assert.equal(parseKafkaObservationError(encoded({ schemaVersion: 1, kind: 'kafka-observation-error', code })), code);
  for (const value of [{ schemaVersion: true, kind: 'kafka-observation-error', code: 'KAFKA_UNAVAILABLE' },
    { schemaVersion: 1, kind: 'kafka-observation-error', code: 'SYNTHETIC_PRIVATE_CANARY' },
    { schemaVersion: 1, kind: 'kafka-observation-error', code: 'KAFKA_UNAVAILABLE', message: 'SYNTHETIC_PRIVATE_CANARY' }]) assert.equal(parseKafkaObservationError(encoded(value)), null);
  assert.equal(parseKafkaObservationError('{"schemaVersion":1,"kind":"kafka-observation-error","code":"KAFKA_UNAVAILABLE","\\u0063ode":"KAFKA_UNAVAILABLE"}'), null);
});

test('failed refresh preserves only the current page memory record and its original capture time', async () => {
  const previous = sample(); const controller = new AbortController(); controller.abort();
  const cases: Array<[typeof fetch, string, AbortSignal?]> = [
    [fetcher('', 404), 'NOT_CONFIGURED'], [fetcher('SYNTHETIC_PRIVATE_CANARY', 500), 'HTTP_ERROR'],
    [fetcher(encoded(sample()).replace('"lag":0', '"lag":0,"lag":0')), 'INVALID_RECORD'],
    [fetcher(' '.repeat(MAX_KAFKA_OBSERVATION_BYTES + 1)), 'INVALID_RECORD'],
    [async () => { throw new Error('SYNTHETIC_PRIVATE_CANARY'); }, 'NETWORK_ERROR'],
    [async () => { throw new Error('SYNTHETIC_PRIVATE_CANARY'); }, 'ABORTED', controller.signal],
  ];
  for (const [read, error, signal] of cases) {
    const result = await loadKafkaObservation({ url, previousRecord: previous, nowMs: now, fetcher: read, signal });
    assert.equal(result.browserError, error); assert.equal(result.record, previous); assert.equal(result.retainedPrevious, true);
    assert.equal(result.record?.capturedAt, previous.capturedAt); assert.ok(!encoded(result).includes('SYNTHETIC_PRIVATE_CANARY'));
  }
  const absent = await loadKafkaObservation({ url, nowMs: now, fetcher: fetcher('', 404) });
  assert.equal(absent.record, null); assert.equal(absent.retainedPrevious, false);
});

test('new targets and older timestamps do not replace memory; isolated publication is a separate explicit policy', async () => {
  const previous = sample();
  for (const [changed, expected] of [[{ ...sample(), targetFingerprint: 'c'.repeat(64) }, 'TARGET_CHANGED'],
    [{ ...sample(), capturedAt: '2026-10-18T12:00:01.999999999Z' }, 'OLDER_RECORD'],
    [{ ...sample(), environment: 'ISOLATED_LAB', scope: 'ISOLATED_KAFKA' }, 'ENVIRONMENT_MISMATCH']] as const) {
    const result = await loadKafkaObservation({ url, previousRecord: previous, nowMs: now, fetcher: fetcher(changed) });
    assert.equal(result.browserError, expected); assert.equal(result.record, previous);
  }
  const isolated = { ...sample(), environment: 'ISOLATED_LAB', scope: 'ISOLATED_KAFKA' };
  assert.ok(parseKafkaObservation(encoded(isolated), now));
  const local = await loadKafkaObservation({ url: '/api/kafka/observation', allowIsolated: true, nowMs: now, fetcher: fetcher(isolated) });
  assert.equal(local.record?.environment, 'ISOLATED_LAB'); assert.equal(local.browserError, null);
  const next = { ...sample(), capturedAt: '2026-10-18T12:00:03Z', readCommittedEndOffset: 9, lag: 1 };
  const loaded = await loadKafkaObservation({ url, previousRecord: previous, nowMs: now, fetcher: fetcher(next) });
  assert.equal(loaded.record?.lag, 1); assert.equal(loaded.retainedPrevious, false);
});

test('browser source reader enforces UTF-8 and fixed paths and requests no credentials or execution parameters', async () => {
  let calls = 0;
  const read: typeof fetch = async (input, options) => { calls++; assert.equal(input, url); assert.equal(options?.cache, 'no-store'); assert.equal(options?.credentials, 'omit'); assert.equal(options?.method, undefined); return new Response(encoded(sample())); };
  assert.ok((await loadKafkaObservation({ url, nowMs: now, fetcher: read })).record); assert.equal(calls, 1);
  for (const value of ['https://example.com/observations/kafka.latest.json', '//example.com/api/kafka/observation', '/api/kafka/observation?group=private', '/api/kafka/observation#private', '/observations/../kafka.latest.json']) {
    assert.equal(safeKafkaObservationUrl(value), false);
    assert.equal((await loadKafkaObservation({ url: value, nowMs: now, fetcher: read })).browserError, 'INVALID_URL');
  }
  assert.equal(calls, 1);
  const invalidUtf8: typeof fetch = async () => new Response(new Uint8Array([0xc3, 0x28]));
  assert.equal((await loadKafkaObservation({ url, nowMs: now, fetcher: invalidUtf8 })).browserError, 'INVALID_RECORD');
  const unavailable = await loadKafkaObservation({ url, nowMs: now, fetcher: fetcher({ schemaVersion: 1, kind: 'kafka-observation-error', code: 'TARGET_UNVERIFIED' }, 503) });
  assert.equal(unavailable.browserError, 'TARGET_UNVERIFIED'); assert.equal(unavailable.record, null);
  const rawFailure = await loadKafkaObservation({ url, nowMs: now, fetcher: fetcher({ schemaVersion: 1, kind: 'kafka-observation-error', code: 'TARGET_UNVERIFIED', message: 'SYNTHETIC_PRIVATE_CANARY' }, 503) });
  assert.equal(rawFailure.browserError, 'HTTP_ERROR'); assert.ok(!encoded(rawFailure).includes('SYNTHETIC_PRIVATE_CANARY'));
});

test('equal capture instants retain the original record and reject conflicting valid values without lexical timestamp loss', async () => {
  const previous = sample();
  for (const changed of [{ ...sample(), readCommittedEndOffset: 9, lag: 1 },
    { ...sample(), sourceCommit: 'c'.repeat(40) }, { ...sample(), groupState: 'EMPTY' },
    { ...sample(), commitState: 'NO_COMMIT', committedOffset: null, lag: null },
    { ...sample(), captureStartedAt: '2026-10-18T12:00:00.000000001Z' }]) {
    assert.ok(parseKafkaObservation(encoded(changed), now));
    const result = await loadKafkaObservation({ url, previousRecord: previous, nowMs: now, fetcher: fetcher(changed) });
    assert.equal(result.browserError, 'CONFLICTING_RECORD'); assert.equal(result.record, previous);
    assert.equal(result.record?.capturedAt, previous.capturedAt); assert.equal(result.retainedPrevious, true);
  }
  const equivalent = { ...sample(), captureStartedAt: '2026-10-18T12:00:00.000000000Z', capturedAt: '2026-10-18T12:00:02.0Z' };
  const reordered = Object.fromEntries(Object.entries(equivalent).reverse());
  const same = await loadKafkaObservation({ url, previousRecord: previous, nowMs: now, fetcher: fetcher(reordered) });
  assert.equal(same.browserError, null); assert.equal(same.record, previous); assert.equal(same.retainedPrevious, true);
  assert.equal(same.record?.capturedAt, '2026-10-18T12:00:02Z');
  const precise = { ...sample(), capturedAt: '2026-10-18T12:00:02.000000001Z' };
  const forward = await loadKafkaObservation({ url, previousRecord: previous, nowMs: now, fetcher: fetcher(precise) });
  assert.equal(forward.browserError, null); assert.equal(forward.record?.capturedAt, precise.capturedAt);
  assert.equal(forward.retainedPrevious, false);
});

test('year zero is rejected by the general reader API loader and CLI while year one remains valid', async () => {
  const zero = { ...sample(), captureStartedAt: '0000-01-01T00:00:00Z', capturedAt: '0000-01-01T00:00:02Z' };
  const one = { ...sample(), captureStartedAt: '0001-01-01T00:00:00Z', capturedAt: '0001-01-01T00:00:02Z' };
  assert.equal(kafkaUtcNs(zero.captureStartedAt), null); assert.equal(parseKafkaObservation(encoded(zero), now), null);
  assert.ok(parseKafkaObservation(encoded(one), now));
  const api = await loadKafkaObservation({ url: '/api/kafka/observation', allowIsolated: true, previousRecord: sample(), nowMs: now, fetcher: fetcher(zero) });
  assert.equal(api.browserError, 'INVALID_RECORD'); assert.equal(api.record?.capturedAt, sample().capturedAt);
  const folder = mkdtempSync(join(tmpdir(), 'platform-kafka-year-'));
  const path = join(folder, 'record.json'); assert.equal(dirname(path), folder);
  const script = fileURLToPath(new URL('../scripts/validate-kafka-observation.ts', import.meta.url));
  try {
    writeFileSync(path, encoded(one), { encoding: 'utf8', mode: 0o600 });
    const positive = spawnSync(process.execPath, ['--experimental-strip-types', '--no-warnings', script, path], { encoding: 'utf8', timeout: 5000, windowsHide: true });
    assert.equal(positive.status, 0); assert.equal(positive.stderr, ''); assert.equal(JSON.parse(positive.stdout).valid, true);
    writeFileSync(path, encoded(zero), { encoding: 'utf8', mode: 0o600 });
    const negative = spawnSync(process.execPath, ['--experimental-strip-types', '--no-warnings', script, path], { encoding: 'utf8', timeout: 5000, windowsHide: true });
    assert.equal(negative.status, 1); assert.equal(negative.stdout, ''); assert.equal(negative.stderr.trim(), 'INVALID_KAFKA_OBSERVATION');
  } finally { rmSync(path, { force: true }); rmdirSync(folder); }
});

test('freshness uses the original record time and keeps nanosecond future or clock regressions unverified', () => {
  const record = sample(); const captured = Date.UTC(2026, 9, 18, 12, 0, 2);
  assert.equal(kafkaObservationView(null, now), 'absent'); assert.equal(kafkaObservationView(record, now), 'recent');
  assert.equal(kafkaObservationView(record, captured + KAFKA_STALE_AFTER_MS), 'recent');
  assert.equal(kafkaObservationView(record, captured + KAFKA_STALE_AFTER_MS + 1), 'stale');
  assert.equal(kafkaObservationView(record, captured - 1), 'clock-check'); assert.equal(kafkaObservationView(record, NaN), 'clock-check');
  assert.equal(kafkaObservationView({ ...record, capturedAt: '2026-10-18T12:00:02.000000001Z' }, captured), 'clock-check');
  assert.equal(validateKafkaObservation(record, now), true);
});

test('readout renders absent, zero, missing commit, stale and fixed unverified messages without a control or raw identity', async () => {
  const source = readFileSync(new URL('../src/components/KafkaObservationCard.tsx', import.meta.url), 'utf8');
  let code = ts.transpileModule(source, { compilerOptions: { jsx: ts.JsxEmit.ReactJSX, module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022 } }).outputText;
  code = code.replace(/from (['"])react\1/g, `from ${JSON.stringify(import.meta.resolve('react'))}`)
    .replace(/from (['"])react\/jsx-runtime\1/g, `from ${JSON.stringify(import.meta.resolve('react/jsx-runtime'))}`)
    .replace(/from (['"])\.\.\/lib\/kafka-observation\1/g, `from ${JSON.stringify(new URL('../src/lib/kafka-observation.ts', import.meta.url).href)}`)
    .replace(/import (['"])\.\.\/styles\/kafka-observation\.css\1;?/g, '');
  const { KafkaObservationReadout } = await import(`data:text/javascript;base64,${Buffer.from(code).toString('base64')}`);
  const render = (record: KafkaObservation | null, clock = now, error: string | null = null) => renderToStaticMarkup(createElement(KafkaObservationReadout, { record, nowMs: clock, error, retained: record !== null }));
  const empty = render(null); assert.ok(empty.includes('Kafka 관측 미연결')); assert.ok(!empty.includes('관측 lag'));
  const zero = render(sample()); assert.ok(zero.includes('관측 lag')); assert.ok(zero.includes('>0</p>')); assert.ok(zero.includes('READ_COMMITTED'));
  const none = { ...sample(), commitState: 'NO_COMMIT' as const, committedOffset: null, lag: null };
  const missing = render(none); assert.ok(missing.includes('Commit 미관측')); assert.ok(missing.includes('미관측'));
  assert.ok(!missing.includes('>0</p>'));
  assert.ok(render(sample(), now + KAFKA_STALE_AFTER_MS + 1).includes('오래된 Kafka 기록'));
  assert.ok(render(sample(), now, 'TARGET_UNVERIFIED').includes('identity를 확인하지 못했습니다'));
  assert.ok(!/<details[^>]*\bopen(?:\s|=|>)/.test(zero)); assert.ok(!zero.includes('<button'));
  assert.ok(!zero.includes('bootstrapServers')); assert.ok(!zero.includes('topicUuid')); assert.ok(!zero.includes('groupId'));
});
