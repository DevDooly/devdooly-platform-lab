"""Pure projection/strict validator for one historical, verified Cloud Spark trial.

No Docker, SQL, network, environment, live status or deployment operation.
The input is the exact allowlisted summary already emitted by Cloud attempt 8.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re

SCOPE = 'ISOLATED_GITHUB_RUNNER_SPARK_JDBC_GARAGE'
SOURCE = '0552a28a0b360543c9b84be2e5c5ccc7d28c2459'
RUN_ID = '38805412935'
SUMMARY_SHA = '00068fc7a88961374e57b4964a4819d70dc51706c3c16de9b28a54d2b8920838'
SUMMARY_BYTES = 5387
FIXTURE_SHA = '39ba10d8c47dce790f3ccc9c9134fea593d6de31f1f3a7992ca61d9f554da3b5'
SNAPSHOT_IDS = ['5876084123105525860', '711948836478668590']
BRONZE_SHA = '9ad14362736e0ada4f44de4ca32296a2e9082e2f78227884326608952116d016'
SILVER_SHA = '2c51c7447e59bf88cd41c016cf846b47e3e4c46b4257a024e9f67079b2b425eb'
RUN_URL = 'https://github.com/DevDooly/devdooly-platform-lab/actions/runs/' + RUN_ID

# This is a historical record allowlist, not a generic mechanism for publishing
# a future successful run. A different run requires separate reviewed evidence.
PROFILE = {
    'schemaVersion': 1, 'scope': SCOPE, 'status': 'VERIFIED',
    'capturedAt': '2026-10-15T20:53:21.475236Z', 'sourceCommit': SOURCE,
    'run': {'id': RUN_ID, 'url': RUN_URL, 'attempt': 8},
    'summary': {'sha256': SUMMARY_SHA, 'bytes': SUMMARY_BYTES},
    'fixture': {'scenario': 'sensor-validation-v1', 'sha256': FIXTURE_SHA, 'bytes': 1100, 'rows': 12},
    'versions': {'spark': '4.1.1', 'java': '21.0.9', 'scala': '2.13.17'},
    'bronze': {'rows': 12, 'snapshots': 2, 'snapshotIds': SNAPSHOT_IDS, 'rowsSha256': BRONZE_SHA},
    'silver': {'rows': 12, 'snapshots': 1, 'success': 7, 'failure': 3, 'duplicate': 2, 'pending': 0,
        'mergeInvocations': 1, 'sequentialReplayInvocations': 1, 'replayWriteInvocations': 0, 'rowsSha256': SILVER_SHA},
    'stop': {'bootstrapCompleted': True, 'sessionStopFailed': False, 'exitCode': 0, 'oomKilled': False,
        'ownedComposeStopped': True, 'ownedInitializerStopped': True},
    'resources': {'sparkCpu': 1, 'sparkMemoryBytes': 3221225472, 'sparkDriverHeapMiB': 1536,
        'sparkPidLimit': 512, 'postgresGaragePidLimit': 256, 'deadlineSeconds': 600, 'hostPublishedPorts': 0},
    'timing': {'bootstrapCompletedElapsedMillis': 24871, 'scope': 'BOOTSTRAP_START_WORK_AND_STOP',
        'stageDurationsOrThroughputMeasured': False},
    'exclusions': {'miniPcContacted': False, 'nativeTrinoVerified': False, 'kubernetesVerified': False,
        'distributedConcurrencyOrCrashRecoveryVerified': False, 'pidSoleCauseProven': False,
        'liveService': False, 'cgroupPeakOrDeltaMeasured': False},
}


def require(value, code):
    if not value:
        raise ValueError(code)


def strict_match(value, expected):
    if type(value) is not type(expected):
        return False
    if isinstance(expected, dict):
        return set(value) == set(expected) and all(strict_match(value[key], item) for key, item in expected.items())
    if isinstance(expected, list):
        return len(value) == len(expected) and all(strict_match(a, b) for a, b in zip(value, expected))
    return value == expected


def validate(value):
    require(isinstance(value, dict) and set(value) == set(PROFILE), 'EXACT_PUBLIC_SPARK_DTO_KEYS_REQUIRED')
    bronze = value.get('bronze')
    require(isinstance(bronze, dict) and isinstance(bronze.get('snapshotIds'), list), 'ACTUAL_SNAPSHOT_ID_LIST_REQUIRED')
    ids = bronze['snapshotIds']
    require(len(ids) == 2 and all(type(item) is str and re.fullmatch(r'[1-9][0-9]{0,18}', item)
        and int(item) <= (1 << 63) - 1 for item in ids) and len(set(ids)) == 2,
        'DISTINCT_DECIMAL_BIGINT_SNAPSHOT_STRINGS_REQUIRED')
    require(strict_match(value, PROFILE), 'ONLY_EXACT_VERIFIED_CLOUD8_RECORD_WITHOUT_EXTRA_CLAIMS')
    return value


def project(raw):
    require(type(raw) is bytes and len(raw) == SUMMARY_BYTES and hashlib.sha256(raw).hexdigest() == SUMMARY_SHA,
        'EXACT_ACTUAL_CLOUD8_SUMMARY_BYTES_REQUIRED')
    source = json.loads(raw)
    result, diagnostic = source['result'], source['sparkDiagnostic']
    bootstrap, progress = diagnostic['bootstrap'], diagnostic['progress']
    require(source['passed'] is True and result['passed'] is True and bootstrap['passed'] is True
        and source['failure'] is None and source['scope'] == result['scope'] == SCOPE
        and source['sourceCommit'] == SOURCE, 'ACTUAL_SUCCESSFUL_SINGLE_CLOUD_SOURCE_REQUIRED')
    require(diagnostic['stateObserved'] is True and diagnostic['runningAtCapture'] is False
        and type(diagnostic['exitCode']) is int and diagnostic['exitCode'] == 0
        and diagnostic['oomKilled'] is False and bootstrap['lastPhase'] == progress['lastPhase'] == 'COMPLETED'
        and bootstrap['sessionStopFailed'] is False and source['ownedComposeContainersStopped'] is True
        and source['ownedInitializerCreationAttempted'] is True and source['ownedInitializerStoppedOrNotCreated'] is True,
        'ACTUAL_COMPLETION_AND_NORMAL_EXIT_REQUIRED')
    require(all(source['checks'].values()) and all(source['initializerIdentityChecks'].values())
        and source['miniPcContacted'] is False and source['nativeTrinoVerified'] is False
        and source['kubernetesVerified'] is False and result['distributedConcurrencyOrCrashRecoveryVerified'] is False,
        'ACTUAL_BOUNDED_CLOUD_SCOPE_REQUIRED')
    value = {
        'schemaVersion': 1, 'scope': source['scope'], 'status': 'VERIFIED',
        'capturedAt': source['capturedAt'].replace('+00:00', 'Z'), 'sourceCommit': source['sourceCommit'],
        'run': {'id': RUN_ID, 'url': RUN_URL, 'attempt': 8},
        'summary': {'sha256': hashlib.sha256(raw).hexdigest(), 'bytes': len(raw)},
        'fixture': {'scenario': 'sensor-validation-v1', 'sha256': result['fixtureSha256'], 'bytes': 1100, 'rows': 12},
        'versions': {key: result[key] for key in ('spark', 'java', 'scala')},
        'bronze': {'rows': result['bronzeRows'], 'snapshots': result['bronzeSnapshotCount'],
            'snapshotIds': result['bronzeSnapshotIds'], 'rowsSha256': result['bronzeRowsSha256']},
        'silver': {'rows': result['silverRows'], 'snapshots': result['silverSnapshotCount'],
            **{key: result[key] for key in ('success', 'failure', 'duplicate', 'pending', 'mergeInvocations',
                'sequentialReplayInvocations', 'replayWriteInvocations')}, 'rowsSha256': result['silverRowsSha256']},
        'stop': {'bootstrapCompleted': bootstrap['passed'] and bootstrap['lastPhase'] == 'COMPLETED',
            'sessionStopFailed': bootstrap['sessionStopFailed'], 'exitCode': diagnostic['exitCode'], 'oomKilled': diagnostic['oomKilled'],
            'ownedComposeStopped': source['ownedComposeContainersStopped'],
            'ownedInitializerStopped': source['ownedInitializerCreationAttempted'] and source['ownedInitializerStoppedOrNotCreated']},
        # PID/heap/deadline values come from the pinned source whose actual role
        # HostConfig guards passed. They are not cgroup peak/delta measurements.
        'resources': {'sparkCpu': source['plannedSparkCpuLimit'], 'sparkMemoryBytes': source['plannedSparkMemoryLimitBytes'],
            'sparkDriverHeapMiB': 1536, 'sparkPidLimit': 512, 'postgresGaragePidLimit': 256,
            'deadlineSeconds': 600, 'hostPublishedPorts': source['plannedHostPublishedPortCount']},
        'timing': {'bootstrapCompletedElapsedMillis': progress['elapsedMillis'], 'scope': 'BOOTSTRAP_START_WORK_AND_STOP',
            'stageDurationsOrThroughputMeasured': False},
        'exclusions': {'miniPcContacted': source['miniPcContacted'], 'nativeTrinoVerified': source['nativeTrinoVerified'],
            'kubernetesVerified': source['kubernetesVerified'],
            'distributedConcurrencyOrCrashRecoveryVerified': result['distributedConcurrencyOrCrashRecoveryVerified'],
            'pidSoleCauseProven': False, 'liveService': False, 'cgroupPeakOrDeltaMeasured': False},
    }
    return validate(value)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--summary', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args(argv)
    require(args.summary.is_file() and not args.summary.is_symlink() and args.summary.stat().st_size == SUMMARY_BYTES,
        'REGULAR_EXACT_SUMMARY_INPUT_REQUIRED')
    value = project(args.summary.read_bytes())
    with args.output.open('x', encoding='utf-8', newline='\n') as stream:
        json.dump(value, stream, ensure_ascii=True, indent=2); stream.write('\n')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
