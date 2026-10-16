"""One explicitly acknowledged source-pinned hosted Cloud capture; no import IO."""
import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import re
import stat
import subprocess
import sys
import types
import uuid

SCOPE = 'FRESH_CLOUD_ICEBERG_CLOSED_COPY_CAPTURE'
FILES = {
    'named_observer.py', 'copy_loader.py', 'normalize_graph.py', 'lifecycle.py',
    'decoder_lifecycle.py', 'composite_entry.py', 'archive_classes.py',
    'bounded_process.py', 'prep_decoder.py', 'run_capture.py',
    'src/org/apache/iceberg/ClosedCopyDecoder.java'}
EXTERNALS = {
    'infra/cloud-lakehouse-ci/run_trial9.py': '73e2293210aba3d9522013d923f8d97bd292baa4623736239d55cc21d9321fe2',
    'infra/cloud-lakehouse-ci/runtime-manifest.json': 'c63aded0a891bb66cb1fb2de591d67e237467681eb4a4e5a337b9d1d1b02d5e8',
    'infra/maintenance/iceberg_retention_plan.py': 'ec1ff5dc06d9da666d9ef1d32557937e36e0a63bc124f08ad6ed39edbf0224ae',
    'infra/spark-silver/artifact-lock.downloaded.json': '6ca247b283025189ecf36c67ae03fe9101b25a53fe7b62593725e076276e33e3',
    'docs/evidence/cloud-lakehouse/full-success.summary.json': '1271685e34712c96b7dacaf7e84e5f32ac52fb925875e262843002ee6ef3b78f'}
FROZEN_FILES = {'bootstrap_trial9.py', 'compose_trial9.py', 'contract.py',
    'frozen_s3_primitives.py', 'pinned_trino_configuration.py', 'run_trial9.py', 's3_readonly.py'}
BASE_FILES = {'infra/spark-ci/run_ci.py', 'infra/spark-ci/compose_plan.py',
    'infra/spark-ci/bootstrap_spark.py', 'infra/spark-silver/spark_silver.py',
    'infra/spark-silver/silver_contract.py', 'infra/spark-silver/artifact-lock.downloaded.json',
    'infra/spark-silver/synthetic-v1.ndjson', 'infra/spark-silver/Dockerfile.candidate'}
POLICY = {'schemaVersion': 1, 'maxInventoryAgeSeconds': 300,
    'minSnapshotAgeSeconds': 86400, 'minimumSnapshotsToKeep': 3}
REASONS = set(('FRAME_MAGIC FRAME_BOUND FRAME_EOF DESCRIPTOR_INVALID OBJECT_MAP_INVALID '
    'OBJECT_BYTES_MISMATCH METADATA_INVALID UNSUPPORTED_FORMAT UNSUPPORTED_METADATA_FEATURE '
    'UNSUPPORTED_CODEC UNSUPPORTED_SCHEMA UNSUPPORTED_ENTRY_CONTENT MISSING_APPROVED_CHILD '
    'FOREIGN_REFERENCE GRAPH_CONFLICT MISSING_SNAPSHOT_REFERENCE REFERENCE_CYCLE GRAPH_BOUND '
    'DECODER_INTERNAL DECODER_BUDGET_EXPIRED').split())


def require(value, code):
    if not value: raise ValueError(code)


def digest(raw): return hashlib.sha256(raw).hexdigest()


def encoded(value):
    return (json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False) + '\n').encode('ascii')


def strict(raw):
    def pairs(items):
        result = {}
        for key, value in items:
            require(key not in result, 'DUPLICATE_SOURCE_MANIFEST_FIELD')
            result[key] = value
        return result
    def finite(text):
        value = float(text); require(math.isfinite(value), 'FINITE_SOURCE_MANIFEST_NUMBER')
        return value
    return json.loads(raw.decode('utf-8'), object_pairs_hook=pairs, parse_float=finite,
        parse_constant=lambda _: require(False, 'FINITE_SOURCE_MANIFEST_NUMBER'))


def read(path, maximum=262144):
    path = Path(path)
    require(path.is_absolute() and path.parent.resolve(strict=True) == path.parent,
        'CANONICAL_SOURCE_PARENT_REQUIRED')
    first = path.lstat()
    require(stat.S_ISREG(first.st_mode) and first.st_nlink == 1 and 0 < first.st_size <= maximum,
        'BOUNDED_REGULAR_SINGLE_LINK_SOURCE_REQUIRED')
    with os.fdopen(os.open(path, os.O_RDONLY | (os.O_NOFOLLOW if os.name == 'posix' else 0)), 'rb') as stream:
        opened = os.fstat(stream.fileno()); raw = stream.read(maximum + 1); held = os.fstat(stream.fileno())
    last = path.lstat()
    identity = lambda value: (value.st_dev, value.st_ino, value.st_mode, value.st_nlink,
        value.st_size, value.st_mtime_ns, value.st_ctime_ns)
    require(identity(first) == identity(opened) == identity(held) == identity(last)
        and len(raw) == first.st_size, 'SOURCE_IDENTITY_CHANGED')
    return raw


def verified_rows(root, rows, expected):
    require(type(rows) is list and len(rows) == len(expected)
        and all(type(row) is dict and set(row) == {'path', 'bytes', 'sha256'} for row in rows)
        and [row['path'] for row in rows] == sorted(expected), 'EXACT_CANONICAL_SOURCE_ROWS_REQUIRED')
    result = {}
    for row in rows:
        require(type(row['bytes']) is int and 0 < row['bytes'] <= 262144
            and type(row['sha256']) is str and re.fullmatch('[a-f0-9]{64}', row['sha256']),
            'EXACT_SOURCE_LENGTH_AND_HASH_REQUIRED')
        raw = read(root / row['path'])
        require(len(raw) == row['bytes'] and digest(raw) == row['sha256'], 'REVIEWED_SOURCE_BYTES_CHANGED')
        result[row['path']] = raw
    return result


