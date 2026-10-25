import { useId, useState } from 'react';
import type { Outcome, RunDetail } from '../lib/api';
import type { ComparisonSources } from '../lib/run-comparison';
import { compareEventOutcomes, selectEventComparisons, type EventComparisonKind } from '../lib/event-comparison';
import { eventSharePath } from '../lib/event-share';
import '../styles/event-comparison.css';

export interface EventRunComparisonProps {
  left: RunDetail;
  right: RunDetail;
  sources: ComparisonSources;
  basePath: string;
  interactive: boolean;
}

interface EventComparisonView {
  left: RunDetail;
  right: RunDetail;
  query: string;
  kind: 'all' | EventComparisonKind;
  limit: number;
}

const kinds: readonly [EventComparisonKind, string][] = [
  ['ambiguous', '대응 모호'],
  ['unobserved', '한쪽 미관측'],
  ['input-different', '보고된 입력 필드 다름'],
  ['verdict-different', '판정 필드 다름'],
  ['observed-equal', '비교 필드 같음'],
];
const kindLabels = Object.fromEntries(kinds) as Record<EventComparisonKind, string>;
const count = (value: number) => value.toLocaleString('ko-KR');
const raw = (value: string | number | null) => Object.is(value, -0) ? '-0' : JSON.stringify(value);
const initialView = (left: RunDetail, right: RunDetail): EventComparisonView => ({ left, right, query: '', kind: 'all', limit: 20 });

function RawTimestamp({ value }: { value: string | null }) {
  return value === null ? <span>기록 없음 · null</span> : <time dateTime={value}>{value}</time>;
}

function InputFields({ outcome }: { outcome: Outcome }) {
  return <dl className="ecm-fields">{(['eventId', 'sensorId', 'eventTime', 'value'] as const).map(field =>
    <div key={field}><dt>{field}</dt><dd><code>{raw(outcome[field])}</code></dd></div>)}</dl>;
}

function VerdictFields({ outcome }: { outcome: Outcome }) {
  return <dl className="ecm-fields ecm-verdict">{(['status', 'reason'] as const).map(field =>
    <div key={field}><dt>{field}</dt><dd><code>{raw(outcome[field])}</code></dd></div>)}</dl>;
}

function EventSide({ outcomes, side, runId, sequence, basePath, interactive }: {
  outcomes: Outcome[];
  side: 'A' | 'B';
  runId: string;
  sequence: number;
  basePath: string;
  interactive: boolean;
}) {
  const single = outcomes.length === 1 ? outcomes[0] : null;
  const path = single === null ? null : eventSharePath({ runId,
    filters: { status: 'ALL', query: '', reason: null }, sequence }, basePath);
  return <section className="ecm-side" aria-label={`${side} 입력 순서 ${sequence} 응답`}>
    <h5>{side} · {outcomes.length === 0 ? '미관측' : `관측 ${count(outcomes.length)}건`}</h5>
    {outcomes.length === 0 ? <p className="ecm-unobserved">이 응답에 미관측 · 0건의 처리 결과로 채우지 않습니다.</p>
      : single !== null ? <>
        <VerdictFields outcome={single} />
        <details className="ecm-input-details"><summary>{side} 보고된 입력 필드 4개 보기</summary><InputFields outcome={single} /></details>
      </> : <>
        <p className="ecm-note">같은 sequence의 행이 여러 개입니다. 임의로 한 행을 고르거나 서로 짝짓지 않습니다.</p>
        <details className="ecm-group-details"><summary>{side} 관측 행 {count(outcomes.length)}건 전체 보기</summary>
          <ol className="ecm-group-rows">{outcomes.map((outcome, index) => <li key={index}>
            <h6>{side} 관측 행 {count(index + 1)} · sequence {outcome.sequence}</h6>
            <VerdictFields outcome={outcome} /><InputFields outcome={outcome} />
          </li>)}</ol>
        </details>
      </>}
    {path !== null && <div className="ecm-event-action">{interactive
      ? <a href={path} aria-label={`${side} 입력 순서 ${sequence} 이벤트 상세 보기`}>{side} 이벤트 상세 보기</a>
      : <span className="ecm-event-disabled" aria-disabled="true">{side} 이벤트 상세 보기 · 조회 중 사용 불가</span>}</div>}
  </section>;
}

