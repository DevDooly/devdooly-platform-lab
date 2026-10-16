import { useEffect, useMemo, useState } from 'react';
import { parseCloudLakehouse, cloudLakehouseRun } from '../lib/cloud-lakehouse';
import '../styles/cloud-lakehouse.css';

const repo = 'https://github.com/DevDooly/devdooly-platform-lab';
const evidenceUrl = `${repo}/blob/main/docs/evidence/cloud-lakehouse/FULL_SUCCESS.md`;
const summaryUrl = `${repo}/blob/main/docs/evidence/cloud-lakehouse/full-success.summary.json`;

/** Historical static record only: no SQL, workload controls or service polling. */
export default function CloudLakehouseCard({ record, observationUrl }: { record?: unknown; observationUrl?: string }) {
  const [loaded, setLoaded] = useState<unknown>(record);
  useEffect(() => {
    if (record !== undefined || !observationUrl) { setLoaded(record); return; }
    let active = true;
    const controller = new AbortController();
    const timer = window.setTimeout(() => controller.abort(), 8000);
    async function load() {
      try {
        const target = new URL(observationUrl!, window.location.href);
        if (target.origin !== window.location.origin || target.username || target.password || target.search || target.hash
          || !target.pathname.endsWith('/observations/cloud-lakehouse.latest.json')) throw new Error('STATIC_ASSET_ONLY');
        const response = await fetch(target, { signal: controller.signal, redirect: 'error', credentials: 'omit' });
        if (!response.ok || !response.body) throw new Error('RECORD_UNAVAILABLE');
        const reader = response.body.getReader(); const chunks: Uint8Array[] = []; let size = 0;
        try {
          for (;;) {
            const next = await reader.read(); if (next.done) break;
            size += next.value.length; if (size > 16_384) throw new Error('RECORD_OVERSIZE'); chunks.push(next.value);
          }
        } finally { await reader.cancel(); }
        const bytes = new Uint8Array(size); let offset = 0;
        for (const chunk of chunks) { bytes.set(chunk, offset); offset += chunk.length; }
        const value: unknown = JSON.parse(new TextDecoder('utf-8', { fatal: true }).decode(bytes));
        if (active && !controller.signal.aborted) setLoaded(value);
      } catch { if (active) setLoaded(null); }
      finally { window.clearTimeout(timer); }
    }
    void load(); return () => { active = false; controller.abort(); window.clearTimeout(timer); };
  }, [record, observationUrl]);
  const evidence = useMemo(() => parseCloudLakehouse(loaded), [loaded]);
  return <section id="cloud-lakehouse" className="section cloud-lakehouse-section" aria-labelledby="cloud-lakehouse-title">
    <div className="section-heading cloud-lakehouse-heading"><div><span className="eyebrow">CLOUD / REWRITE → READ AGAIN</span>
      <h2 id="cloud-lakehouse-title">파일은 줄이고,<br/>조회 결과는 같게.</h2>
      <p>격리 Cloud에서 파일 재작성 전후의 행과 같은 warehouse의 Trino 조회 결과를 기록으로 확인합니다.</p></div>
      <span className="tag">GitHub 격리 Cloud · {evidence ? 'PASS 기록' : '기록 미확인'}</span></div>
    {evidence ? <>
      <p className="cloud-lakehouse-record-time">확인 시점의 기록 · <time dateTime={evidence.recordedAt}>{evidence.recordedAt}</time><br/>현재 서비스의 가용성을 표시하지 않습니다.</p>
      <dl className="cloud-lakehouse-metrics" aria-label="검증한 Cloud 결과">
        <div><dt>스냅샷 데이터 파일</dt><dd>{evidence.result.bronzeDataFilesBefore} → {evidence.result.bronzeDataFilesAfter}<small>개</small></dd></div>
        <div><dt>Trino 조회</dt><dd>{evidence.result.trinoQueryCount}<small>개 SELECT</small></dd></div>
        <div><dt>자기 자원 종료</dt><dd className="cloud-lakehouse-complete">정리 완료</dd></div>
      </dl>
      <div className="cloud-lakehouse-record">
        <table className="cloud-lakehouse-table"><caption>Compaction 전후, 행은 그대로 보존했습니다.</caption>
          <thead><tr><th scope="col">시점</th><th scope="col">원본 행</th><th scope="col">데이터 파일</th></tr></thead>
          <tbody><tr><th scope="row">합치기 전</th><td>{evidence.result.rows[1]}개</td><td>{evidence.result.bronzeDataFilesBefore}개</td></tr>
            <tr><th scope="row">합친 뒤</th><td>{evidence.result.rows[2]}개</td><td>{evidence.result.bronzeDataFilesAfter}개</td></tr></tbody>
        </table>
        <p>Spark의 compaction procedure를 {evidence.result.compactionProcedureCalls}회 호출했습니다. 두 append와 파일 재작성 뒤의 {evidence.result.rows.join(' → ')}행을 Trino에서도 읽고, 행 hash와 Silver 결과를 대조했습니다.</p>
        <p>Silver는 성공 {evidence.result.silverCounts.success}·실패 {evidence.result.silverCounts.failure}·중복 {evidence.result.silverCounts.duplicate}건이며 미처리는 {evidence.result.silverCounts.pending}건입니다.</p>
        <details className="cloud-lakehouse-details"><summary>스냅샷·정상 종료·검증 범위 보기</summary>
          <ol className="cloud-lakehouse-snapshots" aria-label="기록된 Cloud 스냅샷 순서">
            {evidence.result.snapshotIds.map((id, index) => <li key={id}><strong>{index < 2 ? `추가 ${index + 1}` : '파일 재작성'} · {evidence.result.rows[index]}행</strong>
              <span>{evidence.result.snapshotOperations[index]}</span><code>{id}</code></li>)}
          </ol>
          <p>부모 연결로 확인한 append → append → replace 기록입니다. 미니 PC native7의 초기 빈 스냅샷을 포함한 0 → 6 → 12와는 별도 실험입니다.</p>
          <dl>
            <div><dt>정상 종료·정리</dt><dd>Spark 정상 종료 · Trino TERM 요청 반환과 exit {evidence.stop.trinoExitCode}·nonOOM 확인 · 자기 시험 컨테이너와 initializer 종료</dd></div>
            <div><dt>보관 객체·catalog</dt><dd>기존 warehouse 객체 {evidence.result.preservedOldWarehouseObjects}개 bytes 보존 · Trino 조회 후 {evidence.result.postTrinoWarehouseObjects}개 전체 검사 · JDBC pointer 유지</dd></div>
            <div><dt>시험 시계</dt><dd>{(evidence.limits.workloadElapsedMillis / 1000).toFixed(3)}초 · 제한 {evidence.limits.workloadBudgetSeconds}초 · build/pull은 제외하며, CI 전체 시간이나 처리량 측정값이 아닙니다.</dd></div>
            <div><dt>설정한 자원 한도</dt><dd>Spark CPU 1·3GiB·PID 512 · Trino 4GiB · 순차 실행 합계 계획 상한 5GiB · 시작 전 MemAvailable 7GiB gate. 실제 peak 사용량은 측정하지 않았습니다.</dd></div>
            <div><dt>행 hash</dt><dd><code>{evidence.result.rowSha256}</code></dd></div>
            <div><dt>검증 실행 소스</dt><dd><code>{evidence.run.sourceCommit}</code></dd></div>
            <div><dt>원문 summary SHA-256</dt><dd><code>{evidence.artifact.sha256}</code></dd></div>
          </dl>
          <p>이 기록은 미니 PC 배포·Kubernetes·현재 가용성·운영 SLA·분산 동시 실행·crash recovery의 검증이 아닙니다. Snapshot expiration·객체 GC는 하지 않았고, TERM 신호의 직접 전달 여부는 관측하지 않았습니다. 앞선 실패 기록도 근거 문서에 보존합니다.</p>
        </details>
      </div>
      <div className="cloud-lakehouse-links"><a href={`${repo}/actions/runs/${cloudLakehouseRun}`} target="_blank" rel="noreferrer">실제 GitHub 실행 ↗</a>
        <a href={evidenceUrl} target="_blank" rel="noreferrer">성공 범위와 이전 실패 ↗</a><a href={summaryUrl} target="_blank" rel="noreferrer">원문 결과 요약 ↗</a></div>
    </> : <div className="cloud-lakehouse-unavailable" role="status"><h3>{loaded === undefined ? '검증 기록을 불러오고 있습니다.' : '검증 기록을 확인할 수 없습니다.'}</h3>
      <p>실패·부분 기록이나 종료 근거가 없는 기록에는 성공 수치를 표시하지 않습니다.</p><a href={evidenceUrl} target="_blank" rel="noreferrer">실행 근거와 실패 기록 ↗</a></div>}
  </section>;
}
