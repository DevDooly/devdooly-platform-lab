"""Strict public allowlist. No cluster/GitHub response is serialized directly."""
from __future__ import annotations

from datetime import datetime, timezone
import re
from typing import Any

ERROR_CODES = frozenset({'NONE', 'GITHUB_STATUS_UNAVAILABLE', 'ARGO_UNAVAILABLE',
    'WORKLOADS_UNAVAILABLE', 'AUTHENTICATION_FAILED', 'TIMEOUT',
    'INVALID_OBSERVATION', 'COLLECTION_FAILED'})
STATES = frozenset({'pending', 'success', 'failure', 'error'})
HEALTH = frozenset({'Healthy', 'Progressing', 'Degraded', 'Suspended', 'Missing', 'Unknown'})
SYNC = frozenset({'Synced', 'OutOfSync', 'Unknown'})
SHA = re.compile(r'[0-9a-f]{40}')
DIGEST = re.compile(r'sha256:[0-9a-f]{64}')
UTC_TIME = re.compile(r'\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(?:\.\d{1,9})?Z')
SAFE_INTEGER = 9007199254740991
MAX_BUILD_NUMBER = 2147483647


class InvalidObservation(Exception):
    """Fixed diagnostic; never includes untrusted field values."""


def require(condition: bool) -> None:
    if not condition:
        raise InvalidObservation('INVALID_OBSERVATION')


def exact(value: Any, fields: set[str]) -> dict:
    require(isinstance(value, dict) and set(value) == fields)
    return value


def integer(value: Any, minimum: int = 0, maximum: int = SAFE_INTEGER) -> int:
    require(isinstance(value, int) and not isinstance(value, bool) and minimum <= value <= maximum)
    return value


def commit(value: Any) -> str:
    require(isinstance(value, str) and SHA.fullmatch(value) is not None)
    return value


def moment(value: Any, ceiling: datetime | tuple[datetime, int]) -> tuple[datetime, int]:
    require(isinstance(value, str) and UTC_TIME.fullmatch(value) is not None)
    try:
        parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
    except ValueError:
        raise InvalidObservation('INVALID_OBSERVATION') from None
    fraction = value.partition('.')[2].removesuffix('Z') if '.' in value else ''
    precise = (parsed.replace(microsecond=0), int(fraction.ljust(9, '0')) if fraction else 0)
    limit = (ceiling.replace(microsecond=0), ceiling.microsecond * 1000) if isinstance(ceiling, datetime) else ceiling
    # datetime truncates >6 fractional digits. Compare all nine explicitly so
    # a one-nanosecond future observation cannot pass the Python validator.
    require(precise <= limit)
    return precise


def validate_snapshot(value: Any, now: datetime | None = None) -> dict:
    """Reject additional fields, impossible chronology and unsafe identities."""
    ceiling = now or datetime.now(timezone.utc)
    require(ceiling.tzinfo is not None)
    exact(value, {'schemaVersion', 'kind', 'latestAttempt', 'lastSuccess'})
    require(value['schemaVersion'] == 1 and not isinstance(value['schemaVersion'], bool))
    require(value['kind'] == 'platform-observation')
    attempt = exact(value['latestAttempt'], {'attemptedAt', 'status', 'errorCode'})
    attempted = moment(attempt['attemptedAt'], ceiling)
    require(isinstance(attempt['status'], str) and attempt['status'] in {'success', 'failure'})
    require(isinstance(attempt['errorCode'], str) and attempt['errorCode'] in ERROR_CODES)
    require((attempt['status'] == 'success') == (attempt['errorCode'] == 'NONE'))
    last = value['lastSuccess']
    if last is None:
        require(attempt['status'] == 'failure')
        return value
    exact(last, {'capturedAt', 'collectorVersion', 'mainCommit', 'jenkins', 'argo',
                 'workloads', 'deploymentSourceCommit'})
    captured = moment(last['capturedAt'], attempted)
    require(last['collectorVersion'] == '1')
    commit(last['mainCommit'])
    commit(last['deploymentSourceCommit'])
    if attempt['status'] == 'success':
        require(last['capturedAt'] == attempt['attemptedAt'])
    jenkins = last['jenkins']
    if jenkins is not None:
        exact(jenkins, {'sourceCommit', 'statusId', 'state', 'createdAt', 'buildNumber', 'issuer'})
        require(commit(jenkins['sourceCommit']) == last['mainCommit'])
        integer(jenkins['statusId'], 1)
        require(isinstance(jenkins['state'], str) and jenkins['state'] in STATES)
        moment(jenkins['createdAt'], captured)
        integer(jenkins['buildNumber'], 1, MAX_BUILD_NUMBER)
        require(jenkins['issuer'] == 'DevDooly')
    argo = exact(last['argo'], {'revision', 'sync', 'health'})
    commit(argo['revision'])
    require(isinstance(argo['sync'], str) and argo['sync'] in SYNC
            and isinstance(argo['health'], str) and argo['health'] in HEALTH)
    workloads = last['workloads']
    require(isinstance(workloads, list) and len(workloads) == 3)
    components = []
    for workload in workloads:
        require(isinstance(workload, dict))
        component = workload.get('component')
        require(isinstance(component, str) and component in {'api', 'web', 'database'})
        exact(workload, {'component', 'desired', 'ready'} | ({'image'} if component != 'database' else set()))
        integer(workload['desired'], 0, 10)
        integer(workload['ready'], 0, 10)
        if component != 'database':
            image = workload['image']
            prefix = 'ghcr.io/devdooly/devdooly-platform-lab-' + component + '@'
            require(isinstance(image, str) and image.startswith(prefix))
            require(DIGEST.fullmatch(image[len(prefix):]) is not None)
        components.append(component)
    require(set(components) == {'api', 'web', 'database'})
    return value
