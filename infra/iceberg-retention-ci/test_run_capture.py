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
    def exercise(self,temporary,*,prep_fails=False,composite_fails=False,prep_error=None):
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
            if prep_fails:raise prep_error if prep_error is not None else RuntimeError(CANARY)
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


PREP_SHA='9a4edbd67abac55cff8c480a62216867fb20d424611e7ef5a6b1d3fa6cab672b'
JAVA_SHA='d7f9fbab4e1951e5364dcec7e78b8aa1b86531ba034a4c1748b47158a80399d9'
PINS={'prep_decoder.py':PREP_SHA,'src/org/apache/iceberg/ClosedCopyDecoder.java':JAVA_SHA,
    'composite_entry.py':'f'*64}


def prep_records():
    return {'intent.json':{'scope':'SEPARATE_BOUNDED_COMPILER_PREPARATION_ONLY',
        'sourceCommit':SOURCE,'prepExecutorSha256':PREP_SHA,'decoderSourceSha256':JAVA_SHA,
        'artifactLockSha256':c.EXTERNALS['infra/spark-silver/artifact-lock.downloaded.json'],
        'budgetSeconds':600,'cleanupReserveSeconds':40,'originalWorkloadStarted':False,'automaticRetry':False},
        'prep-result.private.json':{'scope':'SEPARATE_PREP_ACTUAL_OUTCOME_NOT_RUNTIME_CLOSURE',
            'sourceCommit':SOURCE,'passed':False,'failureCode':CANARY,'knownColdCid':True,
            'coldIdentityBound':True,'coldRemovalAttempted':True,'coldRemovedAndAbsent':False,
            'originalWorkloadStarted':False,'automaticRetry':False}}


def child_record(name,started=10,nonzero=False):
    value={'schemaVersion':1,'scope':'ONE_BOUNDED_PREP_CHILD_ONLY','name':name,
        'argvSha256':'c'*64,'argumentCount':3,'startedMonotonic':started,
        'prepCutoffMonotonic':600,'executionDeadlineMonotonic':started+5,'timeoutSeconds':5,
        'maximumStdoutBytes':1024**2,'maximumStderrBytes':65536,'stdoutPersisted':True,
        'stdoutArchiveStreamedWithoutRam':False,'environmentSerialized':False,'rawArgvSerialized':False,
        'automaticRetry':False,'osMemoryLimitClaimed':False,'reapGraceSeconds':2,
        'outcome':'EXITED_NONZERO' if nonzero else 'EXITED_ZERO','returnCode':1 if nonzero else 0,
        'finishedMonotonic':started+1,'prepCutoffExceeded':False,'childStarted':True,'childPid':321,
        'childKilled':False,'childReaped':True,'timedOut':False,'stdoutBytes':14,'stderrBytes':0,
        'stdoutObservedBytes':14,'stderrObservedBytes':0,'stdoutSha256':'d'*64,'stderrSha256':'e'*64,
        'stdoutEofObserved':True,'stderrEofObserved':True,'stdoutOverflow':False,'stderrOverflow':False,
        'hashesDescribeAcceptedReadPrefixes':True,'outputPersistenceVerified':True,
        'dockerStopOrRemovalPerformed':False}
    assert set(value)==c.PREP_CHILD_KEYS
    return value


def composite_receipt(stage='DECODER'):
    return {'scope':'COMPOSITE_SOURCE_BOUND_PIPELINE_NOT_PUBLIC_COMPLETENESS','sourceCommit':SOURCE,
        'authoritySourceSha256':PINS['composite_entry.py'],'mainCallsStarted':1,'mainReturnedZero':True,
        'lastStage':stage,'inventoryProduced':False,'failureCode':CANARY,
        'safeNormalizationFailureCode':'UNKNOWN',
        'pipelineFinishedWithoutException':False,'decoderCreatedKnownCid':True,
        'decoderStoppedVerified':False,'decoderAttachCliReaped':False,'originalRoleStopCallsAdded':0,
        'originalInitializerStopCallsAdded':0,'automaticRetry':False,
        'snapshotExpirationOrGcPerformed':False,'publicCompletenessClaimed':False}


