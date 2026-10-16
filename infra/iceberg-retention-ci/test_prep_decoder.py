"""Synthetic source/identity/orchestration tests; no Docker, Java, or download."""
from contextlib import ExitStack
import copy
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest import mock
import zipfile

HERE = Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent/'platform-iceberg-composite-consumer-20261016'))
sys.path.insert(0,str(HERE))
import prep_decoder as p

SOURCE, OWN, DECODER = 'a'*40, 'b'*64, 'c'*64
CID, IMAGE = 'd'*64, 'sha256:'+'e'*64
NAME = 'closed-copy-prep-'+'f'*32
ENV = ['JAVA_HOME=/opt/java/openjdk','SPARK_HOME=/opt/spark']


def image():
    return {'Id':IMAGE,'Os':'linux','Architecture':'amd64','RepoDigests':[p.SPARK],
        'Config':{'Env':list(ENV),'Volumes':None,'Healthcheck':None}}


def cold():
    return {'Id':CID,'Name':'/'+NAME,'Image':IMAGE,'Created':'synthetic-created',
        'Config':{'Image':p.SPARK,'Labels':{'devdooly.io.closed-copy-prep':NAME,
            'devdooly.io.prep-source':OWN},'Entrypoint':['/bin/true'],
            'Cmd':['closed-copy-prep-never-started'],'User':'185:185','Env':list(ENV)},
        'HostConfig':{'ReadonlyRootfs':True,'Privileged':False,'NetworkMode':'none',
            'PortBindings':None,'NanoCpus':100000000,'Memory':128*1024**2,
            'MemorySwap':128*1024**2,'PidsLimit':16,'CapDrop':['ALL'],'CapAdd':None,
            'SecurityOpt':['no-new-privileges:true'],'RestartPolicy':{'Name':'no'},
            'AutoRemove':False,'OomKillDisable':None},
        'State':{'Running':False,'Pid':0,'StartedAt':p.ZERO_START,'OOMKilled':False},
        'Mounts':[],'NetworkSettings':{'Networks':{'none':{}}},'RestartCount':0}