def reviewed_sources(repo, expected_manifest):
    """Verify every Python dependency before loading any project Python module."""
    require(type(expected_manifest) is str and re.fullmatch('[a-f0-9]{64}', expected_manifest),
        'EXPLICIT_CAPTURE_RUNTIME_MANIFEST_SHA')
    folder = repo / 'infra/iceberg-retention-ci'
    raw = read(folder / 'runtime-manifest.json')
    require(digest(raw) == expected_manifest, 'EXACT_REVIEWED_CAPTURE_MANIFEST')
    manifest = strict(raw)
    require(type(manifest) is dict and set(manifest) == {'schemaVersion', 'scope', 'status', 'files', 'immutableInputs'}
        and type(manifest['schemaVersion']) is int and manifest['schemaVersion'] == 1
        and manifest['scope'] == SCOPE and manifest['status'] == 'SOURCE_ONLY_NOT_RUN',
        'EXACT_CAPTURE_MANIFEST_SCOPE')
    sources = verified_rows(folder, manifest['files'], FILES)
    immutable = verified_rows(repo, manifest['immutableInputs'], set(EXTERNALS))
    require(all(digest(immutable[name]) == value for name, value in EXTERNALS.items()),
        'EXACT_UNMODIFIED_FROZEN_EXTERNALS')
    frozen = strict(immutable['infra/cloud-lakehouse-ci/runtime-manifest.json'])
    require(type(frozen) is dict and set(frozen) == {'schemaVersion', 'scope', 'status', 'files', 'basePins'}
        and type(frozen['schemaVersion']) is int and frozen['schemaVersion'] == 1
        and frozen['scope'] == 'FRESH_CLOUD_SPARK_TRINO_BRONZE_TWO_FILE_COMPACTION'
        and frozen['status'] == 'SOURCE_ONLY_NOT_RUN' and type(frozen['basePins']) is dict
        and set(frozen['basePins']) == BASE_FILES, 'EXACT_ORIGINAL_RUNTIME_INPUT_SHAPE')
    originals = verified_rows(repo / 'infra/cloud-lakehouse-ci', frozen['files'], FROZEN_FILES)
    for name, value in frozen['basePins'].items():
        require(type(value) is str and re.fullmatch('[a-f0-9]{64}', value)
            and digest(read(repo / name)) == value, 'FROZEN_TRANSITIVE_INPUT_BYTES_CHANGED')
    require(Path(__file__).resolve(strict=True) == folder / 'run_capture.py'
        and read(Path(__file__).absolute()) == sources['run_capture.py'], 'EXACT_CAPTURE_CALLER_SOURCE')
    return sources, originals


def load(name, path, raw):
    require(name not in sys.modules, 'NO_EXISTING_PROJECT_MODULE_BINDING')
    module = types.ModuleType(name)
    module.__file__ = str(path)
    module.__package__ = ''
    sys.modules[name] = module
    try: exec(compile(raw, str(path), 'exec'), module.__dict__)
    except BaseException:
        del sys.modules[name]
        raise
    return module


def modules(repo, sources, originals):
    folder, frozen = repo / 'infra/iceberg-retention-ci', repo / 'infra/cloud-lakehouse-ci'
    loaded = {}
    for name in ('lifecycle', 'named_observer', 'archive_classes', 'bounded_process',
            'copy_loader', 'normalize_graph', 'decoder_lifecycle', 'prep_decoder', 'composite_entry'):
        loaded[name] = load(name, folder / (name + '.py'), sources[name + '.py'])
    for name in ('contract', 'compose_trial9', 'pinned_trino_configuration'):
        load(name, frozen / (name + '.py'), originals[name + '.py'])
    loaded['producer'] = load('closed_copy_frozen_producer', frozen / 'run_trial9.py', originals['run_trial9.py'])
    return loaded


