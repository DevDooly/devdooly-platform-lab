import type { RunDetail } from './api.ts';

export type ComparisonMetricKey = 'inputCount' | 'successCount' | 'failureCount' | 'duplicateCount' | 'pendingCount';
export interface ComparisonMetric {
  key: ComparisonMetricKey;
  label: string;
  left: number;
  right: number;
  delta: number;
}
export interface ComparisonRate {
  key: 'success' | 'failure';
  label: string;
  /** Percent of inputCount, from 0 to 100. A zero denominator has no rate. */
  left: number | null;
  right: number | null;
  deltaPercentagePoints: number | null;
}
export interface ComparisonFailureReason { reason: string; left: number; right: number; delta: number; }
export interface FailureReasonCoverage {
  failedOutcomeCount: number;
  reportedFailureCount: number;
  complete: boolean;
}
export interface RunComparison {
  left: RunDetail;
  right: RunDetail;
  metrics: ComparisonMetric[];
  rates: ComparisonRate[];
  failureReasons: ComparisonFailureReason[];
  failureReasonCoverage: { left: FailureReasonCoverage; right: FailureReasonCoverage };
  differences: { inputCount: boolean; scenario: boolean; seed: boolean };
  warnings: string[];
}
export interface ComparisonSources {
  left: { path: string; receivedAt: string | null };
  right: { path: string; receivedAt: string | null };
}

const metricLabels: ReadonlyArray<readonly [ComparisonMetricKey, string]> = [
  ['inputCount', '입력'], ['successCount', '성공'], ['failureCount', '실패'],
  ['duplicateCount', '중복'], ['pendingCount', '대기'],
];

function failedReasons(run: RunDetail): { counts: Map<string, number>; coverage: FailureReasonCoverage } {
  const counts = new Map<string, number>();
  let failedOutcomeCount = 0;
  for (const outcome of run.outcomes) {
    if (outcome.status !== 'FAILED') continue;
    failedOutcomeCount++;
    counts.set(outcome.reason, (counts.get(outcome.reason) ?? 0) + 1);
  }
  return { counts, coverage: { failedOutcomeCount, reportedFailureCount: run.failureCount,
    complete: failedOutcomeCount === run.failureCount } };
}

/** Compare validated saved results. Differences do not establish performance or causality. */
export function compareRuns(left: RunDetail, right: RunDetail): RunComparison {
  if (left.id === right.id) throw new Error('서로 다른 실행 ID를 선택하세요.');
  const metrics = metricLabels.map(([key, label]) => ({ key, label, left: left[key], right: right[key], delta: right[key] - left[key] }));
  const rates: ComparisonRate[] = (['success', 'failure'] as const).map(key => {
    const countKey = key === 'success' ? 'successCount' : 'failureCount';
    const leftRate = left.inputCount === 0 ? null : left[countKey] / left.inputCount * 100;
    const rightRate = right.inputCount === 0 ? null : right[countKey] / right.inputCount * 100;
    return { key, label: key === 'success' ? '성공 비율' : '실패 비율', left: leftRate, right: rightRate,
      deltaPercentagePoints: leftRate === null || rightRate === null ? null : rightRate - leftRate };
  });
  const a = failedReasons(left), b = failedReasons(right);
  const reasons = [...new Set([...a.counts.keys(), ...b.counts.keys()])].sort();
  const failureReasons = reasons.map(reason => {
    const leftCount = a.counts.get(reason) ?? 0, rightCount = b.counts.get(reason) ?? 0;
    return { reason, left: leftCount, right: rightCount, delta: rightCount - leftCount };
  });
  const differences = { inputCount: left.inputCount !== right.inputCount, scenario: left.scenario !== right.scenario, seed: left.seed !== right.seed };
  const warnings: string[] = [];
  if (differences.inputCount || differences.scenario || differences.seed) {
    warnings.push('입력 건수·시나리오·seed 중 다른 조건이 있습니다. 건수와 비율 차이를 성능 향상이나 수정 효과로 해석할 수 없습니다.');
  }
  if (!a.coverage.complete) warnings.push('A의 FAILED outcome 수와 보고된 실패 건수가 다릅니다. 실패 사유 표는 관측된 FAILED outcome만 집계합니다.');
  if (!b.coverage.complete) warnings.push('B의 FAILED outcome 수와 보고된 실패 건수가 다릅니다. 실패 사유 표는 관측된 FAILED outcome만 집계합니다.');
  return { left, right, metrics, rates, failureReasons, failureReasonCoverage: { left: a.coverage, right: b.coverage }, differences, warnings };
}

