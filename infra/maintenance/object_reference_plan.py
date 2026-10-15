"""Pure fail-closed object reference planner. No network or deletion executor."""
import argparse
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import re
import stat


def require(value, code):
    if not value:
        raise ValueError(code)


def fields(value, expected):
    require(type(value) is dict and set(value) == set(expected.split()), 'EXACT_SCHEMA_REQUIRED')


def boolean(value):
    require(type(value) is bool, 'BOOLEAN_REQUIRED')


def array(value):
    require(type(value) is list and len(value) <= 10000, 'BOUNDED_ARRAY_REQUIRED')


def token(value, pattern):
    require(type(value) is str and re.fullmatch(pattern, value) is not None, 'TOKEN_INVALID')


def number(value, maximum=10000):
    require(type(value) is int and 0 <= value <= maximum, 'INTEGER_BOUND_REQUIRED')


def stamp(value):
    token(value, r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.[0-9]{1,9})?(?:Z|\+00:00)')
    return dt.datetime.fromisoformat(re.sub(r'(\.\d{6})\d+(?=Z|\+00:00)', r'\1', value).replace('Z', '+00:00'))


def stamp_ns(value):
    parsed = stamp(value)
    delta = parsed.replace(microsecond=0) - dt.datetime(1970, 1, 1, tzinfo=dt.timezone.utc)
    fraction = re.search(r'\.(\d{1,9})', value)
    return (delta.days * 86400 + delta.seconds) * 1_000_000_000 + int(((fraction[1] if fraction else '') + '000000000')[:9])


def identity(value):
    token(value['storeId'], r'[a-z0-9][a-z0-9-]{0,79}')
    token(value['bucket'], r'[a-z0-9][a-z0-9.-]{1,61}[a-z0-9]')
    require('..' not in value['bucket'], 'BUCKET_INVALID')
    return value['storeId'], value['bucket']


def key(value):
    token(value, r'[A-Za-z0-9][A-Za-z0-9._/-]{0,478}')
    require(not value.endswith('/') and all(part not in ('', '.', '..') for part in value.split('/')), 'KEY_TRAVERSAL_OR_EMPTY_SEGMENT_REJECTED')


def sha(value, nullable=False):
    if value is None and nullable:
        return
    token(value, r'[a-f0-9]{64}')


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=True).encode()


