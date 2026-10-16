"""Pure synthetic CLI boundaries; no real git, Docker, Java, network, or Cloud."""
from contextlib import ExitStack, redirect_stdout
import copy
import importlib.util
import io
import json
import os
from pathlib import Path
import tempfile
import types
import unittest
from unittest import mock

HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('synthetic_capture_cli_under_test',HERE/'run_capture.py')
c=importlib.util.module_from_spec(spec);spec.loader.exec_module(c)
SOURCE='a'*40
MANIFEST='b'*64
CANARY='SYNTHETIC_PRIVATE_ERROR_ENV_URI_FULL_CONTAINER_ID_DO_NOT_PUBLISH'


def prepared():
    raw=c.encoded({'privateEnv':CANARY,'privatePath':CANARY})
    return {'proof':{'raw':raw,'sha256':c.digest(raw)},'classes':Path('synthetic-classes'),
        'iceberg':Path('synthetic-iceberg.jar')}


def outcome(status='DETERMINED'):
    private={'decoderStatus':'DECODED','decoderReasonCodes':[],
        'objectCandidateCount':0,'applyEnabled':False,
        'allCapturedObjects':[{'action':'KEEP','id':CANARY}],
        'privateException':CANARY,'rawEnvironment':{'PRIVATE_VALUE':CANARY}}
    inventory={'snapshots':[{'id':CANARY}],'refs':[{'name':CANARY}],'pins':[{'actor':CANARY}]}
    plan={'status':status,'applyEnabled':False,'objectCandidateCount':0,
        'snapshotCandidateCount':0,'files':[{'action':'KEEP','path':CANARY}]}
    if status=='UNDETERMINED':
        private['decoderStatus']='UNDETERMINED';private['decoderReasonCodes']=['MISSING_SNAPSHOT_REFERENCE']
        inventory=plan=None
    return {'result':{'inventory':inventory,'plan':plan,'privateReceipt':private},
        'receipt':{'mainCallsStarted':1,'mainReturnedZero':True,'decoderStoppedVerified':True,
            'decoderAttachCliReaped':True,'pipelineFinishedWithoutException':True,
            'failureCode':CANARY,'cid':CANARY,'argv':[CANARY]},'exitCode':0}


def rows(mapping,names):
    return [{'path':name,'bytes':len(mapping[name]),'sha256':c.digest(mapping[name])}
        for name in sorted(names)]


def source_fixture(directory):
    """Synthetic manifest closure; literal production pins are not overridden in source."""
    repo=Path(directory)/'repo';folder=repo/'infra/iceberg-retention-ci';folder.mkdir(parents=True)
    cli=folder/'run_capture.py';cli.write_bytes(b'# synthetic never executed source\n')
    files={name:('synthetic capture source '+name+'\n').encode() for name in c.FILES}
    files['run_capture.py']=cli.read_bytes()
    originals={name:('synthetic frozen source '+name+'\n').encode() for name in c.FROZEN_FILES}
    mapping={str(folder/name):raw for name,raw in files.items()}
    mapping.update({str(repo/'infra/cloud-lakehouse-ci'/name):raw for name,raw in originals.items()})
    for name in c.BASE_FILES | set(c.EXTERNALS):
        mapping.setdefault(str(repo/name),('synthetic immutable '+name+'\n').encode())
    frozen={'schemaVersion':1,'scope':'FRESH_CLOUD_SPARK_TRINO_BRONZE_TWO_FILE_COMPACTION',
        'status':'SOURCE_ONLY_NOT_RUN','files':rows(originals,c.FROZEN_FILES),
        'basePins':{name:c.digest(mapping[str(repo/name)]) for name in sorted(c.BASE_FILES)}}
    frozen_path='infra/cloud-lakehouse-ci/runtime-manifest.json'
    mapping[str(repo/frozen_path)]=c.encoded(frozen)
    immutable={name:mapping[str(repo/name)] for name in c.EXTERNALS}
    external_pins={name:c.digest(raw) for name,raw in immutable.items()}
    manifest={'schemaVersion':1,'scope':c.SCOPE,'status':'SOURCE_ONLY_NOT_RUN',
        'files':rows(files,c.FILES),'immutableInputs':rows(immutable,c.EXTERNALS)}
    path=folder/'runtime-manifest.json'
    fixture=types.SimpleNamespace(repo=repo,folder=folder,cli=cli,files=files,originals=originals,
        mapping=mapping,manifest=manifest,manifest_path=path,external_pins=external_pins)
    fixture.refresh=lambda:fixture.mapping.__setitem__(str(path),c.encoded(manifest))
    fixture.refresh()
    return fixture


