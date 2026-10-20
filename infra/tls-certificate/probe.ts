/** One approved TLS handshake only. Configuration, certificate DER and native errors stay in RAM. */
import { createHash } from 'node:crypto';
import { lookup } from 'node:dns/promises';
import { openSync, closeSync, writeFileSync } from 'node:fs';
import { connect } from 'node:tls';
import type { TLSSocket } from 'node:tls';
import { pathToFileURL } from 'node:url';
import { publicApiConfiguration } from '../../apps/lab-web/src/lib/public-api-base.ts';
import { isPublicIpv4 } from '../public-https-smoke/smoke.ts';

const SHA = /^[a-f0-9]{40}$/;
const DNS_MS = 5000;
const CONNECTION_MS = 10_000;
const CLOSE_MS = 2000;
const WHOLE_MS = 25_000;
const WARNING_DAYS = 30;
const DAY_SECONDS = 86_400;
const FORBIDDEN_ENV = [
  'NODE_OPTIONS', 'NODE_EXTRA_CA_CERTS', 'NODE_TLS_REJECT_UNAUTHORIZED', 'NODE_USE_SYSTEM_CA',
  'NODE_DEBUG', 'NODE_DEBUG_NATIVE', 'SSL_CERT_FILE', 'SSL_CERT_DIR', 'SSLKEYLOGFILE',
  'HTTP_PROXY', 'HTTPS_PROXY', 'ALL_PROXY', 'NO_PROXY',
  'http_proxy', 'https_proxy', 'all_proxy', 'no_proxy', 'NODE_USE_ENV_PROXY',
] as const;
const ERRORS = ['NONE', 'CONFIGURATION_NOT_VERIFIED', 'ENVIRONMENT_NOT_VERIFIED',
  'DNS_LOOKUP_FAILED', 'DNS_ADDRESS_REJECTED', 'DNS_NO_SUPPORTED_PUBLIC_IPV4', 'DNS_TIMEOUT',
  'CONNECTION_TIMEOUT', 'WHOLE_TIMEOUT', 'TLS_UNVERIFIED', 'TLS_PROPERTIES_UNVERIFIED',
  'CERTIFICATE_UNVERIFIED', 'CERTIFICATE_VALIDITY_UNVERIFIED', 'CLOCK_UNVERIFIED',
  'CLOSE_TIMEOUT', 'OUTPUT_UNAVAILABLE', 'UNVERIFIED'] as const;
type ErrorCode = typeof ERRORS[number];
type Protocol = 'TLSv1.2' | 'TLSv1.3';
class ProbeError extends Error {
  readonly code: ErrorCode;
  constructor(code: ErrorCode) { super('TLS_CERTIFICATE_FAILED'); this.code = code; }
}
function need(value: unknown, code: ErrorCode): asserts value {
  if (!value) throw new ProbeError(code);
}
function errorCode(error: unknown): ErrorCode {
  return error instanceof ProbeError && ERRORS.includes(error.code) ? error.code : 'UNVERIFIED';
}
function utc(milliseconds: number): string {
  need(Number.isSafeInteger(milliseconds) && milliseconds >= 0, 'CLOCK_UNVERIFIED');
  const value = new Date(milliseconds).toISOString();
  need(/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z$/.test(value), 'CLOCK_UNVERIFIED');
  return value;
}

export type CertificateSnapshot = {
  schemaVersion: 1; kind: 'tls-certificate-snapshot'; scope: 'PUBLIC_TLS_HANDSHAKE_ONLY';
  status: 'PASS' | 'FAILED'; errorCode: ErrorCode; validatorSourceCommit: string | null;
  captureStartedAt: string; capturedAt: string; publicIpv4Verified: boolean;
  standardTlsVerified: boolean; connectionClosed: boolean; protocol: Protocol | null;
  targetBindingSha256: string | null; certificateSha256: string | null;
  notBefore: string | null; notAfter: string | null; remainingValiditySeconds: number | null;
  remainingFullDays: number | null; warningThresholdDays: 30;
  expiryAssessment: 'UNKNOWN' | 'VALID_OVER_30_DAYS' | 'EXPIRING_WITHIN_30_DAYS';
  naturalRenewalVerified: false; operatingConfigurationChanged: false;
};
type CertificateFacts = {
  protocol: Protocol; certificateSha256: string; notBefore: string; notAfter: string;
  notBeforeMs: number; notAfterMs: number;
};
type ConnectionOutcome = { error: ErrorCode; closed: boolean; facts: CertificateFacts | null };

