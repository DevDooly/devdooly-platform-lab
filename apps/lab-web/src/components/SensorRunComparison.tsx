import { useId, useState } from 'react';
import type { RunDetail } from '../lib/api';
import type { ComparisonSources } from '../lib/run-comparison';
import type { SensorOutcomeGroup } from '../lib/sensor-outcomes';
import { compareSensorOutcomes, selectSensorComparisons, type SensorComparisonOrder } from '../lib/sensor-comparison';
import { eventSharePath } from '../lib/event-share';
import '../styles/sensor-comparison.css';

export interface SensorRunComparisonProps {
  left: RunDetail;
  right: RunDetail;
  sources: ComparisonSources;
  basePath: string;
  interactive: boolean;
}

interface SensorComparisonView {
  left: RunDetail;
  right: RunDetail;
  query: string;
  differencesOnly: boolean;
  order: SensorComparisonOrder;
  limit: number;
}

type SensorComparisonRow = ReturnType<typeof compareSensorOutcomes>['rows'][number];
const count = (value: number) => value.toLocaleString('ko-KR');
const signed = (value: number) => `${value > 0 ? '+' : value < 0 ? '−' : ''}${count(Math.abs(value))}`;
const rate = (value: number) => `${value.toFixed(2)}%`;
const rateDifference = (value: number) => `${value > 0 ? '+' : value < 0 ? '−' : ''}${Math.abs(value).toFixed(2)}%p`;
const rawId = (value: string) => value === '' ? '"" · 빈 문자열' : JSON.stringify(value);
const metrics = [
  ['total', '조회'], ['success', '성공'], ['failure', '실패'], ['duplicate', '중복'], ['pending', '대기'],
] as const;
const initialView = (left: RunDetail, right: RunDetail): SensorComparisonView => ({
  left, right, query: '', differencesOnly: false, order: 'first', limit: 20,
});

function RawTimestamp({ value }: { value: string | null }) {
  return value === null ? <span>기록 없음 · null</span> : <time dateTime={value}>{value}</time>;
}

function SensorLinks({ group, side, runId, basePath, interactive }: {
  group: SensorOutcomeGroup;
  side: 'A' | 'B';
  runId: string;
  basePath: string;
  interactive: boolean;
}) {
  const actions = (['ALL', ...(group.failure > 0 ? ['FAILED'] : [])] as ('ALL' | 'FAILED')[]).map(status => ({
    status,
    label: status === 'ALL' ? `${side} 이벤트 전체 보기` : `${side} 실패 이벤트 보기`,
    path: eventSharePath({ runId, filters: { status, query: '', reason: null, sensorId: group.sensorId }, sequence: null }, basePath),
  })).filter(action => action.path !== null);
  if (actions.length === 0) return null;
  return <div className="scm-event-actions">{actions.map(action => interactive
    ? <a key={action.status} href={action.path!} aria-label={`${side} 센서 ${JSON.stringify(group.sensorId)} ${action.status === 'ALL' ? '이벤트 전체 보기' : '실패 이벤트 보기'}`}>{action.label}</a>
    : <span key={action.status} className="scm-event-disabled" aria-disabled="true">{action.label} · 조회 중 사용 불가</span>)}</div>;
}

function SensorSide({ group, side, runId, basePath, interactive }: {
  group: SensorOutcomeGroup | null;
  side: 'A' | 'B';
  runId: string;
  basePath: string;
  interactive: boolean;
}) {
  if (group === null) return <p className="scm-unobserved">이 응답에 미관측</p>;
  return <>
    <dl className="scm-counts">{metrics.map(([key, label]) => <div key={key}><dt>{label}</dt><dd>{count(group[key])}건</dd></div>)}
      <div><dt>실패 / 조회</dt><dd>{rate(group.failureRate)}</dd></div></dl>
    <SensorLinks group={group} side={side} runId={runId} basePath={basePath} interactive={interactive} />
  </>;
}

function SensorDelta({ row }: { row: SensorComparisonRow }) {
  if (row.delta === null || row.failureRateDelta === null) return <p className="scm-unobserved">산정 안 함 · 한쪽 응답에 미관측</p>;
  return <dl className="scm-counts scm-deltas">{metrics.map(([key, label]) => <div key={key}><dt>{label}</dt><dd>{signed(row.delta![key])}건</dd></div>)}
    <div><dt>실패 비율 차이</dt><dd>{rateDifference(row.failureRateDelta)}</dd></div></dl>;
}

