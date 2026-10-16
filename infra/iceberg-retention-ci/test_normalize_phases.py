"""Synthetic phase/privacy contracts; no actual proof, Docker, Java, or Cloud."""
import ast
from contextlib import ExitStack, contextmanager
import copy
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
import types
import unittest
from unittest import mock

import composite_entry as entry
import decoder_lifecycle as decoder
import lifecycle as life
import normalize_graph as normalizer
import test_run_capture as cli_fixture

cli = cli_fixture.c
CANARY = 'SYNTHETIC_PRIVATE_ERROR_ENV_URI_EXIT_REPLY_DO_NOT_PUBLISH'
SOURCE, AUTH = 'a' * 40, 'b' * 64
STAMP = '2026-10-16T00:00:05Z'
PLANNER = b'# synthetic planner source, never an actual authority proof\n'
ALIAS = 'f-' + 'c' * 64


def synthetic_normalization():
    return types.SimpleNamespace(
        verified={'validation': {'snapshotIds': ['1'], 'capturedAt': STAMP}},
        descriptor={'objects': [{'alias': ALIAS, 'sha256': 'd' * 64}]},
        loaded={'descriptorBytes': b'{}', 'frameBytes': b'synthetic-frame'},
        authority={'validation': {'sha256': 'e' * 64}, 'lifecycle': {'sha256': 'f' * 64}},
        decoder_bundle={'sha256': '1' * 64, 'writersAfter': {'sha256': '2' * 64}},
        decoder_record={'exitCode': 0},
        reply={'descriptorSha256': normalizer.digest(b'{}'), 'status': 'DECODED',
            'graph': {'currentMetadataId': ALIAS}, 'reasonCodes': []},
        projection={'tableId': 't-' + '3' * 64, 'currentSnapshotId': '1',
            'snapshots': [{'id': '1', 'parentId': None, 'committedAt': STAMP, 'fileIds': []}],
            'refs': [], 'files': []},
        builder=mock.Mock(return_value={'status': 'DETERMINED'}))


@contextmanager
def normalization_bindings(value):
    """Only synthetic dependency returns; execute the real normalizer body."""
    with ExitStack() as stack:
        hooks = {}
        for name, returned in (
                ('validate_authority_bundle', value.verified),
                ('checked_descriptor', value.descriptor),
                ('checked_decoder', value.decoder_record),
                ('strict_json', value.reply), ('graph_projection', value.projection),
                ('utc_ns', 1)):
            hooks[name] = stack.enter_context(mock.patch.object(normalizer, name, return_value=returned))
        stack.enter_context(mock.patch.object(normalizer, 'PLANNER_SHA', normalizer.digest(PLANNER)))
        def load_synthetic_planner(unused, namespace):
            namespace['build_plan'] = value.builder
        stack.enter_context(mock.patch.object(normalizer, 'exec', load_synthetic_planner, create=True))
        yield hooks


def normalize(value, source=PLANNER):
    return normalizer.normalize_graph(b'synthetic-reply', value.loaded, value.authority,
        value.decoder_bundle, source, now=STAMP, policy={}, expected_authority_source_sha256=AUTH)


def original_normalizer_function():
    """Remove only diagnostic statements to compare original operation AST."""
    tree = ast.parse(Path(normalizer.__file__).read_text(encoding='utf-8'))
    function = next(node for node in tree.body if isinstance(node, ast.FunctionDef)
        and node.name == 'normalize_graph')
    if len(function.body) != 2 or not isinstance(function.body[1], ast.Try):
        raise AssertionError('EXPECTED_SINGLE_DIAGNOSTIC_WRAPPER')
    function.body = function.body[1].body
    class StripPhase(ast.NodeTransformer):
        def visit_Assign(self, node):
            if (len(node.targets) == 1 and isinstance(node.targets[0], ast.Name)
                    and node.targets[0].id == 'phase'):
                return None
            return self.generic_visit(node)
    return StripPhase().visit(function)


