import { useEffect, useMemo, useState } from 'react';
import { parseS3Transport } from '../lib/s3-transport';
import '../styles/s3-transport.css';

const evidenceUrl = 'https://github.com/DevDooly/devdooly-platform-lab/blob/main/docs/evidence/s3-runtime-rollout/README.md';
export default function S3TransportCard({ record, observationUrl }: { record?: unknown; observationUrl?: string }) {
  const [loaded, setLoaded] = useState<unknown>(record);
  useEffect(() => {
    if (record !== undefined || !observationUrl) { setLoaded(record); return; }
    let active = true; const controller = new AbortController();
    const timer = window.setTimeout(() => controller.abort(), 8000);
    async function load() {
      try {
        const target = new URL(observationUrl!, window.location.href);
        if (target.origin !== window.location.origin || target.username || target.password || target.search || target.hash
          || !target.pathname.endsWith('/observations/s3.latest.json')) throw new Error('STATIC_ASSET_ONLY');
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
  const evidence = useMemo(() => parseS3Transport(loaded), [loaded]);
  const sdk = evidence?.status === 'DEPLOYED_SDK_VERIFIED' ? evidence.sdk : null;
  return <section id="s3-transport" className="section s3-transport-section" aria-labelledby="s3-transport-title">
    <div className="section-heading s3-transport-heading"><div><span className="eyebrow">08 / S3 TRANSPORT EVIDENCE</span>
      <h2 id="s3-transport-title">배포한 전송 코드로,<br/>원본 바이트까지 확인합니다.</h2>
      <p>배포 관측과 별도 Java 프로세스의 SDK 읽기를 구분한, 확인 시점의 기록입니다.</p></div>
      <span className="tag">{evidence ? (sdk ? '배포 확인 · SDK 읽기 검증' : '배포 확인 · SDK 증거 대기') : '기록 미확인'}</span></div>
    {evidence ? <>
      <ol className="s3-transport-flow" aria-label="S3 검증 범위">
        <li><span>DEPLOYMENT</span><strong>배포 확인</strong><p>같은 소스의 API·web·worker<br/>확인 시점의 정상 상태</p></li>
        <li><span>SEPARATE JVM / SDK GET</span><strong>{sdk ? '3개 전체 읽기' : '증거 대기'}</strong><p>{sdk ? <>3회 호출 · 3회 HTTP 시도<br/>재시도 0회 · Apache5</> : 'SDK 실행·정리·사후 보존 근거를 모두 확인한 뒤 표시합니다.'}</p></li>
        <li><span>CLEANUP / PRESERVATION</span><strong>{sdk ? '정리·회수 완료' : '사후 근거 대기'}</strong><p>원래 객체 24개 + native 검증 객체 12개<br/>{sdk ? 'SDK 종료·정리 후 보존 확인' : 'SDK 검증 전 보존 확인'}</p></li>
      </ol>
      <details className="s3-transport-details"><summary>읽기 결과와 검증 범위 보기</summary><dl>
        <div><dt>공개 기록 시각 UTC</dt><dd><time dateTime={evidence.observedAt}>{evidence.observedAt}</time></dd></div>
        <div><dt>배포 소스</dt><dd><code>{evidence.sourceCommit}</code></dd></div>
        {sdk && <><div><dt>SDK 읽기 시각 UTC</dt><dd><time dateTime={sdk.capturedAt}>{sdk.capturedAt}</time></dd></div>
          <div><dt>전체 본문과 실행 계수</dt><dd>3개 객체의 길이·EOF·전체 SHA-256 확인 · API 호출 3회 · HTTP 시도 3회 · 재시도 0회</dd></div>
          <div><dt>클라이언트 설정과 종료</dt><dd>Apache5 · 최대 시도 설정 3회 · 클라이언트 close 확인 · 임시 Job·설정 정리 및 읽기 전용 키 회수 확인</dd></div>
          <div><dt>SDK 결과 SHA-256</dt><dd><code>{sdk.proofSha256.run}</code></dd></div>
          <div><dt>정리 / 회수 결과 SHA-256</dt><dd><code>{sdk.proofSha256.cleanup}</code><br/><code>{sdk.proofSha256.revoke}</code></dd></div></>}
        <div><dt>보존 확인 시각 UTC</dt><dd><time dateTime={evidence.preservation.capturedAt}>{evidence.preservation.capturedAt}</time></dd></div>
        <div><dt>남겨 둔 실패와 미관측</dt><dd>최초 API·web watch는 실패 기록을 유지하며 단일 원인은 미확정입니다. 이후 읽기 전용 관측으로 배포를 확인했습니다. 이전 worker의 종료 코드는 미관측입니다.</dd></div>
      </dl><p>SDK 읽기는 배포된 API JAR를 별도 프로세스에서 사용한 결과입니다. 운영 API JVM 내부의 GET, 쓰기 호환성, 장애 주입, 지연·SLA를 검증한 기록은 아닙니다. 최대 시도 설정 3회와 이번 재시도 0회는 서로 다른 값입니다.</p></details>
      <p className="s3-transport-note">저장된 기록을 표시합니다. 현재 상태를 계속 조회하거나 SDK 요청을 실행하지 않습니다.</p>
    </> : <div className="s3-transport-unavailable" role="status"><h3>{loaded === undefined ? '검증 기록을 불러오고 있습니다.' : '검증 기록을 확인할 수 없습니다.'}</h3>
      <p>공개 요약의 필수 항목과 범위가 모두 맞는 경우에만 결과를 표시합니다.</p></div>}
    <a className="s3-transport-link" href={evidenceUrl} target="_blank" rel="noreferrer">배포·SDK 읽기의 근거와 한계 보기 ↗</a>
  </section>;
}
