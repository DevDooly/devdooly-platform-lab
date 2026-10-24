import assert from 'node:assert/strict';
import test from 'node:test';
import { createRequire } from 'node:module';
import { readFileSync } from 'node:fs';
import { pathToFileURL } from 'node:url';
import type { Outcome } from '../src/lib/api.ts';
import type { EventFlowInspectorProps } from '../src/components/EventFlowInspector.tsx';

const require = createRequire(import.meta.url);
const ts = require('typescript');
const { createElement } = require('react');
const { renderToStaticMarkup } = require('react-dom/server');
const source = readFileSync(new URL('../src/components/EventFlowInspector.tsx', import.meta.url), 'utf8');
const compiled = ts.transpileModule(source, { compilerOptions: { jsx: ts.JsxEmit.ReactJSX,
  module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022 }, reportDiagnostics: true });
assert.equal(compiled.diagnostics.length, 0);
let output = compiled.outputText.replace(/^import ['"][^'"]+\.css['"];?\s*$/gm, '');
output = output.replace(/from (['"])(react(?:\/jsx-runtime)?)\1/g,
  (_unused: string, _quote: string, name: string) => `from ${JSON.stringify(pathToFileURL(require.resolve(name)).href)}`);
output = output.replace(/from ['"]\.\.\/lib\/event-flow['"]/g,
  () => `from ${JSON.stringify(new URL('../src/lib/event-flow.ts', import.meta.url).href)}`);
const { default: Component } = await import(`data:text/javascript;base64,${Buffer.from(output).toString('base64')}`);

const outcomes: Outcome[] = [
  { sequence: 1, eventId: 'same-event', sensorId: 'sensor-original', eventTime: '2026-10-24T00:00:00Z', value: 12, status: 'SUCCESS', reason: 'ACCEPTED' },
  { sequence: 2, eventId: 'event-2', sensorId: 'sensor-2', eventTime: '2026-10-24T00:00:01Z', value: 20, status: 'SUCCESS', reason: 'ACCEPTED' },
  { sequence: 3, eventId: 'event-3', sensorId: 'sensor-3', eventTime: '2026-10-24T00:00:02Z', value: 101, status: 'FAILED', reason: 'OUT_OF_RANGE' },
  { sequence: 4, eventId: 'same-event', sensorId: 'sensor-duplicate', eventTime: '2026-10-24T09:00:03+09:00', value: 77, status: 'DUPLICATE', reason: 'DUPLICATE_EVENT_ID' },
  { sequence: 5, eventId: 'event-5', sensorId: 'sensor-index-decoy', eventTime: 'invalid-time', value: 45, status: 'FAILED', reason: 'INVALID_TIMESTAMP' },
];

function render(overrides: Partial<EventFlowInspectorProps> = {}): string {
  return renderToStaticMarkup(createElement(Component, {
    outcomes, selectedSequence: 4, onSelect: () => {}, runId: 'run-selected', mode: 'recorded',
    observedAt: '2026-10-24T00:01:00Z', capturedAt: '2026-10-24T00:02:00Z', interactive: true, ...overrides,
  }));
}

function selectedPanel(html: string): string {
  const match = html.match(/<div class="event-flow-detail">([\s\S]*)<\/section>$/);
  assert.ok(match, 'selected event detail should be rendered');
  return match[1];
}

function reportedFields(html: string): Record<string, string> {
  return Object.fromEntries([...html.matchAll(/<dt>([^<]+)<\/dt><dd><code>([^<]*)<\/code><\/dd>/g)]
    .map(match => [match[1], match[2]]));
}

test('sequence selection distinguishes repeated event IDs from both the original row and array index', () => {
  const html = render();
  assert.match(html, /<option value="4" selected="">/);
  const panel = selectedPanel(html);
  assert.deepEqual(reportedFields(panel), {
    sequence: '4', eventId: 'same-event', sensorId: 'sensor-duplicate',
    'eventTime 원문': '2026-10-24T09:00:03+09:00', value: '77',
    'reason 원문': 'DUPLICATE_EVENT_ID', 'status 원문': 'DUPLICATE',
  });
  assert.match(panel, /중복으로 보고됨/);
  assert.doesNotMatch(panel, /sensor-original|sensor-index-decoy|ACCEPTED|INVALID_TIMESTAMP/);
});

test('a selected sequence absent from the current filtered outcomes does not leave a prior panel', () => {
  for (const filtered of [outcomes.filter(outcome => outcome.status === 'FAILED'), []]) {
    const html = render({ outcomes: filtered });
    assert.match(html, /<option value="" selected="">/);
    assert.doesNotMatch(html, /class="event-flow-detail"|id="event-flow-detail-title"/);
    assert.doesNotMatch(html, /sensor-duplicate|DUPLICATE_EVENT_ID|<dt>reason 원문<\/dt>|<dt>status 원문<\/dt>/);
  }
});

test('a locked fixture keeps controls disabled, its expected-value source and raw null/time fields', () => {
  const rawTime = '2026-10-24T09:00:00.123456+09:00';
  const html = render({ interactive: false, mode: 'fixture', runId: 'fixture-run', observedAt: null, capturedAt: null,
    outcomes: [{ ...outcomes[3], eventTime: rawTime, value: null, status: 'FAILED', reason: 'INVALID_INPUT' }] });
  assert.match(html, /<select[^>]*id="event-flow-select"[^>]*disabled=""/);
  const sourceLink = html.match(/<a\b[^>]*href="([^"]+)"[^>]*>/);
  assert.ok(sourceLink);
  assert.equal(sourceLink[1], 'https://github.com/DevDooly/devdooly-platform-lab/blob/fda29d1647fb40b9312bbcd50b77eeefcab926e3/apps/api/src/main/java/io/github/devdooly/platformlab/demo/SensorProcessor.java');
  assert.match(html, /<dd>fixture · 고정 샘플 기대값<\/dd>/);
  assert.equal(reportedFields(html)['실행 · runId'], 'fixture-run');
  assert.equal(reportedFields(html)['관측 · observedAt'], 'null');
  assert.equal(reportedFields(html)['파일 생성 · capturedAt'], 'null');
  const fields = reportedFields(selectedPanel(html));
  assert.equal(fields['eventTime 원문'], rawTime);
  assert.equal(fields.value, 'null');
  assert.equal(fields['reason 원문'], 'INVALID_INPUT');
  assert.equal(fields['status 원문'], 'FAILED');
  assert.match(html, /원본 null과 비유한 수를 구분할 수 없습니다/);
});
