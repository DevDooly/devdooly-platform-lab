"""Explicit GitHub-hosted one-attempt integration; uploads only safe summary.

No SSH, kubeconfig, production endpoint, GHCR login/push or deployment exists.
"""
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import shutil
import ssl
import subprocess
import sys
import time
import urllib.request
import uuid
from compose_plan import POSTGRES, GARAGE, SPARK, plan

sys.dont_write_bytecode = True
LOCK_SHA = '6ca247b283025189ecf36c67ae03fe9101b25a53fe7b62593725e076276e33e3'
MODULES = {'spark_silver.py': '189ec387433784e4623ba8b24efeeeed40b90213b2582450170ba687bcf067ec',
    'silver_contract.py': '889fdb91ec4613d19f62a622e4cc889a27e38012905019f05d4743130f8268df',
    'synthetic-v1.ndjson': '39ba10d8c47dce790f3ccc9c9134fea593d6de31f1f3a7992ca61d9f554da3b5',
    'Dockerfile.candidate': '334b4865c926062d40f25801e6c05a6390b9c957c87c4c7b3416aed62001bf24'}
BASE_URL = 'https://repo.maven.apache.org/maven2/'
JARS = {
    'iceberg-spark-runtime-4.1_2.13-1.11.0.jar': ('org/apache/iceberg/iceberg-spark-runtime-4.1_2.13/1.11.0/', 47959591, 'd6ea6c5d099288daeb7d5a92061bd3d7d8f296492632b42378e5f2f0e3066242'),
    'iceberg-aws-bundle-1.11.0.jar': ('org/apache/iceberg/iceberg-aws-bundle/1.11.0/', 63613165, '38f01da7e96850cdd05e6616d758b77b43314b712a8808e3f9a824d56976162f'),
    'postgresql-42.7.14.jar': ('org/postgresql/postgresql/42.7.14/', 1221004, '73914527305a40cce504b0d3d90b23caf565136912d607ae8ae7c5895512332c')}
BOOTSTRAP_PHASES = frozenset(('PYTHON_START', 'IMPORT_SILVER', 'SESSION', 'GZIP_DEFAULT', 'VERSIONS', 'FRESH_TABLES',
    'CREATE_BRONZE', 'APPEND_FIRST', 'APPEND_SECOND', 'VERIFY_BRONZE', 'SILVER_RUN', 'VERIFY_RESULT',
    'WRITE_RESULT', 'STOP_SESSION', 'COMPLETED'))
PYTHON_EXCEPTIONS = frozenset(('Py4JJavaError', 'Py4JNetworkError', 'Py4JError', 'AnalysisException',
    'IllegalArgumentException', 'SparkRuntimeException', 'ImportError', 'ModuleNotFoundError', 'PermissionError',
    'FileNotFoundError', 'RuntimeError', 'ValueError', 'OSError', 'TypeError', 'AssertionError', 'OTHER'))
JAVA_CLASS = re.compile(r'(?:org\.apache\.(?:spark|iceberg)|java|org\.postgresql|software\.amazon)'
                        r'(?:\.[A-Za-z_$][A-Za-z0-9_$]*){1,12}')


def require(value, code):
    if not value:
        raise RuntimeError(code)


def utc():
    return dt.datetime.now(dt.timezone.utc).isoformat()


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def save(path, value, mode=0o600):
    raw = value if isinstance(value, bytes) else (json.dumps(value, sort_keys=True, indent=2) + '\n').encode()
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, mode)
    os.fchmod(fd, mode)
    with os.fdopen(fd, 'wb') as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args):
        return None


def validated_lock(raw):
    require(sha(raw) == LOCK_SHA, 'EXACT_PUBLIC_DOWNLOADED_ARTIFACT_LOCK')
    value = json.loads(raw)
    require(len(value['jars']) == 3 and {v['filename'] for v in value['jars']} == set(JARS), 'EXACT_THREE_ARTIFACTS')
    for row in value['jars']:
        prefix, size, digest = JARS[row['filename']]
        require(row['downloadUrl'] == BASE_URL + prefix + row['filename'] and row['bytes'] == size and row['sha256'] == digest
                and re.fullmatch('[a-f0-9]{128}', row['sha512']), 'FIXED_OFFICIAL_URL_SIZE_AND_HASH')
    return value


