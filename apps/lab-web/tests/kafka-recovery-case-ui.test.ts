import assert from 'node:assert/strict';
import test from 'node:test';
import { createRequire } from 'node:module';
import { readFileSync } from 'node:fs';
import { pathToFileURL } from 'node:url';
import type { RecoveryCase } from '../src/components/KafkaRecoveryExplorer.tsx';

const require = createRequire(import.meta.url);
const ts = require('typescript');
const { createElement } = require('react');
const { renderToStaticMarkup } = require('react-dom/server');
const source = readFileSync(new URL('../src/components/KafkaRecoveryExplorer.tsx', import.meta.url), 'utf8');
const compiled = ts.transpileModule(source, { compilerOptions: { jsx: ts.JsxEmit.ReactJSX,
  module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022 }, reportDiagnostics: true });
assert.equal(compiled.diagnostics.length, 0);
const output = compiled.outputText
  .replace(/import ['"]\.\.\/styles\/kafka-recovery-case\.css['"];?\s*/g, '')
  .replace(/from (['"])(react(?:\/jsx-runtime)?)\1/g,
    (_unused: string, _quote: string, name: string) => `from ${JSON.stringify(pathToFileURL(require.resolve(name)).href)}`);
const { default: KafkaRecoveryExplorer } = await import(`data:text/javascript;base64,${Buffer.from(output).toString('base64')}`);

// Distinct synthetic presentation values: these are not claims about a recorded experiment.
const first: RecoveryCase = {
  id: 'first', label: '첫 중단 위치', title: '첫 기록의 설명', stopPoint: '첫 기록의 중단 시점',
  dbState: '첫 기록의 DB 상태', kafkaState: '첫 기록의 Kafka 상태', resume: '첫 기록의 재개 동작',
  preserved: ['첫 기록의 보존 항목'], logEnd: 7, committedOffset: 6, lag: 1, runRows: 2, outcomeRows: 9,
};
const cases: RecoveryCase[] = [first,
  { ...first, id: 'second', label: '두 번째 중단 위치', title: '두 번째 기록의 설명', logEnd: 30 },
  { ...first, id: 'third', label: '세 번째 중단 위치', title: '세 번째 기록의 설명', logEnd: 40 },
];
const render = (): string => renderToStaticMarkup(createElement(KafkaRecoveryExplorer, { cases }));

test('initial HTML disables every stop-point radio through its native fieldset', () => {
  const markup = render();
  const fieldset = markup.match(/<fieldset\b[^>]*>[\s\S]*?<\/fieldset>/)?.[0];
  assert.ok(fieldset, 'stop-point choices must be grouped in a native fieldset');
  assert.match(fieldset, /^<fieldset\b[^>]*disabled=""/,
    'before hydration a native click must not change checked while the displayed record stays unchanged');
  const radios = [...fieldset.matchAll(/<input\b[^>]*type="radio"[^>]*>/g)].map(match => match[0]);
  assert.equal(radios.length, 3);
  assert.equal(radios.filter(input => /\bchecked=""/.test(input)).length, 1);
  assert.ok(radios.some(input => /\bchecked=""/.test(input) && /\bvalue="first"/.test(input)));
  assert.doesNotMatch(markup.replace(fieldset, ''), /<input\b[^>]*type="radio"/,
    'no stop-point radio may be left outside the disabled fieldset');
});

test('initial HTML keeps the first record and its supplied metrics readable outside the disabled choices', () => {
  const markup = render();
  const outsideChoices = markup.replace(/<fieldset\b[^>]*>[\s\S]*?<\/fieldset>/g, '');
  assert.match(outsideChoices, /<article\b/);
  for (const text of [first.title, first.stopPoint, first.dbState, first.kafkaState, first.resume, ...first.preserved]) {
    assert.ok(outsideChoices.includes(text), `first record must be available in server-rendered HTML: ${text}`);
  }
  for (const [label, value] of [
    ['최종 log end', 7], ['다음 읽을 offset', 6], ['최종 lag', 1], ['DB run 행', 2], ['DB outcome 행', 9],
  ]) assert.ok(outsideChoices.includes(`<dt>${label}</dt><dd>${value}</dd>`));
  assert.doesNotMatch(outsideChoices, /두 번째 기록의 설명|세 번째 기록의 설명/);
  assert.match(markup, /저장된 격리 시험 기록/);
});
