import assert from 'node:assert/strict';
import test from 'node:test';
import { readFileSync } from 'node:fs';
import { createRequire } from 'node:module';

const ts = createRequire(import.meta.url)('typescript');
const source = readFileSync(new URL('../src/components/LabExplorer.tsx', import.meta.url), 'utf8');
const ast = ts.createSourceFile('LabExplorer.tsx', source, ts.ScriptTarget.ES2022, true, ts.ScriptKind.TSX);
let handler: any;
function visit(node: any) {
  if (ts.isFunctionDeclaration(node) && node.name?.text === 'handleTabKey') handler = node;
  ts.forEachChild(node, visit);
}
visit(ast);
assert.ok(handler);
const javascript = ts.transpileModule(ts.createPrinter().printNode(ts.EmitHint.Unspecified, handler, ast), {
  compilerOptions: { target: ts.ScriptTarget.ES2022 },
}).outputText;

test('actual result-tab keyboard handler cycles all three views and moves focus with selection', () => {
  for (const [id, key, expected] of [
    ['chart', 'ArrowRight', 'events'], ['events', 'ArrowRight', 'sensors'], ['sensors', 'ArrowRight', 'chart'],
    ['chart', 'ArrowLeft', 'sensors'], ['sensors', 'ArrowLeft', 'events'], ['events', 'ArrowLeft', 'chart'],
    ['events', 'Home', 'chart'], ['chart', 'End', 'sensors'],
  ]) {
    const selected: string[] = [], focused: string[] = [];
    let prevented = false;
    const handle = new Function('setTab', 'document', javascript + '; return handleTabKey;')(
      (value: string) => selected.push(value), { getElementById: (value: string) => ({ focus: () => focused.push(value) }) });
    handle({ key, currentTarget: { id: id + '-tab' }, preventDefault: () => { prevented = true; } });
    assert.deepEqual(selected, [expected]); assert.deepEqual(focused, [expected + '-tab']); assert.ok(prevented);
  }
});

test('result-tab handler leaves ordinary Tab and modified arrow keys to the browser', () => {
  const handle = new Function('setTab', 'document', javascript + '; return handleTabKey;')(
    () => assert.fail('must not change selection'), { getElementById: () => assert.fail('must not move focus') });
  for (const modifiers of [{ key: 'Tab' }, { key: 'ArrowRight', ctrlKey: true }, { key: 'ArrowLeft', altKey: true }, { key: 'End', metaKey: true }]) {
    handle({ currentTarget: { id: 'chart-tab' }, preventDefault: () => assert.fail('must not prevent default'), ...modifiers });
  }
});
