/** One manual GET-only observation. Raw configuration, bodies and errors stay in RAM. */
import { openSync, closeSync, writeFileSync } from 'node:fs';
import { setTimeout as sleep } from 'node:timers/promises';
import { pathToFileURL } from 'node:url';
import { publicApiConfiguration, publicReadUrl } from '../../apps/lab-web/src/lib/public-api-base.ts';
import { validateJobObservation } from '../../apps/lab-web/src/lib/job-observation.ts';
import { kafkaUtcNs, parseKafkaObservation } from '../../apps/lab-web/src/lib/kafka-observation.ts';
import { PUBLIC_GET_ROUTES, selectPublicIpv4, oneRequest, validateLab, SmokeError } from '../public-https-smoke/smoke.ts';

const SHA = /^[a-f0-9]{40}$/;
const ORIGIN = 'https://devdooly.github.io';
const DNS_MS = 5000;
const REQUEST_MS = 15_000;
const WHOLE_MS = 150_000;
const FORBIDDEN_ENV = ['NODE_OPTIONS', 'NODE_EXTRA_CA_CERTS', 'NODE_TLS_REJECT_UNAUTHORIZED', 'NODE_USE_SYSTEM_CA',
  'NODE_DEBUG', 'NODE_DEBUG_NATIVE', 'SSL_CERT_FILE', 'SSL_CERT_DIR', 'SSLKEYLOGFILE',
  'HTTP_PROXY', 'HTTPS_PROXY', 'ALL_PROXY', 'NO_PROXY',
  'http_proxy', 'https_proxy', 'all_proxy', 'no_proxy', 'NODE_USE_ENV_PROXY'] as const;
const ERRORS = ['NONE', 'CONFIGURATION_NOT_VERIFIED', 'ENVIRONMENT_NOT_VERIFIED', 'DNS_LOOKUP_FAILED',
  'DNS_ADDRESS_REJECTED', 'DNS_NO_SUPPORTED_PUBLIC_IPV4', 'DNS_TIMEOUT', 'REQUEST_TIMEOUT',
  'WHOLE_TIMEOUT', 'TLS_OR_NETWORK_UNVERIFIED', 'HTTP_STATUS_UNVERIFIED', 'HEADERS_UNVERIFIED',
  'RESPONSE_TOO_LARGE', 'INVALID_DTO', 'CLOCK_UNVERIFIED', 'OUTPUT_UNAVAILABLE', 'UNVERIFIED'] as const;
type ErrorCode = typeof ERRORS[number];
type CheckId = typeof PUBLIC_GET_ROUTES[number][0];
type Check = { passed: boolean; status: number | null; sourceCommit: string | null; observedAt: string | null };
export type PublicGetSnapshot = {
  schemaVersion: 1; kind: 'public-https-get-snapshot'; scope: 'PUBLIC_HTTPS_GET_CONTRACTS_ONLY';
  status: 'PASS' | 'FAILED'; errorCode: ErrorCode; validatorSourceCommit: string | null;
  captureStartedAt: string; capturedAt: string; targetOwnershipAcknowledged: boolean;
  publicIpv4Verified: boolean; standardTlsVerified: boolean;
  deniedRequestsTested: false; operatingConfigurationChanged: false; checks: Record<CheckId, Check>;
};
function need(value: unknown, code: ErrorCode): asserts value {
  if (!value) throw new SmokeError(code);
}
function json(raw: Buffer): unknown {
  try { return JSON.parse(new TextDecoder('utf-8', { fatal: true, ignoreBOM: true }).decode(raw)); }
  catch { throw new SmokeError('INVALID_DTO'); }
}

