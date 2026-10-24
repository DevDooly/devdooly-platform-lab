import assert from 'node:assert/strict';
import test from 'node:test';
import { createRequire } from 'node:module';
import { readFileSync } from 'node:fs';
import type { Outcome } from '../src/lib/api.ts';
import { eventPage, eventPageForSequence, type EventPageSize } from '../src/lib/event-pagination.ts';
import { filterEventOutcomes } from '../src/lib/event-search.ts';

const require = createRequire(import.meta.url);
const ts = require('typescript');
const source = readFileSync(new URL('../src/components/LabExplorer.tsx', import.meta.url), 'utf8');
const parsed = ts.createSourceFile('LabExplorer.tsx', source, ts.ScriptTarget.ES2022, true, ts.ScriptKind.TSX);
const names = ['changeEventFilter', 'changeEventQuery', 'changeEventReason', 'resetEventSearch',
  'selectEvent', 'focusEventTable', 'changeEventPage', 'changeEventPageSize'] as const;
const handlers: any[] = [];
let selectedInitializer: any;
function visit(node: any) {
  if (ts.isFunctionDeclaration(node) && names.includes(node.name?.text)) handlers.push(node);
  if (ts.isVariableDeclaration(node) && node.name.getText(parsed) === 'selectedEventSequence') {
    assert.equal(selectedInitializer, undefined); selectedInitializer = node.initializer;
  }
  ts.forEachChild(node, visit);
}
visit(parsed);
assert.deepEqual(handlers.map(node => node.name.text).sort(), [...names].sort());
assert.ok(selectedInitializer);
const printer = ts.createPrinter();
// Run the real handlers and displayed-selection initializer, not copies of their implementation.
const handlerSource = handlers.map(node => printer.printNode(ts.EmitHint.Unspecified, node, parsed)).join('\n')
  + '\nconst selectedEventSequence = ' + printer.printNode(ts.EmitHint.Unspecified, selectedInitializer, parsed) + ';';
const compiled = ts.transpileModule(handlerSource, { compilerOptions: {
  target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.ESNext,
}, reportDiagnostics: true });
assert.equal(compiled.diagnostics.length, 0);

type Selection = { runId: string; mode: string; sequence: number } | null;
function rows(length = 120): Outcome[] {
  return Array.from({ length }, (_, index) => ({ sequence: index === 75 ? 4 : 1000 + index,
    eventId: 'repeated-id', sensorId: index % 2 === 1 ? 'chosen' : 'other',
    eventTime: '2026-10-24T00:00:00Z', value: index, status: 'SUCCESS', reason: 'ACCEPTED' }));
}

function harness(options: { interactive?: boolean; loading?: boolean; outcomes?: Outcome[]; selection?: Selection } = {}) {
  const outcomes = options.outcomes ?? rows();
  const detail = { id: 'display-run', outcomes };
  const state = { filter: 'FAILED', query: 'old-query', reason: 'OLD_REASON' as string | null,
    selection: options.selection === undefined ? { runId: detail.id, mode: 'live', sequence: outcomes[0]!.sequence } : options.selection,
    page: 3, size: 25 as EventPageSize };
  const writes: string[] = [], focusCalls: { id: string; operation: string; options: unknown }[] = [];
  let sharedChanges = 0;
  function invoke(name: typeof names[number], value?: unknown) {
    const dependencies = {
      interactive: options.interactive ?? true, loading: options.loading ?? false, outcomes, detail, data: { detail }, mode: 'live',
      eventSelection: state.selection, eventPageSize: state.size, eventPage, eventPageForSequence,
      markShareChanged: () => { sharedChanges++; },
      setFilter: (value: string) => { writes.push('filter'); state.filter = value; },
      setEventQuery: (value: string) => { writes.push('query'); state.query = value; },
      setEventReason: (value: string | null) => { writes.push('reason'); state.reason = value; },
      setEventSelection: (value: Selection) => { writes.push('selection'); state.selection = value; },
      setEventPageIndex: (value: number) => { writes.push('page'); state.page = value; },
      setEventPageSize: (value: EventPageSize) => { writes.push('size'); state.size = value; },
      document: { getElementById: (id: string) => ({
        focus: (options: unknown) => focusCalls.push({ id, operation: 'focus', options }),
        scrollIntoView: (options: unknown) => focusCalls.push({ id, operation: 'scroll', options }),
      }) },
    };
    const actual = new Function(...Object.keys(dependencies), compiled.outputText + `\nreturn ${name};`)(...Object.values(dependencies));
    actual(value);
  }
  return { state, outcomes, writes, focusCalls, invoke, sharedChanges: () => sharedChanges };
}

