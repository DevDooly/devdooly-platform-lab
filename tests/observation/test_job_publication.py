"""Synthetic job collection/publication tests; never contact the mini PC or GitHub."""
from copy import deepcopy
from datetime import datetime, timezone
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import zipfile

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'infra/observation'))
import job_collector
import job_contract
import pages_uploader
import host_cycle
import platform_contract
from test_phase3_automation import Files, NoLock, snapshot as platform_snapshot, response
import test_pages_observation as previous_tests
pages=previous_tests.module
run=previous_tests.run

NOW=datetime(2000,1,2,tzinfo=timezone.utc)

class NoIsoParserDatetime(datetime):
    """Catches regression to the parser that cannot read 9 digits on Python 3.10."""
    @classmethod
    def fromisoformat(cls,value):
        raise AssertionError('Do not delegate nanosecond timestamps to fromisoformat')

def job_record(captured='2000-01-01T00:00:04Z'):
    return {'schemaVersion':1,'kind':'job-observation','capturedAt':captured,'environment':'MINI_PC','sourceCommit':'a'*40,
        'synthetic':True,'scope':'DEPLOYED_RUNTIME','publicExecutionEnabled':False,
        'runtime':{'status':'STOPPED','stage':'STOPPED','failureCode':None,'startedAt':'2000-01-01T00:00:00Z',
            'heartbeatAt':'2000-01-01T00:00:03Z','stoppedAt':'2000-01-01T00:00:03Z','sourceCommit':'a'*40,'stale':False},
        'slot':{'occupiedRunId':None},'jobs':[{'runId':'job-one','status':'COMPLETED','exportStatus':'EXPORTED',
            'createdAt':'2000-01-01T00:00:00Z','sourceVerifiedAt':'2000-01-01T00:00:01Z','queuedAt':'2000-01-01T00:00:01Z',
            'completedAt':'2000-01-01T00:00:02Z','exportCompletedAt':'2000-01-01T00:00:03Z','terminatedAt':None,
            'counts':{'input':12,'success':7,'failure':3,'duplicate':2,'pending':0},
            'files':{'result':{'sha256':'b'*64,'size':4500},'failures':{'sha256':'c'*64,'size':2200}},
            'fileEvidence':'VERIFIED_AT_EXPORT_COMMIT'}]}

def service():
    return {'kind':'Service','metadata':{'name':'api','namespace':'platform-lab'},'spec':{
        'type':'ClusterIP','clusterIP':'10.43.1.2','selector':{'app.kubernetes.io/name':'platform-lab','app.kubernetes.io/instance':'lab','app.kubernetes.io/component':'api'},
        'ports':[{'name':'http','port':8080,'targetPort':'http','protocol':'TCP'}]}}

