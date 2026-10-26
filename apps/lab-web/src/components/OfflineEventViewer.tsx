import { useEffect, useId, useRef, useState } from 'react';
import { EVENT_PAGE_SIZES, eventPage, type EventPageSize } from '../lib/event-pagination';
import { eventReasonOptions, filterEventOutcomes, type EventSearchFilters } from '../lib/event-search';
import { MAX_OFFLINE_FILE_BYTES, MAX_OFFLINE_OUTCOMES, readOfflineEventFile, type OfflineEventFile, type OfflineEventFileError } from '../lib/offline-event-file';
import '../styles/offline-event-viewer.css';

export interface OfflineViewerView {
  filters: EventSearchFilters;
  pageIndex: number;
  pageSize: EventPageSize;
  selectedIndex: number | null;
}

export const initialOfflineViewerView = (): OfflineViewerView => ({
  filters: { status: 'ALL', query: '', reason: null, sensorId: null },
  pageIndex: 0, pageSize: 25, selectedIndex: null,
});
const count = (value: number) => value.toLocaleString('ko-KR');
const raw = (value: string | number | null) => Object.is(value, -0) ? '-0' : JSON.stringify(value);
const errorMessages: Record<OfflineEventFileError, string> = {
  FILE_TOO_LARGE: '파일 크기가 1 MiB 한도를 넘습니다.',
  INVALID_UTF8: 'UTF-8 텍스트 파일인지 확인해주세요.',
  INVALID_JSON: 'JSON 문법 또는 중복된 object key를 확인해주세요.',
  INVALID_DOCUMENT: '이벤트 내보내기 JSON의 형식·필드·건수를 확인해주세요.',
  TOO_MANY_OUTCOMES: '이벤트 행이 1,000건 한도를 넘습니다.',
  FILTER_MISMATCH: '파일의 검색 조건과 담긴 이벤트가 일치하지 않습니다.',
  READ_FAILED: '파일을 읽지 못했습니다. 파일 접근 상태를 확인해주세요.',
};

function FileSource({ file }: { file: OfflineEventFile }) {
  const { document } = file;
  return <section className="oev-source" aria-label="현재 표시하는 파일의 기록">
    <h3>현재 표시하는 파일</h3>
    <dl className="oev-fields">
      <div><dt>파일 이름</dt><dd><code>{raw(file.name)}</code></dd></div>
      <div><dt>읽은 파일 크기</dt><dd>{count(file.byteLength)} bytes</dd></div>
      <div><dt>schemaVersion</dt><dd>{document.schemaVersion}</dd></div>
      <div><dt>파일에 저장된 행</dt><dd>{count(document.outcomes.length)}건</dd></div>
    </dl>
    <p className="oev-note">출처·mode·시각은 파일에 기록된 값입니다. mode가 live여도 현재 API 응답이 아니며, 파일의 진위·현재 API 상태·원본을 인증하지 않습니다.</p>
    <details><summary>파일에 기록된 출처·건수·원래 검색 조건</summary>
      <dl className="oev-fields">
        <div><dt>runId</dt><dd><code>{raw(document.source.runId)}</code></dd></div>
        <div><dt>mode</dt><dd><code>{raw(document.source.mode)}</code></dd></div>
        <div><dt>observedAt</dt><dd><code>{raw(document.source.observedAt)}</code></dd></div>
        <div><dt>capturedAt</dt><dd><code>{raw(document.source.capturedAt)}</code></dd></div>
        <div><dt>reportedInputCount · 보고된 원입력</dt><dd>{count(document.counts.reportedInputCount)}건</dd></div>
        <div><dt>availableOutcomes · 저장 당시 조회된 행</dt><dd>{count(document.counts.availableOutcomes)}건</dd></div>
        <div><dt>matchedOutcomes · 원래 조건에 맞아 저장된 행</dt><dd>{count(document.counts.matchedOutcomes)}건</dd></div>
        <div><dt>status 조건</dt><dd><code>{raw(document.filters.status)}</code></dd></div>
        <div><dt>query 조건</dt><dd><code>{raw(document.filters.query)}</code></dd></div>
        <div><dt>reason 조건</dt><dd><code>{raw(document.filters.reason)}</code>{document.filters.reason === null ? ' · 전체 사유' : ' · 원문 정확 조건'}</dd></div>
        <div><dt>sensorId 조건</dt><dd>{document.schemaVersion === 2
          ? <><code>{raw(document.filters.sensorId)}</code> · 원문 정확 조건</> : '필드 없음 · 전체 센서 (schemaVersion 1)'}</dd></div>
      </dl>
      <p className="oev-note">세 건수는 서로 다른 범위입니다. 원래 검색 결과 중 일부만 담긴 파일일 수 있으며, 세 건수가 같아도 원본 전체를 빠짐없이 담았다는 증명은 아닙니다.</p>
    </details>
  </section>;
}