class Guards(unittest.TestCase):
    def test_cold_pid_and_full_configuration_drift_reject_before_use(self):
        identity=p.image_identity(p.encoded([image()]))
        expected=p.cold_identity(p.encoded([cold()]),CID,NAME,OWN,identity)
        normalized=cold();normalized['HostConfig']['OomKillDisable']=False
        self.assertEqual(p.cold_identity(p.encoded([normalized]),CID,NAME,OWN,identity,expected),expected)
        for section,key,value in (('State','Pid',False),('State','Pid',1),
                ('HostConfig','ReadonlyRootfs',False),('HostConfig','Memory',256*1024**2),
                ('Config','User','0:0'),('Config','UnreviewedDockerDefault','changed')):
            changed=cold();changed[section][key]=value
            with self.subTest(section=section,key=key),self.assertRaises(ValueError):
                p.cold_identity(p.encoded([changed]),CID,NAME,OWN,identity,expected)

    def test_image_loader_environment_or_implicit_actor_cannot_be_attested(self):
        for key in ('JAVA_TOOL_OPTIONS','_JAVA_OPTIONS','JDK_JAVA_OPTIONS','CLASSPATH','loader_main'):
            changed=image();changed['Config']['Env'].append(key+'=SYNTHETIC_PRIVATE_VALUE')
            with self.subTest(key=key),self.assertRaisesRegex(ValueError,'PREP_IMAGE_OPTION_INJECTION_REJECTED'):
                p.image_identity(p.encoded([changed]))
        for field,value in (('Volumes',{'/foreign':{}}),('Healthcheck',{'Test':['CMD','false']})):
            changed=image();changed['Config'][field]=value
            with self.subTest(field=field),self.assertRaisesRegex(ValueError,'PREP_ACTUAL_PINNED_IMAGE_WITHOUT_IMPLICIT_ACTORS'):
                p.image_identity(p.encoded([changed]))

    def test_any_exported_iceberg_class_including_multirelease_is_shadowing(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary)
            for entry in ('org/apache/spark/Safe.class','org/apache/iceberg/Table.class',
                    'META-INF/versions/21/org/apache/iceberg/Table.class'):
                target=root/'synthetic.jar'
                with zipfile.ZipFile(target,'w') as archive:archive.writestr(entry,b'synthetic-not-executed')
                raw=target.read_bytes();row={'name':target.name,'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest()}
                tree={'scope':'SYNTHETIC_HOOK_ONLY_NOT_OS_PROOF'}
                with mock.patch.object(p,'file_hashes',return_value={**row}),mock.patch.object(p.artifacts,'classpath_tree_inventory',return_value=tree) as inventory:
                    if entry.startswith('org/apache/spark/'):
                        self.assertEqual(p.classpath_inventory(root,[row]),p.sha(p.encoded({'jars':[row],'tree':tree})))
                        inventory.assert_called_once_with(root,[row])
                    else:
                        with self.assertRaisesRegex(ValueError,'ONLY_LOCKED_RUNTIME_MAY_SUPPLY_ICEBERG_CLASSES'):
                            p.classpath_inventory(root,[row])
                        inventory.assert_not_called()


class SyntheticPreparation(unittest.TestCase):
    """Mock every child and platform I/O gate; these are not Linux prep proofs."""
    def harness(self, temporary, *, bad_source=None, compile_exit=0, remove_exit=0):
        root=Path(temporary);repo=root/'repo';(repo/'.local').mkdir(parents=True)
        home=root/'jdk';(home/'bin').mkdir(parents=True)
        output=repo/'.local'/('closed-copy-prep-'+'1'*32)
        pins={Path(p.artifacts.__file__).name:'2'*64,Path(p.processes.__file__).name:'3'*64}
        records,calls={},[]
        source_raw=b'// synthetic source, never compiled or executed\n'
        def proof(path, maximum=512*1024):
            path=Path(path)
            if path == Path(p.__file__).absolute():digest=OWN;raw=b'synthetic-executor'
            elif path.name in pins:digest=pins[path.name];raw=b'synthetic-helper'
            elif path == repo/p.JAVA_RELATIVE:digest=DECODER;raw=source_raw
            else:raise AssertionError('unexpected proof read')
            if path.name == bad_source:digest='0'*64
            return {'raw':raw,'sha256':digest}
        def hashes(path, maximum):
            if Path(path).name=='iceberg-runtime.jar':
                return {'bytes':p.ICEBERG_BYTES,'sha256':p.ICEBERG_SHA,'sha512':p.ICEBERG_SHA512}
            return {'bytes':100,'sha256':'4'*64,'sha512':'5'*128}
        def save(folder,name,value):
            self.assertNotIn((str(folder),name),records)
            raw=value if type(value) is bytes else p.encoded(value)
            records[(str(folder),name)]=copy.deepcopy(value)
            return {'raw':raw,'sha256':p.sha(raw)}
        def execute(argv,folder,name,cutoff,timeout,**kwargs):
            # Exercise the real shared cap API while substituting all child IO.
            p.processes.arguments(argv,name,cutoff,timeout,kwargs.get('maximum_stdout',1024**2),
                kwargs.get('maximum_stderr',65536),kwargs.get('persist_stdout',True),kwargs.get('stdout_filename'))
            calls.append({'name':name,'argv':list(argv),'cutoff':cutoff,**kwargs})
            stdout,stderr,rc=b'',b'',0
            if name=='compiler-java-version':stderr=b'openjdk version "21.0.9"\n'
            elif name=='compiler-javac-version':stdout=b'javac 21.0.9\n'
            elif name=='pinned-image-inspect':stdout=p.encoded([image()])
            elif name=='cold-export-create':stdout=CID.encode()+b'\n'
            elif name in ('cold-export-before','cold-export-after','cold-export-before-remove','failed-prep-cold-before-remove'):
                stdout=p.encoded([cold()])
            elif name=='compile-main-only':rc=compile_exit
            elif name in ('cold-export-remove','failed-prep-cold-remove'):
                stdout=CID.encode()+b'\n';rc=remove_exit
            return {'returncode':rc,'stdout':None if kwargs.get('stdout_filename') else stdout,
                'stderr':stderr,'receipt':{'synthetic':True,'name':name,'returnCode':rc}}
        env={'GITHUB_ACTIONS':'true','RUNNER_ENVIRONMENT':'github-hosted',
            'SOURCE_COMMIT':SOURCE,'GITHUB_SHA':SOURCE,'JAVA_HOME':str(home)}
        # Patching module-local OS/stat objects avoids changing pathlib's host OS.
        proxy=types.SimpleNamespace(name='posix',environ=env,path=os.path,pathsep=os.pathsep)
        class_rows=[{'path':'org/apache/iceberg/ClosedCopyDecoder.class','bytes':8,'sha256':'6'*64}]
        stack=ExitStack();self.addCleanup(stack.close)
        patches=((p,'os',proxy),(p,'sys',types.SimpleNamespace(platform='linux')),
            (p,'stat',types.SimpleNamespace(S_IMODE=lambda value:0o700)),
            (p,'read_proof',proof),(p,'file_hashes',hashes),(p,'save',save),
            (p,'checked_lock',lambda repo:{'raw':b'synthetic-lock','sha256':p.LOCK_SHA}),
            (p,'classpath_inventory',lambda jars,rows:'7'*64),
            (p.processes,'execute',execute),(p.time,'monotonic',lambda:100.0),
            (p.shutil,'disk_usage',lambda path:types.SimpleNamespace(free=10*1024**3)),
            (p.uuid,'uuid4',lambda:types.SimpleNamespace(hex='f'*32)),
            (p.artifacts,'unpack_jars',lambda archive,directory:[{'name':'synthetic.jar','bytes':1,'sha256':'8'*64}]),
            (p.artifacts,'scan_jar',lambda path:None),(p.artifacts,'seal_new_classes',lambda path:class_rows),
            (p.artifacts,'compiled_classes',lambda path:class_rows))
        for target,name,value in patches:stack.enter_context(mock.patch.object(target,name,value))
        # Only the synthetic chmod target is created; no archive or actual JAR.
        original_mkdir=Path.mkdir
        def mkdir(path,*args,**kwargs):
            original_mkdir(path,*args,**kwargs)
            if path==output:(output/'iceberg-runtime.jar').write_bytes(b'synthetic-not-a-jar')
        stack.enter_context(mock.patch.object(Path,'mkdir',mkdir))
        return repo,output,pins,records,calls

    def test_source_pin_rejections_happen_before_any_child_or_prep_output(self):
        for name,code in ((Path(p.__file__).name,'EXACT_PREP_EXECUTOR_SOURCE_REQUIRED'),
                (Path(p.artifacts.__file__).name,'EXACT_PREP_HELPER_SOURCE_REQUIRED'),
                ('ClosedCopyDecoder.java','EXACT_SINGLE_DECODER_JAVA_SOURCE')):
            with self.subTest(name=name),tempfile.TemporaryDirectory() as temporary:
                repo,output,pins,records,calls=self.harness(temporary,bad_source=name)
                with self.assertRaisesRegex(ValueError,code):p.prepare(repo,output,SOURCE,DECODER,OWN,pins)
                self.assertFalse(output.exists());self.assertEqual(calls,[]);self.assertEqual(records,{})

    def test_compile_failure_blocks_attestation_and_owns_exact_one_cold_cleanup(self):
        for remove_exit in (0,9):
            with self.subTest(remove_exit=remove_exit),tempfile.TemporaryDirectory() as temporary:
                repo,output,pins,records,calls=self.harness(temporary,compile_exit=1,remove_exit=remove_exit)
                with self.assertRaisesRegex(ValueError,'PREP_KNOWN_CHILD_NONZERO_NO_RETRY'):
                    p.prepare(repo,output,SOURCE,DECODER,OWN,pins)
                names=[row['name'] for row in calls]
                self.assertEqual(names.count('compile-main-only'),1)
                self.assertEqual(names.count('failed-prep-cold-remove'),1)
                self.assertNotIn('cold-export-remove',names)
                self.assertNotIn((str(output),'prep-attestation.private.json'),records)
                outcome=records[(str(output),'prep-result.private.json')]
                self.assertFalse(outcome['passed']);self.assertTrue(outcome['coldRemovalAttempted'])
                self.assertEqual(outcome['coldRemovedAndAbsent'],remove_exit==0)
                self.assertFalse(outcome['originalWorkloadStarted'])

    def test_synthetic_normal_orchestration_has_one_cold_actor_and_no_runtime_start(self):
        with tempfile.TemporaryDirectory() as temporary:
            repo,output,pins,records,calls=self.harness(temporary)
            result=p.prepare(repo,output,SOURCE,DECODER,OWN,pins)
            attested=records[(str(output),'prep-attestation.private.json')]
            self.assertEqual(result['root'],output)
            self.assertTrue(attested['coldExportNeverStarted']);self.assertTrue(attested['coldExportRemovedAndAbsent'])
            self.assertFalse(attested['runtimeJavaExecutionVerified']);self.assertFalse(attested['originalWorkloadStarted'])
            self.assertEqual(sum(row['name']=='cold-export-remove' for row in calls),1)
            self.assertEqual(sum(row['name']=='cold-export-create' for row in calls),1)
            self.assertFalse(any('start' in row['argv'] or 'exec' in row['argv'] for row in calls))
            compiled=next(row for row in calls if row['name']=='compile-main-only')
            self.assertIn('-proc:none',compiled['argv']);self.assertIn('-implicit:none',compiled['argv'])
            self.assertEqual(compiled['argv'][-1],str(output/'source'/'ClosedCopyDecoder.java'))
            exported=next(row for row in calls if row['name']=='export-classpath')
            self.assertEqual(exported['maximum_stdout'],p.artifacts.MAX_ARCHIVE)
            self.assertEqual(exported['stdout_filename'],'classpath.tar')


class CapturedTreeHook(unittest.TestCase):
    def test_full_tree_and_absence_receipt_changes_private_digest_without_exposing_receipt(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);target=root/'synthetic.jar'
            with zipfile.ZipFile(target,'w') as archive:archive.writestr('org/apache/spark/Safe.class',b'synthetic')
            raw=target.read_bytes();row={'name':target.name,'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest()}
            first={'directories':['','empty'],'verifiedAbsent':['gone.jar'],'privateMarker':'SYNTHETIC_PRIVATE'}
            second={**first,'directories':['','empty','new-directory']}
            third={**first,'verifiedAbsent':[]}
            with mock.patch.object(p,'file_hashes',return_value={**row}),mock.patch.object(p.artifacts,'classpath_tree_inventory',side_effect=[first,second,third]) as tree:
                values=[p.classpath_inventory(root,[row]) for _ in range(3)]
            self.assertEqual(len(set(values)),3);self.assertTrue(all(len(value)==64 for value in values))
            self.assertTrue(all('SYNTHETIC_PRIVATE' not in value for value in values));self.assertEqual(tree.call_count,3)


class PreparationTreeBoundary(unittest.TestCase):
    harness=SyntheticPreparation.harness
    def test_unverified_pre_tree_or_changed_post_tree_prevents_attestation_and_cleans_only_cold_actor(self):
        for stage in ('before','after'):
            with self.subTest(stage=stage),tempfile.TemporaryDirectory() as temporary:
                repo,output,pins,records,calls=self.harness(temporary)
                outcomes=[ValueError('JAR_CLASSPATH_TREE_EXACT')] if stage=='before' else ['7'*64,'8'*64]
                code='JAR_CLASSPATH_TREE_EXACT' if stage=='before' else 'ALL_COMPILER_SOURCE_CLASSPATH_INPUTS_UNCHANGED'
                with mock.patch.object(p,'classpath_inventory',side_effect=outcomes):
                    with self.assertRaisesRegex(ValueError,'^'+code+'$'):p.prepare(repo,output,SOURCE,DECODER,OWN,pins)
                names=[row['name'] for row in calls]
                self.assertEqual(names.count('compile-main-only'),0 if stage=='before' else 1)
                self.assertEqual(names.count('failed-prep-cold-remove'),1)
                self.assertNotIn((str(output),'prep-attestation.private.json'),records)
                self.assertFalse(records[(str(output),'prep-result.private.json')]['passed'])


if __name__=='__main__':unittest.main(verbosity=2)