class DiagnosticProjection(unittest.TestCase):
    def test_exact_valueerror_literals_only_and_provider_canaries_never_escape(self):
        import subprocess
        known='ACTUAL_HOST_COMPILER_JAVA21_REQUIRED'
        self.assertEqual(c.literal_failure(ValueError(known)),known)
        for error in (ValueError(CANARY),RuntimeError(known),ValueError(known,CANARY),
                subprocess.TimeoutExpired([CANARY],1,output=CANARY,stderr=CANARY),
                OSError(CANARY),ValueError(known+'_'+CANARY)):
            with self.subTest(kind=type(error).__name__):
                self.assertEqual(c.literal_failure(error),'UNKNOWN')
                with mock.patch.object(c,'_read_prep_records',side_effect=error):
                    value=c.capture_diagnostic('PREP',False,error,None,Path('unused'),Path('unused'),SOURCE,PINS)
                self.assertNotIn(CANARY,json.dumps(value));self.assertIsNone(value['lastPrepChild'])
                self.assertIsNone(value['prepCleanup'])
        summary=c.safe_summary(SOURCE,MANIFEST)
        self.assertEqual(summary['schemaVersion'],2)
        self.assertEqual(set(summary['diagnostic']),{'stageAttempted','failureCode','lastPrepChild','prepCleanup'})

    def test_exact_receipts_types_extra_fields_and_foreign_source_are_suppressed(self):
        name='compiler-javac-version';valid=prep_records();valid[name+'.result.json']=child_record(name)
        child,cleanup=c._project_prep_records(valid,SOURCE,PREP_SHA,JAVA_SHA)
        self.assertEqual(set(child),{'name','class','outcome','returnCode','stdoutBytes','stderrBytes',
            'timedOut','childStarted','childReaped'});self.assertEqual(child['stdoutBytes'],14)
        for target,key,bad in (('intent.json','sourceCommit','b'*40),('intent.json','prepExecutorSha256','0'*64),
                ('intent.json','decoderSourceSha256','0'*64),('intent.json','artifactLockSha256','0'*64),
                ('intent.json','budgetSeconds',True),(name+'.result.json','EXTRA_PRIVATE',CANARY),
                (name+'.result.json','returnCode',True),(name+'.result.json','stderrBytes',False),
                (name+'.result.json','timedOut',0),(name+'.result.json','outcome',CANARY),
                (name+'.result.json','startedMonotonic',float('nan')),
                ('prep-result.private.json','EXTRA_PRIVATE',CANARY),
                ('prep-result.private.json','knownColdCid',1),
                ('prep-result.private.json','coldIdentityBound',False)):
            with self.subTest(target=target,key=key):
                records=copy.deepcopy(valid);records[target][key]=bad
                one,two=c._project_prep_records(records,SOURCE,PREP_SHA,JAVA_SHA)
                if target=='intent.json':self.assertEqual((one,two),(None,None))
                elif target==name+'.result.json':self.assertIsNone(one)
                else:self.assertIsNone(two)
                self.assertNotIn(CANARY,json.dumps([one,two]))
        self.assertEqual(c._project_prep_records({},SOURCE,PREP_SHA,JAVA_SHA),(None,None))
        unknown=c.safe_summary(SOURCE,MANIFEST)
        self.assertIsNone(unknown['counts']['capturedObjectCount'])
        self.assertIsNone(unknown['counts']['snapshotCount'])

    def test_last_observed_cleanup_child_does_not_replace_first_failure(self):
        records=prep_records()
        records['compiler-javac-version.result.json']=child_record('compiler-javac-version',10)
        records['failed-prep-cold-remove.result.json']=child_record('failed-prep-cold-remove',20,True)
        first=ValueError('ACTUAL_HOST_COMPILER_JAVA21_REQUIRED')
        with mock.patch.object(c,'_read_prep_records',return_value=records):
            value=c.capture_diagnostic('PREP',False,first,None,Path('unused'),Path('unused'),SOURCE,PINS)
        self.assertEqual(value['failureCode'],first.args[0])
        self.assertEqual(value['lastPrepChild']['name'],'failed-prep-cold-remove')
        self.assertEqual(value['lastPrepChild']['returnCode'],1)
        self.assertIs(value['prepCleanup']['coldRemovedAndAbsent'],False)
        self.assertNotIn(CANARY,json.dumps(value));self.assertNotIn('argvSha256',json.dumps(value))
        with mock.patch.object(c,'_read_prep_records',side_effect=RuntimeError(CANARY)):
            value=c.capture_diagnostic('PREP',False,first,None,Path('unused'),Path('unused'),SOURCE,PINS)
        self.assertEqual(value['failureCode'],first.args[0]);self.assertIsNone(value['prepCleanup'])
        records['compiler-javac-version.result.json']['startedMonotonic']=20
        records['compiler-javac-version.result.json']['finishedMonotonic']=21
        records['compiler-javac-version.result.json']['executionDeadlineMonotonic']=25
        for name in ('compiler-javac-version','failed-prep-cold-remove'):
            self.assertEqual(c._prep_child(records[name+'.result.json'],name)['name'],name)
        self.assertIsNone(c._project_prep_records(records,SOURCE,PREP_SHA,JAVA_SHA)[0])

    def test_returned_composite_stage_is_fixed_and_never_publishes_private_failurecode(self):
        receipt=composite_receipt()
        with mock.patch.object(c,'_read_prep_records',return_value={}):
            value=c.capture_diagnostic('SUMMARY',False,None,{'receipt':receipt},None,None,SOURCE,PINS)
        self.assertEqual(value['stageAttempted'],'DECODER');self.assertEqual(value['failureCode'],'UNKNOWN')
        self.assertNotIn(CANARY,json.dumps(value))
        for key,bad in (('lastStage',CANARY),('sourceCommit','b'*40),('authoritySourceSha256','0'*64),
                ('mainCallsStarted',True),('decoderStoppedVerified',1),('EXTRA_PRIVATE',CANARY)):
            changed=copy.deepcopy(receipt);changed[key]=bad
            with self.subTest(key=key),mock.patch.object(c,'_read_prep_records',return_value={}):
                value=c.capture_diagnostic('SUMMARY',False,None,{'receipt':changed},None,None,SOURCE,PINS)
            self.assertEqual(value['stageAttempted'],'SUMMARY');self.assertNotIn(CANARY,json.dumps(value))

    def test_real_main_catch_keeps_literal_failure_when_diagnostic_io_fails(self):
        import subprocess
        with tempfile.TemporaryDirectory() as temporary,\
                mock.patch.object(c,'_read_prep_records',side_effect=subprocess.TimeoutExpired(
                    [CANARY],1,output=CANARY,stderr=CANARY)):
            rc,events,summary,printed=SyntheticMain().exercise(temporary,prep_fails=True,
                prep_error=ValueError('ACTUAL_HOST_COMPILER_JAVA21_REQUIRED'))
        self.assertEqual(rc,1);self.assertEqual(events,['prep'])
        self.assertEqual(summary['diagnostic']['failureCode'],'ACTUAL_HOST_COMPILER_JAVA21_REQUIRED')
        self.assertIsNone(summary['diagnostic']['lastPrepChild']);self.assertIsNone(summary['diagnostic']['prepCleanup'])
        self.assertNotIn(CANARY,json.dumps(summary)+json.dumps(printed))

    @unittest.skipUnless(os.name=='posix','actual Linux openat/owner/mode checks require POSIX')
    def test_private_linux_metadata_reader_rejects_symlinks_links_modes_and_corruption(self):
        with tempfile.TemporaryDirectory() as temporary:
            local=Path(temporary)/'.local';local.mkdir(mode=0o700)
            root=local/('closed-copy-prep-'+'1'*32);root.mkdir(mode=0o700)
            records=prep_records();name='compiler-javac-version'
            records[name+'.result.json']=child_record(name)
            for filename,value in records.items():
                (root/filename).write_bytes(c.encoded(value));(root/filename).chmod(0o600)
            # These raw provider streams exist but must never be opened by the reader.
            (root/(name+'.stderr.private')).write_text(CANARY)
            read=c._read_prep_records(root,local)
            self.assertEqual(c._project_prep_records(read,SOURCE,PREP_SHA,JAVA_SHA)[0]['stdoutBytes'],14)
            path=root/(name+'.result.json');saved=path.read_bytes()
            for mutation in ('mode','symlink','hardlink','corrupt','parent-mode'):
                with self.subTest(mutation=mutation):
                    if mutation=='mode':path.chmod(0o644)
                    elif mutation=='symlink':path.unlink();path.symlink_to(root/'intent.json')
                    elif mutation=='hardlink':os.link(path,root/'another-link')
                    elif mutation=='corrupt':path.write_bytes(b'{"x":NaN}')
                    else:local.chmod(0o755)
                    with self.assertRaises((ValueError,OSError)):c._read_prep_records(root,local)
                    if mutation=='symlink':path.unlink();path.write_bytes(saved)
                    elif mutation=='hardlink':(root/'another-link').unlink()
                    elif mutation=='corrupt':path.write_bytes(saved)
                    path.chmod(0o600);local.chmod(0o700)


if __name__=='__main__':unittest.main(verbosity=2)
