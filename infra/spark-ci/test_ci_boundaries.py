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
        'nativeTrinoVerified': False, 'miniPcPreservationVerified': False, 'kubernetesVerified': False, 'distributedConcurrencyOrCrashRecoveryVerified': False,
        'compressionExperiment': {'requestedCodec': 'gzip', 'catalogDefaultSetBeforeFirstCatalogAccess': True,
            'bronzePropertyBeforeAppend': 'gzip', 'bronzePropertyAfterRun': 'gzip',
            'silverPropertyAfterWriteAndReplay': 'gzip', 'silverPropertyBeforeWriteObserved': False,
            'verification': 'SHOW_TBLPROPERTIES_ONLY', 'actualParquetFooterCodecVerified': False,
            'priorFailureSoleCauseProven': False}}


def initializer_inspect(project='fresh-project'):
    return {'Id':'c'*64,'Name':'/'+project+'-volume-init',
        'Config':{'Labels':{'devdooly.io.spark-ci-project':project},'Image':r.POSTGRES,
            'Entrypoint':['/bin/chown'],'Cmd':['1000:1000','/meta','/data'],'Env':['SECRET=private-value']},
        'HostConfig':{'NetworkMode':'none','Privileged':False,'PortBindings':None,'Memory':64*1024**2,
            'NanoCpus':100000000,'Binds':[project+'_garage-meta:/meta',project+'_garage-data:/data']},
        'State':{'Running':False,'ExitCode':0,'OOMKilled':False}}


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
            'milestones':['PYTHON_START','SESSION'], 'pythonExceptionClass':'RuntimeError', 'javaCauseClasses':[], 'sessionStopFailed':False,
            'nativeLibraryCategories':[], 'failedMapSegmentObserved':False, 'tmpMountFlag':'UNOBSERVED'}
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
        spark=SimpleNamespace(stop=stop,conf=SimpleNamespace(set=lambda *a:None,get=lambda *a:'gzip'))
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

    def test_gzip_default_is_set_and_read_back_before_first_catalog_access(self):
        calls=[]
        spark=SimpleNamespace(conf=SimpleNamespace(set=lambda key,value:calls.append(('set',key,value)),
            get=lambda key:calls.append(('get',key)) or 'gzip'),stop=lambda:calls.append(('stop',)))
        silver=SimpleNamespace(session=lambda:calls.append(('session',)) or spark)
        contract=SimpleNamespace(FIELDS=(),SOURCE_SHA='a'*64,golden_bronze=None,require=None,row_sha=None)
        with tempfile.TemporaryDirectory() as folder,patch.object(b,'PROOF',Path(folder)),patch.object(b.os,'O_NOFOLLOW',0,create=True), \
             patch.object(b,'execute',side_effect=lambda *a:calls.append(('first-catalog-use',))), \
             patch.dict(sys.modules,{'spark_silver':silver,'silver_contract':contract}):
            self.assertEqual(0,b.main())
            diagnostic=json.loads((Path(folder)/'bootstrap-diagnostic.json').read_bytes())
            r.safe_bootstrap_diagnostic(diagnostic)
        self.assertEqual([('session',),('set',b.CODEC_DEFAULT,'gzip'),('get',b.CODEC_DEFAULT),('first-catalog-use',),('stop',)],calls)
        self.assertIn('GZIP_DEFAULT',diagnostic['milestones'])

    def test_table_property_requires_actual_single_exact_gzip_show_result(self):
        calls=[]
        value=[{'key':b.CODEC_PROPERTY,'value':'gzip'}]
        class Frame:
            def limit(self,count):
                self.assert_limit=count;return self
            def collect(self):return [SimpleNamespace(asDict=lambda row=row:row)for row in value]
        frame=Frame();spark=SimpleNamespace(sql=lambda sql:calls.append(sql) or frame)
        self.assertEqual('gzip',b.gzip_property(spark,b.TABLES[0]))
        self.assertEqual(2,frame.assert_limit)
        self.assertEqual("SHOW TBLPROPERTIES phase6.bronze.synthetic_events ('write.parquet.compression-codec')",calls[0])
        for rows in ([],[{'key':b.CODEC_PROPERTY,'value':'zstd'}],[{'key':b.CODEC_PROPERTY,'value':'gzip','message':'private'}],value*2):
            value=rows
            with self.assertRaises(ValueError):b.gzip_property(spark,b.TABLES[1])
        with self.assertRaises(ValueError):b.gzip_property(spark,'private.other_table')

    def test_public_compression_proof_refuses_footer_prewrite_or_cause_overclaim(self):
        for field,wrong in (('actualParquetFooterCodecVerified',True),('silverPropertyBeforeWriteObserved',True),
                            ('priorFailureSoleCauseProven',True),('silverPropertyAfterWriteAndReplay','zstd'),
                            ('bronzePropertyBeforeAppend','UNOBSERVED'),('privatePath','secret')):
            value=sample();value['compressionExperiment'][field]=wrong
            with self.assertRaises(RuntimeError):r.safe_spark_result(value)

    def test_native_message_classification_is_only_whitelist_and_signature_boolean(self):
        class Node:
            def __init__(self,name,message,cause=None):self.name,self.message,self.cause=name,message,cause
            def getClass(self):return SimpleNamespace(getName=lambda:self.name)
            def getMessage(self):return self.message
            def getCause(self):return self.cause
        error=RuntimeError('password=never-public')
        error.java_exception=Node('org.apache.spark.SparkException','private-host',
            Node('java.lang.UnsatisfiedLinkError','/tmp/private/libzstd-jni-1.so: failed to map segment from shared object; secret=private'))
        result=b.exception_classes(error)
        self.assertEqual(['zstd'],result['nativeLibraryCategories']);self.assertIs(True,result['failedMapSegmentObserved'])
        self.assertNotIn('private',json.dumps(result));self.assertNotIn('/tmp',json.dumps(result))
        value={'schemaVersion':1,'scope':'ISOLATED_SPARK_BOOTSTRAP_DIAGNOSTIC','passed':False,'lastPhase':'APPEND_FIRST',
            'milestones':['PYTHON_START','APPEND_FIRST'],'sessionStopFailed':False,'tmpMountFlag':'NOEXEC',**result}
        r.safe_bootstrap_diagnostic(value)
        for change in ({'nativeLibraryCategories':['/private/libfoo.so']},{'nativeLibraryCategories':['zstd','zstd']},
                       {'failedMapSegmentObserved':'false'},{'tmpMountFlag':'rw,noexec,/private/path'}):
            with self.assertRaises(RuntimeError):r.safe_bootstrap_diagnostic({**value,**change})

    def test_effective_tmp_mount_flag_is_enum_only_and_unknown_is_preserved(self):
        root=b'1 0 0:1 / / rw,relatime - overlay overlay rw\n'
        noexec=b'2 1 0:2 / /tmp rw,nosuid,nodev,noexec - tmpfs tmpfs rw,size=209715200\n'
        nested=b'3 2 0:3 / /tmp/sub rw - tmpfs tmpfs rw\n'
        self.assertEqual('EXEC',b.tmp_mount_flag(root))
        self.assertEqual('NOEXEC',b.tmp_mount_flag(root+noexec+nested))
        self.assertEqual('UNOBSERVED',b.tmp_mount_flag(b'private invalid\n'))
        self.assertEqual('UNOBSERVED',b.tmp_mount_flag(b'x'*(1024**2+1)))
        self.assertEqual('UNOBSERVED',b.tmp_mount_flag(noexec+noexec.replace(b'noexec',b'exec')))

    def test_initializer_accepts_reversed_requested_binds_and_explicit_rw_via_actual_inspect_path(self):
        original=initializer_inspect()
        for binds in (list(reversed(original['HostConfig']['Binds'])),
                      [value+':rw'for value in reversed(original['HostConfig']['Binds'])],
                      [original['HostConfig']['Binds'][0]+':rw',original['HostConfig']['Binds'][1]]):
            raw=copy.deepcopy(original);raw['HostConfig']['Binds']=binds
            attempt=r.Attempt(Path('/synthetic'),'fresh-project');attempt.initializer_intended=True
            attempt.command=lambda *a,**k:SimpleNamespace(returncode=0,stdout=json.dumps([raw]).encode())
            self.assertEqual('c'*64,attempt.initializer()['id'])
            self.assertTrue(all(attempt.initializer_identity_checks.values()))

    def test_initializer_rejects_foreign_duplicate_extra_readonly_and_nonexact_bind_modes(self):
        good=initializer_inspect()['HostConfig']['Binds']
        for binds in ([good[0],good[0]],[*good,'fresh-project_extra:/extra'],
                      ['foreign_garage-meta:/meta',good[1]],[good[0]+':ro',good[1]],
                      [good[0]+':rw,z',good[1]],['/private/host:/meta',good[1]],
                      ['fresh-project_garage-data:/meta',good[1]],None):
            raw=initializer_inspect();raw['HostConfig']['Binds']=binds
            attempt=r.Attempt(Path('/synthetic'),'fresh-project');attempt.initializer_intended=True
            attempt.command=lambda *a,**k:SimpleNamespace(returncode=0,stdout=json.dumps([raw]).encode())
            with self.assertRaisesRegex(RuntimeError,'EXACT_FRESH_INITIALIZER'):
                attempt.initializer()
            checks=r.safe_initializer_checks(attempt.initializer_identity_checks)
            self.assertFalse(checks['requestedBindsVerified']);self.assertTrue(checks['imageVerified'])
            self.assertNotIn('/private',json.dumps(checks))

    def test_initializer_public_projection_is_exact_boolean_only_without_private_inspect(self):
        raw=initializer_inspect();raw['Config']['Image']='private/image'
        checks=r.initializer_identity_checks(raw,'fresh-project','fresh-project-volume-init')
        projected=r.safe_initializer_checks(checks)
        self.assertEqual(set(r.INITIALIZER_CHECK_FIELDS),set(projected));self.assertFalse(projected['imageVerified'])
        self.assertTrue(all(type(value)is bool for value in projected.values()))
        for private in ('SECRET','private-value','private/image','fresh-project','c'*64,'/meta'):
            self.assertNotIn(private,json.dumps(projected))
        for changed in ({**checks,'private':'secret'},{**checks,'imageVerified':'false'}):
            with self.assertRaises(RuntimeError):r.safe_initializer_checks(changed)
        attempt=r.Attempt(Path('/synthetic'),'fresh-project')
        self.assertFalse(any(r.safe_initializer_checks(attempt.initializer_identity_checks).values()))
        for raw in ({},{'HostConfig':{}}):
            incomplete=r.initializer_identity_checks(raw,'fresh-project','fresh-project-volume-init')
            self.assertTrue(incomplete['inspectionObserved'])
            self.assertFalse(any(value for key,value in incomplete.items()if key!='inspectionObserved'))

    def test_image_declared_anonymous_volume_does_not_change_two_requested_bind_guard(self):
        raw=initializer_inspect()
        raw['Mounts']=[{'Type':'volume','Name':'image-anonymous','Destination':'/var/lib/postgresql/data','RW':True},
            {'Type':'volume','Name':'fresh-project_garage-data','Destination':'/data','RW':True},
            {'Type':'volume','Name':'fresh-project_garage-meta','Destination':'/meta','RW':True}]
        attempt=r.Attempt(Path('/synthetic'),'fresh-project');attempt.initializer_intended=True
        attempt.command=lambda *a,**k:SimpleNamespace(returncode=0,stdout=json.dumps([raw]).encode())
        self.assertEqual('c'*64,attempt.initializer()['id'])
        self.assertTrue(attempt.initializer_identity_checks['requestedBindsVerified'])

    def test_other_initializer_identity_and_spec_requirements_remain_required(self):
        mutations={
            'fullIdVerified':lambda v:v.update(Id='short'),
            'nameVerified':lambda v:v.update(Name='/foreign'),
            'projectLabelVerified':lambda v:v['Config']['Labels'].update({'devdooly.io.spark-ci-project':'foreign'}),
            'imageVerified':lambda v:v['Config'].update(Image='foreign'),
            'entrypointVerified':lambda v:v['Config'].update(Entrypoint=['/bin/sh']),
            'commandVerified':lambda v:v['Config'].update(Cmd=['different']),
            'networkNoneVerified':lambda v:v['HostConfig'].update(NetworkMode='host'),
            'unprivilegedVerified':lambda v:v['HostConfig'].update(Privileged=True),
            'noHostPortsVerified':lambda v:v['HostConfig'].update(PortBindings={'80/tcp':[{'HostPort':'80'}]}),
            'memoryLimitVerified':lambda v:v['HostConfig'].update(Memory=0),
            'cpuLimitVerified':lambda v:v['HostConfig'].update(NanoCpus=0)}
        for field,mutate in mutations.items():
            raw=initializer_inspect();mutate(raw)
            attempt=r.Attempt(Path('/synthetic'),'fresh-project');attempt.initializer_intended=True
            attempt.command=lambda *a,**k:SimpleNamespace(returncode=0,stdout=json.dumps([raw]).encode())
            with self.subTest(field=field),self.assertRaises(RuntimeError):attempt.initializer()
            self.assertFalse(attempt.initializer_identity_checks[field])


if __name__ == '__main__':
    unittest.main()
