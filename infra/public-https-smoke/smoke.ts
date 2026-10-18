/** Manual off-LAN read probe. Raw configuration, bodies and exceptions never leave RAM. */
import { lookup } from 'node:dns/promises';
import { openSync, closeSync, writeFileSync } from 'node:fs';
import { request } from 'node:https';
import { isIP } from 'node:net';
import { setTimeout as sleep } from 'node:timers/promises';
import { pathToFileURL } from 'node:url';
import { publicApiConfiguration, publicReadUrl } from '../../apps/lab-web/src/lib/public-api-base.ts';
import { isRun, isRunDetail, isSummary, isRelease } from '../../apps/lab-web/src/lib/api.ts';
import { isObservationRecord } from '../../apps/lab-web/src/lib/observation.ts';
import { validateJobObservation, MAX_JOB_OBSERVATION_BYTES } from '../../apps/lab-web/src/lib/job-observation.ts';
import { parseKafkaObservation, kafkaUtcNs, MAX_KAFKA_OBSERVATION_BYTES } from '../../apps/lab-web/src/lib/kafka-observation.ts';
import type { IncomingHttpHeaders } from 'node:http';

const ORIGIN = 'https://devdooly.github.io';
const SHA = /^[a-f0-9]{40}$/;
const REQUEST_MS = 15_000;
const WHOLE_MS = 150_000;
const TOTAL_BYTES = 1024 * 1024;
const ROUTES = [
  ['SUMMARY', '/platform/summary', 256 * 1024],
  ['RELEASES', '/platform/releases', 256 * 1024],
  ['RUN_LIST', '/demo/runs', 256 * 1024],
  ['RUN_DETAIL_EXAMPLE', '/demo/runs/synthetic-v1-seed-42', 256 * 1024],
  ['JOBS', '/jobs/observation', MAX_JOB_OBSERVATION_BYTES],
  ['KAFKA', '/kafka/observation', MAX_KAFKA_OBSERVATION_BYTES],
] as const;
const NEGATIVES = [
  ['DENIED_PATH', '/__smoke-denied', 'GET', ORIGIN, 404, 'NOT_FOUND'],
  ['DENIED_ORIGIN', '/platform/summary', 'GET', 'https://example.invalid', 403, 'ORIGIN_REJECTED'],
  ['DENIED_METHOD', '/platform/summary', 'POST', ORIGIN, 405, 'GET_REQUIRED'],
] as const;
const CODES = new Set(['NONE', 'CONFIGURATION_NOT_VERIFIED', 'DNS_LOOKUP_FAILED',
  'DNS_ADDRESS_REJECTED', 'DNS_NO_SUPPORTED_PUBLIC_IPV4', 'DNS_TIMEOUT', 'REQUEST_TIMEOUT',
  'WHOLE_TIMEOUT', 'TLS_OR_NETWORK_UNVERIFIED', 'HTTP_STATUS_UNVERIFIED',
  'HEADERS_UNVERIFIED', 'RESPONSE_TOO_LARGE', 'INVALID_DTO', 'OUTPUT_UNAVAILABLE', 'UNVERIFIED']);
class SmokeError extends Error {
  readonly code: string;
  constructor(code: string) { super('SMOKE_FAILED'); this.code = code; }
}
function need(value: unknown, code: string): asserts value {
  if (!value) throw new SmokeError(code);
}
const record = (value: unknown): value is Record<string, unknown> =>
  typeof value === 'object' && value !== null && !Array.isArray(value);
const exact = (value: Record<string, unknown>, fields: readonly string[]) =>
  Object.keys(value).length === fields.length && fields.every(key => Object.hasOwn(value, key));

/** Conservative global-unicast IPv4 subset; no exception for special-use /24s. */
export function isPublicIpv4(address: string): boolean {
  if (isIP(address) !== 4) return false;
  const parts = address.split('.').map(Number);
  const number = ((parts[0] * 2 ** 24) + (parts[1] * 2 ** 16) + (parts[2] * 256) + parts[3]) >>> 0;
  const denied = [
    [0x00000000, 8], [0x0a000000, 8], [0x64400000, 10], [0x7f000000, 8],
    [0xa9fe0000, 16], [0xac100000, 12], [0xc0000000, 24], [0xc0000200, 24],
    [0xc0586300, 24], [0xc0a80000, 16], [0xc6120000, 15], [0xc6336400, 24],
    [0xcb007100, 24], [0xe0000000, 4], [0xf0000000, 4],
  ];
  return !denied.some(([prefix, bits]) => (number >>> (32 - bits)) === (prefix >>> (32 - bits)));
}

