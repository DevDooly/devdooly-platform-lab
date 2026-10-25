import { useEffect, useId, useRef, useState } from 'react';
import type { Outcome } from '../lib/api';
import { compareEventOutcomes, selectEventComparisons, type EventComparisonKind } from '../lib/event-comparison';
import { MAX_OFFLINE_FILE_BYTES, MAX_OFFLINE_OUTCOMES, readOfflineEventFile, type OfflineEventFile, type OfflineEventFileError } from '../lib/offline-event-file';
import { OFFLINE_COMPARISON_REPORT_FILENAME, createOfflineComparisonReport, offlineComparisonReportJson } from '../lib/offline-comparison-report';
import '../styles/offline-event-comparison.css';

export interface OfflineComparisonPair { left: OfflineEventFile; right: OfflineEventFile; }
interface OfflineComparisonView {
  pair: OfflineComparisonPair;
  query: string;
  kind: 'all' | EventComparisonKind;
  limit: number;
}

const kinds: readonly [EventComparisonKind, string][] = [
  ['ambiguous', '대응 모호'], ['unobserved', '한쪽 미관측'], ['input-different', '보고된 입력 필드 다름'],
  ['verdict-different', '판정 필드 다름'], ['observed-equal', '비교 필드 같음'],
];
const kindLabels = Object.fromEntries(kinds) as Record<EventComparisonKind, string>;
const count = (value: number) => value.toLocaleString('ko-KR');
const raw = (value: string | number | null) => Object.is(value, -0) ? '-0' : JSON.stringify(value);
const initialView = (pair: OfflineComparisonPair): OfflineComparisonView => ({ pair, query: '', kind: 'all', limit: 20 });
const errorMessages: Record<OfflineEventFileError, string> = {
  FILE_TOO_LARGE: '파일 크기가 1 MiB 한도를 넘습니다.',
  INVALID_UTF8: 'UTF-8 텍스트 파일인지 확인해주세요.',
  INVALID_JSON: 'JSON 문법 또는 중복된 object key를 확인해주세요.',
  INVALID_DOCUMENT: '이벤트 내보내기 JSON의 형식·필드·건수를 확인해주세요.',
  TOO_MANY_OUTCOMES: '이벤트 행이 1,000건 한도를 넘습니다.',
  FILTER_MISMATCH: '파일의 검색 조건과 담긴 이벤트가 일치하지 않습니다.',
  READ_FAILED: '파일을 읽지 못했습니다. 파일 접근 상태를 확인해주세요.',
};

function FileSource({ file, side }: { file: OfflineEventFile; side: 'A' | 'B' }) {
  const { document } = file;
  return <section className="oec-file-source" aria-label={`${side} 비교에 사용한 파일`}>
    <h3>{side} · 비교에 사용한 파일</h3>
    <dl className="oec-metadata">
      <div><dt>파일 이름</dt><dd><code>{raw(file.name)}</code></dd></div>
      <div><dt>읽은 파일 크기</dt><dd>{count(file.byteLength)} bytes</dd></div>
      <div><dt>schemaVersion</dt><dd>{document.schemaVersion}</dd></div>
      <div><dt>파일에 포함된 행</dt><dd>{count(document.outcomes.length)}건</dd></div>
    </dl>
    <details><summary>{side} 파일에 기록된 출처·건수·원래 검색 조건</summary>
      <dl className="oec-metadata">
        <div><dt>runId</dt><dd><code>{raw(document.source.runId)}</code></dd></div>
        <div><dt>mode</dt><dd><code>{raw(document.source.mode)}</code></dd></div>
        <div><dt>observedAt</dt><dd><code>{raw(document.source.observedAt)}</code></dd></div>
        <div><dt>capturedAt</dt><dd><code>{raw(document.source.capturedAt)}</code></dd></div>
        <div><dt>reportedInputCount</dt><dd>{count(document.counts.reportedInputCount)}건</dd></div>
        <div><dt>availableOutcomes</dt><dd>{count(document.counts.availableOutcomes)}건</dd></div>
        <div><dt>matchedOutcomes</dt><dd>{count(document.counts.matchedOutcomes)}건</dd></div>
        <div><dt>status 조건</dt><dd><code>{raw(document.filters.status)}</code></dd></div>
        <div><dt>query 조건</dt><dd><code>{raw(document.filters.query)}</code></dd></div>
        <div><dt>reason 조건</dt><dd><code>{raw(document.filters.reason)}</code>{document.filters.reason === null ? ' · 전체 사유' : ' · 원문 정확 조건'}</dd></div>
        <div><dt>sensorId 조건</dt><dd>{document.schemaVersion === 2
          ? <><code>{raw(document.filters.sensorId)}</code> · 원문 정확 조건</> : '필드 없음 · 전체 센서 (schemaVersion 1)'}</dd></div>
      </dl>
    </details>
  </section>;
}

