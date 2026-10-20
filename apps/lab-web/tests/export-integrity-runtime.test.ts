import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';
import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import ts from 'typescript';
import {
  EXPORT_INTEGRITY_RUNTIME_MANIFEST, EXPORT_INTEGRITY_SOURCE_COMMIT, EXPORT_INTEGRITY_RUN_URL,
  EXPORT_INTEGRITY_COMPLETED_AT, EXPORT_INTEGRITY_XML_SHA256, defaultBinding,
  exportIntegrityPhaseKey, exportIntegrityPhases, parseExportIntegrity, type ExportIntegrityBinding,
} from '../src/lib/export-integrity-runtime.ts';

const now = Date.UTC(2026, 9, 20, 12);
/** Synthetic parser/render input only. Never a public fixture or production evidence binding. */
const testBinding: ExportIntegrityBinding = {
  runtimeManifestSha256: 'a'.repeat(64), sourceCommit: 'b'.repeat(40),
  runUrl: 'https://github.com/DevDooly/devdooly-platform-lab/actions/runs/12345',
  completedAt: '2026-10-20T11:00:00.123456789Z', surefireXmlSha256: 'c'.repeat(64),
};
function sample() {
  return { runUrl: testBinding.runUrl, completedAt: testBinding.completedAt,
    summary: { schemaVersion: 1, scope: 'ISOLATED_EXPORT_INTEGRITY_RUNTIME', synthetic: true,
      sourceCommit: testBinding.sourceCommit, runtimeManifestSha256: testBinding.runtimeManifestSha256,
      status: 'PASSED', failureCode: null, selectedFailure: null, jvmFailure: null, expectedTests: 1, verifiedTests: 1,
      surefireXmlSha256: testBinding.surefireXmlSha256, ownedResourcesRemoved: true,
      sourceAndArtifactsUnchanged: true, operatingServicesChanged: false, hostOrBrokerRestartVerified: false,
      publicExecutionEnabled: false,
      integrityResult: { schemaVersion: 1, status: 'PASS', fixtureInput: 12, successCount: 7, failureCount: 3,
        duplicateCount: 2, pendingCount: 0, directDatabaseFixture: true, dispatchBrokerAck: true,
        sameSizeCorruption: true, verificationFailureObserved: true, pausePersisted: true, pauseCode: 'EXPORT_FAILED',
        runRefusedUnchanged: true, unrepairedResumeRepaused: true, corruptObjectUnchanged: true,
        explicitOwnedFixtureDeleted: true, verifiedExportFiles: 2, completedReplays: 1,
        finalEndOffset: 1, finalCommittedOffset: 1, finalLag: 0, businessRowsAndTimesUnchanged: true,
        sourceAndRawUnchanged: true, dispatchAndExportIdentityUnchanged: true, exported: true, slotFree: true,
        childResourcesClosed: true, targetStable: true } } };
}
const parse = (value: unknown) => parseExportIntegrity(value, now, testBinding);
const parseBound = (value: unknown, binding: unknown) => parseExportIntegrity(value, now, binding as ExportIntegrityBinding);
function resultChanged(changes: Record<string, unknown>) {
  const value = sample(); return { ...value, summary: { ...value.summary, integrityResult: { ...value.summary.integrityResult, ...changes } } };
}

