"""Pure, deterministic retention planner. No deletion executor, network, or shell calls."""
from __future__ import annotations

import argparse
import calendar
from collections import Counter, defaultdict
import datetime as dt
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import sys
import time

UTC = dt.timezone.utc
DAY_NS = 86_400 * 1_000_000_000
SHA = re.compile(r'[a-f0-9]{64}')
UID = re.compile(r'[a-f0-9]{8}(?:-[a-f0-9]{4}){3}-[a-f0-9]{12}')
ID = re.compile(r'[a-z0-9][a-z0-9._-]{0,127}')
DNS = re.compile(r'[a-z0-9](?:[a-z0-9.-]{0,251}[a-z0-9])?')
STAMP = re.compile(r'(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2}):(\d{2})(?:\.(\d{1,9}))?(?:Z|\+00:00)')
MAX_ITEMS = 10_000
INVENTORY_FIELDS = {'schemaVersion', 'kind', 'capturedAt', 'backupRoots', 'storageRoots',
    'originalNamespaces', 'originalVolumes', 'backupGroups', 'trialGroups', 'protectedArtifacts'}
POLICY_FIELDS = {'schemaVersion', 'kind', 'minimumVerifiedPerCompatibilityFamily', 'dailyUtcDays', 'weeklyIsoWeeks',
    'trialMinimumAgeDays', 'maxInventoryAgeSeconds', 'requiredTrialPurpose', 'jobObjectDeletionEnabled', 'applyEnabled'}
PATH_FIELDS = {'path', 'resolvedPath', 'isSymlink'}
BACKUP_FIELDS = {'id', 'kind', 'compatibilityFamily', 'completedAt', 'state', 'complete', 'pinned',
    'keyAvailable', 'requiredMemberIds', 'members'}
MEMBER_FIELDS = {'id', 'role', 'path', 'resolvedPath', 'isSymlink', 'size', 'sha256', 'verified'}
TRIAL_FIELDS = {'id', 'operation', 'completedAt', 'state', 'pinned', 'original', 'namespace', 'podsPresent',
    'workloadsStopped', 'backupGroupId', 'evidenceSha256', 'evidenceVerified', 'volumes'}
VOLUME_FIELDS = {'pvcName', 'pvcUid', 'expectedPvcUid', 'namespace', 'pvName', 'pvUid', 'expectedPvUid',
    'claimRef', 'path', 'resolvedPath', 'isSymlink', 'mounted', 'bound', 'reclaimPolicy'}
SENSITIVE_ROLES = {'KEY', 'CONFIG', 'CREDENTIAL', 'UNKNOWN'}


class ValidationError(ValueError):
    """Fixed code only: raw private input values do not appear in error messages."""


def require(condition, code):
    if not condition:
        raise ValidationError(code)


def exact(value, fields):
    require(type(value) is dict and set(value) == fields, 'SCHEMA_FIELDS_INVALID')


def boolean(value):
    require(type(value) is bool, 'BOOLEAN_REQUIRED')


def integer(value, low=0, high=MAX_ITEMS):
    require(type(value) is int and low <= value <= high, 'INTEGER_RANGE_INVALID')


def text(value, pattern=ID):
    require(type(value) is str and pattern.fullmatch(value) is not None, 'STRING_FORMAT_INVALID')


def token(value, allowed):
    require(type(value) is str and value in allowed, 'ENUM_VALUE_INVALID')


def path_string(value, root=False):
    require(type(value) is str and 1 <= len(value) <= 4096 and '\\' not in value
        and all(ord(char) >= 32 and ord(char) != 127 for char in value), 'PATH_FORMAT_INVALID')
    parsed = PurePosixPath(value)
    require(parsed.is_absolute() and '..' not in parsed.parts and str(parsed) == value and value != '/', 'PATH_NOT_CANONICAL')
    if root:
        require(len(parsed.parts) >= 4, 'ROOT_TOO_BROAD')
    return parsed