function OutcomeFields({ outcome }: { outcome: Outcome }) {
  return <>
    <dl className="oec-fields oec-verdict">{(['status', 'reason'] as const).map(field => <div key={field}>
      <dt>{field}</dt><dd><code>{raw(outcome[field])}</code></dd>
    </div>)}</dl>
    <dl className="oec-fields">{(['eventId', 'sensorId', 'eventTime', 'value'] as const).map(field => <div key={field}>
      <dt>{field}</dt><dd><code>{raw(outcome[field])}</code></dd>
    </div>)}</dl>
  </>;
}

function OutcomeSide({ rows, side, sequence }: { rows: Outcome[]; side: 'A' | 'B'; sequence: number }) {
  return <section className="oec-side" aria-label={`${side} 입력 순서 ${sequence} 파일 행`}>
    <h4>{side} · {rows.length === 0 ? '미관측' : `파일에 ${count(rows.length)}건`}</h4>
    {rows.length === 0 ? <p className="oec-note">이 파일에 미관측 · 원래 입력의 누락이나 처리 0건을 뜻하지 않습니다.</p>
      : rows.length === 1 ? <OutcomeFields outcome={rows[0]} /> : <>
        <p className="oec-note">같은 sequence가 여러 번 기록되어 임의로 대응하지 않습니다.</p>
        <details><summary>{side} 후보 {count(rows.length)}건 전체 보기</summary>
          <ol className="oec-candidates">{rows.map((outcome, index) => <li key={index}>
            <h5>{side} 파일 행 {count(index + 1)} · sequence {outcome.sequence}</h5><OutcomeFields outcome={outcome} />
          </li>)}</ol>
        </details>
      </>}
  </section>;
}

