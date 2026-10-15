"""One GitHub-hosted MariaDB/Garage compatibility attempt using existing ITs."""
import datetime as dt
import hashlib
import ipaddress
import json
import os
from pathlib import Path
import re
import secrets
import signal
import stat
import subprocess
import sys
import time
import xml.etree.ElementTree as ET
import zipfile
from loopback_relay import LoopbackRelay
from surefire_diagnostic import collect as collect_it_diagnostics, empty_diagnostics, report_paths

sys.dont_write_bytecode = True
MARIADB = 'mariadb:11.8.9@sha256:6422478cb8e159f080fb1d8ccf65101e26fe51385787fde7d16c3b165a331f15'
GARAGE = 'dxflrs/garage@sha256:0d7c74fc8ca6fef68a5a941c0e7558c8b1e92ba3588fa7505400e1350456c796'
LABEL = 'devdooly.io.s3-ci-project'
SOURCE_FILES = {
    'pom.xml': '5d81050c5ecda2cb75b8a97c42ea828d9fe29297cd5cce32995ad1ab8d03262e',
    'src/main/java/io/github/devdooly/platformlab/jobs/S3ClientFactory.java': '1a225ab7e8ca9942c2d632557ddbab4246a6769c21a16a8b93c1d82edaf67422',
    'src/test/java/io/github/devdooly/platformlab/jobs/S3ManagedReadDeadlineTest.java': '61429a3b55e4d1c102214814254da99b7021b4edcdc649065a47d84d43603675',
}
RAW_CASES = (
    'realSdkPutGetHeadListDeleteAndStoreRetryVerifyActualBytes',
    'realCoordinatorStagesAndRepeatPreservesQueuedAndCompletedMetadata',
    'realExistingCorruptionIsRetainedAndDbRemainsStagingWithoutDispatch',
    'realObjectSurvivesFailedDbMarkAndIsReverifiedOnRetry',
)
EXPORT_CASE = 'actualResultAndFailuresAreVerifiedBeforeReleaseAndRepeatsCannotReleaseNextJobsSlot'
SELECTION = 'GarageRawSourceIT#' + '+'.join(RAW_CASES) + ',VerifiedResultExportIT#' + EXPORT_CASE
SCOPE = 'ISOLATED_GITHUB_RUNNER_APACHE5_MARIADB_GARAGE'
CONNECTIVITY_PROFILE = 'OWNED_INTERNAL_BRIDGE_HOST_LOOPBACK_TCP_RELAYS'


def require(value, code):
    if not value:
        raise RuntimeError(code)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def utc():
    return dt.datetime.now(dt.timezone.utc).isoformat().replace('+00:00', 'Z')


def save(path, raw):
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, 'wb') as stream:
        stream.write(raw); stream.flush(); os.fsync(stream.fileno())


def save_json(path, value):
    save(path, (json.dumps(value, sort_keys=True, indent=2, allow_nan=False) + '\n').encode())


def source_identity(api):
    for name, digest in SOURCE_FILES.items():
        path = api / name
        require(path.is_file() and not path.is_symlink() and sha(path.read_bytes()) == digest,
                'EXACT_FROZEN_APACHE5_SOURCE_REQUIRED')


def jar_identity(api):
    jars = list((api / 'target').glob('*.jar'))
    require(len(jars) == 1 and jars[0].is_file() and not jars[0].is_symlink(), 'ONE_BUILT_API_JAR')
    path = jars[0]
    with zipfile.ZipFile(path) as jar:
        names = jar.namelist()
        require(len(names) == len(set(names)) and 'BOOT-INF/lib/apache5-client-2.55.16.jar' in names
                and not any('/url-connection-client-' in name for name in names), 'ACTUAL_PINNED_APACHE5_IN_API_JAR')
        classes = list((api / 'target/classes/io/github/devdooly/platformlab/jobs').glob('S3ClientFactory*.class'))
        classes += [api / 'target/classes/io/github/devdooly/platformlab/jobs/S3RawSourceStore.class',
                    api / 'target/classes/io/github/devdooly/platformlab/jobs/exporting/S3ResultExportStore.class']
        require(len(classes) >= 4 and all(path.is_file() for path in classes), 'COMPILED_FACTORY_AND_BOTH_ADAPTERS')
        for compiled in classes:
            entry = 'BOOT-INF/classes/' + compiled.relative_to(api / 'target/classes').as_posix()
            require(jar.read(entry) == compiled.read_bytes(), 'TESTED_CLASS_BYTES_EQUAL_BUILT_API_JAR')
    return {'sha256': sha(path.read_bytes()), 'bytes': path.stat().st_size, 'apache5Sdk': '2.55.16',
            'testedAdapterClassesMatchJar': True}


