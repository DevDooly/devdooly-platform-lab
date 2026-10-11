import copy
import importlib.util
import io
import json
from pathlib import Path
import unittest
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit
import zipfile

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('pages_observation', ROOT / 'infra/scripts/prepare-pages-observation.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

def record(attempt, success=None, label='old'):
    when = '2026-01-01T00:00:' + f'{attempt:02}' + 'Z'
    last = {'capturedAt': '2026-01-01T00:00:' + f'{success:02}' + 'Z', 'label': label} if success is not None else None
    return {'latestAttempt': {'attemptedAt': when, 'status': 'success' if success == attempt else 'failure',
                              'errorCode': 'NONE' if success == attempt else 'TIMEOUT'}, 'lastSuccess': last}

def archive(data, name='platform-observation.json'):
    output = io.BytesIO()
    with zipfile.ZipFile(output, 'w') as zipped:
        zipped.writestr(name, json.dumps(data))
    return output.getvalue()

def run(number, updated, attempt=1, conclusion='success'):
    return {'id': number, 'name': 'Portfolio snapshot v1 · workflow_dispatch', 'path': '.github/workflows/pages.yml',
            'head_branch': 'main', 'event': 'workflow_dispatch', 'status': 'completed', 'conclusion': conclusion,
            'repository': {'full_name': module.REPOSITORY}, 'head_repository': {'full_name': module.REPOSITORY},
            'display_title': 'Portfolio snapshot v1 · workflow_dispatch', 'updated_at': updated,
            'run_attempt': attempt, 'head_sha': 'a' * 40}

class MergeTests(unittest.TestCase):
    def test_nanosecond_newer_attempt_is_not_a_conflict(self):
        baseline, incoming = record(1), record(1)
        baseline['latestAttempt']['attemptedAt'] = '2026-01-01T00:00:01.000000001Z'
        incoming['latestAttempt']['attemptedAt'] = '2026-01-01T00:00:01.000000002Z'
        self.assertEqual(module.merge_records(baseline, incoming), incoming)

    def test_nanosecond_success_order_is_independent_from_latest_attempt(self):
        baseline, incoming = record(9, 3, 'old'), record(7, 3, 'new')
        baseline['lastSuccess']['capturedAt'] = '2026-01-01T00:00:03.000000001Z'
        incoming['lastSuccess']['capturedAt'] = '2026-01-01T00:00:03.000000002Z'
        result = module.merge_records(baseline, incoming)
        self.assertEqual(result['latestAttempt'], baseline['latestAttempt'])
        self.assertEqual(result['lastSuccess'], incoming['lastSuccess'])

    def test_latest_failure_keeps_previous_success(self):
        baseline = record(5, 5)
        incoming = record(9)
        result = module.merge_records(baseline, incoming)
        self.assertEqual(result['latestAttempt'], incoming['latestAttempt'])
        self.assertEqual(result['lastSuccess'], baseline['lastSuccess'])

    def test_delayed_success_improves_last_success_without_erasing_newer_failure(self):
        baseline = record(9, 3)
        incoming = record(7, 7, 'new')
        result = module.merge_records(baseline, incoming)
        self.assertEqual(result['latestAttempt'], baseline['latestAttempt'])
        self.assertEqual(result['lastSuccess'], incoming['lastSuccess'])

    def test_old_attempt_cannot_regress_current_success(self):
        baseline = record(9, 9, 'new')
        self.assertEqual(module.merge_records(baseline, record(2, 2)), baseline)

    def test_equal_attempt_conflicting_status_is_rejected(self):
        with self.assertRaises(module.ObservationError):
            module.merge_records(record(9), record(9, 9))

    def test_same_success_time_conflicting_data_is_rejected(self):
        with self.assertRaises(module.ObservationError):
            module.merge_records(record(9, 3, 'one'), record(7, 3, 'two'))

    def test_inputs_not_mutated(self):
        baseline, incoming = record(3, 3), record(5)
        expected = copy.deepcopy((baseline, incoming))
        result = module.merge_records(baseline, incoming)
        result['lastSuccess']['label'] = 'changed'
        self.assertEqual((baseline, incoming), expected)

class ArtifactTests(unittest.TestCase):
    def setup_source(self, runs, artifact=None, content=None, historical=None, total_count=None, deploy_states=None):
        self.paths = []
        def get(path):
            self.paths.append(path)
            if path.startswith('actions/workflows/'):
                page = int(parse_qs(urlsplit(path).query)['page'][0])
                return {'total_count': len(runs) if total_count is None else total_count,
                        'workflow_runs': runs[(page - 1) * 100:page * 100]}
            if '/jobs?' in path:
                pieces = path.split('/')
                number, attempt = int(pieces[2]), int(pieces[4])
                state = (deploy_states or {}).get((number, attempt), 'success')
                return {'total_count': 1, 'jobs': [{'name': 'deploy', 'run_id': number, 'run_attempt': attempt,
                                                   'head_sha': 'a' * 40, 'status': 'completed', 'conclusion': state}]}
            if '/attempts/' in path:
                return historical
            return {'artifacts': artifact or []}
        return get, lambda _: content

    def artifact(self, number, attempt=1):
        return {'id': 44, 'name': f'platform-observation-{number}-a{attempt}', 'expired': False,
                'workflow_run': {'id': number}}

    def test_live_api_run_name_retains_newer_snapshot_on_delayed_input(self):
        metadata = run(1, '2026-01-01T00:00:09Z')
        self.assertEqual(metadata['name'], metadata['display_title'])
        value = record(9, 7, 'new')
        get, download = self.setup_source([metadata], [self.artifact(1)], archive(value))
        previous = module.previous_snapshot(get, download, 2, 1, lambda _: None)
        self.assertEqual(module.merge_records(previous, record(2, 2)), value)

    def test_mismatched_event_title_is_not_a_baseline(self):
        other = run(1, '2026-01-01T00:00:09Z')
        other['event'] = 'push'
        get, download = self.setup_source([other])
        self.assertIsNone(module.previous_snapshot(get, download, 2, 1, lambda _: None))

    def test_failed_rerun_recovers_previous_successful_attempt(self):
        failed = run(1, '2026-01-01T00:00:09Z', 2, 'failure')
        previous = run(1, '2026-01-01T00:00:04Z')
        value = record(3, 3)
        get, download = self.setup_source([failed], [self.artifact(1)], archive(value), previous)
        self.assertEqual(module.previous_snapshot(get, download, 2, 1, lambda _: None), value)
        self.assertIn('actions/runs/1/attempts/1', self.paths)
        self.assertIn('actions/runs/1/attempts/1/jobs?per_page=100', self.paths)

    def test_current_rerun_can_retain_its_previous_deployed_attempt(self):
        current = run(1, '2026-01-01T00:00:09Z', 2, None)
        current['status'] = 'in_progress'
        value = record(3, 3)
        get, download = self.setup_source([current], [self.artifact(1)], archive(value), run(1, '2026-01-01T00:00:04Z'))
        self.assertEqual(module.previous_snapshot(get, download, 1, 2, lambda _: None), value)

    def test_missing_expected_artifact_fails_closed(self):
        get, download = self.setup_source([run(1, '2026-01-01T00:00:09Z')])
        with self.assertRaises(module.ObservationError):
            module.previous_snapshot(get, download, 2, 1, lambda _: None)

    def test_expired_expected_artifact_fails_closed(self):
        item = self.artifact(1); item['expired'] = True
        get, download = self.setup_source([run(1, '2026-01-01T00:00:09Z')], [item])
        with self.assertRaises(module.ObservationError):
            module.previous_snapshot(get, download, 2, 1, lambda _: None)

    def test_zip_paths_never_extracted(self):
        get, download = self.setup_source([run(1, '2026-01-01T00:00:09Z')], [self.artifact(1)], archive({}, '../outside.json'))
        with self.assertRaises(module.ObservationError):
            module.previous_snapshot(get, download, 2, 1, lambda _: None)

    def test_untrusted_workflow_is_not_a_baseline(self):
        other = run(1, '2026-01-01T00:00:09Z'); other['head_branch'] = 'fork'
        get, download = self.setup_source([other])
        self.assertIsNone(module.previous_snapshot(get, download, 2, 1, lambda _: None))

    def test_success_on_second_page_is_preserved(self):
        history = [run(number, '2026-01-01T00:00:09Z', conclusion='failure') for number in range(101, 1, -1)]
        history.append(run(1, '2026-01-01T00:00:04Z'))
        value = record(3, 3)
        get, download = self.setup_source(history, [self.artifact(1)], archive(value))
        self.assertEqual(module.previous_snapshot(get, download, 200, 1, lambda _: None), value)
        self.assertIn('actions/workflows/pages.yml/runs?per_page=100&page=2', self.paths)
        self.assertFalse(any('branch=' in path for path in self.paths))

    def test_only_newest_deployed_candidate_needs_job_lookup(self):
        history = [run(3, '2026-01-01T00:00:09Z'), run(2, '2026-01-01T00:00:08Z'),
                   run(1, '2026-01-01T00:00:04Z')]
        value = record(7, 7)
        get, download = self.setup_source(history, [self.artifact(3)], archive(value))
        self.assertEqual(module.previous_snapshot(get, download, 200, 1, lambda _: None), value)
        self.assertEqual([path for path in self.paths if '/jobs?' in path],
                         ['actions/runs/3/attempts/1/jobs?per_page=100'])

    def test_history_limit_fails_closed_even_without_a_candidate(self):
        self.assertEqual(module.MAX_WORKFLOW_RUNS, 10000)
        for count in (module.MAX_WORKFLOW_RUNS, module.MAX_WORKFLOW_RUNS + 1):
            with self.subTest(count=count):
                get, download = self.setup_source([], total_count=count)
                with self.assertRaisesRegex(module.ObservationError, 'HISTORY_LIMIT'):
                    module.previous_snapshot(get, download, 2, 1, lambda _: None)

    def test_truncated_history_does_not_become_an_empty_baseline(self):
        history = [run(number, '2026-01-01T00:00:09Z', conclusion='failure') for number in range(100, 0, -1)]
        get, download = self.setup_source(history, total_count=101)
        with self.assertRaisesRegex(module.ObservationError, 'INCOMPLETE_WORKFLOW_HISTORY'):
            module.previous_snapshot(get, download, 200, 1, lambda _: None)

    def test_history_changed_during_pagination_fails_closed(self):
        history = [run(number, '2026-01-01T00:00:09Z', conclusion='failure') for number in range(101, 0, -1)]
        source, download = self.setup_source(history)
        def get(path):
            result = source(path)
            if path.endswith('&page=2'):
                result['total_count'] += 1
            return result
        with self.assertRaisesRegex(module.ObservationError, 'HISTORY_CHANGED'):
            module.previous_snapshot(get, download, 200, 1, lambda _: None)

    def test_duplicate_run_across_pages_fails_closed(self):
        history = [run(number, '2026-01-01T00:00:09Z', conclusion='failure') for number in range(100, 0, -1)]
        history.append(copy.deepcopy(history[0]))
        get, download = self.setup_source(history)
        with self.assertRaisesRegex(module.ObservationError, 'HISTORY_CHANGED'):
            module.previous_snapshot(get, download, 200, 1, lambda _: None)

    def test_failed_or_skipped_deploy_is_not_a_published_baseline(self):
        for state in ('failure', 'skipped'):
            with self.subTest(state=state):
                history = [run(2, '2026-01-01T00:00:09Z'), run(1, '2026-01-01T00:00:04Z')]
                value = record(3, 3)
                get, download = self.setup_source(history, [self.artifact(1)], archive(value), deploy_states={(2, 1): state})
                self.assertEqual(module.previous_snapshot(get, download, 200, 1, lambda _: None), value)

    def test_skipped_rerun_can_recover_its_previous_deployed_attempt(self):
        current = run(1, '2026-01-01T00:00:09Z', 2)
        value = record(3, 3)
        get, download = self.setup_source([current], [self.artifact(1)], archive(value),
                                          run(1, '2026-01-01T00:00:04Z'), deploy_states={(1, 2): 'skipped'})
        self.assertEqual(module.previous_snapshot(get, download, 200, 1, lambda _: None), value)

    def test_deploy_job_lookup_failure_is_not_an_empty_baseline(self):
        source, download = self.setup_source([run(1, '2026-01-01T00:00:09Z')])
        def get(path):
            if '/jobs?' in path:
                raise RuntimeError('fixture job lookup unavailable')
            return source(path)
        with self.assertRaisesRegex(RuntimeError, 'job lookup unavailable'):
            module.previous_snapshot(get, download, 2, 1, lambda _: None)

    def test_wrong_deploy_attempt_identity_is_rejected(self):
        source, download = self.setup_source([run(1, '2026-01-01T00:00:09Z')])
        def get(path):
            result = source(path)
            if '/jobs?' in path:
                result['jobs'][0]['run_attempt'] = 2
            return result
        with self.assertRaisesRegex(module.ObservationError, 'DEPLOY_JOB_IDENTITY_REJECTED'):
            module.previous_snapshot(get, download, 2, 1, lambda _: None)

    def test_incomplete_deploy_job_metadata_fails_closed(self):
        source, download = self.setup_source([run(1, '2026-01-01T00:00:09Z')])
        def get(path):
            result = source(path)
            if '/jobs?' in path:
                result['total_count'] = 101
            return result
        with self.assertRaisesRegex(module.ObservationError, 'INCOMPLETE_DEPLOY_JOB_METADATA'):
            module.previous_snapshot(get, download, 2, 1, lambda _: None)

    def test_ambiguous_deploy_job_name_fails_closed(self):
        source, download = self.setup_source([run(1, '2026-01-01T00:00:09Z')])
        def get(path):
            result = source(path)
            if '/jobs?' in path:
                result['jobs'].append(copy.deepcopy(result['jobs'][0]))
                result['total_count'] = 2
            return result
        with self.assertRaisesRegex(module.ObservationError, 'AMBIGUOUS_DEPLOY_JOB_METADATA'):
            module.previous_snapshot(get, download, 2, 1, lambda _: None)

class InputTests(unittest.TestCase):
    def test_timestamp_calendar_and_precision_are_strict(self):
        invalid = ('2025-02-29T00:00:00Z', '2026-13-01T00:00:00Z', '2026-01-01T00:00:60Z',
                   '0000-01-01T00:00:00Z', '2026-01-01T00:00:00.0000000001Z', '2026-01-01T00:00:00+00:00')
        for value in invalid:
            with self.subTest(value=value), self.assertRaisesRegex(module.ObservationError, 'INVALID_OBSERVATION_TIMESTAMP'):
                module.instant(value)
        self.assertEqual(module.instant('2024-02-29T00:00:00.1Z'), module.instant('2024-02-29T00:00:00.100000000Z'))
        self.assertEqual(module.instant('1970-01-01T00:00:00.000000001Z'), 1)
        self.assertEqual(module.instant('1969-12-31T23:59:59.999999999Z'), -1)

    def test_future_guard_uses_nanoseconds(self):
        validate = module.validator(ROOT)
        value = record(1)
        value['latestAttempt']['attemptedAt'] = '2026-01-01T00:00:01.000000002Z'
        now = module.instant('2026-01-01T00:00:01.000000001Z')
        with patch.object(module.subprocess, 'run', return_value=module.subprocess.CompletedProcess([], 0)), \
                patch.object(module.time, 'time_ns', return_value=now):
            with self.assertRaisesRegex(module.ObservationError, 'FUTURE_OBSERVATION_REJECTED'):
                validate(value)
            value['latestAttempt']['attemptedAt'] = '2026-01-01T00:00:01.000000001Z'
            validate(value)

    def test_duplicate_json_keys_rejected(self):
        with self.assertRaises(module.ObservationError):
            module.parse_record(b'{"value":"hidden","value":"public"}', lambda _: None)

    def test_utf8_byte_limit_not_character_count(self):
        with self.assertRaises(module.ObservationError):
            module.parse_record(json.dumps({'value': '\uac00' * 9000}, ensure_ascii=False).encode(), lambda _: None)

    def test_validator_rejection_is_propagated(self):
        def reject(_):
            raise module.ObservationError('SNAPSHOT_CONTRACT_REJECTED')
        with self.assertRaisesRegex(module.ObservationError, 'CONTRACT_REJECTED'):
            module.parse_record(b'{}', reject)

if __name__ == '__main__':
    unittest.main()
