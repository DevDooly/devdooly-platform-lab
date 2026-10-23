import { useEffect, useRef, useState, type KeyboardEvent } from 'react';
import { describeLiveFailure, fetchRun, liveFailureOf } from '../lib/api';
import { loadLabSources } from '../lib/observation';
import type { ObservationRecord, SourceMode } from '../lib/observation';
import type { LabData, Point, OutcomeStatus } from '../lib/api';
import snapshot from '../data/snapshot.json';
import '../styles/api-connection-scope.css';
import TourStepNavigation from './TourStepNavigation';

const initial = snapshot as LabData;
const evidenceBase = 'https://github.com/DevDooly/devdooly-platform-lab/blob/main/docs/evidence';
const statusLabel: Record<string, string> = { SUCCESS: '성공', FAILED: '실패', DUPLICATE: '중복', PENDING: '대기' };
const reasonLabel: Record<string, string> = {
  ACCEPTED: '검증 통과', DUPLICATE_EVENT_ID: '동일 이벤트 ID', INVALID_TIMESTAMP: '잘못된 시간 형식',
  OUT_OF_ORDER: '센서 시간 역순', OUT_OF_RANGE: '허용 범위 초과', INVALID_INPUT: '입력 형식 오류',
};
const componentLabel: Record<string, string> = { API: 'Spring Boot API', DATABASE: 'Database', JENKINS: 'Jenkins CI', ARGO_CD: 'Argo CD', KUBERNETES: 'Kubernetes', KAFKA: 'Kafka', S3: 'Object storage' };
const formatTime = (value: string | null | undefined) => value && !Number.isNaN(Date.parse(value)) ? new Intl.DateTimeFormat('ko-KR', { dateStyle: 'medium', timeStyle: 'medium', timeZone: 'Asia/Seoul' }).format(new Date(value)) + ' KST' : '아직 관측 전';
function componentStatus(status: string) {
  if (status === 'RUNNING') return '관측됨';
  if (status === 'PLANNED') return 'API 수집 대기';
  if (status === 'UNAVAILABLE') return '연결 확인 필요';
  if (status === 'NOT_CONFIGURED') return '관측 연결 전';
  return '아직 연결 전';
}

