import { kafkaUtcNs } from './kafka-observation.ts';
export { offsetCommitPhaseKey as exportIntegrityPhaseKey } from './offset-commit-recovery.ts';

export const EXPORT_INTEGRITY_RUNTIME_MANIFEST = 'd0ac9e8389d967158102badd1c202c9954fbe5c839d7db333c50985b78e64488';
export const EXPORT_INTEGRITY_SOURCE_COMMIT = '0f5c4bc2b0e5296c0c29924a5487d2c62ad1cd75';
export const EXPORT_INTEGRITY_RUN_URL = 'https://github.com/DevDooly/devdooly-platform-lab/actions/runs/39428536206';
export const EXPORT_INTEGRITY_COMPLETED_AT = '2026-10-20T13:16:39Z';
export const EXPORT_INTEGRITY_XML_SHA256 = 'd6a16be1789f6518c234d3857307ab0a633dd5c6e47a4631e7e9e544506cd7b0';

export interface ExportIntegrityBinding {
  readonly runtimeManifestSha256: string; readonly sourceCommit: string; readonly runUrl: string;
  readonly completedAt: string; readonly surefireXmlSha256: string;
}
export const defaultBinding: ExportIntegrityBinding = {
  runtimeManifestSha256: EXPORT_INTEGRITY_RUNTIME_MANIFEST, sourceCommit: EXPORT_INTEGRITY_SOURCE_COMMIT,
  runUrl: EXPORT_INTEGRITY_RUN_URL, completedAt: EXPORT_INTEGRITY_COMPLETED_AT,
  surefireXmlSha256: EXPORT_INTEGRITY_XML_SHA256,
};

const fixedResult = {
  schemaVersion: 1, status: 'PASS', fixtureInput: 12, successCount: 7, failureCount: 3, duplicateCount: 2, pendingCount: 0,
  directDatabaseFixture: true, dispatchBrokerAck: true, sameSizeCorruption: true, verificationFailureObserved: true,
  pausePersisted: true, pauseCode: 'EXPORT_FAILED', runRefusedUnchanged: true, unrepairedResumeRepaused: true,
  corruptObjectUnchanged: true, explicitOwnedFixtureDeleted: true, verifiedExportFiles: 2, completedReplays: 1,
  finalEndOffset: 1, finalCommittedOffset: 1, finalLag: 0, businessRowsAndTimesUnchanged: true,
  sourceAndRawUnchanged: true, dispatchAndExportIdentityUnchanged: true, exported: true, slotFree: true,
  childResourcesClosed: true, targetStable: true,
} as const;
export type ExportIntegrityResult = Readonly<typeof fixedResult>;
const fixedSummary = {
  schemaVersion: 1, scope: 'ISOLATED_EXPORT_INTEGRITY_RUNTIME', synthetic: true, status: 'PASSED',
  failureCode: null, selectedFailure: null, jvmFailure: null, expectedTests: 1, verifiedTests: 1, ownedResourcesRemoved: true,
  sourceAndArtifactsUnchanged: true, operatingServicesChanged: false, hostOrBrokerRestartVerified: false,
  publicExecutionEnabled: false,
} as const;
export type ExportIntegritySummary = Readonly<typeof fixedSummary & {
  sourceCommit: string; runtimeManifestSha256: string; surefireXmlSha256: string; integrityResult: ExportIntegrityResult;
}>;
export interface ExportIntegrityRecord {
  readonly runUrl: string; readonly completedAt: string; readonly summary: ExportIntegritySummary;
}

const bindingKeys = ['runtimeManifestSha256', 'sourceCommit', 'runUrl', 'completedAt', 'surefireXmlSha256'] as const;
const summaryKeys = [...Object.keys(fixedSummary), 'sourceCommit', 'runtimeManifestSha256', 'surefireXmlSha256', 'integrityResult'];
const resultKeys = Object.keys(fixedResult);
const object = (value: unknown): value is Record<string, unknown> => value !== null && typeof value === 'object' && !Array.isArray(value);
const exact = (value: Record<string, unknown>, keys: readonly string[]) => Reflect.ownKeys(value).length === keys.length
  && keys.every(key => Object.hasOwn(value, key));
