import assert from 'node:assert/strict';
import test from 'node:test';
import { createRequire } from 'node:module';
import { readFileSync } from 'node:fs';
import { pathToFileURL } from 'node:url';
import { API_ENDPOINTS, API_REQUEST_TIMEOUT_MS, MAX_API_RESPONSE_BYTES, ApiReadFailure, apiEndpointPath, readPublicApi } from '../src/data/public-api-reference.ts';

test('console restricts input to the existing public GET paths before making a request', async () => {
  assert.equal(API_ENDPOINTS.length, 6);
  for (const id of ['', '../private', 'a?token=x', 'A', 'a/b', 'a'.repeat(81), 'https://example.test']) {
    assert.equal(apiEndpointPath('detail', id), null);
  }
  assert.equal(apiEndpointPath('detail', 'a'.repeat(80)), `/demo/runs/${'a'.repeat(80)}`);
  let requests = 0;
  const fetcher = (async () => { requests++; throw new Error('unexpected request'); }) as typeof fetch;
  for (const base of ['http://example.test/api', 'https://example.test/api?token=x', 'invalid-public-api-base']) {
    await assert.rejects(readPublicApi(base, 'summary', undefined, fetcher), (error: unknown) => error instanceof ApiReadFailure && error.code === 'INVALID_TARGET');
  }
  await assert.rejects(readPublicApi('/api', 'detail', '../private', fetcher), (error: unknown) => error instanceof ApiReadFailure && error.code === 'INVALID_TARGET');
  assert.equal(requests, 0);
});

test('a direct JSON response retains request and server time and sends no browser credentials', async () => {
  let requests = 0;
  const capturedAt = '2026-10-24T00:00:00Z';
  const fetcher = (async (input, init) => {
    requests++;
    assert.equal(input, 'https://example.test/platform-lab/api/jobs/observation');
    assert.equal(init?.method, 'GET'); assert.equal(init?.credentials, 'omit');
    assert.equal(init?.redirect, 'error'); assert.equal(init?.cache, 'no-store');
    assert.deepEqual(init?.headers, { Accept: 'application/json' });
    assert.equal(init?.body, undefined);
    return new Response(JSON.stringify({ kind: 'job-observation', capturedAt, jobs: [] }), { headers: { 'content-type': 'application/json;charset=UTF-8' } });
  }) as typeof fetch;
  const result = await readPublicApi('https://example.test/platform-lab/api', 'jobs', undefined, fetcher);
  assert.equal(requests, 1); assert.equal(result.status, 200); assert.equal(result.responseTime, capturedAt);
  assert.equal(result.path, '/jobs/observation'); assert.ok(!Number.isNaN(Date.parse(result.receivedAt)));
  assert.equal(JSON.parse(result.json).kind, 'job-observation');
});

test('HTTP errors do not read or retain an upstream error body or retry', async () => {
  let requests = 0, cancelled = false;
  const fetcher = (async () => {
    requests++;
    return new Response(new ReadableStream({ cancel() { cancelled = true; } }), { status: 429 });
  }) as typeof fetch;
  await assert.rejects(readPublicApi('/api', 'kafka', undefined, fetcher), (error: unknown) => error instanceof ApiReadFailure && error.code === 'HTTP_ERROR' && error.status === 429 && error.message === 'HTTP_ERROR');
  assert.equal(requests, 1); assert.equal(cancelled, true);
});

test('streamed data cannot exceed the bound even without a content length', async () => {
  let cancelled = false;
  const fetcher = (async () => new Response(new ReadableStream({
    start(controller) { controller.enqueue(new Uint8Array(MAX_API_RESPONSE_BYTES)); controller.enqueue(new Uint8Array(1)); },
    cancel() { cancelled = true; },
  }), { headers: { 'content-type': 'application/json' } })) as typeof fetch;
  await assert.rejects(readPublicApi('/api', 'runs', undefined, fetcher), (error: unknown) => error instanceof ApiReadFailure && error.code === 'BODY_REJECTED');
  assert.equal(cancelled, true);
});

