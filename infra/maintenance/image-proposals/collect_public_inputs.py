"""Capture only fixed historical PRs through bounded credential-free public GETs.

This improves selected metadata, not qualification proof. Every entry stays KEEP.
No files/commit authors/publication provenance or rollback authority is inferred.
"""
from __future__ import annotations

import argparse
import base64
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time
from urllib.error import HTTPError, URLError
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener

REPOSITORY = 'DevDooly/devdooly-platform-lab'
PREFIX = 'https://api.github.com/repos/' + REPOSITORY + '/'
NUMBERS = (74, 72, 69, 65, 62, 60, 58, 55, 51, 49, 42, 39, 36, 26, 24, 22)
BOT = 'github-actions[bot]'
MAIN_PATH = 'git/ref/heads/main'
PIN_SHA256 = '98e3dd67620aef49d466eaa65d0afbbae825b52556cf20072ef0b03d635ba5b0'
MAX_REQUESTS = 52
MAX_RESPONSE = 128 * 1024
MAX_REPORT = 128 * 1024
LOGICAL_SECONDS = 120
OUTER_SECONDS = 150
REQUEST_SECONDS = 4
SHA = re.compile('[a-f0-9]{40}')
BRANCH = re.compile('automation/lab-images/([a-f0-9]{40})')
FAILURES = {'PUBLIC_HTTP_UNAVAILABLE', 'PUBLIC_REQUEST_UNVERIFIED', 'PUBLIC_RESPONSE_UNVERIFIED',
            'BUDGET_EXHAUSTED', 'RATE_LIMITED', 'PARTIAL_PAGE', 'METADATA_UNVERIFIED',
            'HEAD_OR_METADATA_DRIFT', 'CURRENT_SOURCE_UNVERIFIED', 'MAIN_DRIFT', 'OUTER_UNVERIFIED'}


class Unverified(Exception):
    def __init__(self, code):
        self.code = code if code in FAILURES else 'METADATA_UNVERIFIED'


def need(condition, code='METADATA_UNVERIFIED'):
    if not condition:
        raise Unverified(code)


def canonical(value):
    return (json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False) + '\n').encode()


def unique(pairs):
    value = {}
    for key, item in pairs:
        need(key not in value, 'PUBLIC_RESPONSE_UNVERIFIED')
        value[key] = item
    return value


def decode(raw):
    need(type(raw) is bytes and 0 < len(raw) <= MAX_RESPONSE, 'PUBLIC_RESPONSE_UNVERIFIED')
    try:
        return json.loads(raw.decode('utf-8', 'strict'), object_pairs_hook=unique,
                          parse_float=lambda unused: need(False, 'PUBLIC_RESPONSE_UNVERIFIED'),
                          parse_constant=lambda unused: need(False, 'PUBLIC_RESPONSE_UNVERIFIED'))
    except (ValueError, UnicodeError, RecursionError):
        raise Unverified('PUBLIC_RESPONSE_UNVERIFIED') from None


