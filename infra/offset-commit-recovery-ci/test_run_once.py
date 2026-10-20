"""Linux pure fixtures only. No Docker, Java, Maven, network or token reads."""
from pathlib import Path
import copy
import hashlib
import json
import os
import tempfile
import time
import unittest
from unittest.mock import patch
import run_once as runner


def success(state='NO_COMMIT', offset=None, replays=1):
    return dict(runner.FIXED_RESULT, postUnpauseCommitState=state,
                postUnpauseCommittedOffset=offset, completedReplays=replays)


def marker(value):
    return runner.MARKER + json.dumps(value)


def failure(phase='TEST_ENTRY', kind='ASSERTION', line=None):
    return dict(schemaVersion=1, status='FAIL', failureCode='VALIDATION_FAILED',
                failurePhase=phase, failureKind=kind, failureSourceLine=line)


class RunnerTest(unittest.TestCase):
    def test_actual_uncertain_commit_outcomes_and_both_observed_replay_counts(self):
        for state, offset in (('NO_COMMIT', None), ('OBSERVED', 1)):
            for replays in (0, 1):
                expected = success(state, offset, replays)
                self.assertEqual(expected, runner.parse_result(marker(expected)))
        failed = failure()
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
                     marker(dict(schemaVersion=1, status='FAIL', failureCode='VALIDATION_FAILED', failurePhase='private')),
                     marker(dict(schemaVersion=1, status='FAIL', failureCode='VALIDATION_FAILED')),
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

    def test_native_signatures_emit_only_fixed_observed_enums(self):
        raw = (b'[ERROR] Cannot access https://private.invalid in offline mode; secret=value\n'
               b'java.lang.OutOfMemoryError: not-public\n'
               b'java.nio.file.AccessDeniedException: /private/file\n')
        self.assertEqual(['FILE_ACCESS_DENIED', 'JVM_MEMORY_FAILURE', 'MAVEN_OFFLINE_ARTIFACT_UNAVAILABLE'],
                         runner.native_signals(raw))
        rendered = json.dumps(runner.native_signals(raw))
        for private in ('private.invalid', 'secret', 'not-public', '/private/file', 'OutOfMemoryError'):
            self.assertNotIn(private, rendered)
        with self.assertRaises(ValueError):
            runner.native_signals(b'x' * 1048577)

    def test_java_frame_requires_known_class_file_hash_and_existing_source_line(self):
        with tempfile.TemporaryDirectory() as directory:
            task = Path(directory)
            key, relative, classname = runner.JAVA_DIAGNOSTIC_SOURCES['OffsetCommitRecoveryIT.java']
            path = task / 'it-api' / Path(relative).relative_to('apps/api')
            path.parent.mkdir(parents=True)
            raw = b'first\nsecond\nthird\n'; path.write_bytes(raw)
            source = {key: hashlib.sha256(raw).hexdigest()}
            text = (' at ' + classname + '.test(OffsetCommitRecoveryIT.java:2)\n'
                    ' at foreign.Class.test(OffsetCommitRecoveryIT.java:2)\n'
                    ' at ' + classname + '.test(OffsetCommitRecoveryIT.java:4)\n'
                    ' at ' + classname + '.test(Private.java:2)\n')
            self.assertEqual([{'sourceFile': 'OffsetCommitRecoveryIT.java', 'sourceLine': 2}],
                             runner.java_frames(task, source, text))
            path.write_bytes(b'changed\n')
            self.assertEqual([], runner.java_frames(task, source, text))

    def test_junit_projection_checks_exact_case_counts_and_never_exports_problem_text(self):
        with tempfile.TemporaryDirectory() as directory:
            task = Path(directory)
            self.assertEqual(('ABSENT', None, ''), runner.junit_failure_projection(task))
            path = task / 'it-api/target/surefire-reports' / ('TEST-' + runner.CLASS + '.xml')
            path.parent.mkdir(parents=True)
            xml = ('<testsuite name="' + runner.CLASS + '" tests="1" failures="0" errors="1" skipped="0">'
                   '<testcase classname="' + runner.CLASS + '" name="' + runner.METHOD + '">'
                   '<error type="private.Type" message="secret">private stack</error></testcase></testsuite>')
            path.write_text(xml)
            status, counts, text = runner.junit_failure_projection(task)
            self.assertEqual('VERIFIED', status)
            self.assertEqual({'tests': 1, 'failures': 0, 'errors': 1, 'skipped': 0}, counts)
            self.assertEqual('private stack', text)
            # The text is in-memory parser input only; the public projection takes counts.
            self.assertNotIn('private', json.dumps({'junitReportStatus': status, 'junitCounts': counts}))
            for bad in (xml.replace('errors="1"', 'errors="2"'), xml.replace(runner.METHOD, 'other'),
                        '<!DOCTYPE testsuite>' + xml, xml.replace('<error ', '<failure ')):
                path.write_text(bad)
                self.assertEqual(('UNVERIFIED', None, ''), runner.junit_failure_projection(task))

    def test_owned_exited_jvm_projects_exit_oom_and_fixed_failure_without_values(self):
        failed = failure('SERVICE_GUARDS')
        class Owned:
            deadline = time.monotonic() + 30
            calls = []
            def inspect(self, row):
                return {'State': dict(Status='exited', Running=False, Paused=False, StartedAt='private-start', ExitCode=1, OOMKilled=False)}
            def call(self, args, deadline):
                self.calls.append(args)
                return 0, (marker(failed) + '\nFailed to load ApplicationContext secret=value').encode(), b''
        owned = Owned()
        with tempfile.TemporaryDirectory() as directory:
            result = runner.exited_jvm_diagnostic(owned, {'role': 'jvm', 'id': 'private-id'}, Path(directory), {})
        self.assertEqual(1, result['exitCode'])
        self.assertIs(result['oomKilled'], False)
        self.assertEqual(['SPRING_CONTEXT_FAILED'], result['observedSignals'])
        self.assertEqual(failed, result['javaFailure'])
        self.assertEqual([['logs', '--tail', '200', 'private-id']], owned.calls)
        for private in ('secret', 'private-id', 'private-start', 'ApplicationContext'):
            self.assertNotIn(private, json.dumps(result))

    def test_unverified_or_running_jvm_never_requests_logs(self):
        class Owned:
            deadline = time.monotonic() + 30
            def inspect(self, row):
                return {'State': dict(Status='running', Running=True, Paused=False, ExitCode=0, OOMKilled=False)}
            def call(self, *args):
                raise AssertionError('must not read logs')
        with tempfile.TemporaryDirectory() as directory:
            self.assertIsNone(runner.exited_jvm_diagnostic(Owned(), {'role': 'jvm'}, Path(directory), {}))
            self.assertIsNone(runner.exited_jvm_diagnostic(Owned(), {'role': 'db'}, Path(directory), {}))

    def test_log_failure_preserves_verified_exit_without_exception_message_or_raw_log(self):
        class Owned:
            deadline = time.monotonic() + 30
            def inspect(self, row):
                return {'State': dict(Status='exited', Running=False, Paused=False, StartedAt='same', ExitCode=137, OOMKilled=True)}
            def call(self, *args):
                raise RuntimeError('secret exception must stay private')
        with tempfile.TemporaryDirectory() as directory:
            result = runner.exited_jvm_diagnostic(Owned(), {'role': 'jvm', 'id': 'private'}, Path(directory), {})
        self.assertEqual(137, result['exitCode'])
        self.assertIs(result['oomKilled'], True)
        self.assertEqual('UNAVAILABLE', result['nativeLogStatus'])
        self.assertEqual([], result['observedSignals'])
        self.assertNotIn('secret', json.dumps(result))

    def test_failure_marker_accepts_only_fixed_kinds_and_typed_original_line(self):
        for kind in runner.JAVA_FAILURE_KINDS:
            for line in (None, 1, 10000):
                expected = failure('KAFKA_CREATE', kind, line)
                self.assertEqual(expected, runner.parse_result(marker(expected)))
        for changes in ({'failureKind': 'private.Exception'}, {'failureSourceLine': True},
                        {'failureSourceLine': '2'}, {'failureSourceLine': 0}, {'failureSourceLine': -1},
                        {'failureSourceLine': 10001}, {'failureSourceLine': 2.0}, {'failurePhase': 'UNKNOWN'},
                        {'message': 'not-public'}):
            value = failure(); value.update(changes)
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                runner.parse_result(marker(value))

    def test_claimed_failure_line_requires_hash_matched_actual_it_source_and_range(self):
        with tempfile.TemporaryDirectory() as directory:
            task = Path(directory)
            key, relative, _ = runner.JAVA_DIAGNOSTIC_SOURCES['OffsetCommitRecoveryIT.java']
            path = task / 'it-api' / Path(relative).relative_to('apps/api')
            path.parent.mkdir(parents=True)
            raw = b'first\nsecond\nthird\n'; path.write_bytes(raw)
            source = {key: hashlib.sha256(raw).hexdigest()}
            value = runner.parse_result(marker(failure('KAFKA_CREATE', 'TIMEOUT', 2)))
            self.assertEqual(value, runner.validated_java_failure(task, source, value))
            with self.assertRaises(ValueError):
                runner.validated_java_failure(task, source, failure('KAFKA_CREATE', 'TIMEOUT', 4))
            with self.assertRaises(ValueError):
                runner.validated_java_failure(task, {}, value)
            path.write_bytes(b'changed\nsource\n')
            with self.assertRaises(ValueError):
                runner.validated_java_failure(task, source, value)
            null_line = failure('KAFKA_CREATE', 'OTHER', None)
            self.assertEqual(null_line, runner.validated_java_failure(task, {}, null_line))

    def test_unverified_original_failure_line_is_not_exported_by_jvm_projection(self):
        failed = failure('KAFKA_CREATE', 'UNKNOWN_TOPIC', 9999)
        class Owned:
            deadline = time.monotonic() + 30
            def inspect(self, row):
                return {'State': dict(Status='exited', Running=False, Paused=False, StartedAt='same', ExitCode=1, OOMKilled=False)}
            def call(self, *args):
                return 0, marker(failed).encode(), b''
        with tempfile.TemporaryDirectory() as directory:
            result = runner.exited_jvm_diagnostic(Owned(), {'role': 'jvm', 'id': 'private'}, Path(directory), {})
        self.assertEqual(1, result['exitCode'])
        self.assertIsNone(result['javaFailure'])
        self.assertNotIn('9999', json.dumps(result))


if __name__ == '__main__':
    unittest.main()