def vendor(lock, destination):
    destination.mkdir(mode=0o700)
    client = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect(), urllib.request.HTTPSHandler(context=ssl.create_default_context()))
    deadline = time.monotonic() + 600
    for row in lock['jars']:
        url = row['downloadUrl']
        remaining = deadline - time.monotonic()
        require(remaining > 0, 'VENDOR_DEADLINE')
        request = urllib.request.Request(url, headers={'Accept': 'application/octet-stream', 'User-Agent': 'isolated-spark-ci/1'})
        path = destination / row['filename']
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        with os.fdopen(fd, 'wb') as stream, client.open(request, timeout=min(20, remaining)) as response:
            require(response.status == 200 and response.headers.get('Content-Length') == str(row['bytes']), 'EXACT_VENDOR_HTTP_SIZE')
            h256, h512, count = hashlib.sha256(), hashlib.sha512(), 0
            while True:
                require(time.monotonic() < deadline, 'VENDOR_DEADLINE')
                chunk = response.read(min(1024**2, row['bytes'] - count + 1))
                if not chunk:
                    break
                count += len(chunk)
                require(count <= row['bytes'], 'VENDOR_OVERFLOW')
                stream.write(chunk)
                h256.update(chunk)
                h512.update(chunk)
            require(count == row['bytes'] and h256.hexdigest() == row['sha256'] and h512.hexdigest() == row['sha512'], 'WHOLE_PINNED_VENDOR_BYTES')
            stream.flush()
            os.fsync(stream.fileno())
    save(destination / 'vendor.sha256', ''.join(v['sha256'] + '  /opt/spark/jars/' + v['filename'] + '\n' for v in lock['jars']).encode())


def pg_init(password):
    require(re.fullmatch('[a-f0-9]{64}', password), 'RANDOM_HEX_CATALOG_PASSWORD')
    return ("BEGIN;\nCREATE ROLE iceberg_catalog LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE PASSWORD '" + password + "';\n"
        "ALTER DATABASE iceberg_lab OWNER TO iceberg_catalog;\nREVOKE CREATE ON SCHEMA public FROM PUBLIC;\nALTER SCHEMA public OWNER TO iceberg_catalog;\nSET ROLE iceberg_catalog;\n"
        "CREATE TABLE iceberg_tables(catalog_name VARCHAR(255) NOT NULL,table_namespace VARCHAR(255) NOT NULL,table_name VARCHAR(255) NOT NULL,metadata_location VARCHAR(1000),previous_metadata_location VARCHAR(1000),iceberg_type VARCHAR(5),PRIMARY KEY(catalog_name,table_namespace,table_name));\n"
        "CREATE TABLE iceberg_namespace_properties(catalog_name VARCHAR(255) NOT NULL,namespace VARCHAR(255) NOT NULL,property_key VARCHAR(255),property_value VARCHAR(1000),PRIMARY KEY(catalog_name,namespace,property_key));\nCOMMIT;\n").encode()


def garage_config():
    return ('metadata_dir="/var/lib/garage/meta"\ndata_dir="/var/lib/garage/data"\ndb_engine="sqlite"\nreplication_factor=1\n'
        'rpc_bind_addr="127.0.0.1:3901"\nrpc_public_addr="127.0.0.1:3901"\nrpc_secret="' + secrets.token_hex(32) + '"\n'
        '[s3_api]\napi_bind_addr="0.0.0.0:3900"\ns3_region="garage"\n').encode()


