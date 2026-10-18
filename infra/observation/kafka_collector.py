#!/usr/bin/env python3
"""One bounded fixed application GET; no broker/admin fallback or credential forwarding."""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import time
from urllib.request import ProxyHandler, Request, build_opener

from job_collector import SERVICE_PATH, api_endpoint as job_api_endpoint
from kafka_contract import MAX_KAFKA_SNAPSHOT, parse_kafka_snapshot
from pages_uploader import atomic_private_json, load_kafka_snapshot
from platform_collector import JsonTransport, NoRedirect, validate_server
from platform_contract import moment

API_PATH = '/api/kafka/observation'


class KafkaCollectionError(Exception): pass


def require(value):
    if not value: raise KafkaCollectionError('KAFKA_CAPTURE_FAILED')


def api_endpoint(service):
    # Reuse the existing exact Service identity/selector/port/CIDR gate only.
    endpoint = job_api_endpoint(service)
    require(endpoint.endswith('/api/jobs/observation'))
    return endpoint.removesuffix('/api/jobs/observation') + API_PATH


def collect_kafka(get_kube, *, opener=None, deadline=None, now=None):
    cutoff = time.monotonic() + 10 if deadline is None else deadline
    started = now or datetime.now(timezone.utc)
    endpoint = api_endpoint(get_kube(SERVICE_PATH, 'WORKLOADS_UNAVAILABLE'))
    remaining = min(4, cutoff - time.monotonic())
    require(remaining > 0)
    client = opener or build_opener(ProxyHandler({}), NoRedirect())
    request = Request(endpoint, headers={'Accept': 'application/json',
        'User-Agent': 'devdooly-kafka-observer/1'}, method='GET')
    with client.open(request, timeout=remaining) as response:
        require(response.status == 200)
        raw = response.read(MAX_KAFKA_SNAPSHOT + 1)
    require(time.monotonic() < cutoff and len(raw) <= MAX_KAFKA_SNAPSHOT)
    finished = now or datetime.now(timezone.utc)
    record = parse_kafka_snapshot(raw, finished)
    require(moment(record['captureStartedAt'], finished) >=
        (started.replace(microsecond=0), started.microsecond * 1000))
    require(time.monotonic() < cutoff)
    return record


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--server', required=True)
    parser.add_argument('--token-file', required=True, type=Path)
    parser.add_argument('--ca-file', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--deadline-seconds', default=10, type=int, choices=range(8, 11))
    args = parser.parse_args(argv)
    try:
        deadline = time.monotonic() + args.deadline_seconds
        kube = JsonTransport(validate_server(args.server), deadline,
            ca_file=args.ca_file, token_file=args.token_file)
        record = collect_kafka(kube, deadline=deadline)
        if args.output.exists() or args.output.is_symlink():
            prior = load_kafka_snapshot(args.output, datetime.now(timezone.utc))
            require(prior['targetFingerprint'] == record['targetFingerprint'])
            before = moment(prior['capturedAt'], datetime.now(timezone.utc))
            after = moment(record['capturedAt'], datetime.now(timezone.utc))
            require(after >= before and (after != before or prior == record))
        require(time.monotonic() < deadline)
        atomic_private_json(args.output, record)
        print(json.dumps({'status': 'success', 'errorCode': 'NONE', 'capturedAt': record['capturedAt']}))
        return 0
    except Exception:
        # Late/invalid/new-target captures never replace the prior valid file.
        print(json.dumps({'status': 'failure', 'errorCode': 'KAFKA_CAPTURE_FAILED'}))
        return 1


if __name__ == '__main__': raise SystemExit(main())
