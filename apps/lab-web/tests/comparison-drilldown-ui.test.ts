import assert from 'node:assert/strict';
import test from 'node:test';
import { createRequire } from 'node:module';
import { readFileSync } from 'node:fs';
import { pathToFileURL } from 'node:url';
import { parseEventShareSelection } from '../src/lib/event-share.ts';

const require = createRequire(import.meta.url);
const ts = require('typescript');
const { createElement } = require('react');
const { renderToStaticMarkup } = require('react-dom/server');
const source = readFileSync(new URL('../src/components/RunComparison.tsx', import.meta.url), 'utf8');
const parsed = ts.createSourceFile('RunComparison.tsx', source, ts.ScriptTarget.ES2022, true, ts.ScriptKind.TSX);
const componentNames = ['Timestamp', 'RunRecord', 'FailureReasonCount'];
// Render the real card and count links without running network or browser effects.
const statements = parsed.statements.filter((node: any) =>
  (ts.isVariableStatement(node) && node.declarationList.declarations.some((declaration: any) => declaration.name.getText(parsed) === 'count'))
  || (ts.isFunctionDeclaration(node) && componentNames.includes(node.name?.text)));
assert.equal(statements.length, 4);
const componentSource = ts.createPrinter().printFile(ts.factory.updateSourceFile(parsed, statements));
const compiled = ts.transpileModule(componentSource + '\nexport { RunRecord, FailureReasonCount };', {
  compilerOptions: { jsx: ts.JsxEmit.ReactJSX, module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022 }, reportDiagnostics: true,
});
assert.equal(compiled.diagnostics.length, 0);
const output = `import { comparisonEventPath } from ${JSON.stringify(new URL('../src/lib/comparison-drilldown.ts', import.meta.url).href)};\n`
  + compiled.outputText.replace(/from (['"])(react\/jsx-runtime)\1/g,
    (_unused: string, _quote: string, name: string) => `from ${JSON.stringify(pathToFileURL(require.resolve(name)).href)}`);
const { RunRecord, FailureReasonCount } = await import(`data:text/javascript;base64,${Buffer.from(output).toString('base64')}`);
const basePath = '/devdooly-platform-lab/';
const decode = (value: string): string => value.replaceAll('&amp;', '&').replaceAll('&quot;', '"').replaceAll('&#x27;', "'").replaceAll('&lt;', '<').replaceAll('&gt;', '>');
const hrefs = (markup: string): string[] => [...markup.matchAll(/<a\b[^>]*href="([^"]+)"/g)].map(match => decode(match[1]!));
function selection(href: string) {
  const url = new URL(href, 'https://example.test');
  assert.equal(url.pathname, basePath);
  assert.equal(url.hash, '#lab');
  const result = parseEventShareSelection(url.search);
  assert.equal(result.kind, 'valid');
  if (result.kind !== 'valid') throw new Error('Expected a valid event selection');
  return result.selection;
}
function renderCount(overrides: Record<string, unknown> = {}): string {
  return renderToStaticMarkup(createElement(FailureReasonCount, { side: 'A', runId: 'displayed-a', value: 2, reason: 'VALUE_OUT_OF_RANGE', basePath, ...overrides }));
}

test('displayed run cards expose distinct whole and FAILED links with no selected row or reason', () => {
  for (const side of ['A', 'B']) {
    const runId = side === 'A' ? 'displayed-a' : 'displayed-b';
    const markup = renderToStaticMarkup(createElement(RunRecord, {
      side, basePath, source: { path: '/api/demo/runs/' + runId, receivedAt: '2026-10-24T01:00:01Z' },
      run: { id: runId, name: 'Saved run', status: 'COMPLETED', scenario: 'baseline', seed: 42, synthetic: true,
        startedAt: null, completedAt: null, observedAt: '2026-10-24T01:00:00Z' },
    }));
    assert.deepEqual(hrefs(markup).map(selection), [
      { runId, filters: { status: 'ALL', query: '', reason: null }, sequence: null },
      { runId, filters: { status: 'FAILED', query: '', reason: null }, sequence: null },
    ]);
    assert.ok(markup.includes(`${side} 전체 이벤트 보기`));
    assert.ok(markup.includes(`${side} 실패 이벤트 보기`));
    assert.doesNotMatch(markup, /target=|aria-disabled=|<button/);
  }
});

test('observed positive failure counts preserve exact raw reasons and side labels', () => {
  for (const reason of ['', '  ', ' VALUE_OUT_OF_RANGE ', '<script>"& +한글']) {
    const markup = renderCount({ side: 'B', runId: 'displayed-b', reason });
    const links = hrefs(markup);
    assert.equal(links.length, 1);
    assert.deepEqual(selection(links[0]!), { runId: 'displayed-b', filters: { status: 'FAILED', query: '', reason }, sequence: null });
    assert.ok(decode(markup).includes(`aria-label="B 실행 · 실패 사유 ${reason === '' ? '빈 문자열' : JSON.stringify(reason)} · 2건 이벤트 보기"`));
    assert.match(markup, /2건/);
    assert.doesNotMatch(markup, /<script>|target=|aria-disabled=/);
  }
});

test('zero observed counts or invalid targets retain a plain count without a misleading link', () => {
  for (const overrides of [{ value: 0 }, { runId: '../other' }, { basePath: '//other.test/' }]) {
    const markup = renderCount(overrides);
    assert.deepEqual(hrefs(markup), []);
    assert.match(markup, /건<\/span>/);
    assert.doesNotMatch(markup, /<a\b|<button\b|aria-disabled=/);
  }
});

test('cards and desktop/mobile reason cells use displayed results even when picker IDs change', () => {
  const cardBindings: string[] = [];
  const reasonBindings: string[] = [];
  function visit(node: any) {
    if (ts.isJsxSelfClosingElement(node)) {
      const name = node.tagName.getText(parsed);
      const attributes = Object.fromEntries(node.attributes.properties.filter(ts.isJsxAttribute).map((attribute: any) => [attribute.name.text, attribute.initializer?.getText(parsed)]));
      if (name === 'RunRecord') cardBindings.push(`${attributes.side}:${attributes.run}:${attributes.basePath}`);
      if (name === 'FailureReasonCount') reasonBindings.push(`${attributes.side}:${attributes.runId}:${attributes.reason}:${attributes.basePath}`);
    }
    ts.forEachChild(node, visit);
  }
  visit(parsed);
  assert.deepEqual(cardBindings, [
    '"A":{displayed.result.left}:{basePath}', '"B":{displayed.result.right}:{basePath}',
  ]);
  assert.deepEqual(reasonBindings, [
    '"A":{displayed.result.left.id}:{reason.reason}:{basePath}', '"B":{displayed.result.right.id}:{reason.reason}:{basePath}',
    '"A":{displayed.result.left.id}:{reason.reason}:{basePath}', '"B":{displayed.result.right.id}:{reason.reason}:{basePath}',
  ]);
});
