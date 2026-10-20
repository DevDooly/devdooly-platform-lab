"""Fresh hosted recovery attempt. Definitions only; all execution is explicit.

Candidate intended destination: infra/offset-commit-recovery-ci. Runtime source
manifest is frozen only after Root reviews all Python, Java and documentation.
"""
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
import time
import uuid
import xml.etree.ElementTree as ET

DIR = 'infra/offset-commit-recovery-ci/'
PRIVATE = '.local/offset-commit-recovery-ci/private'
PUBLIC = '.local/offset-commit-recovery-ci-public/summary.json'
MANIFEST = DIR + 'runtime-manifest.json'
BASE = 'infra/kafka-observation-ci/run_once.py'
BASE_MANIFEST = 'infra/kafka-observation-ci/runtime-manifest.json'
COMPILE = 'infra/kafka-acl-ci/run_once.py'
OWNER = DIR + 'runtime_owner.py'
JAVA = {DIR + 'OffsetCommitRecoveryIT.java': 'apps/api/src/test/java/io/github/devdooly/platformlab/jobs/runtime/OffsetCommitRecoveryIT.java',
        DIR + 'OffsetCommitRecoveryProbe.java': 'apps/api/src/test/java/io/github/devdooly/platformlab/jobs/messaging/OffsetCommitRecoveryProbe.java'}
EXTRAS = {BASE_MANIFEST, COMPILE, OWNER, DIR + 'run_once.py', DIR + 'test_runtime_owner.py',
          DIR + 'test_run_once.py', DIR + 'README.ko.md', *JAVA}
CLASS = 'io.github.devdooly.platformlab.jobs.runtime.OffsetCommitRecoveryIT'
METHOD = 'realBrokerPausePersistsCommitFailureAndExplicitResumeRecovers'
PHASES = {'POST_DB_COMMIT_READY': 'post-db-commit-ready.json', 'BROKER_PAUSED': 'broker-paused-ack.json',
          'PAUSED_OBSERVED': 'paused-observed.json', 'BROKER_UNPAUSED': 'broker-unpaused-ack.json'}
MARKER = 'OFFSET_COMMIT_RECOVERY_RESULT '
JAVA_FAILURE_PHASES = frozenset({'TEST_ENTRY', 'SERVICE_GUARDS', 'KAFKA_CREATE', 'STAGE_INPUT',
    'START_FAULT', 'WAIT_DB_COMMIT', 'CHECK_PENDING', 'WAIT_FAULT_EXIT', 'CHECK_PERSISTED_PAUSE',
    'WAIT_UNPAUSE', 'OBSERVE_COMMIT', 'RUN_REFUSAL', 'OPERATOR_RESUME', 'START_RECOVERY',
    'VERIFY_EXPORT', 'VERIFY_FINAL_OFFSET', 'STOP_RECOVERY', 'FINAL_INVARIANTS', 'CLOSE_CLIENTS'})
JAVA_FAILURE_KINDS = frozenset({'ASSERTION', 'INTERRUPTED', 'SQL', 'GROUP_NOT_FOUND', 'UNKNOWN_TOPIC',
    'COORDINATOR_NOT_AVAILABLE', 'COORDINATOR_LOAD_IN_PROGRESS', 'NOT_COORDINATOR', 'TIMEOUT', 'KAFKA_OTHER', 'OTHER'})
NATIVE_SIGNALS = {
    'MAVEN_OFFLINE_ARTIFACT_UNAVAILABLE': (b'Cannot access ', b' in offline mode'),
    'MAVEN_DEPENDENCY_RESOLUTION_FAILED': (b'Could not resolve dependencies for project',),
    'MAVEN_PLUGIN_RESOLUTION_FAILED': (b'Plugin ', b' could not be resolved'),
    'MAVEN_SUREFIRE_FORK_FAILED': (b'The forked VM terminated without properly saying goodbye',),
    'MAVEN_TEST_FAILURE': (b'There are test failures',),
    'MAVEN_NO_MATCHING_TEST': (b'No tests matching pattern',),
    'SPRING_CONTEXT_FAILED': (b'Failed to load ApplicationContext',),
    'JVM_MEMORY_FAILURE': (b'java.lang.OutOfMemoryError',),
    'JAVA_CLASS_UNAVAILABLE': (b'java.lang.NoClassDefFoundError',),
    'FILE_ACCESS_DENIED': (b'java.nio.file.AccessDeniedException',),
}
JAVA_DIAGNOSTIC_SOURCES = {
    'OffsetCommitRecoveryIT.java': (DIR + 'OffsetCommitRecoveryIT.java', JAVA[DIR + 'OffsetCommitRecoveryIT.java'], CLASS),
    'OffsetCommitRecoveryProbe.java': (DIR + 'OffsetCommitRecoveryProbe.java', JAVA[DIR + 'OffsetCommitRecoveryProbe.java'],
        'io.github.devdooly.platformlab.jobs.messaging.OffsetCommitRecoveryProbe'),
    'ContinuousRuntimeIT.java': ('apps/api/src/test/java/io/github/devdooly/platformlab/jobs/runtime/ContinuousRuntimeIT.java',
        'apps/api/src/test/java/io/github/devdooly/platformlab/jobs/runtime/ContinuousRuntimeIT.java',
        'io.github.devdooly.platformlab.jobs.runtime.ContinuousRuntimeIT'),
    'RuntimeProcessProbe.java': ('apps/api/src/test/java/io/github/devdooly/platformlab/jobs/exporting/RuntimeProcessProbe.java',
        'apps/api/src/test/java/io/github/devdooly/platformlab/jobs/exporting/RuntimeProcessProbe.java',
        'io.github.devdooly.platformlab.jobs.exporting.RuntimeProcessProbe'),
}
FIXED_RESULT = {'schemaVersion': 1, 'status': 'PASS', 'fixtureInput': 12, 'successCount': 7,
    'failureCount': 3, 'duplicateCount': 2, 'pendingCount': 0, 'dbCommitBeforeFault': True,
    'pausePersisted': True, 'pauseCode': 'OFFSET_COMMIT_FAILED', 'runRefusedUnchanged': True,
    'operatorResumeRecorded': True, 'readCommittedEndOffset': 1, 'businessRowsAndTimesUnchanged': True,
    'exported': True, 'verifiedExportFiles': 2, 'slotFree': True, 'finalCommittedOffset': 1,
    'finalLag': 0, 'childResourcesClosed': True}
