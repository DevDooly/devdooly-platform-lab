"""Offline synthetic tests: no GitHub, cluster, credentials or real observations."""
from copy import deepcopy
from datetime import datetime, timezone
import io
import json
import os
from pathlib import Path
import stat
import tempfile
import unittest
from unittest.mock import patch
from urllib.error import HTTPError

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'infra/observation'))
import platform_collector as collector
from platform_contract import InvalidObservation, validate_snapshot

NOW = '2026-10-12T00:00:00Z'
LATER = '2026-10-12T00:01:00Z'
MAIN = 'a' * 40
DEPLOYED = 'b' * 40
REVISION = 'c' * 40
CANARY = 'SYNTHETIC_PRIVATE_VALUE_MUST_NEVER_APPEAR'


def status(state='success', number=11, issuer='DevDooly'):
    return {'id':123,'context':'ci/jenkins-test','state':state,
            'creator':{'login':issuer,'email':CANARY},
            'description':f'Jenkins build #{number}: '+collector.DESCRIPTIONS[state],
            'created_at':'2026-10-11T23:59:00Z','target_url':CANARY}


def resource(kind, name, **fields):
    return {'apiVersion':'apps/v1','kind':kind,
            'metadata':{'namespace':'platform-lab','name':name,'private':CANARY},**fields}


class Sources:
    def __init__(self, statuses=None):
        self.statuses = [status()] if statuses is None else statuses
        self.github_calls=[]
        self.kube_calls=[]
        self.main_calls=0
        self.move_main=False
        self.failure_path=None
        self.failure_code='WORKLOADS_UNAVAILABLE'
        self.images={'api':'ghcr.io/devdooly/devdooly-platform-lab-api@sha256:'+'d'*64,
                     'web':'ghcr.io/devdooly/devdooly-platform-lab-web@sha256:'+'e'*64}
        self.argo_health='Healthy'
        self.ready=1
        self.pod_overrides={}

    def github(self, path, code):
        self.github_calls.append(path)
        if path.endswith('/git/ref/heads/main'):
            self.main_calls += 1
            sha='f'*40 if self.move_main and self.main_calls > 1 else MAIN
            return {'ref':'refs/heads/main','object':{'type':'commit','sha':sha},'internal':CANARY}
        if '/statuses?' in path:
            return deepcopy(self.statuses)
        if path=='/repos/'+collector.REPOSITORY:
            return {'full_name':collector.REPOSITORY,'private':False,'extra':CANARY}
        raise AssertionError('Unexpected synthetic GitHub route')

    def kube(self, path, code):
        self.kube_calls.append(path)
        if path==self.failure_path:
            raise collector.CollectionError(self.failure_code)
        if path==collector.ARGO:
            return {'kind':'Application','metadata':{'name':'platform-lab-home','namespace':'argocd'},
                    'status':{'sync':{'status':'Synced','revision':REVISION},
                              'health':{'status':self.argo_health},'private':CANARY}}
        if path.startswith(collector.PREFIX+'pods?'):
            items=[]
            for component in ('api','web','database'):
                pod={'metadata':{'namespace':'platform-lab','name':CANARY+'-'+component,
                    'labels':{'app.kubernetes.io/name':'platform-lab','app.kubernetes.io/instance':'lab',
                              'app.kubernetes.io/component':component}},
                    'spec':{'containers':[{'env':[{'name':'PRIVATE','value':CANARY}]}]},
                    'status':{'podIP':CANARY,'phase':'Running','conditions':[{'type':'Ready','status':'True' if self.ready else 'False'}],
                              'containerStatuses':[{'name':component,'ready':bool(self.ready)}]}}
                if component in self.pod_overrides:self.pod_overrides[component](pod)
                items.append(pod)
            return {'kind':'PodList','metadata':{},'items':items}
        if '/services/' in path:
            return resource('Service',path.rsplit('/',1)[1],spec={'type':'ClusterIP','clusterIP':CANARY})
        if '/statefulsets/' in path:
            return resource('StatefulSet','lab-platform-lab-db',spec={'replicas':1},status={'readyReplicas':self.ready})
        if '/deployments/' in path:
            component=path.rsplit('-',1)[1]
            return resource('Deployment','lab-platform-lab-'+component,spec={'replicas':1,'template':{
                'metadata':{'annotations':{'platform-lab.devdooly.dev/source-commit':DEPLOYED,'private':CANARY}},
                'spec':{'containers':[{'name':component,'image':self.images[component],'env':[{'name':'SECRET','value':CANARY}]}]}}},
                status={'readyReplicas':self.ready})
        raise AssertionError('Unexpected synthetic Kubernetes route')


