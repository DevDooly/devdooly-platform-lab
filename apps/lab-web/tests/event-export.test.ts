import assert from 'node:assert/strict';
import test from 'node:test';
import type { Outcome } from '../src/lib/api.ts';
import { createEventExport, eventExportCsv, eventExportFilename, eventExportJson, type EventExportInput } from '../src/lib/event-export.ts';

const outcome = (sequence: number, fields: Partial<Outcome> = {}): Outcome => ({ sequence,
  eventId: 'repeat-id', sensorId: 'sensor-a', eventTime: 'raw-time', value: 42,
  status: 'SUCCESS', reason: 'ACCEPTED', ...fields });
const input = (fields: Partial<EventExportInput> = {}): EventExportInput => ({
  runId: 'run-example', mode: 'recorded', observedAt: '2026-10-24T08:01:02.123Z',
  capturedAt: '2026-10-24T08:05:00Z', reportedInputCount: 12,
  filters: { status: 'ALL', query: '', reason: null }, outcomes: [], ...fields,
});

/** Read the quoted RFC 4180 records, including embedded line breaks. */
function readCsv(text: string): string[][] {
  assert.ok(text.startsWith('\uFEFF')); assert.ok(text.endsWith('\r\n'));
  const rows: string[][] = []; let row: string[] = [], cell = '', quoted = false;
  const body = text.slice(1);
  for (let i = 0; i < body.length; i++) {
    const character = body[i];
    if (character === '"') {
      if (quoted && body[i + 1] === '"') { cell += '"'; i++; }
      else quoted = !quoted;
    } else if (!quoted && character === ',') { row.push(cell); cell = ''; }
    else if (!quoted && character === '\r' && body[i + 1] === '\n') {
      row.push(cell); rows.push(row); row = []; cell = ''; i++;
    } else cell += character;
  }
  assert.equal(quoted, false); assert.deepEqual(row, []); assert.equal(cell, '');
  return rows;
}

test('export snapshots the same AND-filtered rows, source and raw conditions without leaking extra fields', () => {
  const extra = { ...outcome(9), privateDebug: 'must-not-export' };
  const rows = [outcome(3, { value: null, reason: '', status: 'FAILED', eventTime: 'invalid-time' }),
    outcome(1), extra, outcome(4, { sensorId: 'sensor-b' })];
  const filters = { status: 'ALL' as const, query: '  REPEAT-ID  ', reason: null };
  const request = input({ outcomes: rows, filters });
  const before = structuredClone(request);
  rows.forEach(Object.freeze); Object.freeze(rows); Object.freeze(filters); Object.freeze(request);
  const document = createEventExport(request);
  assert.deepEqual(document.source, { runId: request.runId, mode: 'recorded',
    observedAt: request.observedAt, capturedAt: request.capturedAt });
  assert.deepEqual(document.filters, filters);
  assert.deepEqual(document.counts, { reportedInputCount: 12, availableOutcomes: 4, matchedOutcomes: 4 });
  assert.deepEqual(document.outcomes.map(row => row.sequence), [3, 1, 9, 4]);
  assert.equal(document.outcomes[0]!.value, null); assert.equal(document.outcomes[0]!.eventTime, 'invalid-time');
  assert.deepEqual(Object.keys(document.outcomes[2]!), ['sequence', 'eventId', 'sensorId', 'eventTime', 'value', 'status', 'reason']);
  assert.equal('privateDebug' in document.outcomes[2]!, false);
  assert.notEqual(document.filters, filters); assert.notEqual(document.outcomes[0], rows[0]);
  assert.deepEqual(request, before);
  const narrowed = createEventExport(input({ outcomes: rows, filters: { status: 'FAILED', query: 'sensor-a', reason: '' } }));
  assert.deepEqual(narrowed.outcomes.map(row => row.sequence), [3]);
  assert.deepEqual(narrowed.counts, { reportedInputCount: 12, availableOutcomes: 4, matchedOutcomes: 1 });
});

test('zero matches keep context metadata and distinguish all reasons from an empty raw reason', () => {
  const noMatches = createEventExport(input({ mode: 'fixture', observedAt: null, capturedAt: null,
    outcomes: [outcome(1)], filters: { status: 'FAILED', query: 'No match ', reason: '' } }));
  assert.deepEqual(noMatches.outcomes, []);
  assert.deepEqual(noMatches.counts, { reportedInputCount: 12, availableOutcomes: 1, matchedOutcomes: 0 });
  const rows = readCsv(eventExportCsv(noMatches));
  assert.equal(rows.length, 2); assert.ok(rows.every(row => row.length === 21));
  assert.deepEqual(rows[1], ['context', '1', 'run-example', 'fixture', '', '', '12', '1', '0', 'FAILED',
    'No match ', 'false', '', '', '', '', '', '', '', '', '']);
  const allReasons = readCsv(eventExportCsv(createEventExport(input())));
  assert.equal(allReasons[1]![11], 'true'); assert.equal(allReasons[1]![12], '');
});

