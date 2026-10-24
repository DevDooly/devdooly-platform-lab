import { useId, useState } from 'react';
import type { Outcome } from '../lib/api';
import type { SourceMode } from '../lib/observation';
import { sensorOutcomeSummary, selectSensorGroups, type SensorGroupOrder, type SensorOutcomeGroup } from '../lib/sensor-outcomes';
import '../styles/sensor-outcomes.css';

export interface SensorOutcomeExplorerProps {
  outcomes: readonly Outcome[];
  runId: string;
  mode: SourceMode;
  observedAt: string | null;
  capturedAt: string | null;
  reportedInputCount: number;
  interactive: boolean;
  onViewEvents?: (sensorId: string, status: 'ALL' | 'FAILED') => void;
}

interface SensorView {
  context: SensorOutcomeExplorerProps;
  query: string;
  order: SensorGroupOrder;
  limit: number;
}

const sourceLabels: Record<SourceMode, string> = {
  live: 'live · API 조회', recorded: 'recorded · 게시 관측', fixture: 'fixture · 고정 샘플 기대값',
};
const number = (value: number) => value.toLocaleString('ko-KR');
const raw = (value: string) => value === '' ? '"" · 빈 문자열' : JSON.stringify(value);
const initialView = (context: SensorOutcomeExplorerProps): SensorView => ({ context, query: '', order: 'first', limit: 20 });
const sameContext = (before: SensorOutcomeExplorerProps, after: SensorOutcomeExplorerProps) =>
  before.outcomes === after.outcomes && before.runId === after.runId && before.mode === after.mode
  && before.observedAt === after.observedAt && before.capturedAt === after.capturedAt
  && before.reportedInputCount === after.reportedInputCount;

function FailureReasons({ group }: { group: SensorOutcomeGroup }) {
  return group.failureReasons.length === 0 ? <span className="sensor-no-failures">FAILED 없음</span>
    : <details className="sensor-failure-reasons">
      <summary>사유 {number(group.failureReasons.length)}종 보기</summary>
      <ul>{group.failureReasons.map(item => <li key={item.reason}>
        <code>{raw(item.reason)}</code><span>{number(item.count)}건</span>
      </li>)}</ul>
    </details>;
}

function SensorEventActions({ group, interactive, onViewEvents }: {
  group: SensorOutcomeGroup;
  interactive: boolean;
  onViewEvents: SensorOutcomeExplorerProps['onViewEvents'];
}) {
  if (!onViewEvents) return null;
  return <div className="sensor-event-actions">
    <button type="button" disabled={!interactive}
      aria-label={`센서 ${JSON.stringify(group.sensorId)} 이벤트 전체 보기`}
      onClick={() => onViewEvents(group.sensorId, 'ALL')}>이벤트 전체 보기</button>
    {group.failure > 0 && <button type="button" disabled={!interactive}
      aria-label={`센서 ${JSON.stringify(group.sensorId)} 실패 이벤트 보기`}
      onClick={() => onViewEvents(group.sensorId, 'FAILED')}>실패 이벤트 보기</button>}
  </div>;
}

