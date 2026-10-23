import test from 'node:test';
import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import actualData from '../src/data/tls-certificate.generated.json' with { type: 'json' };
import { buildTlsHistory, type TlsHistoryEntry, type TlsTrustedBinding } from '../src/lib/tls-certificate-history.ts';

// The generated envelope contains the reviewed original text; tests never write or replace the actual fixture.
const ACTUAL_RUN = 'https://github.com/DevDooly/devdooly-platform-lab/actions/runs/39452152238';
const ACTUAL_SOURCE = '8c17642ad4c38a6f0edd3fb47dafa4ec5a431723';
const ACTUAL_HASH = '72c806703547c2fb30a1e9a7e15b1baf41cddc88cc6318ef5589f7c24c69a157';
const ACTUAL_TARGET = '1168720dade3422dda77b9978f95b97eccb0c10b536b14e96023efcb8d20cc13';
const ACTUAL_CERTIFICATE = '9ca310a17f17118a73bd074e5935ff455451cfd733d6ebcaea397cbebabba12b';
const NOW = Date.parse('2026-10-22T00:00:00.000Z');
const ACTUAL_BINDING: TlsTrustedBinding = { runUrl: ACTUAL_RUN, sourceCommit: ACTUAL_SOURCE, artifactSha256: ACTUAL_HASH };
const SECOND_ACTUAL_BINDING: TlsTrustedBinding = {
  runUrl: 'https://github.com/DevDooly/devdooly-platform-lab/actions/runs/39477022262',
  sourceCommit: '6f551a16a8ed536bb126403234c41b9e9b266d43',
  artifactSha256: '8c80681035f3e8f87d18eed2d84577f999e71cada2f6a361d2a727559c75e39f',
};
const actual = actualData.entries[0] as TlsHistoryEntry;
const digest = (text: string) => createHash('sha256').update(text, 'utf8').digest('hex');

/** Synthetic records exist only in test memory, with independently bound hashes and run identities. */
function synthetic(id: number, changes: Record<string, unknown> = {}, rawChange?: (text: string) => string) {
  const summary: Record<string, unknown> = { ...JSON.parse(actual.summaryText),
    validatorSourceCommit: 'b'.repeat(40), captureStartedAt: '2026-10-20T15:51:59.000Z',
    capturedAt: '2026-10-20T15:52:00.000Z', ...changes };
  if (summary.status === 'PASS') {
    const seconds = Math.floor((Date.parse(summary.notAfter as string) - Date.parse(summary.capturedAt as string)) / 1000);
    summary.remainingValiditySeconds = seconds;
    summary.remainingFullDays = Math.floor(seconds / 86_400);
    summary.expiryAssessment = seconds <= 2_592_000 ? 'EXPIRING_WITHIN_30_DAYS' : 'VALID_OVER_30_DAYS';
  }
  let summaryText = JSON.stringify(summary) + '\n';
  if (rawChange) summaryText = rawChange(summaryText);
  const runUrl = `https://github.com/DevDooly/devdooly-platform-lab/actions/runs/${id}`;
  const sourceCommit = summary.validatorSourceCommit as string;
  const metadata = { runUrl, sourceCommit, completedAt: '2026-10-20T15:53:00Z',
    runConclusion: summary.status === 'PASS' ? 'success' : 'failure',
    trialConclusion: summary.status === 'PASS' ? 'success' : 'failure', artifactSha256: digest(summaryText) };
  return { entry: { summaryText, metadata }, trusted: { runUrl, sourceCommit, artifactSha256: metadata.artifactSha256 } };
}
const FAILED_FIELDS = { status: 'FAILED', errorCode: 'TLS_UNVERIFIED', standardTlsVerified: false,
  protocol: null, certificateSha256: null, notBefore: null, notAfter: null,
  remainingValiditySeconds: null, remainingFullDays: null, expiryAssessment: 'UNKNOWN' };
