import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { EventEmitter } from 'node:events';
import { readFileSync } from 'node:fs';
import { mock, test } from 'node:test';

const PRIVATE = 'SYNTHETIC_PRIVATE_GET_CANARY';
const BASE = 'https://api.example.test/platform-lab/api';
const ORIGIN = 'https://devdooly.github.io';
const SOURCE = 'a'.repeat(40);
const API_SOURCE = 'b'.repeat(40);
const NOW = Date.parse('2030-01-01T00:00:00.123Z');
const AT = '2020-01-01T00:00:00Z';
const PATHS = ['/platform/summary', '/platform/releases', '/demo/runs',
  '/demo/runs/synthetic-v1-seed-42', '/jobs/observation', '/kafka/observation'];
const IDS = ['SUMMARY', 'RELEASES', 'RUN_LIST', 'RUN_DETAIL_EXAMPLE', 'JOBS', 'KAFKA'];
const fixture = JSON.parse(readFileSync(new URL('../../apps/lab-web/src/data/snapshot.json', import.meta.url), 'utf8'));
let world;

function payloads() {
  const sample = structuredClone(fixture);
  const run = { ...sample.runs[0], startedAt: AT, completedAt: AT };
  const detail = { ...sample.detail, ...run, observedAt: AT };
  const summary = { ...sample.summary, service: 'devdooly-platform-lab-api', status: 'UP',
    environment: 'mini-pc', sourceCommit: API_SOURCE, observedAt: AT };
  const releases = { items: [{ service: 'api', version: '0.1.0', sourceCommit: API_SOURCE,
    imageDigest: null, deploymentStatus: 'RUNTIME_ONLY', startedAt: AT }], observedAt: AT };
  const runs = { items: [run], observedAt: AT };
  const jobs = { schemaVersion: 1, kind: 'job-observation', capturedAt: AT, environment: 'MINI_PC',
    sourceCommit: 'c'.repeat(40), synthetic: true, scope: 'DEPLOYED_RUNTIME', publicExecutionEnabled: false,
    runtime: { status: 'NOT_STARTED', stage: 'IDLE', failureCode: null, startedAt: null,
      heartbeatAt: null, stoppedAt: null, sourceCommit: 'unknown', stale: false },
    slot: { occupiedRunId: null }, jobs: [] };
  const kafka = { schemaVersion: 1, kind: 'kafka-observation', synthetic: true, environment: 'MINI_PC',
    scope: 'DEPLOYED_KAFKA', publicExecutionEnabled: false, sourceCommit: 'd'.repeat(40),
    captureStartedAt: AT, capturedAt: '2020-01-01T00:00:02Z', consistency: 'BOUNDED_SEQUENTIAL_READ',
    targetFingerprint: 'e'.repeat(64), groupState: 'STABLE', partition: 0, commitState: 'OBSERVED',
    logStartOffset: 0, readCommittedEndOffset: 8, committedOffset: 8, lag: 0 };
  return new Map(PATHS.map((path, index) => ['/platform-lab/api' + path,
    [summary, releases, runs, detail, jobs, kafka][index]]));
}
function fresh(overrides = {}) {
  world = { dns: 0, calls: [], sleeps: 0, addresses: [{ address: '8.8.8.8', family: 4 },
    { address: '1.1.1.1', family: 4 }], payloads: payloads(), ...overrides };
}
function environment(overrides = {}) {
  return { GITHUB_REPOSITORY: 'DevDooly/devdooly-platform-lab', GITHUB_EVENT_NAME: 'workflow_dispatch',
    GITHUB_REF: 'refs/heads/main', GITHUB_RUN_ATTEMPT: '1', GITHUB_SHA: SOURCE,
    LAB_PUBLIC_API_URL: BASE, PUBLIC_GET_CONFIRM: 'true', PUBLIC_GET_TARGET_OWNERSHIP: 'true',
    PUBLIC_GET_VARIABLE_MATCH: 'true', ...overrides };
}
function clock(context, timers = false) {
  context.mock.timers.enable({ apis: timers ? ['Date', 'setTimeout'] : ['Date'], now: NOW });
}
const flush = () => new Promise(resolve => setImmediate(resolve));
const fakeLookup = async (hostname, options) => {
  world.dns++;
  assert.equal(hostname, 'api.example.test');
  assert.deepEqual(options, { family: 4, all: true, verbatim: true });
  if (world.lookupError) throw new Error(PRIVATE + BASE);
  if (world.stallDns) return new Promise(() => {});
  world.onDnsReturn?.();
  return world.addresses;
};
const fakeSleep = async (milliseconds, value, options) => {
  world.sleeps++;
  assert.equal(milliseconds, 1100); assert.equal(value, undefined);
  if (!world.stallSleep) return;
  await new Promise((_resolve, reject) => {
    if (options.signal.aborted) { reject(new Error(PRIVATE)); return; }
    options.signal.addEventListener('abort', () => reject(new Error(PRIVATE)), { once: true });
  });
};
function fakeRequest(options, callback) {
  // The new probe cannot quietly grow a POST, denial path, custom origin or body.
  if (!world.allowFullNine) {
    assert.equal(options.method, 'GET');
    assert.ok(PATHS.some(path => options.path === '/platform-lab/api' + path));
    assert.equal(options.headers.Origin, ORIGIN);
  }
  const request = new EventEmitter(); request.destroyed = false;
  request.destroy = () => { request.destroyed = true; return request; };
  const call = { options, request, pinned: null };
  world.calls.push(call);
  options.lookup('api.example.test', {}, (error, address, family) => {
    assert.equal(error, null); call.pinned = { address, family };
  });
  request.end = (...args) => {
    assert.equal(args.length, 0);
    if (world.stallRequest) return request;
    queueMicrotask(() => {
      if (request.destroyed) return;
      if (world.networkError) { request.emit('error', new Error(PRIVATE + BASE)); return; }
      let status = 200; let payload = world.payloads.get(options.path);
      if (options.path.endsWith('/__smoke-denied')) { status = 404; payload = { kind: 'public-gateway-error', code: 'NOT_FOUND' }; }
      if (options.headers.Origin !== ORIGIN) { status = 403; payload = { kind: 'public-gateway-error', code: 'ORIGIN_REJECTED' }; }
      if (options.method === 'POST') { status = 405; payload = { kind: 'public-gateway-error', code: 'GET_REQUIRED' }; }
      if (world.failureAt === world.calls.length) status = 503;
      if (world.redirect) status = 302;
      const headers = { 'content-type': 'application/json', 'cache-control': 'no-store', vary: 'Origin' };
      if (options.headers.Origin === ORIGIN) headers['access-control-allow-origin'] = ORIGIN;
      if (options.method === 'POST') headers.allow = 'GET';
      if (world.redirect) headers.location = 'https://other.example.invalid/' + PRIVATE;
      world.headerChange?.(headers);
      const response = new EventEmitter(); response.destroyed = false;
      response.statusCode = status; response.headers = headers; response.rawHeaders = Object.entries(headers).flat();
      response.destroy = () => { response.destroyed = true; return response; };
      callback(response);
      queueMicrotask(() => {
        if (request.destroyed || response.destroyed) return;
        const raw = world.oversize ? Buffer.alloc(256 * 1024 + 1, 65)
          : Buffer.from(world.rawTexts?.get(options.path) ?? world.rawText ?? JSON.stringify(payload));
        response.emit('data', raw);
        if (!request.destroyed && !response.destroyed) {
          world.onBeforeEnd?.(world.calls.length);
          response.emit('end');
        }
      });
    });
    return request;
  };
  return request;
}

