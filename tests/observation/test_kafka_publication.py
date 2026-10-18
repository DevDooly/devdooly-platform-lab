"""Synthetic Kafka host/Pages contracts only; no host, Kafka, GitHub or real token."""
from contextlib import nullcontext
from copy import deepcopy
from datetime import datetime, timezone
import io
import json
import os
from pathlib import Path
import subprocess
import shutil
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import zipfile

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'infra/observation'))
import host_cycle
import kafka_collector
import kafka_contract
import pages_uploader
from test_job_publication import service, ReadResponse, job_record
from test_phase3_automation import Files, NoLock, snapshot as platform_snapshot, response
import test_pages_observation as previous_tests
pages=previous_tests.module
NOW=datetime(2000,1,2,tzinfo=timezone.utc)


def kafka_record(captured='2000-01-01T00:00:04Z',started='2000-01-01T00:00:00Z'):
    return {'schemaVersion':1,'kind':'kafka-observation','synthetic':True,'environment':'MINI_PC',
        'scope':'DEPLOYED_KAFKA','publicExecutionEnabled':False,'sourceCommit':'a'*40,
        'captureStartedAt':started,'capturedAt':captured,'consistency':'BOUNDED_SEQUENTIAL_READ',
        'targetFingerprint':'b'*64,'groupState':'STABLE','partition':0,'commitState':'OBSERVED',
        'logStartOffset':1,'readCommittedEndOffset':7,'committedOffset':3,'lag':4}


class KafkaContractTests(unittest.TestCase):
    def test_known_lag_zero_and_absent_commit_remain_distinct(self):
        value=kafka_record();self.assertIs(kafka_contract.validate_kafka_snapshot(value,NOW),value)
        value.update(committedOffset=7,lag=0);kafka_contract.validate_kafka_snapshot(value,NOW)
        value.update(groupState='EMPTY',commitState='NO_COMMIT',committedOffset=None,lag=None)
        kafka_contract.validate_kafka_snapshot(value,NOW)
        value['lag']=0
        with self.assertRaises(Exception):kafka_contract.validate_kafka_snapshot(value,NOW)

    def test_exact_scope_source_fields_numbers_and_offset_relations(self):
        for change in ({'environment':'ISOLATED_LAB','scope':'ISOLATED_KAFKA'},{'sourceCommit':'unknown'},
                {'schemaVersion':True},{'partition':True},{'lag':True},{'committedOffset':True},
                {'logStartOffset':-1},{'readCommittedEndOffset':2},{'committedOffset':8},
                {'readCommittedEndOffset':9007199254740992},{'consistency':'ATOMIC'},
                {'targetFingerprint':'B'*64},{'groupState':['STABLE']},{'publicExecutionEnabled':True},
                {'privateBroker':'SYNTHETIC_PRIVATE_CANARY'}):
            with self.subTest(keys=tuple(change)),self.assertRaises(Exception):
                kafka_contract.validate_kafka_snapshot({**kafka_record(),**change},NOW)

    def test_precise_four_second_boundary_calendar_future_and_order(self):
        value=kafka_record('2000-01-01T00:00:04.123456789Z','2000-01-01T00:00:00.123456789Z')
        kafka_contract.validate_kafka_snapshot(value,NOW)
        for started,captured in (('2000-01-01T00:00:00Z','2000-01-01T00:00:04.000000001Z'),
                ('2000-01-01T00:00:04.000000001Z','2000-01-01T00:00:04Z'),
                ('2000-02-30T00:00:00Z','2000-02-30T00:00:01Z'),
                ('2000-01-02T00:00:00Z','2000-01-02T00:00:00.000000001Z'),
                ('2000-01-01T00:00:00+00:00','2000-01-01T00:00:01Z')):
            with self.subTest(started=started),self.assertRaises(Exception):
                kafka_contract.validate_kafka_snapshot(kafka_record(captured,started),NOW)

    def test_bounded_raw_json_rejects_duplicate_nonfinite_and_extra(self):
        raw=json.dumps(kafka_record()).encode();self.assertEqual(kafka_contract.parse_kafka_snapshot(raw,NOW),kafka_record())
        for invalid in (b' '*8193,b'{"schemaVersion":1,"schemaVersion":1}',b'{"x":NaN}',
                b'{"x":Infinity}',b'\xff',raw+b' {}',raw.replace(b'"lag": 4',b'"lag": 4.0'),
                raw.replace(b'"lag": 4',b'"lag": 4e0'),raw.replace(b'"partition": 0',b'"partition": -0')):
            with self.subTest(prefix=invalid[:16]),self.assertRaises(Exception):kafka_contract.parse_kafka_snapshot(invalid,NOW)