function SensorChart({ points, interactive }: { points: Point[]; interactive: boolean }) {
  const [sensor, setSensor] = useState('all');
  const [selected, setSelected] = useState<number | null>(null);
  const sensors = [...new Set(points.map(point => point.sensorId))].sort();
  const filtered = points.filter(point => sensor === 'all' || point.sensorId === sensor);
  const times = points.map(point => Date.parse(point.eventTime));
  const minTime = Math.min(...times), maxTime = Math.max(...times);
  const values = points.map(point => point.value);
  const low = Math.floor((Math.min(...values, 0)) / 10) * 10;
  const high = Math.ceil(Math.max(...values, 10) / 10) * 10;
  const x = (point: Point) => 52 + (Date.parse(point.eventTime) - minTime) / Math.max(maxTime - minTime, 1) * 572;
  const y = (point: Point) => 187 - (point.value - low) / Math.max(high - low, 1) * 157;
  const active = selected === null ? null : filtered[selected];
  return <div className="sensor-chart">
    <div className="chart-heading"><div><h4>검증을 통과한 데이터</h4><p>성공한 이벤트만 시계열에 반영합니다.</p></div>
      <label className="sensor-select"><span className="sr-only">센서 선택</span><select value={sensor} disabled={!interactive} onChange={event => { setSensor(event.target.value); setSelected(null); }}><option value="all">모든 센서</option>{sensors.map(item => <option key={item} value={item}>{item}</option>)}</select></label>
    </div>
    {points.length === 0 ? <p className="empty-message">표시할 성공 이벤트가 없습니다.</p> : <>
      <div className="chart-scroll" role="region" aria-label="시계열 차트, 좌우 스크롤 가능" tabIndex={0}><svg className="chart-svg" viewBox="0 0 660 233" role="img" aria-label="센서별 성공 이벤트 값. 차트 아래의 데이터 포인트 버튼에서 상세 값을 확인할 수 있습니다.">
        {[0, 1, 2, 3].map(index => { const value = low + (high - low) * index / 3; const pos = 187 - 157 * index / 3; return <g key={index}><line x1="52" x2="624" y1={pos} y2={pos} stroke="var(--line)" strokeDasharray="3 5"/><text x="35" y={pos + 4} textAnchor="end" className="chart-label">{value.toFixed(0)}</text></g>; })}
        {sensors.filter(item => sensor === 'all' || sensor === item).map(item => <polyline key={item} points={points.filter(point => point.sensorId === item).sort((a, b) => Date.parse(a.eventTime) - Date.parse(b.eventTime)).map(point => `${x(point)},${y(point)}`).join(' ')} fill="none" stroke={sensors.indexOf(item) % 2 === 0 ? 'var(--orange)' : 'var(--green)'} strokeWidth="3" strokeLinejoin="round"/>)}
        {filtered.map((point, index) => <circle key={`${point.sensorId}-${point.eventTime}-${index}`} cx={x(point)} cy={y(point)} r={selected === index ? 7 : 5} fill={sensors.indexOf(point.sensorId) % 2 === 0 ? 'var(--orange)' : 'var(--green)'} stroke="var(--paper)" strokeWidth="2" aria-hidden="true" onMouseEnter={interactive ? () => setSelected(index) : undefined} onClick={interactive ? () => setSelected(index) : undefined}/>) }
        <text x="52" y="220" className="chart-label">{new Date(minTime).toISOString().slice(11, 19)} UTC</text><text x="624" y="220" textAnchor="end" className="chart-label">{new Date(maxTime).toISOString().slice(11, 19)} UTC</text>
      </svg></div>
      <p className="chart-scroll-hint">화면이 좁으면 차트를 좌우로 이동해 볼 수 있습니다.</p>
      <div className="point-selector" role="group" aria-label="데이터 포인트 상세 선택"><span>포인트 선택</span><div>{filtered.map((point, index) => <button key={`${point.sensorId}-${point.eventTime}-${index}`} type="button" disabled={!interactive} aria-pressed={selected === index} aria-label={`${point.sensorId}, ${point.eventTime}, 값 ${point.value}`} onClick={() => setSelected(index)}><i style={{ background: sensors.indexOf(point.sensorId) % 2 === 0 ? 'var(--orange)' : 'var(--green)' }}/>{point.sensorId.replace('sensor-', '')} · {point.eventTime.slice(14, 19)} · {point.value}</button>)}</div></div>
      <div className="chart-bottom"><div className="chart-legend">{sensors.map((item, index) => <span key={item}><i style={{ background: index % 2 === 0 ? 'var(--orange)' : 'var(--green)' }}/>{item}</span>)}</div><p aria-live="polite">{active ? `${active.sensorId} · ${active.eventTime.slice(11, 19)} UTC · ${active.value}` : '포인트를 선택하면 값이 표시됩니다.'}</p></div>
    </>}
  </div>;
}

