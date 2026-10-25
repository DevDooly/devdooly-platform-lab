import assert from 'node:assert/strict';
import test from 'node:test';
import { createRequire } from 'node:module';
import { readFileSync } from 'node:fs';
import { pathToFileURL } from 'node:url';
import { isRunDetail, type Outcome, type RunDetail } from '../src/lib/api.ts';

const require = createRequire(import.meta.url);
const ts = require('typescript');
const { createElement } = require('react');
const { renderToStaticMarkup } = require('react-dom/server');
const source = readFileSync(new URL('../src/components/SensorRunComparison.tsx', import.meta.url), 'utf8');
const compiled = ts.transpileModule(source, { compilerOptions: { jsx: ts.JsxEmit.ReactJSX,
  module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022 }, reportDiagnostics: true });
assert.equal(compiled.diagnostics.length, 0);
const output = compiled.outputText
  .replace(/import ['"]\.\.\/styles\/sensor-comparison\.css['"];?\s*/g, '')
  .replace(/from (['"])(react(?:\/jsx-runtime)?)\1/g,
    (_unused: string, _quote: string, name: string) => `from ${JSON.stringify(pathToFileURL(require.resolve(name)).href)}`)
  .replace(/from (['"])\.\.\/lib\/(sensor-comparison|event-share)\1/g,
    (_unused: string, _quote: string, name: string) => `from ${JSON.stringify(new URL(`../src/lib/${name}.ts`, import.meta.url).href)}`);
const { default: SensorRunComparison } = await import(`data:text/javascript;base64,${Buffer.from(output).toString('base64')}`);
const event = (sensorId: string, status: Outcome['status'] = 'SUCCESS', reason = 'ok'): Outcome => ({
  sequence: 0, eventId: 'event', sensorId, eventTime: '2026-10-25T00:00:00Z', value: 1, status, reason,
});
const detail = (id: string, outcomes: Outcome[], overrides: Partial<RunDetail> = {}): RunDetail => ({
  id, name: id, status: 'COMPLETED', synthetic: true, seed: 1, inputCount: outcomes.length,
  successCount: outcomes.filter(row => row.status === 'SUCCESS').length,
  failureCount: outcomes.filter(row => row.status === 'FAILED').length,
  duplicateCount: outcomes.filter(row => row.status === 'DUPLICATE').length,
  pendingCount: outcomes.filter(row => row.status === 'PENDING').length,
  startedAt: '2026-10-25T00:00:00Z', completedAt: '2026-10-25T00:00:01Z',
  observedAt: '2026-10-25T00:00:02.123456789Z', scenario: 'synthetic-ui', description: '',
  outcomes: outcomes.map((row, sequence) => ({ ...row, sequence })), series: [], failureReasons: [], ...overrides,
});
const sources = { left: { path: '/api/demo/runs/left-run', receivedAt: '2026-10-25T00:00:03.987654321Z' },
  right: { path: '/api/demo/runs/right-run', receivedAt: '2026-10-25T00:00:04.000000001Z' } };
function render(left: RunDetail, right: RunDetail, overrides: Record<string, unknown> = {}): string {
  return renderToStaticMarkup(createElement(SensorRunComparison, {
    left, right, sources, basePath: '/devdooly-platform-lab/', interactive: true, ...overrides,
  }));
}
const tableRows = (markup: string) => [...(/<tbody>([\s\S]*?)<\/tbody>/.exec(markup)?.[1] ?? '').matchAll(/<tr>([\s\S]*?)<\/tr>/g)].map(match => match[1]);
const cells = (row: string) => [...row.matchAll(/<td>([\s\S]*?)<\/td>/g)].map(match => match[1]);
const linkUrls = (markup: string) => [...markup.matchAll(/href="([^"]+)"/g)].map(match => new URL(match[1].replaceAll('&amp;', '&'), 'https://example.test'));

test('sensor comparison preserves each response source and distinguishes observed rows from reported input', () => {
  const left = detail('left-run', [event('s', 'FAILED')], { inputCount: 1000, successCount: 999 });
  const right = detail('right-run', [event('s'), event('s', 'PENDING')], { observedAt: '2026-10-25T00:00:05.000000009Z' });
  assert.ok(isRunDetail(left)); assert.ok(isRunDetail(right));
  const markup = render(left, right);
  assert.match(markup, /A · 집계 출처/);
  assert.match(markup, /B · 집계 출처/);
  assert.match(markup, /조회된 outcomes<\/dt><dd>1건/);
  assert.match(markup, /보고된 입력 · inputCount<\/dt><dd>1,000건/);
  assert.match(markup, /조회된 outcomes<\/dt><dd>2건/);
  for (const raw of [left.id, right.id, left.observedAt!, right.observedAt!, sources.left.receivedAt, sources.right.receivedAt,
    `GET ${sources.left.path}`, `GET ${sources.right.path}`]) assert.ok(markup.includes(raw));
  assert.match(markup, /같은 순간의 원자적 관측이 아닙니다/);
  assert.match(markup, /전체 입력의 누락 여부가 검증된 것은 아닙니다/);
  assert.match(markup, /분모는 각 센서의 조회 건수입니다/);
});

test('sensor comparison renders all five B minus A counts and the observed-sensor percentage-point difference', () => {
  const left = detail('left-run', [event('shared'), event('shared'), event('shared', 'FAILED'), event('shared', 'DUPLICATE')]);
  const right = detail('right-run', [event('shared'), event('shared', 'FAILED'), event('shared', 'FAILED'), event('shared', 'FAILED'), event('shared', 'PENDING')]);
  const markup = render(left, right);
  const [a, b, delta] = cells(tableRows(markup)[0]);
  for (const text of ['조회</dt><dd>4건', '성공</dt><dd>2건', '실패</dt><dd>1건', '중복</dt><dd>1건', '대기</dt><dd>0건', '25.00%']) assert.ok(a.includes(text));
  for (const text of ['조회</dt><dd>5건', '성공</dt><dd>1건', '실패</dt><dd>3건', '중복</dt><dd>0건', '대기</dt><dd>1건', '60.00%']) assert.ok(b.includes(text));
  for (const text of ['조회</dt><dd>+1건', '성공</dt><dd>−1건', '실패</dt><dd>+2건', '중복</dt><dd>−1건', '대기</dt><dd>+1건', '+35.00%p']) assert.ok(delta.includes(text));
  assert.match(markup, /건수·관측 차이 있음/);
  assert.match(markup, /차이는 성능·장애율·개선 효과나 원인을 증명하지 않습니다/);
});

test('one-sided observations are not turned into zero counts, deltas, or links for the unobserved side', () => {
  const markup = render(detail('left-run', [event('only-a')]), detail('right-run', [event('only-b', 'FAILED')]));
  const [aRow, bRow] = tableRows(markup);
  const aCells = cells(aRow), bCells = cells(bRow);
  for (const missing of [aCells[1], bCells[0]]) {
    assert.match(missing, /이 응답에 미관측/);
    assert.doesNotMatch(missing, /<a|<dl|0건|0\.00%/);
  }
  for (const delta of [aCells[2], bCells[2]]) {
    assert.match(delta, /산정 안 함 · 한쪽 응답에 미관측/);
    assert.doesNotMatch(delta, /<dl|[+−]\d+건|%p/);
  }
  const selections = linkUrls(markup).map(url => [url.searchParams.get('labRun'), url.searchParams.get('labSensor'), url.searchParams.get('labStatus')]);
  assert.ok(selections.some(([run, sensor, status]) => run === 'left-run' && sensor === 'only-a' && status === 'ALL'));
  assert.ok(selections.some(([run, sensor, status]) => run === 'right-run' && sensor === 'only-b' && status === 'FAILED'));
  assert.ok(!selections.some(([run, sensor]) => run === 'right-run' && sensor === 'only-a'));
  assert.ok(!selections.some(([run, sensor]) => run === 'left-run' && sensor === 'only-b'));
  assert.match(markup, /실제 센서의 추가·삭제·누락을 단정하지 않습니다/);
});

test('event links preserve raw exact IDs including empty, whitespace, case, and HTML, while unsafe UTF-16 has no link', () => {
  const ids = ['', ' ', 'Sensor', 'sensor', 'sensor-1', 'sensor-10', '<script> & "', '\ud800'];
  const rows = ids.map(sensorId => event(sensorId, 'FAILED'));
  const markup = render(detail('left-run', rows), detail('right-run', rows));
  assert.match(markup, /<code>&quot;&quot; · 빈 문자열<\/code>/);
  assert.match(markup, /<code>&quot; &quot;<\/code>/);
  assert.match(markup, /<code>&quot;Sensor&quot;<\/code>/);
  assert.match(markup, /<code>&quot;sensor&quot;<\/code>/);
  assert.doesNotMatch(markup, /<script>/);
  const urls = linkUrls(markup);
  assert.equal(urls.length, 7 * 2 * 2 * 2); // Safe IDs, sides, statuses, desktop/mobile.
  for (const sensorId of ids.slice(0, -1)) {
    for (const side of ['left-run', 'right-run']) for (const status of ['ALL', 'FAILED']) {
      assert.ok(urls.some(url => url.searchParams.get('labSensor') === sensorId && url.searchParams.get('labRun') === side && url.searchParams.get('labStatus') === status));
    }
  }
  for (const url of urls) {
    assert.equal(url.pathname, '/devdooly-platform-lab/');
    assert.equal(url.hash, '#lab');
    assert.equal(url.searchParams.get('labQuery'), '');
    assert.equal(url.searchParams.has('labReason'), false);
    assert.equal(url.searchParams.has('labEvent'), false);
    assert.equal(url.searchParams.has('labSensor'), true);
    assert.notEqual(url.searchParams.get('labSensor'), '\ufffd');
  }
});

test('only positive failed counts get failed links and busy views have no active links or controls', () => {
  const rows = Array.from({ length: 21 }, (_, index) => event(`sensor-${index}`));
  const left = detail('left-run', rows), right = detail('right-run', rows);
  const ready = render(left, right);
  assert.ok(linkUrls(ready).length > 0);
  assert.ok(linkUrls(ready).every(url => url.searchParams.get('labStatus') === 'ALL'));
  const busy = render(left, right, { interactive: false });
  assert.doesNotMatch(busy, /<a\b/);
  assert.match(busy, /class="scm-event-disabled" aria-disabled="true"/);
  assert.match(busy, /<input(?=[^>]*type="search")(?=[^>]*disabled="")/);
  assert.match(busy, /<input(?=[^>]*type="checkbox")(?=[^>]*disabled="")/);
  assert.match(busy, /<select[^>]*disabled=""/);
  assert.equal((busy.match(/<button /g) ?? []).length, 2);
  assert.equal((busy.match(/<button[^>]*disabled=""/g) ?? []).length, 2);
  assert.match(busy, /2026-10-25T00:00:02\.123456789Z/);
});

test('large sensor unions start at 20 complete groups in both layouts and keep their first-seen ordering', () => {
  const rows = Array.from({ length: 21 }, (_, index) => event(`sensor-${index}`));
  const markup = render(detail('left-run', rows), detail('right-run', rows));
  assert.match(markup, /두 응답의 센서 21개 중 조건 일치 21개 · 표시 20개/);
  assert.equal(tableRows(markup).length, 20);
  assert.match(markup, /<code>&quot;sensor-19&quot;<\/code>/);
  assert.doesNotMatch(markup, /<code>&quot;sensor-20&quot;<\/code>/);
  assert.match(markup, /<button type="button">센서 20개 더 보기<\/button>/);
  assert.match(markup, /<button type="button" disabled="">처음 20개로 접기<\/button>/);
  assert.ok(markup.indexOf('&quot;sensor-9&quot;') < markup.indexOf('&quot;sensor-10&quot;'));
  assert.match(markup, /센서별 A·B 비교 카드/);
});

test('empty responses and absent source timestamps remain explicit without imaginary sensor data', () => {
  const markup = render(detail('left-run', [], { observedAt: null }), detail('right-run', [], { observedAt: null }), {
    sources: { left: { path: '/a', receivedAt: null }, right: { path: '/b', receivedAt: null } },
  });
  assert.match(markup, /두 응답의 센서 0개 중 조건 일치 0개 · 표시 0개/);
  assert.match(markup, /두 응답에 센서별로 비교할 이벤트가 없습니다/);
  assert.equal((markup.match(/기록 없음 · null/g) ?? []).length, 4);
  assert.doesNotMatch(markup, /<table|<a\b|0\.00%|센서 20개 더 보기/);
});

test('same outcome counts are not called a full equality and local conditions do not promise export or ID-share persistence', () => {
  const left = detail('left-run', [event('sensor-1', 'FAILED', 'old-reason')]);
  const right = detail('right-run', [{ ...event('sensor-1', 'FAILED', 'new-reason'), value: 999, eventTime: '2026-10-25T00:00:09Z' }]);
  const markup = render(left, right);
  assert.match(markup, /건수 동일/);
  assert.match(markup, /사유·값·시각 변화는 검사하지 않습니다/);
  assert.match(markup, /기존 비교 CSV는 실행 전체 요약이며 이 센서별 표·조건을 담지 않습니다/);
  assert.match(markup, /기존 A·B ID 공유 링크도 이 센서 검색·차이 필터·정렬을 저장하지 않습니다/);
  assert.match(markup, /추가 GET을 요청하지 않습니다/);
  assert.match(markup, /지금 비교한 응답·관측 시각을 고정하지 않습니다/);
  assert.match(markup, /<option value="failure-delta">실패 건수 차이 절댓값 큰순<\/option>/);
  assert.match(markup, /<option value="failure-rate-delta">실패 비율 차이 절댓값 큰순<\/option>/);
  assert.match(markup, /<label[^>]*>[^<]*<input(?=[^>]*type="checkbox")/);
  assert.match(markup, /건수·관측 차이 있는 센서만/);
});