def path_evidence(value, fields=PATH_FIELDS, root=False):
    exact(value, fields)
    path_string(value['path'], root=root); path_string(value['resolvedPath'], root=root); boolean(value['isSymlink'])


def timestamp(value, optional=False):
    if value is None and optional:
        return None
    require(type(value) is str, 'UTC_TIMESTAMP_REQUIRED')
    match = STAMP.fullmatch(value)
    require(match is not None, 'UTC_TIMESTAMP_INVALID')
    try:
        date = dt.datetime(*(int(match[i]) for i in range(1, 7)), tzinfo=UTC)
    except ValueError:
        raise ValidationError('UTC_TIMESTAMP_INVALID') from None
    seconds = calendar.timegm(date.utctimetuple())
    return seconds * 1_000_000_000 + int((match[7] or '').ljust(9, '0'))


def canonical_hash(value):
    encoded = json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False).encode('utf-8')
    return hashlib.sha256(encoded).hexdigest()


def sequence(value, *, nonempty=False):
    require(type(value) is list and int(nonempty) <= len(value) <= MAX_ITEMS, 'ARRAY_SIZE_INVALID')


def unique_ids(values, field='id'):
    sequence(values)
    for value in values:
        require(type(value) is dict and field in value, 'ITEM_ID_REQUIRED'); text(value[field])
    require(len({value[field] for value in values}) == len(values), 'DUPLICATE_ID')


def overlaps(left, right):
    left = PurePosixPath(left); right = PurePosixPath(right)
    return left == right or left in right.parents or right in left.parents


def validate_policy(policy):
    exact(policy, POLICY_FIELDS)
    require(type(policy['schemaVersion']) is int and policy['schemaVersion'] == 1 and policy['kind'] == 'retention-policy', 'POLICY_VERSION_INVALID')
    for field, low, high in (('minimumVerifiedPerCompatibilityFamily', 1, 100), ('dailyUtcDays', 1, 365),
        ('weeklyIsoWeeks', 1, 52), ('trialMinimumAgeDays', 7, 3650), ('maxInventoryAgeSeconds', 1, 3600)):
        integer(policy[field], low, high)
    require(policy['requiredTrialPurpose'] == 'runtime-pvc-restore', 'TRIAL_PURPOSE_INVALID')
    require(policy['jobObjectDeletionEnabled'] is False and policy['applyEnabled'] is False, 'DELETION_EXECUTOR_NOT_IMPLEMENTED')


