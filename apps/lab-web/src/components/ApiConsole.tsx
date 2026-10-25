import { useEffect, useRef, useState } from 'react';
import { API_ENDPOINTS, ApiReadFailure, DEFAULT_RUN_ID, apiEndpointPath, readPublicApi, type ApiEndpointId, type ApiReadResult } from '../data/public-api-reference';
import { parseApiRunChoices } from '../lib/api-run-choices';
import { parseApiRunResult } from '../lib/api-run-result';
import { comparisonEventPath } from '../lib/comparison-drilldown';
import { publicApiConfiguration } from '../lib/public-api-base';
import '../styles/api-console.css';

interface Props { apiBase?: string; basePath?: string; }
type Entry = { state: 'loading'; requestPath: string } | { state: 'success'; result: ApiReadResult } | { state: 'error'; message: string; requestPath: string };
type RunChoices = NonNullable<ReturnType<typeof parseApiRunChoices>> & { path: string; receivedAt: string };
const failureMessage = (error: unknown): string => {
  if (!(error instanceof ApiReadFailure)) return '응답을 확인하지 못했습니다. 새 요청은 조회 버튼으로 시작할 수 있습니다.';
  switch (error.code) {
    case 'INVALID_TARGET': return '공개 API 주소 또는 실행 ID를 확인할 수 없어 요청하지 않았습니다.';
    case 'HTTP_ERROR': return `HTTP ${error.status} 응답입니다. 오류 본문은 표시하지 않습니다. 404는 실행 ID, 429는 조회 제한을 확인하세요.`;
    case 'INVALID_JSON': return 'JSON 응답 형식을 확인하지 못했습니다. 성공 응답으로 표시하지 않습니다.';
    case 'BODY_REJECTED': return '응답이 256 KiB를 넘었거나 읽기를 완료하지 못했습니다. 본문을 표시하지 않습니다.';
    case 'TIMEOUT': return '8초 안에 응답을 완료하지 못해 요청을 중단했습니다. 자동으로 재시도하지 않습니다.';
    case 'NETWORK_ERROR': return '네트워크·CORS·연결 상태를 확인하지 못했습니다. 정확한 원인은 이 화면에서 판별할 수 없습니다.';
  }
};

export function ApiRunSummary({ result, basePath = '/' }: { result: ApiReadResult; basePath?: string }) {
  const parsed = parseApiRunResult(result);
  if (parsed.kind !== 'valid') return <p className="api-summary-unavailable">
    {parsed.kind === 'id-mismatch'
      ? '요청한 실행과 응답 ID가 달라 요약과 이벤트 링크를 표시하지 않습니다.'
      : '응답의 실행 상세 형식을 확인하지 못해 요약과 이벤트 링크를 표시하지 않습니다.'}
    {' '}수신한 JSON은 아래에서 확인할 수 있습니다.
  </p>;
  const { detail } = parsed;
  const allEvents = comparisonEventPath(detail.id, basePath);
  const failedEvents = comparisonEventPath(detail.id, basePath, { status: 'FAILED' });
  const counts = [
    ['입력', detail.inputCount], ['성공', detail.successCount], ['실패', detail.failureCount],
    ['중복', detail.duplicateCount], ['대기', detail.pendingCount],
  ] as const;
  return <section className="api-run-summary" aria-label="수신한 실행 결과 요약">
    <h3>수신한 실행 결과</h3>
    <p className="api-summary-id">실행 ID <code>{detail.id}</code></p>
    <dl className="api-summary-context">
      <div><dt>이름</dt><dd>{detail.name}</dd></div>
      <div><dt>시나리오</dt><dd><code>{detail.scenario}</code></dd></div>
      <div><dt>보고된 상태</dt><dd><code>{detail.status}</code></dd></div>
    </dl>
    <dl className="api-summary-counts" aria-label="응답에 보고된 처리 건수">
      {counts.map(([label, value]) => <div key={label}><dt>{label}</dt><dd>{value.toLocaleString('ko-KR')}<span>건</span></dd></div>)}
    </dl>
    <p className="api-summary-note">위 수치는 응답의 처리 건수입니다. 이 응답에 포함된 이벤트 행은 {detail.outcomes.length.toLocaleString('ko-KR')}건이며, 입력 건수와 별도로 표시합니다.</p>
    <div className="api-summary-actions">
      {allEvents && <a className="button" href={allEvents}>전체 이벤트 보기 <span aria-hidden="true">↗</span></a>}
      {failedEvents && <a className="button" href={failedEvents}>실패 이벤트 보기 <span aria-hidden="true">↗</span></a>}
    </div>
    <p className="api-summary-note">이벤트 화면에서는 ‘공유한 실행·조건 조회’를 눌러 같은 ID를 새로 읽습니다. 위 응답과 관측 시각이 달라질 수 있습니다.</p>
  </section>;
}