export default function SensorRunComparison({ left, right, sources, basePath, interactive }: SensorRunComparisonProps) {
  const id = useId();
  const [savedView, setView] = useState(() => initialView(left, right));
  // Draft IDs and failed requests keep the displayed pair; only a new displayed pair resets this view.
  const view = savedView.left === left && savedView.right === right ? savedView : initialView(left, right);
  if (view !== savedView) setView(view);
  const comparison = compareSensorOutcomes(left.outcomes, right.outcomes);
  const matching = selectSensorComparisons(comparison.rows, view);
  const visible = matching.slice(0, view.limit);
  const update = (change: Partial<Pick<SensorComparisonView, 'query' | 'differencesOnly' | 'order' | 'limit'>>) => setView({ ...view, ...change });

  return <section className="sensor-run-comparison" aria-labelledby={`${id}-title`}>
    <header><h3 id={`${id}-title`}>센서별 A·B 결과 비교</h3>
      <p>표시 중인 두 응답의 outcomes를 센서 ID 원문이 정확히 같은 행끼리 묶어 비교합니다. 차이는 B − A입니다.</p></header>
    <div className="scm-sources">{(['left', 'right'] as const).map((key, index) => {
      const side = index === 0 ? 'A' : 'B';
      const run = key === 'left' ? left : right;
      const summary = comparison[key];
      return <article key={key} aria-label={`${side} 센서 집계 출처`}>
        <h4>{side} · 집계 출처</h4><dl>
          <div><dt>실행 · runId</dt><dd><code>{run.id}</code></dd></div>
          <div><dt>조회된 outcomes</dt><dd>{count(summary.availableOutcomes)}건</dd></div>
          <div><dt>보고된 입력 · inputCount</dt><dd>{count(run.inputCount)}건</dd></div>
          <div><dt>응답의 센서</dt><dd>{count(summary.sensors.length)}개</dd></div>
          <div><dt>API 관측 · observedAt</dt><dd><RawTimestamp value={run.observedAt} /></dd></div>
          <div><dt>브라우저 수신 시각</dt><dd><RawTimestamp value={sources[key].receivedAt} /></dd></div>
          <div><dt>조회 경로</dt><dd><code>GET {sources[key].path}</code></dd></div>
        </dl>
      </article>;
    })}</div>
    <p className="scm-note">A·B는 별도 GET으로 조회한 응답이며 같은 순간의 원자적 관측이 아닙니다. 응답에 포함된 행만 비교하며,
      조회 건수와 inputCount가 같아도 전체 입력의 누락 여부가 검증된 것은 아닙니다. 실패 비율의 분모는 각 센서의 조회 건수입니다.</p>
    <p className="scm-note">‘미관측’은 해당 응답에서 찾지 못했다는 뜻이며 실제 센서의 추가·삭제·누락을 단정하지 않습니다.
      한쪽이 미관측이면 0건으로 채우지 않고 건수·비율 차이를 산정하지 않습니다. 차이는 성능·장애율·개선 효과나 원인을 증명하지 않습니다.</p>
    <div className="scm-controls">
      <div><label htmlFor={`${id}-query`}>비교할 센서 ID 포함 검색</label>
        <input id={`${id}-query`} type="search" value={view.query} disabled={!interactive} placeholder="예: sensor-1"
          aria-describedby={`${id}-help`} onChange={event => update({ query: event.target.value, limit: 20 })} /></div>
      <div><label htmlFor={`${id}-order`}>센서 비교 정렬</label>
        <select id={`${id}-order`} value={view.order} disabled={!interactive} onChange={event => update({ order: event.target.value as SensorComparisonOrder, limit: 20 })}>
          <option value="first">A 첫 등장 후 B에만 관측된 순</option>
          <option value="failure-delta">실패 건수 차이 절댓값 큰순</option>
          <option value="failure-rate-delta">실패 비율 차이 절댓값 큰순</option>
        </select></div>
      <label className="scm-difference-filter" htmlFor={`${id}-differences`}><input id={`${id}-differences`} type="checkbox" checked={view.differencesOnly}
        disabled={!interactive} onChange={event => update({ differencesOnly: event.target.checked, limit: 20 })} />건수·관측 차이 있는 센서만</label>
    </div>
    <p id={`${id}-help`} className="scm-note">검색은 앞뒤 공백을 제외하고 대소문자 구분 없이 센서 ID 안에서 찾습니다. 표시·비교·이벤트 이동에는 ID 원문을 유지합니다.
      차이 필터는 조회·성공·실패·중복·대기 건수 또는 한쪽 미관측만 비교하며 사유·값·시각 변화는 검사하지 않습니다.
      정렬은 반올림 전 차이의 절댓값을 사용하고 산정 불가 행은 뒤에 둡니다. 같은 값은 원래 센서 순서를 유지합니다.</p>
    <p className="scm-status" role="status" aria-live="polite" aria-atomic="true">두 응답의 센서 {count(comparison.rows.length)}개 중 조건 일치 {count(matching.length)}개 · 표시 {count(visible.length)}개</p>
    {matching.length === 0 ? <p className="scm-empty">{comparison.rows.length === 0
      ? '두 응답에 센서별로 비교할 이벤트가 없습니다.' : '현재 검색·차이 조건에 맞는 센서가 없습니다.'}</p> : <>
      <div className="scm-table-scroll" role="region" tabIndex={0} aria-label="센서별 A·B 비교 표 · 가로 스크롤 가능">
        <table className="scm-table"><caption>센서별 관측 건수·실패 비율 · 차이는 B − A</caption>
          <thead><tr><th scope="col">sensorId 원문</th><th scope="col">A · 조회 결과</th><th scope="col">B · 조회 결과</th><th scope="col">차이 · B − A</th></tr></thead>
          <tbody>{visible.map(row => <tr key={row.sensorId}><th scope="row"><code>{rawId(row.sensorId)}</code>
            <p className="scm-row-note">{row.different ? '건수·관측 차이 있음' : '건수 동일'}</p></th>
            <td><SensorSide group={row.left} side="A" runId={left.id} basePath={basePath} interactive={interactive} /></td>
            <td><SensorSide group={row.right} side="B" runId={right.id} basePath={basePath} interactive={interactive} /></td>
            <td><SensorDelta row={row} /></td></tr>)}</tbody>
        </table>
      </div>
      <ul className="scm-mobile" aria-label="센서별 A·B 비교 카드">{visible.map(row => <li key={row.sensorId}>
        <h4><code>{rawId(row.sensorId)}</code></h4><p className="scm-row-note">{row.different ? '건수·관측 차이 있음' : '건수 동일'}</p>
        <div className="scm-mobile-pair"><section aria-label={`A 센서 ${JSON.stringify(row.sensorId)} 조회 결과`}><h5>A · 조회 결과</h5>
          <SensorSide group={row.left} side="A" runId={left.id} basePath={basePath} interactive={interactive} /></section>
          <section aria-label={`B 센서 ${JSON.stringify(row.sensorId)} 조회 결과`}><h5>B · 조회 결과</h5>
            <SensorSide group={row.right} side="B" runId={right.id} basePath={basePath} interactive={interactive} /></section></div>
        <section className="scm-mobile-delta"><h5>차이 · B − A</h5><SensorDelta row={row} /></section>
      </li>)}</ul>
    </>}
    {matching.length > 20 && <div className="scm-more">
      <button type="button" disabled={!interactive || visible.length >= matching.length} onClick={() => update({ limit: view.limit + 20 })}>센서 20개 더 보기</button>
      <button type="button" disabled={!interactive || view.limit <= 20} onClick={() => update({ limit: 20 })}>처음 20개로 접기</button>
    </div>}
    <p className="scm-note">이 화면의 검색·차이 필터·정렬은 이미 읽은 응답만 좁히며 추가 GET을 요청하지 않습니다.
      기존 비교 CSV는 실행 전체 요약이며 이 센서별 표·조건을 담지 않습니다. 기존 A·B ID 공유 링크도 이 센서 검색·차이 필터·정렬을 저장하지 않습니다.</p>
    <p className="scm-note">각 이벤트 링크는 해당 실행의 센서 ID 정확 조건을 전달합니다. 도착 화면에서 조회 버튼을 눌러야 적용되며,
      지금 비교한 응답·관측 시각을 고정하지 않습니다.</p>
  </section>;
}
