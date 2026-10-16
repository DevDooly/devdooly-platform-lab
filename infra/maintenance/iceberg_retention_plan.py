"""Conservative pure snapshot planner. No collector, SQL, network, or executor."""
import calendar
import datetime as dt
import hashlib
import json
import re

MAX_ITEMS = 10000
MAX_EDGES = 100000
SECOND = 1000000000
ID = r'[A-Za-z0-9][A-Za-z0-9._-]{0,79}'
SHA = r'[a-f0-9]{64}'
STAMP = re.compile(r'([0-9]{4})-([0-9]{2})-([0-9]{2})T([0-9]{2}):([0-9]{2}):([0-9]{2})(?:\.([0-9]{1,9}))?(?:Z|\+00:00)')
FLAGS = ('complete', 'refsComplete', 'pinsComplete', 'snapshotFileClosureComplete', 'writersQuiescent')


def require(value, code):
    if not value:
        raise ValueError(code)


def fields(value, names):
    require(type(value) is dict and set(value) == set(names.split()), 'EXACT_SCHEMA_REQUIRED')


def token(value, pattern=ID):
    require(type(value) is str and re.fullmatch(pattern, value) is not None, 'TOKEN_INVALID')


def integer(value, low=0, high=MAX_ITEMS):
    require(type(value) is int and low <= value <= high, 'INTEGER_BOUND_REQUIRED')


def array(value):
    require(type(value) is list and len(value) <= MAX_ITEMS, 'BOUNDED_ARRAY_REQUIRED')


def snapshot_id(value):
    token(value, r'[1-9][0-9]{0,18}')
    require(int(value) <= (1 << 63) - 1, 'POSITIVE_BIGINT_REQUIRED')


def stamp_ns(value):
    require(type(value) is str, 'UTC_TIMESTAMP_INVALID')
    match = STAMP.fullmatch(value)
    require(match is not None, 'UTC_TIMESTAMP_INVALID')
    try:
        date = dt.datetime(*(int(match[i]) for i in range(1, 7)), tzinfo=dt.timezone.utc)
    except ValueError:
        raise ValueError('UTC_TIMESTAMP_INVALID') from None
    return calendar.timegm(date.utctimetuple()) * SECOND + int((match[7] or '').ljust(9, '0'))


def identifiers(value, *, snapshots=False):
    array(value)
    for item in value:
        snapshot_id(item) if snapshots else token(item)
    require(len(set(value)) == len(value), 'DUPLICATE_REFERENCE_REJECTED')


def parse_json(raw):
    """Optional bounded JSON decoder; never reads a file or reports raw input."""
    def pairs(items):
        result = {}
        for key, value in items:
            require(key not in result, 'DUPLICATE_JSON_KEY_REJECTED')
            result[key] = value
        return result
    def constant(_value):
        raise ValueError('NONFINITE_JSON_REJECTED')
    require(type(raw) in (str, bytes), 'JSON_TEXT_REQUIRED')
    try:
        encoded = raw.encode('utf-8') if type(raw) is str else raw
        require(len(encoded) <= 1024 * 1024, 'JSON_SIZE_BOUND_REQUIRED')
        return json.loads(encoded.decode('utf-8'), object_pairs_hook=pairs, parse_constant=constant)
    except (UnicodeError, json.JSONDecodeError, RecursionError):
        raise ValueError('JSON_INVALID') from None


