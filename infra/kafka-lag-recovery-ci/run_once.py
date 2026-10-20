"""One explicitly opted-in hosted Kafka backlog recovery trial; no production path."""
from pathlib import Path
import argparse
import base64
import hashlib
import importlib.util
import json
import os
import re
import shutil
import stat
import time
import uuid
import xml.etree.ElementTree as ET

PRIVATE = '.local/kafka-lag-recovery-ci/private'
PUBLIC = '.local/kafka-lag-recovery-ci-public/summary.json'
MANIFEST = 'infra/kafka-lag-recovery-ci/runtime-manifest.json'
BASE_RUNNER = 'infra/kafka-observation-ci/run_once.py'
BASE_MANIFEST = 'infra/kafka-observation-ci/runtime-manifest.json'
COMPILE_HELPER = 'infra/kafka-acl-ci/run_once.py'
JAVA = 'infra/kafka-lag-recovery-ci/KafkaLagRecoveryIT.java'
STAGED_JAVA = 'apps/api/src/test/java/io/github/devdooly/platformlab/jobs/observation/KafkaLagRecoveryIT.java'
CLASS = 'io.github.devdooly.platformlab.jobs.observation.KafkaLagRecoveryIT'
METHOD = 'closedConsumerBacklogIsRecoveredByNewConsumerFromCommittedOffset'
EXTRAS = {BASE_MANIFEST, COMPILE_HELPER, JAVA, 'infra/kafka-lag-recovery-ci/run_once.py',
          'infra/kafka-lag-recovery-ci/test_run_once.py', 'infra/kafka-lag-recovery-ci/README.ko.md'}
SHA = re.compile(r'[a-f0-9]{64}')
SUCCESS = {'schemaVersion': 1, 'status': 'PASS', 'initialProcessed': 4, 'initialEndOffset': 12,
    'initialCommittedOffset': 4, 'initialLag': 8, 'emptyGroupObserved': True, 'additionalProduced': 6,
    'backlogEndOffset': 18, 'backlogCommittedOffset': 4, 'backlogLag': 14, 'resumedProcessed': 14,
    'resumedFirstOffset': 4, 'resumedLastOffset': 17, 'finalCommittedOffset': 18, 'finalLag': 0,
    'targetStable': True}
PHASES = {'INPUT', 'CREATE_TOPIC', 'PRODUCE_INITIAL', 'INITIAL_CONSUME', 'INITIAL_COMMIT',
    'INITIAL_OBSERVE', 'CLOSE_INITIAL', 'EMPTY_OBSERVE', 'PRODUCE_BACKLOG', 'BACKLOG_OBSERVE',
    'RESUME_CONSUME', 'FINAL_COMMIT', 'FINAL_OBSERVE', 'CLOSE', 'DELETE_FIXTURE', 'COMPLETE'}
CAUSES = {'ASSERTION', 'OBSERVATION', 'TIMEOUT', 'INTERRUPTED', 'KAFKA', 'UNEXPECTED'}


def need(value):
    if not value:
        raise ValueError('LAG_INPUT_OR_RESULT_UNVERIFIED')


def unique(pairs):
    value = {}
    for key, item in pairs:
        need(key not in value)
        value[key] = item
    return value


def read_source(path, maximum=1048576):
    before = path.lstat()
    need(stat.S_ISREG(before.st_mode) and before.st_nlink == 1 and 0 < before.st_size <= maximum)
    with os.fdopen(os.open(path, os.O_RDONLY | os.O_NOFOLLOW), 'rb') as stream:
        opened = os.fstat(stream.fileno()); raw = stream.read(maximum + 1); closed = os.fstat(stream.fileno())
    identity = lambda x: (x.st_dev, x.st_ino, x.st_mode, x.st_nlink, x.st_size, x.st_mtime_ns, x.st_ctime_ns)
    need(identity(before) == identity(opened) == identity(closed) == identity(path.lstat()) and len(raw) == before.st_size)
    return raw


