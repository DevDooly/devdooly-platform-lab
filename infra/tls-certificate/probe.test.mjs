import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { EventEmitter } from 'node:events';
import { mock, test } from 'node:test';

const PRIVATE = 'SYNTHETIC_PRIVATE_CERTIFICATE_CANARY';
const BASE = 'https://api.example.test/platform-lab/api';
const SOURCE = 'a'.repeat(40);
const NOW = Date.parse('2030-01-01T00:00:00.250Z');
const DAY = 86_400_000;
let world;
function fresh(overrides = {}) {
  world = { dns: 0, tls: [], http: 0,
    addresses: [{ address: '8.8.8.8', family: 4 }, { address: '1.1.1.1', family: 4 }],
    authorized: true, reused: false, remoteAddress: '8.8.8.8', remotePort: 443,
    protocol: 'TLSv1.3', raw: Buffer.from(PRIVATE),
    from: new Date(NOW - DAY), to: new Date(NOW + 45 * DAY), ...overrides };
  return world;
}
function environment(overrides = {}) {
  return { GITHUB_REPOSITORY: 'DevDooly/devdooly-platform-lab', GITHUB_EVENT_NAME: 'workflow_dispatch',
    GITHUB_REF: 'refs/heads/main', GITHUB_RUN_ATTEMPT: '1', GITHUB_SHA: SOURCE,
    TLS_CERTIFICATE_CONFIRM: 'true', TLS_CERTIFICATE_TARGET_OWNERSHIP: 'true',
    TLS_CERTIFICATE_VARIABLE_MATCH: 'true', LAB_PUBLIC_API_URL: BASE, ...overrides };
}
function clock(context, timers = false) {
  context.mock.timers.enable({ apis: timers ? ['Date', 'setTimeout'] : ['Date'], now: NOW });
}
const flush = () => new Promise(resolve => setImmediate(resolve));
const fakeLookup = async (hostname, options) => {
  world.dns++;
  assert.equal(hostname, 'api.example.test');
  assert.deepEqual(options, { family: 4, all: true, verbatim: true });
  if (world.dnsThrows) throw new Error(PRIVATE + BASE);
  if (world.stallDns) return new Promise(() => {});
  world.onDnsReturn?.();
  return world.addresses;
};
function fakeConnect(options) {
  const call = { options, socket: null, pinned: null, endCalls: 0, destroyCalls: 0 };
  world.tls.push(call);
  if (world.connectThrows) throw new Error(PRIVATE + BASE);
  const socket = new EventEmitter(); call.socket = socket;
  socket.authorized = world.authorized; socket.remoteAddress = world.remoteAddress;
  socket.remotePort = world.remotePort; socket.destroyed = false;
  socket.isSessionReused = () => world.reused;
  socket.getProtocol = () => world.protocol;
  socket.getPeerX509Certificate = () => {
    if (world.certificateThrows) throw new Error(PRIVATE + BASE);
    world.onCertificateRead?.();
    return world.missingCertificate ? undefined : { raw: world.raw, validFromDate: world.from,
      validToDate: world.to, subject: PRIVATE, issuer: PRIVATE, serialNumber: PRIVATE, subjectAltName: PRIVATE };
  };
  const close = hadError => { socket.destroyed = true; socket.emit('close', hadError); };
  socket.end = () => {
    call.endCalls++; world.onEnd?.();
    if (world.endThrows) throw new Error(PRIVATE);
    if (!world.closeNever) {
      if (world.closeDelay) setTimeout(() => close(world.closeHadError === true), world.closeDelay);
      else queueMicrotask(() => close(world.closeHadError === true));
    }
    return socket;
  };
  socket.destroy = () => {
    call.destroyCalls++; socket.destroyed = true;
    if (world.destroyThrows) throw new Error(PRIVATE);
    if (!world.destroyCloseNever) queueMicrotask(() => close(false));
    return socket;
  };
  options.lookup('api.example.test', {}, (error, address, family) => {
    assert.equal(error, null); call.pinned = { address, family };
  });
  queueMicrotask(() => {
    if (world.emitError) socket.emit('error', new Error(PRIVATE + BASE));
    else if (!world.stallHandshake) { world.onBeforeSecure?.(); socket.emit('secureConnect'); }
  });
  return socket;
}

// Native network entrypoints are replaced before either probe or its guarded smoke import loads.
mock.module('node:dns/promises', { namedExports: { lookup: fakeLookup } });
mock.module('node:tls', { namedExports: { connect: fakeConnect } });
mock.module('node:https', { namedExports: { request: () => { world.http++; throw new Error(PRIVATE); } } });
const { runCertificateProbe } = await import('./probe.ts');