def snapshot(sources=None, instant=NOW, previous=None):
    source=sources or Sources()
    return collector.collect_with_preservation(source.github,source.kube,instant,previous)


class CollectorTests(unittest.TestCase):
    def test_success_extracts_only_public_fields(self):
        value=snapshot()
        self.assertEqual(value['latestAttempt'],{'attemptedAt':NOW,'status':'success','errorCode':'NONE'})
        self.assertEqual(value['lastSuccess']['mainCommit'],MAIN)
        self.assertEqual(value['lastSuccess']['deploymentSourceCommit'],DEPLOYED)
        self.assertEqual(value['lastSuccess']['argo']['revision'],REVISION)
        self.assertNotIn(CANARY,json.dumps(value))

    def test_all_actual_jenkins_states_are_collection_success(self):
        for state in collector.DESCRIPTIONS:
            with self.subTest(state=state):
                value=snapshot(Sources([status(state)]))
                self.assertEqual(value['latestAttempt']['status'],'success')
                self.assertEqual(value['lastSuccess']['jenkins']['state'],state)

    def test_newest_failure_does_not_use_older_success(self):
        value=snapshot(Sources([status('failure',12),status('success',11)]))
        self.assertEqual(value['lastSuccess']['jenkins']['buildNumber'],12)
        self.assertEqual(value['lastSuccess']['jenkins']['state'],'failure')

    def test_wrong_latest_issuer_does_not_fall_back(self):
        value=snapshot(Sources([status('success',12,'Impersonator'),status('success',11)]))
        self.assertEqual(value['latestAttempt']['errorCode'],'INVALID_OBSERVATION')
        self.assertIsNone(value['lastSuccess'])

    def test_unknown_description_is_not_publicized(self):
        bad=status();bad['description']=CANARY
        value=snapshot(Sources([bad]))
        self.assertEqual(value['latestAttempt']['errorCode'],'INVALID_OBSERVATION')
        self.assertNotIn(CANARY,json.dumps(value))

    def test_no_current_main_status_is_not_reported(self):
        value=snapshot(Sources([]))
        self.assertEqual(value['latestAttempt']['status'],'success')
        self.assertEqual(value['lastSuccess']['mainCommit'],MAIN)
        self.assertIsNone(value['lastSuccess']['jenkins'])

    def test_bounded_status_search_does_not_invent_missing_result(self):
        sources=Sources([{'context':'unrelated'} for _ in range(100)])
        value=snapshot(sources)
        self.assertEqual(value['latestAttempt']['errorCode'],'GITHUB_STATUS_UNAVAILABLE')
        self.assertEqual(sum('/statuses?' in path for path in sources.github_calls),5)

    def test_status_page_two_is_used(self):
        sources=Sources()
        base=sources.github
        def get(path, code):
            if '/statuses?' in path and path.endswith('&page=1'):
                return [{'context':'unrelated'} for _ in range(100)]
            return base(path,code)
        value=collector.collect_with_preservation(get,sources.kube,NOW,None)
        self.assertEqual(value['lastSuccess']['jenkins']['buildNumber'],11)

    def test_main_movement_during_collection_is_rejected(self):
        sources=Sources();sources.move_main=True
        self.assertEqual(snapshot(sources)['latestAttempt']['errorCode'],'INVALID_OBSERVATION')

    def test_degraded_argo_and_zero_ready_are_observed(self):
        sources=Sources();sources.argo_health='Degraded';sources.ready=0
        value=snapshot(sources)
        self.assertEqual(value['latestAttempt']['status'],'success')
        self.assertEqual(value['lastSuccess']['argo']['health'],'Degraded')
        self.assertEqual([row['ready'] for row in value['lastSuccess']['workloads']],[0,0,0])

    def test_ready_counts_require_running_ready_containers_and_not_terminating(self):
        mutations=(lambda pod:pod['status'].update(phase='Pending'),
                   lambda pod:pod['metadata'].update(deletionTimestamp='2026-10-11T23:59:00Z'),
                   lambda pod:pod['status'].update(conditions=[{'type':'Ready','status':'False'}]),
                   lambda pod:pod['status'].update(containerStatuses=[{'name':'api','ready':False}]),
                   lambda pod:pod['status'].update(containerStatuses=[]))
        for mutate in mutations:
            with self.subTest(mutation=mutate):
                sources=Sources();sources.pod_overrides['api']=mutate
                value=snapshot(sources)
                api=value['lastSuccess']['workloads'][0]
                self.assertEqual(api['desired'],1)
                self.assertEqual(api['ready'],0)
                self.assertEqual(value['lastSuccess']['workloads'][1]['ready'],1)

    def test_ready_uses_pods_even_when_controller_reports_ready(self):
        sources=Sources();sources.pod_overrides['database']=lambda pod:pod['status'].update(phase='Failed')
        value=snapshot(sources)
        self.assertEqual(value['lastSuccess']['workloads'][2]['ready'],0)

    def test_pod_scope_and_list_truncation_are_rejected(self):
        for change in (lambda value:value['items'][0]['metadata'].update(namespace='other'),
                       lambda value:value['metadata'].update({'continue':'not-complete'}),
                       lambda value:value['items'][0]['metadata']['labels'].update({'app.kubernetes.io/instance':'other'})):
            with self.subTest(change=change):
                sources=Sources();base=sources.kube
                def get(path,code):
                    value=base(path,code)
                    if '/pods?' in path:change(value)
                    return value
                value=collector.collect_with_preservation(sources.github,get,NOW,None)
                self.assertEqual(value['latestAttempt']['errorCode'],'INVALID_OBSERVATION')

    def test_unapproved_image_is_rejected(self):
        sources=Sources();sources.images['web']='attacker.example/image@sha256:'+'e'*64
        self.assertEqual(snapshot(sources)['latestAttempt']['errorCode'],'INVALID_OBSERVATION')

    def test_service_nodeport_is_rejected(self):
        sources=Sources();base=sources.kube
        def get(path,code):
            value=base(path,code)
            if '/services/' in path:value['spec']['type']='NodePort'
            return value
        value=collector.collect_with_preservation(sources.github,get,NOW,None)
        self.assertEqual(value['latestAttempt']['errorCode'],'INVALID_OBSERVATION')

    def test_failed_sources_preserve_entire_previous_success(self):
        previous=snapshot()
        for code in ('GITHUB_STATUS_UNAVAILABLE','ARGO_UNAVAILABLE','WORKLOADS_UNAVAILABLE','AUTHENTICATION_FAILED','TIMEOUT','COLLECTION_FAILED'):
            with self.subTest(code=code):
                def failed(path,error_code):raise collector.CollectionError(code)
                value=collector.collect_with_preservation(failed,failed,LATER,previous)
                self.assertEqual(value['latestAttempt']['errorCode'],code)
                self.assertEqual(value['lastSuccess'],previous['lastSuccess'])
                self.assertIsNot(value['lastSuccess'],previous['lastSuccess'])

    def test_second_failure_keeps_original_success_capture_time(self):
        previous=snapshot();sources=Sources();sources.failure_path=collector.ARGO;sources.failure_code='ARGO_UNAVAILABLE'
        failure=snapshot(sources,LATER,previous)
        again=snapshot(sources,'2026-10-12T00:02:00Z',failure)
        self.assertEqual(again['lastSuccess']['capturedAt'],NOW)
        self.assertEqual(again['latestAttempt']['attemptedAt'],'2026-10-12T00:02:00Z')

    def test_error_detail_never_reaches_output(self):
        def failed(path,code):raise RuntimeError(CANARY)
        value=collector.collect_with_preservation(failed,failed,NOW,None)
        self.assertEqual(value['latestAttempt']['errorCode'],'COLLECTION_FAILED')
        self.assertNotIn(CANARY,json.dumps(value))

    def test_completion_timestamp_is_sampled_after_source_reads(self):
        moments=iter((NOW,NOW,LATER))
        sources=Sources()
        value=collector.collect_with_preservation(sources.github,sources.kube,lambda:next(moments),None)
        self.assertEqual(value['latestAttempt']['attemptedAt'],LATER)
        self.assertEqual(value['lastSuccess']['capturedAt'],LATER)

    def test_kubernetes_requests_are_only_named_reads_and_label_scoped_pods(self):
        sources=Sources();snapshot(sources)
        self.assertEqual(len(sources.kube_calls),8)
        self.assertEqual(sum('/pods?' in path for path in sources.kube_calls),1)
        self.assertTrue(all('/namespaces/platform-lab/' in path or path==collector.ARGO for path in sources.kube_calls))
        self.assertFalse(any(any(resource in path for resource in ('secrets','/log','/exec','nodes')) for path in sources.kube_calls))


