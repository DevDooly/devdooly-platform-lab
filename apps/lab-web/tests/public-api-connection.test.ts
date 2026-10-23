import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { test } from 'node:test';
import { fetchLab, getJson } from '../src/lib/api.ts';
import { publicApiConfiguration, publicReadUrl } from '../src/lib/public-api-base.ts';
import { loadLiveWithRecordedFallback } from '../src/lib/public-observation-source.ts';
import type { PreferredObservation } from '../src/lib/public-observation-source.ts';
import { loadJobObservation, validateJobObservation } from '../src/lib/job-observation.ts';
import type { JobBrowserError, JobObservationRecord } from '../src/lib/job-observation.ts';
import { loadKafkaObservation, validateKafkaObservation } from '../src/lib/kafka-observation.ts';
import type { KafkaBrowserError, KafkaObservation } from '../src/lib/kafka-observation.ts';

// Synthetic DTOs use the existing job/Kafka test contracts; none is published as observation evidence.
const base = 'https://api.example.test/api';
const jobPublished = '/devdooly-platform-lab/observations/jobs.latest.json';
const kafkaPublished = '/devdooly-platform-lab/observations/kafka.latest.json';
const now = Date.UTC(2026, 9, 18, 12, 0, 10);
const marker = 'SYNTHETIC_PRIVATE_FAILURE_MUST_NOT_ENTER_RECORD';
const json = (value: unknown) => new Response(JSON.stringify(value), { headers: { 'Content-Type': 'application/json' } });
function job(): JobObservationRecord {
  return { schemaVersion: 1, kind: 'job-observation', capturedAt: '2026-10-18T12:00:02.123456789Z', environment: 'MINI_PC', sourceCommit: 'a'.repeat(40), synthetic: true,
    scope: 'DEPLOYED_RUNTIME', publicExecutionEnabled: false,
    runtime: { status: 'NOT_STARTED', stage: 'IDLE', failureCode: null, startedAt: null, heartbeatAt: null, stoppedAt: null, sourceCommit: 'unknown', stale: false },
    slot: { occupiedRunId: null }, jobs: [] };
}
function kafka(): KafkaObservation {
  return { schemaVersion: 1, kind: 'kafka-observation', synthetic: true,
    environment: 'MINI_PC', scope: 'DEPLOYED_KAFKA', publicExecutionEnabled: false, sourceCommit: 'a'.repeat(40),
    captureStartedAt: '2026-10-18T12:00:00Z', capturedAt: '2026-10-18T12:00:02Z', consistency: 'BOUNDED_SEQUENTIAL_READ',
    targetFingerprint: 'b'.repeat(64), groupState: 'STABLE', partition: 0, commitState: 'OBSERVED',
    logStartOffset: 0, readCommittedEndOffset: 8, committedOffset: 8, lag: 0 };
}
function selectJob(read: typeof fetch, previousLive: JobObservationRecord | null = null,
  previousRecorded: JobObservationRecord | null = null, signal?: AbortSignal) {
  return loadLiveWithRecordedFallback<JobObservationRecord, JobBrowserError>({
    liveUrl: publicReadUrl(base, '/jobs/observation')!, recordedUrl: jobPublished,
    previousLive, previousRecorded, signal, invalidLiveError: 'INVALID_RECORD',
    acceptLive: value => value.environment === 'MINI_PC',
    load: (url, previousRecord, readSignal) => loadJobObservation({ url, previousRecord, signal: readSignal,
      fetcher: read, rejectRedirects: true }),
  });
}
function selectKafka(read: typeof fetch, previousLive: KafkaObservation | null = null,
  previousRecorded: KafkaObservation | null = null) {
  return loadLiveWithRecordedFallback<KafkaObservation, KafkaBrowserError>({
    liveUrl: publicReadUrl(base, '/kafka/observation')!, recordedUrl: kafkaPublished,
    previousLive, previousRecorded, invalidLiveError: 'INVALID_RECORD',
    load: (url, previousRecord, signal, source) => loadKafkaObservation({ url, previousRecord, signal,
      nowMs: now, allowIsolated: false, apiBase: source === 'api' ? base : undefined,
      fetcher: read, rejectRedirects: true }),
  });
}
function publicGet(input: RequestInfo | URL, options?: RequestInit): string {
  assert.equal(typeof input, 'string');
  assert.equal(options?.method || 'GET', 'GET');
  assert.equal(options?.credentials, 'omit');
  assert.equal(options?.redirect, 'error');
  assert.equal(options?.cache, 'no-store');
  assert.equal(options?.body, undefined);
  const headers = new Headers(options?.headers);
  assert.equal(headers.get('Accept'), 'application/json');
  assert.equal(headers.get('Authorization'), null); assert.equal(headers.get('Cookie'), null);
  assert.equal(headers.get('Content-Type'), null);
  return String(input);
}

