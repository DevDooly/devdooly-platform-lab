import { useEffect, useRef, useState } from 'react';
import { ApiReadFailure, readPublicApi, type ApiReadResult } from '../data/public-api-reference';
import { isRun, isRunDetail, type Run, type RunDetail } from '../lib/api';
import { publicApiConfiguration } from '../lib/public-api-base';
import { compareRuns, comparisonCsv, comparisonSharePath, isComparisonRunId, parseComparisonSelection, type RunComparison as ComparisonResult } from '../lib/run-comparison';
import '../styles/run-comparison.css';

interface Props { apiBase?: string; basePath?: string; }
interface ReadSource { path: string; receivedAt: string; }
interface DisplayedPair { result: ComparisonResult; sources: { left: ReadSource; right: ReadSource }; }
interface RunList { items: Run[]; observedAt: string; source: ReadSource; }
type Busy = 'list' | 'comparison' | null;

const finiteFailure = (error: unknown): string => {
  if (!(error instanceof ApiReadFailure)) return '응답 형식 또는 실행 ID를 확인하지 못했습니다.';
  switch (error.code) {
    case 'INVALID_TARGET': return '공개 API 주소 또는 실행 ID가 올바르지 않아 요청하지 않았습니다.';
    case 'HTTP_ERROR': return `HTTP ${error.status} 응답을 받았습니다. 404는 실행 ID, 429는 조회 제한을 확인하세요.`;
    case 'INVALID_JSON': return 'JSON 응답 형식을 확인하지 못했습니다.';
    case 'BODY_REJECTED': return '응답이 256 KiB를 넘었거나 본문 읽기를 완료하지 못했습니다.';
    case 'TIMEOUT': return '8초 안에 응답을 완료하지 못해 요청을 중단했습니다.';
    case 'NETWORK_ERROR': return '네트워크·CORS·연결 상태를 확인하지 못했습니다. 정확한 원인은 이 화면에서 판별할 수 없습니다.';
  }
};

const count = (value: number): string => value.toLocaleString('ko-KR');
const delta = (value: number): string => `${value > 0 ? '+' : value < 0 ? '−' : ''}${count(Math.abs(value))}`;
const percent = (value: number | null): string => value === null ? '산정 불가 · 입력 0건' : `${value.toFixed(1)}%`;
const percentagePoints = (value: number | null): string => value === null ? '산정 불가' : `${value > 0 ? '+' : value < 0 ? '−' : ''}${Math.abs(value).toFixed(1)}%p`;

function Timestamp({ value }: { value: string | null }) {
  return value ? <time dateTime={value}>{value}</time> : <span>기록 없음</span>;
}

function RunRecord({ side, run, source }: { side: 'A' | 'B'; run: RunDetail; source: ReadSource }) {
  return <article className="rc-record" aria-labelledby={`rc-record-${side}`}>
    <div className="rc-record-heading"><span className="rc-side">{side}</span><h3 id={`rc-record-${side}`}>{run.name || '이름 없는 실행'}</h3></div>
    <code className="rc-record-id">{run.id}</code>
    <dl>
      <div><dt>저장된 상태</dt><dd>{run.status}</dd></div>
      <div><dt>시나리오</dt><dd>{run.scenario || '기록 없음'}</dd></div>
      <div><dt>seed · 데이터</dt><dd>{count(run.seed)} · {run.synthetic ? '합성 데이터' : '합성 표시 없음'}</dd></div>
    </dl>
    <details className="rc-record-details"><summary>기록 시각·조회 출처</summary><dl>
      <div><dt>원기록 시작 시각</dt><dd><Timestamp value={run.startedAt} /></dd></div>
      <div><dt>원기록 완료 시각</dt><dd><Timestamp value={run.completedAt} /></dd></div>
      <div><dt>API 조회 시각</dt><dd><Timestamp value={run.observedAt} /></dd></div>
      <div><dt>브라우저 수신 시각</dt><dd><Timestamp value={source.receivedAt} /></dd></div>
      <div><dt>조회 경로</dt><dd><code>GET {source.path}</code></dd></div>
    </dl></details>
  </article>;
}

