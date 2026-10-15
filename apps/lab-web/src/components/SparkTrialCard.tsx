import { useEffect, useMemo, useState } from 'react';
import { parseSparkTrial } from '../lib/spark-trial';
import '../styles/spark-trial.css';

const repo = 'https://github.com/DevDooly/devdooly-platform-lab';
const stages = ['원본 12건', '분류 결과', '순차 재실행'] as const;
export default function SparkTrialCard({ record, observationUrl }: { record?: unknown; observationUrl?: string }) {
  const [loaded, setLoaded] = useState<unknown>(record);
  const [stage, setStage] = useState<0 | 1 | 2>(1);
  useEffect(() => {
    if (record !== undefined || !observationUrl) { setLoaded(record); return; }
    let active = true;
    const controller = new AbortController();
    const timer = window.setTimeout(() => controller.abort(), 8000);
    async function load() {
      try {
        const target = new URL(observationUrl!, window.location.href);
        if (target.origin !== window.location.origin || target.username || target.password || target.search || target.hash
          || !target.pathname.endsWith('/observations/spark.latest.json')) throw new Error('STATIC_ASSET_ONLY');
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
  const evidence = useMemo(() => parseSparkTrial(loaded), [loaded]);
  return <section id="spark-trial" className="section spark-trial-section" aria-labelledby="spark-trial-title">
    <div className="section-heading spark-trial-heading"><div><span className="eyebrow">07 / ONE MERGE → READONLY REPLAY</span>
      <h2 id="spark-trial-title">{evidence ? <>같은 입력을 다시 읽어도,<br/>추가 쓰기는 0건.</> : <>원본부터 재처리까지,<br/>실행 기록으로 확인합니다.</>}</h2>
      <p>{evidence ? 'Spark가 원본을 분류하고 Silver에 저장한 뒤, 같은 입력의 순차 재처리를 확인했습니다.' : 'GitHub 격리 실행기의 Spark 분류·순차 재처리 기록을 조회합니다.'}</p></div>
      <span className="tag">GitHub 격리 실행 · {evidence ? '검증 기록' : '기록 미확인'}</span></div>
    {evidence ? <>
      <ol className="spark-trial-flow" aria-label="검증한 Spark 데이터 처리 흐름">
        <li><span>BRONZE</span><strong>{evidence.bronze.rows}건</strong><p>원본 전체 보관<br/>스냅샷 {evidence.bronze.snapshots}개</p></li>
        <li><span>SILVER / CLASSIFY</span><strong>{evidence.silver.success} / {evidence.silver.failure} / {evidence.silver.duplicate}</strong><p>성공 / 실패 / 중복<br/>한 번의 MERGE</p></li>
        <li><span>SEQUENTIAL REPLAY</span><strong>추가 쓰기 {evidence.silver.replayWriteInvocations}회</strong><p>순차 재실행 1회<br/>Silver 스냅샷 1개 유지</p></li>
      </ol>
      <div className="spark-trial-record"><div className="spark-trial-controls" role="group" aria-label="Spark 기록 단계 선택">
        {stages.map((label, index) => <button type="button" key={label} aria-pressed={stage === index} onClick={() => setStage(index as 0 | 1 | 2)}>{label}</button>)}</div>
        <div className="spark-trial-stage" aria-live="polite" aria-atomic="true">
          {stage === 0 ? <><h3>검증 전에 원본부터 남깁니다.</h3><p>고정 합성 입력을 6건씩 두 번 append해 총 12건·1,100 bytes를 보관했습니다. 잘못된 값과 중복 입력도 Bronze에는 남깁니다.</p>
            <dl className="spark-trial-counts"><div><dt>원본 행</dt><dd>12<small>건</small></dd></div><div><dt>원본 스냅샷</dt><dd>2<small>개</small></dd></div></dl></>
          : stage === 1 ? <><h3>성공뿐 아니라, 실패와 중복도 결과입니다.</h3><p>12건을 모두 분류해 Silver에 기록했습니다. 성공 7건·실패 3건·중복 2건이며 미처리 건은 없습니다.</p>
            <dl className="spark-trial-counts"><div><dt>성공</dt><dd>7<small>건</small></dd></div><div><dt>실패</dt><dd>3<small>건</small></dd></div><div><dt>중복</dt><dd>2<small>건</small></dd></div></dl></>
          : <><h3>같은 입력을 다시 읽고, 쓰기를 건너뜁니다.</h3><p>첫 MERGE 이후 한 번 더 순차 실행했습니다. 추가 쓰기 없이 같은 12건을 확인했고 Silver 스냅샷은 1개로 유지됐습니다.</p>
            <dl className="spark-trial-counts"><div><dt>순차 재실행</dt><dd>1<small>회</small></dd></div><div><dt>추가 쓰기</dt><dd>0<small>회</small></dd></div></dl></>}
        </div><p className="spark-trial-note">버튼은 저장된 검증 기록을 바꿔 보여줍니다. 현재 실행 중인 서비스의 상태는 아닙니다.</p>
        <details className="spark-trial-details"><summary>검증 환경과 종료 근거 보기</summary><dl>
          <div><dt>기록 시각 UTC</dt><dd><time dateTime={evidence.capturedAt}>{evidence.capturedAt}</time></dd></div>
          <div><dt>실행 환경</dt><dd>Spark {evidence.versions.spark} · Java {evidence.versions.java} · Scala {evidence.versions.scala} · JDBC catalog · Garage</dd></div>
          <div><dt>자원과 시간 제한</dt><dd>CPU 1개 · 컨테이너 3GiB · driver heap 1536MiB · Spark PID 512 · 시험 제한 600초</dd></div>
          <div><dt>정상 완료·종료</dt><dd>세션 종료 반환 · COMPLETED · exit code 0 · 시험 컨테이너 및 초기화 컨테이너 종료</dd></div>
          <div><dt>실행 시간의 의미</dt><dd>기록된 bootstrap 시작부터 작업·세션 종료까지 24,871ms입니다. CI 전체 시간이나 처리량 측정값은 아닙니다.</dd></div>
          <div><dt>실패 기록과의 관계</dt><dd>직전 시험은 native-thread 오류 서명과 PID 제한 누적 counter를 관측한 뒤 시간 제한으로 실패했습니다. 이번에는 Spark PID 한도만 256에서 512로 늘렸습니다. 단일 원인이 확정됐다는 뜻은 아닙니다.</dd></div>
          <div><dt>검증 소스</dt><dd><code>{evidence.sourceCommit}</code></dd></div>
          <div><dt>실제 결과 요약 SHA-256</dt><dd><code>{evidence.summary.sha256}</code></dd></div>
        </dl><p>이번 기록은 미니 PC 배포·Trino 재시작·분산 동시 실행·crash recovery·exactly once·성능 SLA를 검증하지 않았습니다. Trino의 별도 기록과 Spark의 스냅샷 수는 합산하지 않습니다.</p></details>
      </div>
      <div className="spark-trial-links"><a href={evidence.run.url} target="_blank" rel="noreferrer">실제 GitHub 실행 결과 ↗</a>
        <a href={`${repo}/blob/main/docs/evidence/spark-silver/README.md`} target="_blank" rel="noreferrer">검증 범위와 실패 기록 ↗</a></div>
    </> : <div className="spark-trial-unavailable" role="status"><h3>{loaded === undefined ? '검증 기록을 불러오고 있습니다.' : '검증 기록을 확인할 수 없습니다.'}</h3>
      <p>필수 결과와 종료 근거를 모두 확인한 기록에만 수치를 표시합니다.</p></div>}
  </section>;
}
