import assert from 'node:assert/strict';
import test from 'node:test';
import { createRequire } from 'node:module';
import { readFileSync } from 'node:fs';
import { pathToFileURL } from 'node:url';

const require = createRequire(import.meta.url);
const ts = require('typescript');
const { createElement } = require('react');
const { renderToStaticMarkup } = require('react-dom/server');
const sourcePath = new URL('../src/components/IcebergPolicyScenarios.tsx', import.meta.url);
const source = readFileSync(sourcePath, 'utf8');
const compiled = ts.transpileModule(source, { compilerOptions: { jsx: ts.JsxEmit.ReactJSX,
  module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022 }, reportDiagnostics: true });
assert.equal(compiled.diagnostics.length, 0);
let output = compiled.outputText.replace(/^import ['"][^'"]+\.css['"];?\s*$/gm, '');
output = output.replace(/from (['"])(react(?:\/jsx-runtime)?)\1/g,
  (unused: string, quote: string, name: string) => `from ${JSON.stringify(pathToFileURL(require.resolve(name)).href)}`);
const { default: Component, parsePolicyScenarios } = await import(`data:text/javascript;base64,${Buffer.from(output).toString('base64')}`);
const bundle = JSON.parse(readFileSync(new URL('../src/data/iceberg-policy-scenarios.generated.json', import.meta.url), 'utf8'));
const render = (value: any = bundle, initialScenarioId?: string) => renderToStaticMarkup(createElement(Component, { bundle: value, initialScenarioId }));

test('saved public bundle has three synthetic scenarios and no live or execution claim', () => {
  const parsed = parsePolicyScenarios(bundle);
  assert.ok(parsed); assert.equal(parsed.scenarios.length, 3);
  assert.deepEqual(parsed.scenarios.map((item: any) => item.plan.snapshotCandidateCount), [0, 1, 0]);
  assert.equal(parsed.provenance.generatorSourceCommit, null);
  assert.ok(parsed.scenarios.every((item: any) => item.plan.objectCandidateCount === 0 && !item.plan.applyEnabled));
});
test('default rendering is labelled synthetic with a native labelled selector and closed details', () => {
  const html = render();
  assert.ok(html.includes('합성 정책 예제'));
  assert.ok(html.includes('for="policy-example-choice"'));
  assert.match(html, /<select\b[^>]*id="policy-example-choice"[^>]*disabled=""/);
  assert.ok(html.includes('aria-busy="true"'));
  assert.ok(html.includes('화면 조작 준비 중입니다.'));
  assert.equal((html.match(/<option\b/g) ?? []).length, 3);
  assert.ok(html.includes('CURRENT_ANCESTOR'));
  assert.ok(!/<details[^>]*\bopen(?:\s|=|>)/.test(html));
  assert.ok(html.includes('aria-live="polite"'));
});
test('detached selection presents a snapshot candidate while candidate files remain protected', () => {
  const html = render(bundle, 'detached-candidate');
  assert.ok(html.includes('OLD_DETACHED_HISTORY_ONLY'));
  assert.ok(html.includes('CANDIDATE_SNAPSHOT_NOT_EXPIRED'));
  assert.ok(html.includes('SHARED_SNAPSHOT_FILE'));
  assert.ok(html.includes('만료 검토 후보'));
  assert.ok(html.includes('객체 후보0개'));
});
test('stale selection presents suppression rather than a successful zero-candidate claim', () => {
  const html = render(bundle, 'stale-inventory');
  assert.ok(html.includes('판정 보류')); assert.ok(html.includes('STALE_INVENTORY'));
  assert.ok(html.includes('판정을 보류하며 보호한 결과'));
  assert.ok(!html.includes('보존 계획 확인'));
});
test('private extras, changed flags and malformed saved fields fail closed', () => {
  const values = [structuredClone(bundle), structuredClone(bundle), structuredClone(bundle), structuredClone(bundle)];
  values[0].rawProvider = 'PRIVATE_CANARY';
  values[1].scenarios[0].plan.applyEnabled = true;
  values[2].scenarios[0].plan.files[0].id = '/PRIVATE_CANARY';
  values[3].scenarios[0].plan.inventoryCapturedAt = 'not-a-time';
  for (const value of values) {
    assert.equal(parsePolicyScenarios(value), null);
    const html = render(value); assert.ok(html.includes('합성 계산 기록을 확인할 수 없습니다.'));
    assert.ok(!html.includes('PRIVATE_CANARY'));
  }
});
test('unknown initial choice falls back to the first saved record and no request code is present', () => {
  const html = render(bundle, 'unknown');
  assert.ok(html.includes('CURRENT_ANCESTOR'));
  assert.ok(!/\b(?:fetch|XMLHttpRequest|WebSocket)\s*\(/.test(source));
  assert.ok(!/\b(?:build_plan|Date\.now)\s*\(/.test(source));
});
