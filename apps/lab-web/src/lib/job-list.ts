import type { JobObservation } from './job-observation.ts';

export interface JobListFilters {
  query: string;
  status: JobObservation['status'] | 'ALL';
  exportStatus: JobObservation['exportStatus'] | 'ALL';
}

export const DEFAULT_JOB_FILTERS: JobListFilters = { query: '', status: 'ALL', exportStatus: 'ALL' };

/** Narrow an accepted observation list without changing its order or job records. */
export function filterObservedJobs(jobs: readonly JobObservation[], filters: JobListFilters): JobObservation[] {
  const query = filters.query.trim().toLowerCase();
  return jobs.filter(job => (!query || job.runId.toLowerCase().includes(query))
    && (filters.status === 'ALL' || job.status === filters.status)
    && (filters.exportStatus === 'ALL' || job.exportStatus === filters.exportStatus));
}