async function selectPublicIpv4(hostname: string): Promise<string> {
  let timer: ReturnType<typeof setTimeout> | undefined;
  try {
    const addresses = await Promise.race([
      lookup(hostname, { family: 4, all: true, verbatim: true }),
      new Promise<never>((_resolve, reject) => { timer = setTimeout(() => reject(new SmokeError('DNS_TIMEOUT')), 5000); }),
    ]);
    need(addresses.length > 0 && addresses.length <= 16, 'DNS_NO_SUPPORTED_PUBLIC_IPV4');
    need(addresses.every(item => item.family === 4 && isPublicIpv4(item.address)), 'DNS_ADDRESS_REJECTED');
    return addresses[0].address;
  } catch (error) {
    if (error instanceof SmokeError) throw error;
    throw new SmokeError('DNS_LOOKUP_FAILED');
  } finally { if (timer) clearTimeout(timer); }
}

export function verifyHeaders(headers: IncomingHttpHeaders, rawHeaders: string[], origin: string): void {
  const once = ['content-type', 'content-length', 'cache-control', 'vary', 'access-control-allow-origin'];
  for (const name of once) {
    let found = 0;
    for (let index = 0; index < rawHeaders.length; index += 2) if (rawHeaders[index].toLowerCase() === name) found++;
    need(found <= 1, 'HEADERS_UNVERIFIED');
  }
  need(typeof headers['content-type'] === 'string'
    && /^application\/json(?:;\s*charset=utf-8)?$/i.test(headers['content-type']), 'HEADERS_UNVERIFIED');
  need(headers['cache-control'] === 'no-store' && headers.vary === 'Origin', 'HEADERS_UNVERIFIED');
  need(headers['access-control-allow-origin'] === (origin === ORIGIN ? ORIGIN : undefined), 'HEADERS_UNVERIFIED');
  need(['authorization', 'cookie', 'www-authenticate', 'proxy-authenticate', 'set-cookie', 'location',
    'refresh', 'access-control-allow-credentials', 'content-encoding', 'x-accel-redirect']
    .every(name => headers[name] === undefined), 'HEADERS_UNVERIFIED');
}

type Reply = { status: number; headers: IncomingHttpHeaders; raw: Buffer };
type Budget = { bytes: number };
async function oneRequest(url: URL, address: string, method: 'GET' | 'POST', origin: string,
  cap: number, budget: Budget, signal: AbortSignal, statusSeen: (status: number) => void): Promise<Reply> {
  return new Promise((resolve, reject) => {
    let done = false;
    let timer: ReturnType<typeof setTimeout> | undefined;
    const finish = (error?: SmokeError, reply?: Reply) => {
      if (done) return;
      done = true;
      if (timer) clearTimeout(timer);
      signal.removeEventListener('abort', aborted);
      if (error) reject(error); else resolve(reply!);
    };
    const req = request({
      protocol: 'https:', hostname: url.hostname, servername: url.hostname, port: 443,
      path: url.pathname, method, family: 4, autoSelectFamily: false, agent: false,
      rejectUnauthorized: true, maxHeaderSize: 16 * 1024,
      lookup: (_hostname, _options, callback) => callback(null, address, 4),
      headers: { Accept: 'application/json', Origin: origin, 'Cache-Control': 'no-cache' },
    }, response => {
      const chunks: Buffer[] = [];
      let bytes = 0;
      try {
        need(typeof response.statusCode === 'number' && response.statusCode >= 100 && response.statusCode <= 599,
          'HTTP_STATUS_UNVERIFIED');
        statusSeen(response.statusCode);
        need(response.statusCode < 300 || response.statusCode >= 400, 'HTTP_STATUS_UNVERIFIED');
        verifyHeaders(response.headers, response.rawHeaders, origin);
        if (response.headers['content-length'] !== undefined) {
          need(/^(0|[1-9][0-9]{0,9})$/.test(response.headers['content-length']), 'HEADERS_UNVERIFIED');
          need(Number(response.headers['content-length']) <= cap, 'RESPONSE_TOO_LARGE');
        }
      } catch (error) {
        finish(error instanceof SmokeError ? error : new SmokeError('HEADERS_UNVERIFIED'));
        response.destroy(); req.destroy(); return;
      }
      response.on('data', (chunk: Buffer) => {
        if (done) return;
        bytes += chunk.length; budget.bytes += chunk.length;
        if (bytes > cap || budget.bytes > TOTAL_BYTES) {
          finish(new SmokeError('RESPONSE_TOO_LARGE')); response.destroy(); req.destroy(); return;
        }
        chunks.push(chunk);
      });
      response.on('end', () => finish(undefined, { status: response.statusCode!, headers: response.headers, raw: Buffer.concat(chunks, bytes) }));
      response.on('error', () => finish(new SmokeError('TLS_OR_NETWORK_UNVERIFIED')));
      response.on('aborted', () => finish(new SmokeError('TLS_OR_NETWORK_UNVERIFIED')));
    });
    const aborted = () => { finish(new SmokeError('WHOLE_TIMEOUT')); req.destroy(); };
    signal.addEventListener('abort', aborted, { once: true });
    timer = setTimeout(() => { finish(new SmokeError('REQUEST_TIMEOUT')); req.destroy(); }, REQUEST_MS);
    req.on('error', () => finish(new SmokeError('TLS_OR_NETWORK_UNVERIFIED')));
    if (signal.aborted) { aborted(); return; }
    req.end();
  });
}