SHA = re.compile(r'[a-f0-9]{64}')
STAGES = frozenset({'PREPARATION_OR_INPUT', 'PREFLIGHT', 'SOURCE_CHECK', 'IMAGE_CHECK', 'FIXTURE_FILES',
    'NETWORK_CREATE', 'KAFKA_CREATE', 'KAFKA_START', 'KAFKA_READY', 'DB_CREATE',
    'GARAGE_CREATE', 'DB_START', 'GARAGE_START', 'DB_READY', 'GARAGE_READY',
    'GARAGE_LAYOUT', 'GARAGE_ACL', 'JVM_CREATE', 'JVM_START', 'POST_DB_WAIT',
    'BROKER_PAUSE', 'PAUSED_WAIT', 'BROKER_UNPAUSE', 'JVM_EXIT', 'XML_RESULT',
    'INVARIANTS', 'CLEANUP', 'STATE_SAVE'})


def failure_diagnostic(error, stage, source_files):
    """Only an actual known-source line and fixed enums may leave private logs."""
    try:
        if stage not in STAGES:
            return None
        selected = None
        trace = error.__traceback__
        visited = 0
        while trace is not None and visited < 64:
            source = source_files.get(trace.tb_frame.f_code.co_filename)
            if (source in ('runner', 'owner', 'base') and trace.tb_frame.f_code.co_name not in {'need', 'require'}
                    and type(trace.tb_lineno) is int and 0 < trace.tb_lineno <= 10000):
                selected = {'stage': stage, 'sourceFile': source, 'sourceLine': trace.tb_lineno}
            trace = trace.tb_next
            visited += 1
        return selected
    except BaseException:
        return None


def need(value):
    if not value:
        raise ValueError('OFFSET_RECOVERY_UNVERIFIED')


def pairs(values):
    result = {}
    for key, val in values:
        need(key not in result)
        result[key] = val
    return result


def read(path, maximum=1048576):
    before = path.lstat()
    need(stat.S_ISREG(before.st_mode) and before.st_nlink == 1 and 0 < before.st_size <= maximum)
    with os.fdopen(os.open(path, os.O_RDONLY | os.O_NOFOLLOW), 'rb') as stream:
        opened = os.fstat(stream.fileno()); raw = stream.read(maximum + 1); closed = os.fstat(stream.fileno())
    identity = lambda x: (x.st_dev, x.st_ino, x.st_mode, x.st_nlink, x.st_size, x.st_mtime_ns, x.st_ctime_ns)
    need(identity(before) == identity(opened) == identity(closed) == identity(path.lstat()) and len(raw) == before.st_size)
    return raw


def descriptor(repo, expected):
    need(type(expected) is str and SHA.fullmatch(expected))
    raw = read(repo / MANIFEST)
    need(hashlib.sha256(raw).hexdigest() == expected)
    value = json.loads(raw, object_pairs_hook=pairs)
    need(type(value) is dict and set(value) == {'schemaVersion', 'scope', 'files'}
         and type(value['schemaVersion']) is int and value['schemaVersion'] == 1
         and value['scope'] == 'HOSTED_LINUX_OFFSET_COMMIT_RECOVERY_SOURCE_ONLY'
         and type(value['files']) is list and len(value['files']) == 118)
    rows = {}
    for row in value['files']:
        need(type(row) is dict and set(row) == {'path', 'bytes', 'sha256'})
        name = row['path']
        need(type(name) is str and name not in rows and not name.startswith('/')
             and '\\' not in name and ':' not in name and '..' not in Path(name).parts
             and Path(name).as_posix() == name and type(row['bytes']) is int and 0 < row['bytes'] <= 1048576
             and type(row['sha256']) is str and SHA.fullmatch(row['sha256']))
        rows[name] = row
    need(EXTRAS <= set(rows) and BASE in rows and not set(JAVA.values()) & set(rows)
         and len([name for name in rows if name.startswith('apps/api/')]) == 106)
    return rows


def load_module(repo, rows, name, label):
    raw = read(repo / name)
    need(len(raw) == rows[name]['bytes'] and hashlib.sha256(raw).hexdigest() == rows[name]['sha256'])
    module = importlib.util.module_from_spec(importlib.util.spec_from_file_location(label, repo / name))
    exec(compile(raw, str(repo / name), 'exec'), module.__dict__)
    return module


def snapshot(base, owner, repo, rows):
    result = {}
    for name, row in rows.items():
        path = repo / name
        for parent in path.parents:
            if parent == repo:
                break
            need(not parent.is_symlink())
        raw = base.read(path)
        need(len(raw) == row['bytes'] and base.digest(raw) == row['sha256'])
        result[name] = row['sha256']
    original = base.load_json(repo / BASE_MANIFEST)
    need(original['scope'] == 'HOSTED_LINUX_KAFKA_IT_SOURCE_ONLY' and len(original['files']) == 109
         and set(rows) == {row['path'] for row in original['files']} | EXTRAS
         and all(rows.get(row['path']) == row for row in original['files'])
         and base.api_inventory(repo / 'apps/api') == {name for name in rows if name.startswith('apps/api/')})
    lock = base.load_json(repo / 'infra/image-lock.json')['images']
    need(set(owner.IMAGES.values()) <= set(lock.values()))
    return result


