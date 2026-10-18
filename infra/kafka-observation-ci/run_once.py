"""Explicit hosted-Linux-only Kafka IT. All imports are stdlib; import has no side effects."""
from pathlib import Path
import argparse
import base64
import datetime as dt
import hashlib
import json
import os
import re
import selectors
import shutil
import signal
import stat
import subprocess
import sys
import time
import uuid
import xml.etree.ElementTree as ET

SHA = re.compile(r'[a-f0-9]{64}')
COMMIT = re.compile(r'[a-f0-9]{40}')
METHOD = 'realClassicGroupNoCommitPositiveZeroAndUncommittedTransactionProveReadOnlyLsoObservation'
CLASS = 'io.github.devdooly.platformlab.jobs.observation.KafkaObservationIT'
KAFKA = 'apache/kafka:4.3.1@sha256:ccd1314e47ec76909e01f86308b4dcf2064f19f7c89759234322314b0e319e26'
JDK = 'eclipse-temurin:21-jdk@sha256:3e3c176ffed168beb42c607be9bc1639b466cf00261a0fb04425562c9d0c5c2b'
PRIVATE = '.local/kafka-observation-ci/private'
PUBLIC = '.local/kafka-observation-ci-public/summary.json'
LABEL = 'io.github.devdooly.kafka-observation'
NORMAL_API_TESTS = 216
BROKER_TMPFS = '/var/lib/kafka/data:rw,nosuid,nodev,noexec,size=268435456,uid=1000,gid=1000,mode=0700'
JVM_TMPFS = '/tmp:rw,nosuid,nodev,size=134217728,mode=1777'
CODES = {'PREPARATION_FAILED', 'UNKNOWN_OUTCOME', 'RESOURCE_IDENTITY_UNVERIFIED', 'DEADLINE_EXCEEDED',
         'SOURCE_CHANGED', 'IT_FAILED', 'XML_UNVERIFIED', 'CLEANUP_UNVERIFIED', 'INVALID_CONFIGURATION'}

class Failure(Exception):
    def __init__(self, code):
        assert code in CODES
        self.code = code
        super().__init__(code)

def require(condition, code='INVALID_CONFIGURATION'):
    if not condition:
        raise Failure(code)

def public_guard_diagnostic(error, phase):
    """Best-effort public source location only; never format exception or values."""
    if not isinstance(error, Failure) or type(phase) is not str or phase not in ('RUN', 'CLEANUP'):
        return
    try:
        trace = error.__traceback__; source_line = None
        for _ in range(32):
            if trace is None:
                break
            frame = trace.tb_frame
            if frame.f_code.co_filename == __file__ and frame.f_code.co_name != 'require':
                source_line = trace.tb_lineno
            trace = trace.tb_next
        if trace is not None or type(source_line) is not int or not 1 <= source_line <= 10000:
            return
        print(json.dumps({'kind': 'KAFKA_IT_ASSERTION_DIAGNOSTIC', 'phase': phase,
                          'assertionSourceLine': source_line}, sort_keys=True))
    except Exception:
        # A diagnostic failure must not replace the original failure or cleanup result.
        return

def digest(raw):
    return hashlib.sha256(raw).hexdigest()

def read(path, limit=1048576):
    before = path.lstat()
    require(stat.S_ISREG(before.st_mode) and before.st_nlink == 1 and 0 <= before.st_size <= limit)
    with os.fdopen(os.open(path, os.O_RDONLY | os.O_NOFOLLOW), 'rb') as stream:
        opened = os.fstat(stream.fileno()); raw = stream.read(limit + 1); closed = os.fstat(stream.fileno())
    after = path.lstat()
    identity = lambda item: (item.st_dev, item.st_ino, item.st_mode, item.st_nlink, item.st_size, item.st_mtime_ns, item.st_ctime_ns)
    require(identity(before) == identity(opened) == identity(closed) == identity(after) and len(raw) == before.st_size)
    return raw

def unique_pairs(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result)
        result[key] = value
    return result

def load_json(path):
    return json.loads(read(path), object_pairs_hook=unique_pairs)

def write_new(path, value):
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    require(not path.exists())
    raw = (json.dumps(value, sort_keys=True, indent=2) + '\n').encode()
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, 'wb') as stream:
        stream.write(raw)

def save_state(folder, state):
    target = folder / 'state.json'
    temporary = folder / 'state.pending.json'
    write_new(temporary, state)
    os.replace(temporary, target)

def hosted_context(environment):
    require(sys.platform == 'linux')
    require(environment.get('GITHUB_ACTIONS') == 'true' and environment.get('RUNNER_ENVIRONMENT') == 'github-hosted')
    require(environment.get('RUNNER_OS') == 'Linux' and environment.get('RUNNER_ARCH') == 'X64')
    require(environment.get('GITHUB_RUN_ATTEMPT') == '1')
    require(COMMIT.fullmatch(environment.get('SOURCE_COMMIT', '')) is not None)
    require(re.fullmatch(r'[0-9]{1,18}', environment.get('GITHUB_RUN_ID', '')) is not None)

def api_inventory(folder):
    result = set()
    for path in folder.rglob('*'):
        require(not path.is_symlink(), 'SOURCE_CHANGED')
        if path.relative_to(folder).parts[0] != 'target':
            info = path.lstat()
            require(stat.S_ISREG(info.st_mode) or stat.S_ISDIR(info.st_mode), 'SOURCE_CHANGED')
            if stat.S_ISREG(info.st_mode): result.add('apps/api/' + path.relative_to(folder).as_posix())
    return result

