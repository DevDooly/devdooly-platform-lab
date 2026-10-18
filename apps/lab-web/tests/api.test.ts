import assert from 'node:assert/strict';
import { createServer } from 'node:http';
import { readFile } from 'node:fs/promises';
import { test } from 'node:test';
import { fetchLab, fetchRun, getJson, isRun, isRunDetail } from '../src/lib/api.ts';

const sample = JSON.parse(await readFile(new URL('../src/data/snapshot.json', import.meta.url), 'utf8'));
const expected = JSON.parse(await readFile(new URL('../../../tests/scenarios/sensor-validation-v1.json', import.meta.url), 'utf8'));
const observedAt = '2026-10-11T10:00:00Z';
const run = { ...sample.runs[0], startedAt: observedAt, completedAt: observedAt };
const detail = { ...sample.detail, ...run, observedAt };
const summary = { ...sample.summary, status: 'UP', observedAt };

test('fixture expected totals are balanced; snapshot never claims observed runtime', () => {
  assert.equal(sample.detail.inputCount, expected.expected.inputCount);
  assert.deepEqual(sample.detail.outcomes.map(({ sequence, status, reason }: { sequence: number; status: string; reason: string }) => ({ sequence, status, reason })), expected.expectedOutcomes);
  assert.deepEqual([sample.detail.successCount, sample.detail.failureCount, sample.detail.duplicateCount, sample.detail.pendingCount], [7, 3, 2, 0]);
  assert.equal(sample.detail.series.length, 7);
  assert.equal(sample.observedAt, null);
  assert.equal(sample.detail.startedAt, null);
  assert.equal(sample.releases.length, 0);
  assert.equal(sample.summary.publicExecutionEnabled, false);
  assert.ok(sample.summary.components.every((component: {status: string}) => component.status !== 'RUNNING'));
});
test('contract accepts real observed timestamps and rejects inconsistent counts', () => {
  assert.equal(isRun(run), true);
  assert.equal(isRun({ ...run, inputCount: 99 }), false);
  assert.equal(isRun({ ...run, successCount: -1 }), false);
  assert.equal(isRun(sample.runs[0]), false);
  assert.equal(isRunDetail(detail), true);
  assert.equal(isRunDetail({ ...detail, series: [{ eventTime: 'invalid-time', sensorId: 'a', value: 2 }] }), false);
  assert.equal(isRunDetail({ ...detail, outcomes: [{ ...detail.outcomes[0], status: 'INVENTED' }] }), false);
});
test('HTTP adapter loads list, detail, runtime summary and releases without a POST', async () => {
  const paths: string[] = [];
  const server = createServer((request, response) => {
    paths.push(`${request.method} ${request.url}`);
    response.setHeader('Content-Type', 'application/json');
    if (request.url === '/api/demo/runs') response.end(JSON.stringify({ items: [run], observedAt }));
    else if (request.url === '/api/demo/runs/' + run.id) response.end(JSON.stringify(detail));
    else if (request.url === '/api/platform/summary') response.end(JSON.stringify(summary));
    else if (request.url === '/api/platform/releases') response.end(JSON.stringify({ items: [], observedAt }));
    else { response.writeHead(404); response.end('{}'); }
  });
  await new Promise<void>(resolve => server.listen(0, '127.0.0.1', resolve));
  const address = server.address();
  assert.ok(address && typeof address === 'object');
  const base = `http://127.0.0.1:${address.port}/api`;
  try {
    const result = await fetchLab(base + '/');
    assert.equal(result.detail.successCount, 7);
    assert.equal(result.summary.status, 'UP');
    assert.equal(paths.length, 4);
    assert.ok(paths.every(path => path.startsWith('GET ')));
    await assert.rejects(fetchRun(base, 'unknown/id'), /공개 조회 주소/);
    assert.equal(paths.length, 4, 'A noncanonical public detail path must not send another request');
  } finally { await new Promise<void>((resolve, reject) => server.close(error => error ? reject(error) : resolve())); }
});
test('malformed HTTP payload is rejected instead of being shown as live data', async () => {
  const server = createServer((_request, response) => { response.setHeader('Content-Type', 'application/json'); response.end(JSON.stringify({ items: [{ ...run, inputCount: 999 }], observedAt })); });
  await new Promise<void>(resolve => server.listen(0, '127.0.0.1', resolve));
  const address = server.address(); assert.ok(address && typeof address === 'object');
  try { await assert.rejects(fetchLab(`http://127.0.0.1:${address.port}/api`), /실행 목록 형식/); }
  finally { await new Promise<void>((resolve, reject) => server.close(error => error ? reject(error) : resolve())); }
});

test('public read adapter rejects a redirect without requesting its target', async () => {
  let requests = 0;
  let targetRequests = 0;
  const server = createServer((request, response) => {
    requests += 1;
    if (request.url === '/redirect-target') {
      targetRequests += 1;
      response.setHeader('Content-Type', 'application/json');
      response.end('{}');
    } else {
      response.writeHead(302, { Location: '/redirect-target' });
      response.end();
    }
  });
  await new Promise<void>(resolve => server.listen(0, '127.0.0.1', resolve));
  const address = server.address(); assert.ok(address && typeof address === 'object');
  try {
    await assert.rejects(getJson(`http://127.0.0.1:${address.port}/api`, '/platform/summary'), TypeError);
    assert.equal(requests, 1);
    assert.equal(targetRequests, 0);
  } finally {
    await new Promise<void>((resolve, reject) => server.close(error => error ? reject(error) : resolve()));
  }
});
