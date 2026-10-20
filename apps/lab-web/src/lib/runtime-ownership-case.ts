import { kafkaUtcNs } from './kafka-observation.ts';

export const RUNTIME_OWNERSHIP_BINDING = Object.freeze({
  runUrl: 'https://github.com/DevDooly/devdooly-platform-lab/actions/runs/39435016002',
  completedAt: '2026-10-20T14:00:19Z',
  sourceCommit: 'dd9feb815ead4744bf4b6c80a466095e2a4bc6ac',
  runtimeManifestSha256: 'ca10e6c10a5c29f82348dd5126afaa218d32a1c11ac49f840913ff17d8cd8d7d',
  surefireXmlSha256: '4b996398184c9b20410f6c9332b1e7df9db7a271f648468cc1f7e0c26f5f0c96',
});
export const RUNTIME_OWNERSHIP_RAW_SHA256 = '7bf8415e9fc8ca8c3d54529865a033697923ca1468e1b2d5a02fef572b2ea370';

const fixedSummary = {
  schemaVersion: 1, scope: 'ISOLATED_RUNTIME_LEASE_LOSS', status: 'PASSED', synthetic: true,
  expectedTests: 1, verifiedTests: 1, failureCode: null, selectedFailure: null, jvmFailure: null,
  sourceAndArtifactsUnchanged: true, ownedResourcesRemoved: true, operatingServicesChanged: false,
  hostOrBrokerRestartVerified: false, publicExecutionEnabled: false,
} as const;

const fixedResult = {
  schemaVersion: 1, status: 'PASS', fixtureInput: 12, leaseSessionCaptured: true,
  ownerMatchedBeforeKill: true, controlIdentityMatched: true, ownedLeaseConnectionKilled: true,
  lockAbsentAfterKill: true, emptyExportObserved: true, actualLeaseLostObserved: true,
  nextStageRejected: true, publisherCalls: 0, receiverCalls: 0, staleJournalUnchanged: true,
  journalStatus: 'RUNNING', journalStage: 'EXPORT', journalFailureCode: null,
  jobStatus: 'QUEUED', exportStatus: 'NOT_REQUESTED', dispatchStatus: 'PENDING',
  businessRuns: 0, businessOutcomes: 0, exportOutboxEntries: 0, slotOccupied: true,
  queuedJobUnchanged: true, sourceAndRawUnchanged: true, dispatchPendingUnchanged: true,
  readCommittedEndOffset: 0, commitState: 'NO_COMMIT', committedOffset: null,
  childResourcesClosed: true, springContextClosed: true, oldChildExited: true,
  freshLeaseAcquiredAfterExit: true, targetStable: true,
} as const;

export type RuntimeOwnershipResult = Readonly<typeof fixedResult>;
export type RuntimeOwnershipSummary = Readonly<typeof fixedSummary & {
  sourceCommit: string; runtimeManifestSha256: string; surefireXmlSha256: string;
  leaseLossResult: RuntimeOwnershipResult;
}>;
export interface RuntimeOwnershipRecord {
  readonly runUrl: string;
  readonly completedAt: string;
  readonly summary: RuntimeOwnershipSummary;
}

const summaryKeys = [...Object.keys(fixedSummary), 'sourceCommit', 'runtimeManifestSha256', 'surefireXmlSha256', 'leaseLossResult'];
const resultKeys = Object.keys(fixedResult);
const object = (value: unknown): value is Record<string, unknown> => value !== null && typeof value === 'object' && !Array.isArray(value);
const exact = (value: Record<string, unknown>, keys: readonly string[]) => Reflect.ownKeys(value).length === keys.length
  && keys.every(key => Object.hasOwn(value, key));

/** A saved, fixed run contract. This performs no runtime action or current-health check. */
export function parseRuntimeOwnershipCase(value: unknown, nowMs = Date.now()): RuntimeOwnershipRecord | null {
  if (!Number.isSafeInteger(nowMs) || nowMs < 0) return null;
  const completed = kafkaUtcNs(RUNTIME_OWNERSHIP_BINDING.completedAt);
  if (completed === null || completed > BigInt(nowMs) * 1_000_000n) return null;
  if (!object(value) || !exact(value, ['runUrl', 'completedAt', 'summary'])
    || value.runUrl !== RUNTIME_OWNERSHIP_BINDING.runUrl || value.completedAt !== RUNTIME_OWNERSHIP_BINDING.completedAt) return null;
  const summary = value.summary;
  if (!object(summary) || !exact(summary, summaryKeys)
    || !Object.entries(fixedSummary).every(([key, expected]) => summary[key] === expected)
    || summary.sourceCommit !== RUNTIME_OWNERSHIP_BINDING.sourceCommit
    || summary.runtimeManifestSha256 !== RUNTIME_OWNERSHIP_BINDING.runtimeManifestSha256
    || summary.surefireXmlSha256 !== RUNTIME_OWNERSHIP_BINDING.surefireXmlSha256) return null;
  const result = summary.leaseLossResult;
  if (!object(result) || !exact(result, resultKeys)
    || !Object.entries(fixedResult).every(([key, expected]) => result[key] === expected)) return null;
  // Copy only reviewed primitive fields; callers cannot carry unselected submitted data into the page.
  return {
    runUrl: RUNTIME_OWNERSHIP_BINDING.runUrl, completedAt: RUNTIME_OWNERSHIP_BINDING.completedAt,
    summary: { ...fixedSummary, sourceCommit: RUNTIME_OWNERSHIP_BINDING.sourceCommit,
      runtimeManifestSha256: RUNTIME_OWNERSHIP_BINDING.runtimeManifestSha256,
      surefireXmlSha256: RUNTIME_OWNERSHIP_BINDING.surefireXmlSha256, leaseLossResult: { ...fixedResult } },
  };
}

