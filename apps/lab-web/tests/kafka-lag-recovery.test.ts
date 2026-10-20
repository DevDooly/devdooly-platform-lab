import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';
import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import ts from 'typescript';
import { KAFKA_LAG_RUNTIME_MANIFEST, KAFKA_LAG_SOURCE_COMMIT, KAFKA_LAG_RUN_URL, KAFKA_LAG_COMPLETED_AT, KAFKA_LAG_XML_SHA256, kafkaLagPhaseKey, kafkaLagPhases, parseKafkaLagRecovery } from '../src/lib/kafka-lag-recovery.ts';

const now = Date.UTC(2026, 9, 20, 12);
/** Synthetic parser/render fixture only; never imported by the public component or published as evidence. */
function sample() {
  return { runUrl: KAFKA_LAG_RUN_URL, completedAt: KAFKA_LAG_COMPLETED_AT,
    summary: { schemaVersion: 1, scope: 'ISOLATED_KAFKA_LAG_RECOVERY_IT', synthetic: true,
      sourceCommit: KAFKA_LAG_SOURCE_COMMIT, runtimeManifestSha256: KAFKA_LAG_RUNTIME_MANIFEST,
      status: 'PASSED', failureCode: null, expectedTests: 1, verifiedTests: 1, surefireXmlSha256: KAFKA_LAG_XML_SHA256,
      sourceAndArtifactsUnchanged: true, ownedResourcesRemoved: true, selectedFailure: null,
      operatingKafkaChanged: false, databaseOrExportRecoveryVerified: false,
      brokerRestartOrHighAvailabilityVerified: false, publicExecutionEnabled: false,
      recoveryResult: { schemaVersion: 1, status: 'PASS', initialProcessed: 4, initialEndOffset: 12,
        initialCommittedOffset: 4, initialLag: 8, emptyGroupObserved: true, additionalProduced: 6,
        backlogEndOffset: 18, backlogCommittedOffset: 4, backlogLag: 14, resumedProcessed: 14,
        resumedFirstOffset: 4, resumedLastOffset: 17, finalCommittedOffset: 18, finalLag: 0, targetStable: true } } };
}

test('missing, failed and partial summaries cannot supply successful phase values', () => {
  for (const value of [undefined, null, {}, { summary: sample().summary },
    { ...sample(), summary: { ...sample().summary, status: 'FAILED' } },
    { ...sample(), summary: { ...sample().summary, failureCode: 'UNKNOWN' } },
    { ...sample(), summary: { ...sample().summary, verifiedTests: 0, surefireXmlSha256: null } },
    { ...sample(), summary: { ...sample().summary, ownedResourcesRemoved: false } },
    { ...sample(), summary: { ...sample().summary, sourceAndArtifactsUnchanged: false } }]) {
    assert.equal(parseKafkaLagRecovery(value, now), null);
  }
});

test('only exact public fields at envelope, summary and result boundaries are accepted', () => {
  const value = sample(); assert.ok(parseKafkaLagRecovery(value, now));
  for (const changed of [{ ...value, token: 'PRIVATE_CANARY' },
    { ...value, summary: { ...value.summary, host: 'PRIVATE_CANARY' } },
    { ...value, summary: { ...value.summary, recoveryResult: { ...value.summary.recoveryResult, topic: 'PRIVATE_CANARY' } } },
    { ...value, summary: { ...value.summary, publicExecutionEnabled: true } },
    { ...value, summary: { ...value.summary, brokerRestartOrHighAvailabilityVerified: true } }]) {
    assert.equal(parseKafkaLagRecovery(changed, now), null);
  }
});

test('recorded counts, source manifest, test count and scalar types must match the one verified contract', () => {
  const value = sample();
  for (const [key, changed] of [['initialCommittedOffset', 3], ['initialLag', 0], ['backlogLag', 13],
    ['resumedProcessed', 13], ['resumedFirstOffset', 0], ['finalCommittedOffset', 17], ['targetStable', false],
    ['schemaVersion', true]] as const) {
    assert.equal(parseKafkaLagRecovery({ ...value, summary: { ...value.summary,
      recoveryResult: { ...value.summary.recoveryResult, [key]: changed } } }, now), null);
  }
  for (const changed of [{ runtimeManifestSha256: 'c'.repeat(64) }, { sourceCommit: 'unknown' },
    { sourceCommit: 'c'.repeat(40) }, { surefireXmlSha256: 'B'.repeat(64) }, { surefireXmlSha256: 'b'.repeat(64) }, { expectedTests: 2 }, { verifiedTests: true }]) {
    assert.equal(parseKafkaLagRecovery({ ...value, summary: { ...value.summary, ...changed } }, now), null);
  }
});

