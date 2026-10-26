import recorded from '../../../../docs/evidence/kafka-redelivery/summary.json';
import type { RecoveryCase } from '../components/KafkaRecoveryExplorer';

const explanations = [
  {
    id: 'publisher-ack-kill', label: '발행 확인 직후',
    title: 'broker는 받았지만, DB는 발행 완료를 모릅니다.',
    stopPoint: 'broker ACK 뒤, DISPATCH intent의 DB 확인 처리 전 publisher JVM을 종료했습니다.',
    dbState: 'DISPATCH intent가 PENDING으로 남습니다. 이 시점에 DB 결과 처리를 완료했다고 가정하지 않습니다.',
    kafkaState: '이미 저장된 작업 envelope가 있습니다. DB의 PENDING을 보고 같은 작업을 다시 발행하면 record가 하나 더 생깁니다.',
    resume: 'PENDING intent를 다시 발행합니다. 두 record의 runId가 같으므로, 첫 처리가 완료된 뒤의 재전달에서는 기존 DB 결과를 반환합니다.',
    preserved: ['최종 DB run은 1개, outcome은 12개', '완료 작업의 기존 결과·원본·완료 시각 보존', 'Kafka record 2개와 업무 결과 1개를 구분'],
  },
  {
    id: 'worker-before-dbcommit-kill', label: 'DB commit 직전',
    title: 'SQL을 실행했어도, commit 전의 결과는 확정되지 않습니다.',
    stopPoint: '실제 SQL 실행 뒤, DB 트랜잭션 commit 전 worker JVM을 종료했습니다.',
    dbState: '다른 DB 연결에서 rollback과 처리 결과 부재를 확인했습니다. 미완료 SQL을 완료 결과로 취급하지 않습니다.',
    kafkaState: 'DB 처리 뒤에 실행할 offset commit에 도달하지 않았습니다. 이 시험의 새 consumer group에는 commit된 offset이 없어 earliest 정책으로 같은 offset 0을 다시 읽습니다.',
    resume: '원본을 다시 검증하고 작업을 처리합니다. 결과·COMPLETED 상태·EXPORT intent를 같은 DB 트랜잭션에서 확정한 뒤 다음 offset을 commit합니다.',
    preserved: ['rollback된 결과를 남기거나 누적하지 않음', '최종 DB run 1개·outcome 12개', '미완료 작업을 재처리하여 완료'],
  },
  {
    id: 'worker-after-db-kill', label: 'DB commit 직후',
    title: 'DB 결과는 남았지만, Kafka 진행 위치는 아직입니다.',
    stopPoint: 'DB commit 뒤, Kafka offset commit 전 worker JVM을 종료했습니다.',
    dbState: 'COMPLETED 작업과 결과·EXPORT intent가 남습니다. 이미 확정된 완료 시각도 유지됩니다.',
    kafkaState: '다음 offset이 아직 commit되지 않은 지점입니다. 같은 record가 다시 전달될 수 있습니다.',
    resume: '같은 runId와 원본 SHA를 확인합니다. DB가 이미 COMPLETED면 결과를 다시 만들지 않고 기존 작업을 반환한 뒤 offset + 1을 commit합니다.',
    preserved: ['완료 결과와 처리 시각을 다시 쓰지 않음', '완료 작업 replay 관측 1회', '최종 DB run 1개·outcome 12개'],
  },
];

/** Numeric results come from the existing public experiment, not from a browser simulation. */
export const kafkaRecoveryCases: RecoveryCase[] = explanations.map(explanation => {
  const result = recorded.actualServiceIt.finalCases.find(item => item.case === explanation.id);
  if (!result) throw new Error(`Missing recorded Kafka case: ${explanation.id}`);
  return { ...explanation, logEnd: result.logEnd, committedOffset: result.committedOffset,
    lag: result.lag, runRows: result.runRows, outcomeRows: result.outcomeRows };
});

export const kafkaRecoveryVerifiedOn = recorded.verifiedOn;
