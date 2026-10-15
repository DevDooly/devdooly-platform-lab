#!/usr/bin/env python3
"""Merge a validated platform snapshot into Pages, without committing to Git.

The baseline comes from the most recent successful trusted Pages run artifact.
Missing/expired expected artifacts fail closed; CDN cache is not authoritative.
"""
import argparse
import copy
import io
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time
from urllib.error import HTTPError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener
import zipfile

REPOSITORY = 'DevDooly/devdooly-platform-lab'
MAX_BYTES = 16384
MAX_JOB_BYTES = 32768
MAX_WORKFLOW_RUNS = 10000
RUN_TITLES = {'Portfolio snapshot v1 · push', 'Portfolio snapshot v1 · workflow_dispatch',
              'Portfolio snapshots v2 · push', 'Portfolio snapshots v2 · workflow_dispatch'}

class ObservationError(Exception):
    pass

def require(value, code):
    if not value:
        raise ObservationError(code)

class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, msg, headers, newurl):
        return None

class GitHub:
    def __init__(self, token):
        require(bool(token), 'READ_ONLY_WORKFLOW_TOKEN_REQUIRED')
        self.token = token
        self.client = build_opener(NoRedirect())

    def get(self, path):
        require(path.startswith('actions/') and '..' not in path, 'INVALID_METADATA_PATH')
        request = Request('https://api.github.com/repos/' + REPOSITORY + '/' + path,
                          headers={'Authorization': 'Bearer ' + self.token, 'Accept': 'application/vnd.github+json',
                                   'X-GitHub-Api-Version': '2026-03-10'})
        with self.client.open(request, timeout=25) as response:
            data = response.read(2_000_001)
            require(len(data) <= 2_000_000, 'METADATA_TOO_LARGE')
            return json.loads(data)

    def archive(self, artifact_id):
        require(type(artifact_id) is int and artifact_id > 0, 'INVALID_ARTIFACT_ID')
        request = Request(f'https://api.github.com/repos/{REPOSITORY}/actions/artifacts/{artifact_id}/zip',
                          headers={'Authorization': 'Bearer ' + self.token, 'Accept': 'application/vnd.github+json',
                                   'X-GitHub-Api-Version': '2026-03-10'})
        try:
            self.client.open(request, timeout=25)
            raise ObservationError('ARTIFACT_REDIRECT_REQUIRED')
        except HTTPError as error:
            require(error.code == 302, 'ARTIFACT_DOWNLOAD_REJECTED')
            destination = error.headers.get('Location', '')
        parsed = urlsplit(destination)
        require(parsed.scheme == 'https' and not parsed.username and not parsed.password
                and parsed.port in (None, 443) and parsed.hostname
                and any(parsed.hostname.endswith(suffix) for suffix in
                        ('.blob.core.windows.net', '.githubusercontent.com', '.actions.githubusercontent.com')),
                'ARTIFACT_STORAGE_HOST_REJECTED')
        # Never forward GitHub Authorization to signed object-storage redirects.
        with self.client.open(Request(destination), timeout=25) as response:
            raw = response.read(131073)
            require(len(raw) <= 131072, 'ARTIFACT_ARCHIVE_TOO_LARGE')
            return raw

def parse_record(raw, validate, max_bytes=MAX_BYTES):
    require(len(raw) <= max_bytes, 'SNAPSHOT_TOO_LARGE')
    try:
        result = json.loads(raw, object_pairs_hook=unique_object)
    except (ValueError, UnicodeError):
        raise ObservationError('INVALID_SNAPSHOT_JSON') from None
    validate(result)
    return result

def unique_object(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, 'DUPLICATE_JSON_KEY')
        result[key] = value
    return result