class ContractTests(unittest.TestCase):
    def reject(self, mutate):
        value=snapshot();mutate(value)
        with self.assertRaises(InvalidObservation):validate_snapshot(value,datetime.fromisoformat(LATER.replace('Z','+00:00')))

    def test_unknown_fields_are_rejected_recursively(self):
        paths=((),('latestAttempt',),('lastSuccess',),('lastSuccess','jenkins'),('lastSuccess','argo'))
        for path in paths:
            with self.subTest(path=path):
                def mutate(value):
                    for key in path:value=value[key]
                    value['internalAddress']=CANARY
                self.reject(mutate)

    def test_future_attempt_and_capture_are_rejected(self):
        self.reject(lambda value:value['latestAttempt'].update(attemptedAt='2099-01-01T00:00:00Z'))
        self.reject(lambda value:value['lastSuccess'].update(capturedAt=LATER))

    def test_invalid_dates_and_offsets_are_rejected(self):
        for instant in ('2026-02-30T00:00:00Z','2026-10-12T00:00:00+00:00','2026-10-12T00:00:60Z'):
            with self.subTest(instant=instant):self.reject(lambda value:value['latestAttempt'].update(attemptedAt=instant))

    def test_created_at_cannot_be_after_capture(self):
        self.reject(lambda value:value['lastSuccess']['jenkins'].update(createdAt=LATER))

    def test_nanosecond_chronology_is_not_truncated_to_microseconds(self):
        value=snapshot()
        value['latestAttempt']['status']='failure';value['latestAttempt']['errorCode']='TIMEOUT'
        value['latestAttempt']['attemptedAt']='2026-10-12T00:00:00.000000001Z'
        value['lastSuccess']['capturedAt']='2026-10-12T00:00:00.000000002Z'
        with self.assertRaises(InvalidObservation):
            validate_snapshot(value,datetime.fromisoformat(LATER.replace('Z','+00:00')))
        value['lastSuccess']['capturedAt']='2026-10-12T00:00:00.000000001Z'
        value['lastSuccess']['jenkins']['createdAt']='2026-10-12T00:00:00.000000002Z'
        with self.assertRaises(InvalidObservation):
            validate_snapshot(value,datetime.fromisoformat(LATER.replace('Z','+00:00')))

    def test_year_zero_and_non_scalar_enums_are_rejected(self):
        self.reject(lambda value:value['latestAttempt'].update(attemptedAt='0000-01-01T00:00:00Z'))
        self.reject(lambda value:value['lastSuccess']['jenkins'].update(state=[]))

    def test_duplicate_workload_is_rejected(self):
        self.reject(lambda value:value['lastSuccess']['workloads'].__setitem__(2,deepcopy(value['lastSuccess']['workloads'][0])))

    def test_database_image_and_unknown_workload_fields_are_rejected(self):
        self.reject(lambda value:value['lastSuccess']['workloads'][2].update(image=CANARY))
        self.reject(lambda value:value['lastSuccess']['workloads'][0].update(host=CANARY))

    def test_boolean_counts_unsafe_ids_and_oversized_build_number_rejected(self):
        self.reject(lambda value:value['lastSuccess']['workloads'][0].update(ready=True))
        self.reject(lambda value:value['lastSuccess']['jenkins'].update(statusId=9007199254740992))
        self.reject(lambda value:value['lastSuccess']['jenkins'].update(buildNumber=2147483648))

    def test_jenkins_source_must_match_current_main(self):
        self.reject(lambda value:value['lastSuccess']['jenkins'].update(sourceCommit=DEPLOYED))

    def test_failure_none_code_and_success_without_snapshot_are_rejected(self):
        self.reject(lambda value:value['latestAttempt'].update(status='failure'))
        self.reject(lambda value:value.update(lastSuccess=None))


