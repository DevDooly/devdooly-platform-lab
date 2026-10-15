import copy
import importlib.util
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('object_reference_planner', ROOT / 'infra/maintenance/object_reference_plan.py')
m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
NOW = '2026-10-15T12:00:00Z'
SHA = 'a' * 64


def isolated():
    objects = [{'key': 'canary/' + name, 'size': 100, 'sha256': SHA, 'contentVerified': True} for name in 'abcd']
    return {'schemaVersion': 1, 'kind': 'object-reference-inventory', 'scope': 'ISOLATED_CANARY_REFERENCE_FIXTURE',
        'noApplicationDatabase': True, 'capturedAt': NOW, 'database': None,
        'listings': [{'storeId': 'isolated-gc', 'bucket': 'fresh-gc-bucket', 'complete': True, 'objects': objects}],
        'canaries': [{'storeId': 'isolated-gc', 'bucket': 'fresh-gc-bucket', **{key: obj[key] for key in ('key', 'size', 'sha256')}, 'deleteEligible': True} for obj in objects],
        'protectedReferences': [{'storeId': 'isolated-gc', 'bucket': 'fresh-gc-bucket', 'key': 'canary/b', 'reason': 'FIXTURE_EXPORTED'},
            {'storeId': 'isolated-gc', 'bucket': 'fresh-gc-bucket', 'key': 'canary/d', 'reason': 'FIXTURE_PENDING'}]}


def production():
    jobs = [{'runId': name, 'scenarioVersion': 'sensor-validation-v2', 'sourceSha256': SHA, 'status': status, 'exportStatus': export}
            for name, status, export in (('staging', 'STAGING', 'NOT_REQUESTED'), ('queued', 'QUEUED', 'NOT_REQUESTED'),
                ('pending', 'COMPLETED', 'PENDING'), ('exported', 'COMPLETED', 'EXPORTED'), ('terminated', 'TERMINATED', 'NOT_REQUESTED'))]
    objects = [{'key': kind + '/' + job['runId'] + '/content', 'size': 100, 'sha256': SHA, 'contentVerified': True} for job in jobs for kind in ('raw', 'result')]
    objects.append({'key': 'unknown-orphan', 'size': 100, 'sha256': None, 'contentVerified': False})
    return {'schemaVersion': 1, 'kind': 'object-reference-inventory', 'scope': 'PRODUCTION_REFERENCES',
        'noApplicationDatabase': False, 'capturedAt': NOW,
        'database': {'storeId': 'production', 'bucket': 'original-bucket', 'sourceCommit': 'b' * 40, 'complete': True,
            'consistentSnapshot': True, 'expectedJobCount': len(jobs), 'expectedOutboxCount': 0, 'expectedSlotCount': 1,
            'jobs': jobs, 'outbox': [], 'slotRunId': None, 'runtimeStatus': 'RUNNING'},
        'listings': [{'storeId': 'production', 'bucket': 'original-bucket', 'complete': True, 'objects': objects}],
        'canaries': [], 'protectedReferences': []}