class ContractTests(unittest.TestCase):
    def test_calendar_constructor_preserves_all_nine_digits_without_iso_parser(self):
        ceiling=NoIsoParserDatetime(2000,1,2,tzinfo=timezone.utc)
        with patch.object(platform_contract,'datetime',NoIsoParserDatetime):
            for digits in range(1,10):
                fraction='123456789'[:digits]
                precise=platform_contract.moment('2000-01-01T00:00:04.'+fraction+'Z',ceiling)
                self.assertEqual(precise[0],datetime(2000,1,1,0,0,4,tzinfo=timezone.utc))
                self.assertEqual(precise[1],int(fraction.ljust(9,'0')))
            limit=platform_contract.moment('2000-01-01T00:00:04.123456788Z',ceiling)
            with self.assertRaises(platform_contract.InvalidObservation):
                platform_contract.moment('2000-01-01T00:00:04.123456789Z',limit)
            for invalid in ('2000-02-30T00:00:00.123456789Z','2000-01-01T25:00:00Z','0000-01-01T00:00:00Z'):
                with self.subTest(invalid=invalid),self.assertRaises(platform_contract.InvalidObservation):platform_contract.moment(invalid,ceiling)

    def test_java_instant_nine_digit_capture_is_preserved_by_job_contract(self):
        value=job_record('2000-01-01T00:00:04.845617298Z')
        self.assertIs(job_contract.validate_job_snapshot(value,NOW),value)
        self.assertEqual(value['capturedAt'],'2000-01-01T00:00:04.845617298Z')

    def test_accepts_only_actual_deployed_environment_and_sha(self):
        value=job_record();self.assertIs(job_contract.validate_job_snapshot(value,NOW),value)
        for change in ({'environment':'ISOLATED_LAB','scope':'ISOLATED_LAB'},{'sourceCommit':'unknown'},{'publicExecutionEnabled':True},{'schemaVersion':True}):
            with self.subTest(change=change),self.assertRaises(job_contract.InvalidObservation):job_contract.validate_job_snapshot({**value,**change},NOW)

    def test_closes_all_nested_objects_against_private_fields(self):
        for path in ((),('runtime',),('slot',),('jobs',0),('jobs',0,'counts'),('jobs',0,'files'),('jobs',0,'files','result')):
            value=job_record();target=value
            for part in path:target=target[part]
            target['token']='SYNTHETIC_SECRET'
            with self.subTest(path=path),self.assertRaises(job_contract.InvalidObservation):job_contract.validate_job_snapshot(value,NOW)

    def test_enforces_files_counts_states_and_no_fake_export_verification(self):
        for change in ({'fileEvidence':'EXPECTED_FROM_DB'},{'exportCompletedAt':None},{'status':'RUNNING'},
                       {'counts':{'input':12,'success':8,'failure':3,'duplicate':2,'pending':0}},
                       {'files':{'result':{'sha256':'B'*64,'size':1},'failures':{'sha256':'c'*64,'size':2}}}):
            value=job_record();value['jobs'][0].update(change)
            with self.subTest(change=change),self.assertRaises(job_contract.InvalidObservation):job_contract.validate_job_snapshot(value,NOW)

    def test_bounded_unique_jobs_and_real_nanosecond_chronology(self):
        value=job_record();value['jobs']*=2
        with self.assertRaises(job_contract.InvalidObservation):job_contract.validate_job_snapshot(value,NOW)
        value=job_record();value['jobs']=[{**value['jobs'][0],'runId':f'job-{i}'} for i in range(21)]
        with self.assertRaises(job_contract.InvalidObservation):job_contract.validate_job_snapshot(value,NOW)
        value=job_record();value['capturedAt']='2000-02-30T00:00:00Z'
        with self.assertRaises(job_contract.InvalidObservation):job_contract.validate_job_snapshot(value,NOW)
        value=job_record();value['jobs'][0]['exportCompletedAt']='2000-01-01T00:00:04.000000001Z'
        with self.assertRaises(job_contract.InvalidObservation):job_contract.validate_job_snapshot(value,NOW)

    def test_runtime_cleanup_failure_is_a_narrow_valid_pause_and_stale_is_age(self):
        value=job_record();value['runtime'].update(status='PAUSED_OPERATOR',failureCode='RESOURCE_CLOSE_FAILED')
        job_contract.validate_job_snapshot(value,NOW)
        value['runtime']['failureCode']='EXPORT_FAILED'
        with self.assertRaises(job_contract.InvalidObservation):job_contract.validate_job_snapshot(value,NOW)
        value=job_record('2000-01-01T00:05:04Z');value['runtime'].update(status='RUNNING',stage='EXPORT',stoppedAt=None,stale=True)
        job_contract.validate_job_snapshot(value,NOW)
        value['runtime']['stale']=False
        with self.assertRaises(job_contract.InvalidObservation):job_contract.validate_job_snapshot(value,NOW)

class ReadResponse(io.BytesIO):
    status=200
    def __enter__(self):return self
    def __exit__(self,*unused):self.close()