def validate_inventory(inventory):
    exact(inventory, INVENTORY_FIELDS)
    require(type(inventory['schemaVersion']) is int and inventory['schemaVersion'] == 1 and inventory['kind'] == 'retention-inventory', 'INVENTORY_VERSION_INVALID')
    timestamp(inventory['capturedAt'])
    for group in ('backupRoots', 'storageRoots'):
        sequence(inventory[group], nonempty=True)
        for root in inventory[group]: path_evidence(root, root=True)
        paths = [root['path'] for root in inventory[group]]
        require(all(not overlaps(a, b) for index, a in enumerate(paths) for b in paths[index + 1:]), 'OVERLAPPING_ROOTS')
    require(all(not overlaps(a['path'], b['path']) for a in inventory['backupRoots'] for b in inventory['storageRoots']), 'BACKUP_STORAGE_ROOT_OVERLAP')
    sequence(inventory['originalNamespaces']); sequence(inventory['originalVolumes'])
    for namespace in inventory['originalNamespaces']:
        exact(namespace, {'name', 'uid'}); text(namespace['name'], DNS); text(namespace['uid'], UID)
    require(len({v['name'] for v in inventory['originalNamespaces']}) == len(inventory['originalNamespaces'])
        and len({v['uid'] for v in inventory['originalNamespaces']}) == len(inventory['originalNamespaces']), 'DUPLICATE_ORIGINAL_NAMESPACE')
    for volume in inventory['originalVolumes']:
        exact(volume, {'pvcUid', 'pvUid', 'path'}); text(volume['pvcUid'], UID); text(volume['pvUid'], UID); path_string(volume['path'])
    require(len({v['pvcUid'] for v in inventory['originalVolumes']}) == len(inventory['originalVolumes'])
        and len({v['pvUid'] for v in inventory['originalVolumes']}) == len(inventory['originalVolumes']), 'DUPLICATE_ORIGINAL_VOLUME')
    unique_ids(inventory['backupGroups']); unique_ids(inventory['trialGroups']); unique_ids(inventory['protectedArtifacts'])
    for backup in inventory['backupGroups']:
        exact(backup, BACKUP_FIELDS); text(backup['compatibilityFamily'])
        token(backup['kind'], {'DB', 'K3S', 'JENKINS', 'RUNTIME', 'UNKNOWN'}); token(backup['state'], {'VERIFIED', 'FAILED', 'UNKNOWN'})
        require(backup['kind'] != 'UNKNOWN' or backup['state'] == 'UNKNOWN', 'UNKNOWN_BACKUP_KIND_CANNOT_BE_VERIFIED')
        timestamp(backup['completedAt'], optional=True)
        for field in ('complete', 'pinned', 'keyAvailable'): boolean(backup[field])
        sequence(backup['requiredMemberIds'])
        for member_id in backup['requiredMemberIds']: text(member_id)
        require(len(set(backup['requiredMemberIds'])) == len(backup['requiredMemberIds']), 'DUPLICATE_REQUIRED_MEMBER')
        unique_ids(backup['members'])
        for member in backup['members']:
            path_evidence(member, MEMBER_FIELDS); token(member['role'], {'ARCHIVE', 'VERIFICATION', 'MANIFEST', *SENSITIVE_ROLES})
            integer(member['size'], 1, 1 << 50); text(member['sha256'], SHA); boolean(member['verified'])
    for trial in inventory['trialGroups']:
        exact(trial, TRIAL_FIELDS); timestamp(trial['completedAt'], optional=True)
        token(trial['state'], {'STOPPED', 'RUNNING', 'PENDING', 'PAUSED', 'UNKNOWN'})
        text(trial['operation'], re.compile(r'\d{8}'))
        try: dt.datetime.strptime(trial['operation'], '%Y%m%d')
        except ValueError: raise ValidationError('TRIAL_OPERATION_DATE_INVALID') from None
        for field in ('pinned', 'original', 'workloadsStopped', 'evidenceVerified'): boolean(trial[field])
        integer(trial['podsPresent'])
        if trial['backupGroupId'] is not None: text(trial['backupGroupId'])
        if trial['evidenceSha256'] is not None: text(trial['evidenceSha256'], SHA)
        namespace = trial['namespace']; exact(namespace, {'name', 'uid', 'expectedUid', 'labels'})
        text(namespace['name'], DNS); text(namespace['uid'], UID); text(namespace['expectedUid'], UID)
        require(type(namespace['labels']) is dict and len(namespace['labels']) <= 32
            and all(type(k) is str and type(v) is str and len(k) <= 253 and len(v) <= 128 for k, v in namespace['labels'].items()), 'NAMESPACE_LABELS_INVALID')
        sequence(trial['volumes'], nonempty=True)
        for volume in trial['volumes']:
            path_evidence(volume, VOLUME_FIELDS)
            for field in ('pvcName', 'namespace', 'pvName'): text(volume[field], DNS)
            for field in ('pvcUid', 'pvUid', 'expectedPvcUid', 'expectedPvUid'): text(volume[field], UID)
            for field in ('mounted', 'bound'): boolean(volume[field])
            token(volume['reclaimPolicy'], {'Retain', 'Delete', 'UNKNOWN'})
            exact(volume['claimRef'], {'name', 'namespace', 'uid'})
            text(volume['claimRef']['name'], DNS); text(volume['claimRef']['namespace'], DNS); text(volume['claimRef']['uid'], UID)
        require(len({v['pvcName'] for v in trial['volumes']}) == len(trial['volumes']), 'DUPLICATE_TRIAL_VOLUME')
    for artifact in inventory['protectedArtifacts']:
        exact(artifact, {'id', 'kind', 'state', 'path'})
        token(artifact['kind'], {'KEY', 'CONFIG', 'CREDENTIAL', 'JOB', 'RAW', 'EXPORT', 'UNKNOWN'})
        token(artifact['state'], {'LIVE', 'PENDING', 'PAUSED', 'COMPLETED', 'UNKNOWN'})
        if artifact['path'] is not None: path_string(artifact['path'])


