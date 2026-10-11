import assert from 'node:assert/strict';
import { execFileSync } from 'node:child_process';
import { mkdir, readFile, writeFile, appendFile } from 'node:fs/promises';
import { setTimeout as sleep } from 'node:timers/promises';
import { fileURLToPath } from 'node:url';
import { resolve } from 'node:path';

const root = fileURLToPath(new URL('../../', import.meta.url));
const local = resolve(root, '.local');
const artifacts = resolve(root, 'artifacts');
const base = process.env.LAB_BASE_URL || 'http://127.0.0.1:4310';
const expectedCommit = process.env.SOURCE_COMMIT || '';
const scenario = JSON.parse(await readFile(resolve(root, 'tests/scenarios/sensor-validation-v1.json'), 'utf8'));
const runPath = '/api/demo/runs/synthetic-v1-seed-42';
const command = process.argv[2];

function compose(args, options = {}) {
  return execFileSync('docker', ['compose', '--env-file', '.local/compose.env', ...args], {
    cwd: root, encoding: 'utf8', timeout: 180_000, ...options,
  });
}
function inspectField(id, template) {
  // Select a single field in memory; never print inspect, environment or config.
  return execFileSync('docker', ['inspect', '--format', template, id], {
    cwd: root, encoding: 'utf8', timeout: 10_000,
  }).trim();
}
async function override(address) {
  // Runner-only network proves API address changes. Production Compose is untouched.
  const content = `services:
  api:
    networks:
      default:
        ipv4_address: ${address}
networks:
  default:
    ipam:
      config:
        - subnet: 172.29.221.0/24
`;
  await writeFile(resolve(local, 'compose-ci.yaml'), content, { mode: 0o600 });
}
async function json(path) {
  const response = await fetch(new URL(path, base), { signal: AbortSignal.timeout(5000) });
  assert.equal(response.status, 200, `Expected HTTP 200 for ${path}`);
  return response.json();
}
async function wait() {
  const deadline = Date.now() + 180_000;
  let attempts = 0;
  while (Date.now() < deadline) {
    attempts++;
    try {
      const [summary, detail] = await Promise.all([json('/api/platform/summary'), json(runPath)]);
      assert.equal(summary.status, 'UP');
      assert.equal(summary.components.find(item => item.name === 'DATABASE')?.status, 'RUNNING');
      assert.equal(summary.components.find(item => item.name === 'DATABASE')?.detail, 'MariaDB');
      assert.equal(detail.inputCount, 12);
      console.log(`Same-origin API and MariaDB sample ready after ${attempts} bounded poll(s).`);
      return;
    } catch {
      // Startup, recreation and DNS refresh may temporarily return 502/503.
      await sleep(2000);
    }
  }
  throw new Error('Same-origin API readiness timed out after 180 seconds.');
}
async function check(phase) {
  assert.ok(['before', 'after'].includes(phase), 'Use check before or check after');
  assert.match(expectedCommit, /^[a-f0-9]{40}$/, 'SOURCE_COMMIT must be the actual checked-out commit SHA');
  const [list, detail, summary, releases] = await Promise.all([
    json('/api/demo/runs'), json(runPath), json('/api/platform/summary'), json('/api/platform/releases'),
  ]);
  assert.equal(list.items.length, 1, 'Bootstrap must create exactly one persisted run');
  assert.equal(list.items[0].id, detail.id);
  for (const [key, value] of Object.entries(scenario.expected)) assert.equal(detail[key], value, key);
  assert.equal(detail.inputCount, detail.successCount + detail.failureCount + detail.duplicateCount + detail.pendingCount);
  assert.equal(detail.series.length, 7);
  assert.deepEqual(detail.outcomes.map(({ sequence, status, reason }) => ({ sequence, status, reason })), scenario.expectedOutcomes);
  assert.equal(summary.environment, 'compose');
  assert.equal(summary.status, 'UP');
  assert.equal(summary.publicExecutionEnabled, false);
  assert.equal(summary.sourceCommit, expectedCommit);
  assert.equal(summary.components.find(item => item.name === 'DATABASE')?.detail, 'MariaDB');
  assert.equal(summary.components.find(item => item.name === 'DATABASE')?.status, 'RUNNING');
  assert.equal(releases.items[0].sourceCommit, expectedCommit);
  assert.equal(compose(['exec', '-T', 'api', 'id', '-u']).trim(), '10001', 'API must run as its non-root user');
  assert.equal(compose(['exec', '-T', 'api', 'id', '-g']).trim(), '10001');
  assert.equal(compose(['exec', '-T', 'web', 'id', '-u']).trim(), '101', 'Nginx must run as its non-root user');
  assert.equal(compose(['exec', '-T', 'web', 'id', '-g']).trim(), '101');
  for (const name of ['JENKINS', 'ARGO_CD', 'KUBERNETES']) {
    assert.equal(summary.components.find(item => item.name === name)?.status, 'NOT_CONFIGURED');
  }
  const rejected = await fetch(new URL('/api/demo/runs', base), {
    method: 'POST', body: '{}', headers: { 'Content-Type': 'application/json' }, signal: AbortSignal.timeout(5000),
  });
  assert.equal(rejected.status, 405, 'Public POST must be rejected');
  const capture = { capturedAt: new Date().toISOString(), sourceCommit: expectedCommit, phase, list, detail, summary, releases, publicPostStatus: rejected.status };
  if (phase === 'after') {
    const before = JSON.parse(await readFile(resolve(artifacts, 'compose-before.json'), 'utf8'));
    const stable = ({ observedAt, ...stored }) => stored;
    assert.deepEqual(stable(detail), stable(before.detail), 'Stored run times and every outcome must survive API recreation unchanged');
    assert.deepEqual(list.items, before.list.items, 'Restart must not create another run');
    assert.notEqual(releases.items[0].startedAt, before.releases.items[0].startedAt, 'Runtime must have restarted');
    const previousContainers = JSON.parse(await readFile(resolve(local, 'recreate-before.json'), 'utf8'));
    const apiId = compose(['ps', '-q', 'api']).trim();
    const webId = compose(['ps', '-q', 'web']).trim();
    assert.notEqual(apiId, previousContainers.apiId, 'API container must be replaced');
    assert.equal(webId, previousContainers.webId, 'Nginx container must stay running');
    assert.equal(inspectField(webId, '{{.State.StartedAt}}'), previousContainers.webStartedAt, 'Nginx must not restart');
    const apiAddress = inspectField(apiId, '{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}');
    assert.notEqual(apiAddress, previousContainers.apiAddress, 'API address must change to prove DNS refresh');
    capture.apiContainerRecreated = true;
    capture.apiAddressChanged = true;
    capture.nginxContainerUnchanged = true;
    capture.persistedSampleUnchanged = true;
  }
  await mkdir(artifacts, { recursive: true });
  await writeFile(resolve(artifacts, `compose-${phase}.json`), JSON.stringify(capture, null, 2) + '\n');
  if (process.env.GITHUB_STEP_SUMMARY) {
    await appendFile(process.env.GITHUB_STEP_SUMMARY,
      `- Compose ${phase}: MariaDB, input 12 = success 7 + failed 3 + duplicate 2 + pending 0, POST 405, source commit verified${phase === 'after' ? ', API address changed; Nginx and persisted results unchanged' : ''}.
`);
  }
  console.log(`Compose ${phase} verified: MariaDB, 12=7+3+2+0, POST 405, source commit matches.`);
}
async function recreate() {
  const apiId = compose(['ps', '-q', 'api']).trim();
  const webId = compose(['ps', '-q', 'web']).trim();
  assert.ok(apiId && webId, 'Both API and Nginx must exist before recreation');
  const state = {
    apiId, webId,
    apiAddress: inspectField(apiId, '{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}'),
    webStartedAt: inspectField(webId, '{{.State.StartedAt}}'),
  };
  await writeFile(resolve(local, 'recreate-before.json'), JSON.stringify(state), { mode: 0o600 });
  await override('172.29.221.11');
  compose(['up', '-d', '--no-deps', '--force-recreate', 'api'], { stdio: 'inherit' });
  console.log('Recreated API only; waiting for existing Nginx to refresh its upstream address.');
}

if (command === 'prepare') {
  await mkdir(local, { recursive: true });
  await override('172.29.221.10');
  console.log('Prepared runner-only Compose network override; no credentials printed.');
} else if (command === 'wait') await wait();
else if (command === 'check') await check(process.argv[3]);
else if (command === 'recreate') await recreate();
else throw new Error('Use prepare, wait, check before|after, or recreate');