def build_plan(inventory, policy, *, now):
    """Classify normalized assertions, without verifying live metadata or changing input."""
    fields(policy, 'schemaVersion maxInventoryAgeSeconds minSnapshotAgeSeconds minimumSnapshotsToKeep')
    require(type(policy['schemaVersion']) is int and policy['schemaVersion'] == 1, 'POLICY_VERSION_REQUIRED')
    integer(policy['maxInventoryAgeSeconds'], 1, 300)
    integer(policy['minSnapshotAgeSeconds'], 1, 3650 * 86400)
    integer(policy['minimumSnapshotsToKeep'], 1)
    fields(inventory, 'schemaVersion kind scope tableId capturedAt observations currentSnapshotId snapshots refs pins files')
    require(type(inventory['schemaVersion']) is int and inventory['schemaVersion'] == 1
        and inventory['kind'] == 'iceberg-retention-inventory', 'INVENTORY_VERSION_REQUIRED')
    require(inventory['scope'] in ('SYNTHETIC_REFERENCE_FIXTURE', 'CAPTURED_TABLE_METADATA'), 'SCOPE_REQUIRED')
    token(inventory['tableId']); snapshot_id(inventory['currentSnapshotId'])
    current, captured = stamp_ns(now), stamp_ns(inventory['capturedAt'])
    observed = inventory['observations']
    fields(observed, ' '.join(FLAGS) + ' metadataBeforeId metadataAfterId metadataBeforeSha256 metadataAfterSha256')
    for flag in FLAGS:
        require(type(observed[flag]) is bool, 'BOOLEAN_REQUIRED')
    token(observed['metadataBeforeId']); token(observed['metadataAfterId'])
    token(observed['metadataBeforeSha256'], SHA); token(observed['metadataAfterSha256'], SHA)
    for group in ('snapshots', 'refs', 'pins', 'files'):
        array(inventory[group])

    snapshots, committed, files, refs, pins = {}, {}, {}, set(), set()
    edges = 0
    for item in inventory['snapshots']:
        fields(item, 'id parentId committedAt fileIds'); snapshot_id(item['id'])
        require(item['id'] not in snapshots, 'DUPLICATE_SNAPSHOT_REJECTED')
        if item['parentId'] is not None:
            snapshot_id(item['parentId'])
        identifiers(item['fileIds']); edges += len(item['fileIds'])
        committed[item['id']] = stamp_ns(item['committedAt']); snapshots[item['id']] = item
    for item in inventory['files']:
        fields(item, 'id kind'); token(item['id'])
        require(item['id'] not in files, 'DUPLICATE_FILE_REJECTED')
        require(item['kind'] in ('DATA', 'DELETE', 'MANIFEST', 'MANIFEST_LIST', 'METADATA', 'UNKNOWN'), 'FILE_KIND_INVALID')
        files[item['id']] = item
    for item in inventory['refs']:
        fields(item, 'name kind snapshotId'); token(item['name']); snapshot_id(item['snapshotId'])
        require(item['name'] not in refs, 'DUPLICATE_REF_REJECTED'); refs.add(item['name'])
        require(item['kind'] in ('TAG', 'BRANCH'), 'REF_KIND_INVALID')
    for item in inventory['pins']:
        fields(item, 'id kind snapshotIds fileIds'); token(item['id'])
        require(item['id'] not in pins, 'DUPLICATE_PIN_REJECTED'); pins.add(item['id'])
        require(item['kind'] in ('BACKUP', 'VALIDATION'), 'PIN_KIND_INVALID')
        identifiers(item['snapshotIds'], snapshots=True); identifiers(item['fileIds'])
        edges += len(item['snapshotIds']) + len(item['fileIds'])
    require(edges <= MAX_EDGES, 'GRAPH_EDGE_BOUND_REQUIRED')

    suppress = set()
    for flag in FLAGS:
        if not observed[flag]:
            suppress.add({'complete': 'INVENTORY_INCOMPLETE', 'refsComplete': 'REFS_INCOMPLETE',
                'pinsComplete': 'PINS_INCOMPLETE', 'snapshotFileClosureComplete': 'FILE_CLOSURE_INCOMPLETE',
                'writersQuiescent': 'WRITERS_NOT_QUIESCENT'}[flag])
    if observed['metadataBeforeId'] != observed['metadataAfterId'] or observed['metadataBeforeSha256'] != observed['metadataAfterSha256']:
        suppress.add('METADATA_CHANGED')
    if current < captured:
        suppress.add('CLOCK_BEFORE_INVENTORY')
    elif current - captured > policy['maxInventoryAgeSeconds'] * SECOND:
        suppress.add('STALE_INVENTORY')
    if not snapshots or inventory['currentSnapshotId'] not in snapshots:
        suppress.add('CURRENT_SNAPSHOT_MISSING')
    if any(value > captured for value in committed.values()):
        suppress.add('FUTURE_SNAPSHOT')
    if any(item['kind'] == 'UNKNOWN' for item in files.values()):
        suppress.add('UNKNOWN_FILE_KIND')
    targets = [item['snapshotId'] for item in inventory['refs']]
    targets += [sid for item in inventory['pins'] for sid in item['snapshotIds']]
    if any(sid not in snapshots for sid in targets):
        suppress.add('SNAPSHOT_REFERENCE_MISSING')
    all_file_ids = [fid for item in snapshots.values() for fid in item['fileIds']]
    all_file_ids += [fid for item in inventory['pins'] for fid in item['fileIds']]
    if any(fid not in files for fid in all_file_ids):
        suppress.add('FILE_REFERENCE_MISSING')

    # Parent links are a bounded forest in this first supported subset. A missing
    # already-expired parent is not guessed safe: it makes the plan undetermined.
    done = set()
    for sid in snapshots:
        chain, node = set(), sid
        while node is not None and node not in done:
            if node not in snapshots:
                suppress.add('PARENT_SNAPSHOT_MISSING'); break
            if node in chain:
                suppress.add('SNAPSHOT_CYCLE'); break
            chain.add(node); parent = snapshots[node]['parentId']
            if parent in snapshots and committed[parent] > committed[node]:
                suppress.add('PARENT_TIME_AFTER_CHILD')
            node = parent
        done.update(chain)

    reasons = {sid: set() for sid in snapshots}
    if not suppress:
        def protect(sid, direct, ancestor):
            first = True
            while sid is not None:
                reason = direct if first else ancestor
                if reason in reasons[sid]:
                    break
                reasons[sid].add(reason)
                first, sid = False, snapshots[sid]['parentId']
        protect(inventory['currentSnapshotId'], 'CURRENT_SNAPSHOT', 'CURRENT_ANCESTOR')
        for item in inventory['refs']:
            protect(item['snapshotId'], 'REF_SNAPSHOT', 'REF_ANCESTOR')
        for item in inventory['pins']:
            for sid in item['snapshotIds']:
                protect(sid, item['kind'] + '_PIN', item['kind'] + '_ANCESTOR')
        latest = sorted(snapshots, key=lambda sid: (committed[sid], int(sid)), reverse=True)
        for sid in latest[:policy['minimumSnapshotsToKeep']]:
            reasons[sid].add('MINIMUM_SNAPSHOT_COUNT')
        for sid in snapshots:
            if current - committed[sid] < policy['minSnapshotAgeSeconds'] * SECOND:
                reasons[sid].add('WITHIN_MINIMUM_AGE')

    entries, candidates = [], set()
    for sid in sorted(snapshots, key=int):
        if suppress:
            reasons[sid].add('UNDETERMINED_INVENTORY')
        elif not reasons[sid]:
            reasons[sid].add('OLD_DETACHED_HISTORY_ONLY'); candidates.add(sid)
        entries.append({'id': sid, 'action': 'EXPIRATION_CANDIDATE' if sid in candidates else 'KEEP', 'reasons': sorted(reasons[sid])})
    uses = {fid: set() for fid in files}
    for sid, item in snapshots.items():
        for fid in item['fileIds']:
            if fid in uses:
                uses[fid].add(sid)
    file_pins = {fid: set() for fid in files}
    for item in inventory['pins']:
        for fid in item['fileIds']:
            if fid in file_pins:
                file_pins[fid].add(item['kind'] + '_FILE_PIN')
    file_entries = []
    for fid in sorted(files):
        why = set()
        if suppress: why.add('UNDETERMINED_INVENTORY')
        if uses[fid] - candidates: why.add('RETAINED_SNAPSHOT_REFERENCE')
        if uses[fid] & candidates: why.add('CANDIDATE_SNAPSHOT_NOT_EXPIRED')
        if len(uses[fid]) > 1: why.add('SHARED_SNAPSHOT_FILE')
        why.update(file_pins[fid])
        if files[fid]['kind'] in ('METADATA', 'UNKNOWN'): why.add('METADATA_OR_UNKNOWN_ALWAYS_PROTECTED')
        if not why: why.add('UNREFERENCED_FILE_NOT_AUTHORIZED')
        file_entries.append({'id': fid, 'action': 'KEEP', 'reasons': sorted(why)})
    digest = hashlib.sha256(json.dumps(inventory, sort_keys=True, separators=(',', ':'), ensure_ascii=True, allow_nan=False).encode()).hexdigest()
    return {'schemaVersion': 1, 'kind': 'iceberg-retention-plan', 'status': 'UNDETERMINED' if suppress else 'DETERMINED',
        'inventoryScope': inventory['scope'], 'tableId': inventory['tableId'], 'inventoryCapturedAt': inventory['capturedAt'],
        'evaluatedAt': now, 'evaluationTimeProvidedByCaller': True, 'inventorySha256': digest,
        'suppressionReasons': sorted(suppress), 'snapshots': entries, 'files': file_entries,
        'snapshotCandidateCount': len(candidates), 'objectCandidateCount': 0,
        'applyEnabled': False, 'deletionExecutorImplemented': False, 'inventoryClaimsIndependentlyVerified': False}
