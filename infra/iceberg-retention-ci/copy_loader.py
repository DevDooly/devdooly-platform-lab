"""Bounded closed-copy reads and framing. No SQL, network, subprocess or writes."""
from contextlib import ExitStack
import calendar
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import re
import stat
import struct
import sys

PRODUCER_SHA = '73e2293210aba3d9522013d923f8d97bd292baa4623736239d55cc21d9321fe2'
RUNTIME_SHA = 'c63aded0a891bb66cb1fb2de591d67e237467681eb4a4e5a337b9d1d1b02d5e8'
BUCKET = 'platform-lab-iceberg-20261015'
PREFIX = 'warehouse/phase6/'
MAX_OBJECTS, MAX_OBJECT, MAX_TOTAL, MAX_DESCRIPTOR = 128, 4*1024**2, 32*1024**2, 512*1024
MAX_FRAME = 8+4+MAX_DESCRIPTOR+4+4*MAX_OBJECTS+MAX_TOTAL
HEX = re.compile('[a-f0-9]{64}')
FILE_ALIAS = re.compile('f-[a-f0-9]{64}')
OBSERVER_SHA = '801f6aa7bbe7717ff26a9d925478d7608256741537cf6f0cf52381ccaca0c4c3'
CONTRACT_SHA = 'e88d2bedfeb95b71b22e2b5b04701119e8203431d3c8e8cc521958f2dcfad98a'
NAMES = ('jdbc-01-before-trino', 'jdbc-02-after-trino-selects', 'jdbc-03-final')
STAGES = ('SPARK', 'TRINO', 'FINAL_VERIFY')
ROLES = {'postgres', 'garage', 'spark', 'trino', 'reader'}


def require(value, code):
    if not value:
        raise ValueError(code)


def exact(value, keys):
    require(type(value) is dict and set(value) == set(keys.split()), 'EXACT_CLOSED_COPY_SCHEMA_REQUIRED')


def digest(raw): return hashlib.sha256(raw).hexdigest()


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=True, allow_nan=False).encode('ascii')


def strict_json(raw, maximum):
    require(type(raw) is bytes and 0 < len(raw) <= maximum, 'BOUNDED_CLOSED_COPY_JSON_REQUIRED')
    def unique(pairs):
        result = {}
        for key, child in pairs:
            require(key not in result, 'DUPLICATE_CLOSED_COPY_JSON_FIELD')
            result[key] = child
        return result
    def invalid(_value): raise ValueError('NONFINITE_CLOSED_COPY_JSON')
    def finite(value):
        number = float(value); require(math.isfinite(number), 'NONFINITE_CLOSED_COPY_JSON'); return number
    try:
        value = json.loads(raw.decode('utf-8'), object_pairs_hook=unique, parse_constant=invalid, parse_float=finite)
        nodes = [(value, 0)]; count = 0
        while nodes:
            child, depth = nodes.pop(); count += 1
            require(depth <= 64 and count <= 100000, 'CLOSED_COPY_JSON_GRAPH_BOUND')
            if type(child) is dict: nodes.extend((item, depth+1) for item in child.values())
            elif type(child) is list: nodes.extend((item, depth+1) for item in child)
        return value
    except (ValueError, UnicodeError, RecursionError) as error:
        if type(error) is ValueError and re.fullmatch('[A-Z0-9_]+', str(error)):
            raise
        raise ValueError('INVALID_CLOSED_COPY_JSON') from None


def file_alias(bucket, key):
    return 'f-'+digest(json.dumps([bucket, key], separators=(',', ':'), ensure_ascii=True).encode('ascii'))


def validated_map(raw, expected_sha):
    require(type(expected_sha) is str and HEX.fullmatch(expected_sha) and digest(raw) == expected_sha,
        'EXACT_CAPTURE_MAP_WHOLE_SHA_REQUIRED')
    values = strict_json(raw, MAX_DESCRIPTOR)
    require(type(values) is list and 1 <= len(values) <= MAX_OBJECTS, 'NONEMPTY_CAPTURE_MAP_BOUND')
    keys, copies, aliases, total = set(), set(), set(), 0
    result = []
    for row in values:
        exact(row, 'key size sha256 copy')
        key = row['key']
        require(type(key) is str and key.startswith(PREFIX) and re.fullmatch('[A-Za-z0-9._/-]{1,1024}', key)
            and '..' not in key.split('/') and '//' not in key, 'ONLY_CAPTURED_APPROVED_PREFIX_KEYS')
        require(type(row['size']) is int and 0 <= row['size'] <= MAX_OBJECT
            and type(row['sha256']) is str and HEX.fullmatch(row['sha256'])
            and row['copy'] == digest(key.encode('utf-8'))+'.bin', 'EXACT_CAPTURED_OBJECT_RECORD')
        alias = file_alias(BUCKET, key)
        require(key not in keys and row['copy'] not in copies and alias not in aliases, 'CAPTURE_MAP_IDENTITY_COLLISION')
        keys.add(key); copies.add(row['copy']); aliases.add(alias); total += row['size']
        require(total <= MAX_TOTAL, 'CAPTURE_MAP_TOTAL_BOUND')
        result.append({**row, 'alias': alias})
    return sorted(result, key=lambda row: row['key'])