function rejected(entry: TlsHistoryEntry, trusted: TlsTrustedBinding) {
  const result = buildTlsHistory([actual, entry], [ACTUAL_BINDING, trusted], NOW);
  assert.equal(result.records.length, 1);
  assert.equal(result.lastSuccess?.artifactSha256, ACTUAL_HASH);
  assert.equal(result.visibleIssue, 'QUARANTINED_INPUT');
  assert.equal(result.quarantinedCount, 1);
  return result;
}

test('실제 원문 bytes와 사전 검토한 출처를 결합한 첫 저장 관측', () => {
  assert.equal(actualData.entries.length, 2);
  assert.equal(Buffer.byteLength(actual.summaryText, 'utf8'), 911);
  assert.equal(digest(actual.summaryText), ACTUAL_HASH);
  const result = buildTlsHistory([actual], [ACTUAL_BINDING], NOW);
  assert.equal(result.records.length, 1);
  assert.equal(result.visibleIssue, 'NONE');
  assert.equal(result.quarantinedCount, 0);
  assert.equal(result.lastAttempt, result.lastSuccess);
  assert.equal(result.comparison.kind, 'FIRST_VERIFIED');
  assert.equal(result.comparison.previous, null);
  assert.equal(result.comparison.current, result.lastSuccess);
  assert.deepEqual(result.lastSuccess?.summary, JSON.parse(actual.summaryText));
  assert.equal(result.lastSuccess?.summary.targetBindingSha256, ACTUAL_TARGET);
  assert.equal(result.lastSuccess?.summary.certificateSha256, ACTUAL_CERTIFICATE);
  assert.equal(result.lastSuccess?.summary.notAfter, '2027-01-16T13:10:02.000Z');
  assert.equal(result.lastSuccess?.summary.capturedAt, '2026-10-20T15:51:13.433Z');
  assert.equal(result.lastSuccess?.summary.remainingValiditySeconds, 7_593_528);
  assert.equal(result.lastSuccess?.summary.remainingFullDays, 87);
  assert.equal(result.lastSuccess?.summary.naturalRenewalVerified, false);

  const second = actualData.entries[1] as TlsHistoryEntry;
  assert.equal(Buffer.byteLength(second.summaryText, 'utf8'), 911);
  assert.equal(digest(second.summaryText), SECOND_ACTUAL_BINDING.artifactSha256);
  const both = buildTlsHistory(actualData.entries, [ACTUAL_BINDING, SECOND_ACTUAL_BINDING], NOW);
  assert.equal(both.records.length, 2);
  assert.equal(both.visibleIssue, 'NONE');
  assert.equal(both.quarantinedCount, 0);
  assert.equal(both.comparison.kind, 'UNCHANGED_CERTIFICATE');
  assert.equal(both.comparison.previous, both.records[0]);
  assert.equal(both.comparison.current, both.records[1]);
  assert.equal(both.comparison.previous?.artifactSha256, ACTUAL_HASH);
  assert.equal(both.comparison.current?.artifactSha256, SECOND_ACTUAL_BINDING.artifactSha256);
  assert.equal(both.lastSuccess, both.comparison.current);
  assert.equal(both.lastAttempt, both.lastSuccess);
  assert.deepEqual(both.lastSuccess?.summary, JSON.parse(second.summaryText));
  assert.equal(both.lastSuccess?.summary.targetBindingSha256, ACTUAL_TARGET);
  assert.equal(both.lastSuccess?.summary.certificateSha256, ACTUAL_CERTIFICATE);
  assert.equal(both.lastSuccess?.summary.notAfter, '2027-01-16T13:10:02.000Z');
  assert.equal(both.lastSuccess?.summary.capturedAt, '2026-10-20T18:42:26.245Z');
  assert.equal(both.lastSuccess?.summary.remainingValiditySeconds, 7_583_255);
  assert.equal(both.lastSuccess?.summary.remainingFullDays, 87);
  assert.equal(both.lastSuccess?.summary.naturalRenewalVerified, false);
});

