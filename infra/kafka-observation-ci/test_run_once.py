"""Offline failure-boundary fixtures only. No Docker, Java, sockets or network are started."""
from pathlib import Path
import copy
import contextlib
import io
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
            'Tmpfs': {'/var/lib/kafka/data': runner.BROKER_TMPFS.split(':', 1)[1],
                '/etc/kafka/secrets': runner.BROKER_SECRETS_TMPFS.split(':', 1)[1],
                '/mnt/shared/config': runner.BROKER_CONFIG_TMPFS.split(':', 1)[1]}}
        value = {'Id': row['id'], 'Name': '/' + row['name'], 'Created': row['createdAt'], 'Image': row['imageId'],
            'Config': {'Image': row['image'], 'User': '1000:1000', 'Labels': {runner.LABEL: 'b' * 32,
                runner.LABEL + '.source': 'a' * 40, runner.LABEL + '.run': '123'}, 'Volumes': {'/etc/kafka/secrets': {}, '/var/lib/kafka/data': {}, '/mnt/shared/config': {}}},
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

    def test_declared_kafka_volumes_are_covered_by_three_safe_bounded_tmpfs(self):
        state, row, value = self.container_fixture()
        expected = {
            '/var/lib/kafka/data': 'rw,nosuid,nodev,noexec,size=268435456,uid=1000,gid=1000,mode=0700',
            '/etc/kafka/secrets': 'rw,nosuid,nodev,noexec,size=1048576,uid=1000,gid=1000,mode=0700',
            '/mnt/shared/config': 'rw,nosuid,nodev,noexec,size=1048576,uid=1000,gid=1000,mode=0700'}
        self.assertEqual(value['HostConfig']['Tmpfs'], expected)
        self.assertEqual(set(value['Config']['Volumes']), set(expected))
        value['Mounts'] = [{'Type': 'tmpfs', 'Destination': target, 'Source': '', 'RW': True}
                           for target in expected]
        def execute(args, deadline, **kwargs): return (0, json.dumps([value]).encode(), b'')
        owned = runner.OwnedDocker(self.root, state, 100, execute)
        self.assertEqual(owned.inspect(row)['Mounts'], value['Mounts'])

    def test_missing_unbounded_or_unexpected_broker_mounts_remain_rejected(self):
        state, row, valid = self.container_fixture(); current = [valid]
        def execute(args, deadline, **kwargs): return (0, json.dumps(current).encode(), b'')
        owned = runner.OwnedDocker(self.root, state, 100, execute)
        cases = []
        for target in ('/etc/kafka/secrets', '/mnt/shared/config'):
            changed = copy.deepcopy(valid); del changed['HostConfig']['Tmpfs'][target]; cases.append(changed)
            changed = copy.deepcopy(valid); changed['HostConfig']['Tmpfs'][target] = 'rw,size=1073741824'; cases.append(changed)
            changed = copy.deepcopy(valid); changed['Mounts'] = [{'Type': 'volume', 'Destination': target,
                'Source': '/var/lib/docker/volumes/unknown', 'RW': True}]; cases.append(changed)
        changed = copy.deepcopy(valid); changed['Config']['Volumes']['/unexpected'] = {}; cases.append(changed)
        changed = copy.deepcopy(valid); changed['HostConfig']['Tmpfs']['/unexpected'] = 'rw,size=1048576'; cases.append(changed)
        changed = copy.deepcopy(valid); changed['Mounts'] = [{'Type': 'tmpfs', 'Destination': '/unexpected', 'Source': '', 'RW': True}]; cases.append(changed)
        changed = copy.deepcopy(valid); changed['Mounts'] = [{'Type': 'bind', 'Destination': '/etc/kafka/secrets', 'Source': '/etc', 'RW': True}]; cases.append(changed)
        for index, changed in enumerate(cases):
            current[:] = [changed]
            with self.subTest(index=index), self.assertRaises(runner.Failure) as caught:
                owned.inspect(row)
            self.assertEqual(caught.exception.code, 'RESOURCE_IDENTITY_UNVERIFIED')

    def test_source_guard_failure_publishes_failed_even_when_cleanup_is_unknown(self):
        environment = {'SOURCE_COMMIT': 'a' * 40, 'GITHUB_RUN_ID': '123'}
        for index, outcome in enumerate((True, False, TypeError('unknown cleanup outcome'))):
            cleaned = outcome is True
            repo = self.root / str(index); task = repo / runner.PRIVATE; task.mkdir(parents=True)
            state = dict(self.state(), schemaVersion=1, phase='PREPARED', prepared=True, manifestSha256='c' * 64)
            runner.write_new(task / 'state.json', state)
            with patch.object(runner, 'hosted_context'), patch.object(runner.os, 'getuid', return_value=1001, create=True), patch.object(runner.os, 'getgid', return_value=1001, create=True), \
                    patch.object(runner, 'source_snapshot', side_effect=runner.Failure('SOURCE_CHANGED')), \
                    patch.object(runner.OwnedDocker, 'cleanup', return_value=cleaned, side_effect=outcome if isinstance(outcome, Exception) else None), patch.object(runner.subprocess, 'Popen') as process:
                self.assertEqual(runner.run(repo, 'c' * 64, environment), 1); process.assert_not_called()
            summary = runner.load_json(repo / runner.PUBLIC)
            self.assertEqual(summary['status'], 'FAILED'); self.assertEqual(summary['failureCode'], 'SOURCE_CHANGED')
            self.assertIs(summary['sourceBytesUnchanged'], False); self.assertIs(summary['ownedResourcesRemoved'], cleaned)

    def test_normal_api_requires_exact_218_actual_cases_and_zero_skips(self):
        folder = self.root / 'normal'; folder.mkdir()
        report = folder / 'TEST-normal.xml'
        for tests, skipped, cases in [(218, 0, 218), (217, 0, 217), (219, 0, 219), (218, 1, 218), (218, 0, 217)]:
            report.write_text('<testsuite name="normal" tests="' + str(tests) + '" failures="0" errors="0" skipped="' + str(skipped) + '">' +
                ''.join('<testcase name="case-' + str(index) + '"/>' for index in range(cases)) + '</testsuite>')
            if (tests, skipped, cases) == (218, 0, 218): self.assertEqual(runner.verify_normal_api_reports(folder), 218)
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

    def test_public_diagnostic_is_only_a_fixed_phase_and_same_file_assertion_line(self):
        owned = runner.OwnedDocker(self.root, self.state(), 100, lambda *args, **kwargs: self.fail('No CLI expected'))
        output = io.StringIO()
        try:
            owned.inspect({'id': None, 'name': 'PRIVATE_RESOURCE_CANARY'})
        except runner.Failure as error:
            error.args = ('PRIVATE_ERROR_CANARY',)
            error.private_value = 'PRIVATE_FIELD_CANARY'
            with contextlib.redirect_stdout(output): runner.public_guard_diagnostic(error, 'RUN')
        else:
            self.fail('Expected the actual typed identity guard to reject the row')
        value = json.loads(output.getvalue())
        self.assertEqual(set(value), {'kind', 'phase', 'assertionSourceLine'})
        self.assertEqual(value['kind'], 'KAFKA_IT_ASSERTION_DIAGNOSTIC'); self.assertEqual(value['phase'], 'RUN')
        self.assertIs(type(value['assertionSourceLine']), int); self.assertTrue(1 <= value['assertionSourceLine'] <= 10000)
        line = Path(runner.__file__).read_text(encoding='utf-8').splitlines()[value['assertionSourceLine'] - 1]
        self.assertIn("row.get('id')", line); self.assertIn('RESOURCE_IDENTITY_UNVERIFIED', line)
        self.assertNotIn('PRIVATE_', output.getvalue()); self.assertNotIn(str(self.root), output.getvalue())

    def test_diagnostic_suppresses_foreign_frames_unknown_exceptions_and_invalid_phases(self):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            runner.public_guard_diagnostic(runner.Failure('SOURCE_CHANGED'), 'RUN')
            try:
                raise runner.Failure('SOURCE_CHANGED')
            except runner.Failure as foreign:
                runner.public_guard_diagnostic(foreign, 'RUN')
            try:
                runner.require(False, 'SOURCE_CHANGED')
            except runner.Failure as error:
                runner.public_guard_diagnostic(error, 'PRIVATE_PHASE_CANARY')
                runner.public_guard_diagnostic(error, ['RUN'])
            runner.public_guard_diagnostic(RuntimeError('PRIVATE_EXCEPTION_CANARY'), 'RUN')
        self.assertEqual(output.getvalue(), '')

    def test_run_first_failure_location_precedes_cleanup_without_changing_failed_summary(self):
        repo = self.root / 'run'; task = repo / runner.PRIVATE; task.mkdir(parents=True)
        state = dict(self.state(), schemaVersion=1, phase='PREPARED', prepared=True, manifestSha256='c' * 64)
        runner.write_new(task / 'state.json', state)
        original_cleanup = runner.OwnedDocker.cleanup
        def failed_source(*args): runner.require(False, 'SOURCE_CHANGED')
        def failed_cleanup(owned):
            owned.state['resources'].append({'kind': 'network', 'id': None, 'name': 'PRIVATE_NAME_CANARY', 'phase': 'CREATED'})
            return original_cleanup(owned)
        output = io.StringIO()
        with patch.object(runner, 'hosted_context'), patch.object(runner.os, 'getuid', return_value=1001, create=True), \
                patch.object(runner.os, 'getgid', return_value=1001, create=True), patch.object(runner, 'source_snapshot', side_effect=failed_source), \
                patch.object(runner.OwnedDocker, 'cleanup', autospec=True, side_effect=failed_cleanup), \
                patch.object(runner.subprocess, 'Popen') as process, contextlib.redirect_stdout(output):
            self.assertEqual(runner.run(repo, 'c' * 64, {'SOURCE_COMMIT': 'a' * 40, 'GITHUB_RUN_ID': '123'}), 1)
            process.assert_not_called()
        records = [json.loads(line) for line in output.getvalue().splitlines()]
        self.assertEqual(len(records), 2); self.assertEqual([row['phase'] for row in records], ['RUN', 'CLEANUP'])
        for row in records:
            self.assertEqual(set(row), {'kind', 'phase', 'assertionSourceLine'})
            self.assertEqual(row['kind'], 'KAFKA_IT_ASSERTION_DIAGNOSTIC')
        source_lines = Path(runner.__file__).read_text(encoding='utf-8').splitlines()
        self.assertIn('source_snapshot(repo, expected)', source_lines[records[0]['assertionSourceLine'] - 1])
        self.assertIn("row.get('id')", source_lines[records[1]['assertionSourceLine'] - 1])
        self.assertNotIn('PRIVATE_', output.getvalue()); self.assertNotIn(str(self.root), output.getvalue())
        result = runner.load_json(repo / runner.PUBLIC)
        self.assertEqual(len(result), 19); self.assertEqual(result['failureCode'], 'SOURCE_CHANGED')
        self.assertEqual(result['status'], 'FAILED'); self.assertEqual(result['verifiedTests'], 0)
        self.assertIsNone(result['surefireXmlSha256']); self.assertIsNone(result['skips'])
        self.assertIs(result['sourceBytesUnchanged'], False); self.assertIs(result['ownedResourcesRemoved'], False)

    def test_diagnostic_output_failure_does_not_change_cleanup_guard_result(self):
        state = self.state(); state['resources'].append({'kind': 'network', 'id': None, 'name': 'PRIVATE_NAME_CANARY', 'phase': 'CREATED'})
        owned = runner.OwnedDocker(self.root, state, 100, lambda *args, **kwargs: self.fail('No CLI expected'))
        with patch('builtins.print', side_effect=OSError('PRIVATE_STDOUT_CANARY')):
            self.assertIs(owned.cleanup(), False)
        self.assertEqual(state['resources'][0]['phase'], 'CREATED')

    def it_diagnostic_fixture(self):
        staged = self.root / 'it-api'; staged.mkdir()
        relative = 'apps/api/src/test/java/io/github/devdooly/platformlab/jobs/observation/KafkaObservationIT.java'
        source = staged / Path(relative).relative_to('apps/api'); source.parent.mkdir(parents=True)
        public = ('class KafkaObservationIT {\n    @Test void ' + runner.METHOD + '() throws Exception {\n'
            + '        assertThat(true).isTrue();\n    }\n    static String required(String name) { return name; }\n}\n').encode()
        source.write_bytes(public)
        folder = staged / 'target/surefire-reports'; folder.mkdir(parents=True)
        report = folder / ('TEST-' + runner.CLASS + '.xml')
        def write_report(tag, message='PRIVATE_MESSAGE_CANARY', error_type='PRIVATE_PROVIDER_TYPE_CANARY', frame_line=3):
            counts = {'failure': ('1', '0', '0'), 'error': ('0', '1', '0'), 'skipped': ('0', '0', '1'), None: ('0', '0', '0')}
            failed, errors, skipped = counts[tag]
            suite = runner.ET.Element('testsuite', name=runner.CLASS, tests='1', failures=failed, errors=errors, skipped=skipped)
            case = runner.ET.SubElement(suite, 'testcase', classname=runner.CLASS, name=runner.METHOD)
            if tag is not None:
                problem = runner.ET.SubElement(case, tag, message=message, type=error_type)
                problem.text = 'PRIVATE_STACK_CANARY\n    at ' + runner.CLASS + '.' + runner.METHOD + '(KafkaObservationIT.java:' + str(frame_line) + ')\n'
            report.write_bytes(runner.ET.tostring(suite))
        def capture(status=1, state=None, include_rpc=False):
            output = io.StringIO()
            reader = contextlib.nullcontext()
            if runner.os.name == 'nt':
                # Exercise pure XML/privacy classification on Windows; Linux still uses the real O_NOFOLLOW reader.
                def fixture_read(path, limit=1048576):
                    raw = path.read_bytes()
                    if len(raw) > limit: raise runner.Failure('INVALID_CONFIGURATION')
                    return raw
                reader = patch.object(runner, 'read', side_effect=fixture_read)
            with reader, contextlib.redirect_stdout(output):
                runner.public_it_failure_diagnostic(staged, {relative: runner.digest(public)}, status,
                    {'State': state if state is not None else {'Running': False, 'ExitCode': 1, 'OOMKilled': False}})
            encoded = output.getvalue(); records = [json.loads(line) for line in encoded.splitlines()]
            self.assertTrue(records); value = records[-1]
            self.assertEqual(set(value), {'kind', 'failureKind', 'testSourceLine'})
            self.assertEqual(value['kind'], 'KAFKA_IT_FAILURE_DIAGNOSTIC')
            self.assertNotIn('PRIVATE_', encoded); self.assertNotIn(str(self.root), encoded)
            if include_rpc:
                for record in records[:-1]:
                    self.assertEqual(set(record), {'kind', 'stage', 'failureKind'})
                    self.assertEqual(record['kind'], 'KAFKA_OBSERVER_RPC_DIAGNOSTIC')
                return records
            self.assertEqual(len(records), 1)
            return value
        return report, write_report, capture

    def test_it_diagnostic_classifies_actual_single_report_without_provider_values(self):
        report, write_report, capture = self.it_diagnostic_fixture()
        for tag, kind in [('failure', 'JUNIT_ASSERTION_FAILED'), ('error', 'JUNIT_ERROR'),
                ('skipped', 'JUNIT_SKIPPED'), (None, 'JUNIT_SUCCEEDED_PROCESS_FAILED')]:
            with self.subTest(tag=tag):
                write_report(tag); value = capture(); self.assertEqual(value['failureKind'], kind)
                self.assertEqual(value['testSourceLine'], 3 if tag in ('failure', 'error') else None)
        write_report('failure', frame_line=50000)
        self.assertIsNone(capture()['testSourceLine'])
        write_report('failure')
        suite = runner.ET.fromstring(report.read_bytes()); problem = suite.find('testcase/failure')
        problem.text += '    at ' + runner.CLASS + '.' + runner.METHOD + '(KafkaObservationIT.java:4)\n'
        report.write_bytes(runner.ET.tostring(suite)); self.assertIsNone(capture()['testSourceLine'])
        source = report.parents[2] / 'src/test/java/io/github/devdooly/platformlab/jobs/observation/KafkaObservationIT.java'
        original = source.read_bytes(); source.write_bytes(b'PRIVATE_SOURCE_CANARY')
        write_report('failure'); self.assertIsNone(capture()['testSourceLine']); source.write_bytes(original)
        write_report('error'); report.write_bytes(report.read_bytes().replace(runner.CLASS.encode(), b'PRIVATE_FOREIGN_CLASS_CANARY'))
        value = capture(); self.assertEqual(value['failureKind'], 'JUNIT_REPORT_UNVERIFIED'); self.assertIsNone(value['testSourceLine'])

    def test_it_diagnostic_rejects_invalid_bounded_xml_and_keeps_container_enums_fixed(self):
        report, write_report, capture = self.it_diagnostic_fixture()
        self.assertEqual(capture()['failureKind'], 'JUNIT_REPORT_ABSENT')
        for raw in [b'PRIVATE_INVALID_XML_CANARY', b'<!DOCTYPE PRIVATE_CANARY><testsuite/>', b'x' * 1048577]:
            with self.subTest(size=len(raw)):
                report.write_bytes(raw); value = capture()
                self.assertEqual(value['failureKind'], 'JUNIT_REPORT_UNVERIFIED'); self.assertIsNone(value['testSourceLine'])
        for state, kind in [({'Running': False, 'ExitCode': 137, 'OOMKilled': True}, 'CONTAINER_OOM_KILLED'),
                ({'Running': True, 'ExitCode': 0}, 'CONTAINER_STILL_RUNNING'),
                ({'Running': False, 'ExitCode': 0}, 'CONTAINER_ATTACH_UNVERIFIED')]:
            self.assertEqual(capture(state=state)['failureKind'], kind)
        with patch('builtins.print', side_effect=OSError('PRIVATE_PRINT_CANARY')):
            runner.public_it_failure_diagnostic(self.root, {}, 1, {'State': {}})

    def test_it_diagnostic_only_accepts_exact_own_stackless_observer_code_pairs(self):
        report, write_report, capture = self.it_diagnostic_fixture()
        own = 'io.github.devdooly.platformlab.jobs.observation.KafkaObservationService$ObservationFailure'
        codes = {'NOT_CONFIGURED', 'INVALID_CONFIGURATION', 'CAPTURE_BUSY', 'OBSERVER_POISONED', 'CAPTURE_TIMEOUT',
            'KAFKA_UNAVAILABLE', 'TARGET_UNVERIFIED', 'GROUP_UNAVAILABLE', 'GROUP_UNSTABLE', 'OFFSETS_UNVERIFIED',
            'CLOCK_UNVERIFIED', 'CLOSE_UNVERIFIED'}
        for code in codes:
            with self.subTest(code=code):
                write_report('error', message=code, error_type=own)
                report.write_bytes(report.read_bytes().replace(('    at ' + runner.CLASS).encode(), b'    at PRIVATE_UNKNOWN_FRAME_CANARY'))
                value = capture(); self.assertEqual(value['failureKind'], 'OBSERVER_' + code); self.assertIsNone(value['testSourceLine'])
        for message, error_type in [('CAPTURE_TIMEOUT', 'PRIVATE_PROVIDER_TYPE_CANARY'), ('PRIVATE_MESSAGE_CANARY', own),
                ('CAPTURE_TIMEOUT PRIVATE_CANARY', own), (' CAPTURE_TIMEOUT', own), ('CAPTURE_TIMEOUT', own + 'PRIVATE_CANARY')]:
            with self.subTest(message=message, error_type=error_type):
                write_report('error', message=message, error_type=error_type)
                self.assertEqual(capture()['failureKind'], 'JUNIT_ERROR')

    def test_rpc_system_out_only_exports_one_valid_finite_record_from_owned_case(self):
        report, write_report, capture = self.it_diagnostic_fixture()
        valid = {'kind': 'KAFKA_OBSERVER_RPC_DIAGNOSTIC', 'stage': 'LIST_COMMITTED', 'failureKind': 'RPC_TIMEOUT'}
        write_report('error', message='KAFKA_UNAVAILABLE',
            error_type='io.github.devdooly.platformlab.jobs.observation.KafkaObservationService$ObservationFailure')
        suite = runner.ET.fromstring(report.read_bytes()); case = suite.find('testcase')
        runner.ET.SubElement(suite, 'system-out').text = 'PRIVATE_PROVIDER_CANARY\n' + json.dumps(valid)
        runner.ET.SubElement(case, 'system-out').text = json.dumps(valid)  # Identical duplicated capture is one record.
        report.write_bytes(runner.ET.tostring(suite))
        records = capture(include_rpc=True); self.assertEqual(len(records), 2); self.assertEqual(records[0], valid)
        self.assertEqual(records[1]['failureKind'], 'OBSERVER_KAFKA_UNAVAILABLE')

    def test_rpc_system_out_rejects_unknown_duplicate_extra_and_conflicting_private_input(self):
        report, write_report, capture = self.it_diagnostic_fixture()
        valid = {'kind': 'KAFKA_OBSERVER_RPC_DIAGNOSTIC', 'stage': 'LIST_COMMITTED', 'failureKind': 'RPC_TIMEOUT'}
        invalid = [json.dumps(dict(valid, stage='PRIVATE_STAGE_CANARY')), json.dumps(dict(valid, failureKind='PRIVATE_TYPE_CANARY')),
            json.dumps(dict(valid, extra='PRIVATE_VALUE_CANARY')), '{"kind":"KAFKA_OBSERVER_RPC_DIAGNOSTIC","stage":"LIST_COMMITTED","stage":"PRIVATE_DUP_CANARY","failureKind":"RPC_TIMEOUT"}',
            '{"kind":"KAFKA_OBSERVER_RPC_DIAGNOSTIC","stage":NaN,"failureKind":"RPC_TIMEOUT"}', 'PRIVATE_OVERSIZE_CANARY' * 40,
            json.dumps(valid) + '\n' + json.dumps(dict(valid, stage='LIST_END'))]
        for text in invalid:
            with self.subTest(size=len(text)):
                write_report('error'); suite = runner.ET.fromstring(report.read_bytes())
                runner.ET.SubElement(suite.find('testcase'), 'system-out').text = text
                report.write_bytes(runner.ET.tostring(suite))
                records = capture(include_rpc=True); self.assertEqual(len(records), 1)
                self.assertEqual(records[0]['failureKind'], 'JUNIT_ERROR')

if __name__ == '__main__':
    unittest.main()
