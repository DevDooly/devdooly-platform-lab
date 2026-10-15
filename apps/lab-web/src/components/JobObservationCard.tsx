import { useEffect, useRef, useState } from 'react';
import { jobObservationView, loadJobObservation } from '../lib/job-observation';
import type { JobBrowserError, JobFile, JobObservationRecord } from '../lib/job-observation';
import '../styles/job-observation.css';

const repository = 'https://github.com/DevDooly/devdooly-platform-lab';
const runtimeNames = { NOT_STARTED: '실행 기록 없음', RUNNING: '마지막 DB 신호: 실행 중', PAUSED_OPERATOR: '운영자 확인 대기 · 자동 재시작 차단', STOPPED: '종료 기록' };
const stageNames = { IDLE: '작업 대기', PUBLISH: 'Kafka 발행', CONSUME: '수신·DB 처리', EXPORT: '결과·실패 파일 저장 확인', STOPPED: '종료' };
const jobNames = { STAGING: '원본 준비', QUEUED: '처리 대기', COMPLETED: 'DB 처리 완료', TERMINATED: '명시적 종료' };
const exportNames = { NOT_REQUESTED: 'export 요청 전', PENDING: 'export 대기 · 슬롯 유지', EXPORTED: '저장 확인 기록 · 슬롯 해제', CANCELLED: 'export 취소' };
const environmentNames = { LOCAL: '로컬 검증', TEST: '자동 시험', ISOLATED_LAB: '격리 Lab 시험', MINI_PC: '배포 런타임', UNKNOWN: '환경 미분류' };
const errorNames: Record<JobBrowserError, string> = {
  NOT_CONFIGURED: '작업 관측 연결 또는 게시 기록이 아직 없습니다.', HTTP_ERROR: '새 작업 관측을 조회하지 못했습니다.',
  NETWORK_ERROR: '브라우저 연결 문제로 새 기록을 읽지 못했습니다.', INVALID_RECORD: '공개 형식을 확인할 수 없어 새 기록을 표시하지 않았습니다.',
  ABORTED: '기록 조회가 중단되거나 제한 시간을 넘었습니다.', OLDER_RECORD: '수집 시각이 이전 기록보다 오래되어 마지막 유효 기록을 유지합니다.',
};
function time(value: string | null) {
  return value ? `${new Intl.DateTimeFormat('ko-KR', { timeZone: 'UTC', year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', second: '2-digit', hourCycle: 'h23' }).format(new Date(value))} UTC` : '미기록';
}
function Source({ label, sha }: { label: string; sha: string }) {
  return <div><dt>{label}</dt><dd>{sha === 'unknown' ? '소스 SHA 미기록' : <a href={`${repository}/commit/${sha}`} target="_blank" rel="noreferrer"><code>{sha}</code><span className="sr-only"> GitHub 소스 커밋, 새 창</span> ↗</a>}</dd></div>;
}
function FileEvidence({ label, file }: { label: string; file: JobFile }) {
  return <div className="job-file"><h4>{label}</h4><p>{file.size.toLocaleString('ko-KR')} bytes</p><details><summary>예상 파일 SHA-256</summary><code>{file.sha256}</code></details></div>;
}

