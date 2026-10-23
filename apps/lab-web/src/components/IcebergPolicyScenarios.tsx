import { useEffect, useMemo, useState } from 'react';
import '../styles/iceberg-policy-scenarios.css';

type Action = 'KEEP' | 'EXPIRATION_CANDIDATE';
type Row = { id: string; action: Action; reasons: string[] };
type Plan = { schemaVersion: 1; kind: string; status: 'DETERMINED' | 'UNDETERMINED'; inventoryScope: string;
  tableId: string; inventoryCapturedAt: string; evaluatedAt: string; evaluationTimeProvidedByCaller: true;
  inventorySha256: string; suppressionReasons: string[]; snapshots: Row[]; files: Row[];
  snapshotCandidateCount: number; objectCandidateCount: 0; applyEnabled: false; deletionExecutorImplemented: false;
  inventoryClaimsIndependentlyVerified: false };
type Scenario = { id: string; label: string; description: string; changedCondition: string;
  fixtureFile: string; fixtureBytesSha256: string; plan: Plan };
type Bundle = { schemaVersion: 1; kind: string; scope: string;
  policy: { schemaVersion: 1; maxInventoryAgeSeconds: number; minSnapshotAgeSeconds: number; minimumSnapshotsToKeep: number };
  provenance: { plannerSourceCommit: string; plannerSourceTree: string; plannerSourceSha256: string;
    generatorSourceCommit: null; generatorSourceSha256: string; publicFixtureInputs: { file: string; bytes: number; sha256: string }[];
    offlineComputation: true; onlyPublicFixtures: true; liveMetadataCollected: false; serviceCommandsExecuted: false; wallClockEvaluation: false };
  scenarios: Scenario[] };
const repo = 'https://github.com/DevDooly/devdooly-platform-lab';
const ids = ['current-ancestor', 'detached-candidate', 'stale-inventory'];
const reasonText: Record<string, string> = {
  CURRENT_SNAPSHOT: '현재 snapshot', CURRENT_ANCESTOR: '현재 snapshot의 조상', REF_SNAPSHOT: 'branch·tag의 직접 참조',
  REF_ANCESTOR: 'branch·tag가 보호하는 조상', BACKUP_PIN: '백업 시점 보호', BACKUP_ANCESTOR: '백업 시점의 조상',
  VALIDATION_PIN: '검증 시점 보호', VALIDATION_ANCESTOR: '검증 시점의 조상', MINIMUM_SNAPSHOT_COUNT: '최소 보관 수',
  WITHIN_MINIMUM_AGE: '최소 경과 기간 이내', OLD_DETACHED_HISTORY_ONLY: '보호 범위 밖의 오래된 detached 이력',
  UNDETERMINED_INVENTORY: '판정을 보류한 입력', RETAINED_SNAPSHOT_REFERENCE: '보호 중인 snapshot이 참조',
  CANDIDATE_SNAPSHOT_NOT_EXPIRED: '후보 snapshot은 아직 만료되지 않음', SHARED_SNAPSHOT_FILE: '여러 snapshot이 공유',
  BACKUP_FILE_PIN: '백업 파일 보호', VALIDATION_FILE_PIN: '검증 파일 보호',
  METADATA_OR_UNKNOWN_ALWAYS_PROTECTED: 'metadata 또는 종류가 불명인 파일 보호', UNREFERENCED_FILE_NOT_AUTHORIZED: '참조가 없어도 삭제 판단을 하지 않음',
};
const object = (value: unknown): value is Record<string, any> => value !== null && typeof value === 'object' && !Array.isArray(value);
const exact = (value: Record<string, unknown>, names: string) => Object.keys(value).sort().join(' ') === names.split(' ').sort().join(' ');
const text = (value: unknown, maximum = 300): value is string => typeof value === 'string' && value.length > 0 && value.length <= maximum;
const hash = (value: unknown): value is string => typeof value === 'string' && /^[a-f0-9]{64}$/.test(value);
const commit = (value: unknown): value is string => typeof value === 'string' && /^[a-f0-9]{40}$/.test(value);
const stamp = (value: unknown) => typeof value === 'string'
  && ['2026-10-16T12:00:00.123456789Z', '2026-10-16T12:05:00.123456790Z'].includes(value);