export default function LabExplorer({ apiBase = '/api', observationUrl = '/data/lab-observation.json' }: { apiBase?: string; observationUrl?: string }) {
  const [data, setData] = useState<LabData>(initial);
  const [mode, setMode] = useState<SourceMode>('fixture');
  const [observation, setObservation] = useState<ObservationRecord | null>(null);
  const cachedObservation = useRef<ObservationRecord | null>(null);
  const [loading, setLoading] = useState(false);
  const [interactive, setInteractive] = useState(false);
  const [error, setError] = useState('');
  const [tab, setTab] = useState<'chart' | 'events'>('chart');
  const [filter, setFilter] = useState<OutcomeStatus | 'ALL'>('ALL');
  const controller = useRef<AbortController | null>(null);
  const mounted = useRef(true);

  async function refresh() {
    controller.current?.abort();
    const request = new AbortController(); controller.current = request;
    setLoading(true); setError('');
    const timer = setTimeout(() => request.abort(), 8000);
    try {
      const result = await loadLabSources({ apiBase, observationUrl, fixture: initial, signal: request.signal, preferredId: data.detail.id, previousObservation: cachedObservation.current });
      if (mounted.current && controller.current === request) { setData(result.data); setMode(result.mode); setObservation(result.observation); cachedObservation.current = result.cachedObservation; setError(result.liveFailure ? describeLiveFailure(result.liveFailure) : ''); }
    }
    catch (failure) { if (mounted.current && controller.current === request) { setData(initial); setMode('fixture'); setObservation(null); setError(describeLiveFailure(liveFailureOf(failure))); } }
    finally { clearTimeout(timer); if (mounted.current && controller.current === request) setLoading(false); }
  }
  useEffect(() => { mounted.current = true; setInteractive(true); void refresh(); return () => { mounted.current = false; controller.current?.abort(); }; }, []);

  async function selectRun(id: string) {
    if (mode !== 'live') return;
    controller.current?.abort(); const request = new AbortController(); controller.current = request;
    setLoading(true); setError(''); const timer = setTimeout(() => request.abort(), 8000);
    try { const detail = await fetchRun(apiBase, id, request.signal); if (mounted.current) setData(previous => ({ ...previous, detail })); }
    catch (failure) { if (mounted.current && controller.current === request) setError(`선택한 결과를 불러오지 못했습니다. 이전 결과를 표시합니다. ${describeLiveFailure(liveFailureOf(failure))}`); }
    finally { clearTimeout(timer); if (mounted.current && controller.current === request) setLoading(false); }
  }
  function handleTabKey(event: KeyboardEvent<HTMLButtonElement>) {
    if (event.ctrlKey || event.altKey || event.metaKey) return;
    if (!['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(event.key)) return;
    const next = event.key === 'Home' ? 'chart' : event.key === 'End' ? 'events'
      : event.currentTarget.id === 'chart-tab' ? 'events' : 'chart';
    event.preventDefault();
    setTab(next);
    document.getElementById(`${next}-tab`)?.focus();
  }
  const platformSourceMode = mode === 'live' ? '실시간 조회 API' : mode === 'recorded' ? '게시된 마지막 수집 기록' : '합성 샘플';
  const platformTimeLabel = mode === 'live' ? 'API 관측 시각' : mode === 'recorded' ? '기록 수집 시각' : '샘플 파일 생성 시각';
  const platformSourceTime = mode === 'live' ? data.summary.observedAt : mode === 'recorded' ? observation?.capturedAt : initial.capturedAt;
  const detail = data.detail;
  const outcomes = detail.outcomes.filter(row => filter === 'ALL' || row.status === filter);
  const counts: [string, number, string][] = [['성공', detail.successCount, 'success'], ['실패', detail.failureCount, 'failed'], ['중복', detail.duplicateCount, 'duplicate'], ['대기', detail.pendingCount, 'pending']];
  return <>
    <section id="lab" className="section lab-section" aria-labelledby="lab-title" aria-busy={!interactive}>
      <div className="section-heading"><div><span className="eyebrow">02 / EXPLORE THE LAB</span><h2 id="lab-title">결과로 보는 작은 데이터 파이프라인.</h2><p>합성 센서 이벤트를 검증하고, 처리된 이유까지 확인합니다.</p></div><span className="section-mark">[ READ ONLY ]</span></div>
      <div className={`connection-banner ${mode === 'live' ? 'connected' : ''}`} role="status" aria-live="polite"><span className="signal-dot"/><div><strong>{loading ? '실시간 상태 확인 중' : mode === 'live' ? '실시간 API 연결됨' : mode === 'recorded' ? '미니 PC에서 확인한 마지막 기록' : error || '합성 데이터 샘플'}</strong><span>{mode === 'live' ? `API 관측 · ${formatTime(data.observedAt)}` : mode === 'recorded' ? `수집 · ${formatTime(observation?.capturedAt)}` : `합성 데이터 샘플 · 파일 생성 ${formatTime(initial.capturedAt)}`}</span>{!interactive && <small>화면 조작 준비 중</small>}</div><button className="button button-small" onClick={() => void refresh()} disabled={!interactive || loading}><span aria-hidden="true">↻</span> {loading ? '확인 중' : '실시간 조회'}</button></div>
      {mode === 'fixture' && <p className="snapshot-note">이 화면은 고정 샘플의 기대 결과입니다. 미니 PC의 실제 결과가 연결되면 수집 시각과 출처를 함께 표시합니다.</p>}
      {mode === 'recorded' && observation && <div className="observation-note"><p>{error ? `${error}. ` : ''}수집 당시의 합성 데이터 처리 결과와 API 런타임입니다. 현재 상태나 CI/CD 배포 이력을 뜻하지 않습니다.</p><div><span>DEPLOYED SOURCE</span><code title={observation.provenance.sourceCommit}>{observation.provenance.sourceCommit.slice(0, 12)}</code>{observation.provenance.evidenceUrl && <a href={observation.provenance.evidenceUrl} target="_blank" rel="noreferrer">검증 기록 ↗</a>}</div></div>}
      {mode === 'live' && error && <p className="error-note" role="alert">{error}</p>}
      <div className="lab-workspace"><div className="run-main">
        <div className="run-title"><div><span className="code-label">SCENARIO / {detail.scenario}</span><h3>{detail.name}</h3></div><span className="tag tag-green">합성 데이터</span></div>
        <div className="run-controls"><label htmlFor="run-select">실행 결과</label><select id="run-select" aria-describedby="selected-run-id" value={detail.id} onChange={event => void selectRun(event.target.value)} disabled={!interactive || loading || mode !== 'live'}>{data.runs.map(run => <option value={run.id} key={run.id}>{run.id} · {run.inputCount}건 · {run.name} / seed {run.seed}</option>)}</select><span className="code-label">SEED {detail.seed}</span></div>
        <div className="metrics"><div className="metric metric-total"><span>입력 이벤트</span><strong>{detail.inputCount}<small>건</small></strong></div>{counts.map(([label, value, color]) => <button className={`metric ${color} ${filter === ({ 성공: 'SUCCESS', 실패: 'FAILED', 중복: 'DUPLICATE', 대기: 'PENDING' } as Record<string, string>)[label] && tab === 'events' ? 'metric-selected' : ''}`} key={label} disabled={!interactive} onClick={() => { setFilter(({ 성공: 'SUCCESS', 실패: 'FAILED', 중복: 'DUPLICATE', 대기: 'PENDING' } as Record<string, OutcomeStatus>)[label]!); setTab('events'); }} aria-label={`${label} ${value}건 상세 보기`}><span><i/>{label}</span><strong>{value}<small>건</small></strong></button>)}</div>
        <div className="count-bar" aria-label="입력 이벤트 처리 비율">{counts.filter(([, value]) => value > 0).map(([label, value, color]) => <span key={label} className={color} style={{ flex: value }} title={`${label} ${value}건`}/>)}</div>
        <p className="balance-note">입력 {detail.inputCount} = 성공 {detail.successCount} + 실패 {detail.failureCount} + 중복 {detail.duplicateCount} + 대기 {detail.pendingCount}</p>
        <div className="tabs" role="tablist" aria-label="실행 결과 보기"><button disabled={!interactive} onKeyDown={handleTabKey} role="tab" tabIndex={tab === 'chart' ? 0 : -1} id="chart-tab" aria-controls="chart-panel" aria-selected={tab === 'chart'} onClick={() => setTab('chart')}>시계열 결과 <span>↗</span></button><button disabled={!interactive} onKeyDown={handleTabKey} role="tab" tabIndex={tab === 'events' ? 0 : -1} id="events-tab" aria-controls="events-panel" aria-selected={tab === 'events'} onClick={() => setTab('events')}>이벤트 상세 <span>{detail.outcomes.length}</span></button></div>
        <div id="chart-panel" role="tabpanel" aria-labelledby="chart-tab" hidden={tab !== 'chart'}><SensorChart key={`${detail.id}-${mode}`} points={detail.series} interactive={interactive}/></div>
        <div id="events-panel" role="tabpanel" aria-labelledby="events-tab" hidden={tab !== 'events'}><div className="event-filters"><label htmlFor="event-filter">처리 상태</label><select id="event-filter" value={filter} disabled={!interactive} onChange={event => setFilter(event.target.value as OutcomeStatus | 'ALL')}><option value="ALL">전체 이벤트</option>{Object.entries(statusLabel).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select><span>{outcomes.length}건 표시</span></div><div className="table-scroll" role="region" tabIndex={0} aria-label="이벤트 상세 표, 좌우 스크롤 가능"><table><caption className="sr-only">입력 순서별 이벤트 처리 결과</caption><thead><tr><th scope="col">순서 / ID</th><th scope="col">센서</th><th scope="col">입력 시간 (UTC)</th><th scope="col">값</th><th scope="col">결과 / 이유</th></tr></thead><tbody>{outcomes.map(row => <tr key={row.sequence}><td><span className="muted">{String(row.sequence).padStart(2, '0')}</span> {row.eventId}</td><td>{row.sensorId}</td><td className="time-cell">{row.eventTime}</td><td>{row.value ?? '—'}</td><td><span className={`result-label ${row.status.toLowerCase()}`}>{statusLabel[row.status]}</span><small>{reasonLabel[row.reason] || row.reason}</small></td></tr>)}</tbody></table>{outcomes.length === 0 && <p className="empty-message">해당 상태의 이벤트가 없습니다.</p>}</div></div>
      </div><aside className="run-aside"><div className="aside-heading"><span className="eyebrow">WHY THESE RESULTS</span><h3>건수보다,<br/>처리한 이유까지.</h3></div><div className="reason-item"><span>01</span><div><h4>중복은 한 번만</h4><p>같은 이벤트 ID가 다시 들어와도 중복으로 분리합니다.</p></div></div><div className="reason-item"><span>02</span><div><h4>시간의 순서 확인</h4><p>잘못된 시간 형식과 센서별 과거 이벤트를 검증합니다.</p></div></div><div className="reason-item"><span>03</span><div><h4>실패도 결과에 남기기</h4><p>범위를 벗어난 값을 실패 사유와 함께 조회합니다.</p></div></div><div className="run-metadata"><p id="selected-run-id"><span>선택한 실행 ID</span><strong>{detail.id}</strong></p><p><span>실행 시작</span><strong>{formatTime(detail.startedAt)}</strong></p><p><span>실행 완료</span><strong>{formatTime(detail.completedAt)}</strong></p><p><span>결과 관측</span><strong>{formatTime(detail.observedAt)}</strong></p></div><p className="small-note">회사 데이터·코드를 사용하지 않는 개인 공개 예제입니다.</p></aside></div>
      <TourStepNavigation step={1}/>
    </section>
    <section id="platform" className="section platform-section" aria-labelledby="platform-title"><div className="section-heading"><div><span className="eyebrow">03 / FROM SOURCE TO SERVICE</span><h2 id="platform-title">배포도 설명할 수 있도록.</h2><p>미니 PC의 검증 기록과 조회 API의 관측 상태를 함께 확인합니다.</p></div><span className="section-mark">[ OBSERVABILITY ]</span></div>
      <div className="deployment-flow" aria-label="빌드·이미지 게시·배포 도구의 역할"><span><b>01</b> Git commit</span><i>→</i><span><b>02</b> CI · Jenkins / Actions</span><i>→</i><span><b>03</b> GHCR image digest</span><i>→</i><span><b>04</b> GitOps + Helm</span><i>→</i><span><b>05</b> Argo CD / K3s</span></div>
      <div className="platform-evidence"><div><span className="eyebrow">VERIFICATION RECORDS</span><h3>설치와 실행은 기록으로 확인합니다.</h3><p>같은 소스 SHA의 Jenkins 테스트·패키징과 Actions 통합 검증을 통과한 이미지를 게시하고, 검토한 GitOps 선언을 Argo CD가 배포합니다.</p></div><div className="evidence-links"><a href="#platform-record">게시된 배포·Pod 기록 보기 <span aria-hidden="true">↓</span></a><a href={`${evidenceBase}/cicd-gate/README.md`} target="_blank" rel="noreferrer">같은 SHA의 CI·게시 gate 검증 <span aria-hidden="true">↗</span></a><a href={`${evidenceBase}/mini-pc/README.md`} target="_blank" rel="noreferrer">미니 PC 배포 검증 기록 <span aria-hidden="true">↗</span></a><a href={`${evidenceBase}/jenkins-ci/README.md`} target="_blank" rel="noreferrer">Jenkins 실제 빌드 기록 <span aria-hidden="true">↗</span></a></div></div>
      <details className="api-connection-scope">
        <summary>조회 API의 상세 연결 범위</summary>
        <div className="api-scope-body">
          <dl className="api-scope-meta"><div><dt>표시 모드</dt><dd>{platformSourceMode}</dd></div><div><dt>{platformTimeLabel}</dt><dd>{formatTime(platformSourceTime)}</dd></div></dl>
          <p className="platform-observation-note">아래는 이 조회 API가 수집한 항목과 런타임 정보입니다. ‘API 수집 대기’와 ‘관측 연결 전’은 이 API의 수집 범위를 뜻합니다. 게시된 배포·Pod 기록은 위 링크에서 따로 확인할 수 있습니다.</p>
      <div className="platform-grid">{data.summary.components.map(component => <article className="platform-item" key={component.name}><div><span className={`component-dot ${component.status === 'RUNNING' ? 'running' : ''}`}/><h3>{componentLabel[component.name] || component.name}</h3><span className="platform-status">{mode === 'recorded' && component.status === 'RUNNING' ? '수집 당시 관측' : componentStatus(component.status)}</span></div><p>{component.status === 'PLANNED' ? '이 조회 API의 수집 대상에 아직 포함되지 않았습니다.' : component.detail}</p></article>)}</div>
      <div className="release-strip"><div><span className="eyebrow">RUNTIME INFORMATION</span><strong>{data.releases.length ? mode === 'recorded' ? '수집 당시 API 런타임' : '현재 API 런타임' : '자동 관측 이력 연결 전'}</strong></div>{data.releases.length ? data.releases.map((release, index) => <div key={`${release.service}-${index}`} className="release-meta"><span>{release.service} / v{release.version}</span><code>{release.sourceCommit === 'unknown' ? '소스 commit 미주입' : release.sourceCommit.slice(0, 12)}</code><small>{release.deploymentStatus === 'LOCAL_RUNTIME' ? '로컬 실행 정보 · CI/CD 이력 연결 전' : release.deploymentStatus === 'RUNTIME_ONLY' ? 'API 런타임 정보 · CI/CD 이력 연결 전' : release.deploymentStatus}</small><small>{release.imageDigest ? `이미지 ${release.imageDigest}` : '이미지 digest 미관측'}</small></div>) : <p>실제 설치·빌드 기록은 위 문서에서 확인할 수 있습니다. 이 영역에는 API가 수집한 런타임 정보를 표시합니다.</p>}<span className="tag">공개 실행 비활성</span></div>
        </div>
      </details>
      <TourStepNavigation step={3}/>
    </section>
  </>;
}