class Attempt:
    def __init__(self, root, project):
        self.root, self.project, self.sequence = root, project, 0
        self.compose = ['docker', 'compose', '-p', project, '-f', str(root / 'compose.json')]
        self.initializer_intended = False
        self.initializer_name = project + '-volume-init'

    def command(self, args, timeout=60, sensitive=False, check=True):
        self.sequence += 1
        result = subprocess.run(args, input=None, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=timeout)
        require(len(result.stdout) <= 8*1024**2 and len(result.stderr) <= 8*1024**2, 'COMMAND_OUTPUT_BOUND')
        if not sensitive:
            save(self.root / ('command-%03d.stdout' % self.sequence), result.stdout)
            save(self.root / ('command-%03d.stderr' % self.sequence), result.stderr)
        require(not check or result.returncode == 0, 'ISOLATED_COMMAND_FAILED_NO_RETRY')
        return result

    def cli(self, *args, **kwargs):
        return self.command([*self.compose, *args], **kwargs)

    def garage(self, *args, sensitive=False):
        return self.cli('exec', '-T', 'garage', '/garage', '-c', '/etc/garage.toml', *args, sensitive=sensitive).stdout

    def containers(self):
        ids = self.command(['docker', 'ps', '-aq', '--no-trunc', '--filter', 'label=com.docker.compose.project=' + self.project]).stdout.decode().split()
        require(len(ids) <= 3 and all(re.fullmatch('[a-f0-9]{64}', value) for value in ids), 'ONLY_THREE_EXACT_PROJECT_CONTAINERS')
        result = []
        for cid in ids:
            raw = json.loads(self.command(['docker', 'inspect', cid], sensitive=True).stdout)[0]
            role = raw['Config']['Labels']['com.docker.compose.service']
            require(raw['Id'] == cid and raw['Config']['Labels']['com.docker.compose.project'] == self.project and role in ('postgres', 'garage', 'spark')
                    and not raw['HostConfig']['Privileged'] and not raw['HostConfig'].get('PortBindings'), 'OWN_ISOLATED_NO_PORT_CONTAINER')
            require(len(raw['NetworkSettings']['Networks']) == 1 and list(raw['NetworkSettings']['Networks']) == [self.project + '_trial'], 'ONLY_OWN_INTERNAL_NETWORK')
            expected_cpu, expected_memory = (1000000000, 3*1024**3) if role == 'spark' else (500000000, 512*1024**2)
            require(raw['HostConfig']['NanoCpus'] == expected_cpu and raw['HostConfig']['Memory'] == expected_memory, 'ACTUAL_CONTAINER_LIMITS')
            result.append({'id': cid, 'role': role, 'running': raw['State']['Running'], 'exitCode': raw['State']['ExitCode'], 'oom': raw['State']['OOMKilled']})
        require(len({v['role'] for v in result}) == len(result), 'UNIQUE_OWN_CONTAINER_ROLES')
        return result

    def initializer(self):
        if not self.initializer_intended:
            return None
        value = self.command(['docker', 'inspect', self.initializer_name], sensitive=True, check=False)
        if value.returncode != 0:
            # A failed inspect is not interpreted as absence (daemon/network
            # failure could otherwise conceal a live initializer).
            ids = self.command(['docker', 'ps', '-aq', '--no-trunc', '--filter', 'name=^/' + self.initializer_name + '$']).stdout.decode().split()
            require(ids == [], 'INITIALIZER_IDENTITY_LOOKUP_UNRESOLVED')
            return None
        raw = json.loads(value.stdout)[0]
        require(re.fullmatch('[a-f0-9]{64}', raw['Id']) and raw['Name'] == '/' + self.initializer_name
            and raw['Config']['Labels'].get('devdooly.io.spark-ci-project') == self.project
            and raw['Config']['Image'] == POSTGRES and raw['Config']['Entrypoint'] == ['/bin/chown']
            and raw['Config']['Cmd'] == ['1000:1000', '/meta', '/data']
            and raw['HostConfig']['NetworkMode'] == 'none' and not raw['HostConfig']['Privileged']
            and not raw['HostConfig'].get('PortBindings') and raw['HostConfig']['Memory'] == 64*1024**2
            and raw['HostConfig']['NanoCpus'] == 100000000
            and raw['HostConfig']['Binds'] == [self.project + '_garage-meta:/meta', self.project + '_garage-data:/data'], 'EXACT_FRESH_INITIALIZER_IDENTITY_AND_SCOPE')
        return {'id': raw['Id'], 'running': raw['State']['Running'], 'exitCode': raw['State']['ExitCode'], 'oom': raw['State']['OOMKilled']}


