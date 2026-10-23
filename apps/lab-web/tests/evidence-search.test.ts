import assert from 'node:assert/strict';
import { test } from 'node:test';
import { evidenceItems } from '../src/data/evidence-index.ts';
import type { EvidenceItem } from '../src/data/evidence-index.ts';
import {
  changeEvidenceFilters, evidencePage, evidenceQueryWords, filterEvidence,
  initialEvidenceView, MAX_EVIDENCE_QUERY_LENGTH, showMoreEvidence,
} from '../src/lib/evidence-search.ts';

function search(query: string, change: Parameters<typeof changeEvidenceFilters>[1] = {}) {
  return filterEvidence(evidenceItems, changeEvidenceFilters(initialEvidenceView(), { query, ...change })).map(item => item.id);
}

function fixture(id: string, overrides: Partial<EvidenceItem> = {}): EvidenceItem {
  return { id, topics: ['java'], scope: 'cloud', state: 'verified', title: `표제 ${id}`,
    description: '검색 설명', boundary: '확인 범위', recordedOn: '2026-10-20',
    source: 'https://example.invalid/source', evidence: 'https://example.invalid/evidence', ...overrides };
}

test('Jenkins와 잠금은 각각 실제 관련 기록을 찾는다', () => {
  assert.deepEqual(search('Jenkins'), ['github-app-natural-renewal', 'delivery-gate']);
  assert.deepEqual(search('잠금'), ['runtime-lease-loss']);
  assert.deepEqual(search('Java 잠금'), ['runtime-lease-loss']);
  assert.deepEqual(search('Kafka 잠금'), []);
});

test('Kafka 검색과 Cloud 환경 필터는 교집합의 원래 순서를 유지한다', () => {
  assert.deepEqual(search('Kafka', { scope: 'cloud' }), [
    'invalid-message-runtime', 'export-integrity-runtime', 'offset-commit-recovery',
    'kafka-lag-recovery', 'kafka-isolated', 'kafka-acl-isolated',
  ]);
  assert.deepEqual(search('Kafka', { scope: 'cloud', topic: 'delivery' }), ['kafka-acl-isolated']);
});

test('공백으로 구분한 모든 단어와 보이는 환경 이름을 함께 검색한다', () => {
  assert.deepEqual(search('  KAFKA   ClOuD  '), [
    'invalid-message-runtime', 'export-integrity-runtime', 'offset-commit-recovery',
    'kafka-lag-recovery', 'kafka-isolated', 'kafka-acl-isolated',
  ]);
  assert.deepEqual(search('Windows', { topic: 'java' }), ['ai-java-example']);
  assert.deepEqual(search('Kubernetes Helm'), [
    'current-worker-fixture', 'kubernetes-runtime', 'delivery-gate', 'kafka-mini-pc-pending',
    'public-read-gateway-internal', 'public-read-https',
  ]);
});

test('NFKC와 대소문자 및 여러 종류의 공백을 정규화한다', () => {
  assert.deepEqual(search('　Ｊｅｎｋｉｎｓ　'), ['github-app-natural-renewal', 'delivery-gate']);
  assert.deepEqual(search('\tjenKINS\n'), ['github-app-natural-renewal', 'delivery-gate']);
  assert.deepEqual(evidenceQueryWords('　ＫＡＦＫＡ\n Cloud\t'), ['kafka', 'cloud']);
});

test('빈 검색은 원본 순서와 객체 참조를 유지하며 일치 없음은 빈 배열이다', () => {
  const result = filterEvidence(evidenceItems, initialEvidenceView());
  assert.deepEqual(result.map(item => item.id), evidenceItems.map(item => item.id));
  assert.ok(result.every((item, index) => item === evidenceItems[index]));
  assert.deepEqual(search('찾을수없는고유검색어ZXQ'), []);
  assert.deepEqual(search(' \t\n '), evidenceItems.map(item => item.id));
});

test('확인 범위와 링크 및 상태 라벨은 검색 대상에 포함하지 않는다', () => {
  const item = fixture('hidden-fields', {
    boundary: 'boundary-only-token', source: 'https://example.invalid/source-only-token',
    evidence: 'https://example.invalid/evidence-only-token', screen: '#screen-only-token',
    evidenceLabel: 'evidence-label-only-token', recordLabel: 'record-label-only-token',
  });
  for (const query of ['boundary-only-token', 'source-only-token', 'evidence-only-token',
    'screen-only-token', 'evidence-label-only-token', 'record-label-only-token']) {
    assert.deepEqual(filterEvidence([item], { query, topic: 'all', scope: 'all' }), []);
  }
  assert.deepEqual(filterEvidence([item], { query: '검색 Java Cloud', topic: 'all', scope: 'all' }), [item]);
});

