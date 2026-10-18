import { useEffect, useRef, useState } from 'react';
import { kafkaObservationView, kafkaUtcNs, loadKafkaObservation } from '../lib/kafka-observation';
import type { KafkaBrowserError, KafkaObservation } from '../lib/kafka-observation';
import '../styles/kafka-observation.css';
import { publicReadUrl } from '../lib/public-api-base';
import { loadLiveWithRecordedFallback } from '../lib/public-observation-source';

const repository = 'https://github.com/DevDooly/devdooly-platform-lab';
const errorNames: Record<KafkaBrowserError, string> = {
  NOT_CONFIGURED: 'Kafka 관측 연결 또는 게시 기록이 아직 없습니다.', INVALID_CONFIGURATION: '관측 대상 설정을 확인하지 못했습니다.',
  CAPTURE_BUSY: '다른 관측 요청이 진행 중입니다.', OBSERVER_POISONED: '관측 실행기의 정리 상태 확인이 필요합니다.',
  CAPTURE_TIMEOUT: '관측 제한 시간 안에 새 기록을 확인하지 못했습니다.', KAFKA_UNAVAILABLE: 'Kafka의 새 관측을 확인하지 못했습니다.',
  TARGET_UNVERIFIED: '설정된 관측 대상의 identity를 확인하지 못했습니다.', GROUP_UNAVAILABLE: '대상 그룹을 확인하지 못했습니다.',
  GROUP_UNSTABLE: '그룹 상태가 관측 조건을 충족하지 않았습니다.', OFFSETS_UNVERIFIED: '오프셋 관계를 확인하지 못했습니다.',
  CLOCK_UNVERIFIED: '관측 시각을 확인하지 못했습니다.', CLOSE_UNVERIFIED: '관측 클라이언트의 종료 경계를 확인하지 못했습니다.',
  HTTP_ERROR: '새 Kafka 기록을 조회하지 못했습니다.', NETWORK_ERROR: '브라우저 연결 문제로 새 기록을 읽지 못했습니다.',
  INVALID_RECORD: '공개 계약을 확인할 수 없어 새 기록을 표시하지 않았습니다.', ABORTED: '기록 조회가 중단되거나 제한 시간을 넘었습니다.',
  OLDER_RECORD: '이전보다 오래된 기록이므로 마지막 유효 기록을 유지합니다.', TARGET_CHANGED: '대상 지문이 바뀌어 기존 기록과 합치지 않습니다.',
  CONFLICTING_RECORD: '같은 수집 시각에 다른 값이 있어 마지막 유효 기록을 유지합니다.',
  ENVIRONMENT_MISMATCH: '격리 시험 기록을 배포 환경의 공개 기록으로 표시하지 않습니다.', INVALID_URL: '고정 관측 경로를 확인할 수 없습니다.',
};
const count = (value: number | null) => value === null ? '미관측' : value.toLocaleString('ko-KR');

