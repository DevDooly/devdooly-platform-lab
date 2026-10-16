"""Explicit hosted-runner prep only. Import does not start or download anything."""
import hashlib
import math
import os
from pathlib import Path
import re
import shutil
import stat
import sys
import time
import uuid
import zipfile

import archive_classes as artifacts
import bounded_process as processes
from lifecycle import encoded, read_proof, require, sha, strict

SPARK = 'docker.io/apache/spark@sha256:0b8f5befe00d258df03b252158b3894b8654390f1958741accf98155539a662a'
LOCK_SHA = '6ca247b283025189ecf36c67ae03fe9101b25a53fe7b62593725e076276e33e3'
ICEBERG_SHA = 'd6ea6c5d099288daeb7d5a92061bd3d7d8f296492632b42378e5f2f0e3066242'
ICEBERG_SHA512 = 'f4620bb2d20777146a769a8a939a5bed658e1d5708b6a5155e1f6e831c0bfd29bd1f82618dc59bc0f30399ffcb03add3e66656286692dc6c2be94e4e1f4e7479'
ICEBERG_BYTES = 47959591
ICEBERG_URL = 'https://repo.maven.apache.org/maven2/org/apache/iceberg/iceberg-spark-runtime-4.1_2.13/1.11.0/iceberg-spark-runtime-4.1_2.13-1.11.0.jar'
MAIN = 'org.apache.iceberg.ClosedCopyDecoder'
RUNTIME_CP = '/opt/spark/jars/*:/opt/decoder/iceberg-runtime.jar:/opt/decoder/classes'
JAVA_RELATIVE = 'infra/iceberg-retention-ci/src/org/apache/iceberg/ClosedCopyDecoder.java'
ZERO_START = '0001-01-01T00:00:00Z'


def save(folder, name, value):
    raw = value if type(value) is bytes else encoded(value)
    path = folder / name
    with os.fdopen(os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600), 'wb') as stream:
        stream.write(raw); stream.flush(); os.fsync(stream.fileno())
    return {'raw': raw, 'sha256': sha(raw)}


def file_hashes(path, maximum):
    """Bounded stable whole hashes, without changing a source or staging file."""
    first = path.lstat()
    require(stat.S_ISREG(first.st_mode) and first.st_nlink == 1 and 0 < first.st_size <= maximum,
        'PREP_BOUNDED_REGULAR_SINGLE_LINK_INPUT_REQUIRED')
    hashes = (hashlib.sha256(), hashlib.sha512())
    with os.fdopen(os.open(path, os.O_RDONLY | os.O_NOFOLLOW), 'rb') as stream:
        opened = os.fstat(stream.fileno()); size = 0
        while True:
            raw = stream.read(min(65536, maximum + 1 - size))
            if not raw: break
            size += len(raw); require(size <= maximum, 'PREP_WHOLE_INPUT_BOUND')
            for digest in hashes: digest.update(raw)
        last = os.fstat(stream.fileno())
    final = path.lstat()
    identity = lambda value: (value.st_dev, value.st_ino, value.st_size, value.st_mode,
        value.st_nlink, value.st_mtime_ns, value.st_ctime_ns)
    require(identity(first) == identity(opened) == identity(last) == identity(final)
        and size == first.st_size, 'PREP_INPUT_IDENTITY_CHANGED')
    return {'bytes': size, 'sha256': hashes[0].hexdigest(), 'sha512': hashes[1].hexdigest()}


def checked_lock(repo):
    proof = read_proof(repo / 'infra/spark-silver/artifact-lock.downloaded.json')
    require(proof['sha256'] == LOCK_SHA, 'EXACT_EXISTING_DOWNLOADED_ARTIFACT_LOCK')
    value = strict(proof['raw'])
    rows = [row for row in value['jars'] if row['coordinate'] == 'org.apache.iceberg:iceberg-spark-runtime-4.1_2.13:1.11.0']
    require(len(rows) == 1 and rows[0] == {
        'bytes': ICEBERG_BYTES,
        'coordinate': 'org.apache.iceberg:iceberg-spark-runtime-4.1_2.13:1.11.0',
        'downloadUrl': ICEBERG_URL, 'filename': 'iceberg-spark-runtime-4.1_2.13-1.11.0.jar',
        'sha256': ICEBERG_SHA, 'sha512': ICEBERG_SHA512, 'sha512SidecarVerified': True},
        'ONE_EXACT_LOCKED_OFFICIAL_ICEBERG_ARTIFACT')
    require(value['baseImage']['reference'] == SPARK and value['baseImage']['platform'] == 'linux/amd64',
        'SAME_EXISTING_SPARK_BASE_REFERENCE')
    return proof


