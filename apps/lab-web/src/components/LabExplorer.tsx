import { useEffect, useRef, useState } from 'react';
import { fetchLab, fetchRun } from '../lib/api';
import type { LabData, Point, OutcomeStatus } from '../lib/api';
import snapshot from '../data/snapshot.json';

const initial = snapshot as LabData;
const statusLabel: Record<string, string> = { SUCCESS: '성공', FAILED: '실패', DUPLICATE: '중복', PENDING: '대기' };
const reasonLabel: Record<string, string> = {
  ACCEPTED: '검증 통과', DUPLICATE_EVENT_ID: '동일 이벤트 ID', INVALID_TIMESTAMP: '잘못된 시간 형식',
  OUT_OF_ORDER: '센서 시간 역순', OUT_OF_RANGE: '허용 범위 초과', INVALID_INPUT: '입력 형식 오류',
};
const componentLabel: Record<string, string> = { API: 'Spring Boot API', DATABASE: 'Database', JENKINS: 'Jenkins CI', ARGO_CD: 'Argo CD', KUBERNETES: 'Kubernetes', KAFKA: 'Kafka', S3: 'Object storage' };
const formatTime = (value: string | null | undefined) => value && !Number.isNaN(Date.parse(value)) ? new Intl.DateTimeFormat('ko-KR', { dateStyle: 'medium', timeStyle: 'medium', timeZone: 'Asia/Seoul' }).format(new Date(value)) + ' KST' : '아직 관측 전';
function componentStatus(status: string) {
  if (status === 'RUNNING') return '관측됨';
  if (status === 'PLANNED') return '확장 예정';
  if (status === 'UNAVAILABLE') return '연결 확인 필요';
  return '아직 연결 전';
}

function SensorChart({ points }: { points: Point[] }) {
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
      <label className="sensor-select"><span className="sr-only">센서 선택</span><select value={sensor} onChange={event => { setSensor(event.target.value); setSelected(null); }}><option value="all">모든 센서</option>{sensors.map(item => <option key={item} value={item}>{item}</option>)}</select></label>
    </div>
    {points.length === 0 ? <p className="empty-message">표시할 성공 이벤트가 없습니다.</p> : <>
      <svg className="chart-svg" viewBox="0 0 660 233" role="img" aria-label="센서별 성공 이벤트 값. 차트 아래의 데이터 포인트 버튼에서 상세 값을 확인할 수 있습니다.">
        {[0, 1, 2, 3].map(index => { const value = low + (high - low) * index / 3; const pos = 187 - 157 * index / 3; return <g key={index}><line x1="52" x2="624" y1={pos} y2={pos} stroke="var(--line)" strokeDasharray="3 5"/><text x="35" y={pos + 4} textAnchor="end" className="chart-label">{value.toFixed(0)}</text></g>; })}
        {sensors.filter(item => sensor === 'all' || sensor === item).map(item => <polyline key={item} points={points.filter(point => point.sensorId === item).sort((a, b) => Date.parse(a.eventTime) - Date.parse(b.eventTime)).map(point => `${x(point)},${y(point)}`).join(' ')} fill="none" stroke={sensors.indexOf(item) % 2 === 0 ? 'var(--orange)' : 'var(--green)'} strokeWidth="3" strokeLinejoin="round"/>)}
        {filtered.map((point, index) => <circle key={`${point.sensorId}-${point.eventTime}-${index}`} cx={x(point)} cy={y(point)} r={selected === index ? 7 : 5} fill={sensors.indexOf(point.sensorId) % 2 === 0 ? 'var(--orange)' : 'var(--green)'} stroke="var(--paper)" strokeWidth="2" aria-hidden="true" onMouseEnter={() => setSelected(index)} onClick={() => setSelected(index)}/>) }
        <text x="52" y="220" className="chart-label">{new Date(minTime).toISOString().slice(11, 19)} UTC</text><text x="624" y="220" textAnchor="end" className="chart-label">{new Date(maxTime).toISOString().slice(11, 19)} UTC</text>
      </svg>
      <div className="point-selector" role="group" aria-label="데이터 포인트 상세 선택"><span>포인트 선택</span><div>{filtered.map((point, index) => <button key={`${point.sensorId}-${point.eventTime}-${index}`} type="button" aria-pressed={selected === index} aria-label={`${point.sensorId}, ${point.eventTime}, 값 ${point.value}`} onClick={() => setSelected(index)}><i style={{ background: sensors.indexOf(point.sensorId) % 2 === 0 ? 'var(--orange)' : 'var(--green)' }}/>{point.sensorId.replace('sensor-', '')} · {point.eventTime.slice(14, 19)} · {point.value}</button>)}</div></div>
      <div className="chart-bottom"><div className="chart-legend">{sensors.map((item, index) => <span key={item}><i style={{ background: index % 2 === 0 ? 'var(--orange)' : 'var(--green)' }}/>{item}</span>)}</div><p aria-live="polite">{active ? `${active.sensorId} · ${active.eventTime.slice(11, 19)} UTC · ${active.value}` : '포인트를 선택하면 값이 표시됩니다.'}</p></div>
    </>}
  </div>;
}

