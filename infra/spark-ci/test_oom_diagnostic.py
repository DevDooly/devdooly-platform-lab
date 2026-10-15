"""Bounded diagnostic-only contracts; no Docker, JVM, network or SQL execution."""
import ast
import copy
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
import run_ci as r


def sample():
    values = {'pids.current': ['23'], 'pids.max': ['512'], 'pids.events': ['max 7'],
        'memory.current': ['1000000'], 'memory.max': ['3221225472'],
        'memory.events': ['low 0', 'high 0', 'max 2', 'oom 0', 'oom_kill 0', 'oom_group_kill 0', 'sock_throttled 0']}
    return ('CGROUP_V2_CONTAINER_ROOT\n' + ''.join('BEGIN '+name+'\n'+'\n'.join(values[name])+'\nEND '+name+'\n'
        for name in r.CGROUP_FILES)).encode()


def state(cid='a'*64, running=True):
    return {'role': 'spark', 'id': cid, 'running': running, 'exitCode': 0, 'oom': False}


def result(raw=None, code=0, truncated=False, timed_out=False):
    return SimpleNamespace(stdout=sample() if raw is None else raw, stderr=b'private-path-secret', returncode=code,
        capture_truncated=truncated, capture_timed_out=timed_out)


class OomDiagnostics(unittest.TestCase):
    def setUp(self):
        self.stack = []
        for name, value in (('O_NOFOLLOW', getattr(os, 'O_NOFOLLOW', 0)),
                ('fchmod', getattr(os, 'fchmod', lambda fd, mode: None))):
            item = patch.object(os, name, value, create=True); item.start(); self.addCleanup(item.stop)

    def test_only_exact_fixed_oom_signatures_escape_private_tail(self):
        cases = {'JAVA_HEAP_SPACE_SIGNATURE': b'Java heap space\n',
            'NATIVE_THREAD_SIGNATURE': b'unable to create native thread: possibly out of memory or process/resource limits reached\n',
            'DIRECT_BUFFER_SIGNATURE': b'Cannot reserve 1024 bytes of direct buffer memory (allocated: 5, limit: 8)\n',
            'METASPACE_SIGNATURE': b'Metaspace\n'}
        for expected, message in cases.items():
            raw = b'private-value\njava.lang.OutOfMemoryError: '+message
            self.assertEqual(expected, r.oom_subtype_signature(raw))
            self.assertEqual('JAVA_OUT_OF_MEMORY_SIGNATURE', r.log_signature(raw))
            self.assertNotIn('private', r.oom_subtype_signature(raw))
        self.assertEqual('DIRECT_BUFFER_SIGNATURE', r.oom_subtype_signature(b'java.lang.OutOfMemoryError: Direct buffer memory\n'))

    def test_unknown_ambiguous_and_outside_tail_do_not_invent_a_cause(self):
        for raw in (b'java.lang.OutOfMemoryError: unknown private message\n', b'Java heap space\n',
                b'java.lang.OutOfMemoryError: Java heap space private\n',
                b'java.lang.OutOfMemoryError: Metaspace\n'+b'x'*262144):
            self.assertEqual('OOM_SUBTYPE_UNOBSERVED', r.oom_subtype_signature(raw))
        self.assertEqual('MULTIPLE_OOM_SUBTYPE_SIGNATURES', r.oom_subtype_signature(
            b'java.lang.OutOfMemoryError: Metaspace\njava.lang.OutOfMemoryError: Java heap space\n'))

    def test_actual_numbers_and_lifetime_events_are_not_replaced_by_hypotheses(self):
        value = r.parse_cgroup_sample(sample())
        self.assertEqual(512, value['pidsMax']); self.assertEqual(7, value['pidsEventsMax'])
        self.assertEqual(3221225472, value['memoryMaxBytes']); self.assertEqual(0, value['memoryEventsOomKill'])
        self.assertTrue(value['pidsLimitMatchesPlan']); self.assertTrue(value['memoryLimitMatchesPlan'])
        raw = sample().replace(b'BEGIN pids.max\n512', b'BEGIN pids.max\nmax').replace(b'oom_group_kill 0\n', b'')
        value = r.parse_cgroup_sample(raw)
        self.assertIsNone(value['pidsMax']); self.assertTrue(value['pidsMaxUnlimited'])
        self.assertIsNone(value['memoryEventsOomGroupKill']); self.assertFalse(value['pidsLimitMatchesPlan'])

    def test_parser_rejects_extra_private_output_duplicates_wrong_root_and_partial_numeric_data(self):
        for raw in (sample()+b'private-path\n', sample().replace(b'ROOT', b'HOST'),
                sample().replace(b'max 7', b'max 7\nmax 8'), sample().replace(b'max 7', b'max private'),
                sample().replace(b'oom 0\n', b''), sample().replace(b'1000000', b'-1'),
                sample().replace(b'1000000', b'9223372036854775808'), sample()[:-2], b'x'*8193):
            with self.assertRaises((RuntimeError, UnicodeError)): r.parse_cgroup_sample(raw)

    def test_same_full_owned_id_is_bound_before_and_after_and_raw_errors_stay_private(self):
        with tempfile.TemporaryDirectory() as folder:
            attempt = SimpleNamespace(root=Path(folder), containers=lambda: [state()])
            with patch.object(r, 'bounded_cgroup_exec', return_value=result()) as execute:
                value = r.capture_spark_cgroup(attempt, state())
            execute.assert_called_once_with('a'*64)
            self.assertEqual('OBSERVED', value['collection']); self.assertTrue(value['identityBound'])
            self.assertFalse(value['baselineOrDeltaMeasured']); self.assertTrue(value['diagnosticExecOverheadIncluded'])
            self.assertEqual(7, value['values']['pidsEventsMax'])
            self.assertNotIn('private', json.dumps(value)); self.assertNotIn('a'*64, json.dumps(value))
            self.assertIn(b'private-path-secret', (Path(folder)/'spark-cgroup.stderr').read_bytes())

    def test_foreign_id_exited_owner_and_post_read_replacement_cannot_supply_metrics(self):
        for snapshots, expected_status in (([[state('b'*64)]], 'UNOBSERVED'),
                ([[state(running=False)]], 'NOT_RUNNING'), ([[state()], [state('b'*64)]], 'UNOBSERVED')):
            with tempfile.TemporaryDirectory() as folder:
                attempt = SimpleNamespace(root=Path(folder), containers=iter(snapshots).__next__)
                with patch.object(r, 'bounded_cgroup_exec', return_value=result()) as execute:
                    value = r.capture_spark_cgroup(attempt, state())
                self.assertEqual(expected_status, value['collection']); self.assertEqual({}, value['values'])
                self.assertFalse(value['identityBound'])
                if len(snapshots) == 1: execute.assert_not_called()

    def test_pid_saturation_exec_failure_timeout_and_overflow_remain_unobserved(self):
        for captured in (result(code=126), result(timed_out=True), result(truncated=True), result(raw=b'partial')):
            with tempfile.TemporaryDirectory() as folder:
                attempt = SimpleNamespace(root=Path(folder), containers=lambda: [state()])
                with patch.object(r, 'bounded_cgroup_exec', return_value=captured): value = r.capture_spark_cgroup(attempt, state())
                self.assertEqual('UNOBSERVED', value['collection']); self.assertEqual({}, value['values'])
                self.assertTrue(value['execAttempted']); self.assertFalse(value['identityBound'])
                self.assertNotIn('private', json.dumps(value))

    def test_fixed_readonly_exec_has_bounded_real_child_pipes_without_running_docker(self):
        original = subprocess.Popen; calls = []
        def child(argv, **kwargs):
            calls.append(argv)
            return original([sys.executable, '-c', "import sys;sys.stdout.buffer.write(b'x'*1048576);sys.stdout.flush()"], **kwargs)
        with patch.object(r.subprocess, 'Popen', side_effect=child): value = r.bounded_cgroup_exec('a'*64)
        self.assertTrue(value.capture_truncated); self.assertLessEqual(len(value.stdout), 8192); self.assertLessEqual(len(value.stderr), 8192)
        self.assertEqual([['docker', 'exec', '--user', '185:185', 'a'*64, '/bin/sh', '-c', r.CGROUP_SCRIPT]], calls)
        self.assertNotIn('cat ', r.CGROUP_SCRIPT); self.assertNotIn('tee ', r.CGROUP_SCRIPT)
        with self.assertRaises(RuntimeError): r.bounded_cgroup_exec('short-id')

    def test_deadline_diagnostic_samples_before_logs_and_cleanup_with_no_relaunch(self):
        events=[]
        with tempfile.TemporaryDirectory() as folder:
            attempt=SimpleNamespace(root=Path(folder), containers=lambda:[state()]); (Path(folder)/'proof').mkdir()
            def capture(*args): events.append('cgroup'); return r.empty_cgroup_diagnostic()
            def logs(*args): events.append('logs'); return result(raw=b'java.lang.OutOfMemoryError: Metaspace\n')
            diagnostic={}
            with patch.object(r,'capture_spark_cgroup',side_effect=capture),patch.object(r,'bounded_deadline_logs',side_effect=logs):
                try: r.spark_diagnostics(attempt,state(),diagnostic,deadline_capture=True)
                finally: events.append('caller-cleanup')
            self.assertEqual(['cgroup','logs','caller-cleanup'],events)
            self.assertEqual('METASPACE_SIGNATURE',diagnostic['oomSubtypeSignature']); self.assertFalse(diagnostic['oomKilled'])

    def test_computation_images_non_pid_limits_deadline_and_cleanup_remain_frozen(self):
        here=Path(__file__).resolve().parent
        expected_files={'compose_plan.py':'fcaa911c8dcb9c6b56821ed3ff40d71c282658c8f5beb88200bff07c25336ee5',
            'bootstrap_spark.py':'e10ef3cca6a71b7ce362ab769fdb1436e2b84bf3705e584d6d14c9173b0ab816'}
        for name,digest in expected_files.items(): self.assertEqual(digest,hashlib.sha256((here/name).read_bytes()).hexdigest())
        current=ast.parse((here/'run_ci.py').read_text('utf-8'))
        def function(tree,name): return next(node for node in tree.body if isinstance(node,ast.FunctionDef) and node.name==name)
        expected_functions={'wait_spark_once':'3794bcb25699d30a0356767d9c4aa41b1d3a5144f6aec5b819ab9a6f5869efa2',
            'safe_spark_result':'a56f016c51a14df7db64620a91c7468a2c2917ce0eb968b3d8b45af765a19efb',
            'bounded_deadline_logs':'954f4f05ff1b00a4474f1079e7f96e7594bc6f7dcb9dfeceeafeb3ac860549e2'}
        for name,digest in expected_functions.items(): self.assertEqual(digest,hashlib.sha256(ast.dump(function(current,name)).encode()).hexdigest())
        new_main=copy.deepcopy(function(current,'main'))
        diagnostic=next(node for node in new_main.body if isinstance(node,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='diagnostics' for t in node.targets))
        kept=[(key,value)for key,value in zip(diagnostic.value.keys,diagnostic.value.values)if key.value not in ('oomSubtypeSignature','cgroup')]
        diagnostic.value.keys=[key for key,value in kept]; diagnostic.value.values=[value for key,value in kept]
        self.assertEqual('f9b5ff0002829c7d2ed78b9f6350c88431898be47c26a3d8904093f31bbaaa8a',hashlib.sha256(ast.dump(new_main).encode()).hexdigest())


if __name__=='__main__': unittest.main()
