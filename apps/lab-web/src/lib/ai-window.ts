/** Public, static JMH evidence only. This module never executes Java or calls a server. */
export const windowProfiles = ['sparse', 'nested'] as const;
export const windowSizes = [128, 512, 2048, 4096] as const;
export type WindowProfile = typeof windowProfiles[number];
export type WindowSize = typeof windowSizes[number];
export type WindowMetric = { meanMicros: number; errorMicros: number; allocationBytesPerOp: number };
export type WindowMeasurement = {
  profile: WindowProfile; size: WindowSize; quadratic: WindowMetric; sweep: WindowMetric; ratio: number;
  rawSha256: string; normalizedSha256: string; resultSha256: string; coveredNanos: number; peakConcurrentSessions: number;
};
export type WindowConditions = {
  jmhVersion: '1.37'; javaVersion: string; os: 'Windows'; forks: 3; threads: 1;
  warmupIterations: number; warmupMillis: number; measurementIterations: number; measurementMillis: number;
  heapMiB: number; gc: 'G1'; timezone: 'Asia/Seoul';
};
export type WindowEvidence = {
  schemaVersion: 1; scope: 'INDEPENDENT_SYNTHETIC_WINDOWS_JAVA21'; sourceCommit: string | null;
  sourceTreeSha256: string; jarSha256: string; fixtureManifestSha256: string; rawResultSha256: string; measuredAt: string;
  humanReview: 'PENDING' | 'REVIEWED'; conditions: WindowConditions; measurements: WindowMeasurement[];
  evidenceLinks: { readme: string; source: string };
};

export function closedFormWindow(profile: WindowProfile, size: WindowSize) {
  return profile === 'sparse'
    ? { coveredNanos: size * 11_000_000, peakConcurrentSessions: 1 }
    : { coveredNanos: size * 1_000_000, peakConcurrentSessions: size };
}
const sha = (value: unknown): value is string => typeof value === 'string' && /^[a-f0-9]{64}$/.test(value);
const commit = (value: unknown) => value === null || (typeof value === 'string' && /^[a-f0-9]{40}$/.test(value));
const object = (value: unknown): value is Record<string, unknown> => value !== null && typeof value === 'object' && !Array.isArray(value);
const exact = (value: Record<string, unknown>, fields: string[], optional: string[] = []) => fields.every(key => Object.hasOwn(value, key)) && Object.keys(value).every(key => fields.includes(key) || optional.includes(key));
const finite = (value: unknown, maximum: number, positive = false): value is number => typeof value === 'number' && Number.isFinite(value) && (positive ? value > 0 : value >= 0) && value <= maximum;
const integer = (value: unknown, maximum: number): value is number => finite(value, maximum, true) && Number.isInteger(value);
const metric = (value: unknown): value is WindowMetric => object(value) && exact(value, ['meanMicros', 'errorMicros', 'allocationBytesPerOp'])
  && finite(value.meanMicros, 1_000_000_000, true) && finite(value.errorMicros, 1_000_000_000) && finite(value.allocationBytesPerOp, 1_073_741_824);
function publicLink(value: unknown): value is string {
  if (typeof value !== 'string' || value.length > 300) return false;
  try {
    const url = new URL(value);
    return url.protocol === 'https:' && !url.username && !url.password && !url.search && !url.hash
      && url.hostname === 'github.com' && /^\/DevDooly\/devdooly-platform-lab\/(?:blob|tree)\/(?:main|[a-f0-9]{40})\/(?:examples\/java-window-analysis(?:\/|$)|docs\/evidence\/ai-window-analysis\/)/.test(url.pathname)
      && !url.pathname.split('/').some(part => part === '..' || part === '.');
  } catch { return false; }
}

/** Reject unbounded, partial, inconsistent, private or fabricated-success-shaped records. */
export function parseWindowEvidence(value: unknown): WindowEvidence | null {
  if (!object(value) || !exact(value, ['schemaVersion', 'scope', 'sourceCommit', 'sourceTreeSha256', 'jarSha256', 'fixtureManifestSha256', 'rawResultSha256', 'measuredAt', 'humanReview', 'conditions', 'measurements', 'evidenceLinks'])
    || value.schemaVersion !== 1 || value.scope !== 'INDEPENDENT_SYNTHETIC_WINDOWS_JAVA21' || !commit(value.sourceCommit)
    || !sha(value.sourceTreeSha256) || !sha(value.jarSha256) || !sha(value.fixtureManifestSha256) || !sha(value.rawResultSha256)
    || typeof value.measuredAt !== 'string' || !/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.[0-9]{1,9})?(?:Z|\+00:00)$/.test(value.measuredAt) || !Number.isFinite(Date.parse(value.measuredAt))
    || (value.humanReview !== 'PENDING' && value.humanReview !== 'REVIEWED')) return null;
  const conditions = value.conditions;
  if (!object(conditions) || !exact(conditions, ['jmhVersion', 'javaVersion', 'os', 'forks', 'threads', 'warmupIterations', 'warmupMillis', 'measurementIterations', 'measurementMillis', 'heapMiB', 'gc', 'timezone'])
    || conditions.jmhVersion !== '1.37' || conditions.os !== 'Windows' || conditions.forks !== 3 || conditions.threads !== 1
    || typeof conditions.javaVersion !== 'string' || !/^(?:Microsoft OpenJDK )?21(?:\.[0-9]+){0,3}(?:\+[0-9]+(?:-LTS)?)?$/.test(conditions.javaVersion)
    || !integer(conditions.warmupIterations, 20) || !integer(conditions.measurementIterations, 20)
    || !integer(conditions.warmupMillis, 60_000) || !integer(conditions.measurementMillis, 60_000)
    || !integer(conditions.heapMiB, 1024) || conditions.gc !== 'G1' || conditions.timezone !== 'Asia/Seoul') return null;
  if (!Array.isArray(value.measurements) || value.measurements.length !== 8) return null;
  const seen = new Set<string>();
  for (const item of value.measurements) {
    if (!object(item) || !exact(item, ['profile', 'size', 'quadratic', 'sweep', 'ratio', 'rawSha256', 'normalizedSha256', 'resultSha256', 'coveredNanos', 'peakConcurrentSessions'])
      || !windowProfiles.includes(item.profile as WindowProfile) || !windowSizes.includes(item.size as WindowSize)
      || !metric(item.quadratic) || !metric(item.sweep) || !finite(item.ratio, 1_000_000_000, true)
      || Math.abs(item.ratio - item.quadratic.meanMicros / item.sweep.meanMicros) > Math.max(1e-9, item.ratio * 1e-6)
      || !sha(item.rawSha256) || !sha(item.normalizedSha256) || !sha(item.resultSha256)) return null;
    const expected = closedFormWindow(item.profile as WindowProfile, item.size as WindowSize);
    if (item.coveredNanos !== expected.coveredNanos || item.peakConcurrentSessions !== expected.peakConcurrentSessions) return null;
    const key = `${item.profile}/${item.size}`; if (seen.has(key)) return null; seen.add(key);
  }
  const links = value.evidenceLinks;
  if (!object(links) || !exact(links, ['readme', 'source']) || !publicLink(links.readme) || !publicLink(links.source)) return null;
  return value as WindowEvidence;
}