def descriptor(repo, expected):
    need(type(expected) is str and SHA.fullmatch(expected))
    raw = read_source(repo / MANIFEST)
    need(hashlib.sha256(raw).hexdigest() == expected)
    value = json.loads(raw, object_pairs_hook=unique)
    need(type(value) is dict and set(value) == {'schemaVersion', 'scope', 'files'}
         and type(value['schemaVersion']) is int and value['schemaVersion'] == 1
         and value['scope'] == 'HOSTED_LINUX_KAFKA_LAG_RECOVERY_SOURCE_ONLY')
    need(type(value['files']) is list and len(value['files']) == 115)
    rows = {}
    for row in value['files']:
        need(type(row) is dict and set(row) == {'path', 'bytes', 'sha256'})
        name = row['path']
        need(type(name) is str and name not in rows and not name.startswith('/') and '\\' not in name
             and ':' not in name and '..' not in Path(name).parts and Path(name).as_posix() == name
             and type(row['bytes']) is int and 0 < row['bytes'] <= 1048576
             and type(row['sha256']) is str and SHA.fullmatch(row['sha256']))
        rows[name] = row
    need(EXTRAS <= set(rows) and BASE_RUNNER in rows and STAGED_JAVA not in rows
         and len([name for name in rows if name.startswith('apps/api/')]) == 106)
    return rows


def load_verified(repo, rows, name, module_name):
    raw = read_source(repo / name)
    need(len(raw) == rows[name]['bytes'] and hashlib.sha256(raw).hexdigest() == rows[name]['sha256'])
    module = importlib.util.module_from_spec(importlib.util.spec_from_file_location(module_name, repo / name))
    exec(compile(raw, str(repo / name), 'exec'), module.__dict__)
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
    original = base.load_json(repo / BASE_MANIFEST)
    base.require(original['scope'] == 'HOSTED_LINUX_KAFKA_IT_SOURCE_ONLY' and len(original['files']) == 109
        and set(rows) == {row['path'] for row in original['files']} | EXTRAS
        and all(rows.get(row['path']) == row for row in original['files']), 'SOURCE_CHANGED')
    base.require(base.api_inventory(repo / 'apps/api') == {name for name in rows if name.startswith('apps/api/')}, 'SOURCE_CHANGED')
    lock = base.load_json(repo / 'infra/image-lock.json')
    base.require(lock['images']['apache/kafka:4.3.1'] == base.KAFKA
        and lock['images']['eclipse-temurin:21-jdk'] == base.JDK, 'SOURCE_CHANGED')
    return result


def hosted(base, repo, environment):
    base.hosted_context(environment)
    base.require(environment.get('GITHUB_REPOSITORY') == 'DevDooly/devdooly-platform-lab'
        and environment.get('GITHUB_EVENT_NAME') == 'workflow_dispatch'
        and environment.get('GITHUB_REF') == 'refs/heads/main'
        and environment.get('KAFKA_LAG_RUNTIME_OPT_IN') == 'true'
        and environment.get('GITHUB_RUN_ATTEMPT') == '1')
    base.require(repo == Path(environment['GITHUB_WORKSPACE']).resolve(strict=True))
    code, out, _ = base.command(['git', '-C', str(repo), 'rev-parse', 'HEAD'], time.monotonic() + 5)
    base.require(code == 0 and out.decode('ascii').strip() == environment['SOURCE_COMMIT'], 'SOURCE_CHANGED')


def staged_unchanged(base, staged, snapshot):
    expected = {name: value for name, value in snapshot.items() if name.startswith('apps/api/')}
    expected[STAGED_JAVA] = snapshot[JAVA]
    base.require(len(expected) == 107 and base.api_inventory(staged) == set(expected), 'SOURCE_CHANGED')
    for name, digest in expected.items():
        base.require(base.digest(base.read(staged / Path(name).relative_to('apps/api'))) == digest, 'SOURCE_CHANGED')