test('빈 이력과 잘못된 설정을 인증서 성공으로 표시하지 않는다', () => {
  const empty = buildTlsHistory([], [], NOW);
  assert.equal(empty.visibleIssue, 'NO_VERIFIED_RECORD');
  assert.equal(empty.lastSuccess, null);
  assert.equal(empty.comparison.kind, 'NO_VERIFIED_RECORD');
  for (const now of [NaN, Infinity, -1, -0, NOW + 0.5]) {
    assert.equal(buildTlsHistory([actual], [ACTUAL_BINDING], now).visibleIssue, 'INVALID_CONFIGURATION');
  }
  for (const trusted of [
    [{ ...ACTUAL_BINDING, sourceCommit: 'A'.repeat(40) }],
    [{ ...ACTUAL_BINDING, runUrl: ACTUAL_RUN + '?attempt=1' }],
    [ACTUAL_BINDING, { ...ACTUAL_BINDING, artifactSha256: 'c'.repeat(64) }],
  ]) assert.equal(buildTlsHistory([actual], trusted, NOW).visibleIssue, 'INVALID_CONFIGURATION');
});

test('현재 시각이 인증서 만료 뒤여도 수집 당시 검증한 역사 기록을 보존한다', () => {
  const result = buildTlsHistory([actual], [ACTUAL_BINDING], Date.parse('2027-02-01T00:00:00.000Z'));
  assert.equal(result.visibleIssue, 'NONE');
  assert.equal(result.lastSuccess?.summary.capturedAt, '2026-10-20T15:51:13.433Z');
  assert.equal(result.lastSuccess?.summary.remainingFullDays, 87);
  assert.equal(result.lastSuccess?.summary.expiryAssessment, 'VALID_OVER_30_DAYS');
});

test('원문 공백 변화도 원문 hash와 다르면 마지막 성공을 덮지 않는다', () => {
  const result = buildTlsHistory([{ ...actual, summaryText: actual.summaryText + ' ' }], [ACTUAL_BINDING], NOW);
  assert.equal(result.lastSuccess, null);
  assert.equal(result.visibleIssue, 'QUARANTINED_INPUT');
  assert.equal(result.quarantinedCount, 1);
});

test('검토하지 않은 run/source/hash와 잘못된 metadata6은 거부한다', () => {
  const item = synthetic(1001);
  const metadata = item.entry.metadata;
  for (const changed of [
    { ...metadata, runUrl: 'https://github.com/another/repository/actions/runs/1001' },
    { ...metadata, sourceCommit: 'c'.repeat(40) },
    { ...metadata, artifactSha256: 'd'.repeat(64) },
    { ...metadata, completedAt: '2026-10-20T15:50:00Z' },
    { ...metadata, completedAt: '2026-10-23T00:00:00Z' },
    { ...metadata, completedAt: '2026-02-30T00:00:00Z' },
    { ...metadata, runConclusion: 'failure' },
    { ...metadata, trialConclusion: 'failure' },
    { ...metadata, privateValue: 'must-not-leak' },
  ]) rejected({ ...item.entry, metadata: changed }, item.trusted);
  rejected(item.entry, { ...item.trusted, artifactSha256: 'e'.repeat(64) });
  const untrusted = buildTlsHistory([actual, item.entry], [ACTUAL_BINDING], NOW);
  assert.equal(untrusted.visibleIssue, 'QUARANTINED_INPUT');
});