export default function ApiConsole({ apiBase = '/api', basePath = '/' }: Props) {
  const configuration = publicApiConfiguration(apiBase);
  const [ready, setReady] = useState(false);
  const [runId, setRunId] = useState(DEFAULT_RUN_ID);
  const [runChoices, setRunChoices] = useState<RunChoices | null>(null);
  const [runChoicesNotice, setRunChoicesNotice] = useState<'invalid' | 'error' | null>(null);
  const [entries, setEntries] = useState<Partial<Record<ApiEndpointId, Entry>>>({});
  const [busy, setBusy] = useState<ApiEndpointId | null>(null);
  const [copyStatus, setCopyStatus] = useState<Partial<Record<ApiEndpointId, string>>>({});
  const inFlight = useRef(false);
  const mounted = useRef(false);
  const controlsDisabled = !ready || configuration.invalid || busy !== null;
  useEffect(() => { mounted.current = true; setReady(true); return () => { mounted.current = false; }; }, []);
  function changeRunId(value: string) {
    if (controlsDisabled || inFlight.current) return;
    setRunId(value);
  }
  async function query(id: ApiEndpointId) {
    const requestPath = apiEndpointPath(id, runId);
    if (!ready || configuration.invalid || inFlight.current || !requestPath) return;
    inFlight.current = true; setBusy(id); setEntries(previous => ({ ...previous, [id]: { state: 'loading', requestPath } }));
    if (id === 'runs') setRunChoicesNotice(null);
    setCopyStatus(previous => ({ ...previous, [id]: '' }));
    try {
      const result = await readPublicApi(configuration.apiBase, id, runId);
      if (mounted.current) {
        setEntries(previous => ({ ...previous, [id]: { state: 'success', result } }));
        if (id === 'runs') {
          const choices = parseApiRunChoices(result.json);
          if (choices) setRunChoices({ ...choices, path: result.path, receivedAt: result.receivedAt });
          else setRunChoicesNotice('invalid');
        }
      }
    } catch (error) {
      if (mounted.current) {
        setEntries(previous => ({ ...previous, [id]: { state: 'error', message: failureMessage(error), requestPath } }));
        if (id === 'runs') setRunChoicesNotice('error');
      }
    } finally { inFlight.current = false; if (mounted.current) setBusy(null); }
  }
  async function copy(id: ApiEndpointId, json: string) {
    try {
      await navigator.clipboard.writeText(json);
      if (mounted.current) setCopyStatus(previous => ({ ...previous, [id]: 'JSON을 복사했습니다.' }));
    } catch {
      if (mounted.current) setCopyStatus(previous => ({ ...previous, [id]: '복사하지 못했습니다. 펼친 JSON을 직접 선택해 복사할 수 있습니다.' }));
    }
  }
  return <div className="api-console">
    <div className="api-connection" role="status">
      <strong>{configuration.invalid ? 'API 연결 설정 확인 필요' : configuration.externalHttps ? '공개 HTTPS API 직접 조회' : '현재 사이트의 /api 직접 조회'}</strong>
      <p>{configuration.invalid ? '설정된 주소를 검증하지 못했습니다. 요청을 차단한 상태입니다.' : ready ? '화면 준비 완료. 아래 조회 버튼을 눌러야 요청합니다.' : '화면 조작 준비 중입니다. 자동 요청은 하지 않습니다.'}</p>
      <p>예제 응답이나 저장된 스냅샷으로 대체하지 않습니다. HTTP·JSON 조회 성공은 전체 서비스의 정상 동작이나 응답 필드별 검증을 뜻하지 않습니다.</p>
    </div>
    <nav className="api-endpoint-index" aria-label="공개 API 목차">{API_ENDPOINTS.map(endpoint => <a key={endpoint.id} href={`#api-${endpoint.id}`}><span>GET</span>{endpoint.title}</a>)}</nav>
    <div className="api-endpoint-list">{API_ENDPOINTS.map(endpoint => {
      const entry = entries[endpoint.id];
      const invalidId = endpoint.id === 'detail' && apiEndpointPath('detail', runId) === null;
      const displayedPath = entry?.state === 'success' ? entry.result.path : entry?.requestPath;
      const selectionChanged = endpoint.id === 'detail' && displayedPath && displayedPath !== apiEndpointPath('detail', runId);
      return <article className="api-endpoint" id={`api-${endpoint.id}`} key={endpoint.id} aria-labelledby={`api-heading-${endpoint.id}`}>
        <div className="api-endpoint-heading"><span className="api-method">GET</span><h2 id={`api-heading-${endpoint.id}`}>{endpoint.title}</h2></div>
        <code className="api-path">/api{endpoint.path}</code>
        <p>{endpoint.description}</p>
        {endpoint.id === 'detail' ? <>
        <div className="api-run-picker">
          <button className="button api-load-runs" type="button" disabled={controlsDisabled} onClick={() => { void query('runs'); }}>
            {busy === 'runs' ? '실행 목록 불러오는 중…' : '실행 목록 불러오기'}
          </button>
          <label htmlFor="api-run-select">조회한 실행 목록에서 선택</label>
          <select id="api-run-select" value={runId} disabled={controlsDisabled || !runChoices?.items.length}
            aria-describedby="api-run-choice-hint api-run-choice-status" onChange={event => changeRunId(event.target.value)}>
            {!runChoices?.items.some(run => run.id === runId) && <option value={runId}>{runId ? `${runId} · 현재 ID (목록 밖)` : '실행을 선택하거나 아래에서 ID를 입력하세요'}</option>}
            {runChoices?.items.map(run => <option key={run.id} value={run.id}>{run.id} · 입력 {run.inputCount}건</option>)}
          </select>
          <p id="api-run-choice-hint">최근 최대 20개 실행입니다. 선택하면 아래 ID만 바뀌며, 상세 요청은 조회 버튼으로 시작합니다.</p>
          <div className="api-run-choice-status" id="api-run-choice-status" role="status">
            {busy === 'runs' && <p>실행 목록 응답을 기다립니다.{runChoices && ' 아래 선택 목록은 이전에 조회한 결과입니다.'}</p>}
            {runChoicesNotice === 'invalid' && <p>이번 응답에서 선택할 실행 목록을 확인하지 못했습니다.{runChoices ? ' 이전 선택 목록을 유지합니다.' : ' 실행 ID를 직접 입력해 조회할 수 있습니다.'}</p>}
            {runChoicesNotice === 'error' && <p>이번 실행 목록 요청에 실패했습니다.{runChoices ? ' 이전 선택 목록을 유지합니다.' : ' 실행 ID를 직접 입력해 조회할 수 있습니다.'}</p>}
            {runChoices ? <>
              <p>목록 출처: <code>GET /api{runChoices.path}</code> · 관측 시각 <time dateTime={runChoices.observedAt}>{runChoices.observedAt}</time> · 브라우저 수신 <time dateTime={runChoices.receivedAt}>{runChoices.receivedAt}</time></p>
              {runChoices.items.length === 0 && <p>조회한 실행 목록이 비어 있습니다. 아래에서 실행 ID를 직접 입력해 조회할 수 있습니다.</p>}
            </> : runChoicesNotice === null && busy !== 'runs' && <p>아직 선택할 목록을 불러오지 않았습니다. 실행 ID를 직접 입력해도 됩니다.</p>}
          </div>
        </div>
        <div className="api-run-id">
          <label htmlFor="api-run-id">경로 파라미터 · 실행 ID</label>
          <input id="api-run-id" value={runId} maxLength={80} spellCheck={false} autoComplete="off" aria-invalid={invalidId || undefined}
            aria-describedby="api-run-id-hint" disabled={controlsDisabled} onChange={event => changeRunId(event.target.value)} />
          <p id="api-run-id-hint">소문자·숫자로 시작하며 소문자·숫자·점·밑줄·하이픈으로 최대 80자입니다. 목록에 없는 ID도 입력할 수 있으며, 존재 여부는 상세 조회에서 확인합니다.{invalidId && ' 현재 ID 형식이 올바르지 않습니다.'}</p>
        </div></> : <p className="api-parameter-note">입력 파라미터 없음 · query string과 인증 정보는 전송하지 않습니다.</p>}
        <details className="api-field-details"><summary>응답에서 볼 항목</summary><dl>{endpoint.fields.map(([field, description]) => <div key={field}><dt><code>{field}</code></dt><dd>{description}</dd></div>)}</dl></details>
        <p className="api-boundary">{endpoint.boundary}</p>
        <button className="button api-query" type="button" disabled={controlsDisabled || invalidId} onClick={() => { void query(endpoint.id); }}>
          {busy === endpoint.id ? '응답 기다리는 중…' : 'GET으로 직접 조회'}<span aria-hidden="true">↗</span>
        </button>
        <div className="api-result" aria-live="polite" aria-busy={entry?.state === 'loading'}>
          {selectionChanged && <p className="api-selection-changed">선택이 바뀌었습니다. 아래는 이전 ID의 {entry?.state === 'success' ? '조회 결과' : '요청'}입니다. 새 ID는 조회 버튼을 눌러 확인하세요.</p>}
          {!entry && <p className="api-idle">아직 조회하지 않았습니다.</p>}
          {(entry?.state === 'loading' || entry?.state === 'error') && <p className="api-result-request">요청: <code>GET /api{entry.requestPath}</code></p>}
          {entry?.state === 'loading' && <p>최대 8초 동안 응답을 기다립니다.</p>}
          {entry?.state === 'error' && <p className="api-error">{entry.message}</p>}
          {entry?.state === 'success' && <>
            <p className="api-success">HTTP {entry.result.status} · JSON 응답 수신</p>
            <dl className="api-result-meta"><div><dt>요청</dt><dd><code>GET /api{entry.result.path}</code></dd></div><div><dt>출처</dt><dd>설정된 API에 직접 조회 · 스냅샷 아님</dd></div><div><dt>브라우저 수신 시각</dt><dd><time dateTime={entry.result.receivedAt}>{entry.result.receivedAt}</time></dd></div><div><dt>응답의 조회·관측 시각</dt><dd>{entry.result.responseTime ? <time dateTime={entry.result.responseTime}>{entry.result.responseTime}</time> : '응답에서 확인되지 않음'}</dd></div></dl>
            {endpoint.id === 'detail' && <ApiRunSummary result={entry.result} basePath={basePath} />}
            <details className="api-json"><summary>실제 JSON 응답 펼치기</summary><div className="api-copy-row"><button type="button" onClick={() => { void copy(endpoint.id, entry.result.json); }}>JSON 복사</button><span role="status">{copyStatus[endpoint.id]}</span></div><pre tabIndex={0} aria-label={`${endpoint.title} JSON 응답`}><code>{entry.result.json}</code></pre></details>
          </>}
        </div>
        <a className="api-back-index" href="#api-list">API 목차로 ↑</a>
      </article>;
    })}</div>
  </div>;
}