def descriptor_from_map(raw, request):
    exact(request, 'sourceCommit captureMapSha256 approvedBucket approvedPrefix targetTable')
    require(type(request['sourceCommit']) is str and re.fullmatch('[a-f0-9]{40}', request['sourceCommit'])
        and request['approvedBucket'] == BUCKET and request['approvedPrefix'] == PREFIX, 'FROZEN_TRIAL_CAPTURE_SCOPE_REQUIRED')
    target = request['targetTable']; exact(target, 'catalog namespace table currentMetadataUri tableLocation')
    require(all(type(target[key]) is str and re.fullmatch('[A-Za-z_][A-Za-z0-9_]{0,79}', target[key]) for key in ('catalog','namespace','table')),
        'EXACT_TARGET_TABLE_IDENTIFIERS_REQUIRED')
    values = validated_map(raw, request['captureMapSha256'])
    uri_map = {'s3://'+BUCKET+'/'+row['key']: row for row in values}
    location = target['tableLocation']
    require(type(location) is str and location.startswith('s3://'+BUCKET+'/'+PREFIX)
        and re.fullmatch('s3://[A-Za-z0-9._/-]{1,1200}', location) and '..' not in location.split('/')
        and not location.endswith('/') and '//' not in location.removeprefix('s3://')
        and target['currentMetadataUri'] in uri_map, 'APPROVED_TABLE_METADATA_URI_REQUIRED')
    require(target['currentMetadataUri'].startswith(location+'/metadata/'), 'CURRENT_METADATA_OUTSIDE_TARGET_LOCATION')
    value = {'schemaVersion': 1, 'scope': 'CLOSED_COPY_ICEBERG_FORMAT2_DECODE',
        'sourceCommit': request['sourceCommit'], 'producerSha256': PRODUCER_SHA, 'runtimeManifestSha256': RUNTIME_SHA,
        'captureMapSha256': request['captureMapSha256'], 'approvedBucket': BUCKET, 'approvedPrefix': PREFIX,
        'targetTable': dict(target), 'objects': values}
    encoded = canonical(value); require(len(encoded) <= MAX_DESCRIPTOR, 'DESCRIPTOR_JSON_BOUND')
    return value, encoded


def identity(info):
    return (info.st_dev, info.st_ino, info.st_uid, info.st_gid, info.st_mode, info.st_nlink,
        info.st_size, info.st_mtime_ns, info.st_ctime_ns)


def _directory(fd, owner, mode):
    info = os.fstat(fd)
    require(stat.S_ISDIR(info.st_mode) and info.st_uid == owner and stat.S_IMODE(info.st_mode) == mode,
        'EXACT_CLOSED_COPY_DIRECTORY_PERMISSION')
    return info


def _opened_dir(stack, name, parent=None):
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC
    fd = os.open(name, flags, dir_fd=parent); stack.callback(os.close, fd); return fd


def _read_file(parent, name, owner, mode, maximum, expected_size=None, expected_sha=None):
    before = os.stat(name, dir_fd=parent, follow_symlinks=False)
    require(stat.S_ISREG(before.st_mode) and before.st_nlink == 1 and before.st_uid == owner
        and stat.S_IMODE(before.st_mode) == mode and 0 <= before.st_size <= maximum,
        'EXACT_REGULAR_SINGLE_LINK_COPY_REQUIRED')
    fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=parent)
    try:
        first = os.fstat(fd); require(identity(before) == identity(first), 'COPY_OPEN_IDENTITY_CHANGED')
        chunks, count = [], 0
        while True:
            chunk = os.read(fd, min(65536, maximum+1-count))
            if not chunk: break
            count += len(chunk); require(count <= maximum, 'COPY_BYTES_BOUND'); chunks.append(chunk)
        raw = b''.join(chunks); last = os.fstat(fd)
        after = os.stat(name, dir_fd=parent, follow_symlinks=False)
        require(identity(before) == identity(last) == identity(after) and count == before.st_size
            and (expected_size is None or count == expected_size)
            and (expected_sha is None or digest(raw) == expected_sha), 'COPY_IDENTITY_EOF_SIZE_OR_SHA_CHANGED')
        return raw, before
    finally:
        os.close(fd)