def safe_path(value, roots):
    if value['isSymlink'] or value['path'] != value['resolvedPath']:
        return False
    return any(not root['isSymlink'] and root['path'] == root['resolvedPath']
        and PurePosixPath(root['path']) in PurePosixPath(value['path']).parents for root in roots)


def backup_guards(backup, inventory, now_ns, fresh):
    reasons = set()
    if not fresh: reasons.add('STALE_INVENTORY')
    if backup['state'] != 'VERIFIED': reasons.add('STATE_' + backup['state'])
    if backup['pinned']: reasons.add('PINNED')
    if not backup['keyAvailable']: reasons.add('KEY_UNAVAILABLE')
    completed = timestamp(backup['completedAt'], optional=True)
    if completed is None: reasons.add('COMPLETION_TIME_UNKNOWN')
    elif completed > now_ns: reasons.add('FUTURE_COMPLETION')
    members = backup['members']; roles = Counter(member['role'] for member in members)
    if (not backup['complete'] or not members or set(backup['requiredMemberIds']) != {member['id'] for member in members}
        or roles['ARCHIVE'] != 1 or roles['VERIFICATION'] < 1):
        reasons.add('INCOMPLETE_GROUP')
    if any(not member['verified'] for member in members): reasons.add('MEMBER_UNVERIFIED')
    if any(member['role'] in SENSITIVE_ROLES for member in members): reasons.add('SENSITIVE_OR_UNKNOWN_MEMBER')
    if any(not safe_path(member, inventory['backupRoots']) for member in members): reasons.add('UNSAFE_BACKUP_PATH')
    protected = [artifact['path'] for artifact in inventory['protectedArtifacts'] if artifact['path'] is not None]
    if any(overlaps(member['path'], path) for member in members for path in protected): reasons.add('PROTECTED_ARTIFACT_OVERLAP')
    if any(overlaps(member['resolvedPath'], original['path']) for member in members for original in inventory['originalVolumes']):
        reasons.add('ORIGINAL_STORAGE_OVERLAP')
    return reasons


