"""Synthetic delegate/filesystem guards; frozen source binding reads only, no Cloud."""
import copy
import hashlib
import json
import os
from pathlib import Path
import tempfile
import types
import unittest
from unittest import mock

import named_observer as n

SOURCE = 'a' * 40
root = Path(os.environ.get('PLATFORM_LAB_SOURCE_ROOT', str(Path(__file__).resolve().parents[2])))
FROZEN_SOURCE = root/'infra/cloud-lakehouse-ci/run_trial9.py'


class SyntheticDeadline:
    def __init__(self):
        self.started = 123.25
        self.now = n.time.monotonic


class Synthetic:
    def __init__(self, root):
        self.module = types.ModuleType('synthetic_only_not_actual_runtime_authority')
        self.base = object(); self.root = root; self.project = 'cloud-trial9-' + 'b' * 32
        self.images = {'syntheticOnly': 'not-a-runtime-image'}
        self.clock = SyntheticDeadline()
        self.module.Deadline = SyntheticDeadline
        self.attempt = types.SimpleNamespace(root=root, project=self.project, command_stage='SPARK', deadline=self.clock)
        self.raw = b'synthetic-table-one|synthetic-pointer-one\nsynthetic-table-two|synthetic-pointer-two\n'
        self.make = mock.Mock(return_value=self.attempt)
        self.jdbc = mock.Mock(return_value=self.raw)
        self.main = mock.Mock()
        self.module.make_attempt = self.make; self.module.jdbc = self.jdbc; self.module.main = self.main
        self.originals = {'make_attempt': self.make, 'jdbc': self.jdbc, 'main': self.main}

    def patches(self):
        return mock.patch.object(n, 'verified_functions', return_value=self.originals)

    def bind(self):
        actual = self.module.make_attempt(self.base, root=self.root, project=self.project, images=self.images)
        assert actual is self.attempt

    def complete(self):
        for stage, _stem in n.CHECKPOINTS:
            self.attempt.command_stage = stage
            assert self.module.jdbc(attempt=self.attempt) is self.raw