class SourceAdmission(unittest.TestCase):
    def bindings(self,fixture):
        stack=ExitStack();self.addCleanup(stack.close)
        stack.enter_context(mock.patch.object(c,'__file__',str(fixture.cli)))
        stack.enter_context(mock.patch.object(c,'EXTERNALS',fixture.external_pins))
        def read(path,maximum=262144):
            raw=fixture.mapping[str(Path(path))];self.assertLessEqual(len(raw),maximum);return raw
        stack.enter_context(mock.patch.object(c,'read',read))
        return stack

    def test_exact_synthetic_transitive_closure_is_read_without_project_module_loading(self):
        with tempfile.TemporaryDirectory() as temporary:
            f=source_fixture(temporary)
            with self.bindings(f),mock.patch.object(c,'modules') as modules,mock.patch.object(c.subprocess,'run') as child:
                actual=c.reviewed_sources(f.repo,c.digest(f.mapping[str(f.manifest_path)]))
                self.assertEqual(actual,(f.files,f.originals));modules.assert_not_called();child.assert_not_called()

    def test_explicit_manifest_pin_type_duplicate_and_transitive_tampering_precede_modules_and_child(self):
        mutations=('pin-type','pin-mismatch','manifest-type','duplicate-key','duplicate-row',
            'bool-length','capture-source','frozen-source','transitive-source')
        for mutation in mutations:
            with self.subTest(mutation=mutation),tempfile.TemporaryDirectory() as temporary:
                f=source_fixture(temporary)
                if mutation=='manifest-type':f.manifest['schemaVersion']=True
                elif mutation=='duplicate-row':f.manifest['files'][-1]=copy.deepcopy(f.manifest['files'][0])
                elif mutation=='bool-length':f.manifest['files'][0]['bytes']=True
                elif mutation=='capture-source':f.mapping[str(f.folder/'copy_loader.py')]+=b'changed'
                elif mutation=='frozen-source':f.mapping[str(f.repo/'infra/cloud-lakehouse-ci/contract.py')]+=b'changed'
                elif mutation=='transitive-source':f.mapping[str(f.repo/'infra/spark-silver/silver_contract.py')]+=b'changed'
                f.refresh()
                if mutation=='duplicate-key':
                    f.mapping[str(f.manifest_path)]=f.mapping[str(f.manifest_path)].replace(
                        b'"schemaVersion":1',b'"schemaVersion":1,"schemaVersion":1')
                expected=c.digest(f.mapping[str(f.manifest_path)])
                if mutation=='pin-type':expected=True
                elif mutation=='pin-mismatch':expected='0'*64
                # main's first environment/argument checks are synthetic; no host state changes.
                argv=['run_capture.py','--source-manifest-sha256',str(expected),'--ack-fresh-closed-copy-capture']
                env={'GITHUB_ACTIONS':'true','RUNNER_ENVIRONMENT':'github-hosted',
                    'GITHUB_RUN_ATTEMPT':'1','SOURCE_COMMIT':SOURCE,'GITHUB_SHA':SOURCE}
                proxy=types.SimpleNamespace(platform='linux',argv=argv)
                with self.bindings(f),mock.patch.object(c,'sys',proxy),\
                        mock.patch('sys.argv',argv),\
                        mock.patch.object(c,'os',types.SimpleNamespace(environ=env)),\
                        mock.patch.object(c,'modules') as modules,mock.patch.object(c.subprocess,'run') as child:
                    with self.assertRaises((ValueError,TypeError)):
                        if mutation=='pin-type':c.reviewed_sources(f.repo,expected)
                        else:c.main()
                    modules.assert_not_called();child.assert_not_called()

    def test_strict_manifest_rejects_duplicate_nested_and_nonfinite_json_values(self):
        for raw in (b'{"files":{"path":1,"path":2}}',b'{"x":NaN}',b'{"x":1e9999}',b'{"x":-1e9999}'):
            with self.subTest(raw=raw),self.assertRaises(ValueError):c.strict(raw)
        for invalid in (None,True,123,'A'*64):
            with self.subTest(type=type(invalid).__name__),self.assertRaises(ValueError):
                c.reviewed_sources(Path('unused'),invalid)