export async function runPublicGetProbe(environment: NodeJS.ProcessEnv): Promise<PublicGetSnapshot> {
  const startedMs = Date.now();
  const result: PublicGetSnapshot = {
    schemaVersion: 1, kind: 'public-https-get-snapshot', scope: 'PUBLIC_HTTPS_GET_CONTRACTS_ONLY',
    status: 'FAILED', errorCode: 'UNVERIFIED',
    validatorSourceCommit: typeof environment.GITHUB_SHA === 'string' && SHA.test(environment.GITHUB_SHA) ? environment.GITHUB_SHA : null,
    captureStartedAt: new Date(startedMs).toISOString(), capturedAt: new Date(startedMs).toISOString(),
    targetOwnershipAcknowledged: false, publicIpv4Verified: false, standardTlsVerified: false,
    deniedRequestsTested: false, operatingConfigurationChanged: false,
    checks: Object.fromEntries(PUBLIC_GET_ROUTES.map(([id]) => [id,
      { passed: false, status: null, sourceCommit: null, observedAt: null }])) as Record<CheckId, Check>,
  };
  const deadline = performance.now() + WHOLE_MS;
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), WHOLE_MS);
  const withinWhole = () => need(!controller.signal.aborted && performance.now() < deadline, 'WHOLE_TIMEOUT');
  try {
    need(environment.GITHUB_REPOSITORY === 'DevDooly/devdooly-platform-lab'
      && environment.GITHUB_EVENT_NAME === 'workflow_dispatch' && environment.GITHUB_REF === 'refs/heads/main'
      && environment.GITHUB_RUN_ATTEMPT === '1' && result.validatorSourceCommit !== null
      && environment.PUBLIC_GET_CONFIRM === 'true' && environment.PUBLIC_GET_TARGET_OWNERSHIP === 'true'
      && environment.PUBLIC_GET_VARIABLE_MATCH === 'true', 'CONFIGURATION_NOT_VERIFIED');
    need(FORBIDDEN_ENV.every(name => environment[name] === undefined), 'ENVIRONMENT_NOT_VERIFIED');
    const configuration = publicApiConfiguration(environment.LAB_PUBLIC_API_URL);
    need(configuration.externalHttps && !configuration.invalid, 'CONFIGURATION_NOT_VERIFIED');
    result.targetOwnershipAcknowledged = true;
    withinWhole();
    const dnsDeadline = performance.now() + DNS_MS;
    const address = await selectPublicIpv4(new URL(configuration.apiBase).hostname);
    withinWhole(); need(performance.now() < dnsDeadline, 'DNS_TIMEOUT');
    result.publicIpv4Verified = true;
    const budget = { bytes: 0 };
    const payloads: unknown[] = [];
    for (const [index, [id, path, cap]] of PUBLIC_GET_ROUTES.entries()) {
      if (index > 0) { await sleep(1100, undefined, { signal: controller.signal }); withinWhole(); }
      withinWhole();
      const target = publicReadUrl(configuration.apiBase, path);
      need(target !== null, 'CONFIGURATION_NOT_VERIFIED');
      const requestDeadline = performance.now() + REQUEST_MS;
      // No method, route, origin or request-body option is accepted from input.
      const reply = await oneRequest(new URL(target), address, 'GET', ORIGIN, cap, budget,
        controller.signal, status => { result.checks[id].status = status; });
      withinWhole(); need(performance.now() < requestDeadline, 'REQUEST_TIMEOUT');
      result.standardTlsVerified = true;
      need(reply.status === 200, 'HTTP_STATUS_UNVERIFIED');
      if (index < 4) {
        payloads.push(json(reply.raw));
        if (index === 3) {
          const validated = validateLab(payloads);
          for (const [labIndex, [labId]] of PUBLIC_GET_ROUTES.slice(0, 4).entries()) {
            Object.assign(result.checks[labId], { passed: true, sourceCommit: validated.sourceCommit,
              observedAt: validated.observedTimes[labIndex] });
          }
        }
      } else if (id === 'JOBS') {
        const value = json(reply.raw);
        need(validateJobObservation(value) && value.environment === 'MINI_PC' && value.scope === 'DEPLOYED_RUNTIME'
          && SHA.test(value.sourceCommit), 'INVALID_DTO');
        const captured = kafkaUtcNs(value.capturedAt);
        need(captured !== null && captured <= BigInt(Date.now() + 5000) * 1_000_000n, 'INVALID_DTO');
        Object.assign(result.checks[id], { passed: true, sourceCommit: value.sourceCommit, observedAt: value.capturedAt });
      } else {
        const value = parseKafkaObservation(new TextDecoder('utf-8', { fatal: true, ignoreBOM: true }).decode(reply.raw), Date.now() + 5000);
        need(value && value.environment === 'MINI_PC' && value.scope === 'DEPLOYED_KAFKA', 'INVALID_DTO');
        Object.assign(result.checks[id], { passed: true, sourceCommit: value.sourceCommit, observedAt: value.capturedAt });
      }
      withinWhole();
    }
    withinWhole(); result.status = 'PASS'; result.errorCode = 'NONE';
  } catch (error) {
    result.errorCode = controller.signal.aborted ? 'WHOLE_TIMEOUT'
      : error instanceof SmokeError && (ERRORS as readonly string[]).includes(error.code) ? error.code as ErrorCode : 'UNVERIFIED';
  } finally { clearTimeout(timer); }
  const completedMs = Date.now();
  result.capturedAt = new Date(completedMs).toISOString();
  if (!Number.isSafeInteger(startedMs) || !Number.isSafeInteger(completedMs) || startedMs < 0 || completedMs < startedMs) {
    result.status = 'FAILED'; result.errorCode = 'CLOCK_UNVERIFIED';
  } else if (controller.signal.aborted || performance.now() >= deadline) {
    result.status = 'FAILED'; result.errorCode = 'WHOLE_TIMEOUT';
  }
  return result;
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  const consoleResult = (status: 'PASS' | 'FAILED', errorCode: ErrorCode) =>
    process.stdout.write(JSON.stringify({ status, errorCode }) + '\n');
  let output: number;
  try { need(process.argv.length === 3, 'OUTPUT_UNAVAILABLE'); output = openSync(process.argv[2], 'wx', 0o600); }
  catch { consoleResult('FAILED', 'OUTPUT_UNAVAILABLE'); process.exit(1); }
  let status: 'PASS' | 'FAILED' = 'FAILED'; let code: ErrorCode = 'UNVERIFIED';
  try {
    const result = await runPublicGetProbe(process.env);
    const text = JSON.stringify(result, null, 2) + '\n';
    need(Buffer.byteLength(text, 'utf8') <= 4096, 'OUTPUT_UNAVAILABLE');
    writeFileSync(output, text); status = result.status; code = result.errorCode;
  } catch { code = 'OUTPUT_UNAVAILABLE'; }
  finally { try { closeSync(output); } catch { status = 'FAILED'; code = 'OUTPUT_UNAVAILABLE'; } }
  consoleResult(status, code);
  // An unfinished native DNS lookup cannot extend this one-shot command.
  process.exit(status === 'PASS' ? 0 : 1);
}
