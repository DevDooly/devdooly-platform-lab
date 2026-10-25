import { useEffect, useRef, useState } from 'react';
import { jobObservationView, loadJobObservation } from '../lib/job-observation';
import type { JobBrowserError, JobObservationRecord } from '../lib/job-observation';
import '../styles/job-observation.css';
import JobObservationList from './JobObservationList';
import { DEFAULT_JOB_FILTERS } from '../lib/job-list';
import type { JobListFilters } from '../lib/job-list';
import { publicReadUrl } from '../lib/public-api-base';
import { loadLiveWithRecordedFallback } from '../lib/public-observation-source';

const repository = 'https://github.com/DevDooly/devdooly-platform-lab';
const runtimeNames = { NOT_STARTED: '실행 기록 없음', RUNNING: '마지막 DB 신호: 실행 중', PAUSED_OPERATOR: '운영자 확인 대기 · 자동 재시작 차단', STOPPED: '종료 기록' };
const stageNames = { IDLE: '작업 대기', PUBLISH: 'Kafka 발행', CONSUME: '수신·DB 처리', EXPORT: '결과·실패 파일 저장 확인', STOPPED: '종료' };
const environmentNames = { LOCAL: '로컬 검증', TEST: '자동 시험', ISOLATED_LAB: '격리 Lab 시험', MINI_PC: '배포 런타임', UNKNOWN: '환경 미분류' };
const errorNames: Record<JobBrowserError, string> = {
  NOT_CONFIGURED: '작업 관측 연결 또는 게시 기록이 아직 없습니다.', HTTP_ERROR: '새 작업 관측을 조회하지 못했습니다.',
  NETWORK_ERROR: '브라우저 연결 문제로 새 기록을 읽지 못했습니다.', INVALID_RECORD: '공개 형식을 확인할 수 없어 새 기록을 표시하지 않았습니다.',
  ABORTED: '기록 조회가 중단되거나 제한 시간을 넘었습니다.', OLDER_RECORD: '수집 시각이 이전 기록보다 오래되어 마지막 유효 기록을 유지합니다.',
  CONFLICTING_RECORD: '같은 수집 시각의 작업 기록이 달라 마지막 유효 기록을 유지합니다.',
};
function time(value: string | null) {
  return value ? `${new Intl.DateTimeFormat('ko-KR', { timeZone: 'UTC', year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', second: '2-digit', hourCycle: 'h23' }).format(new Date(value))} UTC` : '미기록';
}
function Source({ label, sha }: { label: string; sha: string }) {
  return <div><dt>{label}</dt><dd>{sha === 'unknown' ? '소스 SHA 미기록' : <a href={`${repository}/commit/${sha}`} target="_blank" rel="noreferrer"><code>{sha}</code><span className="sr-only"> GitHub 소스 커밋, 새 창</span> ↗</a>}</dd></div>;
}
export default function JobObservationCard({ apiBase, observationUrl, mode, preferLive = false, basePath = '/' }: { apiBase: string; observationUrl: string; mode: 'api' | 'recorded'; preferLive?: boolean; basePath?: string }) {
  const [record, setRecord] = useState<JobObservationRecord | null>(null);
  const [error, setError] = useState<JobBrowserError | null>(null);
  const [retained, setRetained] = useState(false);
  const [loading, setLoading] = useState(true);
  const [jobFilters, setJobFilters] = useState<JobListFilters>({ ...DEFAULT_JOB_FILTERS });
  const [now, setNow] = useState(0);
  const previous = useRef<JobObservationRecord | null>(null);
  const previousLive = useRef<JobObservationRecord | null>(null);
  const previousRecorded = useRef<JobObservationRecord | null>(null);
  const [sourceMode, setSourceMode] = useState(mode);
  const [fallbackUsed, setFallbackUsed] = useState(false);
  const [fallbackError, setFallbackError] = useState<JobBrowserError | null>(null);
  const active = useRef<AbortController | null>(null);
  const url = mode === 'api' ? publicReadUrl(apiBase, '/jobs/observation') || '' : observationUrl;
  async function refresh() {
    active.current?.abort(); const controller = new AbortController(); active.current = controller; setLoading(true);
    const timeout = window.setTimeout(() => controller.abort(), 8000);
    const result = preferLive
      ? await loadLiveWithRecordedFallback<JobObservationRecord, JobBrowserError>({
          liveUrl: url, recordedUrl: observationUrl, previousLive: previousLive.current,
          previousRecorded: previousRecorded.current, signal: controller.signal,
          invalidLiveError: 'INVALID_RECORD', acceptLive: value => value.environment === 'MINI_PC',
          load: (target, previousRecord, signal) => loadJobObservation({ url: target, previousRecord, signal, rejectRedirects: true }),
        })
      : { ...(await loadJobObservation({ url, previousRecord: previous.current, signal: controller.signal })),
          sourceMode: mode, fallbackUsed: false, fallbackBrowserError: null, lastLive: null, lastRecorded: null };
    window.clearTimeout(timeout); if (active.current !== controller) return;
    previous.current = result.record; previousLive.current = result.lastLive; previousRecorded.current = result.lastRecorded;
    setSourceMode(result.sourceMode); setFallbackUsed(result.fallbackUsed); setFallbackError(result.fallbackBrowserError);
    setRecord(result.record); setError(result.browserError); setRetained(result.retainedPrevious); setNow(Date.now()); setLoading(false);
  }
  useEffect(() => {
    previous.current = null; previousLive.current = null; previousRecorded.current = null; setSourceMode(mode); setFallbackUsed(false); setFallbackError(null); setRecord(null); setJobFilters({ ...DEFAULT_JOB_FILTERS }); void refresh();
    const clock = window.setInterval(() => setNow(Date.now()), 1_000);
    const poll = mode === 'api' ? window.setInterval(() => void refresh(), 10_000) : null;
    return () => { active.current?.abort(); active.current = null; window.clearInterval(clock); if (poll !== null) window.clearInterval(poll); };
  }, [url, mode, preferLive, observationUrl]);
  const view = jobObservationView(record, now);
  const runtime = record?.runtime;
  return <section id="job-observation" className="section job-observation-section" aria-labelledby="job-observation-title">
    <div className="section-heading job-observation-heading"><div><span className="eyebrow">JOBS / PROCESS → VERIFY → RELEASE</span><h2 id="job-observation-title">작업 처리부터 파일 확인까지.</h2><p>원본 준비 → Kafka 발행·수신 → DB 처리 → 두 파일 저장 확인 → 슬롯 해제 순서를 관측합니다.</p></div><button className="button button-small" type="button" disabled={loading} onClick={() => void refresh()}>{loading ? '관측 읽는 중' : '작업 기록 다시 읽기'} <span aria-hidden="true">↻</span></button></div>
    <div className="job-observation-meta"><span className="tag">{sourceMode === 'recorded' ? '기록된 DB 관측 · 실시간 아님' : '읽기 API · 10초마다 조회'}</span>{record && <span className="tag">{environmentNames[record.environment]}</span>}{record && <p>마지막 DB 확인 <time dateTime={record.capturedAt}>{time(record.capturedAt)}</time></p>}</div>
    {fallbackUsed && <p className="job-observation-notice" role="status">실시간 API를 읽지 못해 {record ? '게시된 마지막 기록을 표시합니다. 원래 소스와 수집 시각을 유지합니다.' : '게시본도 아직 확인하지 못했습니다.'}{fallbackError ? ' 새 게시본 조회에도 문제가 있어 이전 유효 게시본이 있으면 유지합니다.' : ''}</p>}
    {error && <p className="job-observation-notice" role="status">{errorNames[error]}{retained ? ' 기존 필드와 확인 시각을 보존합니다.' : ' 미관측 항목을 성공으로 채우지 않습니다.'}</p>}
    {view.freshness === 'stale' && <p className="job-observation-notice" role="status">오래된 DB 기록 · 확인 후 2시간이 지났습니다. 아래 값은 현재 운영 상태를 뜻하지 않습니다.</p>}
    {view.freshness === 'clock-check' && <p className="job-observation-notice" role="status">기록과 브라우저의 시각 확인이 필요합니다. 최신 상태로 판단하지 않습니다.</p>}
    {record && runtime ? <>
      {record.scope === 'ISOLATED_LAB' && <p className="job-observation-scope">별도 Kafka·MariaDB·Garage에서 실행한 개인 합성 데이터 검증입니다. 운영 서비스에 상시 실행기를 배포한 결과와 구분합니다.</p>}
      <div className="job-runtime-grid">
        <article className="job-runtime-card"><span className="code-label">RUNTIME / LAST DB SIGNAL</span><h3>{runtimeNames[runtime.status]}</h3><p className="job-runtime-stage">마지막 단계: {stageNames[runtime.stage]}</p>
          {runtime.failureCode && <p className="job-observation-notice">고정 오류 코드 <code>{runtime.failureCode}</code><br/>원인 확인 후 명시적으로 재개합니다. 브라우저에는 재개 권한이 없습니다.</p>}
          <dl className="job-observation-details"><div><dt>heartbeat 기록</dt><dd>{time(runtime.heartbeatAt)}</dd></div><div><dt>실행 시작 / 종료·정지 기록</dt><dd>{time(runtime.startedAt)}<br/>{time(runtime.stoppedAt)}</dd></div><Source label="실행기 소스 SHA" sha={runtime.sourceCommit}/></dl>
          {view.heartbeat === 'stale-signal' && <p className="job-observation-notice">heartbeat 기록 후 5분 초과 · DB에 RUNNING이 남아 있어도 현재 프로세스 생존을 확인한 것은 아닙니다.</p>}
          {view.heartbeat === 'clock-check' && <p className="job-observation-notice">heartbeat·DB 확인·브라우저 시각의 순서를 확인해야 합니다.</p>}
          {view.heartbeat === 'recent-signal' && <p className="job-observation-note">최근 5분 이내 DB 신호입니다. 현재 프로세스 생존이나 Kafka·저장소 가용성을 직접 확인하지 않습니다.</p>}
        </article>
        <article className="job-runtime-card"><span className="code-label">ADMISSION / SINGLE SLOT</span><h3>{record.slot.occupiedRunId ? '실행 슬롯 점유 기록' : '실행 슬롯 비어 있음'}</h3><p>{record.slot.occupiedRunId ? <code>{record.slot.occupiedRunId}</code> : '마지막 DB snapshot에서 점유 작업이 없습니다.'}</p><p className="job-observation-note">DB 처리 완료만으로 슬롯을 해제하지 않습니다. 결과·실패 두 파일의 전체 내용·크기·SHA-256 검증 후 export 확인을 DB에 commit합니다. 운영자의 명시적 종료는 별도 경로입니다.</p><dl className="job-observation-details"><Source label="관측 API 소스 SHA" sha={record.sourceCommit}/></dl></article>
      </div>
      <JobObservationList jobs={record.jobs} context={record} basePath={basePath} filters={jobFilters} onFiltersChange={setJobFilters} disabled={loading} />
    </> : !loading && <div className="job-observation-empty"><h3>작업 관측 미연결 · NOT_CONFIGURED</h3><p>실제 DB 기록이 연결되면 실행기·슬롯·작업·export 정보를 표시합니다. 확인되지 않은 파일·시간·성공 상태를 대신 넣지 않습니다.</p></div>}
    <p className="job-observation-note">파일 원문·저장소 경로·호스트·자격증명은 공개하지 않습니다. <a href={`${repository}/blob/main/apps/lab-web/JOB_OBSERVATION.md`} target="_blank" rel="noreferrer">관측 범위와 한계 ↗</a></p>
  </section>;
}
