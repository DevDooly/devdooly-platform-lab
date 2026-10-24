import { eventSharePath } from './event-share.ts';

export interface ComparisonEventOptions {
  status?: 'ALL' | 'FAILED';
  reason?: string | null;
}

/** Open the displayed run using the Lab's existing explicit-read share contract. */
export function comparisonEventPath(runId: string, basePath: string, options: ComparisonEventOptions = {}): string | null {
  return eventSharePath({
    runId,
    filters: { status: options.status ?? 'ALL', query: '', reason: options.reason ?? null },
    sequence: null,
  }, basePath);
}
