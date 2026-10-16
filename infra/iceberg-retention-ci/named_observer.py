"""Named observations only. No CLI, workload start, SQL, network, or cleanup calls."""
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import re
import stat
import sys
import threading
import time
import types

PRODUCER_SHA = '73e2293210aba3d9522013d923f8d97bd292baa4623736239d55cc21d9321fe2'
RUNTIME_MANIFEST_SHA = 'c63aded0a891bb66cb1fb2de591d67e237467681eb4a4e5a337b9d1d1b02d5e8'
CHECKPOINTS = (('SPARK', 'jdbc-01-before-trino'),
               ('TRINO', 'jdbc-02-after-trino-selects'),
               ('FINAL_VERIFY', 'jdbc-03-final'))


def require(value, code):
    if not value:
        raise ValueError(code)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def stable(path, expected, maximum):
    before = path.lstat()
    require(path.is_absolute() and path.resolve(strict=True) == path and not path.is_symlink()
        and stat.S_ISREG(before.st_mode) and 0 < before.st_size <= maximum, 'REGULAR_PINNED_SOURCE_REQUIRED')
    flags = os.O_RDONLY | (os.O_NOFOLLOW if os.name == 'posix' else 0)
    with os.fdopen(os.open(path, flags), 'rb') as stream:
        first = os.fstat(stream.fileno()); raw = stream.read(maximum + 1); last = os.fstat(stream.fileno())
    after = path.lstat()
    identity = lambda info: (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns)
    require(identity(before) == identity(first) == identity(last) == identity(after)
        and before.st_ctime_ns == after.st_ctime_ns and first.st_ctime_ns == last.st_ctime_ns
        and len(raw) == before.st_size and sha(raw) == expected, 'SOURCE_WHOLE_SHA_OR_IDENTITY_CHANGED')
    return raw


def verified_functions(module):
    require(type(module) is types.ModuleType, 'LOADED_FROZEN_MODULE_REQUIRED')
    path = Path(module.__file__).absolute()
    require(path.name == 'run_trial9.py' and module.HERE == path.parent, 'EXACT_PRODUCER_PATH_REQUIRED')
    source = stable(path, PRODUCER_SHA, 65536)
    manifest = json.loads(stable(path.parent / 'runtime-manifest.json', RUNTIME_MANIFEST_SHA, 32768))
    require(set(manifest) == {'schemaVersion', 'scope', 'status', 'files', 'basePins'}
        and manifest['scope'] == 'FRESH_CLOUD_SPARK_TRINO_BRONZE_TWO_FILE_COMPACTION'
        and manifest['status'] == 'SOURCE_ONLY_NOT_RUN', 'EXACT_FROZEN_MANIFEST_REQUIRED')
    require({row['path'] for row in manifest['files']} == {'run_trial9.py', 'contract.py', 'compose_trial9.py',
        'frozen_s3_primitives.py', 'pinned_trino_configuration.py', 's3_readonly.py', 'bootstrap_trial9.py'}
        and len(manifest['files']) == 7, 'EXACT_SEVEN_RUNTIME_FILES_REQUIRED')
    for row in manifest['files']:
        require(len(stable(path.parent / row['path'], row['sha256'], 131072)) == row['bytes'], 'RUNTIME_SOURCE_BYTES_CHANGED')
    repo = path.parent.parents[1]
    for relative, digest in manifest['basePins'].items():
        stable(repo / relative, digest, 131072)
    compiled = compile(source, str(path), 'exec', optimize=sys.flags.optimize)
    expected = {code.co_name: code for code in compiled.co_consts if isinstance(code, types.CodeType)}
    originals = {}
    for name in ('make_attempt', 'jdbc', 'main'):
        function = getattr(module, name, None)
        require(type(function) is types.FunctionType and function.__globals__ is module.__dict__
            and function.__code__ == expected[name] and function.__defaults__ is None
            and function.__kwdefaults__ is None and function.__closure__ is None,
            'ORIGINAL_FROZEN_FUNCTION_BINDING_REQUIRED')
        originals[name] = function
    return originals


def save(path, value):
    raw = value if type(value) is bytes else (json.dumps(value, sort_keys=True, allow_nan=False, indent=2) + '\n').encode()
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | (os.O_NOFOLLOW if os.name == 'posix' else 0)
    with os.fdopen(os.open(path, flags, 0o600), 'wb') as stream:
        if os.name == 'posix': os.fchmod(stream.fileno(), 0o600)
        stream.write(raw); stream.flush(); os.fsync(stream.fileno())


