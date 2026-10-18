"""Pure KEEP/SUPERSEDED_CANDIDATE planning from captured public metadata.

No GitHub client, writer, Git, cluster or deletion operation is called.
Historical publication validation is not current CI/registry/deployment approval.
"""
from datetime import datetime
from pathlib import Path
from types import ModuleType, SimpleNamespace
import argparse
import base64
import hashlib
import json
import re
import sys

REPOSITORY = 'DevDooly/devdooly-platform-lab'
BOT = 'github-actions[bot]'
BRANCH = re.compile(r'automation/lab-images/([a-f0-9]{40})')
SHA = re.compile(r'[a-f0-9]{40}')
RULES_PIN = '662d4a5e92f2e3f614a952c506db7be5640df3a92d119d14290935516a3b03d6'
VALUES = 'gitops/environments/home-lab/values.yaml'


class Hold(Exception):
    def __init__(self, reason):
        self.reason = reason


def need(condition, reason='PROVENANCE_UNVERIFIED'):
    if not condition:
        raise Hold(reason)


def load_pinned_rules(directory=None):
    """Separate local adapter. Imports exact public sources, without running their CLI."""
    base = Path(directory) if directory is not None else Path(__file__).resolve().parent
    repository = base.parents[2]
    raw = (base/'public-rules-pins.json').read_bytes()
    if hashlib.sha256(raw).hexdigest() != RULES_PIN:
        raise ValueError('PUBLIC_RULE_PIN_MISMATCH')
    pins = json.loads(raw)
    names = ('gitops_values', 'ci_publication_gate', 'validate_gitops_pr', 'propose_gitops_pr')
    need(len(pins['files']) == 4)
    sources = {}
    for item in pins['files']:
        data = (repository/item['repositoryPath']).read_bytes()
        need(len(data) == item['bytes'] and hashlib.sha256(data).hexdigest() == item['sha256'])
        sources[item['path']] = data
    missing = object()
    previous = {name: sys.modules.get(name, missing) for name in names}
    modules = {}
    try:
        for name in names:
            filename = repository/'infra/scripts'/(name+'.py')
            module = ModuleType(name)
            module.__file__ = str(filename)
            sys.modules[name] = module
            exec(compile(sources[name+'.py'], str(filename), 'exec'), module.__dict__)
            modules[name] = module
    finally:
        for name, module in previous.items():
            if module is missing:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = module
    return SimpleNamespace(values=modules['gitops_values'], validator=modules['validate_gitops_pr'],
                           proposer=modules['propose_gitops_pr'])


