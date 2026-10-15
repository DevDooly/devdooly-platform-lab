"""Offline contracts only; no Docker, network, JAR loading, or PySpark."""
import copy
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import compose_plan as p
import run_ci as r
import bootstrap_spark as b


def sample():
    return {'schemaVersion': 1, 'passed': True, 'scope': 'ISOLATED_GITHUB_RUNNER_SPARK_JDBC_GARAGE', 'spark': '4.1.1',
        'java': '21.0.9+10-LTS', 'scala': '2.13.17', 'fixtureSha256': r.MODULES['synthetic-v1.ndjson'],
        'bronzeRows': 12, 'bronzeSnapshotCount': 2, 'bronzeRowsSha256': 'a'*64, 'bronzeSnapshotIds': ['9007199254740993', '9223372036854775807'],
        'silverRows': 12, 'success': 7, 'failure': 3, 'duplicate': 2, 'pending': 0, 'silverRowsSha256': 'b'*64, 'silverSnapshotCount': 1,
        'mergeInvocations': 1, 'sequentialReplayInvocations': 1, 'replayWriteInvocations': 0, 'sparkApplicationCount': 1,
        'nativeTrinoVerified': False, 'miniPcPreservationVerified': False, 'kubernetesVerified': False, 'distributedConcurrencyOrCrashRecoveryVerified': False}


