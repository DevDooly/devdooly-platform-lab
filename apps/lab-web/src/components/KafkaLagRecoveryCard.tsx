import { useId, useMemo, useRef, useState } from 'react';
import { kafkaLagPhaseKey, kafkaLagPhases, parseKafkaLagRecovery } from '../lib/kafka-lag-recovery.ts';
import '../styles/kafka-lag-recovery.css';

const repository = 'https://github.com/DevDooly/devdooly-platform-lab';
const evidenceUrl = `${repository}/blob/main/docs/evidence/kafka-lag-recovery/README.md`;

/** Saved validated props only: phase selection never contacts Kafka or executes a workload. */
export default function KafkaLagRecoveryCard({ record }: { record?: unknown }) {
  const evidence = useMemo(() => parseKafkaLagRecovery(record), [record]);
  const [selected, setSelected] = useState(3);
  const buttons = useRef<Array<HTMLButtonElement | null>>([]);
  const identifier = useId();
  const detailId = `${identifier}-detail`;
  const svgTitleId = `${identifier}-svg-title`;
  const svgDescriptionId = `${identifier}-svg-description`;
  const svgArrowId = `${identifier}-svg-arrow`;
  const stages = evidence ? kafkaLagPhases(evidence) : [];
  const stage = stages[selected];
  return <section id="kafka-lag-recovery" className="section kafka-lag-recovery" aria-labelledby={`${identifier}-title`}>
    <div className="section-heading kafka-lag-heading"><div>
      <span className="eyebrow">KAFKA / COMMIT AND RESUME</span>
      <h2 id={`${identifier}-title`}>소비자를 정상 종료한 뒤,<br/>어디서 다시 읽을까요?</h2>
      <p>격리 Kafka의 합성 메시지로 commit·대기량·새 소비자의 재개 지점을 확인하는 시험입니다.</p>
    </div><span className="tag">저장된 격리 검증 · {evidence ? '결과 확인' : '공개 기록 대기'}</span></div>
    {evidence && stage ? <>
      <p className="kafka-lag-context">아래는 한 번의 격리 실행 기록입니다. 운영 Kafka의 현재 상태나 처리량을 나타내지 않습니다.
        {' '}실행 완료 <time dateTime={evidence.completedAt}>{new Intl.DateTimeFormat('ko-KR', { timeZone: 'Asia/Seoul', dateStyle: 'medium', timeStyle: 'medium' }).format(new Date(evidence.completedAt))} KST</time></p>
      <div className="kafka-lag-controls" role="group" aria-label="저장된 Kafka 복구 단계" aria-describedby={`${identifier}-hint`}>
        {stages.map((item, index) => <button key={item.id} type="button"
          ref={element => { buttons.current[index] = element; }}
          aria-pressed={selected === index} aria-controls={detailId}
          onClick={() => setSelected(index)} onKeyDown={event => {
            const next = kafkaLagPhaseKey(index, event.key);
            if (next === null) return;
            event.preventDefault(); setSelected(next); buttons.current[next]?.focus();
          }}><span>{index + 1}</span>{item.title}</button>)}
      </div>
      <p id={`${identifier}-hint`} className="kafka-lag-note">저장된 단계 선택 · Tab·Enter·Space와 좌우 방향키·Home·End를 사용할 수 있습니다. 메시지를 발행하거나 소비하지 않습니다.</p>
      <figure className="kafka-lag-chart" tabIndex={0} aria-label="단계별 offset 차이 차트. 작은 화면에서는 가로로 이동할 수 있습니다.">
        <svg viewBox="0 0 640 220" role="img" aria-labelledby={`${svgTitleId} ${svgDescriptionId}`}>
          <title id={svgTitleId}>단계별 offset 차이(lag): 8, 8, 14, 0</title>
          <desc id={svgDescriptionId}>처음 commit 후 8, 정상 종료 후 8, 추가 발행 후 14, 새 소비자가 재가입해 읽은 뒤 0입니다. 화살표와 가로축은 단계 순서이며 경과 시간이나 처리 속도를 뜻하지 않습니다.</desc>
          <defs><marker id={svgArrowId} markerWidth="7" markerHeight="7" refX="6" refY="3" orient="auto" markerUnits="strokeWidth">
            <path d="M0 0 L6 3 L0 6 Z" className="kafka-lag-arrow"/>
          </marker></defs>
          <text x="30" y="25" className="kafka-lag-axis-title">Offset 차이(lag)</text>
          {[0, 8, 14].map(lag => <g key={lag}>
            <line x1="58" x2="610" y1={175 - lag * 8} y2={175 - lag * 8} className="kafka-lag-grid-line"/>
            <text x="42" y={180 - lag * 8} textAnchor="end" className="kafka-lag-tick">{lag}</text>
          </g>)}
          {['M102 111 H236', 'M264 107 L396 67', 'M422 71 L557 166'].map(path =>
            <path key={path} d={path} fill="none" markerEnd={`url(#${svgArrowId})`} className="kafka-lag-trace"/>)}
          {stages.map((item, index) => <g key={item.id}>
            <circle cx={90 + index * 160} cy={175 - item.lag * 8} r={selected === index ? 9 : 6}
              className={selected === index ? 'kafka-lag-point is-selected' : 'kafka-lag-point'}/>
            <text x={90 + index * 160} y={155 - item.lag * 8} textAnchor="middle" className="kafka-lag-value">{item.lag}</text>
            <text x={90 + index * 160} y="207" textAnchor="middle" className="kafka-lag-tick">{index + 1}단계</text>
          </g>)}
        </svg>
        <figcaption>화살표는 단계의 진행만 나타냅니다. 가로 간격은 경과 시간·처리 속도와 관계없습니다. 정확한 값은 아래 표에서도 읽을 수 있습니다.</figcaption>
      </figure>
      <div id={detailId} className="kafka-lag-selected" role="status" aria-live="polite" aria-atomic="true">
        <h3>{selected + 1}단계 · {stage.title}</h3><p>{stage.description}</p>
        <dl><div><dt>그룹</dt><dd>{stage.group}</dd></div><div><dt>READ_COMMITTED end</dt><dd>{stage.end}</dd></div>
          <div><dt>Commit</dt><dd>{stage.committed}</dd></div><div><dt>Offset 차이(lag)</dt><dd>{stage.lag}</dd></div></dl>
      </div>
      <div className="kafka-lag-table-scroll" tabIndex={0} role="region" aria-label="네 단계의 offset 값. 작은 화면에서는 가로로 이동할 수 있습니다."><table className="kafka-lag-table">
        <caption>같은 대상에서 확인한 네 단계 · lag = READ_COMMITTED end − commit</caption>
        <thead><tr><th scope="col">단계</th><th scope="col">그룹</th><th scope="col">End</th><th scope="col">Commit</th><th scope="col">Lag</th></tr></thead>
        <tbody>{stages.map((item, index) => <tr key={item.id} aria-current={selected === index ? 'step' : undefined}>
          <th scope="row">{index + 1}. {item.title}</th><td>{item.group}</td><td>{item.end}</td><td>{item.committed}</td><td>{item.lag}</td>
        </tr>)}</tbody>
      </table></div>
      <p className="kafka-lag-boundary">소비자를 정상 종료하고 새 클라이언트로 재개한 시험입니다. 합성 메시지의 읽기와 key·value 확인이며 운영 worker의 업무 처리를 검증한 결과가 아닙니다. 프로세스 강제 중단·broker 재시작·DB/export 복원·운영 장애 복구·고가용성 검증과 구분합니다. 단계 선택은 정적 기록 조회입니다.</p>
      <nav className="kafka-lag-links" aria-label="Kafka 복구 검증 근거">
        <a href={evidence.runUrl} target="_blank" rel="noreferrer">실제 GitHub 실행 ↗</a>
        <a href={`${repository}/commit/${evidence.summary.sourceCommit}`} target="_blank" rel="noreferrer">검증 소스 ↗</a>
        <a href={evidenceUrl} target="_blank" rel="noreferrer">검증 조건과 한계 ↗</a>
      </nav>
      <details className="kafka-lag-provenance"><summary>검증 출처 확인</summary><dl>
        <div><dt>테스트</dt><dd>기대 {evidence.summary.expectedTests}개 · 확인 {evidence.summary.verifiedTests}개</dd></div>
        <div><dt>검증 소스 SHA</dt><dd><code>{evidence.summary.sourceCommit}</code></dd></div>
        <div><dt>실행 파일 목록 SHA-256</dt><dd><code>{evidence.summary.runtimeManifestSha256}</code></dd></div>
        <div><dt>JUnit XML SHA-256</dt><dd><code>{evidence.summary.surefireXmlSha256}</code></dd></div>
      </dl><p>원본 소스·산출물 보존과 소유 시험 자원의 정리를 확인한 공개 요약입니다. 이 화면의 계약 검사는 기록의 전자서명이나 독립 감사를 제공하지 않습니다.</p></details>
    </> : <div className="kafka-lag-empty" role="status"><h3>검증한 공개 기록을 기다리고 있습니다.</h3>
      <p>실제 실행·JUnit 결과·정리 기록을 확인한 요약이 연결되면 단계별 값을 표시합니다. 미확인 결과를 lag 0이나 복구 성공으로 채우지 않습니다.</p></div>}
  </section>;
}
