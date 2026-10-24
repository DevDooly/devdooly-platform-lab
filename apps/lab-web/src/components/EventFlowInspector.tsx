import { useEffect, useRef } from 'react';
import type { Outcome } from '../lib/api';
import type { SourceMode } from '../lib/observation';
import { EVENT_RULE_SOURCE, explainEvent } from '../lib/event-flow';
import '../styles/event-flow.css';

export interface EventFlowInspectorProps {
  outcomes: Outcome[];
  selectedSequence: number | null;
  onSelect: (sequence: number | null) => void;
  runId: string;
  mode: SourceMode;
  observedAt: string | null;
  capturedAt?: string | null;
  interactive: boolean;
}

const sourceLabels: Record<SourceMode, string> = {
  live: 'live · API 조회',
  recorded: 'recorded · 게시 관측',
  fixture: 'fixture · 고정 샘플 기대값',
};

export default function EventFlowInspector({
  outcomes, selectedSequence, onSelect, runId, mode, observedAt, capturedAt, interactive,
}: EventFlowInspectorProps) {
  const selected = selectedSequence === null ? undefined : outcomes.find(outcome => outcome.sequence === selectedSequence);
  const explanation = selected ? explainEvent(selected) : null;
  const detailHeading = useRef<HTMLHeadingElement>(null);
  const hasSelection = selected !== undefined;

  useEffect(() => {
    if (!hasSelection) return;
    detailHeading.current?.focus({ preventScroll: true });
    detailHeading.current?.scrollIntoView({ behavior: 'auto', block: 'start' });
  }, [selectedSequence, runId, mode, hasSelection]);

  return <section className="event-flow" aria-labelledby="event-flow-title">
    <div className="event-flow-heading">
      <h4 id="event-flow-title">이벤트 판정 흐름</h4>
      <p>한 이벤트의 응답 필드와 보고된 판정 사유를 함께 봅니다.</p>
    </div>
    <div className="event-flow-picker">
      <label htmlFor="event-flow-select">흐름을 볼 이벤트</label>
      <select id="event-flow-select" value={selected ? String(selected.sequence) : ''}
        disabled={!interactive || outcomes.length === 0}
        onChange={event => onSelect(event.target.value === '' ? null : Number(event.target.value))}>
        <option value="">이벤트를 선택하세요</option>
        {outcomes.map(outcome => <option key={outcome.sequence} value={String(outcome.sequence)}>
          {outcome.status} · {outcome.eventId} · sequence {outcome.sequence}
        </option>)}
      </select>
    </div>
    <p className="event-flow-scope">단계별 trace와 당시 코드 버전은 제공되지 않습니다. 아래는 현재 참고 규칙 해설이며 재실행한 기록이 아닙니다.{' '}
      <a href={EVENT_RULE_SOURCE} target="_blank" rel="noreferrer">
        SensorProcessor · fda29d1 <span aria-hidden="true">↗</span>
      </a>
    </p>
    <dl className="event-flow-provenance">
      <div><dt>표시 출처</dt><dd>{sourceLabels[mode]}</dd></div>
      <div><dt>실행 · runId</dt><dd><code>{runId}</code></dd></div>
      <div><dt>관측 · observedAt</dt><dd><code>{observedAt === null ? 'null' : observedAt}</code></dd></div>
      {mode !== 'live' && <div><dt>{mode === 'recorded' ? '수집' : '파일 생성'} · capturedAt</dt>
        <dd><code>{capturedAt === undefined ? '미제공' : capturedAt === null ? 'null' : capturedAt}</code></dd>
      </div>}
    </dl>
    {selected && explanation ? <div className="event-flow-detail">
      <h5 id="event-flow-detail-title" className="event-flow-detail-title" ref={detailHeading} tabIndex={-1}>
        선택한 이벤트 · sequence {selected.sequence}
      </h5>
      <div className="event-flow-cards">
        <article className="event-flow-card" aria-labelledby="event-flow-fields-title">
          <div className="event-flow-card-heading"><span aria-hidden="true">01</span><h6 id="event-flow-fields-title">응답에 남은 이벤트 필드</h6></div>
          <dl className="event-flow-fields">
            <div><dt>sequence</dt><dd><code>{selected.sequence}</code></dd></div>
            <div><dt>eventId</dt><dd><code>{selected.eventId}</code></dd></div>
            <div><dt>sensorId</dt><dd><code>{selected.sensorId}</code></dd></div>
            <div><dt>eventTime 원문</dt><dd><code>{selected.eventTime}</code></dd></div>
            <div><dt>value</dt><dd><code>{selected.value === null ? 'null' : String(selected.value)}</code></dd></div>
          </dl>
          {selected.value === null && <p className="event-flow-null-note">응답의 null만으로 원본 null과 비유한 수를 구분할 수 없습니다.</p>}
        </article>
        <article className="event-flow-card" aria-labelledby="event-flow-reason-title">
          <div className="event-flow-card-heading"><span aria-hidden="true">02</span><h6 id="event-flow-reason-title">보고된 판정 사유</h6></div>
          <dl className="event-flow-raw"><div><dt>reason 원문</dt><dd><code>{selected.reason}</code></dd></div></dl>
          <p className="event-flow-explanation-title">{explanation.reasonTitle}</p>
          <p>{explanation.reasonText}</p>
        </article>
        <article className="event-flow-card" aria-labelledby="event-flow-result-title">
          <div className="event-flow-card-heading"><span aria-hidden="true">03</span><h6 id="event-flow-result-title">보고된 결과 분류</h6></div>
          <dl className="event-flow-raw"><div><dt>status 원문</dt><dd><code>{selected.status}</code></dd></div></dl>
          <p className="event-flow-explanation-title">{explanation.resultTitle}</p>
          <p>{explanation.resultText}</p>
        </article>
      </div>
    </div> : <p className="event-flow-empty">{outcomes.length === 0
      ? '현재 검색·처리 상태·사유 조건에 표시할 이벤트가 없습니다.'
      : '이벤트를 선택하면 응답 필드, 판정 사유, 결과 분류를 볼 수 있습니다.'}</p>}
  </section>;
}
