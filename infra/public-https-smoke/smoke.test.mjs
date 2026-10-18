import assert from 'node:assert/strict';
import { EventEmitter } from 'node:events';
import { readFileSync } from 'node:fs';
import { mock, test } from 'node:test';

const PRIVATE_MARKER = 'SYNTHETIC_PRIVATE_TIME_MARKER';
const BASE = 'https://api.example.test/platform-lab/api';
const API_SHA = 'b'.repeat(40);
const VALIDATOR_SHA = 'a'.repeat(40);
const ORIGIN = 'https://devdooly.github.io';
const at = '2020-01-01T00:00:00Z';
const paths = ['/platform/summary', '/platform/releases', '/demo/runs',
  '/demo/runs/synthetic-v1-seed-42', '/jobs/observation', '/kafka/observation'];
const source = JSON.parse(readFileSync(new URL('../../apps/lab-web/src/data/snapshot.json', import.meta.url), 'utf8'));
let world;

function fixtures() {
  const sample = structuredClone(source);
  const run = { ...sample.runs[0], startedAt: at, completedAt: at };
  const detail = { ...sample.detail, ...run, observedAt: '2020-01-01T00:00:03.123456789Z' };
  const summary = { ...sample.summary, service: 'devdooly-platform-lab-api', status: 'UP',
    environment: 'mini-pc', sourceCommit: API_SHA, observedAt: at };
  const releases = { items: [{ service: 'api', version: '0.1.0', sourceCommit: API_SHA,
    imageDigest: null, deploymentStatus: 'RUNTIME_ONLY', startedAt: at }], observedAt: '2020-01-01T00:00:01Z' };
  const runs = { items: [run], observedAt: '2020-01-01T00:00:02Z' };
  const jobs = { schemaVersion: 1, kind: 'job-observation', capturedAt: at, environment: 'MINI_PC',
    sourceCommit: API_SHA, synthetic: true, scope: 'DEPLOYED_RUNTIME', publicExecutionEnabled: false,
    runtime: { status: 'NOT_STARTED', stage: 'IDLE', failureCode: null, startedAt: null, heartbeatAt: null,
      stoppedAt: null, sourceCommit: 'unknown', stale: false }, slot: { occupiedRunId: null }, jobs: [] };
  const kafka = { schemaVersion: 1, kind: 'kafka-observation', synthetic: true, environment: 'MINI_PC',
    scope: 'DEPLOYED_KAFKA', publicExecutionEnabled: false, sourceCommit: API_SHA,
    captureStartedAt: at, capturedAt: '2020-01-01T00:00:02Z', consistency: 'BOUNDED_SEQUENTIAL_READ',
    targetFingerprint: 'c'.repeat(64), groupState: 'STABLE', partition: 0, commitState: 'OBSERVED',
    logStartOffset: 0, readCommittedEndOffset: 8, committedOffset: 8, lag: 0 };
  return new Map(paths.map((path, index) => ['/platform-lab/api' + path,
    [summary, releases, runs, detail, jobs, kafka][index]]));
}
function fresh(overrides = {}) {
  world = { dns: 0, calls: [], sleeps: 0, addresses: [{ address: '8.8.8.8', family: 4 },
    { address: '1.1.1.1', family: 4 }], payloads: fixtures(), ...overrides };
  return world;
}
function environment(overrides = {}) {
  return { GITHUB_SHA: VALIDATOR_SHA, LAB_PUBLIC_API_URL: BASE, SMOKE_CONFIRM: 'true',
    SMOKE_ROUTE_OWNERSHIP: 'true', SMOKE_VARIABLE_MATCH: 'true', ...overrides };
}
const fakeLookup = async (hostname, options) => {
  world.dns++;
  assert.equal(hostname, 'api.example.test');
  assert.deepEqual(options, { family: 4, all: true, verbatim: true });
  if (world.lookupError) throw new Error(PRIVATE_MARKER + ' ' + BASE);
  return world.addresses;
};
const fakeSleep = async (milliseconds, value, options) => {
  world.sleeps++;
  assert.equal(milliseconds, 1100);
  assert.equal(value, undefined);
  if (!world.stallSleep) return;
  await new Promise((_resolve, reject) => {
    if (options.signal.aborted) { reject(new Error(PRIVATE_MARKER)); return; }
    options.signal.addEventListener('abort', () => reject(new Error(PRIVATE_MARKER)), { once: true });
  });
};
function fakeRequest(options, callback) {
  const req = new EventEmitter();
  req.destroyed = false;
  req.destroy = () => { req.destroyed = true; return req; };
  const call = { options, req, pinned: null };
  world.calls.push(call);
  options.lookup('api.example.test', {}, (error, address, family) => {
    assert.equal(error, null); call.pinned = { address, family };
  });
  req.end = () => {
    if (world.stallRequest) return req;
    queueMicrotask(() => {
      if (req.destroyed) return;
      let status = 200;
      let payload = world.payloads.get(options.path);
      if (options.path.endsWith('/__smoke-denied')) { status = 404; payload = { kind: 'public-gateway-error', code: 'NOT_FOUND' }; }
      if (options.headers.Origin !== ORIGIN) { status = 403; payload = { kind: 'public-gateway-error', code: 'ORIGIN_REJECTED' }; }
      if (options.method === 'POST') { status = 405; payload = { kind: 'public-gateway-error', code: 'GET_REQUIRED' }; }
      if (world.redirect) status = 302;
      const headers = { 'content-type': 'application/json', 'cache-control': 'no-store', vary: 'Origin' };
      if (options.headers.Origin === ORIGIN) headers['access-control-allow-origin'] = ORIGIN;
      if (options.method === 'POST') headers.allow = 'GET';
      if (world.redirect) headers.location = 'https://other.example.invalid/' + PRIVATE_MARKER;
      if (world.headerChange) world.headerChange(headers);
      const response = new EventEmitter();
      response.statusCode = status; response.headers = headers;
      response.rawHeaders = Object.entries(headers).flat();
      response.destroyed = false;
      response.destroy = () => { response.destroyed = true; return response; };
      callback(response);
      queueMicrotask(() => {
        if (response.destroyed || req.destroyed) return;
        const raw = world.oversize ? Buffer.alloc(256 * 1024 + 1, 65) : Buffer.from(JSON.stringify(payload));
        response.emit('data', raw);
        if (!response.destroyed && !req.destroyed) response.emit('end');
      });
    });
    return req;
  };
  return req;
}

