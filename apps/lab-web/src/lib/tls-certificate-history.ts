/** Build-time stored TLS observations only. No clock reads, filesystem or network operations. */
import { createHash } from 'node:crypto';

export const TLS_SNAPSHOT_ERROR_CODES = ['NONE', 'CONFIGURATION_NOT_VERIFIED', 'ENVIRONMENT_NOT_VERIFIED',
  'DNS_LOOKUP_FAILED', 'DNS_ADDRESS_REJECTED', 'DNS_NO_SUPPORTED_PUBLIC_IPV4', 'DNS_TIMEOUT',
  'CONNECTION_TIMEOUT', 'WHOLE_TIMEOUT', 'TLS_UNVERIFIED', 'TLS_PROPERTIES_UNVERIFIED',
  'CERTIFICATE_UNVERIFIED', 'CERTIFICATE_VALIDITY_UNVERIFIED', 'CLOCK_UNVERIFIED',
  'CLOSE_TIMEOUT', 'OUTPUT_UNAVAILABLE', 'UNVERIFIED'] as const;
export type TlsSnapshotErrorCode = typeof TLS_SNAPSHOT_ERROR_CODES[number];
interface TlsSnapshotCommon {
  readonly schemaVersion: 1;
  readonly kind: 'tls-certificate-snapshot';
  readonly scope: 'PUBLIC_TLS_HANDSHAKE_ONLY';
  readonly validatorSourceCommit: string;
  readonly captureStartedAt: string;
  readonly capturedAt: string;
  readonly publicIpv4Verified: boolean;
  readonly connectionClosed: boolean;
  readonly targetBindingSha256: string | null;
  readonly warningThresholdDays: 30;
  readonly naturalRenewalVerified: false;
  readonly operatingConfigurationChanged: false;
}
export interface TlsPassSnapshot extends TlsSnapshotCommon {
  readonly status: 'PASS'; readonly errorCode: 'NONE'; readonly standardTlsVerified: true;
  readonly publicIpv4Verified: true; readonly connectionClosed: true;
  readonly targetBindingSha256: string; readonly protocol: 'TLSv1.2' | 'TLSv1.3';
  readonly certificateSha256: string; readonly notBefore: string; readonly notAfter: string;
  readonly remainingValiditySeconds: number; readonly remainingFullDays: number;
  readonly expiryAssessment: 'VALID_OVER_30_DAYS' | 'EXPIRING_WITHIN_30_DAYS';
}
export interface TlsFailedSnapshot extends TlsSnapshotCommon {
  readonly status: 'FAILED'; readonly errorCode: Exclude<TlsSnapshotErrorCode, 'NONE'>;
  readonly standardTlsVerified: false; readonly protocol: null; readonly certificateSha256: null;
  readonly notBefore: null; readonly notAfter: null; readonly remainingValiditySeconds: null;
  readonly remainingFullDays: null; readonly expiryAssessment: 'UNKNOWN';
}
export type TlsSnapshot = TlsPassSnapshot | TlsFailedSnapshot;
export interface TlsHistoryEntry { readonly summaryText: string; readonly metadata: unknown; }
export interface TlsTrustedBinding { readonly runUrl: string; readonly sourceCommit: string; readonly artifactSha256: string; }
export interface TlsHistoryRecord extends TlsTrustedBinding {
  readonly completedAt: string;
  readonly summary: TlsSnapshot;
}
export interface TlsVerifiedRecord extends TlsHistoryRecord { readonly summary: TlsPassSnapshot; }
export type TlsComparisonKind = 'NO_VERIFIED_RECORD' | 'FIRST_VERIFIED' | 'UNCHANGED_CERTIFICATE'
  | 'CERTIFICATE_CHANGED_EXTENDED' | 'CERTIFICATE_CHANGED_SAME_EXPIRY' | 'CERTIFICATE_CHANGED_EARLIER_EXPIRY';
export type TlsHistoryIssue = 'NONE' | 'LATEST_ATTEMPT_FAILED' | 'QUARANTINED_INPUT'
  | 'NO_VERIFIED_RECORD' | 'INVALID_CONFIGURATION';
export interface TlsHistoryView {
  readonly records: readonly TlsHistoryRecord[];
  readonly lastAttempt: TlsHistoryRecord | null;
  readonly lastSuccess: TlsVerifiedRecord | null;
  readonly comparison: {
    readonly kind: TlsComparisonKind;
    readonly previous: TlsVerifiedRecord | null;
    readonly current: TlsVerifiedRecord | null;
  };
  readonly visibleIssue: TlsHistoryIssue;
  readonly quarantinedCount: number;
}

