import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';
import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import ts from 'typescript';
import {
  OFFSET_COMMIT_RUNTIME_MANIFEST, OFFSET_COMMIT_SOURCE_COMMIT, OFFSET_COMMIT_RUN_URL,
  OFFSET_COMMIT_COMPLETED_AT, OFFSET_COMMIT_XML_SHA256, defaultBinding,
  offsetCommitPhaseKey, offsetCommitPhases, parseOffsetCommitRecovery,
  type OffsetCommitBinding,
} from '../src/lib/offset-commit-recovery.ts';

const now = Date.UTC(2026, 9, 20, 12);
/** Synthetic parser/render fixture only. Never public evidence and never passed as a production binding. */
const testBinding: OffsetCommitBinding = {
  runtimeManifestSha256: 'a'.repeat(64), sourceCommit: 'b'.repeat(40),
  runUrl: 'https://github.com/DevDooly/devdooly-platform-lab/actions/runs/12345',
  completedAt: '2026-10-20T11:00:00.123456789Z', surefireXmlSha256: 'c'.repeat(64),
};
function sample(state: 'NO_COMMIT' | 'OBSERVED' = 'NO_COMMIT', completedReplays: 0 | 1 = 0) {
  return { runUrl: testBinding.runUrl, completedAt: testBinding.completedAt,
    summary: { schemaVersion: 1, scope: 'ISOLATED_REAL_OFFSET_COMMIT_RECOVERY', synthetic: true,
      sourceCommit: testBinding.sourceCommit, runtimeManifestSha256: testBinding.runtimeManifestSha256,
      status: 'PASSED', failureCode: null, selectedFailure: null, jvmFailure: null, expectedTests: 1, verifiedTests: 1,
      surefireXmlSha256: testBinding.surefireXmlSha256, ownedResourcesRemoved: true,
      sourceAndArtifactsUnchanged: true, operatingServicesChanged: false, hostOrBrokerRestartVerified: false,
      publicExecutionEnabled: false,
      recoveryResult: { schemaVersion: 1, status: 'PASS', fixtureInput: 12, successCount: 7, failureCount: 3,
        duplicateCount: 2, pendingCount: 0, dbCommitBeforeFault: true, pausePersisted: true,
        pauseCode: 'OFFSET_COMMIT_FAILED', runRefusedUnchanged: true, operatorResumeRecorded: true,
        postUnpauseCommitState: state, postUnpauseCommittedOffset: state === 'NO_COMMIT' ? null : 1,
        readCommittedEndOffset: 1, completedReplays, businessRowsAndTimesUnchanged: true, exported: true,
        verifiedExportFiles: 2, slotFree: true, finalCommittedOffset: 1, finalLag: 0, childResourcesClosed: true } } };
}
const parse = (value: unknown) => parseOffsetCommitRecovery(value, now, testBinding);
const parseBound = (value: unknown, binding: unknown) => parseOffsetCommitRecovery(value, now, binding as OffsetCommitBinding);
function resultChanged(changes: Record<string, unknown>) {
  const value = sample(); return { ...value, summary: { ...value.summary, recoveryResult: { ...value.summary.recoveryResult, ...changes } } };
}

test('production binding accepts the reviewed real record and rejects synthetic fixtures', () => {
  const actual = JSON.parse(readFileSync(new URL('../src/data/offset-commit-recovery.generated.json', import.meta.url), 'utf8'));
  const actualNow = Date.parse(OFFSET_COMMIT_COMPLETED_AT) + 1;
  assert.deepEqual(defaultBinding, {
    runtimeManifestSha256: actual.summary.runtimeManifestSha256, sourceCommit: actual.summary.sourceCommit,
    runUrl: actual.runUrl, completedAt: actual.completedAt, surefireXmlSha256: actual.summary.surefireXmlSha256,
  });
  assert.ok(parseOffsetCommitRecovery(actual, actualNow));
  assert.equal(parseOffsetCommitRecovery(actual, Date.parse(OFFSET_COMMIT_COMPLETED_AT) - 1), null);
  assert.equal(parseOffsetCommitRecovery(sample(), actualNow), null);
  const pending = { ...testBinding, sourceCommit: 'PENDING_REVIEW' };
  const unread = Object.defineProperty({}, 'summary', { get() { throw new Error('Evidence read before binding validation'); } });
  assert.equal(parseOffsetCommitRecovery(unread, actualNow, pending), null);
  for (const key of Object.keys(testBinding)) {
    assert.equal(parseBound(sample(), { ...testBinding, [key]: 'PENDING_REVIEW' }), null);
  }
});

