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
  for (const scenario of ['live', 'recorded', 'missing', 'malformed', 'cached'] as const) {
    await context.test(scenario, async () => {
      const record = testObservation();
      const server = createServer((request, response) => {
        response.setHeader('Content-Type', 'application/json');
        if (request.url === '/data/lab-observation.json') {
          if (scenario === 'missing') { response.writeHead(404); response.end('{}'); }
          else if (scenario === 'malformed') response.end(JSON.stringify({ ...record, provenance: { ...record.provenance, sourceCommit: 'unknown' } }));
          else if (scenario === 'cached') { response.writeHead(503); response.end('{}'); }
          else response.end(JSON.stringify(record));
        } else if (scenario !== 'live') { response.writeHead(503); response.end('{}'); }
        else if (request.url === '/api/demo/runs') response.end(JSON.stringify({ items: record.data.runs, observedAt: record.data.observedAt }));
        else if (request.url === '/api/demo/runs/synthetic-v1-seed-42') response.end(JSON.stringify(record.data.detail));
        else if (request.url === '/api/platform/summary') response.end(JSON.stringify(record.data.summary));
        else if (request.url === '/api/platform/releases') response.end(JSON.stringify({ items: record.data.releases, observedAt: record.data.observedAt }));
        else { response.writeHead(404); response.end('{}'); }
      });
      await new Promise<void>(resolve => server.listen(0, '127.0.0.1', resolve));
      const address = server.address(); assert.ok(address && typeof address === 'object');
      const base = `http://127.0.0.1:${address.port}`;
      try {
        const result = await loadLabSources({ apiBase: base + '/api', observationUrl: base + '/data/lab-observation.json', fixture, signal: AbortSignal.timeout(2000), previousObservation: scenario === 'cached' ? record : null });
        assert.equal(result.mode, scenario === 'live' ? 'live' : ['recorded', 'cached'].includes(scenario) ? 'recorded' : 'fixture');
        if (result.mode === 'recorded') { assert.equal(result.data.observedAt, record.data.observedAt); assert.equal(result.observation?.capturedAt, record.capturedAt); }
        if (result.mode === 'fixture') assert.equal(result.data.detail.startedAt, null);
      } finally { await new Promise<void>((resolve, reject) => server.close(error => error ? reject(error) : resolve())); }
    });
  }
});
