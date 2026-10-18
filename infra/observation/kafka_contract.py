"""Strict deployed Kafka DTO only; this module neither contacts Kafka nor grants ACLs."""
from __future__ import annotations
from datetime import datetime, timezone
import json
import re

from platform_contract import commit, exact, integer, moment, require

MAX_KAFKA_SNAPSHOT = 8 * 1024


def precise_ns(value):
    when, fraction = value
    elapsed = when - datetime(1970, 1, 1, tzinfo=timezone.utc)
    return (elapsed.days * 86400 + elapsed.seconds) * 1_000_000_000 + fraction


def validate_kafka_snapshot(value, now=None):
    """Only MINI_PC/DEPLOYED_KAFKA can enter the automatic publication path."""
    ceiling = now or datetime.now(timezone.utc)
    require(ceiling.tzinfo is not None)
    exact(value, {'schemaVersion', 'kind', 'synthetic', 'environment', 'scope',
        'publicExecutionEnabled', 'sourceCommit', 'captureStartedAt', 'capturedAt',
        'consistency', 'targetFingerprint', 'groupState', 'partition', 'commitState',
        'logStartOffset', 'readCommittedEndOffset', 'committedOffset', 'lag'})
    require(type(value['schemaVersion']) is int and value['schemaVersion'] == 1
        and value['kind'] == 'kafka-observation' and value['synthetic'] is True
        and value['environment'] == 'MINI_PC' and value['scope'] == 'DEPLOYED_KAFKA'
        and value['publicExecutionEnabled'] is False)
    commit(value['sourceCommit'])
    started = moment(value['captureStartedAt'], ceiling)
    captured = moment(value['capturedAt'], ceiling)
    require(0 <= precise_ns(captured) - precise_ns(started) <= 4_000_000_000)
    require(value['consistency'] == 'BOUNDED_SEQUENTIAL_READ'
        and isinstance(value['targetFingerprint'], str)
        and re.fullmatch('[a-f0-9]{64}', value['targetFingerprint']) is not None
        and isinstance(value['groupState'], str) and value['groupState'] in {'STABLE', 'EMPTY'}
        and type(value['partition']) is int and value['partition'] == 0)
    start = integer(value['logStartOffset'])
    end = integer(value['readCommittedEndOffset'], start)
    require(isinstance(value['commitState'], str))
    if value['commitState'] == 'NO_COMMIT':
        require(value['committedOffset'] is None and value['lag'] is None)
    else:
        require(value['commitState'] == 'OBSERVED')
        committed = integer(value['committedOffset'], start, end)
        require(integer(value['lag']) == end - committed)
    return value


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result)
        result[key] = value
    return result


def integer_lexeme(value):
    require(value!='-0')
    return int(value)


def parse_kafka_snapshot(raw, now=None):
    require(type(raw) is bytes and 0 < len(raw) <= MAX_KAFKA_SNAPSHOT)
    value = json.loads(raw.decode('utf-8','strict'), object_pairs_hook=unique_object, parse_int=integer_lexeme,
        parse_float=lambda unused: require(False),
        parse_constant=lambda unused: require(False))
    return validate_kafka_snapshot(value, now)