def safe_spark_result(value):
    fields = {'schemaVersion', 'passed', 'scope', 'spark', 'java', 'scala', 'fixtureSha256', 'bronzeRows', 'bronzeSnapshotCount', 'bronzeRowsSha256',
        'bronzeSnapshotIds', 'silverRows', 'success', 'failure', 'duplicate', 'pending', 'silverRowsSha256', 'silverSnapshotCount', 'mergeInvocations',
        'sequentialReplayInvocations', 'replayWriteInvocations', 'sparkApplicationCount', 'nativeTrinoVerified', 'miniPcPreservationVerified', 'kubernetesVerified',
        'distributedConcurrencyOrCrashRecoveryVerified', 'compressionExperiment'}
    require(isinstance(value, dict) and set(value) == fields and value['schemaVersion'] == 1 and value['passed'] is True
        and value['scope'] == 'ISOLATED_GITHUB_RUNNER_SPARK_JDBC_GARAGE' and value['spark'] == '4.1.1'
        and value['fixtureSha256'] == MODULES['synthetic-v1.ndjson'], 'EXACT_PUBLIC_SPARK_RESULT')
    counts = {'bronzeRows': 12, 'bronzeSnapshotCount': 2, 'silverRows': 12, 'success': 7, 'failure': 3, 'duplicate': 2, 'pending': 0,
              'silverSnapshotCount': 1, 'mergeInvocations': 1, 'sequentialReplayInvocations': 1, 'replayWriteInvocations': 0, 'sparkApplicationCount': 1}
    require(all(type(value[key]) is int and value[key] == count for key, count in counts.items()), 'EXACT_FIXED_COUNTS')
    require(all(value[key] is False for key in ('nativeTrinoVerified', 'miniPcPreservationVerified', 'kubernetesVerified', 'distributedConcurrencyOrCrashRecoveryVerified')), 'NO_PRODUCTION_OR_TRINO_OVERCLAIM')
    compression = {'requestedCodec': 'gzip', 'catalogDefaultSetBeforeFirstCatalogAccess': True,
        'bronzePropertyBeforeAppend': 'gzip', 'bronzePropertyAfterRun': 'gzip',
        'silverPropertyAfterWriteAndReplay': 'gzip', 'silverPropertyBeforeWriteObserved': False,
        'verification': 'SHOW_TBLPROPERTIES_ONLY', 'actualParquetFooterCodecVerified': False,
        'priorFailureSoleCauseProven': False}
    require(isinstance(value['compressionExperiment'], dict) and set(value['compressionExperiment']) == set(compression)
        and all(type(value['compressionExperiment'][key]) is type(expected)
            and value['compressionExperiment'][key] == expected for key, expected in compression.items()), 'EXPLICIT_GZIP_TABLE_PROPERTY_EXPERIMENT_ONLY')
    require(re.fullmatch(r'21(?:\.[A-Za-z0-9+._-]+)?', value['java']) and re.fullmatch(r'2\.13\.[0-9]+', value['scala']), 'BOUNDED_ACTUAL_JAVA_SCALA')
    require(all(re.fullmatch('[a-f0-9]{64}', value[key]) for key in ('bronzeRowsSha256', 'silverRowsSha256'))
        and len(value['bronzeSnapshotIds']) == 2 and all(re.fullmatch('[1-9][0-9]{0,18}', v) and int(v) < 2**63 for v in value['bronzeSnapshotIds'])
        and len(set(value['bronzeSnapshotIds'])) == 2, 'BOUNDED_SAFE_HASH_AND_SNAPSHOT_IDS')
    return value


def safe_bootstrap_diagnostic(value):
    fields = {'schemaVersion', 'scope', 'passed', 'lastPhase', 'milestones', 'pythonExceptionClass', 'javaCauseClasses', 'sessionStopFailed',
        'nativeLibraryCategories', 'failedMapSegmentObserved', 'tmpMountFlag'}
    require(isinstance(value, dict) and set(value) == fields and type(value['schemaVersion']) is int and value['schemaVersion'] == 1
        and value['scope'] == 'ISOLATED_SPARK_BOOTSTRAP_DIAGNOSTIC' and type(value['passed']) is bool
        and value['lastPhase'] in BOOTSTRAP_PHASES and type(value['sessionStopFailed']) is bool
        and type(value['failedMapSegmentObserved']) is bool and value['tmpMountFlag'] in ('NOEXEC', 'EXEC', 'UNOBSERVED'),
        'BOUNDED_MESSAGE_FREE_BOOTSTRAP_DIAGNOSTIC')
    milestones, causes = value['milestones'], value['javaCauseClasses']
    require(isinstance(milestones, list) and 1 <= len(milestones) <= 32 and all(v in BOOTSTRAP_PHASES for v in milestones)
        and milestones[0] == 'PYTHON_START' and isinstance(causes, list) and len(causes) <= 8
        and all(isinstance(v, str) and len(v) <= 160 and JAVA_CLASS.fullmatch(v) for v in causes), 'ONLY_FIXED_MILESTONES_AND_JAVA_CLASS_NAMES')
    libraries = value['nativeLibraryCategories']
    require(isinstance(libraries, list) and len(libraries) <= 4 and all(v in ('zstd', 'snappy', 'lz4', 'hadoop') for v in libraries)
        and libraries == sorted(set(libraries)), 'ONLY_NATIVE_LIBRARY_WHITELIST_CATEGORIES')
    if value['passed']:
        require(value['lastPhase'] == milestones[-1] == 'COMPLETED' and value['pythonExceptionClass'] is None
            and causes == [] and value['sessionStopFailed'] is False and libraries == []
            and value['failedMapSegmentObserved'] is False, 'SUCCESSFUL_BOOTSTRAP_DIAGNOSTIC')
    else:
        require(value['pythonExceptionClass'] in PYTHON_EXCEPTIONS and value['lastPhase'] in milestones, 'FAILED_BOOTSTRAP_CLASS_ONLY')
    return value