export function OfflineComparisonResult({ pair, interactive, canSaveReport }: {
  pair: OfflineComparisonPair; interactive: boolean; canSaveReport: () => boolean;
}) {
  const id = useId();
  const [savedView, setView] = useState(() => initialView(pair));
  const [reportNotice, setReportNotice] = useState<{ view: OfflineComparisonView; text: string; failed: boolean } | null>(null);
  const view = savedView.pair === pair ? savedView : initialView(pair);
  if (view !== savedView) { setView(view); setReportNotice(null); }
  const currentReportNotice = reportNotice?.view === view ? reportNotice : null;
  const comparison = compareEventOutcomes(pair.left.document.outcomes, pair.right.document.outcomes);
  const matching = selectEventComparisons(comparison.rows, view);
  const visible = matching.slice(0, view.limit);
  const update = (change: Partial<Pick<OfflineComparisonView, 'query' | 'kind' | 'limit'>>) => {
    setView({ ...view, ...change });
    setReportNotice(null);
  };

  function saveComparisonReport() {
    if (!interactive || !canSaveReport()) return;
    let objectUrl: string | null = null;
    let anchor: HTMLAnchorElement | null = null;
    try {
      const report = createOfflineComparisonReport(pair, { query: view.query, kind: view.kind, limit: view.limit }, new Date().toISOString());
      const content = offlineComparisonReportJson(report);
      const blob = new Blob([content], { type: 'application/json;charset=utf-8' });
      objectUrl = URL.createObjectURL(blob);
      anchor = document.createElement('a');
      anchor.href = objectUrl;
      anchor.download = OFFLINE_COMPARISON_REPORT_FILENAME;
      anchor.hidden = true;
      document.body.appendChild(anchor);
      anchor.click();
      setReportNotice({ view, text: '비교 보고서 JSON 다운로드를 요청했습니다. 브라우저 다운로드 목록에서 저장 여부를 확인하세요.', failed: false });
    } catch {
      setReportNotice({ view, text: '비교 보고서 다운로드를 요청하지 못했습니다. 같은 비교 조건에서 다시 시도해주세요.', failed: true });
    } finally {
      anchor?.remove();
      if (objectUrl !== null) {
        const urlToRevoke = objectUrl;
        setTimeout(() => URL.revokeObjectURL(urlToRevoke), 1000);
      }
    }
  }

  return <section className="oec-result" aria-labelledby={`${id}-title`}>
    <h2 id={`${id}-title`}>표시 중인 파일 비교</h2>
    <div className="oec-source-pair"><FileSource file={pair.left} side="A" /><FileSource file={pair.right} side="B" /></div>
    <p className="oec-note">출처·mode·시각은 파일에 기록된 값입니다. 파일의 진위·현재 API 상태·원본을 인증하지 않습니다.
      원래 검색 결과 중 일부만 담긴 파일일 수 있습니다. 세 건수가 같아도 원본 전체를 빠짐없이 담았다는 증명은 아닙니다.</p>
    <p className="oec-note">아래 분류는 두 파일에 기록된 sequence 그룹 수입니다. 같은 숫자의 입력 위치를 나란히 볼 뿐 같은 이벤트·원본 입력임을 보장하지 않습니다.
      보고된 입력 4필드(eventId·sensorId·eventTime·value)와 판정 2필드(status·reason)를 별도로 비교합니다.</p>
    <dl className="oec-kinds" aria-label="파일 이벤트 비교 분류 건수">{kinds.map(([kind, label]) => <div key={kind}><dt>{label}</dt><dd>{count(comparison.counts[kind])}개</dd></div>)}</dl>
    <div className="oec-controls">
      <div><label htmlFor={`${id}-query`}>파일 내 eventId·sensorId 포함 검색</label>
        <input id={`${id}-query`} type="search" value={view.query} disabled={!interactive} placeholder="예: event-1 또는 sensor-1"
          aria-describedby={`${id}-help`} onChange={event => update({ query: event.target.value, limit: 20 })} /></div>
      <div><label htmlFor={`${id}-kind`}>파일 이벤트 비교 분류</label>
        <select id={`${id}-kind`} value={view.kind} disabled={!interactive} onChange={event => update({ kind: event.target.value as OfflineComparisonView['kind'], limit: 20 })}>
          <option value="all">전체 분류</option>{kinds.map(([kind, label]) => <option key={kind} value={kind}>{label}</option>)}
        </select></div>
    </div>
    <p id={`${id}-help`} className="oec-note">검색은 앞뒤 공백을 제외하고 대소문자 구분 없이 양쪽의 모든 eventId·sensorId에서 찾습니다.
      원문은 유지하며 sequence 숫자 오름차순으로 표시합니다. 이 검색·분류는 파일에 기록된 원래 검색 조건과 별개입니다.</p>
    <p className="oec-status" role="status" aria-live="polite" aria-atomic="true">파일의 입력 순서 {count(comparison.rows.length)}개 중 조건 일치 {count(matching.length)}개 · 표시 {count(visible.length)}개</p>
    <section className="oec-report" aria-labelledby={`${id}-report-title`}>
      <h3 id={`${id}-report-title`}>현재 조건의 비교 보고서</h3>
      <p id={`${id}-report-scope`}>화면에는 {count(visible.length)}개를 표시하지만 보고서는 현재 조건에 맞는 입력 순서 그룹 전체 {count(matching.length)}개와 양쪽의 모든 모호 후보를 담습니다. 조건 일치가 0개여도 보고서를 만듭니다.</p>
      <button type="button" disabled={!interactive} aria-describedby={`${id}-report-scope`} onClick={saveComparisonReport}>비교 보고서 JSON 저장</button>
      <p className={`oec-report-status${currentReportNotice?.failed ? ' oec-report-error' : ''}`} role="status" aria-live="polite" aria-atomic="true">{currentReportNotice?.text ?? ''}</p>
      <details><summary>보고서에 담는 내용·다시 불러오기 범위</summary>
        <p>원파일의 이름·크기·출처·원래 검색 조건·세 건수와 이 화면의 검색·분류·표시 개수를 나누어 담습니다. 보고서 생성 시각은 파일에 기록된 관측 시각과 별개입니다.</p>
        <p>이 보고서는 기존 이벤트 내보내기 JSON schemaVersion 1·2와 다른 검토용 형식입니다. 이 파일 비교 화면에 다시 불러올 수 없으며 원파일 bytes를 복원하는 자료도 아닙니다.</p>
        <p>파일의 원문 필드가 보고서에 포함됩니다. 공유하기 전에 내용을 확인하세요.</p>
      </details>
    </section>
    {matching.length === 0 ? <p className="oec-empty">{comparison.rows.length === 0
      ? '두 파일에 비교할 이벤트 행이 없습니다.' : '현재 검색·분류 조건에 맞는 입력 순서가 없습니다.'}</p>
      : <ol className="oec-rows" aria-label="파일의 입력 순서별 A·B 비교">{visible.map(row => <li key={row.sequence}>
        <article aria-label={`파일 입력 순서 ${row.sequence} 비교`}>
          <header className="oec-row-header"><h3>입력 순서 · sequence {row.sequence}</h3><p className={`oec-kind oec-kind-${row.kind}`}>{kindLabels[row.kind]}</p></header>
          <dl className="oec-differences">
            <div><dt>입력 필드 차이</dt><dd>{row.inputDifferences === null ? '비교 안 함 · 대응 모호 또는 한쪽 미관측'
              : row.inputDifferences.length === 0 ? '비교한 4개 필드 같음' : <code>{row.inputDifferences.join(' · ')}</code>}</dd></div>
            <div><dt>판정 필드 차이</dt><dd>{row.verdictDifferences === null ? '비교 안 함 · 대응 모호 또는 한쪽 미관측'
              : row.verdictDifferences.length === 0 ? 'status·reason 같음' : <code>{row.verdictDifferences.join(' · ')}</code>}</dd></div>
          </dl>
          <div className="oec-outcome-pair"><OutcomeSide rows={row.left} side="A" sequence={row.sequence} /><OutcomeSide rows={row.right} side="B" sequence={row.sequence} /></div>
        </article>
      </li>)}</ol>}
    {matching.length > 20 && <div className="oec-more">
      <button type="button" disabled={!interactive || visible.length >= matching.length} onClick={() => update({ limit: view.limit + 20 })}>입력 순서 20개 더 보기</button>
      <button type="button" disabled={!interactive || view.limit <= 20} onClick={() => update({ limit: 20 })}>처음 20개로 접기</button>
    </div>}
    <p className="oec-note">입력 필드가 다르면 그 분류를 우선하고 판정 차이도 별도로 표시합니다. 비교 필드의 일치는 원본 입력 전체·앞선 처리 문맥·실행 코드가 같다는 증명이 아닙니다.</p>
    <p className="oec-note">eventTime 원문을 같은 순간으로 정규화하지 않습니다. value가 null이면 원래 null인지 직렬화 전 NaN·Infinity 등이었는지 복원할 수 없습니다.
      판정 차이만으로 회귀·수정 효과·원인을 단정하지 않습니다. 이 파일 비교는 API 상세 이동·CSV·공유 링크를 만들지 않습니다.</p>
  </section>;
}