// Mock native entrypoints before the new probe and its CLI-guarded shared module load.
mock.module('node:dns/promises', { namedExports: { lookup: fakeLookup } });
mock.module('node:https', { namedExports: { request: fakeRequest } });
mock.module('node:timers/promises', { namedExports: { setTimeout: fakeSleep } });
const { runPublicGetProbe } = await import('./probe.ts');
const { runSmoke } = await import('../public-https-smoke/smoke.ts');

function privacy(result) {
  const text = JSON.stringify(result);
  for (const value of [PRIVATE, BASE, 'api.example.test', '8.8.8.8', '1.1.1.1', 'other.example.invalid']) {
    assert.equal(text.includes(value), false);
  }
  assert.ok(Buffer.byteLength(text, 'utf8') <= 4096);
  assert.equal(result.deniedRequestsTested, false);
  assert.equal(result.operatingConfigurationChanged, false);
}
function failed(result, code) {
  assert.equal(result.status, 'FAILED'); assert.equal(result.errorCode, code); privacy(result);
}

test('기존 full9 원문은 마지막 helper export 선언을 제외하면 bytes가 같다', () => {
  const raw = readFileSync(new URL('../public-https-smoke/smoke.ts', import.meta.url));
  const suffix = Buffer.from('\n// Read-only helpers shared with the separately guarded GET-only probe.\n'
    + 'export { ROUTES as PUBLIC_GET_ROUTES, selectPublicIpv4, oneRequest, validateLab, SmokeError };\n');
  assert.deepEqual(raw.subarray(-suffix.length), suffix);
  assert.equal(createHash('sha256').update(raw.subarray(0, -suffix.length)).digest('hex'),
    '7c8a6cf84fe4fe96ac2f1343a838adc33107e87437306203679ca161d95279d9');
});