/** Retain numeric negatives; neutralize formula-like strings before CSV quoting. */
function csvCell(value: string | number | null): string {
  let text = value === null ? '' : String(value);
  if (typeof value === 'string' && (/^[\t\r\n]/.test(text) || /^\s*[=+\-@]/u.test(text))) text = "'" + text;
  return '"' + text.replaceAll('"', '""') + '"';
}

/** UTF-8 BOM, raw source timestamps and explicit units make the export reviewable. */
export function comparisonCsv(comparison: RunComparison, sources?: ComparisonSources): string {
  const { left, right } = comparison;
  type Cell = string | number | null;
  const rows: Cell[][] = [['구분', '항목', '단위', 'A', 'B', '차이(B-A)']];
  const metadata = (label: string, a: Cell, b: Cell) => rows.push(['메타데이터', label, '', a, b, null]);
  metadata('실행 ID', left.id, right.id);
  metadata('실행 이름', left.name, right.name);
  metadata('시나리오', left.scenario, right.scenario);
  metadata('seed', left.seed, right.seed);
  metadata('합성 데이터', left.synthetic ? '예' : '아니오', right.synthetic ? '예' : '아니오');
  metadata('실행 상태', left.status, right.status);
  metadata('조회 출처(GET)', sources?.left.path ?? '/demo/runs/' + left.id, sources?.right.path ?? '/demo/runs/' + right.id);
  metadata('응답 수신 시각(원문)', sources?.left.receivedAt ?? null, sources?.right.receivedAt ?? null);
  metadata('관측 시각(원문)', left.observedAt, right.observedAt);
  metadata('시작 시각(원문)', left.startedAt, right.startedAt);
  metadata('완료 시각(원문)', left.completedAt, right.completedAt);
  rows.push(['해석 범위', '저장된 두 실행의 차이이며 성능 향상이나 수정 효과를 증명하지 않습니다.', '', null, null, null]);
  for (const metric of comparison.metrics) rows.push(['건수', metric.label, '건', metric.left, metric.right, metric.delta]);
  for (const rate of comparison.rates) rows.push(['입력 대비 비율', rate.label, '% (차이: %p)', rate.left, rate.right, rate.deltaPercentagePoints]);
  metadata('비율 분모', left.inputCount, right.inputCount);
  rows.push(['해석 범위', '입력 건수가 0이면 비율과 해당 비율 차이는 빈칸입니다.', '', null, null, null]);
  metadata('실패 사유 집계 근거', '관측된 FAILED outcome', '관측된 FAILED outcome');
  metadata('관측된 FAILED outcome 수', comparison.failureReasonCoverage.left.failedOutcomeCount, comparison.failureReasonCoverage.right.failedOutcomeCount);
  metadata('실패 사유 집계와 보고된 실패 건수 일치', comparison.failureReasonCoverage.left.complete ? '예' : '아니오', comparison.failureReasonCoverage.right.complete ? '예' : '아니오');
  for (const reason of comparison.failureReasons) rows.push(['실패 사유', reason.reason, '건', reason.left, reason.right, reason.delta]);
  for (const warning of comparison.warnings) rows.push(['주의', warning, '', null, null, null]);
  return '\uFEFF' + rows.map(row => row.map(csvCell).join(',')).join('\r\n') + '\r\n';
}

export function isComparisonRunId(value: unknown): value is string {
  return typeof value === 'string' && /^[a-z0-9][a-z0-9._-]{0,79}$/.test(value);
}

/** A selection only: opening a shared link never implies a request or execution. */
export function parseComparisonSelection(search: string): { left: string; right: string } | null {
  const params = new URLSearchParams(search);
  if ([...params.keys()].some(key => key !== 'left' && key !== 'right')
    || params.getAll('left').length !== 1 || params.getAll('right').length !== 1) return null;
  const left = params.get('left'), right = params.get('right');
  return isComparisonRunId(left) && isComparisonRunId(right) && left !== right ? { left, right } : null;
}

/** Fixed page and ID-only query; basePath is Astro's configured path prefix. */
export function comparisonSharePath(left: string, right: string, basePath = '/'): string | null {
  if (!isComparisonRunId(left) || !isComparisonRunId(right) || left === right) return null;
  if (!/^\/(?:[a-z0-9._~-]+\/)*[a-z0-9._~-]*$/i.test(basePath)
    || basePath.split('/').some(part => part === '.' || part === '..')) return null;
  const prefix = basePath.replace(/\/$/, '');
  return prefix + '/runs/compare/?' + new URLSearchParams({ left, right }).toString();
}
