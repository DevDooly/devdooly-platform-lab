import assert from 'node:assert/strict';
import test from 'node:test';
import { createRequire } from 'node:module';
import { readFileSync } from 'node:fs';
import { pathToFileURL } from 'node:url';

const require = createRequire(import.meta.url);
const ts = require('typescript');
const { createElement } = require('react');
const { renderToStaticMarkup } = require('react-dom/server');
const source = readFileSync(new URL('../src/components/LabExplorer.tsx', import.meta.url), 'utf8');
const parsed = ts.createSourceFile('LabExplorer.tsx', source, ts.ScriptTarget.ES2022, true, ts.ScriptKind.TSX);
// Render the real controls without importing the Lab's effects, source loaders or chart.
const statements = parsed.statements.filter((node: any) =>
  (ts.isVariableStatement(node) && node.declarationList.declarations.some((declaration: any) => declaration.name.getText(parsed) === 'statusLabel'))
  || (ts.isInterfaceDeclaration(node) && node.name.text === 'EventSearchControlsProps')
  || (ts.isFunctionDeclaration(node) && node.name?.text === 'EventSearchControls'));
assert.equal(statements.length, 3);
const componentSource = ts.createPrinter().printFile(ts.factory.updateSourceFile(parsed, statements));
const compiled = ts.transpileModule(componentSource, { compilerOptions: { jsx: ts.JsxEmit.ReactJSX,
  module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022 }, reportDiagnostics: true });
assert.equal(compiled.diagnostics.length, 0);
const output = compiled.outputText.replace(/from (['"])(react\/jsx-runtime)\1/g,
  (_unused: string, _quote: string, name: string) => `from ${JSON.stringify(pathToFileURL(require.resolve(name)).href)}`);
const { EventSearchControls } = await import(`data:text/javascript;base64,${Buffer.from(output).toString('base64')}`);

function render(overrides: Record<string, unknown> = {}): string {
  return renderToStaticMarkup(createElement(EventSearchControls, {
    status: 'ALL', query: '', reason: null, reasons: ['', 'ACCEPTED', 'all', 'reason:'],
    shown: 1000, total: 1000, disabled: false,
    onStatusChange() {}, onQueryChange() {}, onReasonChange() {}, onReset() {}, ...overrides,
  }));
}

test('search controls have explicit labels and lock together before input is available', () => {
  const html = render({ disabled: true });
  for (const id of ['event-search-query', 'event-filter', 'event-reason']) {
    assert.match(html, new RegExp(`<label for="${id}">`));
    assert.match(html, new RegExp(`<(?:input|select)[^>]*id="${id}"[^>]*disabled=""`));
  }
  assert.match(html, /<button[^>]*disabled=""[^>]*>검색·필터 초기화<\/button>/);
  assert.match(html, /placeholder="예: evt-003 또는 sensor-a"/);
  assert.doesNotMatch(render(), /disabled=""/);
});

test('empty and sentinel-like raw reasons stay distinct from all reasons', () => {
  assert.match(render(), /<option value="all" selected="">전체 사유<\/option>/);
  const empty = render({ reason: '' });
  assert.match(empty, /<option value="reason:" selected="">빈 사유 \(빈 문자열\)<\/option>/);
  assert.doesNotMatch(empty, /<option value="all" selected="">/);
  assert.match(render({ reason: 'all' }), /<option value="reason:all" selected="">&quot;all&quot;<\/option>/);
  assert.match(render({ reason: 'reason:' }), /<option value="reason:reason:" selected="">&quot;reason:&quot;<\/option>/);
});

test('conditions and an absent raw reason remain visible after changing the run', () => {
  const html = render({ status: 'FAILED', query: '  SENSOR-[a]  ', reason: 'OLD_RAW', reasons: ['ACCEPTED'], shown: 0 });
  assert.match(html, /value="  SENSOR-\[a\]  "/);
  assert.match(html, /<option value="FAILED" selected="">실패<\/option>/);
  assert.match(html, /<option value="reason:OLD_RAW" selected="">&quot;OLD_RAW&quot; · 이 실행에 없음<\/option>/);
  assert.match(html, /결과 0건 \/ 전체 1000건/);
  assert.match(html, /검색·필터 조건은 실행을 바꿔도 유지/);
  assert.match(html, /위 건수는 전체 실행 결과이며 아래 표와 흐름 선택만 좁힙니다/);
});

test('exact sensor is absent for all sensors and shows even an empty raw ID', () => {
  assert.doesNotMatch(render(), /event-exact-sensor/);
  assert.equal(render({ sensorId: null }), render());
  const html = render({ sensorId: '', onSensorClear() {}, shown: 0 });
  assert.match(html, /센서 ID 정확히 일치/);
  assert.match(html, /<code>&quot;&quot;<\/code>/);
  assert.match(html, /결과 0건 \/ 전체 1000건/);
  assert.match(html, /<button[^>]*>센서 조건 해제<\/button>/);
  assert.doesNotMatch(html, /disabled=""/);
});

test('exact sensor exposes spaces, case and markup safely and locks its clear action', () => {
  const html = render({ sensorId: '  Sensor-<b>&  ', disabled: true, onSensorClear() {} });
  assert.match(html, /<code>&quot;  Sensor-&lt;b&gt;&amp;  &quot;<\/code>/);
  assert.doesNotMatch(html, /<b>/);
  assert.match(html, /<button[^>]*disabled=""[^>]*>센서 조건 해제<\/button>/);
  assert.match(render({ sensorId: 's' }), /<button[^>]*disabled=""[^>]*>센서 조건 해제<\/button>/);
});