def image_identity(raw):
    values = strict(raw)
    require(type(values) is list and len(values) == 1, 'ONE_PINNED_PREP_IMAGE_REQUIRED')
    image = values[0]; config = image['Config']
    require(re.fullmatch('sha256:[a-f0-9]{64}', image['Id']) and image['Os'] == 'linux'
        and image['Architecture'] == 'amd64'
        and any(item.endswith('@' + SPARK.rsplit('@', 1)[1]) for item in image['RepoDigests'])
        and not config.get('Volumes') and not config.get('Healthcheck'),
        'PREP_ACTUAL_PINNED_IMAGE_WITHOUT_IMPLICIT_ACTORS')
    env = config.get('Env') or []
    require(type(env) is list and all(type(item) is str and '=' in item for item in env),
        'PREP_ACTUAL_IMAGE_ENV_SHAPE')
    forbidden = {'CLASSPATH', 'JAVA_TOOL_OPTIONS', '_JAVA_OPTIONS', 'JDK_JAVA_OPTIONS'}
    require(all(item.split('=', 1)[0].upper() not in forbidden
        and not item.split('=', 1)[0].upper().startswith('LOADER_') for item in env),
        'PREP_IMAGE_OPTION_INJECTION_REJECTED')
    return {'id': image['Id'], 'envSha256': sha(encoded(env))}


def cold_identity(raw, cid, name, source, image, expected_signature=None):
    values = strict(raw)
    require(type(values) is list and len(values) == 1, 'ONE_OWN_COLD_EXPORT_CONTAINER')
    value = values[0]; config, host, state = value['Config'], value['HostConfig'], value['State']
    require(value['Id'] == cid and re.fullmatch('[a-f0-9]{64}', cid) and value['Name'] == '/' + name
        and value['Image'] == image['id'] and config['Image'] == SPARK
        and config['Labels'].get('devdooly.io.closed-copy-prep') == name
        and config['Labels'].get('devdooly.io.prep-source') == source
        and config['Entrypoint'] == ['/bin/true'] and config['Cmd'] == ['closed-copy-prep-never-started']
        and config['User'] == '185:185' and sha(encoded(config.get('Env') or [])) == image['envSha256']
        and not config.get('Healthcheck') and not value['Mounts']
        and host['ReadonlyRootfs'] is True and host['Privileged'] is False
        and host['NetworkMode'] == 'none' and set(value['NetworkSettings']['Networks']) == {'none'}
        and not host.get('PortBindings') and host['NanoCpus'] == 100000000
        and host['Memory'] == host['MemorySwap'] == 128*1024**2
        and type(host['PidsLimit']) is int and host['PidsLimit'] == 16
        and host['CapDrop'] == ['ALL'] and not host.get('CapAdd')
        and host['SecurityOpt'] == ['no-new-privileges:true']
        and host['RestartPolicy']['Name'] == 'no' and value['RestartCount'] == 0
        and not host.get('AutoRemove') and state['Running'] is False
        and type(state['Pid']) is int and state['Pid'] == 0 and state['StartedAt'] == ZERO_START
        and state['OOMKilled'] is False,
        'EXACT_BOUND_NEVER_STARTED_PREP_CONTAINER')
    require('OomKillDisable' in host and (host['OomKillDisable'] is None or host['OomKillDisable'] is False),
        'PREP_ENABLED_OOM_KILLER_REQUIRED')
    signature = {'id': cid, 'created': value['Created'], 'configSha256': sha(encoded(config)),
        'hostSha256': sha(encoded({**host, 'OomKillDisable': False})), 'mounts': value['Mounts']}
    require(expected_signature is None or signature == expected_signature, 'COLD_PREP_CONFIGURATION_CHANGED')
    return signature


def classpath_inventory(jars, rows):
    actual = []
    for row in rows:
        observed = file_hashes(jars / row['name'], 128*1024**2)
        require(observed['bytes'] == row['bytes'] and observed['sha256'] == row['sha256'],
            'EXPORTED_CLASSPATH_BYTES_CHANGED')
        with zipfile.ZipFile(jars / row['name']) as archive:
            for member in archive.infolist():
                require(not re.match(r'(?:META-INF/versions/[0-9]+/)?org/apache/iceberg/.*\.class\Z',
                    member.filename), 'ONLY_LOCKED_RUNTIME_MAY_SUPPLY_ICEBERG_CLASSES')
        actual.append(dict(row))
    require(actual == sorted(actual, key=lambda value: value['name']), 'CANONICAL_EXPORTED_CLASSPATH_ORDER')
    return sha(encoded(actual))


