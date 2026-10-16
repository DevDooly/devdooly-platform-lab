/** Stored CLI summary only. This parser cannot run a capture or apply retention. */
import { parseCaptureDiagnostic, type CaptureDiagnostic, type CaptureDiagnosticProfile } from './iceberg-capture-diagnostic.ts';
export const icebergCaptureManifest = 'c8cecad8fc09ab20a78382c4a96daf5c9e761065cb774abd6cd9b65d0ee8be28';
export const icebergCaptureManifestV2 = '53493f2dfeedee530ad152b5dc08f2c08b3d560ac39fac887820129913c8db3d';
/** Exact reviewed closed-classpath runtime; this pin does not claim an actual capture outcome. */
export const icebergCaptureManifestClosedClasspath: string | null = 'a9704dce98583b3935e05ac759a3b0e9c8af839fb9b3fa141ad1d96a13708f18';
/** Exact reviewed bounded-manifest runtime; this pin does not claim an actual capture outcome. */
export const icebergCaptureManifestBoundedManifest: string | null = '6aea1d3987d4a258718f4fd242d05ff1364a73cf4772272260975fce7eb172cd';
export const captureReasons = {
  FRAME_MAGIC: '입력 형식 확인 실패', FRAME_BOUND: '입력 크기 제한', FRAME_EOF: '입력 전체 바이트 미확인',
  DESCRIPTOR_INVALID: '입력 계약 확인 실패', OBJECT_MAP_INVALID: '객체 목록 확인 실패',
  OBJECT_BYTES_MISMATCH: '객체 바이트 불일치', METADATA_INVALID: '메타데이터 해석 실패',
  UNSUPPORTED_FORMAT: '지원하지 않는 메타데이터 형식', UNSUPPORTED_METADATA_FEATURE: '지원하지 않는 메타데이터 기능',
  UNSUPPORTED_CODEC: '지원하지 않는 압축 형식', UNSUPPORTED_SCHEMA: '지원하지 않는 스키마',
  UNSUPPORTED_ENTRY_CONTENT: '지원하지 않는 manifest 항목', MISSING_APPROVED_CHILD: '승인된 하위 객체 미확인',
  FOREIGN_REFERENCE: '허용 범위 밖 참조', GRAPH_CONFLICT: '메타데이터 연결 불일치',
  MISSING_SNAPSHOT_REFERENCE: '스냅샷 참조 미확인', REFERENCE_CYCLE: '참조 순환', GRAPH_BOUND: '메타데이터 연결 크기 제한',
  DECODER_INTERNAL: '해석기 판정 미완료', DECODER_BUDGET_EXPIRED: '해석 시간 제한',
} as const;
export const captureFailures = {
  CAPTURE_UNDETERMINED: '메타데이터 판정 미완료', PREP_NOT_VERIFIED: '준비 결과 검증 미확인',
  COMPOSITE_NOT_VERIFIED: '실행 결과 검증 미확인', SUMMARY_NOT_VERIFIED: '결과 검증 미확인',
} as const;
const checkKeys = ['sourceBytesVerified', 'compilerPrepVerified', 'originalMainCalledOnce', 'originalMainReturnedZero',
  'decoderStoppedVerified', 'decoderAttachCliReaped', 'sameRunStoppedActorsAndClockVerified', 'inventoryProduced', 'allObjectsKept'] as const;
const countKeys = ['capturedObjectCount', 'snapshotCount', 'refCount', 'validationPinCount', 'snapshotCandidateCount', 'objectCandidateCount'] as const;
const inventoryCountKeys = ['snapshotCount', 'refCount', 'validationPinCount', 'snapshotCandidateCount'] as const;
const falseKeys = ['snapshotExpirationPerformed', 'objectDeletionPerformed', 'miniPcContacted', 'liveTableIndependentlyVerified',
  'parquetContentsDecoded', 'historicalMetadataRestored', 'rawProofsOrCredentialsUploaded', 'automaticRetryPerformed'] as const;
const topKeys = ['schemaVersion', 'scope', 'sourceCommit', 'runtimeManifestSha256', 'passed', 'status', 'failureCategory', 'checks',
  'counts', 'proofHashes', 'decoderReasonCodes', 'policy', 'originalWorkloadBudgetSeconds', 'separatePrepBudgetSeconds', 'cleanupReserveSeconds', ...falseKeys];
export type IcebergCapture = {
  scope: 'FRESH_CLOUD_ICEBERG_CLOSED_COPY_CAPTURE'; sourceCommit: string; runtimeManifestSha256: string;
  passed: boolean; status: 'DETERMINED' | 'UNDETERMINED' | 'FAILED'; failureCategory: keyof typeof captureFailures | null;
  checks: Record<typeof checkKeys[number], boolean>;
  counts: { capturedObjectCount: number | null; snapshotCount: number | null; refCount: number | null;
    validationPinCount: number | null; snapshotCandidateCount: number | null; objectCandidateCount: 0 };
  proofHashes: { prepProofSha256: string | null; normalizationReceiptCanonicalSha256: string | null };
  decoderReasonCodes: (keyof typeof captureReasons)[];
  policy: { schemaVersion: 1; maxInventoryAgeSeconds: 300; minSnapshotAgeSeconds: 86400; minimumSnapshotsToKeep: 3 };
  originalWorkloadBudgetSeconds: 600; separatePrepBudgetSeconds: 600; cleanupReserveSeconds: 40;
} & Record<typeof falseKeys[number], false> & ({ schemaVersion: 1; diagnostic?: never } | { schemaVersion: 2; diagnostic: CaptureDiagnostic });
const object = (value: unknown): value is Record<string, unknown> => value !== null && typeof value === 'object' && !Array.isArray(value);
const exact = (value: Record<string, unknown>, keys: readonly string[]) => Object.keys(value).length === keys.length && keys.every(key => Object.hasOwn(value, key));
const hash = (value: unknown): value is string => typeof value === 'string' && /^[a-f0-9]{64}$/.test(value);
const nullableHash = (value: unknown) => value === null || hash(value);
const number = (value: unknown, maximum: number, minimum = 0): value is number => typeof value === 'number' && Number.isSafeInteger(value) && value >= minimum && value <= maximum;
function diagnosticProfile(manifest: unknown): CaptureDiagnosticProfile | null {
  if (manifest === icebergCaptureManifestV2) return 'SCHEMA2_INITIAL';
  if (icebergCaptureManifestClosedClasspath !== null && manifest === icebergCaptureManifestClosedClasspath) return 'SCHEMA2_CLOSED_CLASSPATH';
  if (icebergCaptureManifestBoundedManifest !== null && manifest === icebergCaptureManifestBoundedManifest) return 'SCHEMA2_BOUNDED_MANIFEST';
  return null;
}

