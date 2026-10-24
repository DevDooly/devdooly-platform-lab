import { useEffect, useRef, useState } from 'react';
import { API_ENDPOINTS, ApiReadFailure, DEFAULT_RUN_ID, apiEndpointPath, readPublicApi, type ApiEndpointId, type ApiReadResult } from '../data/public-api-reference';
import { publicApiConfiguration } from '../lib/public-api-base';
import '../styles/api-console.css';

interface Props { apiBase?: string; }
type Entry = { state: 'loading' } | { state: 'success'; result: ApiReadResult } | { state: 'error'; message: string };
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

export default function ApiConsole({ apiBase = '/api' }: Props) {
  const configuration = publicApiConfiguration(apiBase);
  const [ready, setReady] = useState(false);
  const [runId, setRunId] = useState(DEFAULT_RUN_ID);
  const [entries, setEntries] = useState<Partial<Record<ApiEndpointId, Entry>>>({});
  const [busy, setBusy] = useState<ApiEndpointId | null>(null);
  const [copyStatus, setCopyStatus] = useState<Partial<Record<ApiEndpointId, string>>>({});
  const inFlight = useRef(false);
  const mounted = useRef(false);
  useEffect(() => { mounted.current = true; setReady(true); return () => { mounted.current = false; }; }, []);
  async function query(id: ApiEndpointId) {
    if (!ready || configuration.invalid || inFlight.current || !apiEndpointPath(id, runId)) return;
    inFlight.current = true; setBusy(id); setEntries(previous => ({ ...previous, [id]: { state: 'loading' } }));
    setCopyStatus(previous => ({ ...previous, [id]: '' }));
    try {
      const result = await readPublicApi(configuration.apiBase, id, runId);
      if (mounted.current) setEntries(previous => ({ ...previous, [id]: { state: 'success', result } }));
    } catch (error) {
      if (mounted.current) setEntries(previous => ({ ...previous, [id]: { state: 'error', message: failureMessage(error) } }));
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
      return <article className="api-endpoint" id={`api-${endpoint.id}`} key={endpoint.id} aria-labelledby={`api-heading-${endpoint.id}`}>
        <div className="api-endpoint-heading"><span className="api-method">GET</span><h2 id={`api-heading-${endpoint.id}`}>{endpoint.title}</h2></div>
        <code className="api-path">/api{endpoint.path}</code>
        <p>{endpoint.description}</p>
        {endpoint.id === 'detail' ? <div className="api-run-id">
          <label htmlFor="api-run-id">경로 파라미터 · 실행 ID</label>
          <input id="api-run-id" value={runId} maxLength={80} spellCheck={false} autoComplete="off" aria-invalid={invalidId || undefined}
            aria-describedby="api-run-id-hint" disabled={!ready || busy !== null || configuration.invalid} onChange={event => setRunId(event.target.value)} />
          <p id="api-run-id-hint">소문자·숫자로 시작하며 소문자·숫자·점·밑줄·하이픈으로 최대 80자입니다. 목록 응답의 id를 복사해 넣을 수 있습니다.{invalidId && ' 현재 ID 형식이 올바르지 않습니다.'}</p>
        </div> : <p className="api-parameter-note">입력 파라미터 없음 · query string과 인증 정보는 전송하지 않습니다.</p>}
        <details className="api-field-details"><summary>응답에서 볼 항목</summary><dl>{endpoint.fields.map(([field, description]) => <div key={field}><dt><code>{field}</code></dt><dd>{description}</dd></div>)}</dl></details>
        <p className="api-boundary">{endpoint.boundary}</p>
        <button className="button api-query" type="button" disabled={!ready || configuration.invalid || busy !== null || invalidId} onClick={() => { void query(endpoint.id); }}>
          {busy === endpoint.id ? '응답 기다리는 중…' : 'GET으로 직접 조회'}<span aria-hidden="true">↗</span>
        </button>
        <div className="api-result" aria-live="polite" aria-busy={entry?.state === 'loading'}>
          {!entry && <p className="api-idle">아직 조회하지 않았습니다.</p>}
          {entry?.state === 'loading' && <p>최대 8초 동안 응답을 기다립니다.</p>}
          {entry?.state === 'error' && <p className="api-error">{entry.message}</p>}
          {entry?.state === 'success' && <>
            <p className="api-success">HTTP {entry.result.status} · JSON 응답 수신</p>
            <dl className="api-result-meta"><div><dt>요청</dt><dd><code>GET /api{entry.result.path}</code></dd></div><div><dt>출처</dt><dd>설정된 API에 직접 조회 · 스냅샷 아님</dd></div><div><dt>브라우저 수신 시각</dt><dd><time dateTime={entry.result.receivedAt}>{entry.result.receivedAt}</time></dd></div><div><dt>응답의 조회·관측 시각</dt><dd>{entry.result.responseTime ? <time dateTime={entry.result.responseTime}>{entry.result.responseTime}</time> : '응답에서 확인되지 않음'}</dd></div></dl>
            <details className="api-json"><summary>실제 JSON 응답 펼치기</summary><div className="api-copy-row"><button type="button" onClick={() => { void copy(endpoint.id, entry.result.json); }}>JSON 복사</button><span role="status">{copyStatus[endpoint.id]}</span></div><pre tabIndex={0} aria-label={`${endpoint.title} JSON 응답`}><code>{entry.result.json}</code></pre></details>
          </>}
        </div>
        <a className="api-back-index" href="#api-list">API 목차로 ↑</a>
      </article>;
    })}</div>
  </div>;
}