test('성공은 고정 GET6·DNS1이며 다른 실제 source40과 과거 DTO시각을 보존한다', { concurrency: false }, async context => {
  clock(context); fresh();
  const result = await runPublicGetProbe(environment());
  assert.equal(result.status, 'PASS'); assert.equal(result.errorCode, 'NONE');
  assert.equal(result.kind, 'public-https-get-snapshot'); assert.equal(result.scope, 'PUBLIC_HTTPS_GET_CONTRACTS_ONLY');
  assert.equal(world.dns, 1); assert.equal(world.calls.length, 6); assert.equal(world.sleeps, 5);
  assert.deepEqual(world.calls.map(call => call.options.path), PATHS.map(path => '/platform-lab/api' + path));
  assert.deepEqual(Object.keys(result.checks), IDS);
  assert.equal(result.validatorSourceCommit, SOURCE);
  assert.deepEqual(IDS.map(id => result.checks[id].sourceCommit), [API_SOURCE, API_SOURCE, API_SOURCE, API_SOURCE, 'c'.repeat(40), 'd'.repeat(40)]);
  assert.equal(result.checks.JOBS.observedAt, AT);
  assert.equal(result.checks.KAFKA.observedAt, '2020-01-01T00:00:02Z');
  assert.equal(result.captureStartedAt, new Date(NOW).toISOString());
  assert.equal(result.capturedAt, new Date(NOW).toISOString());
  for (const { options, pinned } of world.calls) {
    assert.deepEqual(pinned, { address: '8.8.8.8', family: 4 });
    assert.equal(options.hostname, 'api.example.test'); assert.equal(options.servername, 'api.example.test');
    assert.equal(options.port, 443); assert.equal(options.family, 4); assert.equal(options.rejectUnauthorized, true);
    assert.equal(options.autoSelectFamily, false); assert.equal(options.agent, false);
    for (const key of ['Authorization', 'Cookie', 'Content-Type', 'Host']) assert.equal(options.headers[key], undefined);
    for (const key of ['body', 'ca', 'cert', 'key', 'pfx', 'checkServerIdentity']) assert.equal(options[key], undefined);
  }
  privacy(result);
});

test('소유저장소·main·manual·첫attempt·SHA·ACK·mirror·URL guard는 각각 DNS0이다', { concurrency: false }, async context => {
  clock(context);
  for (const change of [{ GITHUB_REPOSITORY: 'other/repo' }, { GITHUB_EVENT_NAME: 'push' },
    { GITHUB_REF: 'refs/heads/feature' }, { GITHUB_RUN_ATTEMPT: '2' }, { GITHUB_SHA: 'unknown' },
    { PUBLIC_GET_CONFIRM: 'false' }, { PUBLIC_GET_TARGET_OWNERSHIP: 'false' },
    { PUBLIC_GET_VARIABLE_MATCH: 'false' }, { LAB_PUBLIC_API_URL: '' },
    { LAB_PUBLIC_API_URL: 'http://api.example.test/api' }, { LAB_PUBLIC_API_URL: 'https://127.0.0.1/api' },
    { LAB_PUBLIC_API_URL: 'https://secret-token@api.example.test/api' },
    { LAB_PUBLIC_API_URL: BASE + '?redirect=' + PRIVATE }]) {
    fresh(); failed(await runPublicGetProbe(environment(change)), 'CONFIGURATION_NOT_VERIFIED');
    assert.equal(world.dns, 0); assert.equal(world.calls.length, 0);
  }
});