export function OfflineEventViewerResult({ file, view, interactive, onViewChange }: {
  file: OfflineEventFile;
  view: OfflineViewerView;
  interactive: boolean;
  onViewChange: (change: Partial<OfflineViewerView>) => void;
}) {
  const id = useId();
  const detailHeading = useRef<HTMLHeadingElement>(null);
  const { outcomes } = file.document;
  // Preserve each original array position: sequence and eventId may both repeat.
  const matches = new Set(filterEventOutcomes(outcomes, view.filters));
  const matching = outcomes.map((outcome, index) => ({ outcome, index })).filter(row => matches.has(row.outcome));
  const page = eventPage(matching.map(row => row.outcome), view.pageIndex, view.pageSize);
  const reasons = eventReasonOptions(outcomes);
  const sensors = [...new Set(outcomes.map(outcome => outcome.sensorId))];
  const selected = view.selectedIndex !== null && Number.isInteger(view.selectedIndex) && view.selectedIndex >= 0
    ? outcomes[view.selectedIndex] : undefined;
  const selectedPosition = matching.findIndex(row => row.index === view.selectedIndex);
  const selectedPage = selectedPosition < 0 ? null : Math.floor(selectedPosition / view.pageSize);
  const update = (change: Partial<OfflineViewerView>) => { if (interactive) onViewChange(change); };
  const changeFilters = (change: Partial<EventSearchFilters>) => update({ filters: { ...view.filters, ...change }, pageIndex: 0, selectedIndex: null });

  useEffect(() => {
    if (selected) detailHeading.current?.focus();
  }, [file, view.selectedIndex]);

  return <section className="oev-result" aria-labelledby={`${id}-title`}>
    <h2 id={`${id}-title`}>저장된 이벤트 탐색</h2>
    <FileSource file={file} />
    <fieldset className="oev-search" disabled={!interactive}>
      <legend>이 화면에서 찾기</legend>
      <div className="oev-controls">
        <div><label htmlFor={`${id}-query`}>eventId·sensorId 포함 검색</label>
          <input id={`${id}-query`} type="search" value={view.filters.query} placeholder="예: event-1 또는 sensor-1"
            aria-describedby={`${id}-search-help`} onChange={event => changeFilters({ query: event.target.value })} /></div>
        <div><label htmlFor={`${id}-status`}>화면 status 조건</label>
          <select id={`${id}-status`} value={view.filters.status} onChange={event => changeFilters({ status: event.target.value as EventSearchFilters['status'] })}>
            <option value="ALL">전체 상태</option>{(['SUCCESS', 'FAILED', 'DUPLICATE', 'PENDING'] as const).map(status => <option value={status} key={status}>{status}</option>)}
          </select></div>
        <div><label htmlFor={`${id}-reason`}>reason 원문 정확 검색</label>
          <select id={`${id}-reason`} value={view.filters.reason === null ? 'all' : `reason:${view.filters.reason}`}
            onChange={event => changeFilters({ reason: event.target.value === 'all' ? null : event.target.value.slice('reason:'.length) })}>
            <option value="all">전체 사유</option>{reasons.map(reason => <option value={`reason:${reason}`} key={reason}>{raw(reason)}{reason === '' ? ' · 빈 문자열' : ''}</option>)}
          </select></div>
        <div><label htmlFor={`${id}-sensor`}>sensorId 원문 정확 검색</label>
          <select id={`${id}-sensor`} value={view.filters.sensorId == null ? 'all' : `sensor:${view.filters.sensorId}`}
            onChange={event => changeFilters({ sensorId: event.target.value === 'all' ? null : event.target.value.slice('sensor:'.length) })}>
            <option value="all">전체 센서</option>{sensors.map(sensor => <option value={`sensor:${sensor}`} key={sensor}>{raw(sensor)}{sensor === '' ? ' · 빈 문자열' : ''}</option>)}
          </select></div>
      </div>
      <p id={`${id}-search-help`} className="oev-note">포함 검색은 앞뒤 공백을 제외하고 대소문자 구분 없이 찾습니다. status·reason·sensorId 조건을 함께 적용합니다.
        이 화면 조건은 파일에 기록된 원래 검색 조건과 별개이며, 파일에 저장된 행만 검색합니다.</p>
      <button type="button" onClick={() => update({ filters: initialOfflineViewerView().filters, pageIndex: 0, selectedIndex: null })}>화면 조건 초기화</button>
    </fieldset>
    <p className="oev-status" role="status" aria-live="polite" aria-atomic="true">파일 행 {count(outcomes.length)}건 중 화면 조건 일치 {count(page.total)}건 · 표시 {count(page.start)}–{count(page.end)}번째</p>
    <p className="oev-note">파일에 저장된 행 순서와 중복을 그대로 표시합니다. 파일 행 번호는 이 파일 안의 위치이며 sequence·eventId와 다릅니다.</p>
    <nav className="oev-pagination" aria-label="저장된 이벤트 페이지">
      <div><label htmlFor={`${id}-page-size`}>페이지당 행 수</label>
        <select id={`${id}-page-size`} value={view.pageSize} disabled={!interactive}
          onChange={event => update({ pageSize: Number(event.target.value) as EventPageSize, pageIndex: 0 })}>
          {EVENT_PAGE_SIZES.map(size => <option key={size} value={size}>{size}행</option>)}
        </select></div>
      <p>{page.totalPages === 0 ? '0 / 0' : `${page.index + 1} / ${page.totalPages}`} 페이지</p>
      <div className="oev-actions">
        <button type="button" disabled={!interactive || page.index === 0} onClick={() => update({ pageIndex: page.index - 1 })}>이전 페이지</button>
        <button type="button" disabled={!interactive || page.index + 1 >= page.totalPages} onClick={() => update({ pageIndex: page.index + 1 })}>다음 페이지</button>
      </div>
    </nav>
    {page.total === 0 ? <p className="oev-empty">{outcomes.length === 0
      ? '이 파일에는 저장된 이벤트 행이 없습니다. 보고된 원입력·조회 행 수가 0건이라는 뜻은 아닙니다.'
      : '화면 조건에 맞는 행이 없습니다. 화면 조건을 바꾸거나 초기화해 저장된 행을 다시 살펴보세요.'}</p>
      : <div className="oev-table-wrap" role="region" aria-label="저장된 이벤트 행 목록" tabIndex={0}>
        <table className="oev-table"><caption>현재 페이지의 저장된 행 · 원문 상세는 행별 버튼으로 확인</caption>
          <thead><tr><th scope="col">파일 행</th><th scope="col">sequence</th><th scope="col">eventId</th><th scope="col">sensorId</th><th scope="col">status</th><th scope="col">reason</th><th scope="col">원문</th></tr></thead>
          <tbody>{page.rows.map((outcome, offset) => {
            const index = matching[page.start - 1 + offset].index;
            return <tr key={index} data-file-row={index + 1} className={view.selectedIndex === index ? 'oev-row-selected' : undefined}>
              <th scope="row">{count(index + 1)}</th><td><code>{raw(outcome.sequence)}</code></td><td><code>{raw(outcome.eventId)}</code></td>
              <td><code>{raw(outcome.sensorId)}</code></td><td><code>{raw(outcome.status)}</code></td><td><code>{raw(outcome.reason)}</code></td>
              <td><button type="button" disabled={!interactive} aria-label={`파일 행 ${index + 1} 원문 보기`} aria-pressed={view.selectedIndex === index}
                aria-controls={`${id}-detail`} onClick={() => update({ selectedIndex: index })}>원문 보기</button></td>
            </tr>;
          })}</tbody>
        </table>
      </div>}
    <section id={`${id}-detail`} className="oev-detail" aria-labelledby={`${id}-detail-title`}>
      <h3 id={`${id}-detail-title`} ref={detailHeading} tabIndex={-1}>{selected ? `파일 행 ${count(view.selectedIndex! + 1)} 원문 상세` : '선택한 행의 원문 상세'}</h3>
      {selected ? <>
        <dl className="oev-fields">{(['sequence', 'eventId', 'sensorId', 'eventTime', 'value', 'status', 'reason'] as const).map(field =>
          <div key={field}><dt>{field}</dt><dd><code>{raw(selected[field])}</code></dd></div>)}</dl>
        <p className="oev-note">문자열은 따옴표와 이스케이프를 포함해 표시합니다. eventTime은 시간대를 변환하지 않은 파일 값입니다.
          value가 null이면 원래 null인지, 저장 전 NaN·Infinity 등이었는지 복원할 수 없습니다.</p>
        <div className="oev-actions">
          {selectedPage !== null && selectedPage !== page.index && <button type="button" disabled={!interactive} onClick={() => update({ pageIndex: selectedPage })}>선택한 행의 페이지로 이동</button>}
          <button type="button" disabled={!interactive} onClick={() => update({ selectedIndex: null })}>행 선택 해제</button>
        </div>
      </> : <p className="oev-note">목록에서 원문 보기를 선택하면 해당 파일 행의 모든 필드를 확인할 수 있습니다.</p>}
    </section>
  </section>;
}