test('decoded 중복키·unknown키·중첩값·잘못된 숫자 lexeme을 거부한다', () => {
  const transformations = [
    (text: string) => text.replace('"schemaVersion":1', '"schemaVersion":1,"\\u0073chemaVersion":1'),
    (text: string) => text.replace('{', '{"unknown":true,'),
    (text: string) => text.replace('"schemaVersion":1', '"schemaVersion":{"value":1}'),
    (text: string) => text.replace('"warningThresholdDays":30', '"warningThresholdDays":3e1'),
    (text: string) => text.replace('"warningThresholdDays":30', '"warningThresholdDays":30.0'),
    (text: string) => text.replace('"schemaVersion":1', '"schemaVersion":-0'),
    (text: string) => '[' + text.trim() + ']',
    (text: string) => text + '{}',
    (text: string) => text + ' '.repeat(4096),
  ];
  for (const change of transformations) {
    const item = synthetic(1002, {}, change); rejected(item.entry, item.trusted);
  }
});

test('PASS의 false/null/string 타입과 성공 관측 관계를 거부한다', () => {
  for (const changes of [
    { schemaVersion: true }, { publicIpv4Verified: false }, { standardTlsVerified: 1 },
    { connectionClosed: false }, { protocol: 'TLSv1.1' }, { targetBindingSha256: null },
    { certificateSha256: null }, { warningThresholdDays: '30' }, { naturalRenewalVerified: true },
    { operatingConfigurationChanged: true }, { errorCode: 'TLS_UNVERIFIED' },
    { notBefore: '2026-10-20T15:52:00.001Z' }, { notAfter: '2026-10-20T15:52:00.000Z' },
  ]) {
    const item = synthetic(1003, changes); rejected(item.entry, item.trusted);
  }
  const wrongSeconds = synthetic(1004, {}, text => text.replace(/"remainingValiditySeconds":\d+/, '"remainingValiditySeconds":1'));
  rejected(wrongSeconds.entry, wrongSeconds.trusted);
  const wrongDays = synthetic(1005, {}, text => text.replace(/"remainingFullDays":\d+/, '"remainingFullDays":false'));
  rejected(wrongDays.entry, wrongDays.trusted);
});

test('UTC 실제 날짜·millisecond 형식·시계 역전·미래 관측을 거부한다', () => {
  for (const changes of [
    { capturedAt: '2026-10-20T15:52:00Z' },
    { capturedAt: '2026-10-20T15:52:00.000+00:00' },
    { capturedAt: '2026-02-30T15:52:00.000Z' },
    { captureStartedAt: '2026-10-20T15:52:00.001Z' },
    { capturedAt: '2026-10-23T15:52:00.000Z' },
  ]) {
    const item = synthetic(1006, changes); rejected(item.entry, item.trusted);
  }
});

test('정확30일은 floor초 경보이며 1ms와1000ms 차이를 독립 기대값으로 구분한다', () => {
  const cases = [
    ['2026-11-19T15:52:00.000Z', 2_592_000, 30, 'EXPIRING_WITHIN_30_DAYS'],
    ['2026-11-19T15:52:00.999Z', 2_592_000, 30, 'EXPIRING_WITHIN_30_DAYS'],
    ['2026-11-19T15:52:01.000Z', 2_592_001, 30, 'VALID_OVER_30_DAYS'],
    ['2026-11-19T15:51:59.999Z', 2_591_999, 29, 'EXPIRING_WITHIN_30_DAYS'],
  ] as const;
  for (const [notAfter, seconds, days, assessment] of cases) {
    const item = synthetic(1007, { notAfter });
    const result = buildTlsHistory([item.entry], [item.trusted], NOW);
    assert.equal(result.visibleIssue, 'NONE');
    assert.equal(result.lastSuccess?.summary.remainingValiditySeconds, seconds);
    assert.equal(result.lastSuccess?.summary.remainingFullDays, days);
    assert.equal(result.lastSuccess?.summary.expiryAssessment, assessment);
  }
});