def hosted(base, repo, environment):
    base.hosted_context(environment)
    need(environment.get('GITHUB_REPOSITORY') == 'DevDooly/devdooly-platform-lab'
         and environment.get('GITHUB_EVENT_NAME') == 'workflow_dispatch'
         and environment.get('GITHUB_REF') == 'refs/heads/main'
         and environment.get('OFFSET_COMMIT_RUNTIME_OPT_IN') == 'true'
         and environment.get('GITHUB_RUN_ATTEMPT') == '1'
         and repo == Path(environment['GITHUB_WORKSPACE']).resolve(strict=True))
    code, out, _ = base.command(['git', '-C', str(repo), 'rev-parse', 'HEAD'], time.monotonic() + 5)
    need(code == 0 and out.decode('ascii').strip() == environment['SOURCE_COMMIT'])


def staged_check(base, task, source):
    staged = task / 'it-api'
    expected = {name: val for name, val in source.items() if name.startswith('apps/api/')}
    expected.update({target: source[name] for name, target in JAVA.items()})
    need(len(expected) == 108 and base.api_inventory(staged) == set(expected))
    for name, val in expected.items():
        need(base.digest(base.read(staged / Path(name).relative_to('apps/api'))) == val)


def bound_state(base, task, expected, environment):
    state = base.load_json(task / 'state.json')
    need(state['sourceCommit'] == environment['SOURCE_COMMIT'] and state['runId'] == environment['GITHUB_RUN_ID']
         and state['manifestSha256'] == expected and re.fullmatch(r'[a-f0-9]{32}', state['nonce']))
    return state


def prepare(base, helper, owner, repo, rows, expected, environment):
    hosted(base, repo, environment)
    source = snapshot(base, owner, repo, rows)
    task = repo / PRIVATE
    need(not task.exists() and not (repo / PUBLIC).exists())
    task.mkdir(parents=True, mode=0o700)
    state = {'schemaVersion': 1, 'phase': 'PREPARING', 'sourceCommit': environment['SOURCE_COMMIT'],
        'runId': environment['GITHUB_RUN_ID'], 'nonce': uuid.uuid4().hex, 'manifestSha256': expected,
        'sourceSnapshot': source, 'resources': [], 'prepared': False, 'controlPhase': 'NOT_STARTED'}
    base.save_state(task, state)
    helper.private_file(base, task / 'settings.xml',
        b'<settings xmlns="http://maven.apache.org/SETTINGS/1.2.0"><interactiveMode>false</interactiveMode>'
        b'<mirrors><mirror><id>owned-public-central-only</id><mirrorOf>*</mirrorOf>'
        b'<url>https://repo.maven.apache.org/maven2</url></mirror></mirrors></settings>\n')
    staged = task / 'it-api'
    for name in source:
        if name.startswith('apps/api/'):
            target = staged / Path(name).relative_to('apps/api')
            target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            shutil.copyfile(repo / name, target)
    for name, relative in JAVA.items():
        target = staged / Path(relative).relative_to('apps/api')
        need(not target.exists())
        target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        shutil.copyfile(repo / name, target)
    need(not (staged / 'target').exists())
    env = base.private_environment(task, Path(environment['JAVA_HOME']).resolve(strict=True))
    env['MAVEN_OPTS'] += ' -Xmx128m'
    deadline = time.monotonic() + 900
    common = helper.maven_arguments(task, staged)
    base.checked_command(['sh', str(staged / 'mvnw'), *common, '-DskipTests', 'test-compile'], deadline, environment=env)
    candidates = [x for x in (task / 'wrapper-home').rglob('bin/mvn') if x.is_file() and not x.is_symlink()]
    need(len(candidates) == 1)
    maven = candidates[0].parent.parent.resolve(strict=True)
    need(maven.is_relative_to(task / 'wrapper-home'))
    version = base.checked_command(['sh', str(maven / 'bin/mvn'), '-version'], deadline, environment=env).decode('utf8')
    need(re.search(r'Apache Maven 3\.10\.0(?:\s|\x1b)', version) and re.search(r'Java version: 21(?:\.|,)', version))
    surefire, dependency = helper.managed_plugin_versions(base, task)
    plugin = 'org.apache.maven.plugins:maven-dependency-plugin:' + dependency
    base.checked_command(['sh', str(maven / 'bin/mvn'), *common, plugin + ':go-offline'], deadline, environment=env)
    engines = list((task / 'repository/org/junit/platform/junit-platform-engine').glob('*/*.jar'))
    need(len(engines) == 1 and re.fullmatch(r'[0-9]+\.[0-9]+\.[0-9]+', engines[0].parent.name))
    for artifact in ('org.apache.maven.surefire:surefire-junit-platform:' + surefire,
                     'org.junit.platform:junit-platform-launcher:' + engines[0].parent.name):
        base.checked_command(['sh', str(maven / 'bin/mvn'), *common, plugin + ':get',
                              '-Dartifact=' + artifact, '-Dtransitive=true'], deadline, environment=env)
    need(not list((staged / 'target').rglob('TEST-*.xml')))
    staged_check(base, task, source)
    owned = owner.OwnedDocker(base, task, state, deadline)
    state['images'] = {role: owned.image(image, allow_pull=True) for role, image in owner.IMAGES.items()}
    state.update(mavenRelativePath=maven.relative_to(task).as_posix(),
        artifactSnapshot=base.artifact_snapshot(task / 'repository'), mavenSnapshot=base.tool_snapshot(maven),
        phase='PREPARED', prepared=True)
    need(snapshot(base, owner, repo, rows) == source and time.monotonic() < deadline)
    base.save_state(task, state)