test('CA·TLS우회·proxy·debug·keylog 환경은 빈 값도 DNS 전에 거부한다', { concurrency: false }, async context => {
  clock(context);
  for (const name of ['NODE_OPTIONS', 'NODE_EXTRA_CA_CERTS', 'NODE_TLS_REJECT_UNAUTHORIZED', 'NODE_USE_SYSTEM_CA',
    'NODE_DEBUG', 'NODE_DEBUG_NATIVE', 'SSL_CERT_FILE', 'SSL_CERT_DIR', 'SSLKEYLOGFILE',
    'HTTP_PROXY', 'HTTPS_PROXY', 'ALL_PROXY', 'NO_PROXY', 'http_proxy', 'https_proxy', 'all_proxy', 'no_proxy', 'NODE_USE_ENV_PROXY']) {
    for (const value of ['', PRIVATE]) {
      fresh(); failed(await runPublicGetProbe(environment({ [name]: value })), 'ENVIRONMENT_NOT_VERIFIED');
      assert.equal(world.dns, 0); assert.equal(world.calls.length, 0);
    }
  }
});

test('혼합 private·IPv6·빈 DNS·17개 주소와 DNS오류는 HTTPS0이다', { concurrency: false }, async context => {
  clock(context);
  for (const [addresses, code] of [
    [[{ address: '8.8.8.8', family: 4 }, { address: '192.168.0.1', family: 4 }], 'DNS_ADDRESS_REJECTED'],
    [[{ address: '::1', family: 6 }], 'DNS_ADDRESS_REJECTED'], [[], 'DNS_NO_SUPPORTED_PUBLIC_IPV4'],
    [Array.from({ length: 17 }, () => ({ address: '8.8.8.8', family: 4 })), 'DNS_NO_SUPPORTED_PUBLIC_IPV4'],
  ]) {
    fresh({ addresses }); failed(await runPublicGetProbe(environment()), code);
    assert.equal(world.dns, 1); assert.equal(world.calls.length, 0);
  }
  fresh({ lookupError: true }); failed(await runPublicGetProbe(environment()), 'DNS_LOOKUP_FAILED');
  assert.equal(world.calls.length, 0);
});

test('redirect·nativeTLS오류·각 HTTP실패 위치에서 재시도와 후속GET을 보내지 않는다', { concurrency: false }, async context => {
  clock(context);
  for (const [change, code] of [[{ redirect: true }, 'HTTP_STATUS_UNVERIFIED'], [{ networkError: true }, 'TLS_OR_NETWORK_UNVERIFIED']]) {
    fresh(change); failed(await runPublicGetProbe(environment()), code); assert.equal(world.calls.length, 1);
  }
  for (let failureAt = 1; failureAt <= 6; failureAt++) {
    fresh({ failureAt }); failed(await runPublicGetProbe(environment()), 'HTTP_STATUS_UNVERIFIED');
    assert.equal(world.calls.length, failureAt); assert.equal(world.dns, 1);
  }
});

test('CORS·cache·금지header·본문상한 실패는 첫 요청에서 멈추고 원문을 내보내지 않는다', { concurrency: false }, async context => {
  clock(context);
  for (const headerChange of [headers => { delete headers['cache-control']; },
    headers => { delete headers['access-control-allow-origin']; },
    headers => { headers['set-cookie'] = PRIVATE; }, headers => { headers.location = BASE + PRIVATE; },
    headers => { headers['content-type'] = 'text/plain'; }]) {
    fresh({ headerChange }); failed(await runPublicGetProbe(environment()), 'HEADERS_UNVERIFIED');
    assert.equal(world.calls.length, 1);
  }
  fresh({ oversize: true }); failed(await runPublicGetProbe(environment()), 'RESPONSE_TOO_LARGE');
  assert.equal(world.calls.length, 1); assert.equal(world.calls[0].request.destroyed, true);
});