test('production binding accepts the reviewed actual record and rejects synthetic fixtures', async () => {
  const actual = JSON.parse(readFileSync(new URL('../src/data/export-integrity-runtime.generated.json', import.meta.url), 'utf8'));
  const actualNow = Date.parse(EXPORT_INTEGRITY_COMPLETED_AT) + 1;
  assert.deepEqual(defaultBinding, {
    runtimeManifestSha256: actual.summary.runtimeManifestSha256, sourceCommit: actual.summary.sourceCommit,
    runUrl: actual.runUrl, completedAt: actual.completedAt, surefireXmlSha256: actual.summary.surefireXmlSha256,
  });
  assert.deepEqual([EXPORT_INTEGRITY_RUNTIME_MANIFEST, EXPORT_INTEGRITY_SOURCE_COMMIT, EXPORT_INTEGRITY_RUN_URL,
    EXPORT_INTEGRITY_COMPLETED_AT, EXPORT_INTEGRITY_XML_SHA256], Object.values(defaultBinding));
  assert.ok(parseExportIntegrity(actual, actualNow));
  assert.equal(parseExportIntegrity(actual, Date.parse(EXPORT_INTEGRITY_COMPLETED_AT) - 1), null);
  assert.equal(parseExportIntegrity(sample(), actualNow), null);
  const unread = Object.defineProperty({}, 'summary', { get() { throw new Error('Record read before binding validation'); } });
  for (const key of Object.keys(testBinding)) {
    assert.equal(parseBound(unread, { ...testBinding, [key]: 'PENDING_REVIEW' }), null);
    assert.equal(parseBound(sample(), { ...testBinding, [key]: 'PENDING_REVIEW' }), null);
  }
  const { default: Card } = await presentation();
  const ready = renderToStaticMarkup(createElement(Card, { record: actual }));
  assert.ok(ready.includes('저장된 격리 검증'));
  assert.equal((ready.match(/<button\b/g) || []).length, 4);
});

test('complete bound records preserve exact 18/29 contracts and return normalized copies', () => {
  const value = sample(); const record = parse(value); assert.ok(record);
  assert.deepEqual(record, value); assert.equal(Object.keys(record.summary).length, 18);
  assert.equal(Object.keys(record.summary.integrityResult).length, 29);
  assert.notEqual(record, value); assert.notEqual(record.summary, value.summary);
  assert.notEqual(record.summary.integrityResult, value.summary.integrityResult);
  value.summary.integrityResult.finalLag = 7; value.summary.integrityResult.completedReplays = 0;
  value.summary.status = 'FAILED'; value.runUrl = 'PRIVATE_CANARY';
  assert.equal(record.summary.integrityResult.finalLag, 0); assert.equal(record.summary.integrityResult.completedReplays, 1);
  assert.equal(record.summary.status, 'PASSED'); assert.equal(record.runUrl, testBinding.runUrl);
});

test('missing and partial records cannot supply successful metrics at any boundary', () => {
  const value = sample();
  for (const changed of [undefined, null, false, [], 'PASS', {}, { summary: value.summary },
    { ...value, summary: null }, { ...value, summary: [] }, { ...value, summary: { ...value.summary, integrityResult: null } }]) {
    assert.equal(parse(changed), null);
  }
  for (const key of Object.keys(value)) {
    const partial = { ...value } as Record<string, unknown>; delete partial[key]; assert.equal(parse(partial), null, key);
  }
  for (const key of Object.keys(value.summary)) {
    const partial = { ...value.summary } as Record<string, unknown>; delete partial[key];
    assert.equal(parse({ ...value, summary: partial }), null, key);
  }
  for (const key of Object.keys(value.summary.integrityResult)) {
    const partial = { ...value.summary.integrityResult } as Record<string, unknown>; delete partial[key];
    assert.equal(parse({ ...value, summary: { ...value.summary, integrityResult: partial } }), null, key);
  }
});

test('private, unknown, symbol and non-enumerable additions are rejected', () => {
  const value = sample();
  for (const changed of [{ ...value, token: 'PRIVATE_CANARY' },
    { ...value, summary: { ...value.summary, containerId: 'PRIVATE_CANARY' } },
    resultChanged({ objectKey: 'PRIVATE_CANARY' }), resultChanged({ rawRows: [] }),
    { ...value, [Symbol('private')]: 'PRIVATE_CANARY' },
    Object.defineProperty({ ...value }, 'privateHost', { value: 'PRIVATE_CANARY' }),
    { ...value, summary: Object.defineProperty({ ...value.summary }, 'privatePath', { value: 'PRIVATE_CANARY' }) },
    { ...value, summary: { ...value.summary, integrityResult: { ...value.summary.integrityResult, [Symbol('private')]: true } } }]) {
    assert.equal(parse(changed), null);
  }
  assert.equal(parseBound(value, { ...testBinding, privatePath: 'PRIVATE_CANARY' }), null);
});

