import { useEffect, useRef, useState } from 'react';
import { loadPlatformObservation, platformObservationView } from '../lib/platform-observation';
import type { BrowserObservationError, PlatformObservationRecord } from '../lib/platform-observation';
import '../styles/platform-observation.css';

const repository = 'https://github.com/DevDooly/devdooly-platform-lab';
const browserMessages: Record<BrowserObservationError, string> = {
  NOT_PUBLISHED: '공개 플랫폼 관측 파일이 아직 게시되지 않았습니다.',
  HTTP_ERROR: '브라우저에서 게시된 파일을 읽지 못했습니다.',
  NETWORK_ERROR: '브라우저의 연결 문제로 게시된 파일을 읽지 못했습니다.',
  INVALID_RECORD: '파일의 공개 형식을 확인할 수 없어 새 내용을 표시하지 않았습니다.',
  ABORTED: '브라우저의 파일 조회가 중단되거나 제한 시간을 넘었습니다.',
};
const collectorMessages = {
  NONE: '', GITHUB_STATUS_UNAVAILABLE: 'GitHub 검증 기록 조회 실패', ARGO_UNAVAILABLE: 'Argo CD 관측 실패',
  WORKLOADS_UNAVAILABLE: '워크로드 관측 실패', AUTHENTICATION_FAILED: '수집 인증 실패',
  TIMEOUT: '수집 제한 시간 초과', INVALID_OBSERVATION: '수집 결과 형식 확인 실패', COLLECTION_FAILED: '수집 실패',
};
const jenkinsStates = { pending: '검증 진행 중', success: '검증 성공', failure: '검증 실패', error: '검증 중단' };
const workloadNames = { api: 'Spring Boot API', web: 'Astro 웹', database: 'MariaDB' };
function time(value: string) {
  return new Intl.DateTimeFormat('ko-KR', { timeZone: 'UTC', year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', second: '2-digit', hourCycle: 'h23' }).format(new Date(value));
}
function SourceCommit({ label, sha }: { label: string; sha: string }) {
  return <div className="platform-source"><dt>{label}</dt><dd><a href={`${repository}/commit/${sha}`} target="_blank" rel="noreferrer"><code>{sha}</code><span className="sr-only"> GitHub 커밋 보기, 새 창</span><span aria-hidden="true"> ↗</span></a></dd></div>;
}

export default function PlatformObservationCard({ observationUrl }: { observationUrl: string }) {
  const [record, setRecord] = useState<PlatformObservationRecord | null>(null);
  const [browserError, setBrowserError] = useState<BrowserObservationError | null>(null);
  const [retained, setRetained] = useState(false);
  const [loading, setLoading] = useState(true);
  const [now, setNow] = useState(0);
  const previous = useRef<PlatformObservationRecord | null>(null);
  const active = useRef<AbortController | null>(null);

  async function refresh() {
    active.current?.abort();
    const controller = new AbortController();
    active.current = controller;
    setLoading(true);
    const timeout = window.setTimeout(() => controller.abort(), 8000);
    const result = await loadPlatformObservation({ url: observationUrl, previousRecord: previous.current, signal: controller.signal });
    window.clearTimeout(timeout);
    // A superseded/unmounted request must not overwrite a newer result.
    if (active.current !== controller) return;
    previous.current = result.record;
    setRecord(result.record);
    setBrowserError(result.browserError);
    setRetained(result.retainedPrevious);
    setNow(Date.now());
    setLoading(false);
  }
  useEffect(() => {
    void refresh();
    const clock = window.setInterval(() => setNow(Date.now()), 60_000);
    return () => { active.current?.abort(); active.current = null; window.clearInterval(clock); };
  }, [observationUrl]);

  const view = platformObservationView(record, now);
  const success = record?.lastSuccess;
  const freshness = view.freshness === 'stale' ? '오래된 기록 · 2시간 초과'
    : view.freshness === 'clock-check' ? '기록과 브라우저 시각 확인 필요'
    : view.freshness === 'within-window' ? '최근 2시간 이내 수집 기록' : '성공 기록 없음';

  return <section id="platform-record" className="section platform-record-section" aria-labelledby="platform-record-title">
    <div className="section-heading platform-record-heading"><div><span className="eyebrow">OBSERVED / PUBLIC RECORD</span><h2 id="platform-record-title">배포 이후, 마지막으로 확인한 상태.</h2><p>미니 PC에서 수집한 공개 기록입니다. 실시간 상태와 구분해 읽습니다.</p></div><button type="button" className="button button-small" disabled={loading} onClick={() => void refresh()}>{loading ? '기록 읽는 중' : '게시된 기록 다시 읽기'}<span aria-hidden="true">↻</span></button></div>

    <div className="platform-record-meta" aria-live="polite" aria-atomic="true">
      <span className="tag">정적 관측 기록</span>
      {record && <span className={`tag ${view.freshness === 'stale' || view.freshness === 'clock-check' ? 'record-caution' : ''}`}>{freshness}</span>}
      {record && <p>마지막 수집 시도 <time dateTime={record.latestAttempt.attemptedAt}>{time(record.latestAttempt.attemptedAt)} UTC</time> · {view.collectorFailed ? '수집 실패' : '수집 완료'}</p>}
      {!record && !loading && <p>관측 파일이 준비되면 빌드·GitOps·워크로드 기록을 이곳에서 확인할 수 있습니다.</p>}
    </div>

    {browserError && <div className="platform-record-notice" role="status"><strong>브라우저 조회 안내</strong><p>{browserMessages[browserError]}{retained ? ' 이전에 읽은 유효 기록을 유지합니다.' : ''} 이 안내는 수집기의 성공·실패 상태와 별도입니다.</p></div>}
    {view.collectorFailed && record && <div className="platform-record-notice record-caution" role="status"><strong>수집 실패 · {collectorMessages[record.latestAttempt.errorCode]}</strong><p>{success ? '아래는 마지막으로 성공한 수집 기록입니다. 새 수집 실패를 배포 실패나 서비스 중단으로 단정하지 않습니다.' : '아직 성공한 수집 기록이 없습니다.'}</p></div>}
    {view.freshness === 'clock-check' && <p className="platform-record-notice">기록의 시각이 브라우저보다 앞섭니다. 시각을 확인하기 전까지 최신 상태로 판단하지 않습니다.</p>}

    {success && <>
      <div className="platform-capture"><span>마지막 성공 기록</span><time dateTime={success.capturedAt}>{time(success.capturedAt)} UTC</time><small>collector v{success.collectorVersion}</small></div>
      <div className="platform-record-grid">
        <article className="platform-record-card"><span className="code-label">01 / SOURCE VALIDATION</span><h3>수집 당시 main의 Jenkins</h3>
          {success.jenkins ? <><p className={`platform-state ${success.jenkins.state === 'failure' || success.jenkins.state === 'error' ? 'is-caution' : success.jenkins.state === 'pending' ? 'is-pending' : ''}`}>{jenkinsStates[success.jenkins.state]}<span>build #{success.jenkins.buildNumber}</span></p><p className="record-small">상태 생성 <time dateTime={success.jenkins.createdAt}>{time(success.jenkins.createdAt)} UTC</time></p></> : <p className="platform-state is-pending">해당 main의 검증 기록 미관측</p>}
          <dl><SourceCommit label="수집 당시 main SHA" sha={success.mainCommit}/>{success.jenkins && <SourceCommit label="Jenkins 검증 대상 SHA" sha={success.jenkins.sourceCommit}/>}</dl>
          <p className="record-small">{success.jenkins ? `GitHub 공개 commit status · ${success.jenkins.issuer} · status #${success.jenkins.statusId}` : '과거 빌드의 성공을 이 main의 성공으로 대신 표시하지 않습니다.'}</p>
        </article>
        <article className="platform-record-card"><span className="code-label">02 / GITOPS DECLARATION</span><h3>Argo CD가 관측한 선언</h3><p className={`platform-state ${success.argo.sync !== 'Synced' || success.argo.health !== 'Healthy' ? 'is-caution' : ''}`}>{success.argo.sync}<span>{success.argo.health}</span></p><dl><SourceCommit label="Argo GitOps revision" sha={success.argo.revision}/><SourceCommit label="API 배포 선언 소스 SHA" sha={success.deploymentSourceCommit}/></dl><p className="record-small">API Deployment template의 소스 annotation입니다. 실행 중인 JVM의 소스를 직접 조회한 값은 아닙니다.</p></article>
      </div>
      <div className="platform-workloads"><div className="workload-heading"><h3>수집 당시 워크로드</h3><span>Pod 준비 수 / 목표 수</span></div><div className="workload-grid">{(['api', 'web', 'database'] as const).map(component => {
        const item = success.workloads.find(workload => workload.component === component)!;
        return <article className="workload-record" key={component}><div><h4>{workloadNames[item.component]}</h4><p><strong>{item.ready}</strong><span> / {item.desired}</span><span className="sr-only"> Pod 준비 수 / 목표 수</span></p></div>{'image' in item ? <details><summary>선언 이미지 digest</summary><code>{item.image}</code></details> : <p className="record-small">실제 Pod의 준비 상태 관측</p>}</article>;
      })}</div></div>
      <p className="platform-record-footnote">준비 수는 삭제 중이 아니며 Running·Ready이고 모든 컨테이너가 준비된 실제 Pod의 개수입니다. 목표 수는 Deployment·StatefulSet 선언 값입니다. main, Jenkins 검증 대상, GitOps revision과 API 배포 선언은 서로 다른 근거이며 롤백 때의 차이도 그대로 표시합니다. 이미지 digest는 선언 값으로 실행 컨테이너의 imageID 검증과 구분합니다.</p>
    </>}
    {!success && <div className="platform-record-empty"><span aria-hidden="true">⌁</span><h3>확인한 기록만 채웁니다.</h3><p>실제 수집 기록이 없는 항목에 샘플 성공이나 현재 시각을 넣지 않습니다.</p></div>}
    <div className="platform-record-links"><p>다시 읽기는 게시된 파일을 조회합니다. 위 런타임 조회 API의 ‘관측 연결 전’ 표시는 별도 수집 연결 상태입니다.</p><a className="text-link" href={`${repository}/blob/main/apps/lab-web/PLATFORM_OBSERVATION.md`} target="_blank" rel="noreferrer">공개 기록의 범위와 형식 ↗</a></div>
  </section>;
}