export default function OfflineEventComparison() {
  const id = useId();
  const [ready, setReady] = useState(false);
  const [draft, setDraft] = useState<{ left: File | null; right: File | null }>({ left: null, right: null });
  const [pair, setPair] = useState<OfflineComparisonPair | null>(null);
  const [busy, setBusy] = useState(false);
  const [phase, setPhase] = useState('');
  const [error, setError] = useState('');
  const [inputKey, setInputKey] = useState(0);
  const inFlight = useRef(false);
  const mounted = useRef(false);

  useEffect(() => {
    mounted.current = true;
    setReady(true);
    return () => { mounted.current = false; };
  }, []);

  const locked = !ready || busy;

  function canSaveReport() {
    return mounted.current && ready && !inFlight.current;
  }

  function selectFile(side: 'left' | 'right', file: File | null) {
    if (locked || inFlight.current) return;
    setDraft(current => ({ ...current, [side]: file }));
    setError('');
  }

  function clearFiles() {
    if (locked || inFlight.current) return;
    setDraft({ left: null, right: null });
    setPair(null);
    setError('');
    setPhase('');
    setInputKey(current => current + 1);
  }

  async function compareFiles() {
    if (locked || inFlight.current || draft.left === null || draft.right === null) return;
    inFlight.current = true;
    setBusy(true); setError(''); setPhase('A 파일을 읽고 검증하고 있습니다.');
    try {
      const left = await readOfflineEventFile(draft.left);
      if (!mounted.current) return;
      if (!left.ok) { setError(`A 파일: ${errorMessages[left.code]}`); return; }
      setPhase('B 파일을 읽고 검증하고 있습니다.');
      const right = await readOfflineEventFile(draft.right);
      if (!mounted.current) return;
      if (!right.ok) { setError(`B 파일: ${errorMessages[right.code]}`); return; }
      setPair({ left: left.file, right: right.file });
    } catch {
      if (mounted.current) setError(errorMessages.READ_FAILED);
    } finally {
      inFlight.current = false;
      if (mounted.current) { setBusy(false); setPhase(''); }
    }
  }

  return <div className="offline-event-comparison">
    <section className="oec-input-section" aria-labelledby={`${id}-title`}>
      <h2 id={`${id}-title`}>비교할 JSON 파일 선택</h2>
      <p>이벤트 상세의 ‘검색 결과 저장’에서 받은 JSON schemaVersion 1·2를 사용하세요. 파일당 최대 {count(MAX_OFFLINE_FILE_BYTES)} bytes(1 MiB), 이벤트 최대 {count(MAX_OFFLINE_OUTCOMES)}건입니다.</p>
      <p className="oec-note">파일 선택만으로 읽지 않습니다. 비교 버튼을 누르면 A·B 순서로 UTF-8·JSON 형식·필드·건수·원래 검색 조건을 검증한 뒤 브라우저 메모리에서 비교합니다.
        같은 파일이나 같은 runId도 비교할 수 있습니다.</p>
      <div className="oec-file-inputs" key={inputKey}>{(['left', 'right'] as const).map((side, index) => <div key={side}>
        <label htmlFor={`${id}-${side}`}>{index === 0 ? 'A' : 'B'} JSON 파일</label>
        <input id={`${id}-${side}`} type="file" accept=".json,application/json" disabled={locked} onChange={event => selectFile(side, event.target.files?.[0] ?? null)} />
        <p className="oec-draft">선택 대기: {draft[side] === null ? '파일 없음' : <><code>{raw(draft[side]!.name)}</code> · {count(draft[side]!.size)} bytes</>}</p>
      </div>)}</div>
      <div className="oec-actions">
        <button type="button" disabled={locked || draft.left === null || draft.right === null} onClick={() => { void compareFiles(); }}>선택한 파일 비교</button>
        <button type="button" disabled={locked || (draft.left === null && draft.right === null && pair === null && error === '')} onClick={clearFiles}>선택·표시 모두 비우기</button>
      </div>
      <p className="oec-ready" role="status" aria-live="polite" aria-atomic="true">{busy ? phase : ready ? '파일 선택과 비교를 준비했습니다. 자동으로 읽지 않습니다.' : '화면 조작 준비 중입니다. 파일을 자동으로 읽지 않습니다.'}</p>
      {error !== '' && <p className="oec-error" role="alert">{error}{pair !== null && ' 표시 중인 비교와 검색 조건은 유지했습니다.'}</p>}
      {pair !== null && <p className="oec-note">아래는 마지막으로 두 파일 검증을 모두 마친 비교입니다. 위 파일 선택만 바꾸거나 새 파일 검증이 실패해도 표시 결과는 바뀌지 않습니다.</p>}
      <p className="oec-note">선택한 파일을 서버에 업로드하거나 브라우저 저장소에 보관하지 않습니다. 비우기는 이 화면의 선택·표시를 메모리에서 해제하며 원래 파일을 지우지 않습니다.
        페이지·정적 자산을 처음 받는 연결은 필요할 수 있으며, 오프라인 설치형 앱(PWA)을 뜻하지 않습니다.</p>
    </section>
    {pair === null ? <p className="oec-empty">아직 비교한 파일이 없습니다. A·B를 선택하고 비교 버튼을 눌러주세요.</p>
      : <OfflineComparisonResult pair={pair} interactive={!locked} canSaveReport={canSaveReport} />}
  </div>;
}