def build_plan(inventory, *, now):
    """Validate all claims, then classify. Collector truth/races are not verified here."""
    fields(inventory, 'schemaVersion kind scope noApplicationDatabase capturedAt database listings canaries protectedReferences')
    require(type(inventory['schemaVersion']) is int and inventory['schemaVersion'] == 1
            and inventory['kind'] == 'object-reference-inventory', 'INVENTORY_VERSION_REQUIRED')
    captured = stamp_ns(inventory['capturedAt']); current = stamp_ns(now)
    require(current >= captured, 'CLOCK_BEFORE_INVENTORY')
    boolean(inventory['noApplicationDatabase'])
    isolated = inventory['scope'] == 'ISOLATED_CANARY_REFERENCE_FIXTURE'
    require(isolated or inventory['scope'] == 'PRODUCTION_REFERENCES', 'EXPLICIT_SCOPE_REQUIRED')
    db = inventory['database']
    require((isolated and inventory['noApplicationDatabase'] is True and db is None)
            or (not isolated and inventory['noApplicationDatabase'] is False and type(db) is dict), 'SCOPE_DATABASE_FACTS_MISMATCH')
    db_store, jobs, suppress = None, {}, []
    if not isolated:
        fields(db, 'storeId bucket sourceCommit complete consistentSnapshot expectedJobCount expectedOutboxCount expectedSlotCount jobs outbox slotRunId runtimeStatus')
        db_store = identity(db); token(db['sourceCommit'], r'[a-f0-9]{40}')
        for name in ('complete', 'consistentSnapshot'):
            boolean(db[name])
        for name in ('expectedJobCount', 'expectedOutboxCount', 'expectedSlotCount'):
            number(db[name])
        for name in ('jobs', 'outbox'):
            array(db[name])
        statuses = {'STAGING', 'QUEUED', 'COMPLETED', 'TERMINATED', 'UNKNOWN'}
        exports = {'NOT_REQUESTED', 'PENDING', 'EXPORTED', 'CANCELLED', 'UNKNOWN'}
        jobs = {}
        for job in db['jobs']:
            fields(job, 'runId scenarioVersion sourceSha256 status exportStatus')
            token(job['runId'], r'[a-z0-9][a-z0-9._-]{0,79}')
            require(job['runId'] not in jobs, 'DUPLICATE_JOB_REJECTED')
            require(job['scenarioVersion'] in ('sensor-validation-v1', 'sensor-validation-v2', 'UNKNOWN')
                    and job['status'] in statuses and job['exportStatus'] in exports, 'JOB_ENUM_INVALID')
            require('UNKNOWN' in (job['status'], job['exportStatus']) or
                    (job['status'] in ('STAGING', 'QUEUED') and job['exportStatus'] == 'NOT_REQUESTED') or
                    (job['status'] == 'COMPLETED' and job['exportStatus'] in ('PENDING', 'EXPORTED', 'CANCELLED')) or
                    (job['status'] == 'TERMINATED' and job['exportStatus'] == 'NOT_REQUESTED'), 'JOB_STATE_COMBINATION_INVALID')
            sha(job['sourceSha256']); jobs[job['runId']] = job
        outbox_ids = set()
        for outbox in db['outbox']:
            fields(outbox, 'jobRunId eventType status')
            require(outbox['jobRunId'] in jobs and outbox['eventType'] in ('DISPATCH', 'EXPORT', 'UNKNOWN')
                    and outbox['status'] in ('PENDING', 'ACKNOWLEDGED', 'CANCELLED', 'UNKNOWN'), 'OUTBOX_REFERENCE_OR_ENUM_INVALID')
            outbox_id = (outbox['jobRunId'], outbox['eventType'])
            require(outbox_id not in outbox_ids, 'DUPLICATE_OUTBOX_REJECTED'); outbox_ids.add(outbox_id)
        require(db['slotRunId'] is None or db['slotRunId'] in jobs, 'SLOT_REFERENCE_INVALID')
        require(db['runtimeStatus'] in ('NOT_STARTED', 'RUNNING', 'STOPPED', 'PAUSED_OPERATOR', 'UNKNOWN'), 'RUNTIME_ENUM_INVALID')
        suppress = []
        if not db['complete'] or not db['consistentSnapshot'] or db['expectedJobCount'] != len(jobs) or db['expectedOutboxCount'] != len(db['outbox']) or db['expectedSlotCount'] != 1:
            suppress.append('DATABASE_SNAPSHOT_INCOMPLETE')
        if db['slotRunId'] is not None:
            suppress.append('EXECUTION_SLOT_OCCUPIED')
        if db['runtimeStatus'] in ('PAUSED_OPERATOR', 'UNKNOWN'):
            suppress.append('RUNTIME_PAUSED_OR_UNKNOWN')
        if any(job['status'] == 'UNKNOWN' or job['exportStatus'] == 'UNKNOWN' or job['scenarioVersion'] == 'UNKNOWN' for job in jobs.values()):
            suppress.append('UNKNOWN_DATABASE_JOB')
        if any(row['status'] in ('PENDING', 'UNKNOWN') or row['eventType'] == 'UNKNOWN' for row in db['outbox']):
            suppress.append('OUTBOX_PENDING_OR_UNKNOWN')
    if current - captured > 300_000_000_000:
        suppress.append('INVENTORY_STALE')
    array(inventory['listings']); objects = {}; listing_ids = set()
    for listing in inventory['listings']:
        fields(listing, 'storeId bucket complete objects')
        store = identity(listing); boolean(listing['complete']); array(listing['objects'])
        require(store not in listing_ids, 'DUPLICATE_LISTING_REJECTED'); listing_ids.add(store)
        if not listing['complete']:
            suppress.append('OBJECT_LISTING_INCOMPLETE')
        for obj in listing['objects']:
            fields(obj, 'key size sha256 contentVerified')
            key(obj['key']); number(obj['size'], 2**40); sha(obj['sha256'], True); boolean(obj['contentVerified'])
            require(not obj['contentVerified'] or obj['sha256'] is not None, 'VERIFIED_HASH_REQUIRED')
            ident = (*store, obj['key']); require(ident not in objects, 'DUPLICATE_OBJECT_REJECTED'); objects[ident] = obj
            require(len(objects) <= 10000, 'TOTAL_OBJECT_BOUND_REQUIRED')
    require((isolated and len(listing_ids) == 1) or (not isolated and db_store in listing_ids), 'EXACT_SCOPE_LISTING_REQUIRED')
    array(inventory['canaries']); canaries = {}
    require(isolated or not inventory['canaries'], 'PRODUCTION_CANARIES_FORBIDDEN')
    for canary in inventory['canaries']:
        fields(canary, 'storeId bucket key size sha256 deleteEligible')
        store = identity(canary); key(canary['key']); number(canary['size'], 4194304); sha(canary['sha256']); boolean(canary['deleteEligible'])
        ident = (*store, canary['key'])
        require(ident not in canaries and ident in objects and store != db_store, 'CANARY_MUST_BE_UNIQUE_LISTED_DISPOSABLE_STORE')
        canaries[ident] = canary
    array(inventory['protectedReferences']); refs = {}
    for ref in inventory['protectedReferences']:
        fields(ref, 'storeId bucket key reason'); store = identity(ref); key(ref['key'])
        require(ref['reason'] in ('BACKUP', 'EVIDENCE', 'FIXTURE_EXPORTED', 'FIXTURE_PENDING'), 'REFERENCE_REASON_INVALID')
        require(store in listing_ids and (not isolated or (*store, ref['key']) in objects), 'REFERENCE_SCOPE_REQUIRED')
        refs.setdefault((*store, ref['key']), set()).add(ref['reason'])
    plans = []
    for ident, obj in sorted(objects.items()):
        reasons = []
        if ident[:2] == db_store:
            matches = [job for run, job in jobs.items() if obj['key'].startswith('raw/' + run + '/') or obj['key'].startswith('result/' + run + '/')]
            if matches:
                reasons.append('DATABASE_RUN_REFERENCE')
                if any(job['status'] in ('STAGING', 'QUEUED') or job['exportStatus'] == 'PENDING' for job in matches):
                    reasons.append('INCOMPLETE_OR_PENDING_JOB')
            else:
                reasons.append('UNKNOWN_PRODUCTION_OBJECT_PROTECTED')
        reasons.extend('PROTECTED_' + reason for reason in sorted(refs.get(ident, ())))
        canary = canaries.get(ident)
        if canary is None:
            reasons.append('UNREGISTERED_OBJECT_PROTECTED')
        elif not canary['deleteEligible']:
            reasons.append('REGISTERED_CANARY_NOT_ELIGIBLE')
        elif obj['size'] != canary['size'] or obj['sha256'] != canary['sha256'] or not obj['contentVerified']:
            reasons.append('CANARY_IDENTITY_UNVERIFIED')
        reasons.extend(suppress)
        plans.append({'storeId': ident[0], 'bucket': ident[1], 'key': ident[2], 'size': obj['size'], 'sha256': obj['sha256'],
                      'action': 'KEEP' if reasons else 'DELETE_CANDIDATE', 'reasons': sorted(set(reasons)) or ['EXPLICIT_VERIFIED_DISPOSABLE_CANARY_ONLY']})
    return {'schemaVersion': 1, 'kind': 'object-reference-plan', 'scope': inventory['scope'], 'noApplicationDatabase': inventory['noApplicationDatabase'], 'capturedAt': inventory['capturedAt'], 'evaluatedAt': now,
            'inventorySha256': hashlib.sha256(canonical(inventory)).hexdigest(), 'applyEnabled': False,
            'deletionExecutorImplemented': False, 'collectorClaimsIndependentlyVerified': False,
            'entries': plans, 'candidateCount': sum(row['action'] == 'DELETE_CANDIDATE' for row in plans),
            'protectedCount': sum(row['action'] == 'KEEP' for row in plans)}


