import { useId, useMemo, useRef, useState } from 'react';
import { offsetCommitPhaseKey, offsetCommitPhases, parseOffsetCommitRecovery } from '../lib/offset-commit-recovery.ts';
import type { OffsetCommitRecoveryRecord } from '../lib/offset-commit-recovery.ts';
import '../styles/offset-commit-recovery.css';

const repository = 'https://github.com/DevDooly/devdooly-platform-lab';
const evidenceUrl = `${repository}/blob/main/docs/evidence/offset-commit-recovery/README.md`;

/** The public entry always checks the reviewed saved-record binding; selection performs no I/O. */
export default function OffsetCommitRecoveryCard({ record }: { record?: unknown }) {
  const evidence = useMemo(() => parseOffsetCommitRecovery(record), [record]);
  return <OffsetCommitRecoveryView evidence={evidence}/>;
}

/** Presentation of an already validated record, also used by synthetic render tests. */
export function OffsetCommitRecoveryView({ evidence }: { evidence: OffsetCommitRecoveryRecord | null }) {
  const [selected, setSelected] = useState(3);
  const buttons = useRef<Array<HTMLButtonElement | null>>([]);
  const identifier = useId();
  const detailId = `${identifier}-phase`;
  const phases = evidence ? offsetCommitPhases(evidence) : [];
  const phase = phases[selected];
  const result = evidence?.summary.recoveryResult;
  return <section id="offset-commit-recovery" className="section offset-recovery" aria-labelledby={`${identifier}-title`}>
    <div className="section-heading offset-recovery-heading"><div>
      <span className="eyebrow">KAFKA / PERSISTED PAUSE</span>
      <h2 id={`${identifier}-title`}>DB는 끝났는데,<br/>Kafka commit이 실패하면?</h2>
      <p>격리 환경에서 실제 commit 실패와 운영자 재개 절차를 확인하는 시험입니다.</p>
    </div><span className="tag">{evidence ? '저장된 격리 검증' : '공개 기록 대기'}</span></div>
    {evidence && result && phase ? <>
      <p className="offset-recovery-context">한 번의 저장된 검증 기록 · 완료 <time dateTime={evidence.completedAt}>
        {new Intl.DateTimeFormat('ko-KR', { timeZone: 'Asia/Seoul', dateStyle: 'medium', timeStyle: 'medium' })
          .format(new Date(evidence.completedAt))} KST</time>. 단계 간 간격은 경과 시간을 뜻하지 않습니다.</p>
      <div className="offset-recovery-controls" role="group" aria-label="저장된 commit 실패 복구 단계">
        {phases.map((item, index) => <button key={item.id} type="button"
          ref={element => { buttons.current[index] = element; }}
          aria-pressed={selected === index} aria-controls={detailId}
          onClick={() => setSelected(index)} onKeyDown={event => {
            const next = offsetCommitPhaseKey(index, event.key);
            if (next === null) return;
            event.preventDefault(); setSelected(next); buttons.current[next]?.focus();
          }}><span aria-hidden="true">{index + 1}</span>{item.title}</button>)}
      </div>
      <div id={detailId} className="offset-recovery-selected" role="status" aria-live="polite" aria-atomic="true">
        <h3>{selected + 1}단계 · {phase.title}</h3><p>{phase.description}</p>
      </div>
      <p className="offset-recovery-observed">Broker 재개 뒤 실제 commit 관측은 <strong>
        {result.postUnpauseCommitState === 'NO_COMMIT' ? '기록 없음 (null)' : `offset ${result.postUnpauseCommittedOffset}`}</strong>,
        완료 작업의 실제 재전달은 <strong>{result.completedReplays}회</strong>였습니다.
        각각 관측한 값이며, 첫 offset 조회만으로 재전달 횟수를 추정하지 않습니다.</p>
      <details className="offset-recovery-evidence">
        <summary>전체 근거와 확인 수치</summary>
        <p>저장된 순서의 선택입니다. Tab·Enter·Space와 좌우 방향키·Home·End를 사용할 수 있으며, Kafka·DB에 명령을 보내지 않습니다.</p>
        <div className="offset-recovery-table" tabIndex={0} role="region" aria-label="단계별 저장 상태. 작은 화면에서는 가로로 이동할 수 있습니다.">
          <table><caption>업무 처리 완료와 export 완료를 구분한 네 단계</caption>
            <thead><tr><th scope="col">단계</th><th scope="col">대상</th><th scope="col">업무 / 실행 상태</th><th scope="col">Export</th></tr></thead>
            <tbody>{phases.map((item, index) => <tr key={item.id}>
              <th scope="row">{index + 1}. {item.title}</th><td>{item.domain === 'JOB' ? '업무 작업(job)' : '실행(runtime)'}</td><td>{item.status}</td><td>{item.exportStatus}</td>
            </tr>)}</tbody>
          </table>
        </div>
        <dl className="offset-recovery-counts">
          <div><dt>합성 입력</dt><dd>{result.fixtureInput}개</dd></div>
          <div><dt>성공 / 실패 / 중복</dt><dd>{result.successCount} / {result.failureCount} / {result.duplicateCount}</dd></div>
          <div><dt>미처리 입력</dt><dd>{result.pendingCount}개</dd></div>
          <div><dt>전체 bytes·SHA 대조</dt><dd>결과·실패 파일 {result.verifiedExportFiles}개</dd></div>
          <div><dt>최종 commit / lag</dt><dd>{result.finalCommittedOffset} / {result.finalLag}</dd></div>
          <div><dt>최종 실행 슬롯</dt><dd>{result.slotFree ? '비어 있음' : '미확인'}</dd></div>
        </dl>
        <p>업무 행·처리 시각과 원본 bytes를 보존했고, 지정한 export 상태 변경을 따로 검사했습니다. 일반 run CLI의 pause 우회 거부, 명시 resume, child 자원 닫힘과 소유 시험 자원 정리도 함께 확인한 결과입니다.</p>
        <p className="offset-recovery-boundary">작은 합성 입력의 격리 시험입니다. 운영 worker·현재 운영 자료의 복구, 정확히 한 번의 업무 처리, broker·호스트 재시작, HA·지속 처리량을 증명하지 않습니다.</p>
        <nav className="offset-recovery-links" aria-label="Commit 실패 복구의 실제 근거">
          <a href={evidence.runUrl} target="_blank" rel="noreferrer">실제 GitHub 실행 ↗</a>
          <a href={`${repository}/blob/${evidence.summary.sourceCommit}/infra/offset-commit-recovery-ci/OffsetCommitRecoveryIT.java`}
            target="_blank" rel="noreferrer">검증한 Java 소스 ↗</a>
          <a href={evidenceUrl} target="_blank" rel="noreferrer">검증 조건과 한계 ↗</a>
        </nav>
        <dl className="offset-recovery-provenance">
          <div><dt>테스트 / 검증 소스</dt><dd>{evidence.summary.verifiedTests}개 확인 · <code>{evidence.summary.sourceCommit}</code></dd></div>
          <div><dt>고정 입력 목록 SHA-256</dt><dd><code>{evidence.summary.runtimeManifestSha256}</code></dd></div>
          <div><dt>JUnit XML SHA-256</dt><dd><code>{evidence.summary.surefireXmlSha256}</code></dd></div>
        </dl>
      </details>
    </> : <div className="offset-recovery-pending" role="status">
      <h3>검증한 공개 기록을 기다리고 있습니다.</h3>
      <p>실제 실행·JUnit 결과·소유 자원 정리를 확인한 요약이 연결되면 단계를 표시합니다. 미확인·실패·부분 결과를 성공 수치로 채우지 않습니다.</p>
    </div>}
  </section>;
}