class KafkaCollectorTests(unittest.TestCase):
    def test_same_service_identity_and_fixed_get_without_application_credentials(self):
        calls=[]
        stamp=NOW.isoformat().replace('+00:00','Z');value=kafka_record(stamp,stamp)
        def kube(path,code):calls.append(path);return service()
        def opened(request,**kwargs):
            self.assertEqual(request.full_url,'http://10.43.1.2:8080/api/kafka/observation')
            self.assertEqual(request.method,'GET');self.assertNotIn('?',request.full_url)
            self.assertIsNone(request.get_header('Authorization'));self.assertIsNone(request.get_header('Cookie'))
            self.assertLessEqual(kwargs['timeout'],4)
            return ReadResponse(json.dumps(value).encode())
        self.assertEqual(kafka_collector.collect_kafka(kube,opener=SimpleNamespace(open=opened),now=NOW),value)
        self.assertEqual(calls,[kafka_collector.SERVICE_PATH])
        invalid=service();invalid['spec']['clusterIP']='169.254.169.254'
        with self.assertRaises(Exception):kafka_collector.api_endpoint(invalid)

    def test_late_response_and_replayed_capture_are_not_success(self):
        stamp=NOW.isoformat().replace('+00:00','Z');raw=json.dumps(kafka_record(stamp,stamp)).encode()
        with patch.object(kafka_collector.time,'monotonic',side_effect=[0,0,11]):
            with self.assertRaises(Exception):kafka_collector.collect_kafka(lambda *unused:service(),
                opener=SimpleNamespace(open=lambda *unused,**kwargs:ReadResponse(raw)),deadline=10,now=NOW)
        with self.assertRaises(Exception):kafka_collector.collect_kafka(lambda *unused:service(),
            opener=SimpleNamespace(open=lambda *unused,**kwargs:ReadResponse(json.dumps(kafka_record()).encode())),now=NOW)

    def test_error_invalid_new_target_and_old_response_preserve_prior_file(self):
        for changed in (RuntimeError('SYNTHETIC_PRIVATE_CANARY'),{'targetFingerprint':'c'*64},
                {'capturedAt':'2000-01-01T00:00:03Z'}):
            with self.subTest(change_type=type(changed).__name__),tempfile.TemporaryDirectory() as temporary:
                output=Path(temporary)/'kafka.json';original=json.dumps(kafka_record()).encode();output.write_bytes(original);os.chmod(output,0o600)
                value={**kafka_record(),**changed} if isinstance(changed,dict) else None
                with patch.object(kafka_collector,'JsonTransport'),patch.object(kafka_collector,'collect_kafka',
                        side_effect=changed if isinstance(changed,Exception) else None,return_value=value),\
                        patch.object(kafka_collector,'load_kafka_snapshot',return_value=kafka_record()),\
                        patch('sys.stdout',new_callable=io.StringIO) as printed:
                    status=kafka_collector.main(['--server','https://127.0.0.1:6443','--token-file','unused',
                        '--ca-file','unused','--output',str(output)])
                self.assertEqual(status,1);self.assertEqual(output.read_bytes(),original)
                self.assertEqual(json.loads(printed.getvalue()),{'status':'failure','errorCode':'KAFKA_CAPTURE_FAILED'})
                self.assertNotIn('SYNTHETIC_PRIVATE_CANARY',printed.getvalue())


