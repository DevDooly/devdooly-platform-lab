/** Keep API and published records in separate caches; a failed live read is never live success. */
export interface ObservationLoad<Record, ErrorCode> {
  record: Record | null; browserError: ErrorCode | null; retainedPrevious: boolean;
}
export interface PreferredObservation<Record, ErrorCode> extends ObservationLoad<Record, ErrorCode> {
  sourceMode: 'api' | 'recorded'; fallbackUsed: boolean; fallbackBrowserError: ErrorCode | null;
  lastLive: Record | null; lastRecorded: Record | null;
}
export async function loadLiveWithRecordedFallback<Record, ErrorCode extends string>(options: {
  liveUrl: string; recordedUrl: string; previousLive: Record | null; previousRecorded: Record | null;
  signal?: AbortSignal; invalidLiveError: ErrorCode; acceptLive?: (record: Record) => boolean;
  load: (url: string, previous: Record | null, signal: AbortSignal, source: 'api' | 'recorded') => Promise<ObservationLoad<Record, ErrorCode>>;
}): Promise<PreferredObservation<Record, ErrorCode>> {
  // Both reads fit inside the owning card's existing eight-second deadline.
  const bounded = (milliseconds: number) => options.signal
    ? AbortSignal.any([options.signal, AbortSignal.timeout(milliseconds)]) : AbortSignal.timeout(milliseconds);
  const live = await options.load(options.liveUrl, options.previousLive, bounded(5000), 'api');
  if (live.browserError === null && live.record !== null && (!options.acceptLive || options.acceptLive(live.record))) {
    return { ...live, sourceMode: 'api', fallbackUsed: false, fallbackBrowserError: null,
      lastLive: live.record, lastRecorded: options.previousRecorded };
  }
  const published = await options.load(options.recordedUrl, options.previousRecorded, bounded(2000), 'recorded');
  if (published.record === null && live.browserError !== null && live.retainedPrevious === true
    && live.record !== null && live.record === options.previousLive
    && (!options.acceptLive || options.acceptLive(live.record))) {
    return { record: live.record, browserError: live.browserError, retainedPrevious: true,
      sourceMode: 'api', fallbackUsed: false, fallbackBrowserError: published.browserError,
      lastLive: live.record, lastRecorded: null };
  }
  return { ...published, browserError: live.browserError || options.invalidLiveError,
    sourceMode: 'recorded', fallbackUsed: true, fallbackBrowserError: published.browserError,
    lastLive: options.previousLive, lastRecorded: published.record };
}