# Reviewed literal ValueError codes from the unchanged prep/archive/bounded sources.
REVIEWED_FAILURE_CODES = frozenset((
    'ACTUAL_DECODER_COMPILE_STDERR_ZERO_REQUIRED',
    'ACTUAL_HOST_COMPILER_JAVA21_REQUIRED',
    'ACTUAL_LOCKED_ICEBERG_SHA256_SHA512_REQUIRED',
    'ALL_COMPILER_SOURCE_CLASSPATH_INPUTS_UNCHANGED',
    'ARCHIVE_CHANGED_DURING_UNPACK',
    'ARCHIVE_OPEN_IDENTITY_CHANGED',
    'BOUNDED_CALL_NAME_AND_ARGV_REQUIRED',
    'BOUNDED_OWN_REGULAR_ARCHIVE_REQUIRED',
    'CANONICAL_EXISTING_PRIVATE_FOLDER_REQUIRED',
    'CANONICAL_EXPORTED_CLASSPATH_ORDER',
    'CANONICAL_PRIVATE_DIRECTORY_REQUIRED',
    'CLASSES_ROOT_CHANGED',
    'CLASS_DIRECTORY_CHANGED_DURING_TREE_READ',
    'CLASS_DIRECTORY_OPEN_CHANGED',
    'CLASS_FILE_OPEN_CHANGED',
    'CLASS_IDENTITY_CHANGED_AFTER_TREE_READ',
    'COLD_PREP_CONFIGURATION_CHANGED',
    'COMPILED_CLASS_CHANGED_DURING_READ',
    'COMPILED_CLASS_COUNT_BOUND',
    'COMPILED_CLASS_IO_FAILED',
    'COMPLETE_COMPILED_CLASS_BYTES_REQUIRED',
    'DECODER_CLASS_SHADOW_IN_SPARK_JAR',
    'DIRECT_FRESH_ARCHIVE_FILENAME_REQUIRED',
    'DUPLICATE_TAR_MEMBER_REJECTED',
    'EXACT_BOUND_NEVER_STARTED_PREP_CONTAINER',
    'EXACT_DECODER_MAIN_CLASS_REQUIRED',
    'EXACT_EXISTING_DOWNLOADED_ARTIFACT_LOCK',
    'EXACT_FAILED_PREP_COLD_REMOVE',
    'EXACT_NEW_READONLY_JAR_REQUIRED',
    'EXACT_PREP_EXECUTOR_SOURCE_REQUIRED',
    'EXACT_PREP_HELPER_SOURCE_REQUIRED',
    'EXACT_SINGLE_DECODER_JAVA_SOURCE',
    'EXPLICIT_BOUNDED_STREAM_LIMITS_REQUIRED',
    'EXPORTED_CLASSPATH_BYTES_CHANGED',
    'FAILED_PREP_COLD_ABSENCE_REQUIRED',
    'FINITE_PREP_CUTOFF_AND_TIMEOUT_REQUIRED',
    'FIXED_ARGV_LIST_REQUIRED',
    'FRESH_CANONICAL_PRIVATE_PREP_ROOT',
    'FRESH_EMPTY_PRIVATE_JAR_OUTPUT_REQUIRED',
    'JAR_CLASSPATH_ABSENCE_UNVERIFIED',
    'JAR_CLASSPATH_CASE_ALIAS_REJECTED',
    'JAR_CLASSPATH_TREE_CHANGED',
    'JAR_CLASSPATH_TREE_EXACT',
    'JAR_CLASSPATH_TREE_IO_FAILED',
    'JAR_CLASSPATH_TREE_REQUIRED',
    'JAR_COUNT_AND_TOTAL_BOUND',
    'JAR_MANIFEST_AGGREGATE_BYTES_BOUND',
    'JAR_MANIFEST_ATTRIBUTE_REQUIRED',
    'JAR_MANIFEST_BYTES_BOUND',
    'JAR_MANIFEST_CLASSPATH_CLOSURE_BOUND',
    'JAR_MANIFEST_CLASSPATH_EXPANSION_REJECTED',
    'JAR_MANIFEST_CLASSPATH_EXPORT_MAP_REQUIRED',
    'JAR_MANIFEST_CLASSPATH_REFERENCE_BOUND',
    'JAR_MANIFEST_CLASSPATH_TARGET_MISSING',
    'JAR_MANIFEST_CLASSPATH_TOKEN_REJECTED',
    'JAR_MANIFEST_CONTINUATION_REJECTED',
    'JAR_MANIFEST_DECLARED_EMPTY',
    'JAR_MANIFEST_DECLARED_SIZE_BOUND',
    'JAR_MANIFEST_DUPLICATE_ATTRIBUTE_REJECTED',
    'JAR_MANIFEST_READ_MISMATCH',
    'JAR_MANIFEST_UTF8_REQUIRED',
    'JAR_OUTPUT_ROOT_IDENTITY_CHANGED',
    'JAVA21_CLASS_HEADER_REQUIRED',
    'LARGE_STDOUT_MUST_STREAM_TO_ARCHIVE_FILE',
    'LINUX_PRIVATE_ARTIFACT_IO_REQUIRED',
    'LINUX_SELECTORS_PIPE_EXECUTION_REQUIRED',
    'NEW_CLASS_SEAL_FAILED',
    'NEW_JAR_CHANGED_DURING_ZIP_SCAN',
    'NEW_JAR_READBACK_BOUND',
    'NEW_JAR_READBACK_IDENTITY_CHANGED',
    'NEW_JAR_READBACK_WHOLE_SHA_CHANGED',
    'NONEMPTY_JARS_ROOT_REQUIRED',
    'NO_RUNNER_JAVA_OPTION_INJECTION',
    'ONE_EXACT_LOCKED_OFFICIAL_ICEBERG_ARTIFACT',
    'ONE_OWN_COLD_EXPORT_CONTAINER',
    'ONE_PINNED_PREP_IMAGE_REQUIRED',
    'ONE_UNAMBIGUOUS_JAR_MANIFEST_REQUIRED',
    'ONLY_BOUNDED_REGULAR_JAR_REQUIRED',
    'ONLY_EXACT_JARS_ROOT_REQUIRED',
    'ONLY_FRESH_PRIVATE_CLASSES_TARGET',
    'ONLY_LOCKED_RUNTIME_MAY_SUPPLY_ICEBERG_CLASSES',
    'ONLY_OWN_CLASS_PACKAGE_DIRECTORIES',
    'ONLY_OWN_SINGLE_LINK_JAVA21_CLASSES',
    'ONLY_UNIQUE_PAX_TIME_METADATA',
    'ONLY_USTAR_HEADER_REQUIRED',
    'OWNED_PRIVATE_DIRECTORY_REQUIRED',
    'OWN_COLD_EXPORT_ABSENCE_REQUIRED',
    'OWN_COLD_EXPORT_CLEANUP_UNVERIFIED_NO_RETRY',
    'OWN_COLD_EXPORT_REMOVE_RETURNED_EXACT_ID',
    'OWN_PREP_CHILD_REAP_UNVERIFIED',
    'OWN_PRIVATE_FOLDER_MODE700_REQUIRED',
    'PAX_EXACT_RECORD_LENGTH_REQUIRED',
    'PAX_TIME_METADATA_BOUND',
    'PREP_ABSOLUTE_CUTOFF_EXCEEDED',
    'PREP_ACTUAL_IMAGE_ENV_SHAPE',
    'PREP_ACTUAL_PINNED_IMAGE_WITHOUT_IMPLICIT_ACTORS',
    'PREP_BOUNDED_REGULAR_SINGLE_LINK_INPUT_REQUIRED',
    'PREP_BUDGET_AND_ORIGINAL_DISK_RESERVE',
    'PREP_CHILD_DEADLINE_ALREADY_EXPIRED',
    'PREP_CHILD_IO_FAILED_NO_RETRY',
    'PREP_CHILD_START_FAILED_NO_RETRY',
    'PREP_CHILD_TIMEOUT_NO_RETRY',
    'PREP_CREATED_FULL_CID_REQUIRED',
    'PREP_ENABLED_OOM_KILLER_REQUIRED',
    'PREP_FAILED_OR_UNKNOWN_NO_RETRY',
    'PREP_IMAGE_OPTION_INJECTION_REJECTED',
    'PREP_INPUT_IDENTITY_CHANGED',
    'PREP_KNOWN_CHILD_NONZERO_NO_RETRY',
    'PREP_ONLY_SAME_SOURCE_GITHUB_HOSTED_LINUX',
    'PREP_PRESERVE_EXISTING_EIGHT_GIB_RESERVE',
    'PREP_PRIVATE_RECORD_ALREADY_EXISTS_NO_RETRY',
    'PREP_STDERR_LIMIT_EXCEEDED_NO_RETRY',
    'PREP_STDOUT_LIMIT_EXCEEDED_NO_RETRY',
    'PREP_SUCCESS_NOT_OBSERVED',
    'PREP_WHOLE_INPUT_BOUND',
    'PRIVATE_DIRECTORY_IDENTITY_CHANGED',
    'PRIVATE_FOLDER_IDENTITY_CHANGED',
    'PRIVATE_JAR_IO_FAILED',
    'PRIVATE_PREP_FAILURE_RECEIPT_UNWRITABLE',
    'PRIVATE_PREP_ROOT_MODE',
    'SAME_EXISTING_SPARK_BASE_REFERENCE',
    'SEALED_CLASS_DIRECTORY_MODE_REQUIRED',
    'SEALED_CLASS_INVENTORY_READBACK',
    'SEALED_CLASS_WHOLE_BYTES_CHANGED',
    'STRICT_BOUNDED_JAR_MANIFEST_REQUIRED',
    'TAR_ASCII_NAME_REQUIRED',
    'TAR_BOUNDED_NAME_REQUIRED',
    'TAR_COMPLETE_BYTES_REQUIRED',
    'TAR_DIRECTORY_BOUND_REQUIRED',
    'TAR_HEADER_CHECKSUM_REQUIRED',
    'TAR_HEADER_COUNT_BOUND',
    'TAR_HIDDEN_TEXT_REJECTED',
    'TAR_LINK_TARGET_REJECTED',
    'TAR_OCTAL_FIELD_REQUIRED',
    'TAR_ONLY_DIRECTORY_OR_REGULAR_JAR',
    'TAR_PARENT_DIRECTORY_MUST_PRECEDE_CHILD',
    'TAR_SAFE_COMPONENTS_REQUIRED',
    'TAR_SAFE_RELATIVE_NAME_REQUIRED',
    'TAR_TRAILING_DATA_REJECTED',
    'TAR_TWO_ZERO_END_BLOCKS_REQUIRED',
    'TAR_ZERO_PADDING_REQUIRED',
    'VALID_BOUNDED_JAR_ZIP_REQUIRED',
    'ZIP_ENTRY_COUNT_BOUND',
    'ZIP_SAFE_ENTRY_NAME_REQUIRED',
))

