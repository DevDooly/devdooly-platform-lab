import type { Outcome } from './api.ts';
import type { EventExportDocument } from './event-export.ts';
import { filterEventOutcomes } from './event-search.ts';
import { parseJobObservationJson as parseDocumentJson } from './job-observation-json.ts';

export const MAX_OFFLINE_FILE_BYTES = 1048576;
export const MAX_OFFLINE_OUTCOMES = 1000;

export type OfflineEventFileError = 'FILE_TOO_LARGE' | 'INVALID_UTF8' | 'INVALID_JSON' | 'INVALID_DOCUMENT'
  | 'TOO_MANY_OUTCOMES' | 'FILTER_MISMATCH' | 'READ_FAILED';

export interface OfflineEventFile {
  name: string;
  byteLength: number;
  document: EventExportDocument;
}

const statuses = ['SUCCESS', 'FAILED', 'DUPLICATE', 'PENDING'];
const count = (value: unknown): value is number => typeof value === 'number' && Number.isSafeInteger(value) && value >= 0;
const timestamp = (value: unknown): boolean => value === null
  || (typeof value === 'string' && !Number.isNaN(Date.parse(value)));

function exactKeys(value: unknown, keys: readonly string[]): value is Record<string, unknown> {
  if (typeof value !== 'object' || value === null || Array.isArray(value)) return false;
  const own = Object.keys(value);
  return own.length === keys.length && own.every(key => keys.includes(key));
}

function isOutcome(value: unknown): value is Outcome {
  return exactKeys(value, ['sequence', 'eventId', 'sensorId', 'eventTime', 'value', 'status', 'reason'])
    && count(value.sequence) && typeof value.eventId === 'string' && typeof value.sensorId === 'string'
    && typeof value.eventTime === 'string' && typeof value.reason === 'string'
    && (value.value === null || (typeof value.value === 'number' && Number.isFinite(value.value)))
    && typeof value.status === 'string' && statuses.includes(value.status);
}

function validateDocument(value: unknown): { ok: true; document: EventExportDocument }
  | { ok: false; code: OfflineEventFileError } {
  const invalid = { ok: false, code: 'INVALID_DOCUMENT' } as const;
  if (!exactKeys(value, ['schemaVersion', 'source', 'counts', 'filters', 'outcomes'])
    || (value.schemaVersion !== 1 && value.schemaVersion !== 2)
    || !exactKeys(value.source, ['runId', 'mode', 'observedAt', 'capturedAt'])
    || typeof value.source.runId !== 'string' || typeof value.source.mode !== 'string'
    || !['live', 'recorded', 'fixture'].includes(value.source.mode)
    || !timestamp(value.source.observedAt) || !timestamp(value.source.capturedAt)
    || !exactKeys(value.counts, ['reportedInputCount', 'availableOutcomes', 'matchedOutcomes'])
    || !count(value.counts.reportedInputCount) || !count(value.counts.availableOutcomes) || !count(value.counts.matchedOutcomes)
    || !exactKeys(value.filters, value.schemaVersion === 1 ? ['status', 'query', 'reason'] : ['status', 'query', 'reason', 'sensorId'])
    || typeof value.filters.status !== 'string' || !['ALL', ...statuses].includes(value.filters.status)
    || typeof value.filters.query !== 'string' || !(value.filters.reason === null || typeof value.filters.reason === 'string')
    || (value.schemaVersion === 2 && typeof value.filters.sensorId !== 'string')
    || !Array.isArray(value.outcomes)) return invalid;
  if (value.outcomes.length > MAX_OFFLINE_OUTCOMES) return { ok: false, code: 'TOO_MANY_OUTCOMES' };
  if (!value.outcomes.every(isOutcome) || value.counts.matchedOutcomes !== value.outcomes.length
    || value.counts.matchedOutcomes > value.counts.availableOutcomes) return invalid;
  // All schema fields were checked above; exactKeys intentionally narrows only to a generic record.
  const document = value as unknown as EventExportDocument;
  if (filterEventOutcomes(document.outcomes, document.filters).length !== document.outcomes.length)
    return { ok: false, code: 'FILTER_MISMATCH' };
  return { ok: true, document };
}

/** Read a bounded saved export, without treating its metadata as a network destination or proof of origin. */
export function readOfflineEventBytes(bytes: Uint8Array): { ok: true; document: EventExportDocument }
  | { ok: false; code: OfflineEventFileError } {
  if (bytes.byteLength > MAX_OFFLINE_FILE_BYTES) return { ok: false, code: 'FILE_TOO_LARGE' };
  let text: string;
  try { text = new TextDecoder('utf-8', { fatal: true }).decode(bytes); }
  catch { return { ok: false, code: 'INVALID_UTF8' }; }
  let document: unknown;
  try { document = parseDocumentJson(text); }
  catch { return { ok: false, code: 'INVALID_JSON' }; }
  return validateDocument(document);
}

/** The declared-size gate avoids reading an oversized file; the actual bytes are bounded again after reading. */
export async function readOfflineEventFile(file: { name: string; size: number; arrayBuffer(): Promise<ArrayBuffer> }):
  Promise<{ ok: true; file: OfflineEventFile } | { ok: false; code: OfflineEventFileError }> {
  try {
    if (file.size > MAX_OFFLINE_FILE_BYTES) return { ok: false, code: 'FILE_TOO_LARGE' };
    const bytes = new Uint8Array(await file.arrayBuffer());
    const result = readOfflineEventBytes(bytes);
    return result.ok ? { ok: true, file: { name: file.name, byteLength: bytes.byteLength, document: result.document } } : result;
  } catch { return { ok: false, code: 'READ_FAILED' }; }
}
