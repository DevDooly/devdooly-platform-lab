import assert from 'node:assert/strict';
import test from 'node:test';
import { buildApiRequestCommand } from '../src/lib/api-request-command.ts';
import type { ApiEndpointId } from '../src/data/public-api-reference.ts';

const base = 'https://api.example.test/platform-lab/api';
const runId = 'selected-run.alpha_01';
const shells = ['posix', 'powershell'] as const;
// Inspect command text only. No command, shell, or HTTP request is executed.
function commandArguments(command: string | null): string[] {
  assert.ok(command);
  assert.equal(/[\r\n\t]/.test(command), false);
  return command.match(/'[^']*'|[^ ]+/g)!;
}
function assertCommand(command: string | null, executable: string, url: string) {
  assert.deepEqual(commandArguments(command), [executable, '-q', '--request', 'GET', '--header', "'Accept: application/json'",
    '--connect-timeout', '5', '--max-time', '8', '--silent', '--show-error', '--fail', '--url', `'${url}'`]);
}

test('all six public paths have one bounded GET command with curlrc disabled as the first option in either shell', () => {
  const paths: [ApiEndpointId, string][] = [
    ['runs', '/demo/runs'], ['detail', `/demo/runs/${runId}`], ['summary', '/platform/summary'],
    ['releases', '/platform/releases'], ['jobs', '/jobs/observation'], ['kafka', '/kafka/observation'],
  ];
  for (const shell of shells) for (const [endpoint, path] of paths) {
    assertCommand(buildApiRequestCommand(base, endpoint, runId, shell), shell === 'posix' ? 'curl' : 'curl.exe', base + path);
  }
});

test('detail commands follow the current raw ID and accept only the existing one-to-eighty-character public ID contract', () => {
  for (const id of ['0', 'a'.repeat(80), 'run._-9', 'new-selected-run']) {
    assertCommand(buildApiRequestCommand(base, 'detail', id, 'posix'), 'curl', `${base}/demo/runs/${id}`);
  }
  for (const id of ['', 'A', '-run', 'a'.repeat(81), '../run', 'run/other', 'run?x=1', 'run#x', 'run%2fother',
    'run\n', 'run\r\n', 'ru\nn', "run'", 'run"', 'run$HOME', 'run`id`', 'run;id', 'run\\other']) {
    for (const shell of shells) assert.equal(buildApiRequestCommand(base, 'detail', id, shell), null, id);
  }
  assertCommand(buildApiRequestCommand(base, 'summary', 'irrelevant;draft\n', 'posix'), 'curl', `${base}/platform/summary`);
});

test('relative api requires an exact HTTPS origin and revalidates the resulting absolute public configuration', () => {
  for (const relative of ['/api', '/api/']) for (const shell of shells) {
    assertCommand(buildApiRequestCommand(relative, 'detail', runId, shell, 'https://site.example.test'),
      shell === 'posix' ? 'curl' : 'curl.exe', `https://site.example.test/api/demo/runs/${runId}`);
  }
  for (const origin of [undefined, '', 'null', 'http://localhost:4321', 'http://site.example.test',
    'https://site.example.test/', 'https://site.example.test/path', 'https://site.example.test?x=1',
    'https://site.example.test#x', 'https://user:password@site.example.test',
    'https://SITE.example.test', 'https://site.example.test:443', 'https://site.example.test:8443',
    'https://127.0.0.1', 'https://localhost', 'https://service.internal', 'https://api.svc.cluster.local']) {
    assert.equal(buildApiRequestCommand('/api', 'runs', runId, 'posix', origin), null, String(origin));
  }
});

test('unsafe schemes, credentials, queries, private hosts, ports, and nonpublic bases cannot become commands', () => {
  for (const invalid of ['', 'http://api.example.test/api', 'ftp://api.example.test/api', '//api.example.test/api',
    'https://user:secret@api.example.test/api', 'https://@api.example.test/api',
    'https://api.example.test/api?token=secret', 'https://api.example.test/api#part',
    'https://api.example.test/admin', 'https://api.example.test:8443/api', 'https://127.0.0.1/api',
    'https://localhost/api', 'https://api.internal/api', 'invalid-public-api-base']) {
    assert.equal(buildApiRequestCommand(invalid, 'jobs', runId, 'posix'), null, invalid);
  }
  assertCommand(buildApiRequestCommand('https://api.example.test/api/', 'jobs', runId, 'posix'),
    'curl', 'https://api.example.test/api/jobs/observation');
});

test('ASCII URL whitelist rejects shell metacharacters and controls before URL normalization can erase them', () => {
  const forbidden = ["'", '"', '$', '`', ';', '\\', '\n', '\r', '\t', '\0', ' ', '|', '&', '<', '>', '(', ')',
    '%0a', '%27', '%24', '%60', '\u2028', '한'];
  for (const token of forbidden) {
    const invalidBase = `https://api.exa${token}mple.test/api`;
    const invalidOrigin = `https://site.exa${token}mple.test`;
    for (const shell of shells) {
      assert.equal(buildApiRequestCommand(invalidBase, 'runs', runId, shell), null, JSON.stringify(token));
      assert.equal(buildApiRequestCommand('/api', 'runs', runId, shell, invalidOrigin), null, JSON.stringify(token));
      assert.equal(buildApiRequestCommand('https://api.example.test/api' + token, 'runs', runId, shell), null, JSON.stringify(token));
    }
  }
});

test('unknown endpoint or shell cannot select another executable or add command options', () => {
  for (const shell of ['', 'cmd', 'pwsh', 'PowerShell', 'powershell\n', 'posix;other'] as unknown as ('posix' | 'powershell')[]) {
    assert.equal(buildApiRequestCommand(base, 'runs', runId, shell), null, shell);
  }
  for (const endpoint of ['unknown', '../admin', 'runs --insecure', 'detail\n'] as ApiEndpointId[]) {
    assert.equal(buildApiRequestCommand(base, endpoint, runId, 'posix'), null, endpoint);
  }
  const posix = buildApiRequestCommand(base, 'detail', runId, 'posix');
  const powershell = buildApiRequestCommand(base, 'detail', runId, 'powershell');
  assert.ok(posix); assert.equal(powershell, posix.replace(/^curl /, 'curl.exe '));
});