def source_snapshot(repo, expected):
    require(SHA.fullmatch(expected) is not None)
    manifest_path = repo / 'infra/kafka-observation-ci/runtime-manifest.json'
    raw = read(manifest_path)
    require(digest(raw) == expected, 'SOURCE_CHANGED')
    manifest = json.loads(raw, object_pairs_hook=unique_pairs)
    require(set(manifest) == {'schemaVersion', 'scope', 'files'} and manifest['schemaVersion'] == 1)
    require(manifest['scope'] == 'HOSTED_LINUX_KAFKA_IT_SOURCE_ONLY')
    paths = set(); snapshot = {}
    for row in manifest['files']:
        require(set(row) == {'path', 'sha256', 'bytes'} and type(row['bytes']) is int and 0 < row['bytes'] <= 1048576)
        relative = Path(row['path'])
        require(not relative.is_absolute() and '..' not in relative.parts and '\\' not in row['path'])
        require(row['path'] not in paths and SHA.fullmatch(row['sha256']) is not None)
        paths.add(row['path'])
        for parent in (repo / relative).parents:
            if parent == repo:
                break
            require(not parent.is_symlink())
        value = read(repo / relative)
        require(len(value) == row['bytes'] and digest(value) == row['sha256'], 'SOURCE_CHANGED')
        snapshot[row['path']] = row['sha256']
    api = {name for name in paths if name.startswith('apps/api/')}
    require(len(api) == 106 and len(paths) == 109)
    actual_api = api_inventory(repo / 'apps/api')
    require(actual_api == api, 'SOURCE_CHANGED')
    require('infra/kafka-observation-ci/run_once.py' in paths and 'infra/image-lock.json' in paths)
    lock = load_json(repo / 'infra/image-lock.json')
    require(lock['images']['apache/kafka:4.3.1'] == KAFKA and lock['images']['eclipse-temurin:21-jdk'] == JDK)
    return snapshot

def command(args, deadline, environment=None, limit=4194304):
    """Bounded stdout+stderr in RAM; kill the local process group on deadline/overflow."""
    require(time.monotonic() < deadline, 'DEADLINE_EXCEEDED')
    proc = subprocess.Popen(args, env=environment, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE, start_new_session=True)
    selector = selectors.DefaultSelector(); buffers = {'stdout': bytearray(), 'stderr': bytearray()}
    for stream, key in ((proc.stdout, 'stdout'), (proc.stderr, 'stderr')):
        os.set_blocking(stream.fileno(), False); selector.register(stream, selectors.EVENT_READ, key)
    try:
        while selector.get_map():
            require(time.monotonic() < deadline, 'DEADLINE_EXCEEDED')
            for key, _ in selector.select(max(0, min(0.1, deadline - time.monotonic()))):
                raw = os.read(key.fileobj.fileno(), 16384)
                if raw:
                    buffers[key.data].extend(raw)
                    require(sum(map(len, buffers.values())) <= limit, 'UNKNOWN_OUTCOME')
                else:
                    selector.unregister(key.fileobj)
        code = proc.wait(timeout=max(0.001, deadline - time.monotonic()))
        require(time.monotonic() <= deadline, 'DEADLINE_EXCEEDED')
        return code, bytes(buffers['stdout']), bytes(buffers['stderr'])
    except BaseException as error:
        if proc.poll() is None:
            os.killpg(proc.pid, signal.SIGKILL)
        proc.wait(timeout=5)
        if isinstance(error, subprocess.TimeoutExpired):
            raise Failure('DEADLINE_EXCEEDED') from error
        raise
    finally:
        selector.close(); proc.stdout.close(); proc.stderr.close()

def checked_command(args, deadline, code='PREPARATION_FAILED', environment=None):
    status, out, err = command(args, deadline, environment)
    require(status == 0, code)
    return out

def artifact_snapshot(folder):
    """Only immutable Maven payloads; repository lock/download metadata is not an artifact."""
    result = {}
    for path in sorted(folder.rglob('*')):
        require(not path.is_symlink())
        if path.is_file() and path.suffix in {'.jar', '.pom', '.zip'}:
            require(len(result) < 12000)
            result[path.relative_to(folder).as_posix()] = digest(read(path, 134217728))
    require(result and sum(path.stat().st_size for path in folder.rglob('*') if path.is_file()) <= 1073741824)
    return result

def tool_snapshot(folder):
    result = {}
    for path in sorted(folder.rglob('*')):
        require(not path.is_symlink())
        if path.is_file():
            require(len(result) < 5000)
            result[path.relative_to(folder).as_posix()] = digest(read(path, 134217728))
    require(result)
    return result

def private_environment(task, java_home):
    require(java_home.is_dir() and (java_home / 'bin/java').is_file())
    return {'PATH': str(java_home / 'bin') + ':/usr/bin:/bin', 'JAVA_HOME': str(java_home), 'LANG': 'C.UTF-8',
            'MAVEN_SKIP_RC': 'true', 'MAVEN_OPTS': '-Dmaven.user.home=' + str(task / 'wrapper-home') +
            ' -Duser.home=' + str(task / 'user-home')}