class CollectorTests(unittest.TestCase):
    def test_exact_service_identity_selector_cidr_port_are_required(self):
        self.assertEqual(job_collector.api_endpoint(service()),'http://10.43.1.2:8080/api/jobs/observation')
        for change in ({'clusterIP':'127.0.0.1'},{'clusterIP':'169.254.169.254'},{'clusterIP':'192.168.1.1'},{'clusterIP':'10.44.1.2'},
                       {'type':'ExternalName'},{'type':'NodePort'},{'selector':{}},{'ports':[{'name':'http','port':80,'targetPort':'http'}]}):
            value=service();value['spec'].update(change)
            with self.subTest(change=change),self.assertRaises(job_collector.JobCollectionError):job_collector.api_endpoint(value)

    def test_only_fixed_get_routes_and_no_serviceaccount_auth_to_application(self):
        calls=[]
        def kube(path,code):calls.append(path);return service()
        def opened(request,**kwargs):
            self.assertEqual(request.full_url,'http://10.43.1.2:8080/api/jobs/observation');self.assertEqual(request.method,'GET')
            self.assertIsNone(request.get_header('Authorization'));self.assertIsNone(request.get_header('Cookie'))
            return ReadResponse(json.dumps(job_record()).encode())
        value=job_collector.collect_jobs(kube,opener=SimpleNamespace(open=opened),now=NOW)
        self.assertEqual(calls,[job_collector.SERVICE_PATH]);self.assertEqual(value,job_record())

    def test_oversize_duplicate_keys_and_unknown_fields_are_rejected(self):
        for raw in (b' '* (job_contract.MAX_JOB_SNAPSHOT+1),b'{"value":1,"value":2}',json.dumps({**job_record(),'bucket':'private'}).encode()):
            with self.subTest(raw=raw[:20]),self.assertRaises(Exception):
                job_collector.collect_jobs(lambda *args:service(),opener=SimpleNamespace(open=lambda *args,**kwargs:ReadResponse(raw)),now=NOW)

    def test_capture_error_keeps_last_good_file_and_does_not_print_raw_error(self):
        with tempfile.TemporaryDirectory() as folder:
            output=Path(folder)/'jobs.json';output.write_bytes(b'existing-good-record')
            with patch.object(job_collector,'JsonTransport'),patch.object(job_collector,'collect_jobs',side_effect=RuntimeError('PRIVATE_CANARY')),\
                    patch('sys.stdout',new_callable=io.StringIO) as stdout:
                status=job_collector.main(['--server','https://127.0.0.1:6443','--token-file','unused','--ca-file','unused','--output',str(output)])
            self.assertEqual(status,1);self.assertEqual(output.read_bytes(),b'existing-good-record')
            self.assertEqual(json.loads(stdout.getvalue()),{'status':'failure','errorCode':'JOB_CAPTURE_FAILED'})
            self.assertNotIn('PRIVATE_CANARY',stdout.getvalue())

class UploadFeatureTests(Files):
    def test_joint_dispatch_uses_two_bounded_inputs_and_combined_intent(self):
        calls=[]
        def sender(request):calls.append(json.loads(request.data));return response()
        pages_uploader.dispatch(platform_snapshot(),self.token,self.journal,sender=sender,now=NOW,job_snapshot=job_record())
        self.assertEqual(set(calls[0]['inputs']),{'platform_snapshot','jobs_snapshot'})
        self.assertEqual(json.loads(calls[0]['inputs']['jobs_snapshot']),job_record())
        changed=job_record('2000-01-01T00:00:05Z')
        pages_uploader.dispatch(platform_snapshot(),self.token,self.journal,sender=sender,now=NOW,job_snapshot=changed)
        self.assertEqual(len(calls),2)
        result=pages_uploader.dispatch(platform_snapshot(),self.token,self.journal,sender=lambda _:self.fail('same intent'),now=NOW,job_snapshot=changed)
        self.assertEqual(result['attemptStatus'],'SAME_ATTEMPT_NOT_RETRIED')
        self.assertNotIn(self.token.read_text(),self.journal.read_text());self.assertNotIn('jobs_snapshot',self.journal.read_text())

    def test_invalid_job_input_does_not_send_or_write_intent(self):
        invalid=job_record();invalid['environment']='ISOLATED_LAB';invalid['scope']='ISOLATED_LAB'
        with self.assertRaises(pages_uploader.AutomationError):
            pages_uploader.dispatch(platform_snapshot(),self.token,self.journal,sender=lambda _:self.fail('invalid send'),now=NOW,job_snapshot=invalid)
        self.assertFalse(self.journal.exists())

