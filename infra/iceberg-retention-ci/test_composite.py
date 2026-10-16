"""Synthetic source contracts only; no Docker, Cloud, SQL or copied warehouse."""
from contextlib import contextmanager
import ast
import copy
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import time
import types
import unittest
from unittest import mock

import composite_entry as entry
import decoder_lifecycle as dec
import lifecycle as life

SOURCE = 'a' * 40
CID = 'b' * 64
root = Path(os.environ.get('PLATFORM_LAB_SOURCE_ROOT', str(Path(__file__).resolve().parents[2])))


class Clock:
    def __init__(self): self.started = time.monotonic() - 1; self.now = time.monotonic
    def remaining(self, maximum, reserve=0):
        left = 600 - (self.now() - self.started) - reserve
        life.require(left > 0, 'SINGLE_WORKLOAD_DEADLINE_NO_RESET')
        return min(maximum, left)


def prepared(folder):
    return {'imageId': 'sha256:' + 'c'*64, 'classes': folder/'classes', 'iceberg': folder/'iceberg.jar',
        'proofSha256': 'd'*64, 'decoderSourceSha256': 'e'*64, 'sourceCommit': SOURCE,
        'imageEnvSha256': life.sha(life.encoded(['PATH=/verified-only']))}


def owned_decoder(folder):
    # Execute only two pinned pure canonical functions, never producer main/imports.
    raw=(root/'infra/cloud-lakehouse-ci/run_trial9.py').read_bytes()
    assert life.sha(raw)==life.PRODUCER
    nodes=[node for node in ast.parse(raw).body if isinstance(node,ast.FunctionDef)
        and node.name in ('canonical_host','canonical_mounts')]
    assert len(nodes)==2
    scope={'json':json,'require':life.require}
    exec(compile(ast.Module(body=nodes,type_ignores=[]),'<pinned-pure-canonical-functions>','exec'),scope)
    return dec.Decoder(prepared(folder),folder/'out','cloud-trial9-'+'1'*32,time.monotonic(),
        canonical_host=scope['canonical_host'],canonical_mounts=scope['canonical_mounts'])


def inspect_fixture(decoder):
    return {'Id': CID, 'Name': '/'+decoder.name, 'Image': decoder.prepared['imageId'], 'Created': 'synthetic',
        'Config': {'Image': dec.SPARK, 'Labels': decoder.labels, 'Entrypoint': ['java'],
            'Cmd': decoder.java_args, 'User': '185:185', 'Env': ['PATH=/verified-only']},
        'HostConfig': {'ReadonlyRootfs': True, 'Privileged': False, 'NetworkMode': 'none',
            'PortBindings': None, 'NanoCpus': 1000000000, 'Memory': 512*1024**2,
            'MemorySwap': 512*1024**2, 'PidsLimit': 64, 'RestartPolicy': {'Name': 'no'},
            'CapDrop': ['ALL'], 'SecurityOpt': ['no-new-privileges:true'], 'AutoRemove': False,'OomKillDisable':None},
        'NetworkSettings': {'Networks': {'none': {}}}, 'RestartCount': 0,
        'Mounts': [{'Source': str(decoder.prepared['classes']), 'Destination': '/opt/decoder/classes',
            'Type': 'bind', 'RW': False}, {'Source': str(decoder.prepared['iceberg']),
            'Destination': '/opt/decoder/iceberg-runtime.jar', 'Type': 'bind', 'RW': False}],
        'State': {'Running': False, 'Pid': 0, 'ExitCode': 0, 'OOMKilled': False,
            'StartedAt': '0001-01-01T00:00:00Z'}}