// Register before importing the production file. Real DNS/HTTPS functions are never called.
mock.module('node:dns/promises', { namedExports: { lookup: fakeLookup } });
mock.module('node:https', { namedExports: { request: fakeRequest } });
mock.module('node:timers/promises', { namedExports: { setTimeout: fakeSleep } });
const { runSmoke, isPublicIpv4 } = await import('./smoke.ts');
const flush = () => new Promise(resolve => setImmediate(resolve));
function privacy(result) {
  const serialized = JSON.stringify(result);
  for (const privateText of [PRIVATE_MARKER, BASE, 'api.example.test', '8.8.8.8', '1.1.1.1', 'other.example.invalid']) {
    assert.equal(serialized.includes(privateText), false);
  }
  assert.ok(serialized.length < 5000);
}

test('single public IPv4 is pinned with original TLS hostname and only nine owned requests', { concurrency: false }, async () => {
  fresh();
  const result = await runSmoke(environment());
  assert.equal(result.status, 'PASS'); assert.equal(result.errorCode, 'NONE');
  assert.equal(world.dns, 1); assert.equal(world.calls.length, 9);
  assert.equal(result.standardTlsVerified, true);
  assert.deepEqual(world.calls.slice(0, 6).map(call => call.options.path), paths.map(path => '/platform-lab/api' + path));
  for (const { options, pinned } of world.calls) {
    assert.deepEqual(pinned, { address: '8.8.8.8', family: 4 });
    assert.equal(options.hostname, 'api.example.test'); assert.equal(options.servername, 'api.example.test');
    assert.equal(options.rejectUnauthorized, true); assert.equal(options.family, 4);
    assert.equal(options.autoSelectFamily, false); assert.equal(options.agent, false);
    assert.equal(options.headers.Authorization, undefined); assert.equal(options.headers.Cookie, undefined);
    assert.equal(options.headers['Content-Type'], undefined);
    assert.equal(options.body, undefined); assert.equal(options.headers.Host, undefined);
  }
  assert.equal(world.calls.at(-1).options.method, 'POST');
  assert.deepEqual(['SUMMARY', 'RELEASES', 'RUN_LIST', 'RUN_DETAIL_EXAMPLE'].map(id => result.checks[id].observedAt),
    [at, '2020-01-01T00:00:01Z', '2020-01-01T00:00:02Z', '2020-01-01T00:00:03.123456789Z']);
  privacy(result);
});

test('missing config, mirror mismatch and ownership/manual acknowledgement stop before all IO including POST', { concurrency: false }, async () => {
  for (const overrides of [{ LAB_PUBLIC_API_URL: '' }, { SMOKE_VARIABLE_MATCH: 'false' },
    { SMOKE_ROUTE_OWNERSHIP: 'false' }, { SMOKE_CONFIRM: 'false' }, { GITHUB_SHA: 'not-a-source' }]) {
    fresh(); const result = await runSmoke(environment(overrides));
    assert.equal(result.errorCode, 'CONFIGURATION_NOT_VERIFIED');
    assert.equal(world.dns, 0); assert.equal(world.calls.length, 0); privacy(result);
  }
});

