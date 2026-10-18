"""Same-run proof and stopped-actor checks; no start/stop or network calls here."""
from contextlib import contextmanager
import hashlib
import json
import math
import os
from pathlib import Path
import re
import stat
import time

PRODUCER = '73e2293210aba3d9522013d923f8d97bd292baa4623736239d55cc21d9321fe2'
RUNTIME = 'c63aded0a891bb66cb1fb2de591d67e237467681eb4a4e5a337b9d1d1b02d5e8'
OBSERVER = '801f6aa7bbe7717ff26a9d925478d7608256741537cf6f0cf52381ccaca0c4c3'
ROLES = {'postgres', 'garage', 'spark', 'trino', 'reader'}
NAMES = ('jdbc-01-before-trino', 'jdbc-02-after-trino-selects', 'jdbc-03-final')


def require(value, code):
    if not value: raise ValueError(code)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def encoded(value):
    return (json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False) + '\n').encode()


def strict(raw):
    def pairs(items):
        value = {}
        for key, item in items:
            require(key not in value, 'DUPLICATE_PROOF_FIELD')
            value[key] = item
        return value
    def finite(text):
        value = float(text); require(math.isfinite(value), 'FINITE_PROOF_NUMBER_REQUIRED'); return value
    return json.loads(raw.decode('utf-8'), object_pairs_hook=pairs,
        parse_float=finite, parse_constant=lambda _: require(False, 'FINITE_PROOF_NUMBER_REQUIRED'))


def read_proof(path, maximum=65536):
    path = Path(path)
    require(path.is_absolute() and path.parent.resolve(strict=True) == path.parent,
        'CANONICAL_PROOF_PARENT_REQUIRED')
    first = path.lstat()
    require(stat.S_ISREG(first.st_mode) and first.st_nlink == 1 and 0 < first.st_size <= maximum,
        'BOUNDED_REGULAR_SINGLE_LINK_PROOF_REQUIRED')
    with os.fdopen(os.open(path, os.O_RDONLY | (os.O_NOFOLLOW if os.name == 'posix' else 0)), 'rb') as stream:
        opened = os.fstat(stream.fileno()); raw = stream.read(maximum + 1); held = os.fstat(stream.fileno())
    last = path.lstat()
    key = lambda s: (s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns)
    require(key(first) == key(opened) == key(held) == key(last) and len(raw) == first.st_size
        and first.st_ctime_ns == last.st_ctime_ns and opened.st_ctime_ns == held.st_ctime_ns,
        'PROOF_IDENTITY_CHANGED')
    return {'raw': raw, 'sha256': sha(raw)}


def remaining(module, seen, reserve=0):
    clock = seen.attempt.deadline
    require(type(clock) is module.Deadline and clock is seen.deadline
        and clock.started == seen.deadline_started and clock.now is seen.deadline_now is time.monotonic,
        'ORIGINAL_CLOCK_TYPE_OR_IDENTITY_CHANGED')
    return clock.remaining(60, reserve)


@contextmanager
def clamped_original_reads(module, seen, reserve):
    """Post-main only; preserve original fullspec reader and clamp every child."""
    attempt = seen.attempt
    require('command' not in attempt.__dict__, 'NO_EXISTING_INSTANCE_COMMAND_OVERRIDE')
    original = attempt.command
    expected_ids = {value['id'] for value in attempt.bound.values()}
    fixed = [
        ['docker', 'ps', '-aq', '--no-trunc', '--filter', 'label=com.docker.compose.project=' + attempt.project],
        ['docker', 'network', 'inspect', attempt.project + '_trial'],
        ['docker', 'inspect', attempt.initializer_name],
        ['docker', 'ps', '-aq', '--no-trunc', '--filter', 'name=^/' + attempt.initializer_name + '$']]
    def bounded(args, timeout=60, sensitive=False, check=True):
        require(type(args) is list and (args in fixed or len(args) == 3
            and args[:2] == ['docker', 'inspect'] and args[2] in expected_ids),
            'ONLY_ORIGINAL_FIXED_FULLSPEC_READ_COMMANDS')
        require(type(timeout) in (int, float) and math.isfinite(timeout) and timeout > 0,
            'FINITE_ORIGINAL_READ_TIMEOUT')
        result = original(args, timeout=min(timeout, remaining(module, seen, reserve)),
            sensitive=sensitive, check=check)
        remaining(module, seen, reserve)
        return result
    attempt.command = bounded
    failed = False
    try:
        yield
    except BaseException:
        failed = True
        raise
    finally:
        drift = attempt.command is not bounded
        del attempt.command
        if drift and not failed: raise ValueError('POST_MAIN_READ_COMMAND_HOOK_DRIFT')