class KafkaUploadTests(Files):
    def test_three_inputs_have_joint_fingerprint_and_same_intent_is_not_retried(self):
        sent=[]
        def sender(request):sent.append(json.loads(request.data));return response()
        pages_uploader.dispatch(platform_snapshot(),self.token,self.journal,sender=sender,now=NOW,
            job_snapshot=job_record(),kafka_snapshot=kafka_record())
        self.assertEqual(set(sent[0]['inputs']),{'platform_snapshot','jobs_snapshot','kafka_snapshot'})
        changed=kafka_record();changed['committedOffset']=7;changed['lag']=0
        pages_uploader.dispatch(platform_snapshot(),self.token,self.journal,sender=sender,now=NOW,
            job_snapshot=job_record(),kafka_snapshot=changed)
        self.assertEqual(len(sent),2)
        result=pages_uploader.dispatch(platform_snapshot(),self.token,self.journal,sender=lambda unused:self.fail('retry'),
            now=NOW,job_snapshot=job_record(),kafka_snapshot=changed)
        self.assertEqual(result['attemptStatus'],'SAME_ATTEMPT_NOT_RETRIED')
        self.assertNotIn('kafka_snapshot',self.journal.read_text());self.assertNotIn(self.token.read_text(),self.journal.read_text())

    def test_invalid_optional_kafka_cannot_block_two_valid_existing_inputs(self):
        sent=[];bad={**kafka_record(),'environment':'ISOLATED_LAB','scope':'ISOLATED_KAFKA'}
        pages_uploader.dispatch(platform_snapshot(),self.token,self.journal,now=NOW,
            sender=lambda request:(sent.append(json.loads(request.data)) or response()),job_snapshot=job_record(),kafka_snapshot=bad)
        self.assertEqual(set(sent[0]['inputs']),{'platform_snapshot','jobs_snapshot'})

    def test_payload_escaping_budget_drops_only_optional_kafka_before_send(self):
        sent=[]
        # The underlying existing platform/jobs contract checks are tested elsewhere;
        # here force a boundary-sized serialized request to exercise the real byte cap.
        original=pages_uploader.json.dumps
        def encoded(value,*args,**kwargs):
            raw=original(value,*args,**kwargs)
            if isinstance(value,dict) and set(value)=={'ref','inputs'} and 'kafka_snapshot' in value['inputs']:
                return raw+' '*65536
            return raw
        with patch.object(pages_uploader.json,'dumps',side_effect=encoded):
            pages_uploader.dispatch(platform_snapshot(),self.token,self.journal,now=NOW,
                sender=lambda request:(sent.append(json.loads(request.data)) or response()),
                job_snapshot=job_record(),kafka_snapshot=kafka_record())
        self.assertEqual(set(sent[0]['inputs']),{'platform_snapshot','jobs_snapshot'})


