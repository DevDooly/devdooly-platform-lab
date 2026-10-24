import assert from 'node:assert/strict';
import test from 'node:test';
import { createRequire } from 'node:module';
import { readFileSync } from 'node:fs';
import { pathToFileURL } from 'node:url';

const require = createRequire(import.meta.url);
const ts = require('typescript');
const { createElement } = require('react');
const { renderToStaticMarkup } = require('react-dom/server');
const source = readFileSync(new URL('../src/components/EventTablePagination.tsx', import.meta.url), 'utf8');
const compiled = ts.transpileModule(source, { compilerOptions: { jsx: ts.JsxEmit.ReactJSX,
  module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022 }, reportDiagnostics: true });
assert.equal(compiled.diagnostics.length, 0);
const output = compiled.outputText
  .replace(/import ['"]\.\.\/styles\/event-pagination\.css['"];?\s*/g, '')
  .replace(/from (['"])(react\/jsx-runtime)\1/g,
    (_unused: string, _quote: string, name: string) => `from ${JSON.stringify(pathToFileURL(require.resolve(name)).href)}`)
  .replace(/from (['"])\.\.\/lib\/event-pagination\1/g,
    `from ${JSON.stringify(new URL('../src/lib/event-pagination.ts', import.meta.url).href)}`);
const { default: EventTablePagination } = await import(`data:text/javascript;base64,${Buffer.from(output).toString('base64')}`);

function render(overrides: Record<string, unknown> = {}): string {
  return renderToStaticMarkup(createElement(EventTablePagination, {
    page: { rows: [], index: 0, totalPages: 40, total: 1000, start: 1, end: 25 }, pageSize: 25,
    selectedSequence: null, selectedPage: null, disabled: false, position: 'top',
    onPageChange() {}, onPageSizeChange() {}, ...overrides,
  }));
}
function disabledButton(markup: string, name: string): boolean {
  return new RegExp(`<button[^>]*disabled=""[^>]*>${name}</button>`).test(markup);
}

test('range and boundary controls identify the current slice without reducing whole-result actions', () => {
  const first = render();
  assert.match(first, /검색 1,000건 중 1–25행 · 1 \/ 40페이지/);
  assert.ok(disabledButton(first, '처음')); assert.ok(disabledButton(first, '이전'));
  assert.equal(disabledButton(first, '다음'), false); assert.equal(disabledButton(first, '마지막'), false);
  assert.match(first, /흐름 보기와 CSV·JSON 저장은 검색 조건에 맞는 전체 이벤트/);
  const last = render({ page: { rows: [], index: 39, totalPages: 40, total: 999, start: 976, end: 999 } });
  assert.match(last, /검색 999건 중 976–999행 · 40 \/ 40페이지/);
  assert.equal(disabledButton(last, '처음'), false); assert.equal(disabledButton(last, '이전'), false);
  assert.ok(disabledButton(last, '다음')); assert.ok(disabledButton(last, '마지막'));
});

test('zero results have no imaginary page and still allow changing row size when idle', () => {
  const empty = render({ page: { rows: [], index: 0, totalPages: 0, total: 0, start: 0, end: 0 } });
  assert.match(empty, /검색 0건 · 표시할 행이 없습니다/);
  assert.doesNotMatch(empty, /1 \/ 0페이지/);
  for (const name of ['처음', '이전', '다음', '마지막']) assert.ok(disabledButton(empty, name));
  assert.doesNotMatch(empty, /<select[^>]*disabled=""/);
  assert.match(empty, /<option value="25" selected="">25행<\/option>/);
  assert.match(empty, /<option value="50">50행<\/option>/);
  assert.match(empty, /<option value="100">100행<\/option>/);
});

test('top and bottom groups have unique associated labels and every busy control is disabled', () => {
  const top = render({ disabled: true, selectedSequence: 0, selectedPage: 3 });
  const bottom = render({ position: 'bottom' });
  assert.match(top, /aria-label="이벤트 표 페이지 · 위"/);
  assert.match(bottom, /aria-label="이벤트 표 페이지 · 아래"/);
  assert.match(top, /for="event-page-size-top"/); assert.match(top, /id="event-page-size-top"/);
  assert.match(bottom, /for="event-page-size-bottom"/); assert.match(bottom, /id="event-page-size-bottom"/);
  assert.match(top, /<select[^>]*disabled=""/);
  assert.equal((top.match(/<button /g) ?? []).length, 5);
  assert.equal((top.match(/<button[^>]*disabled=""/g) ?? []).length, 5);
});

test('selection zero is valid, and only an off-page selection exposes a jump without clearing it', () => {
  const here = render({ selectedSequence: 0, selectedPage: 0 });
  assert.match(here, /선택한 이벤트 0번 · 현재 페이지에 있습니다/);
  assert.doesNotMatch(here, /선택한 이벤트 행으로 이동/);
  const away = render({ selectedSequence: 996, selectedPage: 39 });
  assert.match(away, /선택한 이벤트 996번 · 40페이지에 있습니다/);
  assert.match(away, /<button[^>]*>선택한 이벤트 행으로 이동<\/button>/);
  assert.doesNotMatch(render({ selectedSequence: 996, selectedPage: null }), /선택한 이벤트 996번/);
});
