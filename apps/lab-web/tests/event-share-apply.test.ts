import assert from 'node:assert/strict';
import test from 'node:test';
import { createRequire } from 'node:module';
import { readFileSync } from 'node:fs';
import type { LabData, RunDetail } from '../src/lib/api.ts';
import { resolveEventShareSelection, type EventShareParseResult } from '../src/lib/event-share.ts';

const require = createRequire(import.meta.url);
const ts = require('typescript');
const source = readFileSync(new URL('../src/components/LabExplorer.tsx', import.meta.url), 'utf8');
const parsed = ts.createSourceFile('LabExplorer.tsx', source, ts.ScriptTarget.ES2022, true, ts.ScriptKind.TSX);
let handler: any, selectedInitializer: any;
function visit(node: any) {
  if (ts.isFunctionDeclaration(node) && node.name?.text === 'applySharedSelection') {
    assert.equal(handler, undefined, 'Exactly one real apply handler is tested'); handler = node;
  }
  if (ts.isVariableDeclaration(node) && node.name.getText(parsed) === 'selectedEventSequence') {
    assert.equal(selectedInitializer, undefined, 'Exactly one displayed selection initializer is tested'); selectedInitializer = node.initializer;
  }
  ts.forEachChild(node, visit);
}
visit(parsed); assert.ok(handler, 'The actual component must define applySharedSelection');
// Execute the actual handler with controlled network/state dependencies, without mounting unrelated effects.
const printed = ts.createPrinter().printNode(ts.EmitHint.Unspecified, handler, parsed);
const compiled = ts.transpileModule(printed, { compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.ESNext }, reportDiagnostics: true });
assert.equal(compiled.diagnostics.length, 0);
const fixture: LabData = JSON.parse(readFileSync(new URL('../src/data/snapshot.json', import.meta.url), 'utf8'));
const request: EventShareParseResult = { kind: 'valid', selection: {
  runId: 'outside-recent-list', filters: { status: 'DUPLICATE', query: '  EVT-003  ', reason: 'DUPLICATE_EVENT_ID' }, sequence: 4,
} };
const response: RunDetail = { ...fixture.detail, id: 'outside-recent-list', observedAt: '2026-10-24T12:00:00Z' };
type FetchCall = { base: string; id: string; signal: AbortSignal };

function harness(options: { interactive?: boolean; loading?: boolean; mode?: string; inFlight?: boolean;
  request?: EventShareParseResult; fetch?: () => Promise<RunDetail> } = {}) {
  const previous = structuredClone(fixture);
  const state = { data: previous, filter: 'SUCCESS', query: 'old-search', reason: 'ACCEPTED' as string | null,
    selection: { runId: previous.detail.id, mode: 'live', sequence: 1 } as { runId: string; mode: string; sequence: number } | null,
    tab: 'chart', loading: options.loading ?? false, error: 'old-error', notice: 'old-notice' };
  const calls: FetchCall[] = [], businessWrites: string[] = [], loadingWrites: boolean[] = [], timers: number[] = [], cleared: number[] = [];
  const oldController = new AbortController(), controller = { current: oldController }, mounted = { current: true };
  const shareInFlight = { current: options.inFlight ?? false };
  const dependencies = {
    interactive: options.interactive ?? true, loading: options.loading ?? false, mode: options.mode ?? 'live', shareInFlight,
    shareRequest: options.request ?? request, controller, mounted, apiBase: '/public-api', AbortController,
    fetchRun: async (base: string, id: string, signal: AbortSignal) => { calls.push({ base, id, signal }); return options.fetch ? options.fetch() : response; },
    resolveEventShareSelection,
    setLoading: (value: boolean) => { state.loading = value; loadingWrites.push(value); },
    setError: (value: string) => { state.error = value; },
    setShareNotice: (value: string) => { state.notice = value; },
    setData: (update: (data: LabData) => LabData) => { businessWrites.push('data'); state.data = update(state.data); },
    setFilter: (value: string) => { businessWrites.push('filter'); state.filter = value; },
    setEventQuery: (value: string) => { businessWrites.push('query'); state.query = value; },
    setEventReason: (value: string | null) => { businessWrites.push('reason'); state.reason = value; },
    setEventSelection: (value: typeof state.selection) => { businessWrites.push('selection'); state.selection = value; },
    setTab: (value: string) => { businessWrites.push('tab'); state.tab = value; },
    describeLiveFailure: () => 'READ_FAILED', liveFailureOf: (failure: unknown) => failure,
    setTimeout: (_callback: () => void, duration: number) => { timers.push(duration); return timers.length; },
    clearTimeout: (id: number) => { cleared.push(id); },
  };
  const apply: () => Promise<void> = new Function(...Object.keys(dependencies), compiled.outputText + '\nreturn applySharedSelection;')(...Object.values(dependencies));
  return { apply, state, previous, calls, businessWrites, loadingWrites, timers, cleared, oldController, controller, mounted, shareInFlight };
}

