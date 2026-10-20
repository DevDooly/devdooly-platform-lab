"""Linux pure fixtures only. No Docker, Java, Maven, network or token reads."""
from pathlib import Path
import copy
import hashlib
import json
import os
import tempfile
import unittest
from unittest.mock import patch
import run_once as runner


def success(state='NO_COMMIT', offset=None, replays=1):
    return dict(runner.FIXED_RESULT, postUnpauseCommitState=state,
                postUnpauseCommittedOffset=offset, completedReplays=replays)


def marker(value):
    return runner.MARKER + json.dumps(value)


class RunnerTest(unittest.TestCase):
    def test_actual_uncertain_commit_outcomes_and_both_observed_replay_counts(self):
        for state, offset in (('NO_COMMIT', None), ('OBSERVED', 1)):
            for replays in (0, 1):
                expected = success(state, offset, replays)
                self.assertEqual(expected, runner.parse_result(marker(expected)))
        failed = dict(schemaVersion=1, status='FAIL', failureCode='VALIDATION_FAILED')
        self.assertEqual(failed, runner.parse_result(marker(failed)))
        self.assertIsNone(runner.parse_result('ordinary library output'))

    def test_invalid_marker_counts_types_relations_and_private_fields_rejected(self):
        for changes in ({'completedReplays': 2}, {'completedReplays': True}, {'finalLag': 1},
                        {'fixtureInput': True}, {'pausePersisted': 1}, {'private': 'sensitive'},
                        {'postUnpauseCommittedOffset': 1}, {'postUnpauseCommitState': 'OBSERVED'}):
            value = success(); value.update(changes)
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                runner.parse_result(marker(value))
        for text in (marker(success()) + '\n' + marker(success()),
                     runner.MARKER + '{"schemaVersion":1,"schemaVersion":1}',
                     'OFFSET_COMMIT_RECOVERY_PRIVATE raw error'):
            with self.assertRaises(ValueError) as caught:
                runner.parse_result(text)
            self.assertNotIn('raw error', str(caught.exception))

    def test_phase_canonical_contract_is_exact_and_identities_differ(self):
        state = dict(sourceCommit='a' * 40, runId='123', nonce='b' * 32)
        raw = runner.phase_bytes(state, 'BROKER_PAUSED')
        expected = {'schemaVersion': 1, **state, 'phase': 'BROKER_PAUSED'}
        self.assertEqual((json.dumps(expected, sort_keys=True, separators=(',', ':')) + '\n').encode(), raw)
        self.assertLess(len(raw), 1024)
        other = dict(state, nonce='c' * 32)
        self.assertNotEqual(raw, runner.phase_bytes(other, 'BROKER_PAUSED'))
        with self.assertRaises(ValueError):
            runner.phase_bytes(state, 'UNKNOWN')

    def test_phase_roundtrip_rejects_duplicates_wrong_owner_mode_and_symlink(self):
        state = dict(sourceCommit='a' * 40, runId='123', nonce='b' * 32)
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory) / 'control'; folder.mkdir(mode=0o700)
            self.assertFalse(runner.phase_read(folder, state, 'BROKER_PAUSED'))
            runner.phase_write(folder, state, 'BROKER_PAUSED')
            self.assertTrue(runner.phase_read(folder, state, 'BROKER_PAUSED'))
            with patch.object(runner.os, 'getuid', return_value=os.getuid() + 1), self.assertRaises(ValueError):
                runner.phase_read(folder, state, 'BROKER_PAUSED')
            with self.assertRaises(ValueError):
                runner.phase_write(folder, state, 'BROKER_PAUSED')
            path = folder / runner.PHASES['BROKER_PAUSED']
            path.chmod(0o644)
            with self.assertRaises(ValueError):
                runner.phase_read(folder, state, 'BROKER_PAUSED')
            path.unlink(); target = folder / 'fixture'; target.write_bytes(b'private')
            path.symlink_to(target)
            with self.assertRaises(ValueError):
                runner.phase_read(folder, state, 'BROKER_PAUSED')

    def test_phase_wrong_nonce_and_hardlink_do_not_release_gate(self):
        state = dict(sourceCommit='a' * 40, runId='123', nonce='b' * 32)
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory) / 'control'; folder.mkdir(mode=0o700)
            path = folder / runner.PHASES['POST_DB_COMMIT_READY']
            path.write_bytes(runner.phase_bytes(dict(state, nonce='c' * 32), 'POST_DB_COMMIT_READY'))
            path.chmod(0o600)
            with self.assertRaises(ValueError):
                runner.phase_read(folder, state, 'POST_DB_COMMIT_READY')
            path.write_bytes(runner.phase_bytes(state, 'POST_DB_COMMIT_READY'))
            os.link(path, folder / 'extra-link')
            with self.assertRaises(ValueError):
                runner.phase_read(folder, state, 'POST_DB_COMMIT_READY')

    def test_descriptor_requires_exact_old106_inventory_and_rejects_escape_or_hash_drift(self):
        names = ['apps/api/file' + str(x) for x in range(106)]
        names += [runner.BASE, 'infra/kafka-observation-ci/test_run_once.py', 'infra/image-lock.json']
        names += sorted(runner.EXTRAS)
        self.assertEqual(118, len(names))
        value = dict(schemaVersion=1, scope='HOSTED_LINUX_OFFSET_COMMIT_RECOVERY_SOURCE_ONLY',
                     files=[dict(path=name, bytes=1, sha256='a' * 64) for name in names])
        raw = json.dumps(value).encode()
        with patch.object(runner, 'read', return_value=raw):
            self.assertEqual(118, len(runner.descriptor(Path('/unused'), hashlib.sha256(raw).hexdigest())))
            with self.assertRaises(ValueError):
                runner.descriptor(Path('/unused'), 'b' * 64)
        for bad in ('../outside', '/outside', 'C:/outside', 'apps\\api\\file', names[0]):
            invalid = copy.deepcopy(value); invalid['files'][1]['path'] = bad
            data = json.dumps(invalid).encode()
            with patch.object(runner, 'read', return_value=data), self.assertRaises(ValueError):
                runner.descriptor(Path('/unused'), hashlib.sha256(data).hexdigest())

    def test_helper_hash_is_checked_before_module_definitions_execute(self):
        raw = b'PURE_FIXTURE=True\n'
        rows = {'helper.py': dict(bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest())}
        with patch.object(runner, 'read', return_value=raw):
            self.assertTrue(runner.load_module(Path('/unused'), rows, 'helper.py', 'pure_fixture').PURE_FIXTURE)
        with patch.object(runner, 'read', return_value=b'raise AssertionError("must not execute")'):
            with self.assertRaises(ValueError):
                runner.load_module(Path('/unused'), rows, 'helper.py', 'changed_fixture')

    def test_foreign_state_cannot_bind_to_another_source_run_or_manifest(self):
        state = dict(sourceCommit='a' * 40, runId='123', nonce='b' * 32, manifestSha256='c' * 64)
        class Base:
            def load_json(self, _): return state
        env = dict(SOURCE_COMMIT='a' * 40, GITHUB_RUN_ID='123')
        self.assertEqual(state, runner.bound_state(Base(), Path('/unused'), 'c' * 64, env))
        for key, value in (('runId', 'other'), ('sourceCommit', 'd' * 40), ('nonce', '../outside')):
            prior = state[key]; state[key] = value
            with self.assertRaises(ValueError):
                runner.bound_state(Base(), Path('/unused'), 'c' * 64, env)
            state[key] = prior

    def test_failure_diagnostic_contains_only_enum_and_actual_allowed_source_line(self):
        private = 'not-for-public-diagnostic'
        try:
            runner.parse_result(marker(dict(success(), finalLag=1)))
        except ValueError as error:
            error.args = (private,)
            value = runner.failure_diagnostic(error, 'GARAGE_ACL', {runner.__file__: 'runner'})
            trace = error.__traceback__
            selected_line = None
            while trace is not None:
                if trace.tb_frame.f_code.co_filename == runner.__file__ and trace.tb_frame.f_code.co_name != 'need':
                    selected_line = trace.tb_lineno
                trace = trace.tb_next
            self.assertEqual({'stage': 'GARAGE_ACL', 'sourceFile': 'runner', 'sourceLine': selected_line}, value)
            encoded = json.dumps(value)
            self.assertNotIn(private, encoded)
            self.assertNotIn('ValueError', encoded)
            self.assertNotIn(runner.__file__, encoded)
            self.assertIsNone(runner.failure_diagnostic(error, private, {runner.__file__: 'runner'}))
            self.assertIsNone(runner.failure_diagnostic(error, 'GARAGE_ACL', {}))
            self.assertIsNone(runner.failure_diagnostic(error, 'GARAGE_ACL', {runner.__file__: private}))


if __name__ == '__main__':
    unittest.main()
