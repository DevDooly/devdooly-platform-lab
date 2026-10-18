"""Offline failure-boundary fixtures only. No Docker, Java, sockets or network are started."""
from pathlib import Path
import copy
import importlib.util
import json
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('kafka_observation_runner', Path(__file__).with_name('run_once.py'))
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)

class BoundaryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def state(self):
        return {'nonce': 'b' * 32, 'sourceCommit': 'a' * 40, 'runId': '123', 'resources': []}

    def network_fixture(self):
        stamp = (runner.dt.datetime.now(runner.dt.timezone.utc) - runner.dt.timedelta(seconds=1)).isoformat().replace('+00:00', 'Z')
        row = {'kind': 'network', 'name': 'owned', 'id': 'c' * 64, 'phase': 'CREATED', 'intendedAt': stamp, 'createdAt': stamp}
        value = {'Id': row['id'], 'Name': 'owned', 'Created': stamp, 'Labels': {runner.LABEL: 'b' * 32,
            runner.LABEL + '.source': 'a' * 40, runner.LABEL + '.run': '123'}, 'Internal': True, 'Driver': 'bridge'}
        return row, value

    def container_fixture(self, role='broker'):
        state = self.state(); network, _ = self.network_fixture(); state['resources'].append(network)
        row = {'kind': 'container', 'name': 'owned-' + role, 'id': 'd' * 64, 'phase': 'CREATED', 'role': role,
            'createdAt': network['createdAt'], 'intendedAt': network['intendedAt'], 'image': runner.KAFKA,
            'imageId': 'sha256:' + 'e' * 64, 'networkMode': network['id']}
        state['resources'].append(row)
        host = {'NetworkMode': network['id'], 'PortBindings': {}, 'Binds': None, 'NanoCpus': 1000000000,
            'Memory': 1073741824, 'MemorySwap': 1073741824, 'PidsLimit': 256, 'Privileged': False,
            'ReadonlyRootfs': False, 'CapDrop': ['ALL'], 'CapAdd': None, 'SecurityOpt': ['no-new-privileges'],
            'PidMode': '', 'IpcMode': 'private', 'UTSMode': '', 'UsernsMode': '', 'Devices': None,
            'DeviceRequests': None, 'VolumesFrom': None, 'Links': None, 'Mounts': None,
            'Tmpfs': {'/var/lib/kafka/data': runner.BROKER_TMPFS.split(':', 1)[1]}}
        value = {'Id': row['id'], 'Name': '/' + row['name'], 'Created': row['createdAt'], 'Image': row['imageId'],
            'Config': {'Image': row['image'], 'User': '1000:1000', 'Labels': {runner.LABEL: 'b' * 32,
                runner.LABEL + '.source': 'a' * 40, runner.LABEL + '.run': '123'}, 'Volumes': {'/var/lib/kafka/data': {}}},
            'HostConfig': host, 'State': {'Running': False, 'Status': 'created', 'StartedAt': '0001-01-01T00:00:00Z'},
            'NetworkSettings': {'Networks': {network['name']: {'NetworkID': ''}}}, 'Mounts': []}
        if role == 'jvm':
            broker = dict(row, role='broker', name='owned-broker', id='f' * 64); state['resources'].insert(1, broker)
            state['runtimeUser'] = '1001:1001'; state['mavenRelativePath'] = 'wrapper-home/maven'
            for relative in ('it-api', 'repository', 'wrapper-home/maven'): (self.root / relative).mkdir(parents=True, exist_ok=True)
            (self.root / 'settings.xml').write_text('fixture')
            row['networkMode'] = 'container:' + broker['id']; row['image'] = runner.JDK
            value['Config'].update(Image=runner.JDK, User='1001:1001', Volumes=None)
            host.update(NetworkMode=row['networkMode'], ReadonlyRootfs=True, Tmpfs={'/tmp': runner.JVM_TMPFS.split(':', 1)[1]})
            bindings = [('it-api', '/owned/api', True), ('repository', '/owned/repository', True),
                ('wrapper-home/maven', '/owned/maven', False), ('settings.xml', '/owned/settings.xml', False)]
            host['Mounts'] = [{'Type': 'bind', 'Source': str((self.root / source).resolve()), 'Target': target,
                **({} if writable else {'ReadOnly': True})} for source, target, writable in bindings]
            value['Mounts'] = [{'Type': 'bind', 'Source': str((self.root / source).resolve()), 'Destination': target,
                'RW': writable, 'Propagation': 'rprivate'} for source, target, writable in bindings]
        return state, row, value

    def xml(self, **attributes):
        values = {'name': runner.CLASS, 'tests': '1', 'failures': '0', 'errors': '0', 'skipped': '0'}
        values.update(attributes)
        path = self.root / 'report.xml'
        path.write_text('<testsuite ' + ' '.join(key + '="' + value + '"' for key, value in values.items()) + '>' +
            '<properties><property name="java.specification.version" value="21"/><property name="os.name" value="Linux"/></properties>' +
            '<testcase classname="' + runner.CLASS + '" name="' + runner.METHOD + '"/></testsuite>', encoding='utf8')
        return path

    def test_exact_one_it_zero_skips_and_linux_java21_is_required(self):
        self.assertRegex(runner.verify_xml(self.xml()), r'^[a-f0-9]{64}$')
        for key, value in [('tests', '0'), ('tests', '2'), ('skipped', '1'), ('failures', '1'), ('errors', '1'), ('name', 'OtherTest')]:
            with self.subTest(key=key, value=value), self.assertRaises(runner.Failure):
                runner.verify_xml(self.xml(**{key: value}))

    def test_wrong_method_or_additional_testcase_is_rejected(self):
        path = self.xml()
        original = path.read_text()
        for text in (original.replace(runner.METHOD, 'different'), original.replace('</testsuite>', '<testcase/></testsuite>')):
            path.write_text(text)
            with self.assertRaises(runner.Failure): runner.verify_xml(path)

    def test_xml_doctype_and_embedded_skip_are_rejected(self):
        path = self.xml(); original = path.read_text()
        for text in ('<!DOCTYPE testsuite>' + original, original.replace('/></testsuite>', '><skipped/></testcase></testsuite>')):
            path.write_text(text)
            with self.assertRaises(runner.Failure): runner.verify_xml(path)

    def test_xml_other_runtime_is_not_a_linux_java21_pass(self):
        path = self.xml(); original = path.read_text()
        for text in (original.replace('value="21"', 'value="25"'), original.replace('value="Linux"', 'value="Windows"')):
            path.write_text(text)
            with self.assertRaises(runner.Failure): runner.verify_xml(path)

    def test_duplicate_json_keys_are_not_last_value_wins(self):
        path = self.root / 'duplicate.json'; path.write_text('{"phase":"PREPARED","phase":"CLEANED"}')
        with self.assertRaises(runner.Failure): runner.load_json(path)

    def test_failed_or_unconfirmed_cleanup_cannot_publish_pass(self):
        for xml, unchanged, clean in [(None, True, True), ('c' * 64, False, True), ('c' * 64, True, False)]:
            with self.subTest(xml=xml, unchanged=unchanged, clean=clean), self.assertRaises(runner.Failure):
                runner.public_summary('a' * 40, 'b' * 64, 'PASSED', None, xml, unchanged, clean)
        value = runner.public_summary('a' * 40, 'b' * 64, 'FAILED', 'IT_FAILED', None, False, True)
        self.assertFalse(value['testSourceAssertionsVerified']); self.assertEqual(value['verifiedTests'], 0)
        self.assertIsNone(value['skips'])

    def test_public_summary_is_a_fixed_allowlist_and_no_new_numeric_observation(self):
        value = runner.public_summary('a' * 40, 'b' * 64, 'PASSED', None, 'c' * 64, True, True)
        self.assertEqual(set(value), {'schemaVersion', 'kind', 'scope', 'synthetic', 'publicExecutionEnabled',
            'sourceCommit', 'runtimeManifestSha256', 'status', 'failureCode', 'expectedTests', 'verifiedTests', 'skips',
            'testSourceAssertionsVerified', 'surefireXmlSha256', 'sourceBytesUnchanged', 'ownedResourcesRemoved',
            'httpOrMiniPcRuntimeVerified', 'kafkaAclVerified', 'allJvmThreadsVerified'})
        for field in ('publicExecutionEnabled', 'httpOrMiniPcRuntimeVerified', 'kafkaAclVerified', 'allJvmThreadsVerified'):
            self.assertIs(value[field], False)

    def test_expired_parent_deadline_starts_no_process(self):
        with patch.object(runner.time, 'monotonic', return_value=100), patch.object(runner.subprocess, 'Popen') as process:
            with self.assertRaises(runner.Failure) as caught: runner.command(['UNUSED'], 99)
            self.assertEqual(caught.exception.code, 'DEADLINE_EXCEEDED'); process.assert_not_called()

    def test_unknown_create_id_is_latched_without_retry_or_speculative_delete(self):
        calls = []
        def execute(args, deadline, **kwargs):
            calls.append(args)
            return (0, b'', b'') if len(calls) == 1 else (0, b'not-a-container-id', b'')
        state = self.state(); owned = runner.OwnedDocker(self.root, state, 100, execute)
        name = 'platform-kafka-observation-123-' + 'b' * 32 + '-network'
        with self.assertRaises(runner.Failure): owned.create('network', name, ['network', 'create', name])
        self.assertEqual(state['resources'][0]['phase'], 'CREATE_INTENT')
        self.assertFalse(owned.cleanup()); self.assertEqual(len(calls), 2)
        self.assertFalse(any('rm' in call or 'stop' in call for call in calls))

    def test_create_timeout_stops_before_inspect_or_next_create(self):
        calls = []
        def execute(args, deadline, **kwargs):
            calls.append(args)
            if len(calls) == 1: return (0, b'', b'')
            raise runner.Failure('DEADLINE_EXCEEDED')
        state = self.state(); owned = runner.OwnedDocker(self.root, state, 100, execute)
        name = 'platform-kafka-observation-123-' + 'b' * 32 + '-network'
        with self.assertRaises(runner.Failure) as caught: owned.create('network', name, ['network', 'create', name])
        self.assertEqual(caught.exception.code, 'UNKNOWN_OUTCOME')
        self.assertFalse(owned.cleanup()); self.assertEqual(len(calls), 2)

    def test_identity_mismatch_prevents_any_stop_or_remove(self):
        calls = []; state = self.state()
        row, value = self.network_fixture(); state['resources'].append(row)
        value['Labels'] = {runner.LABEL: 'wrong'}
        def execute(args, deadline, **kwargs):
            calls.append(args)
            return (0, json.dumps([value]).encode(), b'')
        owned = runner.OwnedDocker(self.root, state, 100, execute)
        self.assertFalse(owned.cleanup()); self.assertEqual(len(calls), 1)
        self.assertNotIn('rm', calls[0])

    def test_successful_remove_still_requires_daemon_confirmed_absence(self):
        calls = []; state = self.state()
        row, value = self.network_fixture(); state['resources'].append(row)
        def execute(args, deadline, **kwargs):
            calls.append(args)
            if 'inspect' in args:
                return (0, json.dumps([value]).encode(), b'')
            if 'rm' in args: return (0, b'', b'')
            return (1, b'', b'unknown daemon outcome')
        owned = runner.OwnedDocker(self.root, state, 100, execute)
        self.assertFalse(owned.cleanup()); self.assertNotEqual(row['phase'], 'REMOVED')
        self.assertEqual([item for item in calls if 'rm' in item][0][-1], row['id'])

    def test_docker_uses_only_local_socket_and_empty_owned_config(self):
        calls = []
        def execute(args, deadline, **kwargs): calls.append((args, kwargs)); return (0, b'', b'')
        owned = runner.OwnedDocker(self.root, self.state(), 100, execute)
        owned.call(['info'])
        self.assertEqual(calls[0][0][:2], ['/usr/bin/docker', '--host=unix:///var/run/docker.sock'])
        self.assertEqual(set(calls[0][1]['environment']), {'PATH', 'LANG', 'DOCKER_CONFIG'})
        self.assertTrue(Path(calls[0][1]['environment']['DOCKER_CONFIG']).is_relative_to(self.root))

    def test_payload_mutation_is_detected_by_artifact_snapshot(self):
        folder = self.root / 'repo'; folder.mkdir(); jar = folder / 'client.jar'; jar.write_bytes(b'original')
        before = runner.artifact_snapshot(folder); jar.write_bytes(b'changed')
        self.assertNotEqual(before, runner.artifact_snapshot(folder))

    def test_tool_script_mutation_is_not_ignored_like_repository_metadata(self):
        folder = self.root / 'maven'; folder.mkdir(); script = folder / 'mvn'; script.write_bytes(b'original')
        before = runner.tool_snapshot(folder); script.write_bytes(b'changed')
        self.assertNotEqual(before, runner.tool_snapshot(folder))

    def source_fixture(self):
        files = []
        content = {**{'apps/api/fixture-' + str(index) + '.java': b'x' for index in range(106)},
            'infra/kafka-observation-ci/run_once.py': b'x', 'infra/kafka-observation-ci/test_run_once.py': b'x',
            'infra/image-lock.json': json.dumps({'images': {'apache/kafka:4.3.1': runner.KAFKA,
                'eclipse-temurin:21-jdk': runner.JDK}}).encode()}
        for relative, data in content.items():
            path = self.root / relative; path.parent.mkdir(parents=True, exist_ok=True); path.write_bytes(data)
            files.append({'path': relative, 'sha256': runner.digest(data), 'bytes': len(data)})
        path = self.root / 'infra/kafka-observation-ci/runtime-manifest.json'
        path.write_text(json.dumps({'schemaVersion': 1, 'scope': 'HOSTED_LINUX_KAFKA_IT_SOURCE_ONLY', 'files': files}))
        return runner.digest(path.read_bytes())

    def test_pinned_source_mutation_fails_before_any_subprocess(self):
        expected = self.source_fixture(); runner.source_snapshot(self.root, expected)
        (self.root / 'apps/api/fixture-0.java').write_bytes(b'mutated')
        with patch.object(runner.subprocess, 'Popen') as process, self.assertRaises(runner.Failure) as caught:
            runner.source_snapshot(self.root, expected)
        self.assertEqual(caught.exception.code, 'SOURCE_CHANGED'); process.assert_not_called()

    def test_unpinned_extra_api_source_or_extension_is_rejected(self):
        expected = self.source_fixture()
        for relative in ('.mvn/extensions.xml', 'src/main/java/target/Injected.java', 'src/test/java/target/Injected.java'):
            path = self.root / 'apps/api' / relative; path.parent.mkdir(parents=True, exist_ok=True); path.write_bytes(b'extra')
            self.assertIn('apps/api/' + relative, runner.api_inventory(self.root / 'apps/api'))
            with self.subTest(relative=relative), self.assertRaises(runner.Failure) as caught: runner.source_snapshot(self.root, expected)
            self.assertEqual(caught.exception.code, 'SOURCE_CHANGED'); path.unlink()

    def test_malformed_inspect_fields_are_failures_instead_of_type_errors(self):
        state, row, valid = self.container_fixture()
        calls = []
        current = [valid]
        def execute(args, deadline, **kwargs): calls.append(args); return (0, json.dumps(current).encode(), b'')
        owned = runner.OwnedDocker(self.root, state, 100, execute)
        for broken in ({'id': None}, {'id': 123}, None):
            with self.subTest(row=broken), self.assertRaises(runner.Failure): owned.inspect(broken)
        for key, item in [('Name', None), ('Config', None), ('HostConfig', []), ('State', None), ('Mounts', None), ('NetworkSettings', None)]:
            value = copy.deepcopy(valid); value[key] = item; current[:] = [value]
            with self.subTest(field=key), self.assertRaises(runner.Failure): owned.inspect(row)

    def test_creation_timestamp_is_latched_then_must_match_exactly(self):
        state = self.state(); row, value = self.network_fixture(); row.pop('createdAt'); state['resources'].append(row)
        def execute(args, deadline, **kwargs): return (0, json.dumps([value]).encode(), b'')
        owned = runner.OwnedDocker(self.root, state, 100, execute)
        owned.inspect(row, initialize=True); self.assertEqual(row['createdAt'], value['Created'])
        value['Created'] = (runner.dt.datetime.now(runner.dt.timezone.utc)).isoformat().replace('+00:00', 'Z')
        with self.assertRaises(runner.Failure): owned.inspect(row)

    def test_actual_container_resource_and_namespace_changes_are_rejected(self):
        state, row, valid = self.container_fixture(); current = [valid]
        def execute(args, deadline, **kwargs): return (0, json.dumps(current).encode(), b'')
        owned = runner.OwnedDocker(self.root, state, 100, execute); owned.inspect(row)
        for field, item in [('NanoCpus', 0), ('Memory', 0), ('MemorySwap', -1), ('PidsLimit', None), ('Privileged', True),
                ('ReadonlyRootfs', True), ('CapAdd', ['NET_ADMIN']), ('CapDrop', []), ('SecurityOpt', []), ('PidMode', 'host'),
                ('IpcMode', 'host'), ('PortBindings', {'9092/tcp': [{'HostPort': '9092'}]})]:
            changed = copy.deepcopy(valid); changed['HostConfig'][field] = item; current[:] = [changed]
            with self.subTest(field=field), self.assertRaises(runner.Failure): owned.inspect(row)

    def test_anonymous_volume_and_non_owned_or_extra_bind_mounts_are_rejected(self):
        state, row, valid = self.container_fixture('jvm'); current = [valid]
        def execute(args, deadline, **kwargs): return (0, json.dumps(current).encode(), b'')
        owned = runner.OwnedDocker(self.root, state, 100, execute); owned.inspect(row)
        changed = copy.deepcopy(valid); changed['Mounts'].append({'Type': 'volume', 'Destination': '/anonymous', 'Source': '/var/lib/docker/volumes/unknown', 'RW': True})
        cases = [changed]
        changed = copy.deepcopy(valid); changed['Mounts'][0]['Source'] = '/etc'; changed['HostConfig']['Mounts'][0]['Source'] = '/etc'; cases.append(changed)
        changed = copy.deepcopy(valid); changed['HostConfig']['Tmpfs'] = {'/tmp': 'rw,size=1073741824'}; cases.append(changed)
        changed = copy.deepcopy(valid); changed['Config']['Volumes'] = {'/anonymous': {}}; cases.append(changed)
        changed = copy.deepcopy(valid); changed['HostConfig']['Mounts'][0]['Target'] = []; cases.append(changed)
        for changed in cases:
            current[:] = [changed]
            with self.subTest(change=changed), self.assertRaises(runner.Failure): owned.inspect(row)

    def test_source_guard_failure_publishes_failed_even_when_cleanup_is_unknown(self):
        environment = {'SOURCE_COMMIT': 'a' * 40, 'GITHUB_RUN_ID': '123'}
        for index, outcome in enumerate((True, False, TypeError('unknown cleanup outcome'))):
            cleaned = outcome is True
            repo = self.root / str(index); task = repo / runner.PRIVATE; task.mkdir(parents=True)
            state = dict(self.state(), schemaVersion=1, phase='PREPARED', prepared=True, manifestSha256='c' * 64)
            runner.write_new(task / 'state.json', state)
            with patch.object(runner, 'hosted_context'), patch.object(runner.os, 'getuid', return_value=1001), patch.object(runner.os, 'getgid', return_value=1001), \
                    patch.object(runner, 'source_snapshot', side_effect=runner.Failure('SOURCE_CHANGED')), \
                    patch.object(runner.OwnedDocker, 'cleanup', return_value=cleaned, side_effect=outcome if isinstance(outcome, Exception) else None), patch.object(runner.subprocess, 'Popen') as process:
                self.assertEqual(runner.run(repo, 'c' * 64, environment), 1); process.assert_not_called()
            summary = runner.load_json(repo / runner.PUBLIC)
            self.assertEqual(summary['status'], 'FAILED'); self.assertEqual(summary['failureCode'], 'SOURCE_CHANGED')
            self.assertIs(summary['sourceBytesUnchanged'], False); self.assertIs(summary['ownedResourcesRemoved'], cleaned)

    def test_normal_api_requires_exact_216_actual_cases_and_zero_skips(self):
        folder = self.root / 'normal'; folder.mkdir()
        report = folder / 'TEST-normal.xml'
        for tests, skipped, cases in [(216, 0, 216), (215, 0, 215), (217, 0, 217), (216, 1, 216), (216, 0, 215)]:
            report.write_text('<testsuite name="normal" tests="' + str(tests) + '" failures="0" errors="0" skipped="' + str(skipped) + '">' +
                ''.join('<testcase name="case-' + str(index) + '"/>' for index in range(cases)) + '</testsuite>')
            if (tests, skipped, cases) == (216, 0, 216): self.assertEqual(runner.verify_normal_api_reports(folder), 216)
            else:
                with self.subTest(tests=tests, skipped=skipped, cases=cases), self.assertRaises(runner.Failure): runner.verify_normal_api_reports(folder)

    def test_non_hosted_or_non_first_attempt_is_rejected(self):
        environment = {'GITHUB_ACTIONS': 'true', 'RUNNER_ENVIRONMENT': 'github-hosted', 'RUNNER_OS': 'Linux',
            'RUNNER_ARCH': 'X64', 'GITHUB_RUN_ATTEMPT': '1', 'SOURCE_COMMIT': 'a' * 40, 'GITHUB_RUN_ID': '123'}
        with patch.object(runner.sys, 'platform', 'linux'):
            runner.hosted_context(environment)
            for key, value in [('RUNNER_ENVIRONMENT', 'self-hosted'), ('GITHUB_RUN_ATTEMPT', '2'), ('SOURCE_COMMIT', 'unknown')]:
                bad = dict(environment, **{key: value})
                with self.subTest(key=key), self.assertRaises(runner.Failure): runner.hosted_context(bad)
        with patch.object(runner.sys, 'platform', 'win32'), self.assertRaises(runner.Failure): runner.hosted_context(environment)

if __name__ == '__main__':
    unittest.main()