def observed_time():
    return {'utc': datetime.now(timezone.utc).isoformat(), 'monotonicNs': time.monotonic_ns()}


class Observations:
    """Private RAM binding and counts; not a producer-pass or closure attestation."""
    def __init__(self, module, folder, source_commit, originals):
        self.module, self.folder, self.source_commit, self.originals = module, folder, source_commit, originals
        self.thread = threading.get_ident()
        self.make_started = self.make_completed = self.jdbc_started = self.jdbc_completed = 0
        self.attempt = self.deadline = self.deadline_started = self.deadline_now = None

    def same_thread(self):
        require(threading.get_ident() == self.thread, 'ONLY_ORIGINAL_SEQUENTIAL_CALL_THREAD')

    def make_attempt(self, *args, **kwargs):
        self.same_thread()
        require(self.make_started == 0, 'MAKE_ATTEMPT_ALREADY_OBSERVED_NO_RETRY')
        self.make_started = 1
        save(self.folder / 'make-attempt.intent.json', {'scope': 'NAMED_OBSERVATION_ONLY',
            'sourceCommit': self.source_commit, 'producerSha256': PRODUCER_SHA,
            'runtimeManifestSha256': RUNTIME_MANIFEST_SHA, 'before': observed_time()})
        # Actual main passes these four fixed arguments. Inspection does not
        # serialize base, image values, process environment, or credentials.
        names = ('base', 'root', 'project', 'images')
        require(len(args) <= 4 and set(kwargs).issubset(names), 'EXACT_MAKE_ATTEMPT_ARGUMENTS_REQUIRED')
        bound = dict(zip(names, args))
        require(not set(bound).intersection(kwargs), 'DUPLICATE_MAKE_ATTEMPT_ARGUMENTS')
        bound.update(kwargs)
        require(set(bound) == set(names) and type(bound['root']) is type(Path())
            and type(bound['project']) is str and re.fullmatch('cloud-trial9-[a-f0-9]{32}', bound['project']),
            'EXACT_MAKE_ATTEMPT_ARGUMENTS_REQUIRED')
        actual = self.originals['make_attempt'](*args, **kwargs)
        require(actual.root == bound['root'] and actual.project == bound['project'],
            'EXACT_RETURNED_ATTEMPT_BINDING_REQUIRED')
        self.attempt = actual
        self.make_completed = 1
        save(self.folder / 'make-attempt.binding.json', {'scope': 'NAMED_OBSERVATION_ONLY',
            'sourceCommit': self.source_commit, 'producerSha256': PRODUCER_SHA,
            'runtimeManifestSha256': RUNTIME_MANIFEST_SHA, 'attemptRoot': str(actual.root),
            'project': actual.project, 'after': observed_time(), 'returnObjectPreserved': True})
        return actual

    def jdbc(self, *args, **kwargs):
        self.same_thread()
        require(self.make_completed == 1 and self.jdbc_started == self.jdbc_completed
            and self.jdbc_started < 3, 'ONLY_THREE_ONCE_ONLY_JDBC_OBSERVATIONS')
        require((len(args) == 1 and not kwargs) or (not args and set(kwargs) == {'attempt'}),
            'EXACT_JDBC_ARGUMENT_REQUIRED')
        attempt = args[0] if args else kwargs['attempt']
        require(attempt is self.attempt, 'EXACT_SAME_ATTEMPT_OBJECT_REQUIRED')
        stage, stem = CHECKPOINTS[self.jdbc_started]
        require(attempt.command_stage == stage, 'EXACT_ORIGINAL_JDBC_STAGE_ORDER_REQUIRED')
        clock = attempt.deadline
        started = getattr(clock, 'started', None)
        now = getattr(clock, 'now', None)
        require(type(clock) is self.module.Deadline and now is time.monotonic
            and type(started) in (int, float) and math.isfinite(started)
            and started > 0, 'EXISTING_ORIGINAL_WORKLOAD_CLOCK_REQUIRED')
        if self.deadline is None:
            self.deadline, self.deadline_started, self.deadline_now = clock, started, now
        require(clock is self.deadline and started == self.deadline_started
            and now is self.deadline_now, 'ORIGINAL_CLOCK_CHANGED_NO_RESET')
        self.jdbc_started += 1
        before = observed_time()
        save(self.folder / (stem + '.intent.json'), {'scope': 'NAMED_JDBC_RETURN_BYTES_ONLY',
            'sequence': self.jdbc_started, 'stage': stage, 'before': before,
            'originalDeadlineStartedMonotonic': started, 'producerSha256': PRODUCER_SHA,
            'runtimeManifestSha256': RUNTIME_MANIFEST_SHA, 'sourceCommit': self.source_commit})
        raw = self.originals['jdbc'](*args, **kwargs)
        after = observed_time()
        require(type(raw) is bytes and 0 < len(raw) < 16384, 'BOUNDED_ORIGINAL_JDBC_BYTES_REQUIRED')
        require(after['monotonicNs'] >= before['monotonicNs'] and attempt.deadline is self.deadline
            and attempt.deadline.started == self.deadline_started and attempt.deadline.now is self.deadline_now,
            'ORIGINAL_CLOCK_CHANGED_DURING_DELEGATION')
        save(self.folder / (stem + '.raw'), raw)
        save(self.folder / (stem + '.checkpoint.json'), {'scope': 'NAMED_JDBC_RETURN_BYTES_ONLY',
            'sequence': self.jdbc_started, 'stage': stage, 'before': before, 'after': after,
            'rawBytes': len(raw), 'rawSha256': sha(raw), 'returnBytesPreserved': True,
            'originalDeadlineStartedMonotonic': started, 'producerSha256': PRODUCER_SHA,
            'runtimeManifestSha256': RUNTIME_MANIFEST_SHA, 'sourceCommit': self.source_commit})
        self.jdbc_completed += 1
        return raw


