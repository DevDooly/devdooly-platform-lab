/** A recorded, synthetic trial. This module cannot execute SQL or mutate the Lab. */
export const bronzeFixtureSha256 = '39ba10d8c47dce790f3ccc9c9134fea593d6de31f1f3a7992ca61d9f554da3b5';
export const bronzeFirstRowsSha256 = '411dc42e274b9c0e73e08b1725fd08fcc75cc3217c1f10d3102f79c8319b48ec';
export const bronzeFullRowsSha256 = '1c31bc6976083c78549cb0a6b1a48517d16e5bd683da474d75bea1756f1d8514';
export type BronzeSnapshot = {
  id: string; parentId: string | null; operation: 'append'; addedRows: 6; totalRows: 6 | 12;
  distinctEventIds: 5 | 10; sensorA: 5 | 8; sensorB: 1 | 4;
};
export type IcebergDataflow = {
  schemaVersion: 1; scope: 'ISOLATED_SYNTHETIC_ICEBERG_JDBC'; recordedAt: string;
  applicationSourceCommit: string; gitopsRevision: string;
  fixture: { inputRows: 12; bytes: 1100; sha256: string; firstRowsSha256: string; fullRowsSha256: string };
  engines: { trino: '483'; postgresql: '17.11'; catalog: 'JDBC_V1'; tableFormat: 'ICEBERG'; trinoJava: '25.0.3' };
  snapshots: [BronzeSnapshot, BronzeSnapshot];
  checks: {
    nativeWriteRead: true; timeTravel: true; trinoNormalRestart: true; postgresSameProcess: true;
    queryResultsUnchanged: true; workloadsStopped: true; originalJobsPreserved: 8;
    originalWholeObjectsVerified: 24; originalObjectDeletes: 0;
  };
  retention: { ownPvcCount: 2; policy: 'Retain'; warehouseRetained: true };
  window: { firstAttemptPassed: false; explicitFreshWindow: true };
  proofSha256: { baseline: string; prepare: string; capability: string; catalog: string; query: string; restart: string; stop: string; final: string };
};

const object = (value: unknown): value is Record<string, unknown> => value !== null && typeof value === 'object' && !Array.isArray(value);
const exact = (value: Record<string, unknown>, fields: readonly string[]) => fields.length === Object.keys(value).length && fields.every(key => Object.hasOwn(value, key));
const sha = (value: unknown): value is string => typeof value === 'string' && /^[a-f0-9]{64}$/.test(value);
const commit = (value: unknown) => typeof value === 'string' && /^[a-f0-9]{40}$/.test(value);
const fixed = (value: unknown, expected: Record<string, unknown>) => object(value) && exact(value, Object.keys(expected)) && Object.entries(expected).every(([key, item]) => value[key] === item);
function snapshotId(value: unknown): value is string {
  // Iceberg IDs are positive signed BIGINTs: never round them through JS Number.
  return typeof value === 'string' && /^[1-9][0-9]{0,18}$/.test(value) && BigInt(value) <= 9_223_372_036_854_775_807n;
}
function utc(value: unknown): value is string {
  if (typeof value !== 'string' || !/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.[0-9]{1,9})?Z$/.test(value)) return false;
  const date = new Date(value);
  return Number.isFinite(date.getTime()) && date.toISOString().slice(0, 19) === value.slice(0, 19);
}

/** Unknown/private fields, incomplete proofs and inconsistent parent chains fail closed. */
export function parseIcebergDataflow(value: unknown): IcebergDataflow | null {
  if (!object(value) || !exact(value, ['schemaVersion', 'scope', 'recordedAt', 'applicationSourceCommit', 'gitopsRevision', 'fixture', 'engines', 'snapshots', 'checks', 'retention', 'window', 'proofSha256'])
      || value.schemaVersion !== 1 || value.scope !== 'ISOLATED_SYNTHETIC_ICEBERG_JDBC' || !utc(value.recordedAt)
      || !commit(value.applicationSourceCommit) || !commit(value.gitopsRevision)) return null;
  const fixture = value.fixture;
  if (!object(fixture) || !exact(fixture, ['inputRows', 'bytes', 'sha256', 'firstRowsSha256', 'fullRowsSha256'])
      || fixture.inputRows !== 12 || fixture.bytes !== 1100 || fixture.sha256 !== bronzeFixtureSha256
      || fixture.firstRowsSha256 !== bronzeFirstRowsSha256 || fixture.fullRowsSha256 !== bronzeFullRowsSha256) return null;
  if (!fixed(value.engines, { trino: '483', postgresql: '17.11', catalog: 'JDBC_V1', tableFormat: 'ICEBERG', trinoJava: '25.0.3' })
      || !fixed(value.checks, { nativeWriteRead: true, timeTravel: true, trinoNormalRestart: true, postgresSameProcess: true,
        queryResultsUnchanged: true, workloadsStopped: true, originalJobsPreserved: 8, originalWholeObjectsVerified: 24, originalObjectDeletes: 0 })
      || !fixed(value.retention, { ownPvcCount: 2, policy: 'Retain', warehouseRetained: true })
      || !fixed(value.window, { firstAttemptPassed: false, explicitFreshWindow: true })) return null;
  const snapshots = value.snapshots;
  if (!Array.isArray(snapshots) || snapshots.length !== 2) return null;
  for (let index = 0; index < 2; index++) {
    const row: unknown = snapshots[index];
    if (!object(row) || !exact(row, ['id', 'parentId', 'operation', 'addedRows', 'totalRows', 'distinctEventIds', 'sensorA', 'sensorB'])
        || !snapshotId(row.id) || row.operation !== 'append' || row.addedRows !== 6
        || row.totalRows !== (index === 0 ? 6 : 12) || row.distinctEventIds !== (index === 0 ? 5 : 10)
        || row.sensorA !== (index === 0 ? 5 : 8) || row.sensorB !== (index === 0 ? 1 : 4)) return null;
    if (index === 0 ? row.parentId !== null : row.parentId !== snapshots[0].id || row.id === snapshots[0].id) return null;
  }
  if (!object(value.proofSha256) || !exact(value.proofSha256, ['baseline', 'prepare', 'capability', 'catalog', 'query', 'restart', 'stop', 'final'])
      || !Object.values(value.proofSha256).every(sha)) return null;
  return value as unknown as IcebergDataflow;
}
