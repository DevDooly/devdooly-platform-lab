import assert from 'node:assert/strict';
import test from 'node:test';
import { closedFormWindow, parseWindowEvidence, windowProfiles, windowSizes } from '../src/lib/ai-window.ts';

// Invented bounded values for validator tests only. Never emitted as public measurement evidence.
function sample() {
  const hash = 'a'.repeat(64);
  return {
    schemaVersion: 1, scope: 'INDEPENDENT_SYNTHETIC_WINDOWS_JAVA21', sourceCommit: null,
    sourceTreeSha256: hash, jarSha256: hash, fixtureManifestSha256: hash, rawResultSha256: hash,
    measuredAt: '2026-10-15T12:00:00.123456+00:00', humanReview: 'PENDING',
    conditions: { jmhVersion: '1.37', javaVersion: '21.0.9', os: 'Windows', forks: 3, threads: 1,
      warmupIterations: 2, warmupMillis: 500, measurementIterations: 5, measurementMillis: 500,
      heapMiB: 256, gc: 'G1', timezone: 'Asia/Seoul' },
    measurements: windowProfiles.flatMap(profile => windowSizes.map(size => ({ profile, size,
      quadratic: { meanMicros: 20, errorMicros: 2, allocationBytesPerOp: 1024 },
      sweep: { meanMicros: 5, errorMicros: 1, allocationBytesPerOp: 512 }, ratio: 4,
      rawSha256: hash, normalizedSha256: hash, resultSha256: hash, ...closedFormWindow(profile, size) }))),
    evidenceLinks: {
      readme: 'https://github.com/DevDooly/devdooly-platform-lab/blob/main/docs/evidence/ai-window-analysis/README.md',
      source: 'https://github.com/DevDooly/devdooly-platform-lab/tree/main/examples/java-window-analysis',
    },
  };
}
test('accepts complete bounded evidence with honest null commit and pending human review', () => {
  assert.ok(parseWindowEvidence(sample()));
  const actualJdk = sample(); actualJdk.conditions.javaVersion = 'Microsoft OpenJDK 21.0.9+10-LTS';
  assert.ok(parseWindowEvidence(actualJdk));
});
test('rejects unconnected data and incomplete or duplicate fixture coverage', () => {
  assert.equal(parseWindowEvidence(undefined), null); assert.equal(parseWindowEvidence(null), null);
  const partial = sample(); partial.measurements.pop(); assert.equal(parseWindowEvidence(partial), null);
  const duplicate = sample(); duplicate.measurements[7] = duplicate.measurements[0]; assert.equal(parseWindowEvidence(duplicate), null);
});
test('rejects nonfinite or negative metrics and inconsistent claimed time ratio', () => {
  for (const value of [NaN, Infinity, -1, 0]) {
    const record = sample(); record.measurements[0].sweep.meanMicros = value; assert.equal(parseWindowEvidence(record), null);
  }
  const record = sample(); record.measurements[0].ratio = 400; assert.equal(parseWindowEvidence(record), null);
});
test('rejects false functional results even when timing values look valid', () => {
  const union = sample(); union.measurements[0].coveredNanos += 1; assert.equal(parseWindowEvidence(union), null);
  const peak = sample(); peak.measurements[7].peakConcurrentSessions -= 1; assert.equal(parseWindowEvidence(peak), null);
});
test('rejects private/unknown fields and external credential-bearing evidence URLs', () => {
  assert.equal(parseWindowEvidence({ ...sample(), credentials: 'not-public' }), null);
  for (const url of ['file:///private/report.json', 'https://user:password@github.com/DevDooly/devdooly-platform-lab/tree/main/examples/java-window-analysis',
    'https://example.com/raw.json', 'https://github.com/DevDooly/devdooly-platform-lab/tree/main/examples/java-window-analysis?token=secret']) {
    const record = sample(); record.evidenceLinks.source = url; assert.equal(parseWindowEvidence(record), null);
  }
});
test('requires three forks and the recorded Windows Java21 environment', () => {
  for (const [field, value] of [['forks', 0], ['threads', 8], ['javaVersion', '25.0.1'], ['javaVersion', 'Microsoft OpenJDK 25.0.1+8-LTS'], ['os', 'Ubuntu']] as const) {
    const record = sample(); Object.assign(record.conditions, { [field]: value }); assert.equal(parseWindowEvidence(record), null);
  }
});
test('rejects invalid provenance, non-UTC dates and array-shaped review claims', () => {
  for (const change of [{ sourceCommit: 'unknown' }, { rawResultSha256: 'bad' }, { measuredAt: '2026-10-15T12:00:00+09:00' }, { humanReview: ['PENDING'] }]) {
    assert.equal(parseWindowEvidence({ ...sample(), ...change }), null);
  }
});
