"""Offline public synthetic inputs -> existing Python planner -> display-only JSON."""
from pathlib import Path
import argparse
import copy
import hashlib
import importlib.util
import json

ROOT = Path(__file__).resolve().parents[2]
FIXTURES = Path(__file__).resolve().parent / 'fixtures'
PLANNER = ROOT / 'infra/maintenance/iceberg_retention_plan.py'
PLANNER_SHA256 = 'ec1ff5dc06d9da666d9ef1d32557937e36e0a63bc124f08ad6ed39edbf0224ae'
PLANNER_SOURCE_COMMIT = '245d61a5749760a20918ab091d9410ce6735b1c0'
PLANNER_SOURCE_TREE = '3216836b9d0329a0616234edb36316aff9b75f9b'
OUTPUT = ROOT / 'apps/lab-web/src/data/iceberg-policy-scenarios.generated.json'
NOW = '2026-10-16T12:00:00.123456789Z'
POLICY = {'schemaVersion': 1, 'maxInventoryAgeSeconds': 300,
          'minSnapshotAgeSeconds': 604800, 'minimumSnapshotsToKeep': 1}
SCENARIOS = (
    ('current-ancestor', '현재 이력에 연결된 오래된 snapshot', '현재 snapshot의 조상은 오래됐어도 보호합니다.',
     'snapshot100의 parent를900으로 연결: current300 → 200 → 100 → 900', NOW, 'current-ancestor.inventory.json'),
    ('detached-candidate', '보호 범위 밖의 오래된 detached snapshot', '분리된900만 만료 검토 후보이며 파일은 모두 보호합니다.',
     '기준 공개 fixture: current/ref/pin 밖의 오래된900', NOW, 'detached-candidate.inventory.json'),
    ('stale-inventory', '수집 뒤300초를 넘긴 입력', '오래된 입력에서는 후보 판정을 보류합니다.',
     '기준 입력 그대로, 가정 평가 시각만 수집 뒤300초+1ns',
     '2026-10-16T12:05:00.123456790Z', 'stale-inventory.inventory.json'),
)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def load_planner():
    raw = PLANNER.read_bytes()
    if len(raw) > 131072 or sha(raw) != PLANNER_SHA256:
        raise ValueError('PUBLIC_PLANNER_SOURCE_UNVERIFIED')
    spec = importlib.util.spec_from_file_location('public_synthetic_retention_planner', PLANNER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def require_public_synthetic(value):
    if (type(value) is not dict or value.get('scope') != 'SYNTHETIC_REFERENCE_FIXTURE'
            or value.get('tableId') != 'synthetic-table'):
        raise ValueError('PUBLIC_SYNTHETIC_FIXTURE_REQUIRED')


def build_bundle():
    planner = load_planner()
    records, inputs = [], []
    for identifier, label, description, change, now, filename in SCENARIOS:
        raw = (FIXTURES / filename).read_bytes()
        if len(raw) > 65536:
            raise ValueError('PUBLIC_FIXTURE_SIZE_BOUND')
        value = planner.parse_json(raw)
        require_public_synthetic(value)
        before = copy.deepcopy(value)
        policy = copy.deepcopy(POLICY)
        plan = planner.build_plan(value, policy, now=now)
        if value != before or policy != POLICY:
            raise ValueError('PURE_PLANNER_INPUT_MUTATION')
        if (plan['inventoryScope'] != 'SYNTHETIC_REFERENCE_FIXTURE'
                or any(plan[key] is not False for key in
                    ('applyEnabled', 'deletionExecutorImplemented', 'inventoryClaimsIndependentlyVerified'))):
            raise ValueError('SYNTHETIC_PLAN_SCOPE_REQUIRED')
        inputs.append({'file': filename, 'bytes': len(raw), 'sha256': sha(raw)})
        records.append({'id': identifier, 'label': label, 'description': description,
            'changedCondition': change, 'fixtureFile': filename, 'fixtureBytesSha256': sha(raw), 'plan': plan})
    return {'schemaVersion': 1, 'kind': 'iceberg-policy-scenarios', 'scope': 'SYNTHETIC_REFERENCE_FIXTURE',
        'policy': POLICY, 'provenance': {'plannerSourceCommit': PLANNER_SOURCE_COMMIT,
            'plannerSourceTree': PLANNER_SOURCE_TREE, 'plannerSourceSha256': PLANNER_SHA256,
            'generatorSourceCommit': None, 'generatorSourceSha256': sha(Path(__file__).read_bytes()),
            'publicFixtureInputs': inputs, 'offlineComputation': True, 'onlyPublicFixtures': True,
            'liveMetadataCollected': False, 'serviceCommandsExecuted': False, 'wallClockEvaluation': False},
        'scenarios': records}


def encode_bundle(value):
    raw = (json.dumps(value, ensure_ascii=False, allow_nan=False, sort_keys=True, indent=2) + '\n').encode('utf-8')
    if len(raw) > 65536:
        raise ValueError('SYNTHETIC_BUNDLE_SIZE_BOUND')
    return raw


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    value = build_bundle()
    raw = encode_bundle(value)
    if args.check:
        if OUTPUT.read_bytes() != raw:
            raise SystemExit('GENERATED_PUBLIC_BUNDLE_DIFFERENCE')
    else:
        OUTPUT.parent.mkdir(parents=True, exist_ok=True)
        with OUTPUT.open('xb') as stream:
            stream.write(raw)
    print(json.dumps({'scope': value['scope'], 'scenarioCount': len(value['scenarios']),
        'bytes': len(raw), 'sha256': sha(raw),
        'snapshotCandidateCounts': [item['plan']['snapshotCandidateCount'] for item in value['scenarios']],
        'objectCandidateCounts': [item['plan']['objectCandidateCount'] for item in value['scenarios']],
        'existingOutputCompared': args.check}))
