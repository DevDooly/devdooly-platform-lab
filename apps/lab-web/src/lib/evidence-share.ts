import { evidenceScopes, evidenceTopics } from '../data/evidence-index.ts';
import { changeEvidenceFilters, initialEvidenceView, MAX_EVIDENCE_QUERY_LENGTH } from './evidence-search.ts';
import type { EvidenceView } from './evidence-search.ts';

export type EvidenceShareFilters = Pick<EvidenceView, 'query' | 'topic' | 'scope'>;
const keys = ['evidenceQuery', 'evidenceTopic', 'evidenceScope'] as const;
const topic = (value: unknown): value is EvidenceShareFilters['topic'] => typeof value === 'string'
  && (value === 'all' || evidenceTopics.some(item => item.id === value));
const scope = (value: unknown): value is EvidenceShareFilters['scope'] => typeof value === 'string'
  && (value === 'all' || evidenceScopes.some(item => item.id === value));

function webUrl(value: string): URL | null {
  try { const url = new URL(value); return url.protocol === 'http:' || url.protocol === 'https:' ? url : null; }
  catch { return null; }
}

/** Keep raw slice-before-NFKC search semantics; only URL's required USV coercion happens here. */
function sharedQuery(value: string): string {
  const params = new URLSearchParams();
  params.set('query', value.slice(0, MAX_EVIDENCE_QUERY_LENGTH));
  return params.get('query')!;
}

/** Unknown keys are ignored; any duplicate own key or invalid enum resets all filters. */
export function parseEvidenceShareUrl(value: string): EvidenceView {
  const empty = initialEvidenceView();
  const url = webUrl(value);
  if (!url || keys.some(key => url.searchParams.getAll(key).length > 1)) return empty;
  const selectedTopic = url.searchParams.get('evidenceTopic') ?? 'all';
  const selectedScope = url.searchParams.get('evidenceScope') ?? 'all';
  if (!topic(selectedTopic) || !scope(selectedScope)) return empty;
  return changeEvidenceFilters(empty, { query: sharedQuery(url.searchParams.get('evidenceQuery') ?? ''),
    topic: selectedTopic, scope: selectedScope });
}

/** Copy a clean HTTP(S) origin/path: no credentials, existing query/hash or page limit. */
export function buildEvidenceShareUrl(base: string, filters: EvidenceShareFilters): string | null {
  const url = webUrl(base);
  if (!url || typeof filters?.query !== 'string' || !topic(filters.topic) || !scope(filters.scope)) return null;
  url.username = ''; url.password = ''; url.search = ''; url.hash = '';
  const params = new URLSearchParams();
  params.set(keys[0], sharedQuery(filters.query));
  params.set(keys[1], filters.topic); params.set(keys[2], filters.scope);
  url.search = params.toString(); url.hash = 'evidence';
  return url.href;
}