def run_composite_synthetic(test, folder, error, *, late=False, broken_diagnostic=False):
    """Actual entry.run with source-bound synthetic modules; no process launch."""
    here = folder / 'repo/infra/cloud-lakehouse-ci'; here.mkdir(parents=True)
    (here.parents[1] / 'infra/maintenance').mkdir()
    planner = here.parents[1] / 'infra/maintenance/iceberg_retention_plan.py'
    planner.write_bytes(PLANNER)
    producer = types.SimpleNamespace(HERE=here, main=mock.Mock(return_value=0),
        canonical_host=object(), canonical_mounts=object())
    seen = types.SimpleNamespace(attempt=types.SimpleNamespace(root=folder, project='synthetic-project'),
        deadline_started=100.0)
    @contextmanager
    def observe(*unused): yield seen
    observer = types.SimpleNamespace(__file__=life.__file__, named_observer=observe)
    loaded = {'frameBytes': b'synthetic-frame', 'descriptorBytes': b'{}'}
    loader = types.SimpleNamespace(__file__=life.__file__, derive_request=mock.Mock(return_value={}),
        load_closed_copies=mock.Mock(return_value=loaded))
    class BrokenDiagnostics(types.SimpleNamespace):
        def __getattribute__(self, name):
            if name == 'NormalizationFailure': raise KeyboardInterrupt(CANARY)
            return super().__getattribute__(name)
    namespace = BrokenDiagnostics if broken_diagnostic else types.SimpleNamespace
    normalized = {'inventory': None, 'plan': None, 'privateReceipt': {}}
    module = namespace(__file__=normalizer.__file__, NormalizationFailure=normalizer.NormalizationFailure,
        NORMALIZATION_PHASE_CODES=normalizer.NORMALIZATION_PHASE_CODES,
        normalize_graph=mock.Mock(return_value=normalized))
    if not late: module.normalize_graph.side_effect = error
    own_decoder = types.SimpleNamespace(cid='9' * 64, absolute=700.0, cutoff=660.0,
        stopped=True, cli_reaped=True,
        run=mock.Mock(return_value={'cid': '9' * 64, 'exitCode': 0,
            'reply': {'raw': b'{}', 'sha256': life.sha(b'{}')}}))
    proof = {'raw': b'{}', 'sha256': life.sha(b'{}')}
    authority = {'validation': dict(proof), 'clock': dict(proof)}
    stopped = {'roles': [], 'initializer': {}}
    actual_read = life.read_proof
    pins = {Path(m.__file__).name: actual_read(Path(m.__file__).absolute())['sha256']
        for m in (life, decoder, observer, loader, module)}
    def read(path, *args):
        value = actual_read(path, *args)
        if Path(path) == planner: value['sha256'] = normalizer.PLANNER_SHA
        return value
    environment = {'GITHUB_ACTIONS': 'true', 'RUNNER_ENVIRONMENT': 'github-hosted',
        'SOURCE_COMMIT': SOURCE, 'GITHUB_SHA': SOURCE}
    remaining = [None, None, error] if late else [None, None]
    with mock.patch.object(entry.sys, 'platform', 'linux'), mock.patch.dict(os.environ, environment), \
            mock.patch.object(entry.sys, 'argv', ['entry', '--source-manifest-sha256', life.RUNTIME,
                '--ack-fresh-cloud-trial9']), \
            mock.patch.object(life, 'read_proof', side_effect=read), \
            mock.patch.object(life, 'validate_producer', return_value=authority), \
            mock.patch.object(life, 'stopped_snapshot', side_effect=lambda *a, **k: copy.deepcopy(stopped)), \
            mock.patch.object(life, 'remaining', side_effect=remaining), \
            mock.patch.object(decoder, 'prep', return_value={'imageId': 'sha256:' + '8' * 64}), \
            mock.patch.object(decoder, 'Decoder', return_value=own_decoder) as create_decoder:
        result = entry.run(producer, observer, loader, module, source_commit=SOURCE, output=folder / 'new',
            authority_source_sha256=actual_read(Path(entry.__file__).absolute())['sha256'],
            component_source_pins=pins, prep_proof={}, prep_sha256='4' * 64,
            decoder_source_sha256='5' * 64, classes=folder, iceberg=folder, policy={})
    producer.main.assert_called_once_with(); create_decoder.assert_called_once()
    own_decoder.run.assert_called_once_with(loaded['frameBytes'])
    module.normalize_graph.assert_called_once()
    test.assertEqual(result['exitCode'], 1)
    test.assertEqual(result['receipt']['lastStage'], 'NORMALIZE')
    test.assertFalse(result['receipt']['pipelineFinishedWithoutException'])
    test.assertEqual(result['receipt']['originalRoleStopCallsAdded'], 0)
    test.assertEqual(result['receipt']['originalInitializerStopCallsAdded'], 0)
    saved = json.loads((folder / 'new/composite-result.private.json').read_bytes())
    test.assertEqual(saved, result['receipt'])
    return result


