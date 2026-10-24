import { useEffect, useMemo, useState } from 'react';
import {
  createEventExport, eventExportCsv, eventExportFilename, eventExportJson,
  type EventExportInput,
} from '../lib/event-export';
import '../styles/event-export.css';

export interface EventExportControlsProps {
  input: EventExportInput;
  matchedCount: number;
  disabled: boolean;
}

const sourceLabels = {
  live: 'live · API 조회',
  recorded: 'recorded · 게시 관측',
  fixture: 'fixture · 고정 샘플 기대값',
} as const;

export default function EventExportControls({ input, matchedCount, disabled }: EventExportControlsProps) {
  const context = useMemo(() => ({}), [
    input.runId, input.mode, input.observedAt, input.capturedAt, input.reportedInputCount,
    input.filters.status, input.filters.query, input.filters.reason, input.filters.sensorId, input.outcomes,
  ]);
  const [notice, setNotice] = useState<{ context: object; text: string; failed: boolean } | null>(null);

  useEffect(() => { setNotice(null); }, [context]);
  const currentNotice = notice?.context === context ? notice : null;

  function prepareFile(format: 'csv' | 'json') {
    if (disabled) return;
    let objectUrl: string | null = null;
    let anchor: HTMLAnchorElement | null = null;
    try {
      const exportDocument = createEventExport(input);
      const content = format === 'csv' ? eventExportCsv(exportDocument) : eventExportJson(exportDocument);
      const filename = eventExportFilename(exportDocument, format);
      const blob = new Blob([content], { type: format === 'csv' ? 'text/csv;charset=utf-8' : 'application/json;charset=utf-8' });
      objectUrl = URL.createObjectURL(blob);
      anchor = document.createElement('a');
      anchor.href = objectUrl;
      anchor.download = filename;
      anchor.hidden = true;
      document.body.appendChild(anchor);
      anchor.click();
      setNotice({
        context,
        text: `${format.toUpperCase()} 파일을 준비했습니다. 브라우저 다운로드 목록에서 저장 여부를 확인하세요.`,
        failed: false,
      });
    } catch {
      setNotice({ context, text: '파일을 준비하지 못했습니다. 같은 조건에서 다시 시도해 주세요.', failed: true });
    } finally {
      anchor?.remove();
      if (objectUrl !== null) {
        const urlToRevoke = objectUrl;
        // Let the browser begin consuming the download before releasing its Blob URL.
        setTimeout(() => URL.revokeObjectURL(urlToRevoke), 1000);
      }
    }
  }

  return <section className="event-export" aria-labelledby="event-export-title">
    <div className="event-export-heading">
      <h4 id="event-export-title">검색 결과 저장</h4>
      <p>검색 결과 전체 <strong>{matchedCount.toLocaleString('ko-KR')}건</strong> · 조회된 전체 {input.outcomes.length.toLocaleString('ko-KR')}건 · 보고된 입력 {input.reportedInputCount.toLocaleString('ko-KR')}건</p>
    </div>
    <p className="event-export-scope">페이지와 관계없이 검색·처리 상태·사유·정확한 센서 조건에 맞는 이벤트 전체를 입력 순서로 저장합니다. 흐름 보기에서 선택한 한 건만 저장하는 기능은 아닙니다. 0건이어도 조건과 출처를 담은 파일을 만듭니다.</p>
    <div className="event-export-actions" aria-label="검색 결과 파일 형식">
      <button type="button" disabled={disabled} onClick={() => prepareFile('csv')}>CSV 다운로드</button>
      <button type="button" disabled={disabled} onClick={() => prepareFile('json')}>JSON 다운로드</button>
    </div>
    <p className={`event-export-status${currentNotice?.failed ? ' event-export-status-error' : ''}`} role="status" aria-live="polite" aria-atomic="true">{currentNotice?.text ?? ''}</p>
    <details className="event-export-notes">
      <summary>파일에 담는 정보·CSV 주의사항</summary>
      <dl className="event-export-provenance">
        <div><dt>표시 출처</dt><dd>{sourceLabels[input.mode]}</dd></div>
        <div><dt>실행 · runId</dt><dd><code>{input.runId}</code></dd></div>
        <div><dt>정확한 센서 조건</dt><dd>{input.filters.sensorId == null ? '전체 센서' : <code>{JSON.stringify(input.filters.sensorId)}</code>}</dd></div>
        <div><dt>상세 관측 · observedAt</dt><dd><code>{input.observedAt === null ? 'null' : input.observedAt}</code></dd></div>
        {input.mode !== 'live' && <div><dt>{input.mode === 'recorded' ? '수집' : '파일 생성'} · capturedAt</dt><dd><code>{input.capturedAt === null ? 'null' : input.capturedAt}</code></dd></div>}
      </dl>
      <p>JSON은 표시된 이벤트의 원문 필드와 조건을 담으며 문자열·숫자·null 타입을 유지합니다. HTTP 응답 전체를 담는 파일은 아닙니다.</p>
      <p>CSV는 첫 데이터 행에 조건·출처를 담은 context를, 이후 행에 event를 담습니다. 0건이면 context만 남습니다. null 값은 빈 칸과 valueIsNull로, 사유 전체와 빈 문자열 조건은 메타데이터로 구분합니다.</p>
      <p>정확한 센서 조건이 없으면 기존 JSON 형식 1·CSV 21열을 유지합니다. 조건이 있으면 형식 2로 센서 원문을 담고 CSV에 filterSensorIsAll·filterSensorId 두 열을 추가합니다. 빈 센서 ID도 전체 센서와 구분해 저장합니다.</p>
      <p>CSV는 수식으로 해석될 수 있는 문자열 앞에 작은따옴표(')를 붙입니다. JSON에는 이 변환을 적용하지 않습니다. 새 조회나 실행·재판정은 하지 않습니다.</p>
    </details>
  </section>;
}
