"""Pure checks for one fresh synthetic warehouse. No I/O or deletion adapter.

preflight checks facts, not execution authority or the absence of other writers.
The owned wrapper must call it with an observed clock immediately before its one
expiration request. verify_expiration uses that same before observation; it does
not establish freshness, authorization, physical reclamation, or atomic deletion.
Any failed/partial observation is rejected with a fixed code, never a PASS.
"""
import re
import uuid

BRONZE = 'warehouse/phase6/bronze/synthetic_events/'
SILVER = 'warehouse/phase6/silver/sensor_outcomes/'
MAX_LONG = 2**63 - 1
MAX_OBJECT_BYTES = 4 * 1024**2
MAX_TOTAL_BYTES = 64 * 1024**2
CODES = frozenset({'CONTRACT_UNVERIFIED', 'INPUT_SHAPE_UNVERIFIED', 'IDENTITY_UNVERIFIED',
    'TIME_UNVERIFIED', 'KEY_UNVERIFIED', 'SNAPSHOT_UNVERIFIED', 'REFS_UNVERIFIED',
    'FILESET_UNVERIFIED', 'OBJECT_UNVERIFIED', 'EXPIRATION_STATE_UNVERIFIED',
    'UNEXPECTED_OBJECT_DELTA', 'DELETION_COUNTER_UNVERIFIED', 'NO_SUCH_KEY_UNVERIFIED'})
STATE_FIELDS = {'tableUuid', 'currentSnapshotId', 'metadataKey', 'gcEnabled',
    'tagRetentionDefault', 'snapshots', 'refs', 'objects'}
SNAPSHOT_FIELDS = {'id', 'parentId', 'operation', 'committedAtMs', 'totalRecords',
    'dataFiles', 'manifestList', 'manifests'}
RESULT_FIELDS = {'deleted_data_files_count', 'deleted_position_delete_files_count',
    'deleted_equality_delete_files_count', 'deleted_manifest_files_count',
    'deleted_manifest_lists_count', 'deleted_statistics_files_count'}


def require(value, code):
    if not value:
        raise ValueError(code if code in CODES else 'CONTRACT_UNVERIFIED')


def _integer(value, minimum, maximum, code):
    require(type(value) is int and minimum <= value <= maximum, code)
    return value


def _identity(value):
    require(type(value) is str and re.fullmatch(r'[1-9][0-9]{0,18}', value) is not None,
        'IDENTITY_UNVERIFIED')
    require(int(value) <= MAX_LONG, 'IDENTITY_UNVERIFIED')
    return value


def _key(value, prefix=None, suffix=None):
    require(type(value) is str and 1 <= len(value) <= 512, 'KEY_UNVERIFIED')
    parts = value.split('/')
    require(all(part not in {'', '.', '..'} and re.fullmatch(r'[A-Za-z0-9_.-]{1,128}', part)
        for part in parts), 'KEY_UNVERIFIED')
    require(value.startswith((BRONZE, SILVER)), 'KEY_UNVERIFIED')
    require(prefix is None or value.startswith(prefix), 'KEY_UNVERIFIED')
    require(suffix is None or value.endswith(suffix), 'KEY_UNVERIFIED')
    return value