def verify_xml(path, expected_class=CLASS, expected_method=METHOD):
    raw = read(path, 1048576)
    require(b'<!DOCTYPE' not in raw and b'<!ENTITY' not in raw, 'XML_UNVERIFIED')
    root = ET.fromstring(raw)
    require(root.tag == 'testsuite' and root.attrib.get('name') == expected_class, 'XML_UNVERIFIED')
    require(tuple(root.attrib.get(key) for key in ('tests', 'failures', 'errors', 'skipped')) == ('1', '0', '0', '0'), 'XML_UNVERIFIED')
    cases = root.findall('testcase')
    require(len(cases) == 1 and cases[0].attrib.get('classname') == expected_class and cases[0].attrib.get('name') == expected_method, 'XML_UNVERIFIED')
    require(not any(cases[0].find(tag) is not None for tag in ('failure', 'error', 'skipped')), 'XML_UNVERIFIED')
    properties = {item.attrib.get('name'): item.attrib.get('value') for item in root.findall('properties/property')}
    require(properties.get('java.specification.version') == '21' and properties.get('os.name') == 'Linux', 'XML_UNVERIFIED')
    return digest(raw)

def verify_normal_api_reports(folder):
    reports = list(folder.glob('TEST-*.xml'))
    require(reports and not any('KafkaObservationIT' in path.name for path in reports), 'XML_UNVERIFIED')
    count = 0
    names = set()
    for path in reports:
        raw = read(path)
        require(b'<!DOCTYPE' not in raw and b'<!ENTITY' not in raw, 'XML_UNVERIFIED')
        report = ET.fromstring(raw)
        require(report.tag == 'testsuite' and type(report.attrib.get('name')) is str, 'XML_UNVERIFIED')
        require(report.attrib['name'] not in names, 'XML_UNVERIFIED'); names.add(report.attrib['name'])
        require(all(report.attrib.get(key) == '0' for key in ('failures', 'errors', 'skipped')), 'XML_UNVERIFIED')
        require(re.fullmatch(r'[0-9]+', report.attrib.get('tests', '')) is not None, 'XML_UNVERIFIED')
        cases = report.findall('testcase')
        require(len(cases) == int(report.attrib['tests']), 'XML_UNVERIFIED')
        require(not any(case.find(tag) is not None for case in cases for tag in ('failure', 'error', 'skipped')), 'XML_UNVERIFIED')
        count += len(cases)
    require(count == NORMAL_API_TESTS, 'XML_UNVERIFIED')
    return count

def prepare(repo, expected, environment):
    hosted_context(environment)
    snapshot = source_snapshot(repo, expected)
    task = repo / PRIVATE
    require(not task.exists() and not (repo / PUBLIC).exists() and not (repo / 'apps/api/target').exists())
    task.mkdir(parents=True, mode=0o700)
    nonce = uuid.uuid4().hex
    state = {'schemaVersion': 1, 'phase': 'PREPARING', 'sourceCommit': environment['SOURCE_COMMIT'],
             'runId': environment['GITHUB_RUN_ID'], 'nonce': nonce, 'manifestSha256': expected,
             'sourceSnapshot': snapshot, 'resources': [], 'prepared': False}
    save_state(task, state)
    settings = task / 'settings.xml'
    settings.write_text('<settings xmlns="http://maven.apache.org/SETTINGS/1.2.0"><interactiveMode>false</interactiveMode>'
        '<mirrors><mirror><id>owned-public-central-only</id><mirrorOf>*</mirrorOf>'
        '<url>https://repo.maven.apache.org/maven2</url></mirror></mirrors></settings>\n', encoding='utf8')
    settings.chmod(0o600)
    java = Path(environment['JAVA_HOME']).resolve(strict=True)
    env = private_environment(task, java)
    deadline = time.monotonic() + 900
    args = ['sh', str(repo / 'apps/api/mvnw'), '-B', '-ntp', '-s', str(settings), '-gs', str(settings),
            '-Dmaven.repo.local=' + str(task / 'repository'), '-f', str(repo / 'apps/api/pom.xml'), 'verify']
    status, out, err = command(args, deadline, env)
    (task / 'normal-api-verify.stdout.log').write_bytes(out); (task / 'normal-api-verify.stderr.log').write_bytes(err)
    require(status == 0, 'PREPARATION_FAILED')
    count = verify_normal_api_reports(repo / 'apps/api/target/surefire-reports')
    candidates = [path for path in (task / 'wrapper-home').rglob('bin/mvn') if path.is_file() and not path.is_symlink()]
    require(len(candidates) == 1)
    maven = candidates[0].parent.parent.resolve(strict=True)
    require(maven.is_relative_to(task / 'wrapper-home'))
    version = checked_command(['sh', str(maven / 'bin/mvn'), '-version'], deadline, environment=env).decode('utf8', errors='replace')
    require(re.search(r'Apache Maven 3\.10\.0(?:\s|\x1b)', version) is not None)
    require(re.search(r'Java version: 21(?:\.|,)', version) is not None)
    (task / 'host-maven-version.txt').write_text(version, encoding='utf8')
    state.update(mavenRelativePath=maven.relative_to(task).as_posix(), normalApiTests=count,
                 artifactSnapshot=artifact_snapshot(task / 'repository'), mavenSnapshot=tool_snapshot(maven))
    require(source_snapshot(repo, expected) == snapshot, 'SOURCE_CHANGED')
    require(time.monotonic() <= deadline, 'DEADLINE_EXCEEDED')
    state.update(phase='PREPARED', prepared=True); save_state(task, state)
    return state

