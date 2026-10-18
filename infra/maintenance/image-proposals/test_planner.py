"""Synthetic protection-boundary tests. No live GitHub/Git/registry/cluster access."""
from pathlib import Path
import copy
import hashlib
import importlib.util
import json
import unittest
from unittest.mock import patch

BASE = Path(__file__).resolve().parent
specification = importlib.util.spec_from_file_location('retention_planner_under_test', BASE/'planner.py')
planner = importlib.util.module_from_spec(specification)
specification.loader.exec_module(planner)
REPO = 'DevDooly/devdooly-platform-lab'
BOT = 'github-actions[bot]'
CURRENT_MAIN = '9'*40


def values(source, api='1', web='2', database='fixture-db'):
    return (f'api:\n  image:\n    repository: ghcr.io/devdooly/devdooly-platform-lab-api\n'
            f'    digest: sha256:{api*64}\n  sourceCommit: {source}\n'
            f'web:\n  image:\n    repository: ghcr.io/devdooly/devdooly-platform-lab-web\n'
            f'    digest: sha256:{web*64}\ndatabase:\n  existingSecret: {database}\n')


def snapshot(commit, text):
    raw = text.encode()
    return {'commit':commit,'text':text,'gitBlobSha':hashlib.sha1(('blob '+str(len(raw))+'\0').encode()+raw).hexdigest()}


def proposal(number, source, head, when, api, web):
    before = values('c'*40)
    after = values(source, api, web)
    publication = {'schemaVersion':1,'sourceCommit':source,'validationRunId':100+number,
        'jenkins':{'context':'ci/jenkins-test','buildNumber':10+number,'statusId':500+number,'issuer':'DevDooly'},
        'publicationRunUrl':f'https://github.com/{REPO}/actions/runs/{200+number}',
        'images':{component:{'repository':f'ghcr.io/devdooly/devdooly-platform-lab-{component}',
            'digest':'sha256:'+letter*64,'reference':f'ghcr.io/devdooly/devdooly-platform-lab-{component}@sha256:'+letter*64,
            'platform':'linux/amd64'} for component,letter in (('api',api),('web',web))}}
    # Independent literal of the publicly pinned proposer format, not planner._body().
    body = ('검증한 합성 데이터 Lab의 API·웹 이미지 digest만 갱신합니다. 비밀번호와 DB 설정은 변경하지 않습니다.\n\n'
        f'- 소스: `{source}`\n- Jenkins: build {10+number}, status {500+number}, `ci/jenkins-test`\n'
        f'- 컨테이너 검증: https://github.com/{REPO}/actions/runs/{100+number}\n'
        f'- 이미지 게시: https://github.com/{REPO}/actions/runs/{200+number}\n'
        f'- API: `ghcr.io/devdooly/devdooly-platform-lab-api@sha256:{api*64}`\n'
        f'- 웹: `ghcr.io/devdooly/devdooly-platform-lab-web@sha256:{web*64}`\n\n'
        '이 PR은 초안입니다. registry 출처·Helm 렌더링·변경 범위를 확인한 뒤 병합합니다. '
        '병합 후 Argo CD 동기화와 실제 HTTP·DB 결과를 별도로 확인해야 합니다. 자동 병합하지 않습니다.\n')
    pr = {'number':number,'state':'open','draft':True,'auto_merge':None,
        'base':{'ref':'main','sha':CURRENT_MAIN,'repo':{'full_name':REPO}},
        'head':{'ref':'automation/lab-images/'+source,'sha':head,'repo':{'full_name':REPO}},
        'html_url':f'https://github.com/{REPO}/pull/{number}', 'user':{'login':BOT,'type':'Bot'},
        'created_at':when,'updated_at':when,'commits':1,'labels':[],'body':body}
    return {'number':number,'observedDraft':True,'observedLabels':[], 'proof':{
        'pr':pr,'files':[{'filename':planner.VALUES,'status':'modified'}],
        'baseValues':snapshot(CURRENT_MAIN,before),'headValues':snapshot(head,after),
        'sourceValues':snapshot(source,before),'publication':publication,
        'reviewSnapshot':{'complete':True,'headSha':head,'reviewCount':0,'requestedReviewerCount':0,'humanCommentCount':0,'assigneeCount':0},
        'commitSnapshot':{'complete':True,'headSha':head,'items':[{'sha':head,'authorLogin':BOT,'committerLogin':BOT}]},
        'sourceComparison':{'baseSource':source,'headCommit':head,'mergeBaseSource':source,'aheadBy':1,'behindBy':0},
        'comparisonToLatest':None}}


