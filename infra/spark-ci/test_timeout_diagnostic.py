"""Fixed transition files and deadline diagnostics; no Docker/PySpark/network."""
import ast
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import bootstrap_spark as b
import run_ci as r


def progress():
    return {'schemaVersion':1,'scope':'ISOLATED_SPARK_BOOTSTRAP_PROGRESS','sequence':3,
        'lastPhase':'SESSION','milestones':['PYTHON_START','IMPORT_SILVER','SESSION'],
        'elapsedMillis':100,'tmpMountFlag':'NOEXEC','completionNotProven':True}


class TimeoutDiagnostics(unittest.TestCase):
    def setUp(self):
        # Existing timeout contracts never invoke Docker; resource sampling has
        # its own exact-target mocked tests in test_oom_diagnostic.py.
        sample = patch.object(r, 'capture_spark_cgroup', return_value=r.empty_cgroup_diagnostic())
        sample.start(); self.addCleanup(sample.stop)

    def test_complete_fixed_transition_is_atomic_immutable_and_does_not_claim_completion(self):
        with tempfile.TemporaryDirectory()as folder,patch.object(b,'PROOF',Path(folder)),patch.object(os,'O_NOFOLLOW',getattr(os,'O_NOFOLLOW',0),create=True):
            b.write_progress(progress()['milestones'],'NOEXEC',100)
            raw=Path(folder,'bootstrap-progress-03.json').read_bytes()
            self.assertEqual(progress(),json.loads(raw));self.assertTrue(json.loads(raw)['completionNotProven'])
            self.assertEqual([],list(Path(folder).glob('*.tmp')))
            with self.assertRaises(FileExistsError):b.write_progress(progress()['milestones'],'NOEXEC',100)
            self.assertEqual(raw,Path(folder,'bootstrap-progress-03.json').read_bytes())

    def test_progress_rejects_private_fields_unknown_phases_and_false_completion(self):
        for change in ({'host':'secret'},{'completionNotProven':False},{'lastPhase':'SQL_SECRET'},
                {'elapsedMillis':float('nan')},{'sequence':True},{'milestones':['PYTHON_START','SESSION','SESSION']}):
            with self.assertRaises((RuntimeError,TypeError)):r.safe_progress({**progress(),**change})

    def test_read_latest_complete_progress_ignores_unpublished_partial_temporary_file(self):
        with tempfile.TemporaryDirectory()as folder,patch.object(os,'O_NOFOLLOW',getattr(os,'O_NOFOLLOW',0),create=True):
            root=Path(folder);(root/'proof').mkdir()
            (root/'proof/bootstrap-progress-03.json').write_text(json.dumps(progress()))
            (root/'proof/.bootstrap-progress-04.json.tmp').write_text('{')
            self.assertEqual(progress(),r.read_progress(root))
            (root/'proof/bootstrap-progress-03.json').write_text('{"host":"private"}')
            with self.assertRaises(RuntimeError):r.read_progress(root)

    def test_unpublished_transition_on_link_failure_does_not_create_false_progress(self):
        with tempfile.TemporaryDirectory()as folder,patch.object(b,'PROOF',Path(folder)),patch.object(os,'O_NOFOLLOW',getattr(os,'O_NOFOLLOW',0),create=True),patch.object(os,'link',side_effect=OSError('synthetic unavailable')):
            with self.assertRaises(OSError):b.write_progress(progress()['milestones'],'NOEXEC',100)
            self.assertFalse(Path(folder,'bootstrap-progress-03.json').exists())

    def test_actual_deadline_path_captures_before_caller_cleanup_and_never_resubmits(self):
        events=[];diagnostic={'stateObserved':False,'deadlineCapture':'NOT_REQUESTED'}
        attempt=SimpleNamespace(containers=lambda:events.append('inventory'))
        def capture(*args,**kwargs):
            self.assertTrue(kwargs['deadline_capture']);events.append('capture');diagnostic['stateObserved']=True
        with patch.object(r.time,'monotonic',side_effect=[0,600]),patch.object(r,'spark_diagnostics',side_effect=capture):
            with self.assertRaisesRegex(RuntimeError,'ONE_SPARK_PROCESS_DEADLINE'):r.wait_spark_once(attempt,{'id':'a'*64},diagnostic)
        self.assertEqual(['capture'],events);self.assertEqual('CAPTURED',diagnostic['deadlineCapture'])

    def test_capture_failure_preserves_deadline_and_reports_unobserved_without_skipping_caller_finally(self):
        events=[];diagnostic={'stateObserved':False,'deadlineCapture':'NOT_REQUESTED'}
        with patch.object(r.time,'monotonic',side_effect=[0,600]),patch.object(r,'spark_diagnostics',side_effect=RuntimeError('private exception data')):
            try:
                with self.assertRaisesRegex(RuntimeError,'ONE_SPARK_PROCESS_DEADLINE'):r.wait_spark_once(None,{'id':'a'*64},diagnostic)
            finally:events.append('caller-cleanup')
        self.assertEqual('UNOBSERVED',diagnostic['deadlineCapture']);self.assertEqual(['caller-cleanup'],events)
        self.assertNotIn('private',json.dumps(diagnostic))

    def test_deadline_logs_bound_real_child_streams_without_running_docker(self):
        original=subprocess.Popen;calls=[]
        def child(argv,**kwargs):
            calls.append(argv)
            return original([sys.executable,'-c',"import sys;sys.stdout.buffer.write(b'x'*1048576);sys.stdout.flush();sys.stderr.buffer.write(b'y'*1048576)"],**kwargs)
        with patch.object(r.subprocess,'Popen',side_effect=child):result=r.bounded_deadline_logs('a'*64)
        self.assertTrue(result.capture_truncated);self.assertLessEqual(len(result.stdout),262144);self.assertLessEqual(len(result.stderr),262144)
        self.assertEqual([['docker','logs','--tail','200','a'*64]],calls)

    def test_foreign_container_cannot_supply_deadline_state_or_progress(self):
        attempt=SimpleNamespace(containers=lambda:[{'role':'spark','id':'b'*64}]);diagnostic={'stateObserved':False}
        with patch.object(r,'bounded_deadline_logs')as logs:
            with self.assertRaisesRegex(RuntimeError,'SAME_EXACT_SPARK'):r.spark_diagnostics(attempt,{'id':'a'*64},diagnostic,deadline_capture=True)
        logs.assert_not_called();self.assertFalse(diagnostic['stateObserved'])

    def test_partial_final_diagnostic_cannot_erase_last_complete_transition(self):
        with tempfile.TemporaryDirectory()as folder,patch.object(os,'O_NOFOLLOW',getattr(os,'O_NOFOLLOW',0),create=True),patch.object(os,'fchmod',getattr(os,'fchmod',lambda fd,mode:None),create=True):
            root=Path(folder);(root/'proof').mkdir()
            (root/'proof/bootstrap-progress-03.json').write_text(json.dumps(progress()))
            (root/'proof/bootstrap-diagnostic.json').write_text('{')
            state={'id':'a'*64,'role':'spark','running':True,'exitCode':0,'oom':False}
            attempt=SimpleNamespace(root=root,containers=lambda:[state]);diagnostic={'stateObserved':False,'bootstrap':None}
            logs=SimpleNamespace(stdout=b'',stderr=b'',returncode=0,capture_truncated=False)
            with patch.object(r,'bounded_deadline_logs',return_value=logs),self.assertRaises(ValueError):r.spark_diagnostics(attempt,state,diagnostic,deadline_capture=True)
            self.assertEqual(progress(),diagnostic['progress']);self.assertTrue(diagnostic['stateObserved']);self.assertIsNone(diagnostic['bootstrap'])

    def test_deadline_capture_reads_allowlisted_progress_and_keeps_raw_logs_private(self):
        with tempfile.TemporaryDirectory()as folder,patch.object(os,'O_NOFOLLOW',getattr(os,'O_NOFOLLOW',0),create=True),patch.object(os,'fchmod',getattr(os,'fchmod',lambda fd,mode:None),create=True):
            root=Path(folder);(root/'proof').mkdir();(root/'proof/bootstrap-progress-03.json').write_text(json.dumps(progress()))
            state={'id':'a'*64,'role':'spark','running':True,'exitCode':0,'oom':False}
            attempt=SimpleNamespace(root=root,containers=lambda:[state]);diagnostic={'stateObserved':False}
            logs=SimpleNamespace(stdout=b'private-secret-path',stderr=b'java.lang.OutOfMemoryError private-secret',returncode=0,capture_truncated=False)
            with patch.object(r,'bounded_deadline_logs',return_value=logs):r.spark_diagnostics(attempt,state,diagnostic,deadline_capture=True)
            self.assertTrue(diagnostic['stateObserved']);self.assertIsNone(diagnostic['exitCode']);self.assertEqual(progress(),diagnostic['progress'])
            self.assertEqual('JAVA_OUT_OF_MEMORY_SIGNATURE',diagnostic['logSignature']);self.assertNotIn('private-secret',json.dumps(diagnostic))
            self.assertIn(b'private-secret',(root/'spark-diagnostic.stdout').read_bytes())

    def test_limits_workflow_and_computation_remain_frozen(self):
        here=Path(__file__).resolve().parent
        tree=ast.parse((here/'bootstrap_spark.py').read_text('utf-8'))
        compute=next(n for n in tree.body if isinstance(n,ast.FunctionDef)and n.name=='execute')
        self.assertEqual('f231cfd9b5c70f5699b1bba8444fd8644be4bf5d7fb641c1b50f2e0df41c8579',hashlib.sha256(ast.dump(compute,include_attributes=False).encode()).hexdigest())
        wait=next(n for n in ast.parse((here/'run_ci.py').read_text('utf-8')).body if isinstance(n,ast.FunctionDef)and n.name=='wait_spark_once')
        self.assertEqual(600,wait.body[0].value.right.value)
        self.assertEqual(1,r.MODULES['spark_silver.py'].count('71bd63230704c6d880eb1208abc63ef5080448cfd46bf3295f1bc77f38ddd9f7'))


if __name__=='__main__':unittest.main()
