import assert from 'node:assert/strict';
import test from 'node:test';
import type { Outcome, RunDetail } from '../src/lib/api.ts';
import { compareRuns, comparisonCsv, comparisonSharePath, isComparisonRunId, parseComparisonSelection } from '../src/lib/run-comparison.ts';

const outcome = (sequence: number, status: Outcome['status'], reason: string): Outcome => ({
  sequence, status, reason, eventId: 'event-' + sequence, sensorId: 'sensor-1', eventTime: '2026-10-24T00:00:00Z', value: null,
});
const left: RunDetail = {
  id: 'run-a', name: '실행 A', status: 'COMPLETED', synthetic: true, seed: 42,
  inputCount: 10, successCount: 4, failureCount: 3, duplicateCount: 2, pendingCount: 1,
  scenario: 'baseline', description: '합성 입력', observedAt: '2026-10-24T09:01:00+09:00',
  startedAt: '2026-10-24T00:00:00.000Z', completedAt: '2026-10-24T00:01:00.000Z', series: [],
  outcomes: [outcome(1, 'SUCCESS', '범위 오류'), outcome(2, 'SUCCESS', ''), outcome(3, 'SUCCESS', ''), outcome(4, 'SUCCESS', ''),
    outcome(5, 'FAILED', '범위 오류'), outcome(6, 'FAILED', '범위 오류'), outcome(7, 'FAILED', '지연'),
    outcome(8, 'DUPLICATE', '지연'), outcome(9, 'DUPLICATE', ''), outcome(10, 'PENDING', '')],
  failureReasons: [{ reason: '요약을 집계 근거로 사용하지 않음', count: 999 }],
};
const right: RunDetail = {
  ...left, id: 'run-b', name: '실행 B', seed: 43, scenario: 'different-input',
  inputCount: 8, successCount: 4, failureCount: 2, duplicateCount: 1, pendingCount: 1,
  outcomes: [outcome(1, 'SUCCESS', ''), outcome(2, 'SUCCESS', ''), outcome(3, 'SUCCESS', ''), outcome(4, 'SUCCESS', ''),
    outcome(5, 'FAILED', '범위 오류'), outcome(6, 'FAILED', '누락'), outcome(7, 'DUPLICATE', ''), outcome(8, 'PENDING', '')],
  failureReasons: [],
};

test('compares independently expected counts, input rates and FAILED-only reason matrix', () => {
  const comparison = compareRuns(left, right);
  assert.deepEqual(comparison.metrics.map(({ key, left, right, delta }) => [key, left, right, delta]), [
    ['inputCount', 10, 8, -2], ['successCount', 4, 4, 0], ['failureCount', 3, 2, -1],
    ['duplicateCount', 2, 1, -1], ['pendingCount', 1, 1, 0],
  ]);
  assert.deepEqual(comparison.rates.map(({ key, left, right, deltaPercentagePoints }) => [key, left, right, deltaPercentagePoints]), [
    ['success', 40, 50, 10], ['failure', 30, 25, -5],
  ]);
  assert.deepEqual(comparison.failureReasons, [
    { reason: '누락', left: 0, right: 1, delta: 1 }, { reason: '범위 오류', left: 2, right: 1, delta: -1 },
    { reason: '지연', left: 1, right: 0, delta: -1 },
  ]);
  assert.deepEqual(comparison.failureReasonCoverage, {
    left: { failedOutcomeCount: 3, reportedFailureCount: 3, complete: true },
    right: { failedOutcomeCount: 2, reportedFailureCount: 2, complete: true },
  });
  assert.deepEqual(comparison.differences, { inputCount: true, scenario: true, seed: true });
  assert.match(comparison.warnings.join(' '), /성능 향상이나 수정 효과로 해석할 수 없습니다/);
  assert.throws(() => compareRuns(left, left), /서로 다른 실행 ID/);
});