function deferred() {
  let resolve!: (detail: RunDetail) => void, reject!: (reason: Error) => void;
  const promise = new Promise<RunDetail>((a, b) => { resolve = a; reject = b; });
  return { promise, resolve, reject };
}

test('explicit share apply loads an ID outside the recent list and commits exact response with raw conditions', async () => {
  const h = harness();
  assert.ok(!h.previous.runs.some(run => run.id === response.id));
  await h.apply();
  assert.equal(h.calls.length, 1); assert.equal(h.calls[0]!.base, '/public-api'); assert.equal(h.calls[0]!.id, response.id);
  assert.equal(h.calls[0]!.signal, h.controller.current.signal); assert.equal(h.oldController.signal.aborted, true);
  assert.equal(h.state.data.detail, response); assert.equal(h.state.data.runs, h.previous.runs); assert.equal(h.state.data.summary, h.previous.summary);
  assert.equal(h.state.filter, 'DUPLICATE'); assert.equal(h.state.query, '  EVT-003  '); assert.equal(h.state.reason, 'DUPLICATE_EVENT_ID');
  assert.deepEqual(h.state.selection, { runId: response.id, mode: 'live', sequence: 4 }); assert.equal(h.state.tab, 'events');
  assert.match(h.state.notice, /4번 이벤트/); assert.match(h.state.notice, /원래 공유 시점의 결과를 고정하지 않습니다/);
  assert.deepEqual(h.loadingWrites, [true, false]); assert.equal(h.shareInFlight.current, false); assert.deepEqual(h.timers, [8000]); assert.deepEqual(h.cleared, [1]);
});

test('missing and filtered shared sequences clear old selection without silently choosing another event', async () => {
  for (const [sequence, notice] of [[999, /이번 응답에 없어/], [3, /조건에서 제외/]] as const) {
    const h = harness({ request: { kind: 'valid', selection: { ...request.selection, sequence } } });
    await h.apply();
    assert.equal(h.state.data.detail, response); assert.equal(h.state.selection, null); assert.equal(h.state.tab, 'events');
    assert.equal(h.state.query, '  EVT-003  '); assert.match(h.state.notice, notice);
  }
});

test('failed shared read preserves previous data, filters and event selection', async () => {
  const h = harness({ fetch: async () => { throw new Error('network unavailable'); } });
  const before = { data: h.state.data, filter: h.state.filter, query: h.state.query, reason: h.state.reason, selection: h.state.selection, tab: h.state.tab };
  await h.apply();
  for (const key of ['data', 'filter', 'query', 'reason', 'selection', 'tab'] as const) assert.equal(h.state[key], before[key]);
  assert.deepEqual(h.businessWrites, []); assert.match(h.state.notice, /이전 실행·조건·선택을 유지/); assert.match(h.state.notice, /READ_FAILED/);
  assert.equal(h.state.loading, false); assert.equal(h.shareInFlight.current, false); assert.deepEqual(h.cleared, [1]);
});