def container_guard(value, cid, name, project, image_id, network, binds):
    require(value['Id'] == cid and re.fullmatch('[a-f0-9]{64}', cid)
            and value['Name'] == '/' + name and value['Config']['Labels'].get(LABEL) == project
            and value['Image'] == image_id and value['HostConfig']['RestartPolicy']['Name'] == 'no',
            'EXACT_OWNED_CONTAINER_ID_NAME_LABEL_IMAGE')
    require(set(value['NetworkSettings']['Networks']) == {network}, 'ONLY_OWNED_CONTAINER_NETWORK')
    actual = value['HostConfig'].get('Binds') or []
    expected = {name + ':' + target + ':' + mode for name, target, mode in binds}
    normalized = {item + ':rw' if item.count(':') == 1 else item for item in actual}
    require(len(actual) == len(normalized) == len(expected) and normalized == expected, 'EXACT_NAMED_VOLUME_AND_CONFIG_BINDS')
    require(value['State']['OOMKilled'] is False, 'OWNED_CONTAINER_OOM_FORBIDDEN')


def port_binding_diagnostic(value, container_port):
    """Public fixed fields only: requested configuration is never a live-port fallback."""
    target = str(container_port) + '/tcp'

    def projection(parent, key):
        if not isinstance(parent, dict) or key not in parent:
            return 'UNOBSERVED', None, None
        ports = parent[key]
        if not isinstance(ports, dict):
            return 'MALFORMED', None, None
        if target not in ports:
            return 'TARGET_MISSING', ports, None
        entries = ports[target]
        if entries is None:
            return 'TARGET_UNPUBLISHED', ports, None
        if not isinstance(entries, list) or len(entries) != 1:
            return 'TARGET_INVALID_COUNT', ports, None
        entry = entries[0]
        if not isinstance(entry, dict) or not isinstance(entry.get('HostIp'), str) or not isinstance(entry.get('HostPort'), str):
            return 'TARGET_MALFORMED', ports, None
        return 'SINGLE_BINDING', ports, entry

    request_state, requested, request = projection(value.get('HostConfig'), 'PortBindings')
    active_state, active, actual = projection(value.get('NetworkSettings'), 'Ports')
    requested_loopback = request is not None and request['HostIp'] == '127.0.0.1'
    active_loopback = actual is not None and actual['HostIp'] == '127.0.0.1'
    port = actual['HostPort'] if actual is not None else ''
    active_numeric = 1 <= len(port) <= 5 and port.isascii() and port.isdecimal() and 0 < int(port) <= 65535
    return {
        'schemaVersion': 1, 'scope': 'POST_START_OWN_CONTAINER_PORT_BINDING_PROJECTION',
        'containerRunningObserved': isinstance(value.get('State'), dict) and value['State'].get('Running') is True,
        'requestedMapState': request_state, 'activeMapState': active_state,
        'requestedSingleLoopbackBinding': requested_loopback,
        'requestedEmptyOrZeroHostPort': request is not None and request['HostPort'] in ('', '0'),
        'requestedOnlyRequiredPort': request is not None and isinstance(requested, dict) and set(requested) == {target},
        'activeSingleLoopbackBinding': active_loopback, 'activeNumericHostPort': active_numeric,
        'activeOnlyRequiredPublishedPort': actual is not None and isinstance(active, dict)
            and all(key == target or item is None for key, item in active.items()),
        'requestedAndActiveLoopbackConsistent': requested_loopback and active_loopback,
    }


def bound_port(value, container_port):
    entries = value['NetworkSettings']['Ports'].get(str(container_port) + '/tcp')
    require(isinstance(entries, list) and len(entries) == 1 and entries[0]['HostIp'] == '127.0.0.1'
            and entries[0]['HostPort'].isdigit() and 0 < int(entries[0]['HostPort']) <= 65535,
            'NUMERIC_LOOPBACK_ONLY_EPHEMERAL_PORT')
    require(all(key == str(container_port) + '/tcp' or value is None
                for key, value in value['NetworkSettings']['Ports'].items()), 'ONLY_ONE_REQUIRED_PRIVATE_PORT')
    return int(entries[0]['HostPort'])


