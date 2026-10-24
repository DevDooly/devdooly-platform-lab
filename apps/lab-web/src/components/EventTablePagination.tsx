import { EVENT_PAGE_SIZES, type EventPage, type EventPageSize } from '../lib/event-pagination';
import '../styles/event-pagination.css';

export interface EventTablePaginationProps {
  page: EventPage;
  pageSize: EventPageSize;
  selectedSequence: number | null;
  selectedPage: number | null;
  disabled: boolean;
  position: 'top' | 'bottom';
  onPageChange: (index: number) => void;
  onPageSizeChange: (size: EventPageSize) => void;
}

export default function EventTablePagination({ page, pageSize, selectedSequence, selectedPage,
  disabled, position, onPageChange, onPageSizeChange }: EventTablePaginationProps) {
  const first = page.totalPages === 0 || page.index === 0;
  const last = page.totalPages === 0 || page.index === page.totalPages - 1;
  const selected = selectedSequence !== null && selectedPage !== null;
  const selectId = `event-page-size-${position}`;
  const count = (value: number) => value.toLocaleString('ko-KR');

  return <nav className="event-pagination" aria-label={`이벤트 표 페이지 · ${position === 'top' ? '위' : '아래'}`}>
    <div className="event-pagination-heading">
      <p className="event-pagination-range">{page.total === 0
        ? '검색 0건 · 표시할 행이 없습니다.'
        : `검색 ${count(page.total)}건 중 ${count(page.start)}–${count(page.end)}행 · ${count(page.index + 1)} / ${count(page.totalPages)}페이지`}</p>
      <div className="event-pagination-size">
        <label htmlFor={selectId}>페이지당 행 수</label>
        <select id={selectId} value={pageSize} disabled={disabled}
          onChange={event => { if (!disabled) onPageSizeChange(Number(event.currentTarget.value) as EventPageSize); }}>
          {EVENT_PAGE_SIZES.map(size => <option key={size} value={size}>{size}행</option>)}
        </select>
      </div>
    </div>
    <div className="event-pagination-actions">
      <button type="button" disabled={disabled || first} onClick={() => onPageChange(0)}>처음</button>
      <button type="button" disabled={disabled || first} onClick={() => onPageChange(page.index - 1)}>이전</button>
      <button type="button" disabled={disabled || last} onClick={() => onPageChange(page.index + 1)}>다음</button>
      <button type="button" disabled={disabled || last} onClick={() => onPageChange(page.totalPages - 1)}>마지막</button>
    </div>
    {selected && <p className="event-pagination-selection">
      <span>선택한 이벤트 {count(selectedSequence)}번 · {selectedPage === page.index
        ? '현재 페이지에 있습니다.' : `${count(selectedPage + 1)}페이지에 있습니다.`}</span>
      {selectedPage !== page.index && <button type="button" disabled={disabled}
        onClick={() => onPageChange(selectedPage)}>선택한 이벤트 행으로 이동</button>}
    </p>}
    {position === 'top' && <p className="event-pagination-scope">표만 페이지로 나눕니다. 흐름 보기와 CSV·JSON 저장은 검색 조건에 맞는 전체 이벤트를 사용합니다.</p>}
  </nav>;
}