def phase_bytes(state, phase):
    need(phase in PHASES)
    return (json.dumps({'schemaVersion': 1, 'sourceCommit': state['sourceCommit'], 'runId': state['runId'],
                        'nonce': state['nonce'], 'phase': phase}, sort_keys=True, separators=(',', ':')) + '\n').encode('ascii')


def phase_read(folder, state, phase):
    details = folder.lstat()
    need(stat.S_ISDIR(details.st_mode) and details.st_uid == os.getuid()
         and stat.S_IMODE(details.st_mode) == 0o700 and not folder.is_symlink())
    path = folder / PHASES[phase]
    if not os.path.lexists(path):
        return False
    info = path.lstat()
    need(info.st_uid == os.getuid() and stat.S_IMODE(info.st_mode) == 0o600)
    need(read(path, 1024) == phase_bytes(state, phase))
    return True


def phase_write(folder, state, phase):
    need(not os.path.lexists(folder / PHASES[phase]))
    temporary = folder / ('.' + PHASES[phase] + '.pending')
    fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, 'wb') as stream:
        stream.write(phase_bytes(state, phase)); stream.flush(); os.fsync(stream.fileno())
    need(not os.path.lexists(folder / PHASES[phase]))
    os.rename(temporary, folder / PHASES[phase])
    need(phase_read(folder, state, phase))


def await_phase(owned, folder, state, phase, containers, deadline):
    while time.monotonic() < deadline:
        for row in containers:
            value = owned.inspect(row, allow_paused=row['role'] == 'kafka')
            need(value['State']['Running'] is True)
        if phase_read(folder, state, phase):
            return
        time.sleep(.1)
    need(False)


def kafka_environment(cluster):
    return {'CLUSTER_ID': cluster, 'KAFKA_NODE_ID': '1', 'KAFKA_PROCESS_ROLES': 'broker,controller',
        'KAFKA_LISTENERS': 'BROKER://127.0.0.1:19092,CONTROLLER://127.0.0.1:19093',
        'KAFKA_ADVERTISED_LISTENERS': 'BROKER://127.0.0.1:19092', 'KAFKA_CONTROLLER_QUORUM_VOTERS': '1@127.0.0.1:19093',
        'KAFKA_LISTENER_SECURITY_PROTOCOL_MAP': 'BROKER:PLAINTEXT,CONTROLLER:PLAINTEXT',
        'KAFKA_INTER_BROKER_LISTENER_NAME': 'BROKER', 'KAFKA_CONTROLLER_LISTENER_NAMES': 'CONTROLLER',
        'KAFKA_OFFSETS_TOPIC_REPLICATION_FACTOR': '1', 'KAFKA_OFFSETS_TOPIC_NUM_PARTITIONS': '1',
        'KAFKA_TRANSACTION_STATE_LOG_REPLICATION_FACTOR': '1', 'KAFKA_TRANSACTION_STATE_LOG_MIN_ISR': '1',
        'KAFKA_AUTO_CREATE_TOPICS_ENABLE': 'false', 'KAFKA_NUM_PARTITIONS': '1',
        'KAFKA_DEFAULT_REPLICATION_FACTOR': '1', 'KAFKA_MIN_INSYNC_REPLICAS': '1',
        'KAFKA_GROUP_INITIAL_REBALANCE_DELAY_MS': '0', 'KAFKA_LOG_DIRS': '/var/lib/kafka/data/logs',
        'KAFKA_METADATA_LOG_DIR': '/var/lib/kafka/data/metadata', 'KAFKA_HEAP_OPTS': '-Xms512m -Xmx512m'}


def profile(owner, role, image, environment, *, user=None, entrypoint=None, cmd=None, binds=None):
    return {'memory': owner.MEMORY[role], 'readonly': role in {'garage', 'jvm'},
        'user': user if user is not None else image['user'], 'entrypoint': entrypoint if entrypoint is not None else image['entrypoint'],
        'cmd': cmd if cmd is not None else image['cmd'], 'env': image['env'] | environment,
        'tmpfs': owner.TMPFS[role], 'binds': binds or {}}


def exec_ready(owned, row, command, deadline):
    while time.monotonic() < deadline:
        code, out, _ = owned.execute(row, command, min(deadline, time.monotonic() + 5))
        if code == 0:
            return out
        time.sleep(.5)
    need(False)


def garage_call(owned, garage, *args):
    code, raw, _ = owned.execute(garage, ['/garage', '-c', '/etc/garage.toml', *args])
    need(code == 0)
    return raw


def parse_result(text):
    found = None
    for line in text.splitlines():
        if not line.startswith('OFFSET_COMMIT_RECOVERY_'):
            continue
        need(line.startswith(MARKER) and found is None)
        value = json.loads(line[len(MARKER):], object_pairs_hook=pairs)
        if type(value) is dict and value.get('status') == 'FAIL':
            need(set(value) == {'schemaVersion', 'status', 'failureCode', 'failurePhase', 'failureKind', 'failureSourceLine'}
                 and type(value['schemaVersion']) is int and value['schemaVersion'] == 1
                 and value['failureCode'] == 'VALIDATION_FAILED'
                 and type(value['failurePhase']) is str and value['failurePhase'] in JAVA_FAILURE_PHASES
                 and type(value['failureKind']) is str and value['failureKind'] in JAVA_FAILURE_KINDS
                 and (value['failureSourceLine'] is None or type(value['failureSourceLine']) is int
                      and 0 < value['failureSourceLine'] <= 10000))
            found = value
            continue
        need(type(value) is dict and set(value) == set(FIXED_RESULT) | {
            'postUnpauseCommitState', 'postUnpauseCommittedOffset', 'completedReplays'}
            and all(type(value[key]) is type(expected) and value[key] == expected for key, expected in FIXED_RESULT.items())
            and type(value['completedReplays']) is int and value['completedReplays'] in (0, 1)
            and ((value['postUnpauseCommitState'] == 'NO_COMMIT' and value['postUnpauseCommittedOffset'] is None)
                 or (value['postUnpauseCommitState'] == 'OBSERVED' and type(value['postUnpauseCommittedOffset']) is int
                     and value['postUnpauseCommittedOffset'] == 1)))
        found = value
    return found