test('public configuration keeps legacy defaults and rejects unsafe external settings before URL construction', () => {
  for (const value of [undefined, '', '/api', '/api/']) {
    const configured = publicApiConfiguration(value);
    assert.equal(configured.invalid, false); assert.equal(configured.externalHttps, false);
    assert.equal(publicReadUrl(configured.apiBase, '/jobs/observation'), '/api/jobs/observation');
  }
  assert.equal(publicApiConfiguration(base + '/').apiBase, base);
  assert.equal(publicApiConfiguration(base).externalHttps, true);
  for (const value of ['http://api.example.test/api', 'https://user:pass@api.example.test/api',
    'https://@api.example.test/api', base + '?', base + '?token=private', base + '#', base + '#private',
    'https://api.example.test/admin', 'https://api.example.test:8443/api',
    'https://127.0.0.1/api', 'https://localhost/api', 'https://api.svc.cluster.local/api', ' ' + base]) {
    const configured = publicApiConfiguration(value);
    assert.equal(configured.invalid, true, value);
    assert.equal(publicReadUrl(configured.apiBase, '/jobs/observation'), null);
  }
  for (const path of ['/admin', '/jobs', '/jobs/observation?run=x', '/kafka/observation#x',
    '/demo/runs/a%2Fb', '/demo/runs/../private']) assert.equal(publicReadUrl(base, path), null);
});

test('actual Lab, Job and Kafka adapters send the six fixed GET routes to the same explicit base', async context => {
  const sample = JSON.parse(readFileSync(new URL('../src/data/snapshot.json', import.meta.url), 'utf8'));
  const observedAt = '2026-10-18T12:00:02Z';
  const run = { ...sample.runs[0], startedAt: observedAt, completedAt: observedAt };
  const detail = { ...sample.detail, ...run, observedAt };
  const calls: string[] = [];
  const read: typeof fetch = async (input, options) => {
    const url = publicGet(input, options); calls.push(url);
    if (url === base + '/demo/runs') return json({ items: [run], observedAt });
    if (url === base + '/demo/runs/' + run.id) return json(detail);
    if (url === base + '/platform/summary') return json({ ...sample.summary, status: 'UP', observedAt });
    if (url === base + '/platform/releases') return json({ items: [], observedAt });
    if (url === base + '/jobs/observation') return json(job());
    if (url === base + '/kafka/observation') return json(kafka());
    throw new Error('UNEXPECTED_TEST_URL');
  };
  context.mock.method(globalThis, 'fetch', read);
  const lab = await fetchLab(publicApiConfiguration(base).apiBase);
  const jobs = await selectJob(read); const broker = await selectKafka(read);
  assert.equal(lab.detail.inputCount, 12); assert.equal(lab.detail.successCount, 7);
  assert.equal(jobs.sourceMode, 'api'); assert.equal(jobs.fallbackUsed, false);
  assert.equal(jobs.record?.sourceCommit, job().sourceCommit);
  assert.equal(broker.sourceMode, 'api'); assert.equal(broker.record?.lag, 0);
  assert.equal(broker.record?.capturedAt, kafka().capturedAt);
  assert.deepEqual([...calls].sort(), ['/demo/runs', '/demo/runs/' + run.id, '/platform/summary',
    '/platform/releases', '/jobs/observation', '/kafka/observation'].map(path => base + path).sort());
  await assert.rejects(getJson(base, '/admin')); await assert.rejects(getJson(base, '/jobs/observation?run=x'));
  await assert.rejects(getJson(publicApiConfiguration(base + '?').apiBase, '/platform/summary'));
  assert.equal(calls.length, 6, 'Rejected configurations and paths must not call the mocked transport');
});