def _time(value):
    need(type(value) is str and re.fullmatch(r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z', value))
    return datetime.fromisoformat(value.replace('Z', '+00:00'))


def _source(proof):
    if type(proof) is dict:
        pr = proof.get('pr')
        head = pr.get('head') if type(pr) is dict else None
        ref = head.get('ref') if type(head) is dict else None
        match = BRANCH.fullmatch(ref) if type(ref) is str else None
        if match:
            return match[1]
    return None


def _snapshot(value, commit):
    need(type(value) is dict and set(value) == {'commit', 'text', 'gitBlobSha'})
    need(value['commit'] == commit and type(value['text']) is str)
    raw = value['text'].encode('utf-8')
    need(len(raw) <= 32768)
    need(hashlib.sha1(('blob '+str(len(raw))+'\0').encode()+raw).hexdigest() == value['gitBlobSha'])
    return value['text']


def _body(manifest, after):
    """Exact historical proposer body format; mismatches are held, never repaired."""
    source = manifest['sourceCommit']; jenkins = manifest['jenkins']
    return (
        '검증한 합성 데이터 Lab의 API·웹 이미지 digest만 갱신합니다. 비밀번호와 DB 설정은 변경하지 않습니다.\n\n'
        f"- 소스: `{source}`\n"
        f"- Jenkins: build {jenkins['buildNumber']}, status {jenkins['statusId']}, `{jenkins['context']}`\n"
        f"- 컨테이너 검증: https://github.com/{REPOSITORY}/actions/runs/{manifest['validationRunId']}\n"
        f"- 이미지 게시: {manifest['publicationRunUrl']}\n"
        f"- API: `{after['api']['image']['repository']}@{after['api']['image']['digest']}`\n"
        f"- 웹: `{after['web']['image']['repository']}@{after['web']['image']['digest']}`\n\n"
        '이 PR은 초안입니다. registry 출처·Helm 렌더링·변경 범위를 확인한 뒤 병합합니다. '
        '병합 후 Argo CD 동기화와 실제 HTTP·DB 결과를 별도로 확인해야 합니다. 자동 병합하지 않습니다.\n'
    )


def _qualify(row, current_main, captured, rules):
    proof = row['proof']
    need(type(proof) is dict, 'METADATA_INCOMPLETE')
    need(set(proof) == {'pr', 'files', 'baseValues', 'headValues', 'sourceValues', 'publication',
                        'reviewSnapshot', 'commitSnapshot', 'sourceComparison', 'comparisonToLatest'})
    pr = proof['pr']; source = _source(proof)
    need(source is not None and type(pr) is dict)
    need(pr.get('number') == row['number'])
    need(pr.get('draft') is True and row['observedDraft'] is True, 'NOT_A_DRAFT')
    need(row['observedLabels'] == [] and pr.get('labels') == [], 'HUMAN_OR_PROTECTED_LABEL')
    need(pr.get('base', {}).get('sha') == current_main)
    try:
        rules.proposer.require_draft_pr(pr, 'automation/lab-images/'+source, pr['head']['sha'])
    except Exception:
        raise Hold('SAFE_DRAFT_UNVERIFIED') from None
    need(pr.get('user', {}).get('login') == BOT and pr.get('user', {}).get('type') == 'Bot')
    created = _time(pr.get('created_at')); updated = _time(pr.get('updated_at'))
    need(captured is not None and created <= updated <= captured, 'SNAPSHOT_TIME_UNVERIFIED')
    need(created == updated, 'HUMAN_OR_UNEXPLAINED_UPDATE')
    review = proof['reviewSnapshot']
    need(type(review) is dict and set(review) == {'complete', 'headSha', 'reviewCount', 'requestedReviewerCount', 'humanCommentCount', 'assigneeCount'})
    need(review['complete'] is True and review['headSha'] == pr['head']['sha'], 'REVIEW_HISTORY_INCOMPLETE')
    need(all(type(review[key]) is int and review[key] >= 0 for key in ('reviewCount','requestedReviewerCount','humanCommentCount','assigneeCount')))
    need(all(review[key] == 0 for key in ('reviewCount','requestedReviewerCount','humanCommentCount','assigneeCount')), 'REVIEWED_OR_HUMAN_ACTIVITY')
    commits = proof['commitSnapshot']
    need(type(commits) is dict and set(commits) == {'complete', 'headSha', 'items'})
    need(commits['complete'] is True and commits['headSha'] == pr['head']['sha'], 'COMMIT_HISTORY_INCOMPLETE')
    need(type(commits['items']) is list and 1 <= len(commits['items']) <= 10)
    need(type(pr.get('commits')) is int and pr['commits'] == len(commits['items']))
    for item in commits['items']:
        need(type(item) is dict and set(item) == {'sha','authorLogin','committerLogin'})
        need(type(item['sha']) is str and SHA.fullmatch(item['sha']))
        need(item['authorLogin'] == BOT and item['committerLogin'] == BOT, 'HUMAN_OR_UNKNOWN_COMMIT')
    need(commits['items'][-1]['sha'] == pr['head']['sha'])
    comparison = proof['sourceComparison']
    need(type(comparison) is dict and set(comparison) == {'baseSource','headCommit','mergeBaseSource','aheadBy','behindBy'})
    need(comparison['baseSource'] == source and comparison['mergeBaseSource'] == source and comparison['headCommit'] == pr['head']['sha'])
    need(type(comparison['aheadBy']) is int and comparison['aheadBy'] == len(commits['items']) and
         type(comparison['behindBy']) is int and comparison['behindBy'] == 0)
    base_text = _snapshot(proof['baseValues'], current_main)
    head_text = _snapshot(proof['headValues'], pr['head']['sha'])
    source_text = _snapshot(proof['sourceValues'], source)
    local = {
        f"pulls/{row['number']}": pr,
        f"pulls/{row['number']}/files?per_page=100&page=1": proof['files'],
    }
    for commit, text in ((current_main,base_text),(pr['head']['sha'],head_text)):
        local[f'contents/{VALUES}?ref={commit}'] = {'type':'file','encoding':'base64',
            'size':len(text.encode()),'content':base64.b64encode(text.encode()).decode()}
    def get(key):
        if key not in local:
            raise ValueError('UNEXPECTED_OFFLINE_LOOKUP')
        return local[key]
    try:
        scope = rules.validator.evaluate_pr(row['number'], current_main, pr['head']['sha'], get)
        # The source parameter is a captured historical main context, not today's main gate.
        expected, branch = rules.proposer.prepare(proof['publication'], source, source_text, 'DevDooly')
        need(branch == pr['head']['ref'] and rules.values.parse(head_text) == expected)
        need(scope['scope'] == 'GITOPS_CHANGE_SCOPE_ONLY')
    except Exception:
        raise Hold('IMAGE_ONLY_OR_PUBLICATION_UNVERIFIED') from None
    need(type(pr.get('body')) is str and pr['body'] == _body(proof['publication'], expected), 'BODY_OR_PROVENANCE_CHANGED')
    return {'number':row['number'],'source':source,'created':created,'proof':proof}


def plan_retention(document, rules):
    """Pure planner: no I/O and no mutation of document or external state."""
    required = {'schemaVersion','kind','repository','capturedAt','currentMainCommit','protectedSources','proposals'}
    if (type(document) is not dict or not required <= set(document) or
        set(document)-required-{'captureNote'} or type(document['schemaVersion']) is not int or document['schemaVersion'] != 1 or
        document['kind'] != 'image-proposal-retention-input' or document['repository'] != REPOSITORY or
        type(document['currentMainCommit']) is not str or not SHA.fullmatch(document['currentMainCommit'])):
        raise ValueError('INVALID_PUBLIC_INPUT')
    proposals = document['proposals']; protection = document['protectedSources']
    if type(proposals) is not list or len(proposals) > 100 or type(protection) is not dict or set(protection) != {'complete','current','rollback'}:
        raise ValueError('INVALID_PUBLIC_INPUT')
    if type(protection['complete']) is not bool:
        raise ValueError('INVALID_PUBLIC_INPUT')
    for key in ('current','rollback'):
        if type(protection[key]) is not list or len(protection[key]) > 16 or any(type(value) is not str or not SHA.fullmatch(value) for value in protection[key]):
            raise ValueError('INVALID_PUBLIC_INPUT')
    complete = protection['complete'] and bool(protection['current']) and bool(protection['rollback'])
    try:
        captured = None if document['capturedAt'] is None else _time(document['capturedAt'])
    except Exception:
        raise ValueError('INVALID_PUBLIC_INPUT') from None
    protected = set(protection['current']+protection['rollback'])
    rows = {}; qualified = {}
    for proposal in proposals:
        if (type(proposal) is not dict or set(proposal) != {'number','observedDraft','observedLabels','proof'} or
            type(proposal['number']) is not int or proposal['number'] <= 0 or proposal['number'] in rows or
            type(proposal['observedDraft']) is not bool or type(proposal['observedLabels']) is not list):
            raise ValueError('INVALID_PUBLIC_INPUT')
        number = proposal['number']; source = _source(proposal['proof'])
        rows[number] = {'number':number,'classification':'KEEP','reason':'PROVENANCE_UNVERIFIED','sourceCommit':source,'supersededBy':None}
        if not complete:
            rows[number]['reason'] = 'PROTECTION_INCOMPLETE'; continue
        if source in protected:
            rows[number]['reason'] = 'CURRENT_OR_ROLLBACK_PROTECTED'; continue
        try:
            qualified[number] = _qualify(proposal, document['currentMainCommit'], captured, rules)
        except Hold as hold:
            rows[number]['reason'] = hold.reason
        except Exception:
            rows[number]['reason'] = 'PROVENANCE_UNVERIFIED'
    latest = None
    if qualified:
        newest = max(record['created'] for record in qualified.values())
        matches = [record for record in qualified.values() if record['created'] == newest]
        if len({record['source'] for record in matches}) == 1:
            latest = max(matches, key=lambda record:record['number'])
    for number, record in qualified.items():
        if latest is None:
            rows[number]['reason'] = 'NO_UNIQUE_LATEST'; continue
        if record['source'] == latest['source']:
            rows[number]['reason'] = 'LATEST_QUALIFIED_SOURCE'; continue
        comparison = record['proof']['comparisonToLatest']
        if (type(comparison) is not dict or set(comparison) != {'baseSource','headSource','mergeBaseSource','status','aheadBy','behindBy'} or
            comparison['baseSource'] != record['source'] or comparison['headSource'] != latest['source'] or
            comparison['mergeBaseSource'] != record['source'] or comparison['status'] != 'ahead' or
            type(comparison['aheadBy']) is not int or comparison['aheadBy'] <= 0 or
            type(comparison['behindBy']) is not int or comparison['behindBy'] != 0 or
            record['created'] >= latest['created']):
            rows[number]['reason'] = 'ANCESTRY_OR_AGE_UNVERIFIED'; continue
        rows[number].update(classification='SUPERSEDED_CANDIDATE',reason='STRICT_AUTOMATION_OLDER_ANCESTOR',supersededBy=latest['number'])
    result = sorted(rows.values(),key=lambda row:row['number'],reverse=True)
    return {'schemaVersion':1,'kind':'image-proposal-retention-plan','passed':True,
        'scope':'CAPTURED_PUBLIC_METADATA_DRY_RUN_ONLY','repository':REPOSITORY,
        'applyEnabled':False,'mutationOperations':0,'registryContentsVerified':False,
        'currentCiRevalidated':False,'deploymentVerified':False,
        'protectedSourcesComplete':bool(complete),'latestQualifiedProposal':latest['number'] if latest else None,
        'keepCount':sum(row['classification']=='KEEP' for row in result),
        'supersededCandidateCount':sum(row['classification']=='SUPERSEDED_CANDIDATE' for row in result),
        'rows':result}


def _unique(pairs):
    output = {}
    for key,value in pairs:
        if key in output: raise ValueError('INVALID_PUBLIC_INPUT')
        output[key] = value
    return output


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input',required=True); parser.add_argument('--output',required=True)
    args = parser.parse_args()
    source = Path(args.input); target = Path(args.output)
    if target.exists() or source.stat().st_size > 1024*1024:
        raise ValueError('INVALID_LOCAL_INPUT')
    document = json.loads(source.read_text(encoding='utf-8'),object_pairs_hook=_unique,
                          parse_constant=lambda unused: (_ for _ in ()).throw(ValueError('INVALID_PUBLIC_INPUT')))
    result = plan_retention(document,load_pinned_rules())
    with target.open('x',encoding='utf-8') as stream:
        stream.write(json.dumps(result,indent=2)+'\n')
    print(json.dumps({'passed':True,'keepCount':result['keepCount'],'supersededCandidateCount':result['supersededCandidateCount'],'applyEnabled':False}))


if __name__ == '__main__':
    try: main()
    except Exception:
        print(json.dumps({'passed':False,'failureCode':'INVALID_OR_UNVERIFIED_INPUT','applyEnabled':False}))
        raise SystemExit(1)