def build_plan(inventory, policy, *, now):
    """Validate exact v1 input and return a new plan without reading paths or changing input."""
    validate_policy(policy); validate_inventory(inventory)
    now_ns = timestamp(now); captured = timestamp(inventory['capturedAt'])
    require(now_ns >= captured, 'CLOCK_BEFORE_INVENTORY')
    fresh = now_ns - captured <= policy['maxInventoryAgeSeconds'] * 1_000_000_000
    backups = sorted(inventory['backupGroups'], key=lambda item: item['id'])
    guards = {backup['id']: backup_guards(backup, inventory, now_ns, fresh) for backup in backups}
    # A pinned but otherwise healthy verified backup may still be the family anchor.
    healthy = [backup for backup in backups if not guards[backup['id']] - {'PINNED'}]
    families = defaultdict(list)
    for backup in healthy: families[(backup['kind'], backup['compatibilityFamily'])].append(backup)
    retained = defaultdict(set)
    today = dt.datetime.fromtimestamp(now_ns // 1_000_000_000, UTC).date()
    week_start = today - dt.timedelta(days=today.weekday())
    for family, values in families.items():
        ordered = sorted(values, key=lambda item: (-timestamp(item['completedAt']), item['id']))
        for backup in ordered[:policy['minimumVerifiedPerCompatibilityFamily']]: retained[backup['id']].add('LATEST_VERIFIED_FAMILY')
        days = {}; weeks = {}
        for backup in ordered:
            if now_ns - timestamp(backup['completedAt']) < policy['dailyUtcDays'] * DAY_NS:
                retained[backup['id']].add('RECENT_BACKUP_WINDOW')
            date = dt.datetime.fromtimestamp(timestamp(backup['completedAt']) // 1_000_000_000, UTC).date()
            if 0 <= (today - date).days < policy['dailyUtcDays']: days.setdefault(date, backup)
            start = date - dt.timedelta(days=date.weekday())
            if 0 <= (week_start - start).days // 7 < policy['weeklyIsoWeeks']: weeks.setdefault(start, backup)
        for backup in days.values(): retained[backup['id']].add('DAILY_REPRESENTATIVE')
        for backup in weeks.values(): retained[backup['id']].add('WEEKLY_REPRESENTATIVE')
    # Never split a shared file or remove a checkpoint referenced by any trial.
    path_groups = defaultdict(set)
    for backup in backups:
        for member in backup['members']: path_groups[member['resolvedPath']].add(backup['id'])
    for groups in path_groups.values():
        if len(groups) > 1:
            for backup_id in groups: guards[backup_id].add('SHARED_BACKUP_MEMBER')
    paths = list(path_groups)
    for index, left in enumerate(paths):
        for right in paths[index + 1:]:
            if overlaps(left, right):
                for backup_id in path_groups[left] | path_groups[right]: guards[backup_id].add('SHARED_BACKUP_MEMBER')
    by_id = {backup['id']: backup for backup in backups}
    for trial in inventory['trialGroups']:
        if trial['backupGroupId'] in by_id: retained[trial['backupGroupId']].add('TRIAL_BACKUP_DEPENDENCY')
    backup_decisions = []
    healthy_ids = {backup['id'] for backup in healthy}
    for backup in backups:
        reasons = guards[backup['id']] | retained[backup['id']]
        if (backup['kind'], backup['compatibilityFamily']) not in families: reasons.add('NO_HEALTHY_VERIFIED_FAMILY_ANCHOR')
        candidate = not reasons
        backup_decisions.append({'id': backup['id'], 'kind': backup['kind'], 'compatibilityFamily': backup['compatibilityFamily'],
            'action': 'DELETE_CANDIDATE' if candidate else 'KEEP', 'reasons': ['OUTSIDE_RETENTION_WINDOWS'] if candidate else sorted(reasons),
            'preconditions': {'completedAt': backup['completedAt'], 'membersManifestSha256': canonical_hash(backup['members']),
                'members': [{key: member[key] for key in ('id', 'path', 'resolvedPath', 'size', 'sha256')} for member in sorted(backup['members'], key=lambda value: value['id'])]} if candidate else {}})
    original_ns = {item['name'] for item in inventory['originalNamespaces']}
    original_ns_uids = {item['uid'] for item in inventory['originalNamespaces']}
    original_pvc = {item['pvcUid'] for item in inventory['originalVolumes']}
    original_pv = {item['pvUid'] for item in inventory['originalVolumes']}
    original_paths = [item['path'] for item in inventory['originalVolumes']]
    trial_decisions = []
    all_trial_volumes = [(trial['id'], volume) for trial in inventory['trialGroups'] for volume in trial['volumes']]
    for trial in sorted(inventory['trialGroups'], key=lambda value: value['id']):
        reasons = set(); namespace = trial['namespace']; completed = timestamp(trial['completedAt'], optional=True)
        if not fresh: reasons.add('STALE_INVENTORY')
        if trial['pinned']: reasons.add('PINNED')
        if trial['state'] != 'STOPPED': reasons.add('STATE_' + trial['state'])
        if trial['podsPresent'] or not trial['workloadsStopped']: reasons.add('LIVE_OR_UNKNOWN_WORKLOAD')
        if completed is None: reasons.add('COMPLETION_TIME_UNKNOWN')
        elif completed > now_ns: reasons.add('FUTURE_COMPLETION')
        elif now_ns - completed < policy['trialMinimumAgeDays'] * DAY_NS: reasons.add('MINIMUM_AGE_NOT_MET')
        if trial['original'] or namespace['name'] in original_ns or namespace['uid'] in original_ns_uids: reasons.add('ORIGINAL_RESOURCE')
        if namespace['uid'] != namespace['expectedUid']: reasons.add('NAMESPACE_UID_CHANGED')
        if (namespace['labels'].get('devdooly.io/purpose') != policy['requiredTrialPurpose']
            or namespace['labels'].get('devdooly.io/operation') != trial['operation']): reasons.add('OWNERSHIP_UNVERIFIED')
        if trial['backupGroupId'] not in healthy_ids: reasons.add('VERIFIED_BACKUP_UNAVAILABLE')
        if not trial['evidenceVerified'] or trial['evidenceSha256'] is None: reasons.add('VERIFIED_EVIDENCE_UNAVAILABLE')
        for volume in trial['volumes']:
            if (volume['pvcUid'] in original_pvc or volume['pvUid'] in original_pv
                or any(overlaps(volume['resolvedPath'], path) for path in original_paths)): reasons.add('ORIGINAL_STORAGE_OVERLAP')
            if (volume['pvcUid'] != volume['expectedPvcUid'] or volume['pvUid'] != volume['expectedPvUid']
                or volume['namespace'] != namespace['name'] or volume['claimRef'] != {'name': volume['pvcName'], 'namespace': namespace['name'], 'uid': volume['pvcUid']}):
                reasons.add('VOLUME_IDENTITY_OR_BINDING_CHANGED')
            if not volume['bound'] or volume['reclaimPolicy'] != 'Retain': reasons.add('VOLUME_STATE_UNVERIFIED')
            if volume['mounted']: reasons.add('MOUNTED_VOLUME')
            if not safe_path(volume, inventory['storageRoots']): reasons.add('UNSAFE_TRIAL_PATH')
            for other_id, other in all_trial_volumes:
                if other is not volume and (volume['pvcUid'] == other['pvcUid'] or volume['pvUid'] == other['pvUid']
                    or overlaps(volume['resolvedPath'], other['resolvedPath'])): reasons.add('SHARED_TRIAL_STORAGE')
        candidate = not reasons
        trial_decisions.append({'id': trial['id'], 'action': 'DELETE_CANDIDATE' if candidate else 'KEEP',
            'reasons': ['EXPIRED_STOPPED_VERIFIED_TRIAL'] if candidate else sorted(reasons),
            'preconditions': {'namespace': {'name': namespace['name'], 'uid': namespace['uid'], 'labels': dict(sorted(namespace['labels'].items()))},
                'completedAt': trial['completedAt'], 'backupGroupId': trial['backupGroupId'], 'evidenceSha256': trial['evidenceSha256'],
                'backupMembersManifestSha256': canonical_hash(by_id[trial['backupGroupId']]['members']),
                'volumes': json.loads(json.dumps(sorted(trial['volumes'], key=lambda value: value['pvcName'])))} if candidate else {}})
    protected = [{'id': item['id'], 'kind': item['kind'], 'action': 'KEEP',
        'reasons': ['NO_JOB_OBJECT_GC_PROTOCOL' if item['kind'] in {'JOB', 'RAW', 'EXPORT'} else 'ALWAYS_PROTECTED_ARTIFACT']}
        for item in sorted(inventory['protectedArtifacts'], key=lambda value: value['id'])]
    return {'schemaVersion': 1, 'kind': 'retention-plan', 'dryRun': True, 'deletionExecutorImplemented': False,
        'plannedAt': now, 'inventoryCapturedAt': inventory['capturedAt'], 'inventoryFresh': fresh,
        'inventorySha256': canonical_hash(inventory), 'policySha256': canonical_hash(policy),
        'backupGroups': backup_decisions, 'trialGroups': trial_decisions, 'protectedArtifacts': protected,
        'summary': {'backupGroups': len(backup_decisions), 'backupCandidates': sum(item['action'] == 'DELETE_CANDIDATE' for item in backup_decisions),
            'trialGroups': len(trial_decisions), 'trialCandidates': sum(item['action'] == 'DELETE_CANDIDATE' for item in trial_decisions),
            'protectedArtifacts': len(protected), 'applyImplemented': False}}


def strict_json(raw):
    require(type(raw) in (bytes, str) and len(raw) <= 16_777_216, 'INPUT_SIZE_INVALID')
    def pairs(values):
        result = {}
        for key, value in values:
            require(key not in result, 'DUPLICATE_JSON_KEY'); result[key] = value
        return result
    def invalid_constant(unused): raise ValidationError('NONFINITE_JSON_NUMBER')
    try:
        return json.loads(raw, object_pairs_hook=pairs, parse_constant=invalid_constant)
    except (json.JSONDecodeError, UnicodeDecodeError):
        raise ValidationError('JSON_INVALID') from None


def read_private_inventory(path):
    require(not path.is_symlink(), 'INVENTORY_SYMLINK_REJECTED')
    info = path.stat()
    require(stat.S_ISREG(info.st_mode) and info.st_nlink == 1 and info.st_size <= 16_777_216, 'INVENTORY_FILE_INVALID')
    if os.name == 'posix': require(not info.st_mode & 0o077, 'INVENTORY_PERMISSIONS_TOO_OPEN')
    return strict_json(path.read_bytes())


def system_utc_now():
    seconds, nanos = divmod(time.time_ns(), 1_000_000_000)
    return dt.datetime.fromtimestamp(seconds, UTC).strftime('%Y-%m-%dT%H:%M:%S') + f'.{nanos:09d}Z'


def main(argv=None):
    parser = argparse.ArgumentParser(description='Plan only; no deletion executor exists.')
    parser.add_argument('--inventory', required=True, type=Path)
    parser.add_argument('--policy', type=Path, default=Path(__file__).with_name('policy.json'))
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--now', help='Explicit UTC clock; marks this plan HYPOTHETICAL. Never an apply approval.')
    args = parser.parse_args(argv)
    try:
        inventory = read_private_inventory(args.inventory)
        policy = strict_json(args.policy.read_bytes())
        now = args.now or system_utc_now()
        plan = build_plan(inventory, policy, now=now)
        plan['clockSource'] = 'EXPLICIT_HYPOTHETICAL' if args.now is not None else 'SYSTEM_UTC'
        parent = args.output.parent
        require(parent.is_dir() and not parent.is_symlink(), 'OUTPUT_DIRECTORY_INVALID')
        if os.name == 'posix': require(not parent.stat().st_mode & 0o077, 'OUTPUT_DIRECTORY_PERMISSIONS_TOO_OPEN')
        fd = os.open(args.output, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, 'O_NOFOLLOW', 0), 0o600)
        with os.fdopen(fd, 'wb') as output:
            output.write((json.dumps(plan, sort_keys=True, indent=2, ensure_ascii=False) + '\n').encode('utf-8'))
            output.flush(); os.fsync(output.fileno())
        print(json.dumps({'schemaVersion': 1, 'kind': 'retention-plan-summary', 'dryRun': True,
            'clockSource': plan['clockSource'], 'inventoryFresh': plan['inventoryFresh'], **plan['summary']}))
        return 0
    except (ValidationError, OSError) as failure:
        code = str(failure) if isinstance(failure, ValidationError) else 'PRIVATE_FILE_IO_FAILED'
        print(json.dumps({'schemaVersion': 1, 'kind': 'retention-plan-error', 'dryRun': True, 'code': code}))
        return 1


if __name__ == '__main__':
    sys.exit(main())