function privacy(result) {
  const text = JSON.stringify(result);
  for (const value of [PRIVATE, BASE, 'api.example.test', '8.8.8.8', '1.1.1.1',
    'serialNumber', 'subjectAltName', 'issuer', 'authorization', 'secret-token']) {
    assert.equal(text.includes(value), false, value);
  }
  assert.ok(Buffer.byteLength(text, 'utf8') <= 4096);
  assert.equal(world.http, 0);
  assert.equal(result.naturalRenewalVerified, false);
  assert.equal(result.operatingConfigurationChanged, false);
}
function failed(result, code) {
  assert.equal(result.status, 'FAILED');
  assert.equal(result.errorCode, code);
  assert.equal(result.standardTlsVerified, false);
  for (const key of ['protocol', 'certificateSha256', 'notBefore', 'notAfter',
    'remainingValiditySeconds', 'remainingFullDays']) assert.equal(result[key], null, key);
  assert.equal(result.expiryAssessment, 'UNKNOWN'); privacy(result);
}

test('단일 DNS와 고정 IPv4의 TLS 한 번만 사용하고 허용22필드만 반환한다', { concurrency: false }, async context => {
  clock(context); fresh();
  const result = await runCertificateProbe(environment());
  assert.equal(result.status, 'PASS'); assert.equal(result.errorCode, 'NONE');
  assert.equal(world.dns, 1); assert.equal(world.tls.length, 1);
  assert.equal(result.publicIpv4Verified, true); assert.equal(result.standardTlsVerified, true);
  assert.equal(result.connectionClosed, true); assert.equal(result.protocol, 'TLSv1.3');
  assert.equal(result.remainingValiditySeconds, 45 * 86_400); assert.equal(result.remainingFullDays, 45);
  assert.equal(result.warningThresholdDays, 30); assert.equal(result.expiryAssessment, 'VALID_OVER_30_DAYS');
  assert.equal(result.validatorSourceCommit, SOURCE);
  assert.equal(result.targetBindingSha256, createHash('sha256').update('https://api.example.test:443').digest('hex'));
  assert.equal(result.certificateSha256, createHash('sha256').update(Buffer.from(PRIVATE)).digest('hex'));
  assert.deepEqual(Object.keys(result).sort(), ['schemaVersion', 'kind', 'scope', 'status', 'errorCode',
    'validatorSourceCommit', 'captureStartedAt', 'capturedAt', 'publicIpv4Verified', 'standardTlsVerified',
    'connectionClosed', 'protocol', 'targetBindingSha256', 'certificateSha256', 'notBefore', 'notAfter',
    'remainingValiditySeconds', 'remainingFullDays', 'warningThresholdDays', 'expiryAssessment',
    'naturalRenewalVerified', 'operatingConfigurationChanged'].sort());
  assert.equal(result.kind, 'tls-certificate-snapshot'); assert.equal(result.scope, 'PUBLIC_TLS_HANDSHAKE_ONLY');
  const { options, pinned, endCalls, destroyCalls } = world.tls[0];
  assert.equal(options.host, 'api.example.test'); assert.equal(options.servername, 'api.example.test');
  assert.equal(options.port, 443); assert.equal(options.family, 4); assert.equal(options.autoSelectFamily, false);
  assert.equal(options.rejectUnauthorized, true); assert.equal(options.minVersion, 'TLSv1.2');
  assert.equal(options.session, undefined); assert.equal(options.enableTrace, false);
  for (const key of ['ca', 'cert', 'key', 'pfx', 'checkServerIdentity', 'headers', 'path']) assert.equal(options[key], undefined);
  assert.deepEqual(pinned, { address: '8.8.8.8', family: 4 });
  assert.equal(endCalls, 1); assert.equal(destroyCalls, 0); privacy(result);
});

test('main·수동·첫attempt·소유저장소·SHA·ACK·URL 불일치는 DNS 전 거부한다', { concurrency: false }, async context => {
  clock(context);
  for (const change of [{ GITHUB_REPOSITORY: 'other/repository' }, { GITHUB_EVENT_NAME: 'push' },
    { GITHUB_REF: 'refs/heads/feature' }, { GITHUB_RUN_ATTEMPT: '2' }, { GITHUB_SHA: 'PENDING' },
    { TLS_CERTIFICATE_CONFIRM: 'false' }, { TLS_CERTIFICATE_TARGET_OWNERSHIP: 'false' },
    { TLS_CERTIFICATE_VARIABLE_MATCH: 'false' }, { LAB_PUBLIC_API_URL: '' },
    { LAB_PUBLIC_API_URL: 'http://api.example.test/api' }, { LAB_PUBLIC_API_URL: 'https://127.0.0.1/api' },
    { LAB_PUBLIC_API_URL: 'https://secret-token@api.example.test/api' }]) {
    fresh(); failed(await runCertificateProbe(environment(change)), 'CONFIGURATION_NOT_VERIFIED');
    assert.equal(world.dns, 0); assert.equal(world.tls.length, 0);
  }
});

