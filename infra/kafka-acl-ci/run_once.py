"""Dedicated manual hosted Kafka ACL IT; production and the original runner are immutable."""
from pathlib import Path
import argparse
import base64
import hashlib
import importlib.util
import json
import os
import re
import secrets
import shutil
import stat
import sys
import time
import uuid
import xml.etree.ElementTree as ET

PRIVATE = '.local/kafka-acl-ci/private'
PUBLIC = '.local/kafka-acl-ci-public/summary.json'
MANIFEST = 'infra/kafka-acl-ci/runtime-manifest.json'
BASE_RUNNER = 'infra/kafka-observation-ci/run_once.py'
CLASS = 'io.github.devdooly.platformlab.jobs.observation.KafkaObservationAclIT'
METHOD = 'describeOnlyPrincipalObservesAndRejectsSelectedRpcs'
ACL_TEST_SOURCE = 'infra/kafka-acl-ci/KafkaObservationAclIT.java'
ACL_TEST_STAGED = 'apps/api/src/test/java/io/github/devdooly/platformlab/jobs/observation/KafkaObservationAclIT.java'
SHA = re.compile(r'[a-f0-9]{64}')
COMMIT = re.compile(r'[a-f0-9]{40}')


def need(value):
    if not value:
        raise ValueError('ACL_SOURCE_UNVERIFIED')


def read_source(path, maximum=1048576):
    before = path.lstat()
    need(stat.S_ISREG(before.st_mode) and before.st_nlink == 1 and 0 < before.st_size <= maximum)
    with os.fdopen(os.open(path, os.O_RDONLY | os.O_NOFOLLOW), 'rb') as stream:
        opened = os.fstat(stream.fileno())
        raw = stream.read(maximum + 1)
        closed = os.fstat(stream.fileno())
    after = path.lstat()
    identity = lambda s: (s.st_dev, s.st_ino, s.st_mode, s.st_nlink, s.st_size, s.st_mtime_ns, s.st_ctime_ns)
    need(identity(before) == identity(opened) == identity(closed) == identity(after) and len(raw) == before.st_size)
    return raw


def unique(pairs):
    result = {}
    for key, value in pairs:
        need(key not in result)
        result[key] = value
    return result


def descriptor(repo, expected):
    need(type(expected) is str and SHA.fullmatch(expected))
    raw = read_source(repo / MANIFEST)
    need(hashlib.sha256(raw).hexdigest() == expected)
    manifest = json.loads(raw, object_pairs_hook=unique)
    need(type(manifest) is dict and set(manifest) == {'schemaVersion', 'scope', 'files'}
         and manifest['schemaVersion'] == 1 and manifest['scope'] == 'HOSTED_LINUX_KAFKA_ACL_IT_SOURCE_ONLY')
    rows = manifest['files']
    need(type(rows) is list and len(rows) == 113)
    snapshot = {}
    for row in rows:
        need(type(row) is dict and set(row) == {'path', 'sha256', 'bytes'})
        name = row['path']
        need(type(name) is str and name not in snapshot and not name.startswith('/') and '\\' not in name
             and '..' not in Path(name).parts and ':' not in name)
        need(type(row['bytes']) is int and 0 < row['bytes'] <= 1048576 and type(row['sha256']) is str and SHA.fullmatch(row['sha256']))
        snapshot[name] = row
    need(BASE_RUNNER in snapshot and 'infra/kafka-observation-ci/runtime-manifest.json' in snapshot)
    need(len([name for name in snapshot if name.startswith('apps/api/')]) == 106
         and ACL_TEST_SOURCE in snapshot and ACL_TEST_STAGED not in snapshot)
    return snapshot


def load_base(repo, rows):
    row = rows[BASE_RUNNER]
    raw = read_source(repo / BASE_RUNNER)
    need(len(raw) == row['bytes'] and hashlib.sha256(raw).hexdigest() == row['sha256'])
    spec = importlib.util.spec_from_file_location('reviewed_kafka_observation_ci_base', repo / BASE_RUNNER)
    module = importlib.util.module_from_spec(spec)
    # Compile the bytes just verified; no second loader read and no global monkeypatch.
    exec(compile(raw, str(repo / BASE_RUNNER), 'exec'), module.__dict__)
    return module