def _read_closed_files(attempt_root, capture_map_sha256):
    """Linux only. Called only after source-bound stopped-actor validation."""
    require(sys.platform == 'linux' and os.name == 'posix'
        and all(hasattr(os, name) for name in ('O_NOFOLLOW','O_DIRECTORY','O_CLOEXEC')),
        'LINUX_OPENAT_CLOSED_COPY_READER_REQUIRED')
    root = Path(attempt_root)
    require(root.is_absolute() and '..' not in root.parts and re.fullmatch('cloud-trial9-private-[a-f0-9]{32}', root.name),
        'EXACT_FRESH_ATTEMPT_ROOT_REQUIRED')
    try:
        with ExitStack() as stack:
            fd = _opened_dir(stack, '/')
            ancestors = []
            for name in root.parts[1:]:
                parent = fd; fd = _opened_dir(stack, name, parent)
                ancestors.append((parent,name,fd,os.fstat(fd)))
            root_fd = fd; root_before = _directory(root_fd, os.getuid(), 0o700)
            proof_fd = _opened_dir(stack, 'proof', root_fd); proof_before = _directory(proof_fd, os.getuid(), 0o777)
            objects_fd = _opened_dir(stack, 'objects-after-trino', proof_fd); objects_before = _directory(objects_fd, 185, 0o755)
            map_raw, map_info = _read_file(proof_fd, 'warehouse-after-trino.json', 185, 0o644, MAX_DESCRIPTOR,
                expected_sha=capture_map_sha256)
            records = validated_map(map_raw, capture_map_sha256)
            require(set(os.listdir(objects_fd)) == {row['copy'] for row in records}, 'UNEXPLAINED_COPY_DIRECTORY_ENTRY')
            content, identities = {}, {}
            for row in records:
                raw, info = _read_file(objects_fd, row['copy'], 185, 0o644, MAX_OBJECT, row['size'], row['sha256'])
                content[row['alias']] = raw; identities[row['copy']] = info
            require(set(os.listdir(objects_fd)) == set(identities), 'COPY_DIRECTORY_CHANGED_DURING_READ')
            for name, before in identities.items():
                require(identity(os.stat(name, dir_fd=objects_fd, follow_symlinks=False)) == identity(before), 'COPY_CHANGED_AFTER_WHOLE_READ')
            require(identity(os.stat('warehouse-after-trino.json', dir_fd=proof_fd, follow_symlinks=False)) == identity(map_info),
                'CAPTURE_MAP_CHANGED_DURING_COPY_READ')
            for parent, name, held, before in ((root_fd,'proof',proof_fd,proof_before),
                (proof_fd,'objects-after-trino',objects_fd,objects_before)):
                require(identity(os.fstat(held)) == identity(before)
                    and identity(os.stat(name, dir_fd=parent, follow_symlinks=False)) == identity(before), 'HELD_COPY_DIRECTORY_CHANGED')
            require(identity(os.fstat(root_fd)) == identity(root_before)
                and identity(root.lstat()) == identity(root_before), 'ATTEMPT_ROOT_CHANGED_DURING_READ')
            for parent, name, held, before in ancestors:
                require(identity(os.fstat(held)) == identity(before)
                    and identity(os.stat(name, dir_fd=parent, follow_symlinks=False)) == identity(before),
                    'HELD_ATTEMPT_ANCESTRY_CHANGED')
            return map_raw, records, content
    except OSError:
        raise ValueError('CLOSED_COPY_OS_READ_FAILED') from None


