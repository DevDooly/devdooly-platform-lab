"""Synthetic SQLite and archive-order regressions; no cluster or real backup reads."""
import argparse
from contextlib import closing
import importlib.util
from pathlib import Path
import shutil
import sqlite3
import tarfile
import tempfile
from types import SimpleNamespace
import unittest
from unittest import mock

SCRIPT = Path(__file__).resolve().parents[2]/'infra/scripts/backup-lab.py'
spec = importlib.util.spec_from_file_location('backup_under_test', SCRIPT)
backup = importlib.util.module_from_spec(spec); spec.loader.exec_module(backup)
REAL_CONNECT = sqlite3.connect


class TrackedConnection(sqlite3.Connection):
    closed = False
    def backup(self, target, *args, **kwargs):
        result = super().backup(target, *args, **kwargs)
        target.backup_finished = True
        return result
    def execute(self, sql, *args, **kwargs):
        if sql == 'PRAGMA journal_mode=DELETE' and not getattr(self, 'backup_finished', False):
            raise AssertionError('Destination journal mode must change after completed backup')
        return super().execute(sql, *args, **kwargs)
    def close(self):
        super().close(); self.closed = True


class SqliteSnapshotContracts(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='synthetic-sqlite-backup-')
        self.root = Path(self.temporary.name).resolve()
        self.connections = []
        self.writer = None

    def tearDown(self):
        for value in self.connections:
            if not value.closed: value.close()
        if self.writer: self.writer.close()
        self.temporary.cleanup()

    def wal_source(self, path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.writer = REAL_CONNECT(path)
        self.assertEqual(self.writer.execute('PRAGMA journal_mode=WAL').fetchone(), ('wal',))
        self.writer.execute('PRAGMA wal_autocheckpoint=0')
        self.writer.execute('CREATE TABLE synthetic(id INTEGER PRIMARY KEY, value TEXT)')
        self.writer.executemany('INSERT INTO synthetic VALUES (?,?)', [(i, 'fixture-'+str(i)) for i in range(1, 13)])
        self.writer.commit()
        self.assertGreater(Path(str(path)+'-wal').stat().st_size, 0)
        return path

    def connect(self, *args, **kwargs):
        value = REAL_CONNECT(*args, **kwargs, factory=TrackedConnection)
        self.connections.append(value)  # Strong references expose missing explicit close.
        return value

    def assert_closed(self):
        self.assertEqual(len(self.connections), 2)
        for value in self.connections:
            self.assertTrue(value.closed)
            with self.assertRaises(sqlite3.ProgrammingError): value.execute('SELECT 1')

    def test_real_wal_source_becomes_standalone_delete_snapshot_with_both_connections_closed(self):
        source = self.wal_source(self.root/'source.db'); target = self.root/'snapshot.db'
        original = [source.read_bytes(), Path(str(source)+'-wal').read_bytes()]
        with mock.patch.object(backup.sqlite3, 'connect', side_effect=self.connect):
            backup.sqlite_snapshot(source, target, lambda *_: None)
        self.assert_closed()
        self.assertEqual([source.read_bytes(), Path(str(source)+'-wal').read_bytes()], original)
        self.assertEqual(self.writer.execute('PRAGMA journal_mode').fetchone(), ('wal',))
        backup.require_standalone_snapshot(target)
        with closing(REAL_CONNECT(target.as_uri()+'?mode=ro&immutable=1', uri=True)) as value:
            self.assertEqual(value.execute('PRAGMA journal_mode').fetchone(), ('delete',))
            self.assertEqual(value.execute('PRAGMA integrity_check').fetchall(), [('ok',)])
            self.assertEqual(value.execute('SELECT COUNT(*) FROM synthetic').fetchone(), (12,))

    def test_backup_failure_closes_both_connections_and_never_deletes_partial_files(self):
        source = self.wal_source(self.root/'source.db'); target = self.root/'partial.db'
        def fail(*_): raise backup.BackupError('synthetic progress failure')
        with mock.patch.object(backup.sqlite3, 'connect', side_effect=self.connect):
            with self.assertRaises(backup.BackupError): backup.sqlite_snapshot(source, target, fail)
        self.assert_closed(); self.assertTrue(target.exists())

    def test_any_journal_companion_or_existing_destination_fails_without_removal(self):
        source = self.wal_source(self.root/'source.db')
        for suffix in ('', '-wal', '-shm', '-journal'):
            destination = self.root/('snapshot-'+str(len(suffix))+'.db')
            companion = Path(str(destination)+suffix); companion.write_bytes(b'preserve-synthetic-bytes')
            with self.assertRaises(backup.BackupError): backup.sqlite_snapshot(source, destination, lambda *_: None)
            self.assertEqual(companion.read_bytes(), b'preserve-synthetic-bytes')
            companion.unlink()  # Test-owned fixture cleanup, never production behavior.

    def test_real_create_backup_archives_only_after_close_and_rejects_late_companion(self):
        data = self.root/'data'; backups = self.root/'backups'; backups.mkdir()
        source = self.wal_source(data/'k3s/server/db/state.db')
        (data/'k3s/server/token').write_text('synthetic-token')
        for name in ('cred', 'tls'): (data/'k3s/server'/name).mkdir()
        args = argparse.Namespace(data_root=data, backup_root=backups, namespace='platform-lab',
            db_statefulset='lab-platform-lab-db', api_deployment='lab-platform-lab-api')
        resource = {'spec': {'replicas': 1, 'template': {'spec': {'containers': [{'image': 'example.invalid/image@sha256:'+'a'*64}]}}}}
        real_tree, real_copy = shutil.copytree, shutil.copy2
        tar_calls = []
        late_companion = [False]
        def copy_tree(src, dst, *a, **kw):
            if str(src) == '/etc/rancher/k3s': Path(dst).mkdir(); return dst
            return real_tree(src, dst, *a, **kw)
        def copy_file(src, dst, *a, **kw):
            if str(src).startswith('/etc/systemd/system/k3s.service'):
                Path(dst).write_text('synthetic-unit')
                if late_companion[0]: (Path(dst).parent/'state.db-wal').write_bytes(b'preserved-late-wal')
                return dst
            return real_copy(src, dst, *a, **kw)
        def command(argv, **_):
            if argv[0] == 'tar':
                self.assert_closed(); snapshot = Path(argv[4]); backup.require_standalone_snapshot(snapshot/'state.db')
                tar_calls.append(argv)
                with tarfile.open(argv[2], 'w:gz') as output: output.add(snapshot, arcname='.')
                return b''
            query = argv[-1]
            if 'TABLE_NAME,ENGINE' in query: return b'synthetic\tInnoDB\n'
            if 'SELECT COUNT(*)' in query: return b'1\n12\n12\t7\t3\t2\t0\n'
            return b'synthetic-baseline\n'
        def dump(argv, **kwargs):
            self.assertIn('mariadb-dump', argv[-1]); kwargs['stdout'].write(b'CREATE TABLE synthetic(id INT);\n')
            return SimpleNamespace(returncode=0)
        with mock.patch.object(backup, 'require_private'), mock.patch.object(backup, 'kube', return_value=resource), \
             mock.patch.object(backup, 'command', side_effect=command), mock.patch.object(backup.subprocess, 'run', side_effect=dump), \
             mock.patch.object(backup.shutil, 'disk_usage', return_value=SimpleNamespace(free=20*1024**3)), \
             mock.patch.object(backup.shutil, 'copytree', side_effect=copy_tree), mock.patch.object(backup.shutil, 'copy2', side_effect=copy_file), \
             mock.patch.object(backup.sqlite3, 'connect', side_effect=self.connect):
            self.assertTrue(backup.create_backup(args)['logicalDumpCreated'])
            self.assertEqual(len(tar_calls), 1)
            self.connections.clear(); late_companion[0] = True
            with self.assertRaises(backup.BackupError): backup.create_backup(args)
            self.assert_closed(); self.assertEqual(len(tar_calls), 1)
        self.assertEqual(len(list(backups.glob('*/manifest.json'))), 1)
        self.assertEqual(len(list(backups.glob('*/k3s-datastore/state.db-wal'))), 1)


if __name__ == '__main__': unittest.main()