class NormalizationPhases(unittest.TestCase):
    def test_each_real_normalizer_region_is_fixed_and_original_operations_are_preserved(self):
        function = original_normalizer_function()
        fingerprint = hashlib.sha256(ast.dump(function, include_attributes=False).encode()).hexdigest()
        self.assertEqual(fingerprint, '31495f334b816fb40ef1f95081b2af11cc33f7b91e2c38e626e36e554e73cfbc')
        self.assertEqual(normalizer.NORMALIZATION_PHASE_CODES, cli.NORMALIZATION_PHASE_CODES)
        failures = (
            ('AUTHORITY', 'validate_authority_bundle', RuntimeError(CANARY)),
            ('DESCRIPTOR', 'checked_descriptor', OSError(CANARY)),
            ('DECODER_LIFECYCLE', 'checked_decoder', RuntimeError(CANARY)),
            ('PLANNER_SOURCE', None, None),
            ('REPLY', 'strict_json', subprocess.TimeoutExpired([CANARY], 1, output=CANARY, stderr=CANARY)),
            ('GRAPH', 'graph_projection', RuntimeError(CANARY)),
            ('EXIT_BINDING', None, None),
            ('CLOCK', 'utc_ns', KeyboardInterrupt(CANARY)),
            ('INVENTORY', None, None), ('PLAN', None, None), ('RESULT', None, None))
        for phase, hook, error in failures:
            with self.subTest(phase=phase):
                value = synthetic_normalization(); source = PLANNER
                if phase == 'PLANNER_SOURCE': source += b'tampered'
                elif phase == 'EXIT_BINDING': value.decoder_record['exitCode'] = 3
                elif phase == 'INVENTORY': value.verified['validation']['snapshotIds'] = ['2']
                elif phase == 'PLAN': value.builder.side_effect = SystemExit(CANARY)
                elif phase == 'RESULT': del value.decoder_bundle['writersAfter']
                with normalization_bindings(value) as hooks:
                    if hook is not None: hooks[hook].side_effect = error
                    with self.assertRaises(normalizer.NormalizationFailure) as caught: normalize(value, source)
                expected = 'NORMALIZE_' + phase + '_UNVERIFIED'
                self.assertIs(type(caught.exception), normalizer.NormalizationFailure)
                self.assertEqual(caught.exception.args, (expected,))
                self.assertEqual(caught.exception.phaseCode, expected)
                self.assertTrue(caught.exception.__suppress_context__)
                self.assertIsNone(caught.exception.__cause__)
                self.assertNotIn(CANARY, str(caught.exception))
        # Same original function body and return value for synthetic normal/partial paths.
        for partial in (False, True):
            with self.subTest(partial=partial):
                value = synthetic_normalization()
                if partial:
                    value.projection = None; value.reply['status'] = 'UNDETERMINED'
                    value.reply['reasonCodes'] = ['MISSING_APPROVED_CHILD']; value.decoder_record['exitCode'] = 2
                with normalization_bindings(value):
                    namespace = dict(normalizer.__dict__)
                    exec(compile(ast.fix_missing_locations(ast.Module(body=[copy.deepcopy(function)], type_ignores=[])),
                        '<original-operation-body-only>', 'exec'), namespace)
                    expected = namespace['normalize_graph'](b'synthetic-reply', value.loaded, value.authority,
                        value.decoder_bundle, PLANNER, now=STAMP, policy={}, expected_authority_source_sha256=AUTH)
                    self.assertEqual(expected, normalize(value))

    def test_exact_wrapper_only_and_diagnostic_failure_never_masks_first_composite_error(self):
        phase = 'NORMALIZE_GRAPH_UNVERIFIED'
        trusted = normalizer.NormalizationFailure(phase)
        self.assertEqual(entry.safe_normalization_failure(trusted, normalizer, 'NORMALIZE'), phase)
        class Subclass(normalizer.NormalizationFailure): pass
        class RaisingAttributes:
            def __getattribute__(self, unused): raise SystemExit(CANARY)
        forged = normalizer.NormalizationFailure(phase); forged.phaseCode = CANARY
        for error, module, stage in (
                (Subclass(phase), normalizer, 'NORMALIZE'), (ValueError(phase), normalizer, 'NORMALIZE'),
                (RuntimeError(CANARY), normalizer, 'NORMALIZE'), (forged, normalizer, 'NORMALIZE'),
                (trusted, normalizer, 'WRITERS_AFTER'), (trusted, object(), 'NORMALIZE'),
                (trusted, RaisingAttributes(), 'NORMALIZE')):
            self.assertEqual(entry.safe_normalization_failure(error, module, stage), 'UNKNOWN')
        cases = ((trusted, False, False, phase),
            (ValueError('SYNTHETIC_FIRST_FAILURE'), False, True, 'UNKNOWN'),
            (ValueError('SYNTHETIC_POST_NORMALIZE_DEADLINE'), True, False, 'UNKNOWN'))
        for error, late, broken, expected in cases:
            with self.subTest(late=late, broken=broken), tempfile.TemporaryDirectory() as temporary:
                result = run_composite_synthetic(self, Path(temporary), error, late=late, broken_diagnostic=broken)
                self.assertEqual(result['receipt']['safeNormalizationFailureCode'], expected)
                self.assertEqual(result['receipt']['failureCode'], error.args[0])

    def test_cli_phase_requires_exact_source_failed_normalize_and_safe_receipt(self):
        receipt = cli_fixture.composite_receipt('NORMALIZE')
        phase = 'NORMALIZE_RESULT_UNVERIFIED'; receipt['safeNormalizationFailureCode'] = phase
        def project(value, passed=False):
            with mock.patch.object(cli, '_read_prep_records', return_value={}):
                return cli.capture_diagnostic('SUMMARY', passed, None, {'receipt': value}, None, None,
                    cli_fixture.SOURCE, cli_fixture.PINS)
        self.assertEqual(project(receipt)['failureCode'], phase)
        mutations = (
            ('sourceCommit', '0' * 40), ('authoritySourceSha256', '0' * 64),
            ('lastStage', 'WRITERS_AFTER'), ('lastStage', CANARY),
            ('safeNormalizationFailureCode', CANARY), ('safeNormalizationFailureCode', None),
            ('pipelineFinishedWithoutException', True), ('pipelineFinishedWithoutException', 0),
            ('originalRoleStopCallsAdded', True), ('extraPrivate', CANARY))
        for key, value in mutations:
            with self.subTest(key=key, value_type=type(value).__name__):
                changed = copy.deepcopy(receipt); changed[key] = value
                public = project(changed)
                self.assertEqual(public['failureCode'], 'UNKNOWN')
                self.assertEqual(public['stageAttempted'], 'SUMMARY')
                self.assertNotIn(CANARY, json.dumps(public))
        public = project(receipt, True)
        self.assertIsNone(public['failureCode']); self.assertEqual(public['stageAttempted'], 'SUMMARY')
        for key in ('safeNormalizationFailureCode',):
            missing = copy.deepcopy(receipt); del missing[key]
            self.assertEqual(project(missing)['failureCode'], 'UNKNOWN')

    def test_cli_first_error_wins_and_public_shape_counts_do_not_claim_normalization(self):
        receipt = cli_fixture.composite_receipt('NORMALIZE')
        receipt['safeNormalizationFailureCode'] = 'NORMALIZE_AUTHORITY_UNVERIFIED'
        provider = subprocess.TimeoutExpired([CANARY], 1, output=CANARY, stderr=CANARY)
        for error, expected in (
                (ValueError('ACTUAL_HOST_COMPILER_JAVA21_REQUIRED'), 'ACTUAL_HOST_COMPILER_JAVA21_REQUIRED'),
                (ValueError(CANARY), 'UNKNOWN'), (provider, 'UNKNOWN'),
                (ValueError('NORMALIZE_GRAPH_UNVERIFIED'), 'UNKNOWN')):
            with self.subTest(error_type=type(error).__name__), \
                    mock.patch.object(cli, '_read_prep_records', side_effect=provider):
                public = cli.capture_diagnostic('SUMMARY', False, error, {'receipt': receipt},
                    None, None, cli_fixture.SOURCE, cli_fixture.PINS)
            self.assertEqual(public['failureCode'], expected)
            self.assertEqual(set(public), {'stageAttempted', 'failureCode', 'lastPrepChild', 'prepCleanup'})
            self.assertIsNone(public['lastPrepChild']); self.assertIsNone(public['prepCleanup'])
            self.assertNotIn(CANARY, json.dumps(public))
        self.assertEqual(cli.literal_failure(ValueError('NORMALIZE_GRAPH_UNVERIFIED')), 'UNKNOWN')
        failed = {'result': None, 'receipt': receipt, 'exitCode': 1}
        summary = cli.safe_summary(cli_fixture.SOURCE, cli_fixture.MANIFEST,
            prepared=cli_fixture.prepared(), outcome=failed, stage='SUMMARY')
        self.assertFalse(summary['passed']); self.assertEqual(summary['status'], 'FAILED')
        self.assertEqual(summary['failureCategory'], 'SUMMARY_NOT_VERIFIED')
        for key in ('capturedObjectCount', 'snapshotCount', 'refCount', 'validationPinCount', 'snapshotCandidateCount'):
            self.assertIsNone(summary['counts'][key])
        self.assertEqual(summary['counts']['objectCandidateCount'], 0)
        self.assertFalse(summary['checks']['sameRunStoppedActorsAndClockVerified'])
        self.assertFalse(summary['checks']['inventoryProduced']); self.assertFalse(summary['checks']['allObjectsKept'])
        self.assertNotIn(CANARY, json.dumps(summary))


if __name__ == '__main__': unittest.main(verbosity=2)