test('all four post-unpause and replay combinations are accepted without inference', () => {
  for (const state of ['NO_COMMIT', 'OBSERVED'] as const) {
    for (const replays of [0, 1] as const) {
      const record = parse(sample(state, replays)); assert.ok(record);
      assert.equal(record.summary.recoveryResult.postUnpauseCommitState, state);
      assert.equal(record.summary.recoveryResult.postUnpauseCommittedOffset, state === 'NO_COMMIT' ? null : 1);
      assert.equal(record.summary.recoveryResult.completedReplays, replays);
      assert.equal(Object.keys(record.summary).length, 18);
      assert.equal(Object.keys(record.summary.recoveryResult).length, 23);
    }
  }
});

test('accepted records are normalized copies rather than references to input objects', () => {
  const value = sample(); const record = parse(value); assert.ok(record);
  assert.deepEqual(record, value); assert.notEqual(record, value);
  assert.notEqual(record.summary, value.summary); assert.notEqual(record.summary.recoveryResult, value.summary.recoveryResult);
  value.summary.recoveryResult.completedReplays = 1; value.summary.status = 'FAILED'; value.runUrl = 'PRIVATE_CANARY';
  assert.equal(record.summary.recoveryResult.completedReplays, 0); assert.equal(record.summary.status, 'PASSED');
  assert.equal(record.runUrl, testBinding.runUrl);
});

test('missing, partial, failed and unverified results never provide successful phases', () => {
  const value = sample();
  const partialSummary = { ...value.summary } as Record<string, unknown>; delete partialSummary.verifiedTests;
  const missingJvmSummary = { ...value.summary } as Record<string, unknown>; delete missingJvmSummary.jvmFailure;
  const partialResult = { ...value.summary.recoveryResult } as Record<string, unknown>; delete partialResult.childResourcesClosed;
  for (const changed of [undefined, null, false, [], 'PASS', {}, { summary: value.summary },
    { ...value, summary: null }, { ...value, summary: partialSummary }, { ...value, summary: missingJvmSummary },
    { ...value, summary: { ...value.summary, recoveryResult: partialResult } },
    { ...value, summary: { ...value.summary, status: 'FAILED' } },
    { ...value, summary: { ...value.summary, failureCode: 'COMMIT_FAILED' } },
    { ...value, summary: { ...value.summary, selectedFailure: { phase: 'COMMIT' } } },
    { ...value, summary: { ...value.summary, jvmFailure: { exitCode: 1, message: 'PRIVATE_CANARY' } } },
    { ...value, summary: { ...value.summary, verifiedTests: 0 } },
    { ...value, summary: { ...value.summary, ownedResourcesRemoved: false } },
    { ...value, summary: { ...value.summary, sourceAndArtifactsUnchanged: false } }]) {
    assert.equal(parse(changed), null);
  }
});

test('private or unknown fields are rejected at every public boundary', () => {
  const value = sample();
  for (const changed of [{ ...value, token: 'PRIVATE_CANARY' },
    { ...value, summary: { ...value.summary, containerId: 'PRIVATE_CANARY' } },
    resultChanged({ topic: 'PRIVATE_CANARY' }), resultChanged({ rawRows: [] }),
    { ...value, [Symbol('private')]: 'PRIVATE_CANARY' },
    Object.defineProperty({ ...value }, 'privateHost', { value: 'PRIVATE_CANARY' })]) {
    assert.equal(parse(changed), null);
  }
  assert.equal(parseBound(value, { ...testBinding, privatePath: 'PRIVATE_CANARY' }), null);
});

