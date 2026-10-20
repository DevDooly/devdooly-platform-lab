import { useId, useMemo, useRef, useState } from 'react';
import { exportIntegrityPhaseKey, exportIntegrityPhases, parseExportIntegrity } from '../lib/export-integrity-runtime.ts';
import type { ExportIntegrityRecord } from '../lib/export-integrity-runtime.ts';
import '../styles/export-integrity-runtime.css';

const repository = 'https://github.com/DevDooly/devdooly-platform-lab';
const evidenceUrl = `${repository}/blob/main/docs/evidence/export-integrity-runtime/README.md`;

/** Public props always pass the reviewed saved-record binding; selection performs no I/O. */
export default function ExportIntegrityRuntimeCard({ record }: { record?: unknown }) {
  const evidence = useMemo(() => parseExportIntegrity(record), [record]);
  return <ExportIntegrityRuntimeView evidence={evidence}/>;
}

/** Presentation of an already validated record, also used by synthetic render tests. */
export function ExportIntegrityRuntimeView({ evidence }: { evidence: ExportIntegrityRecord | null }) {
  const [selected, setSelected] = useState(3);
  const buttons = useRef<Array<HTMLButtonElement | null>>([]);
  const identifier = useId();
  const detailId = `${identifier}-phase`;
  const phases = evidence ? exportIntegrityPhases(evidence) : [];
  const phase = phases[selected];
  const result = evidence?.summary.integrityResult;
  return <section id="export-integrity-runtime" className="section export-integrity" aria-labelledby={`${identifier}-title`}>
    <div className="section-heading export-integrity-heading"><div>
      <span className="eyebrow">EXPORT / VERIFIED REPAIR</span>
      <h2 id={`${identifier}-title`}>결과 파일이 손상된 채로<br/>resume하면?</h2>
      <p>격리 환경에서 실제 export 검증 실패와 명시 수리 전후를 확인하는 시험입니다.</p>
    </div><span className="tag">{evidence ? '저장된 격리 검증' : '공개 기록 대기'}</span></div>
    {evidence && result && phase ? <>
      <p className="export-integrity-context">한 번의 저장된 검증 기록 · 완료 <time dateTime={evidence.completedAt}>
        {new Intl.DateTimeFormat('ko-KR', { timeZone: 'Asia/Seoul', dateStyle: 'medium', timeStyle: 'medium' })
          .format(new Date(evidence.completedAt))} KST</time>. 단계 간 간격은 경과 시간을 뜻하지 않습니다.</p>
      <div className="export-integrity-controls" role="group" aria-label="저장된 export 무결성 회복 단계" aria-describedby={`${identifier}-hint`}>
        {phases.map((item, index) => <button key={item.id} type="button"
          ref={element => { buttons.current[index] = element; }}
          aria-pressed={selected === index} aria-controls={detailId}
          onClick={() => setSelected(index)} onKeyDown={event => {
            const next = exportIntegrityPhaseKey(index, event.key);
            if (next === null) return;
            event.preventDefault(); setSelected(next); buttons.current[next]?.focus();
          }}><span aria-hidden="true">{index + 1}</span>{item.title}</button>)}
      </div>
      <p id={`${identifier}-hint`} className="export-integrity-hint">단계 선택은 저장 기록 조회입니다. Tab·Enter·Space와 좌우 방향키·Home·End를 사용할 수 있습니다.</p>
      <div id={detailId} className="export-integrity-selected" role="status" aria-live="polite" aria-atomic="true">
        <h3>{selected + 1}단계 · {phase.title}</h3><p>{phase.description}</p>
      </div>
      <details className="export-integrity-evidence">
        <summary>전체 근거와 확인 수치</summary>
        <p>최초 업무 완료는 직접 DB fixture로 준비했습니다. 마지막 consumer 처리는 이미 완료된 메시지의 replay이며, 업무를 다시 계산했다는 뜻이 아닙니다. resume는 저장소 수리가 아니며, 시험 코드가 소유 손상 객체 한 개를 명시 삭제한 뒤에 회복을 확인했습니다.</p>
        <div className="export-integrity-table" tabIndex={0} role="region" aria-label="단계별 업무와 실행 상태. 작은 화면에서는 가로로 이동할 수 있습니다.">
          <table><caption>업무 완료와 실행 pause, export 완료를 구분한 네 단계</caption>
            <thead><tr><th scope="col">단계</th><th scope="col">대상</th><th scope="col">업무 / 실행 상태</th><th scope="col">Export</th><th scope="col">슬롯</th></tr></thead>
            <tbody>{phases.map((item, index) => <tr key={item.id} aria-current={selected === index ? 'step' : undefined}>
              <th scope="row">{index + 1}. {item.title}</th><td>{item.domain === 'JOB' ? '업무 작업(job)' : '실행(runtime)'}</td>
              <td>{item.status}</td><td>{item.exportStatus}</td><td>{item.slot}</td>
            </tr>)}</tbody>
          </table>
        </div>
        <dl className="export-integrity-counts">
          <div><dt>합성 입력</dt><dd>{result.fixtureInput}개</dd></div>
          <div><dt>성공 / 실패 / 중복</dt><dd>{result.successCount} / {result.failureCount} / {result.duplicateCount}</dd></div>
          <div><dt>미처리 입력</dt><dd>{result.pendingCount}개</dd></div>
          <div><dt>전체 bytes·SHA 대조</dt><dd>결과·실패 파일 {result.verifiedExportFiles}개</dd></div>
          <div><dt>완료 메시지 replay</dt><dd>{result.completedReplays}회</dd></div>
          <div><dt>최종 end / commit / lag</dt><dd>{result.finalEndOffset} / {result.finalCommittedOffset} / {result.finalLag}</dd></div>
        </dl>
        <p>업무 행·처리 시각, 원본 bytes와 DISPATCH·EXPORT 식별자를 보존했고 허용한 export 상태 변경을 따로 검사했습니다. 두 번의 실제 검증 실패, 원 CLI의 run 거부와 resume, child 자원 닫힘과 소유 시험 자원 정리도 함께 확인한 기록입니다.</p>
        <p className="export-integrity-boundary">작은 합성 입력과 새 격리 자원의 시험입니다. 시험 소유 객체의 명시 수리이며, 현재 운영 자료의 자동 복구를 검증한 결과는 아닙니다.</p>
        <nav className="export-integrity-links" aria-label="Export 무결성 회복의 실제 근거">
          <a href={evidence.runUrl} target="_blank" rel="noreferrer">실제 GitHub 실행 ↗</a>
          <a href={`${repository}/blob/${evidence.summary.sourceCommit}/infra/export-integrity-runtime-ci/ExportIntegrityRuntimeIT.java`}
            target="_blank" rel="noreferrer">검증한 Java 소스 ↗</a>
          <a href={evidenceUrl} target="_blank" rel="noreferrer">검증 조건과 한계 ↗</a>
        </nav>
        <dl className="export-integrity-provenance">
          <div><dt>테스트 / 검증 소스</dt><dd>{evidence.summary.verifiedTests}개 확인 · <code>{evidence.summary.sourceCommit}</code></dd></div>
          <div><dt>고정 입력 목록 SHA-256</dt><dd><code>{evidence.summary.runtimeManifestSha256}</code></dd></div>
          <div><dt>JUnit XML SHA-256</dt><dd><code>{evidence.summary.surefireXmlSha256}</code></dd></div>
        </dl>
      </details>
    </> : <div className="export-integrity-pending" role="status">
      <h3>검증한 공개 기록을 기다리고 있습니다.</h3>
      <p>실제 실행·JUnit 결과·소유 자원 정리를 확인한 요약이 연결되면 단계를 표시합니다. 미확인·실패·부분 결과를 성공 수치로 채우지 않습니다.</p>
    </div>}
  </section>;
}
