import { kafkaUtcNs } from './kafka-observation.ts';

export const KAFKA_LAG_RUNTIME_MANIFEST = '07d084f0f8a46745f99918fbc1794c908b11c8b5224b84c6d49bbe3afc5d2236';
export const KAFKA_LAG_SOURCE_COMMIT = '5e22dbecfa4da458a563fd5fa1fc4c9c34a7ef17';
export const KAFKA_LAG_RUN_URL = 'https://github.com/DevDooly/devdooly-platform-lab/actions/runs/39412343874';
export const KAFKA_LAG_COMPLETED_AT = '2026-10-20T11:05:48Z';
export const KAFKA_LAG_XML_SHA256 = '622b937f1da1a9d39ca5da53812e64a1ad9b63222ec2fe10082e0cd5a60f471d';
const recoveryResult = {
  schemaVersion: 1, status: 'PASS', initialProcessed: 4, initialEndOffset: 12,
  initialCommittedOffset: 4, initialLag: 8, emptyGroupObserved: true, additionalProduced: 6,
  backlogEndOffset: 18, backlogCommittedOffset: 4, backlogLag: 14, resumedProcessed: 14,
  resumedFirstOffset: 4, resumedLastOffset: 17, finalCommittedOffset: 18, finalLag: 0, targetStable: true,
} as const;
export interface KafkaLagRecoverySummary {
  schemaVersion: 1; scope: 'ISOLATED_KAFKA_LAG_RECOVERY_IT'; synthetic: true;
  sourceCommit: string; runtimeManifestSha256: string; status: 'PASSED'; failureCode: null;
  expectedTests: 1; verifiedTests: 1; surefireXmlSha256: string;
  sourceAndArtifactsUnchanged: true; ownedResourcesRemoved: true;
  recoveryResult: typeof recoveryResult; selectedFailure: null;
  operatingKafkaChanged: false; databaseOrExportRecoveryVerified: false;
  brokerRestartOrHighAvailabilityVerified: false; publicExecutionEnabled: false;
}
export interface KafkaLagRecoveryRecord {
  runUrl: string; completedAt: string; summary: KafkaLagRecoverySummary;
}
const summaryKeys = ['schemaVersion', 'scope', 'synthetic', 'sourceCommit', 'runtimeManifestSha256',
  'status', 'failureCode', 'expectedTests', 'verifiedTests', 'surefireXmlSha256',
  'sourceAndArtifactsUnchanged', 'ownedResourcesRemoved', 'recoveryResult', 'selectedFailure',
  'operatingKafkaChanged', 'databaseOrExportRecoveryVerified', 'brokerRestartOrHighAvailabilityVerified',
  'publicExecutionEnabled'] as const;
const object = (value: unknown): value is Record<string, unknown> => value !== null && typeof value === 'object' && !Array.isArray(value);
const exact = (value: Record<string, unknown>, keys: readonly string[]) => Object.keys(value).length === keys.length && keys.every(key => Object.hasOwn(value, key));

/** Validate this saved result only. It neither executes a recovery nor authenticates a receipt. */
export function parseKafkaLagRecovery(value: unknown, nowMs = Date.now()): KafkaLagRecoveryRecord | null {
  if (!Number.isSafeInteger(nowMs) || !object(value) || !exact(value, ['runUrl', 'completedAt', 'summary'])
    || typeof value.runUrl !== 'string' || !/^https:\/\/github\.com\/DevDooly\/devdooly-platform-lab\/actions\/runs\/[1-9]\d{0,19}$/.test(value.runUrl)
    || value.runUrl !== KAFKA_LAG_RUN_URL
    || value.completedAt !== KAFKA_LAG_COMPLETED_AT) return null;
  const completed = kafkaUtcNs(value.completedAt);
  if (completed === null || completed > BigInt(nowMs) * 1_000_000n) return null;
  const summary = value.summary;
  if (!object(summary) || !exact(summary, summaryKeys) || summary.schemaVersion !== 1
    || summary.scope !== 'ISOLATED_KAFKA_LAG_RECOVERY_IT' || summary.synthetic !== true
    || typeof summary.sourceCommit !== 'string' || !/^[a-f0-9]{40}$/.test(summary.sourceCommit)
    || summary.sourceCommit !== KAFKA_LAG_SOURCE_COMMIT
    || summary.runtimeManifestSha256 !== KAFKA_LAG_RUNTIME_MANIFEST
    || summary.status !== 'PASSED' || summary.failureCode !== null || summary.selectedFailure !== null
    || summary.expectedTests !== 1 || summary.verifiedTests !== 1
    || summary.surefireXmlSha256 !== KAFKA_LAG_XML_SHA256
    || summary.sourceAndArtifactsUnchanged !== true || summary.ownedResourcesRemoved !== true
    || summary.operatingKafkaChanged !== false || summary.databaseOrExportRecoveryVerified !== false
    || summary.brokerRestartOrHighAvailabilityVerified !== false || summary.publicExecutionEnabled !== false) return null;
  const result = summary.recoveryResult;
  if (!object(result) || !exact(result, Object.keys(recoveryResult))
    || !Object.entries(recoveryResult).every(([key, expected]) => result[key] === expected)) return null;
  return value as unknown as KafkaLagRecoveryRecord;
}

export interface KafkaLagPhase {
  id: 'initial' | 'closed' | 'backlog' | 'recovered'; title: string;
  group: 'STABLE' | 'EMPTY'; end: number; committed: number; lag: number;
  description: string;
}
export function kafkaLagPhases(record: KafkaLagRecoveryRecord): KafkaLagPhase[] {
  const result = record.summary.recoveryResult;
  return [
    { id: 'initial', title: '처음 4건 읽기', group: 'STABLE', end: result.initialEndOffset,
      committed: result.initialCommittedOffset, lag: result.initialLag,
      description: '합성 메시지 12건 중 offset 0–3의 4건을 읽고 key·value를 확인했습니다. 다음 시작 위치인 commit 4를 저장했습니다.' },
    { id: 'closed', title: '소비자 정상 종료', group: 'EMPTY', end: result.initialEndOffset,
      committed: result.initialCommittedOffset, lag: result.initialLag,
      description: '기존 소비자를 정상 종료했습니다. 그룹이 EMPTY가 된 뒤에도 commit 4와 offset 차이 8을 확인했습니다.' },
    { id: 'backlog', title: '대기 중 6건 추가', group: 'EMPTY', end: result.backlogEndOffset,
      committed: result.backlogCommittedOffset, lag: result.backlogLag,
      description: '소비자가 없는 동안 합성 메시지 6건을 더 발행했습니다. end 18과 commit 4의 offset 차이(lag)는 14였습니다.' },
    { id: 'recovered', title: '새 소비자로 재개', group: 'STABLE', end: result.backlogEndOffset,
      committed: result.finalCommittedOffset, lag: result.finalLag,
      description: '새 소비자가 재가입해 저장된 commit 4부터 offset 17까지 14건을 읽고 key·value를 확인했습니다. commit 18과 lag 0을 확인했습니다.' },
  ];
}

/** Native buttons retain Enter/Space; these keys additionally move the selected phase and focus. */
export function kafkaLagPhaseKey(index: number, key: string): number | null {
  if (!Number.isInteger(index) || index < 0 || index > 3) return null;
  if (key === 'Home') return 0;
  if (key === 'End') return 3;
  if (key === 'ArrowLeft') return (index + 3) % 4;
  if (key === 'ArrowRight') return (index + 1) % 4;
  return null;
}