def _state(value, snapshot_count, now_ms=None, allowed_missing_parent=None):
    require(type(value) is dict and set(value) == STATE_FIELDS, 'INPUT_SHAPE_UNVERIFIED')
    identity = value['tableUuid']
    require(type(identity) is str and re.fullmatch(
        r'[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}', identity),
        'IDENTITY_UNVERIFIED')
    parsed = uuid.UUID(identity)
    require(parsed.int != 0 and str(parsed) == identity, 'IDENTITY_UNVERIFIED')
    _identity(value['currentSnapshotId'])
    _key(value['metadataKey'], BRONZE + 'metadata/', '.metadata.json')
    require(value['gcEnabled'] is True and value['tagRetentionDefault'] is True,
        'INPUT_SHAPE_UNVERIFIED')
    if now_ms is not None:
        _integer(now_ms, 1, MAX_LONG, 'TIME_UNVERIFIED')
    objects = value['objects']
    require(type(objects) is list and 1 <= len(objects) <= 128, 'OBJECT_UNVERIFIED')
    object_map, total_bytes = {}, 0
    for item in objects:
        require(type(item) is dict and set(item) == {'key', 'bytes', 'sha256'}, 'OBJECT_UNVERIFIED')
        key = _key(item['key'])
        size = _integer(item['bytes'], 1, MAX_OBJECT_BYTES, 'OBJECT_UNVERIFIED')
        require(type(item['sha256']) is str and re.fullmatch(r'[a-f0-9]{64}', item['sha256']),
            'OBJECT_UNVERIFIED')
        require(key not in object_map, 'OBJECT_UNVERIFIED')
        total_bytes += size
        require(total_bytes <= MAX_TOTAL_BYTES, 'OBJECT_UNVERIFIED')
        object_map[key] = dict(item)
    require(value['metadataKey'] in object_map, 'OBJECT_UNVERIFIED')
    require(any(key.startswith(SILVER) for key in object_map), 'OBJECT_UNVERIFIED')
    snapshots = value['snapshots']
    require(type(snapshots) is list and len(snapshots) == snapshot_count, 'SNAPSHOT_UNVERIFIED')
    snapshot_map, known_data, metadata_files = {}, {}, set()
    for item in snapshots:
        require(type(item) is dict and set(item) == SNAPSHOT_FIELDS, 'SNAPSHOT_UNVERIFIED')
        snapshot_id = _identity(item['id'])
        require(snapshot_id not in snapshot_map, 'SNAPSHOT_UNVERIFIED')
        parent = item['parentId']
        require(parent is None or _identity(parent) != snapshot_id, 'SNAPSHOT_UNVERIFIED')
        require(type(item['operation']) is str and item['operation'] in {'append', 'replace'}, 'SNAPSHOT_UNVERIFIED')
        committed = _integer(item['committedAtMs'], 1, MAX_LONG, 'TIME_UNVERIFIED')
        require(now_ms is None or committed <= now_ms, 'TIME_UNVERIFIED')
        records = _integer(item['totalRecords'], 1, 18, 'SNAPSHOT_UNVERIFIED')
        data_files = item['dataFiles']
        require(type(data_files) is list and 1 <= len(data_files) <= 2, 'FILESET_UNVERIFIED')
        data, summed = {}, 0
        for file in data_files:
            require(type(file) is dict and set(file) == {'key', 'records', 'bytes'}, 'FILESET_UNVERIFIED')
            key = _key(file['key'], BRONZE + 'data/', '.parquet')
            count = _integer(file['records'], 1, 18, 'FILESET_UNVERIFIED')
            size = _integer(file['bytes'], 1, MAX_OBJECT_BYTES, 'FILESET_UNVERIFIED')
            require(key not in data and key in object_map and object_map[key]['bytes'] == size,
                'FILESET_UNVERIFIED')
            require(key not in known_data or known_data[key] == file, 'FILESET_UNVERIFIED')
            data[key], known_data[key] = dict(file), dict(file)
            summed += count
        require(summed == records, 'FILESET_UNVERIFIED')
        manifest_list = _key(item['manifestList'], BRONZE + 'metadata/', '.avro')
        manifests = item['manifests']
        require(type(manifests) is list and 1 <= len(manifests) <= 32, 'FILESET_UNVERIFIED')
        manifest_keys = [_key(key, BRONZE + 'metadata/', '.avro') for key in manifests]
        require(len(set(manifest_keys)) == len(manifest_keys) and manifest_list not in manifest_keys,
            'FILESET_UNVERIFIED')
        require({manifest_list, *manifest_keys} <= set(object_map), 'FILESET_UNVERIFIED')
        metadata_files.update({manifest_list, *manifest_keys})
        normalized = dict(item)
        normalized.update(dataFiles=[data[key] for key in sorted(data)], manifests=sorted(manifest_keys))
        snapshot_map[snapshot_id] = normalized
    require(not (set(known_data) & metadata_files), 'FILESET_UNVERIFIED')
    for item in snapshot_map.values():
        require(item['parentId'] is None or item['parentId'] in snapshot_map
            or item['parentId'] == allowed_missing_parent, 'SNAPSHOT_UNVERIFIED')
    refs = value['refs']
    require(type(refs) is list and len(refs) == 2, 'REFS_UNVERIFIED')
    ref_map = {}
    for ref in refs:
        require(type(ref) is dict and set(ref) == {'name', 'kind', 'snapshotId'}, 'REFS_UNVERIFIED')
        name = ref['name']
        require(type(name) is str and name in {'main', 'retained_first6'} and name not in ref_map, 'REFS_UNVERIFIED')
        require(ref['kind'] == ('BRANCH' if name == 'main' else 'TAG')
            and _identity(ref['snapshotId']) in snapshot_map, 'REFS_UNVERIFIED')
        ref_map[name] = dict(ref)
    require(set(ref_map) == {'main', 'retained_first6'}
        and ref_map['main']['snapshotId'] == value['currentSnapshotId'], 'REFS_UNVERIFIED')
    ordered = sorted(snapshot_map.values(), key=lambda item: item['committedAtMs'])
    require(all(left['committedAtMs'] < right['committedAtMs'] for left, right in zip(ordered, ordered[1:])),
        'TIME_UNVERIFIED')
    return {'snapshots': snapshot_map, 'ordered': ordered, 'objects': object_map, 'refs': ref_map}


def _closure(snapshot):
    return {file['key'] for file in snapshot['dataFiles']} | {snapshot['manifestList']} | set(snapshot['manifests'])