async function publicAddress(hostname: string, signal: AbortSignal): Promise<string> {
  const phaseDeadline = performance.now() + DNS_MS;
  let timer: ReturnType<typeof setTimeout> | undefined;
  let aborted: (() => void) | undefined;
  try {
    need(!signal.aborted, 'WHOLE_TIMEOUT');
    const addresses = await Promise.race([
      lookup(hostname, { family: 4, all: true, verbatim: true }),
      new Promise<never>((_resolve, reject) => {
        timer = setTimeout(() => reject(new ProbeError('DNS_TIMEOUT')), DNS_MS);
      }),
      new Promise<never>((_resolve, reject) => {
        aborted = () => reject(new ProbeError('WHOLE_TIMEOUT'));
        signal.addEventListener('abort', aborted, { once: true });
      }),
    ]);
    need(Array.isArray(addresses) && addresses.length > 0 && addresses.length <= 16,
      'DNS_NO_SUPPORTED_PUBLIC_IPV4');
    need(addresses.every(item => item !== null && typeof item === 'object'
      && item.family === 4 && typeof item.address === 'string' && isPublicIpv4(item.address)), 'DNS_ADDRESS_REJECTED');
    need(!signal.aborted, 'WHOLE_TIMEOUT');
    need(performance.now() < phaseDeadline, 'DNS_TIMEOUT');
    return addresses[0].address;
  } catch (error) {
    if (error instanceof ProbeError) throw error;
    throw new ProbeError('DNS_LOOKUP_FAILED');
  } finally {
    if (timer !== undefined) clearTimeout(timer);
    if (aborted) signal.removeEventListener('abort', aborted);
  }
}

function certificateFacts(socket: TLSSocket, address: string): CertificateFacts {
  need(socket.authorized === true && socket.isSessionReused() === false
    && socket.remoteAddress === address && socket.remotePort === 443, 'TLS_PROPERTIES_UNVERIFIED');
  const protocol = socket.getProtocol();
  need(protocol === 'TLSv1.2' || protocol === 'TLSv1.3', 'TLS_PROPERTIES_UNVERIFIED');
  const certificate = socket.getPeerX509Certificate();
  need(certificate !== undefined && certificate !== null, 'CERTIFICATE_UNVERIFIED');
  const raw = certificate.raw;
  const from = certificate.validFromDate;
  const to = certificate.validToDate;
  need(Buffer.isBuffer(raw) && raw.length >= 1 && raw.length <= 64 * 1024
    && from instanceof Date && to instanceof Date, 'CERTIFICATE_UNVERIFIED');
  const notBeforeMs = from.getTime(); const notAfterMs = to.getTime();
  need(Number.isSafeInteger(notBeforeMs) && Number.isSafeInteger(notAfterMs)
    && notBeforeMs >= 0 && notAfterMs > notBeforeMs, 'CERTIFICATE_UNVERIFIED');
  return { protocol, certificateSha256: createHash('sha256').update(raw).digest('hex'),
    notBefore: utc(notBeforeMs), notAfter: utc(notAfterMs), notBeforeMs, notAfterMs };
}