export default function OfflineEventViewer() {
  const id = useId();
  const [ready, setReady] = useState(false);
  const [draft, setDraft] = useState<File | null>(null);
  const [file, setFile] = useState<OfflineEventFile | null>(null);
  const [view, setView] = useState(initialOfflineViewerView);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [inputKey, setInputKey] = useState(0);
  const inFlight = useRef(false);
  const mounted = useRef(false);
  const readRevision = useRef(0);
  const currentFile = useRef<OfflineEventFile | null>(null);
  const locked = !ready || busy;

  useEffect(() => {
    mounted.current = true;
    setReady(true);
    return () => { mounted.current = false; readRevision.current += 1; inFlight.current = false; };
  }, []);

  function selectFile(next: File | null) {
    if (!mounted.current || locked || inFlight.current) return;
    setDraft(next);
    setError('');
  }

  function updateView(expectedFile: OfflineEventFile, change: Partial<OfflineViewerView>) {
    if (!mounted.current || locked || inFlight.current || currentFile.current !== expectedFile) return;
    setView(current => ({ ...current, ...change }));
  }

  function clearFiles() {
    if (!mounted.current || locked || inFlight.current) return;
    currentFile.current = null;
    setDraft(null); setFile(null); setView(initialOfflineViewerView()); setError('');
    setInputKey(current => current + 1);
  }

  async function openFile() {
    if (!mounted.current || locked || inFlight.current || draft === null) return;
    inFlight.current = true;
    const revision = ++readRevision.current;
    setBusy(true); setError('');
    try {
      const result = await readOfflineEventFile(draft);
      if (!mounted.current || revision !== readRevision.current) return;
      if (!result.ok) { setError(errorMessages[result.code]); return; }
      currentFile.current = result.file;
      setFile(result.file);
      setView(initialOfflineViewerView());
    } catch {
      if (mounted.current && revision === readRevision.current) setError(errorMessages.READ_FAILED);
    } finally {
      if (revision === readRevision.current) {
        inFlight.current = false;
        if (mounted.current) setBusy(false);
      }
    }
  }

  return <div className="offline-event-viewer">
    <section className="oev-input-section" aria-labelledby={`${id}-title`}>
      <h2 id={`${id}-title`}>이벤트 JSON 파일 열기</h2>
      <p>이벤트 내보내기 JSON schemaVersion 1·2 파일 한 개를 읽습니다. 파일당 최대 {count(MAX_OFFLINE_FILE_BYTES)} bytes(1 MiB), 이벤트 최대 {count(MAX_OFFLINE_OUTCOMES)}건입니다. 비교 보고서는 열 수 없습니다.</p>
      <label htmlFor={`${id}-file`}>열 파일 선택</label>
      <input key={inputKey} id={`${id}-file`} type="file" accept=".json,application/json" disabled={locked}
        aria-describedby={`${id}-file-help`} onChange={event => selectFile(event.target.files?.[0] ?? null)} />
      <p id={`${id}-file-help`} className="oev-note">파일 선택만으로 읽지 않습니다. 아래 열기 버튼을 눌러야 표시 결과를 바꿉니다. 새 파일 읽기에 실패하면 이전 결과와 화면 조건을 유지합니다.</p>
      <p className="oev-draft">열기 대기: {draft ? <code>{raw(draft.name)}</code> : '선택한 파일 없음'}</p>
      <div className="oev-actions">
        <button type="button" disabled={locked || draft === null} onClick={openFile}>선택한 파일 열기</button>
        <button type="button" disabled={locked} onClick={clearFiles}>선택·표시 모두 비우기</button>
      </div>
      <p className="oev-status" role="status" aria-live="polite" aria-atomic="true">{busy ? '선택한 파일을 읽고 검증하고 있습니다.' : !ready ? '파일 읽기 화면을 준비하고 있습니다.' : ''}</p>
      {error && <p className="oev-error" role="alert">{error} {file ? '이전에 연 파일을 계속 표시합니다.' : '아직 표시할 파일이 없습니다.'}</p>}
      <p className="oev-note">파일을 서버에 업로드하거나 브라우저 저장소에 보관하지 않습니다. 비우기는 화면의 선택과 결과를 제거하며 원파일을 삭제하지 않습니다.
        페이지를 처음 여는 데 필요한 정적 파일은 연결이 필요할 수 있으며, 오프라인 설치 앱(PWA)을 뜻하지 않습니다.</p>
    </section>
    {file ? <OfflineEventViewerResult file={file} view={view} interactive={!locked} onViewChange={change => updateView(file, change)} />
      : <p className="oev-empty">아직 연 파일이 없습니다. JSON 파일을 선택한 뒤 선택한 파일 열기를 눌러주세요.</p>}
  </div>;
}
