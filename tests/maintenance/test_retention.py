import contextlib
import copy
import importlib.util
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
import uuid
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('retention', ROOT / 'infra/maintenance/retention.py')
r = importlib.util.module_from_spec(spec); spec.loader.exec_module(r)
POLICY = json.loads((ROOT / 'infra/maintenance/policy.json').read_text(encoding='utf-8'))
NOW = '2026-10-15T12:00:00Z'


def uid(number): return str(uuid.UUID(int=number))


def backup(identity, completed='2026-09-01T00:00:00Z', family='runtime-v1', kind='RUNTIME'):
    members = [{'id': role.lower(), 'role': role, 'path': '/private/backups/platform/' + identity + '/' + role.lower(),
        'resolvedPath': '/private/backups/platform/' + identity + '/' + role.lower(), 'isSymlink': False,
        'size': 100, 'sha256': ('a' if role == 'ARCHIVE' else 'b') * 64, 'verified': True}
        for role in ('ARCHIVE', 'VERIFICATION')]
    return {'id': identity, 'kind': kind, 'compatibilityFamily': family, 'completedAt': completed, 'state': 'VERIFIED',
        'complete': True, 'pinned': False, 'keyAvailable': True, 'requiredMemberIds': ['archive', 'verification'], 'members': members}


def trial(identity='trial', completed='2026-10-08T12:00:00Z', index=10, count=1):
    namespace = 'platform-lab-pvc-restore-' + identity
    volumes = []
    for offset in range(count):
        number = index * 100 + offset * 10
        name = 'data-' + identity + '-' + str(offset)
        volumes.append({'pvcName': name, 'pvcUid': uid(number), 'expectedPvcUid': uid(number), 'namespace': namespace,
            'pvName': 'pv-' + identity + '-' + str(offset), 'pvUid': uid(number + 1), 'expectedPvUid': uid(number + 1),
            'claimRef': {'name': name, 'namespace': namespace, 'uid': uid(number)},
            'path': '/private/storage/platform/' + name, 'resolvedPath': '/private/storage/platform/' + name,
            'isSymlink': False, 'mounted': False, 'bound': True, 'reclaimPolicy': 'Retain'})
    return {'id': identity, 'operation': '20261015', 'completedAt': completed, 'state': 'STOPPED', 'pinned': False,
        'original': False, 'namespace': {'name': namespace, 'uid': uid(index), 'expectedUid': uid(index),
            'labels': {'devdooly.io/purpose': 'runtime-pvc-restore', 'devdooly.io/operation': '20261015'}},
        'podsPresent': 0, 'workloadsStopped': True, 'backupGroupId': 'latest', 'evidenceSha256': 'c' * 64,
        'evidenceVerified': True, 'volumes': volumes}


def inventory(backups=None, trials=None):
    return {'schemaVersion': 1, 'kind': 'retention-inventory', 'capturedAt': NOW,
        'backupRoots': [{'path': '/private/backups/platform', 'resolvedPath': '/private/backups/platform', 'isSymlink': False}],
        'storageRoots': [{'path': '/private/storage/platform', 'resolvedPath': '/private/storage/platform', 'isSymlink': False}],
        'originalNamespaces': [{'name': 'platform-lab', 'uid': uid(1)}],
        'originalVolumes': [{'pvcUid': uid(2), 'pvUid': uid(3), 'path': '/private/storage/platform/original'}],
        'backupGroups': backups if backups is not None else [backup('latest', '2026-10-15T11:00:00Z'), backup('expired')],
        'trialGroups': trials or [], 'protectedArtifacts': []}


def plan(value, now=NOW): return r.build_plan(value, copy.deepcopy(POLICY), now=now)


def decisions(result, group='backupGroups'): return {item['id']: item for item in result[group]}