def selected_result(base, task):
    reports = list((task / 'it-api/target/surefire-reports').glob('TEST-*.xml'))
    need(len(reports) == 1)
    raw = base.read(reports[0], 1048576)
    need(b'<!DOCTYPE' not in raw and b'<!ENTITY' not in raw)
    root = ET.fromstring(raw); cases = root.findall('testcase')
    need(root.tag == 'testsuite' and root.get('name') == CLASS and len(cases) == 1
         and cases[0].get('classname') == CLASS and cases[0].get('name') == METHOD)
    result = parse_result('\n'.join(node.text or '' for node in [*root.findall('system-out'), *cases[0].findall('system-out')]))
    return reports[0], result


def native_signals(raw):
    """Classify observed text signatures, never declare them a proven root cause."""
    need(type(raw) is bytes and len(raw) <= 1048576)
    lines = raw.splitlines()
    return sorted(name for name, parts in NATIVE_SIGNALS.items()
                  if any(all(part in line for part in parts) for line in lines))


def validated_java_failure(task, source, value):
    """Do not publish a claimed original IT line without its exact source bytes."""
    need(type(value) is dict and value.get('status') == 'FAIL')
    line = value['failureSourceLine']
    if line is None:
        return value
    need(type(line) is int and 0 < line <= 10000)
    key, relative, _ = JAVA_DIAGNOSTIC_SOURCES['OffsetCommitRecoveryIT.java']
    expected = source.get(key)
    need(type(expected) is str and SHA.fullmatch(expected))
    path = task / 'it-api' / Path(relative).relative_to('apps/api')
    need(not any(parent.is_symlink() for parent in path.parents if parent.is_relative_to(task)))
    raw = read(path)
    need(hashlib.sha256(raw).hexdigest() == expected and line <= len(raw.decode('utf8', 'strict').splitlines()))
    return value


def java_frames(task, source, text):
    """Only line references into the hash-matched four known public Java files."""
    need(type(text) is str and len(text.encode('utf8')) <= 2097152)
    found = set()
    for name, (key, relative, classname) in JAVA_DIAGNOSTIC_SOURCES.items():
        expected = source.get(key)
        if type(expected) is not str or not SHA.fullmatch(expected):
            continue
        path = task / 'it-api' / Path(relative).relative_to('apps/api')
        try:
            need(not any(parent.is_symlink() for parent in path.parents if parent.is_relative_to(task)))
            raw = read(path)
            need(hashlib.sha256(raw).hexdigest() == expected)
            total = len(raw.decode('utf8', 'strict').splitlines())
        except Exception:
            continue
        pattern = re.compile(r'^[ \t]*at ' + re.escape(classname)
            + r'(?:\$[A-Za-z0-9_$]+)?\.[A-Za-z0-9_$<>]{1,128}\('
            + re.escape(name) + r':([1-9][0-9]{0,3})\)[ \t]*$')
        for line in text.splitlines():
            match = pattern.fullmatch(line)
            if match and int(match.group(1)) <= total:
                found.add((name, int(match.group(1))))
    return [{'sourceFile': name, 'sourceLine': line} for name, line in sorted(found)][:8]


def junit_failure_projection(task):
    """Private report text stays in memory; selected counts never mean test PASS."""
    reports = task / 'it-api/target/surefire-reports'
    path = reports / ('TEST-' + CLASS + '.xml')
    if not os.path.lexists(path):
        return 'ABSENT', None, ''
    try:
        need(not any(parent.is_symlink() for parent in (task / 'it-api', reports.parent, reports)))
        need(list(reports.glob('TEST-*.xml')) == [path])
        raw = read(path, 1048576)
        need(b'<!DOCTYPE' not in raw and b'<!ENTITY' not in raw)
        root = ET.fromstring(raw); cases = root.findall('testcase')
        need(root.tag == 'testsuite' and root.get('name') == CLASS and len(cases) == 1
             and cases[0].get('classname') == CLASS and cases[0].get('name') == METHOD)
        keys = ('tests', 'failures', 'errors', 'skipped')
        need(all(root.get(key) in ('0', '1') for key in keys) and root.get('tests') == '1')
        counts = {key: int(root.get(key)) for key in keys}
        need(sum(counts[key] for key in keys[1:]) <= 1)
        problems = [node for node in cases[0] if node.tag in ('failure', 'error', 'skipped')]
        need(len(problems) == sum(counts[key] for key in keys[1:])
             and all(counts[{'failure': 'failures', 'error': 'errors', 'skipped': 'skipped'}[node.tag]] == 1 for node in problems))
        selected = [*problems, *root.findall('system-out'), *cases[0].findall('system-out')]
        text = '\n'.join(node.text or '' for node in selected)
        need(len(text.encode('utf8')) <= 1048576)
        return 'VERIFIED', counts, text
    except Exception:
        return 'UNVERIFIED', None, ''


