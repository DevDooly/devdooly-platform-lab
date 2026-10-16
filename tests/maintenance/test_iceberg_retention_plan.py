import ast
import copy
import importlib.util
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / 'infra/maintenance/iceberg_retention_plan.py'
spec = importlib.util.spec_from_file_location('iceberg_retention_plan', SOURCE)
m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
NOW = '2026-10-16T12:00:00.123456789Z'
POLICY = {'schemaVersion': 1, 'maxInventoryAgeSeconds': 300,
          'minSnapshotAgeSeconds': 7 * 86400, 'minimumSnapshotsToKeep': 1}


def fixture():
    old = '2026-10-01T00:00:00Z'
    snapshots = [{'id': sid, 'parentId': parent, 'committedAt': old, 'fileIds': [file]}
        for sid, parent, file in [('100', None, 'initial-manifest'), ('200', '100', 'shared-data'),
            ('300', '200', 'shared-data'), ('400', None, 'tag-data'), ('500', '400', 'tag-data'),
            ('600', None, 'backup-data'), ('700', None, 'validation-data'), ('800', None, 'recent-data'),
            ('900', None, 'candidate-only-data')]]
    snapshots[7]['committedAt'] = '2026-10-16T11:00:00Z'
    snapshots[8]['fileIds'].append('shared-data')
    return {'schemaVersion': 1, 'kind': 'iceberg-retention-inventory', 'scope': 'SYNTHETIC_REFERENCE_FIXTURE',
        'tableId': 'synthetic-table', 'capturedAt': NOW,
        'observations': {'complete': True, 'refsComplete': True, 'pinsComplete': True,
            'snapshotFileClosureComplete': True, 'writersQuiescent': True,
            'metadataBeforeId': 'metadata-pointer-1', 'metadataAfterId': 'metadata-pointer-1',
            'metadataBeforeSha256': 'a' * 64, 'metadataAfterSha256': 'a' * 64},
        'currentSnapshotId': '300', 'snapshots': snapshots,
        'refs': [{'name': 'main', 'kind': 'BRANCH', 'snapshotId': '300'},
                 {'name': 'keep-tag', 'kind': 'TAG', 'snapshotId': '500'}],
        'pins': [{'id': 'backup-1', 'kind': 'BACKUP', 'snapshotIds': ['600'], 'fileIds': ['backup-data']},
                 {'id': 'validation-1', 'kind': 'VALIDATION', 'snapshotIds': ['700'], 'fileIds': ['validation-data']}],
        'files': [{'id': name, 'kind': kind} for name, kind in [
            ('initial-manifest', 'MANIFEST_LIST'), ('shared-data', 'DATA'), ('tag-data', 'DELETE'),
            ('backup-data', 'DATA'), ('validation-data', 'MANIFEST'), ('recent-data', 'DATA'),
            ('candidate-only-data', 'DATA'), ('table-metadata', 'METADATA'), ('unreferenced-data', 'DATA')]]}