test('사용자 CA·TLS 우회·프록시·debug·keylog 환경은 빈 값도 DNS 전에 거부한다', { concurrency: false }, async context => {
  clock(context);
  for (const name of ['NODE_OPTIONS', 'NODE_EXTRA_CA_CERTS', 'NODE_TLS_REJECT_UNAUTHORIZED', 'NODE_USE_SYSTEM_CA',
    'NODE_DEBUG', 'NODE_DEBUG_NATIVE', 'SSL_CERT_FILE', 'SSL_CERT_DIR', 'SSLKEYLOGFILE',
    'HTTP_PROXY', 'HTTPS_PROXY', 'ALL_PROXY', 'NO_PROXY', 'http_proxy', 'https_proxy', 'all_proxy', 'no_proxy', 'NODE_USE_ENV_PROXY']) {
    for (const value of ['', PRIVATE]) {
      fresh(); failed(await runCertificateProbe(environment({ [name]: value })), 'ENVIRONMENT_NOT_VERIFIED');
      assert.equal(world.dns, 0); assert.equal(world.tls.length, 0);
    }
  }
});

test('DNS의 혼합 private·IPv6·빈 값·17개 응답은 TLS 전 거부한다', { concurrency: false }, async context => {
  clock(context);
  for (const [addresses, code] of [
    [[{ address: '8.8.8.8', family: 4 }, { address: '192.168.0.1', family: 4 }], 'DNS_ADDRESS_REJECTED'],
    [[{ address: '::1', family: 6 }], 'DNS_ADDRESS_REJECTED'],
    [[null], 'DNS_ADDRESS_REJECTED'], [[], 'DNS_NO_SUPPORTED_PUBLIC_IPV4'],
    [Array.from({ length: 17 }, () => ({ address: '8.8.8.8', family: 4 })), 'DNS_NO_SUPPORTED_PUBLIC_IPV4'],
  ]) {
    fresh({ addresses }); failed(await runCertificateProbe(environment()), code);
    assert.equal(world.dns, 1); assert.equal(world.tls.length, 0);
  }
});

test('native DNS와 TLS 오류 원문은 공개하지 않고 재시도하지 않는다', { concurrency: false }, async context => {
  clock(context);
  fresh({ dnsThrows: true }); failed(await runCertificateProbe(environment()), 'DNS_LOOKUP_FAILED');
  assert.equal(world.dns, 1); assert.equal(world.tls.length, 0);
  fresh({ connectThrows: true }); const creation = await runCertificateProbe(environment());
  failed(creation, 'TLS_UNVERIFIED'); assert.equal(creation.connectionClosed, false);
  assert.equal(world.dns, 1); assert.equal(world.tls.length, 1);
  fresh({ emitError: true }); const error = await runCertificateProbe(environment());
  failed(error, 'TLS_UNVERIFIED'); assert.equal(error.connectionClosed, true);
  assert.equal(world.tls.length, 1);
});

test('미인증·session재사용·다른remote 또는TLS프로토콜은 폐기한다', { concurrency: false }, async context => {
  clock(context);
  for (const change of [{ authorized: false }, { authorized: undefined }, { reused: true },
    { reused: undefined }, { remoteAddress: '1.1.1.1' }, { remotePort: 444 },
    { remotePort: '443' }, { protocol: 'TLSv1.1' }, { protocol: null }]) {
    fresh(change); const result = await runCertificateProbe(environment());
    failed(result, 'TLS_PROPERTIES_UNVERIFIED'); assert.equal(result.connectionClosed, true);
    assert.equal(world.tls.length, 1); assert.equal(world.tls[0].destroyCalls, 1);
  }
  fresh({ protocol: 'TLSv1.2' }); assert.equal((await runCertificateProbe(environment())).protocol, 'TLSv1.2');
});