def build_frame(descriptor_bytes, records, content):
    require(type(descriptor_bytes) is bytes and 0 < len(descriptor_bytes) <= MAX_DESCRIPTOR, 'DESCRIPTOR_BYTES_BOUND')
    descriptor = strict_json(descriptor_bytes, MAX_DESCRIPTOR)
    exact(descriptor, 'schemaVersion scope sourceCommit producerSha256 runtimeManifestSha256 captureMapSha256 approvedBucket approvedPrefix targetTable objects')
    require(type(records) is list and 1 <= len(records) <= MAX_OBJECTS and type(content) is dict
        and canonical(descriptor['objects']) == canonical(records)
        and records == sorted(records, key=lambda row: row['key']) and set(content) == {row['alias'] for row in records},
        'FRAME_DESCRIPTOR_OBJECTS_CHANGED')
    parts = [b'ICCPY001', struct.pack('>I', len(descriptor_bytes)), descriptor_bytes, struct.pack('>I', len(records))]
    total = 0
    for row in records:
        raw = content[row['alias']]
        require(type(raw) is bytes and len(raw) == row['size'] and digest(raw) == row['sha256'], 'FRAME_WHOLE_OBJECT_CHANGED')
        total += len(raw); require(total <= MAX_TOTAL, 'FRAME_PAYLOAD_BOUND')
        parts.extend((struct.pack('>I', len(raw)), raw))
    frame = b''.join(parts); require(len(frame) <= MAX_FRAME, 'FRAME_TOTAL_BOUND'); return frame


def utc_ns(value):
    require(type(value) is str, 'EXACT_UTC_CAPTURE_TIME_REQUIRED')
    match = re.fullmatch(r'([0-9]{4})-([0-9]{2})-([0-9]{2})T([0-9]{2}):([0-9]{2}):([0-9]{2})(?:\.([0-9]{1,9}))?(?:Z|\+00:00)', value)
    require(match is not None, 'EXACT_UTC_CAPTURE_TIME_REQUIRED')
    try: stamp = datetime(*(int(match[i]) for i in range(1, 7)), tzinfo=timezone.utc)
    except ValueError: raise ValueError('EXACT_UTC_CAPTURE_TIME_REQUIRED') from None
    return calendar.timegm(stamp.utctimetuple())*10**9 + int((match[7] or '').ljust(9, '0'))


def number(value):
    return type(value) in (int, float) and math.isfinite(value)


def proof_bytes(proof, maximum=65536):
    exact(proof, 'raw sha256')
    require(type(proof['raw']) is bytes and 0 < len(proof['raw']) <= maximum and type(proof['sha256']) is str
        and HEX.fullmatch(proof['sha256']) and digest(proof['raw']) == proof['sha256'], 'RAW_PROOF_WHOLE_SHA_REQUIRED')
    return proof['raw']


def proof_value(proof, maximum=65536):
    return strict_json(proof_bytes(proof, maximum), maximum)


def source_header(value, source, authority=None, observer=False):
    require(value['sourceCommit'] == source and value['producerSha256'] == PRODUCER_SHA
        and value['runtimeManifestSha256'] == RUNTIME_SHA, 'SAME_FROZEN_PRODUCER_SOURCE_REQUIRED')
    if authority is not None:
        require(value['authoritySourceSha256'] == authority, 'SOURCE_BOUND_COMPOSITE_AUTHORITY_REQUIRED')
    if observer: require(value['observerManifestSha256'] == OBSERVER_SHA, 'EXACT_OBSERVER_SOURCE_REQUIRED')


def validate_stopped(proof, authority, clock, expected_authority_source_sha256, *, after=False):
    value = proof_value(proof)
    exact(value, 'schemaVersion scope authoritySourceSha256 sourceCommit producerSha256 runtimeManifestSha256 observerManifestSha256 project attemptRoot capturedAt monotonic hostBootId clockSha256 roles initializer originalRoleStopCallsAdded originalInitializerStopCallsAdded')
    source_header(value, authority['sourceCommit'], expected_authority_source_sha256, True)
    require(type(value['schemaVersion']) is int and value['schemaVersion'] == 1
        and value['scope'] == ('POST' if after else 'PRE')+'_DECODER_EXACT_STOPPED_FRESH_CLOUD_ACTORS'
        and value['clockSha256'] == authority['clock']['sha256'] and value['hostBootId'] == clock['hostBootId']
        and number(value['monotonic']) and clock['startedMonotonic'] <= value['monotonic'] < clock['startedMonotonic']+600,
        'SAME_BOOT_ORIGINAL_CLOCK_STOPPED_GATE_REQUIRED')
    require(type(value['project']) is str and re.fullmatch('cloud-trial9-[a-f0-9]{32}', value['project'])
        and type(value['attemptRoot']) is str and value['attemptRoot'].startswith('/')
        and Path(value['attemptRoot']).name == 'cloud-trial9-private-'+value['project'].removeprefix('cloud-trial9-'),
        'SAME_FRESH_PROJECT_AND_ATTEMPT_ROOT_REQUIRED')
    require(all(type(value[k]) is int and value[k] == 0 for k in ('originalRoleStopCallsAdded','originalInitializerStopCallsAdded')),
        'NO_ORIGINAL_ACTOR_STOP_CALLS_ADDED')
    require(type(value['roles']) is list and len(value['roles']) == 5, 'ALL_FIVE_STOPPED_ROLE_PROOFS_REQUIRED')
    seen, ids = set(), set()
    for row in value['roles']:
        exact(row, 'id role running exitCode oom pid startedAt configBindingSha256')
        require(row['role'] in ROLES and row['role'] not in seen and type(row['id']) is str
            and HEX.fullmatch(row['id']) and row['id'] not in ids and row['running'] is False
            and row['oom'] is False and type(row['pid']) is int and row['pid'] == 0
            and type(row['exitCode']) is int and 0 <= row['exitCode'] <= 255
            and type(row['configBindingSha256']) is str and HEX.fullmatch(row['configBindingSha256']),
            'EXACT_STOPPED_CID_PID_CONFIG_BINDING_REQUIRED')
        utc_ns(row['startedAt'])
        if row['role'] in ('spark','reader'): require(row['exitCode'] == 0, 'NORMAL_SPARK_READER_EXIT_REQUIRED')
        if row['role'] == 'trino': require(row['exitCode'] in (0,143), 'NORMAL_TRINO_EXIT_REQUIRED')
        seen.add(row['role']); ids.add(row['id'])
    exact(value['initializer'], 'id running exitCode oom')
    init = value['initializer']
    require(type(init['id']) is str and HEX.fullmatch(init['id']) and init['id'] not in ids
        and init['running'] is False and init['oom'] is False and type(init['exitCode']) is int
        and init['exitCode'] == 0, 'EXACT_STOPPED_INITIALIZER_REQUIRED')
    utc_ns(value['capturedAt'])
    return value