def exited_jvm_diagnostic(owned, row, task, source):
    """Best-effort bounded observation of this exact already-exited owned JVM."""
    try:
        need(type(row) is dict and row.get('role') == 'jvm')
        value = owned.inspect(row); state = value['State']
        need(state['Status'] == 'exited' and state['Running'] is False and state['Paused'] is False
             and type(state['ExitCode']) is int and 0 <= state['ExitCode'] <= 255
             and type(state['OOMKilled']) is bool)
        raw, log_status = b'', 'UNAVAILABLE'
        try:
            status, stdout, stderr = owned.call(['logs', '--tail', '200', row['id']],
                min(owned.deadline, time.monotonic() + 5))
            need(status == 0 and type(stdout) is bytes and type(stderr) is bytes
                 and len(stdout) + len(stderr) <= 1048576)
            raw, log_status = stdout + b'\n' + stderr, 'READ'
            need(len(raw) <= 1048576)
        except Exception:
            raw, log_status = b'', 'UNAVAILABLE'
        after = owned.inspect(row)['State']
        need(all(after[key] == state[key] and type(after[key]) is type(state[key])
                 for key in ('Status', 'Running', 'Paused', 'StartedAt', 'ExitCode', 'OOMKilled')))
        report_status, counts, report_text = junit_failure_projection(task)
        text = raw.decode('utf8', 'replace') + '\n' + report_text
        need(len(text.encode('utf8')) <= 2097152)
        selected = None
        for candidate in (report_text, raw.decode('utf8', 'replace')):
            try:
                projected = parse_result(candidate)
                need(projected is None or projected['status'] == 'FAIL')
                if projected is not None:
                    projected = validated_java_failure(task, source, projected)
            except Exception:
                continue
            if projected is not None:
                if selected is not None and selected != projected:
                    selected = None
                    break
                selected = projected
        return {'schemaVersion': 1, 'status': 'OWNED_JVM_EXITED', 'exitCode': state['ExitCode'],
            'oomKilled': state['OOMKilled'], 'nativeLogStatus': log_status, 'observedSignals': native_signals(raw),
            'junitReportStatus': report_status, 'junitCounts': counts,
            'javaFrames': java_frames(task, source, text), 'javaFailure': selected}
    except BaseException:
        return None