test('DER·Date의 실제 타입과 크기·날짜 범위가 틀리면 certificate필드는 null이다', { concurrency: false }, async context => {
  clock(context);
  for (const change of [{ missingCertificate: true }, { raw: PRIVATE }, { raw: Buffer.alloc(0) },
    { raw: Buffer.alloc(65_537) }, { from: '2030-01-01T00:00:00Z' }, { to: new Date(NaN) },
    { from: new Date(NOW + DAY), to: new Date(NOW) }, { certificateThrows: true }]) {
    fresh(change); const result = await runCertificateProbe(environment());
    failed(result, 'CERTIFICATE_UNVERIFIED'); assert.equal(result.connectionClosed, true);
    assert.equal(world.tls.length, 1);
  }
});

test('완료시각이notBefore보다이르거나notAfter와같으면 유효성 성공을 만들지 않는다', { concurrency: false }, async context => {
  clock(context);
  for (const change of [{ from: new Date(NOW + 1) }, { to: new Date(NOW) }]) {
    fresh(change); const result = await runCertificateProbe(environment());
    failed(result, 'CERTIFICATE_VALIDITY_UNVERIFIED'); assert.equal(result.connectionClosed, true);
  }
  fresh({ from: new Date(NOW) }); assert.equal((await runCertificateProbe(environment())).status, 'PASS');
});

test('30일경계는공개floor초기준이며완료직전1ms도정확히보존한다', { concurrency: false }, async context => {
  clock(context);
  for (const [remainingMs, seconds, assessment] of [
    [30 * DAY - 1, 30 * 86_400 - 1, 'EXPIRING_WITHIN_30_DAYS'],
    [30 * DAY, 30 * 86_400, 'EXPIRING_WITHIN_30_DAYS'],
    [30 * DAY + 999, 30 * 86_400, 'EXPIRING_WITHIN_30_DAYS'],
    [30 * DAY + 1000, 30 * 86_400 + 1, 'VALID_OVER_30_DAYS'],
    [1, 0, 'EXPIRING_WITHIN_30_DAYS'],
  ]) {
    fresh({ to: new Date(NOW + remainingMs) }); const result = await runCertificateProbe(environment());
    assert.equal(result.status, 'PASS'); assert.equal(result.remainingValiditySeconds, seconds);
    assert.equal(result.remainingFullDays, Math.floor(seconds / 86_400));
    assert.equal(result.expiryAssessment, assessment); assert.equal(result.notAfter, new Date(NOW + remainingMs).toISOString());
    privacy(result);
  }
});

test('close가실제관측되기전성공하지않고잔여기간은close완료시각으로계산한다', { concurrency: false }, async context => {
  clock(context, true); fresh({ closeDelay: 500 });
  let settled = false;
  const pending = runCertificateProbe(environment()).then(value => { settled = true; return value; });
  await flush(); assert.equal(settled, false); assert.equal(world.tls[0].endCalls, 1);
  context.mock.timers.tick(500); const result = await pending;
  assert.equal(result.status, 'PASS'); assert.equal(result.connectionClosed, true);
  assert.equal(result.captureStartedAt, new Date(NOW).toISOString());
  assert.equal(result.capturedAt, new Date(NOW + 500).toISOString());
  assert.equal(result.remainingValiditySeconds, 45 * 86_400 - 1); privacy(result);
});

test('close2초실패는폐기를시도하고지연native에러를원문로그로만들지않는다', { concurrency: false }, async context => {
  clock(context, true); fresh({ closeNever: true });
  const pending = runCertificateProbe(environment()); await flush();
  context.mock.timers.tick(2001); const result = await pending;
  failed(result, 'CLOSE_TIMEOUT'); assert.equal(result.connectionClosed, false);
  assert.equal(world.tls[0].destroyCalls, 1);
  assert.doesNotThrow(() => world.tls[0].socket.emit('error', new Error(PRIVATE + BASE)));
});

test('DNS5초deadline은TLS를시작하지않으며whole25초도성공하지않는다', { concurrency: false }, async context => {
  clock(context, true); fresh({ stallDns: true });
  const pending = runCertificateProbe(environment()); await flush();
  context.mock.timers.tick(5001); failed(await pending, 'DNS_TIMEOUT');
  assert.equal(world.dns, 1); assert.equal(world.tls.length, 0);
  fresh({ stallDns: true }); const whole = runCertificateProbe(environment()); await flush();
  context.mock.timers.tick(25_001); failed(await whole, 'WHOLE_TIMEOUT');
  assert.equal(world.tls.length, 0);
});