class CiBoundaries(unittest.TestCase):
    def test_network_and_aliases_are_internal_only_with_no_host_routes_or_ports(self):
        plan = p.plan('spark-isolated-ci:'+'a'*32)
        self.assertEqual({'trial': {'internal': True}}, plan['networks'])
        self.assertEqual({'postgres', 'garage', 'spark'}, set(plan['services']))
        for service in plan['services'].values():
            self.assertFalse(any(key in service for key in ('ports', 'network_mode', 'extra_hosts', 'privileged')))
            self.assertEqual({'trial'}, set(service['networks']))
            self.assertEqual('no', service['restart'])
        self.assertEqual([p.POSTGRES_ALIAS], plan['services']['postgres']['networks']['trial']['aliases'])
        self.assertEqual([p.GARAGE_ALIAS], plan['services']['garage']['networks']['trial']['aliases'])

    def test_single_local_spark_limits_and_secret_paths_do_not_embed_credentials(self):
        plan = p.plan('spark-isolated-ci:'+'a'*32)
        spark = plan['services']['spark']
        self.assertEqual((1, '3g', '185:185'), (spark['cpus'], spark['mem_limit'], spark['user']))
        self.assertTrue(spark['read_only'])
        self.assertIn('local[1]', spark['command'])
        self.assertNotIn('--packages', json.dumps(plan))
        self.assertNotIn('password', json.dumps(spark['environment']).lower())
        self.assertEqual('/run/ci/bootstrap-password', plan['services']['postgres']['environment']['POSTGRES_PASSWORD_FILE'])

    def test_source_lock_change_is_rejected_before_any_download(self):
        with self.assertRaisesRegex(RuntimeError, 'EXACT_PUBLIC_DOWNLOADED'):
            r.validated_lock(b'{"jars": []}')

    def test_complete_public_result_preserves_bigint_and_narrow_scope(self):
        value = sample()
        self.assertIs(value, r.safe_spark_result(value))
        self.assertEqual('9223372036854775807', value['bronzeSnapshotIds'][1])

    def test_public_result_refuses_private_fields_production_claim_or_bad_counts(self):
        for change in ({'host': 'private'}, {'miniPcPreservationVerified': True}, {'nativeTrinoVerified': True}, {'success': 8}, {'replayWriteInvocations': 1}):
            with self.subTest(change=change), self.assertRaises(RuntimeError):
                r.safe_spark_result({**sample(), **change})

    def test_numeric_rounded_or_duplicate_snapshot_ids_are_not_public_proof(self):
        for ids in ([9007199254740993, '7'], ['7', '7'], ['1', '9223372036854775808']):
            with self.subTest(ids=ids), self.assertRaises((RuntimeError, TypeError)):
                r.safe_spark_result({**sample(), 'bronzeSnapshotIds': ids})

    def test_pg_catalog_is_transactional_dedicated_nonadmin_and_password_is_bounded(self):
        sql = r.pg_init('a'*64).decode()
        self.assertTrue(sql.startswith('BEGIN;'))
        self.assertTrue(sql.endswith('COMMIT;\n'))
        self.assertIn('CREATE ROLE iceberg_catalog LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE', sql)
        self.assertNotIn('lab_catalog', sql)
        with self.assertRaises(RuntimeError):
            r.pg_init("bad'; DROP DATABASE anything;")

    def test_container_inventory_uses_full_ids_and_does_not_adopt_foreign_roles(self):
        attempt = r.Attempt(Path('/synthetic'), 'fresh-project')
        calls = []
        def command(args, **kwargs):
            calls.append(args)
            return SimpleNamespace(stdout=b'')
        attempt.command = command
        self.assertEqual([], attempt.containers())
        self.assertIn('--no-trunc', calls[0])

    def test_workflow_is_manual_read_only_and_uploads_one_explicit_safe_file(self):
        raw = (Path(__file__).resolve().parents[2] / '.github/workflows/lab-ci.yml').read_text('utf-8')
        self.assertIn('  workflow_dispatch:\n    inputs:\n      run_spark_trial:', raw)
        self.assertIn('default: false\n        type: boolean', raw)
        job = raw.split('\n  isolated-spark:\n', 1)[1]
        self.assertIn("if: ${{ github.event_name == 'workflow_dispatch' && inputs.run_spark_trial == true }}", job)
        self.assertIn('permissions:\n  contents: read', raw)
        self.assertIn('persist-credentials: false', job)
        self.assertIn('path: .local/spark-ci-public/summary.json', job)
        self.assertNotIn('secrets.', job)

    def test_unknown_initializer_lookup_is_not_reported_as_absent(self):
        attempt = r.Attempt(Path('/synthetic'), 'fresh-project')
        self.assertIsNone(attempt.initializer())
        attempt.initializer_intended = True
        def command(args, **kwargs):
            if args[1] == 'inspect':
                return SimpleNamespace(returncode=1, stdout=b'')
            raise RuntimeError('DOCKER_READ_UNAVAILABLE')
        attempt.command = command
        with self.assertRaisesRegex(RuntimeError, 'DOCKER_READ_UNAVAILABLE'):
            attempt.initializer()

    def test_session_failure_is_caught_before_any_synthetic_table_operation(self):
        def session():
            raise PermissionError('private-host credential=never-public')
        silver = SimpleNamespace(session=session)
        contract = SimpleNamespace(FIELDS=(), SOURCE_SHA='a'*64, golden_bronze=None, require=None, row_sha=None)
        with tempfile.TemporaryDirectory() as folder, patch.object(b, 'PROOF', Path(folder)), patch.object(b.os, 'O_NOFOLLOW', 0, create=True), \
             patch.dict(sys.modules, {'spark_silver': silver, 'silver_contract': contract}):
            self.assertEqual(1, b.main())
            value = json.loads((Path(folder)/'bootstrap-diagnostic.json').read_bytes())
            self.assertEqual('SESSION', value['lastPhase'])
            self.assertEqual('PermissionError', value['pythonExceptionClass'])
            self.assertEqual(['PYTHON_START', 'IMPORT_SILVER', 'SESSION'], value['milestones'])
            self.assertFalse((Path(folder)/'spark-result.json').exists())
            self.assertNotIn('private-host', json.dumps(value))
            self.assertIs(value, r.safe_bootstrap_diagnostic(value))

    def test_java_cause_projection_never_serializes_error_messages_or_unknown_classes(self):
        class Node:
            def __init__(self, name, cause=None): self.name, self.cause = name, cause
            def getClass(self): return SimpleNamespace(getName=lambda: self.name)
            def getCause(self): return self.cause
        error = RuntimeError('jdbc://private/password=secret')
        error.java_exception = Node('org.apache.spark.SparkException', Node('org.postgresql.util.PSQLException', Node('private.Secret')))
        value = b.exception_classes(error)
        self.assertEqual(['org.apache.spark.SparkException', 'org.postgresql.util.PSQLException'], value['javaCauseClasses'])
        self.assertNotIn('jdbc', json.dumps(value))
        self.assertNotIn('Secret', json.dumps(value))

    def test_actual_exit_oom_and_private_tail_are_recorded_without_inferred_cause(self):
        cid = 'c'*64
        state = {'id': cid, 'role': 'spark', 'running': False, 'exitCode': 137, 'oom': False}
        calls = []
        with tempfile.TemporaryDirectory() as folder, patch.object(r, 'save', side_effect=lambda path, raw: path.write_bytes(raw)):
            def command(argv, **kwargs):
                calls.append((argv, kwargs))
                return SimpleNamespace(returncode=0, stdout=b'java.lang.OutOfMemoryError: private-secret', stderr=b'')
            attempt = SimpleNamespace(root=Path(folder), containers=lambda: [state], command=command)
            value = {}
            r.spark_diagnostics(attempt, state, value)
            self.assertEqual(137, value['exitCode'])
            self.assertIs(False, value['oomKilled'])
            self.assertEqual('JAVA_OUT_OF_MEMORY_SIGNATURE', value['logSignature'])
            self.assertNotIn(cid, json.dumps(value))
            self.assertNotIn('private-secret', json.dumps(value))
            self.assertEqual(['docker', 'logs', '--tail', '200', cid], calls[0][0])
            self.assertTrue(calls[0][1]['sensitive'])
            self.assertIn(b'private-secret', (Path(folder)/'spark-diagnostic.stdout').read_bytes())

    def test_diagnostic_rejects_extra_fields_messages_and_unknown_class_names(self):
        value = {'schemaVersion':1, 'scope':'ISOLATED_SPARK_BOOTSTRAP_DIAGNOSTIC', 'passed':False, 'lastPhase':'SESSION',
            'milestones':['PYTHON_START','SESSION'], 'pythonExceptionClass':'RuntimeError', 'javaCauseClasses':[], 'sessionStopFailed':False}
        self.assertIs(value, r.safe_bootstrap_diagnostic(value))
        for change in ({'message':'secret'}, {'javaCauseClasses':['private.Credential']}, {'pythonExceptionClass':'private-password'},
                       {'milestones':['PYTHON_START']*33}, {'lastPhase':'arbitrary-host'}):
            with self.subTest(change=change), self.assertRaises(RuntimeError):
                r.safe_bootstrap_diagnostic({**value, **change})

    def test_diagnostic_parse_failure_preserves_actual_state_and_does_not_repeat_work(self):
        state = {'id':'c'*64,'role':'spark','running':False,'exitCode':1,'oom':False}
        with tempfile.TemporaryDirectory() as folder, patch.object(r, 'save', side_effect=lambda path, raw: path.write_bytes(raw)):
            root=Path(folder);(root/'proof').mkdir();(root/'proof/bootstrap-diagnostic.json').write_text('{"message":"secret"}')
            attempt=SimpleNamespace(root=root, containers=lambda:[state], command=lambda *a,**k:SimpleNamespace(returncode=0,stdout=b'',stderr=b''))
            value={}
            with self.assertRaises((RuntimeError, KeyError)):
                r.spark_diagnostics(attempt,state,value)
            self.assertTrue(value['stateObserved'])
            self.assertEqual(1,value['exitCode'])
            self.assertFalse(value['oomKilled'])

    def test_session_stop_failure_cannot_publish_successful_completion_diagnostic(self):
        def stop(): raise RuntimeError('secret cleanup details')
        spark=SimpleNamespace(stop=stop)
        silver=SimpleNamespace(session=lambda:spark)
        contract=SimpleNamespace(FIELDS=(),SOURCE_SHA='a'*64,golden_bronze=None,require=None,row_sha=None)
        with tempfile.TemporaryDirectory() as folder, patch.object(b,'PROOF',Path(folder)), \
             patch.object(b.os,'O_NOFOLLOW',0,create=True), patch.object(b,'execute'), \
             patch.dict(sys.modules,{'spark_silver':silver,'silver_contract':contract}):
            self.assertEqual(1,b.main())
            value=json.loads((Path(folder)/'bootstrap-diagnostic.json').read_bytes())
            self.assertFalse(value['passed'])
            self.assertTrue(value['sessionStopFailed'])
            self.assertEqual('STOP_SESSION',value['lastPhase'])
            self.assertNotIn('secret',json.dumps(value))
            r.safe_bootstrap_diagnostic(value)


if __name__ == '__main__':
    unittest.main()