class FileAndTransportTests(unittest.TestCase):
    def test_atomic_replace_and_read_preserve_snapshot(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'snapshot.json';clock=datetime.fromisoformat(LATER.replace('Z','+00:00'))
            collector.atomic_save(path,snapshot(),clock)
            self.assertEqual(collector.read_previous(path,clock),snapshot())
            self.assertEqual(list(Path(directory).iterdir()),[path])

    @unittest.skipUnless(os.name=='posix','POSIX 0600 semantics require the Linux host')
    def test_atomic_output_permissions_are_0600(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'snapshot.json'
            collector.atomic_save(path,snapshot(),datetime.fromisoformat(NOW.replace('Z','+00:00')))
            self.assertEqual(stat.S_IMODE(path.stat().st_mode),0o600)

    def test_invalid_snapshot_does_not_replace_previous_file(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'snapshot.json';clock=datetime.fromisoformat(LATER.replace('Z','+00:00'))
            collector.atomic_save(path,snapshot(),clock);before=path.read_bytes()
            bad=snapshot();bad['private']=CANARY
            with self.assertRaises(InvalidObservation):collector.atomic_save(path,bad,clock)
            self.assertEqual(path.read_bytes(),before)

    def test_invalid_previous_input_stops_before_collection(self):
        previous=snapshot();previous['lastSuccess']['capturedAt']='2099-01-01T00:00:00Z'
        sources=Sources()
        with self.assertRaises(InvalidObservation):snapshot(sources,LATER,previous)
        self.assertEqual(sources.github_calls,[])

    def test_redirects_are_never_followed(self):
        self.assertIsNone(collector.NoRedirect().redirect_request(None,None,302,'',{},'https://attacker.example/'))

    def test_server_requires_https_private_address_and_no_credentials_or_query(self):
        self.assertEqual(collector.validate_server('https://127.0.0.1:6443/'),'https://127.0.0.1:6443')
        for server in ('http://127.0.0.1:6443','https://user:pass@127.0.0.1:6443','https://8.8.8.8','https://127.0.0.1?token=bad'):
            with self.subTest(server=server),self.assertRaises(collector.CollectionError):collector.validate_server(server)

    def test_transport_maps_forbidden_without_leaking_body(self):
        with tempfile.TemporaryDirectory() as directory:
            token=Path(directory)/'token';token.write_text('aaa.bbb.ccc')
            client=collector.JsonTransport('https://127.0.0.1:6443',collector.time.monotonic()+10,token_file=token)
            with patch.object(client.opener,'open',side_effect=HTTPError(CANARY,403,CANARY,{},io.BytesIO(CANARY.encode()))):
                with self.assertRaisesRegex(collector.CollectionError,'^AUTHENTICATION_FAILED$'):
                    client('/api/v1/namespaces/platform-lab/pods','WORKLOADS_UNAVAILABLE')

    def test_existing_writer_lock_prevents_network_and_output_changes(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'snapshot.json';path.write_bytes(b'preserve-me')
            (path.parent/('.'+path.name+'.lock')).write_text('')
            out=io.StringIO()
            with patch.object(collector,'JsonTransport') as transport,patch('sys.stdout',out):
                code=collector.main(['--server','https://127.0.0.1:6443','--token-file',str(path),
                    '--ca-file',str(path),'--output',str(path)])
            self.assertEqual(code,1);transport.assert_not_called();self.assertEqual(path.read_bytes(),b'preserve-me')
            self.assertNotIn(str(path),out.getvalue())

    def test_invalid_ca_records_failed_attempt_and_preserves_previous_success(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'snapshot.json'
            old=status();old['created_at']='2000-01-01T00:00:00Z'
            previous=snapshot(Sources([old]),'2000-01-02T00:00:00Z')
            path.write_text(json.dumps(previous))
            out=io.StringIO()
            with patch('sys.stdout',out):
                result=collector.main(['--server','https://127.0.0.1:6443','--token-file',str(Path(directory)/'token'),
                    '--ca-file',str(Path(directory)/'missing-ca'), '--output',str(path)])
            self.assertEqual(result,1)
            value=json.loads(path.read_text())
            self.assertEqual(value['latestAttempt']['errorCode'],'AUTHENTICATION_FAILED')
            self.assertEqual(value['lastSuccess'],previous['lastSuccess'])
            self.assertNotIn(str(directory),out.getvalue())

    def test_failed_atomic_replace_retains_previous_bytes_and_cleans_temp(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'snapshot.json';path.write_bytes(b'previous-safe-file')
            with patch.object(collector.os,'replace',side_effect=OSError(CANARY)):
                with self.assertRaises(OSError):
                    collector.atomic_save(path,snapshot(),datetime.fromisoformat(NOW.replace('Z','+00:00')))
            self.assertEqual(path.read_bytes(),b'previous-safe-file')
            self.assertEqual(list(Path(directory).iterdir()),[path])


if __name__=='__main__':unittest.main()