def workflow_runs(get):
    """Read complete bounded history; never turn an unknown baseline into a seed."""
    runs, seen, total = [], set(), None
    for page_number in range(1, MAX_WORKFLOW_RUNS // 100 + 1):
        # Keep this query unfiltered: GitHub caps searches using branch/status
        # filters. The trusted main identity is checked locally below.
        page = get(f'actions/workflows/pages.yml/runs?per_page=100&page={page_number}')
        require(isinstance(page, dict) and isinstance(page.get('workflow_runs'), list)
                and type(page.get('total_count')) is int and page['total_count'] >= 0,
                'INVALID_WORKFLOW_METADATA')
        # Reaching our bounded scan cap cannot prove that an older successful
        # deployment does not exist. Do not fall back to the initial seed.
        require(page['total_count'] < MAX_WORKFLOW_RUNS, 'WORKFLOW_HISTORY_LIMIT_REQUIRES_REVIEW')
        if total is None:
            total = page['total_count']
        require(page['total_count'] == total, 'WORKFLOW_HISTORY_CHANGED_DURING_READ')
        expected = min(100, total - len(runs))
        require(len(page['workflow_runs']) == expected, 'INCOMPLETE_WORKFLOW_HISTORY')
        for run in page['workflow_runs']:
            require(isinstance(run, dict) and type(run.get('id')) is int and run['id'] > 0,
                    'INVALID_WORKFLOW_METADATA')
            require(run['id'] not in seen, 'WORKFLOW_HISTORY_CHANGED_DURING_READ')
            seen.add(run['id'])
            runs.append(run)
        if len(runs) == total:
            return runs
    raise ObservationError('WORKFLOW_HISTORY_LIMIT_REQUIRES_REVIEW')


def deployment_succeeded(get, metadata, attempt):
    """A successful workflow with a skipped deploy did not publish a baseline."""
    document = get(f"actions/runs/{metadata['id']}/attempts/{attempt}/jobs?per_page=100")
    require(isinstance(document, dict) and isinstance(document.get('jobs'), list)
            and type(document.get('total_count')) is int
            and 0 <= document['total_count'] <= 100
            and len(document['jobs']) == document['total_count'], 'INCOMPLETE_DEPLOY_JOB_METADATA')
    require(all(isinstance(job, dict) for job in document['jobs']), 'INVALID_DEPLOY_JOB_METADATA')
    jobs = [job for job in document['jobs'] if job.get('name') == 'deploy']
    require(len(jobs) <= 1, 'AMBIGUOUS_DEPLOY_JOB_METADATA')
    if not jobs:
        return False
    job = jobs[0]
    require(job.get('run_id') == metadata['id'] and job.get('run_attempt') == attempt
            and job.get('head_sha') == metadata.get('head_sha'), 'DEPLOY_JOB_IDENTITY_REJECTED')
    return job.get('status') == 'completed' and job.get('conclusion') == 'success'


def previous_snapshot(get, download, current_run, current_attempt, validate, *, jobs=False):
    # GitHub's workflow-runs API returns the evaluated run-name in `name`
    # as well as display_title. The workflow path and repository identify the
    # publisher; accept its fixed versioned title for the matching event.
    runs = [r for r in workflow_runs(get) if r.get('name') in RUN_TITLES | {'Publish portfolio'} and r.get('path') == '.github/workflows/pages.yml'
            and r.get('head_branch') == 'main' and r.get('event') in ('push', 'workflow_dispatch')
            and r.get('repository', {}).get('full_name', '').lower() == REPOSITORY.lower()
            and r.get('head_repository', {}).get('full_name', '').lower() == REPOSITORY.lower()
            and r.get('display_title') in {'Portfolio snapshot v1 · ' + r.get('event', ''),
                                         'Portfolio snapshots v2 · ' + r.get('event', '')}
            and (not jobs or r.get('display_title') == 'Portfolio snapshots v2 · ' + r.get('event', ''))]
    attempts = []
    for run in runs:
        latest = run.get('run_attempt', 1)
        require(type(latest) is int and 1 <= latest <= 10, 'WORKFLOW_ATTEMPT_LIMIT_REQUIRES_REVIEW')
        for attempt in range(latest, 0, -1):
            if run['id'] == current_run and attempt >= current_attempt:
                continue
            metadata = run if attempt == latest else get(f"actions/runs/{run['id']}/attempts/{attempt}")
            require(metadata.get('id') == run['id'] and metadata.get('run_attempt', 1) == attempt
                    and metadata.get('head_sha') == run.get('head_sha'), 'WORKFLOW_ATTEMPT_IDENTITY_REJECTED')
            if metadata.get('status') == 'completed' and metadata.get('conclusion') == 'success':
                attempts.append((metadata, attempt))
    if not attempts:
        return None
    # Every new-version successful Pages run must have its matching snapshot.
    attempts.sort(key=lambda pair: (pair[0].get('updated_at', ''), pair[0]['id'], pair[1]), reverse=True)
    published = next((pair for pair in attempts if deployment_succeeded(get, pair[0], pair[1])), None)
    if published is None:
        return None
    chosen, attempt = published
    document = get(f"actions/runs/{chosen['id']}/artifacts?per_page=100")
    artifacts = document.get('artifacts', [])
    artifact_prefix='job-observation' if jobs else 'platform-observation'
    matches = [a for a in artifacts if a.get('name') == f"{artifact_prefix}-{chosen['id']}-a{attempt}"]
    require(len(matches) == 1 and not matches[0].get('expired')
            and matches[0].get('workflow_run', {}).get('id') == chosen['id'], 'PUBLISHED_BASELINE_ARTIFACT_UNAVAILABLE')
    archive = download(matches[0]['id'])
    with zipfile.ZipFile(io.BytesIO(archive)) as zipped:
        entries = zipped.infolist()
        if jobs:
            return decode_job_archive(zipped,entries,validate)
        require(len(entries) == 1 and entries[0].filename == 'platform-observation.json'
                and entries[0].file_size <= MAX_BYTES, 'ARTIFACT_CONTENT_REJECTED')
        with zipped.open(entries[0]) as stream:
            raw = stream.read(MAX_BYTES + 1)
    return parse_record(raw, validate)


def decode_job_archive(zipped, entries, validate):
    """Every v2 deployment retains an explicit presence manifest, even at first setup."""
    names=[entry.filename for entry in entries]
    require(len(names)==len(set(names)) and set(names) in ({'publication.json'}, {'publication.json','jobs.latest.json'}), 'ARTIFACT_CONTENT_REJECTED')
    manifest_entry=next(entry for entry in entries if entry.filename=='publication.json')
    require(manifest_entry.file_size<=512,'ARTIFACT_CONTENT_REJECTED')
    with zipped.open(manifest_entry) as stream:
        try:manifest=json.loads(stream.read(513),object_pairs_hook=unique_object)
        except (ValueError,UnicodeError):raise ObservationError('ARTIFACT_CONTENT_REJECTED') from None
    require(isinstance(manifest,dict) and set(manifest)=={'schemaVersion','kind','recordPresent'}
            and type(manifest['schemaVersion']) is int and manifest['schemaVersion']==1
            and manifest['kind']=='job-observation-publication' and type(manifest['recordPresent']) is bool,
            'ARTIFACT_CONTENT_REJECTED')
    require(manifest['recordPresent']==('jobs.latest.json' in names),'ARTIFACT_CONTENT_REJECTED')
    if not manifest['recordPresent']:return None
    entry=next(entry for entry in entries if entry.filename=='jobs.latest.json')
    require(entry.file_size<=MAX_JOB_BYTES,'ARTIFACT_CONTENT_REJECTED')
    with zipped.open(entry) as stream:raw=stream.read(MAX_JOB_BYTES+1)
    return parse_record(raw,validate,MAX_JOB_BYTES)

def instant(value):
    """Calendar-valid UTC epoch nanoseconds, without floats or precision loss."""
    from datetime import datetime, timezone
    match = re.fullmatch(r'([0-9]{4})-([0-9]{2})-([0-9]{2})T([0-9]{2}):([0-9]{2}):([0-9]{2})(?:\.([0-9]{1,9}))?Z', value) if isinstance(value, str) else None
    require(match is not None, 'INVALID_OBSERVATION_TIMESTAMP')
    try:
        date = datetime(*(int(part) for part in match.groups()[:6]), tzinfo=timezone.utc)
    except ValueError:
        raise ObservationError('INVALID_OBSERVATION_TIMESTAMP') from None
    elapsed = date - datetime(1970, 1, 1, tzinfo=timezone.utc)
    return (elapsed.days * 86400 + elapsed.seconds) * 1_000_000_000 + int((match[7] or '').ljust(9, '0'))

def merge_records(baseline, incoming):
    if baseline is None:
        return copy.deepcopy(incoming)
    if incoming is None:
        return copy.deepcopy(baseline)
    before = instant(baseline['latestAttempt']['attemptedAt'])
    after = instant(incoming['latestAttempt']['attemptedAt'])
    if after == before:
        require(baseline['latestAttempt'] == incoming['latestAttempt'], 'CONFLICTING_OBSERVATION_ATTEMPT')
    result = copy.deepcopy(incoming if after > before else baseline)
    successes = [r['lastSuccess'] for r in (baseline, incoming) if r.get('lastSuccess')]
    if len(successes) == 2 and instant(successes[0]['capturedAt']) == instant(successes[1]['capturedAt']):
        require(successes[0] == successes[1], 'CONFLICTING_SUCCESS_SNAPSHOT')
    # A delayed earlier success may improve lastSuccess while keeping a newer
    # failure as latestAttempt. Never replace collection time with build time.
    result['lastSuccess'] = copy.deepcopy(max(successes, key=lambda s: instant(s['capturedAt']))) if successes else None
    return result


def merge_job_records(baseline,incoming):
    if baseline is None:return copy.deepcopy(incoming)
    if incoming is None:return copy.deepcopy(baseline)
    before,after=instant(baseline['capturedAt']),instant(incoming['capturedAt'])
    if before==after:require(baseline==incoming,'CONFLICTING_JOB_SNAPSHOT')
    return copy.deepcopy(incoming if after>before else baseline)

def validator(repository):
    source = (repository / 'apps/lab-web/src/lib/platform-observation.ts').as_uri()
    script = ("import fs from 'node:fs';import {validatePlatformObservation} from " + json.dumps(source) + ";"
              "try{if(!validatePlatformObservation(JSON.parse(fs.readFileSync(0,'utf8'))))process.exit(2);}"
              "catch{process.exit(2);}")
    def validate(record):
        result = subprocess.run(['node', '--experimental-strip-types', '--input-type=module', '-e', script],
                                input=json.dumps(record), text=True, capture_output=True, timeout=20)
        require(result.returncode == 0, 'SNAPSHOT_CONTRACT_REJECTED')
        require(instant(record['latestAttempt']['attemptedAt']) <= time.time_ns(), 'FUTURE_OBSERVATION_REJECTED')
    return validate


def job_validator(repository):
    source=(repository/'apps/lab-web/src/lib/job-observation.ts').as_uri()
    script=("import fs from 'node:fs';import {validateJobObservation} from "+json.dumps(source)+";"
            "try{if(!validateJobObservation(JSON.parse(fs.readFileSync(0,'utf8'))))process.exit(2);}catch{process.exit(2);}")
    def validate(record):
        result=subprocess.run(['node','--experimental-strip-types','--input-type=module','-e',script],
            input=json.dumps(record),text=True,capture_output=True,timeout=20)
        require(result.returncode==0,'JOB_SNAPSHOT_CONTRACT_REJECTED')
        require(record['environment']=='MINI_PC' and record['scope']=='DEPLOYED_RUNTIME'
                and re.fullmatch('[a-f0-9]{40}',record['sourceCommit']) is not None,'DEPLOYED_JOB_SNAPSHOT_REQUIRED')
        require(instant(record['capturedAt'])<=time.time_ns(),'FUTURE_JOB_OBSERVATION_REJECTED')
    return validate


def prepare_job_output(baseline,incoming,output_directory,artifact_directory,validate):
    result=merge_job_records(baseline,incoming)
    output_directory.mkdir(parents=True,exist_ok=True)
    artifact_directory.mkdir(parents=True,exist_ok=True)
    output=output_directory/'jobs.latest.json'
    artifact=artifact_directory/'jobs.latest.json'
    if result is not None:
        validate(result)
        encoded=json.dumps(result,ensure_ascii=True,separators=(',',':'))+'\n'
        require(len(encoded.encode('ascii'))<=MAX_JOB_BYTES,'SNAPSHOT_TOO_LARGE')
        output.write_text(encoded,encoding='utf-8',newline='\n')
        artifact.write_text(encoded,encoding='utf-8',newline='\n')
    else:
        # Remove any copied stale/isolated seed in these exact build paths.
        output.unlink(missing_ok=True);artifact.unlink(missing_ok=True)
    manifest={'schemaVersion':1,'kind':'job-observation-publication','recordPresent':result is not None}
    (artifact_directory/'publication.json').write_text(json.dumps(manifest)+'\n',encoding='utf-8',newline='\n')
    return result

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repository', type=Path, default=Path.cwd())
    parser.add_argument('--output-directory', type=Path, required=True)
    parser.add_argument('--seed-file', type=Path, required=True)
    parser.add_argument('--job-output-directory',type=Path)
    parser.add_argument('--job-artifact-directory',type=Path)
    parser.add_argument('--job-seed-file',type=Path)
    args = parser.parse_args()
    try:
        require(os.environ.get('GITHUB_REPOSITORY', '').lower() == REPOSITORY.lower()
                and os.environ.get('GITHUB_REF') == 'refs/heads/main', 'TRUSTED_MAIN_ONLY')
        validate = validator(args.repository.resolve())
        github = GitHub(os.environ.get('GH_TOKEN', ''))
        previous = previous_snapshot(github.get, github.archive, int(os.environ['GITHUB_RUN_ID']), int(os.environ['GITHUB_RUN_ATTEMPT']), validate)
        seed = parse_record(args.seed_file.read_bytes(), validate) if args.seed_file.is_file() else None
        baseline = merge_records(seed, previous)
        # GitHub's runner prints explicit step env. Read user data from the
        # event file instead so invalid payloads never appear in console env.
        event = json.loads(Path(os.environ['GITHUB_EVENT_PATH']).read_text('utf-8'))
        incoming_text = event.get('inputs', {}).get('platform_snapshot', '') if os.environ.get('GITHUB_EVENT_NAME') == 'workflow_dispatch' else ''
        require(isinstance(incoming_text, str), 'INVALID_DISPATCH_INPUT')
        incoming = parse_record(incoming_text.encode('utf-8'), validate) if incoming_text else None
        result = merge_records(baseline, incoming)
        require(result is not None, 'INITIAL_VERIFIED_SNAPSHOT_REQUIRED')
        validate(result)
        args.output_directory.mkdir(parents=True, exist_ok=True)
        output = args.output_directory / 'platform-observation.json'
        output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8', newline='\n')
        job_result=None
        if args.job_output_directory is not None:
            require(args.job_artifact_directory is not None,'JOB_ARTIFACT_DIRECTORY_REQUIRED')
            validate_jobs=job_validator(args.repository.resolve())
            previous_jobs=previous_snapshot(github.get,github.archive,int(os.environ['GITHUB_RUN_ID']),int(os.environ['GITHUB_RUN_ATTEMPT']),validate_jobs,jobs=True)
            job_seed=parse_record(args.job_seed_file.read_bytes(),validate_jobs,MAX_JOB_BYTES) if args.job_seed_file is not None and args.job_seed_file.is_file() else None
            job_baseline=merge_job_records(job_seed,previous_jobs)
            incoming_jobs_text=event.get('inputs',{}).get('jobs_snapshot','') if os.environ.get('GITHUB_EVENT_NAME')=='workflow_dispatch' else ''
            require(isinstance(incoming_jobs_text,str),'INVALID_DISPATCH_INPUT')
            incoming_jobs=parse_record(incoming_jobs_text.encode('utf-8'),validate_jobs,MAX_JOB_BYTES) if incoming_jobs_text else None
            job_result=prepare_job_output(job_baseline,incoming_jobs,args.job_output_directory,args.job_artifact_directory,validate_jobs)
        print(json.dumps({'snapshotPrepared': True, 'attemptedAt': result['latestAttempt']['attemptedAt'],
                          'lastSuccessAt': (result.get('lastSuccess') or {}).get('capturedAt'), 'gitCommitCreated': False,
                          'jobRecordPresent':job_result is not None,'jobCapturedAt':job_result['capturedAt'] if job_result else None}))
        return 0
    except Exception as error:
        print('Pages observation withheld: ' + (str(error) if isinstance(error, ObservationError) else 'VALIDATION_OR_METADATA_FAILURE'), file=sys.stderr)
        return 1

if __name__ == '__main__':
    raise SystemExit(main())