def prepare(base, helper, repo, rows, expected, environment):
    hosted(base, repo, environment)
    snapshot = source_snapshot(base, repo, rows)
    task = repo / PRIVATE
    base.require(not task.exists() and not (repo / PUBLIC).exists())
    task.mkdir(parents=True, mode=0o700)
    state = {'schemaVersion': 1, 'phase': 'PREPARING', 'sourceCommit': environment['SOURCE_COMMIT'],
        'runId': environment['GITHUB_RUN_ID'], 'nonce': uuid.uuid4().hex, 'manifestSha256': expected,
        'sourceSnapshot': snapshot, 'resources': [], 'prepared': False}
    base.save_state(task, state)
    helper.private_file(base, task / 'settings.xml',
        b'<settings xmlns="http://maven.apache.org/SETTINGS/1.2.0"><interactiveMode>false</interactiveMode>'
        b'<mirrors><mirror><id>owned-public-central-only</id><mirrorOf>*</mirrorOf>'
        b'<url>https://repo.maven.apache.org/maven2</url></mirror></mirrors></settings>\n')
    staged = task / 'it-api'
    for name in snapshot:
        if name.startswith('apps/api/'):
            destination = staged / Path(name).relative_to('apps/api')
            destination.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            shutil.copyfile(repo / name, destination)
    target = staged / Path(STAGED_JAVA).relative_to('apps/api')
    base.require(not target.exists() and not (staged / 'target').exists())
    target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    shutil.copyfile(repo / JAVA, target)
    env = base.private_environment(task, Path(environment['JAVA_HOME']).resolve(strict=True))
    deadline = time.monotonic() + 900
    common = helper.maven_arguments(task, staged)
    base.checked_command(['sh', str(staged / 'mvnw'), *common, '-DskipTests', 'test-compile'], deadline, environment=env)
    candidates = [x for x in (task / 'wrapper-home').rglob('bin/mvn') if x.is_file() and not x.is_symlink()]
    base.require(len(candidates) == 1)
    maven = candidates[0].parent.parent.resolve(strict=True)
    base.require(maven.is_relative_to(task / 'wrapper-home'))
    version = base.checked_command(['sh', str(maven / 'bin/mvn'), '-version'], deadline, environment=env).decode('utf8', 'strict')
    base.require(re.search(r'Apache Maven 3\.10\.0(?:\s|\x1b)', version) and re.search(r'Java version: 21(?:\.|,)', version))
    surefire, dependency = helper.managed_plugin_versions(base, task)
    plugin = 'org.apache.maven.plugins:maven-dependency-plugin:' + dependency
    base.checked_command(['sh', str(maven / 'bin/mvn'), *common, plugin + ':go-offline'], deadline, environment=env)
    engines = list((task / 'repository/org/junit/platform/junit-platform-engine').glob('*/*.jar'))
    base.require(len(engines) == 1 and not engines[0].is_symlink())
    junit = engines[0].parent.name
    base.require(re.fullmatch(r'[0-9]+\.[0-9]+\.[0-9]+', junit))
    for artifact in ('org.apache.maven.surefire:surefire-junit-platform:' + surefire,
                     'org.junit.platform:junit-platform-launcher:' + junit):
        base.checked_command(['sh', str(maven / 'bin/mvn'), *common, plugin + ':get', '-Dartifact=' + artifact,
                              '-Dtransitive=true'], deadline, environment=env)
    base.require(not list((staged / 'target').rglob('TEST-*.xml')), 'XML_UNVERIFIED')
    staged_unchanged(base, staged, snapshot)
    state.update(mavenRelativePath=maven.relative_to(task).as_posix(), artifactSnapshot=base.artifact_snapshot(task / 'repository'),
        mavenSnapshot=base.tool_snapshot(maven), phase='PREPARED', prepared=True)
    base.require(source_snapshot(base, repo, rows) == snapshot and time.monotonic() <= deadline, 'SOURCE_CHANGED')
    base.save_state(task, state)


def parse_markers(text):
    success, failure = None, None
    for line in text.splitlines():
        if line.startswith('KAFKA_LAG_RECOVERY_RESULT '):
            need(success is None)
            value = json.loads(line.split(' ', 1)[1], object_pairs_hook=unique)
            need(type(value) is dict and set(value) == set(SUCCESS)
                 and all(type(value[key]) is type(expected) and value[key] == expected for key, expected in SUCCESS.items()))
            success = value
        elif line.startswith('KAFKA_LAG_RECOVERY_FAILURE '):
            need(failure is None)
            value = json.loads(line.split(' ', 1)[1], object_pairs_hook=unique)
            need(type(value) is dict and set(value) == {'schemaVersion', 'status', 'phase', 'cause'}
                 and type(value['schemaVersion']) is int and value['schemaVersion'] == 1 and value['status'] == 'FAILED'
                 and value['phase'] in PHASES and value['cause'] in CAUSES)
            failure = value
        elif line.startswith('KAFKA_LAG_RECOVERY_'):
            need(False)
    need(not (success and failure))
    return success, failure


