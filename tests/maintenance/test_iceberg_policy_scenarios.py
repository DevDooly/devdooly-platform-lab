"""Public synthetic source/output contracts only; no server, actual capture, or private inputs."""
from pathlib import Path
import copy
import hashlib
import importlib.util
import json
import unittest

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('public_scenario_generator', ROOT / 'examples/iceberg-retention-scenarios/generate_scenarios.py')
generator = importlib.util.module_from_spec(spec)
spec.loader.exec_module(generator)


class SyntheticScenarios(unittest.TestCase):
    def test_three_fixed_conditions_have_distinct_expected_boundaries(self):
        records = generator.build_bundle()['scenarios']
        self.assertEqual(['current-ancestor', 'detached-candidate', 'stale-inventory'], [item['id'] for item in records])
        self.assertEqual(['DETERMINED', 'DETERMINED', 'UNDETERMINED'], [item['plan']['status'] for item in records])
        self.assertEqual([0, 1, 0], [item['plan']['snapshotCandidateCount'] for item in records])
        plans = [item['plan'] for item in records]
        rows = [{row['id']: row for row in plan['snapshots']} for plan in plans]
        self.assertIn('CURRENT_ANCESTOR', rows[0]['900']['reasons'])
        self.assertIn('REF_ANCESTOR', rows[0]['900']['reasons'])
        self.assertEqual('EXPIRATION_CANDIDATE', rows[1]['900']['action'])
        self.assertEqual(['STALE_INVENTORY'], plans[2]['suppressionReasons'])
        self.assertTrue(all(row['action'] == 'KEEP' for row in plans[2]['snapshots']))

    def test_snapshot_candidate_never_becomes_a_file_deletion_candidate(self):
        records = generator.build_bundle()['scenarios']
        self.assertTrue(all(item['plan']['objectCandidateCount'] == 0 for item in records))
        self.assertTrue(all(len(item['plan']['files']) == 9 for item in records))
        self.assertTrue(all(row['action'] == 'KEEP' for item in records for row in item['plan']['files']))
        files = {row['id']: row for row in records[1]['plan']['files']}
        self.assertIn('CANDIDATE_SNAPSHOT_NOT_EXPIRED', files['candidate-only-data']['reasons'])
        self.assertIn('SHARED_SNAPSHOT_FILE', files['shared-data']['reasons'])
        self.assertIn('RETAINED_SNAPSHOT_REFERENCE', files['shared-data']['reasons'])
        self.assertIn('UNREFERENCED_FILE_NOT_AUTHORIZED', files['unreferenced-data']['reasons'])

    def test_generation_is_deterministic_and_public_sources_stay_unchanged(self):
        inputs = [generator.PLANNER, Path(generator.__file__)] + [generator.FIXTURES / row[-1] for row in generator.SCENARIOS]
        before = {path: hashlib.sha256(path.read_bytes()).hexdigest() for path in inputs}
        first = generator.encode_bundle(generator.build_bundle())
        self.assertEqual(first, generator.encode_bundle(generator.build_bundle()))
        self.assertEqual(first, generator.OUTPUT.read_bytes())
        self.assertEqual(before, {path: hashlib.sha256(path.read_bytes()).hexdigest() for path in inputs})

    def test_provenance_separates_fixture_bytes_and_canonical_planner_input_hash(self):
        bundle = generator.build_bundle()
        self.assertIsNone(bundle['provenance']['generatorSourceCommit'])
        self.assertTrue(bundle['provenance']['offlineComputation'])
        for item in bundle['scenarios']:
            raw = (generator.FIXTURES / item['fixtureFile']).read_bytes()
            self.assertEqual(hashlib.sha256(raw).hexdigest(), item['fixtureBytesSha256'])
            canonical = json.dumps(json.loads(raw), sort_keys=True, separators=(',', ':'), ensure_ascii=True, allow_nan=False).encode()
            self.assertEqual(hashlib.sha256(canonical).hexdigest(), item['plan']['inventorySha256'])
            for key in ('applyEnabled', 'deletionExecutorImplemented', 'inventoryClaimsIndependentlyVerified'):
                self.assertIs(item['plan'][key], False)

    def test_generator_scope_rejects_captured_or_unknown_inputs(self):
        value = json.loads((generator.FIXTURES / 'detached-candidate.inventory.json').read_bytes())
        for change in ({'scope': 'CAPTURED_TABLE_METADATA'}, {'tableId': 'unverified-table'}, {'scope': None}):
            changed = copy.deepcopy(value); changed.update(change)
            with self.assertRaisesRegex(ValueError, '^PUBLIC_SYNTHETIC_FIXTURE_REQUIRED$'):
                generator.require_public_synthetic(changed)


if __name__ == '__main__':
    unittest.main()
