import assert from 'node:assert/strict';
import test from 'node:test';
import type { Outcome } from '../src/lib/api.ts';
import { createEventExport, eventExportJson, type EventExportDocument, type EventExportInput } from '../src/lib/event-export.ts';
import { compareEventOutcomes } from '../src/lib/event-comparison.ts';
import { MAX_OFFLINE_FILE_BYTES, MAX_OFFLINE_OUTCOMES, readOfflineEventBytes, readOfflineEventFile } from '../src/lib/offline-event-file.ts';

// Synthetic saved exports only. Local validation cannot authenticate the reported metadata or prove full input coverage.
const encoder = new TextEncoder();
const row = (sequence: number, fields: Partial<Outcome> = {}): Outcome => ({ sequence, eventId: 'repeat-id', sensorId: 'sensor-a',
  eventTime: 'raw-invalid-time', value: 1, status: 'SUCCESS', reason: 'ACCEPTED', ...fields });
function input(fields: Partial<EventExportInput> = {}): EventExportInput {
  return { runId: 'run-example', mode: 'recorded', observedAt: '2026-10-25T09:00:00+09:00', capturedAt: null,
    reportedInputCount: 12, filters: { status: 'ALL', query: '', reason: null }, outcomes: [row(7), row(0)], ...fields };
}
const document = () => createEventExport(input());
const read = (value: unknown) => readOfflineEventBytes(encoder.encode(JSON.stringify(value)));
function accepted(value: EventExportDocument): EventExportDocument {
  const result = readOfflineEventBytes(encoder.encode(eventExportJson(value)));
  assert.equal(result.ok, true);
  if (!result.ok) assert.fail(result.code);
  assert.deepEqual(result.document, value);
  return result.document;
}

test('current producer schema 1 and 2 round-trip full, partial and zero-match exports without rewriting raw fields', () => {
  const outcomes = [row(8, { sensorId: '', reason: '', status: 'FAILED', value: null }), row(2), row(2, { status: 'DUPLICATE' })];
  for (const filters of [
    { status: 'ALL' as const, query: ' ', reason: null },
    { status: 'DUPLICATE' as const, query: ' REPEAT-ID ', reason: 'ACCEPTED' },
    { status: 'FAILED' as const, query: '', reason: '', sensorId: '' },
    { status: 'FAILED' as const, query: 'missing', reason: '', sensorId: '' },
  ]) accepted(createEventExport(input({ outcomes, filters })));
  const full = accepted(createEventExport(input({ outcomes })));
  assert.deepEqual(full.outcomes.map(outcome => outcome.sequence), [8, 2, 2]);
  assert.equal(full.outcomes[0]!.eventTime, 'raw-invalid-time'); assert.equal(full.outcomes[0]!.value, null);
});

test('all three source modes, parseable raw timestamps and arbitrary run IDs are retained as data', () => {
  for (const mode of ['live', 'recorded', 'fixture'] as const) {
    const value = createEventExport(input({ mode, runId: ' ../?x=<script>\n한글 ',
      observedAt: '2026-10-25T09:00:00+09:00', capturedAt: 'Sun, 25 Oct 2026 00:01:00 GMT' }));
    accepted(value);
  }
  accepted(createEventExport(input({ runId: '', observedAt: null, capturedAt: null })));
});

test('partial observations need not cover reported inputs or have unique, continuous or bounded-by-count sequence values', () => {
  const value = createEventExport(input({ reportedInputCount: 0, outcomes: [row(Number.MAX_SAFE_INTEGER), row(0), row(0)] }));
  value.counts.availableOutcomes = 10000;
  const parsed = accepted(value);
  assert.deepEqual(parsed.counts, { reportedInputCount: 0, availableOutcomes: 10000, matchedOutcomes: 3 });
  const comparison = compareEventOutcomes(parsed.outcomes, parsed.outcomes);
  assert.deepEqual(comparison.rows.map(group => [group.sequence, group.kind]), [[0, 'ambiguous'], [Number.MAX_SAFE_INTEGER, 'observed-equal']]);
  assert.equal(comparison.rows[0]!.left[0], parsed.outcomes[1]);
  assert.equal(comparison.rows[0]!.left[1], parsed.outcomes[2]);
});

