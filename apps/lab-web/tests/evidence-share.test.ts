import assert from 'node:assert/strict';
import { test } from 'node:test';
import { buildEvidenceShareUrl, parseEvidenceShareUrl } from '../src/lib/evidence-share.ts';
import { evidenceScopes, evidenceTopics } from '../src/data/evidence-index.ts';
import { evidenceQueryWords, initialEvidenceView } from '../src/lib/evidence-search.ts';

const base = 'https://devdooly.github.io/devdooly-platform-lab/';

test('a share link retains only the HTTP(S) origin/path and its three owned conditions', () => {
  const original = { query: '수집기 Pages', topic: 'delivery' as const, scope: 'mini-pc' as const, limit: 18 };
  const link = buildEvidenceShareUrl('https://user:password@example.com:8443/lab/%2F%3F%23?token=omit&limit=18#old', original)!;
  const url = new URL(link);
  assert.equal(url.origin, 'https://example.com:8443'); assert.equal(url.pathname, '/lab/%2F%3F%23');
  assert.equal(url.username, ''); assert.equal(url.password, ''); assert.equal(url.hash, '#evidence');
  assert.deepEqual([...url.searchParams.keys()], ['evidenceQuery', 'evidenceTopic', 'evidenceScope']);
  assert.deepEqual(parseEvidenceShareUrl(link), { ...original, limit: 6 });
  assert.equal(original.limit, 18);
});

test('missing conditions use defaults and unrelated parameters or page limits are never restored', () => {
  for (const link of [base, base + '?limit=600&query=Kafka&topic=java#other']) {
    assert.deepEqual(parseEvidenceShareUrl(link), initialEvidenceView());
  }
  assert.deepEqual(parseEvidenceShareUrl(base + '?evidenceQuery=Kafka&unrelated=1&limit=600'),
    { query: 'Kafka', topic: 'all', scope: 'all', limit: 6 });
  assert.equal(new URL(buildEvidenceShareUrl('http://localhost:4321/lab?unrelated=1#old', initialEvidenceView())!).origin,
    'http://localhost:4321');
});

test('all declared topic and scope IDs round-trip without inventing another taxonomy', () => {
  for (const topic of ['all', ...evidenceTopics.map(item => item.id)] as const) {
    for (const scope of ['all', ...evidenceScopes.map(item => item.id)] as const) {
      const view = { query: 'KAFKA Cloud', topic, scope, limit: 6 };
      assert.deepEqual(parseEvidenceShareUrl(buildEvidenceShareUrl(base, view)!), view);
    }
  }
});

test('any duplicate owned key resets the whole share, including encoded or identical duplicates', () => {
  for (const suffix of [
    'evidenceQuery=A&evidenceQuery=A', 'evidenceQuery=A&evidenceQuery=B',
    'evidenceTopic=java&evidence%54opic=java', 'evidenceScope=cloud&evidenceScope=invalid',
  ]) assert.deepEqual(parseEvidenceShareUrl(base + '?evidenceQuery=valid&' + suffix), initialEvidenceView());
});

test('invalid or empty enum values reset all conditions instead of silently widening one filter', () => {
  for (const suffix of ['evidenceTopic=', 'evidenceTopic=Java', 'evidenceTopic=__proto__',
    'evidenceScope=MINI_PC', 'evidenceScope=cloud%20', 'evidenceScope=']) {
    assert.deepEqual(parseEvidenceShareUrl(base + '?evidenceQuery=valid&' + suffix), initialEvidenceView());
  }
  assert.equal(buildEvidenceShareUrl(base, { query: '', topic: 'invalid', scope: 'all' } as never), null);
});

test('query punctuation, literal plus, spaces and Unicode are encoded and decoded once', () => {
  for (const query of ['한글 & ? # % +', 'literal+plus space', '%2B %252B', '　ＫＡＦＫＡ　Cloud', 'a'.repeat(199) + 'ﬃ']) {
    const restored = parseEvidenceShareUrl(buildEvidenceShareUrl(base, { query, topic: 'all', scope: 'all' })!);
    assert.equal(restored.query, query);
    assert.deepEqual(evidenceQueryWords(restored.query), evidenceQueryWords(query));
  }
  assert.equal(parseEvidenceShareUrl(base + '?evidenceQuery=%252B').query, '%2B');
  assert.equal(parseEvidenceShareUrl(base + '?evidenceQuery=%2B+').query, '+ ');
  assert.equal(parseEvidenceShareUrl(base + '?evidenceQuery=%').query, '%');
  assert.equal(parseEvidenceShareUrl(base + '?evidenceQuery=%FF').query, '\uFFFD');
});

test('the 200 UTF-16 ceiling precedes NFKC and URL USV coercion is stable at a split surrogate', () => {
  const complete = 'a'.repeat(198) + '😀';
  assert.equal(parseEvidenceShareUrl(buildEvidenceShareUrl(base, { query: complete, topic: 'all', scope: 'all' })!).query, complete);
  const split = 'a'.repeat(199) + '😀';
  const view = parseEvidenceShareUrl(buildEvidenceShareUrl(base, { query: split, topic: 'all', scope: 'all' })!);
  assert.equal(view.query, 'a'.repeat(199) + '\uFFFD'); assert.equal(view.query.length, 200);
  assert.deepEqual(parseEvidenceShareUrl(buildEvidenceShareUrl(base, view)!), view);
  const encodedLong = new URL(base); encodedLong.searchParams.set('evidenceQuery', 'x'.repeat(1000));
  assert.equal(parseEvidenceShareUrl(encodedLong.href).query, 'x'.repeat(200));
});

test('non-web and relative URLs cannot produce or restore a share link', () => {
  for (const invalid of ['/relative', '//example.com/lab', 'javascript:alert(1)', 'file:///tmp/lab', 'data:text/plain,hello', 'not a URL']) {
    assert.equal(buildEvidenceShareUrl(invalid, initialEvidenceView()), null);
    assert.deepEqual(parseEvidenceShareUrl(invalid), initialEvidenceView());
  }
});