test('run links and completion dates are restricted to the actual repository and strict past UTC', () => {
  for (const runUrl of ['https://example.test/actions/runs/12345', sample().runUrl + '?token=private',
    sample().runUrl + '#private', 'https://github.com/DevDooly/another-repo/actions/runs/12345',
    'http://github.com/DevDooly/devdooly-platform-lab/actions/runs/12345',
    'https://github.com/DevDooly/devdooly-platform-lab/actions/runs/39412343875']) {
    assert.equal(parseKafkaLagRecovery({ ...sample(), runUrl }, now), null);
  }
  for (const completedAt of ['2026-02-30T00:00:00Z', '2026-10-20T00:00:00+00:00',
    '2026-10-21T00:00:00Z', '2026-10-20T00:00:00Z', '2026-10-20T00:00:00.0000000001Z']) {
    assert.equal(parseKafkaLagRecovery({ ...sample(), completedAt }, now), null);
  }
});

test('phase values retain commit while empty, then resume exactly at offset four; keyboard selection remains bounded', () => {
  const record = parseKafkaLagRecovery(sample(), now); assert.ok(record);
  assert.deepEqual(kafkaLagPhases(record).map(item => [item.group, item.end, item.committed, item.lag]),
    [['STABLE', 12, 4, 8], ['EMPTY', 12, 4, 8], ['EMPTY', 18, 4, 14], ['STABLE', 18, 18, 0]]);
  assert.equal(kafkaLagPhaseKey(0, 'ArrowLeft'), 3); assert.equal(kafkaLagPhaseKey(3, 'ArrowRight'), 0);
  assert.equal(kafkaLagPhaseKey(2, 'Home'), 0); assert.equal(kafkaLagPhaseKey(1, 'End'), 3);
  assert.equal(kafkaLagPhaseKey(2, 'Tab'), null); assert.equal(kafkaLagPhaseKey(-1, 'ArrowRight'), null);
});

test('card renders pending without metrics, and validated props provide controls, accessible chart, table and explicit limits', async () => {
  const source = readFileSync(new URL('../src/components/KafkaLagRecoveryCard.tsx', import.meta.url), 'utf8');
  let code = ts.transpileModule(source, { compilerOptions: { jsx: ts.JsxEmit.ReactJSX, module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022 } }).outputText;
  code = code.replace(/from (['"])react\1/g, `from ${JSON.stringify(import.meta.resolve('react'))}`)
    .replace(/from (['"])react\/jsx-runtime\1/g, `from ${JSON.stringify(import.meta.resolve('react/jsx-runtime'))}`)
    .replace(/from (['"])\.\.\/lib\/kafka-lag-recovery\.ts\1/g,
      `from ${JSON.stringify(new URL('../src/lib/kafka-lag-recovery.ts', import.meta.url).href)}`)
    .replace(/import (['"])\.\.\/styles\/kafka-lag-recovery\.css\1;?/g, '');
  const { default: Card } = await import(`data:text/javascript;base64,${Buffer.from(code).toString('base64')}`);
  const pending = renderToStaticMarkup(createElement(Card));
  assert.ok(pending.includes('공개 기록 대기')); assert.ok(!pending.includes('<table'));
  assert.ok(!pending.includes('<svg')); assert.ok(!pending.includes('<button'));
  const invalid = renderToStaticMarkup(createElement(Card, { record: { ...sample(), token: 'PRIVATE_CANARY' } }));
  assert.ok(invalid.includes('공개 기록 대기')); assert.ok(!invalid.includes('PRIVATE_CANARY'));
  const ready = renderToStaticMarkup(createElement(Card, { record: sample() }));
  assert.equal((ready.match(/<button\b/g) || []).length, 4);
  assert.equal((ready.match(/aria-pressed="true"/g) || []).length, 1);
  assert.ok(ready.includes('role="img"')); assert.ok(ready.includes('<caption>'));
  assert.ok(ready.includes('가로 간격은 경과 시간')); assert.ok(ready.includes('정상 종료하고 새 클라이언트'));
  assert.ok(ready.includes('고가용성 검증과 구분')); assert.ok(ready.includes('target="_blank"'));
  assert.ok(!ready.includes('onload=')); assert.ok(!ready.includes('<form'));
});