test('failed, unclean, mutated-source or differently scoped summaries are not successes', () => {
  const value = sample();
  for (const changes of [{ schemaVersion: true }, { scope: 'DEPLOYED_EXPORT_INTEGRITY_RUNTIME' }, { synthetic: false },
    { status: 'FAILED' }, { failureCode: 'EXPORT_FAILED' }, { selectedFailure: { stage: 'INVARIANTS' } },
    { jvmFailure: { exitCode: 1, raw: 'PRIVATE_CANARY' } }, { jvmFailure: 'null' }, { jvmFailure: false },
    { expectedTests: 2 }, { expectedTests: '1' }, { verifiedTests: 0 }, { verifiedTests: true },
    { ownedResourcesRemoved: false }, { ownedResourcesRemoved: 'true' }, { sourceAndArtifactsUnchanged: false },
    { operatingServicesChanged: true }, { hostOrBrokerRestartVerified: true }, { publicExecutionEnabled: true },
    { failureCode: undefined }, { selectedFailure: 'NONE' }]) {
    assert.equal(parse({ ...value, summary: { ...value.summary, ...changes } }), null);
  }
});

test('every fixed integrity fact is required, including same-size corruption, real repause and explicit repair', () => {
  for (const [key, expected] of Object.entries(sample().summary.integrityResult)) {
    const changed = typeof expected === 'boolean' ? !expected : typeof expected === 'number' ? expected + 1 : `${expected}-OTHER`;
    assert.equal(parse(resultChanged({ [key]: changed })), null, key);
  }
  for (const changes of [{ fixtureInput: '12' }, { pausePersisted: 1 }, { directDatabaseFixture: 'true' },
    { explicitOwnedFixtureDeleted: 1 }, { verifiedExportFiles: true }, { completedReplays: 0 },
    { completedReplays: '1' }, { completedReplays: 0.5 }, { finalEndOffset: null },
    { finalCommittedOffset: false }, { finalLag: NaN }, { exported: 'true' }, { childResourcesClosed: null }]) {
    assert.equal(parse(resultChanged(changes)), null);
  }
});

test('source, manifest and XML identity require exact reviewed hashes and binding shape', () => {
  const value = sample();
  for (const key of ['sourceCommit', 'runtimeManifestSha256', 'surefireXmlSha256'] as const) {
    assert.equal(parse({ ...value, summary: { ...value.summary, [key]: 'd'.repeat(key === 'sourceCommit' ? 40 : 64) } }), null);
  }
  for (const changes of [{ runtimeManifestSha256: 'A'.repeat(64) }, { runtimeManifestSha256: 'a'.repeat(63) },
    { sourceCommit: 'B'.repeat(40) }, { sourceCommit: 'b'.repeat(39) }, { sourceCommit: null },
    { surefireXmlSha256: 'C'.repeat(64) }, { surefireXmlSha256: true }]) {
    assert.equal(parseBound({ ...value, summary: { ...value.summary, ...changes } }, { ...testBinding, ...changes }), null);
  }
  for (const binding of [null, undefined, [], {}, { ...testBinding, runUrl: undefined }]) {
    assert.equal(parseBound(value, binding), null);
  }
  for (const badNow of [NaN, Infinity, -Infinity, now + 0.1]) {
    assert.equal(parseExportIntegrity(value, badNow, testBinding), null);
  }
});