NORMALIZATION_PHASE_CODES = frozenset((
    'NORMALIZE_AUTHORITY_UNVERIFIED',
    'NORMALIZE_DESCRIPTOR_UNVERIFIED',
    'NORMALIZE_DECODER_LIFECYCLE_UNVERIFIED',
    'NORMALIZE_PLANNER_SOURCE_UNVERIFIED',
    'NORMALIZE_REPLY_UNVERIFIED',
    'NORMALIZE_GRAPH_UNVERIFIED',
    'NORMALIZE_EXIT_BINDING_UNVERIFIED',
    'NORMALIZE_CLOCK_UNVERIFIED',
    'NORMALIZE_INVENTORY_UNVERIFIED',
    'NORMALIZE_PLAN_UNVERIFIED',
    'NORMALIZE_RESULT_UNVERIFIED',
))


PREP_CHILD_CLASSES = {
    'compiler-java-version': 'JAVA_VERSION',
    'compiler-javac-version': 'JAVAC_VERSION',
    'pinned-image-pull': 'IMAGE_PULL',
    'pinned-image-inspect': 'IMAGE_INSPECT',
    'cold-export-create': 'COLD_CREATE',
    'cold-export-before': 'COLD_INSPECT',
    'export-classpath': 'CLASSPATH_EXPORT',
    'cold-export-after': 'COLD_INSPECT',
    'locked-iceberg-download': 'ICEBERG_DOWNLOAD',
    'compile-main-only': 'MAIN_COMPILE',
    'cold-export-before-remove': 'COLD_INSPECT',
    'cold-export-remove': 'COLD_REMOVE',
    'cold-export-absence': 'COLD_ABSENCE',
    'failed-prep-cold-before-remove': 'COLD_INSPECT',
    'failed-prep-cold-remove': 'COLD_REMOVE',
    'failed-prep-cold-absence': 'COLD_ABSENCE',
}
PREP_OUTCOMES = frozenset(('START_FAILED EXITED_ZERO EXITED_NONZERO TIMED_OUT '
    'STDOUT_LIMIT_EXCEEDED STDERR_LIMIT_EXCEEDED OWN_CHILD_REAP_UNVERIFIED '
    'OUTPUT_OR_CONTROL_IO_FAILED PRIVATE_OUTPUT_IO_UNVERIFIED PREP_CUTOFF_EXCEEDED').split())
COMPOSITE_STAGES = frozenset(('PREP ORIGINAL_MAIN PRODUCER_PROOFS WRITERS_BEFORE '
    'LOAD_CLOSED_COPIES DECODER WRITERS_AFTER NORMALIZE COMPLETED').split())
PREP_INTENT_KEYS = frozenset(('scope sourceCommit prepExecutorSha256 decoderSourceSha256 '
    'artifactLockSha256 budgetSeconds cleanupReserveSeconds originalWorkloadStarted automaticRetry').split())
PREP_RESULT_KEYS = frozenset(('scope sourceCommit passed failureCode knownColdCid coldIdentityBound '
    'coldRemovalAttempted coldRemovedAndAbsent originalWorkloadStarted automaticRetry').split())
PREP_CHILD_KEYS = frozenset(('schemaVersion scope name argvSha256 argumentCount startedMonotonic '
    'prepCutoffMonotonic executionDeadlineMonotonic timeoutSeconds maximumStdoutBytes maximumStderrBytes '
    'stdoutPersisted stdoutArchiveStreamedWithoutRam environmentSerialized rawArgvSerialized automaticRetry '
    'osMemoryLimitClaimed reapGraceSeconds outcome returnCode finishedMonotonic prepCutoffExceeded childStarted '
    'childPid childKilled childReaped timedOut stdoutBytes stderrBytes stdoutObservedBytes stderrObservedBytes '
    'stdoutSha256 stderrSha256 stdoutEofObserved stderrEofObserved stdoutOverflow stderrOverflow '
    'hashesDescribeAcceptedReadPrefixes outputPersistenceVerified dockerStopOrRemovalPerformed').split())
