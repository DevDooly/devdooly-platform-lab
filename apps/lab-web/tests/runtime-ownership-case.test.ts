import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { readFileSync } from 'node:fs';
import { test } from 'node:test';
import {
  parseRuntimeOwnershipCase, runtimeOwnershipPhases,
  RUNTIME_OWNERSHIP_BINDING, RUNTIME_OWNERSHIP_RAW_SHA256,
} from '../src/lib/runtime-ownership-case.ts';

// Read the existing public evidence. This creates no generated success file or runtime fixture.
const raw = readFileSync(new URL('../../../docs/evidence/runtime-lease-loss/summary.json', import.meta.url));
const actualSummary = JSON.parse(raw.toString('utf8'));
const actualMetadata = JSON.parse(readFileSync(new URL('../../../docs/evidence/runtime-lease-loss/run-metadata.json', import.meta.url), 'utf8'));
const recordedMs = Date.parse('2026-10-20T14:00:19Z');
const now = recordedMs + 86_400_000;
const fresh = () => JSON.parse(JSON.stringify({
  runUrl: actualMetadata.runUrl, completedAt: actualMetadata.completedAt, summary: actualSummary,
}));

test('실제 공개 원문 지문·metadata·18/35필드와 고정 실행만 수용한다', () => {
  assert.equal(raw.length, 1777);
  assert.equal(createHash('sha256').update(raw).digest('hex'), RUNTIME_OWNERSHIP_RAW_SHA256);
  assert.equal(actualMetadata.artifactSha256, RUNTIME_OWNERSHIP_RAW_SHA256);
  assert.equal(actualMetadata.runConclusion, 'success');
  assert.equal(actualMetadata.trialConclusion, 'success');
  assert.equal(actualMetadata.sourceCommit, 'dd9feb815ead4744bf4b6c80a466095e2a4bc6ac');
  assert.equal(actualMetadata.completedAt, '2026-10-20T14:00:19Z');
  const value = fresh();
  const record = parseRuntimeOwnershipCase(value, now);
  assert.ok(record);
  assert.deepEqual(record, value);
  assert.equal(Object.keys(record.summary).length, 18);
  assert.equal(Object.keys(record.summary.leaseLossResult).length, 35);
  assert.equal(record.runUrl, 'https://github.com/DevDooly/devdooly-platform-lab/actions/runs/39435016002');
  assert.equal(record.summary.runtimeManifestSha256, 'ca10e6c10a5c29f82348dd5126afaa218d32a1c11ac49f840913ff17d8cd8d7d');
  assert.equal(record.summary.surefireXmlSha256, '4b996398184c9b20410f6c9332b1e7df9db7a271f648468cc1f7e0c26f5f0c96');
});

test('다른 실행·source·manifest·XML·완료 시각과 pending binding을 거부한다', () => {
  for (const mutation of [
    (v: ReturnType<typeof fresh>) => { v.runUrl = v.runUrl.replace('39435016002', '39435016003'); },
    (v: ReturnType<typeof fresh>) => { v.completedAt = '2026-10-20T14:00:20Z'; },
    (v: ReturnType<typeof fresh>) => { v.summary.sourceCommit = '0'.repeat(40); },
    (v: ReturnType<typeof fresh>) => { v.summary.runtimeManifestSha256 = '0'.repeat(64); },
    (v: ReturnType<typeof fresh>) => { v.summary.surefireXmlSha256 = '0'.repeat(64); },
    (v: ReturnType<typeof fresh>) => { v.summary.sourceCommit = 'PENDING_REVIEW'; },
  ]) {
    const value = fresh(); mutation(value);
    assert.equal(parseRuntimeOwnershipCase(value, now), null);
  }
  assert.ok(Object.isFrozen(RUNTIME_OWNERSHIP_BINDING));
});

test('outer와result의 누락·unknown·배열·숨은 own key는 성공 화면에 사용하지 않는다', () => {
  for (const mutation of [
    (v: ReturnType<typeof fresh>) => { v.extra = true; },
    (v: ReturnType<typeof fresh>) => { delete v.runUrl; },
    (v: ReturnType<typeof fresh>) => { v.summary.extra = 'PRIVATE_CANARY'; },
    (v: ReturnType<typeof fresh>) => { delete v.summary.sourceAndArtifactsUnchanged; },
    (v: ReturnType<typeof fresh>) => { v.summary.leaseLossResult.extra = true; },
    (v: ReturnType<typeof fresh>) => { delete v.summary.leaseLossResult.oldChildExited; },
    (v: ReturnType<typeof fresh>) => { v.summary.leaseLossResult = []; },
    (v: ReturnType<typeof fresh>) => { Object.defineProperty(v, 'hidden', { value: 'PRIVATE_CANARY' }); },
    (v: ReturnType<typeof fresh>) => { v.summary[Symbol('PRIVATE_CANARY')] = true; },
  ]) {
    const value = fresh(); mutation(value);
    assert.equal(parseRuntimeOwnershipCase(value, now), null);
  }
  for (const value of [null, [], {}, { summary: null }]) assert.equal(parseRuntimeOwnershipCase(value, now), null);
});

