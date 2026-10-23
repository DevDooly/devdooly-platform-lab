/** Public historical proof only. This parser never accesses Jenkins or GitHub. */
export interface GitHubAppRenewalRecord {
  schemaVersion: 1;
  status: 'NATURAL_EXPIRY_REFRESH_VERIFIED';
  scope: 'canonical-credential-access';
  observedAt: string;
  oldExpiresAt: string;
  oldHttp: { status: 401; at: string };
  refresh: { nativeAccessCount: 1; tokenChanged: true; cacheObjectChanged: true };
  newHttp: { status: 200; at: string; repositoryIdentityMatches: true };
  newExpiresAt: string;
  validitySeconds: 3600;
  preservation: { credentialStoreMembership: true; jobConfiguration: true; jobState: true; privateInputs: true };
  operations: { forcedExpiration: false; credentialUpdate: false; statusWrite: false; build: false; rawValueOutput: false; automaticRetry: false };
}
const object = (value: unknown): value is Record<string, unknown> => value !== null && typeof value === 'object' && !Array.isArray(value);
const exact = (value: Record<string, unknown>, keys: readonly string[]) => Object.keys(value).length === keys.length && keys.every(key => Object.hasOwn(value, key));
const fixed = (value: unknown, expected: Record<string, unknown>) => object(value) && exact(value, Object.keys(expected))
  && Object.entries(expected).every(([key, item]) => value[key] === item);
function utcSecond(value: unknown): value is string {
  if (typeof value !== 'string' || !/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$/.test(value)) return false;
  const date = new Date(value);
  return Number.isFinite(date.getTime()) && date.toISOString() === value.replace('Z', '.000Z');
}
export function parseGitHubAppRenewal(value: unknown): GitHubAppRenewalRecord | null {
  if (!object(value) || !exact(value, ['schemaVersion', 'status', 'scope', 'observedAt', 'oldExpiresAt', 'oldHttp', 'refresh', 'newHttp', 'newExpiresAt', 'validitySeconds', 'preservation', 'operations'])
    || value.schemaVersion !== 1 || value.status !== 'NATURAL_EXPIRY_REFRESH_VERIFIED' || value.scope !== 'canonical-credential-access'
    || !utcSecond(value.observedAt) || !utcSecond(value.oldExpiresAt) || !utcSecond(value.newExpiresAt) || value.validitySeconds !== 3600) return null;
  const oldHttp = value.oldHttp; const newHttp = value.newHttp;
  if (!object(oldHttp) || !exact(oldHttp, ['status', 'at']) || oldHttp.status !== 401 || !utcSecond(oldHttp.at)
    || !object(newHttp) || !exact(newHttp, ['status', 'at', 'repositoryIdentityMatches']) || newHttp.status !== 200
    || newHttp.repositoryIdentityMatches !== true || !utcSecond(newHttp.at)
    || !fixed(value.refresh, { nativeAccessCount: 1, tokenChanged: true, cacheObjectChanged: true })
    || !fixed(value.preservation, { credentialStoreMembership: true, jobConfiguration: true, jobState: true, privateInputs: true })
    || !fixed(value.operations, { forcedExpiration: false, credentialUpdate: false, statusWrite: false, build: false, rawValueOutput: false, automaticRetry: false })) return null;
  const expired = Date.parse(value.oldExpiresAt); const rejected = Date.parse(oldHttp.at);
  const accepted = Date.parse(newHttp.at); const observed = Date.parse(value.observedAt); const renewedExpiry = Date.parse(value.newExpiresAt);
  if (expired > rejected || rejected > accepted || accepted > observed || observed >= renewedExpiry
    || renewedExpiry - accepted !== value.validitySeconds * 1000) return null;
  return value as unknown as GitHubAppRenewalRecord;
}
