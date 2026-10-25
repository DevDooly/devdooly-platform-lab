import { eventSharePath } from './event-share.ts';
import type { JobObservation, JobObservationRecord } from './job-observation.ts';

/** Link a completed deployed job to a new explicit read, not its recorded snapshot. */
export function jobEventLinks(
  job: JobObservation,
  context: Pick<JobObservationRecord, 'environment' | 'scope'>,
  basePath: string,
): { all: string; failed: string | null } | null {
  if (context.environment !== 'MINI_PC' || context.scope !== 'DEPLOYED_RUNTIME'
    || job.status !== 'COMPLETED' || job.counts === null) return null;

  const path = (status: 'ALL' | 'FAILED') => eventSharePath({
    runId: job.runId,
    filters: { status, query: '', reason: null },
    sequence: null,
  }, basePath);
  const all = path('ALL');
  if (all === null) return null;
  return { all, failed: job.counts.failure > 0 ? path('FAILED') : null };
}