def selected_markers(base, staged):
    paths = list((staged / 'target/surefire-reports').glob('TEST-*.xml'))
    if len(paths) != 1:
        return None, None
    raw = base.read(paths[0], 1048576)
    need(b'<!DOCTYPE' not in raw and b'<!ENTITY' not in raw)
    root = ET.fromstring(raw)
    cases = root.findall('testcase')
    need(root.tag == 'testsuite' and root.get('name') == CLASS and len(cases) == 1
         and cases[0].get('classname') == CLASS and cases[0].get('name') == METHOD)
    return parse_markers('\n'.join(node.text or '' for node in [*root.findall('system-out'), *cases[0].findall('system-out')]))


def broker_environment(cluster):
    return {'CLUSTER_ID': cluster, 'KAFKA_NODE_ID': '1', 'KAFKA_PROCESS_ROLES': 'broker,controller',
        'KAFKA_LISTENERS': 'BROKER://127.0.0.1:19092,CONTROLLER://127.0.0.1:19093',
        'KAFKA_ADVERTISED_LISTENERS': 'BROKER://127.0.0.1:19092', 'KAFKA_CONTROLLER_QUORUM_VOTERS': '1@127.0.0.1:19093',
        'KAFKA_LISTENER_SECURITY_PROTOCOL_MAP': 'BROKER:PLAINTEXT,CONTROLLER:PLAINTEXT',
        'KAFKA_INTER_BROKER_LISTENER_NAME': 'BROKER', 'KAFKA_CONTROLLER_LISTENER_NAMES': 'CONTROLLER',
        'KAFKA_OFFSETS_TOPIC_REPLICATION_FACTOR': '1', 'KAFKA_OFFSETS_TOPIC_NUM_PARTITIONS': '1',
        'KAFKA_TRANSACTION_STATE_LOG_REPLICATION_FACTOR': '1', 'KAFKA_TRANSACTION_STATE_LOG_MIN_ISR': '1',
        'KAFKA_AUTO_CREATE_TOPICS_ENABLE': 'false', 'KAFKA_NUM_PARTITIONS': '1', 'KAFKA_DEFAULT_REPLICATION_FACTOR': '1',
        'KAFKA_MIN_INSYNC_REPLICAS': '1', 'KAFKA_GROUP_INITIAL_REBALANCE_DELAY_MS': '0',
        'KAFKA_LOG_DIRS': '/var/lib/kafka/data/logs', 'KAFKA_METADATA_LOG_DIR': '/var/lib/kafka/data/metadata',
        'KAFKA_HEAP_OPTS': '-Xms512m -Xmx512m'}


def bound_state(base, task, expected, environment):
    state = base.load_json(task / 'state.json')
    base.require(state['sourceCommit'] == environment['SOURCE_COMMIT'] and state['runId'] == environment['GITHUB_RUN_ID']
        and state['manifestSha256'] == expected and re.fullmatch('[a-f0-9]{32}', state['nonce']))
    return state


