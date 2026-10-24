import type { Outcome } from './api.ts';
import { filterEventOutcomes, type EventSearchFilters } from './event-search.ts';
import type { SourceMode } from './observation.ts';

export interface EventExportInput {
  runId: string;
  mode: SourceMode;
  observedAt: string | null;
  capturedAt: string | null;
  reportedInputCount: number;
  filters: Readonly<EventSearchFilters>;
  /** All outcomes already read for this run, before the current search conditions. */
  outcomes: readonly Outcome[];
}

interface EventExportBase {
  source: { runId: string; mode: SourceMode; observedAt: string | null; capturedAt: string | null };
  counts: { reportedInputCount: number; availableOutcomes: number; matchedOutcomes: number };
  outcomes: Outcome[];
}

type ExportFilters = { status: EventSearchFilters['status']; query: string; reason: string | null };

export type EventExportDocument = EventExportBase & (
  | { schemaVersion: 1; filters: ExportFilters }
  | { schemaVersion: 2; filters: ExportFilters & { sensorId: string } }
);

/** Snapshot the current search result without fetching, reclassifying or forwarding unknown fields. */
export function createEventExport(input: EventExportInput): EventExportDocument {
  const { runId, mode, observedAt, capturedAt, reportedInputCount, filters } = input;
  const outcomes = filterEventOutcomes(input.outcomes, filters).map(row => ({
    sequence: row.sequence, eventId: row.eventId, sensorId: row.sensorId, eventTime: row.eventTime,
    value: row.value, status: row.status, reason: row.reason,
  }));
  const source = { runId, mode, observedAt, capturedAt };
  const exportFilters = { status: filters.status, query: filters.query, reason: filters.reason };
  const counts = { reportedInputCount, availableOutcomes: input.outcomes.length, matchedOutcomes: outcomes.length };
  if (filters.sensorId != null) return { schemaVersion: 2, source,
    filters: { ...exportFilters, sensorId: filters.sensorId }, counts, outcomes };
  return { schemaVersion: 1, source, filters: exportFilters, counts, outcomes };
}

/** JSON retains the reported strings, numeric values and nulls without CSV display prefixes. */
export function eventExportJson(document: EventExportDocument): string {
  return JSON.stringify(document, null, 2) + '\n';
}

type CsvCell = string | number | boolean | null;

/** Numeric negatives remain numbers; formula-like strings get a visible apostrophe prefix. */
function csvCell(value: CsvCell): string {
  let text = value === null ? '' : String(value);
  if (typeof value === 'string' && (/^[\t\r\n]/.test(text) || /^\s*[=+\-@]/u.test(text))) text = "'" + text;
  return '"' + text.replaceAll('"', '""') + '"';
}

/** One context row preserves source and search conditions even when no events match. */
export function eventExportCsv(document: EventExportDocument): string {
  const { source, filters, counts } = document;
  const header = ['recordType', 'schemaVersion', 'runId', 'sourceMode', 'observedAt', 'capturedAt',
    'reportedInputCount', 'availableOutcomes', 'matchedOutcomes', 'filterStatus', 'filterQuery',
    'filterReasonIsAll', 'filterReason',
    ...(document.schemaVersion === 2 ? ['filterSensorIsAll', 'filterSensorId'] : []),
    'sequence', 'eventId', 'sensorId', 'eventTime', 'value',
    'valueIsNull', 'status', 'reason'];
  const metadata: CsvCell[] = [document.schemaVersion, source.runId, source.mode, source.observedAt,
    source.capturedAt, counts.reportedInputCount, counts.availableOutcomes, counts.matchedOutcomes,
    filters.status, filters.query, filters.reason === null, filters.reason,
    ...(document.schemaVersion === 2 ? [false, document.filters.sensorId] : [])];
  const rows: CsvCell[][] = [header, ['context', ...metadata, null, null, null, null, null, null, null, null]];
  for (const row of document.outcomes) rows.push(['event', ...metadata, row.sequence, row.eventId,
    row.sensorId, row.eventTime, row.value, row.value === null, row.status, row.reason]);
  return '\uFEFF' + rows.map(row => row.map(csvCell).join(',')).join('\r\n') + '\r\n';
}

/** The static prefix and bounded allowlist prevent run IDs from introducing paths or control bytes. */
export function eventExportFilename(document: EventExportDocument, format: 'csv' | 'json'): string {
  const runId = document.source.runId.replace(/[^a-z0-9._-]+/gi, '-').replace(/^[._-]+|[._-]+$/g, '')
    .slice(0, 80).replace(/[._-]+$/g, '') || 'run';
  return `lab-events-${document.source.mode}-${runId}.${format}`;
}