def validate_authority_bundle(authority, expected_authority_source_sha256):
    """Recompute raw proof hashes and relations; a caller's passed flag is insufficient.

    Receipts are authenticated by the source-pinned composite callable, not a
    cryptographic signature or a sandbox for hostile replacement Python modules.
    """
    exact(authority, 'sourceCommit producerSha256 runtimeManifestSha256 observerManifestSha256 authoritySourceSha256 producerSummary sparkResult sparkDiagnostic readerResult clock trinoStopIntent trinoStopResult named observerResult makeBinding validation lifecycle namedSqlIntents queryPlanSource captureMap')
    require(type(expected_authority_source_sha256) is str and HEX.fullmatch(expected_authority_source_sha256)
        and type(authority['sourceCommit']) is str and re.fullmatch('[a-f0-9]{40}', authority['sourceCommit']),
        'EXPLICIT_SOURCE_BOUND_AUTHORITY_REQUIRED')
    source_header(authority, authority['sourceCommit'], expected_authority_source_sha256, True)
    source = authority['sourceCommit']
    summary = proof_value(authority['producerSummary'])
    expected_checks = {'frozenInputs','vendor','pinnedImages','freshPhysicalVolumes','actualMemAvailable7Gi',
        'internalNetwork','singleClock','normalSparkExit','normalTrinoExit','pythonReaderExit','jdbcAndWholeObjectsUnchanged'}
    require(summary['sourceCommit'] == source and summary['passed'] is True and summary['failure'] is None
        and summary['ownedContainersStopped'] is True and summary['ownedInitializerStopped'] is True
        and summary['enabledOomKillerRepresentationsVerified'] is True
        and type(summary['workloadElapsedMillis']) is int and 0 <= summary['workloadElapsedMillis'] <= 600000
        and type(summary['checks']) is dict and set(summary['checks']) == expected_checks
        and all(v is True for v in summary['checks'].values())
        and summary['cleanupDiagnostics'] == {'initializer':'STOPPED_VERIFIED','containers':'STOPPED_VERIFIED'},
        'ACTUAL_FROZEN_PRODUCER_SUCCESS_REQUIRED')
    clock = proof_value(authority['clock']); exact(clock, 'startedMonotonic hostBootId budgetSeconds')
    require(number(clock['startedMonotonic']) and clock['startedMonotonic'] > 0
        and type(clock['budgetSeconds']) is int and clock['budgetSeconds'] == 600
        and type(clock['hostBootId']) is str and re.fullmatch('[a-f0-9]{8}(?:-[a-f0-9]{4}){3}-[a-f0-9]{12}', clock['hostBootId']),
        'ORIGINAL_SINGLE_BOOT_AND_CLOCK_REQUIRED')
    query_source = authority['queryPlanSource']; proof_bytes(query_source, 131072)
    require(query_source['sha256'] == CONTRACT_SHA, 'FROZEN_QUERY_PLAN_SOURCE_REQUIRED')
    # Exact known pure source: definitions and stdlib imports only. Calling these
    # functions builds strings/checks rows, and executes no SQL or subprocess.
    pure = {}; exec(compile(query_source['raw'], '<pinned-query-contract>', 'exec'), pure)
    spark = proof_value(authority['sparkResult']); diagnostic = proof_value(authority['sparkDiagnostic'])
    reader = proof_value(authority['readerResult'])
    require(spark['passed'] is True and diagnostic['passed'] is True and diagnostic['phase'] == 'COMPLETED'
        and diagnostic['sessionStopFailed'] is False and reader['passed'] is True
        and reader['allPreTrinoBytesEqual'] is True and reader['onlyGetAndList'] is True,
        'SAME_RUN_PRIVATE_SPARK_READER_SUCCESS_REQUIRED')
    chain = pure['snapshot_chain'](spark['snapshots'], 3)
    ids = [r['snapshot_id'] for r in chain]
    require(summary['result']['snapshotIds'] == ids and summary['result']['rowFingerprints'] == spark['rowFingerprints']
        and type(spark['rowFingerprints']) is list and len(spark['rowFingerprints']) == 3
        and all(type(v) is str and HEX.fullmatch(v) for v in spark['rowFingerprints']), 'SAME_ACTUAL_VALIDATED_SNAPSHOTS_REQUIRED')
    proof_bytes(authority['captureMap'], MAX_DESCRIPTOR)
    capture_map = validated_map(authority['captureMap']['raw'], authority['captureMap']['sha256'])
    require(type(reader['wholeObjects']) is int and reader['wholeObjects'] == len(capture_map)
        and type(reader['oldObjects']) is int and reader['oldObjects'] == spark['oldWarehouseObjects']
        and spark['afterWarehouseObjects'] == len(capture_map), 'ACTUAL_CAPTURE_MAP_AND_READER_COUNT_BINDING')
    require(type(authority['named']) is list and len(authority['named']) == 3, 'EXACT_THREE_NAMED_PROOFS_REQUIRED')
    previous_ns = None; raw_pointer = None; checkpoints = []
    for index, entry in enumerate(authority['named']):
        exact(entry, 'name raw rawSha256 checkpoint checkpointSha256')
        require(entry['name'] == NAMES[index] and type(entry['raw']) is bytes and 0 < len(entry['raw']) < 16384
            and digest(entry['raw']) == entry['rawSha256'] and digest(entry['checkpoint']) == entry['checkpointSha256'],
            'NAMED_WHOLE_BYTE_HASH_BINDING_REQUIRED')
        checkpoint = strict_json(entry['checkpoint'], 65536)
        exact(checkpoint, 'scope sequence stage before after rawBytes rawSha256 returnBytesPreserved originalDeadlineStartedMonotonic producerSha256 runtimeManifestSha256 sourceCommit')
        source_header(checkpoint, source)
        require(checkpoint['scope'] == 'NAMED_JDBC_RETURN_BYTES_ONLY' and type(checkpoint['sequence']) is int
            and checkpoint['sequence'] == index+1 and checkpoint['stage'] == STAGES[index]
            and type(checkpoint['rawBytes']) is int and checkpoint['rawBytes'] == len(entry['raw'])
            and checkpoint['rawSha256'] == entry['rawSha256'] and checkpoint['returnBytesPreserved'] is True
            and checkpoint['originalDeadlineStartedMonotonic'] == clock['startedMonotonic'], 'EXACT_NAMED_STAGE_AND_CLOCK_REQUIRED')
        for key in ('before','after'):
            timing = checkpoint[key]; exact(timing, 'utc monotonicNs'); utc_ns(timing['utc'])
            require(type(timing['monotonicNs']) is int and timing['monotonicNs'] >= clock['startedMonotonic']*10**9
                and timing['monotonicNs'] < (clock['startedMonotonic']+600)*10**9
                and (previous_ns is None or timing['monotonicNs'] >= previous_ns), 'NAMED_MONOTONIC_ORDER_REQUIRED')
            previous_ns = timing['monotonicNs']
        require(raw_pointer is None or raw_pointer == entry['raw'], 'ACTUAL_JDBC_POINTER_BYTES_CHANGED')
        raw_pointer = entry['raw']; checkpoints.append(checkpoint)
    observed = proof_value(authority['observerResult'])
    source_header(observed, source)
    require(observed['scope'] == 'NAMED_RETURN_OBSERVATIONS_NOT_PRODUCER_SUCCESS'
        and all(type(observed[k]) is int and observed[k] == v for k,v in (
            ('makeCallsStarted',1),('makeCallsCompleted',1),('jdbcCallsStarted',3),('jdbcCallsCompleted',3),('extraSqlCallsAdded',0)))
        and all(observed[k] is True for k in ('allThreeCheckpointsObserved','originalFunctionsRestored'))
        and all(observed[k] is False for k in ('hookDriftDetected','producerRunPassedClaimed','writersQuiescentVerified','tableClosureVerified','automaticRetry')),
        'COMPLETE_RESTORED_OBSERVER_NOT_INDEPENDENT_AUTHORITY')
    binding = proof_value(authority['makeBinding']); source_header(binding, source)
    require(binding['scope'] == 'NAMED_OBSERVATION_ONLY' and binding['returnObjectPreserved'] is True, 'ORIGINAL_ATTEMPT_RETURN_BINDING_REQUIRED')
    validation = proof_value(authority['validation'])
    exact(validation, 'schemaVersion scope authoritySourceSha256 queryPlanSourceSha256 sourceCommit producerSha256 runtimeManifestSha256 capturedAt producerSummarySha256 sparkResultSha256 snapshotIds rowFingerprints namedSqlIntents closedActorScope backupExportActorCount individualNamedQueryRawResultsClaimed')
    source_header(validation, source, expected_authority_source_sha256)
    require(type(validation['schemaVersion']) is int and validation['schemaVersion'] == 1
        and validation['scope'] == 'SAME_RUN_FROZEN_SPARK_TRINO_SNAPSHOT_VALIDATION'
        and validation['queryPlanSourceSha256'] == CONTRACT_SHA and validation['snapshotIds'] == ids
        and validation['rowFingerprints'] == spark['rowFingerprints']
        and validation['capturedAt'] == checkpoints[-1]['after']['utc']
        and validation['producerSummarySha256'] == authority['producerSummary']['sha256']
        and validation['sparkResultSha256'] == authority['sparkResult']['sha256']
        and validation['closedActorScope'] == 'THIS_FRESH_TRIAL_ONLY'
        and type(validation['backupExportActorCount']) is int and validation['backupExportActorCount'] == 0
        and validation['individualNamedQueryRawResultsClaimed'] is False, 'SOURCE_BOUND_SNAPSHOT_VALIDATION_REQUIRED')
    expected_queries = pure['query_plan'](chain)
    require(type(authority['namedSqlIntents']) is list and len(authority['namedSqlIntents']) == len(expected_queries)
        and type(validation['namedSqlIntents']) is list and len(validation['namedSqlIntents']) == len(expected_queries), 'ALL_ACTUAL_TEN_QUERY_INTENTS_REQUIRED')
    for saved, declared, (name, sql) in zip(authority['namedSqlIntents'], validation['namedSqlIntents'], expected_queries):
        exact(saved, 'name raw sha256'); intent = proof_value({k:saved[k] for k in ('raw','sha256')})
        exact(declared, 'name rawSha256 sqlSha256')
        require(saved['name'] == name and intent == {'sqlSha256':digest(sql.encode()),'automaticRetry':False}
            and declared == {'name':name,'rawSha256':saved['sha256'],'sqlSha256':intent['sqlSha256']}, 'FROZEN_SELECT_INTENT_WHOLE_HASH_MISMATCH')
    stopped = validate_stopped(authority['lifecycle'], authority, clock, expected_authority_source_sha256)
    require(stopped['project'] == binding['project'] and stopped['attemptRoot'] == binding['attemptRoot']
        and utc_ns(stopped['capturedAt']) >= utc_ns(validation['capturedAt'])
        and stopped['monotonic']*10**9 >= previous_ns, 'STOPPED_GATE_MUST_FOLLOW_NAMED_VALIDATION')
    stop = proof_value(authority['trinoStopResult']); intent = proof_value(authority['trinoStopIntent'])
    exact(stop, 'cid pid startTicks hostBootId cgroupSha256 startedAt signalScope graceSeconds signalDeliveryDirectlyObserved automaticRetry requestReturnedZero actualExitCode nonOom')
    exact(intent, 'cid pid startTicks hostBootId cgroupSha256 startedAt signalScope graceSeconds signalDeliveryDirectlyObserved automaticRetry')
    trino = next(row for row in stopped['roles'] if row['role'] == 'trino')
    require(intent == {k:v for k,v in stop.items() if k not in ('requestReturnedZero','actualExitCode','nonOom')}
        and stop['cid'] == trino['id'] and stop['startedAt'] == trino['startedAt']
        and stop['actualExitCode'] == trino['exitCode'] and stop['signalScope'] == 'CONFIGURED_OR_DEFAULT_SIGTERM'
        and type(stop['graceSeconds']) is int and stop['graceSeconds'] == 30
        and type(stop['pid']) is int and stop['pid'] > 0 and type(stop['startTicks']) is int and stop['startTicks'] > 0
        and stop['hostBootId'] == clock['hostBootId'] and type(stop['cgroupSha256']) is str and HEX.fullmatch(stop['cgroupSha256'])
        and stop['signalDeliveryDirectlyObserved'] is False and stop['automaticRetry'] is False
        and stop['requestReturnedZero'] is True and stop['nonOom'] is True, 'ACTUAL_TRINO_STOP_INTENT_AND_EXIT_BINDING')
    return {'summary':summary,'clock':clock,'spark':spark,'validation':validation,'stopped':stopped,
        'captureMap':capture_map,'pointerBytes':raw_pointer}