class CycleFeatureTests(Files):
    def setUp(self):
        super().setUp()
        def directory(path):path.mkdir(mode=0o700,exist_ok=True);os.chmod(path,0o700)
        guard=patch.object(host_cycle,'private_directory',side_effect=directory);guard.start();self.addCleanup(guard.stop)

    def config(self):
        return {'k3s_path':'/PRIVATE/k3s','kubeconfig':'/PRIVATE/admin-config','server':'https://127.0.0.1:6443','ca_file':'/PRIVATE/ca',
            'collector_path':'/PRIVATE/platform_collector.py','state_directory':str(self.root/'state'),'runtime_directory':str(self.root/'runtime'),
            'pages_token_file':str(self.token),'jobs_enabled':'true'}

    def execute(self,job_failure=False,nanoseconds=False):
        config=self.config();calls=[];posted=[]
        def runner(arguments,**kwargs):
            calls.append(arguments)
            if len(calls)==1:return SimpleNamespace(returncode=0,stdout=b'aaa.bbb.ccc')
            output=Path(arguments[arguments.index('--output')+1]);instant=datetime.now(timezone.utc).isoformat(timespec='microseconds').replace('+00:00','Z')
            if nanoseconds:instant=instant[:-1]+'298Z'
            if len(calls)==2:output.write_text(json.dumps(platform_snapshot(instant)));os.chmod(output,0o600);return SimpleNamespace(returncode=0)
            self.assertNotIn('--kubeconfig',arguments)
            if job_failure:
                output.write_text(json.dumps(job_record()));os.chmod(output,0o600)
                raise subprocess.TimeoutExpired(arguments,20,stderr='PRIVATE_CANARY')
            output.write_text(json.dumps(job_record(instant)));os.chmod(output,0o600);return SimpleNamespace(returncode=0)
        def publish(*args,**kwargs):posted.append((args,kwargs));return pages_uploader.public_report('DISPATCHED',123)
        report=host_cycle.run_cycle(config,runner=runner,uploader=publish,lock_class=NoLock)
        return config,calls,posted,report

    def test_enabled_jobs_share_short_lived_token_and_joint_dispatch_then_cleanup(self):
        config,calls,posted,report=self.execute()
        self.assertEqual(report['attemptStatus'],'DISPATCHED');self.assertEqual(len(calls),3)
        self.assertEqual(set(posted[0][1]),{'job_snapshot'})
        self.assertEqual(posted[0][1]['job_snapshot']['environment'],'MINI_PC')
        self.assertEqual(list(Path(config['runtime_directory']).iterdir()),[])
        self.assertEqual(json.loads((Path(config['state_directory'])/'jobs-capture.json').read_text())['status'],'success')

    def test_nine_digit_http_capture_is_dispatched_without_loss_or_legacy_iso_parser(self):
        with patch.object(host_cycle,'datetime',NoIsoParserDatetime):
            config,calls,posted,report=self.execute(nanoseconds=True)
        self.assertEqual(report['attemptStatus'],'DISPATCHED')
        captured=posted[0][1]['job_snapshot']['capturedAt']
        self.assertRegex(captured,r'\.[0-9]{6}298Z$')
        self.assertEqual(json.loads((Path(config['state_directory'])/'jobs-capture.json').read_text())['capturedAt'],captured)
        self.assertEqual(list(Path(config['runtime_directory']).iterdir()),[])

    def test_job_timeout_still_publishes_platform_and_keeps_last_good_job_file(self):
        config,calls,posted,report=self.execute(job_failure=True)
        self.assertEqual(report['attemptStatus'],'DISPATCHED');self.assertEqual(posted[0][1],{})
        self.assertEqual(list(Path(config['runtime_directory']).iterdir()),[])
        journal=json.loads((Path(config['state_directory'])/'jobs-capture.json').read_text())
        self.assertEqual(journal['status'],'failure');self.assertIsNone(journal['capturedAt'])
        self.assertNotIn('PRIVATE_CANARY',json.dumps(journal))
        self.assertEqual(json.loads((Path(config['state_directory'])/'jobs-observation.json').read_text()),job_record())

