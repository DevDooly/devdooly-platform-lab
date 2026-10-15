import copy
import json
import tempfile
import time
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

    def requested_and_active(self):
        value = self.container()
        value['HostConfig']['PortBindings'] = {'3306/tcp': [{'HostIp': '127.0.0.1', 'HostPort': ''}]}
        value['State']['Running'] = True
        return value

    def test_port_projection_separates_ephemeral_request_from_active_allocation(self):
        value = self.requested_and_active()
        result = c.port_binding_diagnostic(value, 3306)
        self.assertEqual(result['requestedMapState'], 'SINGLE_BINDING')
        self.assertEqual(result['activeMapState'], 'SINGLE_BINDING')
        self.assertTrue(all(result[key] for key in ('containerRunningObserved', 'requestedSingleLoopbackBinding',
            'requestedEmptyOrZeroHostPort', 'requestedOnlyRequiredPort', 'activeSingleLoopbackBinding',
            'activeNumericHostPort', 'activeOnlyRequiredPublishedPort', 'requestedAndActiveLoopbackConsistent')))
        self.assertEqual(c.bound_port(value, 3306), 12345)

    def test_requested_loopback_port_never_substitutes_for_missing_or_unpublished_active_port(self):
        for ports, expected in (({}, 'TARGET_MISSING'), ({'3306/tcp': None}, 'TARGET_UNPUBLISHED'),
                                 ({'3306/tcp': []}, 'TARGET_INVALID_COUNT')):
            value = self.requested_and_active(); value['NetworkSettings']['Ports'] = ports
            result = c.port_binding_diagnostic(value, 3306)
            self.assertTrue(result['requestedSingleLoopbackBinding'])
            self.assertEqual(result['activeMapState'], expected)
            self.assertFalse(result['activeNumericHostPort'])
            self.assertFalse(result['activeOnlyRequiredPublishedPort'])
            with self.assertRaises(RuntimeError): c.bound_port(value, 3306)

    def test_partial_inspect_fields_are_unobserved_not_verified(self):
        for value in ({}, {'HostConfig': {}, 'NetworkSettings': {}, 'State': {}},
                      {'HostConfig': {'PortBindings': None}, 'NetworkSettings': {'Ports': None}}):
            result = c.port_binding_diagnostic(value, 3306)
            self.assertIn(result['requestedMapState'], ('UNOBSERVED', 'MALFORMED'))
            self.assertIn(result['activeMapState'], ('UNOBSERVED', 'MALFORMED'))
            self.assertTrue(all(item is False for item in result.values() if isinstance(item, bool)))

    def test_port_projection_is_bounded_and_contains_no_raw_connection_or_container_fields(self):
        value = self.requested_and_active()
        value['Config']['Env'] = ['SECRET=never-publish-this-value']
        value['NetworkSettings']['Ports']['3306/tcp'][0]['HostPort'] = '9'*10000
        result = c.port_binding_diagnostic(value, 3306)
        self.assertFalse(result['activeNumericHostPort'])
        self.assertEqual(set(result), {'schemaVersion', 'scope', 'containerRunningObserved', 'requestedMapState',
            'activeMapState', 'requestedSingleLoopbackBinding', 'requestedEmptyOrZeroHostPort',
            'requestedOnlyRequiredPort', 'activeSingleLoopbackBinding', 'activeNumericHostPort',
            'activeOnlyRequiredPublishedPort', 'requestedAndActiveLoopbackConsistent'})
        encoded = json.dumps(result)
        for private in ('never-publish-this-value', '127.0.0.1', 'own-db', 'new-db', 'a'*64, '9'*100):
            self.assertNotIn(private, encoded)

    def test_public_port_diagnostic_does_not_accept_nonloopback_or_extra_active_binding(self):
        value = self.requested_and_active()
        value['NetworkSettings']['Ports']['3306/tcp'][0]['HostIp'] = '0.0.0.0'
        result = c.port_binding_diagnostic(value, 3306)
        self.assertFalse(result['activeSingleLoopbackBinding'])
        with self.assertRaises(RuntimeError): c.bound_port(value, 3306)
        value = self.requested_and_active()
        value['NetworkSettings']['Ports']['other/tcp'] = [{'HostIp': '127.0.0.1', 'HostPort': '12346'}]
        self.assertFalse(c.port_binding_diagnostic(value, 3306)['activeOnlyRequiredPublishedPort'])
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

    def relay_scope(self):
        value = self.container()
        value['HostConfig'].update(Memory=1024, MemorySwap=1024, NanoCpus=1000000000, PortBindings={}, PublishAllPorts=False)
        value['NetworkSettings']['Ports'] = {'3306/tcp': None}
        value['NetworkSettings']['Networks']['own'] = {'NetworkID':'b'*64, 'EndpointID':'c'*64, 'IPAddress':'172.25.0.2'}
        value['State'].update(Running=True, Pid=123, StartedAt='fixed')
        value['RestartCount'] = 0
        item = {'id':'a'*64, 'name':'own-db', 'imageId':'sha256:fixed', 'network':'own',
                'binds':[('new-db','/var/lib/mysql','rw')], 'memory':1024, 'nanoCpus':1000000000}
        network = {'Name':'own', 'Id':'b'*64, 'Internal':True, 'Driver':'bridge', 'Scope':'local',
                   'Labels':{c.LABEL:'own'}, 'IPAM':{'Config':[{'Subnet':'172.25.0.0/16'}]},
                   'Containers':{'a'*64:{'Name':'own-db','EndpointID':'c'*64,'IPv4Address':'172.25.0.2/16'}}}
        return value, network, item

    def test_relay_target_requires_exact_internal_endpoint_and_unrestarted_process(self):
        value, network, item = self.relay_scope()
        self.assertEqual(c.verified_internal_target(value,network,item,'own',3306), ('172.25.0.2',3306))
        mutations = [lambda v,n:v['NetworkSettings']['Networks']['own'].update(NetworkID='d'*64),
                     lambda v,n:n.update(Internal=False), lambda v,n:n['IPAM']['Config'][0].update(Subnet='172.26.0.0/16'),
                     lambda v,n:v.update(RestartCount=1), lambda v,n:v['State'].update(Running=False),
                     lambda v,n:n['Containers']['a'*64].update(IPv4Address='172.25.0.3/16'),
                     lambda v,n:v['HostConfig'].update(PortBindings={'3306/tcp':[{'HostIp':'127.0.0.1','HostPort':''}]})]
        for mutate in mutations:
            v,n,i = self.relay_scope(); mutate(v,n)
            with self.assertRaises(RuntimeError):c.verified_internal_target(v,n,i,'own',3306)

    def test_relay_target_does_not_accept_foreign_id_image_spec_or_ports(self):
        for mutate in (lambda v:v.update(Id='d'*64), lambda v:v.update(Image='sha256:foreign'),
                       lambda v:v['HostConfig'].update(Memory=2048), lambda v:v['HostConfig'].update(NanoCpus=2),
                       lambda v:v['HostConfig'].update(Binds=['foreign:/var/lib/mysql:rw'])):
            value, network, item = self.relay_scope();mutate(value)
            with self.assertRaises(RuntimeError):c.verified_internal_target(value,network,item,'own',3306)
        value,network,item=self.relay_scope()
        with self.assertRaises(RuntimeError):c.verified_internal_target(value,network,item,'own',22)

    def test_relay_fresh_callbacks_are_bounded_independent_readonly_and_bind_same_process_spec(self):
        initial, network, item = self.relay_scope()
        initial['Mounts'] = [{'Source':'new-db','Destination':'/var/lib/mysql'}]
        attempt = mock.Mock(project='own')
        attempt.guard.return_value = initial
        attempt.command.return_value = (0,json.dumps([network]).encode())
        value = c.create_owned_relay(attempt,item,3306,time.monotonic()+100)
        live = copy.deepcopy(initial)
        response = lambda obj: mock.Mock(returncode=0,stdout=json.dumps([obj]).encode())
        with mock.patch.object(c.subprocess,'run',side_effect=[response(live),response(network)]) as read:
            self.assertEqual(value.verify_target(),('172.25.0.2',3306))
            self.assertTrue(all(0 < call.kwargs['timeout'] <= 2 for call in read.call_args_list))
            self.assertEqual([call.args[0][:2] for call in read.call_args_list],[['docker','inspect'],['docker','network']])
        self.assertEqual(attempt.guard.call_count,1)
        self.assertEqual(attempt.command.call_count,1)
        for mutate in (lambda v:v['State'].update(Pid=124),lambda v:v['State'].update(StartedAt='different'),
                       lambda v:v['Config'].update(Env=['foreign']),lambda v:v['Mounts'][0].update(Source='foreign')):
            live=copy.deepcopy(initial);mutate(live)
            with mock.patch.object(c.subprocess,'run',side_effect=[response(live),response(network)]):
                with self.assertRaises(RuntimeError):value.verify_target()


if __name__ == '__main__':
    unittest.main()
