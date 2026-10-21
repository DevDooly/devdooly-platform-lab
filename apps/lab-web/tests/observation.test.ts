import assert from 'node:assert/strict';
import { createServer } from 'node:http';
import { readFile } from 'node:fs/promises';
import { test } from 'node:test';
import { isObservationRecord, loadLabSources, selectDataSource } from '../src/lib/observation.ts';
import type { ObservationRecord } from '../src/lib/observation.ts';
import type { LabData } from '../src/lib/api.ts';

const fixture = JSON.parse(await readFile(new URL('../src/data/snapshot.json', import.meta.url), 'utf8')) as LabData;
const expected = JSON.parse(await readFile(new URL('../../../tests/scenarios/sensor-validation-v1.json', import.meta.url), 'utf8'));
const sourceCommit = 'd'.repeat(40); // Test identity only. No test observation is published.
function testObservation(): ObservationRecord {
  const data = structuredClone(fixture);
  delete data.capturedAt; delete data.snapshotNote;
  data.runs = data.runs.map(run => ({ ...run, startedAt: '2026-10-11T10:00:00Z', completedAt: '2026-10-11T10:00:01Z' }));
  data.detail = { ...data.detail, ...data.runs[0]!, observedAt: '2026-10-11T10:00:03Z' };
  data.summary = { ...data.summary, status: 'UP', environment: 'kubernetes', sourceCommit, observedAt: '2026-10-11T10:00:02Z' };
  data.summary.components = data.summary.components.map(component => component.name === 'API' || component.name === 'DATABASE' ? { ...component, status: 'RUNNING', detail: component.name === 'DATABASE' ? 'MariaDB' : 'Spring Boot 조회 API' } : component);
  data.releases = [{ service: 'api', version: '0.1.0', sourceCommit, imageDigest: null, deploymentStatus: 'RUNTIME_ONLY', startedAt: '2026-10-11T10:00:00Z' }];
  data.observedAt = data.summary.observedAt;
  return { schemaVersion: 1, kind: 'observed', capturedAt: '2026-10-11T10:00:05Z', provenance: { environment: 'mini-pc', sourceCommit, collectorVersion: '1', evidenceUrl: 'https://github.com/DevDooly/devdooly-platform-lab/actions/runs/1' }, data };
}

