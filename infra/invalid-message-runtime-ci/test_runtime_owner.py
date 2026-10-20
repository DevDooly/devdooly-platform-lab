"""Pure Docker-inspect/transition fixtures; never contacts a Docker daemon."""
from pathlib import Path
import copy
import json
import tempfile
import time
import unittest
import runtime_owner as owner


class DockerFixture:
    def __init__(self):
        self.values, self.calls = {}, []

    def save_state(self, task, state):
        pass

    def command(self, args, deadline, **options):
        self.calls.append(args)
        if args[:2] != ['/usr/bin/docker', '--host=unix:///var/run/docker.sock']:
            raise AssertionError('unexpected transport')
        args = args[2:]
        if args[0] == 'inspect' or args[:2] == ['network', 'inspect']:
            return 0, json.dumps([self.values[args[-1]]]).encode(), b''
        if args[0] in ('unpause', 'stop'):
            value = self.values[args[-1]]
            status = {'unpause': 'running', 'stop': 'exited'}[args[0]]
            value['State'].update(Status=status, Running=status != 'exited', Paused=status == 'paused')
            return 0, b'', b''
        if args[0] == 'rm' or args[:2] == ['network', 'rm']:
            self.values.pop(args[-1])
            return 0, b'', b''
        if args[:2] == ['ps', '-a'] or args[:2] == ['network', 'ls']:
            needle = next((x[3:] for x in args if x.startswith('id=')), None)
            return 0, (needle.encode() if needle in self.values else b''), b''
        raise AssertionError('unexpected operation')


def fixture(directory):
    base = DockerFixture()
    state = dict(schemaVersion=1, scope='ISOLATED_INVALID_MESSAGE_RUNTIME',
                 runId='123', sourceCommit='a' * 40, nonce='b' * 32, runtimeUser='1001:1001', resources=[])
    owned = owner.OwnedDocker(base, Path(directory), state, time.monotonic() + 30)
    created = '2026-10-20T01:00:00Z'
    network = dict(kind='network', name=owned.prefix + '-network', id='1' * 64,
                   phase='CREATED', createdAt=created)
    state['resources'].append(network)
    base.values[network['id']] = dict(Id=network['id'], Name=network['name'], Created=created,
        Internal=True, Driver='bridge', Labels=dict(owned.labels))
    profile = dict(memory=owner.MEMORY['kafka'], tmpfs=copy.deepcopy(owner.TMPFS['kafka']),
        readonly=False, user='1000:1000', env={'PATH': '/usr/bin'}, entrypoint=None,
        cmd=['/etc/kafka/docker/run'], binds={})
    broker = dict(kind='container', role='kafka', name=owned.prefix + '-kafka', id='2' * 64,
        phase='CREATED', createdAt=created, startedAt=created, image=owner.IMAGES['kafka'],
        imageId='sha256:' + '3' * 64, networkMode=network['id'], profile=profile)
    state['resources'].append(broker)
    base.values[broker['id']] = dict(Id=broker['id'], Name='/' + broker['name'], Created=created,
        Image=broker['imageId'], RestartCount=0,
        State=dict(Status='running', Running=True, Paused=False, StartedAt=created, ExitCode=0, OOMKilled=False),
        Config=dict(Image=broker['image'], User=profile['user'], Entrypoint=None, Cmd=profile['cmd'],
                    Env=['PATH=/usr/bin'], Labels=dict(owned.labels), Volumes=None),
        HostConfig=dict(NetworkMode=network['id'], PortBindings={}, Binds=None, Privileged=False,
            ReadonlyRootfs=False, NanoCpus=1000000000, Memory=1073741824, MemorySwap=1073741824,
            PidsLimit=256, AutoRemove=False, RestartPolicy={'Name': 'no', 'MaximumRetryCount': 0},
            CapAdd=None, CapDrop=['ALL'], SecurityOpt=['no-new-privileges'], PidMode='', UTSMode='',
            UsernsMode='', IpcMode='private', Devices=None, DeviceRequests=None, VolumesFrom=None,
            Links=None, Tmpfs=copy.deepcopy(profile['tmpfs']), Mounts=[]),
        Mounts=[], NetworkSettings={'Networks': {'fixture': {'NetworkID': network['id']}}})
    return owned, base, state, network, broker