test('CSV preserves raw quotes, commas and embedded newlines while protecting formula-like strings only', () => {
  const rows = [outcome(1, { eventId: '=SUM(1,2)', sensorId: '  +sensor', eventTime: '"quoted",\r\nnext', value: -1, reason: '-1' }),
    outcome(2, { eventId: '@id', sensorId: '\tvalue', value: null, reason: '\nreason' }),
    outcome(3, { eventId: 'plain', sensorId: 'sensor', reason: 'future' })];
  const document = createEventExport(input({ runId: '-run', outcomes: rows,
    filters: { status: 'ALL', query: ' ', reason: null } }));
  const records = readCsv(eventExportCsv(document));
  assert.ok(records.every(row => row.length === 21));
  assert.equal(records[2]![2], "'-run"); assert.equal(records[2]![14], "'=SUM(1,2)");
  assert.equal(records[2]![15], "'  +sensor"); assert.equal(records[2]![16], '"quoted",\r\nnext');
  assert.equal(records[2]![17], '-1'); assert.equal(records[2]![18], 'false'); assert.equal(records[2]![20], "'-1");
  assert.equal(records[3]![14], "'@id"); assert.equal(records[3]![15], "'\tvalue");
  assert.equal(records[3]![17], ''); assert.equal(records[3]![18], 'true'); assert.equal(records[3]![20], "'\nreason");
  assert.equal(records[4]![14], 'plain');
  const json = eventExportJson(document);
  assert.ok(json.endsWith('\n')); assert.match(json, /\n  "schemaVersion": 1,/);
  assert.deepEqual(JSON.parse(json), document);
  assert.equal(JSON.parse(json).outcomes[0].eventId, '=SUM(1,2)');
});

test('filenames retain a static source prefix and bound run IDs to a path-free name', () => {
  assert.equal(eventExportFilename(createEventExport(input()), 'json'), 'lab-events-recorded-run-example.json');
  assert.equal(eventExportFilename(createEventExport(input({ mode: 'live', runId: '../../a\\b:\n?*\"<>|  ' })), 'csv'),
    'lab-events-live-a-b.csv');
  assert.equal(eventExportFilename(createEventExport(input({ mode: 'fixture', runId: '../\\' })), 'json'),
    'lab-events-fixture-run.json');
  const name = eventExportFilename(createEventExport(input({ runId: 'a'.repeat(300) })), 'csv');
  assert.equal(name, 'lab-events-recorded-' + 'a'.repeat(80) + '.csv');
});

test('no exact sensor condition preserves version 1 JSON and CSV bytes', () => {
  const expectedJson = `{
  "schemaVersion": 1,
  "source": {
    "runId": "run-example",
    "mode": "recorded",
    "observedAt": "2026-10-24T08:01:02.123Z",
    "capturedAt": "2026-10-24T08:05:00Z"
  },
  "filters": {
    "status": "ALL",
    "query": "",
    "reason": null
  },
  "counts": {
    "reportedInputCount": 12,
    "availableOutcomes": 1,
    "matchedOutcomes": 1
  },
  "outcomes": [
    {
      "sequence": 1,
      "eventId": "repeat-id",
      "sensorId": "sensor-a",
      "eventTime": "raw-time",
      "value": 42,
      "status": "SUCCESS",
      "reason": "ACCEPTED"
    }
  ]
}
`;
  const expectedCsv = '\uFEFF' + [
    '"recordType","schemaVersion","runId","sourceMode","observedAt","capturedAt","reportedInputCount","availableOutcomes","matchedOutcomes","filterStatus","filterQuery","filterReasonIsAll","filterReason","sequence","eventId","sensorId","eventTime","value","valueIsNull","status","reason"',
    '"context","1","run-example","recorded","2026-10-24T08:01:02.123Z","2026-10-24T08:05:00Z","12","1","1","ALL","","true","","","","","","","","",""',
    '"event","1","run-example","recorded","2026-10-24T08:01:02.123Z","2026-10-24T08:05:00Z","12","1","1","ALL","","true","","1","repeat-id","sensor-a","raw-time","42","false","SUCCESS","ACCEPTED"',
  ].join('\r\n') + '\r\n';
  for (const filters of [
    { status: 'ALL' as const, query: '', reason: null },
    { status: 'ALL' as const, query: '', reason: null, sensorId: undefined },
    { status: 'ALL' as const, query: '', reason: null, sensorId: null },
  ]) {
    const document = createEventExport(input({ outcomes: [outcome(1)], filters }));
    assert.equal(document.schemaVersion, 1);
    assert.deepEqual(Object.keys(document.filters), ['status', 'query', 'reason']);
    assert.equal(eventExportJson(document), expectedJson);
    assert.equal(eventExportCsv(document), expectedCsv);
  }
});