export function KafkaObservationReadout({ record, nowMs, error, retained }: { record: KafkaObservation | null; nowMs: number;
  error: KafkaBrowserError | null; retained: boolean }) {
  const view = kafkaObservationView(record, nowMs);
  return <>
    {error && <p className="kafka-observation-notice" role="status">{errorNames[error]}{retained ? ' 현재 화면에 읽어둔 값과 원래 수집 시각을 보존합니다.' : ' 미관측 값을 0 또는 성공으로 채우지 않습니다.'}</p>}
    {view === 'stale' && <p className="kafka-observation-notice" role="status">오래된 Kafka 기록 · 확인 후 2시간이 지났습니다. 현재 lag나 가용성을 뜻하지 않습니다.</p>}
    {view === 'clock-check' && <p className="kafka-observation-notice" role="status">기록과 브라우저 시각을 확인해야 합니다. 최신 상태로 판단하지 않습니다.</p>}
    {record ? <>
      <div className="kafka-observation-meta"><span className="tag">{record.environment === 'MINI_PC' ? '배포 Kafka의 마지막 기록' : '격리 Lab 시험 기록'}</span><span className="tag">그룹 {record.groupState} · partition {record.partition}</span></div>
      <div className="kafka-offset-grid">
        <article><span className="code-label">COMMITTED / OBSERVED OFFSET</span><h3>{record.commitState === 'OBSERVED' ? 'Commit 관측' : 'Commit 미관측'}</h3><p className="kafka-offset-value">{count(record.committedOffset)}</p><p>{record.commitState === 'NO_COMMIT' ? '대상 partition의 commit이 없습니다. offset 0으로 바꾸지 않습니다.' : '마지막 bounded read에서 확인한 committed offset입니다.'}</p></article>
        <article><span className="code-label">READ_COMMITTED / LSO − COMMIT</span><h3>관측 lag</h3><p className="kafka-offset-value">{count(record.lag)}</p><p>{record.lag === null ? 'Commit 미관측이므로 lag도 미관측입니다.' : 'READ_COMMITTED LSO와 committed offset의 차이입니다. 실제 0을 미관측과 구분합니다.'}</p></article>
      </div>
      <dl className="kafka-observation-details"><div><dt>Log start offset</dt><dd>{count(record.logStartOffset)}</dd></div><div><dt>READ_COMMITTED latest · LSO</dt><dd>{count(record.readCommittedEndOffset)}</dd></div><div><dt>수집 시작</dt><dd><time dateTime={record.captureStartedAt}>{record.captureStartedAt}</time></dd></div><div><dt>수집 완료</dt><dd><time dateTime={record.capturedAt}>{record.capturedAt}</time></dd></div><div><dt>순차 조회 구간</dt><dd>{Number(kafkaUtcNs(record.capturedAt)! - kafkaUtcNs(record.captureStartedAt)!) / 1_000_000_000}초 · 최대 4초</dd></div><div><dt>관측 API source SHA</dt><dd><a href={`${repository}/commit/${record.sourceCommit}`} target="_blank" rel="noreferrer"><code>{record.sourceCommit}</code><span className="sr-only"> GitHub 소스 커밋, 새 창</span> ↗</a></dd></div></dl>
      <details className="kafka-observation-fingerprint"><summary>관측 대상 지문 확인</summary><code>{record.targetFingerprint}</code><p>같은 대상의 기록인지 비교하는 SHA-256입니다. raw cluster·topic·group identity를 공개하지 않으며 서명·인증을 증명하지 않습니다. 지문이 바뀌면 같은 시계열로 자동 병합하지 않습니다.</p></details>
    </> : <div className="kafka-observation-empty"><h3>Kafka 관측 미연결</h3><p>실제 계약을 통과한 기록이 연결되면 그룹·commit·LSO·lag와 수집 시각을 표시합니다. 기본 성공 예제나 미확인 0 lag는 넣지 않습니다.</p></div>}
  </>;
}