def target_from_pointer(raw):
    try: pointer_rows = [line.split('|') for line in raw.decode('ascii').splitlines()]
    except UnicodeError: raise ValueError('EXACT_JDBC_POINTER_FORMAT_REQUIRED') from None
    require(len(pointer_rows) == 2 and all(len(row) == 5 for row in pointer_rows)
        and len({tuple(row[:3]) for row in pointer_rows}) == 2, 'EXACT_TWO_JDBC_POINTER_ROWS_REQUIRED')
    selected = [row for row in pointer_rows if row[:3] == ['phase6','bronze','synthetic_events']]
    require(len(selected) == 1 and selected[0][3].count('/metadata/') == 1, 'ACTUAL_NAMED_CURRENT_METADATA_URI_REQUIRED')
    current = selected[0][3]
    return {'catalog':'phase6','namespace':'bronze','table':'synthetic_events','currentMetadataUri':current,
        'tableLocation':current.split('/metadata/')[0]}


def derive_request(authority_bundle, expected_authority_source_sha256):
    """Called after the actual main and stopped gate; no future pointer is input."""
    verified = validate_authority_bundle(authority_bundle, expected_authority_source_sha256)
    request = {'sourceCommit':authority_bundle['sourceCommit'],'captureMapSha256':authority_bundle['captureMap']['sha256'],
        'approvedBucket':BUCKET,'approvedPrefix':PREFIX,'targetTable':target_from_pointer(verified['pointerBytes'])}
    descriptor_from_map(authority_bundle['captureMap']['raw'], request)
    return request


