"""Only a new owned decoder container. Does not touch original trial actors."""
import os
from pathlib import Path
import re
import subprocess
import threading
import time

from lifecycle import encoded, read_proof, require, sha, strict

SPARK = 'docker.io/apache/spark@sha256:0b8f5befe00d258df03b252158b3894b8654390f1958741accf98155539a662a'
ICEBERG_SHA = 'd6ea6c5d099288daeb7d5a92061bd3d7d8f296492632b42378e5f2f0e3066242'
MAIN = 'org.apache.iceberg.ClosedCopyDecoder'
CLASSPATH = '/opt/spark/jars/*:/opt/decoder/iceberg-runtime.jar:/opt/decoder/classes'
DOCKER = ['docker', '--host', 'unix:///var/run/docker.sock']
MAX_REPLY = 4 * 1024**2
RESERVE = 40


def command(args, cutoff, maximum=5, check=True):
    timeout = min(maximum, cutoff - time.monotonic())
    require(timeout > 0, 'DECODER_ORIGINAL_ABSOLUTE_DEADLINE')
    result = subprocess.run([*DOCKER, *args], stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=timeout)
    require(len(result.stdout) <= 1024**2 and len(result.stderr) <= 65536, 'DECODER_CONTROL_OUTPUT_BOUND')
    require(not check or result.returncode == 0, 'DECODER_CONTROL_FAILED_NO_RETRY')
    return result


def prep(proof, expected_sha, classes, iceberg, source, decoder_source_sha):
    """Compile is a separate prior stage; no javac or build/pull is invoked."""
    require(re.fullmatch('[a-f0-9]{64}', expected_sha) and re.fullmatch('[a-f0-9]{64}', decoder_source_sha)
        and proof['sha256'] == expected_sha and sha(proof['raw']) == expected_sha,
        'EXACT_PRIOR_DECODER_PREP_PROOF_REQUIRED')
    value = strict(proof['raw'])
    require(value['scope'] == 'ACTUAL_DECODER_COMPILE_WITH_PINNED_SPARK_CLASSPATH'
        and value['sourceCommit'] == source and value['decoderSourceSha256'] == decoder_source_sha
        and type(value['compileExitCode']) is int and value['compileExitCode'] == 0
        and type(value['compileStderrBytes']) is int and value['compileStderrBytes'] == 0
        and value['runtimeImageReference'] == SPARK and value['javaMajor'] == 21
        and re.fullmatch('sha256:[a-f0-9]{64}', value['runtimeImageId'])
        and value['mainClass'] == MAIN and value['classpath'] == CLASSPATH,
        'SOURCE_IMAGE_CLASSPATH_COMPILE_ATTESTATION_REQUIRED')
    classes, iceberg = Path(classes).absolute(), Path(iceberg).absolute()
    require(classes.resolve(strict=True) == classes and classes.is_dir()
        and not classes.is_symlink() and not any(c in str(classes) + str(iceberg) for c in ',\r\n'),
        'CANONICAL_DECODER_READONLY_MOUNTS_REQUIRED')
    require(os.name == 'posix' and classes.stat().st_mode & 0o777 in (0o555,0o755)
        and iceberg.lstat().st_mode & 0o777 == 0o444,
        'NEW_NONSECRET_INPUTS_READABLE_BY_CONTAINER_UID185')
    require(type(value['classes']) is list and 0 < len(value['classes']) <= 64,
        'BOUNDED_COMPILED_CLASS_INVENTORY_REQUIRED')
    expected = set()
    for row in value['classes']:
        relative = row['path']
        require(type(relative) is str and re.fullmatch(r'org/apache/iceberg/ClosedCopyDecoder(?:\$[A-Za-z0-9_$]+)?\.class', relative)
            and relative not in expected, 'EXACT_UNIQUE_PACKAGE_LOCAL_CLASS_REQUIRED')
        expected.add(relative)
        actual = read_proof(classes / relative, 1024**2)
        require(actual['sha256'] == row['sha256'] and len(actual['raw']) == row['bytes'],
            'COMPILED_CLASS_WHOLE_BYTES_CHANGED')
        require((classes/relative).lstat().st_mode & 0o777 == 0o444, 'NEW_COMPILED_CLASS_WORLD_READABLE_ONLY')
    for directory in (p for p in classes.rglob('*') if p.is_dir()):
        require(not directory.is_symlink() and str(directory.relative_to(classes)) in
            ('org','org/apache','org/apache/iceberg') and directory.stat().st_mode & 0o777 in (0o555,0o755),
            'EXACT_CONTAINER_READABLE_CLASS_PACKAGE_DIRECTORIES')
    require('org/apache/iceberg/ClosedCopyDecoder.class' in expected
        and {str(p.relative_to(classes)).replace('\\', '/') for p in classes.rglob('*') if not p.is_dir()} == expected,
        'NO_EXTRA_DECODER_CLASS_FILES')
    require(read_proof(iceberg, 48*1024**2)['sha256'] == ICEBERG_SHA, 'EXACT_LOCKED_ICEBERG_RUNTIME_JAR')
    # This actual read is performed before original main/workload clock.
    image = strict(command(['image', 'inspect', SPARK], time.monotonic() + 5).stdout)
    require(type(image) is list and len(image) == 1 and image[0]['Id'] == value['runtimeImageId']
        and image[0]['Os'] == 'linux' and image[0]['Architecture'] == 'amd64'
        and any(item.endswith('@' + SPARK.rsplit('@', 1)[1]) for item in image[0]['RepoDigests'])
        and not image[0]['Config'].get('Volumes') and not image[0]['Config'].get('Healthcheck'),
        'ACTUAL_PREP_PINNED_RUNTIME_IMAGE')
    env = image[0]['Config'].get('Env') or []
    forbidden = {'CLASSPATH', 'JAVA_TOOL_OPTIONS', '_JAVA_OPTIONS', 'JDK_JAVA_OPTIONS'}
    require(all(item.split('=', 1)[0].upper() not in forbidden
        and not item.split('=', 1)[0].upper().startswith('LOADER_') for item in env),
        'NO_IMAGE_JAVA_OR_LOADER_OPTION_INJECTION')
    return {'proofSha256': expected_sha, 'imageId': value['runtimeImageId'], 'classes': classes,
        'iceberg': iceberg, 'sourceCommit': source, 'decoderSourceSha256': decoder_source_sha,
        'imageEnvSha256': sha(encoded(env))}


