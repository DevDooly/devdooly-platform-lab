/** Kafka public v1: bounded source reader before parsing, no private identities or controls. */
export const MAX_KAFKA_OBSERVATION_BYTES = 8 * 1024;
export const KAFKA_STALE_AFTER_MS = 2 * 60 * 60 * 1000;
export const KAFKA_ERROR_CODES = ['NOT_CONFIGURED', 'INVALID_CONFIGURATION', 'CAPTURE_BUSY', 'OBSERVER_POISONED',
  'CAPTURE_TIMEOUT', 'KAFKA_UNAVAILABLE', 'TARGET_UNVERIFIED', 'GROUP_UNAVAILABLE', 'GROUP_UNSTABLE',
  'OFFSETS_UNVERIFIED', 'CLOCK_UNVERIFIED', 'CLOSE_UNVERIFIED'] as const;
export type KafkaErrorCode = typeof KAFKA_ERROR_CODES[number];
export type KafkaBrowserError = KafkaErrorCode | 'HTTP_ERROR' | 'NETWORK_ERROR' | 'INVALID_RECORD' | 'ABORTED'
  | 'OLDER_RECORD' | 'TARGET_CHANGED' | 'CONFLICTING_RECORD' | 'ENVIRONMENT_MISMATCH' | 'INVALID_URL';
export interface KafkaObservation {
  schemaVersion: 1; kind: 'kafka-observation'; synthetic: true;
  environment: 'ISOLATED_LAB' | 'MINI_PC'; scope: 'ISOLATED_KAFKA' | 'DEPLOYED_KAFKA'; publicExecutionEnabled: false;
  sourceCommit: string; captureStartedAt: string; capturedAt: string; consistency: 'BOUNDED_SEQUENTIAL_READ';
  targetFingerprint: string; groupState: 'STABLE' | 'EMPTY'; partition: 0;
  commitState: 'OBSERVED' | 'NO_COMMIT'; logStartOffset: number; readCommittedEndOffset: number;
  committedOffset: number | null; lag: number | null;
}
const keys = ['schemaVersion', 'kind', 'synthetic', 'environment', 'scope', 'publicExecutionEnabled', 'sourceCommit',
  'captureStartedAt', 'capturedAt', 'consistency', 'targetFingerprint', 'groupState', 'partition', 'commitState',
  'logStartOffset', 'readCommittedEndOffset', 'committedOffset', 'lag'] as const;
const object = (value: unknown): value is Record<string, unknown> => typeof value === 'object' && value !== null && !Array.isArray(value);
const exact = (value: Record<string, unknown>, fields: readonly string[]) => Object.keys(value).length === fields.length && fields.every(key => Object.hasOwn(value, key));
const offset = (value: unknown): value is number => typeof value === 'number' && Number.isSafeInteger(value) && value >= 0;

