import assert from 'node:assert/strict';
import { createServer } from 'node:http';
import { readFile } from 'node:fs/promises';
import { test } from 'node:test';
import { loadPlatformObservation, MAX_PLATFORM_OBSERVATION_BYTES, platformObservationView, PLATFORM_STALE_AFTER_MS, validatePlatformObservation } from '../src/lib/platform-observation.ts';
import type { PlatformObservationRecord } from '../src/lib/platform-observation.ts';

// Test identities/times only. This factory never writes a published observation file.
function observation(): PlatformObservationRecord {
  return {
    schemaVersion: 1, kind: 'platform-observation',
    latestAttempt: { attemptedAt: '2026-10-12T01:00:00.123456789Z', status: 'success', errorCode: 'NONE' },
    lastSuccess: {
      capturedAt: '2026-10-12T01:00:00.123456789Z', collectorVersion: '1', mainCommit: 'a'.repeat(40),
      jenkins: { sourceCommit: 'a'.repeat(40), statusId: 123, state: 'success', createdAt: '2026-10-12T00:58:00Z', buildNumber: 7, issuer: 'DevDooly' },
      argo: { revision: 'b'.repeat(40), sync: 'Synced', health: 'Healthy' },
      workloads: [
        { component: 'api', desired: 1, ready: 1, image: `ghcr.io/devdooly/devdooly-platform-lab-api@sha256:${'d'.repeat(64)}` },
        { component: 'web', desired: 1, ready: 1, image: `ghcr.io/devdooly/devdooly-platform-lab-web@sha256:${'e'.repeat(64)}` },
        { component: 'database', desired: 1, ready: 1 },
      ],
      deploymentSourceCommit: 'c'.repeat(40),
    },
  };
}