class FocusedGuards(unittest.TestCase):
    def test_stable_proof_rejects_links_duplicates_nonfinite_and_clock_callable_drift(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp); path=root/'proof'; path.write_bytes(b'{"a":1}')
            self.assertEqual(life.read_proof(path)['sha256'], hashlib.sha256(path.read_bytes()).hexdigest())
            for raw in (b'{"a":1,"a":2}', b'{"a":NaN}', b'{"a":1e9999}'):
                with self.assertRaises(ValueError): life.strict(raw)
            linked=root/'linked'; os.link(path, linked)
            with self.assertRaises(ValueError): life.read_proof(path)
            clock=Clock(); seen=types.SimpleNamespace(attempt=types.SimpleNamespace(deadline=clock),
                deadline=clock,deadline_started=clock.started,deadline_now=clock.now)
            self.assertGreater(life.remaining(types.SimpleNamespace(Deadline=Clock),seen),0)
            clock.now=lambda:clock.started
            with self.assertRaises(ValueError): life.remaining(types.SimpleNamespace(Deadline=Clock),seen)

    def test_missing_original_role_cannot_become_all_stopped_and_never_calls_stop(self):
        clock=Clock(); role_calls=mock.Mock(return_value=[])
        class Attempt:
            def command(self,*args,**kwargs):raise AssertionError('No command expected in synthetic empty-list test')
        attempt=Attempt();attempt.deadline=clock
        attempt.bound={role:{'id':str(i)*64} for i,role in enumerate(sorted(life.ROLES),1)}
        attempt.started_roles=set(life.ROLES);attempt.containers=role_calls
        attempt.project='cloud-trial9-'+'1'*32;attempt.initializer_name=attempt.project+'-volume-init'
        seen=types.SimpleNamespace(attempt=attempt,deadline=clock,deadline_started=clock.started,deadline_now=clock.now)
        with self.assertRaisesRegex(ValueError,'ALL_FIVE_EXACT_OWN_ROLES_MUST_EXIST'):
            life.stopped_snapshot(types.SimpleNamespace(Deadline=Clock),seen,{},'synthetic', 'f'*64)
        role_calls.assert_called_once_with()

    def test_each_original_read_timeout_uses_remaining_absolute_clock_and_restores_after_failure(self):
        now=[697.0]; calls=[]
        class Attempt:
            def command(self,args,timeout=60,sensitive=False,check=True):
                calls.append((args,timeout,sensitive,check))
                if len(calls)==2:raise subprocess.TimeoutExpired(args,timeout)
                now[0]+=2
                return types.SimpleNamespace(returncode=0,stdout=b'')
        with mock.patch.object(life.time,'monotonic',side_effect=lambda:now[0]) as monotonic:
            clock=Clock();clock.started=100;clock.now=monotonic
            attempt=Attempt();attempt.deadline=clock;attempt.project='cloud-trial9-'+'1'*32
            attempt.initializer_name=attempt.project+'-volume-init';attempt.bound={'spark':{'id':CID}}
            seen=types.SimpleNamespace(attempt=attempt,deadline=clock,deadline_started=100,deadline_now=monotonic)
            original=attempt.command
            with self.assertRaises(subprocess.TimeoutExpired):
                with life.clamped_original_reads(types.SimpleNamespace(Deadline=Clock),seen,0):
                    attempt.command(['docker','inspect',CID],sensitive=True)
                    attempt.command(['docker','inspect',CID],sensitive=True,check=False)
            self.assertNotIn('command',attempt.__dict__)
            self.assertIs(attempt.command.__func__,original.__func__)
            self.assertEqual([row[1] for row in calls],[3,1])
            self.assertEqual([(row[2],row[3]) for row in calls],[(True,True),(True,False)])
            with self.assertRaisesRegex(ValueError,'ONLY_ORIGINAL_FIXED_FULLSPEC_READ_COMMANDS'):
                with life.clamped_original_reads(types.SimpleNamespace(Deadline=Clock),seen,0):
                    attempt.command(['docker','stop',CID])
            self.assertEqual(len(calls),2);self.assertNotIn('command',attempt.__dict__)

    def test_decoder_prestart_full_identity_and_env_network_mount_limit_drift(self):
        with tempfile.TemporaryDirectory() as temp:
            folder=Path(temp); owned=owned_decoder(folder)
            owned.cid=CID; owned.java_args=['synthetic-fixed-java-args']; raw=inspect_fixture(owned)
            with mock.patch.object(dec,'command',return_value=types.SimpleNamespace(stdout=life.encoded([raw]))):
                self.assertFalse(owned.inspect()['Running'])
            equivalent=copy.deepcopy(raw);equivalent['HostConfig']['OomKillDisable']=False;equivalent['Mounts'].reverse()
            with mock.patch.object(dec,'command',return_value=types.SimpleNamespace(stdout=life.encoded([equivalent]))):
                self.assertFalse(owned.inspect()['Running'])
            for field in ('env','network','mount','limit','cid'):
                changed=copy.deepcopy(raw)
                if field=='env':changed['Config']['Env'].append('JAVA_TOOL_OPTIONS=private-not-serialized')
                elif field=='network':changed['HostConfig']['NetworkMode']='host'
                elif field=='mount':changed['Mounts'][0]['RW']=True
                elif field=='limit':changed['HostConfig']['PidsLimit']=True
                else:changed['Id']='f'*64
                with self.subTest(field=field), mock.patch.object(dec,'command',return_value=types.SimpleNamespace(stdout=life.encoded([changed]))):
                    with self.assertRaises(ValueError):owned.inspect()

    def test_decoder_cleanup_stops_only_exact_new_cid_waits_and_reaps_not_just_cli(self):
        with tempfile.TemporaryDirectory() as temp:
            folder=Path(temp); owned=owned_decoder(folder)
            owned.cid=CID; owned.process=mock.Mock(); owned.process.poll.side_effect=[None,0]
            states=[{'Running':True},{'Running':True},{'Running':False,'Pid':0,'ExitCode':137}]
            calls=[]
            def control(args,*unused,**kwargs):
                calls.append(args)
                return types.SimpleNamespace(stdout=b'137\n',returncode=0)
            with mock.patch.object(owned,'inspect',side_effect=states),mock.patch.object(dec,'command',side_effect=control):
                final=owned.cleanup(); self.assertEqual(final['ExitCode'],137)
                self.assertIs(owned.cleanup(),final)
            self.assertTrue(owned.stopped);self.assertTrue(owned.cli_reaped)
            self.assertEqual(calls,[['stop','--time=2',CID],['kill','--signal=KILL',CID],['wait',CID]])
            owned.process.kill.assert_called_once();owned.process.wait.assert_called_once()

    def test_cleanup_unknown_is_not_retried_and_watchdog_does_not_claim_stop(self):
        with tempfile.TemporaryDirectory() as temp:
            folder=Path(temp); owned=owned_decoder(folder)
            owned.cid=CID;owned.cutoff=time.monotonic()-1
            with mock.patch.object(owned,'inspect',side_effect=ValueError('synthetic-unknown')) as inspection:
                owned.watchdog()
                self.assertTrue(owned.watchdog_fired);self.assertFalse(owned.stopped)
                with self.assertRaisesRegex(ValueError,'PREVIOUS_OWN_DECODER_CLEANUP_UNRESOLVED_NO_REPEAT'):owned.cleanup()
                inspection.assert_called_once()
            self.assertEqual(owned.cleanup_failure,'OWN_DECODER_STOP_OR_REAP_UNVERIFIED')

    def test_synthetic_normal_decoder_start_frame_reply_wait_and_thread_join(self):
        with tempfile.TemporaryDirectory() as temp:
            owned=owned_decoder(Path(temp));created=inspect_fixture
            calls=[];started=False
            def control(args,*unused,**kwargs):
                calls.append(args)
                if args[0]=='create':return types.SimpleNamespace(stdout=CID.encode()+b'\n',returncode=0)
                if args[0]=='wait':return types.SimpleNamespace(stdout=b'0\n',returncode=0)
                self.assertEqual(args,['inspect',CID])
                value=created(owned)
                if started:value['State']['StartedAt']='synthetic-started'
                return types.SimpleNamespace(stdout=life.encoded([value]),returncode=0)
            class Process:
                def __init__(inner,args,**kwargs):
                    nonlocal started
                    calls.append(args);started=True;inner.returncode=None;inner.stderr=io.BytesIO(b'')
                    class Input(io.BytesIO):
                        def close(stream):
                            self.assertEqual(stream.getvalue(),b'synthetic-RAM-frame');super().close()
                    inner.stdin=Input()
                    kwargs['stdout'].write(b'{"status":"DECODED"}\n')
                    self.assertTrue(callable(kwargs['preexec_fn']))
                def wait(inner,*,timeout):
                    self.assertGreater(timeout,0);inner.returncode=0;return 0
                def poll(inner):return inner.returncode
            posix=types.SimpleNamespace(name='posix',path=os.path,fsync=os.fsync,fchmod=mock.Mock())
            resource=types.SimpleNamespace(RLIMIT_FSIZE=1,setrlimit=mock.Mock())
            with mock.patch.object(dec,'os',posix),mock.patch.dict(sys.modules,{'resource':resource}),\
                    mock.patch.object(dec,'command',side_effect=control),mock.patch.object(dec.subprocess,'Popen',side_effect=Process):
                result=owned.run(b'synthetic-RAM-frame')
            self.assertTrue(result['ownDecoderStopped']);self.assertTrue(result['attachCliReaped'])
            self.assertEqual(result['exitCode'],0);self.assertFalse(owned.watchdog_fired)
            self.assertEqual(sum(c[0]=='create' for c in calls),1)
            self.assertEqual(sum(c[:len(dec.DOCKER)+1]==[*dec.DOCKER,'start'] for c in calls),1)
            self.assertEqual(sum(c[0]=='wait' for c in calls),1)
            self.assertFalse(any(c[0] in ('stop','kill','rm') for c in calls))
            state=json.loads((owned.folder/'decoder-state.private.json').read_bytes())
            self.assertTrue(state['identityBound']);self.assertTrue(state['startAttempted'])
            self.assertTrue(state['ownedDecoderStoppedVerified']);self.assertFalse(state['finalOomKilled'])

    def test_create_or_bind_failure_retains_explicit_not_started_unverified_state(self):
        for variant in ('unknown-create','foreign-bind','bool-cold-pid'):
            with self.subTest(variant=variant),tempfile.TemporaryDirectory() as temp:
                owned=owned_decoder(Path(temp));calls=[]
                def control(args,*unused,**kwargs):
                    calls.append(args)
                    if args[0]=='create':
                        if variant=='unknown-create':raise ValueError('SYNTHETIC_CREATE_UNKNOWN')
                        return types.SimpleNamespace(stdout=CID.encode()+b'\n',returncode=0)
                    value=inspect_fixture(owned)
                    if variant=='bool-cold-pid':value['State']['Pid']=False
                    else:value['Id']='f'*64
                    return types.SimpleNamespace(stdout=life.encoded([value]),returncode=0)
                posix=types.SimpleNamespace(name='posix',path=os.path,fsync=os.fsync,fchmod=mock.Mock())
                resource=types.SimpleNamespace(RLIMIT_FSIZE=1,setrlimit=mock.Mock())
                with mock.patch.object(dec,'os',posix),mock.patch.dict(sys.modules,{'resource':resource}),\
                        mock.patch.object(dec,'command',side_effect=control),mock.patch.object(dec.subprocess,'Popen') as popen:
                    with self.assertRaises(ValueError):owned.run(b'synthetic-RAM-frame')
                popen.assert_not_called()
                state=json.loads((owned.folder/'decoder-state.private.json').read_bytes())
                self.assertTrue(state['createAttempted']);self.assertEqual(state['identityBound'],variant=='bool-cold-pid')
                self.assertFalse(state['startAttempted']);self.assertFalse(state['attachCliReaped'])
                self.assertFalse(state['ownedDecoderStoppedVerified']);self.assertIsNone(state['finalOomKilled'])
                self.assertFalse(any(c[0] in ('stop','kill','wait') for c in calls))

    def test_stderr_is_actually_capped_at_64k_and_overflow_wakes_own_watchdog(self):
        for size in (65536,65537):
            with self.subTest(size=size),tempfile.TemporaryDirectory() as temp:
                owned=owned_decoder(Path(temp));path=Path(temp)/'private-stderr'
                with path.open('xb') as out:owned.drain_stderr(io.BytesIO(b'x'*size),out)
                self.assertEqual(path.stat().st_size,65536)
                self.assertEqual(owned.stderr_overflow,size>65536)
                self.assertEqual(owned.wake.is_set(),size>65536)
                self.assertIsNone(owned.stderr_error)

    def test_main_return_one_runs_once_never_invokes_loader_or_decoder_and_keeps_private_failure(self):
        with tempfile.TemporaryDirectory() as temp:
            folder=Path(temp); here=folder/'repo/infra/cloud-lakehouse-ci';here.mkdir(parents=True)
            (here.parents[1]/'infra/maintenance').mkdir()
            planner=here.parents[1]/'infra/maintenance/iceberg_retention_plan.py';planner.write_bytes(b'synthetic planner source')
            producer=types.SimpleNamespace(HERE=here,main=mock.Mock(return_value=1))
            @contextmanager
            def observe(*unused):yield types.SimpleNamespace(make_completed=1,jdbc_completed=0)
            observer=types.SimpleNamespace(__file__=life.__file__,named_observer=observe)
            loader=types.SimpleNamespace(__file__=life.__file__,load_closed_copies=mock.Mock())
            normalizer=types.SimpleNamespace(__file__=life.__file__,normalize_graph=mock.Mock())
            pins={Path(m.__file__).name:life.read_proof(Path(m.__file__).absolute())['sha256'] for m in (life,dec,observer,loader,normalizer)}
            actual_read=life.read_proof
            def read(path,*args):
                value=actual_read(path,*args)
                if Path(path)==planner:value['sha256']='ec1ff5dc06d9da666d9ef1d32557937e36e0a63bc124f08ad6ed39edbf0224ae'
                return value
            environment={'GITHUB_ACTIONS':'true','RUNNER_ENVIRONMENT':'github-hosted','SOURCE_COMMIT':SOURCE,'GITHUB_SHA':SOURCE}
            with mock.patch.object(entry.sys,'platform','linux'),mock.patch.dict(os.environ,environment),mock.patch.object(life,'read_proof',side_effect=read),\
                    mock.patch.object(entry.sys,'argv',['entry','--source-manifest-sha256',life.RUNTIME,'--ack-fresh-cloud-trial9']),\
                    mock.patch.object(dec,'prep',return_value={}),mock.patch.object(dec,'Decoder') as decoder_class:
                result=entry.run(producer,observer,loader,normalizer,source_commit=SOURCE,output=folder/'new',
                    authority_source_sha256=actual_read(Path(entry.__file__).absolute())['sha256'],component_source_pins=pins,
                    prep_proof={},prep_sha256='f'*64,decoder_source_sha256='e'*64,classes=folder,iceberg=folder,policy={})
            producer.main.assert_called_once_with();loader.load_closed_copies.assert_not_called();decoder_class.assert_not_called()
            self.assertEqual(result['exitCode'],1)
            self.assertEqual(result['receipt']['failureCode'],'ORIGINAL_MAIN_RETURN_ZERO_REQUIRED')
            self.assertEqual(result['receipt']['lastStage'],'PRODUCER_PROOFS')
            self.assertEqual(result['receipt']['originalRoleStopCallsAdded'],0)
            self.assertFalse(result['receipt']['publicCompletenessClaimed'])


if __name__=='__main__':unittest.main(verbosity=2)