test('literal strings, invalid event times, null and zero values survive without normalization', () => {
  const value = createEventExport(input({ outcomes: [row(0, { eventId: '', sensorId: ' Sensor-A ', eventTime: '', reason: '', value: null }),
    row(1, { eventId: '\ud800', sensorId: '__proto__', eventTime: 'not-a-date', value: 0 })] }));
  const parsed = accepted(value);
  assert.equal(parsed.outcomes[0]!.value, null); assert.equal(parsed.outcomes[1]!.value, 0);
  assert.equal(parsed.outcomes[1]!.eventId, '\ud800');
});

test('byte limit is inclusive and applies to UTF-8 bytes rather than character count', () => {
  const text = eventExportJson(document());
  const padded = encoder.encode(text + ' '.repeat(MAX_OFFLINE_FILE_BYTES - encoder.encode(text).byteLength));
  assert.equal(padded.byteLength, MAX_OFFLINE_FILE_BYTES); assert.equal(readOfflineEventBytes(padded).ok, true);
  assert.deepEqual(readOfflineEventBytes(new Uint8Array(MAX_OFFLINE_FILE_BYTES + 1)), { ok: false, code: 'FILE_TOO_LARGE' });
  const value = document(); value.source.runId = '한'.repeat(400000);
  const encoded = encoder.encode(JSON.stringify(value));
  assert.ok(JSON.stringify(value).length < MAX_OFFLINE_FILE_BYTES); assert.ok(encoded.byteLength > MAX_OFFLINE_FILE_BYTES);
  assert.deepEqual(readOfflineEventBytes(encoded), { ok: false, code: 'FILE_TOO_LARGE' });
});

test('exactly 1000 outcomes are accepted and 1001 are rejected independently of claimed counts', () => {
  const thousand = createEventExport(input({ outcomes: Array.from({ length: MAX_OFFLINE_OUTCOMES }, (_, sequence) => row(sequence)) }));
  assert.equal(accepted(thousand).outcomes.length, 1000);
  const overflow = structuredClone(thousand); overflow.outcomes.push(row(1000));
  overflow.counts.availableOutcomes = 1001; overflow.counts.matchedOutcomes = 1001;
  assert.deepEqual(read(overflow), { ok: false, code: 'TOO_MANY_OUTCOMES' });
  overflow.counts.matchedOutcomes = 0;
  assert.deepEqual(read(overflow), { ok: false, code: 'TOO_MANY_OUTCOMES' });
});

test('malformed UTF-8 has a finite decoding error; one leading UTF-8 BOM is optional', () => {
  for (const bytes of [new Uint8Array([0xff]), new Uint8Array([0xc0, 0xaf]), new Uint8Array([0xe3, 0x81]),
    new Uint8Array([0xed, 0xa0, 0x80])]) assert.deepEqual(readOfflineEventBytes(bytes), { ok: false, code: 'INVALID_UTF8' });
  const text = eventExportJson(document());
  assert.equal(readOfflineEventBytes(encoder.encode('\uFEFF' + text)).ok, true);
  for (const prefix of ['\uFEFF\uFEFF', ' \uFEFF'])
    assert.deepEqual(readOfflineEventBytes(encoder.encode(prefix + text)), { ok: false, code: 'INVALID_JSON' });
});

test('invalid JSON and decoded duplicate keys fail before schema validation without echoing input', () => {
  const text = JSON.stringify(document());
  const duplicates = [
    text.replace('"schemaVersion":1', '"schemaVersion":1,"schemaVersion":1'),
    text.replace('"schemaVersion":1', '"schemaVersion":1,"\\u0073chemaVersion":1'),
    text.replace('"runId":"run-example"', '"runId":"run-example","\\u0072unId":"secret-token"'),
    text.replace('"query":""', '"query":"","query":""'),
    text.replace('"matchedOutcomes":2', '"matchedOutcomes":2,"matchedOutcomes":2'),
    text.replace('"sequence":7', '"sequence":7,"\\u0073equence":7'),
  ];
  for (const invalid of ['', 'null trailing', '{', text + 'x', ...duplicates])
    assert.deepEqual(readOfflineEventBytes(encoder.encode(invalid)), { ok: false, code: 'INVALID_JSON' });
});

