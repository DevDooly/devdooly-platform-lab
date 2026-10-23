#!/usr/bin/env python3
"""Read deployed job HTTP DTO through the existing ClusterIP; no admin fallback."""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import ipaddress
import json
from pathlib import Path
import sys
import time
from urllib.request import ProxyHandler, Request, build_opener

from job_contract import MAX_JOB_SNAPSHOT, validate_job_snapshot
from pages_uploader import atomic_private_json
from platform_collector import JsonTransport, NoRedirect, validate_server

SERVICE_PATH = '/api/v1/namespaces/platform-lab/services/api'
API_PATH = '/api/jobs/observation'

class JobCollectionError(Exception): pass

def require(value):
    if not value: raise JobCollectionError('JOB_CAPTURE_FAILED')

def unique_object(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result); result[key] = value
    return result

def api_endpoint(service):
    require(isinstance(service, dict) and service.get('kind') == 'Service')
    metadata, spec = service.get('metadata', {}), service.get('spec', {})
    require(metadata.get('name') == 'api' and metadata.get('namespace') == 'platform-lab' and spec.get('type', 'ClusterIP') == 'ClusterIP')
    require(spec.get('selector') == {'app.kubernetes.io/name':'platform-lab', 'app.kubernetes.io/instance':'lab', 'app.kubernetes.io/component':'api'})
    ports = spec.get('ports')
    require(isinstance(ports, list) and len(ports) == 1 and ports[0].get('name') == 'http' and ports[0].get('port') == 8080
            and ports[0].get('targetPort') == 'http' and ports[0].get('protocol', 'TCP') == 'TCP')
    try: address = ipaddress.ip_address(spec.get('clusterIP'))
    except (ValueError, TypeError): raise JobCollectionError('JOB_CAPTURE_FAILED') from None
    # This installation's K3s service CIDR. Never follow a Service redirect to
    # a host/local-metadata/public endpoint or use externalName/nodePort.
    require(address.version == 4 and address in ipaddress.ip_network('10.43.0.0/16'))
    return f'http://{address}:8080{API_PATH}'

def collect_jobs(get_kube, *, opener=None, deadline=None, now=None):
    endpoint = api_endpoint(get_kube(SERVICE_PATH, 'WORKLOADS_UNAVAILABLE'))
    remaining = 6 if deadline is None else min(6, deadline - time.monotonic())
    require(remaining > 0)
    client = opener or build_opener(ProxyHandler({}), NoRedirect())
    # ServiceAccount Authorization is used only for the Kubernetes GET above;
    # no credential, cookie or redirect is sent to the application endpoint.
    request = Request(endpoint, headers={'Accept':'application/json', 'User-Agent':'devdooly-job-observer/1'}, method='GET')
    with client.open(request, timeout=remaining) as response:
        require(response.status == 200)
        raw = response.read(MAX_JOB_SNAPSHOT + 1)
    require(deadline is None or time.monotonic() < deadline)
    require(len(raw) <= MAX_JOB_SNAPSHOT)
    return validate_job_snapshot(json.loads(raw, object_pairs_hook=unique_object), now or datetime.now(timezone.utc))

def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--server', required=True); parser.add_argument('--token-file', required=True, type=Path)
    parser.add_argument('--ca-file', required=True, type=Path); parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--deadline-seconds', default=15, type=int, choices=range(10, 21))
    args = parser.parse_args(argv)
    try:
        deadline = time.monotonic() + args.deadline_seconds
        kube = JsonTransport(validate_server(args.server), deadline, ca_file=args.ca_file, token_file=args.token_file)
        record = collect_jobs(kube, deadline=deadline)
        atomic_private_json(args.output, record)
        print(json.dumps({'status':'success', 'errorCode':'NONE', 'capturedAt':record['capturedAt']}))
        return 0
    except Exception:
        # Keep the last valid file byte-for-byte; no new success clock/error body.
        print(json.dumps({'status':'failure', 'errorCode':'JOB_CAPTURE_FAILED'}))
        return 1

if __name__ == '__main__': raise SystemExit(main())