class IcebergRetentionTests(unittest.TestCase):
    def plan(self, value=None, *, now=NOW, policy=None):
        return m.build_plan(fixture() if value is None else value, POLICY if policy is None else policy, now=now)

    def test_only_old_detached_snapshot_is_a_non_actionable_candidate(self):
        plan = self.plan()
        self.assertEqual('DETERMINED', plan['status'])
        self.assertEqual(['900'], [row['id'] for row in plan['snapshots'] if row['action'] == 'EXPIRATION_CANDIDATE'])
        self.assertEqual(1, plan['snapshotCandidateCount']); self.assertEqual(0, plan['objectCandidateCount'])
        self.assertFalse(plan['applyEnabled']); self.assertFalse(plan['deletionExecutorImplemented'])
        self.assertFalse(plan['inventoryClaimsIndependentlyVerified'])
        captured = fixture(); captured['scope'] = 'CAPTURED_TABLE_METADATA'
        self.assertFalse(self.plan(captured)['inventoryClaimsIndependentlyVerified'])

    def test_current_all_ref_kinds_and_backup_validation_ancestors_are_protected(self):
        for kind in ('TAG', 'BRANCH'):
            value = fixture(); value['refs'][1]['kind'] = kind
            value['snapshots'][5]['parentId'] = '900'
            plan = self.plan(value); entries = {row['id']: row for row in plan['snapshots']}
            for sid in ('100', '200', '300', '400', '500', '600', '700', '900'):
                self.assertEqual('KEEP', entries[sid]['action'])
            self.assertIn('CURRENT_ANCESTOR', entries['100']['reasons'])
            self.assertIn('REF_ANCESTOR', entries['400']['reasons'])
            self.assertIn('BACKUP_ANCESTOR', entries['900']['reasons'])
        value = fixture(); value['snapshots'][6]['parentId'] = '900'
        self.assertIn('VALIDATION_ANCESTOR', {row['id']: row for row in self.plan(value)['snapshots']}['900']['reasons'])
        # An ordinary linear history has no candidate, however old its parents are.
        value = fixture(); value['snapshots'][0]['parentId'] = '900'
        self.assertEqual(0, self.plan(value)['snapshotCandidateCount'])

    def test_shared_pinned_metadata_and_unreferenced_files_all_stay_keep(self):
        plan = self.plan(); entries = {row['id']: row for row in plan['files']}
        self.assertTrue(all(row['action'] == 'KEEP' for row in entries.values()))
        self.assertIn('SHARED_SNAPSHOT_FILE', entries['shared-data']['reasons'])
        self.assertIn('RETAINED_SNAPSHOT_REFERENCE', entries['shared-data']['reasons'])
        self.assertIn('CANDIDATE_SNAPSHOT_NOT_EXPIRED', entries['candidate-only-data']['reasons'])
        self.assertIn('BACKUP_FILE_PIN', entries['backup-data']['reasons'])
        self.assertIn('VALIDATION_FILE_PIN', entries['validation-data']['reasons'])
        self.assertIn('METADATA_OR_UNKNOWN_ALWAYS_PROTECTED', entries['table-metadata']['reasons'])
        self.assertIn('UNREFERENCED_FILE_NOT_AUTHORIZED', entries['unreferenced-data']['reasons'])

    def test_incomplete_unstable_or_unknown_inventory_suppresses_every_candidate(self):
        variants = []
        for flag in m.FLAGS:
            value = fixture(); value['observations'][flag] = False; variants.append(value)
        value = fixture(); value['observations']['metadataAfterSha256'] = 'b' * 64; variants.append(value)
        value = fixture(); value['observations']['metadataAfterId'] = 'metadata-pointer-2'; variants.append(value)
        value = fixture(); value['files'][0]['kind'] = 'UNKNOWN'; variants.append(value)
        for value in variants:
            plan = self.plan(value)
            self.assertEqual('UNDETERMINED', plan['status']); self.assertTrue(plan['suppressionReasons'])
            self.assertEqual(0, plan['snapshotCandidateCount']); self.assertEqual(0, plan['objectCandidateCount'])
            self.assertTrue(all(row['action'] == 'KEEP' for row in plan['snapshots'] + plan['files']))

    def test_dangling_reference_cycles_and_inconsistent_parent_time_fail_closed(self):
        for change in [lambda v: v.update(currentSnapshotId='999'),
            lambda v: v['refs'][0].update(snapshotId='999'),
            lambda v: v['pins'][0]['snapshotIds'].append('999'),
            lambda v: v['pins'][0]['fileIds'].append('missing'),
            lambda v: v['snapshots'][0]['fileIds'].append('missing'),
            lambda v: v['snapshots'][0].update(parentId='999'),
            lambda v: v['snapshots'][0].update(parentId='300'),
            lambda v: v['snapshots'][0].update(committedAt='2026-10-02T00:00:00Z')]:
            value = fixture(); change(value); plan = self.plan(value)
            self.assertEqual('UNDETERMINED', plan['status']); self.assertEqual(0, plan['snapshotCandidateCount'])

    def test_nanosecond_age_freshness_minimum_count_and_future_clock_boundaries(self):
        self.assertEqual(1, self.plan(now='2026-10-16T12:05:00.123456789Z')['snapshotCandidateCount'])
        for now in ('2026-10-16T12:05:00.123456790Z', '2026-10-16T12:00:00.123456788Z'):
            self.assertEqual('UNDETERMINED', self.plan(now=now)['status'])
        value = fixture(); value['snapshots'][8]['committedAt'] = '2026-10-09T12:00:00.123456789Z'
        self.assertEqual(1, self.plan(value)['snapshotCandidateCount'])
        value['snapshots'][8]['committedAt'] = '2026-10-09T12:00:00.123456790Z'
        self.assertEqual(0, self.plan(value)['snapshotCandidateCount'])
        policy = {**POLICY, 'minimumSnapshotsToKeep': 9}
        self.assertEqual(0, self.plan(policy=policy)['snapshotCandidateCount'])
        value = fixture(); value['snapshots'][8]['committedAt'] = '2026-10-16T12:00:00.123456790Z'
        self.assertEqual('UNDETERMINED', self.plan(value)['status'])

    def test_exact_schema_types_aliases_bigints_and_duplicate_json_reject_without_values(self):
        for change in [lambda v: v.update(secret='private-sentinel'),
            lambda v: v['observations'].update(complete=1), lambda v: v.update(schemaVersion=True),
            lambda v: v['snapshots'].append(copy.deepcopy(v['snapshots'][0])),
            lambda v: v['files'].append(copy.deepcopy(v['files'][0])),
            lambda v: v['refs'].append(copy.deepcopy(v['refs'][0])),
            lambda v: v['pins'].append(copy.deepcopy(v['pins'][0])),
            lambda v: v['snapshots'][0]['fileIds'].append(v['snapshots'][0]['fileIds'][0]),
            lambda v: v.update(currentSnapshotId=300), lambda v: v.update(currentSnapshotId='9223372036854775808'),
            lambda v: v.update(tableId='../private-sentinel'), lambda v: v['files'][0].update(id='/private-sentinel'),
            lambda v: v.update(capturedAt='2026-02-30T12:00:00Z')]:
            value = fixture(); change(value)
            with self.assertRaises(ValueError) as caught: self.plan(value)
            self.assertRegex(str(caught.exception), r'^[A-Z_]+$'); self.assertNotIn('private-sentinel', str(caught.exception))
        for raw in ('{"secret":1,"secret":2}', '{"secret":"private-sentinel"', '{"x":NaN}', b'\xff'):
            with self.assertRaises(ValueError) as caught: m.parse_json(raw)
            self.assertRegex(str(caught.exception), r'^[A-Z_]+$'); self.assertNotIn('private-sentinel', str(caught.exception))
        self.assertEqual(fixture(), m.parse_json(json.dumps(fixture())))

    def test_deterministic_pure_input_unchanged_and_no_execution_modules(self):
        value, policy = fixture(), copy.deepcopy(POLICY)
        before, before_policy = copy.deepcopy(value), copy.deepcopy(policy)
        self.assertEqual(self.plan(value, policy=policy), self.plan(value, policy=policy))
        self.assertEqual(before, value); self.assertEqual(before_policy, policy)
        tree = ast.parse(SOURCE.read_text(encoding='utf-8'))
        imports = {node.names[0].name for node in ast.walk(tree) if isinstance(node, ast.Import)}
        self.assertEqual({'calendar', 'datetime', 'hashlib', 'json', 're'}, imports)
        self.assertFalse(any(isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
            and node.func.id in ('open', 'exec', 'eval', '__import__') for node in ast.walk(tree)))


if __name__ == '__main__':
    unittest.main()
