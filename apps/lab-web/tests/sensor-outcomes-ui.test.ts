import assert from 'node:assert/strict';
import test from 'node:test';
import { createRequire } from 'node:module';
import { readFileSync } from 'node:fs';
import { pathToFileURL } from 'node:url';
import type { Outcome } from '../src/lib/api.ts';

const require = createRequire(import.meta.url);
const ts = require('typescript');
const { createElement } = require('react');
const { renderToStaticMarkup } = require('react-dom/server');
const source = readFileSync(new URL('../src/components/SensorOutcomeExplorer.tsx', import.meta.url), 'utf8');
const compiled = ts.transpileModule(`${source}\nexport { SensorEventActions };`, { compilerOptions: { jsx: ts.JsxEmit.ReactJSX,
  module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022 }, reportDiagnostics: true });
assert.equal(compiled.diagnostics.length, 0);
const output = compiled.outputText
  .replace(/import ['"]\.\.\/styles\/sensor-outcomes\.css['"];?\s*/g, '')
  .replace(/from (['"])(react(?:\/jsx-runtime)?)\1/g,
    (_unused: string, _quote: string, name: string) => `from ${JSON.stringify(pathToFileURL(require.resolve(name)).href)}`)
  .replace(/from (['"])\.\.\/lib\/sensor-outcomes\1/g,
    `from ${JSON.stringify(new URL('../src/lib/sensor-outcomes.ts', import.meta.url).href)}`);
const { default: SensorOutcomeExplorer, SensorEventActions } = await import(`data:text/javascript;base64,${Buffer.from(output).toString('base64')}`);
const event = (sensorId: string, status: Outcome['status'] = 'SUCCESS', reason = 'ok'): Outcome => ({
  sequence: 0, eventId: 'event', sensorId, eventTime: '2026-10-24T13:00:00Z', value: 1, status, reason,
});
function render(outcomes: Outcome[], overrides: Record<string, unknown> = {}): string {
  return renderToStaticMarkup(createElement(SensorOutcomeExplorer, {
    outcomes, runId: 'test-run', mode: 'live', observedAt: '2026-10-24T13:00:00.123456789Z',
    capturedAt: null, reportedInputCount: 1000, interactive: true, ...overrides,
  }));
}

test('sensor view distinguishes available rows from reported inputs and gives the exact rate denominator', () => {
  const markup = render([
    event('sensor-1'), event('sensor-1', 'FAILED', 'outside'), event('sensor-1', 'DUPLICATE'), event('sensor-1', 'PENDING'),
  ]);
  assert.match(markup, /응답에 나타난 센서<\/span><strong>1개/);
  assert.match(markup, /조회된 outcomes<\/span><strong>4건/);
  assert.match(markup, /보고된 입력 · inputCount<\/span><strong>1,000건/);
  assert.match(markup, /25\.00%/);
  assert.match(markup, /FAILED \/ 센서별 조회 건수 × 100/);
  assert.match(markup, /입력 건수와 조회 건수가 같아도 전체 입력의 누락 여부가 검증된 것은 아닙니다/);
  assert.match(markup, /이벤트 탭의 검색·상태·사유·페이지 조건은 적용하지 않습니다/);
  assert.match(markup, /처리 시간이나 센서 장애율을 뜻하지 않습니다/);
  assert.match(markup, /대기 · PENDING<\/dt><dd>1건/);
});

test('empty and whitespace sensor IDs and failure reasons remain visible as distinct raw strings', () => {
  const markup = render([event('', 'FAILED', ''), event(' ', 'FAILED', ' '), event('Sensor'), event('sensor')]);
  assert.match(markup, /응답에 나타난 센서<\/span><strong>4개/);
  assert.match(markup, /<code>&quot;&quot; · 빈 문자열<\/code>/);
  assert.match(markup, /<code>&quot; &quot;<\/code>/);
  assert.match(markup, /<code>&quot;Sensor&quot;<\/code>/);
  assert.match(markup, /<code>&quot;sensor&quot;<\/code>/);
  assert.match(markup, /100\.00%/);
  assert.match(markup, /FAILED 없음/);
});

test('large lists start with 20 complete sensor groups and expose incremental controls', () => {
  const markup = render(Array.from({ length: 21 }, (_, index) => event(`sensor-${index}`)));
  assert.match(markup, /전체 21개 센서 중 검색 21개 · 표시 20개/);
  assert.match(markup, /<code>&quot;sensor-19&quot;<\/code>/);
  assert.doesNotMatch(markup, /<code>&quot;sensor-20&quot;<\/code>/);
  assert.match(markup, /<button type="button">센서 20개 더 보기<\/button>/);
  assert.match(markup, /<button type="button" disabled="">처음 20개로 접기<\/button>/);
  assert.match(markup, /role="status" aria-live="polite" aria-atomic="true"/);
  assert.match(markup, /센서별 결과 카드/);
});

test('busy source controls are disabled and provenance timestamps are not reformatted', () => {
  const markup = render(Array.from({ length: 21 }, (_, index) => event(`sensor-${index}`)), {
    mode: 'recorded', interactive: false, capturedAt: '2026-10-24T13:01:00.987654321Z',
  });
  assert.match(markup, /recorded · 게시 관측/);
  assert.match(markup, /2026-10-24T13:00:00\.123456789Z/);
  assert.match(markup, /2026-10-24T13:01:00\.987654321Z/);
  assert.match(markup, /<input[^>]*disabled=""/);
  assert.match(markup, /<select[^>]*disabled=""/);
  assert.equal((markup.match(/<button /g) ?? []).length, 3);
  assert.equal((markup.match(/<button[^>]*disabled=""/g) ?? []).length, 3);
  const inputId = /<input id="([^"]+)"/.exec(markup)?.[1];
  assert.ok(inputId);
  assert.ok(markup.includes(`<label for="${inputId}">센서 ID 포함 검색</label>`));
});

test('an empty response has no imaginary sensor rows, rate, or load-more action', () => {
  const markup = render([], { mode: 'fixture', observedAt: null, capturedAt: null });
  assert.match(markup, /조회된 outcomes<\/span><strong>0건/);
  assert.match(markup, /이번 응답에 센서별로 집계할 이벤트가 없습니다/);
  assert.match(markup, /fixture · 고정 샘플 기대값/);
  assert.match(markup, /<code>null<\/code>/);
  assert.doesNotMatch(markup, /<table|0\.00%|센서 20개 더 보기/);
});

test('optional sensor event actions are present in both layouts and only failures get a failed action', () => {
  const rows = [event('sensor-1', 'FAILED', 'outside'), event('sensor-10'), event('Sensor-1')];
  const legacy = render(rows);
  assert.doesNotMatch(legacy, /sensor-event-actions|이벤트 전체 보기|실패 이벤트 보기/);
  const markup = render(rows, { onViewEvents() {} });
  assert.equal((markup.match(/class="sensor-event-actions"/g) ?? []).length, 6);
  assert.equal((markup.match(/>이벤트 전체 보기<\/button>/g) ?? []).length, 6);
  assert.equal((markup.match(/>실패 이벤트 보기<\/button>/g) ?? []).length, 2);
  assert.match(markup, /aria-label="센서 &quot;sensor-1&quot; 실패 이벤트 보기"/);
  assert.doesNotMatch(markup, /aria-label="센서 &quot;sensor-10&quot; 실패 이벤트 보기"/);
  assert.match(markup, /센서 목록의 검색·정렬은 이벤트 탭의 필터를 바꾸지 않습니다/);
  assert.match(markup, /기존 검색어·사유·선택·페이지 조건을 초기화합니다/);
  for (const text of ['조회된 outcomes</span><strong>3건', 'FAILED / 센서별 조회 건수 × 100',
    '2026-10-24T13:00:00.123456789Z', '100.00%']) {
    assert.ok(markup.includes(text));
    assert.ok(legacy.includes(text));
  }
  assert.ok(markup.indexOf('&quot;sensor-1&quot;') < markup.indexOf('&quot;sensor-10&quot;'));
  assert.ok(markup.indexOf('&quot;sensor-10&quot;') < markup.indexOf('&quot;Sensor-1&quot;'));
});

test('sensor actions preserve exact raw IDs in names and callbacks, including empty, whitespace, and markup', () => {
  for (const sensorId of ['', ' ', 'Sensor', 'sensor', '  <script> & "  ']) {
    const seen: [string, string][] = [];
    const group = { sensorId, total: 1, success: 0, failure: 1, duplicate: 0, pending: 0,
      failureRate: 100, failureReasons: [{ reason: 'outside', count: 1 }] };
    const element = SensorEventActions({ group, interactive: true,
      onViewEvents: (id: string, status: string) => seen.push([id, status]) });
    const [all, failed] = element.props.children;
    assert.equal(all.props['aria-label'], `센서 ${JSON.stringify(sensorId)} 이벤트 전체 보기`);
    assert.equal(failed.props['aria-label'], `센서 ${JSON.stringify(sensorId)} 실패 이벤트 보기`);
    all.props.onClick();
    failed.props.onClick();
    assert.deepEqual(seen, [[sensorId, 'ALL'], [sensorId, 'FAILED']]);
  }
  const markup = render([event('', 'FAILED'), event(' '), event('<script>', 'FAILED')], { onViewEvents() {} });
  assert.match(markup, /aria-label="센서 &quot;&quot; 이벤트 전체 보기"/);
  assert.match(markup, /aria-label="센서 &quot; &quot; 이벤트 전체 보기"/);
  assert.match(markup, /aria-label="센서 &quot;&lt;script&gt;&quot; 실패 이벤트 보기"/);
  assert.doesNotMatch(markup, /<script>/);
});

test('busy sensor drill actions are disabled without changing displayed rows or provenance', () => {
  const markup = render([event('sensor-1', 'FAILED'), event('sensor-10')], {
    onViewEvents() {}, interactive: false, mode: 'recorded', capturedAt: '2026-10-24T13:01:00.987654321Z',
  });
  const actions = markup.match(/<div class="sensor-event-actions">[\s\S]*?<\/div>/g) ?? [];
  assert.equal(actions.length, 4);
  assert.equal(actions.join('').match(/<button /g)?.length, 6);
  assert.equal(actions.join('').match(/<button[^>]*disabled=""/g)?.length, 6);
  assert.match(markup, /recorded · 게시 관측/);
  assert.match(markup, /2026-10-24T13:00:00\.123456789Z/);
  assert.match(markup, /2026-10-24T13:01:00\.987654321Z/);
  assert.match(markup, /조회된 outcomes<\/span><strong>2건/);
});
