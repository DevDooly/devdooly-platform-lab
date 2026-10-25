import { compareEventOutcomes, selectEventComparisons, type EventComparisonKind, type EventComparisonRow } from './event-comparison.ts';
import type { EventExportDocument } from './event-export.ts';
import type { OfflineEventFile } from './offline-event-file.ts';

export const OFFLINE_COMPARISON_REPORT_FILENAME = 'devdooly-event-comparison-report.json';

export interface OfflineReportSelection {
  query: string;
  kind: 'all' | EventComparisonKind;
  limit: number;
}

interface OfflineReportFileMetadata {
  name: string;
  byteLength: number;
  schemaVersion: EventExportDocument['schemaVersion'];
  source: EventExportDocument['source'];
  filters: EventExportDocument['filters'];
  counts: EventExportDocument['counts'];
  storedOutcomeCount: number;
}

export interface OfflineComparisonReport {
  format: 'devdooly-offline-event-comparison-report';
  schemaVersion: 1;
  capturedAt: string;
  files: { left: OfflineReportFileMetadata; right: OfflineReportFileMetadata };
  view: { query: string; kind: 'all' | EventComparisonKind; displayLimit: number };
  counts: { totalGroups: number; matchingGroups: number; displayedGroups: number };
  classifications: Record<EventComparisonKind, number>;
  groups: EventComparisonRow[];
}

function fileMetadata(file: OfflineEventFile): OfflineReportFileMetadata {
  const { document } = file;
  return { name: file.name, byteLength: file.byteLength, schemaVersion: document.schemaVersion,
    source: { ...document.source }, filters: { ...document.filters }, counts: { ...document.counts },
    storedOutcomeCount: document.outcomes.length };
}

/** Snapshot every matching group, independently of the display window and subsequent file/view changes. */
export function createOfflineComparisonReport(pair: { left: OfflineEventFile; right: OfflineEventFile },
  selection: OfflineReportSelection, capturedAt: string): OfflineComparisonReport {
  const comparison = compareEventOutcomes(pair.left.document.outcomes, pair.right.document.outcomes);
  const matching = selectEventComparisons(comparison.rows, selection);
  return { format: 'devdooly-offline-event-comparison-report', schemaVersion: 1, capturedAt,
    files: { left: fileMetadata(pair.left), right: fileMetadata(pair.right) },
    view: { query: selection.query, kind: selection.kind, displayLimit: selection.limit },
    counts: { totalGroups: comparison.rows.length, matchingGroups: matching.length,
      displayedGroups: matching.slice(0, selection.limit).length },
    classifications: { ...comparison.counts },
    groups: matching.map(row => ({ ...row,
      left: row.left.map(outcome => ({ ...outcome })), right: row.right.map(outcome => ({ ...outcome })),
      inputDifferences: row.inputDifferences === null ? null : [...row.inputDifferences],
      verdictDifferences: row.verdictDifferences === null ? null : [...row.verdictDifferences],
    })),
  };
}

/** A review report is a separate format, not an original export or a restorable comparison session. */
export function offlineComparisonReportJson(report: OfflineComparisonReport): string {
  return JSON.stringify(report, null, 2) + '\n';
}