test('새 FAILED는 마지막 시도와 마지막 PASS를 분리하고 인증서 값을 보존한다', () => {
  const failed = synthetic(1008, FAILED_FIELDS);
  const result = buildTlsHistory([actual, failed.entry], [ACTUAL_BINDING, failed.trusted], NOW);
  assert.equal(result.records.length, 2);
  assert.equal(result.visibleIssue, 'LATEST_ATTEMPT_FAILED');
  assert.equal(result.lastAttempt?.summary.status, 'FAILED');
  assert.equal(result.lastAttempt?.summary.certificateSha256, null);
  assert.equal(result.lastSuccess?.artifactSha256, ACTUAL_HASH);
  assert.equal(result.lastSuccess?.summary.remainingFullDays, 87);
  assert.equal(result.comparison.kind, 'FIRST_VERIFIED');
  assert.equal(result.comparison.current, result.lastSuccess);
  assert.equal(result.quarantinedCount, 0);
});

test('실패만 검증됐으면 인증서 성공 이력이 없는 상태를 숨기지 않는다', () => {
  const failed = synthetic(1009, { ...FAILED_FIELDS, connectionClosed: false });
  const result = buildTlsHistory([failed.entry], [failed.trusted], NOW);
  assert.equal(result.lastSuccess, null);
  assert.equal(result.lastAttempt?.summary.errorCode, 'TLS_UNVERIFIED');
  assert.equal(result.visibleIssue, 'LATEST_ATTEMPT_FAILED');
  assert.equal(result.comparison.kind, 'NO_VERIFIED_RECORD');
});

test('실패의 성공 전용 값·미확인 대상·시계 역전은 격리하면서 이전 PASS를 남긴다', () => {
  for (const changes of [
    { protocol: 'TLSv1.3' }, { certificateSha256: ACTUAL_CERTIFICATE }, { notAfter: '2027-01-16T13:10:02.000Z' },
    { remainingFullDays: 87 }, { standardTlsVerified: true }, { expiryAssessment: 'VALID_OVER_30_DAYS' },
    { errorCode: 'NONE' }, { errorCode: 'RAW_EXCEPTION_TEXT' },
    { targetBindingSha256: null, publicIpv4Verified: false },
    { errorCode: 'CLOCK_UNVERIFIED', captureStartedAt: '2026-10-20T15:52:00.001Z' },
  ]) {
    const failed = synthetic(1010, { ...FAILED_FIELDS, ...changes }); rejected(failed.entry, failed.trusted);
  }
});

test('같은 run의 동일 원문은 멱등이며 metadata 충돌은 격리한다', () => {
  const deduplicated = buildTlsHistory([actual, actual], [ACTUAL_BINDING, ACTUAL_BINDING], NOW);
  assert.equal(deduplicated.records.length, 1);
  assert.equal(deduplicated.visibleIssue, 'NONE');
  const conflicting = { ...actual, metadata: { ...(actual.metadata as Record<string, unknown>), completedAt: '2026-10-20T15:51:17Z' } };
  rejected(conflicting, ACTUAL_BINDING);
});

test('같은 PASS의 동등한 완료 시각은 입력 순서대로 최초 표기와 검토된 원문을 보존한다', () => {
  const metadata = actual.metadata as Record<string, unknown>;
  const equivalent = { ...actual, metadata: { ...metadata,
    completedAt: (metadata.completedAt as string).replace('Z', '.000Z') } };
  const before = JSON.stringify([actual, equivalent]);
  for (const entries of [[actual, equivalent], [equivalent, actual]]) {
    const result = buildTlsHistory(entries, [ACTUAL_BINDING], NOW);
    assert.deepEqual(result, buildTlsHistory([entries[0]], [ACTUAL_BINDING], NOW));
    assert.equal(result.quarantinedCount, 0);
    assert.equal(result.visibleIssue, 'NONE');
    assert.equal(result.records.length, 1);
    assert.equal(result.lastAttempt, result.lastSuccess);
    assert.equal(result.lastSuccess?.completedAt, (entries[0].metadata as Record<string, unknown>).completedAt);
    assert.equal(result.lastSuccess?.artifactSha256, digest(actual.summaryText));
    assert.deepEqual(result.lastSuccess?.summary, JSON.parse(actual.summaryText));
  }
  assert.equal(JSON.stringify([actual, equivalent]), before);
});