def source_snapshot(base, repo, rows):
    result = {}
    for name, row in rows.items():
        path = repo / name
        for parent in path.parents:
            if parent == repo:
                break
            base.require(not parent.is_symlink(), 'SOURCE_CHANGED')
        raw = base.read(path)
        base.require(len(raw) == row['bytes'] and base.digest(raw) == row['sha256'], 'SOURCE_CHANGED')
        result[name] = row['sha256']
    base.require(base.api_inventory(repo / 'apps/api') == {name for name in rows if name.startswith('apps/api/')}, 'SOURCE_CHANGED')
    original = base.load_json(repo / 'infra/kafka-observation-ci/runtime-manifest.json')
    base.require(original['scope'] == 'HOSTED_LINUX_KAFKA_IT_SOURCE_ONLY' and len(original['files']) == 109, 'SOURCE_CHANGED')
    base.require(all(rows.get(row['path']) == row for row in original['files']), 'SOURCE_CHANGED')
    lock = base.load_json(repo / 'infra/image-lock.json')
    base.require(lock['images']['apache/kafka:4.3.1'] == base.KAFKA
                 and lock['images']['eclipse-temurin:21-jdk'] == base.JDK, 'SOURCE_CHANGED')
    return result


def hosted(base, repo, environment):
    base.hosted_context(environment)
    base.require(environment.get('GITHUB_REPOSITORY') == 'DevDooly/devdooly-platform-lab'
        and environment.get('GITHUB_EVENT_NAME') == 'workflow_dispatch'
        and environment.get('GITHUB_REF') == 'refs/heads/main'
        and environment.get('KAFKA_ACL_RUNTIME_OPT_IN') == 'true')
    base.require(repo == Path(environment['GITHUB_WORKSPACE']).resolve(strict=True))
    code, out, _ = base.command(['git', '-C', str(repo), 'rev-parse', 'HEAD'], time.monotonic() + 5)
    base.require(code == 0 and out.decode('ascii').strip() == environment['SOURCE_COMMIT'], 'SOURCE_CHANGED')


def prepared_staging(base, repo, task, snapshot):
    staged = task / 'it-api'
    base.require(not staged.exists())
    for name in snapshot:
        if name.startswith('apps/api/'):
            destination = staged / Path(name).relative_to('apps/api')
            destination.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            shutil.copyfile(repo / name, destination)
    # Keep the repository's original API106 inventory intact. Only this fresh staging gets the IT.
    destination = staged / Path(ACL_TEST_STAGED).relative_to('apps/api')
    base.require(not destination.exists())
    destination.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    shutil.copyfile(repo / ACL_TEST_SOURCE, destination)
    base.require(not (staged / 'target').exists())
    return staged


def maven_arguments(task, staged):
    return ['-B', '-ntp', '-s', str(task / 'settings.xml'), '-gs', str(task / 'settings.xml'),
            '-Dmaven.repo.local=' + str(task / 'repository'), '-f', str(staged / 'pom.xml')]


def managed_plugin_versions(base, task):
    raw = base.read(task / 'repository/org/springframework/boot/spring-boot-dependencies/4.1.1/spring-boot-dependencies-4.1.1.pom')
    base.require(b'<!DOCTYPE' not in raw and b'<!ENTITY' not in raw)
    root = ET.fromstring(raw)
    ns = {'m': 'http://maven.apache.org/POM/4.0.0'}
    version = root.find('m:version', ns)
    base.require(version is not None and version.text == '4.1.1')
    values = []
    for key in ('maven-surefire-plugin.version', 'maven-dependency-plugin.version'):
        value = root.find('m:properties/m:' + key, ns)
        base.require(value is not None and type(value.text) is str and re.fullmatch(r'[0-9]+\.[0-9]+\.[0-9]+', value.text))
        values.append(value.text)
    return values


