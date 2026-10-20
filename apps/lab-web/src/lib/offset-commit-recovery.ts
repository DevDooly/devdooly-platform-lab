import { kafkaUtcNs } from './kafka-observation.ts';

export const OFFSET_COMMIT_RUNTIME_MANIFEST = 'c2457176d92d7892c1bc5d5c4e7f83a471b105de6a08898bb35b837f6ce2a551';
export const OFFSET_COMMIT_SOURCE_COMMIT = '0d49ab99bd1caccf8109642758f2ea8367dbb504';
export const OFFSET_COMMIT_RUN_URL = 'https://github.com/DevDooly/devdooly-platform-lab/actions/runs/39424186853';
export const OFFSET_COMMIT_COMPLETED_AT = '2026-10-20T12:44:26Z';
export const OFFSET_COMMIT_XML_SHA256 = '6b102c50d3d87dd104ec797ab95c3b9d77dda2b7b9e0a922c0e22003de43f273';

export interface OffsetCommitBinding {
  readonly runtimeManifestSha256: string; readonly sourceCommit: string; readonly runUrl: string;
  readonly completedAt: string; readonly surefireXmlSha256: string;
}
export const defaultBinding: OffsetCommitBinding = {
  runtimeManifestSha256: OFFSET_COMMIT_RUNTIME_MANIFEST, sourceCommit: OFFSET_COMMIT_SOURCE_COMMIT,
  runUrl: OFFSET_COMMIT_RUN_URL, completedAt: OFFSET_COMMIT_COMPLETED_AT, surefireXmlSha256: OFFSET_COMMIT_XML_SHA256,
};

const fixedResult = {
  schemaVersion: 1, status: 'PASS', fixtureInput: 12, successCount: 7, failureCount: 3, duplicateCount: 2, pendingCount: 0,
  dbCommitBeforeFault: true, pausePersisted: true, pauseCode: 'OFFSET_COMMIT_FAILED', runRefusedUnchanged: true,
  operatorResumeRecorded: true, readCommittedEndOffset: 1, businessRowsAndTimesUnchanged: true, exported: true,
  verifiedExportFiles: 2, slotFree: true, finalCommittedOffset: 1, finalLag: 0, childResourcesClosed: true,
} as const;
export type OffsetCommitRecoveryResult = Readonly<typeof fixedResult & {
  postUnpauseCommitState: 'NO_COMMIT' | 'OBSERVED'; postUnpauseCommittedOffset: null | 1; completedReplays: 0 | 1;
}>;
const fixedSummary = {
  schemaVersion: 1, scope: 'ISOLATED_REAL_OFFSET_COMMIT_RECOVERY', synthetic: true, status: 'PASSED',
  failureCode: null, selectedFailure: null, jvmFailure: null, expectedTests: 1, verifiedTests: 1, ownedResourcesRemoved: true,
  sourceAndArtifactsUnchanged: true, operatingServicesChanged: false, hostOrBrokerRestartVerified: false,
  publicExecutionEnabled: false,
} as const;
export type OffsetCommitRecoverySummary = Readonly<typeof fixedSummary & {
  sourceCommit: string; runtimeManifestSha256: string; surefireXmlSha256: string;
  recoveryResult: OffsetCommitRecoveryResult;
}>;
export interface OffsetCommitRecoveryRecord {
  readonly runUrl: string; readonly completedAt: string; readonly summary: OffsetCommitRecoverySummary;
}

const bindingKeys = ['runtimeManifestSha256', 'sourceCommit', 'runUrl', 'completedAt', 'surefireXmlSha256'] as const;
const summaryKeys = [...Object.keys(fixedSummary), 'sourceCommit', 'runtimeManifestSha256', 'surefireXmlSha256', 'recoveryResult'];
const resultKeys = [...Object.keys(fixedResult), 'postUnpauseCommitState', 'postUnpauseCommittedOffset', 'completedReplays'];
const object = (value: unknown): value is Record<string, unknown> => value !== null && typeof value === 'object' && !Array.isArray(value);
const exact = (value: Record<string, unknown>, keys: readonly string[]) => Reflect.ownKeys(value).length === keys.length
  && keys.every(key => Object.hasOwn(value, key));
const hash = (value: unknown): value is string => typeof value === 'string' && /^[a-f0-9]{64}$/.test(value);
const commit = (value: unknown): value is string => typeof value === 'string' && /^[a-f0-9]{40}$/.test(value);
const run = (value: unknown): value is string => typeof value === 'string'
  && /^https:\/\/github\.com\/DevDooly\/devdooly-platform-lab\/actions\/runs\/[1-9]\d{0,19}$/.test(value);

