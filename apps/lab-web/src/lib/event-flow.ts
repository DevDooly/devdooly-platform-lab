import type { Outcome } from './api.ts';

export const EVENT_RULE_SOURCE = 'https://github.com/DevDooly/devdooly-platform-lab/blob/fda29d1647fb40b9312bbcd50b77eeefcab926e3/apps/api/src/main/java/io/github/devdooly/platformlab/demo/SensorProcessor.java';

interface EventExplanation {
  matchesReference: boolean;
  reasonTitle: string;
  reasonText: string;
  resultTitle: string;
  resultText: string;
}

const referenceReasons = [
  { status: 'FAILED', reason: 'INVALID_INPUT', title: '기본 입력 조건',
    text: '현재 참고 규칙은 먼저 이벤트·eventId·sensorId·값의 존재, 두 ID의 공백과 값의 유한 여부를 확인합니다. 보고 값 null만으로 원래 입력을 복원할 수는 없습니다.' },
  { status: 'DUPLICATE', reason: 'DUPLICATE_EVENT_ID', title: '실행 내 이벤트 ID 중복',
    text: '현재 참고 규칙은 기본 입력 다음에 실행 내 eventId 재등장을 확인합니다. 이후 조건에서 실패한 ID도 기억하지만 기본 입력이 유효하지 않은 경우에는 등록하지 않습니다.' },
  { status: 'FAILED', reason: 'INVALID_TIMESTAMP', title: 'Java 시각 해석',
    text: '현재 참고 규칙은 기본 입력과 이벤트 ID 중복 다음에 Java Instant.parse로 시각을 해석합니다.' },
  { status: 'FAILED', reason: 'OUT_OF_RANGE', title: '값 범위 0~100',
    text: '현재 참고 규칙은 시각 해석 다음에 값이 0~100 범위인지 확인하며, 0과 100도 허용합니다.' },
  { status: 'FAILED', reason: 'OUT_OF_ORDER', title: '센서별 최신 성공 시각',
    text: '현재 참고 규칙은 값 범위 다음에 같은 센서의 최신 성공 시각보다 이전인지 확인합니다. 동일 시각은 허용하며 성공만 최신 시각을 갱신합니다.' },
  { status: 'SUCCESS', reason: 'ACCEPTED', title: '이벤트 수용',
    text: '현재 참고 규칙에서 ACCEPTED는 수용 사유이며, 수용한 이벤트의 시각으로 해당 센서의 최신 성공 시각을 갱신합니다.' },
] as const;

const referenceResults = {
  SUCCESS: { resultTitle: '성공으로 보고됨', resultText: '참고 구현은 성공·실패·중복 결과를 모두 저장하며, SUCCESS만 시계열(series)에 포함합니다.' },
  FAILED: { resultTitle: '실패로 보고됨', resultText: '참고 구현은 FAILED도 결과로 저장하며 실패 사유 집계에 포함합니다.' },
  DUPLICATE: { resultTitle: '중복으로 보고됨', resultText: '참고 구현은 DUPLICATE도 결과로 저장하며 실패와 분리해 집계합니다.' },
};

/** Explain reported status/reason against the pinned reference without replaying its checks. */
export function explainEvent(outcome: Outcome): EventExplanation {
  const reference = referenceReasons.find(rule => rule.status === outcome.status && rule.reason === outcome.reason);
  if (!reference) return {
    matchesReference: false,
    reasonTitle: '현재 참고 규칙으로 확정할 수 없음',
    reasonText: '알려진 status·reason 조합과 일치하지 않아 현재 참고 규칙의 판정에 연결할 수 없습니다.',
    resultTitle: '보고된 분류 유지',
    resultText: '보고된 status와 reason 원문을 확인하세요. 이 설명은 보고된 분류를 변경하지 않습니다.',
  };
  return { matchesReference: true, reasonTitle: reference.title, reasonText: reference.text, ...referenceResults[reference.status] };
}