def run(base, helper, repo, rows, expected, environment):
    hosted(base, repo, environment)
    task = repo / PRIVATE
    state = bound_state(base, task, expected, environment)
    base.require(state['phase'] == 'PREPARED' and state['prepared'] is True and not state['resources'])
    owned = base.OwnedDocker(task, state, time.monotonic() + 600)
    code, xml_hash, unchanged, cleaned, result, diagnostic = None, None, False, False, None, None
    try:
        base.require(os.getuid() > 0 and os.getgid() > 0)
        state.update(phase='RUN_INTENT', runtimeUser=str(os.getuid()) + ':' + str(os.getgid()))
        base.save_state(task, state)
        base.require(source_snapshot(base, repo, rows) == state['sourceSnapshot'], 'SOURCE_CHANGED')
        maven = (task / state['mavenRelativePath']).resolve(strict=True)
        base.require(maven.is_relative_to(task / 'wrapper-home') and base.tool_snapshot(maven) == state['mavenSnapshot']
            and base.artifact_snapshot(task / 'repository') == state['artifactSnapshot'], 'SOURCE_CHANGED')
        staged = task / 'it-api'
        staged_unchanged(base, staged, state['sourceSnapshot'])
        base.require(not (staged / 'target/surefire-reports').exists())
        status, raw, _ = owned.call(['info', '--format', '{{json .}}'])
        info = json.loads(raw, object_pairs_hook=unique)
        base.require(status == 0 and info['OSType'] == 'linux' and info['NCPU'] >= 2 and info['MemTotal'] >= 3221225472)
        broker_image = base.image_identity(owned, base.KAFKA)
        jdk_image = base.image_identity(owned, base.JDK)
        broker_defaults = helper.image_environment(base, owned, base.KAFKA)
        jdk_defaults = helper.image_environment(base, owned, base.JDK)
        cluster = base64.urlsafe_b64encode(uuid.uuid4().bytes).decode().rstrip('=')
        kafka_env = broker_environment(cluster)
        helper.private_file(base, task / 'broker.env', ''.join(k + '=' + v + '\n' for k, v in kafka_env.items()).encode('ascii'))
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
        helper.auth_guard(base, owned, broker, broker_defaults | kafka_env)
        base.require(owned.call(['start', broker['id']])[0] == 0, 'UNKNOWN_OUTCOME')
        until = min(owned.deadline, time.monotonic() + 60)
        while True:
            base.require(time.monotonic() < until, 'DEADLINE_EXCEEDED')
            helper.auth_guard(base, owned, broker, broker_defaults | kafka_env)
            status, _, _ = owned.call(['exec', broker['id'], 'bash', '-c', 'exec 3<>/dev/tcp/127.0.0.1/19092'], min(until, time.monotonic() + 3))
            if status == 0:
                break
            time.sleep(.5)
        mounts = [item for source, target, readonly in [(staged, '/owned/api', False), (task / 'repository', '/owned/repository', False),
            (maven, '/owned/maven', True), (task / 'settings.xml', '/owned/settings.xml', True)]
            for item in ('--mount', 'type=bind,src=' + str(source) + ',dst=' + target + (',readonly' if readonly else ''))]
        test_env = {'SOURCE_COMMIT': state['sourceCommit'], 'LAB_KAFKA_LAG_TEST_BOOTSTRAP': '127.0.0.1:19092',
            'LAB_KAFKA_LAG_TEST_DISPOSABLE': 'true', 'LAB_KAFKA_LAG_TEST_CLUSTER_ID': cluster,
            'MAVEN_SKIP_RC': 'true', 'MAVEN_OPTS': '-Duser.home=/tmp/owned-home'}
        test_args = [item for key, value in test_env.items() for item in ('--env', key + '=' + value)]
        jvm = owned.create('container', prefix + '-jvm', [
            ['create', '--name', prefix + '-jvm', '--network', 'container:' + broker['id'], '--user', state['runtimeUser'],
             '--cpus', '1', '--memory', '1g', '--memory-swap', '1g', '--pids-limit', '256', '--read-only',
             '--cap-drop', 'ALL', '--security-opt', 'no-new-privileges', '--tmpfs', base.JVM_TMPFS,
             *mounts, *test_args, '--entrypoint', '/bin/sh'],
            [base.JDK, '/owned/maven/bin/mvn', '-o', '-B', '-ntp', '-s', '/owned/settings.xml', '-gs', '/owned/settings.xml',
             '-Dmaven.repo.local=/owned/repository', '-f', '/owned/api/pom.xml', '-Dtest=KafkaLagRecoveryIT#' + METHOD,
             '-DfailIfNoTests=true', '-Dsurefire.failIfNoSpecifiedTests=true', '-Dlab.kafka-lag.tests=true',
             '-DargLine=-Xmx768m -Duser.timezone=Asia/Seoul', 'test']],
            role='jvm', image=base.JDK, imageId=jdk_image, networkMode='container:' + broker['id'])
        helper.auth_guard(base, owned, jvm, jdk_defaults | test_env)
        status, _, _ = owned.call(['start', '-a', jvm['id']])
        value = helper.auth_guard(base, owned, jvm, jdk_defaults | test_env)
        result, diagnostic = selected_markers(base, staged)
        base.require(status == 0 and value['State']['Running'] is False and value['State']['ExitCode'] == 0
            and value['State']['OOMKilled'] is False, 'IT_FAILED')
        reports = list((staged / 'target/surefire-reports').glob('TEST-*.xml'))
        base.require(len(reports) == 1, 'XML_UNVERIFIED')
        xml_hash = base.verify_xml(reports[0], CLASS, METHOD)
        base.require(result == SUCCESS and diagnostic is None, 'XML_UNVERIFIED')
        helper.auth_guard(base, owned, broker, broker_defaults | kafka_env)
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
        if not cleaned:
            code = code or 'CLEANUP_UNVERIFIED'
        state['phase'] = 'CLEANED' if cleaned else 'CLEANUP_UNVERIFIED'
        try:
            base.save_state(task, state)
        except BaseException:
            cleaned = False
            code = code or 'CLEANUP_UNVERIFIED'
        base.write_new(repo / PUBLIC, {'schemaVersion': 1, 'scope': 'ISOLATED_KAFKA_LAG_RECOVERY_IT',
            'synthetic': True, 'sourceCommit': state['sourceCommit'], 'runtimeManifestSha256': expected,
            'status': 'PASSED' if code is None else 'FAILED', 'failureCode': code,
            'expectedTests': 1, 'verifiedTests': 1 if xml_hash else 0, 'surefireXmlSha256': xml_hash,
            'sourceAndArtifactsUnchanged': unchanged, 'ownedResourcesRemoved': cleaned,
            'recoveryResult': result if code is None else None, 'selectedFailure': diagnostic,
            'operatingKafkaChanged': False, 'databaseOrExportRecoveryVerified': False,
            'brokerRestartOrHighAvailabilityVerified': False, 'publicExecutionEnabled': False})
    return 0 if code is None else 1


