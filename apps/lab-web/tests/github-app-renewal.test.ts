import assert from 'node:assert/strict';
import test from 'node:test';
import { parseGitHubAppRenewal } from '../src/lib/github-app-renewal.ts';

// Synthetic contract fixtures, not substitutes for the separately reviewed live proof.
const fixture = (): any => ({ schemaVersion: 1, status: 'NATURAL_EXPIRY_REFRESH_VERIFIED', scope: 'canonical-credential-access',
  observedAt: '2026-10-23T10:19:30Z', oldExpiresAt: '2026-10-23T10:18:35Z', oldHttp: { status: 401, at: '2026-10-23T10:19:28Z' },
  refresh: { nativeAccessCount: 1, tokenChanged: true, cacheObjectChanged: true },
  newHttp: { status: 200, at: '2026-10-23T10:19:30Z', repositoryIdentityMatches: true }, newExpiresAt: '2026-10-23T11:19:30Z', validitySeconds: 3600,
  preservation: { credentialStoreMembership: true, jobConfiguration: true, jobState: true, privateInputs: true },
  operations: { forcedExpiration: false, credentialUpdate: false, statusWrite: false, build: false, rawValueOutput: false, automaticRetry: false } });

test('complete historical proof is accepted without mutating its source', () => {
  const value = fixture(); const original = JSON.stringify(value);
  assert.equal(parseGitHubAppRenewal(value), value);
  assert.equal(JSON.stringify(value), original);
});
test('a status label cannot turn partial, forced or wrong-scope records into success', () => {
  for (const value of [null, [], {}, { ...fixture(), schemaVersion: 2 }, { ...fixture(), status: 'PENDING' }, { ...fixture(), scope: 'build' }]) assert.equal(parseGitHubAppRenewal(value), null);
  for (const section of ['refresh', 'preservation', 'operations']) for (const key of Object.keys(fixture()[section])) {
    const missing = fixture(); delete missing[section][key]; assert.equal(parseGitHubAppRenewal(missing), null);
    const wrong = fixture(); wrong[section][key] = !wrong[section][key]; assert.equal(parseGitHubAppRenewal(wrong), null);
  }
  const twice = fixture(); twice.refresh.nativeAccessCount = 2; assert.equal(parseGitHubAppRenewal(twice), null);
});
test('old rejection, new acceptance and exact repository are all required', () => {
  for (const [section, key, replacement] of [['oldHttp', 'status', 200], ['newHttp', 'status', 401], ['newHttp', 'repositoryIdentityMatches', false]]) {
    const value = fixture(); value[section as string][key as string] = replacement; assert.equal(parseGitHubAppRenewal(value), null);
  }
});
test('early rejection, reversed requests and relabelled observation fail closed', () => {
  for (const [section, key, time] of [
    ['oldHttp', 'at', '2026-10-23T10:18:34Z'], ['newHttp', 'at', '2026-10-23T10:19:27Z'],
    ['', 'observedAt', '2026-10-23T10:19:29Z'], ['', 'observedAt', '2026-10-23T11:19:30Z'],
  ]) { const value = fixture(); (section ? value[section] : value)[key] = time; assert.equal(parseGitHubAppRenewal(value), null); }
});
test('whole UTC timestamps and an independently consistent one-hour lifetime are required', () => {
  for (const time of ['now', '2026-02-30T10:19:30Z', '2026-10-23T19:19:30+09:00', '2026-10-23T10:19:30.000Z']) {
    const value = fixture(); value.observedAt = time; assert.equal(parseGitHubAppRenewal(value), null);
  }
  for (const [key, replacement] of [['newExpiresAt', '2026-10-23T11:19:29Z'], ['newExpiresAt', '2026-10-23T11:19:31Z'], ['validitySeconds', 60], ['validitySeconds', '3600']]) {
    const value = fixture(); value[key] = replacement; assert.equal(parseGitHubAppRenewal(value), null);
  }
});
test('unknown fields are rejected at every public boundary', () => {
  for (const path of ['', 'oldHttp', 'refresh', 'newHttp', 'preservation', 'operations']) {
    const value = fixture(); (path ? value[path] : value).token = 'must-not-be-public'; assert.equal(parseGitHubAppRenewal(value), null);
  }
});