test('a failed live Job read uses the independent published source and time instead of relabeling live cache', async () => {
  const previousLive = job();
  const published = { ...job(), sourceCommit: 'c'.repeat(40), capturedAt: '2026-10-18T11:59:59.999999999Z' };
  assert.equal(validateJobObservation(published), true);
  const calls: string[] = [];
  const read: typeof fetch = async (input, options) => {
    const url = publicGet(input, options); calls.push(url);
    if (url === base + '/jobs/observation') throw new Error(marker);
    assert.equal(url, jobPublished); return json(published);
  };
  const selected = await selectJob(read, previousLive);
  assert.equal(selected.sourceMode, 'recorded'); assert.equal(selected.fallbackUsed, true);
  assert.equal(selected.browserError, 'NETWORK_ERROR'); assert.deepEqual(selected.record, published);
  assert.equal(selected.lastLive, previousLive); assert.notEqual(selected.record, previousLive);
  assert.equal(selected.record?.sourceCommit, published.sourceCommit);
  assert.equal(selected.record?.capturedAt, published.capturedAt);
  assert.deepEqual(calls, [base + '/jobs/observation', jobPublished]);
  assert.equal(JSON.stringify(selected).includes(marker), false);
});

test('Kafka HTTP, private, regressed, changed-target and isolated live responses fall back without weakening its validator', async () => {
  const previousLive = kafka();
  const published = { ...kafka(), sourceCommit: 'c'.repeat(40),
    captureStartedAt: '2026-10-18T11:59:58Z', capturedAt: '2026-10-18T11:59:59.999999999Z' };
  assert.equal(validateKafkaObservation(published, now), true);
  const cases: Array<[() => Response, KafkaBrowserError]> = [
    [() => new Response(marker, { status: 503 }), 'HTTP_ERROR'],
    [() => json({ ...kafka(), rawCluster: marker }), 'INVALID_RECORD'],
    [() => json({ ...kafka(), capturedAt: '2026-10-18T12:00:01.999999999Z' }), 'OLDER_RECORD'],
    [() => json({ ...kafka(), targetFingerprint: 'd'.repeat(64) }), 'TARGET_CHANGED'],
    [() => json({ ...kafka(), sourceCommit: 'd'.repeat(40) }), 'CONFLICTING_RECORD'],
    [() => json({ ...kafka(), environment: 'ISOLATED_LAB', scope: 'ISOLATED_KAFKA' }), 'ENVIRONMENT_MISMATCH'],
  ];
  for (const [response, expected] of cases) {
    const calls: string[] = [];
    const read: typeof fetch = async (input, options) => {
      const url = publicGet(input, options); calls.push(url);
      if (url === base + '/kafka/observation') return response();
      assert.equal(url, kafkaPublished); return json(published);
    };
    const selected = await selectKafka(read, previousLive);
    assert.equal(selected.browserError, expected); assert.equal(selected.sourceMode, 'recorded');
    assert.deepEqual({ ...selected.record }, published); assert.equal(selected.lastLive, previousLive);
    assert.equal(selected.record?.capturedAt, published.capturedAt);
    assert.deepEqual(calls, [base + '/kafka/observation', kafkaPublished]);
    assert.equal(JSON.stringify(selected).includes(marker), false);
  }
});

