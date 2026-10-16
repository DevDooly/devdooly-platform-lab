import { useEffect, useMemo, useState } from 'react';
import { captureAssetUrl, captureFailures, captureReasons, observedCount, parseIcebergCapture } from '../lib/iceberg-capture';
import '../styles/iceberg-capture.css';

const repo = 'https://github.com/DevDooly/devdooly-platform-lab';
const statusLabels = { DETERMINED: '보존 계획 확인', UNDETERMINED: '판정 미완료', FAILED: '검증 미통과' } as const;
export default function IcebergCaptureCard({ record, observationUrl }: { record?: unknown; observationUrl?: string }) {
  const [loaded, setLoaded] = useState<unknown>(record);
  useEffect(() => {
    if (record !== undefined || !observationUrl) { setLoaded(record); return; }
    let active = true;
    const controller = new AbortController();
    const timer = window.setTimeout(() => controller.abort(), 8000);
    async function load() {
      try {
        const target = captureAssetUrl(observationUrl!, window.location.href);
        if (!target) throw new Error('STATIC_ASSET_ONLY');
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
  const evidence = useMemo(() => parseIcebergCapture(loaded), [loaded]);
  const publicRecordUrl = observationUrl && captureAssetUrl(observationUrl,
    typeof window === 'undefined' ? 'https://static.invalid/' : window.location.href) ? observationUrl : null;
  return <section id="iceberg-capture" className="section iceberg-capture-section" aria-labelledby="iceberg-capture-title">
    <div className="section-heading iceberg-capture-heading"><div><span className="eyebrow">CAPTURE / KEEP-ONLY PLAN</span>
      <h2 id="iceberg-capture-title">메타데이터를 읽고,<br/>보존 계획으로 연결합니다.</h2>
      <p>Cloud 격리 실행의 정적 공개 요약을 표시합니다. 확인한 수치와 아직 판정하지 못한 부분을 함께 남깁니다.</p></div>
      <span className={`tag iceberg-capture-tag${evidence ? ` iceberg-capture-${evidence.status.toLowerCase()}` : ''}`}>정적 Cloud 검증 기록 · {evidence ? statusLabels[evidence.status] : '공개 기록 대기'}</span></div>
    {evidence ? <>
      <p className="iceberg-capture-context">저장된 GitHub 격리 실행 기록이며, 현재 운영 서비스의 상태는 아닙니다.</p>
      <div className="iceberg-capture-outcome" role="status"><h3>{statusLabels[evidence.status]}</h3>
        <p>{evidence.status === 'DETERMINED'
          ? '메타데이터 연결을 확인해 보존 계획을 만들었습니다. 모든 캡처 객체는 KEEP이며 삭제와 스냅샷 만료는 수행하지 않았습니다.'
          : evidence.status === 'UNDETERMINED'
            ? '메타데이터 판정이 완료되지 않았습니다. 관측한 값은 표시하고, 이 기록을 삭제나 만료의 근거로 사용하지 않습니다.'
            : '공개 요약으로 필수 검증의 완료를 확인하지 못했습니다. 확인한 값만 표시하며 확인하지 못한 수치는 미관측으로 남깁니다.'}</p>
        {evidence.failureCategory && <p className="iceberg-capture-reason">{captureFailures[evidence.failureCategory]}</p>}</div>
      <dl className="iceberg-capture-metrics" aria-label="공개 요약에서 관측한 수치">
        <div><dt>전체 바이트를 캡처한 객체</dt><dd>{observedCount(evidence.counts.capturedObjectCount)}{evidence.counts.capturedObjectCount !== null && <small>개</small>}</dd></div>
        <div><dt>목록에 포함한 스냅샷</dt><dd>{observedCount(evidence.counts.snapshotCount)}{evidence.counts.snapshotCount !== null && <small>개</small>}</dd></div>
        <div><dt>검증용 보호 항목</dt><dd>{observedCount(evidence.counts.validationPinCount)}{evidence.counts.validationPinCount !== null && <small>개</small>}</dd></div>
      </dl>
      <p className="iceberg-capture-note">미관측은 0개를 뜻하지 않습니다. 객체 삭제 후보 0개는 모든 객체를 KEEP으로 남기는 정책이며, 실제 삭제 결과가 아닙니다.</p>
      <details className="iceberg-capture-details"><summary>판정 근거와 검증 범위 보기</summary><dl>
        <div><dt>참조 목록 / 스냅샷 제안</dt><dd>{observedCount(evidence.counts.refCount)} / {observedCount(evidence.counts.snapshotCandidateCount)}<span> 제안은 실행되지 않았습니다.</span></dd></div>
        <div><dt>원래 작업 호출 / 반환값</dt><dd>{evidence.checks.originalMainCalledOnce ? '1회 확인' : '미확인'} / {evidence.checks.originalMainReturnedZero ? '0 반환 확인' : '미확인'}</dd></div>
        <div><dt>같은 실행의 중지 상태·시간 제한</dt><dd>{evidence.checks.sameRunStoppedActorsAndClockVerified ? '확인' : '미확인'}</dd></div>
        <div><dt>시간 범위</dt><dd>준비 별도 600초 · 원래 작업 600초 · 정리 여유 40초. 처리량이나 SLA 측정값이 아닙니다.</dd></div>
        <div><dt>보존 정책</dt><dd>최소 스냅샷 3개 · 최소 경과 24시간 · 판정 당시 입력 유효 시간 300초 · 모든 객체 KEEP</dd></div>
        <div><dt>검증 소스</dt><dd><code>{evidence.sourceCommit}</code></dd></div>
        <div><dt>실행 파일 목록 SHA-256</dt><dd><code>{evidence.runtimeManifestSha256}</code></dd></div>
        <div><dt>준비 증거 SHA-256</dt><dd><code>{evidence.proofHashes.prepProofSha256 ?? '미관측'}</code></dd></div>
        <div><dt>정규화 privateReceipt의 canonical SHA-256</dt><dd><code>{evidence.proofHashes.normalizationReceiptCanonicalSha256 ?? '미관측'}</code></dd></div>
      </dl>{evidence.decoderReasonCodes.length > 0 && <ul className="iceberg-capture-reasons" aria-label="고정된 판정 미완료 항목">
        {evidence.decoderReasonCodes.map(reason => <li key={reason}>{captureReasons[reason]} <code>{reason}</code></li>)}</ul>}
        {evidence.schemaVersion === 2 ? <div className="iceberg-capture-diagnostic"><h3>추가 진단</h3><dl>
          <div><dt>시도한 단계</dt><dd><code>{evidence.diagnostic.stageAttempted}</code> · 완료를 뜻하지 않습니다.</dd></div>
          <div><dt>처음 잡은 고정 오류 코드</dt><dd>{evidence.diagnostic.failureCode === 'UNKNOWN' ? '식별된 고정 코드 미확인'
            : evidence.diagnostic.failureCode === null ? '통과 기록: 실패 코드 없음' : <code>{evidence.diagnostic.failureCode}</code>}</dd></div>
          {evidence.diagnostic.lastPrepChild ? <>
            <div><dt>마지막으로 관측한 준비 명령</dt><dd><code>{evidence.diagnostic.lastPrepChild.name}</code><span> · {evidence.diagnostic.lastPrepChild.class}</span></dd></div>
            <div><dt>그 명령 프로세스의 결과 / 반환값</dt><dd><code>{evidence.diagnostic.lastPrepChild.outcome}</code> / {evidence.diagnostic.lastPrepChild.returnCode ?? '미관측'}</dd></div>
            <div><dt>명령 Popen/CLI 생성 / 회수</dt><dd>{evidence.diagnostic.lastPrepChild.childStarted ? '생성 관측' : '미확인'} / {evidence.diagnostic.lastPrepChild.childReaped ? '회수 확인' : '미확인'}</dd></div>
            <div><dt>받아들인 출력 prefix 바이트</dt><dd>stdout {observedCount(evidence.diagnostic.lastPrepChild.stdoutBytes)} / stderr {observedCount(evidence.diagnostic.lastPrepChild.stderrBytes)} bytes</dd></div>
          </> : <div><dt>마지막 준비 명령</dt><dd>미관측</dd></div>}
          {evidence.diagnostic.prepCleanup ? <>
            <div><dt>준비용 컨테이너 ID 연결 / 범위 검증</dt><dd>{evidence.diagnostic.prepCleanup.knownColdCid ? '확인' : '미확인'} / {evidence.diagnostic.prepCleanup.coldIdentityBound ? '확인' : '미확인'}</dd></div>
            <div><dt>그 컨테이너의 제거 시도 / 제거 후 부재</dt><dd>{evidence.diagnostic.prepCleanup.coldRemovalAttempted ? '시도 관측' : '미확인'} / {evidence.diagnostic.prepCleanup.coldRemovedAndAbsent ? '확인' : '미확인'}</dd></div>
          </> : <div><dt>준비용 컨테이너 정리</dt><dd>미관측</dd></div>}
        </dl><p>마지막 준비 명령만으로 최초 실패 원인을 특정하지 않으며 정리 명령일 수 있습니다. Popen/CLI 생성·회수는 Docker 컨테이너 시작·종료 증거가 아닙니다. 바이트 수는 받아들인 prefix이며 전체 출력이나 EOF 확인을 뜻하지 않습니다. 미확인을 자원 부재나 원인 확정으로 바꾸지 않습니다.</p></div>
          : <p>이 schema 1 기록에는 추가 진단 필드가 없습니다. 실패 원인·명령 실행·준비 자원의 정리나 부재를 추정하지 않습니다.</p>}
        <p>Parquet 내용을 해석하거나 현재 운영 테이블을 독립적으로 재검증한 결과가 아닙니다. 기존 Cloud compaction·native Trino 검증과 이 실행의 수치를 합산하지 않습니다.</p></details>
    </> : <div className="iceberg-capture-unavailable" role="status"><h3>{loaded === undefined ? '공개 요약을 불러오고 있습니다.' : '공개 기록을 확인할 수 없습니다.'}</h3>
      <p>검토한 실제 실행 요약이 연결되면 판정과 관측 수치를 표시합니다. 준비 코드나 합성 테스트를 실행 성공으로 표시하지 않습니다.</p></div>}
    <div className="iceberg-capture-links"><a href={`${repo}/blob/main/docs/runbooks/iceberg-closed-copy-capture.md`} target="_blank" rel="noreferrer">실행 절차와 범위 ↗</a>
      <a href={`${repo}/tree/main/infra/iceberg-retention-ci`} target="_blank" rel="noreferrer">입력 계약과 검증 코드 ↗</a>
      {evidence && publicRecordUrl && <a href={publicRecordUrl} target="_blank" rel="noreferrer">공개 결과 JSON ↗</a>}</div>
  </section>;
}