def no_duplicate_json(pairs):
    value = {}
    for name, item in pairs:
        require(name not in value, 'DUPLICATE_JSON_KEY_REJECTED'); value[name] = item
    return value


def main():
    parser = argparse.ArgumentParser(); parser.add_argument('--inventory', required=True, type=Path); parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args(); os.umask(0o077)
    info = args.inventory.lstat()
    require(stat.S_ISREG(info.st_mode) and info.st_uid == os.geteuid() and stat.S_IMODE(info.st_mode) == 0o600
            and args.inventory.resolve(strict=True) == args.inventory and info.st_size <= 16 * 1024**2, 'PRIVATE_INPUT_REQUIRED')
    parent = args.output.parent; pinfo = parent.lstat()
    require(parent.resolve(strict=True) == parent and stat.S_ISDIR(pinfo.st_mode) and pinfo.st_uid == os.geteuid()
            and stat.S_IMODE(pinfo.st_mode) == 0o700, 'PRIVATE_OUTPUT_PARENT_REQUIRED')
    inventory = json.loads(args.inventory.read_bytes(), object_pairs_hook=no_duplicate_json)
    plan = build_plan(inventory, now=dt.datetime.now(dt.timezone.utc).isoformat())
    fd = os.open(args.output, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, 'wb') as stream:
        stream.write(canonical(plan) + b'\n'); stream.flush(); os.fsync(stream.fileno())
    print(json.dumps({'candidateCount': plan['candidateCount'], 'protectedCount': plan['protectedCount'], 'applyEnabled': False}))


if __name__ == '__main__':
    main()