const SUMMARY_KEYS = ['schemaVersion', 'kind', 'scope', 'status', 'errorCode', 'validatorSourceCommit',
  'captureStartedAt', 'capturedAt', 'publicIpv4Verified', 'standardTlsVerified', 'connectionClosed', 'protocol',
  'targetBindingSha256', 'certificateSha256', 'notBefore', 'notAfter', 'remainingValiditySeconds',
  'remainingFullDays', 'warningThresholdDays', 'expiryAssessment', 'naturalRenewalVerified', 'operatingConfigurationChanged'] as const;
const METADATA_KEYS = ['runUrl', 'sourceCommit', 'completedAt', 'runConclusion', 'trialConclusion', 'artifactSha256'] as const;
const BINDING_KEYS = ['runUrl', 'sourceCommit', 'artifactSha256'] as const;
const SHA40 = /^[a-f0-9]{40}$/;
const SHA64 = /^[a-f0-9]{64}$/;
const RUN_URL = /^https:\/\/github\.com\/DevDooly\/devdooly-platform-lab\/actions\/runs\/[1-9]\d{0,19}$/;
const DAY_SECONDS = 86_400;

/** Serialized data only: reject accessors and extra/symbol keys before reading selected fields. */
function exactObject(value: unknown, fields: readonly string[]): value is Record<string, unknown> {
  if (typeof value !== 'object' || value === null || Array.isArray(value)) return false;
  const prototype = Object.getPrototypeOf(value);
  if (prototype !== Object.prototype && prototype !== null) return false;
  const keys = Reflect.ownKeys(value);
  return keys.length === fields.length && fields.every(key => {
    const descriptor = Object.getOwnPropertyDescriptor(value, key);
    return descriptor !== undefined && descriptor.enumerable === true && Object.hasOwn(descriptor, 'value');
  });
}

