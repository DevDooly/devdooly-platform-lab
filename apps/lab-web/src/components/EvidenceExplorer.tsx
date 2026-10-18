import { useState } from 'react';
import { evidenceItems, evidenceScopes, evidenceTopics } from '../data/evidence-index';
import type { EvidenceTopic } from '../data/evidence-index';
import '../styles/evidence-explorer.css';

/** Filtering curated public links only. No API calls, runtime actions, or live-state claims. */
export default function EvidenceExplorer() {
  const [topic, setTopic] = useState('all');
  const [scope, setScope] = useState('all');
  const visible = evidenceItems.filter(item => (topic === 'all' || item.topics.includes(topic as EvidenceTopic))
    && (scope === 'all' || item.scope === scope));
  return <section id="evidence" className="section evidence-section" aria-labelledby="evidence-title">
    <div className="section-heading evidence-heading"><div>
      <span className="eyebrow">EVIDENCE / FIND BY SKILL</span>
      <h2 id="evidence-title">어떤 기술을, 어디까지 검증했는지.</h2>
      <p>개인 Lab의 구현과 공개 검증 기록을 기술별로 찾습니다.</p>
    </div><a className="text-link" href="#progress">구축 기록 보기 ↗</a></div>
    <p id="evidence-filter-hint" className="evidence-intro">검증 환경과 당시의 범위를 함께 표시합니다. 두 필터를 함께 적용하며, 공개 기록과 후속 연결 대기를 구분합니다.</p>
    <div className="evidence-filters">
      <label htmlFor="evidence-topic">기술<select id="evidence-topic" aria-describedby="evidence-filter-hint" aria-controls="evidence-results" value={topic} onChange={event => setTopic(event.target.value)}>
        <option value="all">모든 기술</option>{evidenceTopics.map(option => <option key={option.id} value={option.id}>{option.label}</option>)}
      </select></label>
      <label htmlFor="evidence-scope">검증 환경<select id="evidence-scope" aria-describedby="evidence-filter-hint" aria-controls="evidence-results" value={scope} onChange={event => setScope(event.target.value)}>
        <option value="all">모든 환경</option>{evidenceScopes.map(option => <option key={option.id} value={option.id}>{option.label}</option>)}
      </select></label>
      <button className="button button-small evidence-reset" type="button" onClick={() => { setTopic('all'); setScope('all'); }}>전체 보기</button>
    </div>
    <p className="evidence-count" role="status" aria-live="polite" aria-atomic="true">조건에 맞는 항목 {visible.length}개 · 공개 기록 {visible.filter(item => item.state === 'verified').length}개 · 연결 대기 {visible.filter(item => item.state === 'pending').length}개</p>
    {visible.length === 0 ? <p id="evidence-results" className="evidence-empty">선택한 기술과 환경에 해당하는 공개 기록이 없습니다. 전체 보기로 돌아가 다른 기록을 살펴보세요.</p>
      : <ul id="evidence-results" className="evidence-grid">{visible.map(item => <li key={item.id}>
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
            <li><a href={item.screen}>관련 화면 <span aria-hidden="true">↓</span></a></li>
          </ul>
        </article>
      </li>)}</ul>}
  </section>;
}