def log_signature(raw):
    # Categories indicate signatures in a bounded tail, never a proven cause.
    raw = raw[-262144:]
    signatures = (
        ('JAVA_OUT_OF_MEMORY_SIGNATURE', rb'java\.lang\.OutOfMemoryError'),
        ('JAVA_CLASS_LOADING_SIGNATURE', rb'(?:ClassNotFoundException|NoClassDefFoundError|UnsupportedClassVersionError)'),
        ('PYTHON_IMPORT_SIGNATURE', rb'(?:ModuleNotFoundError|ImportError):'),
        ('EXECUTABLE_NOT_FOUND_SIGNATURE', rb'(?:exec:.*(?:no such file or directory|not found)|tini:.*No such file)'),
        ('PERMISSION_DENIED_SIGNATURE', rb'(?:PermissionError:|[Pp]ermission denied)'),
        ('SPARK_ARGUMENT_SIGNATURE', rb'(?:Error: Unrecognized option|Unknown option:|Missing application resource)'))
    return next((name for name, pattern in signatures if re.search(pattern, raw)), 'NO_RECOGNIZED_SIGNATURE')


def spark_diagnostics(attempt, expected, diagnostic):
    before = next(v for v in attempt.containers() if v['role'] == 'spark')
    require(before['id'] == expected['id'], 'SAME_EXACT_SPARK_CONTAINER_FOR_DIAGNOSTICS')
    require(type(before['running']) is bool and type(before['oom']) is bool and type(before['exitCode']) is int,
        'ACTUAL_SPARK_STATE_TYPES')
    diagnostic.update(stateObserved=True, runningAtCapture=before['running'],
        exitCode=None if before['running'] else before['exitCode'], oomKilled=before['oom'])
    logs = attempt.command(['docker', 'logs', '--tail', '200', before['id']], sensitive=True, check=False)
    # These files remain in the private runner directory and are never artifacts.
    save(attempt.root / 'spark-diagnostic.stdout', logs.stdout)
    save(attempt.root / 'spark-diagnostic.stderr', logs.stderr)
    after = next(v for v in attempt.containers() if v['role'] == 'spark')
    require(after['id'] == before['id'], 'SAME_EXACT_SPARK_CONTAINER_AFTER_DIAGNOSTICS')
    require(type(after['running']) is bool and type(after['oom']) is bool and type(after['exitCode']) is int,
        'ACTUAL_SPARK_STATE_TYPES')
    diagnostic.update(runningAtCapture=after['running'], exitCode=None if after['running'] else after['exitCode'],
        oomKilled=after['oom'], logCollection='COLLECTED' if logs.returncode == 0 else 'UNAVAILABLE',
        logSignature=log_signature(logs.stdout + b'\n' + logs.stderr) if logs.returncode == 0 else 'LOG_UNAVAILABLE')
    bootstrap = None
    path = attempt.root / 'proof/bootstrap-diagnostic.json'
    if path.exists() or path.is_symlink():
        info = path.lstat()
        require(not path.is_symlink() and path.is_file() and 0 < info.st_size <= 16384, 'BOUNDED_REGULAR_BOOTSTRAP_DIAGNOSTIC')
        raw = path.read_bytes()
        require(len(raw) == info.st_size, 'STABLE_BOOTSTRAP_DIAGNOSTIC_BYTES')
        bootstrap = safe_bootstrap_diagnostic(json.loads(raw))
    diagnostic['bootstrap'] = bootstrap