test('exact root, source, counts, filters and outcome keys reject unknown, missing and object-like keys', () => {
  const locations = ['root', 'source', 'counts', 'filters', 'outcome'] as const;
  for (const location of locations) {
    for (const key of ['unknown', '__proto__', 'constructor']) {
      const value = document();
      const target = location === 'root' ? value : location === 'outcome' ? value.outcomes[0]! : value[location];
      Object.defineProperty(target, key, { value: 'private-data', enumerable: true });
      assert.deepEqual(read(value), { ok: false, code: 'INVALID_DOCUMENT' }, `${location}/${key}`);
    }
    const value = document();
    const target = location === 'root' ? value : location === 'outcome' ? value.outcomes[0]! : value[location];
    delete (target as unknown as Record<string, unknown>)[Object.keys(target)[0]!];
    assert.deepEqual(read(value), { ok: false, code: 'INVALID_DOCUMENT' }, `missing ${location}`);
  }
});

test('schema versions and object/array boundaries are strict', () => {
  for (const value of [null, [], true, 1, 'document']) assert.deepEqual(read(value), { ok: false, code: 'INVALID_DOCUMENT' });
  for (const version of [0, 3, '1', null, true]) {
    const value = { ...document(), schemaVersion: version };
    assert.deepEqual(read(value), { ok: false, code: 'INVALID_DOCUMENT' });
  }
  for (const key of ['source', 'counts', 'filters', 'outcomes'] as const) {
    const value: Record<string, unknown> = { ...document() }; value[key] = key === 'outcomes' ? {} : [];
    assert.deepEqual(read(value), { ok: false, code: 'INVALID_DOCUMENT' });
  }
  const badRow: Record<string, unknown> = { ...document(), outcomes: [[]] };
  badRow.counts = { reportedInputCount: 1, availableOutcomes: 1, matchedOutcomes: 1 };
  assert.deepEqual(read(badRow), { ok: false, code: 'INVALID_DOCUMENT' });
  const version1 = document(); (version1.filters as unknown as Record<string, unknown>).sensorId = 'sensor-a';
  assert.deepEqual(read(version1), { ok: false, code: 'INVALID_DOCUMENT' });
  const version2 = { ...document(), schemaVersion: 2 };
  assert.deepEqual(read(version2), { ok: false, code: 'INVALID_DOCUMENT' });
});

test('source fields require strings, recognized modes and nullable parseable metadata timestamps', () => {
  for (const [key, invalid] of [['runId', null], ['runId', 7], ['mode', 'offline'], ['mode', null],
    ['observedAt', 'invalid-time'], ['observedAt', 0], ['capturedAt', ''], ['capturedAt', {}]] as const) {
    const value = document(); (value.source as unknown as Record<string, unknown>)[key] = invalid;
    assert.deepEqual(read(value), { ok: false, code: 'INVALID_DOCUMENT' }, key);
  }
});

test('counts must be nonnegative safe integers with matched length and available coverage only', () => {
  for (const key of ['reportedInputCount', 'availableOutcomes', 'matchedOutcomes'] as const)
    for (const invalid of [-1, 0.5, Number.MAX_SAFE_INTEGER + 1, '2', null]) {
      const value = document(); (value.counts as unknown as Record<string, unknown>)[key] = invalid;
      assert.deepEqual(read(value), { ok: false, code: 'INVALID_DOCUMENT' }, key);
    }
  for (const counts of [{ reportedInputCount: 12, availableOutcomes: 2, matchedOutcomes: 1 },
    { reportedInputCount: 12, availableOutcomes: 1, matchedOutcomes: 2 }])
    assert.deepEqual(read({ ...document(), counts }), { ok: false, code: 'INVALID_DOCUMENT' });
});

