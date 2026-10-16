"""Trusted fixed caller only; bounded Linux child streams, no CLI or workload."""
from contextlib import ExitStack
import hashlib
import json
import math
import os
from pathlib import Path
import re
import selectors
import stat
import subprocess
import time

MIB = 1024**2
MAX_ARCHIVE_STDOUT = 1024*MIB + 16*MIB
REAP_GRACE_SECONDS = 2


def require(value, code):
    if not value: raise ValueError(code)


def arguments(argv, name, cutoff, timeout, maximum_stdout, maximum_stderr,
        persist_stdout, stdout_filename):
    require(type(argv) is list and 0 < len(argv) <= 256
        and all(type(v) is str and 0 < len(v) <= 16384 and '\0' not in v for v in argv),
        'FIXED_ARGV_LIST_REQUIRED')
    raw = json.dumps(argv, ensure_ascii=True, separators=(',', ':')).encode('ascii')
    require(len(raw) <= 65536 and type(name) is str and re.fullmatch('[a-z][a-z0-9-]{0,63}', name),
        'BOUNDED_CALL_NAME_AND_ARGV_REQUIRED')
    require(type(cutoff) in (int, float) and math.isfinite(cutoff)
        and type(timeout) in (int, float) and math.isfinite(timeout) and 0 < timeout <= 600,
        'FINITE_PREP_CUTOFF_AND_TIMEOUT_REQUIRED')
    require(type(maximum_stdout) is int and 0 < maximum_stdout <= MAX_ARCHIVE_STDOUT
        and type(maximum_stderr) is int and 0 < maximum_stderr <= 65536
        and type(persist_stdout) is bool, 'EXPLICIT_BOUNDED_STREAM_LIMITS_REQUIRED')
    require(stdout_filename is None or persist_stdout and type(stdout_filename) is str
        and re.fullmatch('[a-z][a-z0-9.-]{0,127}', stdout_filename)
        and stdout_filename not in (name+'.intent.json', name+'.result.json', name+'.stderr.private'),
        'DIRECT_FRESH_ARCHIVE_FILENAME_REQUIRED')
    require(stdout_filename is not None or maximum_stdout <= MIB,
        'LARGE_STDOUT_MUST_STREAM_TO_ARCHIVE_FILE')
    return {'argvSha256': hashlib.sha256(raw).hexdigest(), 'argumentCount': len(argv)}