test('noninteractive, busy, nonlive and invalid requests cannot fetch or change displayed selection', async () => {
  for (const options of [{ interactive: false }, { loading: true }, { inFlight: true }, { mode: 'fixture' }, { mode: 'recorded' },
    { request: { kind: 'absent' } as const }, { request: { kind: 'invalid' } as const }]) {
    const h = harness(options); const before = structuredClone(h.state);
    await h.apply();
    assert.deepEqual(h.calls, []); assert.deepEqual(h.businessWrites, []); assert.deepEqual(h.state, before);
    assert.deepEqual(h.timers, []); assert.equal(h.oldController.signal.aborted, false);
  }
});

test('a second activation while awaiting a shared read cannot start an additional GET', async () => {
  const pending = deferred(), h = harness({ fetch: () => pending.promise });
  const first = h.apply(); await h.apply();
  assert.equal(h.calls.length, 1); assert.equal(h.state.data, h.previous); assert.deepEqual(h.businessWrites, []);
  pending.resolve(response); await first;
  assert.equal(h.state.data.detail, response); assert.equal(h.shareInFlight.current, false);
});

test('a superseding controller prevents deferred success from committing stale data or clearing new loading state', async () => {
  const pending = deferred(), h = harness({ fetch: () => pending.promise });
  const task = h.apply(); h.controller.current = new AbortController(); const startedNotice = h.state.notice;
  pending.resolve(response); await task;
  assert.deepEqual(h.businessWrites, []); assert.equal(h.state.data, h.previous); assert.equal(h.state.notice, startedNotice);
  assert.deepEqual(h.loadingWrites, [true]); assert.equal(h.shareInFlight.current, false); assert.deepEqual(h.cleared, [1]);
});

test('unmounted handlers cannot commit either delayed success or delayed failure notices', async () => {
  for (const fail of [false, true]) {
    const pending = deferred(), h = harness({ fetch: () => pending.promise });
    const task = h.apply(); h.mounted.current = false; const startedNotice = h.state.notice;
    if (fail) pending.reject(new Error('late network failure')); else pending.resolve(response);
    await task;
    assert.deepEqual(h.businessWrites, []); assert.equal(h.state.data, h.previous); assert.equal(h.state.notice, startedNotice);
    assert.deepEqual(h.loadingWrites, [true]); assert.equal(h.shareInFlight.current, false); assert.deepEqual(h.cleared, [1]);
  }
});

test('the real displayed-selection initializer excludes vanished, filtered and differently sourced selections from copied links', () => {
  assert.ok(selectedInitializer, 'The component must derive its displayed selection');
  const expression = ts.createPrinter().printNode(ts.EmitHint.Unspecified, selectedInitializer, parsed);
  const code = ts.transpileModule('const selectedEventSequence = ' + expression + ';', {
    compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.ESNext }, reportDiagnostics: true,
  });
  assert.equal(code.diagnostics.length, 0);
  const evaluate = new Function('eventSelection', 'detail', 'mode', 'outcomes', code.outputText + '\nreturn selectedEventSequence;');
  const detail = fixture.detail;
  const selected = { runId: detail.id, mode: 'live', sequence: 4 };
  const missingRows = detail.outcomes.filter(row => row.sequence !== 4);
  const filteredRows = [detail.outcomes[2]!]; // The response has sequence 4; this displayed filter only contains sequence 3.
  assert.equal(evaluate(selected, detail, 'live', detail.outcomes), 4, 'An existing visible selection is preserved');
  assert.equal(evaluate(null, detail, 'live', detail.outcomes), null, 'No selection stays absent');
  assert.equal(evaluate(selected, { ...detail, outcomes: missingRows }, 'live', missingRows), null, 'Same-run refresh no longer reports the selected sequence');
  assert.equal(evaluate(selected, detail, 'live', filteredRows), null, 'A sequence outside the current filter is not shared');
  assert.equal(evaluate({ ...selected, runId: 'another-run' }, detail, 'live', detail.outcomes), null, 'Another run cannot reuse the selection');
  assert.equal(evaluate({ ...selected, mode: 'recorded' }, detail, 'live', detail.outcomes), null, 'Another source mode cannot reuse the selection');
});