class OwnerTest(unittest.TestCase):
    def test_environment_duplicate_or_malformed_keys_are_not_merged_silently(self):
        self.assertEqual({'A': 'x=y'}, owner.env_map(['A=x=y']))
        for value in (['A=x', 'A=y'], ['missing'], ['bad-key=x'], {'A': 'x'}, ['A=' + 'x' * 16384]):
            with self.assertRaises(ValueError):
                owner.env_map(value)

    def test_network_identity_creation_and_owner_are_checked_before_any_mutation(self):
        with tempfile.TemporaryDirectory() as directory:
            owned, base, state, network, _ = fixture(directory)
            self.assertEqual(network['id'], owned.inspect(network)['Id'])
            original = copy.deepcopy(base.values[network['id']])
            for key, val in (('Id', 'f' * 64), ('Name', 'foreign'), ('Created', '2026-10-19T01:00:00Z'),
                             ('Internal', False), ('Driver', 'host'), ('Labels', {})):
                base.values[network['id']] = dict(original, **{key: val})
                with self.subTest(key=key), self.assertRaises(ValueError):
                    owned.inspect(network)
            self.assertTrue(all(call[2:4] == ['network', 'inspect'] for call in base.calls))

    def test_running_container_rejects_restarts_published_ports_and_extra_mounts(self):
        with tempfile.TemporaryDirectory() as directory:
            owned, base, state, _, broker = fixture(directory)
            self.assertEqual('running', owned.inspect(broker)['State']['Status'])
            original = copy.deepcopy(base.values[broker['id']])
            changes = [lambda v: v.update(RestartCount=1),
                       lambda v: v['State'].update(StartedAt='2026-10-20T02:00:00Z'),
                       lambda v: v['HostConfig'].update(PortBindings={'19092/tcp': [{'HostPort': '19092'}]}),
                       lambda v: v['Mounts'].append({'Type': 'volume', 'Destination': '/foreign'}),
                       lambda v: v['HostConfig'].update(Memory=2147483648),
                       lambda v: v['Config'].update(Env=['PATH=/usr/bin', 'UNEXPECTED=private'])]
            for change in changes:
                base.values[broker['id']] = copy.deepcopy(original)
                change(base.values[broker['id']])
                with self.assertRaises(ValueError):
                    owned.inspect(broker)
            self.assertTrue(all(call[2] == 'inspect' for call in base.calls))

    def test_bind_source_and_writable_bit_must_match_requested_and_actual_mounts(self):
        profile = {'tmpfs': {}, 'binds': {'/owned/settings.xml': ['/private/settings.xml', False]}}
        good = dict(HostConfig={'Tmpfs': {}, 'Mounts': [{'Type': 'bind', 'Target': '/owned/settings.xml',
                     'Source': '/private/settings.xml', 'ReadOnly': True}]}, Config={'Volumes': None},
                    Mounts=[{'Type': 'bind', 'Destination': '/owned/settings.xml', 'Source': '/private/settings.xml',
                             'RW': False, 'Propagation': 'rprivate'}])
        owner.mount_check(good, profile)
        for field, val in (('Source', '/etc'), ('RW', True), ('Propagation', 'shared')):
            bad = copy.deepcopy(good); bad['Mounts'][0][field] = val
            with self.assertRaises(ValueError):
                owner.mount_check(bad, profile)
        bad = copy.deepcopy(good); bad['HostConfig']['Mounts'][0]['ReadOnly'] = False
        with self.assertRaises(ValueError):
            owner.mount_check(bad, profile)

    def test_unexpected_paused_broker_is_not_accepted_or_unpaused_on_normal_path(self):
        with tempfile.TemporaryDirectory() as directory:
            owned, base, state, _, broker = fixture(directory)
            base.values[broker['id']]['State'].update(Status='paused', Running=True, Paused=True)
            with self.assertRaises(ValueError):
                owned.inspect(broker, allow_paused=True)
            with self.assertRaises(ValueError):
                owned.inspect(broker)
            with self.assertRaises(ValueError):
                owned.unpause(broker)
            self.assertFalse(any(call[2] in ('pause', 'unpause', 'stop', 'rm') for call in base.calls))

    def test_cleanup_unpauses_exact_owned_broker_before_stop_and_removes_network_last(self):
        with tempfile.TemporaryDirectory() as directory:
            owned, base, state, network, broker = fixture(directory)
            base.values[broker['id']]['State'].update(Status='paused', Running=True, Paused=True)
            self.assertTrue(owned.cleanup())
            mutations = [call[2:] for call in base.calls if call[2] in ('unpause', 'stop', 'rm')
                         or call[2:4] == ['network', 'rm']]
            self.assertEqual([['unpause', broker['id']], ['stop', '--time', '10', broker['id']],
                              ['rm', broker['id']], ['network', 'rm', network['id']]], mutations)
            self.assertTrue(all(row['phase'] == 'REMOVED' for row in state['resources']))

    def test_unknown_create_outcome_and_foreign_labels_are_preserved_as_unverified(self):
        for mode in ('missing-id', 'foreign-label'):
            with tempfile.TemporaryDirectory() as directory:
                owned, base, state, _, broker = fixture(directory)
                if mode == 'missing-id':
                    broker.update(id=None, phase='CREATE_INTENT')
                else:
                    base.values[broker['id']]['Config']['Labels'] = {}
                self.assertFalse(owned.cleanup())
                self.assertFalse(any(call[2] in ('stop', 'rm', 'pause', 'unpause')
                                     or call[2:4] == ['network', 'rm'] for call in base.calls))

    def test_role_image_budget_and_foreign_scope_are_rejected_before_native_calls(self):
        with tempfile.TemporaryDirectory() as directory:
            owned, base, state, _, broker = fixture(directory)
            profile = copy.deepcopy(broker['profile'])
            with self.assertRaises(ValueError):
                owned.container('kafka', owner.IMAGES['jvm'], {}, 'unknown', profile)
            profile['memory'] *= 2
            with self.assertRaises(ValueError):
                owned.container('kafka', owner.IMAGES['kafka'], {}, 'unknown', profile)
            for changes in ({'schemaVersion': True}, {'scope': 'ISOLATED_REAL_OFFSET_COMMIT_RECOVERY'}):
                with self.assertRaises(ValueError):
                    owner.OwnedDocker(base, Path(directory), dict(state, **changes), time.monotonic() + 30)
            self.assertEqual([], base.calls)


if __name__ == '__main__':
    unittest.main()