def verified_internal_target(value, network, item, project, target_port):
    """Read-only ownership proof; neither requested ports nor DNS are a route."""
    container_guard(value, item['id'], item['name'], project, item['imageId'], item['network'], item['binds'])
    host = value['HostConfig']
    require(host['Memory'] == host['MemorySwap'] == item['memory'] and host['NanoCpus'] == item['nanoCpus'],
            'ACTUAL_RELAY_TARGET_LIMITS')
    require(value['State']['Running'] is True and value['State']['Pid'] > 0 and value['RestartCount'] == 0,
            'NEW_RUNNING_UNRESTARTED_RELAY_TARGET')
    require(host.get('PortBindings') in (None, {}) and not host.get('PublishAllPorts')
            and all(entry is None for entry in value['NetworkSettings']['Ports'].values()), 'NO_DOCKER_HOST_PORTS_FOR_RELAY_PROFILE')
    require(network['Name'] == item['network'] == project and network['Internal'] is True
            and network['Driver'] == 'bridge' and network['Scope'] == 'local'
            and network['Labels'].get(LABEL) == project and re.fullmatch('[a-f0-9]{64}', network['Id']),
            'EXACT_OWNED_INTERNAL_LOCAL_BRIDGE')
    endpoint = value['NetworkSettings']['Networks'][project]
    registered = network['Containers'][item['id']]
    require(endpoint['NetworkID'] == network['Id'] and registered['Name'] == item['name']
            and endpoint['EndpointID'] == registered['EndpointID'], 'CONTAINER_AND_NETWORK_ENDPOINT_IDENTITY')
    address = ipaddress.ip_address(endpoint['IPAddress'])
    member = ipaddress.ip_interface(registered['IPv4Address'])
    subnets = [ipaddress.ip_network(row['Subnet']) for row in network['IPAM']['Config'] if row.get('Subnet')]
    require(address.version == 4 and address.is_private and not address.is_loopback and not address.is_multicast
            and not address.is_unspecified and address == member.ip
            and any(net.version == 4 and address in net for net in subnets), 'EXACT_NETWORK_MEMBER_PRIVATE_IPV4')
    require(target_port in (3306, 3900), 'ONLY_FIXED_SERVICE_PORTS')
    return str(address), target_port


def create_owned_relay(attempt, item, target_port, deadline):
    initial = attempt.guard(item)
    network = json.loads(attempt.command(['docker', 'network', 'inspect', item['network']])[1])[0]
    target = verified_internal_target(initial, network, item, attempt.project, target_port)
    # No shared Attempt.command/sequence/logging from worker threads. Fresh
    # read-only CLI output stays in RAM and is never published, printed or logged.
    def read_json(argv):
        remaining = deadline-time.monotonic()
        require(remaining > 0, 'RELAY_SCOPE_READ_DEADLINE')
        result = subprocess.run(argv, capture_output=True, timeout=min(2, remaining))
        require(result.returncode == 0 and len(result.stdout) <= 8*1024**2, 'BOUNDED_RELAY_SCOPE_READ_REQUIRED')
        values = json.loads(result.stdout)
        require(isinstance(values, list) and len(values) == 1, 'ONE_RELAY_SCOPE_OBJECT_REQUIRED')
        return values[0]

    def verifier():
        live = read_json(['docker', 'inspect', item['id']])
        active_network = read_json(['docker', 'network', 'inspect', item['network']])
        require(live['Config'] == initial['Config'] and live['HostConfig'] == initial['HostConfig']
                and live['State']['Pid'] == initial['State']['Pid'] and live['State']['StartedAt'] == initial['State']['StartedAt']
                and sorted(live['Mounts'], key=lambda x: json.dumps(x, sort_keys=True))
                    == sorted(initial['Mounts'], key=lambda x: json.dumps(x, sort_keys=True)), 'SAME_RELAY_TARGET_PROCESS_AND_FULL_SPEC')
        actual = verified_internal_target(live, active_network, item, attempt.project, target_port)
        require(actual == target and active_network['Id'] == network['Id'], 'SAME_FIXED_RELAY_ENDPOINT_AND_NETWORK')
        return actual

    require(0 < deadline-time.monotonic() <= 360, 'BOUNDED_RELAY_SESSION_WINDOW')
    return LoopbackRelay(*target, verifier, lifetime=deadline-time.monotonic())