class PublicProjection(unittest.TestCase):
    def test_success_is_aggregate_and_private_canaries_never_egress(self):
        value=c.safe_summary(SOURCE,MANIFEST,prepared=prepared(),outcome=outcome(),stage='SUMMARY')
        self.assertTrue(value['passed']);self.assertEqual(value['status'],'DETERMINED')
        self.assertTrue(all(value['checks'].values()));self.assertEqual(value['counts']['capturedObjectCount'],1)
        self.assertEqual(value['counts']['snapshotCount'],1)
        self.assertRegex(value['proofHashes']['normalizationReceiptCanonicalSha256'],'^[a-f0-9]{64}$')
        self.assertNotIn(CANARY,json.dumps(value));self.assertNotIn('normalizationReceiptSha256',value['proofHashes'])
        for flag in ('snapshotExpirationPerformed','objectDeletionPerformed','miniPcContacted',
                'liveTableIndependentlyVerified','rawProofsOrCredentialsUploaded','automaticRetryPerformed'):
            self.assertIs(value[flag],False)

    def test_undetermined_and_failed_never_publish_invented_observed_zero_counts(self):
        unknown=c.safe_summary(SOURCE,MANIFEST,stage='PREP')
        self.assertFalse(unknown['passed']);self.assertEqual(unknown['status'],'FAILED')
        for key in ('capturedObjectCount','snapshotCount','refCount','validationPinCount','snapshotCandidateCount'):
            self.assertIsNone(unknown['counts'][key])
        self.assertEqual(unknown['counts']['objectCandidateCount'],0)
        value=c.safe_summary(SOURCE,MANIFEST,prepared=prepared(),outcome=outcome('UNDETERMINED'),stage='SUMMARY')
        self.assertFalse(value['passed']);self.assertEqual(value['status'],'UNDETERMINED')
        self.assertEqual(value['failureCategory'],'CAPTURE_UNDETERMINED')
        self.assertEqual(value['counts']['capturedObjectCount'],1);self.assertIsNone(value['counts']['snapshotCount'])
        for field,bad in (('mainCallsStarted',2),('mainReturnedZero',False),('decoderStoppedVerified',False),
                ('decoderAttachCliReaped',False),('pipelineFinishedWithoutException',False)):
            changed=outcome();changed['receipt'][field]=bad
            failed=c.safe_summary(SOURCE,MANIFEST,prepared=prepared(),outcome=changed,stage='SUMMARY')
            self.assertFalse(failed['passed']);self.assertEqual(failed['status'],'FAILED')
        changed=outcome();changed['exitCode']=1
        self.assertFalse(c.safe_summary(SOURCE,MANIFEST,prepared=prepared(),outcome=changed)['passed'])

    def test_all_keep_no_apply_types_reasons_and_nonpartial_inventory_are_mandatory(self):
        mutations=('private-apply','private-candidate','private-bool-candidate','captured-delete',
            'plan-apply','plan-candidate','plan-bool-candidate','plan-delete','unknown-reason',
            'partial-inventory','snapshot-bool-count','bad-exit-type')
        for mutation in mutations:
            changed=outcome();private=changed['result']['privateReceipt'];plan=changed['result']['plan']
            if mutation=='private-apply':private['applyEnabled']=True
            elif mutation=='private-candidate':private['objectCandidateCount']=1
            elif mutation=='private-bool-candidate':private['objectCandidateCount']=False
            elif mutation=='captured-delete':private['allCapturedObjects'][0]['action']='DELETE'
            elif mutation=='plan-apply':plan['applyEnabled']=True
            elif mutation=='plan-candidate':plan['objectCandidateCount']=1
            elif mutation=='plan-bool-candidate':plan['objectCandidateCount']=False
            elif mutation=='plan-delete':plan['files'][0]['action']='DELETE'
            elif mutation=='unknown-reason':private['decoderReasonCodes']=[CANARY]
            elif mutation=='partial-inventory':changed['result']['inventory']=None
            elif mutation=='snapshot-bool-count':plan['snapshotCandidateCount']=True
            elif mutation=='bad-exit-type':changed['exitCode']=False
            with self.subTest(mutation=mutation),self.assertRaises((ValueError,TypeError)):
                c.safe_summary(SOURCE,MANIFEST,prepared=prepared(),outcome=changed)