class RetentionTests(unittest.TestCase):
    def test_old_complete_group_is_one_candidate_with_all_hash_preconditions(self):
        result = decisions(plan(inventory()))
        self.assertEqual('KEEP', result['latest']['action'])
        candidate = result['expired']; self.assertEqual('DELETE_CANDIDATE', candidate['action'])
        self.assertEqual(2, len(candidate['preconditions']['members']))
        self.assertTrue(all(member['sha256'] for member in candidate['preconditions']['members']))

    def test_latest_verified_is_kept_forever_per_kind_and_compatibility_family(self):
        groups = [backup('db', family='db-v1', kind='DB'), backup('db-new-schema', family='db-v2', kind='DB'),
            backup('k3s', kind='K3S'), backup('jenkins', kind='JENKINS'), backup('runtime')]
        result = plan(inventory(groups))
        self.assertEqual(0, result['summary']['backupCandidates'])
        self.assertTrue(all('LATEST_VERIFIED_FAMILY' in item['reasons'] for item in result['backupGroups']))

    def test_incomplete_newer_backup_does_not_replace_last_complete_verified_anchor(self):
        old = backup('old'); newer = backup('newer', '2026-10-15T11:00:00Z'); newer['complete'] = False
        result = decisions(plan(inventory([old, newer])))
        self.assertIn('LATEST_VERIFIED_FAMILY', result['old']['reasons'])
        self.assertIn('INCOMPLETE_GROUP', result['newer']['reasons'])

    def test_daily_window_keeps_all_recent_backups_not_only_newest_same_day(self):
        result = decisions(plan(inventory([backup('latest', '2026-10-15T11:00:00Z'), backup('same-day', '2026-10-15T10:00:00Z')])))
        self.assertIn('RECENT_BACKUP_WINDOW', result['same-day']['reasons'])
        self.assertEqual('KEEP', result['same-day']['action'])

    def test_iso_week_boundary_selects_one_representative_in_each_of_four_weeks(self):
        groups = [backup('latest', '2026-10-15T11:00:00Z'), backup('week4', '2026-09-21T00:00:00Z'),
            backup('outside', '2026-09-20T23:59:59.999999999Z'), backup('older-same-week', '2026-09-22T00:00:00Z')]
        result = decisions(plan(inventory(groups)))
        self.assertEqual('DELETE_CANDIDATE', result['outside']['action'])
        self.assertIn('WEEKLY_REPRESENTATIVE', result['older-same-week']['reasons'])
        self.assertEqual('DELETE_CANDIDATE', result['week4']['action'])

    def test_nanosecond_order_and_equal_time_id_tie_are_stable(self):
        groups = [backup('a', '2026-08-01T00:00:00.000000001Z'), backup('b', '2026-08-01T00:00:00.000000002Z')]
        self.assertIn('LATEST_VERIFIED_FAMILY', decisions(plan(inventory(groups)))['b']['reasons'])
        groups[0]['completedAt'] = groups[1]['completedAt']
        self.assertIn('LATEST_VERIFIED_FAMILY', decisions(plan(inventory(groups)))['a']['reasons'])

    def test_failed_unknown_pinned_and_key_unavailable_are_never_candidates(self):
        for field, value, reason in (('state', 'FAILED', 'STATE_FAILED'), ('state', 'UNKNOWN', 'STATE_UNKNOWN'),
            ('pinned', True, 'PINNED'), ('keyAvailable', False, 'KEY_UNAVAILABLE')):
            data = inventory(); data['backupGroups'][1][field] = value
            with self.subTest(field=field, value=value):
                self.assertIn(reason, decisions(plan(data))['expired']['reasons'])

    def test_missing_extra_unverified_and_sensitive_members_protect_whole_group(self):
        for mode, reason in (('missing', 'INCOMPLETE_GROUP'), ('unverified', 'MEMBER_UNVERIFIED'), ('key', 'SENSITIVE_OR_UNKNOWN_MEMBER')):
            data = inventory(); old = data['backupGroups'][1]
            if mode == 'missing': old['members'].pop()
            elif mode == 'unverified': old['members'][0]['verified'] = False
            else:
                member = copy.deepcopy(old['members'][0]); member.update(id='key', role='KEY')
                old['members'].append(member); old['requiredMemberIds'].append('key')
            with self.subTest(mode=mode):
                decision = decisions(plan(data))['expired']; self.assertEqual('KEEP', decision['action']); self.assertIn(reason, decision['reasons'])

    def test_path_traversal_and_unknown_fields_or_versions_reject_entire_input(self):
        variants = []
        value = inventory(); value['backupGroups'][1]['members'][0]['path'] = '/private/backups/platform/../escape'; variants.append(value)
        value = inventory(); value['backupGroups'][0]['surprise'] = 'future'; variants.append(value)
        value = inventory(); value['schemaVersion'] = 2; variants.append(value)
        value = inventory(); value['trialGroups'] = [trial()]; value['trialGroups'][0]['state'] = 'NEW_FUTURE_STATE'; variants.append(value)
        for value in variants:
            with self.subTest(value=value), self.assertRaises(r.ValidationError): plan(value)

    def test_symlink_or_resolved_path_change_keeps_group_without_reading_files(self):
        for field, value in (('isSymlink', True), ('resolvedPath', '/private/backups/platform/elsewhere')):
            data = inventory(); data['backupGroups'][1]['members'][0][field] = value
            with self.subTest(field=field): self.assertIn('UNSAFE_BACKUP_PATH', decisions(plan(data))['expired']['reasons'])

    def test_shared_backup_member_is_not_split_between_groups(self):
        data = inventory(); data['backupGroups'][1]['members'][0] = copy.deepcopy(data['backupGroups'][0]['members'][0])
        self.assertIn('SHARED_BACKUP_MEMBER', decisions(plan(data))['expired']['reasons'])

    def test_nested_member_overlap_and_original_storage_veto_backup_candidates(self):
        data = inventory(); member = data['backupGroups'][1]['members'][0]
        member['path'] = member['resolvedPath'] = data['backupGroups'][0]['members'][0]['path'] + '/nested'
        self.assertIn('SHARED_BACKUP_MEMBER', decisions(plan(data))['expired']['reasons'])
        data = inventory(); data['originalVolumes'][0]['path'] = data['backupGroups'][1]['members'][0]['path']
        self.assertIn('ORIGINAL_STORAGE_OVERLAP', decisions(plan(data))['expired']['reasons'])

    def test_protected_key_config_credentials_and_all_job_objects_stay_protected(self):
        data = inventory()
        data['protectedArtifacts'] = [{'id': kind.lower(), 'kind': kind, 'state': state, 'path': None}
            for kind, state in (('KEY', 'COMPLETED'), ('CONFIG', 'UNKNOWN'), ('CREDENTIAL', 'LIVE'), ('JOB', 'PENDING'), ('RAW', 'PAUSED'), ('EXPORT', 'COMPLETED'))]
        result = plan(data)
        self.assertTrue(all(item['action'] == 'KEEP' for item in result['protectedArtifacts']))
        self.assertEqual(3, sum('NO_JOB_OBJECT_GC_PROTOCOL' in item['reasons'] for item in result['protectedArtifacts']))

    def test_protected_path_overlap_vetoes_archive_candidate(self):
        data = inventory(); path = data['backupGroups'][1]['members'][0]['path']
        data['protectedArtifacts'] = [{'id': 'secret', 'kind': 'CREDENTIAL', 'state': 'UNKNOWN', 'path': path}]
        self.assertIn('PROTECTED_ARTIFACT_OVERLAP', decisions(plan(data))['expired']['reasons'])

    def test_expired_trial_is_one_group_candidate_and_backup_is_kept_as_dependency(self):
        data = inventory(trials=[trial()]); result = plan(data)
        item = result['trialGroups'][0]; self.assertEqual('DELETE_CANDIDATE', item['action'])
        self.assertEqual(uid(10), item['preconditions']['namespace']['uid'])
        self.assertIn('TRIAL_BACKUP_DEPENDENCY', decisions(result)['latest']['reasons'])

    def test_full_seven_days_boundary_is_required(self):
        data = inventory(trials=[trial(completed='2026-10-08T12:00:00.000000001Z')])
        self.assertIn('MINIMUM_AGE_NOT_MET', plan(data)['trialGroups'][0]['reasons'])

    def test_one_mounted_volume_blocks_all_five_trial_volumes(self):
        data = inventory(trials=[trial(count=5)]); data['trialGroups'][0]['volumes'][3]['mounted'] = True
        result = plan(data); self.assertEqual(0, result['summary']['trialCandidates'])
        self.assertIn('MOUNTED_VOLUME', result['trialGroups'][0]['reasons'])

    def test_pending_paused_unknown_live_and_pinned_trials_are_kept(self):
        for field, value in (('state', 'PENDING'), ('state', 'PAUSED'), ('state', 'UNKNOWN'), ('state', 'RUNNING'), ('podsPresent', 1), ('workloadsStopped', False), ('pinned', True)):
            data = inventory(trials=[trial()]); data['trialGroups'][0][field] = value
            with self.subTest(field=field, value=value): self.assertEqual('KEEP', plan(data)['trialGroups'][0]['action'])

    def test_changed_namespace_pvc_pv_or_claimref_identity_blocks_trial(self):
        for field in ('namespace', 'pvcUid', 'pvUid', 'claimRef'):
            data = inventory(trials=[trial()]); item = data['trialGroups'][0]
            if field == 'namespace': item['namespace']['uid'] = uid(999)
            elif field == 'claimRef': item['volumes'][0]['claimRef']['uid'] = uid(999)
            else: item['volumes'][0][field] = uid(999)
            with self.subTest(field=field): self.assertEqual('KEEP', plan(data)['trialGroups'][0]['action'])

    def test_original_namespace_uid_and_nested_original_path_are_protected(self):
        for mode in ('namespace', 'namespace-uid', 'pvc', 'pv', 'path'):
            data = inventory(trials=[trial()]); item = data['trialGroups'][0]; volume = item['volumes'][0]
            if mode == 'namespace': item['namespace']['name'] = 'platform-lab'
            elif mode == 'namespace-uid': item['namespace']['uid'] = item['namespace']['expectedUid'] = uid(1)
            elif mode == 'pvc': volume['pvcUid'] = volume['expectedPvcUid'] = uid(2)
            elif mode == 'pv': volume['pvUid'] = volume['expectedPvUid'] = uid(3)
            else: volume['path'] = volume['resolvedPath'] = '/private/storage/platform/original/nested'
            with self.subTest(mode=mode): self.assertEqual('KEEP', plan(data)['trialGroups'][0]['action'])

    def test_unsupported_old_trial_labels_are_kept_not_rejected(self):
        data = inventory(trials=[trial()]); data['trialGroups'][0]['namespace']['labels'] = {'devdooly.io/purpose': 'restore-drill', 'devdooly.io/backup-id': '20261011000000'}
        self.assertIn('OWNERSHIP_UNVERIFIED', plan(data)['trialGroups'][0]['reasons'])

    def test_missing_backup_evidence_delete_policy_or_unbound_state_blocks_trial(self):
        for field in ('backup', 'evidence', 'delete', 'unbound', 'symlink'):
            data = inventory(trials=[trial()]); item = data['trialGroups'][0]
            if field == 'backup': item['backupGroupId'] = None
            elif field == 'evidence': item['evidenceVerified'] = False
            elif field == 'delete': item['volumes'][0]['reclaimPolicy'] = 'Delete'
            elif field == 'unbound': item['volumes'][0]['bound'] = False
            else: item['volumes'][0]['isSymlink'] = True
            with self.subTest(field=field): self.assertEqual('KEEP', plan(data)['trialGroups'][0]['action'])

    def test_shared_trial_storage_blocks_both_groups(self):
        left = trial('left', index=10); right = trial('right', index=20)
        right['volumes'][0]['resolvedPath'] = right['volumes'][0]['path'] = left['volumes'][0]['path']
        result = plan(inventory(trials=[left, right]))
        self.assertTrue(all('SHARED_TRIAL_STORAGE' in item['reasons'] for item in result['trialGroups']))

    def test_stale_inventory_future_completion_and_clock_before_capture_fail_closed(self):
        data = inventory(trials=[trial()]); data['capturedAt'] = '2026-10-15T11:00:00Z'
        result = plan(data); self.assertFalse(result['inventoryFresh']); self.assertEqual(0, result['summary']['backupCandidates']); self.assertEqual(0, result['summary']['trialCandidates'])
        data = inventory(); data['backupGroups'][1]['completedAt'] = '2026-10-16T00:00:00Z'
        self.assertIn('FUTURE_COMPLETION', decisions(plan(data))['expired']['reasons'])
        with self.assertRaisesRegex(r.ValidationError, 'CLOCK_BEFORE_INVENTORY'): plan(inventory(), now='2026-10-15T11:59:59Z')

    def test_duplicate_json_nonfinite_bad_date_and_bool_integer_are_rejected(self):
        for raw in ('{"schemaVersion":1,"schemaVersion":1}', '{"value":NaN}'):
            with self.subTest(raw=raw), self.assertRaises(r.ValidationError): r.strict_json(raw)
        for change in ('bad-date', 'bool-size'):
            data = inventory()
            if change == 'bad-date': data['backupGroups'][0]['completedAt'] = '2026-02-30T00:00:00Z'
            else: data['backupGroups'][0]['members'][0]['size'] = True
            with self.subTest(change=change), self.assertRaises(r.ValidationError): plan(data)

    def test_malformed_nested_identity_values_return_schema_error(self):
        for field in ('required-member', 'pvc-name'):
            data = inventory(trials=[trial()])
            if field == 'required-member': data['backupGroups'][0]['requiredMemberIds'] = [{'unexpected': 'object'}]
            else: data['trialGroups'][0]['volumes'][0]['pvcName'] = ['unexpected-list']
            with self.subTest(field=field), self.assertRaises(r.ValidationError): plan(data)

    def test_actual_shape_fresh_five_plus_old_one_and_unknown_eighteen_have_no_candidates(self):
        current = trial('runtime', completed='2026-10-15T06:41:00Z', count=5)
        old = trial('db', completed='2026-10-11T08:00:00Z', index=20); old.update(state='UNKNOWN', pinned=True, backupGroupId=None, evidenceVerified=False)
        data = inventory([backup('latest', '2026-10-15T06:14:00Z')], [current, old])
        data['protectedArtifacts'] = [{'id': 'unknown-' + str(i), 'kind': 'UNKNOWN', 'state': 'UNKNOWN', 'path': '/private/backups/platform/unknown-' + str(i)} for i in range(18)]
        result = plan(data); self.assertEqual(0, result['summary']['backupCandidates']); self.assertEqual(0, result['summary']['trialCandidates']); self.assertEqual(18, result['summary']['protectedArtifacts'])

    def test_plan_is_deterministic_and_does_not_mutate_inputs(self):
        data = inventory(trials=[trial()]); snapshot = copy.deepcopy(data); policy = copy.deepcopy(POLICY)
        first = r.build_plan(data, policy, now=NOW); self.assertEqual(first, r.build_plan(data, policy, now=NOW))
        self.assertEqual(snapshot, data); self.assertEqual(POLICY, policy)

    def test_cli_marks_clock_override_and_never_overwrites_plan(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder); os.chmod(root, 0o700); source = root / 'inventory.json'; output = root / 'plan.json'
            source.write_text(json.dumps(inventory()), encoding='utf-8'); os.chmod(source, 0o600)
            args = ['--inventory', str(source), '--policy', str(ROOT / 'infra/maintenance/policy.json'), '--output', str(output), '--now', NOW]
            with contextlib.redirect_stdout(io.StringIO()) as stdout:
                self.assertEqual(0, r.main(args))
            self.assertNotIn('/private/', stdout.getvalue())
            created = output.read_bytes(); self.assertEqual('EXPLICIT_HYPOTHETICAL', json.loads(created)['clockSource'])
            with contextlib.redirect_stdout(io.StringIO()): self.assertEqual(1, r.main(args))
            self.assertEqual(created, output.read_bytes())

    def test_cli_system_clock_retains_fresh_fraction_without_explicit_override(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder); os.chmod(root, 0o700); source = root / 'inventory.json'; output = root / 'plan.json'
            data = inventory(); data['capturedAt'] = '2026-10-15T12:00:00.123456789Z'
            source.write_text(json.dumps(data), encoding='utf-8'); os.chmod(source, 0o600)
            args = ['--inventory', str(source), '--policy', str(ROOT / 'infra/maintenance/policy.json'), '--output', str(output)]
            fresh_now = '2026-10-15T12:00:00.123456790Z'
            with mock.patch.object(r.time, 'time_ns', return_value=r.timestamp(fresh_now)), contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(0, r.main(args))
            result = json.loads(output.read_bytes())
            self.assertEqual(fresh_now, result['plannedAt']); self.assertEqual('SYSTEM_UTC', result['clockSource'])
            self.assertTrue(result['inventoryFresh'])
            source = root / 'immediate.json'; output = root / 'immediate-plan.json'
            data['capturedAt'] = r.system_utc_now(); source.write_text(json.dumps(data), encoding='utf-8'); os.chmod(source, 0o600)
            args = ['--inventory', str(source), '--policy', str(ROOT / 'infra/maintenance/policy.json'), '--output', str(output)]
            with contextlib.redirect_stdout(io.StringIO()): self.assertEqual(0, r.main(args))
            result = json.loads(output.read_bytes()); self.assertGreaterEqual(r.timestamp(result['plannedAt']), r.timestamp(data['capturedAt']))

    def test_apply_flag_and_policy_enabling_deletion_are_not_supported(self):
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit): r.main(['--inventory', 'unused', '--output', 'unused', '--apply'])
        for field in ('applyEnabled', 'jobObjectDeletionEnabled'):
            policy = copy.deepcopy(POLICY); policy[field] = True
            with self.subTest(field=field), self.assertRaisesRegex(r.ValidationError, 'DELETION_EXECUTOR_NOT_IMPLEMENTED'):
                r.build_plan(inventory(), policy, now=NOW)


if __name__ == '__main__': unittest.main()
