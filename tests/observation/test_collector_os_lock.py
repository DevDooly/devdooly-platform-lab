"""Offline OS-lock checks; SIGKILL coverage requires a real POSIX process."""
from contextlib import redirect_stdout
import io
import json
import os
from pathlib import Path
import signal
import stat
import subprocess
import sys
import tempfile
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch

SOURCE=Path(__file__).resolve().parents[2]/'infra/observation'
sys.path.insert(0,str(SOURCE))
import platform_collector as collector
from test_platform_collector import snapshot


class CollectorOSLockTests(unittest.TestCase):
    def test_repeated_acquisition_keeps_inode_and_existing_bytes(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'writer.lock'
            path.write_bytes(b'synthetic-lock');path.chmod(0o600)
            identity=(path.stat().st_dev,path.stat().st_ino)
            for unused in range(2):
                with collector.CollectorLock(path):
                    self.assertEqual((path.stat().st_dev,path.stat().st_ino),identity)
                self.assertTrue(path.exists())
                self.assertEqual(path.read_bytes(),b'synthetic-lock')

    def test_directory_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(collector.CollectionError,'^COLLECTION_FAILED$'):
                with collector.CollectorLock(Path(directory)):
                    self.fail('directory cannot become a writer lock')

    def test_hard_link_is_rejected_without_changing_target(self):
        with tempfile.TemporaryDirectory() as directory:
            target=Path(directory)/'target';target.write_bytes(b'keep-me');target.chmod(0o600)
            alias=Path(directory)/'writer.lock'
            try:os.link(target,alias)
            except OSError:self.skipTest('hard links are unavailable on this filesystem')
            with self.assertRaisesRegex(collector.CollectionError,'^COLLECTION_FAILED$'):
                with collector.CollectorLock(alias):
                    self.fail('a linked file cannot become a writer lock')
            self.assertEqual(target.read_bytes(),b'keep-me')
            self.assertEqual(target.stat().st_nlink,2)


@unittest.skipUnless(os.name=='posix','POSIX ownership, flock and SIGKILL require Linux/Unix')
class PosixCollectorLockTests(unittest.TestCase):
    def test_symlink_is_rejected_without_changing_target(self):
        with tempfile.TemporaryDirectory() as directory:
            target=Path(directory)/'target';target.write_bytes(b'keep-me');target.chmod(0o600)
            alias=Path(directory)/'writer.lock';alias.symlink_to(target)
            with self.assertRaisesRegex(collector.CollectionError,'^COLLECTION_FAILED$'):
                with collector.CollectorLock(alias):
                    self.fail('a symlink cannot become a writer lock')
            self.assertEqual(target.read_bytes(),b'keep-me')
            self.assertTrue(alias.is_symlink())

    def test_permissive_mode_is_rejected_without_repair(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'writer.lock';path.write_bytes(b'keep-me');path.chmod(0o644)
            with self.assertRaisesRegex(collector.CollectionError,'^COLLECTION_FAILED$'):
                with collector.CollectorLock(path):
                    self.fail('an unsafe lock mode cannot be silently repaired')
            self.assertEqual(stat.S_IMODE(path.stat().st_mode),0o644)
            self.assertEqual(path.read_bytes(),b'keep-me')

    def test_foreign_owner_is_rejected_and_descriptor_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'writer.lock';path.write_bytes(b'keep-me');path.chmod(0o600)
            info=path.stat()
            foreign=SimpleNamespace(st_mode=info.st_mode,st_nlink=1,
                                    st_uid=os.geteuid()+1,st_size=info.st_size)
            close=os.close
            with patch.object(collector.os,'fstat',return_value=foreign),\
                    patch.object(collector.os,'close',wraps=close) as closed:
                with self.assertRaisesRegex(collector.CollectionError,'^COLLECTION_FAILED$'):
                    with collector.CollectorLock(path):
                        self.fail('a foreign owner cannot provide this process lock')
            self.assertEqual(closed.call_count,1)
            self.assertEqual(path.read_bytes(),b'keep-me')

    def test_sigkill_releases_lock_for_next_collection_with_same_inode(self):
        child_code='''
import sys,signal
from pathlib import Path
sys.path.insert(0,sys.argv[1])
import platform_collector as collector
class BlockAfterLock:
    def __init__(self,*args,**kwargs):
        Path(sys.argv[3]).write_text('LOCK_HELD',encoding='ascii')
        signal.pause()
        raise AssertionError('the test child must be killed while holding the lock')
collector.JsonTransport=BlockAfterLock
raise SystemExit(collector.main([
    '--server','https://127.0.0.1:6443','--token-file',sys.argv[2],
    '--ca-file',sys.argv[2],'--output',sys.argv[2]]))
'''
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'snapshot.json'
            previous=snapshot();path.write_text(json.dumps(previous))
            before=path.read_bytes()
            marker=Path(directory)/'child-ready'
            lock_path=path.parent/('.'+path.name+'.lock')
            child=subprocess.Popen([sys.executable,'-I','-B','-c',child_code,
                str(SOURCE),str(path),str(marker)],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
            try:
                deadline=time.monotonic()+8
                while not marker.exists() and child.poll() is None and time.monotonic()<deadline:
                    time.sleep(0.02)
                self.assertTrue(marker.exists(),'child did not reach the held-lock boundary')
                self.assertIsNone(child.poll())
                identity=(lock_path.stat().st_dev,lock_path.stat().st_ino)
                self.assertEqual(path.read_bytes(),before)
                with patch.object(collector,'JsonTransport') as transport,redirect_stdout(io.StringIO()):
                    result=collector.main(['--server','https://127.0.0.1:6443',
                        '--token-file',str(path),'--ca-file',str(path),'--output',str(path)])
                self.assertEqual(result,1);transport.assert_not_called()
                self.assertEqual(path.read_bytes(),before)
                child.kill();child.wait(timeout=5)
                self.assertEqual(child.returncode,-signal.SIGKILL)
                self.assertEqual((lock_path.stat().st_dev,lock_path.stat().st_ino),identity)
                self.assertEqual(path.read_bytes(),before)
                with patch.object(collector,'JsonTransport',
                        side_effect=collector.CollectionError('AUTHENTICATION_FAILED')) as transport,\
                        redirect_stdout(io.StringIO()):
                    result=collector.main(['--server','https://127.0.0.1:6443',
                        '--token-file',str(path),'--ca-file',str(path),'--output',str(path)])
                self.assertEqual(result,1);self.assertEqual(transport.call_count,1)
                recovered=json.loads(path.read_text())
                self.assertEqual(recovered['latestAttempt']['errorCode'],'AUTHENTICATION_FAILED')
                self.assertEqual(recovered['lastSuccess'],previous['lastSuccess'])
                self.assertEqual((lock_path.stat().st_dev,lock_path.stat().st_ino),identity)
            finally:
                if child.poll() is None:
                    child.kill();child.wait(timeout=5)


if __name__=='__main__':unittest.main()