/** The contract is flat. Decode each JSON string token, and reject decoded duplicate keys before losing them. */
function strictFlatObject(text: unknown): Record<string, unknown> | null {
  if (typeof text !== 'string' || new TextEncoder().encode(text).byteLength > MAX_KAFKA_OBSERVATION_BYTES) return null;
  let cursor = 0;
  const whitespace = () => { while (cursor < text.length && /[\t\r\n ]/.test(text[cursor])) cursor++; };
  const string = (): string => {
    if (text[cursor] !== '"') throw new Error('INVALID_RECORD');
    const start = cursor++;
    while (cursor < text.length) {
      if (text[cursor] === '\\') { cursor += 2; continue; }
      if (text[cursor++] === '"') return JSON.parse(text.slice(start, cursor)) as string;
    }
    throw new Error('INVALID_RECORD');
  };
  const primitive = (): unknown => {
    if (text[cursor] === '"') return string();
    for (const [token, value] of [['true', true], ['false', false], ['null', null]] as const) {
      if (text.startsWith(token, cursor)) { cursor += token.length; return value; }
    }
    // Every numeric field is an integer. Reject decimal/exponent lexemes before floating-point rounding can hide a fraction.
    const match = /^-?(?:0|[1-9]\d*)/.exec(text.slice(cursor));
    if (!match) throw new Error('INVALID_RECORD');
    cursor += match[0].length;
    const value = Number(match[0]);
    if (!Number.isSafeInteger(value) || Object.is(value, -0)) throw new Error('INVALID_RECORD');
    return value;
  };
  try {
    whitespace(); if (text[cursor++] !== '{') return null;
    const result: Record<string, unknown> = Object.create(null);
    whitespace(); if (text[cursor] === '}') { cursor++; whitespace(); return cursor === text.length ? result : null; }
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

/** Real UTC dates, exactly zero through nine fraction digits, compared without millisecond truncation. */
export function kafkaUtcNs(value: unknown): bigint | null {
  if (typeof value !== 'string') return null;
  const match = /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2}):(\d{2})(?:\.(\d{1,9}))?Z$/.exec(value);
  if (!match) return null;
  const [year, month, day, hour, minute, second] = match.slice(1, 7).map(Number);
  if (year < 1) return null;
  const date = new Date(0); date.setUTCFullYear(year, month - 1, day); date.setUTCHours(hour, minute, second, 0);
  if (date.getUTCFullYear() !== year || date.getUTCMonth() !== month - 1 || date.getUTCDate() !== day
    || date.getUTCHours() !== hour || date.getUTCMinutes() !== minute || date.getUTCSeconds() !== second) return null;
  return BigInt(date.getTime()) * 1_000_000n + BigInt((match[7] || '').padEnd(9, '0'));
}
export function validateKafkaObservation(value: unknown, nowMs = Date.now()): value is KafkaObservation {
  if (!Number.isSafeInteger(nowMs) || !object(value) || !exact(value, keys)
    || value.schemaVersion !== 1 || value.kind !== 'kafka-observation' || value.synthetic !== true || value.publicExecutionEnabled !== false
    || !(value.environment === 'MINI_PC' && value.scope === 'DEPLOYED_KAFKA' || value.environment === 'ISOLATED_LAB' && value.scope === 'ISOLATED_KAFKA')
    || typeof value.sourceCommit !== 'string' || !/^[a-f0-9]{40}$/.test(value.sourceCommit)
    || typeof value.targetFingerprint !== 'string' || !/^[a-f0-9]{64}$/.test(value.targetFingerprint)
    || value.consistency !== 'BOUNDED_SEQUENTIAL_READ' || !['STABLE', 'EMPTY'].includes(value.groupState as string) || value.partition !== 0
    || !offset(value.logStartOffset) || !offset(value.readCommittedEndOffset) || value.readCommittedEndOffset < value.logStartOffset) return false;
  const start = kafkaUtcNs(value.captureStartedAt); const end = kafkaUtcNs(value.capturedAt);
  if (start === null || end === null || start > end || end - start > 4_000_000_000n || end > BigInt(nowMs) * 1_000_000n) return false;
  if (value.commitState === 'NO_COMMIT') return value.committedOffset === null && value.lag === null;
  return value.commitState === 'OBSERVED' && offset(value.committedOffset) && offset(value.lag)
    && value.committedOffset >= value.logStartOffset && value.committedOffset <= value.readCommittedEndOffset
    && value.lag === value.readCommittedEndOffset - value.committedOffset;
}
export function parseKafkaObservation(text: unknown, nowMs = Date.now()): KafkaObservation | null {
  const value = strictFlatObject(text); return validateKafkaObservation(value, nowMs) ? value : null;
}
export function parseKafkaObservationError(text: unknown): KafkaErrorCode | null {
  const value = strictFlatObject(text);
  return value && exact(value, ['schemaVersion', 'kind', 'code']) && value.schemaVersion === 1 && value.kind === 'kafka-observation-error'
    && typeof value.code === 'string' && (KAFKA_ERROR_CODES as readonly string[]).includes(value.code) ? value.code as KafkaErrorCode : null;
}
export function safeKafkaObservationUrl(value: string): boolean {
  return value === '/api/kafka/observation' || /^\/(?:[A-Za-z0-9_-]+\/)*observations\/kafka\.latest\.json$/.test(value);
}
async function boundedText(response: Response): Promise<string> {
  if (!response.body) return '';
  const reader = response.body.getReader(); const chunks: Uint8Array[] = []; let size = 0;
  try {
    while (true) {
      const item = await reader.read(); if (item.done) break;
      size += item.value.byteLength;
      if (size > MAX_KAFKA_OBSERVATION_BYTES) { await reader.cancel().catch(() => undefined); throw new Error('INVALID_RECORD'); }
      chunks.push(item.value);
    }
  } finally { reader.releaseLock(); }
  const bytes = new Uint8Array(size); let cursor = 0;
  for (const chunk of chunks) { bytes.set(chunk, cursor); cursor += chunk.byteLength; }
  return new TextDecoder('utf-8', { fatal: true, ignoreBOM: true }).decode(bytes);
}
export interface KafkaObservationLoad { record: KafkaObservation | null; browserError: KafkaBrowserError | null; retainedPrevious: boolean; }
export async function loadKafkaObservation(options: { url: string; previousRecord?: KafkaObservation | null; allowIsolated?: boolean;
  nowMs?: number; signal?: AbortSignal; fetcher?: typeof fetch }): Promise<KafkaObservationLoad> {
  // A previous validated record survives a later browser-clock regression; it is then shown as clock-check.
  const previous = validateKafkaObservation(options.previousRecord, Number.MAX_SAFE_INTEGER) ? options.previousRecord : null;
  const failed = (browserError: KafkaBrowserError): KafkaObservationLoad => ({ record: previous, browserError, retainedPrevious: previous !== null });
  if (!safeKafkaObservationUrl(options.url)) return failed('INVALID_URL');
  let response: Response;
  try { response = await (options.fetcher || fetch)(options.url, { headers: { Accept: 'application/json' }, signal: options.signal, cache: 'no-store', credentials: 'omit' }); }
  catch { return failed(options.signal?.aborted ? 'ABORTED' : 'NETWORK_ERROR'); }
  if (response.status === 404) return failed('NOT_CONFIGURED');
  let text: string;
  try { text = await boundedText(response); }
  catch { return failed(options.signal?.aborted ? 'ABORTED' : 'INVALID_RECORD'); }
  if (!response.ok) {
    const code = parseKafkaObservationError(text);
    if (code && (response.status === 503 || response.status === 400 && code === 'INVALID_CONFIGURATION')) return failed(code);
    return failed('HTTP_ERROR');
  }
  const record = parseKafkaObservation(text, options.nowMs ?? Date.now());
  if (!record) return failed('INVALID_RECORD');
  if (!options.allowIsolated && record.environment !== 'MINI_PC') return failed('ENVIRONMENT_MISMATCH');
  if (previous && record.targetFingerprint !== previous.targetFingerprint) return failed('TARGET_CHANGED');
  if (previous && kafkaUtcNs(record.capturedAt)! < kafkaUtcNs(previous.capturedAt)!) return failed('OLDER_RECORD');
  if (previous && kafkaUtcNs(record.capturedAt) === kafkaUtcNs(previous.capturedAt)) {
    // Key order and equivalent UTC fractional spelling do not create a new capture.
    const same = keys.every(key => key === 'captureStartedAt' || key === 'capturedAt'
      ? kafkaUtcNs(record[key]) === kafkaUtcNs(previous[key]) : record[key] === previous[key]);
    if (!same) return failed('CONFLICTING_RECORD');
    return { record: previous, browserError: null, retainedPrevious: true };
  }
  return { record, browserError: null, retainedPrevious: false };
}
export function kafkaObservationView(record: KafkaObservation | null, nowMs: number): 'absent' | 'recent' | 'stale' | 'clock-check' {
  if (!record) return 'absent';
  const captured = kafkaUtcNs(record.capturedAt);
  if (!Number.isSafeInteger(nowMs) || captured === null || captured > BigInt(nowMs) * 1_000_000n) return 'clock-check';
  return BigInt(nowMs) * 1_000_000n - captured > BigInt(KAFKA_STALE_AFTER_MS) * 1_000_000n ? 'stale' : 'recent';
}
