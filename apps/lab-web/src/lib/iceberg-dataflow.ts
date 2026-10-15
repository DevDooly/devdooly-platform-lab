/** Recorded synthetic evidence only. This module cannot execute SQL or mutate the Lab. */
export const bronzeFixtureSha256 = '39ba10d8c47dce790f3ccc9c9134fea593d6de31f1f3a7992ca61d9f554da3b5';
export const bronzeFirstRowsSha256 = '411dc42e274b9c0e73e08b1725fd08fcc75cc3217c1f10d3102f79c8319b48ec';
export const bronzeFullRowsSha256 = '1c31bc6976083c78549cb0a6b1a48517d16e5bd683da474d75bea1756f1d8514';
export const initialEmptySnapshotId = '2998009981322509692';
export type BronzeSnapshot = {
  id: string; parentId: string | null; operation: 'append'; phase: 'INITIAL_EMPTY' | 'DATA_APPEND';
  addedRecordsSummary: null | 6; totalRows: 0 | 6 | 12; distinctEventIds: 0 | 5 | 10; sensorA: 0 | 5 | 8; sensorB: 0 | 1 | 4;
};
type ExecutorSources = Record<'baseline7.py' | 'network_control7.py' | 'resume_sql7.py' | 'phase6_continuation_attempt7.py', string>;
export type IcebergDataflow = {
  schemaVersion: 2; scope: 'ISOLATED_SYNTHETIC_ICEBERG_JDBC'; recordedAt: string;
  applicationSourceCommit: string; gitopsRevision: string;
  provenance: {
    privateExecutorCommit: null; executorSourceSha256: ExecutorSources;
    adoptedPrepareAttempt: 3; adoptedCapabilityAttempt: 3; adoptedDdlAttempt: 6; nativeAttempt: 7;
    adoptedDdlDiagnosticSha256: string;
    priorSixthProofSha256: Record<'baseline' | 'catalog' | 'query' | 'stop' | 'supervisor', string>;
    priorSixthQueryPassed: false; priorSixthSupervisorPassed: false;
    snapshotInspectionSqlAdjusted: true; frozenSqlPlanSourceChanged: false;
  };
  fixture: { inputRows: 12; bytes: 1100; sha256: string; firstRowsSha256: string; fullRowsSha256: string };
  engines: { trino: '483'; postgresql: '17.11'; catalog: 'JDBC_V1'; tableFormat: 'ICEBERG'; trinoJava: '25.0.3' };
  snapshots: [BronzeSnapshot, BronzeSnapshot, BronzeSnapshot];
  checks: {
    nativeWriteRead: true; timeTravel: true; trinoNormalRestart: true; postgresSameProcess: true;
    queryResultsUnchanged: true; workloadsStopped: true; originalJobsPreserved: 8;
    originalWholeObjectsVerified: 24; originalObjectDeletes: 0;
  };
  retention: { ownPvcCount: 2; policy: 'Retain'; warehouseRetained: true };
  window: { firstAttemptPassed: false; explicitFreshWindow: true; completedDdlAdopted: true;
    initialEmptySnapshots: 1; dataAppendSnapshots: 2; totalSnapshots: 3 };
  proofSha256: Record<'baseline' | 'prepare' | 'capability' | 'catalog' | 'query' | 'restart' | 'stop' | 'final' | 'supervisor', string>;
};

const object = (value: unknown): value is Record<string, unknown> => value !== null && typeof value === 'object' && !Array.isArray(value);
const exact = (value: Record<string, unknown>, fields: readonly string[]) => fields.length === Object.keys(value).length && fields.every(key => Object.hasOwn(value, key));
const sha = (value: unknown): value is string => typeof value === 'string' && /^[a-f0-9]{64}$/.test(value);
const commit = (value: unknown) => typeof value === 'string' && /^[a-f0-9]{40}$/.test(value);
const fixed = (value: unknown, expected: Record<string, unknown>) => object(value) && exact(value, Object.keys(expected)) && Object.entries(expected).every(([key, item]) => value[key] === item);
const hashes = (value: unknown, fields: readonly string[]) => object(value) && exact(value, fields) && Object.values(value).every(sha);
function snapshotId(value: unknown): value is string {
  return typeof value === 'string' && /^[1-9][0-9]{0,18}$/.test(value) && BigInt(value) <= 9_223_372_036_854_775_807n;
}
function utc(value: unknown): value is string {
  if (typeof value !== 'string' || !/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.[0-9]{1,9})?Z$/.test(value)) return false;
  const date = new Date(value);
  return Number.isFinite(date.getTime()) && date.toISOString().slice(0, 19) === value.slice(0, 19);
}