test('observed record preserves actual collection, execution and query times with matching source', () => {
  const record = testObservation();
  assert.equal(isObservationRecord(record), true);
  assert.notEqual(record.capturedAt, record.data.detail.startedAt);
  assert.deepEqual(record.data.detail.outcomes.map(({ sequence, status, reason }) => ({ sequence, status, reason })), expected.expectedOutcomes);
  assert.equal(record.data.summary.components.find(component => component.name === 'JENKINS')?.status, 'NOT_CONFIGURED');
});
test('unknown source, mismatched source, future observation and hidden extra fields are rejected', () => {
  const unknown = testObservation(); unknown.provenance.sourceCommit = 'unknown'; assert.equal(isObservationRecord(unknown), false);
  const mismatch = testObservation(); mismatch.data.summary.sourceCommit = 'a'.repeat(40); assert.equal(isObservationRecord(mismatch), false);
  const future = testObservation(); future.data.detail.observedAt = '2026-10-11T10:00:06Z'; assert.equal(isObservationRecord(future), false);
  const rawAdmin = { ...testObservation(), token: 'must-not-be-published' }; assert.equal(isObservationRecord(rawAdmin), false);
  const nested = testObservation(); Object.assign(nested.data.summary.components[0]!, { token: 'must-not-be-published' }); assert.equal(isObservationRecord(nested), false);
  const credentialUrl = testObservation(); credentialUrl.provenance.evidenceUrl = 'https://github.com/DevDooly?token=must-not-be-published'; assert.equal(isObservationRecord(credentialUrl), false);
  const inconsistent = testObservation(); inconsistent.data.detail.series[0]!.value += 1; assert.equal(isObservationRecord(inconsistent), false);
  const classification = testObservation(); classification.data.detail.outcomes[0]!.status = 'FAILED'; assert.equal(isObservationRecord(classification), false);
});
test('source priority is live API, then last observation, then illustrative fixture', () => {
  const record = testObservation();
  assert.equal(selectDataSource(record.data, record, fixture).mode, 'live');
  const selected = selectDataSource(null, record, fixture);
  assert.equal(selected.mode, 'recorded');
  assert.equal(selected.observation?.capturedAt, '2026-10-11T10:00:05Z');
  assert.equal(selectDataSource(null, null, fixture).mode, 'fixture');
});
test('real HTTP fallback keeps records static and handles missing or malformed public files', async context => {
  for (const scenario of ['live', 'recorded', 'missing', 'malformed', 'cached', 'wrong-detail'] as const) {
    await context.test(scenario, async () => {
      const record = testObservation();
      const other = { ...record.data.runs[0]!, id: 'other-listed-run' };
      const paths: string[] = [];
      const server = createServer((request, response) => {
        paths.push(`${request.method} ${request.url}`);
        response.setHeader('Content-Type', 'application/json');
        if (request.url === '/data/lab-observation.json') {
          if (scenario === 'missing') { response.writeHead(404); response.end('{}'); }
          else if (scenario === 'malformed') response.end(JSON.stringify({ ...record, provenance: { ...record.provenance, sourceCommit: 'unknown' } }));
          else if (scenario === 'cached') { response.writeHead(503); response.end('{}'); }
          else response.end(JSON.stringify(record));
        } else if (scenario !== 'live' && scenario !== 'wrong-detail') { response.writeHead(503); response.end('{}'); }
        else if (request.url === '/api/demo/runs') response.end(JSON.stringify({ items: scenario === 'wrong-detail' ? [...record.data.runs, other] : record.data.runs, observedAt: record.data.observedAt }));
        else if (request.url === '/api/demo/runs/synthetic-v1-seed-42') response.end(JSON.stringify(scenario === 'wrong-detail' ? { ...record.data.detail, id: other.id } : record.data.detail));
        else if (request.url === '/api/platform/summary') response.end(JSON.stringify(record.data.summary));
        else if (request.url === '/api/platform/releases') response.end(JSON.stringify({ items: record.data.releases, observedAt: record.data.observedAt }));
        else { response.writeHead(404); response.end('{}'); }
      });
      await new Promise<void>(resolve => server.listen(0, '127.0.0.1', resolve));
      const address = server.address(); assert.ok(address && typeof address === 'object');
      const base = `http://127.0.0.1:${address.port}`;
      try {
        const result = await loadLabSources({ apiBase: base + '/api', observationUrl: base + '/data/lab-observation.json', fixture, signal: AbortSignal.timeout(2000), previousObservation: scenario === 'cached' ? record : null });
        assert.equal(result.mode, scenario === 'live' ? 'live' : ['recorded', 'cached', 'wrong-detail'].includes(scenario) ? 'recorded' : 'fixture');
        assert.deepEqual(result.liveFailure, scenario === 'live' ? null : { kind: scenario === 'wrong-detail' ? 'INVALID_RESPONSE' : 'HTTP_REJECTED', httpStatus: scenario === 'wrong-detail' ? null : 503 });
        if (result.mode === 'recorded') { assert.equal(result.data.observedAt, record.data.observedAt); assert.equal(result.observation?.capturedAt, record.capturedAt); }
        if (result.mode === 'fixture') assert.equal(result.data.detail.startedAt, null);
        if (scenario === 'wrong-detail') {
          assert.equal(isObservationRecord(record), true);
          assert.deepEqual(result.data, record.data);
          assert.deepEqual(result.cachedObservation, record);
          assert.deepEqual(paths.slice().sort(), ['GET /data/lab-observation.json', 'GET /api/demo/runs',
            'GET /api/demo/runs/synthetic-v1-seed-42', 'GET /api/platform/summary', 'GET /api/platform/releases'].sort());
        }
      } finally { await new Promise<void>((resolve, reject) => server.close(error => error ? reject(error) : resolve())); }
    });
  }
});