/** Flat primitive JSON: decoded duplicate keys and fractional/exponent integer spellings are rejected. */
function flatSummary(text: unknown): Record<string, unknown> | null {
  if (typeof text !== 'string' || Buffer.byteLength(text, 'utf8') > 4096) return null;
  let cursor = 0;
  const whitespace = () => { while (cursor < text.length && /[\t\r\n ]/.test(text[cursor])) cursor++; };
  const string = (): string => {
    if (text[cursor] !== '"') throw new Error('INVALID_TLS_RECORD');
    const start = cursor++;
    while (cursor < text.length) {
      if (text[cursor] === '\\') { cursor += 2; continue; }
      if (text[cursor++] === '"') return JSON.parse(text.slice(start, cursor)) as string;
    }
    throw new Error('INVALID_TLS_RECORD');
  };
  const primitive = (): unknown => {
    if (text[cursor] === '"') return string();
    for (const [token, value] of [['true', true], ['false', false], ['null', null]] as const) {
      if (text.startsWith(token, cursor)) { cursor += token.length; return value; }
    }
    const match = /^-?(?:0|[1-9]\d*)/.exec(text.slice(cursor));
    if (!match) throw new Error('INVALID_TLS_RECORD');
    cursor += match[0].length;
    const number = Number(match[0]);
    if (!Number.isSafeInteger(number) || Object.is(number, -0)) throw new Error('INVALID_TLS_RECORD');
    return number;
  };
  try {
    whitespace(); if (text[cursor++] !== '{') return null;
    const result: Record<string, unknown> = Object.create(null);
    whitespace();
    if (text[cursor] === '}') { cursor++; whitespace(); return cursor === text.length ? result : null; }
    while (cursor < text.length) {
      const key = string(); if (Object.hasOwn(result, key)) return null;
      whitespace(); if (text[cursor++] !== ':') return null;
      whitespace(); result[key] = primitive(); whitespace();
      const separator = text[cursor++];
      if (separator === '}') { whitespace(); return cursor === text.length ? result : null; }
      if (separator !== ',') return null;
      whitespace();
    }
  } catch { return null; }
  return null;
}
function utcMs(value: unknown, metadata = false): number | null {
  if (typeof value !== 'string' || !(metadata
    ? /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{3})?Z$/
    : /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z$/).test(value)) return null;
  const milliseconds = Date.parse(value);
  if (!Number.isSafeInteger(milliseconds) || milliseconds < 0) return null;
  const canonical = value.includes('.') ? value : value.replace('Z', '.000Z');
  return new Date(milliseconds).toISOString() === canonical ? milliseconds : null;
}
function sha(value: unknown, pattern: RegExp): value is string { return typeof value === 'string' && pattern.test(value); }
function binding(value: unknown): value is TlsTrustedBinding {
  return exactObject(value, BINDING_KEYS) && typeof value.runUrl === 'string' && RUN_URL.test(value.runUrl)
    && sha(value.sourceCommit, SHA40) && sha(value.artifactSha256, SHA64);
}
function snapshot(text: string, nowMs: number): TlsSnapshot | null {
  const value = flatSummary(text);
  if (!exactObject(value, SUMMARY_KEYS) || value.schemaVersion !== 1 || value.kind !== 'tls-certificate-snapshot'
    || value.scope !== 'PUBLIC_TLS_HANDSHAKE_ONLY' || !sha(value.validatorSourceCommit, SHA40)
    || value.warningThresholdDays !== 30 || value.naturalRenewalVerified !== false || value.operatingConfigurationChanged !== false
    || typeof value.publicIpv4Verified !== 'boolean' || typeof value.connectionClosed !== 'boolean'
    || !(value.targetBindingSha256 === null || sha(value.targetBindingSha256, SHA64))) return null;
  const start = utcMs(value.captureStartedAt); const end = utcMs(value.capturedAt);
  if (start === null || end === null || start > end || end > nowMs) return null;
  if (value.publicIpv4Verified && value.targetBindingSha256 === null) return null;
  if (value.status === 'PASS') {
    const before = utcMs(value.notBefore); const after = utcMs(value.notAfter);
    if (value.errorCode !== 'NONE' || value.publicIpv4Verified !== true || value.standardTlsVerified !== true
      || value.connectionClosed !== true || !sha(value.targetBindingSha256, SHA64) || !sha(value.certificateSha256, SHA64)
      || !(value.protocol === 'TLSv1.2' || value.protocol === 'TLSv1.3')
      || before === null || after === null || before > end || end >= after || before >= after) return null;
    const seconds = Math.floor((after - end) / 1000);
    if (value.remainingValiditySeconds !== seconds || value.remainingFullDays !== Math.floor(seconds / DAY_SECONDS)
      || value.expiryAssessment !== (seconds <= 30 * DAY_SECONDS ? 'EXPIRING_WITHIN_30_DAYS' : 'VALID_OVER_30_DAYS')) return null;
  } else if (value.status === 'FAILED') {
    if (typeof value.errorCode !== 'string' || value.errorCode === 'NONE'
      || !(TLS_SNAPSHOT_ERROR_CODES as readonly string[]).includes(value.errorCode)
      || value.standardTlsVerified !== false || value.protocol !== null || value.certificateSha256 !== null
      || value.notBefore !== null || value.notAfter !== null || value.remainingValiditySeconds !== null
      || value.remainingFullDays !== null || value.expiryAssessment !== 'UNKNOWN') return null;
  } else return null;
  return Object.freeze({ ...value }) as unknown as TlsSnapshot;
}
function record(entry: unknown, approved: ReadonlyMap<string, TlsTrustedBinding>, nowMs: number): TlsHistoryRecord | null {
  if (!exactObject(entry, ['summaryText', 'metadata']) || typeof entry.summaryText !== 'string'
    || Buffer.byteLength(entry.summaryText, 'utf8') > 4096
    || !exactObject(entry.metadata, METADATA_KEYS)) return null;
  const metadata = entry.metadata;
  if (typeof metadata.runUrl !== 'string' || !RUN_URL.test(metadata.runUrl)
    || !sha(metadata.sourceCommit, SHA40) || !sha(metadata.artifactSha256, SHA64)) return null;
  const trusted = approved.get(metadata.runUrl);
  if (!trusted || trusted.sourceCommit !== metadata.sourceCommit || trusted.artifactSha256 !== metadata.artifactSha256
    || createHash('sha256').update(entry.summaryText, 'utf8').digest('hex') !== trusted.artifactSha256) return null;
  const summary = snapshot(entry.summaryText, nowMs);
  const completed = utcMs(metadata.completedAt, true);
  if (!summary || summary.validatorSourceCommit !== metadata.sourceCommit || completed === null
    || completed < utcMs(summary.capturedAt)! || completed > nowMs) return null;
  const conclusion = summary.status === 'PASS' ? 'success' : 'failure';
  if (metadata.runConclusion !== conclusion || metadata.trialConclusion !== conclusion) return null;
  return Object.freeze({ runUrl: metadata.runUrl, sourceCommit: metadata.sourceCommit,
    artifactSha256: metadata.artifactSha256, completedAt: metadata.completedAt as string, summary });
}
function comparison(successes: readonly TlsVerifiedRecord[]): TlsHistoryView['comparison'] {
  const current = successes.at(-1) ?? null; const previous = successes.at(-2) ?? null;
  let kind: TlsComparisonKind = current === null ? 'NO_VERIFIED_RECORD' : 'FIRST_VERIFIED';
  if (current && previous) {
    if (current.summary.certificateSha256 === previous.summary.certificateSha256) kind = 'UNCHANGED_CERTIFICATE';
    else {
      const difference = utcMs(current.summary.notAfter)! - utcMs(previous.summary.notAfter)!;
      kind = difference > 0 ? 'CERTIFICATE_CHANGED_EXTENDED'
        : difference === 0 ? 'CERTIFICATE_CHANGED_SAME_EXPIRY' : 'CERTIFICATE_CHANGED_EARLIER_EXPIRY';
    }
  }
  return Object.freeze({ kind, previous, current });
}
function view(records: readonly TlsHistoryRecord[], successes: readonly TlsVerifiedRecord[], quarantinedCount: number,
  configurationInvalid = false): TlsHistoryView {
  const lastAttempt = records.at(-1) ?? null; const lastSuccess = successes.at(-1) ?? null;
  const visibleIssue: TlsHistoryIssue = configurationInvalid ? 'INVALID_CONFIGURATION'
    : quarantinedCount > 0 ? 'QUARANTINED_INPUT' : lastAttempt?.summary.status === 'FAILED' ? 'LATEST_ATTEMPT_FAILED'
    : lastSuccess === null ? 'NO_VERIFIED_RECORD' : 'NONE';
  return Object.freeze({ records: Object.freeze([...records]), lastAttempt, lastSuccess,
    comparison: comparison(successes), visibleIssue, quarantinedCount });
}

