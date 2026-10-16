import assert from 'node:assert/strict';
import test from 'node:test';
import { parseS3Transport } from '../src/lib/s3-transport.ts';

// Contract examples only; the public asset is supplied from separately audited receipts.
const pending = () => ({ schemaVersion: 1, status: 'DEPLOYED_SDK_PENDING', sourceCommit: '74a8e98844a8fea0653951136ede0e7de0d7ac08',
  observedAt: '2026-10-15T23:25:02.723586Z', deployment: { healthyObserved: true, sourceCommit: '74a8e98844a8fea0653951136ede0e7de0d7ac08', capturedAt: '2026-10-15T23:10:15.488175Z' },
  sdk: { status: 'NOT_RUN' }, preservation: { afterSdkVerified: false, capturedAt: '2026-10-15T23:12:57.466419Z', originalWholeGets: 24, nativeKnownWholeGets: 12 },
  history: { originalApiwebWatchPassed: false, originalApiwebFailureCause: 'UNPROVEN', oldWorkerExit: 'UNOBSERVED' },
  limits: { pointInTimeOnly: true, productionApiJvmSdkVerified: false, writeCompatibilityVerified: false, latencyOrSlaClaimed: false } });
const verified = (): any => ({ ...pending(), status: 'DEPLOYED_SDK_VERIFIED', observedAt: '2026-10-16T00:00:00Z',
  preservation: { afterSdkVerified: true, capturedAt: '2026-10-15T23:59:00Z', originalWholeGets: 24, nativeKnownWholeGets: 12 },
  sdk: { status: 'VERIFIED', capturedAt: '2026-10-15T23:45:37.148212Z', wholeGets: 3, apiCalls: 3, httpAttempts: 3, retries: 0,
    configuredMaxAttempts: 3, clientClosed: true, httpClient: 'Apache5', cleanupRevoked: true, proofSha256: { run: 'a'.repeat(64), cleanup: 'b'.repeat(64), revoke: 'c'.repeat(64) } } });
test('explicit pending and complete verified contracts remain distinct', () => {
  assert.equal(parseS3Transport(pending())?.sdk.status, 'NOT_RUN');
  assert.equal(parseS3Transport(verified())?.sdk.status, 'VERIFIED');
  const value = verified(); value.preservation.afterSdkVerified = false; assert.equal(parseS3Transport(value), null);
  const partial: any = pending(); partial.sdk = verified().sdk; assert.equal(parseS3Transport(partial), null);
});
test('unknown, partial and private nested fields fail closed', () => {
  for (const value of [undefined, null, {}, [], { ...pending(), schemaVersion: 2 }, { ...verified(), status: 'UNKNOWN' }]) assert.equal(parseS3Transport(value), null);
  for (const path of ['', 'deployment', 'sdk', 'sdk.proofSha256', 'preservation', 'history', 'limits']) {
    const value = verified(); const target = path ? path.split('.').reduce((v, key) => v[key], value) : value;
    target.secretAccessKey = 'private'; assert.equal(parseS3Transport(value), null);
  }
  const missing = verified(); delete missing.sdk.clientClosed; assert.equal(parseS3Transport(missing), null);
});
test('whole reads, observed retries, configuration and owned cleanup are independently required', () => {
  for (const [key, replacement] of [['wholeGets', 2], ['apiCalls', 4], ['httpAttempts', 4], ['retries', 1], ['configuredMaxAttempts', 0], ['clientClosed', false], ['httpClient', 'UrlConnection'], ['cleanupRevoked', false]]) {
    const value = verified(); value.sdk[key] = replacement; assert.equal(parseS3Transport(value), null);
  }
  const short = verified(); short.sdk.proofSha256.run = '7c861'; assert.equal(parseS3Transport(short), null);
  const duplicate = verified(); duplicate.sdk.proofSha256.cleanup = duplicate.sdk.proofSha256.run; assert.equal(parseS3Transport(duplicate), null);
});
test('source and timestamps bind one observed record without claiming live health', () => {
  for (const source of ['74', 'A'.repeat(40), 'https://example.com']) { const value = verified(); value.sourceCommit = source; assert.equal(parseS3Transport(value), null); }
  const mismatch = verified(); mismatch.deployment.sourceCommit = 'd'.repeat(40); assert.equal(parseS3Transport(mismatch), null);
  for (const time of ['now', '2026-02-30T23:45:37Z', '2026-10-15T23:45:37+09:00']) { const value = verified(); value.observedAt = time; assert.equal(parseS3Transport(value), null); }
  const before = verified(); before.preservation.capturedAt = '2026-10-15T23:44:00Z'; assert.equal(parseS3Transport(before), null);
  const relabelled = verified(); relabelled.sdk.capturedAt = '2026-10-16T23:45:37.148212Z'; assert.equal(parseS3Transport(relabelled), null);
});
test('historical failure, unobserved exit and JVM/write/SLA exclusions cannot be upgraded', () => {
  for (const section of ['history', 'limits']) for (const key of Object.keys(verified()[section])) {
    const value = verified(); value[section][key] = !value[section][key]; assert.equal(parseS3Transport(value), null);
  }
  const count = verified(); count.preservation.nativeKnownWholeGets = 13; assert.equal(parseS3Transport(count), null);
  const healthy = verified(); healthy.deployment.healthyObserved = 'live'; assert.equal(parseS3Transport(healthy), null);
});
