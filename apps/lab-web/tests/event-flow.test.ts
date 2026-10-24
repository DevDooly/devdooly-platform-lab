import assert from 'node:assert/strict';
import test from 'node:test';
import type { Outcome } from '../src/lib/api.ts';
import { EVENT_RULE_SOURCE, explainEvent } from '../src/lib/event-flow.ts';

const outcome = (status: Outcome['status'], reason: string, fields: Partial<Outcome> = {}): Outcome => ({
  sequence: 1, eventId: 'event-1', sensorId: 'sensor-1', eventTime: '2026-10-24T00:00:00Z', value: 50,
  status, reason, ...fields,
});

test('known final classifications keep failed reasons and duplicates distinct', () => {
  for (const [status, reason, reasonTitle, resultTitle] of [
    ['SUCCESS', 'ACCEPTED', '이벤트 수용', '성공으로 보고됨'],
    ['DUPLICATE', 'DUPLICATE_EVENT_ID', '실행 내 이벤트 ID 중복', '중복으로 보고됨'],
    ['FAILED', 'INVALID_INPUT', '기본 입력 조건', '실패로 보고됨'],
    ['FAILED', 'INVALID_TIMESTAMP', 'Java 시각 해석', '실패로 보고됨'],
    ['FAILED', 'OUT_OF_RANGE', '값 범위 0~100', '실패로 보고됨'],
    ['FAILED', 'OUT_OF_ORDER', '센서별 최신 성공 시각', '실패로 보고됨'],
  ] as const) {
    const result = explainEvent(outcome(status, reason));
    assert.equal(result.matchesReference, true);
    assert.equal(result.reasonTitle, reasonTitle);
    assert.equal(result.resultTitle, resultTitle);
    assert.match(result.reasonText, /현재 참고 규칙/);
  }
  assert.match(explainEvent(outcome('SUCCESS', 'ACCEPTED')).resultText, /모두 저장.*SUCCESS만 시계열/);
  assert.match(explainEvent(outcome('FAILED', 'OUT_OF_RANGE')).resultText, /저장.*실패 사유 집계/);
  assert.match(explainEvent(outcome('DUPLICATE', 'DUPLICATE_EVENT_ID')).resultText, /저장.*실패와 분리/);
  assert.equal(EVENT_RULE_SOURCE, 'https://github.com/DevDooly/devdooly-platform-lab/blob/fda29d1647fb40b9312bbcd50b77eeefcab926e3/apps/api/src/main/java/io/github/devdooly/platformlab/demo/SensorProcessor.java');
});

test('reference explanations describe order and state without rejudging reported values or times', () => {
  const accepted = outcome('SUCCESS', 'ACCEPTED');
  assert.deepEqual(explainEvent(Object.freeze({ ...accepted, value: 101, eventTime: 'not-an-instant' })), explainEvent(accepted));
  assert.deepEqual(explainEvent(outcome('FAILED', 'OUT_OF_RANGE', { value: 50 })), explainEvent(outcome('FAILED', 'OUT_OF_RANGE', { value: 101 })));
  assert.deepEqual(explainEvent(outcome('FAILED', 'INVALID_TIMESTAMP', { eventTime: 'not-an-instant' })), explainEvent(outcome('FAILED', 'INVALID_TIMESTAMP')));
  const duplicate = explainEvent(outcome('DUPLICATE', 'DUPLICATE_EVENT_ID')).reasonText;
  assert.match(duplicate, /기본 입력 다음.*eventId 재등장/);
  assert.match(duplicate, /실패한 ID도 기억.*기본 입력이 유효하지 않은 경우에는 등록하지 않/);
  assert.match(explainEvent(outcome('FAILED', 'INVALID_TIMESTAMP')).reasonText, /이벤트 ID 중복 다음.*Java Instant\.parse/);
  assert.match(explainEvent(outcome('FAILED', 'OUT_OF_RANGE')).reasonText, /시각 해석 다음.*0~100.*0과 100도 허용/);
  assert.match(explainEvent(outcome('FAILED', 'OUT_OF_ORDER')).reasonText, /값 범위 다음.*같은 센서의 최신 성공 시각보다 이전.*동일 시각은 허용.*성공만 최신 시각을 갱신/);
});

test('null projection does not select or imply INVALID_INPUT', () => {
  for (const [status, reason] of [['SUCCESS', 'ACCEPTED'], ['FAILED', 'OUT_OF_RANGE'], ['FAILED', 'INVALID_INPUT']] as const) {
    assert.deepEqual(explainEvent(outcome(status, reason, { value: null })), explainEvent(outcome(status, reason)));
  }
  assert.match(explainEvent(outcome('FAILED', 'INVALID_INPUT', { value: null })).reasonText, /null만으로 원래 입력을 복원할 수는 없습니다/);
});

test('unknown reasons, PENDING and mismatched pairs remain unconfirmed and retain the report', () => {
  for (const [status, reason] of [
    ['FAILED', 'NEW_REASON'], ['FAILED', 'constructor'], ['SUCCESS', 'OUT_OF_RANGE'],
    ['FAILED', 'ACCEPTED'], ['FAILED', 'DUPLICATE_EVENT_ID'], ['DUPLICATE', 'OUT_OF_ORDER'],
    ['PENDING', 'ACCEPTED'], ['PENDING', 'PENDING'],
  ] as const) {
    const report = Object.freeze(outcome(status, reason, { value: null, eventTime: '' }));
    const before = { ...report };
    const result = explainEvent(report);
    assert.equal(result.matchesReference, false);
    assert.equal(result.reasonTitle, '현재 참고 규칙으로 확정할 수 없음');
    assert.equal(result.resultTitle, '보고된 분류 유지');
    assert.deepEqual(report, before);
  }
});