test('summary provenance, scalar types and scope limits match the complete verified contract', () => {
  const value = sample();
  for (const changes of [{ schemaVersion: true }, { scope: 'DEPLOYED_OFFSET_COMMIT_RECOVERY' }, { synthetic: false },
    { sourceCommit: 'd'.repeat(40) }, { sourceCommit: 'unknown' }, { runtimeManifestSha256: 'd'.repeat(64) },
    { surefireXmlSha256: 'd'.repeat(64) }, { expectedTests: 2 }, { expectedTests: '1' }, { verifiedTests: true },
    { operatingServicesChanged: true }, { hostOrBrokerRestartVerified: true }, { publicExecutionEnabled: true },
    { failureCode: undefined }, { selectedFailure: 'NONE' }, { jvmFailure: false }, { jvmFailure: 'null' }, { ownedResourcesRemoved: 'true' }]) {
    assert.equal(parse({ ...value, summary: { ...value.summary, ...changes } }), null);
  }
});

test('every fixed recovery fact must match, including counts, pause, CLI, export and cleanup', () => {
  const result = sample().summary.recoveryResult;
  const variable = new Set(['postUnpauseCommitState', 'postUnpauseCommittedOffset', 'completedReplays']);
  for (const [key, expected] of Object.entries(result)) {
    if (variable.has(key)) continue;
    const changed = typeof expected === 'boolean' ? !expected : typeof expected === 'number' ? expected + 1 : `${expected}-OTHER`;
    assert.equal(parse(resultChanged({ [key]: changed })), null, key);
  }
  for (const changes of [{ fixtureInput: '12' }, { finalLag: false }, { pausePersisted: 1 },
    { exported: 'true' }, { verifiedExportFiles: true }, { childResourcesClosed: null }]) {
    assert.equal(parse(resultChanged(changes)), null);
  }
});

test('commit-state pairing and replay scalar types are strict while the observations remain independent', () => {
  for (const changes of [{ postUnpauseCommitState: 'NO_COMMIT', postUnpauseCommittedOffset: 1 },
    { postUnpauseCommitState: 'OBSERVED', postUnpauseCommittedOffset: null },
    { postUnpauseCommitState: 'OBSERVED', postUnpauseCommittedOffset: 0 },
    { postUnpauseCommitState: 'OBSERVED', postUnpauseCommittedOffset: '1' },
    { postUnpauseCommitState: 'UNKNOWN' }, { postUnpauseCommittedOffset: false },
    { completedReplays: true }, { completedReplays: '0' }, { completedReplays: -1 }, { completedReplays: 2 },
    { completedReplays: 0.5 }, { completedReplays: NaN }]) {
    assert.equal(parse(resultChanged(changes)), null);
  }
});

test('binding hashes and fields are validated before an otherwise matching record', () => {
  for (const changes of [{ runtimeManifestSha256: 'A'.repeat(64) }, { runtimeManifestSha256: 'a'.repeat(63) },
    { sourceCommit: 'B'.repeat(40) }, { sourceCommit: 'b'.repeat(39) }, { sourceCommit: null },
    { surefireXmlSha256: 'C'.repeat(64) }, { surefireXmlSha256: true }]) {
    const binding = { ...testBinding, ...changes };
    const value = { ...sample(), summary: { ...sample().summary, ...changes } };
    assert.equal(parseBound(value, binding), null);
  }
  for (const binding of [null, undefined, [], {}, { ...testBinding, runUrl: undefined }]) {
    // Explicit undefined uses the reviewed production binding, so this synthetic sample must fail.
    assert.equal(parseBound(sample(), binding), null);
  }
  for (const badNow of [NaN, Infinity, -Infinity, now + 0.1]) {
    assert.equal(parseOffsetCommitRecovery(sample(), badNow, testBinding), null);
  }
});

