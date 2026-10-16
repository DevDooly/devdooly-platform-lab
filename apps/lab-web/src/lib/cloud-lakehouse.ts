/** One audited historical Cloud result. This parser cannot execute SQL or workloads. */
export const cloudLakehouseSource = '223faf71c4fe9cadfd33b5ac5a95969cf3e2b04e';
export const cloudLakehouseRun = '38843953097';
export const cloudLakehouseJob = '116790713619';
export const cloudLakehouseSummary = '1271685e34712c96b7dacaf7e84e5f32ac52fb925875e262843002ee6ef3b78f';
export const cloudLakehouseRecordedAt = '2026-10-16T03:12:33.839802Z';
export const cloudLakehouseSnapshotIds = ['8225039569250402625', '2782914730281457112', '3908786707027856228'] as const;

export type CloudLakehouseRecord = {
  schemaVersion: 1; scope: 'RECORDED_ISOLATED_CLOUD_LAKEHOUSE_TRIAL'; status: 'PASSED'; recordedAt: string;
  run: { id: string; jobId: string; sourceCommit: string };
  artifact: { sha256: string; bytes: 3114; runtimeManifestSha256: string; producerSourceSha256: string };
  result: { rows: [6, 12, 12]; rowSha256: string; snapshotIds: [string, string, string];
    snapshotOperations: ['append', 'append', 'replace']; silverCounts: { rows: 12; success: 7; failure: 3; duplicate: 2; pending: 0 };
    bronzeDataFilesBefore: 2; bronzeDataFilesAfter: 1; compactionProcedureCalls: 1; trinoQueryCount: 10;
    preservedOldWarehouseObjects: 14; postTrinoWarehouseObjects: 20 };
  stop: { sparkNormalExitVerified: true; trinoExitCode: 143; trinoOomKilled: false; trinoStopRequestReturnedZero: true;
    trinoStopRequestedSeconds: 30; trinoSignalDeliveryDirectlyObserved: false; allOwnedContainersStopped: true;
    initializerStopped: true; enabledOomKillerRepresentationsVerified: true };
  limits: { workloadBudgetSeconds: 600; workloadElapsedMillis: 78955; buildAndPullExcluded: true; sparkCpu: 1;
    sparkMemoryBytes: 3221225472; sparkPids: 512; trinoMemoryBytes: 4294967296; plannedSequentialPeakMemoryBytes: 5368709120;
    requiredActualMemAvailableBytes: 7516192768; resourceLimitsAreConfiguration: true };
  exclusions: { miniPcContacted: false; kubernetesVerified: false; currentAvailabilityClaimed: false;
    productionSlaClaimed: false; automaticRetryPerformed: false; snapshotExpirationOrObjectGcPerformed: false };
};

const object = (value: unknown): value is Record<string, unknown> => value !== null && typeof value === 'object' && !Array.isArray(value);
const exact = (value: Record<string, unknown>, keys: readonly string[]) => Object.keys(value).length === keys.length && keys.every(key => Object.hasOwn(value, key));
const fixed = (value: unknown, expected: Record<string, unknown>) => object(value) && exact(value, Object.keys(expected)) && Object.entries(expected).every(([key, item]) => value[key] === item);
const tuple = (value: unknown, expected: readonly unknown[]) => Array.isArray(value) && value.length === expected.length && expected.every((item, index) => value[index] === item);
const snapshot = (value: unknown): value is string => typeof value === 'string' && /^[1-9][0-9]{0,18}$/.test(value) && BigInt(value) <= 9_223_372_036_854_775_807n;

/** Missing, failed, partial, relabelled and private records remain unverified. */
export function parseCloudLakehouse(value: unknown): CloudLakehouseRecord | null {
  if (!object(value) || !exact(value, ['schemaVersion', 'scope', 'status', 'recordedAt', 'run', 'artifact', 'result', 'stop', 'limits', 'exclusions'])
    || value.schemaVersion !== 1 || value.scope !== 'RECORDED_ISOLATED_CLOUD_LAKEHOUSE_TRIAL' || value.status !== 'PASSED'
    || value.recordedAt !== cloudLakehouseRecordedAt
    || !fixed(value.run, { id: cloudLakehouseRun, jobId: cloudLakehouseJob, sourceCommit: cloudLakehouseSource })
    || !fixed(value.artifact, { sha256: cloudLakehouseSummary, bytes: 3114,
      runtimeManifestSha256: 'c63aded0a891bb66cb1fb2de591d67e237467681eb4a4e5a337b9d1d1b02d5e8',
      producerSourceSha256: '73e2293210aba3d9522013d923f8d97bd292baa4623736239d55cc21d9321fe2' })) return null;
  const result = value.result;
  if (!object(result) || !exact(result, ['rows', 'rowSha256', 'snapshotIds', 'snapshotOperations', 'silverCounts', 'bronzeDataFilesBefore',
    'bronzeDataFilesAfter', 'compactionProcedureCalls', 'trinoQueryCount', 'preservedOldWarehouseObjects', 'postTrinoWarehouseObjects'])
    || !tuple(result.rows, [6, 12, 12]) || result.rowSha256 !== '9ad14362736e0ada4f44de4ca32296a2e9082e2f78227884326608952116d016'
    || !tuple(result.snapshotIds, cloudLakehouseSnapshotIds) || !(result.snapshotIds as unknown[]).every(snapshot)
    || !tuple(result.snapshotOperations, ['append', 'append', 'replace'])
    || !fixed(result.silverCounts, { rows: 12, success: 7, failure: 3, duplicate: 2, pending: 0 })
    || result.bronzeDataFilesBefore !== 2 || result.bronzeDataFilesAfter !== 1 || result.compactionProcedureCalls !== 1
    || result.trinoQueryCount !== 10 || result.preservedOldWarehouseObjects !== 14 || result.postTrinoWarehouseObjects !== 20) return null;
  if (!fixed(value.stop, { sparkNormalExitVerified: true, trinoExitCode: 143, trinoOomKilled: false, trinoStopRequestReturnedZero: true,
    trinoStopRequestedSeconds: 30, trinoSignalDeliveryDirectlyObserved: false, allOwnedContainersStopped: true,
    initializerStopped: true, enabledOomKillerRepresentationsVerified: true })
    || !fixed(value.limits, { workloadBudgetSeconds: 600, workloadElapsedMillis: 78955, buildAndPullExcluded: true, sparkCpu: 1,
      sparkMemoryBytes: 3221225472, sparkPids: 512, trinoMemoryBytes: 4294967296, plannedSequentialPeakMemoryBytes: 5368709120,
      requiredActualMemAvailableBytes: 7516192768, resourceLimitsAreConfiguration: true })
    || !fixed(value.exclusions, { miniPcContacted: false, kubernetesVerified: false, currentAvailabilityClaimed: false,
      productionSlaClaimed: false, automaticRetryPerformed: false, snapshotExpirationOrObjectGcPerformed: false })) return null;
  return value as unknown as CloudLakehouseRecord;
}
