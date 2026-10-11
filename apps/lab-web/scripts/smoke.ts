import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { fetchLab } from '../src/lib/api.ts';

const uiUrl = new URL(process.argv[2] || 'http://127.0.0.1:4321/');
const apiBase = process.argv[3] || new URL('/api', uiUrl).href;
const expected = JSON.parse(await readFile(new URL('../../../tests/scenarios/sensor-validation-v1.json', import.meta.url), 'utf8'));
const response = await fetch(uiUrl, { signal: AbortSignal.timeout(8000) });
assert.equal(response.status, 200, 'UI must return HTTP 200');
const html = await response.text();
assert.ok(html.includes('DevDooly'), 'Expected Lab document');
assert.ok(html.includes('합성 데이터 샘플'), 'Static fallback must identify synthetic sample');
const live = await fetchLab(apiBase, AbortSignal.timeout(8000));
for (const [key, value] of Object.entries(expected.expected)) assert.equal(live.detail[key as keyof typeof live.detail], value, `Unexpected ${key}`);
assert.deepEqual(live.detail.outcomes.map(({ sequence, status, reason }) => ({ sequence, status, reason })), expected.expectedOutcomes);
assert.equal(live.summary.publicExecutionEnabled, false, 'This MVP must stay read-only');
console.log(JSON.stringify({ uiStatus: response.status, api: 'connected', scenario: live.detail.scenario, counts: expected.expected, observedAt: live.observedAt, database: live.summary.components.find(component => component.name === 'DATABASE')?.detail, environment: live.summary.environment, publicExecutionEnabled: false }, null, 2));
