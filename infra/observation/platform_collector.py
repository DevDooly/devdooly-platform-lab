#!/usr/bin/env python3
"""Read-only public metadata + tightly scoped Kubernetes SA observation.

Only allowlisted fields are written. No admin fallback, Jenkins API, subprocess,
credential environment variable, network redirect or raw response logging.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
from datetime import datetime, timezone
import ipaddress
import json
import os
from pathlib import Path
import re
import ssl
import stat
import sys
import tempfile
import time
from typing import Any, Callable
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlsplit
from urllib.request import HTTPRedirectHandler, HTTPSHandler, ProxyHandler, Request, build_opener

from platform_contract import (ERROR_CODES, HEALTH, MAX_BUILD_NUMBER, SYNC, InvalidObservation,
                               commit, integer, moment, require, validate_snapshot)

REPOSITORY = 'DevDooly/devdooly-platform-lab'
CONTEXT = 'ci/jenkins-test'
DESCRIPTIONS = {'pending':'validation in progress', 'success':'tests and artifacts verified',
                'failure':'validation failed', 'error':'validation aborted'}
PREFIX = '/api/v1/namespaces/platform-lab/'
APPS = '/apis/apps/v1/namespaces/platform-lab/'
ARGO = '/apis/argoproj.io/v1alpha1/namespaces/argocd/applications/platform-lab-home'
MAX_BODY = 2 * 1024 * 1024


class CollectionError(Exception):
    def __init__(self, code: str):
        super().__init__(code if code in ERROR_CODES and code != 'NONE' else 'COLLECTION_FAILED')


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, message, headers, newurl):
        return None


class JsonTransport:
    def __init__(self, base: str, deadline: float, *, ca_file: Path | None = None,
                 token_file: Path | None = None):
        self.base = base
        self.deadline = deadline
        self.token_file = token_file
        try:
            context = ssl.create_default_context(cafile=str(ca_file) if ca_file else None)
        except (OSError, ssl.SSLError):
            raise CollectionError('AUTHENTICATION_FAILED') from None
        self.opener = build_opener(ProxyHandler({}), NoRedirect(), HTTPSHandler(context=context))

    def __call__(self, path: str, error_code: str) -> Any:
        if not path.startswith('/') or path.startswith('//'):
            raise CollectionError('INVALID_OBSERVATION')
        remaining = self.deadline - time.monotonic()
        if remaining <= 0:
            raise CollectionError('TIMEOUT')
        headers = {'Accept':'application/json', 'User-Agent':'devdooly-platform-observer/1'}
        if self.token_file is not None:
            try:
                with self.token_file.open('rb') as handle:
                    token = handle.read(16385)
                if len(token) > 16384:
                    raise ValueError
                token = token.decode('ascii').strip()
                if not re.fullmatch(r'[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+', token):
                    raise ValueError
            except (OSError, UnicodeError, ValueError):
                raise CollectionError('AUTHENTICATION_FAILED') from None
            headers['Authorization'] = 'Bearer ' + token
        request = Request(self.base + path, headers=headers, method='GET')
        try:
            with self.opener.open(request, timeout=min(6, remaining)) as response:
                body = response.read(MAX_BODY + 1)
            if len(body) > MAX_BODY:
                raise CollectionError(error_code)
            return json.loads(body)
        except HTTPError as error:
            if self.token_file is not None and error.code in {401, 403}:
                raise CollectionError('AUTHENTICATION_FAILED') from None
            raise CollectionError(error_code) from None
        except (TimeoutError,):
            raise CollectionError('TIMEOUT') from None
        except (ssl.SSLError, ssl.CertificateError):
            raise CollectionError('AUTHENTICATION_FAILED') from None
        except URLError as error:
            if isinstance(error.reason, TimeoutError):
                raise CollectionError('TIMEOUT') from None
            if isinstance(error.reason, ssl.SSLError):
                raise CollectionError('AUTHENTICATION_FAILED') from None
            raise CollectionError(error_code) from None
        except (ValueError, UnicodeError, OSError):
            raise CollectionError(error_code) from None


def validate_server(value: str) -> str:
    try:
        parts = urlsplit(value)
        if (parts.scheme != 'https' or parts.username is not None or parts.password is not None
                or parts.query or parts.fragment or parts.path not in {'', '/'} or not parts.hostname):
            raise ValueError
        if parts.port is not None and not 1 <= parts.port <= 65535:
            raise ValueError
        host = parts.hostname
        if host != 'kubernetes.default.svc':
            address = ipaddress.ip_address(host)
            if not address.is_private:
                raise ValueError
    except ValueError:
        raise CollectionError('AUTHENTICATION_FAILED') from None
    return value.rstrip('/')


def latest_jenkins(get: Callable, source: str, ceiling: datetime) -> dict | None:
    for page in range(1, 6):
        records = get(f'/repos/{REPOSITORY}/commits/{source}/statuses?per_page=100&page={page}',
                      'GITHUB_STATUS_UNAVAILABLE')
        require(isinstance(records, list))
        for record in records:
            require(isinstance(record, dict))
            if str(record.get('context', '')).lower() != CONTEXT:
                continue
            # Select latest context before inspecting issuer/state. Never fall
            # back to an older success when a newer status fails verification.
            state = record.get('state')
            require(isinstance(state, str) and state in DESCRIPTIONS)
            require(record.get('creator', {}).get('login') == 'devdooly-platform-lab-ops[bot]')
            description = record.get('description')
            require(isinstance(description, str))
            match = re.fullmatch(r'Jenkins build #([1-9][0-9]*): ' + re.escape(DESCRIPTIONS[state]), description)
            require(match is not None)
            number = integer(int(match.group(1)), 1, MAX_BUILD_NUMBER)
            created = record.get('created_at')
            moment(created, ceiling)
            return {'sourceCommit':source, 'statusId':integer(record.get('id'), 1), 'state':state,
                    'createdAt':created, 'buildNumber':number, 'issuer':'devdooly-platform-lab-ops[bot]'}
        if len(records) < 100:
            return None
    # Do not call a truncated search "not reported".
    raise CollectionError('GITHUB_STATUS_UNAVAILABLE')


def object_identity(document: Any, kind: str, namespace: str, name: str) -> dict:
    require(isinstance(document, dict) and document.get('kind') == kind)
    metadata = document.get('metadata', {})
    require(isinstance(metadata, dict) and metadata.get('namespace') == namespace and metadata.get('name') == name)
    return document


def ready_pod_counts(pods: dict) -> dict[str, int]:
    counts = {'api':0, 'web':0, 'database':0}
    for pod in pods['items']:
        metadata = pod.get('metadata', {})
        labels = metadata.get('labels', {})
        require(isinstance(labels, dict) and labels.get('app.kubernetes.io/name') == 'platform-lab'
                and labels.get('app.kubernetes.io/instance') == 'lab')
        component = labels.get('app.kubernetes.io/component')
        if not isinstance(component, str) or component not in counts:
            continue
        status = pod.get('status', {})
        require(isinstance(status, dict))
        conditions = status.get('conditions', [])
        containers = status.get('containerStatuses', [])
        require(isinstance(conditions, list) and isinstance(containers, list))
        is_ready = any(isinstance(condition, dict) and condition.get('type') == 'Ready'
                       and condition.get('status') == 'True' for condition in conditions)
        containers_ready = bool(containers) and all(isinstance(container, dict)
                              and container.get('ready') is True for container in containers)
        if (not metadata.get('deletionTimestamp') and status.get('phase') == 'Running'
                and is_ready and containers_ready):
            counts[component] += 1
    return counts


def timestamp(value: str | Callable[[], str]) -> str:
    return value() if callable(value) else value


def collect(get_github: Callable, get_kube: Callable, attempted_at: str | Callable[[], str]) -> dict:
    repo = get_github('/repos/' + REPOSITORY, 'GITHUB_STATUS_UNAVAILABLE')
    require(isinstance(repo, dict) and str(repo.get('full_name', '')).lower() == REPOSITORY.lower()
            and repo.get('private') is False)
    main = get_github('/repos/' + REPOSITORY + '/git/ref/heads/main', 'GITHUB_STATUS_UNAVAILABLE')
    require(isinstance(main, dict) and main.get('ref') == 'refs/heads/main'
            and main.get('object', {}).get('type') == 'commit')
    source = commit(main['object'].get('sha'))
    # Sample status time against the current clock; the final envelope records
    # completion time after all reads, not the start of the attempt.
    jenkins = latest_jenkins(get_github, source,
                            datetime.fromisoformat(timestamp(attempted_at).replace('Z', '+00:00')))
    app = object_identity(get_kube(ARGO, 'ARGO_UNAVAILABLE'), 'Application', 'argocd', 'platform-lab-home')
    argo_status = app.get('status', {})
    sync = argo_status.get('sync', {})
    health = argo_status.get('health', {}).get('status', 'Unknown')
    revision = commit(sync.get('revision'))
    sync_status = sync.get('status', 'Unknown')
    require(isinstance(health, str) and health in HEALTH
            and isinstance(sync_status, str) and sync_status in SYNC)
    selector = urlencode({'labelSelector':'app.kubernetes.io/name=platform-lab,app.kubernetes.io/instance=lab', 'limit':100})
    pods = get_kube(PREFIX + 'pods?' + selector, 'WORKLOADS_UNAVAILABLE')
    require(isinstance(pods, dict) and pods.get('kind') == 'PodList' and isinstance(pods.get('items'), list))
    require(not pods.get('metadata', {}).get('continue'))
    # Responses may contain container env/addresses. They are never copied into
    # the output. Aggregate actual Ready Pods, not controller readyReplicas.
    require(all(isinstance(pod, dict) and pod.get('metadata', {}).get('namespace') == 'platform-lab' for pod in pods['items']))
    pod_ready = ready_pod_counts(pods)
    workloads = []
    deployment_source = None
    for component in ('api', 'web', 'database'):
        service_name = 'db' if component == 'database' else component
        service = object_identity(get_kube(PREFIX+'services/'+service_name, 'WORKLOADS_UNAVAILABLE'),
                                  'Service', 'platform-lab', service_name)
        require(service.get('spec', {}).get('type', 'ClusterIP') == 'ClusterIP')
        kind, collection, suffix = ('StatefulSet', 'statefulsets', 'db') if component == 'database' else ('Deployment', 'deployments', component)
        name = 'lab-platform-lab-' + suffix
        resource = object_identity(get_kube(APPS+collection+'/'+name, 'WORKLOADS_UNAVAILABLE'), kind, 'platform-lab', name)
        spec = resource.get('spec', {})
        item = {'component':component, 'desired':integer(spec.get('replicas', 1), 0, 10),
                'ready':integer(pod_ready[component], 0, 10)}
        if component != 'database':
            template = spec.get('template', {})
            containers = template.get('spec', {}).get('containers')
            require(isinstance(containers, list))
            matches = [container for container in containers if isinstance(container, dict) and container.get('name') == component]
            require(len(matches) == 1)
            item['image'] = matches[0].get('image')
            if component == 'api':
                deployment_source = commit(template.get('metadata', {}).get('annotations', {}).get('platform-lab.devdooly.dev/source-commit'))
        workloads.append(item)
    final_main = get_github('/repos/' + REPOSITORY + '/git/ref/heads/main', 'GITHUB_STATUS_UNAVAILABLE')
    require(isinstance(final_main, dict) and final_main.get('ref') == 'refs/heads/main'
            and final_main.get('object', {}).get('type') == 'commit'
            and commit(final_main['object'].get('sha')) == source)
    completed = timestamp(attempted_at)
    ceiling = datetime.fromisoformat(completed.replace('Z', '+00:00'))
    result = {'schemaVersion':1,'kind':'platform-observation',
              'latestAttempt':{'attemptedAt':completed,'status':'success','errorCode':'NONE'},
              'lastSuccess':{'capturedAt':completed,'collectorVersion':'1','mainCommit':source,
                             'jenkins':jenkins,'argo':{'revision':revision,'sync':sync_status,'health':health},
                             'workloads':workloads,'deploymentSourceCommit':deployment_source}}
    return validate_snapshot(result, ceiling)


def collect_with_preservation(get_github: Callable, get_kube: Callable, attempted_at: str | Callable[[], str],
                              previous: dict | None) -> dict:
    ceiling = datetime.fromisoformat(timestamp(attempted_at).replace('Z', '+00:00'))
    if previous is not None:
        validate_snapshot(previous, ceiling)
    try:
        return collect(get_github, get_kube, attempted_at)
    except CollectionError as error:
        code = str(error)
    except (InvalidObservation, ValueError, TypeError, KeyError, AttributeError, OverflowError):
        code = 'INVALID_OBSERVATION'
    except Exception:
        code = 'COLLECTION_FAILED'
    completed = timestamp(attempted_at)
    ceiling = datetime.fromisoformat(completed.replace('Z', '+00:00'))
    result = {'schemaVersion':1,'kind':'platform-observation',
              'latestAttempt':{'attemptedAt':completed,'status':'failure','errorCode':code},
              'lastSuccess':deepcopy(previous['lastSuccess']) if previous is not None else None}
    return validate_snapshot(result, ceiling)


def read_previous(path: Path, now: datetime) -> dict | None:
    if not path.exists():
        return None
    if path.is_symlink() or not stat.S_ISREG(path.stat().st_mode):
        raise InvalidObservation('INVALID_OBSERVATION')
    if path.stat().st_size > MAX_BODY:
        raise InvalidObservation('INVALID_OBSERVATION')
    try:
        with path.open('rb') as handle:
            body = handle.read(MAX_BODY + 1)
        require(len(body) <= MAX_BODY)
        return validate_snapshot(json.loads(body), now)
    except (OSError, ValueError, UnicodeError):
        raise InvalidObservation('INVALID_OBSERVATION') from None


def atomic_save(path: Path, snapshot: dict, now: datetime) -> None:
    validate_snapshot(snapshot, now)
    if path.is_symlink() or (path.exists() and not stat.S_ISREG(path.stat().st_mode)):
        raise InvalidObservation('INVALID_OBSERVATION')
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    descriptor, temporary = tempfile.mkstemp(prefix='.'+path.name+'.', suffix='.tmp', dir=path.parent)
    try:
        os.chmod(temporary, 0o600)
        with os.fdopen(descriptor, 'w', encoding='utf-8', newline='\n') as handle:
            json.dump(snapshot, handle, ensure_ascii=False, indent=2, allow_nan=False)
            handle.write('\n')
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        if os.name == 'posix':
            directory = os.open(path.parent, os.O_RDONLY | getattr(os, 'O_DIRECTORY', 0))
            try: os.fsync(directory)
            finally: os.close(directory)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description='Read-only platform observer; endpoints and credentials are never printed.')
    parser.add_argument('--server', required=True)
    parser.add_argument('--token-file', required=True, type=Path)
    parser.add_argument('--ca-file', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--previous', type=Path)
    parser.add_argument('--deadline-seconds', type=int, default=60, choices=range(10, 91), metavar='10..90')
    args = parser.parse_args(argv)
    lock_path = args.output.parent / ('.' + args.output.name + '.lock')
    lock = None
    try:
        clock = datetime.now(timezone.utc)
        args.output.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        lock = os.open(lock_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, 'O_NOFOLLOW', 0), 0o600)
        previous = read_previous(args.previous or args.output, clock)
        completed_clock = lambda: datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')
        deadline = time.monotonic() + args.deadline_seconds
        try:
            server = validate_server(args.server)
            github = JsonTransport('https://api.github.com', deadline)
            kube = JsonTransport(server, deadline, ca_file=args.ca_file, token_file=args.token_file)
        except CollectionError as error:
            code = str(error)
            def failed_transport(path, error_code):
                raise CollectionError(code)
            github = kube = failed_transport
        snapshot = collect_with_preservation(github, kube, completed_clock, previous)
        atomic_save(args.output, snapshot, datetime.now(timezone.utc))
        # Never print URLs, paths, token, raw responses, exception details or
        # observed data. The operator reviews the allowlisted output file.
        print(json.dumps({'status':snapshot['latestAttempt']['status'],
                          'errorCode':snapshot['latestAttempt']['errorCode'],
                          'attemptedAt':snapshot['latestAttempt']['attemptedAt'],
                          'hasLastSuccess':snapshot['lastSuccess'] is not None}))
        return 0 if snapshot['latestAttempt']['status']=='success' else 1
    except (InvalidObservation, CollectionError):
        print(json.dumps({'status':'failure','errorCode':'INVALID_OBSERVATION'}))
        return 1
    except Exception:
        print(json.dumps({'status':'failure','errorCode':'COLLECTION_FAILED'}))
        return 1
    finally:
        if lock is not None:
            try:
                os.close(lock)
                os.unlink(lock_path)
            except OSError:
                pass


if __name__ == '__main__':
    raise SystemExit(main())
