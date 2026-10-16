/** A bounded public projection; this module cannot contact S3 or the Lab. */
type PendingSdk = { status: 'NOT_RUN' };
type VerifiedSdk = {
  status: 'VERIFIED'; capturedAt: '2026-10-15T23:45:37.148212Z'; wholeGets: 3; apiCalls: 3; httpAttempts: 3;
  retries: 0; configuredMaxAttempts: 3; clientClosed: true; httpClient: 'Apache5'; cleanupRevoked: true;
  proofSha256: { run: string; cleanup: string; revoke: string };
};
type Shared = {
  schemaVersion: 1; sourceCommit: string; observedAt: string;
  deployment: { healthyObserved: true; sourceCommit: string; capturedAt: string };
  preservation: { afterSdkVerified: boolean; capturedAt: string; originalWholeGets: 24; nativeKnownWholeGets: 12 };
  history: { originalApiwebWatchPassed: false; originalApiwebFailureCause: 'UNPROVEN'; oldWorkerExit: 'UNOBSERVED' };
  limits: { pointInTimeOnly: true; productionApiJvmSdkVerified: false; writeCompatibilityVerified: false; latencyOrSlaClaimed: false };
};
export type S3TransportRecord = Shared & (
  { status: 'DEPLOYED_SDK_PENDING'; sdk: PendingSdk } | { status: 'DEPLOYED_SDK_VERIFIED'; sdk: VerifiedSdk }
);
const object = (value: unknown): value is Record<string, unknown> => value !== null && typeof value === 'object' && !Array.isArray(value);
const exact = (value: Record<string, unknown>, keys: readonly string[]) => Object.keys(value).length === keys.length && keys.every(key => Object.hasOwn(value, key));
const fixed = (value: unknown, expected: Record<string, unknown>) => object(value) && exact(value, Object.keys(expected)) && Object.entries(expected).every(([key, item]) => value[key] === item);
const hash = (value: unknown, length: number): value is string => typeof value === 'string' && new RegExp(`^[a-f0-9]{${length}}$`).test(value);
function utc(value: unknown): value is string {
  if (typeof value !== 'string' || !/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.[0-9]{1,9})?Z$/.test(value)) return false;
  const date = new Date(value);
  return Number.isFinite(date.getTime()) && date.toISOString().slice(0, 19) === value.slice(0, 19);
}
export function parseS3Transport(value: unknown): S3TransportRecord | null {
  if (!object(value) || !exact(value, ['schemaVersion', 'status', 'sourceCommit', 'observedAt', 'deployment', 'sdk', 'preservation', 'history', 'limits'])
    || value.schemaVersion !== 1 || !hash(value.sourceCommit, 40) || !utc(value.observedAt)) return null;
  const deployment = value.deployment; const preservation = value.preservation;
  if (!object(deployment) || !exact(deployment, ['healthyObserved', 'sourceCommit', 'capturedAt']) || deployment.healthyObserved !== true
    || deployment.sourceCommit !== value.sourceCommit || !utc(deployment.capturedAt)
    || !object(preservation) || !exact(preservation, ['afterSdkVerified', 'capturedAt', 'originalWholeGets', 'nativeKnownWholeGets'])
    || !utc(preservation.capturedAt) || preservation.originalWholeGets !== 24 || preservation.nativeKnownWholeGets !== 12
    || Date.parse(deployment.capturedAt) > Date.parse(preservation.capturedAt) || Date.parse(preservation.capturedAt) > Date.parse(value.observedAt)
    || !fixed(value.history, { originalApiwebWatchPassed: false, originalApiwebFailureCause: 'UNPROVEN', oldWorkerExit: 'UNOBSERVED' })
    || !fixed(value.limits, { pointInTimeOnly: true, productionApiJvmSdkVerified: false, writeCompatibilityVerified: false, latencyOrSlaClaimed: false })) return null;
  if (value.status === 'DEPLOYED_SDK_PENDING') {
    if (preservation.afterSdkVerified !== false || !fixed(value.sdk, { status: 'NOT_RUN' })) return null;
  } else if (value.status === 'DEPLOYED_SDK_VERIFIED') {
    const sdk = value.sdk;
    if (preservation.afterSdkVerified !== true || !object(sdk)
      || !exact(sdk, ['status', 'capturedAt', 'wholeGets', 'apiCalls', 'httpAttempts', 'retries', 'configuredMaxAttempts', 'clientClosed', 'httpClient', 'cleanupRevoked', 'proofSha256'])
      || sdk.status !== 'VERIFIED' || sdk.capturedAt !== '2026-10-15T23:45:37.148212Z'
      || sdk.wholeGets !== 3 || sdk.apiCalls !== 3 || sdk.httpAttempts !== 3 || sdk.retries !== 0 || sdk.configuredMaxAttempts !== 3
      || sdk.clientClosed !== true || sdk.httpClient !== 'Apache5' || sdk.cleanupRevoked !== true
      || Date.parse(sdk.capturedAt) < Date.parse(deployment.capturedAt) || Date.parse(sdk.capturedAt) > Date.parse(preservation.capturedAt)
      || !object(sdk.proofSha256) || !exact(sdk.proofSha256, ['run', 'cleanup', 'revoke'])
      || !Object.values(sdk.proofSha256).every(item => hash(item, 64)) || new Set(Object.values(sdk.proofSha256)).size !== 3) return null;
  } else return null;
  return value as unknown as S3TransportRecord;
}