test('부분·실패·미정리·source변경 결과는 표시하지 않는다', () => {
  for (const changes of [
    { status: 'FAILED' }, { status: 'PENDING_REVIEW' }, { expectedTests: 2 }, { verifiedTests: 0 },
    { failureCode: 'VALIDATION_FAILED' }, { selectedFailure: { phase: 'CLOSED' } },
    { jvmFailure: { exitCode: 1 } }, { sourceAndArtifactsUnchanged: false }, { ownedResourcesRemoved: false },
  ]) {
    const value = fresh(); Object.assign(value.summary, changes);
    assert.equal(parseRuntimeOwnershipCase(value, now), null);
  }
});

test('false·null·실제1의 primitive 타입과 시험범위 flags를 엄격히 구분한다', () => {
  for (const changes of [
    { schemaVersion: true }, { expectedTests: true }, { verifiedTests: '1' }, { synthetic: false },
    { operatingServicesChanged: true }, { hostOrBrokerRestartVerified: true }, { publicExecutionEnabled: true },
    { failureCode: undefined }, { selectedFailure: false }, { jvmFailure: 0 }, { ownedResourcesRemoved: 1 },
  ]) {
    const value = fresh(); Object.assign(value.summary, changes);
    assert.equal(parseRuntimeOwnershipCase(value, now), null);
  }
});

test('종료·소유권·행과원본보존의 필수 관측이 빠지거나 false이면 거부한다', () => {
  const required = ['leaseSessionCaptured', 'ownerMatchedBeforeKill', 'controlIdentityMatched',
    'ownedLeaseConnectionKilled', 'lockAbsentAfterKill', 'emptyExportObserved', 'actualLeaseLostObserved',
    'nextStageRejected', 'staleJournalUnchanged', 'queuedJobUnchanged', 'sourceAndRawUnchanged',
    'dispatchPendingUnchanged', 'childResourcesClosed', 'springContextClosed', 'oldChildExited',
    'freshLeaseAcquiredAfterExit', 'targetStable', 'slotOccupied'];
  for (const key of required) {
    const value = fresh(); value.summary.leaseLossResult[key] = false;
    assert.equal(parseRuntimeOwnershipCase(value, now), null, key);
  }
});

test('publisher·receiver의0과업무결과0을 false·문자열 또는 성공 수치로 바꾸지 않는다', () => {
  for (const [key, altered] of [
    ['publisherCalls', false], ['receiverCalls', '0'], ['businessRuns', 1], ['businessOutcomes', 1],
    ['exportOutboxEntries', 1], ['fixtureInput', '12'], ['schemaVersion', true], ['status', 'PASSED'],
  ] as const) {
    const value = fresh(); value.summary.leaseLossResult[key] = altered;
    assert.equal(parseRuntimeOwnershipCase(value, now), null);
  }
});

test('staleRUNNING/EXPORT/null을 존재하지 않는영속pause나STOPPED로 대체하지 않는다', () => {
  for (const changes of [
    { journalStatus: 'PAUSED_OPERATOR' }, { journalStatus: 'STOPPED' }, { journalStage: 'PUBLISH' },
    { journalFailureCode: 'LEASE_LOST' }, { jobStatus: 'COMPLETED' },
    { exportStatus: 'EXPORTED' }, { dispatchStatus: 'ACK' },
  ]) {
    const value = fresh(); Object.assign(value.summary.leaseLossResult, changes);
    assert.equal(parseRuntimeOwnershipCase(value, now), null);
  }
});

test('NO_COMMIT/null과end0을commit0·commit1·lag0의증거로 바꾸지 않는다', () => {
  for (const changes of [
    { commitState: 'OBSERVED', committedOffset: 0 }, { commitState: 'NO_COMMIT', committedOffset: 0 },
    { commitState: 'NO_COMMIT', committedOffset: 1 }, { readCommittedEndOffset: false },
    { readCommittedEndOffset: 1 }, { lag: 0 },
  ]) {
    const value = fresh(); Object.assign(value.summary.leaseLossResult, changes);
    assert.equal(parseRuntimeOwnershipCase(value, now), null);
  }
  const record = parseRuntimeOwnershipCase(fresh(), now)!;
  assert.equal(record.summary.leaseLossResult.committedOffset, null);
  assert.equal(record.summary.leaseLossResult.commitState, 'NO_COMMIT');
  assert.equal(Object.hasOwn(record.summary.leaseLossResult, 'lag'), false);
});

