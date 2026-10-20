import { evidenceScopes, evidenceTopics } from '../data/evidence-index.ts';
import type { EvidenceItem, EvidenceScope, EvidenceTopic } from '../data/evidence-index.ts';

export const EVIDENCE_PAGE_SIZE = 6;
export const MAX_EVIDENCE_QUERY_LENGTH = 200;

export interface EvidenceView {
  query: string;
  topic: EvidenceTopic | 'all';
  scope: EvidenceScope | 'all';
  limit: number;
}
type EvidenceFilters = Pick<EvidenceView, 'query' | 'topic' | 'scope'>;

export function initialEvidenceView(): EvidenceView {
  return { query: '', topic: 'all', scope: 'all', limit: EVIDENCE_PAGE_SIZE };
}

function normalized(value: string): string {
  return value.normalize('NFKC').toLowerCase();
}

export function evidenceQueryWords(query: string): string[] {
  return normalized(query.slice(0, MAX_EVIDENCE_QUERY_LENGTH)).trim().split(/\s+/u).filter(Boolean);
}

/** Search only curated descriptions and visible taxonomy labels, never boundaries or URLs. */
export function filterEvidence(items: readonly EvidenceItem[], filters: EvidenceFilters): EvidenceItem[] {
  const words = evidenceQueryWords(filters.query);
  return items.filter(item => {
    if (filters.topic !== 'all' && !item.topics.includes(filters.topic)) return false;
    if (filters.scope !== 'all' && item.scope !== filters.scope) return false;
    const topicLabels = item.topics.map(id => evidenceTopics.find(topic => topic.id === id)!.label);
    const scopeLabel = evidenceScopes.find(scope => scope.id === item.scope)!.label;
    const text = normalized([item.title, item.description, ...topicLabels, scopeLabel].join(' '));
    return words.every(word => text.includes(word));
  });
}

export function changeEvidenceFilters(view: EvidenceView, change: Partial<EvidenceFilters>): EvidenceView {
  return { ...view, ...change, query: (change.query ?? view.query).slice(0, MAX_EVIDENCE_QUERY_LENGTH), limit: EVIDENCE_PAGE_SIZE };
}

export function evidencePage<T>(matched: readonly T[], view: EvidenceView) {
  const items = matched.slice(0, view.limit);
  return { items, total: matched.length, shown: items.length, remaining: matched.length - items.length,
    hasMore: items.length < matched.length, showMoreButton: matched.length > EVIDENCE_PAGE_SIZE };
}

export function showMoreEvidence(view: EvidenceView, matchedTotal: number): EvidenceView {
  if (view.limit >= matchedTotal) return view;
  return { ...view, limit: Math.min(view.limit + EVIDENCE_PAGE_SIZE, matchedTotal) };
}