test('run and completion provenance reject other origins, ambiguous UTC and future nanoseconds', () => {
  for (const runUrl of ['https://example.test/actions/runs/12345', testBinding.runUrl + '?token=PRIVATE_CANARY',
    testBinding.runUrl + '#private', 'https://github.com/DevDooly/another-repo/actions/runs/12345',
    'http://github.com/DevDooly/devdooly-platform-lab/actions/runs/12345',
    'https://github.com/DevDooly/devdooly-platform-lab/actions/runs/012345',
    'https://github.com/DevDooly/devdooly-platform-lab/actions/runs/0',
    'https://github.com/DevDooly/devdooly-platform-lab/actions/runs/' + '1'.repeat(19)]) {
    assert.equal(parseBound({ ...sample(), runUrl }, { ...testBinding, runUrl }), null);
  }
  assert.equal(parse({ ...sample(), runUrl: testBinding.runUrl + '6' }), null);
  for (const completedAt of ['2026-02-30T00:00:00Z', '2026-10-20T11:00:00+00:00', '2026-10-20T11:00:00',
    '2026-10-20T11:00:00z', '2026-10-20T11:00:00.0000000001Z', '2026-10-20T12:00:00.000000001Z',
    '2026-10-21T00:00:00Z', '2026-10-20T11:00:60Z']) {
    assert.equal(parseBound({ ...sample(), completedAt }, { ...testBinding, completedAt }), null);
  }
  assert.equal(parse({ ...sample(), completedAt: '2026-10-20T11:00:00Z' }), null);
  for (const completedAt of ['2026-10-20T12:00:00Z', '2026-10-20T12:00:00.000000000Z']) {
    assert.ok(parseBound({ ...sample(), completedAt }, { ...testBinding, completedAt }));
  }
});

test('four phases separate direct fixture, persisted failure, unrepaired repause and explicitly repaired export', () => {
  const record = parse(sample()); assert.ok(record); const phases = exportIntegrityPhases(record);
  assert.deepEqual(phases.map(({ id, domain, status, exportStatus, slot }) => [id, domain, status, exportStatus, slot]), [
    ['fixture', 'JOB', 'COMPLETED', 'PENDING', '점유'],
    ['paused', 'RUNTIME', 'PAUSED_OPERATOR', 'PENDING', '점유'],
    ['repaused', 'RUNTIME', 'STOPPED → PAUSED_OPERATOR', 'PENDING', '점유'],
    ['exported', 'JOB', 'COMPLETED', 'EXPORTED', '해제'],
  ]);
  assert.ok(phases[0].description.includes('직접 DB 호출')); assert.ok(phases[0].description.includes('consumer 처리의 결과가 아닙니다'));
  assert.ok(phases[0].description.includes('result key에 같은 크기로 변조한 bytes를 저장'));
  assert.ok(!phases[0].description.includes('교체'));
  assert.ok(phases[1].description.includes('EXPORT_FAILED')); assert.ok(phases[1].description.includes('일반 run'));
  assert.ok(phases[2].description.includes('저장소를 수리하지 않았습니다')); assert.ok(phases[2].description.includes('재pause'));
  assert.ok(phases[3].description.includes('시험 코드')); assert.ok(phases[3].description.includes('한 개만 삭제'));
  assert.ok(phases[3].description.includes('별도 resume')); assert.ok(phases[3].description.includes('replay 1회'));
  assert.ok(phases[3].description.includes('end 1·commit 1·lag 0'));
  for (const phase of phases) assert.deepEqual(Object.keys(phase).sort(), ['description', 'domain', 'exportStatus', 'id', 'slot', 'status', 'title']);
});

test('shared phase keys wrap and focus indices while native activation keys remain native', () => {
  assert.equal(exportIntegrityPhaseKey(0, 'ArrowLeft'), 3); assert.equal(exportIntegrityPhaseKey(3, 'ArrowRight'), 0);
  assert.equal(exportIntegrityPhaseKey(2, 'Home'), 0); assert.equal(exportIntegrityPhaseKey(1, 'End'), 3);
  for (const key of ['Tab', 'Enter', ' ', 'Escape', 'ArrowDown']) assert.equal(exportIntegrityPhaseKey(2, key), null);
  for (const index of [-1, 4, 0.5, NaN, Infinity]) assert.equal(exportIntegrityPhaseKey(index, 'ArrowRight'), null);
});

