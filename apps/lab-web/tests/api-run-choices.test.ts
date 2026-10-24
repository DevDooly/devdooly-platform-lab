import assert from 'node:assert/strict';
import { test } from 'node:test';
import { parseApiRunChoices } from '../src/lib/api-run-choices.ts';

const observedAt = '2026-10-24T03:00:00Z';
function run(id: string) {
  return { id, name: 'Same scenario', status: 'COMPLETED', synthetic: true, seed: 42,
    inputCount: 3, successCount: 2, failureCount: 1, duplicateCount: 0, pendingCount: 0,
    startedAt: '2026-10-24T02:59:00Z', completedAt: '2026-10-24T02:59:01Z' };
}

test('choices preserve distinct IDs and response order when names match', () => {
  const choices = parseApiRunChoices(JSON.stringify({ items: [run('run-z'), run('run-a')], observedAt }));
  assert.ok(choices);
  assert.deepEqual(choices.items.map(item => ({ id: item.id, name: item.name })), [
    { id: 'run-z', name: 'Same scenario' },
    { id: 'run-a', name: 'Same scenario' },
  ]);
  assert.equal(choices.items[0].successCount, 2);
  assert.equal(choices.items[1].failureCount, 1);
  assert.equal(choices.observedAt, '2026-10-24T03:00:00Z');
});

test('a valid empty response remains a valid empty choice list', () => {
  assert.deepEqual(parseApiRunChoices('{"items":[],"observedAt":"2026-10-24T03:00:00Z"}'), {
    items: [], observedAt: '2026-10-24T03:00:00Z',
  });
});

test('invalid DTOs, IDs, duplicate IDs, timestamps and JSON cannot become choices', () => {
  const invalidPayloads = [
    { items: [{ ...run('run-a'), inputCount: 99 }], observedAt },
    { items: [{ ...run('run-a'), synthetic: 'true' }], observedAt },
    { items: [run('../run-a')], observedAt },
    { items: [run('')], observedAt },
    { items: [run('run-a'), run('run-a')], observedAt },
    { items: [run('run-a')], observedAt: 'invalid-time' },
    { items: [run('run-a')], observedAt: 1792810800000 },
    { items: [run('run-a')] },
    { items: {}, observedAt },
    null,
  ];
  for (const payload of invalidPayloads) assert.equal(parseApiRunChoices(JSON.stringify(payload)), null);
  assert.equal(parseApiRunChoices('{invalid json'), null);
});