class PlannerTests(unittest.TestCase):
    def plan(self, value, now=NOW): return m.build_plan(value, now=now)

    def test_only_two_registered_unreferenced_canaries_candidate(self):
        plan = self.plan(isolated())
        self.assertEqual(['canary/a', 'canary/c'], [row['key'] for row in plan['entries'] if row['action'] == 'DELETE_CANDIDATE'])
        self.assertFalse(plan['applyEnabled']); self.assertFalse(plan['deletionExecutorImplemented'])
        self.assertTrue(plan['noApplicationDatabase'])

    def test_all_actual_db_reference_statuses_and_unknown_protected(self):
        plan = self.plan(production()); self.assertEqual(0, plan['candidateCount'])
        self.assertEqual(11, plan['protectedCount'])
        for row in plan['entries'][:-1]:
            self.assertIn('DATABASE_RUN_REFERENCE', row['reasons'])

    def test_pure_no_mutation_and_repeat_determinism(self):
        value = isolated(); before = copy.deepcopy(value)
        self.assertEqual(self.plan(value), self.plan(value)); self.assertEqual(before, value)

    def test_scope_cannot_fabricate_database(self):
        for field, changed in (('database', production()['database']), ('noApplicationDatabase', False), ('scope', 'UNKNOWN')):
            value = isolated(); value[field] = changed
            with self.assertRaises(ValueError): self.plan(value)

    def test_production_never_registers_canary(self):
        value = production(); value['canaries'] = isolated()['canaries']
        with self.assertRaises(ValueError): self.plan(value)

    def test_stale_listing_and_clock_fail_closed(self):
        self.assertEqual(0, self.plan(isolated(), '2026-10-15T12:05:00.000001Z')['candidateCount'])
        value = isolated(); value['listings'][0]['complete'] = False
        self.assertEqual(0, self.plan(value)['candidateCount'])
        with self.assertRaises(ValueError): self.plan(isolated(), '2026-10-15T11:59:59.999999Z')

    def test_nano_timestamp_supported_and_exact_boundary(self):
        value = isolated(); value['capturedAt'] = '2026-10-15T12:00:00.123456789Z'
        self.assertEqual(2, self.plan(value, '2026-10-15T12:05:00.123456789Z')['candidateCount'])
        self.assertEqual(0, self.plan(value, '2026-10-15T12:05:00.123456790Z')['candidateCount'])
        with self.assertRaises(ValueError): self.plan(value, '2026-10-15T12:00:00.123456788Z')

    def test_partial_or_inconsistent_db_has_no_candidates_and_reason(self):
        for field, changed in (('complete', False), ('consistentSnapshot', False), ('expectedJobCount', 6), ('expectedOutboxCount', 1), ('expectedSlotCount', 0)):
            value = production(); value['database'][field] = changed
            self.assertTrue(all('DATABASE_SNAPSHOT_INCOMPLETE' in row['reasons'] for row in self.plan(value)['entries']))

    def test_paused_unknown_slot_pending_outbox_reasons(self):
        for status in ('PAUSED_OPERATOR', 'UNKNOWN'):
            value = production(); value['database']['runtimeStatus'] = status
            self.assertTrue(all('RUNTIME_PAUSED_OR_UNKNOWN' in row['reasons'] for row in self.plan(value)['entries']))
        value = production(); value['database']['slotRunId'] = 'pending'
        self.assertTrue(all('EXECUTION_SLOT_OCCUPIED' in row['reasons'] for row in self.plan(value)['entries']))
        value = production(); value['database']['outbox'] = [{'jobRunId': 'pending', 'eventType': 'EXPORT', 'status': 'PENDING'}]; value['database']['expectedOutboxCount'] = 1
        self.assertTrue(all('OUTBOX_PENDING_OR_UNKNOWN' in row['reasons'] for row in self.plan(value)['entries']))

    def test_backup_reference_overrides_eligible_canary(self):
        value = isolated(); value['protectedReferences'].append({'storeId': 'isolated-gc', 'bucket': 'fresh-gc-bucket', 'key': 'canary/a', 'reason': 'BACKUP'})
        self.assertEqual(1, self.plan(value)['candidateCount'])

    def test_size_hash_and_unverified_identity_keep(self):
        for field, changed in (('size', 101), ('sha256', 'c' * 64), ('contentVerified', False)):
            value = isolated(); value['listings'][0]['objects'][0][field] = changed
            self.assertEqual(1, self.plan(value)['candidateCount'])

    def test_same_payload_different_keys_not_same_reference(self):
        value = isolated(); self.assertEqual(value['canaries'][0]['sha256'], value['canaries'][1]['sha256'])
        entries = {row['key']: row for row in self.plan(value)['entries']}
        self.assertEqual('DELETE_CANDIDATE', entries['canary/a']['action']); self.assertEqual('KEEP', entries['canary/b']['action'])

    def test_unknown_unregistered_and_ineligible_always_keep(self):
        value = isolated(); value['canaries'][0]['deleteEligible'] = False
        value['listings'][0]['objects'].append({'key': 'canary/not-registered', 'size': 1, 'sha256': SHA, 'contentVerified': True})
        self.assertEqual(1, self.plan(value)['candidateCount']); self.assertEqual(4, self.plan(value)['protectedCount'])

    def test_duplicate_identity_unknown_fields_version_enum_rejected(self):
        for mutate in (lambda v: v.update(extra=True), lambda v: v.update(schemaVersion=2),
            lambda v: v['listings'].append(copy.deepcopy(v['listings'][0])),
            lambda v: v['listings'][0]['objects'].append(copy.deepcopy(v['listings'][0]['objects'][0])),
            lambda v: v['protectedReferences'][0].update(reason='UNKNOWN')):
            value = isolated(); mutate(value)
            with self.assertRaises(ValueError): self.plan(value)

    def test_traversal_empty_control_and_absolute_keys_rejected(self):
        for changed in ('../x', '/x', 'a/../x', 'a//x', 'a/./x', 'x\n', 'a/'):
            value = isolated(); value['listings'][0]['objects'][0]['key'] = changed
            with self.assertRaises(ValueError): self.plan(value)

    def test_run_prefix_must_end_in_slash(self):
        value = production(); value['listings'][0]['objects'][0]['key'] = 'raw/staging-other/content'
        row = next(row for row in self.plan(value)['entries'] if row['key'] == 'raw/staging-other/content')
        self.assertIn('UNKNOWN_PRODUCTION_OBJECT_PROTECTED', row['reasons'])

    def test_duplicate_json_key_and_bool_integer_rejected(self):
        with self.assertRaises(ValueError): json.loads('{"x":1,"x":2}', object_pairs_hook=m.no_duplicate_json)
        value = isolated(); value['listings'][0]['objects'][0]['size'] = True
        with self.assertRaises(ValueError): self.plan(value)

    def test_invalid_fk_and_state_combinations_rejected(self):
        value = production(); value['database']['jobs'][0]['exportStatus'] = 'EXPORTED'
        with self.assertRaises(ValueError): self.plan(value)
        value = production(); value['database']['slotRunId'] = 'missing'
        with self.assertRaises(ValueError): self.plan(value)

    def test_actual_early_and_completed_operator_termination_states_protected(self):
        value = production(); value['database']['jobs'][0].update(status='TERMINATED', exportStatus='NOT_REQUESTED')
        value['database']['jobs'][2].update(status='COMPLETED', exportStatus='CANCELLED')
        self.assertEqual(0, self.plan(value)['candidateCount'])
        value['database']['jobs'][0]['exportStatus'] = 'CANCELLED'
        with self.assertRaises(ValueError): self.plan(value)

    def test_duplicate_outbox_identity_rejected(self):
        value = production(); row = {'jobRunId': 'pending', 'eventType': 'EXPORT', 'status': 'PENDING'}
        value['database']['outbox'] = [row, copy.deepcopy(row)]; value['database']['expectedOutboxCount'] = 2
        with self.assertRaises(ValueError): self.plan(value)


if __name__ == '__main__': unittest.main()