test('row fields require exact primitive types, finite values and recognized statuses but preserve invalid event times', () => {
  for (const [key, invalid] of [['sequence', -1], ['sequence', 0.2], ['sequence', Number.MAX_SAFE_INTEGER + 1],
    ['eventId', null], ['sensorId', 1], ['eventTime', null], ['reason', []], ['value', '1'], ['value', true],
    ['status', 'ALL'], ['status', 'success'], ['status', null]] as const) {
    const value = document(); (value.outcomes[0] as unknown as Record<string, unknown>)[key] = invalid;
    assert.deepEqual(read(value), { ok: false, code: 'INVALID_DOCUMENT' }, key);
  }
  const text = JSON.stringify(document()).replace('"value":1', '"value":1e999');
  assert.deepEqual(readOfflineEventBytes(encoder.encode(text)), { ok: false, code: 'INVALID_DOCUMENT' });
  for (const status of ['SUCCESS', 'FAILED', 'DUPLICATE', 'PENDING'] as const)
    accepted(createEventExport(input({ outcomes: [row(0, { status, eventTime: 'invalid-time' })] })));
});

test('filter types are strict and each declared AND condition must include every saved row', () => {
  for (const [key, invalid] of [['status', 'all'], ['status', null], ['query', null], ['reason', 0], ['reason', []]] as const) {
    const value = document(); (value.filters as unknown as Record<string, unknown>)[key] = invalid;
    assert.deepEqual(read(value), { ok: false, code: 'INVALID_DOCUMENT' }, key);
  }
  for (const change of [{ status: 'FAILED' }, { query: 'not-present' }, { reason: '' }]) {
    const value = document(); Object.assign(value.filters, change);
    assert.deepEqual(read(value), { ok: false, code: 'FILTER_MISMATCH' });
  }
  const exact = createEventExport(input({ filters: { status: 'ALL', query: '', reason: null, sensorId: 'sensor-a' } }));
  for (const invalid of [null, 1, true]) {
    const value = structuredClone(exact); (value.filters as unknown as Record<string, unknown>).sensorId = invalid;
    assert.deepEqual(read(value), { ok: false, code: 'INVALID_DOCUMENT' });
  }
  const wrongCase = structuredClone(exact); (wrongCase.filters as unknown as Record<string, unknown>).sensorId = 'Sensor-A';
  assert.deepEqual(read(wrongCase), { ok: false, code: 'FILTER_MISMATCH' });
  const wrongSpace = structuredClone(exact); (wrongSpace.filters as unknown as Record<string, unknown>).sensorId = ' sensor-a ';
  assert.deepEqual(read(wrongSpace), { ok: false, code: 'FILTER_MISMATCH' });
  accepted(createEventExport(input({ filters: { status: 'ALL', query: ' REPEAT-ID ', reason: null } })));
});

test('async file reader returns the raw file name, actual byte length and accepted document without network work', async () => {
  const value = document(), bytes = encoder.encode(eventExportJson(value)); let reads = 0;
  const result = await readOfflineEventFile({ name: '../<file>.json', size: bytes.byteLength,
    async arrayBuffer() { reads++; return bytes.buffer; } });
  assert.deepEqual(result, { ok: true, file: { name: '../<file>.json', byteLength: bytes.byteLength, document: value } });
  assert.equal(reads, 1);
});

test('oversized declared files are not read and undersized declarations cannot bypass the actual byte limit', async () => {
  let reads = 0;
  const oversized = { name: 'large.json', size: MAX_OFFLINE_FILE_BYTES + 1,
    async arrayBuffer() { reads++; throw new Error('must-not-read'); } };
  assert.deepEqual(await readOfflineEventFile(oversized), { ok: false, code: 'FILE_TOO_LARGE' });
  assert.equal(reads, 0);
  const mismatch = { name: 'small.json', size: 1,
    async arrayBuffer() { reads++; return new ArrayBuffer(MAX_OFFLINE_FILE_BYTES + 1); } };
  assert.deepEqual(await readOfflineEventFile(mismatch), { ok: false, code: 'FILE_TOO_LARGE' });
  assert.equal(reads, 1);
});

test('read failures return only a finite code and validation errors remain distinct', async () => {
  const failed = await readOfflineEventFile({ name: 'secret-name', size: 1,
    async arrayBuffer() { throw new Error('secret-token-do-not-echo'); } });
  assert.deepEqual(failed, { ok: false, code: 'READ_FAILED' });
  const malformed = await readOfflineEventFile({ name: 'bad.json', size: 1,
    async arrayBuffer() { return encoder.encode('{').buffer; } });
  assert.deepEqual(malformed, { ok: false, code: 'INVALID_JSON' });
});
