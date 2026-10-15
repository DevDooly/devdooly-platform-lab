"""Host-only strict allowlist for actual deployed job observation HTTP records."""
from __future__ import annotations

from datetime import datetime, timezone
import re

from platform_contract import InvalidObservation, commit, exact, integer, moment, require

MAX_JOB_SNAPSHOT = 32 * 1024
RUNTIME_FAILURES = frozenset({'PUBLISH_FAILED', 'EXPORT_FAILED', 'RUNTIME_FAILED', 'INTERRUPTED', 'LEASE_LOST',
    'INVALID_MESSAGE', 'SOURCE_UNAVAILABLE', 'SOURCE_INVALID', 'JOB_REJECTED', 'PROCESSING_FAILED',
    'OFFSET_COMMIT_FAILED', 'POLL_FAILED', 'OPERATOR_RESUME_REQUIRED', 'RESOURCE_CLOSE_FAILED'})

def token(value, choices):
    require(isinstance(value, str) and value in choices)
    return value

def run_id(value):
    require(isinstance(value, str) and re.fullmatch(r'[a-z0-9][a-z0-9._-]{0,79}', value) is not None)
    return value

def nullable_time(value, ceiling):
    return None if value is None else moment(value, ceiling)

def precise_ns(value):
    when, fraction = value
    elapsed = when - datetime(1970, 1, 1, tzinfo=timezone.utc)
    return (elapsed.days * 86400 + elapsed.seconds) * 1_000_000_000 + fraction

def file_record(value):
    exact(value, {'sha256', 'size'})
    require(isinstance(value['sha256'], str) and re.fullmatch(r'[a-f0-9]{64}', value['sha256']) is not None)
    integer(value['size'], 1, 4_194_304)

def validate_job_snapshot(value, now=None):
    """Only MINI_PC/DEPLOYED_RUNTIME is eligible for automated publication."""
    ceiling = now or datetime.now(timezone.utc)
    exact(value, {'schemaVersion', 'kind', 'capturedAt', 'environment', 'sourceCommit', 'synthetic', 'scope',
                  'publicExecutionEnabled', 'runtime', 'slot', 'jobs'})
    require(type(value['schemaVersion']) is int and value['schemaVersion'] == 1 and value['kind'] == 'job-observation')
    captured = moment(value['capturedAt'], ceiling)
    require(value['environment'] == 'MINI_PC' and value['scope'] == 'DEPLOYED_RUNTIME'
            and value['synthetic'] is True and value['publicExecutionEnabled'] is False)
    commit(value['sourceCommit'])
    runtime = exact(value['runtime'], {'status', 'stage', 'failureCode', 'startedAt', 'heartbeatAt', 'stoppedAt', 'sourceCommit', 'stale'})
    status = token(runtime['status'], {'NOT_STARTED', 'RUNNING', 'PAUSED_OPERATOR', 'STOPPED'})
    stage = token(runtime['stage'], {'IDLE', 'PUBLISH', 'CONSUME', 'EXPORT', 'STOPPED'})
    failure = runtime['failureCode']
    require(failure is None or (isinstance(failure, str) and failure in RUNTIME_FAILURES))
    if runtime['sourceCommit'] != 'unknown': commit(runtime['sourceCommit'])
    require(type(runtime['stale']) is bool)
    started = nullable_time(runtime['startedAt'], captured)
    heartbeat = nullable_time(runtime['heartbeatAt'], captured)
    stopped = nullable_time(runtime['stoppedAt'], captured)
    if status == 'NOT_STARTED':
        require(stage == 'IDLE' and failure is None and started is None and heartbeat is None and stopped is None and runtime['stale'] is False)
    else:
        require(started is not None and heartbeat is not None and started <= heartbeat)
        commit(runtime['sourceCommit'])
        if status == 'RUNNING':
            require(stage != 'STOPPED' and failure is None and stopped is None)
            require(runtime['stale'] == (precise_ns(captured) - precise_ns(heartbeat) > 300_000_000_000))
        else:
            require(stopped is not None and heartbeat <= stopped and runtime['stale'] is False)
            if status == 'STOPPED': require(stage == 'STOPPED' and failure is None)
            else: require(failure is not None and (stage != 'STOPPED' or failure == 'RESOURCE_CLOSE_FAILED'))
    slot = exact(value['slot'], {'occupiedRunId'})
    if slot['occupiedRunId'] is not None: run_id(slot['occupiedRunId'])
    jobs = value['jobs']
    require(isinstance(jobs, list) and len(jobs) <= 20)
    identities = set()
    for job in jobs:
        exact(job, {'runId', 'status', 'exportStatus', 'createdAt', 'sourceVerifiedAt', 'queuedAt', 'completedAt',
                    'exportCompletedAt', 'terminatedAt', 'counts', 'files', 'fileEvidence'})
        identity = run_id(job['runId']); require(identity not in identities); identities.add(identity)
        job_status = token(job['status'], {'STAGING', 'QUEUED', 'COMPLETED', 'TERMINATED'})
        export = token(job['exportStatus'], {'NOT_REQUESTED', 'PENDING', 'EXPORTED', 'CANCELLED'})
        evidence = token(job['fileEvidence'], {'NOT_AVAILABLE', 'EXPECTED_FROM_DB', 'VERIFIED_AT_EXPORT_COMMIT'})
        created = moment(job['createdAt'], captured)
        verified = nullable_time(job['sourceVerifiedAt'], captured); queued = nullable_time(job['queuedAt'], captured)
        completed = nullable_time(job['completedAt'], captured); exported = nullable_time(job['exportCompletedAt'], captured)
        terminated = nullable_time(job['terminatedAt'], captured)
        require((verified is None) == (queued is None))
        if verified is not None: require(job['sourceVerifiedAt'] == job['queuedAt'] and created <= verified)
        if completed is not None: require(queued is not None and queued <= completed)
        if exported is not None: require(completed is not None and completed <= exported)
        if terminated is not None: require((completed or created) <= terminated)
        counts, files = job['counts'], job['files']
        if counts is not None:
            exact(counts, {'input', 'success', 'failure', 'duplicate', 'pending'})
            for count in counts.values(): integer(count, 0, 1000)
            require(counts['input'] == sum(counts[key] for key in ('success', 'failure', 'duplicate', 'pending')))
        if files is not None:
            exact(files, {'result', 'failures'}); file_record(files['result']); file_record(files['failures'])
        if job_status == 'COMPLETED':
            require(completed is not None and counts is not None)
            if export == 'PENDING': require(files is not None and evidence == 'EXPECTED_FROM_DB' and exported is None and terminated is None)
            elif export == 'EXPORTED': require(files is not None and evidence == 'VERIFIED_AT_EXPORT_COMMIT' and exported is not None and terminated is None)
            else: require(export == 'CANCELLED' and files is None and evidence == 'NOT_AVAILABLE' and exported is None and terminated is not None)
        else:
            require(completed is None and exported is None and export == 'NOT_REQUESTED' and counts is None and files is None and evidence == 'NOT_AVAILABLE')
            if job_status == 'TERMINATED': require(terminated is not None)
            else: require(terminated is None and (queued is None if job_status == 'STAGING' else queued is not None))
    return value
