import assert from 'node:assert/strict';
import { test } from 'node:test';
import { getJson, liveFailureOf } from '../src/lib/api.ts';

const canary = 'PRIVATE_HTTP_BODY_PROVIDER_CANARY';

test('HTTP error bodies are discarded without replacing the observed failure', { concurrency: false, timeout: 2000 }, async context => {
  for (const behavior of ['pending', 'reject', 'throw'] as const) {
    await context.test(behavior, { timeout: 1000 }, async () => {
      const controller = new AbortController();
      const status = behavior === 'pending' ? 503 : behavior === 'reject' ? 429 : 500;
      let applicationReads = 0; let cancellations = 0; let calls = 0;
      const response = new Response(new ReadableStream<Uint8Array>({
        // A native stream may pull ahead; this test makes no upstream byte claim.
        pull(source) { source.enqueue(new TextEncoder().encode(canary)); },
        cancel() {
          cancellations++;
          if (behavior === 'pending') return new Promise<void>(() => {});
          controller.abort(new Error(canary));
          if (behavior === 'reject') return Promise.reject(new Error(canary));
          throw new Error(canary);
        },
      }), { status });
      for (const method of ['json', 'text'] as const) {
        const original = response[method].bind(response);
        Object.defineProperty(response, method, { value: () => { applicationReads++; return original(); } });
      }
      const body = response.body!;
      const nativeGetReader = body.getReader;
      Object.defineProperty(body, 'getReader', { value: (...args: unknown[]) => {
        applicationReads++;
        return Reflect.apply(nativeGetReader, body, args);
      } });
      const originalFetch = globalThis.fetch;
      globalThis.fetch = async (url, options) => {
        calls++;
        assert.equal(url, '/api/demo/runs');
        assert.equal(options?.signal, controller.signal);
        return response;
      };
      try {
        await assert.rejects(getJson('/api', '/demo/runs', controller.signal), error => {
          const failure = liveFailureOf(error);
          assert.deepEqual(failure, { kind: 'HTTP_REJECTED', httpStatus: status });
          assert.equal(JSON.stringify(failure).includes(canary), false);
          assert.equal(String(error).includes(canary), false);
          return true;
        });
        assert.equal(calls, 1);
        assert.equal(applicationReads, 0);
        assert.equal(cancellations, 1);
        assert.equal(controller.signal.aborted, behavior !== 'pending');
      } finally {
        globalThis.fetch = originalFetch;
      }
    });
  }
});
