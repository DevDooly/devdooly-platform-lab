import assert from 'node:assert/strict';
import test from 'node:test';
import { createRequire } from 'node:module';
import { readFileSync } from 'node:fs';
import { pathToFileURL } from 'node:url';
import type { JobObservation } from '../src/lib/job-observation.ts';
import type { JobListFilters } from '../src/lib/job-list.ts';
import { DEFAULT_JOB_FILTERS } from '../src/lib/job-list.ts';

const require = createRequire(import.meta.url);
const ts = require('typescript');
const { createElement } = require('react');
const { renderToStaticMarkup } = require('react-dom/server');
function component(file: string, imports: Record<string, string>): string {
  const compiled = ts.transpileModule(readFileSync(new URL(file, import.meta.url), 'utf8'), {
    compilerOptions: { jsx: ts.JsxEmit.ReactJSX, module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022 },
    reportDiagnostics: true,
  });
  assert.equal(compiled.diagnostics.length, 0);
  const output = compiled.outputText
    .replace(/import ['"]\.\.\/styles\/[^'"]+\.css['"];?\s*/g, '')
    .replace(/from (['"])(react(?:\/jsx-runtime)?)\1/g,
      (_unused: string, _quote: string, name: string) => `from ${JSON.stringify(pathToFileURL(require.resolve(name)).href)}`)
    .replace(/from (['"])([^'"]+)\1/g, (original: string, _quote: string, name: string) => imports[name]
      ? `from ${JSON.stringify(imports[name])}` : original);
  return `data:text/javascript;base64,${Buffer.from(output).toString('base64')}`;
}
const lifecycle = component('../src/components/JobLifecycle.tsx', {
  '../lib/job-lifecycle': new URL('../src/lib/job-lifecycle.ts', import.meta.url).href,
});
const { default: JobObservationList } = await import(component('../src/components/JobObservationList.tsx', {
  '../lib/job-list': new URL('../src/lib/job-list.ts', import.meta.url).href,
  './JobLifecycle': lifecycle,
}));

const createdAt = '2026-10-25T01:00:00.123456789Z';
const queuedAt = '2026-10-25T01:00:01.123456789Z';
const completedAt = '2026-10-25T01:00:01.123456790Z';
const counts = { input: 12, success: 7, failure: 3, duplicate: 2, pending: 0 };
const result = { sha256: 'a'.repeat(64), size: 1234 };
const failures = { sha256: 'b'.repeat(64), size: 56 };
const staged: JobObservation = { runId: 'alpha-staged', status: 'STAGING', exportStatus: 'NOT_REQUESTED',
  createdAt, sourceVerifiedAt: null, queuedAt: null, completedAt: null, exportCompletedAt: null,
  terminatedAt: null, counts: null, files: null, fileEvidence: 'NOT_AVAILABLE' };
const queued: JobObservation = { ...staged, runId: 'alpha-queued', status: 'QUEUED', sourceVerifiedAt: queuedAt, queuedAt };
const pending: JobObservation = { ...queued, runId: 'alpha-pending', status: 'COMPLETED', exportStatus: 'PENDING', completedAt,
  counts, files: { result, failures }, fileEvidence: 'EXPECTED_FROM_DB' };
const exported: JobObservation = { ...pending, runId: 'beta-exported', exportStatus: 'EXPORTED', exportCompletedAt: completedAt,
  fileEvidence: 'VERIFIED_AT_EXPORT_COMMIT' };
const cancelled: JobObservation = { ...pending, runId: 'alpha-cancelled', exportStatus: 'CANCELLED', files: null,
  fileEvidence: 'NOT_AVAILABLE', terminatedAt: '2026-10-25T01:00:02Z' };
const terminated: JobObservation = { ...queued, runId: 'beta-terminated', status: 'TERMINATED', terminatedAt: '2026-10-25T01:00:02Z' };
const jobs = [exported, staged, cancelled, queued, pending, terminated];
const render = (filters: JobListFilters = DEFAULT_JOB_FILTERS, values: readonly JobObservation[] = jobs, disabled = false): string =>
  renderToStaticMarkup(createElement(JobObservationList, { jobs: values, filters, onFiltersChange: () => {}, disabled }));
const displayed = (markup: string) => Array.from(markup.matchAll(/<article class="job-record"><div class="job-record-heading"><h3><code>([^<]+)<\/code>/g), match => match[1]);

test('default conditions show the fetched jobs in their original order with explicit list-only counts', () => {
  const markup = render();
  assert.deepEqual(displayed(markup), jobs.map(job => job.runId));
  assert.match(markup, /조회 목록 6개 중 조건 일치 6개/);
  assert.match(markup, /role="status" aria-live="polite" aria-atomic="true"/);
  assert.match(markup, /전체 DB 작업 수를 뜻하지 않습니다/);
  assert.match(markup, /runtime·슬롯·관측 출처와 시각은 목록 조건으로 바뀌지 않습니다/);
  assert.match(markup, /<label[^>]*><span>작업 ID 검색<\/span><input type="search"/);
  assert.match(markup, /<option value="ALL" selected="">전체 작업 상태<\/option>/);
  assert.match(markup, /<option value="ALL" selected="">전체 export 상태<\/option>/);
});

test('controlled search and the two state selectors intersect without replacing the selected raw query', () => {
  const markup = render({ query: '  aLPHA  ', status: 'COMPLETED', exportStatus: 'PENDING' });
  assert.deepEqual(displayed(markup), ['alpha-pending']);
  assert.match(markup, /value="  aLPHA  "/);
  assert.match(markup, /<option value="COMPLETED" selected="">DB 처리 완료 · COMPLETED<\/option>/);
  assert.match(markup, /<option value="PENDING" selected="">대기 · PENDING<\/option>/);
  assert.match(markup, /조회 목록 6개 중 조건 일치 1개/);
  assert.doesNotMatch(markup, /아직 기록된 작업이 없습니다|조건에 일치하는 작업이 없습니다/);
});

test('literal punctuation and HTML characters are harmless input, and no match does not mean no recorded jobs', () => {
  const markup = render({ query: '.*[<&"]', status: 'ALL', exportStatus: 'ALL' });
  assert.deepEqual(displayed(markup), []);
  assert.match(markup, /value="\.\*\[&lt;&amp;&quot;\]"/);
  assert.match(markup, /조회 목록 6개 중 조건 일치 0개/);
  assert.match(markup, /조건에 일치하는 작업이 없습니다/);
  assert.match(markup, /조회된 작업은 남아 있습니다/);
  assert.match(markup, /<button[^>]*type="button"[^>]*>조건 초기화<\/button>/);
  assert.doesNotMatch(markup, /아직 기록된 작업이 없습니다/);
});

test('an empty source list preserves the existing empty-record explanation rather than inventing filtered jobs', () => {
  const markup = render({ query: 'missing', status: 'TERMINATED', exportStatus: 'CANCELLED' }, []);
  assert.deepEqual(displayed(markup), []);
  assert.match(markup, /조회 목록 0개 중 조건 일치 0개/);
  assert.match(markup, /아직 기록된 작업이 없습니다/);
  assert.match(markup, /고정 예제 실행 결과와 새 worker 작업 기록은 별도입니다/);
  assert.match(markup, /공개 페이지에서는 작업을 생성하지 않습니다/);
  assert.doesNotMatch(markup, /조건에 일치하는 작업이 없습니다/);
});

test('loading disables all four list controls while keeping the retained rendered results and query visible', () => {
  const markup = render({ query: 'beta', status: 'ALL', exportStatus: 'ALL' }, jobs, true);
  assert.deepEqual(displayed(markup), ['beta-exported', 'beta-terminated']);
  assert.match(markup, /<input[^>]*disabled=""[^>]*value="beta"/);
  assert.equal((markup.match(/<select disabled="">/g) ?? []).length, 2);
  assert.match(markup, /<button[^>]*disabled=""[^>]*>조건 초기화<\/button>/);
  assert.match(markup, /조회 목록 6개 중 조건 일치 2개/);
});

test('narrowing and resetting preserve lifecycle nanoseconds, counts, file sizes, hashes and evidence wording', () => {
  const pendingMarkup = render({ query: '', status: 'COMPLETED', exportStatus: 'PENDING' });
  assert.match(pendingMarkup, /아래는 DB 결과로 만든 예상 파일 정보입니다\. 저장 확인은 아직 기록되지 않았습니다/);
  assert.match(pendingMarkup, /0\.000000001초/);
  assert.match(pendingMarkup, /2026-10-25T01:00:01\.123456790Z/);
  assert.match(pendingMarkup, /<dt>전체<\/dt><dd>12<\/dd>/);
  assert.match(pendingMarkup, /1,234 bytes/);
  assert.match(pendingMarkup, /56 bytes/);
  assert.ok(pendingMarkup.includes(result.sha256));
  assert.ok(pendingMarkup.includes(failures.sha256));
  assert.match(pendingMarkup, /현재 저장소를 재조회한 결과가 아닙니다/);
  const resetMarkup = render({ ...DEFAULT_JOB_FILTERS });
  assert.deepEqual(displayed(resetMarkup), jobs.map(job => job.runId));
  assert.match(resetMarkup, /두 파일의 저장 확인을 기록한 DB 시각이 있습니다/);
  assert.match(resetMarkup, /명시적 종료|export 취소/);
  assert.equal((resetMarkup.match(/<summary>예상 파일 SHA-256<\/summary>/g) ?? []).length, 4);
});