class Decoder:
    def __init__(self, prepared, folder, project, original_started, *, canonical_host, canonical_mounts):
        require(re.fullmatch('cloud-trial9-[a-f0-9]{32}', project), 'EXACT_FRESH_TRIAL_PROJECT')
        self.prepared, self.folder, self.project = prepared, Path(folder), project
        self.canonical_host, self.canonical_mounts = canonical_host, canonical_mounts
        self.absolute = original_started + 600
        self.cutoff = min(time.monotonic() + 60, self.absolute - RESERVE)
        require(self.cutoff > time.monotonic(), 'DECODER_CLEANUP_RESERVE_REQUIRED')
        self.name = project + '-closed-copy-decoder'
        self.cid = self.signature = self.process = None
        self.lock, self.done, self.wake = threading.Lock(), threading.Event(), threading.Event()
        self.watchdog_fired = False
        self.stopped = self.cli_reaped = False
        self.cleanup_failure = None
        self.cleanup_started = False
        self.final_state = None
        self.folder_created = self.create_attempted = self.start_attempted = self.cold_observed = False
        self.stderr_overflow = self.stderr_joined = False
        self.stderr_error = None
        self.labels = {'devdooly.io.iceberg-closed-copy': project,
            'devdooly.io.decoder-source': prepared['decoderSourceSha256']}

    def inspect(self):
        require(self.cid and re.fullmatch('[a-f0-9]{64}', self.cid), 'OWN_DECODER_FULL_CID_REQUIRED')
        values = strict(command(['inspect', self.cid], self.absolute).stdout)
        require(type(values) is list and len(values) == 1, 'ONE_EXACT_DECODER_INSPECT')
        raw = values[0]; config, host = raw['Config'], raw['HostConfig']
        require(raw['Id'] == self.cid and raw['Name'] == '/' + self.name
            and config['Image'] == SPARK and raw['Image'] == self.prepared['imageId']
            and all(config['Labels'].get(k) == v for k, v in self.labels.items())
            and config['Entrypoint'] == ['java'] and config['Cmd'] == self.java_args
            and sha(encoded(config.get('Env') or [])) == self.prepared['imageEnvSha256']
            and not config.get('Healthcheck')
            and config['User'] == '185:185' and host['ReadonlyRootfs'] is True
            and host['Privileged'] is False and host['NetworkMode'] == 'none'
            and set(raw['NetworkSettings']['Networks']) == {'none'} and not host.get('PortBindings')
            and host['NanoCpus'] == 1000000000 and host['Memory'] == host['MemorySwap'] == 512*1024**2
            and type(host['PidsLimit']) is int and host['PidsLimit'] == 64
            and host['RestartPolicy']['Name'] == 'no' and raw['RestartCount'] == 0
            and host['CapDrop'] == ['ALL'] and not host.get('CapAdd') and not host.get('AutoRemove')
            and host['SecurityOpt'] == ['no-new-privileges:true'],
            'EXACT_NEW_DECODER_IDENTITY_AND_LIMITS')
        mounts = {(v['Source'], v['Destination'], v['Type'], v['RW']) for v in raw['Mounts']}
        require(len(raw['Mounts']) == 2 and mounts == {
            (str(self.prepared['classes']), '/opt/decoder/classes', 'bind', False),
            (str(self.prepared['iceberg']), '/opt/decoder/iceberg-runtime.jar', 'bind', False)},
            'EXACT_TWO_DECODER_READONLY_MOUNTS')
        signature = {'id': self.cid, 'config': config, 'host': self.canonical_host(host),
            'mounts': self.canonical_mounts(raw['Mounts']), 'created': raw['Created']}
        if self.signature is not None: require(signature == self.signature, 'DECODER_FULL_SPEC_CHANGED')
        else: self.signature = signature
        return raw['State']

    def cleanup(self):
        """Only this new decoder CID; exit proof is independent of CLI reap."""
        with self.lock:
            if self.cleanup_started:
                require(self.stopped, 'PREVIOUS_OWN_DECODER_CLEANUP_UNRESOLVED_NO_REPEAT')
                return self.final_state
            self.cleanup_started = True
            if self.process is not None and self.process.poll() is None:
                self.process.kill(); self.process.wait(timeout=max(0.01, min(2, self.absolute - time.monotonic())))
            self.cli_reaped = self.process is not None and self.process.poll() is not None
            state = self.inspect()
            if state['Running']:
                command(['stop', '--time=2', self.cid], self.absolute, maximum=5, check=False)
                state = self.inspect()
                if state['Running']:
                    command(['kill', '--signal=KILL', self.cid], self.absolute, maximum=3)
            wait = command(['wait', self.cid], self.absolute, maximum=5)
            state = self.inspect()
            code = wait.stdout.removesuffix(b'\n')
            require(re.fullmatch(b'[0-9]{1,3}', code) and state['Running'] is False
                and type(state['Pid']) is int and state['Pid'] == 0
                and type(state['ExitCode']) is int and int(code) == state['ExitCode'],
                'OWN_DECODER_WAIT_AND_EXIT_REQUIRED')
            self.stopped = True
            self.final_state = state
            return state

    def watchdog(self):
        self.wake.wait(max(0, self.cutoff - time.monotonic()))
        if not self.done.is_set():
            self.watchdog_fired = True
            try: self.cleanup()
            except BaseException: self.cleanup_failure = 'OWN_DECODER_STOP_OR_REAP_UNVERIFIED'

    def drain_stderr(self, source, target):
        kept = 0
        try:
            while True:
                chunk = source.read(4096)
                if not chunk: break
                available = 65536 - kept
                if available:
                    prefix = chunk[:available]; target.write(prefix); kept += len(prefix)
                if len(chunk) > available:
                    self.stderr_overflow = True; self.wake.set()
            target.flush(); os.fsync(target.fileno())
        except BaseException:
            self.stderr_error = 'OWN_DECODER_STDERR_DRAIN_UNVERIFIED'; self.wake.set()

    def run(self, frame):
        require(not os.path.lexists(self.folder), 'FRESH_DECODER_OUTPUT_REQUIRED_NO_RETRY')
        error = None
        try:
            return self._run(frame)
        except BaseException as caught:
            error = caught
            raise
        finally:
            if self.folder_created:
                text = '' if error is None else str(error)
                state = {'scope': 'NEW_DECODER_ACTUAL_STATE_NOT_NORMAL_EXIT_CLAIM',
                    'failureCode': None if error is None else text if re.fullmatch('[A-Z0-9_]{1,128}', text)
                        else 'DECODER_FAILED_OR_UNKNOWN_NO_RETRY',
                    'createAttempted': self.create_attempted,
                    'knownFullCid': self.cid is not None and re.fullmatch('[a-f0-9]{64}', self.cid) is not None,
                    'identityBound': self.signature is not None, 'coldNotStartedObserved': self.cold_observed,
                    'startAttempted': self.start_attempted, 'attachCliStarted': self.process is not None,
                    'attachCliReaped': self.cli_reaped, 'cleanupAttempted': self.cleanup_started,
                    'ownedDecoderStoppedVerified': self.stopped, 'watchdogFired': self.watchdog_fired,
                    'privateStderrOverflow': self.stderr_overflow, 'stderrReaderJoined': self.stderr_joined,
                    'finalExitCode': None if self.final_state is None else self.final_state['ExitCode'],
                    'finalOomKilled': None if self.final_state is None else self.final_state['OOMKilled'],
                    'originalRoleStopCallsAdded': 0, 'originalInitializerStopCallsAdded': 0,
                    'automaticRetry': False}
                try:
                    with (self.folder/'decoder-state.private.json').open('xb') as out:
                        os.fchmod(out.fileno(),0o600) if os.name=='posix' else None
                        out.write(encoded(state));out.flush();os.fsync(out.fileno())
                except Exception:
                    if error is None: raise ValueError('DECODER_STATE_WRITE_FAILED_NO_RETRY') from None

    def _run(self, frame):
        require(type(frame) is bytes and 0 < len(frame) <= 33*1024**2, 'BOUNDED_APPROVED_RAM_FRAME')
        require(os.name == 'posix', 'LINUX_DECODER_ONLY')
        import resource
        budget = max(1, min(60000, int((self.cutoff - time.monotonic())*1000)))
        self.java_args = ['-Xms16m', '-Xmx256m', '-XX:ActiveProcessorCount=1', '-cp', CLASSPATH,
            MAIN, '--budget-millis', str(budget)]
        # Reserve intent before any create; no resource removal/recreation retry.
        self.folder.mkdir(mode=0o700)
        self.folder_created = True
        intent = encoded({'scope': 'ONE_NEW_DECODER_ONLY', 'project': self.project,
            'prepProofSha256': self.prepared['proofSha256'], 'originalAbsoluteCutoff': self.absolute,
            'decodeCutoff': self.cutoff, 'cleanupReserveSeconds': RESERVE, 'automaticRetry': False})
        with (self.folder / 'intent.json').open('xb') as out: out.write(intent); out.flush(); os.fsync(out.fileno())
        args = ['create', '--name', self.name, '--network=none', '--read-only', '--user=185:185',
            '--cpus=1', '--memory=512m', '--memory-swap=512m', '--pids-limit=64', '--cap-drop=ALL',
            '--security-opt=no-new-privileges:true', '--restart=no', '--entrypoint=java', '--interactive']
        for key, value in self.labels.items(): args += ['--label', key + '=' + value]
        for source, target in ((self.prepared['classes'], '/opt/decoder/classes'),
                (self.prepared['iceberg'], '/opt/decoder/iceberg-runtime.jar')):
            args += ['--mount', 'type=bind,src=' + str(source) + ',dst=' + target + ',readonly']
        args += [SPARK, *self.java_args]
        self.create_attempted = True
        created = command(args, self.cutoff)
        self.cid = created.stdout.removesuffix(b'\n').decode('ascii')
        require(re.fullmatch('[a-f0-9]{64}', self.cid), 'CREATED_DECODER_FULL_CID_REQUIRED')
        state = self.inspect()
        require(state['Running'] is False and type(state['Pid']) is int and state['Pid'] == 0
            and state['StartedAt'] == '0001-01-01T00:00:00Z',
            'BOUND_DECODER_NOT_PREVIOUSLY_STARTED')
        self.cold_observed = True
        thread = threading.Thread(target=self.watchdog, name='own-decoder-watchdog', daemon=False)
        error = None; final = None
        try:
            with (self.folder / 'reply.private').open('xb') as stdout, (self.folder / 'stderr.private').open('xb') as stderr:
                os.fchmod(stdout.fileno(), 0o600); os.fchmod(stderr.fileno(), 0o600)
                def limits(): resource.setrlimit(resource.RLIMIT_FSIZE, (MAX_REPLY, MAX_REPLY))
                require(time.monotonic() < self.cutoff and threading.active_count() == 1,
                    'DECODER_START_BEFORE_EXECUTION_CUTOFF_SINGLE_PYTHON_THREAD')
                self.start_attempted = True
                self.process = subprocess.Popen([*DOCKER, 'start', '--attach', '--interactive', self.cid],
                    stdin=subprocess.PIPE, stdout=stdout, stderr=subprocess.PIPE, preexec_fn=limits)
                drain = threading.Thread(target=self.drain_stderr, args=(self.process.stderr, stderr),
                    name='own-decoder-stderr-drain', daemon=False)
                thread.start()
                drain.start()
                try:
                    # No communicate(): stderr has exactly one bounded reader.
                    written = self.process.stdin.write(frame)
                    require(written == len(frame), 'WHOLE_DECODER_STDIN_FRAME_REQUIRED')
                    self.process.stdin.close()
                    self.process.wait(timeout=max(0.01, self.cutoff - time.monotonic()))
                    self.cli_reaped = self.process.poll() is not None
                finally:
                    if not self.process.stdin.closed:
                        try: self.process.stdin.close()
                        except OSError: pass
                    if self.process.poll() is None:
                        try: final = self.cleanup()
                        except BaseException: self.cleanup_failure = 'OWN_DECODER_STOP_OR_REAP_UNVERIFIED'
                    drain.join(timeout=max(0.01, min(5, self.absolute - time.monotonic())))
                    self.stderr_joined = not drain.is_alive()
                    if self.stderr_joined: self.process.stderr.close()
            final = self.cleanup()
        except BaseException as caught:
            error = caught
        finally:
            self.done.set(); self.wake.set()
            if thread.ident is not None: thread.join(timeout=max(0.01, min(10, self.absolute - time.monotonic())))
            if self.cid and not self.stopped:
                try: final = self.cleanup()
                except BaseException: self.cleanup_failure = 'OWN_DECODER_STOP_OR_REAP_UNVERIFIED'
        require(not thread.is_alive() and self.stopped and (self.process is None or self.cli_reaped) and self.cleanup_failure is None
            and time.monotonic() < self.absolute, 'OWN_DECODER_LIFECYCLE_UNRESOLVED')
        if error is not None: raise ValueError('DECODER_EXECUTION_FAILED_NO_RETRY') from None
        require(self.stderr_joined and not self.stderr_overflow and self.stderr_error is None
            and not self.watchdog_fired and final['OOMKilled'] is False
            and final['ExitCode'] in (0, 2, 3) and self.process.returncode == final['ExitCode'],
            'DECODER_NORMAL_OR_HANDLED_EXIT_REQUIRED')
        reply = read_proof(self.folder / 'reply.private', MAX_REPLY)
        require((self.folder / 'stderr.private').stat().st_size <= 65536, 'DECODER_PRIVATE_STDERR_BOUND')
        return {'reply': reply, 'exitCode': final['ExitCode'], 'cid': self.cid,
            'ownDecoderStopped': True, 'attachCliReaped': True, 'watchdogFired': False,
            'originalRoleStopCallsAdded': 0, 'originalInitializerStopCallsAdded': 0}