function json(raw: Buffer): unknown {
  try { return JSON.parse(new TextDecoder('utf-8', { fatal: true, ignoreBOM: true }).decode(raw)); }
  catch { throw new SmokeError('INVALID_DTO'); }
}
function validateLab(payloads: unknown[]): { sourceCommit: string; observedTimes: string[] } {
  const [summary, releases, runs, detail] = payloads;
  need(isSummary(summary) && isRunDetail(detail) && record(releases) && exact(releases, ['items', 'observedAt'])
    && Array.isArray(releases.items) && releases.items.every(isRelease)
    && record(runs) && exact(runs, ['items', 'observedAt']) && Array.isArray(runs.items) && runs.items.every(isRun), 'INVALID_DTO');
  need(summary.service === 'devdooly-platform-lab-api' && summary.environment === 'mini-pc'
    && summary.status === 'UP' && SHA.test(summary.sourceCommit), 'INVALID_DTO');
  const capturedAt = new Date().toISOString();
  const data = { runs: runs.items, detail, summary, releases: releases.items, observedAt: summary.observedAt };
  need(isObservationRecord({ schemaVersion: 1, kind: 'observed', capturedAt,
    provenance: { environment: 'mini-pc', sourceCommit: summary.sourceCommit, collectorVersion: '1' }, data }), 'INVALID_DTO');
  const observedTimes = [summary.observedAt, releases.observedAt, runs.observedAt, detail.observedAt];
  const ceiling = BigInt(Date.now()) * 1_000_000n;
  need(observedTimes.every(value => {
    const instant = kafkaUtcNs(value);
    return instant !== null && instant <= ceiling;
  }), 'INVALID_DTO');
  return { sourceCommit: summary.sourceCommit, observedTimes: observedTimes as string[] };
}

type Check = { passed: boolean; status: number | null; sourceCommit: string | null; observedAt: string | null };
type Result = { schemaVersion: 1; kind: 'public-https-smoke'; status: 'PASS' | 'FAILED'; errorCode: string;
  validatorSourceCommit: string | null; captureStartedAt: string; capturedAt: string;
  routeOwnershipAcknowledged: boolean; publicIpv4Verified: boolean; standardTlsVerified: boolean;
  checks: Record<string, Check> };

