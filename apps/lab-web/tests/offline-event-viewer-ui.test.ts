import assert from 'node:assert/strict';
import test from 'node:test';
import { createRequire } from 'node:module';
import { readFileSync } from 'node:fs';
import { pathToFileURL } from 'node:url';
import type { Outcome } from '../src/lib/api.ts';
import type { EventExportDocument } from '../src/lib/event-export.ts';
import type { OfflineViewerView } from '../src/components/OfflineEventViewer.tsx';
import { readOfflineEventFile, type OfflineEventFile, type OfflineEventFileError } from '../src/lib/offline-event-file.ts';

const require = createRequire(import.meta.url);
const ts = require('typescript');
const { createElement } = require('react');
const { renderToStaticMarkup } = require('react-dom/server');
const source = readFileSync(new URL('../src/components/OfflineEventViewer.tsx', import.meta.url), 'utf8');
const compiled = ts.transpileModule(source, { compilerOptions: { jsx: ts.JsxEmit.ReactJSX,
  module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022 }, reportDiagnostics: true });
assert.equal(compiled.diagnostics.length, 0);
const output = compiled.outputText
  .replace(/import ['"]\.\.\/styles\/offline-event-viewer\.css['"];?\s*/g, '')
  .replace(/from (['"])(react(?:\/jsx-runtime)?)\1/g,
    (_unused: string, _quote: string, name: string) => `from ${JSON.stringify(pathToFileURL(require.resolve(name)).href)}`)
  .replace(/from (['"])\.\.\/lib\/(event-pagination|event-search|offline-event-file)\1/g,
    (_unused: string, _quote: string, name: string) => `from ${JSON.stringify(new URL(`../src/lib/${name}.ts`, import.meta.url).href)}`);
const { default: OfflineEventViewer, OfflineEventViewerResult, initialOfflineViewerView } = await import(`data:text/javascript;base64,${Buffer.from(output).toString('base64')}`);
const event = (sequence: number, overrides: Partial<Outcome> = {}): Outcome => ({ sequence,
  eventId: `event-${sequence}`, sensorId: `sensor-${sequence}`, eventTime: '2026-10-25T00:00:00.123456789Z',
  value: 1, status: 'SUCCESS', reason: 'ok', ...overrides,
});
const saved = (name = 'events.json', outcomes: Outcome[] = [event(8)], overrides: Partial<EventExportDocument> = {}): OfflineEventFile => ({
  name, byteLength: 2048, document: { schemaVersion: 1,
    source: { runId: 'run-1', mode: 'live', observedAt: '2026-10-25T00:00:02.123456789Z', capturedAt: null },
    counts: { reportedInputCount: 10000, availableOutcomes: 1000, matchedOutcomes: outcomes.length },
    filters: { status: 'ALL', query: '', reason: null }, outcomes, ...overrides } as EventExportDocument,
});
function renderResult(file: OfflineEventFile, changes: Partial<OfflineViewerView> = {}, interactive = true) {
  return renderToStaticMarkup(createElement(OfflineEventViewerResult, { file,
    view: { ...initialOfflineViewerView(), ...changes }, interactive, onViewChange: () => {} }));
}
const rowNumbers = (markup: string) => [...markup.matchAll(/<tr data-file-row="(\d+)"/g)].map(match => Number(match[1]));

test('initial HTML requires one explicit file open, is locked until hydration, and describes local file limits', () => {
  const markup = renderToStaticMarkup(createElement(OfflineEventViewer));
  assert.equal((markup.match(/<input[^>]*type="file"[^>]*disabled=""/g) ?? []).length, 1);
  assert.equal((markup.match(/<button[^>]*disabled=""/g) ?? []).length, 2);
  for (const text of ['선택한 파일 열기', '선택·표시 모두 비우기', '아직 연 파일이 없습니다', '1,048,576 bytes(1 MiB)',
    '이벤트 최대 1,000건', '파일 선택만으로 읽지 않습니다', '비교 보고서는 열 수 없습니다',
    '서버에 업로드하거나 브라우저 저장소에 보관하지 않습니다', '원파일을 삭제하지 않습니다']) assert.ok(markup.includes(text), text);
  assert.doesNotMatch(markup, /<a\b|apiBase|CSV|다운로드|공유 링크/);
});

test('file provenance, raw times, three scopes and original filters stay separate from initial screen filters', () => {
  const file = saved('<script>.json', [event(8, { sensorId: '', reason: '', value: -0, eventTime: '' })], {
    schemaVersion: 2, filters: { status: 'ALL', query: '  original  ', reason: '', sensorId: '' },
  });
  const markup = renderResult(file, { selectedIndex: 0 });
  for (const text of ['&lt;script&gt;.json', '&quot;live&quot;', '2026-10-25T00:00:02.123456789Z',
    'capturedAt</dt><dd><code>null</code>', '10,000건', '1,000건', 'matchedOutcomes',
    'mode가 live여도 현재 API 응답이 아니며', '원본 전체를 빠짐없이 담았다는 증명은 아닙니다',
    'sensorId 조건</dt><dd><code>&quot;&quot;</code> · 원문 정확 조건', '&quot;  original  &quot;',
    'reason 조건</dt><dd><code>&quot;&quot;</code>', '파일에 기록된 원래 검색 조건과 별개',
    'eventTime</dt><dd><code>&quot;&quot;</code>', 'value</dt><dd><code>-0</code>']) assert.ok(markup.includes(text), text);
  assert.match(markup, /<input[^>]*type="search"[^>]*value=""/);
  assert.equal((markup.match(/<option value="all" selected="">/g) ?? []).length, 2);
  assert.doesNotMatch(markup, /<script>|<a\b/);
  const v1 = renderResult(saved());
  assert.match(v1, /sensorId 조건<\/dt><dd>필드 없음 · 전체 센서 \(schemaVersion 1\)/);
  assert.match(v1, /reason 조건<\/dt><dd><code>null<\/code> · 전체 사유/);
});

test('repeated sequence and eventId retain original row order and select the second raw record after filtering', () => {
  const outcomes = [event(9), event(7, { eventId: 'SAME', reason: 'first', sensorId: '' }), event(2),
    event(7, { eventId: 'SAME', reason: '', sensorId: '', eventTime: '<script>raw-time', value: null }), event(0)];
  const file = saved('duplicates.json', outcomes);
  assert.deepEqual(rowNumbers(renderResult(file)), [1, 2, 3, 4, 5]);
  const filters = { status: 'ALL' as const, query: ' same ', reason: null, sensorId: '' };
  const markup = renderResult(file, { filters, selectedIndex: 3 });
  assert.deepEqual(rowNumbers(markup), [2, 4]);
  assert.match(markup, /파일 행 4 원문 상세/);
  assert.match(markup, /eventTime<\/dt><dd><code>&quot;&lt;script&gt;raw-time&quot;<\/code>/);
  assert.match(markup, /reason<\/dt><dd><code>&quot;&quot;<\/code>/);
  assert.match(markup, /value<\/dt><dd><code>null<\/code>/);
  assert.match(markup, /aria-label="파일 행 2 원문 보기" aria-pressed="false"/);
  assert.match(markup, /aria-label="파일 행 4 원문 보기" aria-pressed="true"/);
  assert.doesNotMatch(markup, /<script>|<a\b/);
  assert.deepEqual(rowNumbers(renderResult(file, { filters: { ...filters, reason: '' } })), [4]);
  assert.deepEqual(rowNumbers(renderResult(file, { filters: { ...filters, status: 'FAILED' } })), []);
});

test('pages use filtered positions but retain file row identity, including off-page selected details', () => {
  const outcomes = Array.from({ length: 60 }, (_, index) => event(60 - index, { eventId: 'same', sensorId: index % 2 === 0 ? 'even' : 'odd' }));
  const file = saved('sixty.json', outcomes);
  for (const [pageSize, expected] of [[25, 25], [50, 50], [100, 60]] as const) {
    const markup = renderResult(file, { pageSize });
    assert.equal(rowNumbers(markup).length, expected);
    assert.equal(rowNumbers(markup)[0], 1);
    assert.equal(rowNumbers(markup).at(-1), expected);
    assert.match(markup, new RegExp(`<option value="${pageSize}" selected="">${pageSize}행`));
  }
  const later = renderResult(file, { pageIndex: 1, selectedIndex: 0 });
  assert.deepEqual(rowNumbers(later), Array.from({ length: 25 }, (_, index) => index + 26));
  assert.match(later, /파일 행 1 원문 상세/);
  assert.match(later, /선택한 행의 페이지로 이동/);
  const filtered = renderResult(file, { filters: { status: 'ALL', query: '', reason: null, sensorId: 'even' }, pageIndex: 1, selectedIndex: 58 });
  assert.deepEqual(rowNumbers(filtered), [51, 53, 55, 57, 59]);
  assert.match(filtered, /파일 행 59 원문 상세/);
  assert.match(filtered, /화면 조건 일치 30건 · 표시 26–30번째/);
  const busy = renderResult(file, { selectedIndex: 0 }, false);
  assert.match(busy, /<fieldset[^>]*disabled=""/);
  const outsideDisabledFieldset = busy.replace(/<fieldset[^>]*disabled=""[^>]*>[\s\S]*?<\/fieldset>/g, '');
  assert.doesNotMatch(outsideDisabledFieldset, /<button(?![^>]*disabled="")[^>]*>/);
});

test('a file with zero stored rows is distinct from a nonempty file with no screen matches', () => {
  const empty = renderResult(saved('empty.json', []));
  assert.match(empty, /이 파일에는 저장된 이벤트 행이 없습니다/);
  assert.match(empty, /보고된 원입력·조회 행 수가 0건이라는 뜻은 아닙니다/);
  assert.match(empty, /10,000건/);
  assert.match(empty, /파일 행 0건 중 화면 조건 일치 0건/);
  const noMatch = renderResult(saved(), { filters: { status: 'ALL', query: 'absent', reason: null, sensorId: null } });
  assert.match(noMatch, /화면 조건에 맞는 행이 없습니다/);
  assert.match(noMatch, /파일 행 1건 중 화면 조건 일치 0건/);
  assert.doesNotMatch(noMatch, /이 파일에는 저장된 이벤트 행이 없습니다/);
  assert.deepEqual(rowNumbers(empty), []);
  assert.deepEqual(rowNumbers(noMatch), []);
});

// Exercise the actual component handlers with controlled file reads and React setters.
const parsed = ts.createSourceFile('OfflineEventViewer.tsx', source, ts.ScriptTarget.ES2022, true, ts.ScriptKind.TSX);
const handlerNames = ['selectFile', 'updateView', 'clearFiles', 'openFile'];
const declarations: any[] = [];
let errorInitializer: any;
function visit(node: any) {
  if (ts.isFunctionDeclaration(node) && handlerNames.includes(node.name?.text)) declarations.push(node);
  if (ts.isVariableDeclaration(node) && node.name.getText(parsed) === 'errorMessages') errorInitializer = node.initializer;
  ts.forEachChild(node, visit);
}
visit(parsed);
assert.equal(declarations.length, handlerNames.length);
assert.ok(errorInitializer);
const printer = ts.createPrinter();
const handlerSource = 'const errorMessages = ' + printer.printNode(ts.EmitHint.Expression, errorInitializer, parsed) + ';\n'
  + declarations.map(node => printer.printNode(ts.EmitHint.Unspecified, node, parsed)).join('\n');
const handlerCode = ts.transpileModule(handlerSource, { compilerOptions: {
  target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.ESNext }, reportDiagnostics: true });
assert.equal(handlerCode.diagnostics.length, 0);
type ReadResult = { ok: true; file: OfflineEventFile } | { ok: false; code: OfflineEventFileError };
type SelectedFile = { name: string; size: number; arrayBuffer(): Promise<ArrayBuffer> };
function selected(name = 'next.json', content = JSON.stringify(saved().document)): SelectedFile {
  const bytes = new TextEncoder().encode(content);
  return { name, size: bytes.byteLength, arrayBuffer: async () => bytes.buffer as ArrayBuffer };
}
function harness(options: { locked?: boolean; draft?: SelectedFile | null; read?: (file: SelectedFile) => Promise<ReadResult> } = {}) {
  const previous = saved('previous.json');
  const previousView: OfflineViewerView = { filters: { status: 'FAILED', query: 'existing', reason: 'saved', sensorId: '' },
    pageIndex: 2, pageSize: 100, selectedIndex: 0 };
  const state = { draft: options.draft === undefined ? selected() : options.draft,
    file: previous as OfflineEventFile | null, view: previousView, error: 'previous-error', busy: false, inputKey: 0 };
  const calls: SelectedFile[] = [], fileWrites: (OfflineEventFile | null)[] = [], writes: string[] = [];
  const inFlight = { current: false }, mounted = { current: true }, readRevision = { current: 0 }, currentFile = { current: state.file };
  function handlers() {
    const dependencies = {
      locked: options.locked ?? state.busy, draft: state.draft, inFlight, mounted, readRevision, currentFile, initialOfflineViewerView,
      setDraft: (value: SelectedFile | null) => { writes.push('draft'); state.draft = value; },
      setFile: (value: OfflineEventFile | null) => { writes.push('file'); fileWrites.push(value); state.file = value; },
      setView: (change: OfflineViewerView | ((current: OfflineViewerView) => OfflineViewerView)) => {
        writes.push('view'); state.view = typeof change === 'function' ? change(state.view) : change;
      },
      setError: (value: string) => { writes.push('error'); state.error = value; },
      setBusy: (value: boolean) => { writes.push('busy'); state.busy = value; },
      setInputKey: (change: (current: number) => number) => { writes.push('inputKey'); state.inputKey = change(state.inputKey); },
      readOfflineEventFile: async (file: SelectedFile): Promise<ReadResult> => {
        calls.push(file); return options.read ? options.read(file) : readOfflineEventFile(file);
      },
    };
    return new Function(...Object.keys(dependencies), handlerCode.outputText + '\nreturn { selectFile, updateView, clearFiles, openFile };')(...Object.values(dependencies)) as {
      selectFile: (file: SelectedFile | null) => void;
      updateView: (file: OfflineEventFile, change: Partial<OfflineViewerView>) => void;
      clearFiles: () => void;
      openFile: () => Promise<void>;
    };
  }
  return { state, previous, previousView, calls, fileWrites, writes, inFlight, mounted, readRevision, currentFile, handlers };
}
function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>(done => { resolve = done; });
  return { promise, resolve };
}

test('selecting a draft reads nothing; explicitly opening validated JSON replaces the result and resets all screen state', async () => {
  const h = harness();
  const draft = selected('new.json', JSON.stringify(saved('ignored', [event(3), event(3)]).document));
  h.handlers().selectFile(draft);
  assert.deepEqual(h.calls, []);
  assert.equal(h.state.draft, draft);
  assert.equal(h.state.file, h.previous);
  assert.equal(h.state.view, h.previousView);
  await h.handlers().openFile();
  assert.deepEqual(h.calls, [draft]);
  assert.equal(h.fileWrites.length, 1);
  assert.equal(h.state.file!.name, 'new.json');
  assert.equal(h.state.file!.document.outcomes.length, 2);
  assert.equal(h.currentFile.current, h.state.file);
  assert.deepEqual(h.state.view, initialOfflineViewerView());
  assert.equal(h.state.error, '');
  assert.equal(h.state.busy, false);
  assert.equal(h.inFlight.current, false);
});

test('a duplicate JSON key, comparison report, filter mismatch or file read failure keeps the previous file and screen selection', async () => {
  const filterMismatch = saved('mismatch', [event(8)]).document;
  filterMismatch.filters.status = 'FAILED';
  const badFiles = [selected('duplicate.json', '{"schemaVersion":1,"schemaVersion":2}'),
    selected('report.json', '{"schemaVersion":1,"reportType":"offline-comparison","rows":[]}'),
    selected('mismatch.json', JSON.stringify(filterMismatch)),
    { name: 'unreadable.json', size: 10, arrayBuffer: async () => { throw new Error('unreadable'); } }];
  for (const draft of badFiles) {
    const h = harness({ draft });
    await h.handlers().openFile();
    assert.equal(h.state.file, h.previous, draft.name);
    assert.equal(h.currentFile.current, h.previous);
    assert.equal(h.state.view, h.previousView);
    assert.equal(h.state.draft, draft);
    assert.deepEqual(h.fileWrites, []);
    assert.ok(h.state.error.length > 0);
    assert.notEqual(h.state.error, 'previous-error');
    assert.equal(h.state.busy, false);
    assert.equal(h.inFlight.current, false);
  }
});

test('the synchronous lock rejects stale double opens, draft/clear changes and screen edits until the read settles', async () => {
  const pending = deferred<ReadResult>();
  const h = harness({ read: async () => pending.promise });
  const stale = h.handlers();
  const running = stale.openFile();
  const before = h.writes.length;
  await stale.openFile();
  stale.selectFile(selected('unexpected.json'));
  stale.clearFiles();
  stale.updateView(h.previous, { pageSize: 25, selectedIndex: null });
  assert.equal(h.writes.length, before);
  assert.equal(h.calls.length, 1);
  assert.equal(h.state.file, h.previous);
  assert.equal(h.state.view, h.previousView);
  pending.resolve({ ok: true, file: saved('accepted.json') });
  await running;
  stale.updateView(h.previous, { pageSize: 100, selectedIndex: 7 });
  assert.deepEqual(h.state.view, initialOfflineViewerView(), 'a callback from the replaced file cannot edit the new result');
});

test('clear removes draft, result, conditions and selection without a read; missing, locked or unmounted inputs cannot open', async () => {
  const h = harness();
  h.handlers().clearFiles();
  assert.equal(h.state.draft, null);
  assert.equal(h.state.file, null);
  assert.equal(h.currentFile.current, null);
  assert.deepEqual(h.state.view, initialOfflineViewerView());
  assert.equal(h.state.error, '');
  assert.equal(h.state.inputKey, 1);
  assert.deepEqual(h.calls, []);
  const unmounted = harness();
  unmounted.mounted.current = false;
  for (const blocked of [harness({ draft: null }), harness({ locked: true }), unmounted]) {
    await blocked.handlers().openFile();
    assert.deepEqual(blocked.calls, []);
    assert.deepEqual(blocked.writes, []);
  }
});

test('completion after unmount or a superseded lifecycle cannot commit results or unlock a later read', async () => {
  for (const remounted of [false, true]) {
    const pending = deferred<ReadResult>();
    const h = harness({ read: async () => pending.promise });
    const running = h.handlers().openFile();
    h.mounted.current = remounted;
    h.readRevision.current += 1;
    h.inFlight.current = remounted;
    const before = h.writes.length;
    pending.resolve({ ok: true, file: saved('stale.json') });
    await running;
    assert.equal(h.writes.length, before);
    assert.equal(h.state.file, h.previous);
    assert.equal(h.inFlight.current, remounted);
  }
  const thrown = harness({ read: async () => { throw new Error('unexpected read rejection'); } });
  await thrown.handlers().openFile();
  assert.match(thrown.state.error, /파일을 읽지 못했습니다/);
  assert.equal(thrown.state.file, thrown.previous);
  assert.equal(thrown.state.view, thrown.previousView);
  assert.equal(thrown.inFlight.current, false);
});