/** Validate saved public display data only. No graph, age, retention decision, or live request is computed here. */
export function parsePolicyScenarios(value: unknown): Bundle | null {
  if (!object(value) || !exact(value, 'schemaVersion kind scope policy provenance scenarios') || value.schemaVersion !== 1
    || value.kind !== 'iceberg-policy-scenarios' || value.scope !== 'SYNTHETIC_REFERENCE_FIXTURE') return null;
  const policy = value.policy, provenance = value.provenance;
  if (!object(policy) || !exact(policy, 'schemaVersion maxInventoryAgeSeconds minSnapshotAgeSeconds minimumSnapshotsToKeep')
    || policy.schemaVersion !== 1 || policy.maxInventoryAgeSeconds !== 300 || policy.minSnapshotAgeSeconds !== 604800 || policy.minimumSnapshotsToKeep !== 1) return null;
  if (!object(provenance) || !exact(provenance, 'plannerSourceCommit plannerSourceTree plannerSourceSha256 generatorSourceCommit generatorSourceSha256 publicFixtureInputs offlineComputation onlyPublicFixtures liveMetadataCollected serviceCommandsExecuted wallClockEvaluation')
    || !commit(provenance.plannerSourceCommit) || !commit(provenance.plannerSourceTree) || !hash(provenance.plannerSourceSha256)
    || provenance.generatorSourceCommit !== null || !hash(provenance.generatorSourceSha256)
    || provenance.offlineComputation !== true || provenance.onlyPublicFixtures !== true || provenance.liveMetadataCollected !== false
    || provenance.serviceCommandsExecuted !== false || provenance.wallClockEvaluation !== false
    || !Array.isArray(provenance.publicFixtureInputs) || provenance.publicFixtureInputs.length !== 3) return null;
  if (!Array.isArray(value.scenarios) || value.scenarios.length !== 3) return null;
  const rows = (items: unknown, files: boolean): items is Row[] => Array.isArray(items) && items.length === 9
    && items.every(item => object(item) && exact(item, 'id action reasons') && text(item.id, 80) && /^[A-Za-z0-9][A-Za-z0-9._-]{0,79}$/.test(item.id)
      && (files ? item.action === 'KEEP' : item.action === 'KEEP' || item.action === 'EXPIRATION_CANDIDATE')
      && Array.isArray(item.reasons) && item.reasons.length > 0 && item.reasons.length <= 12
      && item.reasons.every((reason: unknown) => typeof reason === 'string' && Object.hasOwn(reasonText, reason))
      && new Set(item.reasons).size === item.reasons.length)
    && new Set(items.map(item => item.id)).size === items.length;
  for (let index = 0; index < 3; index++) {
    const item = value.scenarios[index], input = provenance.publicFixtureInputs[index];
    if (!object(item) || !exact(item, 'id label description changedCondition fixtureFile fixtureBytesSha256 plan') || item.id !== ids[index]
      || !text(item.label) || !text(item.description) || !text(item.changedCondition) || item.fixtureFile !== `${item.id}.inventory.json`
      || !hash(item.fixtureBytesSha256) || !object(input) || !exact(input, 'file bytes sha256') || input.file !== item.fixtureFile
      || !Number.isSafeInteger(input.bytes) || input.bytes <= 0 || input.bytes > 65536 || input.sha256 !== item.fixtureBytesSha256) return null;
    const plan = item.plan;
    if (!object(plan) || !exact(plan, 'schemaVersion kind status inventoryScope tableId inventoryCapturedAt evaluatedAt evaluationTimeProvidedByCaller inventorySha256 suppressionReasons snapshots files snapshotCandidateCount objectCandidateCount applyEnabled deletionExecutorImplemented inventoryClaimsIndependentlyVerified')
      || plan.schemaVersion !== 1 || plan.kind !== 'iceberg-retention-plan' || !['DETERMINED', 'UNDETERMINED'].includes(plan.status)
      || plan.inventoryScope !== 'SYNTHETIC_REFERENCE_FIXTURE' || plan.tableId !== 'synthetic-table' || !stamp(plan.inventoryCapturedAt) || !stamp(plan.evaluatedAt)
      || plan.evaluationTimeProvidedByCaller !== true || !hash(plan.inventorySha256) || !rows(plan.snapshots, false) || !rows(plan.files, true)
      || !plan.snapshots.some((row: Row) => row.id === '900') || !['candidate-only-data', 'shared-data'].every(id => plan.files.some((row: Row) => row.id === id))
      || !Number.isSafeInteger(plan.snapshotCandidateCount) || plan.snapshotCandidateCount !== plan.snapshots.filter((row: Row) => row.action === 'EXPIRATION_CANDIDATE').length
      || plan.objectCandidateCount !== 0 || plan.applyEnabled !== false || plan.deletionExecutorImplemented !== false || plan.inventoryClaimsIndependentlyVerified !== false
      || !Array.isArray(plan.suppressionReasons) || plan.suppressionReasons.some((reason: unknown) => reason !== 'STALE_INVENTORY')
      || (plan.status === 'UNDETERMINED' ? plan.snapshotCandidateCount !== 0 || plan.suppressionReasons.length !== 1 : plan.suppressionReasons.length !== 0)) return null;
  }
  return value as Bundle;
}

