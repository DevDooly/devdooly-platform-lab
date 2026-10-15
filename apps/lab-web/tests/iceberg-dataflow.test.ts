import assert from 'node:assert/strict';
import test from 'node:test';
import { bronzeFixtureSha256, bronzeFirstRowsSha256, bronzeFullRowsSha256, parseIcebergDataflow } from '../src/lib/iceberg-dataflow.ts';

// Synthetic validator fixture only. Never emitted as a public/runtime success record.
function sample() {
  return {
    schemaVersion: 1, scope: 'ISOLATED_SYNTHETIC_ICEBERG_JDBC', recordedAt: '2026-10-15T16:00:00.123456789Z',
    applicationSourceCommit: 'a'.repeat(40), gitopsRevision: 'b'.repeat(40),
    fixture: { inputRows: 12, bytes: 1100, sha256: bronzeFixtureSha256, firstRowsSha256: bronzeFirstRowsSha256, fullRowsSha256: bronzeFullRowsSha256 },
    engines: { trino: '483', postgresql: '17.11', catalog: 'JDBC_V1', tableFormat: 'ICEBERG', trinoJava: '25.0.3' },
    snapshots: [
      { id: '9007199254740993', parentId: null as string | null, operation: 'append', addedRows: 6, totalRows: 6, distinctEventIds: 5, sensorA: 5, sensorB: 1 },
      { id: '9223372036854775807', parentId: '9007199254740993', operation: 'append', addedRows: 6, totalRows: 12, distinctEventIds: 10, sensorA: 8, sensorB: 4 },
    ],
    checks: { nativeWriteRead: true, timeTravel: true, trinoNormalRestart: true, postgresSameProcess: true, queryResultsUnchanged: true,
      workloadsStopped: true, originalJobsPreserved: 8, originalWholeObjectsVerified: 24, originalObjectDeletes: 0 },
    retention: { ownPvcCount: 2, policy: 'Retain', warehouseRetained: true },
    window: { firstAttemptPassed: false, explicitFreshWindow: true },
    proofSha256: Object.fromEntries(['baseline', 'prepare', 'capability', 'catalog', 'query', 'restart', 'stop', 'final'].map((key, index) => [key, String(index).repeat(64)])),
  };
}

test('accepts complete recorded evidence and keeps BIGINT snapshot IDs lossless', () => {
  const evidence = parseIcebergDataflow(sample());
  assert.ok(evidence); assert.equal(evidence.snapshots[0].id, '9007199254740993');
  assert.equal(evidence.snapshots[1].id, '9223372036854775807');
});
test('missing or partial evidence never becomes a successful record', () => {
  assert.equal(parseIcebergDataflow(undefined), null); assert.equal(parseIcebergDataflow(null), null);
  const partial = sample(); partial.snapshots.pop(); assert.equal(parseIcebergDataflow(partial), null);
  const missing = sample(); delete (missing.proofSha256 as Record<string, string>).final; assert.equal(parseIcebergDataflow(missing), null);
});
test('rejects snapshot rounding, out-of-range IDs, duplicate IDs and broken parent chains', () => {
  for (const id of ['0', '01', '-1', '9223372036854775808', 9007199254740993]) {
    const evidence = sample(); Object.assign(evidence.snapshots[0], { id }); assert.equal(parseIcebergDataflow(evidence), null);
  }
  const wrongParent = sample(); wrongParent.snapshots[1].parentId = '7'; assert.equal(parseIcebergDataflow(wrongParent), null);
  const duplicate = sample(); duplicate.snapshots[1].id = duplicate.snapshots[0].id; assert.equal(parseIcebergDataflow(duplicate), null);
});
test('rejects private or unknown fields at every public object boundary', () => {
  const changes = [
    (value: ReturnType<typeof sample>) => Object.assign(value, { bucket: 'not-public' }),
    (value: ReturnType<typeof sample>) => Object.assign(value.fixture, { objectKey: 'not-public' }),
    (value: ReturnType<typeof sample>) => Object.assign(value.engines, { host: 'not-public' }),
    (value: ReturnType<typeof sample>) => Object.assign(value.snapshots[0], { path: 'not-public' }),
    (value: ReturnType<typeof sample>) => Object.assign(value.checks, { logs: 'not-public' }),
    (value: ReturnType<typeof sample>) => Object.assign(value.proofSha256, { secret: 'not-public' }),
  ];
  for (const change of changes) { const value = sample(); change(value); assert.equal(parseIcebergDataflow(value), null); }
});
test('rejects incomplete native restart/stop and falsely rewriting the failed first window', () => {
  for (const field of ['nativeWriteRead', 'timeTravel', 'trinoNormalRestart', 'postgresSameProcess', 'queryResultsUnchanged', 'workloadsStopped']) {
    const value = sample(); Object.assign(value.checks, { [field]: false }); assert.equal(parseIcebergDataflow(value), null);
  }
  const reset = sample(); reset.window.firstAttemptPassed = true; assert.equal(parseIcebergDataflow(reset), null);
  const deletion = sample(); deletion.checks.originalObjectDeletes = 1; assert.equal(parseIcebergDataflow(deletion), null);
});
test('raw Bronze counts and fingerprints cannot be replaced by processed ETL outcomes', () => {
  const silver = sample(); silver.snapshots[1].totalRows = 7; assert.equal(parseIcebergDataflow(silver), null);
  const hash = sample(); hash.fixture.fullRowsSha256 = 'a'.repeat(64); assert.equal(parseIcebergDataflow(hash), null);
  const sensor = sample(); sensor.snapshots[1].sensorA = 7; assert.equal(parseIcebergDataflow(sensor), null);
});
test('rejects invalid dates/source hashes and malformed proof hashes', () => {
  for (const recordedAt of ['2026-02-30T16:00:00Z', '2026-10-15T16:00:00+09:00', '2026-10-15T16:00:00.1234567890Z', 'now']) {
    assert.equal(parseIcebergDataflow({ ...sample(), recordedAt }), null);
  }
  assert.equal(parseIcebergDataflow({ ...sample(), applicationSourceCommit: 'unknown' }), null);
  const hash = sample(); hash.proofSha256.final = 'secret'; assert.equal(parseIcebergDataflow(hash), null);
});