export default function KafkaObservationCard({ apiBase = '/api', observationUrl, mode, preferLive = false }: { apiBase?: string; observationUrl: string; mode: 'api' | 'recorded'; preferLive?: boolean }) {
  const [record, setRecord] = useState<KafkaObservation | null>(null);
  const [error, setError] = useState<KafkaBrowserError | null>(null);
  const [retained, setRetained] = useState(false); const [loading, setLoading] = useState(true); const [now, setNow] = useState(0);
  const previous = useRef<KafkaObservation | null>(null); const active = useRef<AbortController | null>(null);
  const previousLive = useRef<KafkaObservation | null>(null); const previousRecorded = useRef<KafkaObservation | null>(null);
  const [sourceMode, setSourceMode] = useState(mode); const [fallbackUsed, setFallbackUsed] = useState(false);
  const [fallbackError, setFallbackError] = useState<KafkaBrowserError | null>(null);
  const url = mode === 'api' ? publicReadUrl(apiBase, '/kafka/observation') || '' : observationUrl;
  async function refresh() {
    active.current?.abort(); const controller = new AbortController(); active.current = controller; setLoading(true);
    const timeout = window.setTimeout(() => controller.abort(), 8000);
    const result = preferLive
      ? await loadLiveWithRecordedFallback<KafkaObservation, KafkaBrowserError>({
          liveUrl: url, recordedUrl: observationUrl, previousLive: previousLive.current,
          previousRecorded: previousRecorded.current, signal: controller.signal, invalidLiveError: 'INVALID_RECORD',
          load: (target, previousRecord, signal, source) => loadKafkaObservation({ url: target, previousRecord, signal,
            allowIsolated: false, apiBase: source === 'api' ? apiBase : undefined, rejectRedirects: true }),
        })
      : { ...(await loadKafkaObservation({ url, previousRecord: previous.current, signal: controller.signal, allowIsolated: mode === 'api' })),
          sourceMode: mode, fallbackUsed: false, fallbackBrowserError: null, lastLive: null, lastRecorded: null };
    window.clearTimeout(timeout); if (active.current !== controller) return;
    previous.current = result.record; previousLive.current = result.lastLive; previousRecorded.current = result.lastRecorded;
    setSourceMode(result.sourceMode); setFallbackUsed(result.fallbackUsed); setFallbackError(result.fallbackBrowserError);
    setRecord(result.record); setError(result.browserError); setRetained(result.retainedPrevious); setNow(Date.now()); setLoading(false);
  }
  useEffect(() => {
    previous.current = null; previousLive.current = null; previousRecorded.current = null; setSourceMode(mode); setFallbackUsed(false); setFallbackError(null); setRecord(null); setError(null); setRetained(false); void refresh();
    const clock = window.setInterval(() => setNow(Date.now()), 1_000);
    return () => { active.current?.abort(); active.current = null; window.clearInterval(clock); };
  }, [url, mode, preferLive, observationUrl]);
  return <section id="kafka-observation" className="section kafka-observation-section" aria-labelledby="kafka-observation-title">
    <div className="section-heading kafka-observation-heading"><div><span className="eyebrow">KAFKA / BOUNDED READ</span><h2 id="kafka-observation-title">Commit과 lag, 확인한 구간만.</h2><p>설정된 대상 partition을 순차 조회한 마지막 기록입니다. 작업 상태의 DB 관측과 구분합니다.</p></div><button className="button button-small" type="button" disabled={loading} onClick={() => void refresh()}>{loading ? 'Kafka 기록 읽는 중' : 'Kafka 기록 다시 읽기'} <span aria-hidden="true">↻</span></button></div>
    <p className="kafka-observation-note">{sourceMode === 'recorded' ? '공개 파일의 마지막 수집 기록이며 실시간 조회가 아닙니다.' : '고정 읽기 API를 조회합니다. 대상 설정을 브라우저에서 받지 않습니다.'}</p>
    {fallbackUsed && <p className="kafka-observation-notice" role="status">실시간 API를 읽지 못해 {record ? '게시된 마지막 기록을 표시합니다. 원래 소스와 수집 시각을 유지합니다.' : '게시본도 아직 확인하지 못했습니다.'}{fallbackError ? ' 새 게시본 조회에도 문제가 있어 이전 유효 게시본이 있으면 유지합니다.' : ''}</p>}
    <KafkaObservationReadout record={record} nowMs={now} error={error} retained={retained}/>
    <p className="kafka-observation-note">BOUNDED_SEQUENTIAL_READ는 최대 4초 구간의 순차 조회이며 broker·DB의 원자 snapshot이 아닙니다. LSO는 비격리 log-end와 다릅니다. 그룹 상태·API source는 현재 worker 생존이나 소스를 확인하지 않습니다. 읽기 코드만으로 Kafka ACL을 검증했다고 주장하지 않습니다.</p>
  </section>;
}