def cleanup(base, repo, expected, environment):
    hosted(base, repo, environment)
    task = repo / PRIVATE
    if not (task / 'state.json').exists():
        return 0
    state = bound_state(base, task, expected, environment)
    if state['phase'] == 'CLEANED':
        return 0
    owned = base.OwnedDocker(task, state, time.monotonic() + 90)
    cleaned = owned.cleanup()
    state['phase'] = 'CLEANED' if cleaned else 'CLEANUP_UNVERIFIED'
    base.save_state(task, state)
    return 0 if cleaned else 1


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('phase', choices=['prepare', 'run', 'cleanup'])
    parser.add_argument('--source-manifest-sha256', required=True)
    parser.add_argument('--ack-fresh-hosted-kafka-lag-it', action='store_true', required=True)
    args = parser.parse_args()
    repo = Path(__file__).resolve().parents[2]
    rows = descriptor(repo, args.source_manifest_sha256)
    base = load_verified(repo, rows, BASE_RUNNER, 'reviewed_lag_owner_base')
    if args.phase == 'cleanup':
        return cleanup(base, repo, args.source_manifest_sha256, os.environ)
    helper = load_verified(repo, rows, COMPILE_HELPER, 'reviewed_lag_compile_support')
    if args.phase == 'prepare':
        prepare(base, helper, repo, rows, args.source_manifest_sha256, os.environ)
        return 0
    if args.phase == 'run':
        return run(base, helper, repo, rows, args.source_manifest_sha256, os.environ)
    return cleanup(base, repo, args.source_manifest_sha256, os.environ)


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except Exception:
        print(json.dumps({'scope': 'KAFKA_LAG_RUNNER_FAILURE', 'failureCode': 'PREPARATION_OR_INPUT_UNVERIFIED'}))
        raise SystemExit(1)
