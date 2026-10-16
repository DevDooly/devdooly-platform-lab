import assert from 'node:assert/strict';
import test from 'node:test';
import { readFileSync } from 'node:fs';
import { createHash } from 'node:crypto';
import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import ts from 'typescript';
import { captureAssetUrl, icebergCaptureManifest, icebergCaptureManifestV2, icebergCaptureManifestClosedClasspath, icebergCaptureManifestBoundedManifest, observedCount, parseIcebergCapture } from '../src/lib/iceberg-capture.ts';
import { captureFailureCodes, captureClasspathFailureCodes, captureManifestBoundsFailureCodes, parseCaptureDiagnostic } from '../src/lib/iceberg-capture-diagnostic.ts';

const actualRaw = readFileSync(new URL('./fixtures/iceberg-capture-attempt2.summary.json', import.meta.url));
const actual: Record<string, any> = JSON.parse(actualRaw.toString('utf8'));
const actual3Raw = readFileSync(new URL('./fixtures/iceberg-capture-attempt3.summary.json', import.meta.url));
const actual3: Record<string, any> = JSON.parse(actual3Raw.toString('utf8'));

/** Synthetic producer-shaped object only; no actual capture or public asset. */
const fixture = (): Record<string, any> => ({
  schemaVersion: 1, scope: 'FRESH_CLOUD_ICEBERG_CLOSED_COPY_CAPTURE', sourceCommit: 'a'.repeat(40), runtimeManifestSha256: icebergCaptureManifest,
  passed: true, status: 'DETERMINED', failureCategory: null,
  checks: { sourceBytesVerified: true, compilerPrepVerified: true, originalMainCalledOnce: true, originalMainReturnedZero: true,
    decoderStoppedVerified: true, decoderAttachCliReaped: true, sameRunStoppedActorsAndClockVerified: true, inventoryProduced: true, allObjectsKept: true },
  counts: { capturedObjectCount: 9, snapshotCount: 3, refCount: 1, validationPinCount: 3, snapshotCandidateCount: 0, objectCandidateCount: 0 },
  proofHashes: { prepProofSha256: 'b'.repeat(64), normalizationReceiptCanonicalSha256: 'c'.repeat(64) }, decoderReasonCodes: [],
  policy: { schemaVersion: 1, maxInventoryAgeSeconds: 300, minSnapshotAgeSeconds: 86400, minimumSnapshotsToKeep: 3 },
  originalWorkloadBudgetSeconds: 600, separatePrepBudgetSeconds: 600, cleanupReserveSeconds: 40,
  snapshotExpirationPerformed: false, objectDeletionPerformed: false, miniPcContacted: false, liveTableIndependentlyVerified: false,
  parquetContentsDecoded: false, historicalMetadataRestored: false, rawProofsOrCredentialsUploaded: false, automaticRetryPerformed: false,
});
function failed(): Record<string, any> {
  const value = fixture(); value.passed = false; value.status = 'FAILED'; value.failureCategory = 'PREP_NOT_VERIFIED';
  for (const key of Object.keys(value.checks)) value.checks[key] = key === 'sourceBytesVerified';
  for (const key of Object.keys(value.counts)) value.counts[key] = key === 'objectCandidateCount' ? 0 : null;
  value.proofHashes = { prepProofSha256: null, normalizationReceiptCanonicalSha256: null }; return value;
}
function version2(): Record<string, any> {
  return structuredClone(actual);
}
test('the exact real schema 2 failure stays nonpassing with null inventory and separate cleanup facts', () => {
  assert.equal(actualRaw.length, 1733);
  assert.equal(createHash('sha256').update(actualRaw).digest('hex'), 'a88f6ef6bd012e9858554fd0c44d22a834141940da9b61381998ef16b7a585b9');
  const value = parseIcebergCapture(actual); assert.ok(value); assert.equal(value.schemaVersion, 2);
  assert.equal(value.sourceCommit, 'b91a7324a831454554cc6d5293aa4142fd0ba812');
  assert.equal(value.runtimeManifestSha256, '53493f2dfeedee530ad152b5dc08f2c08b3d560ac39fac887820129913c8db3d');
  assert.equal(value.status, 'FAILED'); assert.equal(value.passed, false); assert.equal(value.failureCategory, 'PREP_NOT_VERIFIED');
  assert.equal(value.counts.capturedObjectCount, null); assert.equal(value.counts.snapshotCount, null);
  assert.equal(value.checks.originalMainCalledOnce, false); assert.equal(value.checks.decoderStoppedVerified, false);
  assert.equal(value.schemaVersion === 2 && value.diagnostic.failureCode, 'JAR_MANIFEST_CLASSPATH_EXPANSION_REJECTED');
  if (value.schemaVersion === 2) {
    assert.equal(value.diagnostic.lastPrepChild?.name, 'failed-prep-cold-absence');
    assert.equal(value.diagnostic.lastPrepChild?.returnCode, 0);
    assert.equal(value.diagnostic.lastPrepChild?.childReaped, true);
    assert.equal(value.diagnostic.prepCleanup?.coldRemovedAndAbsent, true);
  }
});
test('the exact real third record keeps preparation failure and null inventory despite cleanup observations', () => {
  assert.equal(actual3Raw.length, 1716);
  assert.equal(createHash('sha256').update(actual3Raw).digest('hex'), '7b5cd2213e8beb6cf988932eb54465828205c81eeb979aef58044f75cd882340');
  const value = parseIcebergCapture(actual3); assert.ok(value); assert.equal(value.schemaVersion, 2);
  assert.equal(value.sourceCommit, 'a03f87837af66fd3770063d9c712c4080e15d9fa');
  assert.equal(value.runtimeManifestSha256, icebergCaptureManifestClosedClasspath);
  assert.equal(value.status, 'FAILED'); assert.equal(value.passed, false); assert.equal(value.failureCategory, 'PREP_NOT_VERIFIED');
  assert.ok(Object.entries(value.counts).every(([key, count]) => count === (key === 'objectCandidateCount' ? 0 : null)));
  assert.ok(Object.entries(value.checks).every(([key, verified]) => verified === (key === 'sourceBytesVerified')));
  assert.equal(value.proofHashes.prepProofSha256, null); assert.equal(value.proofHashes.normalizationReceiptCanonicalSha256, null);
  if (value.schemaVersion === 2) {
    assert.equal(value.diagnostic.stageAttempted, 'PREP'); assert.equal(value.diagnostic.failureCode, 'JAR_MANIFEST_BYTES_BOUND');
    assert.equal(value.diagnostic.lastPrepChild?.name, 'failed-prep-cold-absence');
    assert.equal(value.diagnostic.lastPrepChild?.class, 'COLD_ABSENCE');
    assert.equal(value.diagnostic.lastPrepChild?.outcome, 'EXITED_ZERO');
    assert.equal(value.diagnostic.lastPrepChild?.returnCode, 0); assert.equal(value.diagnostic.lastPrepChild?.childReaped, true);
    assert.ok(value.diagnostic.prepCleanup && Object.values(value.diagnostic.prepCleanup).every(item => item === true));
  }
});
test('synthetic determined, undetermined and failed producer shapes stay distinct', () => {
  assert.equal(parseIcebergCapture(fixture())?.status, 'DETERMINED');
  const unknown = fixture(); unknown.status = 'UNDETERMINED'; unknown.passed = false; unknown.failureCategory = 'CAPTURE_UNDETERMINED';
  unknown.checks.inventoryProduced = false; unknown.decoderReasonCodes = ['MISSING_SNAPSHOT_REFERENCE'];
  for (const key of ['snapshotCount', 'refCount', 'validationPinCount', 'snapshotCandidateCount']) unknown.counts[key] = null;
  assert.equal(parseIcebergCapture(unknown)?.counts.snapshotCount, null);
  assert.equal(parseIcebergCapture(failed())?.status, 'FAILED');
  assert.equal(observedCount(null), '미관측'); assert.equal(observedCount(0), '0');
  for (const value of [undefined, null, {}, [], { ...fixture(), status: 'VERIFIED' }]) assert.equal(parseIcebergCapture(value), null);
  const wrongStatus = failed(); wrongStatus.status = ['FAILED']; assert.equal(parseIcebergCapture(wrongStatus), null);
  const wrongCategory = failed(); wrongCategory.failureCategory = ['PREP_NOT_VERIFIED']; assert.equal(parseIcebergCapture(wrongCategory), null);
});
test('private, unknown and invented provenance fields are rejected at every boundary', () => {
  for (const key of [null, 'checks', 'counts', 'proofHashes', 'policy']) {
    const value = fixture(); (key === null ? value : value[key]).privateEnv = 'SYNTHETIC_PRIVATE_CANARY';
    assert.equal(parseIcebergCapture(value), null);
  }
  for (const key of ['capturedAt', 'runId', 'bucket', 'containerId', 'rawError']) {
    const value = fixture(); value[key] = 'SYNTHETIC_PRIVATE_CANARY'; assert.equal(parseIcebergCapture(value), null);
  }
  const value = fixture(); value.proofHashes.normalizationReceiptSha256 = value.proofHashes.normalizationReceiptCanonicalSha256;
  delete value.proofHashes.normalizationReceiptCanonicalSha256; assert.equal(parseIcebergCapture(value), null);
});
test('aggregate pass cannot be borrowed from an incomplete check or different manifest', () => {
  for (const key of Object.keys(fixture().checks)) { const value = fixture(); value.checks[key] = false; assert.equal(parseIcebergCapture(value), null); }
  for (const change of [(v: Record<string, any>) => { v.passed = false; }, (v: Record<string, any>) => { v.failureCategory = 'PREP_NOT_VERIFIED'; },
    (v: Record<string, any>) => { v.runtimeManifestSha256 = 'd'.repeat(64); }, (v: Record<string, any>) => { v.sourceCommit = 'not-a-commit'; },
    (v: Record<string, any>) => { v.proofHashes.prepProofSha256 = null; }]) {
    const value = fixture(); change(value); assert.equal(parseIcebergCapture(value), null);
  }
});
test('null observations, bounded integer counts and fixed reason enums are preserved', () => {
  for (const [key, replacement] of [['capturedObjectCount', 0], ['capturedObjectCount', 129], ['snapshotCount', -1], ['refCount', 10001],
    ['validationPinCount', 1.5], ['snapshotCandidateCount', true], ['objectCandidateCount', 1]] as const) {
    const value = fixture(); value.counts[key] = replacement; assert.equal(parseIcebergCapture(value), null);
  }
  const missing = failed(); missing.counts.snapshotCount = 0; assert.equal(parseIcebergCapture(missing), null);
  const falseZero = failed(); falseZero.counts.capturedObjectCount = 0; assert.equal(parseIcebergCapture(falseZero), null);
  for (const reasons of [['PRIVATE_ERROR'], ['GRAPH_BOUND', 'GRAPH_BOUND'], Array(17).fill('GRAPH_BOUND')]) {
    const value = fixture(); value.decoderReasonCodes = reasons; assert.equal(parseIcebergCapture(value), null);
  }
});
test('KEEP-only record cannot claim apply, expiry, deletion, deployment or different budgets', () => {
  for (const key of ['snapshotExpirationPerformed', 'objectDeletionPerformed', 'miniPcContacted', 'liveTableIndependentlyVerified',
    'parquetContentsDecoded', 'historicalMetadataRestored', 'rawProofsOrCredentialsUploaded', 'automaticRetryPerformed']) {
    const value = fixture(); value[key] = true; assert.equal(parseIcebergCapture(value), null);
  }
  for (const key of ['originalWorkloadBudgetSeconds', 'separatePrepBudgetSeconds', 'cleanupReserveSeconds']) {
    const value = fixture(); value[key]++; assert.equal(parseIcebergCapture(value), null);
  }
  const value = fixture(); value.policy.minimumSnapshotsToKeep = 1; assert.equal(parseIcebergCapture(value), null);
});
test('only same-origin dedicated evidence locations are eligible for a browser fetch', () => {
  const base = 'https://devdooly.github.io/devdooly-platform-lab/';
  assert.ok(captureAssetUrl('evidence/iceberg-capture/summary.json', base));
  for (const url of ['https://example.com/evidence/iceberg-capture/summary.json', 'https://user:password@devdooly.github.io/evidence/iceberg-capture/summary.json',
    'evidence/iceberg-capture/summary.json?token=private', 'evidence/iceberg-capture/summary.json#fragment', '/api/summary',
    'observations/iceberg-capture.latest.json', 'file:///evidence/iceberg-capture/summary.json', 'javascript:alert(1)']) assert.equal(captureAssetUrl(url, base), null);
});
test('schema 1 history stays separate from strict schema 2 diagnostics and its new runtime', () => {
  assert.equal(parseIcebergCapture(failed())?.schemaVersion, 1);
  assert.equal(parseIcebergCapture(version2())?.schemaVersion, 2);
  const noObservation = version2(); noObservation.diagnostic.lastPrepChild = null; noObservation.diagnostic.prepCleanup = null;
  noObservation.diagnostic.failureCode = 'UNKNOWN'; assert.ok(parseIcebergCapture(noObservation));
  for (const value of [{ ...failed(), runtimeManifestSha256: icebergCaptureManifestV2 },
    { ...version2(), runtimeManifestSha256: icebergCaptureManifest }, { ...failed(), diagnostic: version2().diagnostic }]) assert.equal(parseIcebergCapture(value), null);
  const completed = fixture(); completed.schemaVersion = 2; completed.runtimeManifestSha256 = icebergCaptureManifestV2;
  completed.diagnostic = { stageAttempted: 'COMPLETED', failureCode: null, lastPrepChild: null, prepCleanup: null };
  assert.ok(parseIcebergCapture(completed));
  completed.diagnostic.failureCode = 'UNKNOWN'; assert.equal(parseIcebergCapture(completed), null);
  const lastCleanup = version2(); lastCleanup.diagnostic.lastPrepChild = { ...lastCleanup.diagnostic.lastPrepChild,
    name: 'failed-prep-cold-remove', class: 'COLD_REMOVE', outcome: 'EXITED_NONZERO', returnCode: 1 };
  assert.ok(parseIcebergCapture(lastCleanup)); // Last observed command does not replace the first fixed failure.
});
test('diagnostic fields cannot expose provider text, IDs, argv, hashes or malformed process claims', () => {
  for (const boundary of ['diagnostic', 'lastPrepChild', 'prepCleanup']) {
    const value = version2(); const target = boundary === 'diagnostic' ? value.diagnostic : value.diagnostic[boundary];
    target.rawProviderMessage = 'SYNTHETIC_PRIVATE_CANARY'; assert.equal(parseIcebergCapture(value), null);
  }
  for (const [boundary, key, replacement] of [
    ['diagnostic', 'failureCode', 'SYNTHETIC_PRIVATE_CANARY'], ['diagnostic', 'stageAttempted', ['PREP']],
    ['lastPrepChild', 'name', 'foreign-private-name'], ['lastPrepChild', 'class', 'COLD_REMOVE'],
    ['lastPrepChild', 'outcome', 'PRIVATE_MESSAGE'], ['lastPrepChild', 'returnCode', false],
    ['lastPrepChild', 'stdoutBytes', 1040 * 1024 ** 2 + 1], ['lastPrepChild', 'stderrBytes', 65537],
    ['lastPrepChild', 'childStarted', false], ['lastPrepChild', 'childReaped', false],
    ['prepCleanup', 'coldIdentityBound', false], ['prepCleanup', 'knownColdCid', 1],
  ] as const) {
    const value = version2(); (boundary === 'diagnostic' ? value.diagnostic : value.diagnostic[boundary])[key] = replacement;
    assert.equal(parseIcebergCapture(value), null);
  }
});
test('new classpath codes require the exact separately reviewed runtime while old records keep 129 codes', () => {
  // Runtime profiles are source contracts; the existing real record still belongs to old 534.
  assert.equal(typeof icebergCaptureManifestClosedClasspath, 'string');
  assert.match(icebergCaptureManifestClosedClasspath!, /^[a-f0-9]{64}$/);
  assert.notEqual(icebergCaptureManifestClosedClasspath, icebergCaptureManifestV2);
  assert.notEqual(icebergCaptureManifestClosedClasspath, icebergCaptureManifest);
  assert.equal(captureFailureCodes.length, 129); assert.equal(captureClasspathFailureCodes.length, 5);
  assert.equal(new Set([...captureFailureCodes, ...captureClasspathFailureCodes]).size, 134);
  assert.ok(parseIcebergCapture(actual));
  for (const failureCode of captureClasspathFailureCodes) {
    const old = version2(); old.diagnostic.failureCode = failureCode;
    assert.equal(parseCaptureDiagnostic(old.diagnostic, false), null);
    assert.equal(parseIcebergCapture(old), null);
    const next = structuredClone(old); next.runtimeManifestSha256 = icebergCaptureManifestClosedClasspath;
    assert.equal(parseIcebergCapture(next)?.schemaVersion, 2);
    const foreign = structuredClone(next); foreign.runtimeManifestSha256 = 'f'.repeat(64);
    assert.equal(parseIcebergCapture(foreign), null);
    next.diagnostic.failureCode = 'SYNTHETIC_PRIVATE_CANARY'; assert.equal(parseIcebergCapture(next), null);
  }
  const legacy = failed(); legacy.diagnostic = version2().diagnostic;
  assert.equal(parseIcebergCapture(legacy), null);
});
test('the bounded-manifest runtime alone accepts four new codes and retains the prior five-code extension', () => {
  // Synthetic profile boundary cases; no new actual capture outcome is implied by changing a manifest.
  assert.equal(typeof icebergCaptureManifestBoundedManifest, 'string');
  assert.match(icebergCaptureManifestBoundedManifest!, /^[a-f0-9]{64}$/);
  for (const older of [icebergCaptureManifest, icebergCaptureManifestV2, icebergCaptureManifestClosedClasspath]) {
    assert.notEqual(icebergCaptureManifestBoundedManifest, older);
  }
  assert.equal(captureManifestBoundsFailureCodes.length, 4);
  assert.equal(new Set([...captureFailureCodes, ...captureClasspathFailureCodes, ...captureManifestBoundsFailureCodes]).size, 138);
  for (const failureCode of captureManifestBoundsFailureCodes) {
    for (const runtimeManifestSha256 of [icebergCaptureManifestV2, icebergCaptureManifestClosedClasspath]) {
      const old = version2(); old.runtimeManifestSha256 = runtimeManifestSha256; old.diagnostic.failureCode = failureCode;
      assert.equal(parseIcebergCapture(old), null);
    }
    const old = version2(); old.diagnostic.failureCode = failureCode;
    assert.equal(parseCaptureDiagnostic(old.diagnostic, false), null);
    assert.equal(parseCaptureDiagnostic(old.diagnostic, false, 'SCHEMA2_CLOSED_CLASSPATH'), null);
  }
  for (const failureCode of [...captureClasspathFailureCodes, ...captureManifestBoundsFailureCodes]) {
    const next = version2(); next.runtimeManifestSha256 = icebergCaptureManifestBoundedManifest; next.diagnostic.failureCode = failureCode;
    assert.equal(parseIcebergCapture(next)?.schemaVersion, 2);
    const foreign = structuredClone(next); foreign.runtimeManifestSha256 = 'f'.repeat(64);
    assert.equal(parseIcebergCapture(foreign), null);
    next.diagnostic.failureCode = 'SYNTHETIC_PRIVATE_CANARY'; assert.equal(parseIcebergCapture(next), null);
  }
  assert.ok(parseIcebergCapture(actual)); assert.ok(parseIcebergCapture(actual3));
});
test('provided-record component path never renders a JSON link for an unsafe URL', async () => {
  // Existing TypeScript/React dependencies only; compile in memory and remove CSS solely for SSR.
  const raw = readFileSync(new URL('../src/components/IcebergCaptureCard.tsx', import.meta.url), 'utf8');
  let code = ts.transpileModule(raw, { compilerOptions: { jsx: ts.JsxEmit.ReactJSX,
    module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022 } }).outputText;
  code = code.replace(/from (['"])react\1/g, `from ${JSON.stringify(import.meta.resolve('react'))}`)
    .replace(/from (['"])react\/jsx-runtime\1/g, `from ${JSON.stringify(import.meta.resolve('react/jsx-runtime'))}`)
    .replace(/from (['"])\.\.\/lib\/iceberg-capture\1/g, `from ${JSON.stringify(new URL('../src/lib/iceberg-capture.ts', import.meta.url).href)}`)
    .replace(/import (['"])\.\.\/styles\/iceberg-capture\.css\1;?/g, '');
  const { default: Card } = await import(`data:text/javascript;base64,${Buffer.from(code).toString('base64')}`);
  for (const observationUrl of ['javascript:alert(1)', 'https://example.com/evidence/iceberg-capture/summary.json',
    '/evidence/iceberg-capture/summary.json?token=private']) {
    const html = renderToStaticMarkup(createElement(Card, { record: version2(), observationUrl }));
    assert.ok(!html.includes('공개 결과 JSON')); assert.ok(!html.includes('token=private'));
  }
  const html = renderToStaticMarkup(createElement(Card, { record: version2(), observationUrl: '/evidence/iceberg-capture/summary.json' }));
  assert.ok(html.includes('공개 결과 JSON')); assert.ok(html.includes('Popen/CLI'));
  assert.ok(html.includes('prefix')); assert.ok(!/<details[^>]*\bopen(?:\s|=|>)/.test(html));
});