test('both failed reads retain a validated published cache and no prior evidence stays unobserved', async () => {
  const previousRecorded = { ...job(), sourceCommit: 'c'.repeat(40), capturedAt: '2026-10-18T08:00:00Z' };
  const read: typeof fetch = async (input, options) => {
    const url = publicGet(input, options);
    if (url === base + '/jobs/observation') return new Response(marker, { status: 503 });
    assert.equal(url, jobPublished); return json({ ...job(), token: marker });
  };
  const retained = await selectJob(read, job(), previousRecorded);
  assert.equal(retained.sourceMode, 'recorded'); assert.equal(retained.browserError, 'HTTP_ERROR');
  assert.equal(retained.fallbackBrowserError, 'INVALID_RECORD'); assert.equal(retained.record, previousRecorded);
  assert.equal(retained.record?.capturedAt, '2026-10-18T08:00:00Z'); assert.equal(retained.retainedPrevious, true);
  const absent = await selectJob(read);
  assert.equal(absent.record, null); assert.equal(absent.lastRecorded, null);
  assert.equal(absent.fallbackUsed, true); assert.equal(absent.sourceMode, 'recorded');
  assert.equal(JSON.stringify(absent).includes(marker), false);
});

function assertRetainedLive<Record extends { capturedAt: string }, ErrorCode extends string>(
  selected: PreferredObservation<Record, ErrorCode>, previous: Record, error: ErrorCode, fallbackError: ErrorCode,
) {
  assert.equal(selected.record, previous); assert.equal(selected.lastLive, previous);
  assert.equal(selected.record?.capturedAt, previous.capturedAt); assert.equal(selected.lastRecorded, null);
  assert.equal(selected.sourceMode, 'api'); assert.equal(selected.fallbackUsed, false);
  assert.equal(selected.retainedPrevious, true); assert.equal(selected.browserError, error);
  assert.equal(selected.fallbackBrowserError, fallbackError); assert.equal(JSON.stringify(selected).includes(marker), false);
}

test('Job retains its validated live cache when both reads fail before any published cache exists', async () => {
  const first = await selectJob(async (input, options) => {
    assert.equal(publicGet(input, options), base + '/jobs/observation'); return json(job());
  });
  const previous = first.record; assert.ok(previous); assert.equal(first.lastRecorded, null);
  for (const network of [false, true]) {
    const calls: string[] = [];
    const selected = await selectJob(async (input, options) => {
      const url = publicGet(input, options); calls.push(url);
      if (network) throw new TypeError(marker);
      return url === base + '/jobs/observation' ? new Response(marker, { status: 503 }) : new Response('', { status: 404 });
    }, first.lastLive);
    assert.deepEqual(calls, [base + '/jobs/observation', jobPublished]);
    assertRetainedLive(selected, previous, network ? 'NETWORK_ERROR' : 'HTTP_ERROR', network ? 'NETWORK_ERROR' : 'NOT_CONFIGURED');
  }
});

test('Kafka retains its validated live cache when both reads fail before any published cache exists', async () => {
  const first = await selectKafka(async (input, options) => {
    assert.equal(publicGet(input, options), base + '/kafka/observation'); return json(kafka());
  });
  const previous = first.record; assert.ok(previous); assert.equal(first.lastRecorded, null);
  for (const network of [false, true]) {
    const calls: string[] = [];
    const selected = await selectKafka(async (input, options) => {
      const url = publicGet(input, options); calls.push(url);
      if (network) throw new TypeError(marker);
      return url === base + '/kafka/observation' ? new Response(marker, { status: 503 }) : new Response('', { status: 404 });
    }, first.lastLive);
    assert.deepEqual(calls, [base + '/kafka/observation', kafkaPublished]);
    assertRetainedLive(selected, previous, network ? 'NETWORK_ERROR' : 'HTTP_ERROR', network ? 'NETWORK_ERROR' : 'NOT_CONFIGURED');
  }
});