def fixture():
    old = proposal(1,'e'*40,'a'*40,'2026-10-18T08:00:00Z','3','4')
    new = proposal(2,'f'*40,'b'*40,'2026-10-18T08:10:00Z','6','7')
    old['proof']['comparisonToLatest'] = {'baseSource':'e'*40,'headSource':'f'*40,
        'mergeBaseSource':'e'*40,'status':'ahead','aheadBy':1,'behindBy':0}
    return {'schemaVersion':1,'kind':'image-proposal-retention-input','repository':REPO,
        'capturedAt':'2026-10-18T09:00:00Z','currentMainCommit':CURRENT_MAIN,
        'protectedSources':{'complete':True,'current':['c'*40],'rollback':['d'*40]},'proposals':[old,new]}


class ProtectionBoundaries(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rules = planner.load_pinned_rules()

    def plan(self, document):
        return planner.plan_retention(document,self.rules)

    def row(self, plan, number=1):
        return next(row for row in plan['rows'] if row['number']==number)

    def test_strict_old_ancestor_is_only_a_candidate_and_input_is_unchanged(self):
        document=fixture(); original=copy.deepcopy(document); plan=self.plan(document)
        self.assertEqual(self.row(plan)['classification'],'SUPERSEDED_CANDIDATE')
        self.assertEqual(self.row(plan,2)['reason'],'LATEST_QUALIFIED_SOURCE')
        self.assertEqual(plan['supersededCandidateCount'],1)
        self.assertFalse(plan['applyEnabled']); self.assertEqual(plan['mutationOperations'],0)
        self.assertFalse(plan['registryContentsVerified']); self.assertFalse(plan['currentCiRevalidated'])
        self.assertEqual(document,original)

    def test_current_and_rollback_sources_are_preserved(self):
        document=fixture(); document['protectedSources'].update(current=['e'*40],rollback=['f'*40])
        plan=self.plan(document)
        self.assertEqual(plan['supersededCandidateCount'],0)
        self.assertTrue(all(row['reason']=='CURRENT_OR_ROLLBACK_PROTECTED' for row in plan['rows']))

    def test_incomplete_or_empty_rollback_protection_keeps_everything(self):
        for change in ({'complete':False},{'rollback':[]}):
            with self.subTest(change=change):
                document=fixture(); document['protectedSources'].update(change); plan=self.plan(document)
                self.assertEqual(plan['keepCount'],2); self.assertEqual(plan['supersededCandidateCount'],0)
                self.assertTrue(all(row['reason']=='PROTECTION_INCOMPLETE' for row in plan['rows']))

    def test_missing_public_proof_is_not_inferred_from_branch_or_title(self):
        document=fixture(); document['proposals'][0]['proof']=None
        self.assertEqual(self.row(self.plan(document))['reason'],'METADATA_INCOMPLETE')

    def test_human_commit_keeps_the_proposal(self):
        document=fixture(); document['proposals'][0]['proof']['commitSnapshot']['items'][0]['authorLogin']='DevDooly'
        self.assertEqual(self.row(self.plan(document))['reason'],'HUMAN_OR_UNKNOWN_COMMIT')

    def test_review_requests_comments_and_assignees_all_protect(self):
        for field in ('reviewCount','requestedReviewerCount','humanCommentCount','assigneeCount'):
            with self.subTest(field=field):
                document=fixture(); document['proposals'][0]['proof']['reviewSnapshot'][field]=1
                self.assertEqual(self.row(self.plan(document))['reason'],'REVIEWED_OR_HUMAN_ACTIVITY')

    def test_changed_body_or_labels_or_updated_time_is_preserved(self):
        for mode in ('body','label','time'):
            with self.subTest(mode=mode):
                document=fixture(); row=document['proposals'][0]
                if mode=='body': row['proof']['pr']['body']+='Human note\n'
                elif mode=='label': row['observedLabels']=['keep']
                else: row['proof']['pr']['updated_at']='2026-10-18T08:00:01Z'
                self.assertEqual(self.row(self.plan(document))['classification'],'KEEP')

    def test_existing_image_scope_validator_rejects_extra_file_or_db_change(self):
        for mode in ('file','database'):
            with self.subTest(mode=mode):
                document=fixture(); proof=document['proposals'][0]['proof']
                if mode=='file': proof['files'].append({'filename':'README.md','status':'modified'})
                else:
                    proof['headValues']=snapshot('a'*40,values('e'*40,'3','4','changed-db'))
                self.assertEqual(self.row(self.plan(document))['reason'],'IMAGE_ONLY_OR_PUBLICATION_UNVERIFIED')

    def test_ready_auto_merge_or_fork_is_preserved(self):
        for mode in ('ready','auto_merge','fork'):
            with self.subTest(mode=mode):
                document=fixture(); pr=document['proposals'][0]['proof']['pr']
                if mode=='ready': pr['draft']=False
                elif mode=='auto_merge': pr['auto_merge']={'enabled_by':{'login':BOT}}
                else: pr['head']['repo']['full_name']='other/repository'
                self.assertEqual(self.row(self.plan(document))['classification'],'KEEP')

    def test_older_timestamp_without_ancestry_proof_is_kept(self):
        document=fixture(); document['proposals'][0]['proof']['comparisonToLatest']=None
        self.assertEqual(self.row(self.plan(document))['reason'],'ANCESTRY_OR_AGE_UNVERIFIED')

    def test_different_sources_tied_for_latest_are_all_kept(self):
        document=fixture(); pr=document['proposals'][0]['proof']['pr']
        pr['created_at']=pr['updated_at']='2026-10-18T08:10:00Z'
        plan=self.plan(document)
        self.assertIsNone(plan['latestQualifiedProposal']); self.assertEqual(plan['supersededCandidateCount'],0)
        self.assertTrue(all(row['reason']=='NO_UNIQUE_LATEST' for row in plan['rows']))

    def test_malformed_head_and_future_or_unknown_snapshot_do_not_become_candidates(self):
        for mode in ('head','future','unknown_time'):
            with self.subTest(mode=mode):
                document=fixture()
                if mode=='head': document['proposals'][0]['proof']['pr']['head']=[]
                elif mode=='future':
                    pr=document['proposals'][1]['proof']['pr']; pr['created_at']=pr['updated_at']='2026-10-18T09:01:00Z'
                else: document['capturedAt']=None
                self.assertEqual(self.plan(document)['supersededCandidateCount'],0)

    def test_already_captured_sixteen_are_all_kept_without_fabricated_proof(self):
        document=json.loads((BASE/'examples/incomplete-historical-16.json').read_bytes())
        plan=self.plan(document)
        self.assertEqual(plan['keepCount'],16); self.assertEqual(plan['supersededCandidateCount'],0)
        self.assertIsNone(plan['latestQualifiedProposal'])

    def test_network_writer_and_live_metadata_clients_are_never_instantiated(self):
        with patch.object(self.rules.proposer,'GitHubWriter',side_effect=AssertionError('writer forbidden')), \
             patch.object(self.rules.proposer,'PublicGitHub',side_effect=AssertionError('network forbidden')), \
             patch.object(self.rules.validator,'PublicGitHub',side_effect=AssertionError('network forbidden')):
            self.assertEqual(self.plan(fixture())['supersededCandidateCount'],1)


if __name__=='__main__': unittest.main(verbosity=2)