@contextmanager
def named_observer(module, output, expected_source_commit):
    """Caller invokes frozen main once inside; this adapter invokes no workload."""
    originals = verified_functions(module)
    require(type(expected_source_commit) is str and re.fullmatch('[a-f0-9]{40}', expected_source_commit)
        and os.environ.get('SOURCE_COMMIT') == os.environ.get('GITHUB_SHA') == expected_source_commit,
        'EXPLICIT_SAME_WORKFLOW_SOURCE_REQUIRED')
    output = Path(output).absolute()
    require(output.parent.resolve(strict=True) == output.parent and not output.parent.is_symlink()
        and output.parent.is_dir() and not os.path.lexists(output), 'FRESH_CANONICAL_OBSERVER_DIRECTORY_REQUIRED')
    if os.name == 'posix':
        require(not output.parent.stat().st_mode & 0o022, 'TRUSTED_OBSERVER_PARENT_REQUIRED')
    output.mkdir(mode=0o700)
    observations = Observations(module, output, expected_source_commit, originals)
    make_hook, jdbc_hook = observations.make_attempt, observations.jdbc
    module.make_attempt, module.jdbc = make_hook, jdbc_hook
    failure = None
    try:
        yield observations
    except BaseException as error:
        failure = error
        raise
    finally:
        drift = module.make_attempt is not make_hook or module.jdbc is not jdbc_hook
        module.make_attempt, module.jdbc = originals['make_attempt'], originals['jdbc']
        try:
            save(output / 'observer-result.json', {'scope': 'NAMED_RETURN_OBSERVATIONS_NOT_PRODUCER_SUCCESS',
                'sourceCommit': expected_source_commit, 'producerSha256': PRODUCER_SHA,
                'runtimeManifestSha256': RUNTIME_MANIFEST_SHA,
                'makeCallsStarted': observations.make_started, 'makeCallsCompleted': observations.make_completed,
                'jdbcCallsStarted': observations.jdbc_started, 'jdbcCallsCompleted': observations.jdbc_completed,
                'allThreeCheckpointsObserved': observations.make_completed == 1 and observations.jdbc_completed == 3,
                'contextExitedWithoutException': failure is None, 'hookDriftDetected': drift,
                'originalFunctionsRestored': module.make_attempt is originals['make_attempt'] and module.jdbc is originals['jdbc'],
                'producerRunPassedClaimed': False, 'writersQuiescentVerified': False,
                'tableClosureVerified': False, 'automaticRetry': False, 'extraSqlCallsAdded': 0})
        except Exception:
            if failure is None:
                raise ValueError('OBSERVER_RESULT_WRITE_FAILED_NO_RETRY') from None
        if drift and failure is None:
            raise ValueError('OBSERVER_HOOK_CHANGED_DURING_CONTEXT')