test('a stalled body is aborted at the fixed deadline instead of remaining a loading success', async context => {
  context.mock.timers.enable({ apis: ['setTimeout'] });
  let signal: AbortSignal | null = null;
  const fetcher = (async (_input, init) => {
    signal = init!.signal!;
    return new Response(new ReadableStream({ start(controller) {
      signal!.addEventListener('abort', () => controller.error(new Error('aborted')), { once: true });
    } }), { headers: { 'content-type': 'application/json' } });
  }) as typeof fetch;
  const request = readPublicApi('/api', 'summary', undefined, fetcher);
  const rejection = assert.rejects(request, (error: unknown) => error instanceof ApiReadFailure && error.code === 'TIMEOUT');
  await Promise.resolve();
  context.mock.timers.tick(API_REQUEST_TIMEOUT_MS);
  await rejection;
  assert.equal((signal as AbortSignal | null)?.aborted, true);
});

test('HTML, malformed JSON and transport errors stay fixed failures without a snapshot fallback', async () => {
  for (const response of [new Response('<h1>not JSON</h1>', { headers: { 'content-type': 'text/html' } }),
    new Response('{"items":', { headers: { 'content-type': 'application/json' } })]) {
    await assert.rejects(readPublicApi('/api', 'runs', undefined, (async () => response) as typeof fetch), (error: unknown) => error instanceof ApiReadFailure && error.code === 'INVALID_JSON');
  }
  await assert.rejects(readPublicApi('/api', 'runs', undefined, (async () => { throw new TypeError('PRIVATE_PROVIDER_DETAIL'); }) as typeof fetch),
    (error: unknown) => error instanceof ApiReadFailure && error.code === 'NETWORK_ERROR' && !error.message.includes('PRIVATE'));
});

const require = createRequire(import.meta.url);
const ts = require('typescript');
const { createElement } = require('react');
const { renderToStaticMarkup } = require('react-dom/server');
const sourceUrl = new URL('../src/components/ApiConsole.tsx', import.meta.url);
const source = readFileSync(sourceUrl, 'utf8');
const compiled = ts.transpileModule(source, { compilerOptions: { jsx: ts.JsxEmit.ReactJSX,
  module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022 }, reportDiagnostics: true });
assert.equal(compiled.diagnostics.length, 0);
let output = compiled.outputText.replace(/^import ['"][^'"]+\.css['"];?\s*$/gm, '');
output = output.replace(/from (['"])(react(?:\/jsx-runtime)?)\1/g,
  (_unused: string, _quote: string, name: string) => `from ${JSON.stringify(pathToFileURL(require.resolve(name)).href)}`);
output = output.replace(/from ['"]\.\.\/(data\/public-api-reference|lib\/public-api-base|lib\/api-run-choices)['"]/g,
  (_unused: string, name: string) => `from ${JSON.stringify(new URL(`../src/${name}.ts`, import.meta.url).href)}`);
const { default: Component } = await import(`data:text/javascript;base64,${Buffer.from(output).toString('base64')}`);

test('server rendering offers six accessible documents but no early input, response or automatic request', () => {
  const html = renderToStaticMarkup(createElement(Component, { apiBase: '/api' }));
  assert.equal((html.match(/class="button api-query"[^>]*disabled=""/g) ?? []).length, 6);
  assert.match(html, /<input[^>]*id="api-run-id"[^>]*disabled=""/);
  assert.match(html, /<select[^>]*id="api-run-select"[^>]*disabled=""/);
  assert.ok(html.includes('실행 목록 불러오기'));
  assert.equal((html.match(/아직 조회하지 않았습니다/g) ?? []).length, 6);
  assert.ok(html.includes('API 목차')); assert.ok(html.includes('화면 조작 준비 중입니다.'));
  assert.equal((html.match(/<details\b/g) ?? []).length, 6);
  assert.ok(!/<details[^>]*\bopen(?:\s|=|>)/.test(html));
  assert.ok(!html.includes('JSON 응답 수신'));
});

test('invalid configuration is visibly blocked before hydration', () => {
  const html = renderToStaticMarkup(createElement(Component, { apiBase: 'https://example.test/api?token=PRIVATE_CANARY' }));
  assert.ok(html.includes('요청을 차단한 상태입니다.'));
  assert.ok(!html.includes('PRIVATE_CANARY'));
});