test('완료직전 미래시각은거부하고 과거기록에 만료일이나현재health를 만들지 않는다', () => {
  assert.equal(parseRuntimeOwnershipCase(fresh(), recordedMs - 1), null);
  assert.ok(parseRuntimeOwnershipCase(fresh(), recordedMs));
  assert.ok(parseRuntimeOwnershipCase(fresh(), recordedMs + 365 * 86_400_000));
  for (const badClock of [NaN, Infinity, 1.5, -1, Number.MAX_SAFE_INTEGER + 1]) {
    assert.equal(parseRuntimeOwnershipCase(fresh(), badClock), null);
  }
  for (const timestamp of ['2026-10-20 14:00:19 PRIVATE_CANARY', '2026-10-20T14:00:19+00:00', '2026-10-32T14:00:19Z']) {
    const value = fresh(); value.completedAt = timestamp;
    assert.equal(parseRuntimeOwnershipCase(value, now), null);
  }
});

test('4단계는소스확인순서이고 호출수0은종료뒤관측에만배치한다', () => {
  const record = parseRuntimeOwnershipCase(fresh(), now)!;
  const phases = runtimeOwnershipPhases(record);
  assert.deepEqual(phases.map(phase => phase.id), ['prepared', 'connection-lost', 'closed', 'preserved']);
  assert.deepEqual(phases.map(phase => phase.domain), ['JOB', 'RUNTIME', 'RUNTIME', '종료 뒤 확인']);
  assert.equal(phases[0].terminalObservations.length, 0);
  assert.equal(phases[1].terminalObservations.length, 0);
  assert.deepEqual(phases[2].terminalObservations, [
    { label: 'publisher 호출', value: '0' }, { label: 'receiver 호출', value: '0' },
  ]);
  assert.ok(phases[2].facts.some(fact => fact.value === 'RUNNING / EXPORT'));
  assert.ok(phases[2].facts.some(fact => fact.label === '저장된 failureCode' && fact.value === 'null'));
  assert.ok(phases[3].terminalObservations.some(fact => fact.value === 'NO_COMMIT / null'));
  for (const phase of phases) {
    assert.equal(Object.hasOwn(phase, 'elapsedMillis'), false);
    assert.equal(Object.hasOwn(phase, 'capturedAt'), false);
    assert.equal(Object.hasOwn(phase, 'healthy'), false);
  }
});

test('새lease는종료뒤획득확인뿐이며슬롯점유·자동복구미실행을명시한다', () => {
  const phases = runtimeOwnershipPhases(parseRuntimeOwnershipCase(fresh(), now)!);
  const final = phases[3];
  assert.ok(final.facts.some(fact => fact.label === '새 lease 확인' && fact.value === '이전 child 종료 뒤 획득·검증·해제'));
  assert.ok(final.facts.some(fact => fact.label === 'DISPATCH / 슬롯' && fact.value === 'PENDING / 점유 유지'));
  assert.match(final.note, /새 daemon이나 업무 처리는 실행하지 않았습니다/);
  assert.match(final.note, /슬롯 해제·자동 복구·lag 0을 확인한 결과가 아닙니다/);
  assert.match(phases[1].note, /진행 중 I\/O의 차단을 뜻하지 않습니다/);
});

test('선택한검토필드만복사하고원문·metadata·binding은수정하지않는다', () => {
  const value = fresh(); const before = JSON.stringify(value);
  const metadataBefore = JSON.stringify(actualMetadata);
  const record = parseRuntimeOwnershipCase(value, now)!;
  assert.notEqual(record, value);
  assert.notEqual(record.summary, value.summary);
  assert.notEqual(record.summary.leaseLossResult, value.summary.leaseLossResult);
  runtimeOwnershipPhases(record);
  assert.equal(JSON.stringify(value), before);
  assert.equal(JSON.stringify(actualMetadata), metadataBefore);
  assert.equal(createHash('sha256').update(raw).digest('hex'), RUNTIME_OWNERSHIP_RAW_SHA256);
  assert.equal(RUNTIME_OWNERSHIP_BINDING.completedAt, '2026-10-20T14:00:19Z');
});