class KafkaCycleTests(Files):
    def config(self):
        return {'k3s_path':'/PRIVATE/k3s','kubeconfig':'/PRIVATE/admin','server':'https://127.0.0.1:6443',
            'ca_file':'/PRIVATE/ca','collector_path':'/PRIVATE/platform_collector.py','state_directory':str(self.root/'state'),
            'runtime_directory':str(self.root/'runtime'),'pages_token_file':str(self.token),'jobs_enabled':'true','kafka_enabled':'true'}

    def execute(self,failed=False,budget=False,enabled=True):
        config=self.config();config['kafka_enabled']='true' if enabled else 'false';calls=[];posted=[];clock=[0]
        def private(path):path.mkdir(mode=0o700,exist_ok=True);os.chmod(path,0o700)
        def runner(args,**kwargs):
            calls.append((args,kwargs))
            if len(calls)==1:return SimpleNamespace(returncode=0,stdout=b'aaa.bbb.ccc')
            output=Path(args[args.index('--output')+1]);stamp=datetime.now(timezone.utc).isoformat().replace('+00:00','Z')
            if len(calls)==2:value=platform_snapshot(stamp)
            elif len(calls)==3:
                value=job_record(stamp)
                if budget:clock[0]=120
            else:
                if failed:raise subprocess.TimeoutExpired('kafka-child',12,stderr='SYNTHETIC_PRIVATE_CANARY')
                value=kafka_record(stamp,stamp)
            output.write_text(json.dumps(value));os.chmod(output,0o600);return SimpleNamespace(returncode=0)
        def publish(*args,**kwargs):posted.append(kwargs);return pages_uploader.public_report('DISPATCHED',123)
        with patch.object(host_cycle,'private_directory',side_effect=private):
            report=host_cycle.run_cycle(config,runner=runner,uploader=publish,lock_class=NoLock,
                deadline_class=lambda unused:nullcontext(),monotonic=lambda:clock[0])
        self.assertEqual(list(Path(config['runtime_directory']).iterdir()),[])
        return config,calls,posted,report

    def test_enabled_capture_shares_existing_short_lived_token_without_admin_fallback(self):
        config,calls,posted,report=self.execute()
        self.assertEqual(report['attemptStatus'],'DISPATCHED');self.assertEqual(len(calls),4)
        self.assertEqual(set(posted[0]),{'job_snapshot','kafka_snapshot'})
        self.assertEqual(calls[3][1]['timeout'],12);self.assertNotIn('--kubeconfig',calls[3][0])
        self.assertEqual(json.loads((Path(config['state_directory'])/'kafka-capture.json').read_text())['status'],'success')

    def test_failure_or_insufficient_reserve_keeps_existing_publication_and_cleans_token(self):
        for options in ({'failed':True},{'budget':True},{'enabled':False}):
            with self.subTest(options=options):
                config,calls,posted,report=self.execute(**options)
                self.assertEqual(report['attemptStatus'],'DISPATCHED');self.assertEqual(set(posted[0]),{'job_snapshot'})
                self.assertEqual(len(calls),4 if options.get('failed') else 3)
                self.assertFalse((Path(config['state_directory'])/'kafka-observation.json').exists())


