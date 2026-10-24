import type { JobObservation } from '../lib/job-observation';
import { jobLifecycle, formatJobLifecycleInterval } from '../lib/job-lifecycle';
import '../styles/job-lifecycle.css';

const stepLabels = {
  created: '작업 생성', 'verified-queued': '원본 검증·대기 등록',
  completed: 'DB 처리 완료', exported: '저장 확인 commit', terminated: '명시적 종료',
};
const rawTimes = [
  ['작업 생성', 'createdAt'], ['원본 검증', 'sourceVerifiedAt'], ['대기 등록', 'queuedAt'],
  ['DB 처리 완료', 'completedAt'], ['저장 확인 commit', 'exportCompletedAt'], ['명시적 종료', 'terminatedAt'],
] as const;
const utc = new Intl.DateTimeFormat('ko-KR', {
  timeZone: 'UTC', year: 'numeric', month: '2-digit', day: '2-digit',
  hour: '2-digit', minute: '2-digit', second: '2-digit', hourCycle: 'h23',
});

/** Only displays validated job DTO records; it does not determine runtime or storage health. */
export default function JobLifecycle({ job }: { job: JobObservation }) {
  const lifecycle = jobLifecycle(job);
  return <section className="job-lifecycle" aria-label="작업·export 기록 흐름">
    <h4>작업·export 기록 흐름</h4>
    <ol className="job-lifecycle-steps">
      {lifecycle.steps.map(step => <li key={step.id} data-stage={step.id} data-recorded={step.recorded}>
        <span className="job-lifecycle-step-label">{stepLabels[step.id]}</span>
        <span className="job-lifecycle-stage-state">{step.recorded ? '기록 있음' : '미기록'}</span>
        {step.at !== null && <time dateTime={step.at}>{utc.format(new Date(step.at))} UTC</time>}
      </li>)}
    </ol>
    {lifecycle.exportCancelled && <p className="job-lifecycle-terminal">export 취소 기록 · 저장 확인 commit은 미기록입니다.</p>}
    {job.status === 'TERMINATED' && <p className="job-lifecycle-terminal">명시적 종료 기록이며, 성공한 export 확인을 뜻하지 않습니다.</p>}
    {job.status === 'COMPLETED' && job.exportStatus === 'PENDING' && <p className="job-lifecycle-pending">DB 처리 완료는 기록됐지만 저장 확인 commit은 미기록입니다.</p>}
    <dl className="job-lifecycle-intervals">
      {lifecycle.intervals.map(interval => <div key={interval.id}>
        <dt>{interval.id === 'queued-completed'
          ? '처리 대기 등록 → DB 완료 기록 간격' : 'DB 완료 → 저장 확인 commit 기록 간격'}</dt>
        <dd>{formatJobLifecycleInterval(interval.nanoseconds)}</dd>
      </div>)}
    </dl>
    <p className="job-lifecycle-note">두 시각의 기록 간격입니다. 처리·대기 시간을 나누거나 Kafka·S3 지연을 측정한 값은 아닙니다.
      미기록으로 현재 대기·실행·실패를 판단하지 않습니다.</p>
    <details className="job-lifecycle-raw">
      <summary>원시 시각 6개 보기 · UTC</summary>
      <p>원본 검증·대기 등록은 같은 시각으로 기록됩니다. Kafka 발행 확인이나 처리 시작 시각은 아닙니다.
        위 시각은 초 단위 요약이며, 아래 원문과 기록 간격은 최대 나노초 정밀도를 보존합니다.</p>
      <dl>{rawTimes.map(([label, key]) => <div key={key}>
        <dt>{label} · <code>{key}</code></dt>
        <dd>{job[key] === null ? <>미기록 · <code>null</code></> : <code><time dateTime={job[key]}>{job[key]}</time></code>}</dd>
      </div>)}</dl>
    </details>
  </section>;
}
