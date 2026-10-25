import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';
import { fetchLab, fetchLabForRun, liveFailureOf } from '../src/lib/api.ts';
import type { LabData, Run, RunDetail } from '../src/lib/api.ts';

// Existing synthetic fixture supplies content only; these timestamps and responses are test inputs.
const fixture: LabData = JSON.parse(readFileSync(new URL('../src/data/snapshot.json', import.meta.url), 'utf8'));
const observedAt = '2026-10-26T00:00:03Z';
const base = 'https://example.invalid/api';
const target = 'shared-outside-recent-list';
const run: Run = { ...fixture.runs[0]!, startedAt: '2026-10-26T00:00:00Z', completedAt: '2026-10-26T00:00:01Z' };
const detail: RunDetail = { ...fixture.detail, ...run, id: target, observedAt };
const summary = { ...fixture.summary, status: 'UP', observedAt: '2026-10-26T00:00:02Z' };
const releases = [{ service: 'api', version: '0.1.0', sourceCommit: 'a'.repeat(40), imageDigest: null,
  deploymentStatus: 'RUNTIME_ONLY', startedAt: run.startedAt }];
const metadataPaths = ['/demo/runs', '/platform/summary', '/platform/releases'];
const targetPath = `/demo/runs/${target}`;
const json = (value: unknown) => new Response(JSON.stringify(value), { headers: { 'Content-Type': 'application/json' } });
function payloads(runs: Run[] = [run]): Record<string, unknown> {
  return { '/demo/runs': { items: runs, observedAt }, '/platform/summary': summary,
    '/platform/releases': { items: releases, observedAt }, [targetPath]: detail };
}
type Call = { path: string; options: RequestInit | undefined };
async function withFetch(
  respond: (path: string, options: RequestInit | undefined) => Response | Promise<Response>,
  action: (calls: Call[]) => Promise<void>,
) {
  const original = globalThis.fetch; const calls: Call[] = [];
  globalThis.fetch = async (input, options) => {
    const url = String(input);
    assert.ok(url.startsWith(base + '/'), 'Every request stays on the configured public API');
    const path = url.slice(base.length); calls.push({ path, options });
    assert.equal(options?.method ?? 'GET', 'GET');
    assert.equal(options?.credentials, 'omit'); assert.equal(options?.redirect, 'error');
    assert.equal(options?.cache, 'no-store');
    return respond(path, options);
  };
  try { await action(calls); } finally { globalThis.fetch = original; }
}
function fromPayloads(values: Record<string, unknown>) {
  return (path: string) => {
    assert.ok(Object.hasOwn(values, path), `Unexpected request: ${path}`);
    return json(values[path]);
  };
}
function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>(accept => { resolve = accept; });
  return { promise, resolve };
}
function abortedResponse(signal: AbortSignal | null | undefined): Promise<Response> {
  assert.ok(signal);
  return new Promise((_resolve, reject) => {
    if (signal.aborted) reject(signal.reason);
    else signal.addEventListener('abort', () => reject(signal.reason), { once: true });
  });
}

test('shared context performs exactly three metadata GETs and the requested detail, including outside or empty recent lists', async () => {
  for (const listed of [[run], [], [{ ...run, id: target }]]) {
    const values = payloads(listed);
    await withFetch(fromPayloads(values), async calls => {
      const result = await fetchLabForRun(base + '/', target);
      assert.deepEqual(calls.map(call => call.path), [...metadataPaths, targetPath]);
      assert.deepEqual(result, { runs: listed, summary, releases, observedAt: summary.observedAt, detail });
      assert.equal('capturedAt' in result, false); assert.equal('snapshotNote' in result, false);
    });
  }
});

test('all metadata starts together but no detail starts or LabData resolves until its preceding phase succeeds', { timeout: 2000 }, async () => {
  const values = payloads();
  const metadataReady = deferred<Response>(), detailReady = deferred<Response>(), detailRequested = deferred<void>();
  await withFetch((path) => {
    if (path === '/platform/releases') return metadataReady.promise;
    if (path === targetPath) { detailRequested.resolve(); return detailReady.promise; }
    return fromPayloads(values)(path);
  }, async calls => {
    let resolved = false;
    const pending = fetchLabForRun(base, target).then(result => { resolved = true; return result; });
    assert.deepEqual(calls.map(call => call.path), metadataPaths);
    assert.equal(resolved, false);
    metadataReady.resolve(json(values['/platform/releases']));
    await detailRequested.promise;
    assert.equal(resolved, false, 'A successful metadata batch is not a complete LabData result');
    assert.deepEqual(calls.map(call => call.path), [...metadataPaths, targetPath]);
    detailReady.resolve(json(detail));
    assert.deepEqual((await pending).detail, detail);
  });
});