def test_summary(directory):
    expected = {'io.github.devdooly.platformlab.jobs.GarageRawSourceIT': set(RAW_CASES),
                'io.github.devdooly.platformlab.jobs.exporting.VerifiedResultExportIT': {EXPORT_CASE}}
    totals = {'tests': 0, 'failures': 0, 'errors': 0, 'skipped': 0}
    for name, methods in expected.items():
        path = directory / ('TEST-' + name + '.xml')
        require(path.is_file() and 0 < path.stat().st_size <= 4*1024**2, 'ACTUAL_BOUNDED_IT_XML_REQUIRED')
        root = ET.parse(path).getroot()
        require(root.attrib['name'] == name and {v.attrib['name'] for v in root.findall('testcase')} == methods
                and len(root.findall('testcase')) == len(methods), 'EXACT_FIVE_EXISTING_IT_CASES')
        for key in totals:
            totals[key] += int(root.attrib[key])
        require(all(all(case.find(tag) is None for tag in ('failure', 'error', 'skipped'))
                    for case in root.findall('testcase')), 'ALL_EXISTING_IT_CASES_ACTUALLY_PASSED')
        properties = {v.attrib['name']: v.attrib['value'] for v in root.findall('./properties/property')}
        require(properties.get('user.timezone') == 'Asia/Seoul', 'ACTUAL_IT_JVM_TIMEZONE')
    require(totals == {'tests': 5, 'failures': 0, 'errors': 0, 'skipped': 0}, 'FIVE_PASSED_ZERO_SKIPPED')
    return totals


class Attempt:
    def __init__(self, folder, project):
        self.folder, self.project, self.sequence = folder, project, 0
        self.network = project
        self.created = []
        self.unknown_create = False
        self.unknown_command_group = False
        self.deadline = time.monotonic() + 900

    def command(self, args, *, input=None, env=None, check=True, timeout=60, bounded=True):
        self.sequence += 1
        number = '%04d' % self.sequence
        save_json(self.folder / (number + '-intent.json'), {'sequence': self.sequence, 'issuedAt': utc(),
                  'commandKind': 'maven' if str(args[0]).endswith('mvnw') else 'docker'})
        if bounded:
            timeout = min(timeout, max(0.1, self.deadline - time.monotonic()))
        with os.fdopen(os.open(self.folder / (number + '-stdout.private'), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), 'wb') as out, \
             os.fdopen(os.open(self.folder / (number + '-stderr.private'), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), 'wb') as err:
            process = subprocess.Popen(args, stdin=subprocess.PIPE if input is not None else subprocess.DEVNULL,
                                       env=env, stdout=out, stderr=err, start_new_session=True)
            try:
                process.communicate(input=input, timeout=timeout)
            except subprocess.TimeoutExpired:
                # Only this Popen's isolated process group receives TERM. Do not kill,
                # resubmit a test, or retry an unknown Docker create/start outcome.
                if process.poll() is None and os.getpgid(process.pid) == process.pid:
                    os.killpg(process.pid, signal.SIGTERM)
                until = time.monotonic() + 10
                while time.monotonic() < until:
                    process.poll()
                    try: os.killpg(process.pid, 0)
                    except ProcessLookupError: break
                    time.sleep(.1)
                else: self.unknown_command_group = True
                raise RuntimeError('COMMAND_TIMEOUT_UNKNOWN_OUTCOME_NO_RETRY')
        stdout = (self.folder / (number + '-stdout.private')).read_bytes()
        save_json(self.folder / (number + '-result.json'), {'exitCode': process.returncode, 'completedAt': utc()})
        require(not check or process.returncode == 0, 'COMMAND_FAILED_OR_UNKNOWN_NO_RETRY')
        require(len(stdout) <= 8*1024**2, 'BOUNDED_PRIVATE_COMMAND_RESPONSE')
        return process.returncode, stdout

    def inspect(self, cid, bounded=True):
        return json.loads(self.command(['docker', 'inspect', cid], bounded=bounded, timeout=60 if bounded else 10)[1])[0]

    def create(self, role, image, options, binds, memory, cpus, network=None, command=()):
        name = self.project + '-' + role
        image_id = json.loads(self.command(['docker', 'image', 'inspect', image])[1])[0]['Id']
        save_json(self.folder / (role+'-create-intent.json'), {'name': name, 'imageId': image_id, 'project': self.project})
        self.unknown_create = True
        raw = self.command(['docker', 'create', '--name', name, '--label', LABEL+'='+self.project,
                      '--restart=no', '--memory='+str(memory), '--memory-swap='+str(memory), '--cpus='+str(cpus),
                      '--pids-limit=128', '--network='+ (network or self.network), *options, image, *command])[1]
        # A create timeout/unknown result is never repeated. Root can inspect private intent/name.
        cid = raw.decode().strip()
        require(re.fullmatch('[a-f0-9]{64}', cid), 'ACTUAL_CREATE_FULL_ID_REQUIRED')
        anchor = {'id': cid, 'name': name, 'imageId': image_id, 'binds': binds,
                  'network': network or self.network, 'memory': memory, 'nanoCpus': int(cpus*10**9)}
        self.created.append(anchor)  # Record before start or any further assertion can fail.
        self.unknown_create = False
        self.guard(anchor)
        save_json(self.folder / (role+'-created.json'), {'id': cid, 'name': name, 'imageId': image_id})
        return anchor

    def guard(self, item, bounded=True):
        value = self.inspect(item['id'], bounded=bounded)
        container_guard(value, item['id'], item['name'], self.project, item['imageId'], item['network'], item['binds'])
        require(value['HostConfig']['Memory'] == value['HostConfig']['MemorySwap'] == item['memory']
                and value['HostConfig']['NanoCpus'] == item['nanoCpus'], 'ACTUAL_BOUNDED_CONTAINER_LIMITS')
        return value

    def garage(self, garage, *args):
        self.guard(garage)
        return self.command(['docker', 'exec', garage['id'], '/garage', '-c', '/etc/garage.toml', *args])[1]

    def stop(self):
        clean = not self.unknown_create and not self.unknown_command_group
        for item in reversed(self.created):
            try:
                value = self.guard(item, bounded=False)
                if value['State']['Running']:
                    self.command(['docker', 'kill', '--signal=TERM', item['id']], bounded=False, timeout=10)
                    until = time.monotonic() + 60
                    while value['State']['Running'] and time.monotonic() < until:
                        time.sleep(.5); value = self.guard(item, bounded=False)
                require(not value['State']['Running'] and value['State']['ExitCode'] in (0, 143), 'OWNED_TERM_SHUTDOWN_UNVERIFIED')
            except Exception:
                clean = False
        return clean