class KafkaPagesTests(unittest.TestCase):
    setup_source=previous_tests.ArtifactTests.setup_source
    def v3(self):
        value=previous_tests.run(1,'2026-01-01T00:00:09Z');value['name']='Portfolio snapshots v3 · workflow_dispatch';value['display_title']=value['name'];return value
    def artifact(self):return {'id':44,'name':'kafka-observation-1-a1','expired':False,'workflow_run':{'id':1}}
    def archive(self,value):
        raw=io.BytesIO()
        with zipfile.ZipFile(raw,'w') as zipped:
            zipped.writestr('publication.json',json.dumps({'schemaVersion':1,'kind':'kafka-observation-publication','recordPresent':value is not None}))
            if value is not None:zipped.writestr('kafka.latest.json',json.dumps(value))
        return raw.getvalue()
    def test_v1_v2_upgrade_needs_no_fake_kafka_baseline_and_v3_absence_is_explicit(self):
        old=previous_tests.run(1,'2026-01-01T00:00:09Z')
        for title in ('Portfolio snapshot v1 · workflow_dispatch','Portfolio snapshots v2 · workflow_dispatch'):
            metadata={**old,'name':title,'display_title':title};get,download=self.setup_source([metadata])
            self.assertIsNone(pages.previous_snapshot(get,download,2,1,lambda unused:None,kafka=True))
        get,download=self.setup_source([self.v3()],[self.artifact()],self.archive(None))
        self.assertIsNone(pages.previous_snapshot(get,download,2,1,lambda unused:None,kafka=True))
    def test_v3_recovers_exact_record_and_missing_expired_invalid_baselines_fail_closed(self):
        get,download=self.setup_source([self.v3()],[self.artifact()],self.archive(kafka_record()))
        self.assertEqual(pages.previous_snapshot(get,download,2,1,lambda unused:None,kafka=True),kafka_record())
        for artifacts,archive in (([],None),([{**self.artifact(),'expired':True}],None),([self.artifact()],b'not-a-zip')):
            get,download=self.setup_source([self.v3()],artifacts,archive)
            with self.subTest(artifact_count=len(artifacts)),self.assertRaises(Exception):
                pages.previous_snapshot(get,download,2,1,lambda unused:None,kafka=True)
    def test_target_change_conflict_older_and_missing_input_never_invent_a_new_clock(self):
        old=kafka_record();new=kafka_record('2000-01-01T00:00:05Z','2000-01-01T00:00:01Z')
        self.assertEqual(pages.merge_kafka_records(new,old),new);self.assertEqual(pages.merge_kafka_records(new,None),new)
        for incoming in ({**new,'lag':99},{**old,'targetFingerprint':'c'*64}):
            with self.assertRaises(pages.ObservationError):pages.merge_kafka_records(new,incoming)
    @unittest.skipUnless(shutil.which('node'),'Node runtime required for actual frontend-parser interoperability')
    def test_pages_uses_real_frontend_source_parser_and_rejects_integer_lexeme_aliases(self):
        value=kafka_record();value.update(committedOffset=7,lag=0)
        raw=json.dumps(value)
        module=(ROOT/'apps/lab-web/src/lib/kafka-observation.ts').as_uri()
        script=("import fs from 'node:fs';import {parseKafkaObservation} from "+json.dumps(module)+";"
            "try{process.exit(parseKafkaObservation(fs.readFileSync(0,'utf8'))?0:2);}catch{process.exit(2);}")
        def node(text):
            return subprocess.run(['node','--experimental-strip-types','--input-type=module','-e',script],
                input=text,text=True,capture_output=True,timeout=5).returncode
        self.assertEqual(node(raw),0)
        validate=pages.kafka_validator(ROOT)
        self.assertEqual(pages.parse_record(raw.encode(),validate,pages.MAX_KAFKA_BYTES,integer_lexemes=True),value)
        for invalid in (raw.replace('"lag": 0','"lag": 0.0'),raw.replace('"lag": 0','"lag": 0e0'),
                raw.replace('"partition": 0','"partition": -0')):
            with self.subTest(lexeme=invalid[-20:]):
                self.assertEqual(node(invalid),2)
                with self.assertRaises(pages.ObservationError):
                    pages.parse_record(invalid.encode(),validate,pages.MAX_KAFKA_BYTES,integer_lexemes=True)
        # A parsed Python float is reserialized with a decimal; the actual Pages
        # validator must use the strict source parser rather than object validation.
        with self.assertRaises(pages.ObservationError):validate({**value,'lag':0.0})

    def test_kafka_wire_and_artifact_ingress_require_strict_utf8_without_bom(self):
        value=kafka_record();text=json.dumps(value);raw=text.encode('utf-8')
        validate=lambda record:kafka_contract.validate_kafka_snapshot(record,NOW)
        manifest=json.dumps({'schemaVersion':1,'kind':'kafka-observation-publication','recordPresent':True}).encode('utf-8')
        def variants(content):
            text=content.decode('utf-8')
            return (b'\xef\xbb\xbf'+content,b'\xff'+content,text.encode('utf-16-le'),
                text.encode('utf-16-be'),text.encode('utf-32-le'),text.encode('utf-32-be'))
        def baseline(snapshot,publication):
            archive=io.BytesIO()
            with zipfile.ZipFile(archive,'w') as zipped:
                zipped.writestr('publication.json',publication);zipped.writestr('kafka.latest.json',snapshot)
            with zipfile.ZipFile(io.BytesIO(archive.getvalue())) as zipped:
                return pages.decode_kafka_archive(zipped,zipped.infolist(),validate)
        self.assertEqual(kafka_contract.parse_kafka_snapshot(raw,NOW),value)
        self.assertEqual(pages.parse_record(raw,validate,pages.MAX_KAFKA_BYTES,integer_lexemes=True),value)
        self.assertEqual(baseline(raw,manifest),value)
        for invalid in variants(raw):
            with self.subTest(path='record',prefix=invalid[:8]):
                with self.assertRaises(Exception):kafka_contract.parse_kafka_snapshot(invalid,NOW)
                with self.assertRaises(pages.ObservationError):
                    pages.parse_record(invalid,validate,pages.MAX_KAFKA_BYTES,integer_lexemes=True)
                with self.assertRaises(pages.ObservationError):baseline(invalid,manifest)
        for invalid in variants(manifest):
            with self.subTest(path='publication',prefix=invalid[:8]),self.assertRaises(pages.ObservationError):
                baseline(raw,invalid)

    def test_absence_creates_only_manifest_and_existing_success_is_retained_without_seed(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);out=root/'out';artifact=root/'artifact'
            pages.prepare_kafka_output(None,None,out,artifact,lambda unused:self.fail('fake record'))
            self.assertFalse((out/'kafka.latest.json').exists());self.assertEqual(json.loads((artifact/'publication.json').read_text())['recordPresent'],False)
            value=kafka_record();pages.prepare_kafka_output(value,None,out,artifact,lambda unused:None)
            self.assertEqual((out/'kafka.latest.json').read_bytes(),(artifact/'kafka.latest.json').read_bytes())
            self.assertEqual(json.loads((out/'kafka.latest.json').read_bytes()),value)
    def test_optional_parse_or_target_failure_retains_baseline_instead_of_blocking_other_records(self):
        baseline=kafka_record()
        validate=lambda value:kafka_contract.validate_kafka_snapshot(value,NOW)
        for incoming in (None,'{bad JSON',json.dumps({**baseline,'targetFingerprint':'c'*64}),
                json.dumps({**baseline,'environment':'ISOLATED_LAB','scope':'ISOLATED_KAFKA'}),
                '{"schemaVersion":1,"schemaVersion":1}'):
            with self.subTest(input_type=type(incoming).__name__):
                selected=pages.select_kafka_incoming(baseline,incoming,validate)
                self.assertIsNone(selected);self.assertEqual(pages.merge_kafka_records(baseline,selected),baseline)