test('Lab golden과 API release source 불일치는 네 DTO 비교 뒤 jobs 전에 거부한다', { concurrency: false }, async context => {
  clock(context);
  for (const alter of [map => { map.get('/platform-lab/api' + PATHS[3]).successCount = 6; },
    map => { map.get('/platform-lab/api' + PATHS[1]).items[0].sourceCommit = 'c'.repeat(40); },
    map => { map.get('/platform-lab/api' + PATHS[0]).sourceCommit = 'unknown'; }]) {
    fresh(); alter(world.payloads);
    const result = await runPublicGetProbe(environment()); failed(result, 'INVALID_DTO');
    assert.equal(world.calls.length, 4);
    assert.equal(IDS.slice(0, 4).every(id => result.checks[id].passed === false
      && result.checks[id].sourceCommit === null && result.checks[id].observedAt === null), true);
  }
});

test('jobs unknown source·잘못된scope는 Kafka 전에 멈춘다', { concurrency: false }, async context => {
  clock(context);
  for (const change of [{ sourceCommit: 'unknown' }, { scope: 'LOCAL_VALIDATION' }]) {
    fresh(); Object.assign(world.payloads.get('/platform-lab/api' + PATHS[4]), change);
    const result = await runPublicGetProbe(environment()); failed(result, 'INVALID_DTO');
    assert.equal(world.calls.length, 5); assert.equal(result.checks.JOBS.passed, false);
  }
});

test('Kafka 엄격계약은 source·offset·소수·중복키를 거부하고 NO_COMMIT null은 보존한다', { concurrency: false }, async context => {
  clock(context);
  for (const change of [{ sourceCommit: 'unknown' }, { committedOffset: 9 }, { lag: 1 }]) {
    fresh(); Object.assign(world.payloads.get('/platform-lab/api' + PATHS[5]), change);
    failed(await runPublicGetProbe(environment()), 'INVALID_DTO'); assert.equal(world.calls.length, 6);
  }
  for (const alterText of [text => text.replace('"partition":0', '"partition":0.1'),
    text => text.replace('"partition":0', '"partition":0,"partition":0')]) {
    fresh(); const path = '/platform-lab/api' + PATHS[5];
    world.rawTexts = new Map([[path, alterText(JSON.stringify(world.payloads.get(path)))]]);
    failed(await runPublicGetProbe(environment()), 'INVALID_DTO'); assert.equal(world.calls.length, 6);
  }
  fresh(); Object.assign(world.payloads.get('/platform-lab/api' + PATHS[5]),
    { groupState: 'EMPTY', commitState: 'NO_COMMIT', committedOffset: null, lag: null });
  const result = await runPublicGetProbe(environment()); assert.equal(result.status, 'PASS'); privacy(result);
});

test('관측시각 5초 상한은 원시각을 바꾸지 않고 나노초 초과를 거부한다', { concurrency: false }, async context => {
  clock(context);
  const exact = '2030-01-01T00:00:05.123000000Z';
  const over = '2030-01-01T00:00:05.123000001Z';
  for (const index of [0, 1, 2, 3, 4, 5]) {
    fresh(); const payload = world.payloads.get('/platform-lab/api' + PATHS[index]);
    if (index === 5) payload.captureStartedAt = '2030-01-01T00:00:03.123Z';
    payload[index < 4 ? 'observedAt' : 'capturedAt'] = exact;
    const accepted = await runPublicGetProbe(environment()); assert.equal(accepted.status, 'PASS');
    assert.equal(accepted.checks[IDS[index]].observedAt, exact);
    fresh(); const bad = world.payloads.get('/platform-lab/api' + PATHS[index]);
    if (index === 5) bad.captureStartedAt = '2030-01-01T00:00:03.123Z';
    bad[index < 4 ? 'observedAt' : 'capturedAt'] = over;
    failed(await runPublicGetProbe(environment()), 'INVALID_DTO');
    assert.equal(world.calls.length, Math.max(4, index + 1));
  }
});

