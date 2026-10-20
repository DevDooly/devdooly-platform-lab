"""New lag-runner boundaries only; no Docker, Maven, Java or network calls."""
from pathlib import Path
import copy
import hashlib
import json
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import run_once as trial


class Rejected(Exception):
    pass


def require(value, *_):
    if not value:
        raise Rejected()


def marker(value=None):
    return 'KAFKA_LAG_RECOVERY_RESULT ' + json.dumps(trial.SUCCESS if value is None else value)


class LagRunnerTest(unittest.TestCase):
    def test_exact_success_and_safe_failure_markers(self):
        self.assertEqual((trial.SUCCESS, None), trial.parse_markers(marker()))
        failure = dict(schemaVersion=1, status='FAILED', phase='BACKLOG_OBSERVE', cause='OBSERVATION')
        self.assertEqual((None, failure), trial.parse_markers('KAFKA_LAG_RECOVERY_FAILURE ' + json.dumps(failure)))
        self.assertEqual((None, None), trial.parse_markers('ordinary library output'))

    def test_changed_counts_boolean_substitution_unknown_fields_and_duplicate_keys_rejected(self):
        for changes in ({'finalLag': 1}, {'initialProcessed': True}, {'targetStable': 1}, {'secret': 'private'}):
            with self.subTest(changes=changes):
                value = dict(trial.SUCCESS); value.update(changes)
                with self.assertRaises(ValueError):
                    trial.parse_markers(marker(value))
        raw = marker().replace('"finalLag": 0', '"finalLag": 0,"finalLag": 0')
        with self.assertRaises(ValueError):
            trial.parse_markers(raw)

    def test_duplicate_conflicting_or_unknown_markers_fail_closed(self):
        failure = 'KAFKA_LAG_RECOVERY_FAILURE ' + json.dumps(dict(schemaVersion=1, status='FAILED', phase='INPUT', cause='ASSERTION'))
        for raw in (marker() + '\n' + marker(), marker() + '\n' + failure,
                    'KAFKA_LAG_RECOVERY_SECRET private', 'KAFKA_LAG_RECOVERY_RESULT not-json'):
            with self.subTest(raw=raw[:30]), self.assertRaises(ValueError):
                trial.parse_markers(raw)
        with self.assertRaises(ValueError) as caught:
            trial.parse_markers(failure.replace('ASSERTION', 'private error text'))
        self.assertNotIn('private error', str(caught.exception))

    def test_only_exact_named_single_test_xml_is_selected(self):
        with tempfile.TemporaryDirectory() as folder:
            staged = Path(folder)
            reports = staged / 'target/surefire-reports'; reports.mkdir(parents=True)
            xml = reports / 'TEST-owned.xml'
            body = ('<testsuite name="' + trial.CLASS + '"><testcase classname="' + trial.CLASS
                + '" name="' + trial.METHOD + '"><system-out><![CDATA[' + marker()
                + ']]></system-out></testcase></testsuite>')
            base = SimpleNamespace(read=lambda path, maximum: path.read_bytes())
            xml.write_text(body, encoding='utf8')
            self.assertEqual((trial.SUCCESS, None), trial.selected_markers(base, staged))
            for invalid in (body.replace(trial.METHOD, 'foreign'), '<!DOCTYPE secret>' + body,
                            body.replace('</testsuite>', '<testcase name="extra"/></testsuite>')):
                xml.write_text(invalid, encoding='utf8')
                with self.assertRaises(ValueError):
                    trial.selected_markers(base, staged)

    def test_state_binding_rejects_foreign_run_source_manifest_nonce(self):
        state = dict(sourceCommit='a' * 40, runId='123', manifestSha256='b' * 64, nonce='c' * 32)
        env = dict(SOURCE_COMMIT='a' * 40, GITHUB_RUN_ID='123')
        base = SimpleNamespace(require=require, load_json=lambda _: copy.deepcopy(state))
        self.assertEqual(state, trial.bound_state(base, Path('/unused'), 'b' * 64, env))
        for key, value in (('sourceCommit', 'f' * 40), ('runId', '124'), ('manifestSha256', 'f' * 64), ('nonce', '../foreign')):
            prior = state[key]; state[key] = value
            with self.assertRaises(Rejected):
                trial.bound_state(base, Path('/unused'), 'b' * 64, env)
            state[key] = prior

    def test_descriptor_pins_bytes_and_rejects_path_escape_and_duplicate_inventory(self):
        paths = ['apps/api/file' + str(index) for index in range(106)]
        paths += [trial.BASE_RUNNER, 'infra/kafka-observation-ci/test_run_once.py', 'infra/image-lock.json']
        paths += sorted(trial.EXTRAS)
        rows = [dict(path=name, bytes=1, sha256='a' * 64) for name in paths]
        value = dict(schemaVersion=1, scope='HOSTED_LINUX_KAFKA_LAG_RECOVERY_SOURCE_ONLY', files=rows)
        raw = json.dumps(value).encode()
        with patch.object(trial, 'read_source', return_value=raw):
            self.assertEqual(115, len(trial.descriptor(Path('/unused'), hashlib.sha256(raw).hexdigest())))
            with self.assertRaises(ValueError):
                trial.descriptor(Path('/unused'), 'b' * 64)
        for name in ('../escape', '/absolute', 'apps/api/../escape', 'C:/escape', 'apps\\api\\escape', paths[0]):
            invalid = copy.deepcopy(value); invalid['files'][1]['path'] = name
            data = json.dumps(invalid).encode()
            with patch.object(trial, 'read_source', return_value=data), self.assertRaises(ValueError):
                trial.descriptor(Path('/unused'), hashlib.sha256(data).hexdigest())

    def test_hosted_requires_explicit_main_attempt_one_and_matching_checkout(self):
        with tempfile.TemporaryDirectory() as folder:
            repo = Path(folder).resolve()
            env = dict(GITHUB_REPOSITORY='DevDooly/devdooly-platform-lab', GITHUB_EVENT_NAME='workflow_dispatch',
                GITHUB_REF='refs/heads/main', KAFKA_LAG_RUNTIME_OPT_IN='true', GITHUB_RUN_ATTEMPT='1',
                GITHUB_WORKSPACE=str(repo), SOURCE_COMMIT='a' * 40)
            base = SimpleNamespace(require=require, hosted_context=lambda _: None,
                command=lambda *args: (0, b'a' * 40 + b'\n', b''))
            trial.hosted(base, repo, env)
            for key, value in (('GITHUB_RUN_ATTEMPT', '2'), ('GITHUB_REF', 'refs/pull/1/merge'),
                               ('KAFKA_LAG_RUNTIME_OPT_IN', 'false'), ('SOURCE_COMMIT', 'b' * 40)):
                bad = dict(env); bad[key] = value
                with self.assertRaises(Rejected):
                    trial.hosted(base, repo, bad)

    def test_helper_bytes_are_verified_before_any_module_execution(self):
        raw = b'VERIFIED_FIXTURE_ONLY = True\n'
        name = 'support.py'
        rows = {name: dict(bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest())}
        with patch.object(trial, 'read_source', return_value=raw):
            module = trial.load_verified(Path('/unused'), rows, name, 'pure_verified_fixture')
            self.assertTrue(module.VERIFIED_FIXTURE_ONLY)
        with patch.object(trial, 'read_source', return_value=b'raise AssertionError("must not execute")\n'):
            with self.assertRaises(ValueError) as caught:
                trial.load_verified(Path('/unused'), rows, name, 'pure_changed_fixture')
            self.assertNotIn('must not execute', str(caught.exception))

    def test_cleanup_never_uses_foreign_state_or_deletes_receipts(self):
        state = dict(sourceCommit='a' * 40, runId='123', manifestSha256='b' * 64, nonce='c' * 32, phase='RUN_INTENT')
        calls = []
        class Owner:
            def __init__(self, task, current, deadline):
                calls.append(('owner', current['nonce']))
            def cleanup(self):
                calls.append(('cleanup',)); return True
        with tempfile.TemporaryDirectory() as folder:
            repo = Path(folder).resolve(); task = repo / trial.PRIVATE; task.mkdir(parents=True)
            (task / 'state.json').write_text('untouched receipt')
            env = dict(SOURCE_COMMIT='a' * 40, GITHUB_RUN_ID='123')
            base = SimpleNamespace(require=require, load_json=lambda _: state, OwnedDocker=Owner,
                save_state=lambda *args: calls.append(('save', state['phase'])))
            with patch.object(trial, 'hosted', return_value=None):
                self.assertEqual(0, trial.cleanup(base, repo, 'b' * 64, env))
                self.assertEqual('untouched receipt', (task / 'state.json').read_text())
                self.assertEqual([('owner', 'c' * 32), ('cleanup',), ('save', 'CLEANED')], calls)
                state['runId'] = 'foreign'; calls.clear()
                with self.assertRaises(Rejected):
                    trial.cleanup(base, repo, 'b' * 64, env)
                self.assertEqual([], calls)


if __name__ == '__main__':
    unittest.main()