class ObserverGuards(unittest.TestCase):
    def setUp(self):
        self.environment = mock.patch.dict(os.environ, {'SOURCE_COMMIT': SOURCE, 'GITHUB_SHA': SOURCE})
        self.environment.start(); self.addCleanup(self.environment.stop)

    def test_exact_order_delegate_once_identity_bytes_kwargs_clock_and_finally_restore(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); sample = Synthetic(root); output = root / 'observer'
            with sample.patches(), n.named_observer(sample.module, output, SOURCE) as seen:
                sample.bind(); sample.complete()
                self.assertIs(seen.attempt, sample.attempt)
                self.assertIs(seen.deadline, sample.clock)
                self.assertEqual(sample.clock.started, 123.25)
                self.assertIs(seen.deadline_now, n.time.monotonic)
            sample.make.assert_called_once_with(sample.base, root=sample.root, project=sample.project, images=sample.images)
            self.assertEqual(sample.jdbc.call_args_list, [mock.call(attempt=sample.attempt)] * 3)
            self.assertIs(sample.module.make_attempt, sample.make); self.assertIs(sample.module.jdbc, sample.jdbc)
            sample.main.assert_not_called()
            for index, (stage, stem) in enumerate(n.CHECKPOINTS, 1):
                self.assertEqual((output / (stem + '.raw')).read_bytes(), sample.raw)
                record = json.loads((output / (stem + '.checkpoint.json')).read_bytes())
                self.assertEqual((record['sequence'], record['stage'], record['rawSha256']),
                    (index, stage, hashlib.sha256(sample.raw).hexdigest()))
            result = json.loads((output / 'observer-result.json').read_bytes())
            self.assertTrue(result['allThreeCheckpointsObserved']); self.assertTrue(result['originalFunctionsRestored'])
            self.assertFalse(result['producerRunPassedClaimed']); self.assertFalse(result['writersQuiescentVerified'])
            self.assertFalse(result['tableClosureVerified']); self.assertEqual(result['extraSqlCallsAdded'], 0)

    def test_wrong_order_foreign_attempt_fourth_call_and_clock_reset_reject_before_delegate(self):
        for variant in ('order', 'foreign', 'fourth', 'clock'):
            with self.subTest(variant=variant), tempfile.TemporaryDirectory() as temp:
                root = Path(temp); sample = Synthetic(root)
                with sample.patches():
                    with self.assertRaises(ValueError):
                        with n.named_observer(sample.module, root / 'observer', SOURCE):
                            sample.bind()
                            if variant == 'order': sample.attempt.command_stage = 'TRINO'
                            elif variant == 'fourth': sample.complete()
                            elif variant == 'clock':
                                sample.module.jdbc(sample.attempt); sample.attempt.command_stage = 'TRINO'
                                sample.attempt.deadline = types.SimpleNamespace(started=123.25)
                            sample.module.jdbc(object() if variant == 'foreign' else sample.attempt)
                self.assertEqual(sample.jdbc.call_count, {'order': 0, 'foreign': 0, 'fourth': 3, 'clock': 1}[variant])
                self.assertIs(sample.module.make_attempt, sample.make); self.assertIs(sample.module.jdbc, sample.jdbc)

    def test_original_deadline_type_and_now_callable_cannot_change_before_or_during_delegate(self):
        for variant in ('type', 'first-now', 'later-now', 'during-now'):
            with self.subTest(variant=variant), tempfile.TemporaryDirectory() as temp:
                root = Path(temp); sample = Synthetic(root)
                with sample.patches(), self.assertRaises(ValueError):
                    with n.named_observer(sample.module, root / 'observer', SOURCE):
                        sample.bind()
                        if variant == 'type':
                            sample.attempt.deadline = types.SimpleNamespace(started=123.25, now=n.time.monotonic)
                        elif variant == 'first-now':
                            sample.clock.now = lambda: 123.25
                        elif variant == 'later-now':
                            sample.module.jdbc(sample.attempt)
                            sample.attempt.command_stage = 'TRINO'; sample.clock.now = lambda: 123.25
                        else:
                            def changed_clock(attempt):
                                attempt.deadline.now = lambda: 123.25
                                return sample.raw
                            sample.jdbc.side_effect = changed_clock
                        sample.module.jdbc(sample.attempt)
                self.assertEqual(sample.jdbc.call_count, {'type': 0, 'first-now': 0, 'later-now': 1, 'during-now': 1}[variant])
                self.assertIs(sample.module.make_attempt, sample.make); self.assertIs(sample.module.jdbc, sample.jdbc)

    def test_delegate_and_checkpoint_write_failures_preserve_once_and_restore_without_raw_error(self):
        for variant in ('delegate', 'write'):
            with self.subTest(variant=variant), tempfile.TemporaryDirectory() as temp:
                root = Path(temp); sample = Synthetic(root); output = root / 'observer'
                sentinel = RuntimeError('synthetic-private-error-message')
                if variant == 'delegate': sample.jdbc.side_effect = sentinel
                original_save = n.save
                def failure(path, value):
                    if variant == 'write' and path.suffix == '.raw': raise OSError('synthetic-private-write-error')
                    return original_save(path, value)
                with sample.patches(), mock.patch.object(n, 'save', side_effect=failure):
                    with self.assertRaises(RuntimeError if variant == 'delegate' else OSError) as caught:
                        with n.named_observer(sample.module, output, SOURCE):
                            sample.bind(); sample.module.jdbc(sample.attempt)
                if variant == 'delegate': self.assertIs(caught.exception, sentinel)
                sample.jdbc.assert_called_once_with(sample.attempt)
                self.assertIs(sample.module.make_attempt, sample.make); self.assertIs(sample.module.jdbc, sample.jdbc)
                raw = (output / 'observer-result.json').read_bytes()
                self.assertNotIn(b'synthetic-private', raw)
                result = json.loads(raw); self.assertFalse(result['contextExitedWithoutException'])
                self.assertEqual((result['jdbcCallsStarted'], result['jdbcCallsCompleted']), (1, 0))

    def test_oexcl_existing_named_intent_blocks_sql_and_hook_drift_is_restored(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); sample = Synthetic(root); output = root / 'observer'
            with sample.patches():
                with self.assertRaises(FileExistsError):
                    with n.named_observer(sample.module, output, SOURCE):
                        sample.bind(); blocked = output / (n.CHECKPOINTS[0][1] + '.intent.json')
                        blocked.write_bytes(b'first-synthetic-intent'); sample.module.jdbc(sample.attempt)
                self.assertEqual(blocked.read_bytes(), b'first-synthetic-intent'); sample.jdbc.assert_not_called()
                with self.assertRaises(ValueError):
                    with n.named_observer(sample.module, root / 'drift', SOURCE): sample.module.jdbc = object()
                self.assertIs(sample.module.jdbc, sample.jdbc)
                with self.assertRaises(ValueError):
                    with n.named_observer(sample.module, output, SOURCE): self.fail('existing output accepted')

    def test_actual_pinned_source_code_bindings_are_checked_without_executing_any_body(self):
        # Compile only code objects; do not import frozen modules or call main.
        raw = FROZEN_SOURCE.read_bytes()
        self.assertEqual(n.sha(raw), n.PRODUCER_SHA)
        module = types.ModuleType('static_code_binding_only_not_a_live_module')
        module.__file__ = str(FROZEN_SOURCE); module.HERE = FROZEN_SOURCE.parent
        codes = {code.co_name: code for code in compile(raw, str(FROZEN_SOURCE), 'exec').co_consts if isinstance(code, types.CodeType)}
        for name in ('make_attempt', 'jdbc', 'main'):
            setattr(module, name, types.FunctionType(codes[name], module.__dict__, name))
        original = n.verified_functions(module)
        self.assertIs(original['jdbc'], module.jdbc)
        module.jdbc = lambda attempt: b'forged'
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp) / 'must-not-exist'
            with self.assertRaises(ValueError):
                with n.named_observer(module, output, SOURCE): self.fail('forged callback accepted')
            self.assertFalse(output.exists())


if __name__ == '__main__':
    unittest.main(verbosity=2)
