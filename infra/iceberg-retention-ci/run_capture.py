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
    return {'schemaVersion': 1, 'scope': SCOPE, 'sourceCommit': source,
        'runtimeManifestSha256': manifest_sha, 'passed': bool(passed), 'status': status,
        'failureCategory': failure, 'checks': checks, 'counts': counts, 'proofHashes': hashes,
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
    pins = {name: digest(raw) for name, raw in sources.items()}
    java_sha = pins['src/org/apache/iceberg/ClosedCopyDecoder.java']
    try:
        prepared = loaded['prep_decoder'].prepare(repo, local / ('closed-copy-prep-' + nonce), source,
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
    except BaseException:
        # Raw exceptions, args, paths, graph IDs and private provider streams never leave the runner.
        summary = safe_summary(source, args.source_manifest_sha256, stage=stage)
    write_summary(public, summary)
    print(json.dumps({'scope': SCOPE, 'passed': summary['passed'], 'status': summary['status']}))
    return 0 if summary['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