COMPOSITE_RESULT_KEYS = frozenset(('scope sourceCommit authoritySourceSha256 mainCallsStarted '
    'mainReturnedZero lastStage inventoryProduced failureCode safeNormalizationFailureCode pipelineFinishedWithoutException '
    'decoderCreatedKnownCid decoderStoppedVerified decoderAttachCliReaped originalRoleStopCallsAdded '
    'originalInitializerStopCallsAdded automaticRetry snapshotExpirationOrGcPerformed publicCompletenessClaimed').split())


def diagnostic_require(value):
    if not value: raise ValueError('INVALID_PRIVATE_DIAGNOSTIC_RECORD')


def literal_failure(error):
    # Do not stringify provider exceptions, even if their message looks uppercase.
    if type(error) is ValueError and len(error.args) == 1 and type(error.args[0]) is str:
        if error.args[0] in REVIEWED_FAILURE_CODES: return error.args[0]
    return 'UNKNOWN'


def empty_diagnostic(stage, failed):
    return {'stageAttempted': stage, 'failureCode': 'UNKNOWN' if failed else None,
        'lastPrepChild': None, 'prepCleanup': None}


def _diagnostic_identity(value):
    return (value.st_dev, value.st_ino, value.st_mode, value.st_uid, value.st_nlink,
        value.st_size, value.st_mtime_ns, value.st_ctime_ns)


