"""Offline tests with synthetic snapshots/credentials, no actual dispatch."""
from copy import deepcopy
from datetime import datetime,timezone
import io
import json
import os
from pathlib import Path
import subprocess
import stat
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from urllib.error import HTTPError

HERE=Path(__file__).resolve().parent
for candidate in (HERE.parent/'public-phase3-collector',HERE.parents[1]/'infra/observation'):
    if (candidate/'platform_contract.py').exists():sys.path.insert(0,str(candidate));break

import host_cycle
import pages_uploader as uploader

NOW=datetime(2000,1,2,tzinfo=timezone.utc)
TOKEN='github_pat_'+'SYNTHETIC_CREDENTIAL_'*3
CANARY='SYNTHETIC_PRIVATE_RESPONSE_MUST_NOT_LEAK'


def snapshot(captured='2000-01-01T00:00:00Z'):
    return {'schemaVersion':1,'kind':'platform-observation',
        'latestAttempt':{'attemptedAt':captured,'status':'success','errorCode':'NONE'},
        'lastSuccess':{'capturedAt':captured,'collectorVersion':'1','mainCommit':'a'*40,'jenkins':None,
            'argo':{'revision':'c'*40,'sync':'Synced','health':'Healthy'},'deploymentSourceCommit':'b'*40,
            'workloads':[{'component':'api','desired':1,'ready':1,'image':'ghcr.io/devdooly/devdooly-platform-lab-api@sha256:'+'d'*64},
                         {'component':'web','desired':1,'ready':1,'image':'ghcr.io/devdooly/devdooly-platform-lab-web@sha256:'+'e'*64},
                         {'component':'database','desired':1,'ready':1}]}}


def response(run_id=123):
    return 200,json.dumps({'workflow_run_id':run_id,
        'html_url':f'https://github.com/{uploader.REPOSITORY}/actions/runs/{run_id}',
        'run_url':f'https://api.github.com/repos/{uploader.REPOSITORY}/actions/runs/{run_id}'}).encode()


class Files(unittest.TestCase):
    def setUp(self):
        # Pure cycle fixtures intentionally live under the OS temporary dir.
        # Production rejects its writable ancestors; PathPolicyTests exercise
        # that policy independently using synthetic lstat records.
        if os.name=='posix':
            for module in (uploader,host_cycle):
                guard=patch.object(module,'path_chain');guard.start();self.addCleanup(guard.stop)
            reader=patch.object(uploader,'credential_bytes',side_effect=lambda path,owner:path.read_bytes()[:257])
            reader.start();self.addCleanup(reader.stop)
            owner=patch.object(uploader,'root_owned',return_value=True)
            owner.start();self.addCleanup(owner.stop)
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
        self.token=self.root/'.config/devdooly-platform-lab/github-pages.token'
        self.token.parent.mkdir(parents=True);self.token.write_text(TOKEN);os.chmod(self.token,0o600)
        self.journal=self.root/'dispatch.json'
    def tearDown(self):self.temp.cleanup()