class OwnedDocker:
    def __init__(self, task, state, deadline, execute=command):
        self.task, self.state, self.deadline, self.execute = task, state, deadline, execute
        self.labels = {LABEL: state['nonce'], LABEL + '.source': state['sourceCommit'], LABEL + '.run': state['runId']}
        (task / 'docker-config').mkdir(mode=0o700, exist_ok=True)

    def call(self, args, deadline=None):
        return self.execute(['/usr/bin/docker', '--host=unix:///var/run/docker.sock', *args],
            min(self.deadline, deadline or self.deadline), limit=1048576,
            environment={'PATH': '/usr/bin:/bin', 'LANG': 'C.UTF-8', 'DOCKER_CONFIG': str(self.task / 'docker-config')})

    def inspect(self, row, initialize=False):
        require(type(row) is dict and type(row.get('id')) is str and SHA.fullmatch(row['id']) is not None, 'RESOURCE_IDENTITY_UNVERIFIED')
        require(type(row.get('kind')) is str and row['kind'] in {'network', 'container'} and type(row.get('name')) is str, 'RESOURCE_IDENTITY_UNVERIFIED')
        args = ['network', 'inspect'] if row['kind'] == 'network' else ['inspect']
        code, out, _ = self.call([*args, row['id']])
        require(code == 0, 'RESOURCE_IDENTITY_UNVERIFIED')
        values = json.loads(out, object_pairs_hook=unique_pairs)
        require(type(values) is list and len(values) == 1, 'RESOURCE_IDENTITY_UNVERIFIED')
        value = values[0]
        require(type(value) is dict and type(value.get('Name')) is str, 'RESOURCE_IDENTITY_UNVERIFIED')
        require(value.get('Id') == row['id'] and value['Name'] == (row['name'] if row['kind'] == 'network' else '/' + row['name']), 'RESOURCE_IDENTITY_UNVERIFIED')
        created = value.get('Created')
        require(type(created) is str and re.fullmatch(r'[0-9]{4}-[0-9T:.\-]+Z', created) is not None, 'RESOURCE_IDENTITY_UNVERIFIED')
        try:
            created_time = dt.datetime.fromisoformat(created.replace('Z', '+00:00'))
            intended = dt.datetime.fromisoformat(row['intendedAt'].replace('Z', '+00:00'))
        except (ValueError, KeyError, TypeError, AttributeError):
            raise Failure('RESOURCE_IDENTITY_UNVERIFIED')
        if initialize:
            require('createdAt' not in row and intended <= created_time <= dt.datetime.now(dt.timezone.utc) + dt.timedelta(seconds=1), 'RESOURCE_IDENTITY_UNVERIFIED')
        else:
            require(type(row.get('createdAt')) is str and created == row['createdAt'], 'RESOURCE_IDENTITY_UNVERIFIED')
        config = value.get('Config') if row['kind'] == 'container' else None
        require(row['kind'] == 'network' or type(config) is dict, 'RESOURCE_IDENTITY_UNVERIFIED')
        labels = value.get('Labels') if row['kind'] == 'network' else config.get('Labels')
        require(type(labels) is dict and all(labels.get(key) == val for key, val in self.labels.items()), 'RESOURCE_IDENTITY_UNVERIFIED')
        if row['kind'] == 'network':
            require(value.get('Internal') is True and value.get('Driver') == 'bridge', 'RESOURCE_IDENTITY_UNVERIFIED')
        else:
            host = value.get('HostConfig'); state = value.get('State')
            require(type(host) is dict and type(state) is dict and type(state.get('Running')) is bool, 'RESOURCE_IDENTITY_UNVERIFIED')
            require(type(state.get('Status')) is str and state['Status'] in {'created', 'running', 'exited'} and type(state.get('StartedAt')) is str, 'RESOURCE_IDENTITY_UNVERIFIED')
            require(state['Running'] is (state['Status'] == 'running'), 'RESOURCE_IDENTITY_UNVERIFIED')
            require(type(row.get('role')) is str and row['role'] in {'broker', 'jvm'} and type(row.get('networkMode')) is str, 'RESOURCE_IDENTITY_UNVERIFIED')
            require(row.get('image') == (KAFKA if row['role'] == 'broker' else JDK) and type(row.get('imageId')) is str and re.fullmatch(r'sha256:[a-f0-9]{64}', row['imageId']) is not None, 'RESOURCE_IDENTITY_UNVERIFIED')
            require(value.get('Image') == row.get('imageId') and config.get('Image') == row.get('image'), 'RESOURCE_IDENTITY_UNVERIFIED')
            mode = host.get('NetworkMode')
            require(type(mode) is str, 'RESOURCE_IDENTITY_UNVERIFIED')
            require(host.get('PortBindings') in (None, {}) and host.get('Binds') in (None, []), 'RESOURCE_IDENTITY_UNVERIFIED')
            require(host.get('NanoCpus') == 1000000000 and host.get('Memory') == 1073741824 and host.get('MemorySwap') == 1073741824 and host.get('PidsLimit') == 256, 'RESOURCE_IDENTITY_UNVERIFIED')
            require(host.get('Privileged') is False and host.get('ReadonlyRootfs') is (row['role'] == 'jvm'), 'RESOURCE_IDENTITY_UNVERIFIED')
            require(host.get('CapDrop') == ['ALL'] and host.get('CapAdd') in (None, []) and host.get('SecurityOpt') in (['no-new-privileges'], ['no-new-privileges:true']), 'RESOURCE_IDENTITY_UNVERIFIED')
            require(host.get('PidMode') == '' and host.get('IpcMode') == 'private' and host.get('UTSMode') == '' and host.get('UsernsMode') == '', 'RESOURCE_IDENTITY_UNVERIFIED')
            require(all(host.get(key) in (None, []) for key in ('Devices', 'DeviceRequests', 'VolumesFrom', 'Links')), 'RESOURCE_IDENTITY_UNVERIFIED')
            if row['role'] == 'jvm':
                require(type(self.state.get('runtimeUser')) is str and re.fullmatch(r'[1-9][0-9]*:[1-9][0-9]*', self.state['runtimeUser']) is not None, 'RESOURCE_IDENTITY_UNVERIFIED')
            require(config.get('User') == ('1000:1000' if row['role'] == 'broker' else self.state.get('runtimeUser')), 'RESOURCE_IDENTITY_UNVERIFIED')
            if row['role'] == 'jvm':
                require(mode == row['networkMode'], 'RESOURCE_IDENTITY_UNVERIFIED')
                broker_matches = [item for item in self.state['resources'] if type(item) is dict and item.get('role') == 'broker' and type(item.get('id')) is str and mode == 'container:' + item['id']]
                require(len(broker_matches) == 1 and type(broker_matches[0].get('createdAt')) is str, 'RESOURCE_IDENTITY_UNVERIFIED')
            else:
                matches = [item for item in self.state['resources'] if type(item) is dict and item.get('kind') == 'network' and item.get('id') == row['networkMode']]
                require(len(matches) == 1, 'RESOURCE_IDENTITY_UNVERIFIED'); network = matches[0]
                require(mode in {network['id'], network['name']}, 'RESOURCE_IDENTITY_UNVERIFIED')
                net_settings = value.get('NetworkSettings')
                require(type(net_settings) is dict and type(net_settings.get('Networks')) is dict, 'RESOURCE_IDENTITY_UNVERIFIED')
                links = net_settings['Networks']
                never_started = state.get('Status') == 'created' and state['Running'] is False and str(state.get('StartedAt', '')).startswith('0001-01-01T')
                require(len(links) in ({0, 1} if never_started else {1}), 'RESOURCE_IDENTITY_UNVERIFIED')
                if links:
                    link = next(iter(links.values())); require(type(link) is dict, 'RESOURCE_IDENTITY_UNVERIFIED')
                    require(link.get('NetworkID') in ({'', network['id']} if never_started else {network['id']}), 'RESOURCE_IDENTITY_UNVERIFIED')
            self.mounts(row, value, host, config)
        if initialize:
            row['createdAt'] = created; save_state(self.task, self.state)
        return value

    def mounts(self, row, value, host, config):
        role = row['role']
        expected_tmpfs = {'/var/lib/kafka/data': BROKER_TMPFS.split(':', 1)[1]} if role == 'broker' else {'/tmp': JVM_TMPFS.split(':', 1)[1]}
        require(host.get('Tmpfs') == expected_tmpfs, 'RESOURCE_IDENTITY_UNVERIFIED')
        declared = config.get('Volumes')
        require(declared is None or type(declared) is dict and set(declared).issubset(expected_tmpfs), 'RESOURCE_IDENTITY_UNVERIFIED')
        expected_binds = {}
        if role == 'jvm':
            relative = self.state.get('mavenRelativePath')
            require(type(relative) is str and not Path(relative).is_absolute() and '..' not in Path(relative).parts, 'RESOURCE_IDENTITY_UNVERIFIED')
            maven = (self.task / relative).resolve(strict=True)
            require(maven.is_relative_to(self.task / 'wrapper-home'), 'RESOURCE_IDENTITY_UNVERIFIED')
            expected_binds = {'/owned/api': (str((self.task / 'it-api').resolve(strict=True)), True),
                '/owned/repository': (str((self.task / 'repository').resolve(strict=True)), True),
                '/owned/maven': (str(maven), False), '/owned/settings.xml': (str((self.task / 'settings.xml').resolve(strict=True)), False)}
            require(all(Path(source).is_relative_to(self.task) for source, _ in expected_binds.values()), 'RESOURCE_IDENTITY_UNVERIFIED')
        requested = host.get('Mounts')
        require(requested in (None, []) if not expected_binds else type(requested) is list and len(requested) == 4, 'RESOURCE_IDENTITY_UNVERIFIED')
        if expected_binds:
            seen = set()
            for mount in requested:
                require(type(mount) is dict and mount.get('Type') == 'bind' and type(mount.get('Target')) is str and mount['Target'] in expected_binds, 'RESOURCE_IDENTITY_UNVERIFIED')
                target = mount['Target']; require(target not in seen, 'RESOURCE_IDENTITY_UNVERIFIED'); seen.add(target)
                source, writable = expected_binds[target]
                readonly = mount.get('ReadOnly', False)
                require(type(readonly) is bool and mount.get('Source') == source and readonly is (not writable), 'RESOURCE_IDENTITY_UNVERIFIED')
            require(seen == set(expected_binds), 'RESOURCE_IDENTITY_UNVERIFIED')
        actual = value.get('Mounts'); require(type(actual) is list, 'RESOURCE_IDENTITY_UNVERIFIED')
        seen = set(); binds = set()
        for mount in actual:
            require(type(mount) is dict and type(mount.get('Destination')) is str, 'RESOURCE_IDENTITY_UNVERIFIED')
            target = mount['Destination']; require(target not in seen, 'RESOURCE_IDENTITY_UNVERIFIED'); seen.add(target)
            if mount.get('Type') == 'bind':
                require(target in expected_binds, 'RESOURCE_IDENTITY_UNVERIFIED'); source, writable = expected_binds[target]
                require(mount.get('Source') == source and mount.get('RW') is writable and mount.get('Propagation') == 'rprivate', 'RESOURCE_IDENTITY_UNVERIFIED'); binds.add(target)
            else:
                require(mount.get('Type') == 'tmpfs' and target in expected_tmpfs and mount.get('Source') in (None, '', 'tmpfs') and mount.get('RW') is True, 'RESOURCE_IDENTITY_UNVERIFIED')
        require(binds == set(expected_binds), 'RESOURCE_IDENTITY_UNVERIFIED')

    def create(self, kind, name, args, **identity):
        require(re.fullmatch(r'platform-kafka-observation-[0-9]{1,18}-[a-f0-9]{32}-(network|broker|jvm)', name) is not None)
        listing = ['network', 'ls', '--filter', 'name=^' + name + '$', '--format', '{{.ID}}'] if kind == 'network' else ['ps', '-a', '--filter', 'name=^/' + name + '$', '--format', '{{.ID}}']
        code, out, _ = self.call(listing)
        require(code == 0 and out.strip() == b'', 'RESOURCE_IDENTITY_UNVERIFIED')
        row = {'kind': kind, 'name': name, 'id': None, 'phase': 'CREATE_INTENT',
               'intendedAt': dt.datetime.now(dt.timezone.utc).isoformat().replace('+00:00', 'Z'), **identity}
        self.state['resources'].append(row); save_state(self.task, self.state)
        labels = [item for key, value in self.labels.items() for item in ('--label', key + '=' + value)]
        try:
            code, out, _ = self.call([*args[:-1], *labels, args[-1]] if kind == 'network' else [*args[0], *labels, *args[1]])
        except BaseException:
            raise Failure('UNKNOWN_OUTCOME')
        require(code == 0 and SHA.fullmatch(out.decode('ascii', errors='replace').strip()) is not None, 'UNKNOWN_OUTCOME')
        row.update(id=out.decode().strip(), phase='CREATED'); save_state(self.task, self.state)
        self.inspect(row, initialize=True)
        return row

    def cleanup(self):
        all_removed = True
        if type(self.state.get('resources')) is not list or len(self.state['resources']) > 3:
            return False
        for row in reversed(self.state['resources']):
            try:
                require(type(row) is dict, 'RESOURCE_IDENTITY_UNVERIFIED')
                if row.get('phase') == 'REMOVED': continue
                value = self.inspect(row)
                if row['kind'] != 'network' and value['State']['Running']:
                    code, _, _ = self.call(['stop', '--time', '10', row['id']])
                    require(code == 0 and self.inspect(row)['State']['Running'] is False, 'CLEANUP_UNVERIFIED')
                args = ['network', 'rm'] if row['kind'] == 'network' else ['rm']
                code, _, _ = self.call([*args, row['id']])
                require(code == 0, 'CLEANUP_UNVERIFIED')
                listing = ['network', 'ls', '--no-trunc'] if row['kind'] == 'network' else ['ps', '-a', '--no-trunc']
                code, out, _ = self.call([*listing, '--filter', 'id=' + row['id'], '--format', '{{.ID}}'])
                require(code == 0 and out.strip() == b'', 'CLEANUP_UNVERIFIED')
                row['phase'] = 'REMOVED'; save_state(self.task, self.state)
            except (Failure, OSError, ValueError, KeyError, TypeError, AttributeError) as error:
                public_guard_diagnostic(error, 'CLEANUP')
                all_removed = False
        return all_removed