test('접속10초deadline뒤한socket만폐기하며추가주소를재시도하지않는다', { concurrency: false }, async context => {
  clock(context, true); fresh({ stallHandshake: true });
  const pending = runCertificateProbe(environment()); await flush();
  context.mock.timers.tick(10_001); await flush(); const result = await pending;
  failed(result, 'CONNECTION_TIMEOUT'); assert.equal(result.connectionClosed, true);
  assert.equal(world.dns, 1); assert.equal(world.tls.length, 1); assert.equal(world.tls[0].destroyCalls, 1);
});

test('close의hadError와end오류는certificate성공필드를남기지않는다', { concurrency: false }, async context => {
  clock(context);
  fresh({ closeHadError: true }); failed(await runCertificateProbe(environment()), 'TLS_UNVERIFIED');
  fresh({ endThrows: true }); const result = await runCertificateProbe(environment());
  failed(result, 'CERTIFICATE_UNVERIFIED'); assert.equal(result.connectionClosed, true);
});

test('소켓폐기시close를관측하지못하면connectionClosed를만들지않는다', { concurrency: false }, async context => {
  clock(context, true); fresh({ authorized: false, destroyCloseNever: true });
  const pending = runCertificateProbe(environment()); await flush();
  context.mock.timers.tick(2001); const result = await pending;
  failed(result, 'TLS_PROPERTIES_UNVERIFIED'); assert.equal(result.connectionClosed, false);
});

test('시작완료wallclock역전과최종monotonicdeadline경과는모두실패한다', { concurrency: false }, async context => {
  let wall = NOW; context.mock.method(Date, 'now', () => wall);
  fresh({ onEnd: () => { wall = NOW - 1; } });
  failed(await runCertificateProbe(environment()), 'CLOCK_UNVERIFIED');
  wall = NOW; let monotonic = 0; context.mock.method(performance, 'now', () => monotonic);
  fresh({ onEnd: () => { monotonic = 25_001; } });
  const result = await runCertificateProbe(environment());
  failed(result, 'WHOLE_TIMEOUT'); assert.equal(result.connectionClosed, true);
});

test('대상지문은동일host443에묶이며API경로변경을새갱신증거로만들지않는다', { concurrency: false }, async context => {
  clock(context); fresh(); const first = await runCertificateProbe(environment());
  fresh(); const second = await runCertificateProbe(environment({ LAB_PUBLIC_API_URL: 'https://api.example.test/api' }));
  assert.equal(first.targetBindingSha256, second.targetBindingSha256);
  assert.equal(first.certificateSha256, second.certificateSha256);
  assert.equal(first.naturalRenewalVerified, false); assert.equal(second.naturalRenewalVerified, false);
  privacy(second);
});

test('DNS timer보다반환microtask가먼저여도실제5초경계부터거부한다', { concurrency: false }, async context => {
  clock(context); let monotonic = 0; context.mock.method(performance, 'now', () => monotonic);
  for (const elapsed of [4999, 5000, 5001]) {
    monotonic = 0; fresh({ onDnsReturn: () => { monotonic = elapsed; } });
    const result = await runCertificateProbe(environment());
    if (elapsed < 5000) assert.equal(result.status, 'PASS');
    else { failed(result, 'DNS_TIMEOUT'); assert.equal(world.tls.length, 0); }
    assert.equal(world.dns, 1); privacy(result);
  }
});

test('secureConnect와인증서읽기직후의실제10초기한을모두확인한다', { concurrency: false }, async context => {
  clock(context); let monotonic = 0; context.mock.method(performance, 'now', () => monotonic);
  for (const hook of ['onBeforeSecure', 'onCertificateRead']) for (const elapsed of [9999, 10_000, 10_001]) {
    monotonic = 0; fresh({ [hook]: () => { monotonic = elapsed; } });
    const result = await runCertificateProbe(environment());
    if (elapsed < 10_000) assert.equal(result.status, 'PASS');
    else failed(result, 'CONNECTION_TIMEOUT');
    assert.equal(result.connectionClosed, true); assert.equal(world.tls.length, 1); privacy(result);
  }
});

test('close이벤트가timer보다먼저여도실제2초경계의늦은close는실패한다', { concurrency: false }, async context => {
  clock(context); let monotonic = 0; context.mock.method(performance, 'now', () => monotonic);
  for (const elapsed of [1999, 2000, 2001]) {
    monotonic = 0; fresh({ onEnd: () => { monotonic = elapsed; } });
    const result = await runCertificateProbe(environment());
    if (elapsed < 2000) assert.equal(result.status, 'PASS');
    else failed(result, 'CLOSE_TIMEOUT');
    // The close was observed even when its timing disqualifies certificate success.
    assert.equal(result.connectionClosed, true); assert.equal(world.tls.length, 1); privacy(result);
  }
});