class UploadTests(Files):
    def test_request_uses_only_fixed_endpoint_main_one_allowlisted_input(self):
        requests=[]
        def sender(request):requests.append(request);return response()
        value=uploader.dispatch(snapshot(),self.token,self.journal,sender=sender,now=NOW)
        self.assertEqual(value,uploader.public_report('DISPATCHED',123))
        self.assertEqual(len(requests),1)
        request=requests[0];body=json.loads(request.data)
        self.assertEqual(request.full_url,uploader.ENDPOINT);self.assertEqual(request.method,'POST')
        self.assertEqual(body['ref'],'main');self.assertEqual(set(body['inputs']),{'platform_snapshot'})
        self.assertEqual(json.loads(body['inputs']['platform_snapshot']),snapshot())
        self.assertEqual(set(body),{'ref','inputs'})
        self.assertEqual(request.get_header('X-github-api-version'),'2026-03-10')
        self.assertNotIn(TOKEN,self.journal.read_text());self.assertNotIn(TOKEN,json.dumps(value))

    def test_intent_is_durable_before_post(self):
        def sender(request):
            recorded=json.loads(self.journal.read_text())
            self.assertEqual(recorded['attemptStatus'],'DISPATCH_INTENT_RECORDED')
            self.assertNotIn('Authorization',self.journal.read_text())
            return response()
        uploader.dispatch(snapshot(),self.token,self.journal,sender=sender,now=NOW)

    def test_timeout_is_ambiguous_and_same_intent_never_retries(self):
        calls=[]
        def sender(request):calls.append(1);raise uploader.AutomationError('DISPATCH_AMBIGUOUS')
        first=uploader.dispatch(snapshot(),self.token,self.journal,sender=sender,now=NOW)
        second=uploader.dispatch(snapshot(),self.token,self.journal,sender=sender,now=NOW)
        self.assertEqual(first['attemptStatus'],'DISPATCH_AMBIGUOUS')
        self.assertEqual(second['attemptStatus'],'SAME_ATTEMPT_NOT_RETRIED');self.assertEqual(len(calls),1)

    def test_next_cycle_can_send_newest_attempt_after_ambiguity(self):
        def failed(request):raise uploader.AutomationError('DISPATCH_AMBIGUOUS')
        uploader.dispatch(snapshot(),self.token,self.journal,sender=failed,now=NOW)
        value=uploader.dispatch(snapshot('2000-01-01T00:01:00Z'),self.token,self.journal,sender=lambda request:response(124),now=NOW)
        self.assertEqual(value,uploader.public_report('DISPATCHED',124))

    def test_success_is_not_resent(self):
        uploader.dispatch(snapshot(),self.token,self.journal,sender=lambda request:response(),now=NOW)
        def forbidden(request):raise AssertionError('must not send again')
        self.assertEqual(uploader.dispatch(snapshot(),self.token,self.journal,sender=forbidden,now=NOW)['attemptStatus'],'SAME_ATTEMPT_NOT_RETRIED')

    def test_key_order_only_change_cannot_retry_last_intent(self):
        uploader.dispatch(snapshot(),self.token,self.journal,sender=lambda request:response(),now=NOW)
        value=dict(reversed(list(snapshot().items())))
        value['lastSuccess']=dict(reversed(list(value['lastSuccess'].items())))
        self.assertEqual(uploader.dispatch(value,self.token,self.journal,
            sender=lambda request:self.fail('must not resend'),now=NOW)['attemptStatus'],'SAME_ATTEMPT_NOT_RETRIED')

    def test_invalid_snapshot_does_not_send_or_record_intent(self):
        bad=snapshot();bad['private']=CANARY
        with self.assertRaises(uploader.AutomationError):
            uploader.dispatch(bad,self.token,self.journal,sender=lambda request:self.fail('must not send'),now=NOW)
        self.assertFalse(self.journal.exists())

    def test_malformed_response_or_other_repo_url_is_ambiguous(self):
        for data in (b'{invalid',json.dumps({'workflow_run_id':123,'html_url':'https://attacker.invalid/','run_url':CANARY}).encode()):
            with self.subTest(data=data):
                if self.journal.exists():self.journal.unlink()
                value=uploader.dispatch(snapshot(),self.token,self.journal,sender=lambda request:(200,data),now=NOW)
                self.assertEqual(value['attemptStatus'],'DISPATCH_AMBIGUOUS')
                self.assertNotIn(CANARY,self.journal.read_text())

    def test_204_without_run_details_is_not_assumed_verified(self):
        value=uploader.dispatch(snapshot(),self.token,self.journal,sender=lambda request:(204,b''),now=NOW)
        self.assertEqual(value['attemptStatus'],'DISPATCH_AMBIGUOUS')

    def test_failure_envelope_is_publishable_without_erasing_last_success(self):
        value=snapshot();value['latestAttempt']={'attemptedAt':'2000-01-01T00:01:00Z','status':'failure','errorCode':'AUTHENTICATION_FAILED'}
        def sender(request):
            posted=json.loads(json.loads(request.data)['inputs']['platform_snapshot'])
            self.assertEqual(posted['lastSuccess'],snapshot()['lastSuccess'])
            return response()
        self.assertEqual(uploader.dispatch(value,self.token,self.journal,sender=sender,now=NOW)['attemptStatus'],'DISPATCHED')

    def test_dedicated_path_and_fine_grained_token_required(self):
        wrong=self.root/'github-status.token';wrong.write_text(TOKEN)
        with self.assertRaises(uploader.AutomationError):uploader.read_pages_token(wrong)
        self.token.write_text('ghp_'+'x'*40)
        with self.assertRaises(uploader.AutomationError):uploader.read_pages_token(self.token)

    def test_dispatch_os_lock_prevents_parallel_request(self):
        with uploader.DispatchLock(self.journal.with_name(self.journal.name+'.lock')):
            with self.assertRaises(uploader.AutomationError):
                uploader.dispatch(snapshot(),self.token,self.journal,sender=lambda request:self.fail('must not send'),now=NOW)

    def test_redirect_is_disabled(self):
        self.assertIsNone(uploader.NoRedirect().redirect_request(None,None,302,'',{},'https://attacker.invalid/'))

    def test_http_rejection_never_prints_or_persists_response(self):
        fake=SimpleNamespace(open=lambda *args,**kwargs:(_ for _ in ()).throw(HTTPError(CANARY,403,CANARY,{},io.BytesIO(CANARY.encode()))))
        with patch.object(uploader,'build_opener',return_value=fake):
            with self.assertRaisesRegex(uploader.AutomationError,'^DISPATCH_REJECTED$'):
                uploader.send_once(SimpleNamespace())

    @unittest.skipUnless(os.name=='posix','POSIX credential permission enforcement requires Linux')
    def test_world_readable_token_is_rejected(self):
        os.chmod(self.token,0o644)
        with self.assertRaises(uploader.AutomationError):uploader.read_pages_token(self.token)

    def test_public_report_has_exactly_three_safe_fields(self):
        self.assertEqual(set(uploader.public_report('DISPATCH_AMBIGUOUS')),{'attemptStatus','runId','runUrl'})