test('같은 FAILED의 동등한 완료 시각은 최초 실패 표기와 이전 PASS를 함께 보존한다', () => {
  const failed = synthetic(1017, FAILED_FIELDS);
  const equivalent = { ...failed.entry, metadata: { ...failed.entry.metadata,
    completedAt: failed.entry.metadata.completedAt.replace('Z', '.000Z') } };
  const before = JSON.stringify([failed.entry, equivalent]);
  for (const entries of [[failed.entry, equivalent], [equivalent, failed.entry]]) {
    const trusted = [ACTUAL_BINDING, failed.trusted];
    const result = buildTlsHistory([actual, ...entries], trusted, NOW);
    assert.deepEqual(result, buildTlsHistory([actual, entries[0]], trusted, NOW));
    assert.equal(result.quarantinedCount, 0);
    assert.equal(result.visibleIssue, 'LATEST_ATTEMPT_FAILED');
    assert.equal(result.records.length, 2);
    assert.equal(result.lastAttempt?.summary.status, 'FAILED');
    assert.equal(result.lastAttempt?.completedAt, entries[0].metadata.completedAt);
    assert.equal(result.lastAttempt?.artifactSha256, digest(failed.entry.summaryText));
    assert.deepEqual(result.lastAttempt?.summary, JSON.parse(failed.entry.summaryText));
    assert.equal(result.lastSuccess, result.records[0]);
    assert.equal(result.lastSuccess?.artifactSha256, ACTUAL_HASH);
  }
  assert.equal(JSON.stringify([failed.entry, equivalent]), before);
});

test('같은 run의 실제 1ms 차이와 동등 완료 시각에 섞인 출처·원문 충돌은 격리한다', () => {
  for (const item of [synthetic(1018), synthetic(1019, FAILED_FIELDS)]) {
    const later = { ...item.entry, metadata: { ...item.entry.metadata, completedAt: '2026-10-20T15:53:00.001Z' } };
    for (const entries of [[item.entry, later], [later, item.entry]]) {
      const result = buildTlsHistory(entries, [item.trusted], NOW);
      assert.equal(result.quarantinedCount, 1);
      assert.equal(result.visibleIssue, 'QUARANTINED_INPUT');
      assert.deepEqual(result.records, buildTlsHistory([entries[0]], [item.trusted], NOW).records);
    }
    const equivalent = { ...item.entry, metadata: { ...item.entry.metadata,
      completedAt: item.entry.metadata.completedAt.replace('Z', '.000Z') } };
    const changedEntries = [
      ...[
        { sourceCommit: 'c'.repeat(40) }, { artifactSha256: 'd'.repeat(64) },
        { runUrl: item.trusted.runUrl + '1' },
        { runConclusion: item.entry.metadata.runConclusion === 'success' ? 'failure' : 'success' },
      ].map(change => ({ ...equivalent, metadata: { ...equivalent.metadata, ...change } })),
      { ...equivalent, summaryText: item.entry.summaryText + ' ' },
    ];
    for (const changed of changedEntries) {
      const result = buildTlsHistory([item.entry, changed], [item.trusted], NOW);
      assert.equal(result.quarantinedCount, 1);
      assert.equal(result.visibleIssue, 'QUARANTINED_INPUT');
      assert.deepEqual(result.records, buildTlsHistory([item.entry], [item.trusted], NOW).records);
    }
  }
});

test('다른 대상·같은 시각·늦게 도착한 과거 관측을 재정렬해 합치지 않는다', () => {
  for (const changes of [
    { targetBindingSha256: 'f'.repeat(64) },
    { captureStartedAt: '2026-10-20T15:51:12.647Z', capturedAt: '2026-10-20T15:51:13.433Z' },
    { captureStartedAt: '2026-10-20T15:51:11.000Z', capturedAt: '2026-10-20T15:51:12.000Z' },
  ]) {
    const item = synthetic(1011, changes); rejected(item.entry, item.trusted);
  }
});