export default function EventRunComparison({ left, right, sources, basePath, interactive }: EventRunComparisonProps) {
  const id = useId();
  const [savedView, setView] = useState(() => initialView(left, right));
  // Only a new displayed response pair resets local controls, not draft IDs or failed requests.
  const view = savedView.left === left && savedView.right === right ? savedView : initialView(left, right);
  if (view !== savedView) setView(view);
  const comparison = compareEventOutcomes(left.outcomes, right.outcomes);
  const matching = selectEventComparisons(comparison.rows, view);
  const visible = matching.slice(0, view.limit);
  const update = (change: Partial<Pick<EventComparisonView, 'query' | 'kind' | 'limit'>>) => setView({ ...view, ...change });

  return <section className="event-run-comparison" aria-labelledby={`${id}-title`}>
    <header><h3 id={`${id}-title`}>입력 순서별 이벤트 응답 비교</h3>
      <p>두 응답에서 같은 sequence가 보고된 위치를 나란히 봅니다. sequence는 입력 위치를 맞추는 기준이며, 같은 이벤트나 같은 원본 입력임을 증명하지 않습니다.</p></header>
    <details className="ecm-source-details"><summary>비교 출처·조회 시각 A·B 보기</summary>
      <div className="ecm-sources">{(['left', 'right'] as const).map((key, index) => {
        const run = key === 'left' ? left : right;
        const side = index === 0 ? 'A' : 'B';
        return <section key={key} aria-label={`${side} 이벤트 비교 출처`}><h4>{side} · 비교 출처</h4><dl>
          <div><dt>실행 · runId</dt><dd><code>{run.id}</code></dd></div>
          <div><dt>조회된 outcomes</dt><dd>{count(key === 'left' ? comparison.leftCount : comparison.rightCount)}건</dd></div>
          <div><dt>보고된 입력 · inputCount</dt><dd>{count(run.inputCount)}건</dd></div>
          <div><dt>API 관측 · observedAt</dt><dd><RawTimestamp value={run.observedAt} /></dd></div>
          <div><dt>브라우저 수신 시각</dt><dd><RawTimestamp value={sources[key].receivedAt} /></dd></div>
          <div><dt>조회 경로</dt><dd><code>GET {sources[key].path}</code></dd></div>
        </dl></section>;
      })}</div>
      <p className="ecm-note">A·B는 별도 GET 응답이며 같은 순간의 원자적 관측이 아닙니다. 조회 행 수와 inputCount가 같아도 전체 원본 입력이 빠짐없이 같다는 검증은 아닙니다.</p>
    </details>
    <dl className="ecm-kinds" aria-label="입력 순서별 비교 분류 건수">{kinds.map(([kind, label]) => <div key={kind}><dt>{label}</dt><dd>{count(comparison.counts[kind])}개</dd></div>)}</dl>
    <p className="ecm-note">분류 건수는 sequence 그룹 수이며 각 응답의 이벤트 행 수와 다릅니다.</p>
    <p className="ecm-note">양쪽에 한 행씩 있을 때 eventId·sensorId·eventTime·value를 응답의 문자열·숫자·null 그대로 비교하고, status·reason은 별도로 비교합니다.
      입력 필드가 다르면 ‘보고된 입력 필드 다름’으로 분류하면서 판정 차이도 표시합니다. 같은 sequence에 어느 한쪽이라도 여러 행이 있으면 ‘대응 모호’로 구분합니다.</p>
    <div className="ecm-controls">
      <div><label htmlFor={`${id}-query`}>eventId·sensorId 포함 검색</label>
        <input id={`${id}-query`} type="search" value={view.query} disabled={!interactive} placeholder="예: event-1 또는 sensor-1"
          aria-describedby={`${id}-help`} onChange={event => update({ query: event.target.value, limit: 20 })} /></div>
      <div><label htmlFor={`${id}-kind`}>이벤트 비교 분류</label>
        <select id={`${id}-kind`} value={view.kind} disabled={!interactive} onChange={event => update({ kind: event.target.value as EventComparisonView['kind'], limit: 20 })}>
          <option value="all">전체 분류</option>{kinds.map(([kind, label]) => <option key={kind} value={kind}>{label}</option>)}
        </select></div>
    </div>
    <p id={`${id}-help`} className="ecm-note">검색은 앞뒤 공백을 제외하고 대소문자 구분 없이 양쪽의 모든 eventId·sensorId에서 찾습니다.
      원문은 바꾸지 않으며, 입력 순서의 숫자 오름차순으로 표시합니다. 검색·분류·더 보기는 이미 읽은 응답만 좁히고 추가 GET을 요청하지 않습니다.</p>
    <p className="ecm-status" role="status" aria-live="polite" aria-atomic="true">두 응답의 입력 순서 {count(comparison.rows.length)}개 중 조건 일치 {count(matching.length)}개 · 표시 {count(visible.length)}개</p>
    {matching.length === 0 ? <p className="ecm-empty">{comparison.rows.length === 0
      ? '두 응답에 비교할 이벤트 행이 없습니다.' : '현재 검색·분류 조건에 맞는 입력 순서가 없습니다.'}</p>
      : <ol className="ecm-rows" aria-label="입력 순서별 A·B 이벤트 응답">{visible.map(row => <li key={row.sequence}>
        <article aria-label={`입력 순서 ${row.sequence} 비교`}>
          <header className="ecm-row-header"><h4>입력 순서 · sequence {row.sequence}</h4><p className={`ecm-kind ecm-kind-${row.kind}`}>{kindLabels[row.kind]}</p></header>
          <dl className="ecm-differences">
            <div><dt>입력 필드 차이</dt><dd>{row.inputDifferences === null ? '비교 안 함 · 대응 모호 또는 한쪽 미관측'
              : row.inputDifferences.length === 0 ? '비교한 4개 필드 같음' : <code>{row.inputDifferences.join(' · ')}</code>}</dd></div>
            <div><dt>판정 필드 차이</dt><dd>{row.verdictDifferences === null ? '비교 안 함 · 대응 모호 또는 한쪽 미관측'
              : row.verdictDifferences.length === 0 ? 'status·reason 같음' : <code>{row.verdictDifferences.join(' · ')}</code>}</dd></div>
          </dl>
          <div className="ecm-pair"><EventSide outcomes={row.left} side="A" runId={left.id} sequence={row.sequence} basePath={basePath} interactive={interactive} />
            <EventSide outcomes={row.right} side="B" runId={right.id} sequence={row.sequence} basePath={basePath} interactive={interactive} /></div>
        </article>
      </li>)}</ol>}
    {matching.length > 20 && <div className="ecm-more">
      <button type="button" disabled={!interactive || visible.length >= matching.length} onClick={() => update({ limit: view.limit + 20 })}>입력 순서 20개 더 보기</button>
      <button type="button" disabled={!interactive || view.limit <= 20} onClick={() => update({ limit: 20 })}>처음 20개로 접기</button>
    </div>}
    <p className="ecm-note">비교 필드가 같아도 전체 원본 입력·앞선 처리 문맥·실행 코드가 같다는 뜻은 아닙니다. 판정 차이는 회귀·수정 효과·원인을 증명하지 않습니다.
      응답의 value가 null이면 원래 null인지, 직렬화 전에 NaN·Infinity 등이었는지 이 응답만으로 복원할 수 없습니다. eventTime 문자열을 같은 순간으로 정규화하지 않습니다.</p>
    <p className="ecm-note">이벤트 상세 링크는 한 행만 관측된 쪽에만 제공하며 sequence를 전달합니다. 도착 화면에서 조회 버튼을 눌러 새 GET을 읽으므로 지금 비교한 응답·관측 시각을 고정하지 않습니다.
      기존 비교 CSV는 실행 전체 요약이며 이 이벤트 목록을 담지 않습니다. 기존 A·B ID 공유 링크도 이 목록의 검색·분류·표시 개수를 저장하지 않습니다.</p>
  </section>;
}
