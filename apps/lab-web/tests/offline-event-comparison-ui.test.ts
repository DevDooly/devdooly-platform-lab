import assert from 'node:assert/strict';
import test from 'node:test';
import { createRequire } from 'node:module';
import { readFileSync } from 'node:fs';
import { pathToFileURL } from 'node:url';
import type { Outcome } from '../src/lib/api.ts';
import type { EventExportDocument } from '../src/lib/event-export.ts';
import type { OfflineEventFile, OfflineEventFileError } from '../src/lib/offline-event-file.ts';

const require = createRequire(import.meta.url);
const ts = require('typescript');
const { createElement } = require('react');
const { renderToStaticMarkup } = require('react-dom/server');
const source = readFileSync(new URL('../src/components/OfflineEventComparison.tsx', import.meta.url), 'utf8');
const compiled = ts.transpileModule(source, { compilerOptions: { jsx: ts.JsxEmit.ReactJSX,
  module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022 }, reportDiagnostics: true });
assert.equal(compiled.diagnostics.length, 0);
const output = compiled.outputText
  .replace(/import ['"]\.\.\/styles\/offline-event-comparison\.css['"];?\s*/g, '')
  .replace(/from (['"])(react(?:\/jsx-runtime)?)\1/g,
    (_unused: string, _quote: string, name: string) => `from ${JSON.stringify(pathToFileURL(require.resolve(name)).href)}`)
  .replace(/from (['"])\.\.\/lib\/(event-comparison|offline-event-file)\1/g,
    (_unused: string, _quote: string, name: string) => `from ${JSON.stringify(new URL(`../src/lib/${name}.ts`, import.meta.url).href)}`);
const { default: OfflineEventComparison, OfflineComparisonResult } = await import(`data:text/javascript;base64,${Buffer.from(output).toString('base64')}`);
const event = (sequence: number, overrides: Partial<Outcome> = {}): Outcome => ({ sequence,
  eventId: `event-${sequence}`, sensorId: `sensor-${sequence}`, eventTime: '2026-10-25T00:00:00Z',
  value: 1, status: 'SUCCESS', reason: 'ok', ...overrides,
});
function document(outcomes: Outcome[], overrides: Partial<EventExportDocument> = {}): EventExportDocument {
  return { schemaVersion: 1, source: { runId: 'same-run', mode: 'live', observedAt: '2026-10-25T00:00:02.123456789Z', capturedAt: null },
    counts: { reportedInputCount: 1000, availableOutcomes: 100, matchedOutcomes: outcomes.length },
    filters: { status: 'ALL', query: '', reason: null }, outcomes, ...overrides } as EventExportDocument;
}
const saved = (name: string, outcomes: Outcome[], overrides: Partial<EventExportDocument> = {}): OfflineEventFile => ({
  name, byteLength: 2048, document: document(outcomes, overrides),
});
const pair = (left = saved('a.json', [event(0)]), right = saved('b.json', [event(0)])) => ({ left, right });
function renderResult(value: ReturnType<typeof pair>, interactive = true) {
  return renderToStaticMarkup(createElement(OfflineComparisonResult, { pair: value, interactive }));
}
const rows = (markup: string) => [...markup.matchAll(/<article aria-label="파일 입력 순서 (\d+) 비교">([\s\S]*?)<\/article>/g)]
  .map(match => ({ sequence: Number(match[1]), markup: match[2] }));

test('initial file comparison HTML is locked until hydration, has explicit file selection and no result or endpoint controls', () => {
  const markup = renderToStaticMarkup(createElement(OfflineEventComparison));
  assert.equal((markup.match(/<input[^>]*type="file"[^>]*disabled=""/g) ?? []).length, 2);
  assert.equal((markup.match(/accept="\.json,application\/json"/g) ?? []).length, 2);
  assert.equal((markup.match(/<button[^>]*disabled=""/g) ?? []).length, 2);
  assert.match(markup, /선택한 파일 비교/);
  assert.match(markup, /선택·표시 모두 비우기/);
  assert.match(markup, /아직 비교한 파일이 없습니다/);
  assert.match(markup, /1,048,576 bytes\(1 MiB\)/);
  assert.match(markup, /이벤트 최대 1,000건/);
  assert.match(markup, /파일 선택만으로 읽지 않습니다/);
  assert.match(markup, /같은 파일이나 같은 runId도 비교할 수 있습니다/);
  assert.match(markup, /서버에 업로드하거나 브라우저 저장소에 보관하지 않습니다/);
  assert.match(markup, /오프라인 설치형 앱\(PWA\)을 뜻하지 않습니다/);
  assert.doesNotMatch(markup, /<a\b|apiBase|실시간 조회|CSV 다운로드/);
});

test('file metadata preserves raw provenance, three counts, schema and exact empty versus absent original conditions', () => {
  const left = saved('a <script>.json', [event(0)], {
    source: { runId: '<a href="https://untrusted.test">', mode: 'live', observedAt: '2026-10-25T00:00:02.123456789Z', capturedAt: null },
    filters: { status: 'ALL', query: '  Sensor  ', reason: null },
  });
  const right = saved('b.json', [event(0, { sensorId: '', reason: '' })], { schemaVersion: 2,
    source: { runId: '', mode: 'recorded', observedAt: null, capturedAt: '2026-10-24T23:59:00.987654321Z' },
    filters: { status: 'ALL', query: '', reason: '', sensorId: '' },
  });
  const markup = renderResult(pair(left, right));
  for (const raw of ['&quot;live&quot;', '&quot;recorded&quot;', '2026-10-25T00:00:02.123456789Z', '2026-10-24T23:59:00.987654321Z']) {
    assert.ok(markup.includes(raw));
  }
  assert.match(markup, /reportedInputCount<\/dt><dd>1,000건/);
  assert.match(markup, /availableOutcomes<\/dt><dd>100건/);
  assert.match(markup, /matchedOutcomes<\/dt><dd>1건/);
  assert.match(markup, /schemaVersion<\/dt><dd>1<\/dd>/);
  assert.match(markup, /schemaVersion<\/dt><dd>2<\/dd>/);
  assert.match(markup, /2,048 bytes/);
  assert.match(markup, /reason 조건<\/dt><dd><code>null<\/code> · 전체 사유/);
  assert.match(markup, /reason 조건<\/dt><dd><code>&quot;&quot;<\/code> · 원문 정확 조건/);
  assert.match(markup, /sensorId 조건<\/dt><dd>필드 없음 · 전체 센서 \(schemaVersion 1\)/);
  assert.match(markup, /sensorId 조건<\/dt><dd><code>&quot;&quot;<\/code> · 원문 정확 조건/);
  assert.match(markup, /&quot;  Sensor  &quot;/);
  assert.match(markup, /&lt;script&gt;/);
  assert.match(markup, /&lt;a href=/);
  assert.doesNotMatch(markup, /<script>|<a\b/);
  assert.match(markup, /파일의 진위·현재 API 상태·원본을 인증하지 않습니다/);
  assert.match(markup, /세 건수가 같아도 원본 전체를 빠짐없이 담았다는 증명은 아닙니다/);
});

test('offline results retain five position categories, input difference precedence and independent verdict difference', () => {
  const left = [event(12), event(2), event(2, { eventId: 'duplicate-sequence' }), event(8), event(10), event(11)];
  const right = [event(12), event(2), event(10, { value: null, status: 'FAILED', reason: 'new' }), event(11, { reason: 'changed' })];
  const markup = renderResult(pair(saved('a.json', left), saved('b.json', right)));
  assert.deepEqual(rows(markup).map(row => row.sequence), [2, 8, 10, 11, 12]);
  for (const label of ['대응 모호', '한쪽 미관측', '보고된 입력 필드 다름', '판정 필드 다름', '비교 필드 같음']) {
    assert.ok(markup.includes(`<dt>${label}</dt><dd>1개</dd>`));
  }
  const changed = rows(markup).find(row => row.sequence === 10)!.markup;
  assert.match(changed, /oec-kind-input-different/);
  assert.match(changed, /입력 필드 차이<\/dt><dd><code>value<\/code>/);
  assert.match(changed, /판정 필드 차이<\/dt><dd><code>status · reason<\/code>/);
  assert.match(changed, /<dt>value<\/dt><dd><code>null<\/code>/);
  assert.match(markup, /미관측 · 원래 입력의 누락이나 처리 0건을 뜻하지 않습니다/);
  assert.doesNotMatch(markup, /<a\b/);
});

test('ambiguous groups retain all raw candidates, including escaped fields, without automatic pairing or navigation', () => {
  const left = [event(4, { eventId: '<script>', reason: 'first' }),
    event(4, { eventId: 'second', status: 'FAILED', reason: '' }), event(4, { eventId: 'third', eventTime: '', value: null })];
  const markup = renderResult(pair(saved('same.json', left), saved('same.json', [event(4)])));
  assert.match(markup, /<details><summary>A 후보 3건 전체 보기<\/summary>/);
  assert.equal((markup.match(/<h5>A 파일 행 /g) ?? []).length, 3);
  assert.equal((markup.match(/<dt>eventId<\/dt>/g) ?? []).length, 4);
  for (const text of ['&lt;script&gt;', '&quot;second&quot;', '&quot;third&quot;', '&quot;FAILED&quot;', '&quot;first&quot;']) assert.ok(markup.includes(text));
  assert.match(markup, /<dt>reason<\/dt><dd><code>&quot;&quot;<\/code>/);
  assert.match(markup, /<dt>eventTime<\/dt><dd><code>&quot;&quot;<\/code>/);
  assert.match(markup, /입력 필드 차이<\/dt><dd>비교 안 함/);
  assert.match(markup, /판정 필드 차이<\/dt><dd>비교 안 함/);
  assert.match(markup, /임의로 대응하지 않습니다/);
  assert.doesNotMatch(markup, /<script>|<a\b/);
});

test('large offline lists show twenty complete cards with disabled busy controls and preserve numeric sequence ordering', () => {
  const outcomes = Array.from({ length: 21 }, (_, index) => event(20 - index));
  const value = pair(saved('a.json', outcomes), saved('b.json', outcomes));
  const ready = renderResult(value);
  assert.deepEqual(rows(ready).map(row => row.sequence), Array.from({ length: 20 }, (_, index) => index));
  assert.match(ready, /파일의 입력 순서 21개 중 조건 일치 21개 · 표시 20개/);
  assert.match(ready, /<button type="button">입력 순서 20개 더 보기<\/button>/);
  assert.match(ready, /<button type="button" disabled="">처음 20개로 접기<\/button>/);
  const busy = renderResult(value, false);
  assert.match(busy, /<input(?=[^>]*type="search")(?=[^>]*disabled="")/);
  assert.match(busy, /<select[^>]*disabled=""/);
  assert.equal((busy.match(/<button[^>]*disabled=""/g) ?? []).length, 2);
  assert.doesNotMatch(busy, /<a\b/);
});

test('empty files remain explicit and interpretation does not promise original input, context, code or original nonfinite values', () => {
  const markup = renderResult(pair(saved('a.json', []), saved('b.json', [])));
  assert.match(markup, /파일의 입력 순서 0개 중 조건 일치 0개 · 표시 0개/);
  assert.match(markup, /두 파일에 비교할 이벤트 행이 없습니다/);
  assert.equal(rows(markup).length, 0);
  assert.match(markup, /같은 이벤트·원본 입력임을 보장하지 않습니다/);
  assert.match(markup, /원본 입력 전체·앞선 처리 문맥·실행 코드가 같다는 증명이 아닙니다/);
  assert.match(markup, /직렬화 전 NaN·Infinity/);
  assert.match(markup, /eventTime 원문을 같은 순간으로 정규화하지 않습니다/);
  assert.match(markup, /API 상세 이동·CSV·공유 링크를 만들지 않습니다/);
});

// Execute the real component handlers with controlled file/state dependencies.
const parsed = ts.createSourceFile('OfflineEventComparison.tsx', source, ts.ScriptTarget.ES2022, true, ts.ScriptKind.TSX);
const declarations: any[] = [];
const handlerNames = ['selectFile', 'clearFiles', 'compareFiles'];
let errorInitializer: any;
function visit(node: any) {
  if (ts.isFunctionDeclaration(node) && handlerNames.includes(node.name?.text)) declarations.push(node);
  if (ts.isVariableDeclaration(node) && node.name.getText(parsed) === 'errorMessages') errorInitializer = node.initializer;
  ts.forEachChild(node, visit);
}
visit(parsed);
assert.equal(declarations.length, 3);
assert.ok(errorInitializer);
const printer = ts.createPrinter();
const handlerSource = 'const errorMessages = ' + printer.printNode(ts.EmitHint.Expression, errorInitializer, parsed) + ';\n'
  + declarations.map(node => printer.printNode(ts.EmitHint.Unspecified, node, parsed)).join('\n');
const handlerCode = ts.transpileModule(handlerSource, { compilerOptions: {
  target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.ESNext }, reportDiagnostics: true });
assert.equal(handlerCode.diagnostics.length, 0);
type ReadResult = { ok: true; file: OfflineEventFile } | { ok: false; code: OfflineEventFileError };
type SelectedFile = { name: string; size: number; arrayBuffer(): Promise<ArrayBuffer> };
const selected = (name: string): SelectedFile => ({ name, size: 42, arrayBuffer: async () => new ArrayBuffer(0) });
function harness(options: { locked?: boolean; draft?: { left: SelectedFile | null; right: SelectedFile | null };
  read?: (file: SelectedFile) => Promise<ReadResult> } = {}) {
  const previous = pair();
  const state = { draft: options.draft ?? { left: selected('a.json'), right: selected('b.json') },
    pair: previous as typeof previous | null, error: 'old-error', phase: '', busy: false, inputKey: 0 };
  const calls: SelectedFile[] = [], pairWrites: (typeof previous | null)[] = [], writes: string[] = [];
  const inFlight = { current: false }, mounted = { current: true };
  function handlers() {
    const dependencies = {
      locked: options.locked ?? state.busy, draft: state.draft, inFlight, mounted,
      setDraft: (change: typeof state.draft | ((current: typeof state.draft) => typeof state.draft)) => {
        writes.push('draft'); state.draft = typeof change === 'function' ? change(state.draft) : change;
      },
      setPair: (value: typeof state.pair) => { writes.push('pair'); pairWrites.push(value); state.pair = value; },
      setError: (value: string) => { writes.push('error'); state.error = value; },
      setPhase: (value: string) => { writes.push('phase'); state.phase = value; },
      setBusy: (value: boolean) => { writes.push('busy'); state.busy = value; },
      setInputKey: (change: (current: number) => number) => { writes.push('inputKey'); state.inputKey = change(state.inputKey); },
      readOfflineEventFile: async (file: SelectedFile): Promise<ReadResult> => {
        calls.push(file); return options.read ? options.read(file) : { ok: true, file: saved(file.name, [event(0)]) };
      },
    };
    return new Function(...Object.keys(dependencies), handlerCode.outputText + '\nreturn { selectFile, clearFiles, compareFiles };')(...Object.values(dependencies)) as {
      selectFile: (side: 'left' | 'right', file: SelectedFile | null) => void;
      clearFiles: () => void;
      compareFiles: () => Promise<void>;
    };
  }
  return { state, previous, calls, pairWrites, writes, inFlight, mounted, handlers };
}
function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>(done => { resolve = done; });
  return { promise, resolve };
}

test('file selection alone reads nothing and does not replace the displayed pair; explicit comparison reads A then B once', async () => {
  const h = harness();
  const next = selected('new-a.json');
  h.handlers().selectFile('left', next);
  assert.equal(h.calls.length, 0);
  assert.equal(h.state.draft.left, next);
  assert.equal(h.state.pair, h.previous);
  assert.deepEqual(h.pairWrites, []);
  await h.handlers().compareFiles();
  assert.deepEqual(h.calls.map(file => file.name), ['new-a.json', 'b.json']);
  assert.equal(h.pairWrites.length, 1);
  assert.equal(h.state.pair!.left.name, 'new-a.json');
  assert.equal(h.state.pair!.right.name, 'b.json');
  assert.equal(h.state.busy, false);
  assert.equal(h.inFlight.current, false);
  assert.equal(h.state.error, '');
  assert.equal(h.state.phase, '');
});

test('invalid A skips B and invalid B preserves the same displayed pair without a partial comparison', async () => {
  for (const failing of ['a.json', 'b.json']) {
    const h = harness({ read: async file => file.name === failing ? { ok: false, code: 'INVALID_JSON' }
      : { ok: true, file: saved(file.name, [event(0)]) } });
    await h.handlers().compareFiles();
    assert.deepEqual(h.calls.map(file => file.name), failing === 'a.json' ? ['a.json'] : ['a.json', 'b.json']);
    assert.equal(h.state.pair, h.previous);
    assert.deepEqual(h.pairWrites, []);
    assert.match(h.state.error, failing === 'a.json' ? /^A 파일:/ : /^B 파일:/);
    assert.match(h.state.error, /JSON 문법 또는 중복된 object key를 확인해주세요/);
    assert.equal(h.state.busy, false);
    assert.equal(h.inFlight.current, false);
  }
});

test('the in-flight reference blocks stale double clicks, draft changes and clear until the first sequential read finishes', async () => {
  const first = deferred<ReadResult>();
  const h = harness({ read: async file => file.name === 'a.json' ? first.promise : { ok: true, file: saved(file.name, []) } });
  const stale = h.handlers();
  const running = stale.compareFiles();
  await stale.compareFiles();
  stale.selectFile('right', selected('unexpected.json'));
  stale.clearFiles();
  assert.deepEqual(h.calls.map(file => file.name), ['a.json']);
  assert.equal(h.state.draft.right!.name, 'b.json');
  assert.equal(h.state.pair, h.previous);
  assert.equal(h.state.inputKey, 0);
  first.resolve({ ok: true, file: saved('a.json', []) });
  await running;
  assert.deepEqual(h.calls.map(file => file.name), ['a.json', 'b.json']);
  assert.equal(h.pairWrites.length, 1);
  assert.equal(h.inFlight.current, false);
});

test('locked or incomplete selection reads nothing and identical file references and run IDs remain valid choices', async () => {
  for (const h of [harness({ locked: true }), harness({ draft: { left: null, right: selected('b.json') } })]) {
    await h.handlers().compareFiles();
    assert.equal(h.calls.length, 0);
    assert.deepEqual(h.writes, []);
  }
  const same = selected('same.json');
  const h = harness({ draft: { left: same, right: same } });
  await h.handlers().compareFiles();
  assert.deepEqual(h.calls, [same, same]);
  assert.equal(h.state.pair!.left.document.source.runId, h.state.pair!.right.document.source.runId);
  assert.equal(h.pairWrites.length, 1);
});

test('unmount after A read stops B and any later state commits while releasing the in-flight reference', async () => {
  const first = deferred<ReadResult>();
  const h = harness({ read: async () => first.promise });
  const running = h.handlers().compareFiles();
  h.mounted.current = false;
  const writtenBefore = h.writes.length;
  first.resolve({ ok: true, file: saved('a.json', []) });
  await running;
  assert.deepEqual(h.calls.map(file => file.name), ['a.json']);
  assert.equal(h.writes.length, writtenBefore);
  assert.deepEqual(h.pairWrites, []);
  assert.equal(h.inFlight.current, false);
});

test('clear discards displayed and selected references and resets file inputs without reading or deleting files', () => {
  const h = harness();
  h.handlers().clearFiles();
  assert.deepEqual(h.state.draft, { left: null, right: null });
  assert.equal(h.state.pair, null);
  assert.equal(h.state.inputKey, 1);
  assert.equal(h.state.error, '');
  assert.equal(h.state.phase, '');
  assert.deepEqual(h.calls, []);
  assert.deepEqual(h.pairWrites, [null]);
});

test('read exceptions become a finite message and retain the previous pair without exception text', async () => {
  const h = harness({ read: async () => { throw new Error('private file body and failure detail'); } });
  await h.handlers().compareFiles();
  assert.equal(h.state.error, '파일을 읽지 못했습니다. 파일 접근 상태를 확인해주세요.');
  assert.doesNotMatch(h.state.error, /private|failure detail|Error/);
  assert.equal(h.state.pair, h.previous);
  assert.deepEqual(h.pairWrites, []);
  assert.equal(h.state.busy, false);
});