test('each invalid metadata or detail payload rejects the complete context without selecting a default run', async () => {
  const invalid: [string, unknown][] = [
    ['/demo/runs', { items: [{ ...run, inputCount: 999 }], observedAt }],
    ['/demo/runs', { items: [run], observedAt: null }],
    ['/platform/summary', { ...summary, observedAt: null }],
    ['/platform/releases', { items: [{ ...releases[0], startedAt: null }], observedAt }],
    ['/platform/releases', { items: releases, observedAt: null }],
    [targetPath, { ...detail, outcomes: [{ ...detail.outcomes[0], status: 'INVENTED' }] }],
  ];
  for (const [path, value] of invalid) {
    await withFetch(fromPayloads({ ...payloads(), [path]: value }), async calls => {
      await assert.rejects(fetchLabForRun(base, target), error => {
        assert.deepEqual(liveFailureOf(error), { kind: 'INVALID_RESPONSE', httpStatus: null }); return true;
      });
      assert.deepEqual(calls.map(call => call.path), path === targetPath ? [...metadataPaths, targetPath] : metadataPaths);
    });
  }
});

test('HTTP 429 at metadata or exact detail is returned once without retry, fallback, or private response content', async () => {
  for (const failedPath of ['/platform/summary', targetPath]) {
    const values = payloads();
    await withFetch(path => path === failedPath ? new Response('PRIVATE_RESPONSE_CANARY', { status: 429 }) : fromPayloads(values)(path), async calls => {
      await assert.rejects(fetchLabForRun(base, target), error => {
        assert.deepEqual(liveFailureOf(error), { kind: 'HTTP_REJECTED', httpStatus: 429 });
        assert.ok(error instanceof Error); assert.equal(error.message.includes('PRIVATE_RESPONSE_CANARY'), false);
        return true;
      });
      assert.deepEqual(calls.map(call => call.path), failedPath === targetPath ? [...metadataPaths, targetPath] : metadataPaths);
    });
  }
});

test('a valid but differently identified detail is rejected even if its ID is in the recent list', async () => {
  await withFetch(fromPayloads({ ...payloads(), [targetPath]: { ...detail, id: run.id } }), async calls => {
    await assert.rejects(fetchLabForRun(base, target), error => {
      assert.deepEqual(liveFailureOf(error), { kind: 'INVALID_RESPONSE', httpStatus: null }); return true;
    });
    assert.deepEqual(calls.map(call => call.path), [...metadataPaths, targetPath]);
  });
});

test('cancellation reaches both request phases and cannot produce partial context or another detail request', { timeout: 2000 }, async () => {
  for (const waitingPath of ['/platform/summary', targetPath]) {
    const controller = new AbortController(), waiting = deferred<void>(), values = payloads();
    await withFetch((path, options) => {
      if (path === waitingPath) { waiting.resolve(); return abortedResponse(options?.signal); }
      return fromPayloads(values)(path);
    }, async calls => {
      const pending = fetchLabForRun(base, target, controller.signal);
      await waiting.promise;
      const rejected = assert.rejects(pending, error => {
        assert.deepEqual(liveFailureOf(error), { kind: 'REQUEST_ABORTED', httpStatus: null }); return true;
      });
      controller.abort(new Error('test cancellation')); await rejected;
      assert.ok(calls.every(call => call.options?.signal === controller.signal));
      assert.deepEqual(calls.map(call => call.path), waitingPath === targetPath ? [...metadataPaths, targetPath] : metadataPaths);
    });
  }
});

test('ordinary fetchLab keeps preferred-list selection, first-run fallback, and the empty-list failure contract', async () => {
  const other: Run = { ...run, id: 'second-listed-run' };
  for (const [preferred, expected] of [[undefined, run.id], ['missing-preference', run.id], [other.id, other.id]] as const) {
    const values = { ...payloads([run, other]), [`/demo/runs/${run.id}`]: { ...detail, id: run.id },
      [`/demo/runs/${other.id}`]: { ...detail, id: other.id } };
    await withFetch(fromPayloads(values), async calls => {
      const result = await fetchLab(base, undefined, preferred);
      assert.equal(result.detail.id, expected);
      assert.deepEqual(calls.map(call => call.path), [...metadataPaths, `/demo/runs/${expected}`]);
    });
  }
  await withFetch(fromPayloads(payloads([])), async calls => {
    await assert.rejects(fetchLab(base, undefined, target), error => {
      assert.ok(error instanceof Error); assert.equal(error.message, '아직 저장된 실행 결과가 없습니다.');
      assert.deepEqual(liveFailureOf(error), { kind: 'OTHER', httpStatus: null }); return true;
    });
    assert.deepEqual(calls.map(call => call.path), metadataPaths);
  });
});