function CountComparison({ result }: { result: ComparisonResult }) {
  return <>
    <div className="rc-table-scroll rc-wide" role="region" aria-label="실행 건수 비교 표, 가로로 스크롤할 수 있습니다" tabIndex={0}>
      <table className="rc-table"><caption>저장된 실행 건수 · 차이는 B − A</caption>
        <thead><tr><th scope="col">항목</th><th scope="col">A 건수</th><th scope="col">B 건수</th><th scope="col">차이 · B − A</th></tr></thead>
        <tbody>{result.metrics.map(metric => <tr key={metric.key}><th scope="row">{metric.label}</th><td>{count(metric.left)}</td><td>{count(metric.right)}</td><td>{delta(metric.delta)}</td></tr>)}</tbody>
      </table>
    </div>
    <div className="rc-mobile rc-mobile-metrics">{result.metrics.map(metric => <article className="rc-mobile-row" key={metric.key}>
      <h4>{metric.label}</h4><dl><div><dt>A</dt><dd>{count(metric.left)}건</dd></div><div><dt>B</dt><dd>{count(metric.right)}건</dd></div><div><dt>차이 · B − A</dt><dd>{delta(metric.delta)}건</dd></div></dl>
    </article>)}</div>
    <div className="rc-table-scroll rc-wide" role="region" aria-label="입력 대비 비율 비교 표, 가로로 스크롤할 수 있습니다" tabIndex={0}>
      <table className="rc-table"><caption>각 실행의 입력 건수 대비 비율 · 차이는 퍼센트포인트(%p)</caption>
        <thead><tr><th scope="col">항목</th><th scope="col">A 비율</th><th scope="col">B 비율</th><th scope="col">차이 · B − A</th></tr></thead>
        <tbody>{result.rates.map(rate => <tr key={rate.key}><th scope="row">{rate.label}</th><td>{percent(rate.left)}</td><td>{percent(rate.right)}</td><td>{percentagePoints(rate.deltaPercentagePoints)}</td></tr>)}</tbody>
      </table>
    </div>
    <div className="rc-mobile rc-mobile-metrics">{result.rates.map(rate => <article className="rc-mobile-row" key={rate.key}>
      <h4>{rate.label}</h4><dl><div><dt>A</dt><dd>{percent(rate.left)}</dd></div><div><dt>B</dt><dd>{percent(rate.right)}</dd></div><div><dt>차이 · B − A</dt><dd>{percentagePoints(rate.deltaPercentagePoints)}</dd></div></dl>
    </article>)}</div>
    <p className="rc-note">비율의 분모는 각 실행의 입력 건수입니다. 입력이 0건이면 해당 비율과 비율 차이를 산정하지 않습니다.</p>
  </>;
}