test('run provenance and UTC completion reject other origins, ambiguous dates and future nanoseconds', () => {
  for (const runUrl of ['https://example.test/actions/runs/12345', testBinding.runUrl + '?token=PRIVATE_CANARY',
    testBinding.runUrl + '#private', 'https://github.com/DevDooly/another-repo/actions/runs/12345',
    'http://github.com/DevDooly/devdooly-platform-lab/actions/runs/12345',
    'https://github.com/DevDooly/devdooly-platform-lab/actions/runs/012345',
    'https://github.com/DevDooly/devdooly-platform-lab/actions/runs/0',
    'https://github.com/DevDooly/devdooly-platform-lab/actions/runs/' + '1'.repeat(21)]) {
    assert.equal(parseBound({ ...sample(), runUrl }, { ...testBinding, runUrl }), null);
  }
  assert.equal(parse({ ...sample(), runUrl: testBinding.runUrl + '6' }), null);
  for (const completedAt of ['2026-02-30T00:00:00Z', '2026-10-20T11:00:00+00:00', '2026-10-20T11:00:00',
    '2026-10-20T11:00:00z', '2026-10-20T11:00:00.0000000001Z', '2026-10-20T12:00:00.000000001Z',
    '2026-10-21T00:00:00Z', '2026-10-20T11:00:60Z']) {
    assert.equal(parseBound({ ...sample(), completedAt }, { ...testBinding, completedAt }), null);
  }
  assert.equal(parse({ ...sample(), completedAt: '2026-10-20T11:00:00Z' }), null);
  const completedAt = '2026-10-20T12:00:00.000000000Z';
  assert.ok(parseBound({ ...sample(), completedAt }, { ...testBinding, completedAt }));
});

test('four saved phases separate completed work, persisted pause, explicit resume and verified export', () => {
  const record = parse(sample()); assert.ok(record);
  const phases = offsetCommitPhases(record);
  assert.deepEqual(phases.map(({ id, domain, status, exportStatus }) => [id, domain, status, exportStatus]), [
    ['completed', 'JOB', 'COMPLETED', 'PENDING'], ['paused', 'RUNTIME', 'PAUSED_OPERATOR', 'PENDING'],
    ['resumed', 'RUNTIME', 'STOPPED', 'PENDING'], ['exported', 'JOB', 'COMPLETED', 'EXPORTED'],
  ]);
  assert.ok(phases[0].description.includes('12건')); assert.ok(phases[1].description.includes('OFFSET_COMMIT_FAILED'));
  assert.ok(phases[2].description.includes('일반 run')); assert.ok(phases[2].description.includes('별도 resume'));
  assert.ok(phases[3].description.includes('commit 1')); assert.ok(phases[3].description.includes('lag 0'));
  for (const phase of phases) assert.deepEqual(Object.keys(phase).sort(), ['description', 'domain', 'exportStatus', 'id', 'status', 'title']);
  assert.equal(offsetCommitPhaseKey(0, 'ArrowLeft'), 3); assert.equal(offsetCommitPhaseKey(3, 'ArrowRight'), 0);
  assert.equal(offsetCommitPhaseKey(2, 'Home'), 0); assert.equal(offsetCommitPhaseKey(1, 'End'), 3);
  for (const key of ['Tab', 'Enter', ' ', 'Escape', 'ArrowDown']) assert.equal(offsetCommitPhaseKey(2, key), null);
  for (const index of [-1, 4, 0.5, NaN, Infinity]) assert.equal(offsetCommitPhaseKey(index, 'ArrowRight'), null);
});