def image_identity(owned, image):
    code, _, _ = owned.call(['pull', image])
    require(code == 0, 'PREPARATION_FAILED')
    code, out, _ = owned.call(['image', 'inspect', image])
    require(code == 0, 'PREPARATION_FAILED')
    values = json.loads(out, object_pairs_hook=unique_pairs)
    require(type(values) is list and len(values) == 1)
    value = values[0]
    repo_digest = image.split('@')[0].rsplit(':', 1)[0] + '@' + image.split('@')[1]
    require(value.get('Os') == 'linux' and value.get('Architecture') == 'amd64' and repo_digest in value.get('RepoDigests', []))
    require(re.fullmatch(r'sha256:[a-f0-9]{64}', value.get('Id', '')) is not None)
    return value['Id']

def public_summary(source, manifest, status, code, xml_hash, source_unchanged, cleaned):
    require(status in {'PASSED', 'FAILED'} and (code is None or code in CODES))
    require(COMMIT.fullmatch(source) is not None and SHA.fullmatch(manifest) is not None)
    passed = status == 'PASSED'
    require(not passed or code is None and SHA.fullmatch(xml_hash or '') is not None and source_unchanged and cleaned)
    return {'schemaVersion': 1, 'kind': 'kafka-observation-ci-result', 'scope': 'ISOLATED_KAFKA_IT',
            'synthetic': True, 'publicExecutionEnabled': False, 'sourceCommit': source,
            'runtimeManifestSha256': manifest, 'status': status, 'failureCode': code,
            'expectedTests': 1, 'verifiedTests': 1 if xml_hash else 0, 'skips': 0 if xml_hash else None,
            'testSourceAssertionsVerified': passed, 'surefireXmlSha256': xml_hash,
            'sourceBytesUnchanged': source_unchanged, 'ownedResourcesRemoved': cleaned,
            'httpOrMiniPcRuntimeVerified': False, 'kafkaAclVerified': False, 'allJvmThreadsVerified': False}

