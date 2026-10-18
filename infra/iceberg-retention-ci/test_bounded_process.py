"""Synthetic stdlib processes only on POSIX; Windows skips are intentional."""
import hashlib
import json
import os
from pathlib import Path
import stat
import sys
import tempfile
import time
import types
import unittest
from unittest import mock

import bounded_process as b


class PureArguments(unittest.TestCase):
    def test_hash_only_argv_and_streaming_archive_contract(self):
        marker='SYNTHETIC_PRIVATE_JAVA_ARGUMENT_NOT_FOR_RECORD'
        result=b.arguments(['java',marker],'compile',100.0,5.0,1024**3,65536,True,'classpath.tar')
        self.assertEqual(result['argumentCount'],2)
        self.assertNotIn(marker,json.dumps(result))
        self.assertRegex(result['argvSha256'],'^[a-f0-9]{64}$')
        with self.assertRaises(ValueError):b.arguments(['java'],'compile',100,5,1024**3,65536,False,None)

    def test_direct_paths_bool_nonfinite_and_duplicate_authority_names_rejected(self):
        baseline=[['python'],'step',100.0,5.0,1024,65536,True,None]
        variants=((1,'../step'),(2,float('nan')),(3,True),(4,True),(5,65537),
            (7,'../classpath.tar'),(7,'step.result.json'))
        for index,value in variants:
            changed=list(baseline);changed[index]=value
            with self.subTest(index=index,value=str(value)),self.assertRaises(ValueError):b.arguments(*changed)

    def test_tar_overhead_bound_requires_named_stream_and_rejects_one_extra_byte(self):
        base=[['docker','cp'],'export',100.0,5.0,b.MAX_ARCHIVE_STDOUT,65536,True,'classpath.tar']
        self.assertEqual(b.MAX_ARCHIVE_STDOUT,1024**3+16*1024**2)
        self.assertEqual(b.arguments(*base)['argumentCount'],2)
        for index,value in ((4,b.MAX_ARCHIVE_STDOUT+1),(7,None),(6,False)):
            changed=list(base);changed[index]=value
            with self.subTest(index=index),self.assertRaises(ValueError):b.arguments(*changed)

    def test_non_posix_rejects_before_popen_or_any_output(self):
        with tempfile.TemporaryDirectory() as temp,mock.patch.object(b,'os',types.SimpleNamespace(name='nt')),\
                mock.patch.object(b.subprocess,'Popen') as child:
            with self.assertRaisesRegex(ValueError,'LINUX_SELECTORS_PIPE_EXECUTION_REQUIRED'):
                b.execute(['must-not-run'],Path(temp),'step',time.monotonic()+10,1)
            child.assert_not_called();self.assertEqual(list(Path(temp).iterdir()),[])


@unittest.skipUnless(os.name=='posix','Actual Linux selectors/openat/mode semantics unavailable on Windows')
class LinuxChildren(unittest.TestCase):
    def directory(self):
        folder=tempfile.TemporaryDirectory();self.addCleanup(folder.cleanup)
        root=Path(folder.name);root.chmod(0o700);return root

    def test_archive_streaming_and_ram_only_inspection_never_save_inspected_value(self):
        root=self.directory()
        result=b.execute([sys.executable,'-c','import os;os.write(1,b"x"*200000);os.write(2,b"warn")'],
            root,'archive',time.monotonic()+10,5,maximum_stdout=300000,stdout_filename='classpath.tar')
        self.assertIsNone(result['stdout']);self.assertEqual(result['stderr'],b'warn')
        self.assertEqual((root/'classpath.tar').stat().st_size,200000)
        self.assertEqual(result['receipt']['stdoutSha256'],hashlib.sha256(b'x'*200000).hexdigest())
        self.assertTrue(result['receipt']['stdoutEofObserved']);self.assertTrue(result['receipt']['childReaped'])
        self.assertEqual(stat.S_IMODE((root/'classpath.tar').stat().st_mode),0o600)
        marker=b'SYNTHETIC_INSPECT_ENV_VALUE'
        inspect=b.execute([sys.executable,'-c','print("SYNTHETIC_INSPECT_ENV_VALUE")'],root,'inspect',
            time.monotonic()+10,5,persist_stdout=False)
        self.assertEqual(inspect['stdout'],marker+b'\n');self.assertFalse((root/'inspect.stdout.private').exists())
        for p in root.glob('inspect*'):self.assertNotIn(marker,p.read_bytes())

    def test_output_overflow_and_timeout_preserve_bounded_prefix_and_reap_owned_child(self):
        for name,body,kwargs,code in (
                ('stderr','import os;os.write(2,b"e"*65537)',{},'PREP_STDERR_LIMIT_EXCEEDED_NO_RETRY'),
                ('stdout','import os;os.write(1,b"o"*4097)',{'maximum_stdout':4096},'PREP_STDOUT_LIMIT_EXCEEDED_NO_RETRY'),
                ('timeout','import time;time.sleep(5)',{'timeout':0.1},'PREP_CHILD_TIMEOUT_NO_RETRY')):
            root=self.directory();timeout=kwargs.pop('timeout',5)
            with self.subTest(name=name),self.assertRaisesRegex(ValueError,code):
                b.execute([sys.executable,'-c',body],root,name,time.monotonic()+10,timeout,**kwargs)
            receipt=json.loads((root/(name+'.result.json')).read_bytes())
            self.assertTrue(receipt['childReaped']);self.assertFalse(receipt['dockerStopOrRemovalPerformed'])
            self.assertLessEqual((root/(name+'.stderr.private')).stat().st_size,65536)
            self.assertLessEqual((root/(name+'.stdout.private')).stat().st_size,kwargs.get('maximum_stdout',b.MIB))
            self.assertNotIn(body,(root/(name+'.intent.json')).read_text())

    def test_known_nonzero_returns_and_existing_records_prevent_second_start(self):
        root=self.directory();argv=[sys.executable,'-c','import os,sys;os.write(1,b"partial");sys.exit(7)']
        result=b.execute(argv,root,'nonzero',time.monotonic()+10,5)
        self.assertEqual(result['returncode'],7);self.assertEqual(result['stdout'],b'partial')
        self.assertEqual(result['receipt']['outcome'],'EXITED_NONZERO')
        self.assertTrue(result['receipt']['childReaped'])
        previous=(root/'nonzero.result.json').read_bytes()
        with mock.patch.object(b.subprocess,'Popen') as child:
            with self.assertRaisesRegex(ValueError,'PREP_PRIVATE_RECORD_ALREADY_EXISTS_NO_RETRY'):
                b.execute(argv,root,'nonzero',time.monotonic()+10,5)
            child.assert_not_called()
        self.assertEqual((root/'nonzero.result.json').read_bytes(),previous)


if __name__=='__main__':unittest.main(verbosity=2)