test('search, status, reason and reset changes return to the first page and clear the old selection', () => {
  for (const [name, value, field] of [['changeEventFilter', 'DUPLICATE', 'filter'],
    ['changeEventQuery', '  sensor-a  ', 'query'], ['changeEventReason', '', 'reason']] as const) {
    const h = harness(); h.invoke(name, value);
    assert.equal(h.state[field], value); assert.equal(h.state.page, 0); assert.equal(h.state.selection, null);
    assert.equal(h.sharedChanges(), 1); assert.deepEqual(h.focusCalls, []);
  }
  const h = harness(); h.invoke('resetEventSearch');
  assert.deepEqual({ filter: h.state.filter, query: h.state.query, reason: h.state.reason, page: h.state.page, selection: h.state.selection },
    { filter: 'ALL', query: '', reason: null, page: 0, selection: null });
});

test('table page changes clamp to filtered bounds, preserve selection and focus the table heading', () => {
  const h = harness({ outcomes: rows(63) }); const selected = h.state.selection;
  h.invoke('changeEventPage', 99); assert.equal(h.state.page, 2);
  h.invoke('changeEventPage', -1); assert.equal(h.state.page, 0);
  assert.equal(h.state.selection, selected); assert.equal(h.sharedChanges(), 0);
  assert.deepEqual(h.focusCalls, [0, 1].flatMap(() => [
    { id: 'event-table-title', operation: 'focus', options: { preventScroll: true } },
    { id: 'event-table-title', operation: 'scroll', options: { behavior: 'auto', block: 'start' } },
  ]));
});

test('changing page size keeps a valid selected event visible and otherwise starts at the first page', () => {
  const h = harness({ selection: { runId: 'display-run', mode: 'live', sequence: 4 } });
  const selected = h.state.selection;
  h.invoke('changeEventPageSize', 50);
  assert.equal(h.state.size, 50); assert.equal(h.state.page, 1); assert.equal(h.state.selection, selected);
  h.invoke('changeEventPageSize', 25); assert.equal(h.state.page, 3);
  for (const selection of [null, { runId: 'display-run', mode: 'live', sequence: 9999 }]) {
    const unselected = harness({ selection }); unselected.invoke('changeEventPageSize', 100);
    assert.equal(unselected.state.size, 100); assert.equal(unselected.state.page, 0);
  }
  assert.equal(h.sharedChanges(), 0);
  assert.ok(h.focusCalls.every(call => call.id === 'event-table-title'));
});

test('selecting an event navigates by sparse sequence in the filtered array rather than raw input position', () => {
  const filtered = filterEventOutcomes(rows(), { status: 'ALL', query: 'chosen', reason: null });
  const h = harness({ outcomes: filtered, selection: null });
  h.invoke('selectEvent', 4);
  assert.equal(h.state.page, 1, 'Sequence 4 is filtered position 37, raw position 75');
  assert.deepEqual(h.state.selection, { runId: 'display-run', mode: 'live', sequence: 4 });
  assert.deepEqual(h.focusCalls, []);
  h.invoke('selectEvent', 4);
  assert.equal(h.focusCalls[0]!.id, 'event-flow-detail-title'); assert.equal(h.focusCalls[0]!.operation, 'focus');
  h.invoke('selectEvent', null); assert.equal(h.state.selection, null); assert.equal(h.state.page, 1);
});

test('preparation and active-read locks prevent all paging and search state transitions', () => {
  const actions = [['changeEventFilter', 'SUCCESS'], ['changeEventQuery', 'new'], ['changeEventReason', null],
    ['resetEventSearch', undefined], ['selectEvent', 4], ['changeEventPage', 1], ['changeEventPageSize', 50]] as const;
  for (const options of [{ interactive: false }, { loading: true }]) {
    const h = harness(options); const before = structuredClone(h.state);
    for (const [name, value] of actions) h.invoke(name, value);
    assert.deepEqual(h.state, before); assert.deepEqual(h.writes, []); assert.deepEqual(h.focusCalls, []); assert.equal(h.sharedChanges(), 0);
  }
});