class NoLock:
    def __init__(self,*unused):pass
    def __enter__(self):return self
    def __exit__(self,*unused):pass


class PathPolicyTests(unittest.TestCase):
    """Ownership tests use synthetic metadata; no privileged OS claims."""
    def setUp(self):
        self.path=HERE/'synthetic-root-tree'/'secret.json'

    def check(self, *, bad_parent=None, leaf=None, allowed=frozenset({0}), missing=False):
        def metadata(component):
            final=component==self.path
            if final and missing:raise FileNotFoundError
            mode=stat.S_IFREG|0o600 if final else stat.S_IFDIR|0o755
            uid=0
            if final and leaf:mode,uid=leaf
            if component==self.path.parent and bad_parent:mode,uid=bad_parent
            return SimpleNamespace(st_mode=mode,st_uid=uid,st_nlink=1)
        with patch.object(Path,'lstat',autospec=True,side_effect=metadata),patch.object(uploader.os,'name','posix'):
            uploader.path_chain(self.path,owner_uids=allowed,leaf_kind='file',allow_missing_leaf=missing)

    def test_root_controlled_chain_is_accepted(self):self.check()

    def test_posix_root_owned_leaf_requires_uid_zero(self):
        with patch.object(uploader.os,'name','posix'):
            self.assertTrue(uploader.root_owned(SimpleNamespace(st_uid=0)))
            self.assertFalse(uploader.root_owned(SimpleNamespace(st_uid=1000)))

    def test_private_directory_accepts_only_root_owned_0700_directory(self):
        metadata=SimpleNamespace(st_mode=stat.S_IFDIR|0o700,st_uid=0)
        with patch.object(host_cycle,'path_chain') as chain,patch.object(Path,'mkdir') as mkdir,\
                patch.object(Path,'lstat',return_value=metadata),patch.object(host_cycle.os,'name','posix'):
            host_cycle.private_directory(self.path)
        chain.assert_called_once_with(self.path,leaf_kind='directory',allow_missing_leaf=True)
        mkdir.assert_called_once_with(mode=0o700,exist_ok=True)

    def test_private_directory_rejects_nonroot_modes_and_other_file_kinds(self):
        cases=((stat.S_IFDIR|0o700,1000),(stat.S_IFDIR|0o755,0),
               (stat.S_IFREG|0o700,0),(stat.S_IFLNK|0o700,0))
        for mode,uid in cases:
            with self.subTest(mode=mode,uid=uid),patch.object(host_cycle,'path_chain'),\
                    patch.object(Path,'mkdir'),patch.object(Path,'lstat',
                        return_value=SimpleNamespace(st_mode=mode,st_uid=uid)),\
                    patch.object(host_cycle.os,'name','posix'),\
                    self.assertRaisesRegex(uploader.AutomationError,'^PRIVATE_DIRECTORY_INVALID$'):
                host_cycle.private_directory(self.path)

    def test_root_leaf_below_user_owned_parent_is_rejected(self):
        with self.assertRaisesRegex(uploader.AutomationError,'^PATH_UNTRUSTED$'):
            self.check(bad_parent=(stat.S_IFDIR|0o700,1000))

    def test_root_owned_writable_parent_is_rejected(self):
        for mode in (0o775,0o777):
            with self.subTest(mode=mode),self.assertRaises(uploader.AutomationError):
                self.check(bad_parent=(stat.S_IFDIR|mode,0))

    def test_parent_symlink_is_rejected(self):
        with self.assertRaises(uploader.AutomationError):self.check(bad_parent=(stat.S_IFLNK|0o777,0))

    def test_leaf_symlink_is_rejected(self):
        with self.assertRaises(uploader.AutomationError):self.check(leaf=(stat.S_IFLNK|0o777,0))

    def test_credential_owner_chain_is_only_allowed_explicitly(self):
        self.check(bad_parent=(stat.S_IFDIR|0o700,1000),leaf=(stat.S_IFREG|0o600,1000),allowed={0,1000})
        with self.assertRaises(uploader.AutomationError):
            self.check(bad_parent=(stat.S_IFDIR|0o700,1001),allowed={0,1000})

    def test_new_leaf_still_requires_trusted_parent(self):
        self.check(missing=True)
        with self.assertRaises(uploader.AutomationError):
            self.check(missing=True,bad_parent=(stat.S_IFDIR|0o777,0))

    def test_relative_path_is_rejected(self):
        with self.assertRaises(uploader.AutomationError):uploader.path_chain(Path('relative.json'))

    def test_only_literal_loopback_https_server_with_port_is_allowed(self):
        for server in ('https://127.0.0.1:6443','https://[::1]:6443/'):
            host_cycle.loopback_server(server)
        for server in ('http://127.0.0.1:6443','https://192.0.2.1:6443','https://localhost:6443',
                'https://user:password@127.0.0.1:6443','https://127.0.0.1:6443/path',
                'https://127.0.0.1:6443?query=1','https://127.0.0.1','https://127.0.0.1:6443#fragment'):
            with self.subTest(server=server),self.assertRaisesRegex(uploader.AutomationError,'^CONFIG_INVALID$'):
                host_cycle.loopback_server(server)

    def test_credential_read_holds_parent_descriptors_and_never_follows_symlinks(self):
        # POSIX open behavior is exercised without trusting the test host's
        # temporary directory ownership or requiring a real credential.
        path=Path('/home/operator/.config/devdooly-platform-lab/github-pages.token')
        calls=[]
        def opened(name,flags,**kwargs):
            calls.append((name,flags,kwargs));return len(calls)+10
        def metadata(descriptor):
            final=len(calls)==len(path.parts)
            return SimpleNamespace(st_mode=(stat.S_IFREG|0o600) if final else (stat.S_IFDIR|0o700),
                st_uid=1000 if final else 0,st_nlink=1)
        with patch.object(uploader.os,'name','posix'),patch.object(uploader.os,'O_DIRECTORY',0x10000,create=True),\
                patch.object(uploader.os,'O_NOFOLLOW',0x20000,create=True),patch.object(uploader.os,'O_CLOEXEC',0x40000,create=True),\
                patch.object(uploader.os,'open',side_effect=opened),patch.object(uploader.os,'fstat',side_effect=metadata),\
                patch.object(uploader.os,'close') as closed,patch.object(uploader.os,'read',return_value=TOKEN.encode()):
            self.assertEqual(uploader.credential_bytes(path,1000),TOKEN.encode())
        self.assertEqual(len(calls),len(path.parts))
        self.assertTrue(all(flags&0x20000 for _,flags,_ in calls))
        self.assertTrue(all('dir_fd' in kwargs for _,_,kwargs in calls[1:]))
        self.assertEqual(closed.call_count,len(calls))