def prepare(repo, output, source_commit, decoder_source_sha256, authority_source_sha256, helper_source_pins):
    """Called by a source-pinned caller before the original workload begins."""
    require(sys.platform == 'linux' and os.name == 'posix' and os.environ.get('GITHUB_ACTIONS') == 'true'
        and os.environ.get('RUNNER_ENVIRONMENT') == 'github-hosted'
        and re.fullmatch('[a-f0-9]{40}', source_commit)
        and os.environ.get('SOURCE_COMMIT') == os.environ.get('GITHUB_SHA') == source_commit,
        'PREP_ONLY_SAME_SOURCE_GITHUB_HOSTED_LINUX')
    require(read_proof(Path(__file__).absolute())['sha256'] == authority_source_sha256,
        'EXACT_PREP_EXECUTOR_SOURCE_REQUIRED')
    for module in (artifacts, processes):
        path = Path(module.__file__).absolute()
        require(path.name in helper_source_pins
            and read_proof(path, 131072)['sha256'] == helper_source_pins[path.name],
            'EXACT_PREP_HELPER_SOURCE_REQUIRED')
    require(not any(name in os.environ for name in ('JAVA_TOOL_OPTIONS','_JAVA_OPTIONS','JDK_JAVA_OPTIONS','CLASSPATH')),
        'NO_RUNNER_JAVA_OPTION_INJECTION')
    repo, output = Path(repo).absolute(), Path(output).absolute()
    require(repo.resolve(strict=True) == repo and output.parent.resolve(strict=True) == output.parent
        and not os.path.lexists(output) and output.parent == repo / '.local'
        and re.fullmatch('closed-copy-prep-[a-f0-9]{32}', output.name),
        'FRESH_CANONICAL_PRIVATE_PREP_ROOT')
    lock = checked_lock(repo)
    java_source = read_proof(repo / JAVA_RELATIVE, 131072)
    require(java_source['sha256'] == decoder_source_sha256, 'EXACT_SINGLE_DECODER_JAVA_SOURCE')
    java_home = Path(os.environ['JAVA_HOME']).resolve(strict=True)
    java, javac = java_home / 'bin/java', java_home / 'bin/javac'
    java_binary, compiler_binary = file_hashes(java, 16*1024**2), file_hashes(javac, 16*1024**2)
    output.mkdir(mode=0o700)
    require(stat.S_IMODE(output.stat().st_mode) == 0o700, 'PRIVATE_PREP_ROOT_MODE')
    started = time.monotonic(); cutoff = started + 600; work_cutoff = cutoff - 40
    save(output, 'intent.json', {'scope':'SEPARATE_BOUNDED_COMPILER_PREPARATION_ONLY',
        'sourceCommit':source_commit, 'prepExecutorSha256':authority_source_sha256,
        'decoderSourceSha256':decoder_source_sha256, 'artifactLockSha256':lock['sha256'],
        'budgetSeconds':600, 'cleanupReserveSeconds':40,
        'originalWorkloadStarted':False, 'automaticRetry':False})
    (output / 'docker-config').mkdir(mode=0o700)
    docker = ['docker','--host','unix:///var/run/docker.sock','--config',str(output/'docker-config')]
    name = 'closed-copy-prep-' + uuid.uuid4().hex
    cid = signature = image = None
    removal_attempted = removed = False
    failure = None; attestation = None
    def run(label, argv, timeout=10, *, cleanup=False, **kwargs):
        value = processes.execute(argv, output, label, cutoff if cleanup else work_cutoff, timeout, **kwargs)
        require(value['returncode'] == 0, 'PREP_KNOWN_CHILD_NONZERO_NO_RETRY')
        return value
    def inspect(label, *, cleanup=False):
        value = run(label, [*docker,'inspect',cid], persist_stdout=False, cleanup=cleanup)
        return cold_identity(value['stdout'], cid, name, authority_source_sha256, image, signature)
    try:
        require(shutil.disk_usage(output).free >= 8*1024**3, 'PREP_PRESERVE_EXISTING_EIGHT_GIB_RESERVE')
        java_version = run('compiler-java-version', [str(java),'-version'])
        compiler_version = run('compiler-javac-version', [str(javac),'-version'])
        require(re.search(rb'(?:openjdk|java) version "21(?:[.+][^"\r\n]+)?"', java_version['stdout']+java_version['stderr'])
            and re.fullmatch(rb'javac 21(?:[.+][A-Za-z0-9._+-]+)?\r?\n', compiler_version['stdout'])
            and not compiler_version['stderr'], 'ACTUAL_HOST_COMPILER_JAVA21_REQUIRED')
        run('pinned-image-pull', [*docker,'pull','--platform=linux/amd64',SPARK], 240)
        image_result = run('pinned-image-inspect', [*docker,'image','inspect',SPARK], persist_stdout=False)
        image = image_identity(image_result['stdout'])
        created = run('cold-export-create', [*docker,'create','--name',name,
            '--label','devdooly.io.closed-copy-prep='+name,'--label','devdooly.io.prep-source='+authority_source_sha256,
            '--network=none','--read-only','--user=185:185','--cpus=0.1','--memory=128m',
            '--memory-swap=128m','--pids-limit=16','--cap-drop=ALL',
            '--security-opt=no-new-privileges:true','--restart=no','--entrypoint=/bin/true',
            SPARK,'closed-copy-prep-never-started'])
        cid = created['stdout'].removesuffix(b'\n').decode('ascii')
        require(re.fullmatch('[a-f0-9]{64}',cid), 'PREP_CREATED_FULL_CID_REQUIRED')
        signature = inspect('cold-export-before')
        exported = run('export-classpath', [*docker,'cp',cid+':/opt/spark/jars','-'], 90,
            maximum_stdout=artifacts.MAX_ARCHIVE, stdout_filename='classpath.tar')
        inspect('cold-export-after')
        extraction = output / 'exported'; extraction.mkdir(mode=0o700)
        jars = artifacts.unpack_jars(output/'classpath.tar', extraction)
        classpath_sha = classpath_inventory(extraction/'jars', jars)
        # Default curl redirects are disabled; only the existing official URL is used.
        run('locked-iceberg-download', ['curl','--disable','--fail','--silent','--show-error',
            '--proto','=https','--max-time','120',ICEBERG_URL], 125,
            maximum_stdout=ICEBERG_BYTES, stdout_filename='iceberg-runtime.jar')
        iceberg = output / 'iceberg-runtime.jar'
        jar_hash = file_hashes(iceberg, ICEBERG_BYTES)
        require(jar_hash == {'bytes':ICEBERG_BYTES,'sha256':ICEBERG_SHA,'sha512':ICEBERG_SHA512},
            'ACTUAL_LOCKED_ICEBERG_SHA256_SHA512_REQUIRED')
        artifacts.scan_jar(iceberg)
        iceberg.chmod(0o444)
        sources, empty, classes = output/'source', output/'empty-sourcepath', output/'classes'
        for folder in (sources,empty,classes): folder.mkdir(mode=0o700)
        save(sources, 'ClosedCopyDecoder.java', java_source['raw'])
        host_cp = str(extraction/'jars/*') + os.pathsep + str(iceberg)
        compiled = run('compile-main-only', [str(javac),'-J-Xmx256m','-J-XX:ActiveProcessorCount=1',
            '--release','21','-encoding','UTF-8','-proc:none','-implicit:none',
            '-sourcepath',str(empty),'-cp',host_cp,'-d',str(classes),str(sources/'ClosedCopyDecoder.java')], 120)
        require(compiled['stderr'] == b'', 'ACTUAL_DECODER_COMPILE_STDERR_ZERO_REQUIRED')
        class_rows = artifacts.seal_new_classes(classes)
        require(artifacts.compiled_classes(classes) == class_rows, 'SEALED_CLASS_INVENTORY_READBACK')
        require(classpath_inventory(extraction/'jars', jars) == classpath_sha
            and file_hashes(iceberg,ICEBERG_BYTES) == jar_hash
            and read_proof(repo/JAVA_RELATIVE,131072) == java_source
            and checked_lock(repo) == lock and file_hashes(java,16*1024**2) == java_binary
            and file_hashes(javac,16*1024**2) == compiler_binary,
            'ALL_COMPILER_SOURCE_CLASSPATH_INPUTS_UNCHANGED')
        inspect('cold-export-before-remove')
        removal_attempted = True
        removed_result = run('cold-export-remove', [*docker,'rm',cid])
        require(removed_result['stdout'].removesuffix(b'\n') == cid.encode('ascii'),
            'OWN_COLD_EXPORT_REMOVE_RETURNED_EXACT_ID')
        absent = run('cold-export-absence', [*docker,'ps','-aq','--no-trunc','--filter','id='+cid])
        require(absent['stdout'] == b'', 'OWN_COLD_EXPORT_ABSENCE_REQUIRED')
        removed = True
        require(time.monotonic() < cutoff and shutil.disk_usage(output).free >= 8*1024**3,
            'PREP_BUDGET_AND_ORIGINAL_DISK_RESERVE')
        attestation = {
            'schemaVersion':1,'scope':'ACTUAL_DECODER_COMPILE_WITH_PINNED_SPARK_CLASSPATH',
            'sourceCommit':source_commit,'decoderSourceSha256':decoder_source_sha256,
            'prepExecutorSha256':authority_source_sha256,'prepHelpers':helper_source_pins,
            'runtimeImageReference':SPARK,'runtimeImageId':image['id'],'javaMajor':21,
            'mainClass':MAIN,'classpath':RUNTIME_CP,'classes':class_rows,
            'compileExitCode':compiled['returncode'],'compileStderrBytes':len(compiled['stderr']),
            'compileReceiptSha256':sha(encoded(compiled['receipt'])),
            'javaVersionOutputSha256':sha(java_version['stdout']+java_version['stderr']),
            'javacVersionOutputSha256':sha(compiler_version['stdout']+compiler_version['stderr']),
            'javaExecutableSha256':java_binary['sha256'],'javacExecutableSha256':compiler_binary['sha256'],
            'classpathInventorySha256':classpath_sha,'classpathJarCount':len(jars),
            'classpathArchiveReceiptSha256':sha(encoded(exported['receipt'])),
            'icebergJarSha256':ICEBERG_SHA,'icebergJarSha512':ICEBERG_SHA512,
            'coldExportCid':cid,'coldExportSignatureSha256':sha(encoded(signature)),
            'coldExportNeverStarted':True,'coldExportRemovedAndAbsent':True,
            'prepElapsedMillis':int((time.monotonic()-started)*1000),
            'cleanupReserveSeconds':40,
            'originalWorkloadStarted':False,'runtimeJavaExecutionVerified':False,
            'osCpuMemoryLimitClaimedForCompiler':False,'automaticRetry':False}
    except BaseException as error:
        message = str(error)
        failure = message if re.fullmatch('[A-Z0-9_]{1,128}',message) else 'PREP_FAILED_OR_UNKNOWN_NO_RETRY'
    finally:
        if cid and signature is not None and not removal_attempted:
            try:
                inspect('failed-prep-cold-before-remove', cleanup=True)
                removal_attempted = True
                removed_result = run('failed-prep-cold-remove',[*docker,'rm',cid], cleanup=True)
                require(removed_result['stdout'].removesuffix(b'\n') == cid.encode('ascii'),'EXACT_FAILED_PREP_COLD_REMOVE')
                absent = run('failed-prep-cold-absence',[*docker,'ps','-aq','--no-trunc','--filter','id='+cid], cleanup=True)
                require(absent['stdout'] == b'','FAILED_PREP_COLD_ABSENCE_REQUIRED')
                removed = True
            except BaseException:
                failure = failure or 'OWN_COLD_EXPORT_CLEANUP_UNVERIFIED_NO_RETRY'
        save(output,'prep-result.private.json',{
            'scope':'SEPARATE_PREP_ACTUAL_OUTCOME_NOT_RUNTIME_CLOSURE',
            'sourceCommit':source_commit,'passed':failure is None and attestation is not None,
            'failureCode':failure,
            'knownColdCid':type(cid) is str and re.fullmatch('[a-f0-9]{64}',cid) is not None,
            'coldIdentityBound':signature is not None,
            'coldRemovalAttempted':removal_attempted,'coldRemovedAndAbsent':removed,
            'originalWorkloadStarted':False,'automaticRetry':False})
    require(failure is None and attestation is not None and removed, failure or 'PREP_SUCCESS_NOT_OBSERVED')
    proof = save(output,'prep-attestation.private.json',attestation)
    return {'proof':proof,'classes':output/'classes','iceberg':output/'iceberg-runtime.jar','root':output}