def run(base, helper, owner, repo, rows, expected, environment):
    hosted(base, repo, environment)
    task = repo / PRIVATE
    state = bound_state(base, task, expected, environment)
    need(state['phase'] == 'PREPARED' and state['prepared'] is True and not state['resources'])
    owned = owner.OwnedDocker(base, task, state, time.monotonic() + 30)
    code, result, xml_hash, unchanged, cleaned = None, None, None, False, False
    stage, diagnostic, jvm, jvm_diagnostic = 'PREFLIGHT', None, None, None
    diagnostic_sources = {__file__: 'runner', str(repo / OWNER): 'owner', str(repo / BASE): 'base'}
    try:
        stage = 'SOURCE_CHECK'
        need(os.getuid() > 0 and os.getgid() > 0 and snapshot(base, owner, repo, rows) == state['sourceSnapshot'])
        maven = (task / state['mavenRelativePath']).resolve(strict=True)
        need(maven.is_relative_to(task / 'wrapper-home') and base.tool_snapshot(maven) == state['mavenSnapshot']
             and base.artifact_snapshot(task / 'repository') == state['artifactSnapshot'])
        staged_check(base, task, state['sourceSnapshot'])
        need(not (task / 'it-api/target/surefire-reports').exists())
        stage = 'IMAGE_CHECK'
        need({role: owned.image(image) for role, image in owner.IMAGES.items()} == state['images'])
        stage = 'FIXTURE_FILES'
        state.update(phase='RUN_INTENT', runtimeUser=str(os.getuid()) + ':' + str(os.getgid()))
        owned.save()
        folder = task / 'it-api/target/offset-control'
        need(not folder.exists())
        folder.mkdir(mode=0o700)
        cluster = base64.urlsafe_b64encode(uuid.uuid4().bytes).decode().rstrip('=')
        db_password, root_password = secrets.token_hex(24), secrets.token_hex(24)
        db_env = {'MARIADB_ROOT_PASSWORD': root_password, 'MARIADB_DATABASE': 'platform_lab_runtime_it',
                  'MARIADB_USER': 'runtimeit', 'MARIADB_PASSWORD': db_password}
        kafka_env = kafka_environment(cluster)
        for name, values in (('kafka.env', kafka_env), ('db.env', db_env)):
            helper.private_file(base, task / name, ''.join(key + '=' + val + '\n' for key, val in values.items()).encode('ascii'))
        config = ('metadata_dir="/meta"\ndata_dir="/data"\ndb_engine="sqlite"\nreplication_factor=1\n'
            'rpc_secret="' + secrets.token_hex(32) + '"\nrpc_bind_addr="127.0.0.1:3901"\nrpc_public_addr="127.0.0.1:3901"\n'
            '[s3_api]\ns3_region="garage"\napi_bind_addr="127.0.0.1:3900"\nroot_domain=".s3.invalid"\n')
        helper.private_file(base, task / 'garage.private.toml', config.encode('ascii'))
        (task / 'garage.private.toml').chmod(0o444)
        owned.deadline = time.monotonic() + 600
        stage = 'NETWORK_CREATE'
        network = owned.network()
        stage = 'KAFKA_CREATE'
        broker = owned.container('kafka', owner.IMAGES['kafka'], state['images']['kafka'], network['id'],
            profile(owner, 'kafka', state['images']['kafka'], kafka_env, user='1000:1000'), env_file=task / 'kafka.env')
        stage = 'KAFKA_START'
        owned.start(broker)
        stage = 'KAFKA_READY'
        exec_ready(owned, broker, ['bash', '-c', 'exec 3<>/dev/tcp/127.0.0.1/19092'], min(owned.deadline, time.monotonic() + 60))
        shared = 'container:' + broker['id']
        stage = 'DB_CREATE'
        db = owned.container('db', owner.IMAGES['db'], state['images']['db'], shared,
            profile(owner, 'db', state['images']['db'], db_env), env_file=task / 'db.env')
        stage = 'GARAGE_CREATE'
        garage = owned.container('garage', owner.IMAGES['garage'], state['images']['garage'], shared,
            profile(owner, 'garage', state['images']['garage'], {}, user='1000:1000', entrypoint=['/garage'],
                cmd=['-c', '/etc/garage.toml', 'server'], binds={'/etc/garage.toml': [str(task / 'garage.private.toml'), False]}))
        stage = 'DB_START'
        owned.start(db)
        stage = 'GARAGE_START'
        owned.start(garage)
        stage = 'DB_READY'
        exec_ready(owned, db, ['healthcheck.sh', '--connect', '--innodb_initialized'], min(owned.deadline, time.monotonic() + 120))
        stage = 'GARAGE_READY'
        raw = exec_ready(owned, garage, ['/garage', '-c', '/etc/garage.toml', 'node', 'id', '--quiet'], min(owned.deadline, time.monotonic() + 60))
        node = raw.decode('ascii').strip().split('@')[0]
        need(SHA.fullmatch(node))
        need(re.match(r'^garage v2\.4\.1(?:\s|$)', garage_call(owned, garage, '--version').decode('ascii').strip()))
        stage = 'GARAGE_LAYOUT'
        garage_call(owned, garage, 'layout', 'assign', '-z', 'github-isolated', '-c', '128M', node)
        garage_call(owned, garage, 'layout', 'apply', '--version', '1')
        bucket_name = 'platform-lab-s3-test-' + state['nonce']
        stage = 'GARAGE_ACL'
        bucket = json.loads(garage_call(owned, garage, 'json-api', 'CreateBucket', json.dumps({'globalAlias': bucket_name})))
        key = json.loads(garage_call(owned, garage, 'json-api', 'CreateKey', json.dumps({'name': owned.prefix})))
        garage_call(owned, garage, 'json-api', 'AllowBucketKey', json.dumps({'bucketId': bucket['id'],
            'accessKeyId': key['accessKeyId'], 'permissions': {'read': True, 'write': True, 'owner': False}}))
        acl = json.loads(garage_call(owned, garage, 'json-api', 'GetKeyInfo', json.dumps({'id': key['accessKeyId'], 'showSecretKey': False})))
        need(acl['accessKeyId'] == key['accessKeyId'] and acl['permissions']['createBucket'] is False
             and len(acl['buckets']) == 1 and acl['buckets'][0]['id'] == bucket['id']
             and acl['buckets'][0]['permissions'] == {'read': True, 'write': True, 'owner': False})
        env = {'SOURCE_COMMIT': state['sourceCommit'], 'DB_TEST_URL': 'jdbc:mariadb://127.0.0.1:3306/platform_lab_runtime_it',
            'DB_TEST_USERNAME': 'runtimeit', 'DB_TEST_PASSWORD': db_password, 'LAB_KAFKA_TEST_BOOTSTRAP': '127.0.0.1:19092',
            'LAB_KAFKA_TEST_CLUSTER_ID': cluster, 'LAB_S3_TEST_ENDPOINT': 'http://127.0.0.1:3900',
            'LAB_S3_TEST_BUCKET': bucket_name, 'LAB_S3_TEST_ACCESS_KEY': key['accessKeyId'], 'LAB_S3_TEST_SECRET_KEY': key['secretAccessKey'],
            'OFFSET_CONTROL_DIR': '/owned/api/target/offset-control', 'OFFSET_CONTROL_NONCE': state['nonce'],
            'OFFSET_CONTROL_RUN_ID': state['runId'], 'MAVEN_SKIP_RC': 'true', 'MAVEN_OPTS': '-Xmx128m -Duser.home=/tmp/owned-home'}
        helper.private_file(base, task / 'jvm.env', ''.join(k + '=' + v + '\n' for k, v in env.items()).encode('ascii'))
        cmd = ['/owned/maven/bin/mvn', '-o', '-B', '-ntp', '-s', '/owned/settings.xml', '-gs', '/owned/settings.xml',
            '-Dmaven.repo.local=/owned/repository', '-f', '/owned/api/pom.xml', '-Dtest=OffsetCommitRecoveryIT#' + METHOD,
            '-DfailIfNoTests=true', '-Dsurefire.failIfNoSpecifiedTests=true', '-Dlab.offset-recovery.tests=true',
            '-DargLine=-Xmx512m -Duser.timezone=Asia/Seoul', 'test']
        binds = {'/owned/api': [str(task / 'it-api'), True], '/owned/repository': [str(task / 'repository'), True],
                 '/owned/maven': [str(maven), False], '/owned/settings.xml': [str(task / 'settings.xml'), False]}
        stage = 'JVM_CREATE'
        jvm = owned.container('jvm', owner.IMAGES['jvm'], state['images']['jvm'], shared,
            profile(owner, 'jvm', state['images']['jvm'], env, user=state['runtimeUser'], entrypoint=['/bin/sh'], cmd=cmd, binds=binds), env_file=task / 'jvm.env')
        stage = 'JVM_START'
        owned.start(jvm)
        containers = [broker, db, garage, jvm]
        stage = 'POST_DB_WAIT'
        await_phase(owned, folder, state, 'POST_DB_COMMIT_READY', containers, owned.deadline)
        state['controlPhase'] = 'POST_DB_COMMIT_READY'; owned.save()
        stage = 'BROKER_PAUSE'
        owned.pause(broker)
        phase_write(folder, state, 'BROKER_PAUSED')
        stage = 'PAUSED_WAIT'
        await_phase(owned, folder, state, 'PAUSED_OBSERVED', containers, owned.deadline)
        state['controlPhase'] = 'PAUSED_OBSERVED'; owned.save()
        stage = 'BROKER_UNPAUSE'
        owned.unpause(broker)
        state['controlPhase'] = 'BROKER_UNPAUSED'; owned.save()
        phase_write(folder, state, 'BROKER_UNPAUSED')
        stage = 'JVM_EXIT'
        while time.monotonic() < owned.deadline:
            value = owned.inspect(jvm)
            if not value['State']['Running']:
                break
            for row in (broker, db, garage):
                need(owned.inspect(row)['State']['Running'] is True)
            time.sleep(.1)
        need(time.monotonic() < owned.deadline and value['State']['ExitCode'] == 0 and value['State']['OOMKilled'] is False)
        stage = 'XML_RESULT'
        report, result = selected_result(base, task)
        need(result is not None and result['status'] == 'PASS')
        xml_hash = base.verify_xml(report, CLASS, METHOD)
        stage = 'INVARIANTS'
        need(snapshot(base, owner, repo, rows) == state['sourceSnapshot']
             and base.artifact_snapshot(task / 'repository') == state['artifactSnapshot']
             and base.tool_snapshot(maven) == state['mavenSnapshot'])
        staged_check(base, task, state['sourceSnapshot'])
        need(time.monotonic() < owned.deadline)
        unchanged = True
    except BaseException as error:
        code = 'RECOVERY_UNVERIFIED'
        diagnostic = failure_diagnostic(error, stage, diagnostic_sources)
        if jvm is not None:
            jvm_diagnostic = exited_jvm_diagnostic(owned, jvm, task, state['sourceSnapshot'])
    finally:
        owned.deadline = time.monotonic() + 180
        try:
            stage = 'CLEANUP'
            cleaned = owned.cleanup()
        except BaseException as error:
            cleaned = False
            if diagnostic is None:
                diagnostic = failure_diagnostic(error, stage, diagnostic_sources)
        if not cleaned:
            code = code or 'CLEANUP_UNVERIFIED'
        state['phase'] = 'CLEANED' if cleaned else 'CLEANUP_UNVERIFIED'
        try:
            stage = 'STATE_SAVE'
            owned.save()
        except BaseException as error:
            cleaned = False; code = code or 'CLEANUP_UNVERIFIED'
            if diagnostic is None:
                diagnostic = failure_diagnostic(error, stage, diagnostic_sources)
        base.write_new(repo / PUBLIC, {'schemaVersion': 1, 'scope': 'ISOLATED_REAL_OFFSET_COMMIT_RECOVERY',
            'synthetic': True, 'sourceCommit': state['sourceCommit'], 'runtimeManifestSha256': expected,
            'status': 'PASSED' if code is None else 'FAILED', 'failureCode': code, 'expectedTests': 1,
            'selectedFailure': diagnostic,
            'jvmFailure': jvm_diagnostic,
            'verifiedTests': 1 if xml_hash else 0, 'surefireXmlSha256': xml_hash,
            'recoveryResult': result if code is None else None, 'ownedResourcesRemoved': cleaned,
            'sourceAndArtifactsUnchanged': unchanged, 'operatingServicesChanged': False,
            'hostOrBrokerRestartVerified': False, 'publicExecutionEnabled': False})
    return 0 if code is None else 1