class CycleTests(Files):
    def setUp(self):
        super().setUp()
        # This suite tests cycle decisions/cleanup with synthetic resources,
        # including on nonroot CI runners. Production ownership enforcement
        # remains intact and is exercised separately in PathPolicyTests.
        def fixture_directory(path):
            self.assertIn(self.root,path.parents)
            path.mkdir(mode=0o700,exist_ok=True)
            os.chmod(path,0o700)
        guard=patch.object(host_cycle,'private_directory',side_effect=fixture_directory)
        guard.start();self.addCleanup(guard.stop)

    def config(self):
        return {'k3s_path':'/PRIVATE/k3s','kubeconfig':'/PRIVATE/admin-config',
            'server':'https://127.0.0.1:6443','ca_file':'/PRIVATE/server-ca',
            'collector_path':'/PRIVATE/platform_collector.py','state_directory':str(self.root/'state'),
            'runtime_directory':str(self.root/'runtime'),'pages_token_file':str(self.token)}

    def runner(self, config, *, fail_capture=False, stale=False, timeout=False):
        calls=[]
        def invoke(arguments,**kwargs):
            calls.append((arguments,kwargs))
            self.assertNotIn(TOKEN,json.dumps(arguments));self.assertNotIn(TOKEN,json.dumps(kwargs['env']))
            self.assertFalse(kwargs.get('shell',False))
            if len(calls)==1:return SimpleNamespace(returncode=0,stdout=b'aaa.bbb.ccc\n')
            if timeout:raise subprocess.TimeoutExpired(arguments,80,stderr=CANARY)
            token_path=Path(arguments[arguments.index('--token-file')+1])
            self.assertEqual(token_path.read_bytes(),b'aaa.bbb.ccc')
            output=Path(arguments[arguments.index('--output')+1])
            instant='2000-01-01T00:00:00Z' if stale else datetime.now(timezone.utc).isoformat().replace('+00:00','Z')
            value=snapshot(instant)
            if fail_capture:
                value['latestAttempt']['status']='failure';value['latestAttempt']['errorCode']='AUTHENTICATION_FAILED'
                value['lastSuccess']=snapshot()['lastSuccess']
            output.write_text(json.dumps(value));os.chmod(output,0o600)
            return SimpleNamespace(returncode=1 if fail_capture else 0,stdout=b'')
        return invoke,calls

    def test_fresh_sa_token_collection_dispatch_and_cleanup(self):
        config=self.config();runner,calls=self.runner(config);posted=[]
        def publish(value,token,journal):posted.append(value);return uploader.public_report('DISPATCHED',123)
        value=host_cycle.run_cycle(config,runner=runner,uploader=publish,lock_class=NoLock)
        self.assertEqual(value['attemptStatus'],'DISPATCHED');self.assertEqual(len(calls),2)
        self.assertEqual(calls[0][0][-1],'--duration=10m')
        self.assertIn('--kubeconfig',calls[0][0]);self.assertNotIn('--kubeconfig',calls[1][0])
        self.assertEqual(list(Path(config['runtime_directory']).iterdir()),[])
        self.assertEqual(len(posted),1)

    def test_collection_auth_failure_envelope_is_sent_honestly(self):
        config=self.config();runner,_=self.runner(config,fail_capture=True)
        def publish(value,*unused):
            self.assertEqual(value['latestAttempt']['errorCode'],'AUTHENTICATION_FAILED')
            self.assertEqual(value['lastSuccess'],snapshot()['lastSuccess'])
            return uploader.public_report('DISPATCHED',123)
        self.assertEqual(host_cycle.run_cycle(config,runner=runner,uploader=publish,lock_class=NoLock)['attemptStatus'],'DISPATCHED')

    def test_timeout_removes_short_lived_token_without_dispatch(self):
        config=self.config();runner,_=self.runner(config,timeout=True)
        value=host_cycle.run_cycle(config,runner=runner,uploader=lambda *args:self.fail('must not publish'),lock_class=NoLock)
        self.assertEqual(value['attemptStatus'],'CAPTURE_TIMEOUT')
        self.assertEqual(list(Path(config['runtime_directory']).iterdir()),[])

    def test_failed_capture_cannot_resend_stale_output(self):
        config=self.config();runner,_=self.runner(config,stale=True)
        value=host_cycle.run_cycle(config,runner=runner,uploader=lambda *args:self.fail('must not publish'),lock_class=NoLock)
        self.assertEqual(value['attemptStatus'],'CAPTURE_FAILED')

    def test_issuer_failure_does_not_fall_back_to_admin_collection(self):
        config=self.config();calls=[]
        def runner(arguments,**kwargs):calls.append(arguments);return SimpleNamespace(returncode=1,stdout=CANARY.encode())
        value=host_cycle.run_cycle(config,runner=runner,uploader=lambda *args:self.fail('must not publish'),lock_class=NoLock)
        self.assertEqual(value['attemptStatus'],'SA_TOKEN_UNAVAILABLE');self.assertEqual(len(calls),1)

    def test_service_templates_never_restart_k3s_or_application(self):
        service=(Path(host_cycle.__file__).parent/'platform-observation.service').read_text()
        self.assertIn('Type=oneshot',service);self.assertIn('ProtectSystem=strict',service)
        self.assertNotIn('ExecStartPost=',service);self.assertNotIn('[Install]',service.split('#')[0])
        self.assertNotIn('Restart=',service)


if __name__=='__main__':unittest.main()