def _read_prep_records(root, local):
    """Read only this caller's new private directory and fixed metadata filenames."""
    diagnostic_require(os.name == 'posix')
    root, local = Path(root), Path(local)
    diagnostic_require(root.is_absolute() and local.is_absolute() and root.parent == local
        and local.name == '.local' and re.fullmatch('closed-copy-prep-[a-f0-9]{32}', root.name)
        and root.resolve(strict=True) == root and local.resolve(strict=True) == local)
    parent_before, before = local.lstat(), root.lstat()
    for value in (parent_before, before):
        diagnostic_require(stat.S_ISDIR(value.st_mode) and value.st_uid == os.geteuid()
            and stat.S_IMODE(value.st_mode) == 0o700)
    parent_fd = directory_fd = None
    try:
        parent_fd = os.open(local, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        diagnostic_require(_diagnostic_identity(os.fstat(parent_fd)) == _diagnostic_identity(parent_before))
        directory_fd = os.open(root.name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent_fd)
        diagnostic_require(_diagnostic_identity(os.fstat(directory_fd)) == _diagnostic_identity(before))
        def read_record(name):
            try: first = os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
            except FileNotFoundError: return None
            diagnostic_require(stat.S_ISREG(first.st_mode) and first.st_uid == os.geteuid()
                and first.st_nlink == 1 and stat.S_IMODE(first.st_mode) == 0o600
                and 0 < first.st_size <= 16384)
            with os.fdopen(os.open(name, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=directory_fd), 'rb') as stream:
                opened = os.fstat(stream.fileno()); raw = stream.read(16385); held = os.fstat(stream.fileno())
            after = os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
            diagnostic_require(_diagnostic_identity(first) == _diagnostic_identity(opened)
                == _diagnostic_identity(held) == _diagnostic_identity(after) and len(raw) == first.st_size)
            return strict(raw)
        records = {name: read_record(name) for name in ('intent.json', 'prep-result.private.json')}
        records.update({name+'.result.json': read_record(name+'.result.json') for name in PREP_CHILD_CLASSES})
        diagnostic_require(_diagnostic_identity(before) == _diagnostic_identity(os.fstat(directory_fd))
            == _diagnostic_identity(root.lstat())
            and _diagnostic_identity(parent_before) == _diagnostic_identity(os.fstat(parent_fd))
            == _diagnostic_identity(local.lstat()))
        return records
    finally:
        if directory_fd is not None: os.close(directory_fd)
        if parent_fd is not None: os.close(parent_fd)


def _prep_child(value, name):
    diagnostic_require(type(value) is dict and set(value) == PREP_CHILD_KEYS
        and type(value['schemaVersion']) is int and value['schemaVersion'] == 1
        and value['scope'] == 'ONE_BOUNDED_PREP_CHILD_ONLY' and value['name'] == name
        and name in PREP_CHILD_CLASSES and value['outcome'] in PREP_OUTCOMES)
    for field in ('argvSha256', 'stdoutSha256', 'stderrSha256'):
        diagnostic_require(type(value[field]) is str and re.fullmatch('[a-f0-9]{64}', value[field]))
    diagnostic_require(type(value['argumentCount']) is int and 1 <= value['argumentCount'] <= 256)
    for field in ('startedMonotonic', 'prepCutoffMonotonic', 'executionDeadlineMonotonic',
            'timeoutSeconds', 'finishedMonotonic'):
        diagnostic_require(type(value[field]) in (int, float) and math.isfinite(value[field])
            and value[field] >= 0)
    diagnostic_require(value['startedMonotonic'] <= value['finishedMonotonic']
        and value['startedMonotonic'] < value['executionDeadlineMonotonic'] <= value['prepCutoffMonotonic']
        and 0 < value['timeoutSeconds'] <= 600)
    for stream, maximum in (('stdout', 1040*1024**2), ('stderr', 65536)):
        limit = value['maximum'+stream.title()+'Bytes']
        diagnostic_require(type(limit) is int and 0 < limit <= maximum
            and type(value[stream+'Bytes']) is int and 0 <= value[stream+'Bytes'] <= limit
            and type(value[stream+'ObservedBytes']) is int
            and value[stream+'Bytes'] <= value[stream+'ObservedBytes'] <= limit+1)
    bools = ('stdoutPersisted stdoutArchiveStreamedWithoutRam environmentSerialized rawArgvSerialized '
        'automaticRetry osMemoryLimitClaimed prepCutoffExceeded childStarted childKilled childReaped timedOut '
        'stdoutEofObserved stderrEofObserved stdoutOverflow stderrOverflow hashesDescribeAcceptedReadPrefixes '
        'outputPersistenceVerified dockerStopOrRemovalPerformed').split()
    diagnostic_require(all(type(value[field]) is bool for field in bools)
        and all(value[field] is False for field in ('environmentSerialized', 'rawArgvSerialized',
            'automaticRetry', 'osMemoryLimitClaimed', 'dockerStopOrRemovalPerformed'))
        and value['hashesDescribeAcceptedReadPrefixes'] is True
        and type(value['reapGraceSeconds']) is int and value['reapGraceSeconds'] == 2)
    diagnostic_require(value['returnCode'] is None or type(value['returnCode']) is int
        and -128 <= value['returnCode'] <= 255)
    diagnostic_require(value['childPid'] is None or type(value['childPid']) is int and value['childPid'] > 0)
    diagnostic_require(value['childStarted'] == (value['childPid'] is not None)
        and (not value['childReaped'] or value['childStarted'] and value['returnCode'] is not None)
        and (not value['childKilled'] or value['childStarted'])
        and (value['outcome'] != 'TIMED_OUT' or value['timedOut'])
        and (value['outcome'] not in ('EXITED_ZERO', 'EXITED_NONZERO') or value['childStarted']
            and value['childReaped'] and not value['timedOut'] and value['returnCode'] is not None)
        and (value['outcome'] != 'EXITED_ZERO' or value['returnCode'] == 0)
        and (value['outcome'] != 'EXITED_NONZERO' or value['returnCode'] != 0))
    return {'name': name, 'class': PREP_CHILD_CLASSES[name], 'outcome': value['outcome'],
        'returnCode': value['returnCode'], 'stdoutBytes': value['stdoutBytes'],
        'stderrBytes': value['stderrBytes'], 'timedOut': value['timedOut'],
        'childStarted': value['childStarted'], 'childReaped': value['childReaped']}


def _project_prep_records(records, source, prep_sha, decoder_sha):
    """Only typed aggregate projections escape; private hashes are validation inputs."""
    try:
        intent = records['intent.json']
        diagnostic_require(type(intent) is dict and set(intent) == PREP_INTENT_KEYS
            and intent == {'scope': 'SEPARATE_BOUNDED_COMPILER_PREPARATION_ONLY',
                'sourceCommit': source, 'prepExecutorSha256': prep_sha, 'decoderSourceSha256': decoder_sha,
                'artifactLockSha256': EXTERNALS['infra/spark-silver/artifact-lock.downloaded.json'],
                'budgetSeconds': 600, 'cleanupReserveSeconds': 40,
                'originalWorkloadStarted': False, 'automaticRetry': False}
            and type(intent['budgetSeconds']) is int and type(intent['cleanupReserveSeconds']) is int
            and type(intent['originalWorkloadStarted']) is bool and type(intent['automaticRetry']) is bool)
    except BaseException: return None, None
    cleanup = None
    try:
        value = records['prep-result.private.json']
        diagnostic_require(type(value) is dict and set(value) == PREP_RESULT_KEYS
            and value['scope'] == 'SEPARATE_PREP_ACTUAL_OUTCOME_NOT_RUNTIME_CLOSURE'
            and value['sourceCommit'] == source
            and all(type(value[k]) is bool for k in ('passed', 'knownColdCid', 'coldIdentityBound',
                'coldRemovalAttempted', 'coldRemovedAndAbsent', 'originalWorkloadStarted', 'automaticRetry'))
            and value['originalWorkloadStarted'] is False and value['automaticRetry'] is False
            and (value['failureCode'] is None or type(value['failureCode']) is str
                and len(value['failureCode']) <= 128)
            and (not value['coldIdentityBound'] or value['knownColdCid'])
            and (not value['coldRemovalAttempted'] or value['coldIdentityBound'])
            and (not value['coldRemovedAndAbsent'] or value['coldRemovalAttempted'])
            and (not value['passed'] or value['failureCode'] is None and value['coldRemovedAndAbsent']))
        cleanup = {field: value[field] for field in ('knownColdCid', 'coldIdentityBound',
            'coldRemovalAttempted', 'coldRemovedAndAbsent')}
    except BaseException: pass
    try:
        children = []
        for name in PREP_CHILD_CLASSES:
            value = records.get(name+'.result.json')
            if value is not None: children.append((value['startedMonotonic'], _prep_child(value, name)))
        if not children: return None, cleanup
        latest = max(row[0] for row in children)
        selected = [row[1] for row in children if row[0] == latest]
        diagnostic_require(len(selected) == 1)
        return selected[0], cleanup
    except BaseException: return None, cleanup


def capture_diagnostic(stage, passed, error, outcome, root, local, source, pins):
    value = empty_diagnostic(stage, not passed)
    if error is not None: value['failureCode'] = literal_failure(error)
    # Ignore the old private failureCode, which can originate from a provider.
    # Exact shape/source validation admits only the fixed stage and the new
    # source-owned finite normalization phase, never an original error message.
    try:
        receipt = outcome['receipt']
        diagnostic_require(type(receipt) is dict and set(receipt) == COMPOSITE_RESULT_KEYS
            and receipt['scope'] == 'COMPOSITE_SOURCE_BOUND_PIPELINE_NOT_PUBLIC_COMPLETENESS'
            and receipt['sourceCommit'] == source
            and receipt['authoritySourceSha256'] == pins['composite_entry.py']
            and receipt['lastStage'] in COMPOSITE_STAGES
            and type(receipt['mainCallsStarted']) is int and receipt['mainCallsStarted'] in (0, 1)
            and all(type(receipt[k]) is bool for k in ('mainReturnedZero', 'inventoryProduced',
                'pipelineFinishedWithoutException', 'decoderCreatedKnownCid', 'decoderStoppedVerified',
                'decoderAttachCliReaped', 'automaticRetry', 'snapshotExpirationOrGcPerformed',
                'publicCompletenessClaimed'))
            and all(type(receipt[k]) is int and receipt[k] == 0
                for k in ('originalRoleStopCallsAdded', 'originalInitializerStopCallsAdded'))
            and all(receipt[k] is False for k in ('automaticRetry', 'snapshotExpirationOrGcPerformed',
                'publicCompletenessClaimed'))
            and (receipt['failureCode'] is None or type(receipt['failureCode']) is str
                and len(receipt['failureCode']) <= 128)
            and type(receipt['safeNormalizationFailureCode']) is str
            and (receipt['safeNormalizationFailureCode'] == 'UNKNOWN'
                or (not passed and receipt['lastStage'] == 'NORMALIZE'
                    and receipt['pipelineFinishedWithoutException'] is False
                    and receipt['safeNormalizationFailureCode'] in NORMALIZATION_PHASE_CODES)))
        value['stageAttempted'] = receipt['lastStage']
        if (error is None and not passed and receipt['lastStage'] == 'NORMALIZE'
                and receipt['safeNormalizationFailureCode'] in NORMALIZATION_PHASE_CODES):
            value['failureCode'] = receipt['safeNormalizationFailureCode']
    except BaseException: pass
    try:
        records = _read_prep_records(root, local)
        child, cleanup = _project_prep_records(records, source, pins['prep_decoder.py'],
            pins['src/org/apache/iceberg/ClosedCopyDecoder.java'])
        value['lastPrepChild'], value['prepCleanup'] = child, cleanup
    except BaseException: pass
    return value


def safe_summary(source, manifest_sha, *, prepared=None, outcome=None, stage='PREP'):
    """Construct allowlisted aggregate fields; never echo arbitrary proof values."""
    require(re.fullmatch('[a-f0-9]{40}', source) and re.fullmatch('[a-f0-9]{64}', manifest_sha),
        'PUBLIC_SOURCE_PINS_REQUIRED')
    require(stage in ('PREP', 'COMPOSITE', 'SUMMARY'), 'FIXED_PUBLIC_STAGE_REQUIRED')
    receipt, normalized = {}, None
    if outcome is not None:
        require(type(outcome) is dict and set(outcome) == {'result', 'receipt', 'exitCode'}, 'EXACT_COMPOSITE_RETURN')
        receipt, normalized = outcome['receipt'], outcome['result']
        require(type(receipt) is dict and type(outcome['exitCode']) is int and outcome['exitCode'] in (0, 1),
            'EXACT_COMPOSITE_OUTCOME_TYPES')
    checks = {'sourceBytesVerified': True, 'compilerPrepVerified': prepared is not None,
        'originalMainCalledOnce': type(receipt.get('mainCallsStarted')) is int and receipt['mainCallsStarted'] == 1,
        'originalMainReturnedZero': receipt.get('mainReturnedZero') is True,
        'decoderStoppedVerified': receipt.get('decoderStoppedVerified') is True,
        'decoderAttachCliReaped': receipt.get('decoderAttachCliReaped') is True,
        'sameRunStoppedActorsAndClockVerified': False, 'inventoryProduced': False, 'allObjectsKept': False}
    counts = {'capturedObjectCount': None, 'snapshotCount': None, 'refCount': None,
        'validationPinCount': None, 'snapshotCandidateCount': None, 'objectCandidateCount': 0}
    hashes = {'prepProofSha256': None, 'normalizationReceiptCanonicalSha256': None}
    if prepared is not None:
        proof = prepared['proof']
        require(type(proof) is dict and type(proof['raw']) is bytes
            and digest(proof['raw']) == proof['sha256'] and re.fullmatch('[a-f0-9]{64}', proof['sha256']),
            'ACTUAL_PREP_WHOLE_PROOF_REQUIRED')
        hashes['prepProofSha256'] = proof['sha256']
    reasons, status = [], 'FAILED'
    if normalized is not None:
        require(type(normalized) is dict and set(normalized) == {'inventory', 'plan', 'privateReceipt'},
            'EXACT_NORMALIZATION_RETURN')
        private = normalized['privateReceipt']
        require(type(private) is dict and private['decoderStatus'] in ('DECODED', 'UNDETERMINED', 'REJECTED')
            and type(private['decoderReasonCodes']) is list and len(private['decoderReasonCodes']) <= 16
            and all(type(code) is str and code in REASONS for code in private['decoderReasonCodes'])
            and len(set(private['decoderReasonCodes'])) == len(private['decoderReasonCodes'])
            and private['objectCandidateCount'] == 0 and type(private['objectCandidateCount']) is int
            and private['applyEnabled'] is False, 'SAFE_NORMALIZATION_BOUNDARY_REQUIRED')
        objects = private['allCapturedObjects']
        require(type(objects) is list and 0 < len(objects) <= 128
            and all(type(row) is dict and row.get('action') == 'KEEP' for row in objects),
            'ALL_CAPTURED_OBJECTS_KEPT_REQUIRED')
        counts['capturedObjectCount'] = len(objects)
        hashes['normalizationReceiptCanonicalSha256'] = digest(encoded(private))
        reasons = list(private['decoderReasonCodes'])
        checks['sameRunStoppedActorsAndClockVerified'] = True
        checks['allObjectsKept'] = True
        status = 'UNDETERMINED'
        inventory, plan = normalized['inventory'], normalized['plan']
        require((inventory is None) == (plan is None), 'NO_PARTIAL_INVENTORY_PUBLIC_CLAIM')
        if inventory is not None:
            require(type(inventory) is dict and type(plan) is dict and plan['status'] in ('DETERMINED', 'UNDETERMINED')
                and plan['applyEnabled'] is False and type(plan['objectCandidateCount']) is int
                and plan['objectCandidateCount'] == 0 and type(plan['snapshotCandidateCount']) is int
                and 0 <= plan['snapshotCandidateCount'] <= 10000,
                'SAFE_PURE_PLAN_REQUIRED')
            for field, key in (('snapshotCount', 'snapshots'), ('refCount', 'refs'), ('validationPinCount', 'pins')):
                require(type(inventory[key]) is list and len(inventory[key]) <= 10000, 'BOUNDED_PUBLIC_INVENTORY_COUNT')
                counts[field] = len(inventory[key])
            require(type(plan['files']) is list and len(plan['files']) <= 10000
                and all(type(row) is dict and row.get('action') == 'KEEP' for row in plan['files']),
                'ALL_PLAN_OBJECTS_KEPT_REQUIRED')
            counts['snapshotCandidateCount'] = plan['snapshotCandidateCount']
            checks['inventoryProduced'] = True
            status = plan['status']
    passed = status == 'DETERMINED' and all(checks.values()) and outcome is not None
    passed = passed and outcome['exitCode'] == 0 and receipt.get('pipelineFinishedWithoutException') is True
    if not passed and status == 'DETERMINED': status = 'FAILED'
    failure = None if passed else ('CAPTURE_UNDETERMINED' if status == 'UNDETERMINED'
        else {'PREP': 'PREP_NOT_VERIFIED', 'COMPOSITE': 'COMPOSITE_NOT_VERIFIED', 'SUMMARY': 'SUMMARY_NOT_VERIFIED'}[stage])
    return {'schemaVersion': 2, 'scope': SCOPE, 'sourceCommit': source,
        'runtimeManifestSha256': manifest_sha, 'passed': bool(passed), 'status': status,
        'failureCategory': failure, 'diagnostic': empty_diagnostic(stage, not passed),
        'checks': checks, 'counts': counts, 'proofHashes': hashes,
        'decoderReasonCodes': reasons, 'policy': dict(POLICY),
        'originalWorkloadBudgetSeconds': 600, 'separatePrepBudgetSeconds': 600,
        'cleanupReserveSeconds': 40, 'snapshotExpirationPerformed': False,
        'objectDeletionPerformed': False, 'miniPcContacted': False,
        'liveTableIndependentlyVerified': False, 'parquetContentsDecoded': False,
        'historicalMetadataRestored': False, 'rawProofsOrCredentialsUploaded': False,
        'automaticRetryPerformed': False}


def write_summary(folder, value):
    raw = encoded(value)
    require(len(raw) <= 16384, 'BOUNDED_PUBLIC_CAPTURE_SUMMARY')
    with os.fdopen(os.open(folder / 'summary.json', os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600), 'wb') as stream:
        stream.write(raw); stream.flush(); os.fsync(stream.fileno())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-manifest-sha256', required=True)
    parser.add_argument('--ack-fresh-closed-copy-capture', action='store_true', required=True)
    args = parser.parse_args()
    require(sys.platform == 'linux' and os.environ.get('GITHUB_ACTIONS') == 'true'
        and os.environ.get('RUNNER_ENVIRONMENT') == 'github-hosted'
        and os.environ.get('GITHUB_RUN_ATTEMPT') == '1', 'FIRST_ATTEMPT_GITHUB_HOSTED_LINUX_ONLY')
    source = os.environ.get('SOURCE_COMMIT', '')
    require(re.fullmatch('[a-f0-9]{40}', source) and source == os.environ.get('GITHUB_SHA'), 'SAME_WORKFLOW_SOURCE_REQUIRED')
    repo = Path(__file__).resolve(strict=True).parents[2]
    sources, originals = reviewed_sources(repo, args.source_manifest_sha256)
    head = subprocess.run(['git', '-C', str(repo), 'rev-parse', 'HEAD'], stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=5)
    require(head.returncode == 0 and len(head.stdout) <= 128 and len(head.stderr) <= 1024
        and head.stdout == (source + '\n').encode('ascii'), 'ACTUAL_CAPTURE_CHECKOUT_SOURCE')
    loaded = modules(repo, sources, originals)
    os.umask(0o077)
    local = repo / '.local'
    local.mkdir(mode=0o700, exist_ok=True)
    info = local.lstat()
    require(local.resolve(strict=True) == local and stat.S_ISDIR(info.st_mode)
        and info.st_uid == os.getuid() and stat.S_IMODE(info.st_mode) == 0o700,
        'CANONICAL_OWN_PRIVATE_LOCAL_DIRECTORY')
    public = local / 'iceberg-closed-copy-public'
    require(not os.path.lexists(public) and not os.path.lexists(local / 'cloud-trial9-public'), 'FRESH_PUBLIC_OUTPUTS_NO_RETRY')
    public.mkdir(mode=0o700)
    nonce = uuid.uuid4().hex
    prepared = outcome = None
    stage = 'PREP'
    first_error = None
    prep_root = local / ('closed-copy-prep-' + nonce)
    pins = {name: digest(raw) for name, raw in sources.items()}
    java_sha = pins['src/org/apache/iceberg/ClosedCopyDecoder.java']
    try:
        prepared = loaded['prep_decoder'].prepare(repo, prep_root, source,
            java_sha, pins['prep_decoder.py'], {name: pins[name] for name in ('archive_classes.py', 'bounded_process.py')})
        stage = 'COMPOSITE'
        previous = sys.argv
        try:
            sys.argv = [str(repo / 'infra/cloud-lakehouse-ci/run_trial9.py'),
                '--source-manifest-sha256', EXTERNALS['infra/cloud-lakehouse-ci/runtime-manifest.json'], '--ack-fresh-cloud-trial9']
            outcome = loaded['composite_entry'].run(loaded['producer'], loaded['named_observer'],
                loaded['copy_loader'], loaded['normalize_graph'], source_commit=source,
                output=local / ('closed-copy-capture-' + nonce), authority_source_sha256=pins['composite_entry.py'],
                component_source_pins=pins, prep_proof=prepared['proof'], prep_sha256=prepared['proof']['sha256'],
                decoder_source_sha256=java_sha, classes=prepared['classes'], iceberg=prepared['iceberg'], policy=dict(POLICY))
        finally: sys.argv = previous
        stage = 'SUMMARY'
        summary = safe_summary(source, args.source_manifest_sha256, prepared=prepared, outcome=outcome, stage=stage)
    except BaseException as error:
        first_error = error
        # Raw exceptions, args, paths, graph IDs and private provider streams never leave the runner.
        summary = safe_summary(source, args.source_manifest_sha256, stage=stage)
    summary['diagnostic'] = capture_diagnostic(stage, summary['passed'], first_error, outcome,
        prep_root, local, source, pins)
    write_summary(public, summary)
    print(json.dumps({'scope': SCOPE, 'passed': summary['passed'], 'status': summary['status']}))
    return 0 if summary['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