export async function runSmoke(environment: NodeJS.ProcessEnv): Promise<Result> {
  const result: Result = { schemaVersion: 1, kind: 'public-https-smoke', status: 'FAILED', errorCode: 'UNVERIFIED',
    validatorSourceCommit: SHA.test(environment.GITHUB_SHA || '') ? environment.GITHUB_SHA! : null,
    captureStartedAt: new Date().toISOString(), capturedAt: new Date().toISOString(),
    routeOwnershipAcknowledged: false, publicIpv4Verified: false, standardTlsVerified: false,
    checks: Object.fromEntries([...ROUTES, ...NEGATIVES].map(([id]) => [id, { passed: false, status: null, sourceCommit: null, observedAt: null }])) };
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), WHOLE_MS);
  try {
    need(environment.SMOKE_CONFIRM === 'true' && environment.SMOKE_ROUTE_OWNERSHIP === 'true'
      && environment.SMOKE_VARIABLE_MATCH === 'true' && result.validatorSourceCommit !== null, 'CONFIGURATION_NOT_VERIFIED');
    const configuration = publicApiConfiguration(environment.LAB_PUBLIC_API_URL);
    need(configuration.externalHttps && !configuration.invalid, 'CONFIGURATION_NOT_VERIFIED');
    result.routeOwnershipAcknowledged = true;
    const base = new URL(configuration.apiBase);
    const address = await selectPublicIpv4(base.hostname);
    result.publicIpv4Verified = true;
    const budget = { bytes: 0 };
    const payloads: unknown[] = [];
    for (const [index, [id, path, cap]] of ROUTES.entries()) {
      if (index > 0) await sleep(1100, undefined, { signal: controller.signal });
      const target = publicReadUrl(configuration.apiBase, path);
      need(target !== null, 'CONFIGURATION_NOT_VERIFIED');
      const reply = await oneRequest(new URL(target), address, 'GET', ORIGIN, cap, budget, controller.signal,
        status => { result.checks[id].status = status; });
      result.standardTlsVerified = true;
      need(reply.status === 200, 'HTTP_STATUS_UNVERIFIED');
      if (index < 4) {
        payloads.push(json(reply.raw));
        if (index === 3) {
          const validated = validateLab(payloads);
          for (const [labIndex, [labId]] of ROUTES.slice(0, 4).entries()) Object.assign(result.checks[labId], {
            passed: true, sourceCommit: validated.sourceCommit, observedAt: validated.observedTimes[labIndex],
          });
        }
      } else if (id === 'JOBS') {
        const value = json(reply.raw);
        need(validateJobObservation(value) && value.environment === 'MINI_PC' && value.scope === 'DEPLOYED_RUNTIME'
          && SHA.test(value.sourceCommit) && Date.parse(value.capturedAt) <= Date.now(), 'INVALID_DTO');
        Object.assign(result.checks[id], { passed: true, sourceCommit: value.sourceCommit, observedAt: value.capturedAt });
      } else {
        const value = parseKafkaObservation(new TextDecoder('utf-8', { fatal: true, ignoreBOM: true }).decode(reply.raw), Date.now());
        need(value && value.environment === 'MINI_PC' && value.scope === 'DEPLOYED_KAFKA', 'INVALID_DTO');
        Object.assign(result.checks[id], { passed: true, sourceCommit: value.sourceCommit, observedAt: value.capturedAt });
      }
    }
    // Ownership is checked before DNS/any GET and again before the only POST.
    need(result.routeOwnershipAcknowledged && environment.SMOKE_ROUTE_OWNERSHIP === 'true', 'CONFIGURATION_NOT_VERIFIED');
    for (const [id, path, method, origin, expected, code] of NEGATIVES) {
      await sleep(1100, undefined, { signal: controller.signal });
      const target = new URL(configuration.apiBase + path);
      const reply = await oneRequest(target, address, method, origin, 8 * 1024, budget, controller.signal,
        status => { result.checks[id].status = status; });
      need(reply.status === expected && (method !== 'POST' || reply.headers.allow === 'GET'), 'HTTP_STATUS_UNVERIFIED');
      const value = json(reply.raw);
      need(record(value) && exact(value, ['kind', 'code']) && value.kind === 'public-gateway-error' && value.code === code, 'INVALID_DTO');
      result.checks[id].passed = true;
    }
    result.status = 'PASS'; result.errorCode = 'NONE';
  } catch (error) {
    result.errorCode = controller.signal.aborted ? 'WHOLE_TIMEOUT'
      : error instanceof SmokeError && CODES.has(error.code) ? error.code : 'UNVERIFIED';
  } finally { clearTimeout(timer); result.capturedAt = new Date().toISOString(); }
  return result;
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  let output: number;
  try {
    need(process.argv.length === 3, 'OUTPUT_UNAVAILABLE');
    // Refuse an existing attempt's result before DNS or HTTP, including a zero-byte failed attempt.
    output = openSync(process.argv[2], 'wx', 0o600);
  } catch {
    process.stdout.write(JSON.stringify({ status: 'FAILED', errorCode: 'OUTPUT_UNAVAILABLE' }) + '\n');
    process.exit(1);
  }
  const result = await runSmoke(process.env);
  try {
    writeFileSync(output, JSON.stringify(result, null, 2) + '\n');
    closeSync(output);
    process.stdout.write(JSON.stringify(result) + '\n');
  } catch {
    process.stdout.write(JSON.stringify({ status: 'FAILED', errorCode: 'OUTPUT_UNAVAILABLE' }) + '\n');
    process.exit(1);
  }
  // An OS lookup left in flight after its finite deadline cannot keep the CLI alive.
  process.exit(result.status === 'PASS' ? 0 : 1);
}