/** Schema1/partial/private records remain unavailable; they are never reinterpreted. */
export function parseIcebergDataflow(value: unknown): IcebergDataflow | null {
  if (!object(value) || !exact(value, ['schemaVersion', 'scope', 'recordedAt', 'applicationSourceCommit', 'gitopsRevision', 'provenance', 'fixture', 'engines', 'snapshots', 'checks', 'retention', 'window', 'proofSha256'])
      || value.schemaVersion !== 2 || value.scope !== 'ISOLATED_SYNTHETIC_ICEBERG_JDBC' || !utc(value.recordedAt)
      || !commit(value.applicationSourceCommit) || !commit(value.gitopsRevision)) return null;
  const fixture = value.fixture;
  if (!fixed(fixture, { inputRows: 12, bytes: 1100, sha256: bronzeFixtureSha256,
    firstRowsSha256: bronzeFirstRowsSha256, fullRowsSha256: bronzeFullRowsSha256 })) return null;
  if (!fixed(value.engines, { trino: '483', postgresql: '17.11', catalog: 'JDBC_V1', tableFormat: 'ICEBERG', trinoJava: '25.0.3' })
      || !fixed(value.checks, { nativeWriteRead: true, timeTravel: true, trinoNormalRestart: true, postgresSameProcess: true,
        queryResultsUnchanged: true, workloadsStopped: true, originalJobsPreserved: 8, originalWholeObjectsVerified: 24, originalObjectDeletes: 0 })
      || !fixed(value.retention, { ownPvcCount: 2, policy: 'Retain', warehouseRetained: true })
      || !fixed(value.window, { firstAttemptPassed: false, explicitFreshWindow: true, completedDdlAdopted: true,
        initialEmptySnapshots: 1, dataAppendSnapshots: 2, totalSnapshots: 3 })) return null;
  const provenance = value.provenance;
  if (!object(provenance) || !exact(provenance, ['privateExecutorCommit', 'executorSourceSha256', 'adoptedPrepareAttempt', 'adoptedCapabilityAttempt',
    'adoptedDdlAttempt', 'nativeAttempt', 'adoptedDdlDiagnosticSha256', 'priorSixthProofSha256', 'priorSixthQueryPassed',
    'priorSixthSupervisorPassed', 'snapshotInspectionSqlAdjusted', 'frozenSqlPlanSourceChanged'])
      || provenance.privateExecutorCommit !== null || provenance.adoptedPrepareAttempt !== 3 || provenance.adoptedCapabilityAttempt !== 3
      || provenance.adoptedDdlAttempt !== 6 || provenance.nativeAttempt !== 7 || !sha(provenance.adoptedDdlDiagnosticSha256)
      || provenance.priorSixthQueryPassed !== false || provenance.priorSixthSupervisorPassed !== false
      || provenance.snapshotInspectionSqlAdjusted !== true || provenance.frozenSqlPlanSourceChanged !== false
      || !hashes(provenance.executorSourceSha256, ['baseline7.py', 'network_control7.py', 'resume_sql7.py', 'phase6_continuation_attempt7.py'])
      || !hashes(provenance.priorSixthProofSha256, ['baseline', 'catalog', 'query', 'stop', 'supervisor'])) return null;
  const snapshots = value.snapshots;
  if (!Array.isArray(snapshots) || snapshots.length !== 3) return null;
  const ids = new Set<string>();
  for (let index = 0; index < 3; index++) {
    const row: unknown = snapshots[index];
    if (!object(row) || !exact(row, ['id', 'parentId', 'operation', 'phase', 'addedRecordsSummary', 'totalRows', 'distinctEventIds', 'sensorA', 'sensorB'])
        || !snapshotId(row.id) || ids.has(row.id) || row.operation !== 'append'
        || row.phase !== (index === 0 ? 'INITIAL_EMPTY' : 'DATA_APPEND')
        || row.addedRecordsSummary !== (index === 0 ? null : 6) || row.totalRows !== index * 6
        || row.distinctEventIds !== [0, 5, 10][index] || row.sensorA !== [0, 5, 8][index] || row.sensorB !== [0, 1, 4][index]) return null;
    if (index === 0 ? row.parentId !== null || row.id !== initialEmptySnapshotId : row.parentId !== snapshots[index - 1].id) return null;
    ids.add(row.id);
  }
  if (!hashes(value.proofSha256, ['baseline', 'prepare', 'capability', 'catalog', 'query', 'restart', 'stop', 'final', 'supervisor'])) return null;
  return value as unknown as IcebergDataflow;
}
