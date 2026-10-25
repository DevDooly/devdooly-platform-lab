import assert from 'node:assert/strict';
import test from 'node:test';
import { createRequire } from 'node:module';
import { readFileSync } from 'node:fs';
import { pathToFileURL } from 'node:url';
import type { Outcome, RunDetail } from '../src/lib/api.ts';

const require = createRequire(import.meta.url);
const ts = require('typescript');
const { createElement } = require('react');
const { renderToStaticMarkup } = require('react-dom/server');
const source = readFileSync(new URL('../src/components/EventRunComparison.tsx', import.meta.url), 'utf8');
const compiled = ts.transpileModule(source, { compilerOptions: { jsx: ts.JsxEmit.ReactJSX,
  module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022 }, reportDiagnostics: true });
assert.equal(compiled.diagnostics.length, 0);
const output = compiled.outputText
  .replace(/import ['"]\.\.\/styles\/event-comparison\.css['"];?\s*/g, '')
  .replace(/from (['"])(react(?:\/jsx-runtime)?)\1/g,
    (_unused: string, _quote: string, name: string) => `from ${JSON.stringify(pathToFileURL(require.resolve(name)).href)}`)
  .replace(/from (['"])\.\.\/lib\/(event-comparison|event-share)\1/g,
    (_unused: string, _quote: string, name: string) => `from ${JSON.stringify(new URL(`../src/lib/${name}.ts`, import.meta.url).href)}`);
const { default: EventRunComparison } = await import(`data:text/javascript;base64,${Buffer.from(output).toString('base64')}`);
const event = (sequence: number, overrides: Partial<Outcome> = {}): Outcome => ({
  sequence, eventId: `event-${sequence}`, sensorId: `sensor-${sequence}`, eventTime: '2026-10-25T00:00:00Z',
  value: 1, status: 'SUCCESS', reason: 'ok', ...overrides,
});
const detail = (id: string, outcomes: Outcome[], overrides: Partial<RunDetail> = {}): RunDetail => ({
  id, name: id, status: 'COMPLETED', synthetic: true, seed: 1, inputCount: outcomes.length,
  successCount: outcomes.filter(row => row.status === 'SUCCESS').length,
  failureCount: outcomes.filter(row => row.status === 'FAILED').length,
  duplicateCount: outcomes.filter(row => row.status === 'DUPLICATE').length,
  pendingCount: outcomes.filter(row => row.status === 'PENDING').length,
  startedAt: '2026-10-25T00:00:00Z', completedAt: '2026-10-25T00:00:01Z',
  observedAt: '2026-10-25T00:00:02.123456789Z', scenario: 'synthetic-ui', description: '',
  outcomes, series: [], failureReasons: [], ...overrides,
});
const sources = { left: { path: '/api/demo/runs/left-run', receivedAt: '2026-10-25T00:00:03.987654321Z' },
  right: { path: '/api/demo/runs/right-run', receivedAt: '2026-10-25T00:00:04.000000001Z' } };
function render(left: RunDetail, right: RunDetail, overrides: Record<string, unknown> = {}): string {
  return renderToStaticMarkup(createElement(EventRunComparison, {
    left, right, sources, basePath: '/devdooly-platform-lab/', interactive: true, ...overrides,
  }));
}
const comparisonRows = (markup: string) => [...markup.matchAll(/<article aria-label="입력 순서 (\d+) 비교">([\s\S]*?)<\/article>/g)]
  .map(match => ({ sequence: Number(match[1]), markup: match[2] }));
const linkUrls = (markup: string) => [...markup.matchAll(/href="([^"]+)"/g)]
  .map(match => new URL(match[1].replaceAll('&amp;', '&'), 'https://example.test'));

test('event response comparison renders five distinct kinds in numeric sequence order and retains both kinds of field differences', () => {
  const a = [event(12), event(2), event(2, { eventId: 'same-position-second' }), event(8), event(10), event(11)];
  const b = [event(12), event(2), event(10, { value: 99, status: 'FAILED', reason: 'new-reason' }), event(11, { reason: 'changed-only-reason' })];
  const markup = render(detail('left-run', a), detail('right-run', b));
  const rows = comparisonRows(markup);
  assert.deepEqual(rows.map(row => row.sequence), [2, 8, 10, 11, 12]);
  for (const label of ['대응 모호', '한쪽 미관측', '보고된 입력 필드 다름', '판정 필드 다름', '비교 필드 같음']) {
    assert.ok(markup.includes(`<dt>${label}</dt><dd>1개</dd>`));
  }
  const differing = rows.find(row => row.sequence === 10)!.markup;
  assert.match(differing, /ecm-kind-input-different/);
  assert.match(differing, /입력 필드 차이<\/dt><dd><code>value<\/code>/);
  assert.match(differing, /판정 필드 차이<\/dt><dd><code>status · reason<\/code>/);
  assert.match(differing, /&quot;SUCCESS&quot;/);
  assert.match(differing, /&quot;FAILED&quot;/);
  assert.match(differing, /&quot;new-reason&quot;/);
  assert.match(rows.find(row => row.sequence === 11)!.markup, /ecm-kind-verdict-different/);
  assert.match(rows.find(row => row.sequence === 12)!.markup, /ecm-kind-observed-equal/);
  assert.match(markup, /두 응답의 입력 순서 5개 중 조건 일치 5개 · 표시 5개/);
});

test('ambiguous sides preserve every observed row behind native details without first-row pairing or duplicate-side links', () => {
  const a = [event(4, { eventId: 'first', status: 'FAILED', reason: 'first-reason' }),
    event(4, { eventId: 'second', status: 'DUPLICATE', reason: 'second-reason' }),
    event(4, { eventId: 'third', status: 'PENDING', reason: 'third-reason' })];
  const markup = render(detail('left-run', a), detail('right-run', [event(4, { eventId: 'single-right' })]));
  assert.match(markup, /ecm-kind-ambiguous/);
  assert.match(markup, /<details class="ecm-group-details"><summary>A 관측 행 3건 전체 보기<\/summary>/);
  assert.match(markup, /임의로 한 행을 고르거나 서로 짝짓지 않습니다/);
  assert.match(markup, /입력 필드 차이<\/dt><dd>비교 안 함/);
  assert.match(markup, /판정 필드 차이<\/dt><dd>비교 안 함/);
  for (const text of ['first', 'second', 'third', 'first-reason', 'second-reason', 'third-reason', 'single-right']) {
    assert.ok(markup.includes(`&quot;${text}&quot;`));
  }
  assert.equal((markup.match(/<h6>A 관측 행 /g) ?? []).length, 3);
  assert.equal((markup.match(/<dt>eventId<\/dt>/g) ?? []).length, 4);
  const urls = linkUrls(markup);
  assert.equal(urls.length, 1);
  assert.equal(urls[0].searchParams.get('labRun'), 'right-run');
  assert.equal(urls[0].searchParams.get('labEvent'), '4');
  const both = render(detail('left-run', a), detail('right-run', a));
  assert.equal(linkUrls(both).length, 0);
  assert.equal((both.match(/<h6>[AB] 관측 행 /g) ?? []).length, 6);
});

test('unobserved sides do not get imaginary success, verdict, or links and do not claim source input removal', () => {
  const markup = render(detail('left-run', [event(7, { status: 'FAILED', reason: 'left-only' })]), detail('right-run', []));
  const right = /<section class="ecm-side" aria-label="B 입력 순서 7 응답">([\s\S]*?)<\/section>/.exec(markup)![1];
  assert.match(right, /B · 미관측/);
  assert.match(right, /이 응답에 미관측/);
  assert.doesNotMatch(right, /<a\b|<dl\b|SUCCESS|FAILED|<dd>|관측 0건/);
  assert.match(markup, /ecm-kind-unobserved/);
  assert.match(markup, /전체 원본 입력이 빠짐없이 같다는 검증은 아닙니다/);
  assert.equal(linkUrls(markup).length, 1);
});

test('raw input and verdict fields remain escaped and distinct without date, whitespace, case, or null normalization', () => {
  const a = event(0, { eventId: '<script> & "', sensorId: ' Sensor ', eventTime: '', value: null, reason: '' });
  const b = event(0, { eventId: '<script> & "', sensorId: 'sensor', eventTime: '2026-10-25T00:00:00+00:00', value: 0, reason: '<img src=x onerror=bad>' });
  const markup = render(detail('left-run', [a]), detail('right-run', [b]));
  assert.doesNotMatch(markup, /<script>|<img\b/);
  assert.match(markup, /&lt;script&gt; &amp;/);
  assert.match(markup, /&lt;img src=x onerror=bad&gt;/);
  assert.match(markup, /<code>&quot; Sensor &quot;<\/code>/);
  assert.match(markup, /<code>&quot;sensor&quot;<\/code>/);
  assert.match(markup, /<dt>eventTime<\/dt><dd><code>&quot;&quot;<\/code>/);
  assert.match(markup, /<dt>value<\/dt><dd><code>null<\/code>/);
  assert.match(markup, /<dt>value<\/dt><dd><code>0<\/code>/);
  assert.match(markup, /<dt>reason<\/dt><dd><code>&quot;&quot;<\/code>/);
  assert.match(markup, /입력 필드 차이<\/dt><dd><code>sensorId · eventTime · value<\/code>/);
  assert.match(markup, /판정 필드 차이<\/dt><dd><code>reason<\/code>/);
  assert.match(markup, /원래 null인지/);
  assert.match(markup, /직렬화 전에 NaN·Infinity/);
  assert.match(markup, /eventTime 문자열을 같은 순간으로 정규화하지 않습니다/);
});

test('unique observed rows link only their own run and sequence with neutral filters and no frozen-response promise', () => {
  const rows = [event(5, { eventId: 'repeated-id' }), event(9, { eventId: 'repeated-id', status: 'FAILED' })];
  const markup = render(detail('left-run', rows), detail('right-run', rows));
  const urls = linkUrls(markup);
  assert.equal(urls.length, 4);
  for (const run of ['left-run', 'right-run']) for (const sequence of ['5', '9']) {
    assert.ok(urls.some(url => url.searchParams.get('labRun') === run && url.searchParams.get('labEvent') === sequence));
  }
  for (const url of urls) {
    assert.equal(url.pathname, '/devdooly-platform-lab/');
    assert.equal(url.hash, '#lab');
    assert.equal(url.searchParams.get('labStatus'), 'ALL');
    assert.equal(url.searchParams.get('labQuery'), '');
    assert.equal(url.searchParams.has('labReason'), false);
    assert.equal(url.searchParams.has('labSensor'), false);
  }
  assert.match(markup, /도착 화면에서 조회 버튼을 눌러 새 GET을 읽으므로/);
  assert.match(markup, /지금 비교한 응답·관측 시각을 고정하지 않습니다/);
  assert.equal(linkUrls(render(detail('bad/run', rows), detail('right-run', rows))).length, 2);
});

test('source details preserve independent raw timestamps, paths, reported counts, and missing timestamp nulls', () => {
  const left = detail('left-run', [event(0)], { inputCount: 1000 });
  const right = detail('right-run', [event(0), event(1)], { observedAt: null });
  const markup = render(left, right, { sources: { left: sources.left, right: { ...sources.right, receivedAt: null } } });
  assert.match(markup, /<details class="ecm-source-details"><summary>비교 출처·조회 시각 A·B 보기<\/summary>/);
  assert.match(markup, /조회된 outcomes<\/dt><dd>1건/);
  assert.match(markup, /조회된 outcomes<\/dt><dd>2건/);
  assert.match(markup, /보고된 입력 · inputCount<\/dt><dd>1,000건/);
  for (const text of [left.id, right.id, left.observedAt!, sources.left.receivedAt, `GET ${sources.left.path}`, `GET ${sources.right.path}`]) {
    assert.ok(markup.includes(text));
  }
  assert.equal((markup.match(/기록 없음 · null/g) ?? []).length, 2);
  assert.match(markup, /별도 GET 응답이며 같은 순간의 원자적 관측이 아닙니다/);
});

test('large comparisons initially show twenty complete sequence cards and busy controls and links are inactive', () => {
  const rows = Array.from({ length: 21 }, (_, index) => event(20 - index));
  const left = detail('left-run', rows), right = detail('right-run', rows);
  const ready = render(left, right);
  assert.match(ready, /두 응답의 입력 순서 21개 중 조건 일치 21개 · 표시 20개/);
  assert.deepEqual(comparisonRows(ready).map(row => row.sequence), Array.from({ length: 20 }, (_, index) => index));
  assert.match(ready, /<button type="button">입력 순서 20개 더 보기<\/button>/);
  assert.match(ready, /<button type="button" disabled="">처음 20개로 접기<\/button>/);
  assert.equal(linkUrls(ready).length, 40);
  const busy = render(left, right, { interactive: false });
  assert.doesNotMatch(busy, /<a\b/);
  assert.equal((busy.match(/class="ecm-event-disabled" aria-disabled="true"/g) ?? []).length, 40);
  assert.match(busy, /<input(?=[^>]*type="search")(?=[^>]*disabled="")/);
  assert.match(busy, /<select[^>]*disabled=""/);
  assert.equal((busy.match(/<button[^>]*disabled=""/g) ?? []).length, 2);
  assert.match(busy, /<label[^>]*>eventId·sensorId 포함 검색<\/label>/);
  assert.match(busy, /<label[^>]*>이벤트 비교 분류<\/label>/);
});

test('empty comparisons and interpretation guidance do not imply input identity, code equivalence, regression, or condition export', () => {
  const markup = render(detail('left-run', []), detail('right-run', []));
  assert.match(markup, /두 응답의 입력 순서 0개 중 조건 일치 0개 · 표시 0개/);
  assert.match(markup, /두 응답에 비교할 이벤트 행이 없습니다/);
  assert.equal(comparisonRows(markup).length, 0);
  assert.equal(linkUrls(markup).length, 0);
  assert.doesNotMatch(markup, /입력 순서 20개 더 보기/);
  assert.match(markup, /sequence는 입력 위치를 맞추는 기준/);
  assert.match(markup, /같은 이벤트나 같은 원본 입력임을 증명하지 않습니다/);
  assert.match(markup, /전체 원본 입력·앞선 처리 문맥·실행 코드가 같다는 뜻은 아닙니다/);
  assert.match(markup, /회귀·수정 효과·원인을 증명하지 않습니다/);
  assert.match(markup, /추가 GET을 요청하지 않습니다/);
  assert.match(markup, /기존 비교 CSV는 실행 전체 요약이며 이 이벤트 목록을 담지 않습니다/);
  assert.match(markup, /기존 A·B ID 공유 링크도 이 목록의 검색·분류·표시 개수를 저장하지 않습니다/);
});