const hash = (value: unknown): value is string => typeof value === 'string' && /^[a-f0-9]{64}$/.test(value);
const commit = (value: unknown): value is string => typeof value === 'string' && /^[a-f0-9]{40}$/.test(value);
const run = (value: unknown): value is string => typeof value === 'string'
  && /^https:\/\/github\.com\/DevDooly\/devdooly-platform-lab\/actions\/runs\/[1-9]\d{0,17}$/.test(value);

/** Saved, reviewed evidence only. No experiment or storage operation is performed here. */
export function parseExportIntegrity(value: unknown, nowMs = Date.now(), binding: ExportIntegrityBinding = defaultBinding): ExportIntegrityRecord | null {
  // A pending binding is rejected before any submitted record can supply successful metrics.
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
  const result = summary.integrityResult;
  if (!object(result) || !exact(result, resultKeys)
    || !Object.entries(fixedResult).every(([key, expected]) => result[key] === expected)) return null;
  return {
    runUrl: binding.runUrl, completedAt: binding.completedAt,
    summary: {
      ...fixedSummary, sourceCommit: binding.sourceCommit, runtimeManifestSha256: binding.runtimeManifestSha256,
      surefireXmlSha256: binding.surefireXmlSha256, integrityResult: { ...fixedResult },
    },
  };
}

export interface ExportIntegrityPhase {
  readonly id: 'fixture' | 'paused' | 'repaused' | 'exported'; readonly title: string; readonly description: string;
  readonly domain: 'JOB' | 'RUNTIME';
  readonly status: 'COMPLETED' | 'PAUSED_OPERATOR' | 'STOPPED → PAUSED_OPERATOR';
  readonly exportStatus: 'PENDING' | 'EXPORTED'; readonly slot: '점유' | '해제';
}
export function exportIntegrityPhases(record: ExportIntegrityRecord): ExportIntegrityPhase[] {
  const result = record.summary.integrityResult;
  return [
    { id: 'fixture', title: '완료 작업·손상 준비', domain: 'JOB', status: 'COMPLETED', exportStatus: 'PENDING', slot: '점유',
      description: `실제 publisher의 Kafka ACK 뒤 직접 DB 호출로 합성 입력 ${result.fixtureInput}건의 완료 작업을 준비했습니다. 시험 소유 result key에 같은 크기로 변조한 bytes를 저장했으며, 최초 업무 완료는 consumer 처리의 결과가 아닙니다.` },
    { id: 'paused', title: '검증 실패·영속 pause', domain: 'RUNTIME', status: 'PAUSED_OPERATOR', exportStatus: 'PENDING', slot: '점유',
      description: '새 daemon이 실제 저장소 검증 예외를 받고 EXPORT 단계의 EXPORT_FAILED와 PAUSED_OPERATOR를 DB에 남겼습니다. 일반 run 명령은 journal을 바꾸지 못했고 손상 객체와 점유 슬롯은 유지됐습니다.' },
    { id: 'repaused', title: '수리 없는 resume·재pause', domain: 'RUNTIME', status: 'STOPPED → PAUSED_OPERATOR', exportStatus: 'PENDING', slot: '점유',
      description: '원래 CLI의 resume는 STOPPED와 오류 해제를 기록했지만 저장소를 수리하지 않았습니다. 새 daemon이 같은 손상을 다시 검증하고 EXPORT_FAILED로 재pause했으며, 일반 run 명령은 다시 거부됐습니다.' },
    { id: 'exported', title: '명시 수리·export 검증', domain: 'JOB', status: 'COMPLETED', exportStatus: 'EXPORTED', slot: '해제',
      description: `소유권·대상·hash를 확인한 시험 코드가 손상 객체 한 개만 삭제했습니다. 별도 resume 뒤 실제 daemon이 결과·실패 파일 ${result.verifiedExportFiles}개의 전체 bytes·SHA를 대조했고, 슬롯 해제와 완료 메시지 replay ${result.completedReplays}회, 최종 end ${result.finalEndOffset}·commit ${result.finalCommittedOffset}·lag ${result.finalLag}을 확인했습니다.` },
  ];
}