export default function RunComparison({ apiBase = '/api', basePath = '/' }: Props) {
  const configuration = publicApiConfiguration(apiBase);
  const [ready, setReady] = useState(false);
  const [leftId, setLeftId] = useState('');
  const [rightId, setRightId] = useState('');
  const [list, setList] = useState<RunList | null>(null);
  const [listError, setListError] = useState('');
  const [selectionNotice, setSelectionNotice] = useState('');
  const [displayed, setDisplayed] = useState<DisplayedPair | null>(null);
  const [requestError, setRequestError] = useState('');
  const [busy, setBusy] = useState<Busy>(null);
  const [phase, setPhase] = useState('');
  const [exportStatus, setExportStatus] = useState('');
  const inFlight = useRef(false);
  const mounted = useRef(false);
  const origin = useRef('');
  const exportVersion = useRef(0);
  const resultHeading = useRef<HTMLHeadingElement | null>(null);

  useEffect(() => {
    mounted.current = true;
    origin.current = window.location.origin;
    const selection = parseComparisonSelection(window.location.search);
    if (selection) {
      setLeftId(selection.left); setRightId(selection.right);
      setSelectionNotice('공유 URL에서 A·B 실행 ID를 복원했습니다. 두 실행 비교 버튼을 눌러야 조회합니다.');
    } else {
      const query = new URLSearchParams(window.location.search);
      if (query.has('left') || query.has('right')) setSelectionNotice('공유 URL의 두 실행 ID를 확인하지 못했습니다. 유효한 서로 다른 ID를 선택하거나 입력하세요.');
    }
    setReady(true);
    return () => { mounted.current = false; };
  }, []);

  useEffect(() => {
    if (!displayed) return;
    resultHeading.current?.focus({ preventScroll: true });
    resultHeading.current?.scrollIntoView({ behavior: 'auto', block: 'start' });
  }, [displayed]);

  const locked = !ready || configuration.invalid || busy !== null;
  const leftValid = isComparisonRunId(leftId);
  const rightValid = isComparisonRunId(rightId);
  const sameId = leftId !== '' && leftId === rightId;
  const dirty = displayed !== null && (leftId !== displayed.result.left.id || rightId !== displayed.result.right.id);
  const sharePath = displayed ? comparisonSharePath(displayed.result.left.id, displayed.result.right.id, basePath) : null;
  const shareUrl = sharePath && origin.current ? `${origin.current}${sharePath}` : '';

  function select(side: 'left' | 'right', value: string) {
    if (locked || inFlight.current) return;
    if (side === 'left') setLeftId(value); else setRightId(value);
    setRequestError(''); setSelectionNotice(''); setExportStatus(''); exportVersion.current += 1;
  }

  async function readList() {
    if (locked || inFlight.current) return;
    inFlight.current = true; setBusy('list'); setListError('');
    try {
      const response = await readPublicApi(configuration.apiBase, 'runs');
      const payload: unknown = JSON.parse(response.json);
      if (!payload || typeof payload !== 'object' || !('items' in payload) || !Array.isArray(payload.items)
        || !payload.items.every(isRun) || !payload.items.every(run => isComparisonRunId(run.id))
        || new Set(payload.items.map(run => run.id)).size !== payload.items.length
        || !('observedAt' in payload) || typeof payload.observedAt !== 'string' || Number.isNaN(Date.parse(payload.observedAt))) throw new Error('INVALID_LIST');
      if (!mounted.current) return;
      const items: Run[] = payload.items;
      setList({ items, observedAt: payload.observedAt, source: { path: `${configuration.apiBase}${response.path}`, receivedAt: response.receivedAt } });
      const nextLeft = leftId || items[0]?.id || '';
      const nextRight = rightId || items.find(run => run.id !== nextLeft)?.id || '';
      setLeftId(nextLeft); setRightId(nextRight);
    } catch (error) {
      if (mounted.current) setListError(`${finiteFailure(error)}${list ? ' 이전에 조회한 목록은 아래에 유지합니다.' : ''}`);
    } finally { inFlight.current = false; if (mounted.current) setBusy(null); }
  }

  async function readDetail(id: string): Promise<{ detail: RunDetail; response: ApiReadResult }> {
    const response = await readPublicApi(configuration.apiBase, 'detail', id);
    const detail: unknown = JSON.parse(response.json);
    if (!isRunDetail(detail) || detail.id !== id) throw new Error('INVALID_DETAIL');
    return { detail, response };
  }

  async function compare() {
    if (locked || inFlight.current || !leftValid || !rightValid || sameId) return;
    inFlight.current = true; exportVersion.current += 1;
    setBusy('comparison'); setRequestError(''); setExportStatus(''); setPhase('A 실행 결과를 조회하고 있습니다.');
    let side: 'A' | 'B' = 'A';
    try {
      const left = await readDetail(leftId);
      if (!mounted.current) return;
      side = 'B'; setPhase('A 수신 완료. B 실행 결과를 조회하고 있습니다.');
      const right = await readDetail(rightId);
      const result = compareRuns(left.detail, right.detail);
      if (mounted.current) setDisplayed({ result, sources: {
        left: { path: `${configuration.apiBase}${left.response.path}`, receivedAt: left.response.receivedAt },
        right: { path: `${configuration.apiBase}${right.response.path}`, receivedAt: right.response.receivedAt },
      } });
    } catch (error) {
      if (mounted.current) setRequestError(`${side} 실행: ${finiteFailure(error)} 두 응답을 모두 확인하지 못해 이번 비교를 표시하지 않습니다.`);
    } finally { inFlight.current = false; if (mounted.current) { setBusy(null); setPhase(''); } }
  }

  async function copyShare() {
    if (locked || !displayed || !shareUrl) return;
    const version = exportVersion.current;
    try {
      await navigator.clipboard.writeText(shareUrl);
      if (mounted.current && exportVersion.current === version) setExportStatus('표시 중인 A·B 실행 ID의 공유 링크를 복사했습니다. 링크를 열어도 자동 조회하지 않습니다.');
    } catch {
      if (mounted.current && exportVersion.current === version) setExportStatus('링크를 복사하지 못했습니다. 아래 공유 URL을 직접 선택해 복사하세요.');
    }
  }

  function downloadCsv() {
    if (locked || !displayed) return;
    try {
      const blob = new Blob([comparisonCsv(displayed.result, displayed.sources)], { type: 'text/csv;charset=utf-8' });
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement('a');
      anchor.href = url; anchor.download = `run-comparison-${displayed.result.left.id}-${displayed.result.right.id}.csv`;
      document.body.appendChild(anchor); anchor.click(); anchor.remove();
      setTimeout(() => URL.revokeObjectURL(url), 0);
      setExportStatus('표시 중인 A·B의 비교 요약 CSV를 준비했습니다. 원기록·조회 시각을 함께 담습니다.');
    } catch { setExportStatus('CSV 파일을 준비하지 못했습니다. 표시 중인 비교 결과를 확인하세요.'); }
  }

  return <div className="run-comparison">
    <aside className="rc-scope" aria-label="비교 범위">
      <strong>{configuration.invalid ? 'API 연결 설정 확인 필요' : '기존 공개 GET으로 저장된 두 실행을 조회합니다'}</strong>
      <p>{configuration.invalid ? '설정된 API 주소를 확인하지 못해 요청을 차단했습니다.' : ready ? '화면 준비 완료. 목록과 비교는 각각 버튼을 눌러야 조회합니다.' : '화면 조작 준비 중입니다. 자동 조회하지 않습니다.'}</p>
      <p>차이는 B − A입니다. A·B의 시간 순서나 성과·원인을 뜻하지 않습니다. 실행 생성과 서버 작업을 시작하지 않으며, 실패한 요청을 스냅샷으로 대체하지 않습니다.</p>
    </aside>

    <section className="rc-picker" aria-labelledby="rc-picker-title" aria-busy={busy !== null}>
      <div className="rc-section-heading"><span className="rc-step">01</span><h2 id="rc-picker-title">비교할 실행 선택</h2></div>
      <div className="rc-list-action"><p>최근 저장된 목록에서 고르거나, 알고 있는 실행 ID를 직접 입력하세요.</p><button className="button" type="button" disabled={locked} onClick={() => { void readList(); }}>{busy === 'list' ? '목록 조회 중…' : list ? '실행 목록 다시 조회' : '실행 목록 조회'}</button></div>
      <div className="rc-list-status" aria-live="polite">
        {!list && !listError && <p>목록을 아직 조회하지 않았습니다. <code>GET /demo/runs</code></p>}
        {list && <><p>조회한 목록 {count(list.items.length)}개 · 최근 최대 20개 범위입니다. 목록에 없는 ID도 직접 조회할 수 있습니다.</p><p>목록 API 조회 <Timestamp value={list.observedAt} /> · 브라우저 수신 <Timestamp value={list.source.receivedAt} /></p>{list.items.length < 2 && <p>목록에서 서로 다른 두 실행을 고르기에 충분하지 않습니다. 다른 유효한 실행 ID를 알고 있다면 직접 입력하세요.</p>}</>}
        {listError && <p className="rc-error" role="alert">{listError}</p>}
      </div>
      <div className="rc-selectors">{(['left', 'right'] as const).map((side, index) => {
        const value = side === 'left' ? leftId : rightId;
        const valid = side === 'left' ? leftValid : rightValid;
        const marker = index === 0 ? 'A' : 'B';
        const listed = list?.items.some(run => run.id === value) ?? false;
        return <fieldset className="rc-selection" key={side} disabled={locked}>
          <legend><span className="rc-side">{marker}</span>{marker === 'A' ? '기준 실행' : '비교 실행'}</legend>
          <label htmlFor={`rc-${side}-select`}>조회한 목록에서 선택</label>
          <select id={`rc-${side}-select`} value={value} disabled={locked || !list?.items.length} onChange={event => select(side, event.target.value)} aria-describedby={`rc-${side}-list-hint`}>
            <option value="">실행 선택</option>
            {value && !listed && <option value={value}>{value} · 직접 입력·공유 ID</option>}
            {list?.items.map(run => <option key={run.id} value={run.id}>{run.id} · 입력 {count(run.inputCount)}건</option>)}
          </select>
          <p className="rc-field-hint" id={`rc-${side}-list-hint`}>{value && !listed ? '현재 ID는 조회한 목록에 없습니다. 존재 여부는 비교 요청에서 확인합니다.' : '목록 선택은 실행 ID만 바꾸며 상세 조회를 시작하지 않습니다.'}</p>
          <label htmlFor={`rc-${side}-id`}>실행 ID 직접 입력</label>
          <input id={`rc-${side}-id`} value={value} disabled={locked} maxLength={80} autoComplete="off" spellCheck={false} aria-invalid={(value !== '' && !valid) || sameId || undefined} aria-describedby={`rc-id-hint rc-${side}-validation`} onChange={event => select(side, event.target.value)} />
          <p className="rc-field-hint rc-error" id={`rc-${side}-validation`}>{value !== '' && !valid ? '실행 ID 형식을 확인하세요.' : sameId ? 'A와 B에 서로 다른 실행 ID를 선택하세요.' : '\u00A0'}</p>
        </fieldset>;
      })}</div>
      <p className="rc-note" id="rc-id-hint">ID는 소문자·숫자로 시작하고 소문자·숫자·점·밑줄·하이픈으로 최대 80자입니다.</p>
      {selectionNotice && <p className="rc-selection-notice" role="status">{selectionNotice}</p>}
      <div className="rc-compare-action"><button className="button button-primary" type="button" disabled={locked || !leftValid || !rightValid || sameId} onClick={() => { void compare(); }}>{busy === 'comparison' ? '두 실행 조회 중…' : '두 실행 비교'}<span aria-hidden="true">↗</span></button><p>A 다음 B를 순서대로 조회합니다. 각 요청은 최대 8초이며 자동 재시도하지 않습니다.</p></div>
      <div className="rc-request-status" aria-live="polite" aria-atomic="true">{phase && <p>{phase}{displayed && ' 아래에는 이전에 완료한 비교가 표시됩니다.'}</p>}{requestError && <p className="rc-error" role="alert">{requestError}{displayed && ' 아래의 마지막 정상 비교와 해당 ID·시각은 유지합니다.'}</p>}</div>
    </section>

    {!displayed && <section className="rc-empty" aria-label="비교 결과 대기"><span className="rc-step">02</span><h2>두 실행을 조회하면 비교가 표시됩니다</h2><p>입력·성공·실패·중복·대기 건수와 실패 사유를 나란히 확인합니다. 이 화면에 저장된 비교 전적은 없습니다.</p></section>}
    {displayed && <section className="rc-results" aria-labelledby="rc-results-title" data-comparison-state={dirty ? 'previous-selection' : 'current-selection'}>
      <div className="rc-section-heading"><span className="rc-step">02</span><h2 id="rc-results-title" ref={resultHeading} tabIndex={-1}>표시 중인 비교</h2><span className="rc-result-label">두 응답 조회 완료</span></div>
      {dirty && <div className="rc-dirty" role="status"><strong>선택이 바뀌었습니다. 아래 표는 이전 비교입니다.</strong><p>표시 중인 A: <code>{displayed.result.left.id}</code> · B: <code>{displayed.result.right.id}</code>. 새 선택은 두 실행 비교 버튼을 눌러 조회하세요.</p><p>공유 링크와 CSV도 아래에 표시된 실행을 기준으로 만듭니다.</p></div>}
      <p className="rc-note">아래 A·B는 각각 직접 수신한 응답입니다. 두 조회는 같은 순간의 관측이 아니며, 최신 상태가 계속 유지됨을 보장하지 않습니다.</p>
      <div className="rc-records"><RunRecord side="A" run={displayed.result.left} source={displayed.sources.left} /><RunRecord side="B" run={displayed.result.right} source={displayed.sources.right} /></div>
      <div className="rc-interpretation"><h3>차이를 읽을 때</h3><ul><li>입력 건수: {displayed.result.differences.inputCount ? '서로 다릅니다. 건수 차이와 입력 대비 비율을 함께 확인하세요.' : '두 실행이 같습니다.'}</li><li>시나리오: {displayed.result.differences.scenario ? '서로 다릅니다. 같은 조건의 반복 실행으로 해석할 수 없습니다.' : '표시된 시나리오가 같습니다.'} seed: {displayed.result.differences.seed ? '서로 다릅니다.' : '같습니다.'}</li><li>숫자의 증감은 성능 향상·회귀나 설정 변경의 효과를 증명하지 않습니다.</li></ul>{displayed.result.warnings.length > 0 && <div className="rc-data-warning"><strong>응답 정합성 참고</strong><ul>{displayed.result.warnings.map((warning, index) => <li key={index}>{warning}</li>)}</ul></div>}</div>
      <CountComparison result={displayed.result} />

      <section className="rc-reasons" aria-labelledby="rc-reasons-title"><h3 id="rc-reasons-title">조회된 실패 이벤트 기준 사유 비교</h3><p>각 응답의 <code>outcomes</code> 중 FAILED인 이벤트를 사유별로 집계합니다. 보고된 요약과 일치하지 않으면 전체 실패 사유 분포로 단정할 수 없습니다.</p>
        <div className="rc-coverage">{(['left', 'right'] as const).map((side, index) => { const coverage = displayed.result.failureReasonCoverage[side]; return <p key={side}><strong>{index === 0 ? 'A' : 'B'}</strong> 조회된 실패 이벤트 {count(coverage.failedOutcomeCount)}건 / 보고된 실패 {count(coverage.reportedFailureCount)}건 · {coverage.complete ? '건수 일치' : '건수 불일치'}</p>; })}</div>
        {displayed.result.failureReasons.length === 0 ? <p className="rc-no-reasons">두 응답에서 조회된 실패 이벤트가 없습니다.</p> : <>
          <div className="rc-table-scroll rc-wide" role="region" aria-label="실패 사유 비교 표, 가로로 스크롤할 수 있습니다" tabIndex={0}><table className="rc-table"><caption>실패 이벤트 사유별 건수 · 차이는 B − A</caption><thead><tr><th scope="col">조회된 실패 사유</th><th scope="col">A 건수</th><th scope="col">B 건수</th><th scope="col">차이 · B − A</th></tr></thead><tbody>{displayed.result.failureReasons.map(reason => <tr key={reason.reason}><th scope="row">{reason.reason || '사유 없음'}</th><td>{count(reason.left)}</td><td>{count(reason.right)}</td><td>{delta(reason.delta)}</td></tr>)}</tbody></table></div>
          <div className="rc-mobile rc-mobile-metrics">{displayed.result.failureReasons.map(reason => <article className="rc-mobile-row" key={reason.reason}><h4>{reason.reason || '사유 없음'}</h4><dl><div><dt>A</dt><dd>{count(reason.left)}건</dd></div><div><dt>B</dt><dd>{count(reason.right)}건</dd></div><div><dt>차이 · B − A</dt><dd>{delta(reason.delta)}건</dd></div></dl></article>)}</div>
        </>}
      </section>

      <section className="rc-export" aria-labelledby="rc-export-title"><h3 id="rc-export-title">표시된 비교 공유</h3><p>링크에는 A·B 실행 ID만 담습니다. 링크를 연 화면에서도 비교 버튼을 눌러 다시 조회해야 하며, 같은 시점의 응답을 고정하지 않습니다. CSV에는 현재 표시된 비교 요약과 조회 출처·시각을 담습니다.</p><div className="rc-export-actions"><button className="button" type="button" disabled={locked || !shareUrl} onClick={() => { void copyShare(); }}>비교 링크 복사</button><button className="button" type="button" disabled={locked} onClick={downloadCsv}>비교 요약 CSV 다운로드</button></div>{shareUrl && <div className="rc-share-url"><label htmlFor="rc-share-url">표시된 A·B의 공유 URL</label><input id="rc-share-url" readOnly disabled={locked} value={shareUrl} onFocus={event => event.currentTarget.select()} /></div>}<p className="rc-export-status" role="status">{exportStatus}</p></section>
    </section>}
  </div>;
}
