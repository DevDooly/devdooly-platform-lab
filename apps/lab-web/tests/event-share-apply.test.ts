import assert from 'node:assert/strict';
import test from 'node:test';
import { createRequire } from 'node:module';
import { readFileSync } from 'node:fs';
import type { LabData, RunDetail } from '../src/lib/api.ts';
import { parseEventShareSelection, resolveEventShareSelection, type EventShareParseResult } from '../src/lib/event-share.ts';

import { eventPageForSequence } from '../src/lib/event-pagination.ts';
import { filterEventOutcomes } from '../src/lib/event-search.ts';

const require = createRequire(import.meta.url);
const ts = require('typescript');
const source = readFileSync(new URL('../src/components/LabExplorer.tsx', import.meta.url), 'utf8');
const parsed = ts.createSourceFile('LabExplorer.tsx', source, ts.ScriptTarget.ES2022, true, ts.ScriptKind.TSX);
let handler: any, selectedInitializer: any, initialEffect: any;
function visit(node: any) {
  if (ts.isFunctionDeclaration(node) && node.name?.text === 'applySharedSelection') {
    assert.equal(handler, undefined, 'Exactly one real apply handler is tested'); handler = node;
  }
  if (ts.isVariableDeclaration(node) && node.name.getText(parsed) === 'selectedEventSequence') {
    assert.equal(selectedInitializer, undefined, 'Exactly one displayed selection initializer is tested'); selectedInitializer = node.initializer;
  }
  if (ts.isCallExpression(node) && node.expression.getText(parsed) === 'useEffect'
    && node.arguments[0]?.getText(parsed).includes('parseEventShareSelection')) initialEffect = node.arguments[0];
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
  request?: EventShareParseResult; fetch?: () => Promise<RunDetail>; fetchContext?: () => Promise<LabData> } = {}) {
  const previous = structuredClone(fixture);
  const state = { data: previous, filter: 'SUCCESS', query: 'old-search', reason: 'ACCEPTED' as string | null,
    sensorId: 'previous exact sensor' as string | null,
    selection: { runId: previous.detail.id, mode: 'live', sequence: 1 } as { runId: string; mode: string; sequence: number } | null,
    mode: options.mode ?? 'live', observation: { capturedAt: 'previous-record' } as object | null,
    tab: 'chart', page: 3, loading: options.loading ?? false, error: 'old-error', notice: 'old-notice' };
  const calls: FetchCall[] = [], contextCalls: FetchCall[] = [], businessWrites: string[] = [], loadingWrites: boolean[] = [], timers: number[] = [], cleared: number[] = [];
  const oldController = new AbortController(), controller = { current: oldController }, mounted = { current: true };
  const shareInFlight = { current: options.inFlight ?? false };
  const dependencies = {
    interactive: options.interactive ?? true, loading: options.loading ?? false, mode: options.mode ?? 'live', shareInFlight,
    shareRequest: options.request ?? request, controller, mounted, apiBase: '/public-api', AbortController,
    fetchRun: async (base: string, id: string, signal: AbortSignal) => { calls.push({ base, id, signal }); return options.fetch ? options.fetch() : response; },
    fetchLabForRun: async (base: string, id: string, signal: AbortSignal) => {
      contextCalls.push({ base, id, signal });
      return options.fetchContext ? options.fetchContext() : { ...fixture, detail: response };
    },
    setMode: (value: string) => { businessWrites.push('mode'); state.mode = value; },
    setObservation: (value: object | null) => { businessWrites.push('observation'); state.observation = value; },
    resolveEventShareSelection, filterEventOutcomes, eventPageForSequence, eventPageSize: 25,
    setEventPageIndex: (value: number) => { businessWrites.push('page'); state.page = value; },
    setLoading: (value: boolean) => { state.loading = value; loadingWrites.push(value); },
    setError: (value: string) => { state.error = value; },
    setShareNotice: (value: string) => { state.notice = value; },
    setData: (update: (data: LabData) => LabData) => { businessWrites.push('data'); state.data = update(state.data); },
    setFilter: (value: string) => { businessWrites.push('filter'); state.filter = value; },
    setEventQuery: (value: string) => { businessWrites.push('query'); state.query = value; },
    setEventReason: (value: string | null) => { businessWrites.push('reason'); state.reason = value; },
    setEventSensorId: (value: string | null) => { businessWrites.push('sensor'); state.sensorId = value; },
    setEventSelection: (value: typeof state.selection) => { businessWrites.push('selection'); state.selection = value; },
    setTab: (value: string) => { businessWrites.push('tab'); state.tab = value; },
    describeLiveFailure: () => 'READ_FAILED', liveFailureOf: (failure: unknown) => failure,
    setTimeout: (_callback: () => void, duration: number) => { timers.push(duration); return timers.length; },
    clearTimeout: (id: number) => { cleared.push(id); },
  };
  const apply: () => Promise<void> = new Function(...Object.keys(dependencies), compiled.outputText + '\nreturn applySharedSelection;')(...Object.values(dependencies));
  return { apply, state, previous, calls, contextCalls, businessWrites, loadingWrites, timers, cleared, oldController, controller, mounted, shareInFlight };
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
  assert.equal(h.state.sensorId, null, 'A legacy share without an exact sensor clears the previous sensor condition');
  assert.deepEqual(h.state.selection, { runId: response.id, mode: 'live', sequence: 4 }); assert.equal(h.state.tab, 'events');
  assert.equal(h.state.page, 0);
  assert.match(h.state.notice, /4번 이벤트/); assert.match(h.state.notice, /원래 공유 시점의 결과를 고정하지 않습니다/);
  assert.deepEqual(h.loadingWrites, [true, false]); assert.equal(h.shareInFlight.current, false); assert.deepEqual(h.timers, [8000]); assert.deepEqual(h.cleared, [1]);
});