def load_closed_copies(attempt_root, request, authority_bundle, expected_authority_source_sha256):
    verified = validate_authority_bundle(authority_bundle, expected_authority_source_sha256)
    descriptor, descriptor_bytes = descriptor_from_map(authority_bundle['captureMap']['raw'], request)
    require(str(attempt_root) == verified['stopped']['attemptRoot'] and request['sourceCommit'] == authority_bundle['sourceCommit']
        and request['captureMapSha256'] == authority_bundle['captureMap']['sha256'], 'EXACT_AUTHORIZED_ATTEMPT_AND_CAPTURE_MAP_REQUIRED')
    require(request['targetTable'] == target_from_pointer(verified['pointerBytes']), 'ACTUAL_DERIVED_TARGET_POINTER_REQUIRED')
    map_raw, records, content = _read_closed_files(attempt_root, request['captureMapSha256'])
    require(map_raw == authority_bundle['captureMap']['raw'], 'SOURCE_CAPTURE_MAP_BYTES_CHANGED')
    frame = build_frame(descriptor_bytes, records, content)
    return {'descriptor':descriptor,'descriptorBytes':descriptor_bytes,'frameBytes':frame,
        'privateReceipt':{'schemaVersion':1,'scope':'SOURCE_BOUND_STABLE_WHOLE_COPY_LOAD_NOT_LIVE_TABLE_VERIFICATION',
            'authoritySourceSha256':expected_authority_source_sha256,'lifecycleSha256':authority_bundle['lifecycle']['sha256'],
            'validationSha256':authority_bundle['validation']['sha256'],'captureMapSha256':request['captureMapSha256'],
            'descriptorSha256':digest(descriptor_bytes),'frameSha256':digest(frame),'objects':len(records),
            'wholeBytes':sum(row['size'] for row in records),'writesPerformed':0,'networkCallsPerformed':0,
            'snapshotExpirationOrGcPerformed':False,'independentlyVerifiedLiveTable':False}}