export default function JobObservationCard({ apiBase, observationUrl, mode }: { apiBase: string; observationUrl: string; mode: 'api' | 'recorded' }) {
  const [record, setRecord] = useState<JobObservationRecord | null>(null);
  const [error, setError] = useState<JobBrowserError | null>(null);
  const [retained, setRetained] = useState(false);
  const [loading, setLoading] = useState(true);
  const [now, setNow] = useState(0);
  const previous = useRef<JobObservationRecord | null>(null);
  const active = useRef<AbortController | null>(null);
  const url = mode === 'api' ? `${apiBase.replace(/\/$/, '')}/jobs/observation` : observationUrl;
  async function refresh() {
    active.current?.abort(); const controller = new AbortController(); active.current = controller; setLoading(true);
    const timeout = window.setTimeout(() => controller.abort(), 8000);
    const result = await loadJobObservation({ url, previousRecord: previous.current, signal: controller.signal });
    window.clearTimeout(timeout); if (active.current !== controller) return;
    previous.current = result.record; setRecord(result.record); setError(result.browserError); setRetained(result.retainedPrevious); setNow(Date.now()); setLoading(false);
  }
  useEffect(() => {
    previous.current = null; setRecord(null); void refresh();
    const clock = window.setInterval(() => setNow(Date.now()), 30_000);
    const poll = mode === 'api' ? window.setInterval(() => void refresh(), 10_000) : null;
    return () => { active.current?.abort(); active.current = null; window.clearInterval(clock); if (poll !== null) window.clearInterval(poll); };
  }, [url, mode]);
  const view = jobObservationView(record, now);
  const runtime = record?.runtime;
  return <section id="job-observation" className="section job-observation-section" aria-labelledby="job-observation-title">
    <div className="section-heading job-observation-heading"><div><span className="eyebrow">JOBS / PROCESS → VERIFY → RELEASE</span><h2 id="job-observation-title">작업 처리부터 파일 확인까지.</h2><p>원본 준비 → Kafka 발행·수신 → DB 처리 → 두 파일 저장 확인 → 슬롯 해제 순서를 관측합니다.</p></div><button className="button button-small" type="button" disabled={loading} onClick={() => void refresh()}>{loading ? '관측 읽는 중' : '작업 기록 다시 읽기'} <span aria-hidden="true">↻</span></button></div>
    <div className="job-observation-meta"><span className="tag">{mode === 'recorded' ? '기록된 DB 관측 · 실시간 아님' : '읽기 API · 10초마다 조회'}</span>{record && <span className="tag">{environmentNames[record.environment]}</span>}{record && <p>마지막 DB 확인 <time dateTime={record.capturedAt}>{time(record.capturedAt)}</time></p>}</div>
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
          {view.heartbeat === 'clock-check' && <p className="job-observation-notice">heartbeat와 브라우저 시각을 확인해야 합니다.</p>}
          {view.heartbeat === 'recent-signal' && <p className="job-observation-note">최근 5분 이내 DB 신호입니다. 현재 프로세스 생존이나 Kafka·저장소 가용성을 직접 확인하지 않습니다.</p>}
        </article>
        <article className="job-runtime-card"><span className="code-label">ADMISSION / SINGLE SLOT</span><h3>{record.slot.occupiedRunId ? '실행 슬롯 점유 기록' : '실행 슬롯 비어 있음'}</h3><p>{record.slot.occupiedRunId ? <code>{record.slot.occupiedRunId}</code> : '마지막 DB snapshot에서 점유 작업이 없습니다.'}</p><p className="job-observation-note">DB 처리 완료만으로 슬롯을 해제하지 않습니다. 결과·실패 두 파일의 전체 내용·크기·SHA-256 검증 후 export 확인을 DB에 commit합니다. 운영자의 명시적 종료는 별도 경로입니다.</p><dl className="job-observation-details"><Source label="관측 API 소스 SHA" sha={record.sourceCommit}/></dl></article>
      </div>
      <div className="job-list-heading"><h3>최근 작업 · 최대 20개</h3><p>작업 상태와 export 상태를 구분합니다.</p></div>
      <div className="job-list">{record.jobs.map(job => <article className="job-record" key={job.runId}><div className="job-record-heading"><h3><code>{job.runId}</code></h3><div className="job-record-states"><span>{jobNames[job.status]}</span><span className={job.exportStatus === 'PENDING' ? 'job-pending' : ''}>{exportNames[job.exportStatus]}</span></div></div>
        {job.counts && <dl className="job-counts">{([['전체', job.counts.input], ['성공', job.counts.success], ['실패', job.counts.failure], ['중복', job.counts.duplicate], ['대기', job.counts.pending]] as const).map(([label, count]) => <div key={label}><dt>{label}</dt><dd>{count}</dd></div>)}</dl>}
        <dl className="job-observation-details job-times"><div><dt>작업 생성</dt><dd>{time(job.createdAt)}</dd></div><div><dt>DB 처리 완료</dt><dd>{time(job.completedAt)}</dd></div><div><dt>저장 확인 commit</dt><dd>{time(job.exportCompletedAt)}</dd></div>{job.terminatedAt && <div><dt>명시적 종료</dt><dd>{time(job.terminatedAt)}</dd></div>}</dl>
        {job.files && <><p className="job-file-evidence">{job.fileEvidence === 'VERIFIED_AT_EXPORT_COMMIT' ? '두 파일의 저장 확인을 기록한 DB 시각이 있습니다.' : '아래는 DB 결과로 만든 예상 파일 정보입니다. 저장 확인은 아직 기록되지 않았습니다.'} SHA-256과 크기는 결정적인 DB snapshot에서 다시 계산한 값이며, 현재 저장소를 재조회한 결과가 아닙니다.</p><div className="job-files"><FileEvidence label="전체 처리 결과 JSON" file={job.files.result}/><FileEvidence label="실패 입력 JSON" file={job.files.failures}/></div></>}
      </article>)}</div>
      {record.jobs.length === 0 && <div className="job-observation-empty"><h3>아직 기록된 작업이 없습니다.</h3><p>고정 예제 실행 결과와 새 worker 작업 기록은 별도입니다. 공개 페이지에서는 작업을 생성하지 않습니다.</p></div>}
    </> : !loading && <div className="job-observation-empty"><h3>작업 관측 미연결 · NOT_CONFIGURED</h3><p>실제 DB 기록이 연결되면 실행기·슬롯·작업·export 정보를 표시합니다. 확인되지 않은 파일·시간·성공 상태를 대신 넣지 않습니다.</p></div>}
    <p className="job-observation-note">파일 원문·저장소 경로·호스트·자격증명은 공개하지 않습니다. <a href={`${repository}/blob/main/apps/lab-web/JOB_OBSERVATION.md`} target="_blank" rel="noreferrer">관측 범위와 한계 ↗</a></p>
  </section>;
}
