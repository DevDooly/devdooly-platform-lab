import { useEffect, useState } from 'react';
import { evidenceItems, evidenceScopes, evidenceTopics } from '../data/evidence-index';
import { changeEvidenceFilters, evidencePage, EVIDENCE_PAGE_SIZE, filterEvidence, initialEvidenceView, MAX_EVIDENCE_QUERY_LENGTH, showMoreEvidence } from '../lib/evidence-search';
import type { EvidenceView } from '../lib/evidence-search';
import '../styles/evidence-explorer.css';

/** Curated historical links only. Local search never calls an API or changes evidence. */
export default function EvidenceExplorer() {
  const [interactive, setInteractive] = useState(false);
  const [view, setView] = useState(initialEvidenceView);
  useEffect(() => { setInteractive(true); }, []);
  const matched = filterEvidence(evidenceItems, view);
  const page = evidencePage(matched, view);
  return <section id="evidence" className="section evidence-section" aria-labelledby="evidence-title">
    <div className="section-heading evidence-heading"><div>
      <span className="eyebrow">EVIDENCE / FIND BY SKILL</span>
      <h2 id="evidence-title">어떤 기술을, 어디까지 검증했는지.</h2>
      <p>개인 Lab의 구현과 공개 검증 기록을 기술별로 찾습니다.</p>
    </div><a className="text-link" href="#progress">구축 기록 보기 ↗</a></div>
    <p id="evidence-filter-hint" className="evidence-intro">검색어와 두 필터를 함께 적용합니다. 여러 단어는 모두 포함된 기록을 찾으며, 공개 기록과 후속 연결 대기를 구분합니다.</p>
    <div className="evidence-filters" aria-busy={!interactive}>
      <label className="evidence-search" htmlFor="evidence-search">검색어<input id="evidence-search" type="search" disabled={!interactive} placeholder={interactive ? '예: Kafka' : '검색 준비 중…'}
        maxLength={MAX_EVIDENCE_QUERY_LENGTH} aria-describedby="evidence-filter-hint" aria-controls="evidence-results" value={view.query}
        onChange={event => setView(current => changeEvidenceFilters(current, { query: event.target.value }))} /></label>
      <label htmlFor="evidence-topic">기술<select id="evidence-topic" disabled={!interactive} aria-describedby="evidence-filter-hint" aria-controls="evidence-results" value={view.topic}
        onChange={event => setView(current => changeEvidenceFilters(current, { topic: event.target.value as EvidenceView['topic'] }))}>
        <option value="all">모든 기술</option>{evidenceTopics.map(option => <option key={option.id} value={option.id}>{option.label}</option>)}
      </select></label>
      <label htmlFor="evidence-scope">검증 환경<select id="evidence-scope" disabled={!interactive} aria-describedby="evidence-filter-hint" aria-controls="evidence-results" value={view.scope}
        onChange={event => setView(current => changeEvidenceFilters(current, { scope: event.target.value as EvidenceView['scope'] }))}>
        <option value="all">모든 환경</option>{evidenceScopes.map(option => <option key={option.id} value={option.id}>{option.label}</option>)}
      </select></label>
      <button className="button button-small evidence-reset" type="button" disabled={!interactive} onClick={() => setView(initialEvidenceView())}>조건 초기화</button>
    </div>
    <p className="evidence-count" role="status" aria-live="polite" aria-atomic="true">조건에 맞는 {page.total}개 중 {page.shown}개 표시 · 공개 기록 {matched.filter(item => item.state === 'verified').length}개 · 연결 대기 {matched.filter(item => item.state === 'pending').length}개</p>
    {page.total === 0 ? <p id="evidence-results" className="evidence-empty">{view.query.trim() ? <>“{view.query.trim()}”에 맞는</> : '선택한 조건에 맞는'} 공개 기록이 없습니다. 검색어를 바꾸거나 조건 초기화로 다른 기록을 살펴보세요.</p>
      : <ul id="evidence-results" className="evidence-grid">{page.items.map(item => <li key={item.id}>
        <article className={`evidence-card${item.state === 'pending' ? ' evidence-card-pending' : ''}`} aria-labelledby={`evidence-title-${item.id}`}>
          <div className="evidence-card-meta"><span className="evidence-scope">{evidenceScopes.find(option => option.id === item.scope)!.label}</span>
            <span className="evidence-state">{item.state === 'pending' ? '연결 대기' : (item.recordLabel ?? '검증 기록')}</span></div>
          <h3 id={`evidence-title-${item.id}`}>{item.title}</h3>
          <p>{item.description}</p>
          <p className="evidence-boundary"><strong>확인 범위</strong> {item.boundary}</p>
          <p className="evidence-date">{item.recordedOn ? <>근거 문서 기준 <time dateTime={item.recordedOn}>{item.recordedOn}</time> · 현재 상태와 구분</> : '후속 검증 결과 대기'}</p>
          <ul className="evidence-links" aria-label={`${item.title} 관련 링크`}>
            <li><a href={item.source} target="_blank" rel="noreferrer">구현과 설계 <span aria-hidden="true">↗</span><span className="sr-only"> 새 창</span></a></li>
            <li><a href={item.evidence} target="_blank" rel="noreferrer">{item.evidenceLabel ?? '검증 근거'} <span aria-hidden="true">↗</span><span className="sr-only"> 새 창</span></a></li>
            {item.screen && <li><a href={item.screen}>{item.screen.startsWith('#') ? '관련 화면' : '사례 읽기'} <span aria-hidden="true">{item.screen.startsWith('#') ? '↓' : '→'}</span></a></li>}
          </ul>
        </article>
      </li>)}</ul>}
    {page.showMoreButton && <div className="evidence-more">
      <button className="button" type="button" disabled={!interactive} aria-controls="evidence-results" aria-disabled={!page.hasMore}
        onClick={() => { if (page.hasMore) setView(current => showMoreEvidence(current, matched.length)); }}>
        {page.hasMore ? `${Math.min(EVIDENCE_PAGE_SIZE, page.remaining)}개 더 보기` : '조건에 맞는 기록을 모두 표시했습니다'}
      </button>
    </div>}
  </section>;
}