test('zero input has no rate, and missing failed outcomes remain an incomplete breakdown', () => {
  const empty = { ...left, id: 'empty', inputCount: 0, successCount: 0, failureCount: 0, duplicateCount: 0, pendingCount: 0, outcomes: [] };
  const comparison = compareRuns(empty, { ...right, outcomes: right.outcomes.filter(row => row.sequence !== 6) });
  assert.deepEqual(comparison.rates.map(({ left, right, deltaPercentagePoints }) => [left, right, deltaPercentagePoints]), [
    [null, 50, null], [null, 25, null],
  ]);
  assert.deepEqual(comparison.failureReasonCoverage.right, { failedOutcomeCount: 1, reportedFailureCount: 2, complete: false });
  assert.deepEqual(comparison.failureReasons, [{ reason: '범위 오류', left: 0, right: 1, delta: 1 }]);
  assert.match(comparison.warnings.join(' '), /B의 FAILED outcome 수와 보고된 실패 건수가 다릅니다/);
  assert.deepEqual(compareRuns(empty, { ...empty, id: 'empty-b' }).rates.map(row => [row.left, row.right, row.deltaPercentagePoints]), [[null, null, null], [null, null, null]]);
});

test('CSV keeps Korean, numeric differences, source metadata and raw timestamps while escaping formula strings', () => {
  const comparison = compareRuns({ ...left, name: '=HYPERLINK("https://example.test")', scenario: '+SUM(1,2)', status: '@status',
    outcomes: [outcome(1, 'FAILED', '\tformula'), outcome(2, 'FAILED', '\rformula'), outcome(3, 'FAILED', '-formula')] },
  { ...right, name: '  =formula', scenario: '정상, "입력"' });
  const csv = comparisonCsv(comparison, { left: { path: 'https://example.test/api/demo/runs/run-a', receivedAt: '2026-10-24T09:02:00+09:00' },
    right: { path: '/api/demo/runs/run-b', receivedAt: null } });
  assert.ok(csv.startsWith('\uFEFF"구분","항목","단위","A","B","차이(B-A)"\r\n'));
  assert.ok(csv.includes('"건수","입력","건","10","8","-2"\r\n'));
  assert.ok(csv.includes('"입력 대비 비율","실패 비율","% (차이: %p)","30","25","-5"'));
  assert.ok(csv.includes("\"'=HYPERLINK(\"\"https://example.test\"\")\""));
  for (const safe of ["\"'+SUM(1,2)\"", "\"'@status\"", "\"'\tformula\"", "\"'\rformula\"", "\"'-formula\"", "\"'  =formula\""]) assert.ok(csv.includes(safe), safe);
  assert.ok(csv.includes('"정상, ""입력"""'));
  assert.ok(csv.includes('"https://example.test/api/demo/runs/run-a"'));
  assert.ok(csv.includes('"2026-10-24T09:01:00+09:00"'));
  assert.ok(csv.includes('"2026-10-24T09:02:00+09:00"'));
  assert.ok(csv.includes('"2026-10-24T00:00:00.000Z"'));
  assert.ok(comparisonCsv(compareRuns({ ...left, id: 'zero', inputCount: 0, successCount: 0, failureCount: 0, duplicateCount: 0, pendingCount: 0, outcomes: [] }, right))
    .includes('"성공 비율","% (차이: %p)","","50",""'));
});

test('share selection round-trips only bounded run IDs on the fixed page under a configured base path', () => {
  const path = comparisonSharePath('synthetic-v1_seed.42', 'b'.repeat(80), '/platform-lab/');
  assert.equal(path, '/platform-lab/runs/compare/?left=synthetic-v1_seed.42&right=' + 'b'.repeat(80));
  assert.deepEqual(parseComparisonSelection(new URL(path!, 'https://example.test').search), { left: 'synthetic-v1_seed.42', right: 'b'.repeat(80) });
  assert.equal(comparisonSharePath('a', 'b'), '/runs/compare/?left=a&right=b');
  assert.equal(comparisonSharePath('a', 'a'), null);
  assert.equal(comparisonSharePath('a', 'b', 'https://other.test/'), null);
  for (const value of ['a'.repeat(81), 'A', '../private', 'https://other.test', 'a?request=run']) assert.equal(isComparisonRunId(value), false);
  assert.equal(parseComparisonSelection('?left=a&right=b&left=c'), null);
  assert.equal(parseComparisonSelection('?left=a&right=b&apiBase=https://other.test'), null);
  assert.equal(parseComparisonSelection('?left=a&right=a'), null);
});