/** Exactly one socket; only its close event proves connectionClosed. */
async function handshake(hostname: string, address: string, signal: AbortSignal, deadline: number): Promise<ConnectionOutcome> {
  return new Promise(resolve => {
    let socket: TLSSocket | undefined;
    let finished = false; let closed = false; let destroyRequested = false; let failure: ErrorCode = 'NONE';
    let facts: CertificateFacts | null = null;
    let connectionTimer: ReturnType<typeof setTimeout> | undefined;
    let closeTimer: ReturnType<typeof setTimeout> | undefined;
    let connectionDeadline = 0;
    let closeDeadline: number | undefined;
    const finish = () => {
      if (finished) return;
      finished = true;
      if (connectionTimer !== undefined) clearTimeout(connectionTimer);
      if (closeTimer !== undefined) clearTimeout(closeTimer);
      signal.removeEventListener('abort', onAbort);
      socket?.off('secureConnect', onSecure); socket?.off('close', onClose);
      // Keep the fixed no-op error sink for late native events after bounded teardown.
      resolve({ error: failure === 'NONE' && facts === null ? 'TLS_UNVERIFIED' : failure,
        closed, facts: failure === 'NONE' && closed ? facts : null });
    };
    const destroy = () => {
      if (destroyRequested) return;
      destroyRequested = true;
      try { socket?.destroy(); } catch { /* No native data is exported. */ }
    };
    const awaitClose = () => {
      if (finished || closeTimer !== undefined) return;
      const now = performance.now();
      const left = deadline - now;
      if (left <= 0) {
        failure = 'WHOLE_TIMEOUT'; facts = null; destroy(); finish(); return;
      }
      closeDeadline = Math.min(deadline, now + CLOSE_MS);
      closeTimer = setTimeout(() => {
        if (failure === 'NONE') failure = performance.now() >= deadline ? 'WHOLE_TIMEOUT' : 'CLOSE_TIMEOUT';
        facts = null; destroy(); finish();
      }, closeDeadline - now);
    };
    const fail = (code: ErrorCode) => {
      if (finished) return;
      if (failure === 'NONE') failure = code;
      facts = null;
      if (connectionTimer !== undefined) clearTimeout(connectionTimer);
      awaitClose(); destroy();
    };
    const onError = () => fail('TLS_UNVERIFIED');
    const onAbort = () => fail('WHOLE_TIMEOUT');
    const onClose = (hadError: boolean) => {
      if (finished) return;
      closed = true;
      if (failure === 'NONE') {
        if (signal.aborted || performance.now() >= deadline) failure = 'WHOLE_TIMEOUT';
        else if (facts !== null && (closeDeadline === undefined || performance.now() >= closeDeadline)) failure = 'CLOSE_TIMEOUT';
        else if (hadError === true) failure = 'TLS_UNVERIFIED';
      }
      finish();
    };
    const onSecure = () => {
      if (finished) return;
      try {
        need(!signal.aborted && performance.now() < deadline, 'WHOLE_TIMEOUT');
        need(performance.now() < connectionDeadline, 'CONNECTION_TIMEOUT');
        facts = certificateFacts(socket!, address);
        need(!signal.aborted && performance.now() < deadline, 'WHOLE_TIMEOUT');
        need(performance.now() < connectionDeadline, 'CONNECTION_TIMEOUT');
        if (connectionTimer !== undefined) clearTimeout(connectionTimer);
        awaitClose();
        if (!finished) socket!.end();
      } catch (error) { fail(error instanceof ProbeError ? error.code : 'CERTIFICATE_UNVERIFIED'); }
    };
    try {
      need(!signal.aborted && performance.now() < deadline, 'WHOLE_TIMEOUT');
      connectionDeadline = performance.now() + CONNECTION_MS;
      socket = connect({ host: hostname, servername: hostname, port: 443, family: 4,
        autoSelectFamily: false, rejectUnauthorized: true, minVersion: 'TLSv1.2',
        session: undefined, enableTrace: false,
        lookup: (_hostname, _options, callback) => callback(null, address, 4) });
      socket.on('secureConnect', onSecure); socket.on('error', onError); socket.on('close', onClose);
      signal.addEventListener('abort', onAbort, { once: true });
      connectionTimer = setTimeout(() => fail('CONNECTION_TIMEOUT'), CONNECTION_MS);
      if (signal.aborted) onAbort();
    } catch (error) {
      failure = error instanceof ProbeError ? error.code : 'TLS_UNVERIFIED';
      facts = null;
      if (socket) { awaitClose(); destroy(); } else finish();
    }
  });
}