test('live cache retention never promotes invalid previous evidence rejected environments or unretained objects', async () => {
  const previous = job();
  const failed: typeof fetch = async (input, options) => publicGet(input, options) === base + '/jobs/observation'
    ? new Response(marker, { status: 503 }) : new Response('', { status: 404 });
  const invalidPrevious = { ...job(), capturedAt: 'not-a-UTC-instant' };
  const isolated: JobObservationRecord = { ...job(), environment: 'ISOLATED_LAB', scope: 'ISOLATED_LAB' };
  assert.equal(validateJobObservation(invalidPrevious), false); assert.equal(validateJobObservation(isolated), true);
  const rejected = [await selectJob(failed, invalidPrevious), await selectJob(failed, isolated)];
  rejected.push(await selectJob(async (input, options) => publicGet(input, options) === base + '/jobs/observation'
    ? json({ ...isolated, capturedAt: '2026-10-18T12:00:03Z' }) : new Response('', { status: 404 }), previous));
  for (const [record, retainedPrevious] of [[structuredClone(previous), true], [previous, false]] as const) {
    rejected.push(await loadLiveWithRecordedFallback<JobObservationRecord, JobBrowserError>({
      liveUrl: base + '/jobs/observation', recordedUrl: jobPublished, previousLive: previous, previousRecorded: null,
      invalidLiveError: 'INVALID_RECORD', acceptLive: value => value.environment === 'MINI_PC',
      load: async (_url, _previous, _signal, source) => source === 'api'
        ? { record, retainedPrevious, browserError: 'NETWORK_ERROR' }
        : { record: null, retainedPrevious: false, browserError: 'NOT_CONFIGURED' },
    }));
  }
  for (const selected of rejected) {
    assert.equal(selected.record, null); assert.equal(selected.sourceMode, 'recorded');
    assert.equal(selected.fallbackUsed, true); assert.equal(selected.retainedPrevious, false);
    assert.equal(JSON.stringify(selected).includes(marker), false);
  }
});

test('parent cancellation retains validated live evidence in its own source when no published record exists', { timeout: 1000 }, async () => {
  const first = await selectJob(async () => json(job())); const previous = first.record; assert.ok(previous);
  const controller = new AbortController(); const signals: AbortSignal[] = [];
  let notifyStarted!: () => void;
  const started = new Promise<void>(resolve => { notifyStarted = resolve; });
  const read: typeof fetch = async (input, options) => {
    publicGet(input, options); const signal = options?.signal; assert.ok(signal); signals.push(signal);
    if (signal.aborted) throw new DOMException(marker, 'AbortError');
    return new Promise<Response>((_resolve, reject) => {
      signal.addEventListener('abort', () => reject(new DOMException(marker, 'AbortError')), { once: true });
      notifyStarted();
    });
  };
  const pending = selectJob(read, first.lastLive, null, controller.signal);
  await started; controller.abort(); const selected = await pending;
  assert.equal(signals.length, 2); assert.ok(signals.every(signal => signal.aborted));
  assertRetainedLive(selected, previous, 'ABORTED', 'ABORTED');
});

test('parent cancellation aborts the changed helper reads and cannot turn the retained published cache into live success', { timeout: 1000 }, async () => {
  const controller = new AbortController();
  const previousRecorded = { ...job(), sourceCommit: 'c'.repeat(40), capturedAt: '2026-10-18T11:59:59Z' };
  let notifyStarted!: () => void;
  const started = new Promise<void>(resolve => { notifyStarted = resolve; });
  const signals: AbortSignal[] = [];
  let requestsStartedBeforeAbort = 0;
  const read: typeof fetch = async (input, options) => {
    publicGet(input, options); const signal = options?.signal; assert.ok(signal);
    signals.push(signal);
    if (signal.aborted) throw new DOMException('ABORTED_TEST_READ', 'AbortError');
    requestsStartedBeforeAbort++;
    return new Promise<Response>((_resolve, reject) => {
      signal.addEventListener('abort', () => reject(new DOMException('ABORTED_TEST_READ', 'AbortError')), { once: true });
      notifyStarted();
    });
  };
  const pending = selectJob(read, job(), previousRecorded, controller.signal);
  await started; controller.abort(); const selected = await pending;
  assert.equal(requestsStartedBeforeAbort, 1); assert.equal(signals.length, 2);
  assert.ok(signals.every(signal => signal.aborted));
  assert.equal(selected.browserError, 'ABORTED'); assert.equal(selected.fallbackBrowserError, 'ABORTED');
  assert.equal(selected.sourceMode, 'recorded'); assert.equal(selected.record, previousRecorded);
  assert.equal(selected.record?.capturedAt, previousRecorded.capturedAt); assert.equal(selected.fallbackUsed, true);
});

