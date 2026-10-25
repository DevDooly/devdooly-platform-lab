import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';
import { parseApiRunResult } from '../src/lib/api-run-result.ts';
import type { RunDetail } from '../src/lib/api.ts';

// Test-only response timestamps; fixture content is not claimed as a live observation.
const fixture = JSON.parse(readFileSync(new URL('../src/data/snapshot.json', import.meta.url), 'utf8'));
function detail(): RunDetail {
  return { ...structuredClone(fixture.detail), id: 'response-run.alpha_01', name: '  저장된 실행 <원문>  ',
    scenario: 'recorded-scenario', description: 'Stored response, not service availability',
    startedAt: '2026-10-26T00:00:00.123456789Z', completedAt: '2026-10-26T00:00:01.000000001Z',
    observedAt: '2026-10-26T00:00:02.987654321Z' };
}
const response = (value: unknown, requestedId = 'response-run.alpha_01') => ({
  path: `/demo/runs/${requestedId}`, json: JSON.stringify(value),
});

test('a matching stored response preserves raw metadata, reported counts, event content, and the original JSON', () => {
  const source = detail();
  source.outcomes[4]!.eventTime = 'unparseable original event time';
  source.outcomes[4]!.reason = '  ORIGINAL_REASON  ';
  const input = Object.freeze({ ...response(source), json: ` \n${JSON.stringify(source, null, 2)}\n ` });
  const originalJson = input.json;
  const parsed = parseApiRunResult(input);
  assert.equal(parsed.kind, 'valid');
  assert.deepEqual(parsed.detail, source);
  assert.deepEqual([parsed.detail.inputCount, parsed.detail.successCount, parsed.detail.failureCount,
    parsed.detail.duplicateCount, parsed.detail.pendingCount], [12, 7, 3, 2, 0]);
  assert.equal(parsed.detail.startedAt, '2026-10-26T00:00:00.123456789Z');
  assert.equal(parsed.detail.observedAt, '2026-10-26T00:00:02.987654321Z');
  assert.equal(input.json, originalJson);
});

test('a complete zero-event response stays valid without inventing events or nonzero counts', () => {
  const source = { ...detail(), inputCount: 0, successCount: 0, failureCount: 0, duplicateCount: 0,
    pendingCount: 0, outcomes: [], series: [], failureReasons: [] };
  assert.deepEqual(parseApiRunResult(response(source)), { kind: 'valid', detail: source });
});

test('identity is checked against the stored request path and mismatch requires an otherwise valid detail', () => {
  const source = detail();
  assert.deepEqual(parseApiRunResult(response(source, 'another-requested-run')), { kind: 'id-mismatch' });
  assert.deepEqual(parseApiRunResult(response({ ...source, id: 'another-run', outcomes: null })), { kind: 'invalid' });
  assert.deepEqual(parseApiRunResult(response(source)), { kind: 'valid', detail: source });
});

test('invalid shapes, inconsistent counts, and incomplete detail responses are not summarized as valid', () => {
  const source = detail();
  const { outcomes: _outcomes, ...withoutOutcomes } = source;
  const { observedAt: _observedAt, ...withoutObservedAt } = source;
  const { scenario: _scenario, ...withoutScenario } = source;
  const invalid = [
    null, [], [source], 'HTTP success', true, 200, {}, { items: [source] },
    { ...source, inputCount: 99 }, { ...source, failureCount: -1 }, { ...source, seed: 0.5 },
    { ...source, pendingCount: 0.5 }, { ...source, synthetic: 'true' },
    { ...source, startedAt: null }, { ...source, completedAt: 'invalid-time' }, { ...source, observedAt: null },
    { ...source, outcomes: [{ ...source.outcomes[0], status: 'INVENTED' }] },
    { ...source, failureReasons: [{ reason: 'INVALID_INPUT', count: -1 }] },
    withoutOutcomes, withoutObservedAt, withoutScenario,
  ];
  for (const value of invalid) assert.deepEqual(parseApiRunResult(response(value)), { kind: 'invalid' });
});

test('only an exact detail path with a permitted one-to-eighty-character ID is accepted', () => {
  for (const id of ['0', 'a'.repeat(80), 'run.a-_9']) {
    const source = { ...detail(), id };
    assert.deepEqual(parseApiRunResult(response(source, id)), { kind: 'valid', detail: source });
  }
  const source = detail();
  const invalidPaths = [
    '', '/demo/runs', '/demo/runs/', '/platform/summary', `/api/demo/runs/${source.id}`,
    `https://example.invalid/demo/runs/${source.id}`, `/demo/runs/${source.id}/`,
    `/demo/runs/${source.id}?other=1`, `/demo/runs/${source.id}#events`,
    `/demo/runs/${source.id}\n`, `/demo/runs/${source.id}\r\n`, `/demo/runs/${source.id} `,
    '/demo/runs/A', '/demo/runs/-leading', '/demo/runs/../other', '/demo/runs/a/b',
    '/demo/runs/a%2Fb', `/demo/runs/${'a'.repeat(81)}`,
  ];
  for (const path of invalidPaths) {
    assert.deepEqual(parseApiRunResult({ path, json: JSON.stringify(source) }), { kind: 'invalid' }, path);
  }
});

test('malformed JSON cannot produce a parsed detail or replace the original response text', () => {
  for (const json of ['', '{', '{"id":', '<html>not JSON</html>', `${JSON.stringify(detail())} trailing`]) {
    const input = Object.freeze({ path: '/demo/runs/response-run.alpha_01', json });
    assert.deepEqual(parseApiRunResult(input), { kind: 'invalid' });
    assert.equal(input.json, json);
  }
});

test('returned event-row length and reported totals stay separate when either is larger', () => {
  for (const outcomes of [detail().outcomes.slice(0, 1), [...detail().outcomes, ...detail().outcomes.slice(0, 2)]]) {
    const source = { ...detail(), outcomes };
    const parsed = parseApiRunResult(response(source));
    assert.equal(parsed.kind, 'valid');
    assert.equal(parsed.detail.inputCount, 12);
    assert.equal(parsed.detail.failureCount, 3);
    assert.equal(parsed.detail.outcomes.length, outcomes.length);
    assert.notEqual(parsed.detail.outcomes.length, parsed.detail.inputCount);
    assert.deepEqual(parsed.detail.outcomes, outcomes);
    assert.deepEqual(parsed.detail.failureReasons, source.failureReasons);
  }
});