test('shared event restoration opens the page of its filtered position rather than sequence or raw position', async () => {
  const base = fixture.detail.outcomes[3]!;
  const outcomes = Array.from({ length: 130 }, (_, index) => ({ ...base,
    sequence: index === 125 ? 4 : 1000 + index,
    eventId: index % 2 === 1 ? 'evt-003' : 'other-event',
    status: index % 2 === 1 ? 'DUPLICATE' as const : 'SUCCESS' as const,
    reason: index % 2 === 1 ? 'DUPLICATE_EVENT_ID' : 'ACCEPTED',
  }));
  const detail = { ...response, inputCount: 130, successCount: 65, duplicateCount: 65,
    failureCount: 0, pendingCount: 0, outcomes };
  const h = harness({ fetch: async () => detail });
  await h.apply();
  assert.equal(h.state.data.detail, detail); assert.equal(h.state.selection?.sequence, 4);
  assert.equal(h.state.page, 2, 'Sequence 4 is filtered position 62 and raw position 125');
});

test('missing and filtered shared sequences clear old selection without silently choosing another event', async () => {
  for (const [sequence, notice] of [[999, /이번 응답에 없어/], [3, /조건에서 제외/]] as const) {
    const h = harness({ request: { kind: 'valid', selection: { ...request.selection, sequence } } });
    await h.apply();
    assert.equal(h.state.data.detail, response); assert.equal(h.state.selection, null); assert.equal(h.state.tab, 'events');
    assert.equal(h.state.page, 0);
    assert.equal(h.state.query, '  EVT-003  '); assert.match(h.state.notice, notice);
  }
});

test('shared raw exact sensor restores only its own rows and locates or rejects its selected sequence', async () => {
  for (const sensorId of ['', ' ', 'SENSOR-A', ' sensor-a ']) {
    const outcomes = Array.from({ length: 130 }, (_, index) => ({ ...fixture.detail.outcomes[0]!,
      sequence: index === 125 ? 4 : 1000 + index,
      sensorId: index % 2 === 1 ? sensorId : 'other-sensor',
      eventId: `event-${index}`,
    }));
    const detail = { ...response, inputCount: 130, successCount: 130, duplicateCount: 0,
      failureCount: 0, pendingCount: 0, outcomes };
    for (const [sequence, expectedPage, selected, notice] of [
      [4, 2, 4, /4번 이벤트/],
      [1124, 0, null, /조건에서 제외/],
      [9999, 0, null, /이번 응답에 없어/],
    ] as const) {
      const h = harness({ request: { kind: 'valid', selection: { ...request.selection,
        filters: { status: 'ALL', query: '', reason: null, sensorId }, sequence } }, fetch: async () => detail });
      await h.apply();
      assert.equal(h.calls.length, 1); assert.equal(h.state.data.detail, detail);
      assert.equal(h.state.sensorId, sensorId, 'Empty, whitespace and case remain raw exact conditions');
      assert.equal(h.state.page, expectedPage);
      assert.deepEqual(h.state.selection, selected === null ? null : { runId: detail.id, mode: 'live', sequence: selected });
      assert.equal(h.state.tab, 'events'); assert.match(h.state.notice, notice);
    }
  }
});

test('failed shared read preserves previous data, filters and event selection', async () => {
  const h = harness({ fetch: async () => { throw new Error('network unavailable'); } });
  const before = { data: h.state.data, filter: h.state.filter, query: h.state.query, reason: h.state.reason, sensorId: h.state.sensorId,
    selection: h.state.selection, tab: h.state.tab, page: h.state.page };
  await h.apply();
  for (const key of ['data', 'filter', 'query', 'reason', 'sensorId', 'selection', 'tab', 'page'] as const) assert.equal(h.state[key], before[key]);
  assert.deepEqual(h.businessWrites, []); assert.match(h.state.notice, /이전 실행·조건·선택을 유지/); assert.match(h.state.notice, /READ_FAILED/);
  assert.equal(h.state.loading, false); assert.equal(h.shareInFlight.current, false); assert.deepEqual(h.cleared, [1]);
});