test('같은 leaf와 기간을 다시 관측해도 자연 갱신으로 표시하지 않는다', () => {
  const later = synthetic(1012);
  const result = buildTlsHistory([actual, later.entry], [ACTUAL_BINDING, later.trusted], NOW);
  assert.equal(result.records.length, 2);
  assert.equal(result.comparison.kind, 'UNCHANGED_CERTIFICATE');
  assert.equal(result.comparison.previous?.runUrl, ACTUAL_RUN);
  assert.equal(result.comparison.current?.runUrl, later.trusted.runUrl);
  assert.equal(result.lastSuccess?.summary.naturalRenewalVerified, false);
});

test('다른 leaf의 만료 연장·동일·앞당김은 관측 비교만 구분한다', () => {
  const cases = [
    ['2027-02-16T13:10:02.000Z', 'CERTIFICATE_CHANGED_EXTENDED'],
    ['2027-01-16T13:10:02.000Z', 'CERTIFICATE_CHANGED_SAME_EXPIRY'],
    ['2026-12-16T13:10:02.000Z', 'CERTIFICATE_CHANGED_EARLIER_EXPIRY'],
  ] as const;
  for (const [notAfter, kind] of cases) {
    const later = synthetic(1013, { certificateSha256: 'c'.repeat(64), notAfter });
    const result = buildTlsHistory([actual, later.entry], [ACTUAL_BINDING, later.trusted], NOW);
    assert.equal(result.visibleIssue, 'NONE');
    assert.equal(result.comparison.kind, kind);
    assert.equal(result.lastSuccess?.summary.naturalRenewalVerified, false);
    assert.equal(result.lastSuccess?.summary.operatingConfigurationChanged, false);
  }
});

test('같은 leaf의 모순된 기간은 만료 연장으로 승격하지 않는다', () => {
  const impossible = synthetic(1014, { notAfter: '2027-02-16T13:10:02.000Z' });
  const result = rejected(impossible.entry, impossible.trusted);
  assert.equal(result.comparison.kind, 'FIRST_VERIFIED');
});

test('입력 accessor를 실행하거나 미선택 값을 공개 결과로 옮기지 않는다', () => {
  const item = synthetic(1015);
  let reads = 0;
  const metadata = { ...item.entry.metadata };
  Object.defineProperty(metadata, 'runUrl', { enumerable: true, get() { reads++; return item.trusted.runUrl; } });
  const result = rejected({ ...item.entry, metadata }, item.trusted);
  assert.equal(reads, 0);
  assert.equal(JSON.stringify(result).includes('must-not-leak'), false);
  const extra = synthetic(1016);
  const result2 = rejected({ ...extra.entry, metadata: { ...extra.entry.metadata, secret: 'must-not-leak' } }, extra.trusted);
  assert.equal(JSON.stringify(result2).includes('must-not-leak'), false);
});

test('순수 결과는 입력을 변경하지 않고 선택한 값과 배열을 동결한다', () => {
  const before = JSON.stringify(actualData);
  const bindings = [ACTUAL_BINDING];
  const bindingBefore = JSON.stringify(bindings);
  const result = buildTlsHistory(actualData.entries, bindings, NOW);
  assert.equal(JSON.stringify(actualData), before);
  assert.equal(JSON.stringify(bindings), bindingBefore);
  assert.equal(Object.isFrozen(result), true);
  assert.equal(Object.isFrozen(result.records), true);
  assert.equal(Object.isFrozen(result.lastSuccess), true);
  assert.equal(Object.isFrozen(result.lastSuccess?.summary), true);
  assert.equal(Object.isFrozen(result.comparison), true);
  assert.deepEqual(Object.keys(result), ['records', 'lastAttempt', 'lastSuccess', 'comparison', 'visibleIssue', 'quarantinedCount']);
});
