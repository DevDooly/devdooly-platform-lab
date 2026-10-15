import { useEffect, useMemo, useState } from 'react';
import { parseIcebergDataflow } from '../lib/iceberg-dataflow';
import '../styles/iceberg-dataflow.css';

const repo = 'https://github.com/DevDooly/devdooly-platform-lab';

/** Static record selection only: no browser SQL, credentials or execution endpoint. */
export default function IcebergDataflowCard({ record, observationUrl }: { record?: unknown; observationUrl?: string }) {
  const [loaded, setLoaded] = useState<unknown>(record);
  const [selected, setSelected] = useState<0 | 1>(1);
  useEffect(() => {
    if (record !== undefined || !observationUrl) { setLoaded(record); return; }
    const controller = new AbortController();
    const timer = window.setTimeout(() => controller.abort(), 8000);
    async function load() {
      try {
        const target = new URL(observationUrl!, window.location.href);
        if (target.origin !== window.location.origin || target.username || target.password || target.search || target.hash) throw new Error('STATIC_ASSET_ONLY');
        const response = await fetch(target, { signal: controller.signal, redirect: 'error', credentials: 'omit' });
        if (!response.ok || !response.body) throw new Error('RECORD_UNAVAILABLE');
        const reader = response.body.getReader(); const chunks: Uint8Array[] = []; let size = 0;
        try {
          for (;;) {
            const next = await reader.read(); if (next.done) break;
            size += next.value.length; if (size > 32_768) throw new Error('RECORD_OVERSIZE'); chunks.push(next.value);
          }
        } finally { await reader.cancel(); }
        const bytes = new Uint8Array(size); let offset = 0;
        for (const chunk of chunks) { bytes.set(chunk, offset); offset += chunk.length; }
        const value: unknown = JSON.parse(new TextDecoder('utf-8', { fatal: true }).decode(bytes));
        if (!controller.signal.aborted) setLoaded(value);
      } catch { if (!controller.signal.aborted) setLoaded(null); }
      finally { window.clearTimeout(timer); }
    }
    void load(); return () => { controller.abort(); window.clearTimeout(timer); };
  }, [record, observationUrl]);
  const evidence = useMemo(() => parseIcebergDataflow(loaded), [loaded]);
  const snapshot = evidence?.snapshots[selected];
  const query = snapshot ? `SELECT input_sequence, event_id, sensor_id, event_time_raw, sensor_value\nFROM iceberg.bronze.synthetic_events\nFOR VERSION AS OF ${snapshot.id}\nORDER BY input_sequence;` : null;
  return <section id="dataflow" className="section iceberg-flow-section" aria-labelledby="iceberg-flow-title">
    <div className="section-heading iceberg-flow-heading"><div><span className="eyebrow">06 / APPEND → SNAPSHOT → READ AGAIN</span>
      <h2 id="iceberg-flow-title">데이터가 쌓여도,<br/>이전 시점은 다시 읽을 수 있게.</h2>
      <p>같은 합성 입력을 6개씩 추가하고, Trino 재시작 뒤에도 Iceberg의 행과 스냅샷을 비교합니다.</p></div>
      <span className="tag">별도 데이터 플랫폼 실험 · 기록 조회</span></div>
    <p className="iceberg-flow-scope">Bronze는 원본 12개를 그대로 보관합니다. 중복 event ID와 잘못된 시각·범위 밖 값도 남기므로,
      기존 Java ETL의 성공 7·실패 3·중복 2와 집계 기준이 다릅니다. 회사 데이터는 사용하지 않습니다.</p>
    {evidence && snapshot ? <>
      <ol className="iceberg-flow-diagram" aria-label="실제 검증 기록의 데이터 흐름">
        <li><span>INPUT</span><strong>합성 원본 12개</strong><p>고정 1,100 bytes<br/>두 번의 append 입력</p></li>
        <li><span>ICEBERG / BRONZE</span><strong>6개 → 12개</strong><p>스냅샷 2개<br/>원본 순서·값 유지</p></li>
        <li><span>JDBC CATALOG</span><strong>같은 PostgreSQL</strong><p>영속 메타데이터<br/>동일 프로세스 유지</p></li>
        <li><span>TRINO</span><strong>새 프로세스로 재조회</strong><p>행·스냅샷·파일 동일<br/>시험 종료 후 workload 0</p></li>
      </ol>
      <div className="iceberg-flow-record"><div className="iceberg-flow-record-heading"><div><span className="code-label">RECORDED SNAPSHOTS</span><h3>읽을 시점 고르기</h3></div>
        <div className="iceberg-flow-controls" role="group" aria-label="기록된 스냅샷 선택">
          {evidence.snapshots.map((row, index) => <button type="button" key={row.id} aria-pressed={selected === index} onClick={() => setSelected(index as 0 | 1)}>S{index + 1} · {row.totalRows}개</button>)}
        </div></div>
        <p className="iceberg-flow-note">선택은 이미 검증한 정적 기록만 바꿉니다. 새 쿼리나 서버 작업을 실행하지 않습니다.</p>
        <dl className="iceberg-flow-counts" aria-live="polite"><div><dt>전체 원본 행</dt><dd>{snapshot.totalRows}<small>개</small></dd></div>
          <div><dt>서로 다른 event ID</dt><dd>{snapshot.distinctEventIds}<small>개</small></dd></div>
          <div><dt>센서 A / B 원본 행</dt><dd>{snapshot.sensorA} / {snapshot.sensorB}<small>개</small></dd></div></dl>
        <p>두 번째 스냅샷은 첫 번째를 부모로 가집니다. 이전 시점을 지정하면 6개, 최신 시점을 지정하면 12개를 읽는 결과를 확인한 기록입니다.</p>
        <details className="iceberg-flow-details"><summary>선택한 스냅샷의 조회 SQL 펼치기</summary><pre><code>{query}</code></pre>
          <p>실행 코드 발췌입니다. 공개 페이지에는 SQL 실행 기능·관리 접속 주소·인증 정보가 없습니다.</p></details>
        <details className="iceberg-flow-details"><summary>재시작·종료·원본 보존 근거 펼치기</summary><dl className="iceberg-flow-provenance">
          <div><dt>마지막 검증 종료 UTC · 실시간 상태와 구분</dt><dd><time dateTime={evidence.recordedAt}>{evidence.recordedAt}</time></dd></div>
          <div><dt>조회 엔진과 catalog</dt><dd>Trino {evidence.engines.trino} · 이미지 Java {evidence.engines.trinoJava} · PostgreSQL {evidence.engines.postgresql} · JDBC V1</dd></div>
          <div><dt>정상 재시작과 종료</dt><dd>Trino 정상 종료 관측 후 새 프로세스 · PostgreSQL 동일 프로세스 · 종료 후 시험 Pod 0 · Retain PVC 2개</dd></div>
          <div><dt>기존 애플리케이션 보존</dt><dd>8개 작업과 원본 객체 24개 전체 GET 대조 · 원본 객체 DELETE 0회</dd></div>
          <div><dt>첫 시도와 새 실행 창</dt><dd>첫 prepare 실패·시간 예산 만료는 보존합니다. 별도로 선언한 새 실행 창의 검증이며 첫 시도를 성공으로 바꾸지 않습니다.</dd></div>
          <div><dt>별도 애플리케이션 source / GitOps revision</dt><dd><code>{evidence.applicationSourceCommit}</code><br/><code>{evidence.gitopsRevision}</code></dd></div>
          <div><dt>합성 원본 SHA-256</dt><dd><code>{evidence.fixture.sha256}</code></dd></div>
          <div><dt>두 snapshot ID · 문자열로 보존</dt><dd><code>{evidence.snapshots[0].id}</code><br/><code>{evidence.snapshots[1].id}</code></dd></div>
          <div><dt>query / restart / stop / final 비공개 원본 SHA-256</dt><dd>{(['query', 'restart', 'stop', 'final'] as const).map(key => <span className="iceberg-flow-hash" key={key}>{key}: <code>{evidence.proofSha256[key]}</code></span>)}</dd></div>
        </dl><p>애플리케이션 source는 원본 보존 대상의 식별자입니다. Trino 이미지의 소스 커밋을 뜻하지 않습니다. Spark·Silver·compaction·Airflow는 이 검증에 포함하지 않습니다.</p></details>
      </div>
      <div className="iceberg-flow-links"><a href={`${repo}/blob/main/docs/evidence/iceberg-jdbc/README.md`} target="_blank" rel="noreferrer">실제 검증 범위와 한계 ↗</a>
        <a href={`${repo}/tree/main/infra/iceberg-lab`} target="_blank" rel="noreferrer">고정 입력·DDL·검증 소스 ↗</a></div>
    </> : <div className="iceberg-flow-pending" role="status"><h3>검증 기록을 준비하고 있습니다.</h3>
      <p>계획은 합성 원본 6개 → 12개, 두 스냅샷의 시점 조회, Trino 정상 재시작 후 같은 데이터 읽기입니다.</p>
      <p>조회·재시작·종료·최종 보존 기록이 모두 확인되기 전에는 결과 수치나 성공 상태를 표시하지 않습니다.</p></div>}
  </section>;
}