export interface RuntimeOwnershipFact {
  readonly label: string;
  readonly value: string;
}
export interface RuntimeOwnershipPhase {
  readonly id: 'prepared' | 'connection-lost' | 'closed' | 'preserved';
  readonly step: '01' | '02' | '03' | '04';
  readonly title: string;
  readonly domain: 'JOB' | 'RUNTIME' | '종료 뒤 확인';
  readonly description: string;
  readonly facts: readonly RuntimeOwnershipFact[];
  readonly terminalObservations: readonly RuntimeOwnershipFact[];
  readonly note: string;
}

/** Recorded checkpoints in source order, not elapsed-time or simulated process state. */
export function runtimeOwnershipPhases(record: RuntimeOwnershipRecord): readonly RuntimeOwnershipPhase[] {
  const result = record.summary.leaseLossResult;
  return [
    {
      id: 'prepared', step: '01', title: '처리 전의 작업을 준비', domain: 'JOB',
      description: `합성 입력 ${result.fixtureInput}건을 실제 stage와 원본 전체 GET으로 확인했습니다. 업무 처리가 시작되기 전의 작업과 점유 슬롯을 준비했습니다.`,
      facts: [{ label: 'JOB', value: result.jobStatus }, { label: 'export', value: result.exportStatus },
        { label: 'DISPATCH', value: result.dispatchStatus }, { label: '슬롯', value: '점유' }],
      terminalObservations: [],
      note: '시험 소유의 새 MariaDB·Kafka·Garage·JVM 환경에서 준비한 합성 입력입니다.',
    },
    {
      id: 'connection-lost', step: '02', title: '소유한 잠금 연결 하나를 종료', domain: 'RUNTIME',
      description: '실제 empty export가 false를 반환한 직후, 다음 PUBLISH 전의 시험 전용 경계에서 대기했습니다. 별도 제어 연결로 서버·catalog·계정과 named-lock 소유자를 대조한 뒤 그 lease 연결 하나만 한 번 종료했습니다.',
      facts: [{ label: 'fault 위치', value: 'empty export 뒤 · 다음 PUBLISH 전' },
        { label: '대상 대조', value: '실제 lease 소유자와 일치' }, { label: '연결 종료 뒤', value: '실제 lock 부재 확인' }],
      terminalObservations: [],
      note: '여기서 종료한 대상은 잠금용 DB 연결입니다. worker 프로세스 종료나 진행 중 I/O의 차단을 뜻하지 않습니다.',
    },
    {
      id: 'closed', step: '03', title: '다음 단계는 거부되고 자원은 종료', domain: 'RUNTIME',
      description: '다음 소유권 검사에서 실제 잠금 손실이 확인됐습니다. pause 저장에 필요한 소유권 검사도 거부되어 최종 stop 기록 없이 종료했습니다. DB에는 fault 직전 journal 전체 행과 시각이 그대로 남았습니다.',
      facts: [{ label: 'DB runtime journal', value: `${result.journalStatus} / ${result.journalStage}` },
        { label: '저장된 failureCode', value: 'null' }, { label: '실제 종료', value: 'client·lease·Spring context 닫힘 → child 종료' }],
      terminalObservations: [{ label: 'publisher 호출', value: String(result.publisherCalls) },
        { label: 'receiver 호출', value: String(result.receiverCalls) }],
      note: '호출 수는 실제 terminal에서 대조한 결과입니다. 각 중간 순간의 호출 수나 현재 worker 상태를 계산한 값이 아닙니다.',
    },
    {
      id: 'preserved', step: '04', title: '작업 보존과 종료 후 잠금을 확인', domain: '종료 뒤 확인',
      description: 'queued job의 전체 값·시각과 원본 bytes, DISPATCH·policy·점유 슬롯을 보존했습니다. 이전 child가 종료한 뒤 새 실제 lease를 획득·검증·해제했습니다.',
      facts: [{ label: 'JOB / export', value: `${result.jobStatus} / ${result.exportStatus}` },
        { label: 'DISPATCH / 슬롯', value: 'PENDING / 점유 유지' }, { label: '새 lease 확인', value: '이전 child 종료 뒤 획득·검증·해제' }],
      terminalObservations: [{ label: 'Kafka read-committed end', value: String(result.readCommittedEndOffset) },
        { label: '실제 commit', value: `${result.commitState} / null` }, { label: '업무 run / outcome', value: `${result.businessRuns} / ${result.businessOutcomes}` },
        { label: 'EXPORT outbox', value: String(result.exportOutboxEntries) }],
      note: '새 daemon이나 업무 처리는 실행하지 않았습니다. 슬롯 해제·자동 복구·lag 0을 확인한 결과가 아닙니다.',
    },
  ];
}
