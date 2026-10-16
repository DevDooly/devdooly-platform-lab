import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';
import { parseCloudLakehouse, cloudLakehouseRun, cloudLakehouseJob, cloudLakehouseSource,
  cloudLakehouseSummary, cloudLakehouseRecordedAt, cloudLakehouseSnapshotIds } from '../src/lib/cloud-lakehouse.ts';

// The published asset is an actual audited projection, not a synthetic success fixture.
const actual = JSON.parse(readFileSync(new URL('../public/observations/cloud-lakehouse.latest.json', import.meta.url), 'utf8'));
const sample = (): Record<string, any> => structuredClone(actual);

test('accepts the actual full Cloud record with lossless snapshots and preserved results', () => {
  const value = parseCloudLakehouse(actual);
  assert.ok(value); assert.equal(value.run.id, cloudLakehouseRun); assert.equal(value.run.jobId, cloudLakehouseJob);
  assert.equal(value.run.sourceCommit, cloudLakehouseSource); assert.equal(value.artifact.sha256, cloudLakehouseSummary);
  assert.equal(value.recordedAt, cloudLakehouseRecordedAt); assert.deepEqual(value.result.snapshotIds, cloudLakehouseSnapshotIds);
  assert.deepEqual(value.result.snapshotOperations, ['append', 'append', 'replace']); assert.deepEqual(value.result.rows, [6, 12, 12]);
  assert.equal(value.result.bronzeDataFilesBefore, 2); assert.equal(value.result.bronzeDataFilesAfter, 1);
  assert.equal(value.result.silverCounts.success + value.result.silverCounts.failure + value.result.silverCounts.duplicate, 12);
  assert.equal(value.result.trinoQueryCount, 10); assert.equal(value.stop.allOwnedContainersStopped, true);
});

test('missing, failed, partial or relabelled evidence stays unverified without default counts', () => {
  for (const input of [undefined, null, {}, [], { ...actual, status: 'FAILED' }, { ...actual, status: 'RUNNING' },
    { ...actual, schemaVersion: 2 }, { ...actual, scope: 'LIVE_CLOUD_LAKEHOUSE' }]) assert.equal(parseCloudLakehouse(input), null);
  for (const key of Object.keys(actual)) { const value = sample(); delete value[key]; assert.equal(parseCloudLakehouse(value), null); }
  const partial = sample(); partial.result.rows = [6, 12]; assert.equal(parseCloudLakehouse(partial), null);
  const unknown = sample(); unknown.stop.initializerStopped = null; assert.equal(parseCloudLakehouse(unknown), null);
});

test('private and unknown fields fail closed at every nested object boundary', () => {
  for (const path of [[], ['run'], ['artifact'], ['result'], ['result', 'silverCounts'], ['stop'], ['limits'], ['exclusions']]) {
    const value = sample(); let target = value; for (const key of path) target = target[key];
    target.secret = 'private-not-public'; assert.equal(parseCloudLakehouse(value), null);
  }
  const url = sample(); url.run.url = 'https://example.com/credential'; assert.equal(parseCloudLakehouse(url), null);
  const measured = sample(); measured.limits.observedPeakMemoryBytes = 5368709120; assert.equal(parseCloudLakehouse(measured), null);
});

test('the exact run, source, proofs, time and decimal snapshot identities cannot be substituted', () => {
  for (const change of [
    (value: Record<string, any>) => { value.run.sourceCommit = 'a'.repeat(40); },
    (value: Record<string, any>) => { value.run.id = 38843953097; },
    (value: Record<string, any>) => { value.run.jobId = '116790713620'; },
    (value: Record<string, any>) => { value.artifact.sha256 = 'b'.repeat(64); },
    (value: Record<string, any>) => { value.artifact.runtimeManifestSha256 = 'c'.repeat(64); },
    (value: Record<string, any>) => { value.artifact.producerSourceSha256 = 'd'.repeat(64); },
    (value: Record<string, any>) => { value.artifact.bytes = 3115; },
    (value: Record<string, any>) => { value.recordedAt = '2026-10-16T03:12:34.839802Z'; },
    (value: Record<string, any>) => { value.result.rowSha256 = '1c31bc6976083c78549cb0a6b1a48517d16e5bd683da474d75bea1756f1d8514'; },
  ]) { const value = sample(); change(value); assert.equal(parseCloudLakehouse(value), null); }
  for (const id of [8225039569250402625, '01', '0', '-1', '9223372036854775808']) {
    const value = sample(); value.result.snapshotIds[0] = id; assert.equal(parseCloudLakehouse(value), null);
  }
  const duplicate = sample(); duplicate.result.snapshotIds[1] = duplicate.result.snapshotIds[0]; assert.equal(parseCloudLakehouse(duplicate), null);
});

test('counts, bounded resources, cleanup and scope exclusions remain required observed facts', () => {
  for (const [section, key, replacement] of [
    ['result', 'bronzeDataFilesBefore', 1], ['result', 'bronzeDataFilesAfter', 2], ['result', 'compactionProcedureCalls', 2],
    ['result', 'trinoQueryCount', 0], ['result', 'preservedOldWarehouseObjects', 0], ['result', 'postTrinoWarehouseObjects', 0],
    ['stop', 'sparkNormalExitVerified', false], ['stop', 'trinoExitCode', 137], ['stop', 'trinoOomKilled', true],
    ['stop', 'trinoStopRequestReturnedZero', false], ['stop', 'trinoSignalDeliveryDirectlyObserved', true],
    ['stop', 'allOwnedContainersStopped', false], ['stop', 'initializerStopped', false],
    ['stop', 'enabledOomKillerRepresentationsVerified', null], ['limits', 'workloadBudgetSeconds', 601],
    ['limits', 'workloadElapsedMillis', 78954], ['limits', 'buildAndPullExcluded', false],
    ['limits', 'sparkMemoryBytes', 4294967296], ['limits', 'sparkPids', 256], ['limits', 'trinoMemoryBytes', 3221225472],
    ['limits', 'requiredActualMemAvailableBytes', 0], ['limits', 'resourceLimitsAreConfiguration', false],
  ] as const) { const value = sample(); value[section][key] = replacement; assert.equal(parseCloudLakehouse(value), null); }
  for (const key of Object.keys(actual.exclusions)) { const value = sample(); value.exclusions[key] = true; assert.equal(parseCloudLakehouse(value), null); }
  const missingRows = sample(); missingRows.result.rows = [0, 0, 0]; assert.equal(parseCloudLakehouse(missingRows), null);
  const initialEmpty = sample(); initialEmpty.result.rows = [0, 6, 12]; assert.equal(parseCloudLakehouse(initialEmpty), null);
  const operations = sample(); operations.result.snapshotOperations[2] = 'append'; assert.equal(parseCloudLakehouse(operations), null);
  const silver = sample(); silver.result.silverCounts.pending = 1; assert.equal(parseCloudLakehouse(silver), null);
});