export function parseIcebergCapture(value: unknown): IcebergCapture | null {
  if (!object(value) || (value.schemaVersion !== 1 && value.schemaVersion !== 2)
    || !exact(value, value.schemaVersion === 1 ? topKeys : [...topKeys, 'diagnostic'])
    || value.scope !== 'FRESH_CLOUD_ICEBERG_CLOSED_COPY_CAPTURE'
    || typeof value.sourceCommit !== 'string' || !/^[a-f0-9]{40}$/.test(value.sourceCommit)
    || !(value.schemaVersion === 1 ? value.runtimeManifestSha256 === icebergCaptureManifest : diagnosticProfile(value.runtimeManifestSha256) !== null)
    || typeof value.passed !== 'boolean'
    || typeof value.status !== 'string' || !['DETERMINED', 'UNDETERMINED', 'FAILED'].includes(value.status)
    || value.originalWorkloadBudgetSeconds !== 600 || value.separatePrepBudgetSeconds !== 600 || value.cleanupReserveSeconds !== 40
    || !falseKeys.every(key => value[key] === false)) return null;
  const checks = value.checks, counts = value.counts, proofs = value.proofHashes, policy = value.policy;
  if (!object(checks) || !exact(checks, checkKeys) || !checkKeys.every(key => typeof checks[key] === 'boolean') || checks.sourceBytesVerified !== true
    || !object(counts) || !exact(counts, countKeys) || counts.objectCandidateCount !== 0
    || !(counts.capturedObjectCount === null || number(counts.capturedObjectCount, 128, 1))
    || !inventoryCountKeys.every(key => counts[key] === null || number(counts[key], 10000))
    || !object(proofs) || !exact(proofs, ['prepProofSha256', 'normalizationReceiptCanonicalSha256'])
    || !nullableHash(proofs.prepProofSha256) || !nullableHash(proofs.normalizationReceiptCanonicalSha256)
    || !object(policy) || !exact(policy, ['schemaVersion', 'maxInventoryAgeSeconds', 'minSnapshotAgeSeconds', 'minimumSnapshotsToKeep'])
    || policy.schemaVersion !== 1 || policy.maxInventoryAgeSeconds !== 300 || policy.minSnapshotAgeSeconds !== 86400 || policy.minimumSnapshotsToKeep !== 3) return null;
  if (checks.compilerPrepVerified !== (proofs.prepProofSha256 !== null)
    || checks.allObjectsKept !== (counts.capturedObjectCount !== null)
    || checks.allObjectsKept !== (proofs.normalizationReceiptCanonicalSha256 !== null)
    || checks.sameRunStoppedActorsAndClockVerified !== checks.allObjectsKept
    || !inventoryCountKeys.every(key => checks.inventoryProduced ? counts[key] !== null : counts[key] === null)
    || (checks.inventoryProduced && !checks.allObjectsKept)) return null;
  const reasons = value.decoderReasonCodes;
  if (!Array.isArray(reasons) || reasons.length > 16 || new Set(reasons).size !== reasons.length
    || !reasons.every(reason => typeof reason === 'string' && Object.hasOwn(captureReasons, reason))) return null;
  if (value.status === 'DETERMINED') {
    if (value.passed !== true || value.failureCategory !== null || !checkKeys.every(key => checks[key] === true)) return null;
  } else if (value.status === 'UNDETERMINED') {
    if (value.passed !== false || value.failureCategory !== 'CAPTURE_UNDETERMINED' || checks.allObjectsKept !== true) return null;
  } else if (value.passed !== false || typeof value.failureCategory !== 'string'
    || !['PREP_NOT_VERIFIED', 'COMPOSITE_NOT_VERIFIED', 'SUMMARY_NOT_VERIFIED'].includes(value.failureCategory)) return null;
  if (value.schemaVersion === 2 && parseCaptureDiagnostic(value.diagnostic, value.passed, diagnosticProfile(value.runtimeManifestSha256)!) === null) return null;
  return value as unknown as IcebergCapture;
}

export function observedCount(value: number | null): string {
  return value === null ? '미관측' : value.toLocaleString('ko-KR');
}

/** Dedicated same-origin static evidence, separate from timer observations. */
export function captureAssetUrl(value: string, base: string): URL | null {
  try {
    const current = new URL(base), target = new URL(value, current);
    return /^https?:$/.test(target.protocol) && target.origin === current.origin && !target.username && !target.password
      && !target.search && !target.hash && target.pathname.endsWith('/evidence/iceberg-capture/summary.json') ? target : null;
  } catch { return null; }
}
