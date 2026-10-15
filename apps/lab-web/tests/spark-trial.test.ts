import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';
import { parseSparkTrial, sparkTrialRun, sparkTrialSource, sparkTrialSummary } from '../src/lib/spark-trial.ts';

const actual = JSON.parse(readFileSync(new URL('../public/observations/spark.latest.json', import.meta.url), 'utf8'));
const sample = (): Record<string, any> => structuredClone(actual);
test('accepts the actual published cloud projection with lossless snapshot IDs', () => {
  const value = parseSparkTrial(actual);
  assert.ok(value); assert.equal(value.sourceCommit, sparkTrialSource); assert.equal(value.summary.sha256, sparkTrialSummary);
  assert.equal(value.run.id, sparkTrialRun); assert.deepEqual(value.bronze.snapshotIds, ['5876084123105525860', '711948836478668590']);
  assert.equal(value.silver.success + value.silver.failure + value.silver.duplicate, value.bronze.rows);
});
test('missing, partial and unsuccessful evidence never renders as verified', () => {
  for (const input of [undefined, null, {}, [], { ...actual, status: 'FAILED' }, { ...actual, schemaVersion: 2 }]) assert.equal(parseSparkTrial(input), null);
  const value = sample(); delete value.stop; assert.equal(parseSparkTrial(value), null);
});
test('rejects private or unknown fields at every object boundary', () => {
  for (const key of [null, 'run', 'summary', 'fixture', 'versions', 'bronze', 'silver', 'stop', 'resources', 'timing', 'exclusions']) {
    const value = sample(); const target = key === null ? value : value[key]; target.secret = 'not-public';
    assert.equal(parseSparkTrial(value), null);
  }
});
test('source, proof, run and URL must bind the actual audited trial', () => {
  for (const change of [
    (value: Record<string, any>) => { value.sourceCommit = 'a'.repeat(40); },
    (value: Record<string, any>) => { value.summary.sha256 = 'b'.repeat(64); },
    (value: Record<string, any>) => { value.run.id = 38805412935; },
    (value: Record<string, any>) => { value.run.url += '?redirect=other'; },
    (value: Record<string, any>) => { value.run.url = 'https://example.com'; },
    (value: Record<string, any>) => { value.run.attempt = 7; },
  ]) { const value = sample(); change(value); assert.equal(parseSparkTrial(value), null); }
});
test('rejects rounded snapshot IDs, a duplicate snapshot and native Trino snapshot counts', () => {
  for (const id of [5876084123105525860, '01', '0', '-1', '9223372036854775808']) {
    const value = sample(); value.bronze.snapshotIds[0] = id; assert.equal(parseSparkTrial(value), null);
  }
  const duplicate = sample(); duplicate.bronze.snapshotIds[1] = duplicate.bronze.snapshotIds[0]; assert.equal(parseSparkTrial(duplicate), null);
  const native = sample(); native.bronze.snapshots = 3; assert.equal(parseSparkTrial(native), null);
  const nativeHash = sample(); nativeHash.bronze.rowsSha256 = '1c31bc6976083c78549cb0a6b1a48517d16e5bd683da474d75bea1756f1d8514';
  assert.equal(parseSparkTrial(nativeHash), null);
});
test('counts, sequential replay and successful stop must all remain observed', () => {
  for (const [section, key, replacement] of [
    ['silver', 'success', 12], ['silver', 'pending', 1], ['silver', 'replayWriteInvocations', 1],
    ['silver', 'sequentialReplayInvocations', 0], ['stop', 'bootstrapCompleted', false],
    ['stop', 'sessionStopFailed', true], ['stop', 'exitCode', 137], ['stop', 'ownedComposeStopped', false],
    ['stop', 'ownedInitializerStopped', false],
  ] as const) { const value = sample(); value[section][key] = replacement; assert.equal(parseSparkTrial(value), null); }
});
test('cloud records cannot claim deployment, concurrency, peak usage or a performance benchmark', () => {
  for (const key of Object.keys(actual.exclusions)) { const value = sample(); value.exclusions[key] = true; assert.equal(parseSparkTrial(value), null); }
  const throughput = sample(); throughput.timing.stageDurationsOrThroughputMeasured = true; assert.equal(parseSparkTrial(throughput), null);
  const heap = sample(); heap.resources.sparkMemoryBytes = 1536 * 1024 * 1024; assert.equal(parseSparkTrial(heap), null);
  const old = sample(); old.resources.sparkPidLimit = 256; assert.equal(parseSparkTrial(old), null);
});
test('a stale trial cannot be relabelled with a fresh or malformed timestamp', () => {
  for (const capturedAt of ['2026-10-16T20:53:21.475236Z', '2026-02-30T20:53:21Z', '2026-10-15T20:53:21+09:00', 'now']) {
    assert.equal(parseSparkTrial({ ...actual, capturedAt }), null);
  }
});