/** Reviewed raw artifacts only; a later failed/unverified input never rewrites the last accepted PASS. */
export function buildTlsHistory(entries: readonly TlsHistoryEntry[], trusted: readonly TlsTrustedBinding[], nowMs: number): TlsHistoryView {
  if (!Array.isArray(entries) || !Array.isArray(trusted) || !Number.isSafeInteger(nowMs) || nowMs < 0 || Object.is(nowMs, -0))
    return view([], [], 0, true);
  const approved = new Map<string, TlsTrustedBinding>();
  try {
    for (const item of trusted) {
      if (!binding(item)) return view([], [], 0, true);
      const prior = approved.get(item.runUrl);
      if (prior && (prior.sourceCommit !== item.sourceCommit || prior.artifactSha256 !== item.artifactSha256)) return view([], [], 0, true);
      approved.set(item.runUrl, Object.freeze({ runUrl: item.runUrl, sourceCommit: item.sourceCommit, artifactSha256: item.artifactSha256 }));
    }
  } catch { return view([], [], 0, true); }
  const records: TlsHistoryRecord[] = []; const successes: TlsVerifiedRecord[] = [];
  const seenRuns = new Map<string, TlsHistoryRecord>();
  const certificatePeriods = new Map<string, string>();
  let target: string | null = null; let quarantined = 0;
  for (const entry of entries) {
    try {
      const candidate = record(entry, approved, nowMs);
      if (!candidate || candidate.summary.targetBindingSha256 === null) { quarantined++; continue; }
      const duplicate = seenRuns.get(candidate.runUrl);
      if (duplicate) {
        if (duplicate.sourceCommit !== candidate.sourceCommit || duplicate.artifactSha256 !== candidate.artifactSha256
          || utcMs(duplicate.completedAt, true) !== utcMs(candidate.completedAt, true)) quarantined++;
        continue;
      }
      if ((target !== null && candidate.summary.targetBindingSha256 !== target)
        || (records.length > 0 && utcMs(candidate.summary.capturedAt)! <= utcMs(records.at(-1)!.summary.capturedAt)!)) { quarantined++; continue; }
      if (candidate.summary.status === 'PASS') {
        const period = `${candidate.summary.notBefore}/${candidate.summary.notAfter}`;
        const prior = certificatePeriods.get(candidate.summary.certificateSha256);
        if (prior !== undefined && prior !== period) { quarantined++; continue; }
        certificatePeriods.set(candidate.summary.certificateSha256, period);
        successes.push(candidate as TlsVerifiedRecord);
      }
      target ??= candidate.summary.targetBindingSha256;
      records.push(candidate); seenRuns.set(candidate.runUrl, candidate);
    } catch { quarantined++; }
  }
  return view(records, successes, quarantined);
}