test('문자열 검색은 정규식 문법을 해석하지 않는다', () => {
  const literal = fixture('literal', { title: '문자 a.b [x]' });
  const other = fixture('other', { title: '문자 axb x' });
  assert.deepEqual(filterEvidence([literal, other], { query: 'a.b [x]', topic: 'all', scope: 'all' }), [literal]);
  assert.deepEqual(filterEvidence([literal, other], { query: '.*', topic: 'all', scope: 'all' }), []);
});

test('검색어는 200자까지만 사용하며 조건 상태도 같은 상한을 적용한다', () => {
  assert.equal(MAX_EVIDENCE_QUERY_LENGTH, 200);
  const bounded = changeEvidenceFilters(initialEvidenceView(), { query: 'x'.repeat(200) + 'Jenkins' });
  assert.equal(bounded.query, 'x'.repeat(200));
  assert.deepEqual(evidenceQueryWords(' '.repeat(200) + 'Jenkins'), []);
  assert.deepEqual(evidenceQueryWords('x'.repeat(201)), ['x'.repeat(200)]);
});

test('처음 여섯 개와 더 보기 열두 개 및 마지막 페이지를 구분한다', () => {
  const items = 'abcdefghijklmnopq'.split('').map(id => fixture(id));
  let view = initialEvidenceView();
  let page = evidencePage(items, view);
  assert.equal(page.items.map(item => item.id).join(''), 'abcdef');
  assert.deepEqual({ total: page.total, shown: page.shown, remaining: page.remaining,
    hasMore: page.hasMore, showMoreButton: page.showMoreButton },
  { total: 17, shown: 6, remaining: 11, hasMore: true, showMoreButton: true });
  view = showMoreEvidence(view, items.length);
  page = evidencePage(items, view);
  assert.equal(page.items.map(item => item.id).join(''), 'abcdefghijkl');
  assert.equal(page.shown, 12);
  assert.equal(page.remaining, 5);
  view = showMoreEvidence(view, items.length);
  page = evidencePage(items, view);
  assert.equal(page.items.map(item => item.id).join(''), 'abcdefghijklmnopq');
  assert.deepEqual({ total: page.total, shown: page.shown, remaining: page.remaining,
    hasMore: page.hasMore, showMoreButton: page.showMoreButton },
  { total: 17, shown: 17, remaining: 0, hasMore: false, showMoreButton: true });
  assert.equal(showMoreEvidence(view, items.length), view);
});

test('검색 결과가 여섯 개 이하이면 더 보기 영역이 없다', () => {
  const view = initialEvidenceView();
  for (const count of [0, 1, 6]) {
    const page = evidencePage(Array.from({ length: count }, (_, id) => id), view);
    assert.equal(page.total, count);
    assert.equal(page.shown, count);
    assert.equal(page.remaining, 0);
    assert.equal(page.hasMore, false);
    assert.equal(page.showMoreButton, false);
  }
  assert.equal(evidencePage(Array.from({ length: 7 }, (_, id) => id), view).showMoreButton, true);
});

test('검색어 또는 어느 필터를 바꿔도 표시 개수는 여섯 개로 돌아온다', () => {
  const expanded = { ...initialEvidenceView(), query: 'Kafka', topic: 'java' as const,
    scope: 'cloud' as const, limit: 12 };
  assert.deepEqual(changeEvidenceFilters(expanded, { query: '잠금' }),
    { query: '잠금', topic: 'java', scope: 'cloud', limit: 6 });
  assert.deepEqual(changeEvidenceFilters(expanded, { topic: 'delivery' }),
    { query: 'Kafka', topic: 'delivery', scope: 'cloud', limit: 6 });
  assert.deepEqual(changeEvidenceFilters(expanded, { scope: 'mini-pc' }),
    { query: 'Kafka', topic: 'java', scope: 'mini-pc', limit: 6 });
  assert.equal(expanded.limit, 12);
});

test('초기화는 검색어와 두 필터 및 표시 개수를 함께 복원한다', () => {
  assert.deepEqual(initialEvidenceView(), { query: '', topic: 'all', scope: 'all', limit: 6 });
  assert.notEqual(initialEvidenceView(), initialEvidenceView());
});

test('검색과 페이지 전환은 원본 기록과 상태 및 출처를 바꾸지 않는다', () => {
  const original = JSON.stringify(evidenceItems);
  const view = changeEvidenceFilters(initialEvidenceView(), { query: 'Kafka', scope: 'cloud' });
  const matched = filterEvidence(evidenceItems, view);
  evidencePage(matched, showMoreEvidence(view, matched.length));
  assert.equal(JSON.stringify(evidenceItems), original);
  const legacyId = evidenceItems.find(item => item.id === 'kafka-mini-pc-pending')!;
  assert.equal(legacyId.state, 'verified');
  assert.equal(filterEvidence([legacyId], initialEvidenceView())[0], legacyId);
});