class SyntheticMain(unittest.TestCase):
    def exercise(self,temporary,*,prep_fails=False,composite_fails=False):
        repo=Path(temporary)/'repo';folder=repo/'infra/iceberg-retention-ci';folder.mkdir(parents=True)
        script=folder/'run_capture.py';script.write_bytes(b'# synthetic location only\n')
        sources={name:('synthetic '+name).encode() for name in c.FILES}
        env={'GITHUB_ACTIONS':'true','RUNNER_ENVIRONMENT':'github-hosted','GITHUB_RUN_ATTEMPT':'1',
            'SOURCE_COMMIT':SOURCE,'GITHUB_SHA':SOURCE}
        argv=['run_capture.py','--source-manifest-sha256',MANIFEST,'--ack-fresh-closed-copy-capture']
        proxy_sys=types.SimpleNamespace(platform='linux',argv=argv)
        events=[];written=[];result=outcome();prepared_value=prepared()
        def prep(*args):
            events.append('prep')
            self.assertIs(proxy_sys.argv,argv)
            self.assertEqual(args[2],SOURCE)
            self.assertEqual(args[3],c.digest(sources['src/org/apache/iceberg/ClosedCopyDecoder.java']))
            self.assertEqual(args[4],c.digest(sources['prep_decoder.py']))
            self.assertEqual(args[5],{name:c.digest(sources[name]) for name in ('archive_classes.py','bounded_process.py')})
            if prep_fails:raise RuntimeError(CANARY)
            return prepared_value
        def original_main():
            events.append('original-main')
            self.assertEqual(proxy_sys.argv,[str(repo/'infra/cloud-lakehouse-ci/run_trial9.py'),
                '--source-manifest-sha256',c.EXTERNALS['infra/cloud-lakehouse-ci/runtime-manifest.json'],
                '--ack-fresh-cloud-trial9'])
            if composite_fails:raise RuntimeError(CANARY)
            return 0
        producer=types.SimpleNamespace(main=original_main)
        def composite(*args,**kwargs):
            events.append('composite')
            self.assertEqual(events,['prep','composite'])
            self.assertIs(args[0],producer);self.assertIs(kwargs['prep_proof'],prepared_value['proof'])
            self.assertEqual(kwargs['policy'],c.POLICY)
            self.assertEqual(kwargs['authority_source_sha256'],c.digest(sources['composite_entry.py']))
            args[0].main()
            return result
        loaded={'prep_decoder':types.SimpleNamespace(prepare=prep),
            'composite_entry':types.SimpleNamespace(run=composite),'producer':producer,
            'named_observer':object(),'copy_loader':object(),'normalize_graph':object()}
        proxy_os=types.SimpleNamespace(environ=env,path=os.path,getuid=lambda:script.stat().st_uid,
            umask=mock.Mock(return_value=0o022))
        proxy_stat=types.SimpleNamespace(S_ISDIR=c.stat.S_ISDIR,S_IMODE=lambda mode:0o700)
        output=io.StringIO()
        with mock.patch.object(c,'__file__',str(script)),mock.patch.object(c,'sys',proxy_sys),\
                mock.patch('sys.argv',argv),\
                mock.patch.object(c,'os',proxy_os),mock.patch.object(c,'stat',proxy_stat),\
                mock.patch.object(c,'reviewed_sources',return_value=(sources,{})) as gate,\
                mock.patch.object(c,'modules',return_value=loaded) as modules,\
                mock.patch.object(c.subprocess,'run',return_value=types.SimpleNamespace(
                    returncode=0,stdout=(SOURCE+'\n').encode(),stderr=b'')) as child,\
                mock.patch.object(c,'write_summary',side_effect=lambda folder,value:written.append(value)),\
                redirect_stdout(output):
            rc=c.main()
            gate.assert_called_once_with(repo,MANIFEST);modules.assert_called_once();child.assert_called_once()
            self.assertIs(proxy_sys.argv,argv)
        self.assertEqual(len(written),1);self.assertNotIn(CANARY,output.getvalue()+json.dumps(written))
        return rc,events,written[0],json.loads(output.getvalue())

    def test_prep_precedes_one_original_main_and_fixed_arguments_are_restored(self):
        with tempfile.TemporaryDirectory() as temporary:
            rc,events,summary,printed=self.exercise(temporary)
            self.assertEqual(events,['prep','composite','original-main']);self.assertEqual(rc,0)
            self.assertTrue(summary['passed']);self.assertEqual(set(printed),{'scope','passed','status'})

    def test_prep_or_original_failure_is_sanitized_and_never_retried(self):
        for phase in ('prep','original'):
            with self.subTest(phase=phase),tempfile.TemporaryDirectory() as temporary:
                rc,events,summary,printed=self.exercise(temporary,
                    prep_fails=phase=='prep',composite_fails=phase=='original')
                self.assertEqual(rc,1);self.assertFalse(summary['passed']);self.assertEqual(printed['status'],'FAILED')
                self.assertEqual(events,['prep'] if phase=='prep' else ['prep','composite','original-main'])
                self.assertEqual(summary['failureCategory'],'PREP_NOT_VERIFIED' if phase=='prep' else 'COMPOSITE_NOT_VERIFIED')


if __name__=='__main__':unittest.main(verbosity=2)
