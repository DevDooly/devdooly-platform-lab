import { useEffect, useId, useState } from 'react';
import '../styles/kafka-recovery-case.css';

export type RecoveryCase = {
  id: string;
  label: string;
  title: string;
  stopPoint: string;
  dbState: string;
  kafkaState: string;
  resume: string;
  preserved: string[];
  logEnd: number;
  committedOffset: number;
  lag: number;
  runRows: number;
  outcomeRows: number;
};

type Props = { cases: RecoveryCase[] };

export default function KafkaRecoveryExplorer({ cases }: Props) {
  const instanceId = useId();
  const [selectedId, setSelectedId] = useState(cases[0]?.id ?? '');
  const [ready, setReady] = useState(false);
  useEffect(() => { setReady(true); }, []);
  const selected = cases.find(item => item.id === selectedId) ?? cases[0];
  if (!selected) {
    return <p className="kafka-recovery-empty">표시할 격리 시험 기록이 없습니다.</p>;
  }

  const noteId = `${instanceId}-note`;
  const readyId = `${instanceId}-ready`;
  const titleId = `${instanceId}-title`;
  return (
    <section className="kafka-recovery-explorer" aria-label="Kafka 중단 경계별 검증 기록">
      <p id={noteId} className="kafka-recovery-record-note">
        <strong>저장된 격리 시험 기록입니다.</strong> 중단 위치를 고르면 해당 시험의 결과를 보여줍니다. 새 작업이나 장애 시험을 실행하지 않습니다.
      </p>
      <p id={readyId} className="kafka-recovery-metric-note" role="status" aria-live="polite">
        {ready ? '중단 위치를 선택할 수 있습니다.' : '선택 화면을 준비 중입니다. 아래 첫 시험 기록은 읽을 수 있습니다.'}
      </p>

      <fieldset className="kafka-recovery-selector" aria-describedby={`${noteId} ${readyId}`} disabled={!ready}>
        <legend>중단 위치 선택</legend>
        <div className="kafka-recovery-choices">
          {cases.map(item => (
            <label key={item.id} className={`kafka-recovery-choice${selected.id === item.id ? ' is-selected' : ''}`}>
              <input
                type="radio"
                name={`${instanceId}-stop-point`}
                value={item.id}
                checked={selected.id === item.id}
                onChange={() => setSelectedId(item.id)}
              />
              <span>{item.label}</span>
            </label>
          ))}
        </div>
      </fieldset>

      <article className="kafka-recovery-detail" aria-labelledby={titleId}>
        <header className="kafka-recovery-detail-heading">
          <p className="kafka-recovery-kicker">선택한 시험</p>
          <h3 id={titleId} aria-live="polite" aria-atomic="true">{selected.title}</h3>
        </header>

        <div className="kafka-recovery-stop">
          <h4>중단 시점</h4>
          <p>{selected.stopPoint}</p>
        </div>

        <dl className="kafka-recovery-states">
          <div><dt>남아 있는 DB 상태</dt><dd>{selected.dbState}</dd></div>
          <div><dt>남아 있는 Kafka 상태</dt><dd>{selected.kafkaState}</dd></div>
        </dl>

        <div className="kafka-recovery-resume">
          <h4>다시 시작하면</h4>
          <p>{selected.resume}</p>
        </div>

        <div className="kafka-recovery-preserved">
          <h4>보존 여부를 확인한 항목</h4>
          <ul>{selected.preserved.map((item, index) => <li key={`${selected.id}-${index}`}>{item}</li>)}</ul>
        </div>

        <div className="kafka-recovery-results">
          <h4>이 시험의 최종 관측값</h4>
          <dl className="kafka-recovery-metrics">
            <div><dt>최종 log end</dt><dd>{selected.logEnd}</dd></div>
            <div><dt>다음 읽을 offset</dt><dd>{selected.committedOffset}</dd></div>
            <div><dt>최종 lag</dt><dd>{selected.lag}</dd></div>
            <div><dt>DB run 행</dt><dd>{selected.runRows}</dd></div>
            <div><dt>DB outcome 행</dt><dd>{selected.outcomeRows}</dd></div>
          </dl>
          <p className="kafka-recovery-metric-note">재개를 마친 뒤 관측한 값입니다. committed offset은 다음 읽을 위치이며, lag의 단위는 센서 행이 아닌 작업 envelope입니다.</p>
        </div>
      </article>
    </section>
  );
}