def run():
    require(sys.platform == 'linux' and os.environ.get('GITHUB_ACTIONS') == 'true'
            and os.environ.get('RUNNER_ENVIRONMENT') == 'github-hosted', 'ONLY_DISPOSABLE_GITHUB_LINUX_RUNNER')
    source = os.environ.get('SOURCE_COMMIT', '')
    require(re.fullmatch('[a-f0-9]{40}', source) and source == os.environ.get('GITHUB_SHA'), 'EXPLICIT_ACTUAL_CHECKOUT_SOURCE')
    ids = [os.environ.get(name, '') for name in ('GITHUB_RUN_ID', 'GITHUB_RUN_ATTEMPT')]
    require(all(re.fullmatch('[0-9]{1,20}', value) for value in ids), 'ACTUAL_GITHUB_RUN_IDENTITY')
    workspace = Path(os.environ['GITHUB_WORKSPACE']).resolve(strict=True)
    require(workspace == Path.cwd().resolve(strict=True), 'EXACT_CHECKOUT_WORKING_DIRECTORY')
    api = workspace / 'apps/api'; source_identity(api)
    require(not (api/'target').exists(), 'FRESH_JOB_WITHOUT_STALE_BUILD_OR_TEST_REPORTS')
    project = 'lab-s3-ci-' + '-'.join(ids)
    folder = workspace / '.local/s3-ci' / project
    require(not folder.exists() and not folder.is_symlink(), 'FRESH_ONCE_ONLY_ATTEMPT')
    folder.mkdir(mode=0o700, parents=True); os.chmod(folder, 0o700); os.umask(0o077)
    public_dir = workspace / '.local/s3-ci-public'
    require(not public_dir.exists(), 'NEW_PUBLIC_SUMMARY_DIRECTORY'); public_dir.mkdir(mode=0o700)
    attempt = Attempt(folder, project)
    passed = stopped = False; failure = None; totals = None; artifact = None
    relays = []; relay_reports = []; relays_stopped = True
    it_diagnostics = empty_diagnostics()
    try:
        actual_source = subprocess.run(['git', 'rev-parse', 'HEAD'], capture_output=True, check=True, timeout=10).stdout.decode().strip()
        require(actual_source == source, 'CHECKOUT_SHA_MISMATCH')
        before = attempt.command(['docker', 'ps', '-aq', '--no-trunc'])[1].decode().split()
        require(not before, 'FRESH_RUNNER_DOCKER_SCOPE_REQUIRED')
        for image in (MARIADB, GARAGE):
            attempt.command(['docker', 'pull', image], timeout=180)
        attempt.command(['docker', 'network', 'create', '--internal', '--label', LABEL+'='+project, project])
        network = json.loads(attempt.command(['docker', 'network', 'inspect', project])[1])[0]
        require(network['Internal'] is True and network['Labels'].get(LABEL) == project, 'FRESH_INTERNAL_NETWORK')
        volumes = [project+'-'+role for role in ('db', 'meta', 'data')]
        old_volumes = attempt.command(['docker', 'volume', 'ls', '-q'])[1].decode().split()
        require(set(volumes).isdisjoint(old_volumes), 'ALL_THREE_VOLUME_NAMES_MUST_BE_ABSENT')
        for volume in volumes:
            attempt.command(['docker', 'volume', 'create', '--label', LABEL+'='+project, volume])
            value = json.loads(attempt.command(['docker', 'volume', 'inspect', volume])[1])[0]
            require(value['Name'] == volume and value['Labels'].get(LABEL) == project, 'EXACT_FRESH_OWN_VOLUME')
        # Garage runs nonroot; the short network-isolated initializer touches these new volumes only.
        init = attempt.create('init', MARIADB, ['--user=0:0', '--read-only', '--cap-drop=ALL', '--cap-add=CHOWN',
            '--security-opt=no-new-privileges:true', '--entrypoint=/bin/chown', '-v', volumes[1]+':/meta:rw',
            '-v', volumes[2]+':/data:rw'], [(volumes[1], '/meta', 'rw'), (volumes[2], '/data', 'rw')],
            64*1024**2, .1, 'none', ('1000:1000', '/meta', '/data'))
        attempt.command(['docker', 'start', '-a', init['id']])
        value = attempt.guard(init)
        require(not value['State']['Running'] and value['State']['ExitCode'] == 0, 'EXACT_INITIALIZER_SUCCESS')
        db_password, root_password = secrets.token_hex(24), secrets.token_hex(24)
        db_env = folder / 'mariadb.private.env'
        save(db_env, ('MARIADB_ROOT_PASSWORD='+root_password+'\nMARIADB_DATABASE=platform_lab_export_it\n'
             'MARIADB_USER=exportit\nMARIADB_PASSWORD='+db_password+'\n').encode())
        garage_config = folder / 'garage.private.toml'
        save(garage_config, ('metadata_dir="/meta"\ndata_dir="/data"\ndb_engine="sqlite"\nreplication_factor=1\n'
             'rpc_secret="'+secrets.token_hex(32)+'"\nrpc_bind_addr="127.0.0.1:3901"\n'
             'rpc_public_addr="127.0.0.1:3901"\n[s3_api]\ns3_region="garage"\n'
             'api_bind_addr="0.0.0.0:3900"\nroot_domain=".s3.invalid"\n').encode())
        # Only the RPC config is world-readable inside the private 0700 attempt directory;
        # the container runs UID1000. S3/DB credentials and command logs remain 0600.
        os.chmod(garage_config, 0o444)
        db = attempt.create('db', MARIADB, ['--env-file', str(db_env), '-v', volumes[0]+':/var/lib/mysql:rw',
            '--security-opt=no-new-privileges:true'],
            [(volumes[0], '/var/lib/mysql', 'rw')], 1024**3, 1)
        garage = attempt.create('garage', GARAGE, ['--user=1000:1000', '--read-only', '--cap-drop=ALL',
            '--security-opt=no-new-privileges:true', '--tmpfs=/tmp:size=32m', '--entrypoint=/garage',
            '-v', volumes[1]+':/meta:rw', '-v', volumes[2]+':/data:rw', '-v', str(garage_config)+':/etc/garage.toml:ro',
            ], [(volumes[1], '/meta', 'rw'), (volumes[2], '/data', 'rw'),
            (str(garage_config), '/etc/garage.toml', 'ro')], 512*1024**2, .5, command=('-c', '/etc/garage.toml', 'server'))
        for item in (db, garage):
            attempt.command(['docker', 'start', item['id']]); attempt.guard(item)
        until = time.monotonic() + 120
        while True:
            require(time.monotonic() < until, 'MARIADB_READINESS_DEADLINE')
            attempt.guard(db)
            if attempt.command(['docker', 'exec', db['id'], 'healthcheck.sh', '--connect', '--innodb_initialized'], check=False)[0] == 0:
                break
            time.sleep(1)
        until = time.monotonic() + 60
        while True:
            require(time.monotonic() < until, 'GARAGE_RPC_READINESS_DEADLINE')
            result, raw = attempt.command(['docker', 'exec', garage['id'], '/garage', '-c', '/etc/garage.toml', 'node', 'id', '--quiet'], check=False)
            if result == 0:
                node = raw.decode().strip().split('@')[0]; break
            time.sleep(1)
        require(re.fullmatch('[a-f0-9]{64}', node), 'FRESH_GARAGE_NODE_ID')
        version = attempt.garage(garage, '--version').decode().strip()
        require(re.match(r'^garage v2\.4\.1(?:\s|$)', version), 'ACTUAL_GARAGE_VERSION')
        attempt.garage(garage, 'layout', 'assign', '-z', 'github-isolated', '-c', '128M', node)
        attempt.garage(garage, 'layout', 'apply', '--version', '1')
        bucket_name = 'platform-lab-s3-test-' + '-'.join(ids)
        bucket = json.loads(attempt.garage(garage, 'json-api', 'CreateBucket', json.dumps({'globalAlias': bucket_name})))
        attempt.garage(garage, 'json-api', 'UpdateBucket', json.dumps({'id': bucket['id'], 'body': {'quotas': {'maxSize': 32*1024**2, 'maxObjects': 128}}}))
        key = json.loads(attempt.garage(garage, 'json-api', 'CreateKey', json.dumps({'name': project})))
        attempt.garage(garage, 'json-api', 'AllowBucketKey', json.dumps({'bucketId': bucket['id'], 'accessKeyId': key['accessKeyId'],
                        'permissions': {'read': True, 'write': True, 'owner': False}}))
        acl = json.loads(attempt.garage(garage, 'json-api', 'GetKeyInfo', json.dumps({'id': key['accessKeyId'], 'showSecretKey': False})))
        require(acl['accessKeyId'] == key['accessKeyId'] and acl['permissions']['createBucket'] is False and len(acl['buckets']) == 1
                and acl['buckets'][0]['id'] == bucket['id'] and acl['buckets'][0]['permissions'] == {'read': True, 'write': True, 'owner': False},
                'ACTUAL_ONLY_NEW_BUCKET_NONOWNER_READ_WRITE_KEY')
        # Build before relay lifetime starts. This is a new explicit connectivity
        # profile, never a fallback to a missing Docker published port.
        maven = api / 'mvnw'; os.chmod(maven, maven.stat().st_mode | stat.S_IXUSR)
        build_env = os.environ.copy(); build_env['MAVEN_OPTS'] = '-Xmx768m'
        attempt.command([str(maven), '-B', '-ntp', '-f', str(api/'pom.xml'), '-DskipTests', 'package'], env=build_env, timeout=300)
        artifact = jar_identity(api)
        relay_deadline = min(attempt.deadline, time.monotonic()+360)
        db_relay = create_owned_relay(attempt, db, 3306, relay_deadline)
        relays.append(db_relay); db_port = db_relay.start(); db_relay.probe()
        garage_relay = create_owned_relay(attempt, garage, 3900, relay_deadline)
        relays.append(garage_relay); garage_port = garage_relay.start(); garage_relay.probe()
        env = os.environ.copy()
        env.update({'MAVEN_OPTS': '-Xmx768m', 'DB_TEST_URL': 'jdbc:mariadb://127.0.0.1:'+str(db_port)+'/platform_lab_export_it',
            'DB_TEST_USERNAME': 'exportit', 'DB_TEST_PASSWORD': db_password, 'LAB_S3_TEST_BUCKET': bucket_name,
            'LAB_S3_TEST_ENDPOINT': 'http://127.0.0.1:'+str(garage_port),
            'LAB_S3_TEST_ACCESS_KEY': key['accessKeyId'], 'LAB_S3_TEST_SECRET_KEY': key['secretAccessKey']})
        del key, db_password, root_password
        # This is the existing real-IO code, not a new test that mirrors the adapter.
        reports = api / 'target/surefire-reports'
        require(all(not path.exists() and not path.is_symlink() for path in report_paths(reports)), 'FRESH_EXPECTED_IT_REPORTS_REQUIRED')
        it_diagnostics['freshReportsGatePassed'] = True
        test_exit, _ = attempt.command([str(maven), '-B', '-ntp', '-f', str(api/'pom.xml'), '-Dlab.s3.tests=true', '-Dlab.export.tests=true',
            '-DargLine=-Duser.timezone=Asia/Seoul -Xmx768m', '-Dtest='+SELECTION, 'test'], env=env, timeout=300, check=False)
        del env
        try:
            it_diagnostics = collect_it_diagnostics(reports, test_exit)
        except Exception:
            it_diagnostics['collection'] = 'UNOBSERVED_DIAGNOSTIC_COLLECTION_FAILURE'
        # Informational projection cannot override either the Maven exit or the
        # unchanged exact five-pass/zero-skip/Asia-Seoul gate.
        require(test_exit == 0, 'COMMAND_FAILED_OR_UNKNOWN_NO_RETRY')
        totals = test_summary(reports)
        source_identity(api); require(jar_identity(api) == artifact, 'SOURCE_CLASSES_OR_API_ARTIFACT_CHANGED_DURING_ITS')
        # Existing ITs delete only their registered UUID objects/rows (also on failure).
        # Read the dedicated DB through its own container; root password never enters argv/output.
        sql = b"SELECT CONCAT((SELECT COUNT(*) FROM lab_job),',',(SELECT COUNT(*) FROM lab_outbox),',',(SELECT COUNT(*) FROM demo_run),',',(SELECT COUNT(*) FROM demo_outcome),',',(SELECT COUNT(*) FROM lab_job_slot WHERE occupied_run_id IS NOT NULL));\n"
        state = attempt.command(['docker', 'exec', '-i', db['id'], '/bin/sh', '-c',
            'MYSQL_PWD="$MARIADB_ROOT_PASSWORD" exec mariadb -uroot --batch --raw --skip-column-names platform_lab_export_it'], input=sql)[1].decode().strip()
        require(state == '0,0,0,0,0', 'ONLY_OWN_TEST_ROWS_AND_SLOT_CLEANED')
        require(set(attempt.command(['docker', 'ps', '-aq', '--no-trunc'])[1].decode().split()) == {v['id'] for v in attempt.created},
                'NO_UNKNOWN_DOCKER_CONTAINER_CREATED')
        for item in attempt.created: attempt.guard(item)
        passed = True
    except Exception as error:
        text = str(error)
        failure = {'type': type(error).__name__, 'code': text if re.fullmatch('[A-Z0-9_]{1,128}', text) else 'ISOLATED_ATTEMPT_FAILED_OR_UNKNOWN'}
    finally:
        # Each relay is joined before container TERM, and a failed relay close
        # cannot skip the other relay or the original container cleanup.
        for relay in reversed(relays):
            try:
                relays_stopped = relay.close() and relays_stopped
                relay_reports.append(relay.summary())
            except Exception:
                relays_stopped = False
        stopped = attempt.stop()
        relay_ok = relays_stopped and len(relay_reports) == 2 and all(
            v['tcpPositiveControlPassed'] and v['failureCode'] is None for v in relay_reports)
        if passed and not relay_ok:
            failure = {'type': 'RelayError', 'code': 'OWNED_RELAY_RUNTIME_OR_SHUTDOWN_UNVERIFIED'}
        passed = passed and stopped and relay_ok
        summary = {'schemaVersion': 1, 'passed': passed, 'scope': SCOPE, 'capturedAt': utc(),
            'sourceCommit': source, 'sdk': '2.55.16', 'transport': 'APACHE5', 'tests': totals, 'apiArtifact': artifact,
            'plannedCases': 5, 'createdContainerCount': len(attempt.created), 'ownedContainersStopped': stopped,
            'unknownContainerCreateOutcome': attempt.unknown_create,
            'unknownOwnedCommandProcessGroup': attempt.unknown_command_group,
            'forcedKillPerformed': False, 'automaticAttemptRetryPerformed': False,
            'ownVolumesRetainedUntilRunnerDisposal': True, 'miniPcContacted': False,
            'rawLogsCredentialsOrConnectionValuesPublished': False,
            'connectivityProfile': CONNECTIVITY_PROFILE, 'dockerPortsPublished': False,
            'ownedRelaysStoppedAndJoined': relays_stopped, 'relays': relay_reports,
            'historicalPortGuardFailureCauseObserved': False, 'itDiagnostics': it_diagnostics, 'failure': failure}
        save_json(public_dir / 'summary.json', summary)
        print(json.dumps(summary, sort_keys=True))
    return 0 if passed else 1


if __name__ == '__main__':
    raise SystemExit(run())