test('live failure diagnostics preserve the exact last good record through abort, transport and invalid responses', async context => {
  for (const scenario of ['json', 'dto', 'abort', 'network'] as const) await context.test(scenario, async () => {
    const record = testObservation();
    const preserved = structuredClone(record);
    const controller = new AbortController();
    const canary = 'PRIVATE_LIVE_FAILURE_CANARY';
    const methods: string[] = [];
    const server = createServer((request, response) => {
      methods.push(request.method || '');
      if (request.url === '/data/lab-observation.json') { response.writeHead(404); response.end('{}'); }
      else if (scenario === 'network') request.socket.destroy();
      else if (scenario === 'abort') { controller.abort(new Error(canary)); response.destroy(); }
      else { response.setHeader('Content-Type', 'application/json'); response.end(scenario === 'json' ? canary + '{' : JSON.stringify({ items: [{ ...record.data.runs[0], inputCount: 999 }], observedAt: record.data.observedAt })); }
    });
    await new Promise<void>(resolve => server.listen(0, '127.0.0.1', resolve));
    const address = server.address(); assert.ok(address && typeof address === 'object');
    const base = `http://127.0.0.1:${address.port}`;
    try {
      const result = await loadLabSources({ apiBase: base + '/api', observationUrl: base + '/data/lab-observation.json', fixture, signal: controller.signal, previousObservation: record });
      assert.equal(result.mode, 'recorded');
      assert.deepEqual(result.data, preserved.data); assert.deepEqual(result.observation, preserved);
      assert.deepEqual(result.cachedObservation, preserved); assert.deepEqual(record, preserved);
      assert.deepEqual(result.liveFailure, { kind: scenario === 'abort' ? 'REQUEST_ABORTED' : scenario === 'network' ? 'NETWORK_UNVERIFIED' : 'INVALID_RESPONSE', httpStatus: null });
      const diagnostic = JSON.stringify(result.liveFailure);
      assert.equal(diagnostic.includes(canary), false); assert.equal(diagnostic.includes(base), false);
      assert.ok(methods.length > 0 && methods.every(method => method === 'GET'));
    } finally { await new Promise<void>((resolve, reject) => server.close(error => error ? reject(error) : resolve())); }
  });
});

test('a successful later live read clears the failure while keeping the original cached observation', async () => {
  const record = testObservation();
  let live = false;
  let initialApiRequests = 0;
  let allInitialApiRequests!: () => void;
  const initialBatch = new Promise<void>(resolve => { allInitialApiRequests = resolve; });
  const paths: string[] = [];
  const server = createServer((request, response) => {
    paths.push(`${request.method} ${request.url}`);
    response.setHeader('Content-Type', 'application/json');
    if (request.url === '/data/lab-observation.json') { response.writeHead(404); response.end('{}'); }
    else if (!live) {
      initialApiRequests += 1; response.writeHead(500); response.end('PRIVATE_LIVE_FAILURE_CANARY');
      if (initialApiRequests === 3) allInitialApiRequests();
    } else if (request.url === '/api/demo/runs') response.end(JSON.stringify({ items: record.data.runs, observedAt: record.data.observedAt }));
    else if (request.url === '/api/demo/runs/' + record.data.detail.id) response.end(JSON.stringify(record.data.detail));
    else if (request.url === '/api/platform/summary') response.end(JSON.stringify(record.data.summary));
    else if (request.url === '/api/platform/releases') response.end(JSON.stringify({ items: record.data.releases, observedAt: record.data.observedAt }));
    else { response.writeHead(404); response.end('{}'); }
  });
  await new Promise<void>(resolve => server.listen(0, '127.0.0.1', resolve));
  const address = server.address(); assert.ok(address && typeof address === 'object');
  const base = `http://127.0.0.1:${address.port}`;
  try {
    const options = { apiBase: base + '/api', observationUrl: base + '/data/lab-observation.json', fixture, previousObservation: record };
    const failed = await loadLabSources(options);
    await initialBatch;
    assert.equal(failed.mode, 'recorded'); assert.deepEqual(failed.liveFailure, { kind: 'HTTP_REJECTED', httpStatus: 500 });
    assert.deepEqual(failed.data, record.data); assert.deepEqual(failed.cachedObservation, record);
    assert.equal(paths.length, 4);
    live = true;
    const recovered = await loadLabSources({ ...options, previousObservation: failed.cachedObservation });
    assert.equal(recovered.mode, 'live'); assert.equal(recovered.liveFailure, null); assert.equal(recovered.observation, null);
    assert.deepEqual(recovered.data, record.data); assert.deepEqual(recovered.cachedObservation, record);
    assert.equal(paths.length, 9); assert.ok(paths.every(path => path.startsWith('GET ')));
  } finally { await new Promise<void>((resolve, reject) => server.close(error => error ? reject(error) : resolve())); }
});
