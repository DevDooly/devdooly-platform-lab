import type { JobFile, JobObservation } from '../lib/job-observation';
import { DEFAULT_JOB_FILTERS, filterObservedJobs } from '../lib/job-list';
import type { JobListFilters } from '../lib/job-list';
import JobLifecycle from './JobLifecycle';
import '../styles/job-list.css';

const jobNames = { STAGING: '원본 준비', QUEUED: '처리 대기', COMPLETED: 'DB 처리 완료', TERMINATED: '명시적 종료' };
const exportNames = { NOT_REQUESTED: 'export 요청 전', PENDING: 'export 대기 · 슬롯 유지', EXPORTED: '저장 확인 기록 · 슬롯 해제', CANCELLED: 'export 취소' };
const exportFilterNames = { NOT_REQUESTED: '요청 전', PENDING: '대기', EXPORTED: '저장 확인', CANCELLED: '취소' };

function FileEvidence({ label, file }: { label: string; file: JobFile }) {
  return <div className="job-file"><h4>{label}</h4><p>{file.size.toLocaleString('ko-KR')} bytes</p><details><summary>예상 파일 SHA-256</summary><code>{file.sha256}</code></details></div>;
}

export default function JobObservationList({ jobs, filters, onFiltersChange, disabled }: {
  jobs: readonly JobObservation[];
  filters: JobListFilters;
  onFiltersChange: (value: JobListFilters) => void;
  disabled: boolean;
}) {
  const matching = filterObservedJobs(jobs, filters);
  return <>
    <div className="job-list-heading"><h3>최근 작업 · 최대 20개</h3><p>작업 상태와 export 상태를 구분합니다.</p></div>
    <div className="job-list-controls" role="group" aria-label="작업 목록 조건">
      <label className="job-list-query"><span>작업 ID 검색</span><input type="search" value={filters.query} disabled={disabled} placeholder="작업 ID의 일부 입력" onChange={event => onFiltersChange({ ...filters, query: event.currentTarget.value })}/></label>
      <label><span>작업 상태</span><select value={filters.status} disabled={disabled} onChange={event => onFiltersChange({ ...filters, status: event.currentTarget.value as JobListFilters['status'] })}>
        <option value="ALL">전체 작업 상태</option>
        {(Object.entries(jobNames) as [JobObservation['status'], string][]).map(([value, label]) => <option key={value} value={value}>{label} · {value}</option>)}
      </select></label>
      <label><span>export 상태</span><select value={filters.exportStatus} disabled={disabled} onChange={event => onFiltersChange({ ...filters, exportStatus: event.currentTarget.value as JobListFilters['exportStatus'] })}>
        <option value="ALL">전체 export 상태</option>
        {(Object.entries(exportFilterNames) as [JobObservation['exportStatus'], string][]).map(([value, label]) => <option key={value} value={value}>{label} · {value}</option>)}
      </select></label>
      <button className="job-list-reset" type="button" disabled={disabled} onClick={() => onFiltersChange({ ...DEFAULT_JOB_FILTERS })}>조건 초기화</button>
    </div>
    <p className="job-list-filter-note">ID의 문자 일부를 검색하며 앞뒤 공백과 영문 대소문자를 구분하지 않습니다. 검색과 두 상태 조건을 모두 적용합니다.</p>
    <p className="job-list-count" role="status" aria-live="polite" aria-atomic="true">{`조회 목록 ${jobs.length}개 중 조건 일치 ${matching.length}개`}</p>
    <p className="job-list-filter-note">현재 읽은 최대 20개 작업에만 적용하며, 전체 DB 작업 수를 뜻하지 않습니다. runtime·슬롯·관측 출처와 시각은 목록 조건으로 바뀌지 않습니다.</p>
    <div className="job-list">{matching.map(job => <article className="job-record" key={job.runId}><div className="job-record-heading"><h3><code>{job.runId}</code></h3><div className="job-record-states"><span>{jobNames[job.status]}</span><span className={job.exportStatus === 'PENDING' ? 'job-pending' : ''}>{exportNames[job.exportStatus]}</span></div></div>
      {job.counts && <dl className="job-counts">{([['전체', job.counts.input], ['성공', job.counts.success], ['실패', job.counts.failure], ['중복', job.counts.duplicate], ['대기', job.counts.pending]] as const).map(([label, count]) => <div key={label}><dt>{label}</dt><dd>{count}</dd></div>)}</dl>}
      <JobLifecycle job={job} />
      {job.files && <><p className="job-file-evidence">{job.fileEvidence === 'VERIFIED_AT_EXPORT_COMMIT' ? '두 파일의 저장 확인을 기록한 DB 시각이 있습니다.' : '아래는 DB 결과로 만든 예상 파일 정보입니다. 저장 확인은 아직 기록되지 않았습니다.'} SHA-256과 크기는 결정적인 DB snapshot에서 다시 계산한 값이며, 현재 저장소를 재조회한 결과가 아닙니다.</p><div className="job-files"><FileEvidence label="전체 처리 결과 JSON" file={job.files.result}/><FileEvidence label="실패 입력 JSON" file={job.files.failures}/></div></>}
    </article>)}</div>
    {jobs.length === 0 ? <div className="job-observation-empty"><h3>아직 기록된 작업이 없습니다.</h3><p>고정 예제 실행 결과와 새 worker 작업 기록은 별도입니다. 공개 페이지에서는 작업을 생성하지 않습니다.</p></div>
      : matching.length === 0 && <div className="job-observation-empty"><h3>조건에 일치하는 작업이 없습니다.</h3><p>조회된 작업은 남아 있습니다. 검색어나 상태 조건을 바꾸거나 조건 초기화로 조회 목록을 다시 볼 수 있습니다.</p></div>}
  </>;
}