def _plan(state, now_ms):
    checked = _state(state, 4, now_ms)
    one, two, three, four = checked['ordered']
    require([item['operation'] for item in checked['ordered']] == ['append', 'append', 'replace', 'append']
        and [item['totalRecords'] for item in checked['ordered']] == [6, 12, 12, 18]
        and [item['parentId'] for item in checked['ordered']] == [None, one['id'], two['id'], three['id']],
        'SNAPSHOT_UNVERIFIED')
    require(state['currentSnapshotId'] == four['id']
        and checked['refs']['retained_first6']['snapshotId'] == one['id'], 'REFS_UNVERIFIED')
    files = [{file['key']: file for file in item['dataFiles']} for item in checked['ordered']]
    first, second, compacted, current = [set(value) for value in files]
    require(len(first) == len(compacted) == 1 and len(second) == len(current) == 2
        and first < second and compacted < current and not (compacted & second)
        and not ((current - compacted) & (second | compacted)), 'FILESET_UNVERIFIED')
    require(next(iter(files[0].values()))['records'] == 6
        and all(file['records'] == 6 for file in files[1].values())
        and next(iter(files[2].values()))['records'] == 12
        and files[3][next(iter(current - compacted))]['records'] == 6, 'FILESET_UNVERIFIED')
    data_key = next(iter(second - first))
    protected = set().union(*(_closure(item) for item in (one, three, four)))
    protected |= {key for key in checked['objects'] if key.startswith(SILVER)
        or (key.startswith(BRONZE + 'metadata/') and key.endswith('.metadata.json'))}
    allowed = _closure(two) - protected
    require(data_key in allowed and allowed & (first | second | compacted | current) == {data_key},
        'FILESET_UNVERIFIED')
    return {'snapshotOrder': [item['id'] for item in checked['ordered']], 'expiredSnapshotId': two['id'],
        'cutoffMs': three['committedAtMs'], 'removedDataKey': data_key,
        'protectedKeys': sorted(protected), 'allowedRemovedKeys': sorted(allowed)}, checked


def preflight(state, now_ms):
    _integer(now_ms, 1, MAX_LONG, 'TIME_UNVERIFIED')
    return _plan(state, now_ms)[0]


def verify_expiration(before, after, result, missing):
    plan, first = _plan(before, None)
    second = _state(after, 3, allowed_missing_parent=plan['expiredSnapshotId'])
    require(before['tableUuid'] == after['tableUuid'] and before['currentSnapshotId'] == after['currentSnapshotId']
        and first['refs'] == second['refs'], 'EXPIRATION_STATE_UNVERIFIED')
    retained = set(first['snapshots']) - {plan['expiredSnapshotId']}
    require(set(second['snapshots']) == retained and all(
        first['snapshots'][key] == second['snapshots'][key] for key in retained), 'EXPIRATION_STATE_UNVERIFIED')
    removed = set(first['objects']) - set(second['objects'])
    added = set(second['objects']) - set(first['objects'])
    require(plan['removedDataKey'] in removed and removed <= set(plan['allowedRemovedKeys'])
        and not (removed & set(plan['protectedKeys'])), 'UNEXPECTED_OBJECT_DELTA')
    require(all(first['objects'][key] == second['objects'][key]
        for key in set(first['objects']) & set(second['objects'])), 'OBJECT_UNVERIFIED')
    require(1 <= len(added) <= 16 and all(key.startswith(BRONZE + 'metadata/')
        and key.endswith('.metadata.json') for key in added)
        and after['metadataKey'] in added, 'UNEXPECTED_OBJECT_DELTA')
    require(type(result) is dict and set(result) == RESULT_FIELDS, 'DELETION_COUNTER_UNVERIFIED')
    for value in result.values():
        _integer(value, 0, MAX_LONG, 'DELETION_COUNTER_UNVERIFIED')
    expired = first['snapshots'][plan['expiredSnapshotId']]
    manifests = len(removed & set(expired['manifests']))
    lists = int(expired['manifestList'] in removed)
    require(result == {'deleted_data_files_count': 1, 'deleted_position_delete_files_count': 0,
        'deleted_equality_delete_files_count': 0, 'deleted_manifest_files_count': manifests,
        'deleted_manifest_lists_count': lists, 'deleted_statistics_files_count': 0}, 'DELETION_COUNTER_UNVERIFIED')
    require(type(missing) is dict and set(missing) == {'status', 'code', 'key'}
        and type(missing['status']) is int and missing['status'] == 404
        and missing['code'] == 'NoSuchKey' and missing['key'] == plan['removedDataKey'], 'NO_SUCH_KEY_UNVERIFIED')
    return {'passed': True, 'expiredSnapshotCount': 1, 'retainedSnapshotCount': 3,
        'deletedDataFiles': 1, 'deletedManifests': manifests, 'deletedManifestLists': lists,
        'protectedObjectCount': len(plan['protectedKeys']), 'oldSurvivorObjectCount': len(first['objects']) - len(removed),
        'newMetadataObjectCount': len(added)}