export default function SensorOutcomeExplorer(props: SensorOutcomeExplorerProps) {
  const [savedView, setView] = useState<SensorView>(() => initialView(props));
  const id = useId();
  // A newly displayed response starts its own view, including a same-run refresh.
  const view = sameContext(savedView.context, props) ? savedView : initialView(props);
  if (view !== savedView) setView(view);
  const summary = sensorOutcomeSummary(props.outcomes);
  const matching = selectSensorGroups(summary.sensors, view.query, view.order);
  const visible = matching.slice(0, view.limit);
  const update = (change: Partial<Pick<SensorView, 'query' | 'order' | 'limit'>>) => setView({ ...view, ...change });

  return <section className="sensor-outcomes" aria-label="센서별 결과 분포">
    <header className="sensor-outcomes-heading">
      <h4>센서별 결과 분포</h4>
      <p>어떤 센서에 실패가 모였는지, 이번 응답에 포함된 이벤트를 센서 ID별로 묶어 봅니다.</p>
    </header>
    <div className="sensor-outcomes-summary">
      <div><span>응답에 나타난 센서</span><strong>{number(summary.sensors.length)}개</strong></div>
      <div><span>조회된 outcomes</span><strong>{number(summary.availableOutcomes)}건</strong></div>
      <div><span>보고된 입력 · inputCount</span><strong>{number(props.reportedInputCount)}건</strong></div>
    </div>
    <p className="sensor-outcomes-scope">현재 응답의 전체 outcomes를 집계합니다. 이벤트 탭의 검색·상태·사유·페이지 조건은 적용하지 않습니다.
      입력 건수와 조회 건수가 같아도 전체 입력의 누락 여부가 검증된 것은 아닙니다. 실패 비율은 센서별 조회 건수 중 FAILED 비율이며 처리 시간이나 센서 장애율을 뜻하지 않습니다.</p>
    {summary.availableOutcomes !== props.reportedInputCount && <p className="sensor-outcomes-scope">조회된 이벤트와 보고된 입력 건수가 다릅니다. 아래 분포는 응답에 포함된 행만 집계하며 누락된 센서나 결과를 채우지 않습니다.</p>}
    <dl className="sensor-outcomes-provenance">
      <div><dt>표시 출처</dt><dd>{sourceLabels[props.mode]}</dd></div>
      <div><dt>실행 · runId</dt><dd><code>{props.runId}</code></dd></div>
      <div><dt>관측 · observedAt</dt><dd><code>{props.observedAt === null ? 'null' : props.observedAt}</code></dd></div>
      {props.mode !== 'live' && <div><dt>{props.mode === 'recorded' ? '수집' : '파일 생성'} · capturedAt</dt>
        <dd><code>{props.capturedAt === null ? 'null' : props.capturedAt}</code></dd></div>}
    </dl>
    <div className="sensor-outcomes-controls">
      <div><label htmlFor={`${id}-query`}>센서 ID 포함 검색</label>
        <input id={`${id}-query`} type="search" value={view.query} disabled={!props.interactive}
          placeholder="예: sensor-1" aria-describedby={`${id}-hint`}
          onChange={event => update({ query: event.target.value, limit: 20 })} /></div>
      <div><label htmlFor={`${id}-order`}>센서 정렬</label>
        <select id={`${id}-order`} value={view.order} disabled={!props.interactive}
          onChange={event => update({ order: event.target.value as SensorGroupOrder, limit: 20 })}>
          <option value="first">응답 첫 등장순</option>
          <option value="failure-count">실패 건수 많은순</option>
          <option value="failure-rate">실패 비율 높은순</option>
        </select></div>
      <button type="button" disabled={!props.interactive || view.query === ''}
        onClick={() => update({ query: '', limit: 20 })}>센서 검색 지우기</button>
    </div>
    <p id={`${id}-hint`} className="sensor-outcomes-hint">앞뒤 공백을 제외하고 대소문자 구분 없이 센서 ID 안에서 찾습니다. {props.onViewEvents
      ? 'eventId는 검색하지 않습니다. 센서 목록의 검색·정렬은 이벤트 탭의 필터를 바꾸지 않습니다. 이벤트 보기 버튼은 센서 ID 원문이 정확히 일치하는 조건으로 이벤트 탭을 열며, 기존 검색어·사유·선택·페이지 조건을 초기화합니다.'
      : 'eventId는 검색하지 않으며 이벤트 탭의 필터는 바뀌지 않습니다.'}
      센서 ID와 실패 사유는 JSON 문자열 표기로 보여 공백·빈 문자열·대소문자 차이를 구분합니다. 비율은 소수점 아래 두 자리까지 표시하며 정렬은 반올림 전 값으로 합니다. 같은 값은 응답 첫 등장순입니다.</p>
    <p className="sensor-outcomes-status" role="status" aria-live="polite" aria-atomic="true">
      전체 {number(summary.sensors.length)}개 센서 중 검색 {number(matching.length)}개 · 표시 {number(visible.length)}개
    </p>
    {matching.length === 0 ? <p className="sensor-outcomes-empty">{summary.sensors.length === 0
      ? '이번 응답에 센서별로 집계할 이벤트가 없습니다.' : '검색 조건에 맞는 센서 ID가 없습니다.'}</p>
      : <>
        <div className="sensor-outcomes-desktop" role="region" aria-label="센서별 결과 표 · 가로 스크롤 가능" tabIndex={0}>
          <table className="sensor-outcomes-table">
            <caption>센서별 조회 건수와 처리 상태 · FAILED / 센서별 조회 건수 × 100</caption>
            <thead><tr><th scope="col">sensorId 원문</th><th scope="col">조회</th><th scope="col">성공</th><th scope="col">실패</th>
              <th scope="col">중복</th><th scope="col">대기</th><th scope="col">실패 비율</th><th scope="col">FAILED 사유 원문</th></tr></thead>
            <tbody>{visible.map(group => <tr key={group.sensorId}>
              <th scope="row"><code>{raw(group.sensorId)}</code><SensorEventActions group={group} interactive={props.interactive} onViewEvents={props.onViewEvents} /></th><td>{number(group.total)}</td>
              <td>{number(group.success)}</td><td>{number(group.failure)}</td><td>{number(group.duplicate)}</td><td>{number(group.pending)}</td>
              <td>{group.failureRate.toFixed(2)}%</td><td><FailureReasons group={group} /></td>
            </tr>)}</tbody>
          </table>
        </div>
        <ul className="sensor-outcomes-mobile" aria-label="센서별 결과 카드">{visible.map(group => <li key={group.sensorId}>
          <h5><code>{raw(group.sensorId)}</code></h5>
          <SensorEventActions group={group} interactive={props.interactive} onViewEvents={props.onViewEvents} />
          <dl><div><dt>조회</dt><dd>{number(group.total)}건</dd></div>
            <div><dt>성공 · SUCCESS</dt><dd>{number(group.success)}건</dd></div>
            <div><dt>실패 · FAILED</dt><dd>{number(group.failure)}건</dd></div>
            <div><dt>중복 · DUPLICATE</dt><dd>{number(group.duplicate)}건</dd></div>
            <div><dt>대기 · PENDING</dt><dd>{number(group.pending)}건</dd></div>
            <div><dt>실패 / 조회</dt><dd>{group.failureRate.toFixed(2)}%</dd></div></dl>
          <div className="sensor-mobile-reasons"><strong>FAILED 사유 원문</strong><FailureReasons group={group} /></div>
        </li>)}</ul>
      </>}
    {matching.length > 20 && <div className="sensor-outcomes-more">
      <button type="button" disabled={!props.interactive || visible.length >= matching.length}
        onClick={() => update({ limit: view.limit + 20 })}>센서 20개 더 보기</button>
      <button type="button" disabled={!props.interactive || view.limit <= 20}
        onClick={() => update({ limit: 20 })}>처음 20개로 접기</button>
    </div>}
  </section>;
}
