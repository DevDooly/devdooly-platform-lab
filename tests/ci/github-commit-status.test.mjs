import test from 'node:test';
import assert from 'node:assert/strict';
import { payloadFor, sendStatus } from '../../infra/scripts/github-commit-status.mjs';

const base = { sha: 'a'.repeat(40), buildNumber: '4' };
const fakeCredential = 'unit-test-only-not-a-real-token';

test('success status states that both tests and artifacts were verified', () => {
  assert.deepEqual(payloadFor({ ...base, state: 'success' }), {
    state: 'success', context: 'ci/jenkins-test', description: 'Jenkins build #4: tests and artifacts verified',
  });
});
test('input SHA, state and build number cannot inject URLs or output', () => {
  for (const override of [{ sha: 'unknown' }, { sha: `${base.sha}\nx` }, { buildNumber: '4\nx' }, { state: 'passed' }]) {
    assert.throws(() => payloadFor({ ...base, state: 'success', ...override }));
  }
});
test('missing credential does not perform a request', async () => {
  let requests = 0;
  await assert.rejects(sendStatus({ ...base, state: 'success', token: '' }, async () => { requests += 1; }), /STATUS_CREDENTIAL_MISSING/);
  assert.equal(requests, 0);
});
test('only fixed status API receives the credential, with redirects forbidden', async () => {
  let request;
  const evidence = await sendStatus({ ...base, state: 'success', token: fakeCredential }, async (url, options) => {
    request = { url, options };
    return { status: 201, json: async () => ({ id: 12, state: 'success', context: 'ci/jenkins-test', creator: { login: 'ci-bot[bot]' } }) };
  });
  assert.equal(request.url, `https://api.github.com/repos/DevDooly/devdooly-platform-lab/statuses/${base.sha}`);
  assert.equal(request.options.redirect, 'error');
  assert.equal(evidence.statusId, 12);
  assert.ok(!JSON.stringify(evidence).includes(fakeCredential));
});
test('raw HTTP response and network diagnostic are never reflected', async () => {
  const options = { ...base, state: 'failure', token: fakeCredential };
  await assert.rejects(sendStatus(options, async () => ({ status: 403, text: () => fakeCredential })), /^Error: STATUS_HTTP_403$/);
  await assert.rejects(sendStatus(options, async () => { throw new Error(fakeCredential); }), /^Error: STATUS_REQUEST_UNAVAILABLE$/);
});
test('mismatched status response cannot be called confirmed success', async () => {
  await assert.rejects(sendStatus({ ...base, state: 'success', token: fakeCredential }, async () => ({
    status: 201, json: async () => ({ id: 12, state: 'pending', context: 'ci/jenkins-test', creator: { login: 'ci-bot[bot]' } }),
  })), /STATUS_RESPONSE_MISMATCH/);
});