test('accepts separate main, Jenkins, GitOps and deployed source evidence without collapsing rollback SHAs', () => {
  const record = observation();
  assert.equal(validatePlatformObservation(record), true);
  for (const issuer of ['DevDooly', 'devdooly-platform-lab-ops[bot]'] as const) {
    const candidate = structuredClone(record);
    candidate.lastSuccess!.jenkins!.issuer = issuer;
    assert.equal(validatePlatformObservation(candidate), true);
    assert.equal(candidate.lastSuccess!.capturedAt, record.lastSuccess!.capturedAt);
  }
  assert.notEqual(record.lastSuccess!.mainCommit, record.lastSuccess!.argo.revision);
  assert.notEqual(record.lastSuccess!.argo.revision, record.lastSuccess!.deploymentSourceCommit);
  assert.equal(validatePlatformObservation({ ...record, lastSuccess: { ...record.lastSuccess!, jenkins: null } }), true);
});
test('collector failure retains last success and can coexist with an old snapshot', () => {
  const record = observation();
  record.latestAttempt = { attemptedAt: '2026-10-12T04:00:00Z', status: 'failure', errorCode: 'ARGO_UNAVAILABLE' };
  assert.equal(validatePlatformObservation(record), true);
  assert.deepEqual(platformObservationView(record, Date.parse('2026-10-12T04:01:00Z')), { collectorFailed: true, hasSuccess: true, freshness: 'stale' });
  assert.equal(record.lastSuccess!.capturedAt, '2026-10-12T01:00:00.123456789Z');
});
test('first collection failure is valid without invented prior success', () => {
  const record: PlatformObservationRecord = { schemaVersion: 1, kind: 'platform-observation', latestAttempt: { attemptedAt: '2026-10-12T01:00:00Z', status: 'failure', errorCode: 'TIMEOUT' }, lastSuccess: null };
  assert.equal(validatePlatformObservation(record), true);
  assert.equal(platformObservationView(record, Date.parse('2026-10-12T01:01:00Z')).hasSuccess, false);
  assert.equal(platformObservationView(record, Date.parse('2026-10-12T00:59:59Z')).freshness, 'clock-check');
  assert.equal(validatePlatformObservation({ ...record, latestAttempt: { ...record.latestAttempt, status: 'success', errorCode: 'NONE' } }), false);
});
test('rejects private or unknown fields at every nested object boundary', () => {
  const record = observation();
  const secret = 'test-private-marker';
  const candidates = [
    { ...record, token: secret },
    { ...record, latestAttempt: { ...record.latestAttempt, error: secret } },
    { ...record, lastSuccess: { ...record.lastSuccess!, managementUrl: secret } },
    { ...record, lastSuccess: { ...record.lastSuccess!, jenkins: { ...record.lastSuccess!.jenkins!, authToken: secret } } },
    { ...record, lastSuccess: { ...record.lastSuccess!, argo: { ...record.lastSuccess!.argo, server: '192.168.1.2' } } },
    { ...record, lastSuccess: { ...record.lastSuccess!, workloads: record.lastSuccess!.workloads.map((item, i) => i === 0 ? { ...item, podName: secret } : item) } },
  ];
  assert.ok(candidates.every(candidate => !validatePlatformObservation(candidate)));
});
test('rejects missing keys, mismatched source/issuer and unchecked numeric values', () => {
  const record = observation();
  for (const key of ['mainCommit', 'jenkins', 'deploymentSourceCommit']) {
    const candidate = structuredClone(record) as unknown as { lastSuccess: Record<string, unknown> };
    delete candidate.lastSuccess[key];
    assert.equal(validatePlatformObservation(candidate), false);
  }
  const missingIssuer = structuredClone(record) as unknown as { lastSuccess: { jenkins: Record<string, unknown> } };
  delete missingIssuer.lastSuccess.jenkins.issuer;
  assert.equal(validatePlatformObservation(missingIssuer), false);
  for (const change of [{ sourceCommit: 'f'.repeat(40) }, { issuer: 'someone-else' },
    { issuer: 'devdooly' }, { issuer: 'devdooly-platform-lab-ops' }, { issuer: 'devdooly-platform-lab-ops[bot] ' },
    { issuer: 'DevDooly-platform-lab-ops[bot]' }, { issuer: null }, { issuer: [] }, { issuer: {} },
    { statusId: Number.MAX_SAFE_INTEGER + 1 }, { buildNumber: 0 }, { state: 'running' }]) {
    assert.equal(validatePlatformObservation({ ...record, lastSuccess: { ...record.lastSuccess!, jenkins: { ...record.lastSuccess!.jenkins!, ...change } } }), false);
  }
});
test('workloads require all three components and exact public immutable image references', () => {
  const record = observation();
  const [api, web, database] = record.lastSuccess!.workloads;
  for (const workloads of [
    [api, api, database], [api, web], [api, web, { ...database, image: 'mariadb:latest' }],
    [{ ...api, image: 'ghcr.io/devdooly/devdooly-platform-lab-api:latest' }, web, database],
    [{ ...api, image: `https://user:token@example.invalid/${'a'.repeat(64)}` }, web, database],
    [api, { ...web, desired: 11 }, database], [api, { ...web, ready: 0.5 }, database],
  ]) assert.equal(validatePlatformObservation({ ...record, lastSuccess: { ...record.lastSuccess!, workloads } }), false);
  assert.equal(validatePlatformObservation({ ...record, lastSuccess: { ...record.lastSuccess!, workloads: [{ ...api, desired: 0, ready: 1 }, web, database] } }), true);
});
test('validates actual calendar dates and ordered nanoseconds rather than normalized timestamps', () => {
  const record = observation();
  for (const attemptedAt of ['2026-02-30T01:00:00Z', '2026-10-12T25:00:00Z', '2026-10-12T01:00:60Z', '2026-10-12T01:00:00+00:00', '0000-01-01T00:00:00Z', '2026-10-12T01:00:00.1234567890Z']) {
    assert.equal(validatePlatformObservation({ ...record, latestAttempt: { ...record.latestAttempt, attemptedAt }, lastSuccess: { ...record.lastSuccess!, capturedAt: attemptedAt } }), false);
  }
  assert.equal(validatePlatformObservation({ ...record, latestAttempt: { attemptedAt: '2026-10-12T01:00:00.123456788Z', status: 'failure', errorCode: 'TIMEOUT' } }), false);
  assert.equal(validatePlatformObservation({ ...record, lastSuccess: { ...record.lastSuccess!, jenkins: { ...record.lastSuccess!.jenkins!, createdAt: '2026-10-12T01:00:00.123456790Z' } } }), false);
  assert.equal(validatePlatformObservation({ ...record, latestAttempt: { ...record.latestAttempt, attemptedAt: '2026-10-12T01:00:00Z' } }), false);
});
test('success and failure have disjoint fixed error codes, not raw errors', () => {
  const record = observation();
  for (const latestAttempt of [
    { ...record.latestAttempt, errorCode: 'TIMEOUT' },
    { ...record.latestAttempt, status: 'failure', errorCode: 'NONE' },
    { ...record.latestAttempt, status: 'failure', errorCode: 'request to private host failed' },
  ]) assert.equal(validatePlatformObservation({ ...record, latestAttempt }), false);
});
test('stale boundary uses last success, with future or invalid browser clock explicitly flagged', () => {
  const record = observation();
  const captured = Date.parse(record.lastSuccess!.capturedAt);
  assert.equal(platformObservationView(record, captured + PLATFORM_STALE_AFTER_MS).freshness, 'within-window');
  assert.equal(platformObservationView(record, captured + PLATFORM_STALE_AFTER_MS + 1).freshness, 'stale');
  assert.equal(platformObservationView(record, captured - 1).freshness, 'clock-check');
  assert.equal(platformObservationView(record, Number.NaN).freshness, 'clock-check');
});
test('loader distinguishes a valid collector failure from browser HTTP/network/format failures and retains prior data', async () => {
  const previous = observation();
  const failed = structuredClone(previous);
  failed.latestAttempt = { attemptedAt: '2026-10-12T01:02:00Z', status: 'failure', errorCode: 'WORKLOADS_UNAVAILABLE' };
  const collector = await loadPlatformObservation({ url: '/record', previousRecord: previous, fetcher: async () => new Response(JSON.stringify(failed)) });
  assert.equal(collector.browserError, null);
  assert.equal(collector.record!.latestAttempt.status, 'failure');
  for (const [fetcher, expected] of [
    [async () => new Response('', { status: 404 }), 'NOT_PUBLISHED'],
    [async () => new Response('private raw error', { status: 502 }), 'HTTP_ERROR'],
    [async () => { throw new Error('private raw error'); }, 'NETWORK_ERROR'],
    [async () => new Response('{bad-json'), 'INVALID_RECORD'],
    [async () => new Response(JSON.stringify({ ...previous, token: 'test-private-marker' })), 'INVALID_RECORD'],
    [async () => new Response(' '.repeat(MAX_PLATFORM_OBSERVATION_BYTES + 1)), 'INVALID_RECORD'],
  ] as const) {
    const result = await loadPlatformObservation({ url: '/record', previousRecord: previous, fetcher });
    assert.equal(result.browserError, expected);
    assert.equal(result.record, previous);
    assert.equal(result.retainedPrevious, true);
    assert.equal(JSON.stringify(result).includes('private raw error'), false);
    assert.equal(JSON.stringify(result).includes('test-private-marker'), false);
  }
});
test('loader discards an invalid previous record, marks abort separately and does not fabricate time', async () => {
  const invalid = { ...observation(), token: 'test-only' } as PlatformObservationRecord;
  const controller = new AbortController(); controller.abort();
  const result = await loadPlatformObservation({ url: '/record', previousRecord: invalid, signal: controller.signal, fetcher: async () => { throw new Error('aborted'); } });
  assert.deepEqual(result, { record: null, browserError: 'ABORTED', retainedPrevious: false });
});
test('real HTTP lookup uses public file only, omits credentials and preserves collector timestamps', async () => {
  const record = observation();
  record.lastSuccess!.jenkins!.issuer = 'devdooly-platform-lab-ops[bot]';
  const server = createServer((request, response) => {
    assert.equal(request.url, '/base/data/platform-observation.json');
    assert.equal(request.headers.authorization, undefined);
    assert.equal(request.headers.cookie, undefined);
    response.setHeader('Content-Type', 'application/json'); response.end(JSON.stringify(record));
  });
  await new Promise<void>(resolve => server.listen(0, '127.0.0.1', resolve));
  try {
    const address = server.address(); assert.ok(address && typeof address !== 'string');
    const result = await loadPlatformObservation({ url: `http://127.0.0.1:${address.port}/base/data/platform-observation.json` });
    assert.equal(result.browserError, null);
    assert.deepEqual(result.record, record);
  } finally { await new Promise<void>((resolve, reject) => server.close(error => error ? reject(error) : resolve())); }
});
test('JSON Schema itself closes all object boundaries and matches fixed workload and error identities', async () => {
  const schema = JSON.parse(await readFile(new URL('../schemas/platform-observation.schema.json', import.meta.url), 'utf8'));
  const visit = (value: unknown): void => {
    if (!value || typeof value !== 'object') return;
    const node = value as Record<string, unknown>;
    if (node.type === 'object') assert.equal(node.additionalProperties, false);
    Object.values(node).forEach(item => Array.isArray(item) ? item.forEach(visit) : visit(item));
  };
  visit(schema);
  assert.equal(schema.$defs.success.properties.workloads.minItems, 3);
  assert.deepEqual(schema.$defs.database.required, ['component', 'desired', 'ready']);
  assert.equal(schema.properties.latestAttempt.properties.errorCode.enum.includes('NONE'), true);
  assert.deepEqual(schema.$defs.jenkins.properties.issuer, { enum: ['DevDooly', 'devdooly-platform-lab-ops[bot]'] });
});