test('noninteractive, busy and invalid requests cannot fetch or change displayed selection', async () => {
  for (const options of [{ interactive: false }, { loading: true }, { inFlight: true },
    { request: { kind: 'absent' } as const }, { request: { kind: 'invalid' } as const }]) {
    const h = harness(options); const before = structuredClone(h.state);
    await h.apply();
    assert.deepEqual(h.calls, []); assert.deepEqual(h.contextCalls, []); assert.deepEqual(h.businessWrites, []); assert.deepEqual(h.state, before);
    assert.deepEqual(h.timers, []); assert.equal(h.oldController.signal.aborted, false);
  }
});

test('valid shared entry waits for explicit read while ordinary and invalid entry retain automatic refresh', () => {
  assert.ok(initialEffect);
  const printedEffect = ts.createPrinter().printNode(ts.EmitHint.Expression, initialEffect, parsed);
  const code = ts.transpileModule('const initialize = ' + printedEffect + ';', {
    compilerOptions: { target: ts.ScriptTarget.ES2022 }, reportDiagnostics: true,
  });
  assert.equal(code.diagnostics.length, 0);
  for (const [search, expectedKind, refreshes] of [
    ['?labRun=outside-recent-list&labStatus=FAILED&labQuery=', 'valid', 0],
    ['', 'absent', 1], ['?labRun=broken', 'invalid', 1],
  ] as const) {
    let calls = 0, interactive = false, received: EventShareParseResult | null = null;
    const mounted = { current: false }, controller = { current: new AbortController() };
    const dependencies = { mounted, controller, window: { location: { search } }, parseEventShareSelection,
      setInteractive: (value: boolean) => { interactive = value; },
      setShareRequest: (value: EventShareParseResult) => { received = value; },
      refresh: async () => { calls += 1; },
    };
    const initialize = new Function(...Object.keys(dependencies), code.outputText + '\nreturn initialize;')(...Object.values(dependencies));
    const cleanup = initialize();
    assert.equal(calls, refreshes); assert.equal((received as EventShareParseResult | null)?.kind, expectedKind);
    assert.equal(interactive, true); assert.equal(mounted.current, true);
    cleanup(); assert.equal(mounted.current, false); assert.equal(controller.current.signal.aborted, true);
  }
});

test('fixture and recorded explicit reads commit a complete live context only after success', async () => {
  for (const mode of ['fixture', 'recorded']) {
    let resolve!: (data: LabData) => void;
    const promise = new Promise<LabData>(done => { resolve = done; });
    const h = harness({ mode, fetchContext: () => promise });
    const context = { ...structuredClone(fixture), detail: response, observedAt: response.observedAt };
    const task = h.apply(); await h.apply();
    assert.equal(h.contextCalls.length, 1); assert.equal(h.contextCalls[0]!.id, response.id);
    assert.equal(h.calls.length, 0); assert.equal(h.state.mode, mode);
    assert.equal(h.state.data, h.previous); assert.deepEqual(h.businessWrites, []);
    resolve(context); await task;
    assert.equal(h.state.data, context); assert.equal(h.state.mode, 'live'); assert.equal(h.state.observation, null);
    assert.equal(h.state.filter, 'DUPLICATE'); assert.equal(h.state.selection?.runId, response.id);
    assert.equal(h.calls.length, 0, 'Full context already includes the exact detail, with no second detail read');
  }
});

test('failed or superseded full-context reads preserve fallback provenance and conditions', async () => {
  for (const mode of ['fixture', 'recorded']) {
    for (const outcome of ['failure', 'superseded', 'unmounted']) {
      let resolve!: (data: LabData) => void, reject!: (reason: Error) => void;
      const promise = new Promise<LabData>((a, b) => { resolve = a; reject = b; });
      const h = harness({ mode, fetchContext: () => promise });
      const before = structuredClone(h.state);
      const task = h.apply();
      if (outcome === 'failure') reject(new Error('HTTP 429 or invalid response'));
      else {
        if (outcome === 'superseded') h.controller.current = new AbortController();
        else h.mounted.current = false;
        resolve({ ...fixture, detail: response });
      }
      await task;
      assert.deepEqual(h.businessWrites, []); assert.equal(h.calls.length, 0);
      for (const key of ['data', 'mode', 'observation', 'filter', 'query', 'reason', 'sensorId', 'selection', 'tab', 'page'] as const)
        assert.deepEqual(h.state[key], before[key]);
      assert.equal(h.shareInFlight.current, false); assert.deepEqual(h.cleared, [1]);
    }
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