class JobPagesTests(unittest.TestCase):
    setup_source=previous_tests.ArtifactTests.setup_source

    def artifact(self,number,attempt=1):
        return {'id':44,'name':f'job-observation-{number}-a{attempt}','expired':False,'workflow_run':{'id':number}}

    def archive(self,value):
        raw=io.BytesIO()
        with zipfile.ZipFile(raw,'w') as zipped:
            zipped.writestr('publication.json',json.dumps({'schemaVersion':1,'kind':'job-observation-publication','recordPresent':value is not None}))
            if value is not None:zipped.writestr('jobs.latest.json',json.dumps(value))
        return raw.getvalue()

    def v2(self,number=1):
        value=run(number,'2026-01-01T00:00:09Z');value['name']='Portfolio snapshots v2 · workflow_dispatch';value['display_title']=value['name'];return value

    def test_v3_keeps_v2_job_and_platform_artifact_schemas_without_a_kafka_input(self):
        metadata=self.v2();metadata['name']='Portfolio snapshots v3 · workflow_dispatch';metadata['display_title']=metadata['name']
        value=job_record();get,download=self.setup_source([metadata],[self.artifact(1)],self.archive(value))
        self.assertEqual(pages.previous_snapshot(get,download,2,1,lambda unused:None,jobs=True),value)
        from test_pages_observation import archive
        platform=platform_snapshot();artifact={'id':45,'name':'platform-observation-1-a1','expired':False,'workflow_run':{'id':1}}
        get,download=self.setup_source([metadata],[artifact],archive(platform))
        self.assertEqual(pages.previous_snapshot(get,download,2,1,lambda unused:None),platform)

    def test_v1_deployment_does_not_require_a_job_artifact_during_upgrade(self):
        get,download=self.setup_source([run(1,'2026-01-01T00:00:09Z')])
        self.assertIsNone(pages.previous_snapshot(get,download,2,1,lambda _:None,jobs=True))

    def test_v2_presence_manifest_can_honestly_publish_no_record(self):
        get,download=self.setup_source([self.v2()],[self.artifact(1)],self.archive(None))
        self.assertIsNone(pages.previous_snapshot(get,download,2,1,lambda _:None,jobs=True))

    def test_v2_recovers_exact_latest_deployed_job_record(self):
        value=job_record();get,download=self.setup_source([self.v2()],[self.artifact(1)],self.archive(value))
        self.assertEqual(pages.previous_snapshot(get,download,2,1,lambda _:None,jobs=True),value)

    def test_v2_manifest_cannot_hide_extra_or_missing_record_files(self):
        for extra in ('../private.json','jobs.latest.json'):
            content=io.BytesIO()
            with zipfile.ZipFile(content,'w') as zipped:
                zipped.writestr('publication.json',json.dumps({'schemaVersion':1,'kind':'job-observation-publication','recordPresent':False}))
                zipped.writestr(extra,'{}')
            get,download=self.setup_source([self.v2()],[self.artifact(1)],content.getvalue())
            with self.subTest(extra=extra),self.assertRaises(pages.ObservationError):pages.previous_snapshot(get,download,2,1,lambda _:None,jobs=True)

    def test_v2_missing_expected_artifact_fails_closed_instead_of_regressing_to_seed(self):
        get,download=self.setup_source([self.v2()])
        with self.assertRaisesRegex(pages.ObservationError,'ARTIFACT_UNAVAILABLE'):pages.previous_snapshot(get,download,2,1,lambda _:None,jobs=True)

    def test_v2_platform_baseline_remains_compatible(self):
        from test_pages_observation import archive
        metadata=self.v2();value=platform_snapshot()
        artifact={'id':45,'name':'platform-observation-1-a1','expired':False,'workflow_run':{'id':1}}
        get,download=self.setup_source([metadata],[artifact],archive(value))
        self.assertEqual(pages.previous_snapshot(get,download,2,1,lambda _:None),value)

    def test_jobs_ordering_and_equal_time_conflicts_preserve_capture_time(self):
        old,new=job_record(),job_record('2000-01-01T00:00:05Z')
        self.assertEqual(pages.merge_job_records(new,old),new);self.assertEqual(pages.merge_job_records(new,None),new)
        conflict=deepcopy(new);conflict['runtime']['stage']='EXPORT'
        with self.assertRaises(pages.ObservationError):pages.merge_job_records(new,conflict)

    def test_missing_seed_and_input_removes_copied_asset_and_writes_false_manifest(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);output=root/'out';artifact=root/'artifact';output.mkdir();(output/'jobs.latest.json').write_text('isolated-old-seed')
            self.assertIsNone(pages.prepare_job_output(None,None,output,artifact,lambda _:self.fail('no record to validate')))
            self.assertFalse((output/'jobs.latest.json').exists())
            self.assertEqual(json.loads((artifact/'publication.json').read_text())['recordPresent'],False)

    def test_later_push_without_input_retains_same_job_file_and_manifest(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);value=job_record()
            self.assertEqual(pages.prepare_job_output(value,None,root/'out',root/'artifact',lambda _:None),value)
            self.assertEqual(json.loads((root/'out/jobs.latest.json').read_text()),value)
            self.assertEqual((root/'out/jobs.latest.json').read_bytes(),(root/'artifact/jobs.latest.json').read_bytes())

    def test_job_dispatch_rejects_isolated_scope_and_future_timestamp_even_when_browser_validation_passes(self):
        validate=pages.job_validator(ROOT)
        with patch.object(pages.subprocess,'run',return_value=subprocess.CompletedProcess([],0)),patch.object(pages.time,'time_ns',return_value=pages.instant('2000-01-01T00:00:04Z')):
            validate(job_record())
            value=job_record();value['environment']='ISOLATED_LAB';value['scope']='ISOLATED_LAB'
            with self.assertRaises(pages.ObservationError):validate(value)
            with self.assertRaises(pages.ObservationError):validate(job_record('2000-01-01T00:00:04.000000001Z'))

if __name__=='__main__':unittest.main()