test('reserved HTTPS prefix preserves the six public GET adapters and rejects neighbouring paths', async context => {
  const reservedBase = 'https://api.example.test/platform-lab/api';
  assert.deepEqual(publicApiConfiguration(reservedBase), { apiBase: reservedBase, externalHttps: true, invalid: false });
  assert.equal(publicApiConfiguration(reservedBase + '/').apiBase, reservedBase);
  assert.equal(publicApiConfiguration(base).apiBase, base);
  for (const invalid of [reservedBase + '/extra', 'https://api.example.test/platform-lab/admin',
    'https://api.example.test/other/api', 'https://api.example.test/api/platform-lab/api',
    '/platform-lab/api', 'http://api.example.test/platform-lab/api', reservedBase + '?', reservedBase + '#']) {
    assert.equal(publicApiConfiguration(invalid).invalid, true, invalid);
  }
  const sample = JSON.parse(readFileSync(new URL('../src/data/snapshot.json', import.meta.url), 'utf8'));
  const observedAt = '2026-10-18T12:00:02Z';
  const run = { ...sample.runs[0], startedAt: observedAt, completedAt: observedAt };
  const detail = { ...sample.detail, ...run, observedAt };
  const calls: string[] = [];
  const read: typeof fetch = async (input, options) => {
    const url = publicGet(input, options); calls.push(url);
    if (url === reservedBase + '/demo/runs') return json({ items: [run], observedAt });
    if (url === reservedBase + '/demo/runs/' + run.id) return json(detail);
    if (url === reservedBase + '/platform/summary') return json({ ...sample.summary, status: 'UP', observedAt });
    if (url === reservedBase + '/platform/releases') return json({ items: [], observedAt });
    if (url === reservedBase + '/jobs/observation') return json(job());
    if (url === reservedBase + '/kafka/observation') return json(kafka());
    throw new Error('UNEXPECTED_RESERVED_TEST_URL');
  };
  context.mock.method(globalThis, 'fetch', read);
  const lab = await fetchLab(publicApiConfiguration(reservedBase).apiBase);
  const jobs = await loadJobObservation({ url: publicReadUrl(reservedBase, '/jobs/observation')!,
    fetcher: read, rejectRedirects: true });
  const broker = await loadKafkaObservation({ url: publicReadUrl(reservedBase, '/kafka/observation')!,
    apiBase: reservedBase, nowMs: now, allowIsolated: false, fetcher: read, rejectRedirects: true });
  assert.equal(lab.detail.inputCount, 12); assert.equal(lab.detail.successCount, 7);
  assert.equal(jobs.browserError, null); assert.equal(jobs.record?.sourceCommit, job().sourceCommit);
  assert.equal(broker.browserError, null); assert.deepEqual({ ...broker.record }, kafka());
  assert.deepEqual([...calls].sort(), ['/demo/runs', '/demo/runs/' + run.id, '/platform/summary',
    '/platform/releases', '/jobs/observation', '/kafka/observation'].map(path => reservedBase + path).sort());
  for (const path of ['/admin', '/jobs/observation?run=x', '/kafka/observation#x', '/demo/runs/a%2Fb']) {
    assert.equal(publicReadUrl(reservedBase, path), null);
    await assert.rejects(getJson(reservedBase, path));
  }
  assert.equal(calls.length, 6, 'Rejected paths must not add transport calls');
});
