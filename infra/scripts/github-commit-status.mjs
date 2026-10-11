#!/usr/bin/env node
// Only a repository-scoped commit-status credential is accepted through the
// environment. Never pass tokens as arguments or print raw HTTP responses.
import fs from 'node:fs';
import path from 'node:path';
import { pathToFileURL } from 'node:url';

const repository = 'DevDooly/devdooly-platform-lab';
const context = 'ci/jenkins-test';
const descriptions = {
  pending: 'validation in progress',
  success: 'tests and artifacts verified',
  failure: 'validation failed',
  error: 'validation aborted',
};

export function payloadFor({ sha, state, buildNumber }) {
  if (!/^[0-9a-f]{40}$/.test(sha || '')) throw new Error('INVALID_SOURCE_SHA');
  if (!Object.hasOwn(descriptions, state)) throw new Error('INVALID_STATUS_STATE');
  if (!/^[1-9][0-9]*$/.test(buildNumber || '')) throw new Error('INVALID_BUILD_NUMBER');
  return { state, context, description: `Jenkins build #${buildNumber}: ${descriptions[state]}` };
}

export async function sendStatus({ sha, state, buildNumber, token, output }, fetcher = fetch) {
  const payload = payloadFor({ sha, state, buildNumber });
  if (typeof token !== 'string' || !token || /[\r\n]/.test(token)) throw new Error('STATUS_CREDENTIAL_MISSING');
  let response;
  try {
    response = await fetcher(`https://api.github.com/repos/${repository}/statuses/${sha}`, {
      method: 'POST', redirect: 'error', signal: AbortSignal.timeout(30_000),
      headers: {
        Accept: 'application/vnd.github+json',
        Authorization: `Bearer ${token}`,
        'User-Agent': 'devdooly-lab-jenkins-status',
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(payload),
    });
  } catch {
    throw new Error('STATUS_REQUEST_UNAVAILABLE');
  }
  if (response.status !== 201) throw new Error(`STATUS_HTTP_${response.status}`);
  let created;
  try { created = await response.json(); } catch { throw new Error('INVALID_STATUS_RESPONSE'); }
  if (created.state !== state || created.context !== context || !Number.isSafeInteger(created.id) || created.id < 1
    || !/^[A-Za-z0-9][A-Za-z0-9-]{0,38}(?:\[bot\])?$/.test(created.creator?.login || '')) {
    throw new Error('STATUS_RESPONSE_MISMATCH');
  }
  const evidence = {
    schemaVersion: 1, sourceCommit: sha, buildNumber: Number(buildNumber),
    state, context, statusId: created.id, issuer: created.creator.login,
  };
  if (output) {
    fs.mkdirSync(path.dirname(output), { recursive: true });
    fs.writeFileSync(output, `${JSON.stringify(evidence, null, 2)}\n`, { encoding: 'utf8', mode: 0o600 });
  }
  return evidence;
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  try {
    const evidence = await sendStatus({
      sha: process.env.SOURCE_COMMIT, state: process.env.CI_STATUS,
      buildNumber: process.env.BUILD_NUMBER, token: process.env.GITHUB_STATUS_TOKEN,
      output: process.env.CI_STATUS_OUTPUT,
    });
    console.log(JSON.stringify(evidence));
  } catch (error) {
    // Every error constructed above contains a fixed diagnostic, not a response.
    const safe = /^[A-Z_]+(?:_[0-9]{3})?$/.test(error?.message || '') ? error.message : 'STATUS_CLIENT_FAILED';
    console.error(safe);
    process.exitCode = 1;
  }
}