def run(repo, expected, environment):
    hosted_context(environment)
    task = repo / PRIVATE; state = load_json(task / 'state.json')
    require(state['phase'] == 'PREPARED' and state['prepared'] is True and not state['resources'])
    require(state['sourceCommit'] == environment['SOURCE_COMMIT'] and state['runId'] == environment['GITHUB_RUN_ID'] and state['manifestSha256'] == expected)
    owned = OwnedDocker(task, state, time.monotonic() + 600)
    xml_hash = None; code = None; unchanged = False; cleaned = False
    try:
        state['phase'] = 'RUN_INTENT'; state['runtimeUser'] = str(os.getuid()) + ':' + str(os.getgid()); save_state(task, state)
        require(os.getuid() > 0 and os.getgid() > 0)
        require(source_snapshot(repo, expected) == state['sourceSnapshot'], 'SOURCE_CHANGED')
        require(artifact_snapshot(task / 'repository') == state['artifactSnapshot'], 'SOURCE_CHANGED')
        maven = task / state['mavenRelativePath']; require(maven.resolve().is_relative_to(task / 'wrapper-home'))
        require(tool_snapshot(maven) == state['mavenSnapshot'], 'SOURCE_CHANGED')
        status, out, _ = owned.call(['info', '--format', '{{json .}}'])
        info = json.loads(out); require(status == 0 and info['OSType'] == 'linux' and info['NCPU'] >= 2 and info['MemTotal'] >= 3221225472)
        broker_image = image_identity(owned, KAFKA); jdk_image = image_identity(owned, JDK)
        # No image/dependency download after the first owned resource is created.
        owned.deadline = time.monotonic() + 300
        prefix = 'platform-kafka-observation-' + state['runId'] + '-' + state['nonce']
        network = owned.create('network', prefix + '-network', ['network', 'create', '--internal', '--driver', 'bridge', prefix + '-network'])
        cluster = base64.urlsafe_b64encode(uuid.uuid4().bytes).decode().rstrip('=')
        kafka_env = {'CLUSTER_ID': cluster, 'KAFKA_NODE_ID': '1', 'KAFKA_PROCESS_ROLES': 'broker,controller',
            'KAFKA_LISTENERS': 'BROKER://127.0.0.1:19092,CONTROLLER://127.0.0.1:19093',
            'KAFKA_ADVERTISED_LISTENERS': 'BROKER://127.0.0.1:19092', 'KAFKA_CONTROLLER_QUORUM_VOTERS': '1@127.0.0.1:19093',
            'KAFKA_LISTENER_SECURITY_PROTOCOL_MAP': 'BROKER:PLAINTEXT,CONTROLLER:PLAINTEXT', 'KAFKA_INTER_BROKER_LISTENER_NAME': 'BROKER',
            'KAFKA_CONTROLLER_LISTENER_NAMES': 'CONTROLLER', 'KAFKA_OFFSETS_TOPIC_REPLICATION_FACTOR': '1',
            'KAFKA_OFFSETS_TOPIC_NUM_PARTITIONS': '1', 'KAFKA_TRANSACTION_STATE_LOG_REPLICATION_FACTOR': '1',
            'KAFKA_TRANSACTION_STATE_LOG_MIN_ISR': '1', 'KAFKA_AUTO_CREATE_TOPICS_ENABLE': 'false',
            'KAFKA_NUM_PARTITIONS': '1', 'KAFKA_DEFAULT_REPLICATION_FACTOR': '1', 'KAFKA_MIN_INSYNC_REPLICAS': '1',
            'KAFKA_GROUP_INITIAL_REBALANCE_DELAY_MS': '0', 'KAFKA_LOG_DIRS': '/var/lib/kafka/data/logs',
            'KAFKA_METADATA_LOG_DIR': '/var/lib/kafka/data/metadata', 'KAFKA_HEAP_OPTS': '-Xms512m -Xmx512m'}
        env_args = [item for key, val in kafka_env.items() for item in ('--env', key + '=' + val)]
        broker = owned.create('container', prefix + '-broker', [
            ['create', '--name', prefix + '-broker', '--network', network['id'], '--user', '1000:1000', '--cpus', '1',
             '--memory', '1g', '--memory-swap', '1g', '--pids-limit', '256', '--cap-drop', 'ALL', '--security-opt', 'no-new-privileges',
             '--tmpfs', BROKER_TMPFS, *env_args], [KAFKA]],
             role='broker', image=KAFKA, imageId=broker_image, networkMode=network['id'])
        require(owned.call(['start', broker['id']])[0] == 0, 'UNKNOWN_OUTCOME')
        until = min(owned.deadline, time.monotonic() + 60)
        while True:
            require(time.monotonic() < until, 'DEADLINE_EXCEEDED'); owned.inspect(broker)
            status, _, _ = owned.call(['exec', broker['id'], 'bash', '-c', 'exec 3<>/dev/tcp/127.0.0.1/19092'], min(until, time.monotonic() + 3))
            if status == 0: break
            time.sleep(0.5)
        staged = task / 'it-api'; require(not staged.exists())
        for relative in state['sourceSnapshot']:
            if relative.startswith('apps/api/'):
                target = staged / Path(relative).relative_to('apps/api'); target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(repo / relative, target)
        require(not (staged / 'target').exists())
        mounts = [item for source, target, readonly in [(staged, '/owned/api', False), (task / 'repository', '/owned/repository', False),
            (maven, '/owned/maven', True), (task / 'settings.xml', '/owned/settings.xml', True)]
            for item in ('--mount', 'type=bind,src=' + str(source) + ',dst=' + target + (',readonly' if readonly else ''))]
        test_env = {'SOURCE_COMMIT': state['sourceCommit'], 'LAB_KAFKA_OBSERVATION_TEST_BOOTSTRAP': '127.0.0.1:19092',
            'LAB_KAFKA_OBSERVATION_TEST_DISPOSABLE': 'true', 'LAB_KAFKA_OBSERVATION_TEST_CLUSTER_ID': cluster,
            'MAVEN_SKIP_RC': 'true', 'MAVEN_OPTS': '-Duser.home=/tmp/owned-home'}
        test_args = [item for key, value in test_env.items() for item in ('--env', key + '=' + value)]
        jvm = owned.create('container', prefix + '-jvm', [
            ['create', '--name', prefix + '-jvm', '--network', 'container:' + broker['id'], '--user', str(os.getuid()) + ':' + str(os.getgid()),
             '--cpus', '1', '--memory', '1g', '--memory-swap', '1g', '--pids-limit', '256', '--read-only', '--cap-drop', 'ALL',
             '--security-opt', 'no-new-privileges', '--tmpfs', JVM_TMPFS,
             *mounts, *test_args, '--entrypoint', '/bin/sh'],
            [JDK, '/owned/maven/bin/mvn', '-o', '-B', '-ntp', '-s', '/owned/settings.xml', '-gs', '/owned/settings.xml',
             '-Dmaven.repo.local=/owned/repository', '-f', '/owned/api/pom.xml', '-Dtest=KafkaObservationIT',
             '-DfailIfNoTests=true', '-Dsurefire.failIfNoSpecifiedTests=true', '-Dlab.kafka-observation.tests=true',
             '-DargLine=-Xmx768m -Duser.timezone=Asia/Seoul', 'test']],
             role='jvm', image=JDK, imageId=jdk_image, networkMode='container:' + broker['id'])
        status, out, err = owned.call(['start', '-a', jvm['id']])
        (task / 'it.stdout.log').write_bytes(out); (task / 'it.stderr.log').write_bytes(err)
        value = owned.inspect(jvm)
        require(status == 0 and value['State']['Running'] is False and value['State']['ExitCode'] == 0, 'IT_FAILED')
        reports = list((staged / 'target/surefire-reports').glob('TEST-*.xml'))
        require(len(reports) == 1, 'XML_UNVERIFIED'); xml_hash = verify_xml(reports[0])
        require(source_snapshot(repo, expected) == state['sourceSnapshot'] and artifact_snapshot(task / 'repository') == state['artifactSnapshot'] and tool_snapshot(maven) == state['mavenSnapshot'], 'SOURCE_CHANGED')
        for relative, expected_sha in state['sourceSnapshot'].items():
            if relative.startswith('apps/api/'):
                require(digest(read(staged / Path(relative).relative_to('apps/api'))) == expected_sha, 'SOURCE_CHANGED')
        staged_sources = api_inventory(staged)
        require(staged_sources == {name for name in state['sourceSnapshot'] if name.startswith('apps/api/')}, 'SOURCE_CHANGED')
        require(time.monotonic() <= owned.deadline, 'DEADLINE_EXCEEDED')
        unchanged = True
    except BaseException as error:
        code = error.code if isinstance(error, Failure) else 'UNKNOWN_OUTCOME'
        public_guard_diagnostic(error, 'RUN')
    finally:
        owned.deadline = time.monotonic() + 90
        try:
            cleaned = owned.cleanup()
        except (Failure, OSError, ValueError, KeyError, TypeError, AttributeError):
            cleaned = False
        if not cleaned and code is None: code = 'CLEANUP_UNVERIFIED'
        state['phase'] = 'CLEANED' if cleaned else 'CLEANUP_UNVERIFIED'
        try:
            save_state(task, state)
        except (Failure, OSError, ValueError, KeyError, TypeError):
            cleaned = False
            if code is None: code = 'CLEANUP_UNVERIFIED'
        summary = public_summary(state['sourceCommit'], expected, 'PASSED' if code is None else 'FAILED', code, xml_hash, unchanged, cleaned)
        write_new(repo / PUBLIC, summary)
    return 0 if code is None else 1