/** Saved, bound evidence only. This validates a public contract; it executes no recovery and authenticates no receipt. */
export function parseOffsetCommitRecovery(value: unknown, nowMs = Date.now(), binding: OffsetCommitBinding = defaultBinding): OffsetCommitRecoveryRecord | null {
  // An unreviewed binding must fail before any submitted result can supply successful metrics.
  if (!Number.isSafeInteger(nowMs) || !object(binding) || !exact(binding, bindingKeys)
    || !hash(binding.runtimeManifestSha256) || !commit(binding.sourceCommit) || !hash(binding.surefireXmlSha256)
    || !run(binding.runUrl)) return null;
  const completed = kafkaUtcNs(binding.completedAt);
  if (completed === null || completed > BigInt(nowMs) * 1_000_000n) return null;
  if (!object(value) || !exact(value, ['runUrl', 'completedAt', 'summary'])
    || value.runUrl !== binding.runUrl || value.completedAt !== binding.completedAt) return null;
  const summary = value.summary;
  if (!object(summary) || !exact(summary, summaryKeys)
    || !Object.entries(fixedSummary).every(([key, expected]) => summary[key] === expected)
    || summary.sourceCommit !== binding.sourceCommit || summary.runtimeManifestSha256 !== binding.runtimeManifestSha256
    || summary.surefireXmlSha256 !== binding.surefireXmlSha256) return null;
  const result = summary.recoveryResult;
  if (!object(result) || !exact(result, resultKeys)
    || !Object.entries(fixedResult).every(([key, expected]) => result[key] === expected)
    || !(result.completedReplays === 0 || result.completedReplays === 1)
    || !(result.postUnpauseCommitState === 'NO_COMMIT' && result.postUnpauseCommittedOffset === null
      || result.postUnpauseCommitState === 'OBSERVED' && result.postUnpauseCommittedOffset === 1)) return null;
  return {
    runUrl: binding.runUrl, completedAt: binding.completedAt,
    summary: {
      ...fixedSummary, sourceCommit: binding.sourceCommit, runtimeManifestSha256: binding.runtimeManifestSha256,
      surefireXmlSha256: binding.surefireXmlSha256,
      recoveryResult: { ...fixedResult, postUnpauseCommitState: result.postUnpauseCommitState,
        postUnpauseCommittedOffset: result.postUnpauseCommittedOffset, completedReplays: result.completedReplays },
    },
  };
}

export interface OffsetCommitPhase {
  readonly id: 'completed' | 'paused' | 'resumed' | 'exported'; readonly title: string; readonly description: string;
  readonly domain: 'JOB' | 'RUNTIME';
  readonly status: 'COMPLETED' | 'PAUSED_OPERATOR' | 'STOPPED'; readonly exportStatus: 'PENDING' | 'EXPORTED';
}
export function offsetCommitPhases(record: OffsetCommitRecoveryRecord): OffsetCommitPhase[] {
  const result = record.summary.recoveryResult;
  return [
    { id: 'completed', title: 'DB 처리 완료', domain: 'JOB', status: 'COMPLETED', exportStatus: 'PENDING',
      description: `합성 입력 ${result.fixtureInput}건의 DB 처리를 commit했습니다. 성공 ${result.successCount}건·실패 ${result.failureCount}건·중복 ${result.duplicateCount}건이며 export는 PENDING, 슬롯은 점유 상태였습니다.` },
    { id: 'paused', title: '영속 pause', domain: 'RUNTIME', status: 'PAUSED_OPERATOR', exportStatus: 'PENDING',
      description: '격리 broker를 잠시 멈춘 동안 실제 offset commit 호출이 실패했습니다. CONSUME 단계의 OFFSET_COMMIT_FAILED와 PAUSED_OPERATOR가 DB에 남았고, 완료 업무 행·시각과 점유 슬롯은 유지됐습니다.' },
    { id: 'resumed', title: '명시 resume', domain: 'RUNTIME', status: 'STOPPED', exportStatus: 'PENDING',
      description: '일반 run 명령은 영속 pause를 바꾸지 못했습니다. 별도 resume 명령만 STOPPED와 오류 해제를 기록했으며, 완료 업무와 PENDING export는 보존됐습니다.' },
    { id: 'exported', title: 'export 검증', domain: 'JOB', status: 'COMPLETED', exportStatus: 'EXPORTED',
      description: `명시 resume 뒤 실제 런타임이 export를 마쳤고, 결과·실패 파일 ${result.verifiedExportFiles}개의 전체 bytes·SHA를 대조했습니다. 슬롯 해제와 최종 commit ${result.finalCommittedOffset}·lag ${result.finalLag}을 확인했습니다. 업무 행·처리 시각은 보존됐고 완료 작업 replay는 ${result.completedReplays}회였습니다.` },
  ];
}

/** Native buttons retain Enter/Space; these keys additionally select and focus one of the four saved phases. */
export function offsetCommitPhaseKey(index: number, key: string): number | null {
  if (!Number.isInteger(index) || index < 0 || index > 3) return null;
  if (key === 'Home') return 0;
  if (key === 'End') return 3;
  if (key === 'ArrowLeft') return (index + 3) % 4;
  if (key === 'ArrowRight') return (index + 1) % 4;
  return null;
}
