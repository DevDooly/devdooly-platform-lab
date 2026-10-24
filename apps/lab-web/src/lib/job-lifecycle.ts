import { jobObservationTimeNs } from './job-observation.ts';
import type { JobObservation } from './job-observation.ts';

export interface JobLifecycleStep {
  id: 'created' | 'verified-queued' | 'completed' | 'exported' | 'terminated';
  at: string | null;
  recorded: boolean;
}
export interface JobLifecycleInterval {
  id: 'queued-completed' | 'completed-exported';
  from: string | null;
  to: string | null;
  nanoseconds: bigint | null;
}
export interface JobLifecycle {
  steps: JobLifecycleStep[];
  intervals: [JobLifecycleInterval, JobLifecycleInterval];
  exportCancelled: boolean;
}

const step = (id: JobLifecycleStep['id'], at: string | null): JobLifecycleStep => ({ id, at, recorded: at !== null });
function interval(id: JobLifecycleInterval['id'], from: string | null, to: string | null): JobLifecycleInterval {
  return { id, from, to, nanoseconds: from === null || to === null ? null : jobObservationTimeNs(to)! - jobObservationTimeNs(from)! };
}

/** Display accepted DTO records, without inferring unrecorded stages or runtime progress. */
export function jobLifecycle(job: JobObservation): JobLifecycle {
  const steps = [step('created', job.createdAt), step('verified-queued', job.queuedAt),
    step('completed', job.completedAt), step('exported', job.exportCompletedAt)];
  if (job.terminatedAt !== null) steps.push(step('terminated', job.terminatedAt));
  return { steps, intervals: [interval('queued-completed', job.queuedAt, job.completedAt),
    interval('completed-exported', job.completedAt, job.exportCompletedAt)], exportCancelled: job.exportStatus === 'CANCELLED' };
}

/** Exact seconds for a nonnegative recorded interval; null has no elapsed-time meaning. */
export function formatJobLifecycleInterval(nanoseconds: bigint | null): string {
  if (nanoseconds === null) return '미기록';
  const seconds = nanoseconds / 1_000_000_000n;
  const fraction = (nanoseconds % 1_000_000_000n).toString().padStart(9, '0').replace(/0+$/, '');
  return `${seconds}${fraction ? `.${fraction}` : ''}초`;
}