def stopped_snapshot(module, seen, clock_proof, captured_at, authority_source_sha, reserve=40):
    """Uses original fullspec guards; never accepts a missing role as stopped."""
    remaining(module, seen, reserve)
    attempt = seen.attempt
    expected = {role: value['id'] for role, value in attempt.bound.items()}
    require(set(expected) == ROLES and attempt.started_roles == ROLES, 'EXACT_FIVE_STARTED_AND_BOUND_ROLES')
    with clamped_original_reads(module, seen, reserve):
        actual = attempt.containers()
    require(len(actual) == 5 and {v['role'] for v in actual} == ROLES,
        'ALL_FIVE_EXACT_OWN_ROLES_MUST_EXIST')
    result = []
    for value in sorted(actual, key=lambda item: item['role']):
        role = value['role']
        require(value['id'] == expected[role] and re.fullmatch('[a-f0-9]{64}', value['id'])
            and value['running'] is False and type(value['pid']) is int and value['pid'] == 0
            and value['oom'] is False and type(value['exitCode']) is int,
            'EXACT_KNOWN_CONTAINER_STOP_REQUIRED')
        if role in ('spark', 'reader'):
            require(value['exitCode'] == 0, 'NORMAL_SPARK_AND_READER_EXIT_REQUIRED')
        if role == 'trino': module.normal_exit(role, value, attempt.trino_stop)
        result.append({**value, 'configBindingSha256': sha(encoded(attempt.bound[role]))})
    cid_proof = read_proof(attempt.root / 'initializer.cid', 65)
    cid = cid_proof['raw'].removesuffix(b'\n').decode('ascii')
    require(re.fullmatch('[a-f0-9]{64}', cid) and attempt.initializer_intended is True,
        'ORIGINAL_INITIALIZER_FULL_CID_REQUIRED')
    # Original API returns four fields; no initializer PID/fullspec claim.
    with clamped_original_reads(module, seen, reserve):
        initializer = attempt.initializer()
    require(initializer is not None and initializer['id'] == cid and initializer['running'] is False
        and type(initializer['exitCode']) is int and initializer['exitCode'] == 0
        and initializer['oom'] is False, 'EXACT_ORIGINAL_INITIALIZER_NORMAL_STOP_REQUIRED')
    clock = strict(clock_proof['raw'])
    require(set(clock) == {'startedMonotonic', 'hostBootId', 'budgetSeconds'}
        and clock['startedMonotonic'] == seen.deadline_started and type(clock['budgetSeconds']) is int
        and clock['budgetSeconds'] == 600
        and clock['hostBootId'] == Path('/proc/sys/kernel/random/boot_id').read_text('ascii').strip(),
        'ORIGINAL_SAME_BOOT_SINGLE_CLOCK_REQUIRED')
    remaining(module, seen, reserve)
    return {'schemaVersion': 1, 'scope': 'PRE_DECODER_EXACT_STOPPED_FRESH_CLOUD_ACTORS',
        'authoritySourceSha256': authority_source_sha,
        'sourceCommit': seen.source_commit, 'producerSha256': PRODUCER, 'runtimeManifestSha256': RUNTIME,
        'observerManifestSha256': OBSERVER, 'project': attempt.project, 'attemptRoot': str(attempt.root),
        'capturedAt': captured_at, 'monotonic': time.monotonic(), 'hostBootId': clock['hostBootId'],
        'clockSha256': clock_proof['sha256'], 'roles': result, 'initializer': initializer,
        'originalRoleStopCallsAdded': 0, 'originalInitializerStopCallsAdded': 0}


