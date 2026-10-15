import copy
import tempfile
from pathlib import Path
import unittest
from unittest import mock
import xml.etree.ElementTree as ET

import run_s3_ci as c


class Boundaries(unittest.TestCase):
    def container(self):
        return {'Id': 'a'*64, 'Name': '/own-db', 'Config': {'Labels': {c.LABEL: 'own'}}, 'Image': 'sha256:fixed',
                'HostConfig': {'RestartPolicy': {'Name': 'no'}, 'Binds': ['new-db:/var/lib/mysql:rw']},
                'NetworkSettings': {'Networks': {'own': {}}, 'Ports': {'3306/tcp': [{'HostIp': '127.0.0.1', 'HostPort': '12345'}]}},
                'State': {'OOMKilled': False}}

    def guard(self, value):
        c.container_guard(value, 'a'*64, 'own-db', 'own', 'sha256:fixed', 'own', [('new-db', '/var/lib/mysql', 'rw')])

    def test_foreign_id_name_label_image_or_network_never_adopted(self):
        self.guard(self.container())
        mutations = [lambda v: v.update(Id='b'*64), lambda v: v.update(Name='/foreign'),
            lambda v: v['Config']['Labels'].update({c.LABEL: 'foreign'}), lambda v: v.update(Image='sha256:other'),
            lambda v: v['NetworkSettings']['Networks'].update(foreign={})]
        for mutate in mutations:
            value = self.container(); mutate(value)
            with self.assertRaises(RuntimeError): self.guard(value)

    def test_exact_volumes_accept_explicit_rw_but_not_foreign_ro_or_duplicate(self):
        value = self.container(); value['HostConfig']['Binds'] = ['new-db:/var/lib/mysql']; self.guard(value)
        for binds in (['old-db:/var/lib/mysql:rw'], ['new-db:/var/lib/mysql:ro'], ['new-db:/var/lib/mysql:rw']*2,
                      ['new-db:/var/lib/mysql:rw', 'foreign:/other:rw']):
            value = self.container(); value['HostConfig']['Binds'] = binds
            with self.assertRaises(RuntimeError): self.guard(value)

    def test_only_numeric_loopback_published_port_is_accepted(self):
        self.assertEqual(c.bound_port(self.container(), 3306), 12345)
        for entry in ({'HostIp': '0.0.0.0', 'HostPort': '12345'}, {'HostIp': '::', 'HostPort': '12345'},
                      {'HostIp': '127.0.0.1', 'HostPort': '0'}, {'HostIp': '127.0.0.1', 'HostPort': '70000'}):
            value = self.container(); value['NetworkSettings']['Ports']['3306/tcp'] = [entry]
            with self.assertRaises(RuntimeError): c.bound_port(value, 3306)
        value = self.container(); value['NetworkSettings']['Ports']['3901/tcp'] = None
        self.assertEqual(c.bound_port(value, 3306), 12345)
        value['NetworkSettings']['Ports']['3901/tcp'] = [{'HostIp': '127.0.0.1', 'HostPort': '12346'}]
        with self.assertRaises(RuntimeError): c.bound_port(value, 3306)

    def xml(self, directory, name, methods):
        root = ET.Element('testsuite', name=name, tests=str(len(methods)), failures='0', errors='0', skipped='0')
        props = ET.SubElement(root, 'properties'); ET.SubElement(props, 'property', name='user.timezone', value='Asia/Seoul')
        for method in methods: ET.SubElement(root, 'testcase', name=method)
        path = directory / ('TEST-'+name+'.xml'); ET.ElementTree(root).write(path); return path

    def reports(self, directory):
        self.xml(directory, 'io.github.devdooly.platformlab.jobs.GarageRawSourceIT', c.RAW_CASES)
        return self.xml(directory, 'io.github.devdooly.platformlab.jobs.exporting.VerifiedResultExportIT', [c.EXPORT_CASE])

    def test_exact_existing_five_cases_required_not_maven_exit_alone(self):
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp); path = self.reports(directory)
            self.assertEqual(c.test_summary(directory), {'tests': 5, 'failures': 0, 'errors': 0, 'skipped': 0})
            root = ET.parse(path); root.getroot().find('testcase').set('name', 'unrelated'); root.write(path)
            with self.assertRaises(RuntimeError): c.test_summary(directory)

    def test_failure_skip_and_wrong_timezone_fail_closed(self):
        for tag in ('failure', 'error', 'skipped', 'timezone'):
            with tempfile.TemporaryDirectory() as temp:
                directory = Path(temp); path = self.reports(directory); tree = ET.parse(path)
                if tag == 'timezone': tree.getroot().find('./properties/property').set('value', 'UTC')
                else: ET.SubElement(tree.getroot().find('testcase'), tag)
                tree.write(path)
                with self.assertRaises(RuntimeError): c.test_summary(directory)

    def test_no_persistence_or_crash_case_selected(self):
        self.assertEqual(len(c.RAW_CASES), 4)
        self.assertNotIn('objectPersistsAcrossContainerRecreation', c.SELECTION)
        self.assertNotIn('forciblyKilled', c.SELECTION)
        self.assertIn('VerifiedResultExportIT#'+c.EXPORT_CASE, c.SELECTION)

    def test_oom_or_restart_policy_change_is_not_normal_cleanup(self):
        for mutate in (lambda v: v['State'].update(OOMKilled=True),
                       lambda v: v['HostConfig']['RestartPolicy'].update(Name='always')):
            value = self.container(); mutate(value)
            with self.assertRaises(RuntimeError): self.guard(value)

    def test_private_receipts_cannot_be_overwritten(self):
        # The portable test measures real O_EXCL/no-overwrite behavior. Windows
        # lacks O_NOFOLLOW; only that flag is zeroed here, never in production.
        with mock.patch.object(c.os, 'O_NOFOLLOW', getattr(c.os, 'O_NOFOLLOW', 0), create=True), tempfile.TemporaryDirectory() as temp:
            path = Path(temp)/'intent.json'; c.save_json(path, {'once': True})
            with self.assertRaises(FileExistsError): c.save_json(path, {'retry': True})
            self.assertEqual(path.read_text().count('true'), 1)

    def test_expired_main_deadline_does_not_block_exact_owned_term_cleanup(self):
        with tempfile.TemporaryDirectory() as temp:
            attempt = c.Attempt(Path(temp), 'own'); attempt.deadline = -1
            attempt.created = [{'id': 'a'*64}]
            running = {'State': {'Running': True, 'ExitCode': 0}}
            stopped = {'State': {'Running': False, 'ExitCode': 143}}
            with mock.patch.object(attempt, 'guard', side_effect=[running, stopped]) as guard, \
                 mock.patch.object(attempt, 'command', return_value=(0, b'')) as command, mock.patch.object(c.time, 'sleep'):
                self.assertTrue(attempt.stop())
            self.assertTrue(all(call.kwargs == {'bounded': False} for call in guard.call_args_list))
            command.assert_called_once_with(['docker', 'kill', '--signal=TERM', 'a'*64], bounded=False, timeout=10)


if __name__ == '__main__':
    unittest.main()