export default function LabExplorer({ apiBase = '/api' }: { apiBase?: string }) {
  const [data, setData] = useState<LabData>(initial);
  const [mode, setMode] = useState<'snapshot' | 'live'>('snapshot');
  const [loading, setLoading] = useState(false);
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
    try { const result = await fetchLab(apiBase, request.signal, data.detail.id); if (mounted.current) { setData(result); setMode('live'); } }
    catch { if (mounted.current && controller.current === request) { setData(initial); setMode('snapshot'); setError('실시간 Lab 연결 불가'); } }
    finally { clearTimeout(timer); if (mounted.current && controller.current === request) setLoading(false); }
  }
  useEffect(() => { mounted.current = true; void refresh(); return () => { mounted.current = false; controller.current?.abort(); }; }, []);

  async function selectRun(id: string) {
    if (mode !== 'live') return;
    controller.current?.abort(); const request = new AbortController(); controller.current = request;
    setLoading(true); setError(''); const timer = setTimeout(() => request.abort(), 8000);
    try { const detail = await fetchRun(apiBase, id, request.signal); if (mounted.current) setData(previous => ({ ...previous, detail })); }
    catch { if (mounted.current && controller.current === request) setError('선택한 결과를 불러오지 못했습니다. 이전 결과를 표시합니다.'); }
    finally { clearTimeout(timer); if (mounted.current && controller.current === request) setLoading(false); }
  }
  const detail = data.detail;
  const outcomes = detail.outcomes.filter(row => filter === 'ALL' || row.status === filter);
  const counts: [string, number, string][] = [['성공', detail.successCount, 'success'], ['실패', detail.failureCount, 'failed'], ['중복', detail.duplicateCount, 'duplicate'], ['대기', detail.pendingCount, 'pending']];
  return <>
    <section id="lab" className="section lab-section" aria-labelledby="lab-title">
      <div className="section-heading"><div><span className="eyebrow">02 / EXPLORE THE LAB</span><h2 id="lab-title">결과로 보는 작은 데이터 파이프라인.</h2><p>12개의 합성 센서 이벤트를 검증하고, 처리된 이유까지 확인합니다.</p></div><span className="section-mark">[ READ ONLY ]</span></div>
      <div className={`connection-banner ${mode === 'live' ? 'connected' : ''}`} role="status" aria-live="polite"><span className="signal-dot"/><div><strong>{loading ? '실시간 상태 확인 중' : mode === 'live' ? '실시간 API 연결됨' : error || '합성 데이터 샘플'}</strong><span>{mode === 'live' ? `API 관측 · ${formatTime(data.observedAt)}` : `합성 데이터 샘플 · 파일 생성 ${formatTime(initial.capturedAt)}`}</span></div><button className="button button-small" onClick={() => void refresh()} disabled={loading}><span aria-hidden="true">↻</span> {loading ? '확인 중' : '실시간 조회'}</button></div>
      {mode === 'snapshot' && <p className="snapshot-note">이 화면은 고정 샘플의 기대 결과입니다. 실제 실행·배포 기록은 API 연결 후 표시합니다.</p>}
      {mode === 'live' && error && <p className="error-note" role="alert">{error}</p>}
      <div className="lab-workspace"><div className="run-main">
        <div className="run-title"><div><span className="code-label">SCENARIO / {detail.scenario}</span><h3>{detail.name}</h3></div><span className="tag tag-green">합성 데이터</span></div>
        <div className="run-controls"><label htmlFor="run-select">실행 결과</label><select id="run-select" value={detail.id} onChange={event => void selectRun(event.target.value)} disabled={loading}>{data.runs.map(run => <option value={run.id} key={run.id}>{run.name} / seed {run.seed}</option>)}</select><span className="code-label">SEED {detail.seed}</span></div>
        <div className="metrics"><div className="metric metric-total"><span>입력 이벤트</span><strong>{detail.inputCount}<small>건</small></strong></div>{counts.map(([label, value, color]) => <button className={`metric ${color} ${filter === ({ 성공: 'SUCCESS', 실패: 'FAILED', 중복: 'DUPLICATE', 대기: 'PENDING' } as Record<string, string>)[label] && tab === 'events' ? 'metric-selected' : ''}`} key={label} onClick={() => { setFilter(({ 성공: 'SUCCESS', 실패: 'FAILED', 중복: 'DUPLICATE', 대기: 'PENDING' } as Record<string, OutcomeStatus>)[label]!); setTab('events'); }} aria-label={`${label} ${value}건 상세 보기`}><span><i/>{label}</span><strong>{value}<small>건</small></strong></button>)}</div>
        <div className="count-bar" aria-label="입력 이벤트 처리 비율">{counts.filter(([, value]) => value > 0).map(([label, value, color]) => <span key={label} className={color} style={{ flex: value }} title={`${label} ${value}건`}/>)}</div>
        <p className="balance-note">입력 {detail.inputCount} = 성공 {detail.successCount} + 실패 {detail.failureCount} + 중복 {detail.duplicateCount} + 대기 {detail.pendingCount}</p>
        <div className="tabs" role="tablist" aria-label="실행 결과 보기"><button onKeyDown={event => { if (['ArrowRight', 'End'].includes(event.key)) { event.preventDefault(); setTab('events'); document.getElementById('events-tab')?.focus(); } }} role="tab" tabIndex={tab === 'chart' ? 0 : -1} id="chart-tab" aria-controls="chart-panel" aria-selected={tab === 'chart'} onClick={() => setTab('chart')}>시계열 결과 <span>↗</span></button><button onKeyDown={event => { if (['ArrowLeft', 'Home'].includes(event.key)) { event.preventDefault(); setTab('chart'); document.getElementById('chart-tab')?.focus(); } }} role="tab" tabIndex={tab === 'events' ? 0 : -1} id="events-tab" aria-controls="events-panel" aria-selected={tab === 'events'} onClick={() => setTab('events')}>이벤트 상세 <span>{detail.outcomes.length}</span></button></div>
        <div id="chart-panel" role="tabpanel" aria-labelledby="chart-tab" hidden={tab !== 'chart'}><SensorChart key={`${detail.id}-${mode}`} points={detail.series}/></div>
        <div id="events-panel" role="tabpanel" aria-labelledby="events-tab" hidden={tab !== 'events'}><div className="event-filters"><label htmlFor="event-filter">처리 상태</label><select id="event-filter" value={filter} onChange={event => setFilter(event.target.value as OutcomeStatus | 'ALL')}><option value="ALL">전체 이벤트</option>{Object.entries(statusLabel).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select><span>{outcomes.length}건 표시</span></div><div className="table-scroll" tabIndex={0} aria-label="이벤트 상세 표"><table><caption className="sr-only">입력 순서별 이벤트 처리 결과</caption><thead><tr><th scope="col">순서 / ID</th><th scope="col">센서</th><th scope="col">입력 시간 (UTC)</th><th scope="col">값</th><th scope="col">결과 / 이유</th></tr></thead><tbody>{outcomes.map(row => <tr key={row.sequence}><td><span className="muted">{String(row.sequence).padStart(2, '0')}</span> {row.eventId}</td><td>{row.sensorId}</td><td className="time-cell">{row.eventTime}</td><td>{row.value ?? '—'}</td><td><span className={`result-label ${row.status.toLowerCase()}`}>{statusLabel[row.status]}</span><small>{reasonLabel[row.reason] || row.reason}</small></td></tr>)}</tbody></table>{outcomes.length === 0 && <p className="empty-message">해당 상태의 이벤트가 없습니다.</p>}</div></div>
      </div><aside className="run-aside"><div className="aside-heading"><span className="eyebrow">WHY THESE RESULTS</span><h3>건수보다,<br/>처리한 이유까지.</h3></div><div className="reason-item"><span>01</span><div><h4>중복은 한 번만</h4><p>같은 이벤트 ID가 다시 들어와도 중복으로 분리합니다.</p></div></div><div className="reason-item"><span>02</span><div><h4>시간의 순서 확인</h4><p>잘못된 시간 형식과 센서별 과거 이벤트를 검증합니다.</p></div></div><div className="reason-item"><span>03</span><div><h4>실패도 결과에 남기기</h4><p>범위를 벗어난 값을 실패 사유와 함께 조회합니다.</p></div></div><div className="run-metadata"><p><span>실행 시작</span><strong>{formatTime(detail.startedAt)}</strong></p><p><span>실행 완료</span><strong>{formatTime(detail.completedAt)}</strong></p><p><span>결과 관측</span><strong>{formatTime(detail.observedAt)}</strong></p></div><p className="small-note">회사 데이터·코드를 사용하지 않는 개인 공개 예제입니다.</p></aside></div>
    </section>
    <section id="platform" className="section platform-section" aria-labelledby="platform-title"><div className="section-heading"><div><span className="eyebrow">03 / FROM SOURCE TO SERVICE</span><h2 id="platform-title">배포도 설명할 수 있도록.</h2><p>연결된 상태와 앞으로 구축할 부분을 함께 공개합니다.</p></div><span className="section-mark">[ OBSERVABILITY ]</span></div>
      <div className="deployment-flow" aria-label="구축할 CI CD 처리 흐름"><span><b>01</b> Git commit</span><i>→</i><span><b>02</b> Jenkins CI</span><i>→</i><span><b>03</b> Image digest</span><i>→</i><span><b>04</b> GitOps + Helm</span><i>→</i><span><b>05</b> Argo CD / K3s</span></div>
      <div className="platform-grid">{data.summary.components.map(component => <article className="platform-item" key={component.name}><div><span className={`component-dot ${component.status === 'RUNNING' ? 'running' : ''}`}/><h3>{componentLabel[component.name] || component.name}</h3><span className="platform-status">{componentStatus(component.status)}</span></div><p>{component.detail}</p></article>)}</div>
      <div className="release-strip"><div><span className="eyebrow">RUNTIME INFORMATION</span><strong>{data.releases.length ? '현재 API 런타임' : '배포 관측 이력 없음'}</strong></div>{data.releases.length ? data.releases.map((release, index) => <div key={`${release.service}-${index}`} className="release-meta"><span>{release.service} / v{release.version}</span><code>{release.sourceCommit === 'unknown' ? '소스 commit 미주입' : release.sourceCommit.slice(0, 12)}</code><small>{release.deploymentStatus === 'LOCAL_RUNTIME' ? '로컬 실행 정보 · CI/CD 이력 연결 전' : release.deploymentStatus}</small><small>{release.imageDigest ? `이미지 ${release.imageDigest}` : '이미지 digest 미관측'}</small></div>) : <p>Jenkins·Argo CD의 실제 검증 결과를 연결한 뒤 표시합니다.</p>}<span className="tag">공개 실행 비활성</span></div>
    </section>
  </>;
}