export async function runCertificateProbe(environment: NodeJS.ProcessEnv): Promise<CertificateSnapshot> {
  const startedMs = Date.now(); const start = utc(startedMs);
  const result: CertificateSnapshot = {
    schemaVersion: 1, kind: 'tls-certificate-snapshot', scope: 'PUBLIC_TLS_HANDSHAKE_ONLY',
    status: 'FAILED', errorCode: 'UNVERIFIED',
    validatorSourceCommit: typeof environment.GITHUB_SHA === 'string' && SHA.test(environment.GITHUB_SHA) ? environment.GITHUB_SHA : null,
    captureStartedAt: start, capturedAt: start, publicIpv4Verified: false, standardTlsVerified: false,
    connectionClosed: false, protocol: null, targetBindingSha256: null, certificateSha256: null,
    notBefore: null, notAfter: null, remainingValiditySeconds: null, remainingFullDays: null,
    warningThresholdDays: 30, expiryAssessment: 'UNKNOWN', naturalRenewalVerified: false,
    operatingConfigurationChanged: false,
  };
  const deadline = performance.now() + WHOLE_MS;
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), WHOLE_MS);
  let facts: CertificateFacts | null = null;
  try {
    need(environment.GITHUB_REPOSITORY === 'DevDooly/devdooly-platform-lab'
      && environment.GITHUB_EVENT_NAME === 'workflow_dispatch' && environment.GITHUB_REF === 'refs/heads/main'
      && environment.GITHUB_RUN_ATTEMPT === '1' && result.validatorSourceCommit !== null
      && environment.TLS_CERTIFICATE_CONFIRM === 'true' && environment.TLS_CERTIFICATE_TARGET_OWNERSHIP === 'true'
      && environment.TLS_CERTIFICATE_VARIABLE_MATCH === 'true', 'CONFIGURATION_NOT_VERIFIED');
    need(FORBIDDEN_ENV.every(name => environment[name] === undefined), 'ENVIRONMENT_NOT_VERIFIED');
    const configuration = publicApiConfiguration(environment.LAB_PUBLIC_API_URL);
    need(configuration.externalHttps && !configuration.invalid, 'CONFIGURATION_NOT_VERIFIED');
    const hostname = new URL(configuration.apiBase).hostname;
    result.targetBindingSha256 = createHash('sha256').update(`https://${hostname}:443`, 'utf8').digest('hex');
    const address = await publicAddress(hostname, controller.signal);
    result.publicIpv4Verified = true;
    const outcome = await handshake(hostname, address, controller.signal, deadline);
    result.connectionClosed = outcome.closed;
    need(outcome.error === 'NONE' && outcome.facts !== null, outcome.error === 'NONE' ? 'TLS_UNVERIFIED' : outcome.error);
    facts = outcome.facts;
  } catch (error) { result.errorCode = errorCode(error); }
  finally { clearTimeout(timer); }
  // Completion time belongs to the observed close/result, not handshake start or a future validation ceiling.
  try {
    const completedMs = Date.now(); result.capturedAt = utc(completedMs);
    need(completedMs >= startedMs, 'CLOCK_UNVERIFIED');
    need(!controller.signal.aborted && performance.now() < deadline, 'WHOLE_TIMEOUT');
    if (facts !== null) {
      need(facts.notBeforeMs <= completedMs && completedMs < facts.notAfterMs, 'CERTIFICATE_VALIDITY_UNVERIFIED');
      const seconds = Math.floor((facts.notAfterMs - completedMs) / 1000);
      need(Number.isSafeInteger(seconds) && seconds >= 0, 'CERTIFICATE_VALIDITY_UNVERIFIED');
      Object.assign(result, { protocol: facts.protocol, certificateSha256: facts.certificateSha256,
        notBefore: facts.notBefore, notAfter: facts.notAfter, remainingValiditySeconds: seconds,
        remainingFullDays: Math.floor(seconds / DAY_SECONDS), standardTlsVerified: true,
        expiryAssessment: seconds <= WARNING_DAYS * DAY_SECONDS ? 'EXPIRING_WITHIN_30_DAYS' : 'VALID_OVER_30_DAYS',
        status: 'PASS', errorCode: 'NONE' });
    }
    need(performance.now() < deadline, 'WHOLE_TIMEOUT');
  } catch (error) {
    result.status = 'FAILED'; result.errorCode = errorCode(error); result.standardTlsVerified = false;
    result.protocol = null; result.certificateSha256 = null; result.notBefore = null; result.notAfter = null;
    result.remainingValiditySeconds = null; result.remainingFullDays = null; result.expiryAssessment = 'UNKNOWN';
  }
  return result;
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  const consoleResult = (status: 'PASS' | 'FAILED', code: ErrorCode) =>
    process.stdout.write(JSON.stringify({ status, errorCode: code }) + '\n');
  let output: number;
  try { need(process.argv.length === 3, 'OUTPUT_UNAVAILABLE'); output = openSync(process.argv[2], 'wx', 0o600); }
  catch { consoleResult('FAILED', 'OUTPUT_UNAVAILABLE'); process.exit(1); }
  let status: 'PASS' | 'FAILED' = 'FAILED'; let code: ErrorCode = 'UNVERIFIED';
  try {
    const result = await runCertificateProbe(process.env);
    const text = JSON.stringify(result, null, 2) + '\n';
    need(Buffer.byteLength(text, 'utf8') <= 4096, 'OUTPUT_UNAVAILABLE');
    writeFileSync(output, text); status = result.status; code = result.errorCode;
  } catch { code = 'OUTPUT_UNAVAILABLE'; }
  finally { try { closeSync(output); } catch { status = 'FAILED'; code = 'OUTPUT_UNAVAILABLE'; } }
  consoleResult(status, code);
  // A DNS operation still outstanding after its finite race cannot keep this one-shot CLI alive.
  process.exit(status === 'PASS' ? 0 : 1);
}
