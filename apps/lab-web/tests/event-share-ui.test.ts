import assert from 'node:assert/strict';
import test from 'node:test';
import { createRequire } from 'node:module';
import { readFileSync } from 'node:fs';
import { pathToFileURL } from 'node:url';

const require = createRequire(import.meta.url);
const ts = require('typescript');
const { createElement } = require('react');
const { renderToStaticMarkup } = require('react-dom/server');
const source = readFileSync(new URL('../src/components/EventShareControls.tsx', import.meta.url), 'utf8');
// SSR uses the real components; browser clipboard effects do not run here.
const compiled = ts.transpileModule(source, { compilerOptions: { jsx: ts.JsxEmit.ReactJSX,
  module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022 }, reportDiagnostics: true });
assert.equal(compiled.diagnostics.length, 0);
const output = compiled.outputText
  .replace(/import ['"]\.\.\/styles\/event-share\.css['"];?\s*/g, '')
  .replace(/from (['"])(react(?:\/jsx-runtime)?)\1/g,
    (_unused: string, _quote: string, name: string) => `from ${JSON.stringify(pathToFileURL(require.resolve(name)).href)}`)
  .replace(/from (['"])\.\.\/lib\/event-share\1/g,
    `from ${JSON.stringify(new URL('../src/lib/event-share.ts', import.meta.url).href)}`);
const { EventShareRequest, default: EventShareControls } = await import(`data:text/javascript;base64,${Buffer.from(output).toString('base64')}`);

function render(overrides: Record<string, unknown> = {}): string {
  return renderToStaticMarkup(createElement(EventShareRequest, {
    request: { kind: 'valid', selection: {
      runId: 'test-run', filters: { status: 'FAILED', query: '  EVT-003  ', reason: null }, sequence: 7,
    } },
    disabled: false, live: true, notice: '', onApply() {}, ...overrides,
  }));
}

test('absent and invalid share requests cannot expose an apply action', () => {
  assert.equal(render({ request: { kind: 'absent' } }), '');
  const invalid = render({ request: { kind: 'invalid' } });
  assert.match(invalid, /공유 링크 확인 필요/);
  assert.match(invalid, /현재 표시된 결과는 유지/);
  assert.doesNotMatch(invalid, /<button/);
});

test('valid request keeps raw text distinct from empty and absent conditions and escapes markup', () => {
  const raw = render({ request: { kind: 'valid', selection: {
    runId: 'old-run', filters: { status: 'PENDING', query: '  <script>  ', reason: 'all' }, sequence: 996,
  } } });
  assert.match(raw, /<code>old-run<\/code>/);
  assert.match(raw, /대기 · <code>PENDING<\/code>/);
  assert.match(raw, /<code>&quot;  &lt;script&gt;  &quot;<\/code>/);
  assert.match(raw, /<code>&quot;all&quot;<\/code>/);
  assert.match(raw, /<code>996<\/code>/);
  assert.doesNotMatch(raw, /<script>/);
  assert.match(render(), /전체 사유 · 조건 없음/);
  const empty = render({ request: { kind: 'valid', selection: {
    runId: 'test-run', filters: { status: 'ALL', query: '', reason: '' }, sequence: null,
  } } });
  assert.match(empty, /빈 검색어 · 전체 ID·센서/);
  assert.match(empty, /빈 사유 · 빈 문자열/);
  assert.match(empty, /미선택/);
  assert.doesNotMatch(empty, /전체 사유 · 조건 없음/);
});

test('fallback and busy states block apply, and the banner never calls a shared response frozen', () => {
  assert.doesNotMatch(render(), /<button[^>]*disabled=""/);
  for (const props of [{ live: false }, { disabled: true }]) {
    assert.match(render(props), /<button[^>]*disabled=""[^>]*>공유한 실행·조건 조회<\/button>/);
  }
  assert.match(render({ live: false }), /다른 출처의 같은 번호 이벤트를 대신 선택하지 않습니다/);
  assert.match(render(), /공유한 조건을 아직 적용하지 않았습니다/);
  assert.match(render(), /관측 시각을 고정한 결과는 아닙니다/);
  const applied = render({ notice: '요청한 실행에 조건을 적용했습니다.' });
  assert.match(applied, /요청한 실행에 조건을 적용했습니다/);
  assert.doesNotMatch(applied, /공유한 조건을 아직 적용하지 않았습니다/);
});

test('shared request distinguishes absent sensor selection from exact empty and raw sensor values', () => {
  const selection = { runId: 'test-run', filters: { status: 'ALL', query: '', reason: null }, sequence: null };
  const old = render({ request: { kind: 'valid', selection } });
  assert.doesNotMatch(old, /센서 ID 정확히 일치/);
  assert.equal(render({ request: { kind: 'valid', selection: {
    ...selection, filters: { ...selection.filters, sensorId: null },
  } } }), old);
  for (const sensorId of ['', ' ', 'Sensor-1', 'sensor-1', '  <script>  ']) {
    const markup = render({ request: { kind: 'valid', selection: {
      ...selection, filters: { ...selection.filters, sensorId },
    } } });
    assert.match(markup, /<dt>센서 ID 정확히 일치<\/dt>/);
    const escaped = JSON.stringify(sensorId).replaceAll('&', '&amp;').replaceAll('<', '&lt;')
      .replaceAll('>', '&gt;').replaceAll('"', '&quot;').replaceAll("'", '&#x27;');
    assert.ok(markup.includes(`<code>${escaped}</code>`));
    assert.doesNotMatch(markup, /<script>/);
    assert.equal(markup.includes('· 빈 문자열'), sensorId === '');
    assert.match(markup, /관측 시각을 고정한 결과는 아닙니다/);
  }
});

test('share controls explain exact raw sensor URL scope while preserving the existing SSR copy boundary', () => {
  const controls = (sensorId?: string | null) => renderToStaticMarkup(createElement(EventShareControls, {
    selection: { runId: 'test-run', filters: { status: 'ALL', query: '', reason: null, sensorId }, sequence: null },
    basePath: '/devdooly-platform-lab/', disabled: false,
  }));
  const old = controls();
  assert.match(old, /전체 센서 · 정확 일치 조건 없음/);
  assert.equal(controls(null), old);
  const empty = controls('');
  assert.match(empty, /ID 정확히 일치 <code>&quot;&quot;<\/code> · 빈 문자열/);
  const raw = controls(' Sensor-1 <script> ');
  assert.match(raw, /ID 정확히 일치 <code>&quot; Sensor-1 &lt;script&gt; &quot;<\/code>/);
  assert.match(raw, /검색어·사유·센서 ID 원문은 URL에 포함됩니다/);
  assert.match(raw, /응답과 관측 시각은 고정하지 않습니다/);
  assert.match(raw, /<button type="button" disabled="">실행·검색 링크 복사<\/button>/);
  assert.match(raw, /<input(?=[^>]*readOnly="")(?=[^>]*value="")(?=[^>]*disabled="")/);
  assert.doesNotMatch(raw, /<script>|유효한 공유 링크를 만들 수 없습니다/);
});
