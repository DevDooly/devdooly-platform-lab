"""Pure command-observation contracts; no Docker, SQL, network or workload clock."""
import ast
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace
import unittest
from unittest import mock

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
spec = importlib.util.spec_from_file_location('future_command_runner', HERE/'run_trial9.py')
runner = importlib.util.module_from_spec(spec); spec.loader.exec_module(runner)
SECRET = 'private-password-token-endpoint-do-not-export'


class BaseAttempt:
    def __init__(self, root, project): self.sequence = 0


class CommandDiagnosticContracts(unittest.TestCase):
    def setUp(self):
        self.saved = []
        base = SimpleNamespace(Attempt=BaseAttempt, save=lambda path, value: self.saved.append((path, value)))
        self.attempt = runner.make_attempt(base, Path('private-output'), 'synthetic-project', {})

    def assert_no_secret(self):
        diagnostic = self.attempt.command_diagnostics()
        text = json.dumps(diagnostic)
        self.assertNotIn(SECRET, text)
        for value in diagnostic['failures'] + ([diagnostic['lastCommand']] if diagnostic['lastCommand'] else []):
            self.assertEqual(set(value), {'sequence', 'stage', 'category', 'checkRequested', 'returnCode', 'timedOut', 'outcome'})
        return diagnostic

    def test_checked_nonzero_records_fixed_role_category_without_args_or_stderr(self):
        self.attempt.command_stage = 'START_POSTGRES'
        args = ['docker', 'compose', '-p', SECRET, '-f', SECRET, 'start', 'postgres']
        result = SimpleNamespace(returncode=42, stdout=SECRET.encode(), stderr=SECRET.encode())
        with mock.patch.object(runner.subprocess, 'run', return_value=result) as call:
            with self.assertRaises(ValueError): self.attempt.command(args, sensitive=True)
        call.assert_called_once()
        diagnostic = self.assert_no_secret(); event = diagnostic['failures'][0]
        self.assertEqual((event['sequence'], event['stage'], event['category'], event['returnCode'], event['checkRequested']),
                         (1, 'START_POSTGRES', 'COMPOSE_START_POSTGRES', 42, True))
        self.assertEqual(event['outcome'], 'RETURNED_NONZERO')
        self.assertFalse(event['timedOut'])
        self.assertTrue(all(not isinstance(value, bytes) for _, value in self.saved))
        for role in ('postgres', 'garage', 'spark', 'trino', 'reader'):
            self.assertEqual(runner.command_category(args[:7]+[role]), 'COMPOSE_START_'+role.upper())
        self.assertEqual(runner.command_category(args[:7]+[SECRET]), 'COMPOSE_START_OTHER')

    def test_timeout_cmd_output_and_oserror_message_are_never_public(self):
        args = ['docker', 'inspect', SECRET]
        timeout = subprocess.TimeoutExpired(args, 1, output=SECRET.encode(), stderr=SECRET.encode())
        with mock.patch.object(runner.subprocess, 'run', side_effect=timeout):
            with self.assertRaises(subprocess.TimeoutExpired): self.attempt.command(args, check=False)
        event = self.assert_no_secret()['failures'][0]
        self.assertEqual((event['returnCode'], event['timedOut'], event['outcome'], event['checkRequested']), (None, True, 'TIMED_OUT', False))
        self.attempt.command_stage = SECRET
        with mock.patch.object(runner.subprocess, 'run', side_effect=OSError(SECRET)):
            with self.assertRaises(OSError): self.attempt.command(args)
        event = self.assert_no_secret()['failures'][1]
        self.assertEqual((event['stage'], event['outcome']), ('UNCLASSIFIED_STAGE', 'START_FAILED'))

    def test_primary_failure_survives_cleanup_failure_and_failure_list_is_bounded(self):
        args = ['docker', 'ps', '-aq', SECRET]
        result = SimpleNamespace(returncode=1, stdout=b'', stderr=SECRET.encode())
        self.attempt.command_stage = 'START_GARAGE'
        with mock.patch.object(runner.subprocess, 'run', return_value=result):
            with self.assertRaises(ValueError): self.attempt.command(args, sensitive=True)
            first = self.assert_no_secret()['failures'][0]
            self.attempt.command_stage = 'CLEANUP_CONTAINERS'
            for _ in range(17):
                with self.assertRaises(ValueError): self.attempt.command(args, sensitive=True)
        diagnostic = self.assert_no_secret()
        self.assertEqual(diagnostic['failures'][0], first)
        self.assertEqual(diagnostic['failures'][1]['stage'], 'CLEANUP_CONTAINERS')
        self.assertEqual(len(diagnostic['failures']), 16)
        self.assertTrue(diagnostic['failuresTruncated'])
        self.assertEqual(diagnostic['lastCommand']['sequence'], 18)

    def test_expected_nonzero_is_observed_but_not_relabelled_as_fatal_or_retried(self):
        args = ['docker', 'compose', '-p', SECRET, '-f', SECRET, 'exec', '-T', 'postgres', 'pg_isready']
        result = SimpleNamespace(returncode=1, stdout=b'', stderr=SECRET.encode())
        with mock.patch.object(runner.subprocess, 'run', return_value=result) as call:
            self.assertIs(self.attempt.command(args, check=False), result)
        call.assert_called_once()
        diagnostic = self.assert_no_secret()
        self.assertEqual(diagnostic['failures'], [])
        self.assertEqual((diagnostic['lastCommand']['outcome'], diagnostic['lastCommand']['checkRequested']), ('RETURNED_NONZERO', False))
        # Observation wraps the same original subprocess invocation and limits.
        source = ast.parse((HERE/'run_trial9.py').read_text(encoding='utf-8'), feature_version=(3, 10))
        commands = [node for node in ast.walk(source) if isinstance(node, ast.FunctionDef) and node.name == 'command']
        calls = [node for node in ast.walk(commands[0]) if isinstance(node, ast.Call)
                 and isinstance(node.func, ast.Attribute) and isinstance(node.func.value, ast.Name) and node.func.value.id == 'subprocess']
        self.assertEqual(len(calls), 1)
        self.assertEqual({value.arg for value in calls[0].keywords}, {'stdout', 'stderr', 'timeout'})


if __name__ == '__main__': unittest.main()
