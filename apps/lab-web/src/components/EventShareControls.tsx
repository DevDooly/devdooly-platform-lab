import { useEffect, useMemo, useRef, useState } from 'react';
import { eventSharePath, type EventShareParseResult, type EventShareSelection } from '../lib/event-share';
import '../styles/event-share.css';

export interface EventShareControlsProps {
  selection: EventShareSelection;
  basePath: string;
  disabled: boolean;
}

export interface EventShareRequestProps {
  request: EventShareParseResult;
  disabled: boolean;
  live: boolean;
  notice: string;
  onApply: () => void;
}

const eventShareStatusLabels = {
  ALL: '전체 상태', SUCCESS: '성공', FAILED: '실패', DUPLICATE: '중복', PENDING: '대기',
} as const;

export function EventShareRequest({ request, disabled, live, notice, onApply }: EventShareRequestProps) {
  if (request.kind === 'absent') return null;
  if (request.kind === 'invalid') return <aside className="event-share-request event-share-invalid" aria-labelledby="event-share-request-title">
    <h3 id="event-share-request-title">공유 링크 확인 필요</h3>
    <p role="status">실행 ID 또는 검색·이벤트 조건을 확인하지 못해 공유한 조건을 적용하지 않았습니다. 현재 표시된 결과는 유지합니다. 올바른 링크를 다시 열거나 아래에서 실행과 조건을 직접 선택하세요.</p>
  </aside>;

  const { runId, filters, sequence } = request.selection;
  return <section className="event-share-request" aria-labelledby="event-share-request-title">
    <h3 id="event-share-request-title">링크로 전달받은 실행·검색 조건</h3>
    <p>아래 버튼으로 해당 실행을 다시 조회한 뒤 조건을 적용합니다. 링크를 만든 시점의 응답이나 관측 시각을 고정한 결과는 아닙니다.</p>
    <dl className="event-share-request-values">
      <div><dt>요청한 실행 · runId</dt><dd><code>{runId}</code></dd></div>
      <div><dt>처리 상태</dt><dd>{eventShareStatusLabels[filters.status]} · <code>{filters.status}</code></dd></div>
      <div><dt>이벤트 ID·센서 검색어</dt><dd>{filters.query === '' ? '빈 검색어 · 전체 ID·센서' : <code>{JSON.stringify(filters.query)}</code>}</dd></div>
      <div><dt>사유 원문</dt><dd>{filters.reason === null ? '전체 사유 · 조건 없음' : filters.reason === '' ? '빈 사유 · 빈 문자열' : <code>{JSON.stringify(filters.reason)}</code>}</dd></div>
      {filters.sensorId != null && <div><dt>센서 ID 정확히 일치</dt><dd><code>{JSON.stringify(filters.sensorId)}</code>{filters.sensorId === '' && ' · 빈 문자열'}</dd></div>}
      <div><dt>선택한 이벤트 · sequence</dt><dd>{sequence === null ? '미선택' : <code>{sequence}</code>}</dd></div>
    </dl>
    {!live && <p className="event-share-unavailable">현재 화면은 게시 관측 또는 고정 샘플입니다. 기존 ‘실시간 조회’로 API 연결을 복구한 뒤 공유한 실행·조건을 조회하세요. 다른 출처의 같은 번호 이벤트를 대신 선택하지 않습니다.</p>}
    <div className="event-share-actions"><button type="button" disabled={disabled || !live} onClick={onApply}>공유한 실행·조건 조회</button></div>
    <p className="event-share-status" role="status" aria-live="polite" aria-atomic="true">{notice || '공유한 조건을 아직 적용하지 않았습니다. 조회 버튼을 눌러 적용하세요.'}</p>
  </section>;
}

export default function EventShareControls({ selection, basePath, disabled }: EventShareControlsProps) {
  const [origin, setOrigin] = useState('');
  const mounted = useRef(false);
  const copyAttempt = useRef(0);
  const sharePath = eventSharePath(selection, basePath);
  const shareUrl = origin && sharePath ? `${origin}${sharePath}` : '';
  const context = useMemo(() => ({}), [
    shareUrl, disabled, selection.runId, selection.filters.status,
    selection.filters.query, selection.filters.reason, selection.filters.sensorId, selection.sequence,
  ]);
  const latestContext = useRef(context);
  latestContext.current = context;
  const [notice, setNotice] = useState<{ context: object; text: string; failed: boolean } | null>(null);
  const currentNotice = notice?.context === context ? notice : null;

  useEffect(() => {
    mounted.current = true;
    setOrigin(window.location.origin);
    return () => { mounted.current = false; copyAttempt.current += 1; };
  }, []);

  async function copyShare() {
    if (disabled || !shareUrl) return;
    const attempt = ++copyAttempt.current;
    const copyContext = context;
    try {
      await navigator.clipboard.writeText(shareUrl);
      if (mounted.current && latestContext.current === copyContext && copyAttempt.current === attempt) {
        setNotice({ context: copyContext, text: '실행·검색 링크를 복사했습니다. 링크를 연 화면의 조회 버튼으로 조건을 적용하세요.', failed: false });
      }
    } catch {
      if (mounted.current && latestContext.current === copyContext && copyAttempt.current === attempt) {
        setNotice({ context: copyContext, text: '링크를 복사하지 못했습니다. 아래 공유 URL을 직접 선택해 복사하세요.', failed: true });
      }
    }
  }

  return <section className="event-share" aria-labelledby="event-share-title">
    <h4 id="event-share-title">실행·검색 조건 공유</h4>
    <p>현재 실행 ID, 검색·처리 상태·사유·센서 조건, 선택한 이벤트 번호를 링크에 담습니다. 링크를 연 화면에서 ‘공유한 실행·조건 조회’를 눌러야 적용됩니다. 응답과 관측 시각은 고정하지 않습니다.</p>
    <p className="event-share-scope">센서 조건: {selection.filters.sensorId == null ? '전체 센서 · 정확 일치 조건 없음' : <>ID 정확히 일치 <code>{JSON.stringify(selection.filters.sensorId)}</code>{selection.filters.sensorId === '' && ' · 빈 문자열'}</>}.</p>
    <p className="event-share-scope">검색어·사유·센서 ID 원문은 URL에 포함됩니다. 현재 표시된 이벤트 행과 출처·시각을 보관하려면 CSV 또는 JSON 다운로드를 이용하세요.</p>
    <div className="event-share-actions"><button type="button" disabled={disabled || !shareUrl} onClick={() => { void copyShare(); }}>실행·검색 링크 복사</button></div>
    <div className="event-share-url"><label htmlFor="event-share-url">실행·검색 공유 URL</label><input id="event-share-url" type="text" readOnly value={shareUrl} disabled={disabled || !shareUrl} autoComplete="off" spellCheck={false} onFocus={event => event.currentTarget.select()} aria-describedby="event-share-url-help" /></div>
    <p className="event-share-help" id="event-share-url-help">복사 버튼을 사용할 수 없으면 URL을 선택한 뒤 직접 복사하세요.</p>
    {!sharePath && <p className="event-share-invalid" role="status">현재 실행·조건으로 유효한 공유 링크를 만들 수 없습니다. 아래 이벤트 결과는 그대로 확인할 수 있습니다.</p>}
    <p className={`event-share-status${currentNotice?.failed ? ' event-share-status-error' : ''}`} role="status" aria-live="polite" aria-atomic="true">{currentNotice?.text ?? ''}</p>
  </section>;
}