def cleanup(base, owner, repo, expected, environment):
    hosted(base, repo, environment)
    task = repo / PRIVATE
    if not (task / 'state.json').exists():
        return 0
    state = bound_state(base, task, expected, environment)
    if state['phase'] == 'CLEANED':
        return 0
    owned = owner.OwnedDocker(base, task, state, time.monotonic() + 180)
    clean = owned.cleanup()
    state['phase'] = 'CLEANED' if clean else 'CLEANUP_UNVERIFIED'
    owned.save()
    return 0 if clean else 1


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('phase', choices=['prepare', 'run', 'cleanup'])
    parser.add_argument('--source-manifest-sha256', required=True)
    parser.add_argument('--ack-fresh-hosted-offset-commit-it', action='store_true', required=True)
    args = parser.parse_args()
    repo = Path(__file__).resolve().parents[2]
    rows = descriptor(repo, args.source_manifest_sha256)
    base = load_module(repo, rows, BASE, 'reviewed_offset_base')
    owner = load_module(repo, rows, OWNER, 'reviewed_offset_owner')
    if args.phase == 'cleanup':
        return cleanup(base, owner, repo, args.source_manifest_sha256, os.environ)
    helper = load_module(repo, rows, COMPILE, 'reviewed_offset_compile')
    if args.phase == 'prepare':
        prepare(base, helper, owner, repo, rows, args.source_manifest_sha256, os.environ)
        return 0
    return run(base, helper, owner, repo, rows, args.source_manifest_sha256, os.environ)


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except Exception as error:
        diagnostic = None
        try:
            root = Path(__file__).resolve().parents[2]
            diagnostic = failure_diagnostic(error, 'PREPARATION_OR_INPUT',
                {__file__: 'runner', str(root / OWNER): 'owner', str(root / BASE): 'base'})
        except BaseException:
            pass
        print(json.dumps({'scope': 'OFFSET_COMMIT_RUNNER_FAILURE', 'failureCode': 'PREPARATION_OR_INPUT_UNVERIFIED',
                          'selectedFailure': diagnostic}))
        raise SystemExit(1)