async function presentation() {
  const source = readFileSync(new URL('../src/components/ExportIntegrityRuntimeCard.tsx', import.meta.url), 'utf8');
  let code = ts.transpileModule(source, { compilerOptions: { jsx: ts.JsxEmit.ReactJSX, module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022 } }).outputText;
  code = code.replace(/from (['"])react\1/g, `from ${JSON.stringify(import.meta.resolve('react'))}`)
    .replace(/from (['"])react\/jsx-runtime\1/g, `from ${JSON.stringify(import.meta.resolve('react/jsx-runtime'))}`)
    .replace(/from (['"])\.\.\/lib\/export-integrity-runtime\.ts\1/g,
      `from ${JSON.stringify(new URL('../src/lib/export-integrity-runtime.ts', import.meta.url).href)}`)
    .replace(/import (['"])\.\.\/styles\/export-integrity-runtime\.css\1;?/g, '');
  return import(`data:text/javascript;base64,${Buffer.from(code).toString('base64')}`);
}

test('public card stays neutral for unreviewed records and never echoes private partial records', async () => {
  const { default: Card } = await presentation();
  for (const props of [{}, { record: sample() }, { record: { ...sample(), token: 'PRIVATE_CANARY' } },
    { record: sample(), binding: testBinding },
    { record: { ...sample(), summary: { ...sample().summary, jvmFailure: { raw: 'PRIVATE_CANARY' } } } }]) {
    const pending = renderToStaticMarkup(createElement(Card, props));
    assert.ok(pending.includes('공개 기록 대기')); assert.ok(pending.includes('검증한 공개 기록을 기다리고 있습니다'));
    assert.ok(!pending.includes('PRIVATE_CANARY'));
    for (const element of ['<table', '<details', '<button', '<form', '<svg', '<a ', '<time']) assert.ok(!pending.includes(element));
    assert.ok(!pending.includes('7 / 3 / 2')); assert.ok(!pending.includes('>EXPORTED<'));
  }
});

test('validated view is compact, keyboard-addressable and explicit about fixture and repair scope', async () => {
  const { ExportIntegrityRuntimeView: View } = await presentation();
  const evidence = parse(sample()); assert.ok(evidence);
  const ready = renderToStaticMarkup(createElement(View, { evidence }));
  assert.equal((ready.match(/<button\b/g) || []).length, 4);
  assert.equal((ready.match(/aria-pressed="true"/g) || []).length, 1);
  assert.equal((ready.match(/aria-controls=/g) || []).length, 4);
  assert.ok(ready.includes('aria-live="polite"')); assert.ok(ready.includes('<caption>'));
  assert.equal((ready.match(/<details\b/g) || []).length, 1); assert.ok(!/<details\b[^>]*\bopen(?:=|\s|>)/.test(ready));
  assert.equal((ready.match(/<td>업무 작업\(job\)<\/td>/g) || []).length, 2);
  assert.equal((ready.match(/<td>실행\(runtime\)<\/td>/g) || []).length, 2);
  assert.ok(ready.includes('STOPPED → PAUSED_OPERATOR')); assert.ok(ready.includes('EXPORTED'));
  assert.ok(ready.includes('직접 DB fixture')); assert.ok(ready.includes('resume는 저장소 수리가 아니며'));
  assert.ok(ready.includes('손상 객체 한 개를 명시 삭제')); assert.ok(ready.includes('현재 운영 자료의 자동 복구를 검증한 결과는 아닙니다'));
  assert.ok(ready.includes('경과 시간을 뜻하지 않습니다')); assert.ok(ready.includes('7 / 3 / 2')); assert.ok(ready.includes('1 / 1 / 0'));
  assert.ok(ready.includes('Tab·Enter·Space')); assert.ok(ready.includes('방향키·Home·End'));
  assert.ok(ready.includes(testBinding.runUrl));
  assert.ok(ready.includes(`/blob/${testBinding.sourceCommit}/infra/export-integrity-runtime-ci/ExportIntegrityRuntimeIT.java`));
  assert.ok(ready.includes('/docs/evidence/export-integrity-runtime/README.md'));
  assert.ok(ready.includes(testBinding.runtimeManifestSha256)); assert.ok(ready.includes(testBinding.surefireXmlSha256));
  assert.equal((ready.match(/target="_blank"/g) || []).length, 3);
  assert.ok(!ready.includes('<form')); assert.ok(!ready.includes('onload=')); assert.ok(!ready.includes('PRIVATE_CANARY'));
  assert.ok(!ready.includes('전자서명')); assert.ok(!ready.includes('SLA')); assert.ok(!ready.includes('WORM'));
});