test('DNS5초·request15초·whole150초 timeout은 추가 요청 없이 종료한다', { concurrency: false }, async context => {
  clock(context, true);
  fresh({ stallDns: true }); const dns = runPublicGetProbe(environment()); await flush();
  context.mock.timers.tick(5001); failed(await dns, 'DNS_TIMEOUT'); assert.equal(world.calls.length, 0);
  fresh({ stallRequest: true }); const request = runPublicGetProbe(environment()); await flush();
  context.mock.timers.tick(15_001); failed(await request, 'REQUEST_TIMEOUT');
  assert.equal(world.calls.length, 1); assert.equal(world.calls[0].request.destroyed, true);
  fresh({ stallSleep: true }); const whole = runPublicGetProbe(environment()); await flush();
  context.mock.timers.tick(150_001); failed(await whole, 'WHOLE_TIMEOUT'); assert.equal(world.calls.length, 1);
});

test('timer 이전 DNS 반환이어도 실제5초 경계에서 TLS를 시작하지 않는다', { concurrency: false }, async context => {
  clock(context); let monotonic = 0; context.mock.method(performance, 'now', () => monotonic);
  for (const elapsed of [4999, 5000, 5001]) {
    monotonic = 0; fresh({ onDnsReturn: () => { monotonic = elapsed; } });
    const result = await runPublicGetProbe(environment());
    if (elapsed < 5000) assert.equal(result.status, 'PASS');
    else { failed(result, 'DNS_TIMEOUT'); assert.equal(world.calls.length, 0); }
  }
});

test('timer 이전 body end여도 실제15초 경계와 최종150초 기한에서 성공하지 않는다', { concurrency: false }, async context => {
  clock(context); let monotonic = 0; context.mock.method(performance, 'now', () => monotonic);
  for (const elapsed of [14_999, 15_000, 15_001]) {
    monotonic = 0; fresh({ onBeforeEnd: count => { if (count === 1) monotonic = elapsed; } });
    const result = await runPublicGetProbe(environment());
    if (elapsed < 15_000) assert.equal(result.status, 'PASS');
    else { failed(result, 'REQUEST_TIMEOUT'); assert.equal(world.calls.length, 1); }
  }
  monotonic = 0; fresh({ onBeforeEnd: count => { if (count === 6) monotonic = 150_000; } });
  failed(await runPublicGetProbe(environment()), 'WHOLE_TIMEOUT'); assert.equal(world.calls.length, 6);
});

test('시작보다 완료 wallclock이 앞서면 계약검사 뒤에도 PASS를 만들지 않는다', { concurrency: false }, async context => {
  let wall = NOW; context.mock.method(Date, 'now', () => wall);
  fresh({ onBeforeEnd: count => { if (count === 6) wall = NOW - 1; } });
  failed(await runPublicGetProbe(environment()), 'CLOCK_UNVERIFIED'); assert.equal(world.calls.length, 6);
});

test('기존 full9는 별도 route ACK를 여전히 요구하며 성공시 GET8·POST1이다', { concurrency: false }, async context => {
  clock(context);
  const legacy = { ...environment(), SMOKE_CONFIRM: 'true', SMOKE_VARIABLE_MATCH: 'true', SMOKE_ROUTE_OWNERSHIP: 'true' };
  fresh({ allowFullNine: true });
  const refused = await runSmoke({ ...legacy, SMOKE_ROUTE_OWNERSHIP: 'false' });
  assert.equal(refused.status, 'FAILED'); assert.equal(world.dns, 0); assert.equal(world.calls.length, 0);
  fresh({ allowFullNine: true });
  const full = await runSmoke(legacy); assert.equal(full.status, 'PASS');
  assert.equal(world.calls.length, 9);
  assert.deepEqual(world.calls.map(call => call.options.method), ['GET', 'GET', 'GET', 'GET', 'GET', 'GET', 'GET', 'GET', 'POST']);
  assert.equal(world.calls.at(-1).options.path, '/platform-lab/api/platform/summary');
});