test('production card accepts the real record and rejects synthetic input or injected test bindings', async () => {
  const source = readFileSync(new URL('../src/components/OffsetCommitRecoveryCard.tsx', import.meta.url), 'utf8');
  let code = ts.transpileModule(source, { compilerOptions: { jsx: ts.JsxEmit.ReactJSX, module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022 } }).outputText;
  code = code.replace(/from (['"])react\1/g, `from ${JSON.stringify(import.meta.resolve('react'))}`)
    .replace(/from (['"])react\/jsx-runtime\1/g, `from ${JSON.stringify(import.meta.resolve('react/jsx-runtime'))}`)
    .replace(/from (['"])\.\.\/lib\/offset-commit-recovery\.ts\1/g,
      `from ${JSON.stringify(new URL('../src/lib/offset-commit-recovery.ts', import.meta.url).href)}`)
    .replace(/import (['"])\.\.\/styles\/offset-commit-recovery\.css\1;?/g, '');
  const { default: Card, OffsetCommitRecoveryView: View } = await import(`data:text/javascript;base64,${Buffer.from(code).toString('base64')}`);
  const actual = JSON.parse(readFileSync(new URL('../src/data/offset-commit-recovery.generated.json', import.meta.url), 'utf8'));
  const realCard = renderToStaticMarkup(createElement(Card, { record: actual }));
  assert.ok(realCard.includes('저장된 격리 검증')); assert.ok(realCard.includes(OFFSET_COMMIT_SOURCE_COMMIT));
  assert.ok(realCard.includes('>EXPORTED<')); assert.ok(!realCard.includes('공개 기록 대기'));
  for (const props of [{}, { record: sample() }, { record: { ...sample(), token: 'PRIVATE_CANARY' } },
    { record: sample(), binding: testBinding }]) {
    const pending = renderToStaticMarkup(createElement(Card, props));
    assert.ok(pending.includes('공개 기록 대기')); assert.ok(!pending.includes('PRIVATE_CANARY'));
    for (const element of ['<table', '<details', '<button', '<form', '<svg']) assert.ok(!pending.includes(element));
    assert.ok(!pending.includes('7 / 3 / 2')); assert.ok(!pending.includes('>EXPORTED<'));
  }
  for (const state of ['NO_COMMIT', 'OBSERVED'] as const) {
    for (const replays of [0, 1] as const) {
      const evidence = parse(sample(state, replays)); assert.ok(evidence);
      const ready = renderToStaticMarkup(createElement(View, { evidence }));
      assert.equal((ready.match(/<button\b/g) || []).length, 4);
      assert.equal((ready.match(/aria-pressed="true"/g) || []).length, 1);
      assert.equal((ready.match(/<details\b/g) || []).length, 1); assert.ok(!/<details\b[^>]*\bopen(?:=|\s|>)/.test(ready));
      assert.ok(ready.includes('<caption>')); assert.ok(ready.includes('PAUSED_OPERATOR')); assert.ok(ready.includes('EXPORTED'));
      assert.equal((ready.match(/<td>업무 작업\(job\)<\/td>/g) || []).length, 2);
      assert.equal((ready.match(/<td>실행\(runtime\)<\/td>/g) || []).length, 2);
      assert.ok(ready.includes(state === 'NO_COMMIT' ? '기록 없음 (null)' : 'offset 1'));
      assert.ok(ready.includes(`<strong>${replays}회</strong>`)); assert.ok(ready.includes('각각 관측한 값이며, 첫 offset 조회만으로 재전달 횟수를 추정하지 않습니다.'));
      assert.ok(ready.includes('경과 시간을 뜻하지 않습니다')); assert.ok(ready.includes('broker·호스트 재시작'));
      assert.ok(ready.includes(testBinding.runUrl)); assert.ok(ready.includes(`/blob/${testBinding.sourceCommit}/infra/offset-commit-recovery-ci/OffsetCommitRecoveryIT.java`));
      assert.ok(ready.includes('/docs/evidence/offset-commit-recovery/README.md'));
      assert.ok(ready.includes(testBinding.runtimeManifestSha256)); assert.ok(ready.includes(testBinding.surefireXmlSha256));
      assert.equal((ready.match(/target="_blank"/g) || []).length, 3);
      assert.ok(!ready.includes('<form')); assert.ok(!ready.includes('onload=')); assert.ok(!ready.includes('PRIVATE_CANARY'));
    }
  }
});