def validate_producer(module, seen, main_return, observer_folder, summary_path, authority_source_sha):
    require(type(main_return) is int and main_return == 0, 'ORIGINAL_MAIN_RETURN_ZERO_REQUIRED')
    require(seen.make_completed == 1 and seen.jdbc_completed == 3, 'ALL_ORIGINAL_NAMED_CALLS_REQUIRED')
    summary = read_proof(summary_path)
    value = strict(summary['raw'])
    checks = {'frozenInputs', 'vendor', 'pinnedImages', 'freshPhysicalVolumes', 'actualMemAvailable7Gi',
        'internalNetwork', 'singleClock', 'normalSparkExit', 'normalTrinoExit', 'pythonReaderExit',
        'jdbcAndWholeObjectsUnchanged'}
    require(value['sourceCommit'] == seen.source_commit and value['passed'] is True
        and value['ownedContainersStopped'] is True and value['ownedInitializerStopped'] is True
        and type(value['workloadElapsedMillis']) is int and 0 <= value['workloadElapsedMillis'] <= 600000
        and type(value['checks']) is dict and set(value['checks']) == checks
        and all(v is True for v in value['checks'].values())
        and value['cleanupDiagnostics'] == {'initializer': 'STOPPED_VERIFIED', 'containers': 'STOPPED_VERIFIED'},
        'SAME_RUN_PRODUCER_SUCCESS_AND_CLEANUP_REQUIRED')
    root = seen.attempt.root
    proofs = {key: read_proof(root / 'proof' / filename) for key, filename in (
        ('sparkResult', 'trial9-spark-result.json'), ('sparkDiagnostic', 'trial9-spark-diagnostic.json'),
        ('readerResult', 'reader-result.json'), ('clock', 'clock.json'))}
    proofs['trinoStopIntent'] = read_proof(root / 'trino-normal-stop-intent.json')
    proofs['trinoStopResult'] = read_proof(root / 'trino-normal-stop-result.json')
    proofs['queryPlanSource'] = read_proof(module.HERE / 'contract.py')
    proofs['captureMap'] = read_proof(root / 'proof/warehouse-after-trino.json', 512*1024)
    require(proofs['queryPlanSource']['sha256'] == 'e88d2bedfeb95b71b22e2b5b04701119e8203431d3c8e8cc521958f2dcfad98a',
        'EXACT_PURE_QUERY_PLAN_SOURCE_REQUIRED')
    stop_intent, stop_result = (strict(proofs[key]['raw']) for key in ('trinoStopIntent', 'trinoStopResult'))
    require(stop_intent == {k: v for k, v in seen.attempt.trino_stop.items() if k != 'requestReturnedZero'}
        and stop_result == {**seen.attempt.trino_stop, 'actualExitCode': stop_result['actualExitCode'], 'nonOom': True}
        and type(stop_result['actualExitCode']) is int and stop_result['actualExitCode'] in (0, 143),
        'ACTUAL_PRIVATE_TRINO_NORMAL_STOP_BINDING')
    spark, diagnostic, reader = (strict(proofs[key]['raw']) for key in ('sparkResult', 'sparkDiagnostic', 'readerResult'))
    require(spark['passed'] is True and diagnostic['passed'] is True
        and diagnostic['sessionStopFailed'] is False and diagnostic['phase'] == 'COMPLETED'
        and reader['passed'] is True and reader['allPreTrinoBytesEqual'] is True and reader['onlyGetAndList'] is True,
        'ACTUAL_PRIVATE_SPARK_READER_PROOFS_REQUIRED')
    capture_map = strict(proofs['captureMap']['raw'])
    require(type(capture_map) is list and 0 < len(capture_map) <= 128
        and type(reader['wholeObjects']) is int and reader['wholeObjects'] == len(capture_map),
        'SOURCE_BOUND_WAREHOUSE_MAP_COUNT_REQUIRED')
    named = []
    for index, name in enumerate(NAMES, 1):
        raw = read_proof(observer_folder / (name + '.raw'), 16383)
        checkpoint = read_proof(observer_folder / (name + '.checkpoint.json'))
        record = strict(checkpoint['raw'])
        require(record['sequence'] == index and record['sourceCommit'] == seen.source_commit
            and record['producerSha256'] == PRODUCER and record['runtimeManifestSha256'] == RUNTIME
            and record['rawSha256'] == raw['sha256'] and record['rawBytes'] == len(raw['raw'])
            and record['returnBytesPreserved'] is True
            and record['originalDeadlineStartedMonotonic'] == seen.deadline_started,
            'NAMED_CHECKPOINT_WHOLE_BYTES_BINDING_REQUIRED')
        named.append({'name': name, 'raw': raw['raw'], 'rawSha256': raw['sha256'],
            'checkpoint': checkpoint['raw'], 'checkpointSha256': checkpoint['sha256']})
    require(named[0]['raw'] == named[1]['raw'] == named[2]['raw'], 'ALL_THREE_ACTUAL_POINTER_BYTES_EQUAL')
    chain = module.snapshot_chain(spark['snapshots'], 3)
    ids = [row['snapshot_id'] for row in chain]
    require(value['result']['snapshotIds'] == ids and value['result']['rowFingerprints'] == spark['rowFingerprints'],
        'SAME_RUN_ACTUAL_VALIDATED_SNAPSHOT_SELECTION')
    intents, intent_proofs = [], []
    for name, sql in module.query_plan(chain):
        saved = read_proof(root / ('trino-' + name + '-intent.json'))
        intent = strict(saved['raw'])
        require(intent == {'sqlSha256': sha(sql.encode()), 'automaticRetry': False},
            'ORIGINAL_NAMED_SQL_INTENT_BINDING_REQUIRED')
        intents.append({'name': name, 'rawSha256': saved['sha256'], 'sqlSha256': intent['sqlSha256']})
        intent_proofs.append({'name': name, **saved})
    captured = strict(named[-1]['checkpoint'])['after']['utc']
    validation = {'schemaVersion': 1, 'scope': 'SAME_RUN_FROZEN_SPARK_TRINO_SNAPSHOT_VALIDATION',
        'authoritySourceSha256': authority_source_sha,
        'queryPlanSourceSha256': 'e88d2bedfeb95b71b22e2b5b04701119e8203431d3c8e8cc521958f2dcfad98a',
        'sourceCommit': seen.source_commit, 'producerSha256': PRODUCER, 'runtimeManifestSha256': RUNTIME,
        'capturedAt': captured, 'producerSummarySha256': summary['sha256'],
        'sparkResultSha256': proofs['sparkResult']['sha256'], 'snapshotIds': ids,
        'rowFingerprints': value['result']['rowFingerprints'], 'namedSqlIntents': intents,
        'closedActorScope': 'THIS_FRESH_TRIAL_ONLY', 'backupExportActorCount': 0,
        'individualNamedQueryRawResultsClaimed': False}
    observer_result = read_proof(observer_folder / 'observer-result.json')
    observed = strict(observer_result['raw'])
    require(observed['makeCallsStarted'] == observed['makeCallsCompleted'] == 1
        and observed['jdbcCallsStarted'] == observed['jdbcCallsCompleted'] == 3
        and observed['allThreeCheckpointsObserved'] is True and observed['hookDriftDetected'] is False
        and observed['originalFunctionsRestored'] is True and observed['producerRunPassedClaimed'] is False
        and observed['writersQuiescentVerified'] is False and observed['tableClosureVerified'] is False,
        'ORIGINAL_OBSERVER_COMPLETE_AND_RESTORED_REQUIRED')
    return {**proofs, 'sourceCommit': seen.source_commit, 'producerSha256': PRODUCER,
        'authoritySourceSha256': authority_source_sha, 'namedSqlIntents': intent_proofs,
        'runtimeManifestSha256': RUNTIME, 'observerManifestSha256': OBSERVER, 'producerSummary': summary,
        'named': named, 'observerResult': observer_result,
        'makeBinding': read_proof(observer_folder / 'make-attempt.binding.json'),
        'validation': {'raw': encoded(validation), 'sha256': sha(encoded(validation))}}