function ReasonRow({ row, title }: { row: Row; title: string }) {
  return <article className="policy-example-row"><div><h4>{title}</h4><span className={row.action === 'KEEP' ? 'policy-keep' : 'policy-candidate'}>{row.action === 'KEEP' ? 'KEEP · 보호' : '만료 검토 후보'}</span></div>
    <ul>{row.reasons.map(reason => <li key={reason}>{reasonText[reason]} <code>{reason}</code></li>)}</ul></article>;
}

export default function IcebergPolicyScenarios({ bundle, initialScenarioId = 'current-ancestor' }: { bundle: unknown; initialScenarioId?: string }) {
  const data = useMemo(() => parsePolicyScenarios(bundle), [bundle]);
  const [selectedId, setSelectedId] = useState(initialScenarioId);
  const [interactive, setInteractive] = useState(false);
  useEffect(() => { setInteractive(true); }, []);
  const selected = data?.scenarios.find(item => item.id === selectedId) ?? data?.scenarios[0];
  return <section id="iceberg-policy-scenarios" className="section policy-examples" aria-labelledby="policy-examples-title">
    <div className="section-heading"><div><span className="eyebrow">SYNTHETIC / SAVED PYTHON RESULTS</span>
      <h2 id="policy-examples-title">보존 조건에 따른 판단을 살펴봅니다.</h2><p>공개 합성 입력으로 미리 계산한 세 결과를 선택합니다.</p></div><span className="tag">합성 정책 예제</span></div>
    <p id="policy-examples-hint">같은 정책에서 parent 연결 또는 가정 시각만 바꿨습니다. 개인 합성 snapshot9개·파일9개의 입력이며 기존 Cloud 검증 기록과 별도입니다.</p>
    {data && selected ? <>
      <div className="policy-example-select" aria-busy={!interactive}><label htmlFor="policy-example-choice">합성 조건</label><select id="policy-example-choice" value={selected.id} disabled={!interactive} aria-describedby="policy-examples-hint policy-examples-input-help" onChange={event => setSelectedId(event.target.value)}>{data.scenarios.map(item => <option key={item.id} value={item.id}>{item.label}</option>)}</select>
        <p id="policy-examples-input-help" className="policy-example-note">{!interactive && '화면 조작 준비 중입니다. '}선택은 저장된 합성 결과만 바꿉니다. 새 계산·서버 작업을 실행하지 않습니다.</p></div>
      <p className="policy-example-policy">고정 정책 · 최소 경과7일 · 최소 보관1개 · 입력 유효300초</p>
      <div className={`policy-example-outcome${selected.plan.status === 'UNDETERMINED' ? ' policy-example-undetermined' : ''}`}>
        <p role="status" aria-live="polite" aria-atomic="true">{selected.label} · {selected.plan.status === 'UNDETERMINED' ? '판정 보류' : '보존 계획 확인'}</p>
        <h3>{selected.description}</h3><p>{selected.changedCondition}</p>
        {selected.plan.status === 'UNDETERMINED' && <p>입력의 유효300초를 넘겨 후보를 억제했습니다. KEEP은 판정을 보류하며 보호한 결과입니다. <code>STALE_INVENTORY</code></p>}
      </div>
      <dl className="policy-example-counts"><div><dt>snapshot KEEP</dt><dd>{selected.plan.snapshots.filter(row => row.action === 'KEEP').length}<small>개</small></dd></div><div><dt>snapshot 만료 검토 후보</dt><dd>{selected.plan.snapshotCandidateCount}<small>개</small></dd></div><div><dt>파일 KEEP</dt><dd>{selected.plan.files.length}<small>개</small></dd></div></dl>
      <p className="policy-example-note">객체 후보0개는 모든 파일을 보호하는 이 planner의 정책입니다. snapshot 후보도 실행되지 않은 검토 대상이며 삭제·GC·회수 용량의 결과가 아닙니다.</p>
      <div className="policy-example-rows"><ReasonRow row={selected.plan.snapshots.find(row => row.id === '900')!} title="snapshot900"/>
        <ReasonRow row={selected.plan.files.find(row => row.id === 'candidate-only-data')!} title="후보가 참조한 파일"/>
        <ReasonRow row={selected.plan.files.find(row => row.id === 'shared-data')!} title="여러 snapshot이 공유하는 파일"/></div>
      <details className="policy-example-details"><summary>전체 snapshot9개·파일9개와 생성 근거</summary><p>가정 평가 시각 <code>{selected.plan.evaluatedAt}</code> · 실제 시계 평가가 아닙니다.</p>
        <h3>snapshot</h3><ul className="policy-example-full">{selected.plan.snapshots.map(row => <li key={row.id}><code>{row.id}</code><strong>{row.action === 'KEEP' ? 'KEEP · 보호' : '만료 검토 후보'}</strong><p>{row.reasons.map(reason => reasonText[reason]).join(' · ')}</p></li>)}</ul>
        <h3>파일 · 모두 KEEP</h3><ul className="policy-example-full">{selected.plan.files.map(row => <li key={row.id}><code>{row.id}</code><p>{row.reasons.map(reason => reasonText[reason]).join(' · ')}</p></li>)}</ul>
        <dl className="policy-example-provenance"><div><dt>Python planner source</dt><dd><code>{data.provenance.plannerSourceCommit}</code></dd></div><div><dt>planner 파일 SHA-256</dt><dd><code>{data.provenance.plannerSourceSha256}</code></dd></div><div><dt>공개 합성 JSON bytes SHA-256</dt><dd><code>{selected.fixtureBytesSha256}</code></dd></div><div><dt>정규화 입력 SHA-256</dt><dd><code>{selected.plan.inventorySha256}</code></dd></div></dl>
        <p>생성기 commit은 미확정이며 파일 hash로 연결합니다. 관측 주장의 독립 검증·apply·삭제 실행기는 모두 false입니다. 실제9 summary에서 graph를 복원하거나 이 합성 결과와 합산하지 않았습니다.</p></details>
      <div className="policy-example-links"><a href={`${repo}/tree/main/examples/iceberg-retention-scenarios`} target="_blank" rel="noreferrer">공개 입력과 생성 절차 ↗</a><a href={`${repo}/blob/${data.provenance.plannerSourceCommit}/infra/maintenance/iceberg_retention_plan.py`} target="_blank" rel="noreferrer">실제 Python planner ↗</a></div>
    </> : <p className="policy-example-unavailable" role="status">합성 계산 기록을 확인할 수 없습니다.</p>}
  </section>;
}