def prepare(base, repo, rows, expected, environment):
    hosted(base, repo, environment)
    snapshot = source_snapshot(base, repo, rows)
    task = repo / PRIVATE
    base.require(not task.exists() and not (repo / PUBLIC).exists())
    task.mkdir(parents=True, mode=0o700)
    state = {'schemaVersion': 1, 'phase': 'PREPARING', 'sourceCommit': environment['SOURCE_COMMIT'],
        'runId': environment['GITHUB_RUN_ID'], 'nonce': uuid.uuid4().hex, 'manifestSha256': expected,
        'sourceSnapshot': snapshot, 'resources': [], 'prepared': False}
    base.save_state(task, state)
    settings = task / 'settings.xml'
    settings.write_text('<settings xmlns="http://maven.apache.org/SETTINGS/1.2.0"><interactiveMode>false</interactiveMode>'
        '<mirrors><mirror><id>owned-public-central-only</id><mirrorOf>*</mirrorOf>'
        '<url>https://repo.maven.apache.org/maven2</url></mirror></mirrors></settings>\n', encoding='utf8')
    settings.chmod(0o600)
    staged = prepared_staging(base, repo, task, snapshot)
    java = Path(environment['JAVA_HOME']).resolve(strict=True)
    env = base.private_environment(task, java)
    deadline = time.monotonic() + 900
    common = maven_arguments(task, staged)
    # Compilation only. Do not call base.prepare(), verify, or the existing 218-test suite.
    base.checked_command(['sh', str(staged / 'mvnw'), *common, '-DskipTests', 'test-compile'], deadline, environment=env)
    candidates = [p for p in (task / 'wrapper-home').rglob('bin/mvn') if p.is_file() and not p.is_symlink()]
    base.require(len(candidates) == 1)
    maven = candidates[0].parent.parent.resolve(strict=True)
    base.require(maven.is_relative_to(task / 'wrapper-home'))
    version = base.checked_command(['sh', str(maven / 'bin/mvn'), '-version'], deadline, environment=env).decode('utf8', 'strict')
    base.require(re.search(r'Apache Maven 3\.10\.0(?:\s|\x1b)', version) and re.search(r'Java version: 21(?:\.|,)', version))
    surefire, dependency = managed_plugin_versions(base, task)
    plugin = 'org.apache.maven.plugins:maven-dependency-plugin:' + dependency
    base.checked_command(['sh', str(maven / 'bin/mvn'), *common, plugin + ':go-offline'], deadline, environment=env)
    engines = list((task / 'repository/org/junit/platform/junit-platform-engine').glob('*/*.jar'))
    base.require(len(engines) == 1 and not engines[0].is_symlink())
    junit = engines[0].parent.name
    base.require(re.fullmatch(r'[0-9]+\.[0-9]+\.[0-9]+', junit))
    for artifact in ('org.apache.maven.surefire:surefire-junit-platform:' + surefire,
                     'org.junit.platform:junit-platform-launcher:' + junit):
        base.checked_command(['sh', str(maven / 'bin/mvn'), *common, plugin + ':get',
            '-Dartifact=' + artifact, '-Dtransitive=true'], deadline, environment=env)
    base.require(not list((staged / 'target').rglob('TEST-*.xml')), 'XML_UNVERIFIED')
    state.update(mavenRelativePath=maven.relative_to(task).as_posix(), artifactSnapshot=base.artifact_snapshot(task / 'repository'),
        mavenSnapshot=base.tool_snapshot(maven), phase='PREPARED', prepared=True)
    base.require(source_snapshot(base, repo, rows) == snapshot and time.monotonic() <= deadline, 'SOURCE_CHANGED')
    base.save_state(task, state)


def private_file(base, path, raw):
    base.require(type(raw) is bytes and 0 < len(raw) <= 16384)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, 'wb') as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())
    base.require(base.read(path, 16384) == raw)


