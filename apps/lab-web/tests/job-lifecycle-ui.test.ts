import assert from 'node:assert/strict';
import test from 'node:test';
import { createRequire } from 'node:module';
import { readFileSync } from 'node:fs';
import { pathToFileURL } from 'node:url';
import type { JobObservation } from '../src/lib/job-observation.ts';

const require = createRequire(import.meta.url);
const ts = require('typescript');
const { createElement } = require('react');
const { renderToStaticMarkup } = require('react-dom/server');
const source = readFileSync(new URL('../src/components/JobLifecycle.tsx', import.meta.url), 'utf8');
const compiled = ts.transpileModule(source, { compilerOptions: { jsx: ts.JsxEmit.ReactJSX,
  module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022 }, reportDiagnostics: true });
assert.equal(compiled.diagnostics.length, 0);
const output = compiled.outputText
  .replace(/import ['"]\.\.\/styles\/job-lifecycle\.css['"];?\s*/g, '')
  .replace(/from (['"])(react(?:\/jsx-runtime)?)\1/g,
    (_unused: string, _quote: string, name: string) => `from ${JSON.stringify(pathToFileURL(require.resolve(name)).href)}`)
  .replace(/from (['"])\.\.\/lib\/job-lifecycle\1/g,
    `from ${JSON.stringify(new URL('../src/lib/job-lifecycle.ts', import.meta.url).href)}`);
const { default: JobLifecycle } = await import(`data:text/javascript;base64,${Buffer.from(output).toString('base64')}`);

const createdAt = '2026-10-24T14:00:00.123456789Z';
const queuedAt = '2026-10-24T14:00:01.123456789Z';
const completedAt = '2026-10-24T14:00:01.123456790Z';
const counts = { input: 0, success: 0, failure: 0, duplicate: 0, pending: 0 };
const file = { sha256: 'a'.repeat(64), size: 2 };
const staged: JobObservation = { runId: 'test-job', status: 'STAGING', exportStatus: 'NOT_REQUESTED',
  createdAt, sourceVerifiedAt: null, queuedAt: null, completedAt: null, exportCompletedAt: null,
  terminatedAt: null, counts: null, files: null, fileEvidence: 'NOT_AVAILABLE' };
const queued: JobObservation = { ...staged, status: 'QUEUED', sourceVerifiedAt: queuedAt, queuedAt };
const pending: JobObservation = { ...queued, status: 'COMPLETED', exportStatus: 'PENDING', completedAt,
  counts, files: { result: file, failures: file }, fileEvidence: 'EXPECTED_FROM_DB' };
const render = (job: JobObservation): string => renderToStaticMarkup(createElement(JobLifecycle, { job }));
const recordedSteps = (markup: string) => Array.from(markup.matchAll(/<li data-stage="([^"]+)" data-recorded="true"/g), match => match[1]);

test('staging shows recorded creation and explicit missing stages without invented zero intervals', () => {
  const markup = render(staged);
  assert.deepEqual(recordedSteps(markup), ['created']);
  assert.equal((markup.match(/data-recorded="false"/g) ?? []).length, 3);
  assert.equal((markup.match(/<dd>미기록<\/dd>/g) ?? []).length, 2);
  assert.equal((markup.match(/미기록 · <code>null<\/code>/g) ?? []).length, 5);
  assert.doesNotMatch(markup, /<dd>0초<\/dd>|슬롯 해제|export 취소 기록/);
  assert.match(markup, /<details class="job-lifecycle-raw"><summary>원시 시각 6개 보기 · UTC<\/summary>/);
  assert.doesNotMatch(markup, /<details[^>]* open/);
});

test('queued records source verification and queue registration together without inferring Kafka acknowledgement', () => {
  const markup = render(queued);
  assert.deepEqual(recordedSteps(markup), ['created', 'verified-queued']);
  assert.match(markup, /원본 검증·대기 등록/);
  assert.match(markup, /Kafka 발행 확인이나 처리 시작 시각은 아닙니다/);
  assert.match(markup, /미기록으로 현재 대기·실행·실패를 판단하지 않습니다/);
  assert.match(markup, /sourceVerifiedAt<\/code><\/dt><dd><code><time dateTime="2026-10-24T14:00:01\.123456789Z">2026-10-24T14:00:01\.123456789Z<\/time>/);
  assert.match(markup, /대기 등록 · <code>queuedAt<\/code>/);
});

test('DB complete and pending export remain distinct, preserving a one-nanosecond record gap', () => {
  const markup = render(pending);
  assert.deepEqual(recordedSteps(markup), ['created', 'verified-queued', 'completed']);
  assert.match(markup, /DB 처리 완료는 기록됐지만 저장 확인 commit은 미기록입니다/);
  assert.match(markup, /<dd>0\.000000001초<\/dd>/);
  assert.match(markup, /<dd>미기록<\/dd>/);
  assert.match(markup, /처리·대기 시간을 나누거나 Kafka·S3 지연을 측정한 값은 아닙니다/);
  assert.doesNotMatch(markup, /슬롯 해제|저장 성공|export 취소 기록/);
});

test('export commit retains exact raw timestamps and displays zero as a recorded interval', () => {
  const job: JobObservation = { ...pending, exportStatus: 'EXPORTED', exportCompletedAt: completedAt,
    fileEvidence: 'VERIFIED_AT_EXPORT_COMMIT' };
  const markup = render(job);
  assert.deepEqual(recordedSteps(markup), ['created', 'verified-queued', 'completed', 'exported']);
  assert.match(markup, /<dd>0초<\/dd>/);
  for (const field of ['createdAt', 'sourceVerifiedAt', 'queuedAt', 'completedAt', 'exportCompletedAt', 'terminatedAt']) {
    assert.ok(markup.includes(`<code>${field}</code>`));
  }
  assert.match(markup, /exportCompletedAt<\/code><\/dt><dd><code><time dateTime="2026-10-24T14:00:01\.123456790Z">2026-10-24T14:00:01\.123456790Z<\/time>/);
  assert.doesNotMatch(markup, /DB 처리 완료는 기록됐지만|export 취소 기록/);
});

test('cancelled export adds an explicit termination branch without a successful export or slot-release claim', () => {
  const job: JobObservation = { ...pending, exportStatus: 'CANCELLED', files: null,
    fileEvidence: 'NOT_AVAILABLE', terminatedAt: '2026-10-24T14:01:00Z' };
  const markup = render(job);
  assert.deepEqual(recordedSteps(markup), ['created', 'verified-queued', 'completed', 'terminated']);
  assert.match(markup, /export 취소 기록 · 저장 확인 commit은 미기록입니다/);
  assert.match(markup, /data-stage="exported" data-recorded="false"/);
  assert.match(markup, /<dd>미기록<\/dd>/);
  assert.doesNotMatch(markup, /슬롯 해제|저장 성공|data-stage="exported" data-recorded="true"/);
});

test('pre-DB termination stays outside the successful path and preserves unrecorded intervals', () => {
  const markup = render({ ...queued, status: 'TERMINATED', terminatedAt: '2026-10-24T14:01:00.000000009Z' });
  assert.deepEqual(recordedSteps(markup), ['created', 'verified-queued', 'terminated']);
  assert.match(markup, /명시적 종료 기록이며, 성공한 export 확인을 뜻하지 않습니다/);
  assert.equal((markup.match(/<dd>미기록<\/dd>/g) ?? []).length, 2);
  assert.match(markup, /2026-10-24T14:01:00\.000000009Z/);
  assert.doesNotMatch(markup, /슬롯 해제|export 취소 기록|data-stage="completed" data-recorded="true"/);
});