def cleanup(repo, environment):
    hosted_context(environment)
    task = repo / PRIVATE
    if not (task / 'state.json').exists(): return 0
    state = load_json(task / 'state.json')
    require(state['sourceCommit'] == environment['SOURCE_COMMIT'] and state['runId'] == environment['GITHUB_RUN_ID'])
    if state['phase'] == 'CLEANED': return 0
    owned = OwnedDocker(task, state, time.monotonic() + 90)
    clean = owned.cleanup(); state['phase'] = 'CLEANED' if clean else 'CLEANUP_UNVERIFIED'; save_state(task, state)
    return 0 if clean else 1

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('phase', choices=['prepare', 'run', 'cleanup'])
    parser.add_argument('--source-manifest-sha256', required=True)
    parser.add_argument('--ack-fresh-hosted-kafka-it', action='store_true', required=True)
    args = parser.parse_args()
    repo = Path(__file__).resolve().parents[2]
    require(repo == Path(os.environ['GITHUB_WORKSPACE']).resolve(strict=True))
    if args.phase == 'prepare': prepare(repo, args.source_manifest_sha256, os.environ); return 0
    if args.phase == 'run': return run(repo, args.source_manifest_sha256, os.environ)
    source_snapshot(repo, args.source_manifest_sha256)
    return cleanup(repo, os.environ)

if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except Failure as error:
        print(json.dumps({'scope': 'KAFKA_IT_RUNNER_FAILURE', 'code': error.code}))
        raise SystemExit(1)