test('exact sensor exports use version 2 with raw empty, whitespace and case-sensitive IDs', () => {
  const rows = [outcome(8, { sensorId: '' }), outcome(2, { sensorId: ' sensor-a ' }),
    outcome(5, { sensorId: 'Sensor-A' }), outcome(1),
    outcome(4, { eventId: 'sensor-a', sensorId: 'sensor-ab' }), outcome(7)];
  for (const [sensorId, expected] of [['', [8]], [' sensor-a ', [2]], ['Sensor-A', [5]], ['sensor-a', [1, 7]]] as const) {
    const document = createEventExport(input({ outcomes: rows,
      filters: { status: 'ALL', query: '', reason: null, sensorId } }));
    assert.equal(document.schemaVersion, 2);
    if (document.schemaVersion !== 2) assert.fail('exact sensor must select version 2');
    assert.deepEqual(document.filters, { status: 'ALL', query: '', reason: null, sensorId });
    assert.deepEqual(document.outcomes.map(row => row.sequence), [...expected]);
    assert.deepEqual(document.counts, { reportedInputCount: 12, availableOutcomes: 6, matchedOutcomes: expected.length });
    assert.deepEqual(JSON.parse(eventExportJson(document)), document);
    const records = readCsv(eventExportCsv(document));
    assert.ok(records.every(row => row.length === 23));
    assert.deepEqual(records[0]!.slice(11, 17), ['filterReasonIsAll', 'filterReason',
      'filterSensorIsAll', 'filterSensorId', 'sequence', 'eventId']);
    assert.ok(records.slice(1).every(row => row[1] === '2' && row[13] === 'false' && row[14] === sensorId));
    assert.deepEqual(records.slice(2).map(row => Number(row[15])), [...expected]);
  }
});

test('exact sensor combines with every event condition and keeps version 2 context for zero matches', () => {
  const rows = [outcome(3, { sensorId: '', status: 'FAILED', reason: '' }),
    outcome(4, { sensorId: '', reason: '' }), outcome(9, { status: 'FAILED', reason: '' })];
  const request = input({ outcomes: rows,
    filters: { status: 'FAILED', query: ' REPEAT-ID ', reason: '', sensorId: '' } });
  const document = createEventExport(request);
  assert.deepEqual(document.outcomes.map(row => row.sequence), [3]);
  const noMatches = createEventExport({ ...request, filters: { ...request.filters, query: 'unknown' } });
  assert.equal(noMatches.schemaVersion, 2);
  assert.deepEqual(noMatches.outcomes, []);
  assert.deepEqual(noMatches.counts, { reportedInputCount: 12, availableOutcomes: 3, matchedOutcomes: 0 });
  const records = readCsv(eventExportCsv(noMatches));
  assert.equal(records.length, 2);
  assert.ok(records.every(row => row.length === 23));
  assert.deepEqual(records[1]!.slice(9), ['FAILED', 'unknown', 'false', '', 'false', '', '', '', '', '', '', '', '', '']);
  const json = JSON.parse(eventExportJson(noMatches));
  assert.equal(json.filters.sensorId, ''); assert.equal(json.filters.reason, '');
});

test('version 2 protects sensor CSV metadata and event cells while JSON and frozen input keep raw values', () => {
  const sensorId = ' =SUM(1,2)\r\n"sensor"';
  const row = { ...outcome(6, { sensorId, value: null }), privateDebug: 'do-not-export' };
  const filters = { status: 'ALL' as const, query: '', reason: null, sensorId, privateFilter: 'do-not-export' };
  const request = input({ outcomes: [row], filters });
  const before = structuredClone(request);
  Object.freeze(row); Object.freeze(request.outcomes); Object.freeze(filters); Object.freeze(request);
  const document = createEventExport(request);
  const json = JSON.parse(eventExportJson(document));
  assert.equal(json.filters.sensorId, sensorId);
  assert.equal(json.outcomes[0].sensorId, sensorId);
  assert.deepEqual(Object.keys(json.filters), ['status', 'query', 'reason', 'sensorId']);
  assert.deepEqual(Object.keys(json.outcomes[0]), ['sequence', 'eventId', 'sensorId', 'eventTime', 'value', 'status', 'reason']);
  const records = readCsv(eventExportCsv(document));
  assert.ok(records.every(record => record.length === 23));
  assert.equal(records[1]![14], "'" + sensorId);
  assert.equal(records[2]![14], "'" + sensorId);
  assert.equal(records[2]![17], "'" + sensorId);
  assert.equal(records[2]![19], ''); assert.equal(records[2]![20], 'true');
  assert.notEqual(document.outcomes[0], row); assert.notEqual(document.filters, filters);
  assert.deepEqual(request, before);
  assert.equal(eventExportFilename(document, 'csv'), 'lab-events-recorded-run-example.csv');
});