def execute(argv, folder, name, cutoff, timeout, *, maximum_stdout=MIB,
        maximum_stderr=65536, persist_stdout=True, stdout_filename=None):
    """No retries. Named archive stdout returns None; inspect stdout stays RAM."""
    metadata = arguments(argv, name, cutoff, timeout, maximum_stdout, maximum_stderr,
        persist_stdout, stdout_filename)
    require(os.name == 'posix', 'LINUX_SELECTORS_PIPE_EXECUTION_REQUIRED')
    folder = Path(folder)
    require(folder.is_absolute() and folder.resolve(strict=True) == folder and not folder.is_symlink(),
        'CANONICAL_EXISTING_PRIVATE_FOLDER_REQUIRED')
    info = folder.lstat()
    require(stat.S_ISDIR(info.st_mode) and info.st_uid == os.geteuid()
        and stat.S_IMODE(info.st_mode) == 0o700, 'OWN_PRIVATE_FOLDER_MODE700_REQUIRED')
    started = time.monotonic()
    deadline = min(cutoff, started + timeout)
    require(deadline > started, 'PREP_CHILD_DEADLINE_ALREADY_EXPIRED')
    stdout_path = stdout_filename or name+'.stdout.private'
    archive = stdout_filename is not None
    values = {'stdout': bytearray(), 'stderr': bytearray()}
    counts = {'stdout': 0, 'stderr': 0}
    observed = {'stdout': 0, 'stderr': 0}
    hashes = {'stdout': hashlib.sha256(), 'stderr': hashlib.sha256()}
    eof = {'stdout': False, 'stderr': False}
    limits = {'stdout': maximum_stdout, 'stderr': maximum_stderr}
    overflow = {'stdout': False, 'stderr': False}
    proc = None
    outcome = 'START_FAILED'
    returncode = None
    child_killed = child_reaped = timed_out = False
    error = None
    stream_io_error = False
    with ExitStack() as stack:
        directory = os.open(folder, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        stack.callback(os.close, directory)
        initial_dir = os.fstat(directory)
        require((initial_dir.st_dev, initial_dir.st_ino) == (info.st_dev, info.st_ino),
            'PRIVATE_FOLDER_IDENTITY_CHANGED')
        def reserve(filename):
            try:
                fd = os.open(filename, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                    0o600, dir_fd=directory)
            except FileExistsError:
                raise ValueError('PREP_PRIVATE_RECORD_ALREADY_EXISTS_NO_RETRY') from None
            try: os.fchmod(fd, 0o600)
            except BaseException:
                os.close(fd)
                raise
            return stack.enter_context(os.fdopen(fd, 'wb'))
        # Every authority/stdio destination is reserved before Popen. Existing
        # paths abort without touching them or starting a second child.
        intent_file = reserve(name+'.intent.json')
        result_file = reserve(name+'.result.json')
        stderr_file = reserve(name+'.stderr.private')
        stdout_file = reserve(stdout_path) if persist_stdout else None
        files = {'stdout': stdout_file, 'stderr': stderr_file}
        intent = {'schemaVersion': 1, 'scope': 'ONE_BOUNDED_PREP_CHILD_ONLY', 'name': name,
            **metadata, 'startedMonotonic': started, 'prepCutoffMonotonic': cutoff,
            'executionDeadlineMonotonic': deadline, 'timeoutSeconds': timeout,
            'maximumStdoutBytes': maximum_stdout, 'maximumStderrBytes': maximum_stderr,
            'stdoutPersisted': persist_stdout, 'stdoutArchiveStreamedWithoutRam': archive,
            'environmentSerialized': False, 'rawArgvSerialized': False, 'automaticRetry': False,
            'osMemoryLimitClaimed': False, 'reapGraceSeconds': REAP_GRACE_SECONDS}
        selector = selectors.DefaultSelector()
        stack.callback(selector.close)
        try:
            intent_file.write((json.dumps(intent, sort_keys=True, allow_nan=False)+'\n').encode())
            intent_file.flush(); os.fsync(intent_file.fileno())
            proc = subprocess.Popen(argv, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                stderr=subprocess.PIPE, close_fds=True, bufsize=0, shell=False)
            outcome = 'RUNNING'
            for label, stream in (('stdout', proc.stdout), ('stderr', proc.stderr)):
                os.set_blocking(stream.fileno(), False)
                selector.register(stream, selectors.EVENT_READ, label)
            while selector.get_map():
                left = deadline - time.monotonic()
                if left <= 0:
                    timed_out = True; outcome = 'TIMED_OUT'
                    raise ValueError('PREP_CHILD_TIMEOUT_NO_RETRY')
                for key, _ in selector.select(min(0.1, left)):
                    label = key.data
                    try:
                        chunk = os.read(key.fileobj.fileno(), min(65536, limits[label]-counts[label]+1))
                    except BlockingIOError:
                        continue
                    if not chunk:
                        eof[label] = True; selector.unregister(key.fileobj)
                        continue
                    observed[label] += len(chunk)
                    keep = chunk[:limits[label]-counts[label]]
                    if keep:
                        hashes[label].update(keep); counts[label] += len(keep)
                        if label != 'stdout' or not archive: values[label].extend(keep)
                        if files[label] is not None: files[label].write(keep)
                    if len(keep) != len(chunk):
                        overflow[label] = True
                        outcome = label.upper()+'_LIMIT_EXCEEDED'
                        raise ValueError('PREP_'+label.upper()+'_LIMIT_EXCEEDED_NO_RETRY')
            left = deadline - time.monotonic()
            if left <= 0:
                timed_out = True; outcome = 'TIMED_OUT'
                raise ValueError('PREP_CHILD_TIMEOUT_NO_RETRY')
            returncode = proc.wait(timeout=left)
            child_reaped = True
            outcome = 'EXITED_ZERO' if returncode == 0 else 'EXITED_NONZERO'
        except BaseException as caught:
            error = caught
            if isinstance(caught, OSError) and proc is not None: stream_io_error = True
            if isinstance(caught, subprocess.TimeoutExpired):
                timed_out = True; outcome = 'TIMED_OUT'
            elif outcome == 'RUNNING': outcome = 'OUTPUT_OR_CONTROL_IO_FAILED'
            if proc is not None:
                try:
                    if proc.poll() is None:
                        proc.kill(); child_killed = True
                    returncode = proc.wait(timeout=REAP_GRACE_SECONDS)
                    child_reaped = True
                except BaseException:
                    outcome = 'OWN_CHILD_REAP_UNVERIFIED'; child_reaped = False
        finally:
            if proc is not None:
                for stream in (proc.stdout, proc.stderr):
                    if stream is not None:
                        try: stream.close()
                        except OSError: stream_io_error = True
            for stream in (stdout_file, stderr_file):
                if stream is not None:
                    try: stream.flush(); os.fsync(stream.fileno())
                    except OSError: stream_io_error = True
            try: current_dir = folder.lstat()
            except OSError: current_dir = None
            if current_dir is None or (current_dir.st_dev, current_dir.st_ino) != (initial_dir.st_dev, initial_dir.st_ino):
                stream_io_error = True
            if stream_io_error: outcome = 'PRIVATE_OUTPUT_IO_UNVERIFIED'
            finished = time.monotonic()
            if finished >= cutoff and error is None:
                outcome = 'PREP_CUTOFF_EXCEEDED'; error = ValueError('PREP_ABSOLUTE_CUTOFF_EXCEEDED')
            receipt = {**intent, 'outcome': outcome, 'returnCode': returncode,
                'finishedMonotonic': finished, 'prepCutoffExceeded': finished >= cutoff,
                'childStarted': proc is not None,
                'childPid': None if proc is None else proc.pid, 'childKilled': child_killed,
                'childReaped': child_reaped, 'timedOut': timed_out,
                'stdoutBytes': counts['stdout'], 'stderrBytes': counts['stderr'],
                'stdoutObservedBytes': observed['stdout'], 'stderrObservedBytes': observed['stderr'],
                'stdoutSha256': hashes['stdout'].hexdigest(), 'stderrSha256': hashes['stderr'].hexdigest(),
                'stdoutEofObserved': eof['stdout'], 'stderrEofObserved': eof['stderr'],
                'stdoutOverflow': overflow['stdout'], 'stderrOverflow': overflow['stderr'],
                'hashesDescribeAcceptedReadPrefixes': True, 'outputPersistenceVerified': not stream_io_error,
                'dockerStopOrRemovalPerformed': False}
            try:
                result_file.write((json.dumps(receipt,sort_keys=True,allow_nan=False)+'\n').encode())
                result_file.flush();os.fsync(result_file.fileno())
            except OSError:
                raise ValueError('PRIVATE_PREP_FAILURE_RECEIPT_UNWRITABLE') from None
        if error is not None or stream_io_error:
            code = {'TIMED_OUT':'PREP_CHILD_TIMEOUT_NO_RETRY',
                'STDOUT_LIMIT_EXCEEDED':'PREP_STDOUT_LIMIT_EXCEEDED_NO_RETRY',
                'STDERR_LIMIT_EXCEEDED':'PREP_STDERR_LIMIT_EXCEEDED_NO_RETRY',
                'OWN_CHILD_REAP_UNVERIFIED':'OWN_PREP_CHILD_REAP_UNVERIFIED',
                'PREP_CUTOFF_EXCEEDED':'PREP_ABSOLUTE_CUTOFF_EXCEEDED',
                'START_FAILED':'PREP_CHILD_START_FAILED_NO_RETRY'}.get(outcome,'PREP_CHILD_IO_FAILED_NO_RETRY')
            raise ValueError(code) from None
        return {'returncode': returncode, 'stdout': None if archive else bytes(values['stdout']),
            'stderr': bytes(values['stderr']), 'receipt': receipt}