test('private, loopback, link-local, reserved and unsupported addresses never reach HTTPS', { concurrency: false }, async () => {
  for (const address of ['0.0.0.0', '10.0.0.1', '100.64.0.1', '127.0.0.1', '169.254.169.254',
    '172.16.0.1', '192.0.0.9', '192.0.2.1', '192.88.99.1', '192.168.0.1', '198.18.0.1',
    '198.51.100.1', '203.0.113.1', '224.0.0.1', '255.255.255.255', '::1', '8.8.8.08']) {
    assert.equal(isPublicIpv4(address), false);
  }
  for (const [addresses, expected] of [
    [[{ address: '8.8.8.8', family: 4 }, { address: '10.0.0.1', family: 4 }], 'DNS_ADDRESS_REJECTED'],
    [[], 'DNS_NO_SUPPORTED_PUBLIC_IPV4'],
    [[{ address: '2001:4860:4860::8888', family: 6 }], 'DNS_ADDRESS_REJECTED'],
  ]) {
    fresh({ addresses }); const result = await runSmoke(environment());
    assert.equal(result.errorCode, expected); assert.equal(world.calls.length, 0); privacy(result);
  }
});

test('redirect does not contact another location or continue to a later route', { concurrency: false }, async () => {
  fresh({ redirect: true }); const result = await runSmoke(environment());
  assert.equal(result.errorCode, 'HTTP_STATUS_UNVERIFIED');
  assert.equal(world.calls.length, 1); assert.equal(result.checks.SUMMARY.status, 302); privacy(result);
});

test('stream body cap stops immediately without serializing the body or sending a second request', { concurrency: false }, async () => {
  fresh({ oversize: true }); const result = await runSmoke(environment());
  assert.equal(result.errorCode, 'RESPONSE_TOO_LARGE');
  assert.equal(world.calls.length, 1); assert.equal(world.calls[0].req.destroyed, true); privacy(result);
});

test('request hard deadline destroys the stalled request and prevents later GET or POST', { concurrency: false }, async context => {
  fresh({ stallRequest: true }); context.mock.timers.enable({ apis: ['setTimeout'] });
  const pending = runSmoke(environment()); await flush();
  assert.equal(world.calls.length, 1); context.mock.timers.tick(15_001);
  const result = await pending;
  assert.equal(result.errorCode, 'REQUEST_TIMEOUT'); assert.equal(world.calls.length, 1);
  assert.equal(world.calls[0].req.destroyed, true); privacy(result);
});

test('whole deadline interrupts pacing after the first request with no second request', { concurrency: false }, async context => {
  fresh({ stallSleep: true }); context.mock.timers.enable({ apis: ['setTimeout'] });
  const pending = runSmoke(environment()); await flush();
  assert.equal(world.calls.length, 1); assert.equal(world.sleeps, 1);
  context.mock.timers.tick(150_001); const result = await pending;
  assert.equal(result.errorCode, 'WHOLE_TIMEOUT'); assert.equal(world.calls.length, 1); privacy(result);
});

test('all four exported Lab observation times reject loose Date.parse input, long fractions and normalized dates', { concurrency: false }, async () => {
  const comment = 'Wed, 01 Jan 2020 00:00:00 GMT (' + PRIVATE_MARKER + ')';
  const longFraction = '2020-01-01T00:00:00.' + '1'.repeat(2048) + 'Z';
  const normalizedDate = '2020-02-30T00:00:00Z';
  for (const [path, badTime] of [[paths[0], longFraction], [paths[1], comment], [paths[2], comment], [paths[3], normalizedDate]]) {
    assert.ok(Number.isFinite(Date.parse(badTime)), 'the loose parser must actually accept this regression input');
    fresh(); world.payloads.get('/platform-lab/api' + path).observedAt = badTime;
    const result = await runSmoke(environment());
    assert.equal(result.errorCode, 'INVALID_DTO'); assert.equal(world.calls.length, 4);
    assert.equal(Object.values(result.checks).every(check => check.observedAt === null), true);
    privacy(result);
  }
});

test('DNS exception details remain finite and private with no HTTPS request', { concurrency: false }, async () => {
  fresh({ lookupError: true }); const result = await runSmoke(environment());
  assert.equal(result.errorCode, 'DNS_LOOKUP_FAILED'); assert.equal(world.calls.length, 0); privacy(result);
});

test('missing CORS/cache and forbidden response metadata stop before a later request', { concurrency: false }, async () => {
  for (const change of [headers => { delete headers['cache-control']; },
    headers => { delete headers['access-control-allow-origin']; },
    headers => { headers['set-cookie'] = PRIVATE_MARKER; },
    headers => { headers.location = BASE + '/' + PRIVATE_MARKER; }]) {
    fresh({ headerChange: change }); const result = await runSmoke(environment());
    assert.equal(result.errorCode, 'HEADERS_UNVERIFIED'); assert.equal(world.calls.length, 1); privacy(result);
  }
});