def main():
    require(sys.platform == 'linux' and os.environ.get('GITHUB_ACTIONS') == 'true' and os.environ.get('RUNNER_ENVIRONMENT') == 'github-hosted', 'GITHUB_HOSTED_LINUX_ONLY')
    source = os.environ.get('SOURCE_COMMIT', '')
    require(re.fullmatch('[a-f0-9]{40}', source), 'ACTUAL_CHECKOUT_SOURCE_COMMIT')
    os.umask(0o077)
    repo = Path(__file__).resolve().parents[2]
    require((repo / 'infra/spark-silver').is_dir(), 'TRACKED_SOURCE_PACKET_REQUIRED')
    local = repo / '.local'
    local.mkdir(exist_ok=True)
    public = local / 'spark-ci-public'
    require(not public.exists() and not public.is_symlink(), 'NEW_PUBLIC_SUMMARY_FOLDER_ONLY')
    public.mkdir(mode=0o700)
    nonce = uuid.uuid4().hex
    root = local / ('spark-ci-private-' + nonce)
    root.mkdir(mode=0o700)
    project, image = 'spark-ci-' + nonce, 'spark-isolated-ci:' + nonce
    attempt = Attempt(root, project)
    results, failure, passed, stopped, initializer_stopped = {}, None, False, False, False
    diagnostics = {'stateObserved': False, 'runningAtCapture': None, 'exitCode': None, 'oomKilled': None,
        'logCollection': 'NOT_CAPTURED', 'logSignature': 'LOG_UNAVAILABLE', 'bootstrap': None}
    checks = {'vendorBytesVerified': False, 'pinnedImagesPulled': False, 'internalNetworkVerified': False, 'containerLimitsVerified': False}
    try:
        require(shutil.disk_usage(root).free >= 6*1024**3, 'GITHUB_RUNNER_DISK_RESERVE')
        for kind in ('container', 'volume', 'network'):
            args = ['docker', 'ps', '-aq'] if kind == 'container' else ['docker', kind, 'ls', '-q']
            require(not attempt.command([*args, '--filter', 'label=com.docker.compose.project=' + project]).stdout.strip(), 'FRESH_UUID_PROJECT_ONLY')
        packet = repo / 'infra/spark-silver'
        lock = validated_lock((packet / 'artifact-lock.downloaded.json').read_bytes())
        build = root / 'build'
        build.mkdir(mode=0o700)
        for name, expected in MODULES.items():
            raw = (packet / name).read_bytes()
            require(sha(raw) == expected, 'EXACT_FROZEN_SPARK_MODULE_BYTES')
            save(build / name, raw)
        save(build / 'bootstrap_spark.py', Path(__file__).with_name('bootstrap_spark.py').read_bytes())
        save(build / 'Dockerfile.ci', (build / 'Dockerfile.candidate').read_bytes() + b'\nCOPY --chown=185:185 --chmod=0444 bootstrap_spark.py /opt/silver/bootstrap_spark.py\n')
        vendor(lock, build / 'vendor')
        checks['vendorBytesVerified'] = True
        for reference in (POSTGRES, GARAGE, SPARK):
            attempt.command(['docker', 'pull', '--platform=linux/amd64', reference], timeout=240)
            actual = json.loads(attempt.command(['docker', 'image', 'inspect', reference], sensitive=True).stdout)[0]
            require(actual['Architecture'] == 'amd64' and actual['Os'] == 'linux'
                and any(v.endswith('@' + reference.rsplit('@', 1)[1]) for v in actual['RepoDigests']), 'ACTUAL_PINNED_LINUX_AMD64_IMAGE')
        checks['pinnedImagesPulled'] = True
        attempt.command(['docker', 'build', '--network=none', '--pull=false', '-f', str(build / 'Dockerfile.ci'), '-t', image, str(build)], timeout=240)
        catalog_password = secrets.token_hex(32)
        for name in ('postgres-secrets', 'silver-secrets'):
            (root / name).mkdir(mode=0o755)
            os.chmod(root / name, 0o755)
        save(root / 'postgres-secrets/bootstrap-password', secrets.token_hex(32).encode(), 0o444)
        save(root / 'postgres-init.sql', pg_init(catalog_password), 0o444)
        save(root / 'garage.toml', garage_config(), 0o444)
        (root / 'proof').mkdir(mode=0o777)
        os.chmod(root / 'proof', 0o777)
        save(root / 'compose.json', plan(image))
        attempt.cli('create', '--no-build', 'postgres', 'garage')
        network = json.loads(attempt.command(['docker', 'network', 'inspect', project + '_trial']).stdout)[0]
        require(network['Internal'] is True and network['Labels']['com.docker.compose.project'] == project, 'ACTUAL_INTERNAL_ONLY_NETWORK')
        checks['internalNetworkVerified'] = True
        volumes = [project + '_garage-meta', project + '_garage-data']
        for name in volumes:
            actual = json.loads(attempt.command(['docker', 'volume', 'inspect', name]).stdout)[0]
            require(actual['Labels']['com.docker.compose.project'] == project, 'ONLY_FRESH_OWN_GARAGE_VOLUMES')
        require(not attempt.command(['docker', 'ps', '-aq', '--no-trunc', '--filter', 'name=^/' + attempt.initializer_name + '$']).stdout.strip(), 'FRESH_INITIALIZER_NAME_ABSENT')
        save(root / 'initializer-intent.json', {'name': attempt.initializer_name, 'project': project, 'automaticRetry': False, 'network': 'none'})
        attempt.initializer_intended = True
        attempt.command(['docker', 'create', '--name', attempt.initializer_name, '--label', 'devdooly.io.spark-ci-project=' + project,
            '--cidfile', str(root / 'initializer.cid'), '--network=none', '--read-only', '--memory=64m', '--cpus=0.1', '--pids-limit=16', '--cap-drop=ALL', '--cap-add=CHOWN',
            '--security-opt=no-new-privileges:true', '--entrypoint=/bin/chown', '-v', volumes[0] + ':/meta', '-v', volumes[1] + ':/data', POSTGRES, '1000:1000', '/meta', '/data'])
        init = attempt.initializer()
        require(init is not None and not init['running'], 'EXACT_CREATED_INITIALIZER_BEFORE_START')
        attempt.command(['docker', 'start', '-a', init['id']])
        init = attempt.initializer()
        require(init is not None and not init['running'] and init['exitCode'] == 0 and init['oom'] is False, 'ACTUAL_INITIALIZER_SUCCESS')
        attempt.cli('start', 'postgres', 'garage')
        until = time.monotonic() + 120
        while True:
            require(time.monotonic() < until, 'POSTGRES_READY_DEADLINE')
            ready = attempt.cli('exec', '-T', 'postgres', 'pg_isready', '-h', '127.0.0.1', '-U', 'lab_bootstrap', '-d', 'iceberg_lab', check=False)
            if ready.returncode == 0:
                break
            time.sleep(1)
        pg = attempt.cli('exec', '-T', 'postgres', 'psql', '-X', '-A', '-t', '-U', 'lab_bootstrap', '-d', 'iceberg_lab', '-c', 'SHOW server_version;').stdout.decode().strip()
        require(re.match(r'^17\.11(?:\s|$)', pg), 'ACTUAL_POSTGRES_17_11')
        version = attempt.garage('--version').decode().strip()
        require(re.match(r'^garage v2\.4\.1(?:\s|$)', version), 'ACTUAL_GARAGE_2_4_1')
        until = time.monotonic() + 60
        while True:
            require(time.monotonic() < until, 'GARAGE_RPC_READY_DEADLINE')
            ready = attempt.cli('exec', '-T', 'garage', '/garage', '-c', '/etc/garage.toml', 'node', 'id', '--quiet', check=False)
            if ready.returncode == 0:
                node = ready.stdout.decode().strip().split('@')[0]
                break
            time.sleep(1)
        require(re.fullmatch('[a-f0-9]{64}', node), 'FRESH_GARAGE_NODE_ID')
        attempt.garage('layout', 'assign', '-z', 'github-isolated', '-c', '128M', node)
        attempt.garage('layout', 'apply', '--version', '1')
        bucket = json.loads(attempt.garage('json-api', 'CreateBucket', '{"globalAlias":"platform-lab-iceberg-20261015"}'))
        attempt.garage('json-api', 'UpdateBucket', json.dumps({'id': bucket['id'], 'body': {'quotas': {'maxSize': 64*1024**2, 'maxObjects': 128}}}))
        key = json.loads(attempt.garage('json-api', 'CreateKey', '{"name":"github-isolated-spark"}', sensitive=True))
        attempt.garage('json-api', 'AllowBucketKey', json.dumps({'bucketId': bucket['id'], 'accessKeyId': key['accessKeyId'], 'permissions': {'read': True, 'write': True, 'owner': False}}), sensitive=True)
        acl = json.loads(attempt.garage('json-api', 'GetKeyInfo', json.dumps({'id': key['accessKeyId'], 'showSecretKey': False}), sensitive=True))
        require(acl['accessKeyId'] == key['accessKeyId'] and acl['permissions']['createBucket'] is False and len(acl['buckets']) == 1
            and acl['buckets'][0]['id'] == bucket['id'] and acl['buckets'][0]['permissions'] == {'read': True, 'write': True, 'owner': False}, 'ACTUAL_SINGLE_BUCKET_NONOWNER_KEY')
        for name, value in {'catalog-password': catalog_password, 'endpoint': 'http://garage.platform-lab.svc.cluster.local:3900', 'access-key': key['accessKeyId'], 'secret-key': key['secretAccessKey']}.items():
            save(root / 'silver-secrets' / name, value.encode('ascii'), 0o444)
        del key, catalog_password
        attempt.cli('create', '--no-build', 'spark')
        actual = attempt.containers()
        require({v['role'] for v in actual} == {'postgres', 'garage', 'spark'}, 'EXACT_THREE_OWNED_ROLES_BEFORE_SPARK')
        checks['containerLimitsVerified'] = True
        attempt.cli('start', 'spark')
        until = time.monotonic() + 600
        while True:
            require(time.monotonic() < until, 'ONE_SPARK_PROCESS_DEADLINE')
            current = next(v for v in attempt.containers() if v['role'] == 'spark')
            if not current['running']:
                spark_diagnostics(attempt, current, diagnostics)
                require(current['exitCode'] == 0 and current['oom'] is False, 'ACTUAL_SPARK_CLEAN_EXIT_WITHOUT_OOM')
                require(diagnostics['bootstrap'] is not None and diagnostics['bootstrap']['passed'] is True, 'ACTUAL_BOOTSTRAP_COMPLETION_DIAGNOSTIC')
                break
            time.sleep(2)
        raw = (root / 'proof/spark-result.json').read_bytes()
        require(0 < len(raw) <= 16384, 'BOUNDED_SPARK_PUBLIC_PROOF')
        results = safe_spark_result(json.loads(raw))
        passed = True
    except Exception as error:
        text = str(error)
        failure = {'type': type(error).__name__, 'code': text if re.fullmatch('[A-Z0-9_]{1,128}', text) else 'ISOLATED_ATTEMPT_FAILED_OR_UNKNOWN'}
    finally:
        try:
            init = attempt.initializer()
            if init and init['running']:
                attempt.command(['docker', 'stop', '--time=30', init['id']], timeout=45)
            init = attempt.initializer()
            require(init is None or not init['running'], 'OWN_INITIALIZER_STOPPED_OR_NOT_CREATED')
            initializer_stopped = True
        except Exception:
            initializer_stopped = False
            passed = False
        try:
            owned = attempt.containers()
            for row in owned:
                if row['running']:
                    attempt.command(['docker', 'stop', '--time=30', row['id']], timeout=45)
            final = attempt.containers()
            require(all(not row['running'] for row in final), 'ALL_OWNED_CONTAINERS_STOPPED')
            stopped = True
        except Exception:
            stopped = False
            passed = False
    summary = {'schemaVersion': 1, 'passed': passed, 'scope': 'ISOLATED_GITHUB_RUNNER_SPARK_JDBC_GARAGE', 'capturedAt': utc(),
        'sourceCommit': source, 'result': results, 'failure': failure, 'ownedComposeContainersStopped': stopped,
        'sparkDiagnostic': diagnostics,
        'ownedInitializerCreationAttempted': attempt.initializer_intended, 'ownedInitializerStoppedOrNotCreated': initializer_stopped,
        'fixedImagePlan': {'postgres': POSTGRES, 'garage': GARAGE, 'sparkBase': SPARK}, 'plannedJarCount': 3, 'plannedJarBytes': 112793760,
        'localImageOnly': True, 'imagePushed': False, 'plannedHostPublishedPortCount': 0, 'checks': checks,
        'plannedSparkCpuLimit': 1, 'plannedSparkMemoryLimitBytes': 3*1024**3, 'plannedPostgresAndGarageEachMemoryLimitBytes': 512*1024**2,
        'rawLogsOrCredentialsUploaded': False, 'automaticRetryPerformed': False,
        'nativeTrinoVerified': False, 'miniPcContacted': False, 'kubernetesVerified': False,
        'trialVolumesDeletedByHarness': False, 'runnerStorageIsEphemeral': True}
    save(public / 'summary.json', summary)
    print(json.dumps({'passed': passed, 'scope': summary['scope'], 'ownedContainersStopped': stopped}), flush=True)
    return 0 if passed else 1


if __name__ == '__main__':
    raise SystemExit(main())