def stamp(value):
    need(type(value) is str and re.fullmatch(r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z', value))
    try:
        return datetime.fromisoformat(value.replace('Z', '+00:00'))
    except ValueError:
        raise Unverified('METADATA_UNVERIFIED') from None


def bounded_list(value, maximum):
    need(type(value) is list and len(value) <= maximum)
    return value


def count(value):
    need(type(value) is int and 0 <= value <= 100000)
    return value


def allowed_path(path):
    if path == MAIN_PATH:
        return True
    for number in NUMBERS:
        if path in {'pulls/' + str(number), 'pulls/' + str(number) + '/reviews?per_page=100&page=1'}:
            return True
    return re.fullmatch(r'contents/gitops/environments/home-lab/(values|runtime)[.]yaml\?ref=[a-f0-9]{40}', path) is not None


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, message, headers, newurl):
        raise Unverified('PUBLIC_HTTP_UNAVAILABLE')


class PublicReader:
    def __init__(self):
        self.deadline = time.monotonic() + LOGICAL_SECONDS
        self.calls = 0
        self.bytes = 0
        self.paths = Counter()
        self.rate_limited = False
        self.opener = build_opener(ProxyHandler({}), NoRedirect())

    def get(self, path):
        need(allowed_path(path), 'PUBLIC_REQUEST_UNVERIFIED')
        maximum = 2 if path == MAIN_PATH or re.fullmatch(r'pulls/\d+', path) else 1
        need(self.calls < MAX_REQUESTS and self.paths[path] < maximum
             and time.monotonic() < self.deadline and not self.rate_limited, 'BUDGET_EXHAUSTED')
        self.calls += 1
        self.paths[path] += 1
        url = PREFIX + path
        request = Request(url, method='GET', headers={'Accept': 'application/vnd.github+json',
                          'User-Agent': 'devdooly-public-retention-capture', 'X-GitHub-Api-Version': '2022-11-28',
                          'Cache-Control': 'no-cache'})
        try:
            with self.opener.open(request, timeout=min(REQUEST_SECONDS, self.deadline - time.monotonic())) as response:
                need(response.status == 200 and response.geturl() == url, 'PUBLIC_HTTP_UNAVAILABLE')
                need(response.headers.get('Content-Type', '').split(';', 1)[0].strip().lower()
                     == 'application/json', 'PUBLIC_RESPONSE_UNVERIFIED')
                link = response.headers.get('Link', '')
                need(len(link) <= 4096 and 'rel="next"' not in link, 'PARTIAL_PAGE')
                remaining = response.headers.get('X-RateLimit-Remaining')
                if remaining == '0':
                    self.rate_limited = True
                raw = bytearray()
                while True:
                    need(time.monotonic() < self.deadline, 'BUDGET_EXHAUSTED')
                    chunk = response.read1(8192)
                    if not chunk:
                        break
                    raw.extend(chunk)
                    self.bytes += len(chunk)
                    need(len(raw) <= MAX_RESPONSE and self.bytes <= MAX_REQUESTS * MAX_RESPONSE,
                         'PUBLIC_RESPONSE_UNVERIFIED')
                return decode(bytes(raw))
        except HTTPError as error:
            if error.code in {403, 429}:
                self.rate_limited = True
                raise Unverified('RATE_LIMITED') from None
            raise Unverified('PUBLIC_HTTP_UNAVAILABLE') from None
        except (URLError, OSError, TimeoutError):
            raise Unverified('PUBLIC_HTTP_UNAVAILABLE') from None


def main_sha(value):
    need(type(value) is dict and value.get('ref') == 'refs/heads/main'
         and value.get('object', {}).get('type') == 'commit')
    result = value['object']['sha']
    need(type(result) is str and SHA.fullmatch(result))
    return result


def projection(value, number):
    need(type(value) is dict and value.get('number') == number and value.get('state') in {'open', 'closed'})
    need(type(value.get('draft')) is bool and type(value.get('merged')) is bool
         and 'auto_merge' in value and (value['auto_merge'] is None or type(value['auto_merge']) is dict))
    head = value['head']; base = value['base']
    need(type(head) is dict and type(base) is dict and type(head.get('sha')) is str and SHA.fullmatch(head['sha']))
    need(type(head.get('ref')) is str and len(head['ref']) <= 128 and base.get('ref') == 'main'
         and type(base.get('sha')) is str and SHA.fullmatch(base['sha']))
    source = BRANCH.fullmatch(head['ref'])
    labels = bounded_list(value['labels'], 32)
    names = []
    for item in labels:
        need(type(item) is dict and type(item.get('name')) is str and 0 < len(item['name']) <= 64)
        names.append(item['name'])
    need(len(set(names)) == len(names))
    body = value.get('body')
    need(body is None or (type(body) is str and len(body.encode()) <= 16384))
    created = stamp(value['created_at']); updated = stamp(value['updated_at']); need(created <= updated)
    user = value.get('user'); need(type(user) is dict)
    return {'number': number, 'state': value['state'], 'draft': value['draft'], 'merged': value['merged'],
            'autoMerge': value['auto_merge'] is not None, 'headSha': head['sha'], 'baseSha': base['sha'],
            'sourceCommit': source[1] if source else None,
            'sameRepository': head.get('repo', {}).get('full_name') == REPOSITORY
                              and base.get('repo', {}).get('full_name') == REPOSITORY,
            'createdAt': value['created_at'], 'updatedAt': value['updated_at'],
            'creatorIsExpectedBot': user.get('login') == BOT and user.get('type') == 'Bot',
            'bodySha256': hashlib.sha256((body or '').encode()).hexdigest(), 'labels': sorted(names),
            'requestedReviewerCount': len(bounded_list(value['requested_reviewers'], 100))
                                      + len(bounded_list(value['requested_teams'], 100)),
            'assigneeCount': len(bounded_list(value['assignees'], 100)),
            'issueCommentCount': count(value['comments']), 'reviewCommentCount': count(value['review_comments']),
            'commitCount': count(value['commits']), 'changedFileCount': count(value['changed_files'])}


def reviewed_sources(reader, sha, pins):
    result = []
    need(len(pins['files']) == 2)
    for item in pins['files']:
        value = reader.get('contents/' + item['path'] + '?ref=' + sha)
        need(type(value) is dict and value.get('type') == 'file' and value.get('path') == item['path']
             and value.get('encoding') == 'base64' and value.get('sha') == item['gitBlobSha']
             and type(value.get('size')) is int and value['size'] == item['bytes'], 'CURRENT_SOURCE_UNVERIFIED')
        content = value.get('content')
        need(type(content) is str and len(content) <= 65536, 'CURRENT_SOURCE_UNVERIFIED')
        try:
            raw = base64.b64decode(content.replace('\n', ''), validate=True)
        except ValueError:
            raise Unverified('CURRENT_SOURCE_UNVERIFIED') from None
        need(len(raw) == item['bytes'] and hashlib.sha256(raw).hexdigest() == item['sha256'],
             'CURRENT_SOURCE_UNVERIFIED')
        need(item['role'] in {'api', 'worker'} and type(item['sourceCommit']) is str and SHA.fullmatch(item['sourceCommit']))
        result.append(item['sourceCommit'])
    need(len(set(result)) == 2)
    return sorted(result)


def empty_entry(number):
    return {'number': number, 'retention': 'KEEP', 'captureStatus': 'UNOBSERVED', 'reason': 'METADATA_UNVERIFIED',
            'headSha': None, 'sourceCommit': None, 'observedDraft': None, 'state': None,
            'reviewCount': None, 'humanActivityOrProtectionObserved': None,
            'qualificationProofComplete': False, 'metadata': None}


def collect(reader, pins):
    entries = [empty_entry(number) for number in NUMBERS]
    started = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
    first_main = None; sources = []; main_verified = False; global_failure = None
    try:
        first_main = main_sha(reader.get(MAIN_PATH))
        sources = reviewed_sources(reader, first_main, pins)
    except (Unverified, KeyError, TypeError, AttributeError) as error:
        global_failure = error.code if isinstance(error, Unverified) else 'CURRENT_SOURCE_UNVERIFIED'
    for entry in entries:
        if global_failure is not None:
            entry['reason'] = global_failure
            continue
        try:
            number = entry['number']; path = 'pulls/' + str(number)
            before = projection(reader.get(path), number)
            reviews = bounded_list(reader.get(path + '/reviews?per_page=100&page=1'), 100)
            need(len(reviews) < 100, 'PARTIAL_PAGE')
            need(all(type(item) is dict and type(item.get('id')) is int and item['id'] > 0
                     and type(item.get('state')) is str for item in reviews))
            after = projection(reader.get(path), number)
            need(before == after, 'HEAD_OR_METADATA_DRIFT')
            activity = (len(reviews) > 0 or len(after['labels']) > 0 or after['assigneeCount'] > 0
                        or after['requestedReviewerCount'] > 0 or after['issueCommentCount'] > 0
                        or after['reviewCommentCount'] > 0 or after['createdAt'] != after['updatedAt']
                        or not after['creatorIsExpectedBot'])
            reason = 'HUMAN_ACTIVITY_OR_PROTECTION_OBSERVED' if activity else 'PROVENANCE_AND_ROLLBACK_INCOMPLETE'
            if after['state'] != 'open' or not after['draft'] or after['merged'] or after['autoMerge']:
                reason = 'NOT_AN_OPEN_UNMERGED_DRAFT'
            elif not after['sameRepository'] or after['sourceCommit'] is None:
                reason = 'AUTOMATION_SOURCE_UNVERIFIED'
            entry.update(captureStatus='READ_COMPLETE', reason=reason, headSha=after['headSha'],
                         sourceCommit=after['sourceCommit'], observedDraft=after['draft'], state=after['state'],
                         reviewCount=len(reviews), humanActivityOrProtectionObserved=bool(activity), metadata=after)
        except (Unverified, KeyError, TypeError, AttributeError, ValueError) as error:
            entry['captureStatus'] = 'UNVERIFIED'
            entry['reason'] = error.code if isinstance(error, Unverified) else 'METADATA_UNVERIFIED'
    if global_failure is None:
        try:
            need(main_sha(reader.get(MAIN_PATH)) == first_main, 'MAIN_DRIFT')
            main_verified = True
        except (Unverified, KeyError, TypeError, AttributeError) as error:
            global_failure = error.code if isinstance(error, Unverified) else 'MAIN_DRIFT'
    complete = main_verified and all(entry['captureStatus'] == 'READ_COMPLETE' for entry in entries)
    finished = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
    planner_input = None
    if complete:
        planner_input = {'schemaVersion': 1, 'kind': 'image-proposal-retention-input', 'repository': REPOSITORY,
                         'capturedAt': finished, 'currentMainCommit': first_main,
                         'protectedSources': {'complete': False, 'current': sources, 'rollback': []},
                         'proposals': [{'number': item['number'], 'observedDraft': item['observedDraft'],
                                        'observedLabels': item['metadata']['labels'], 'proof': None} for item in entries],
                         'captureNote': 'Fresh selected public metadata only; publication/files/commit authors/ancestry and rollback authority remain unverified.'}
    report = {'schemaVersion': 1, 'scope': 'FIXED_HISTORICAL_PR_PUBLIC_READ_ONLY_CAPTURE',
              'repository': REPOSITORY, 'captureStartedAt': started, 'capturedAt': finished,
              'selectedMetadataComplete': bool(complete), 'globalFailureCode': global_failure,
              'repositoryMain': first_main, 'mainStableAndPublicValuesExact': bool(main_verified),
              'currentDeclaredSources': sources if main_verified else [], 'liveWorkloadSourceVerified': False,
              'rollbackSourcesVerified': False, 'protectedSourcesComplete': False,
              'requestCount': reader.calls, 'responseBytes': reader.bytes, 'requestMaximum': MAX_REQUESTS,
              'keepCount': 16, 'supersededCandidateCount': 0, 'entries': entries, 'plannerInput': planner_input,
              'filesCommitAuthorsPublicationOrAncestryFetched': False, 'credentialsRead': False,
              'applyEnabled': False, 'mutationOperations': 0, 'clusterOrSshOperations': 0,
              'boundedSequentialObservation': True, 'wholeGithubHistoryVerified': False}
    need(len(canonical(report)) <= MAX_REPORT)
    return report


def pins():
    raw = (Path(__file__).resolve().parent / 'public-capture-pins.json').read_bytes()
    need(hashlib.sha256(raw).hexdigest() == PIN_SHA256, 'CURRENT_SOURCE_UNVERIFIED')
    return decode(raw)


def worker():
    try:
        value = collect(PublicReader(), pins())
        raw = canonical(value)
        need(len(raw) <= MAX_REPORT)
        sys.stdout.buffer.write(raw)
        return 0
    except BaseException:
        print('{"scope":"PUBLIC_CAPTURE_NOT_VERIFIED","failureCode":"OUTER_UNVERIFIED"}')
        return 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output')
    parser.add_argument('--public-read-worker', action='store_true', help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.public_read_worker:
        return worker()
    need(args.output is not None)
    target = Path(args.output); need(not target.exists())
    source = Path(__file__).resolve(); before = source.read_bytes()
    env = {name: os.environ[name] for name in ('SystemRoot', 'WINDIR', 'TEMP', 'TMP') if name in os.environ}
    try:
        result = subprocess.run([sys.executable, '-I', '-B', str(source), '--public-read-worker'],
                                env=env, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE, timeout=OUTER_SECONDS, check=False)
        need(result.returncode == 0 and 0 < len(result.stdout) <= MAX_REPORT
             and len(result.stderr) == 0 and source.read_bytes() == before, 'OUTER_UNVERIFIED')
        report = decode(result.stdout)
    except (subprocess.TimeoutExpired, Unverified, OSError):
        report = {'schemaVersion': 1, 'scope': 'PUBLIC_CAPTURE_NOT_VERIFIED', 'failureCode': 'OUTER_UNVERIFIED',
                  'keepCount': 16, 'supersededCandidateCount': 0, 'plannerInput': None,
                  'entries': [empty_entry(number) for number in NUMBERS], 'applyEnabled': False,
                  'mutationOperations': 0, 'automaticRetryRequested': False}
    with target.open('xb') as stream:
        stream.write(canonical(report))
    print(json.dumps({'scope': report['scope'], 'keepCount': 16, 'supersededCandidateCount': 0,
                      'selectedMetadataComplete': report.get('selectedMetadataComplete', False),
                      'applyEnabled': False, 'mutationOperations': 0}))
    return 0 if report.get('selectedMetadataComplete') is True else 1


if __name__ == '__main__':
    raise SystemExit(main())