@unittest.skipUnless(os.name=='posix','POSIX SIGALRM guard; Windows offline skip is explicit')
class CycleAlarmTests(unittest.TestCase):
    def test_real_short_owned_alarm_interrupts_and_restores_handler_in_child(self):
        code=("import sys,json,signal,time,subprocess;sys.path.insert(0,"+repr(str(Path(host_cycle.__file__).parent))+");import host_cycle\n"
            "old=signal.getsignal(signal.SIGALRM);caught=False\n"
            "try:\n with host_cycle.CycleDeadline(0.05):time.sleep(0.5)\n"
            "except subprocess.TimeoutExpired:caught=True\n"
            "assert caught and signal.getsignal(signal.SIGALRM)==old and signal.getitimer(signal.ITIMER_REAL)==(0.0,0.0)\n"
            "print(json.dumps({'shortAlarmObserved':True,'handlerAndTimerRestored':True}))\n")
        result=subprocess.run([sys.executable,'-I','-B','-c',code],capture_output=True,text=True,timeout=4)
        self.assertEqual(result.returncode,0);self.assertEqual(json.loads(result.stdout),{'shortAlarmObserved':True,'handlerAndTimerRestored':True})
    def test_existing_alarm_is_rejected_without_stealing_owner_state(self):
        import signal
        old=signal.getsignal(signal.SIGALRM)
        signal.setitimer(signal.ITIMER_REAL,1)
        try:
            with self.assertRaises(pages_uploader.AutomationError):
                with host_cycle.CycleDeadline(0.05):self.fail('existing timer stolen')
            self.assertEqual(signal.getsignal(signal.SIGALRM),old);self.assertGreater(signal.getitimer(signal.ITIMER_REAL)[0],0)
        finally:signal.setitimer(signal.ITIMER_REAL,0)


if __name__=='__main__':unittest.main()