def env_map(base, rows):
    base.require(type(rows) is list and len(rows) <= 128)
    value = {}
    for row in rows:
        base.require(type(row) is str and '=' in row and len(row.encode('utf8')) <= 16384)
        key, item = row.split('=', 1)
        base.require(key not in value and re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*', key))
        value[key] = item
    base.require(sum(len(v.encode('utf8')) for v in rows) <= 65536)
    return value


def image_environment(base, owned, image):
    code, raw, _ = owned.call(['image', 'inspect', '--format', '{{json .Config.Env}}', image])
    base.require(code == 0, 'RESOURCE_IDENTITY_UNVERIFIED')
    return env_map(base, json.loads(raw, object_pairs_hook=unique))


def auth_guard(base, owned, resource, expected):
    # Config.Env contains only this fresh fixture's synthetic credentials; it stays in RAM.
    value = owned.inspect(resource)
    base.require(env_map(base, value['Config']['Env']) == expected, 'RESOURCE_IDENTITY_UNVERIFIED')
    return value


def broker_environment(cluster, admin, observer):
    jaas = ('org.apache.kafka.common.security.plain.PlainLoginModule required username="acl_admin" password="'
        + admin + '" user_acl_admin="' + admin + '" user_acl_observer="' + observer + '";')
    return {'CLUSTER_ID': cluster, 'KAFKA_NODE_ID': '1', 'KAFKA_PROCESS_ROLES': 'broker,controller',
        'KAFKA_LISTENERS': 'BROKER://127.0.0.1:19092,CONTROLLER://127.0.0.1:19093',
        'KAFKA_ADVERTISED_LISTENERS': 'BROKER://127.0.0.1:19092', 'KAFKA_CONTROLLER_QUORUM_VOTERS': '1@127.0.0.1:19093',
        'KAFKA_LISTENER_SECURITY_PROTOCOL_MAP': 'BROKER:SASL_PLAINTEXT,CONTROLLER:SASL_PLAINTEXT',
        'KAFKA_INTER_BROKER_LISTENER_NAME': 'BROKER', 'KAFKA_CONTROLLER_LISTENER_NAMES': 'CONTROLLER',
        'KAFKA_SASL_ENABLED_MECHANISMS': 'PLAIN', 'KAFKA_SASL_MECHANISM_INTER_BROKER_PROTOCOL': 'PLAIN',
        'KAFKA_SASL_MECHANISM_CONTROLLER_PROTOCOL': 'PLAIN',
        'KAFKA_LISTENER_NAME_BROKER_PLAIN_SASL_JAAS_CONFIG': jaas,
        'KAFKA_LISTENER_NAME_CONTROLLER_PLAIN_SASL_JAAS_CONFIG': jaas,
        'KAFKA_AUTHORIZER_CLASS_NAME': 'org.apache.kafka.metadata.authorizer.StandardAuthorizer',
        'KAFKA_ALLOW_EVERYONE_IF_NO_ACL_FOUND': 'false', 'KAFKA_SUPER_USERS': 'User:acl_admin',
        'KAFKA_OFFSETS_TOPIC_REPLICATION_FACTOR': '1', 'KAFKA_OFFSETS_TOPIC_NUM_PARTITIONS': '1',
        'KAFKA_TRANSACTION_STATE_LOG_REPLICATION_FACTOR': '1', 'KAFKA_TRANSACTION_STATE_LOG_MIN_ISR': '1',
        'KAFKA_AUTO_CREATE_TOPICS_ENABLE': 'false', 'KAFKA_NUM_PARTITIONS': '1',
        'KAFKA_DEFAULT_REPLICATION_FACTOR': '1', 'KAFKA_MIN_INSYNC_REPLICAS': '1',
        'KAFKA_GROUP_INITIAL_REBALANCE_DELAY_MS': '0', 'KAFKA_LOG_DIRS': '/var/lib/kafka/data/logs',
        'KAFKA_METADATA_LOG_DIR': '/var/lib/kafka/data/metadata', 'KAFKA_HEAP_OPTS': '-Xms512m -Xmx512m'}


def staged_unchanged(base, staged, snapshot):
    expected = {name: value for name, value in snapshot.items() if name.startswith('apps/api/')}
    base.require(ACL_TEST_STAGED not in expected and ACL_TEST_SOURCE in snapshot, 'SOURCE_CHANGED')
    expected[ACL_TEST_STAGED] = snapshot[ACL_TEST_SOURCE]
    base.require(len(expected) == 107 and base.api_inventory(staged) == set(expected), 'SOURCE_CHANGED')
    for name, value in expected.items():
        base.require(base.digest(base.read(staged / Path(name).relative_to('apps/api'))) == value, 'SOURCE_CHANGED')


def selected_diagnostics(base, staged):
    expected = {'OTHER_TOPIC': 'TOPIC_AUTH', 'OTHER_GROUP': 'GROUP_AUTH', 'ALTER_CONFIG': 'TOPIC_AUTH',
                'OFFSET_COMMIT': 'GROUP_AUTH', 'PRODUCE': 'TOPIC_AUTH', 'BAD_PASSWORD': 'SASL_AUTH'}
    phases = {'INPUT', 'SETUP', 'BASELINE', 'OBSERVER', 'DENIED_RPCS', 'PRESERVATION', 'BAD_PASSWORD', 'CLOSE', 'COMPLETE'}
    setup_steps = {'ADMIN_CREATE', 'DESCRIBE_CLUSTER', 'CREATE_TOPICS', 'OTHER_GROUP_OFFSETS',
        'OTHER_GROUP_DESCRIBE', 'CONSUMER_CONFIG', 'CONSUMER_CREATE', 'CONSUMER_JOIN', 'PRODUCER_CONFIG',
        'PRODUCER_CREATE', 'PRODUCE_RECORDS', 'PRODUCER_CLOSE', 'INITIAL_COMMIT', 'ACL_PROFILE',
        'CREATE_ACLS', 'DESCRIBE_ACLS', 'CONSUMER_CLOSE', 'DRIVER_CLOSE'}
    setup_causes = {'ASSERTION', 'GROUP_NOT_FOUND', 'COORDINATOR', 'NOT_CONTROLLER', 'AUTHORIZER_NOT_READY',
        'AUTHORIZATION', 'AUTHENTICATION', 'CONFIGURATION', 'TIMEOUT', 'INTERRUPTED', 'OTHER'}
    result = {'phase': None, 'failureKind': None, 'setupStep': None, 'setupCauseKind': None, 'rpcResults': []}
    reports = list((staged / 'target/surefire-reports').glob('TEST-*.xml'))
    if len(reports) != 1:
        return result
    raw = base.read(reports[0], 1048576)
    base.require(b'<!DOCTYPE' not in raw and b'<!ENTITY' not in raw, 'XML_UNVERIFIED')
    root = ET.fromstring(raw)
    cases = root.findall('testcase')
    base.require(root.tag == 'testsuite' and root.get('name') == CLASS and len(cases) == 1
        and cases[0].get('classname') == CLASS and cases[0].get('name') == METHOD, 'XML_UNVERIFIED')
    records = {}
    for node in [*root.findall('system-out'), *cases[0].findall('system-out')]:
        for line in (node.text or '').splitlines():
            if not line.startswith('{"kind":"KAFKA_ACL_'):
                continue
            value = json.loads(line, object_pairs_hook=unique)
            base.require(type(value) is dict, 'XML_UNVERIFIED')
            if value.get('kind') == 'KAFKA_ACL_RPC_ASSERTION':
                base.require(set(value) == {'kind', 'rpc', 'outcome', 'causeKind'}
                    and value['rpc'] in expected and value['rpc'] not in records
                    and value['outcome'] in {'DENIED', 'WRONG_FAILURE', 'UNEXPECTED_SUCCESS'}
                    and value['causeKind'] in {'TOPIC_AUTH', 'GROUP_AUTH', 'SASL_AUTH', 'TIMEOUT', 'OTHER', 'NONE'}, 'XML_UNVERIFIED')
                records[value['rpc']] = {key: value[key] for key in ('rpc', 'outcome', 'causeKind')}
            elif value.get('kind') == 'KAFKA_ACL_SELECTED_ASSERTIONS':
                base.require(result['phase'] is None and value.get('phase') in phases, 'XML_UNVERIFIED')
                if value['phase'] == 'COMPLETE':
                    base.require(value == {'kind': 'KAFKA_ACL_SELECTED_ASSERTIONS', 'phase': 'COMPLETE',
                        'describeProfile': True, 'deniedRpcs': 5, 'badPasswordRejected': True,
                        'selectedStatePreserved': True}, 'XML_UNVERIFIED')
                else:
                    base.require(set(value) == {'kind', 'phase', 'failureKind', 'setupStep', 'setupCauseKind'}
                        and value['failureKind'] in {'ASSERTION', 'OBSERVATION', 'INTERRUPTED', 'UNEXPECTED'}, 'XML_UNVERIFIED')
                    if value['phase'] == 'SETUP':
                        base.require(type(value['setupStep']) is str and value['setupStep'] in setup_steps
                            and type(value['setupCauseKind']) is str and value['setupCauseKind'] in setup_causes, 'XML_UNVERIFIED')
                        result['setupStep'] = value['setupStep']
                        result['setupCauseKind'] = value['setupCauseKind']
                    else:
                        base.require(value['setupStep'] == 'NONE' and value['setupCauseKind'] == 'NONE', 'XML_UNVERIFIED')
                    result['failureKind'] = value['failureKind']
                result['phase'] = value['phase']
            else:
                base.require(False, 'XML_UNVERIFIED')
    result['rpcResults'] = [records[key] for key in expected if key in records]
    return result


def run(base, repo, rows, expected, environment):
    hosted(base, repo, environment)
    task = repo / PRIVATE
    state = base.load_json(task / 'state.json')
    base.require(state['phase'] == 'PREPARED' and state['prepared'] is True and not state['resources'])
    base.require(state['sourceCommit'] == environment['SOURCE_COMMIT'] and state['runId'] == environment['GITHUB_RUN_ID']
        and state['manifestSha256'] == expected and re.fullmatch('[a-f0-9]{32}', state['nonce']))
    owned = base.OwnedDocker(task, state, time.monotonic() + 600)
    code, xml_hash, unchanged, cleaned = None, None, False, False
    diagnostics = {'phase': None, 'failureKind': None, 'setupStep': None, 'setupCauseKind': None, 'rpcResults': []}
    try:
        base.require(os.getuid() > 0 and os.getgid() > 0)
        state.update(phase='RUN_INTENT', runtimeUser=str(os.getuid()) + ':' + str(os.getgid()))
        base.save_state(task, state)
        base.require(source_snapshot(base, repo, rows) == state['sourceSnapshot'], 'SOURCE_CHANGED')
        maven = (task / state['mavenRelativePath']).resolve(strict=True)
        base.require(maven.is_relative_to(task / 'wrapper-home'))
        base.require(base.artifact_snapshot(task / 'repository') == state['artifactSnapshot']
            and base.tool_snapshot(maven) == state['mavenSnapshot'], 'SOURCE_CHANGED')
        staged = task / 'it-api'
        staged_unchanged(base, staged, state['sourceSnapshot'])
        base.require(not (staged / 'target/surefire-reports').exists())
        status, raw, _ = owned.call(['info', '--format', '{{json .}}'])
        info = json.loads(raw, object_pairs_hook=unique)
        base.require(status == 0 and info['OSType'] == 'linux' and info['NCPU'] >= 2 and info['MemTotal'] >= 3221225472)
        broker_image = base.image_identity(owned, base.KAFKA)
        jdk_image = base.image_identity(owned, base.JDK)
        broker_defaults = image_environment(base, owned, base.KAFKA)
        jdk_defaults = image_environment(base, owned, base.JDK)
        cluster = base64.urlsafe_b64encode(uuid.uuid4().bytes).decode().rstrip('=')
        admin, observer = secrets.token_hex(32), secrets.token_hex(32)
        base.require(admin != observer)
        kafka_env = broker_environment(cluster, admin, observer)
        private_file(base, task / 'broker.env', ''.join(k + '=' + v + '\n' for k, v in kafka_env.items()).encode('ascii'))
        credential_path = staged / 'target/owned-acl-credentials.properties'
        private_file(base, credential_path, ('admin.username=acl_admin\nadmin.password=' + admin
            + '\nobserver.username=acl_observer\nobserver.password=' + observer + '\n').encode('ascii'))
        expected_broker_env = broker_defaults | kafka_env
        owned.deadline = time.monotonic() + 300
        prefix = 'platform-kafka-observation-' + state['runId'] + '-' + state['nonce']
        network = owned.create('network', prefix + '-network', ['network', 'create', '--internal', '--driver', 'bridge', prefix + '-network'])
        broker = owned.create('container', prefix + '-broker', [
            ['create', '--name', prefix + '-broker', '--network', network['id'], '--user', '1000:1000', '--cpus', '1',
             '--memory', '1g', '--memory-swap', '1g', '--pids-limit', '256', '--cap-drop', 'ALL',
             '--security-opt', 'no-new-privileges', '--tmpfs', base.BROKER_TMPFS,
             '--tmpfs', base.BROKER_SECRETS_TMPFS, '--tmpfs', base.BROKER_CONFIG_TMPFS,
             '--env-file', str(task / 'broker.env')], [base.KAFKA]],
            role='broker', image=base.KAFKA, imageId=broker_image, networkMode=network['id'])
        auth_guard(base, owned, broker, expected_broker_env)
        base.require(owned.call(['start', broker['id']])[0] == 0, 'UNKNOWN_OUTCOME')
        until = min(owned.deadline, time.monotonic() + 60)
        while True:
            base.require(time.monotonic() < until, 'DEADLINE_EXCEEDED')
            auth_guard(base, owned, broker, expected_broker_env)
            status, _, _ = owned.call(['exec', broker['id'], 'bash', '-c', 'exec 3<>/dev/tcp/127.0.0.1/19092'], min(until, time.monotonic() + 3))
            if status == 0:
                break
            time.sleep(0.5)
        mounts = [item for source, target, readonly in [(staged, '/owned/api', False), (task / 'repository', '/owned/repository', False),
            (maven, '/owned/maven', True), (task / 'settings.xml', '/owned/settings.xml', True)]
            for item in ('--mount', 'type=bind,src=' + str(source) + ',dst=' + target + (',readonly' if readonly else ''))]
        test_env = {'SOURCE_COMMIT': state['sourceCommit'], 'LAB_KAFKA_ACL_TEST_BOOTSTRAP': '127.0.0.1:19092',
            'LAB_KAFKA_ACL_TEST_DISPOSABLE': 'true', 'LAB_KAFKA_ACL_TEST_CLUSTER_ID': cluster,
            'MAVEN_SKIP_RC': 'true', 'MAVEN_OPTS': '-Duser.home=/tmp/owned-home'}
        test_args = [item for key, value in test_env.items() for item in ('--env', key + '=' + value)]
        jvm = owned.create('container', prefix + '-jvm', [
            ['create', '--name', prefix + '-jvm', '--network', 'container:' + broker['id'], '--user', state['runtimeUser'],
             '--cpus', '1', '--memory', '1g', '--memory-swap', '1g', '--pids-limit', '256', '--read-only',
             '--cap-drop', 'ALL', '--security-opt', 'no-new-privileges', '--tmpfs', base.JVM_TMPFS,
             *mounts, *test_args, '--entrypoint', '/bin/sh'],
            [base.JDK, '/owned/maven/bin/mvn', '-o', '-B', '-ntp', '-s', '/owned/settings.xml', '-gs', '/owned/settings.xml',
             '-Dmaven.repo.local=/owned/repository', '-f', '/owned/api/pom.xml', '-Dtest=KafkaObservationAclIT#' + METHOD,
             '-DfailIfNoTests=true', '-Dsurefire.failIfNoSpecifiedTests=true', '-Dlab.kafka-acl.tests=true',
             '-DargLine=-Xmx768m -Duser.timezone=Asia/Seoul', 'test']],
            role='jvm', image=base.JDK, imageId=jdk_image, networkMode='container:' + broker['id'])
        auth_guard(base, owned, jvm, jdk_defaults | test_env)
        status, _, _ = owned.call(['start', '-a', jvm['id']])
        value = auth_guard(base, owned, jvm, jdk_defaults | test_env)
        diagnostics = selected_diagnostics(base, staged)
        base.require(status == 0 and value['State']['Running'] is False and value['State']['ExitCode'] == 0
            and value['State']['OOMKilled'] is False, 'IT_FAILED')
        reports = list((staged / 'target/surefire-reports').glob('TEST-*.xml'))
        base.require(len(reports) == 1, 'XML_UNVERIFIED')
        xml_hash = base.verify_xml(reports[0], CLASS, METHOD)
        base.require(diagnostics['phase'] == 'COMPLETE' and diagnostics['failureKind'] is None
            and diagnostics['rpcResults'] == [
                {'rpc': key, 'outcome': 'DENIED', 'causeKind': cause} for key, cause in (
                    ('OTHER_TOPIC', 'TOPIC_AUTH'), ('OTHER_GROUP', 'GROUP_AUTH'), ('ALTER_CONFIG', 'TOPIC_AUTH'),
                    ('OFFSET_COMMIT', 'GROUP_AUTH'), ('PRODUCE', 'TOPIC_AUTH'), ('BAD_PASSWORD', 'SASL_AUTH'))], 'XML_UNVERIFIED')
        auth_guard(base, owned, broker, expected_broker_env)
        base.require(source_snapshot(base, repo, rows) == state['sourceSnapshot']
            and base.artifact_snapshot(task / 'repository') == state['artifactSnapshot']
            and base.tool_snapshot(maven) == state['mavenSnapshot'], 'SOURCE_CHANGED')
        staged_unchanged(base, staged, state['sourceSnapshot'])
        base.require(time.monotonic() <= owned.deadline, 'DEADLINE_EXCEEDED')
        unchanged = True
    except BaseException as error:
        code = error.code if isinstance(error, base.Failure) else 'UNKNOWN_OUTCOME'
    finally:
        owned.deadline = time.monotonic() + 90
        try:
            cleaned = owned.cleanup()
        except BaseException:
            cleaned = False
        if not cleaned and code is None:
            code = 'CLEANUP_UNVERIFIED'
        state['phase'] = 'CLEANED' if cleaned else 'CLEANUP_UNVERIFIED'
        try:
            base.save_state(task, state)
        except BaseException:
            cleaned = False
            code = code or 'CLEANUP_UNVERIFIED'
        base.write_new(repo / PUBLIC, {'schemaVersion': 1, 'scope': 'ISOLATED_KAFKA_SASL_ACL_IT',
            'synthetic': True, 'sourceCommit': state['sourceCommit'], 'runtimeManifestSha256': expected,
            'status': 'PASSED' if code is None else 'FAILED', 'failureCode': code,
            'expectedTests': 1, 'verifiedTests': 1 if xml_hash else 0, 'surefireXmlSha256': xml_hash,
            'sourceAndArtifactsUnchanged': unchanged, 'ownedResourcesRemoved': cleaned,
            'describeOnlyProfileVerified': code is None, 'selectedDeniedRpcsVerified': 5 if code is None else None,
            'badPasswordAuthenticationFailureVerified': code is None,
            'selectedTestPhase': diagnostics['phase'], 'selectedFailureKind': diagnostics['failureKind'],
            'selectedSetupStep': diagnostics['setupStep'], 'selectedSetupCauseKind': diagnostics['setupCauseKind'],
            'selectedRpcResults': diagnostics['rpcResults'],
            'selectedAdminStatePreserved': code is None, 'allWritesBlocked': False,
            'tlsConfidentialityVerified': False, 'allJvmThreadsVerified': False, 'operatingKafkaChanged': False,
            'publicExecutionEnabled': False})
    return 0 if code is None else 1


def cleanup(base, repo, expected, environment):
    hosted(base, repo, environment)
    task = repo / PRIVATE
    if not (task / 'state.json').exists():
        return 0
    state = base.load_json(task / 'state.json')
    base.require(state['sourceCommit'] == environment['SOURCE_COMMIT'] and state['runId'] == environment['GITHUB_RUN_ID']
        and state['manifestSha256'] == expected and re.fullmatch('[a-f0-9]{32}', state['nonce']))
    if state['phase'] == 'CLEANED':
        return 0
    # Cleanup needs the unchanged pinned owner implementation, not credentials or healthy authentication.
    owned = base.OwnedDocker(task, state, time.monotonic() + 90)
    cleaned = owned.cleanup()
    state['phase'] = 'CLEANED' if cleaned else 'CLEANUP_UNVERIFIED'
    base.save_state(task, state)
    return 0 if cleaned else 1


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('phase', choices=['prepare', 'run', 'cleanup'])
    parser.add_argument('--source-manifest-sha256', required=True)
    parser.add_argument('--ack-fresh-hosted-kafka-acl-it', action='store_true', required=True)
    args = parser.parse_args()
    repo = Path(__file__).resolve().parents[2]
    rows = descriptor(repo, args.source_manifest_sha256)
    base = load_base(repo, rows)
    if args.phase == 'prepare':
        prepare(base, repo, rows, args.source_manifest_sha256, os.environ)
        return 0
    if args.phase == 'run':
        return run(base, repo, rows, args.source_manifest_sha256, os.environ)
    return cleanup(base, repo, args.source_manifest_sha256, os.environ)


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except Exception:
        print(json.dumps({'scope': 'KAFKA_ACL_RUNNER_FAILURE', 'failureCode': 'PREPARATION_OR_INPUT_UNVERIFIED'}))
        raise SystemExit(1)
