"""Synthetic contracts only. No actual Cloud proof/copy paths are opened."""
import copy
import importlib.util
import json
import os
from pathlib import Path
import stat
import struct
import sys
import tempfile
import unittest
from unittest.mock import patch

import copy_loader as c
import normalize_graph as n

root = Path(os.environ.get('PLATFORM_LAB_SOURCE_ROOT', str(Path(__file__).resolve().parents[2])))
CONTRACT = root/'infra/cloud-lakehouse-ci/contract.py'
PLANNER = root/'infra/maintenance/iceberg_retention_plan.py'
SOURCE, AUTH = '1'*40, '2'*64
STAMP = '2026-10-16T00:00:05Z'
NOW = '2026-10-16T00:00:06Z'
POLICY = {'schemaVersion':1,'maxInventoryAgeSeconds':300,'minSnapshotAgeSeconds':1,'minimumSnapshotsToKeep':1}


def p(value=None, raw=None):
    raw = c.canonical(value) if raw is None else raw
    return {'raw':raw,'sha256':c.digest(raw)}


def replace_proof(bundle, name, change):
    value = c.proof_value(bundle[name]); change(value); bundle[name] = p(value)


def fixture():
    """Source-derived schemas with invented IDs/bytes, never an actual-pass record."""
    query_raw = CONTRACT.read_bytes(); pure = {}; exec(compile(query_raw,'<fixture-contract>','exec'), pure)
    assert c.digest(query_raw) == c.CONTRACT_SHA
    location = 's3://'+c.BUCKET+'/'+c.PREFIX+'bronze/synthetic_events'
    content, map_rows, aliases = {}, [], {}
    for name in ('current.metadata.json','old.metadata.json','ml1.avro','ml2.avro','ml3.avro','manifest.avro','delete.avro','data1.parquet','data2.parquet'):
        key = c.PREFIX+'bronze/synthetic_events/'+('metadata/' if not name.endswith('.parquet') else 'data/')+name
        raw = ('SYNTHETIC-'+name).encode(); identity = c.file_alias(c.BUCKET,key); aliases[name] = identity
        map_rows.append({'key':key,'size':len(raw),'sha256':c.digest(raw),'copy':c.digest(key.encode())+'.bin'})
        content[identity] = raw
    outside_key = c.PREFIX+'silver/sensor_outcomes/metadata/other.metadata.json'; raw = b'SYNTHETIC-OTHER'
    outside = c.file_alias(c.BUCKET,outside_key)
    map_rows.append({'key':outside_key,'size':len(raw),'sha256':c.digest(raw),'copy':c.digest(outside_key.encode())+'.bin'})
    content[outside] = raw; map_proof = p(sorted(map_rows,key=lambda row:row['key']))
    request = {'sourceCommit':SOURCE,'captureMapSha256':map_proof['sha256'],'approvedBucket':c.BUCKET,
        'approvedPrefix':c.PREFIX,'targetTable':{'catalog':'phase6','namespace':'bronze','table':'synthetic_events',
            'currentMetadataUri':location+'/metadata/current.metadata.json','tableLocation':location}}
    descriptor, descriptor_bytes = c.descriptor_from_map(map_proof['raw'],request)
    frame = c.build_frame(descriptor_bytes,descriptor['objects'],content)
    chain = [{'snapshot_id':str(101+i),'parent_id':None if i == 0 else str(100+i),'operation':op,'total_records':str(count)}
        for i,(op,count) in enumerate(zip(('append','append','replace'),(6,12,12)))]
    fingerprints = ['3'*64,'4'*64,'4'*64]
    spark = p({'passed':True,'snapshots':chain,'rowFingerprints':fingerprints,'oldWarehouseObjects':4,'afterWarehouseObjects':len(map_rows)})
    summary = p({'sourceCommit':SOURCE,'passed':True,'failure':None,'ownedContainersStopped':True,'ownedInitializerStopped':True,
        'enabledOomKillerRepresentationsVerified':True,'workloadElapsedMillis':5000,
        'checks':{k:True for k in ('frozenInputs','vendor','pinnedImages','freshPhysicalVolumes','actualMemAvailable7Gi','internalNetwork',
            'singleClock','normalSparkExit','normalTrinoExit','pythonReaderExit','jdbcAndWholeObjectsUnchanged')},
        'cleanupDiagnostics':{'initializer':'STOPPED_VERIFIED','containers':'STOPPED_VERIFIED'},
        'result':{'snapshotIds':['101','102','103'],'rowFingerprints':fingerprints}})
    clock = p({'startedMonotonic':100.0,'hostBootId':'a'*8+'-'+ 'b'*4+'-'+ 'c'*4+'-'+ 'd'*4+'-'+ 'e'*12,'budgetSeconds':600})
    header = {'sourceCommit':SOURCE,'producerSha256':c.PRODUCER_SHA,'runtimeManifestSha256':c.RUNTIME_SHA}
    named = []
    pointer = ('phase6|bronze|synthetic_events|'+request['targetTable']['currentMetadataUri']+'|'+location+'/metadata/old.metadata.json\n'
        +'phase6|silver|sensor_outcomes|s3://'+c.BUCKET+'/'+outside_key+'|\n').encode()
    for index,(name,stage) in enumerate(zip(c.NAMES,c.STAGES),1):
        checkpoint = p({**header,'scope':'NAMED_JDBC_RETURN_BYTES_ONLY','sequence':index,'stage':stage,
            'before':{'utc':'2026-10-16T00:00:0'+str(index)+'Z','monotonicNs':(100+index)*10**9},
            'after':{'utc':STAMP if index == 3 else '2026-10-16T00:00:0'+str(index)+'Z','monotonicNs':(100+index)*10**9+1},
            'rawBytes':len(pointer),'rawSha256':c.digest(pointer),'returnBytesPreserved':True,'originalDeadlineStartedMonotonic':100.0})
        named.append({'name':name,'raw':pointer,'rawSha256':c.digest(pointer),'checkpoint':checkpoint['raw'],'checkpointSha256':checkpoint['sha256']})
    intents, raw_intents = [], []
    for name,sql in pure['query_plan'](chain):
        proof = p({'sqlSha256':c.digest(sql.encode()),'automaticRetry':False})
        raw_intents.append({'name':name,**proof}); intents.append({'name':name,'rawSha256':proof['sha256'],'sqlSha256':c.digest(sql.encode())})
    validation = p({**header,'schemaVersion':1,'scope':'SAME_RUN_FROZEN_SPARK_TRINO_SNAPSHOT_VALIDATION',
        'authoritySourceSha256':AUTH,'queryPlanSourceSha256':c.CONTRACT_SHA,'capturedAt':STAMP,
        'producerSummarySha256':summary['sha256'],'sparkResultSha256':spark['sha256'],
        'snapshotIds':['101','102','103'],'rowFingerprints':fingerprints,'namedSqlIntents':intents,
        'closedActorScope':'THIS_FRESH_TRIAL_ONLY','backupExportActorCount':0,'individualNamedQueryRawResultsClaimed':False})
    roles = [{'id':str(i)*64,'role':role,'running':False,'exitCode':143 if role == 'trino' else 0,'oom':False,'pid':0,
        'startedAt':'2026-10-16T00:00:01Z','configBindingSha256':c.digest(role.encode())} for i,role in enumerate(sorted(c.ROLES),3)]
    stopped = {**header,'schemaVersion':1,'scope':'PRE_DECODER_EXACT_STOPPED_FRESH_CLOUD_ACTORS','authoritySourceSha256':AUTH,
        'observerManifestSha256':c.OBSERVER_SHA,'project':'cloud-trial9-'+'f'*32,'attemptRoot':'/synthetic/cloud-trial9-private-'+'f'*32,
        'capturedAt':'2026-10-16T00:00:05.1Z','monotonic':106.0,'hostBootId':c.proof_value(clock)['hostBootId'],
        'clockSha256':clock['sha256'],'roles':roles,'initializer':{'id':'8'*64,'running':False,'exitCode':0,'oom':False},
        'originalRoleStopCallsAdded':0,'originalInitializerStopCallsAdded':0}
    trino = next(row for row in roles if row['role'] == 'trino')
    stop_intent = {'cid':trino['id'],'pid':999,'startTicks':123456,'hostBootId':stopped['hostBootId'],'cgroupSha256':'a'*64,
        'startedAt':trino['startedAt'],'signalScope':'CONFIGURED_OR_DEFAULT_SIGTERM','graceSeconds':30,
        'signalDeliveryDirectlyObserved':False,'automaticRetry':False}
    authority = {**header,'observerManifestSha256':c.OBSERVER_SHA,'authoritySourceSha256':AUTH,
        'producerSummary':summary,'sparkResult':spark,'sparkDiagnostic':p({'passed':True,'phase':'COMPLETED','sessionStopFailed':False}),
        'readerResult':p({'passed':True,'wholeObjects':len(map_rows),'oldObjects':4,'allPreTrinoBytesEqual':True,'onlyGetAndList':True}),
        'clock':clock,'trinoStopIntent':p(stop_intent),'trinoStopResult':p({**stop_intent,'requestReturnedZero':True,'actualExitCode':143,'nonOom':True}),
        'named':named,'observerResult':p({**header,'scope':'NAMED_RETURN_OBSERVATIONS_NOT_PRODUCER_SUCCESS','makeCallsStarted':1,
            'makeCallsCompleted':1,'jdbcCallsStarted':3,'jdbcCallsCompleted':3,'allThreeCheckpointsObserved':True,'originalFunctionsRestored':True,
            'hookDriftDetected':False,'producerRunPassedClaimed':False,'writersQuiescentVerified':False,'tableClosureVerified':False,
            'automaticRetry':False,'extraSqlCallsAdded':0}),
        'makeBinding':p({**header,'scope':'NAMED_OBSERVATION_ONLY','returnObjectPreserved':True,'project':stopped['project'],'attemptRoot':stopped['attemptRoot']}),
        'validation':validation,'lifecycle':p(stopped),'namedSqlIntents':raw_intents,'queryPlanSource':p(raw=query_raw),'captureMap':map_proof}
    loaded = {'descriptor':descriptor,'descriptorBytes':descriptor_bytes,'frameBytes':frame,'privateReceipt':{
        'descriptorSha256':c.digest(descriptor_bytes),'frameSha256':c.digest(frame),'lifecycleSha256':authority['lifecycle']['sha256'],
        'validationSha256':validation['sha256']}}
    by_alias = {row['alias']:row for row in descriptor['objects']}
    kinds = {name:('METADATA' if name.endswith('.json') else 'MANIFEST_LIST' if name.startswith('ml') else
        'DATA' if name.endswith('.parquet') else 'DELETE' if name == 'delete.avro' else 'MANIFEST') for name in aliases}
    edges = []
    def edge(source,target,kind,status=None): edges.append({'source':source,'target':target,'kind':kind,'status':status})
    edge(aliases['current.metadata.json'],aliases['old.metadata.json'],'METADATA_LOG')
    edge(aliases['manifest.avro'],aliases['data1.parquet'],'MANIFEST_DATA','DELETED')
    edge(aliases['manifest.avro'],aliases['data2.parquet'],'MANIFEST_DATA','ADDED')
    edge(aliases['manifest.avro'],aliases['delete.avro'],'MANIFEST_DELETE','EXISTING')
    edge(aliases['delete.avro'],aliases['data1.parquet'],'DELETE_REFERENCED_DATA')
    snapshots = []
    for index,snapshot in enumerate(chain,1):
        ml = aliases['ml%d.avro'%index]; edge(snapshot['snapshot_id'],ml,'SNAPSHOT_MANIFEST_LIST'); edge(ml,aliases['manifest.avro'],'LIST_MANIFEST')
        snapshots.append({'id':snapshot['snapshot_id'],'parentId':snapshot['parent_id'],'committedAt':'2026-10-16T00:00:0%dZ'%index,
            'manifestListId':ml,'fileIds':sorted([ml,aliases['manifest.avro'],aliases['delete.avro'],aliases['data1.parquet'],aliases['data2.parquet']])})
    graph = {'tableId':'t-'+'a'*64,'currentMetadataId':aliases['current.metadata.json'],'currentSnapshotId':'103',
        'metadataNodes':[{'id':aliases['current.metadata.json'],'role':'CURRENT'},{'id':aliases['old.metadata.json'],'role':'HISTORICAL'}],
        'snapshotNodes':snapshots,'refNodes':[{'name':'r-'+c.digest(b'main'),'kind':'BRANCH','snapshotId':'103'},
            {'name':'r-'+c.digest(b'backup-tag'),'kind':'TAG','snapshotId':'101'}],
        'fileNodes':[{'id':identity,'kind':kinds[name],'size':by_alias[identity]['size'],'sha256':by_alias[identity]['sha256']} for name,identity in aliases.items()],
        'edges':edges,'completeness':{'metadataDecoded':True,'refsDecoded':True,'snapshotFileClosureDecoded':True},
        'decoderProvenance':{'formatVersion':2,'schemaCount':1,'partitionSpecCount':1,'sortOrderCount':1,'mainRefDefaulted':False,
            'allEntriesIncludingDeleted':True,'streamsClosed':True,'outsideTarget':[{'id':outside,'size':by_alias[outside]['size'],'sha256':by_alias[outside]['sha256'],'action':'KEEP'}],
            'networkImplemented':False,'fileIoCreateDeleteSupported':False,'parquetContentsVerified':False,'historicalMetadataRestoreVerified':False}}
    reply = {'schemaVersion':1,'scope':'CLOSED_COPY_ICEBERG_FORMAT2_GRAPH','status':'DECODED','reasonCodes':[],
        'descriptorSha256':c.digest(descriptor_bytes),'graph':graph}
    return request,authority,loaded,reply,content,aliases


def decoder_for(reply, loaded, authority):
    raw = c.canonical(reply)+b'\n'; after = c.proof_value(authority['lifecycle'])
    after.update(scope='POST_DECODER_EXACT_STOPPED_FRESH_CLOUD_ACTORS',monotonic=108.0,capturedAt='2026-10-16T00:00:05.3Z')
    after = p(after)
    record = {'schemaVersion':1,'scope':'OWN_DECODER_CONTAINER_BOUNDED_STOPPED_AND_REAPED','authoritySourceSha256':AUTH,
        'sourceCommit':SOURCE,'producerSha256':c.PRODUCER_SHA,'runtimeManifestSha256':c.RUNTIME_SHA,
        'prepProofSha256':'b'*64,'decoderSourceSha256':'c'*64,'runtimeImageReference':n.SPARK,'runtimeImageId':'sha256:'+'d'*64,
        'icebergJarSha256':n.ICEBERG_SHA,'mainClass':'org.apache.iceberg.ClosedCopyDecoder','clockSha256':authority['clock']['sha256'],
        'originalStartedMonotonic':100.0,'originalAbsoluteCutoff':700.0,'decodeCutoff':160.0,'cleanupReserveSeconds':40,
        'capturedAt':'2026-10-16T00:00:05.4Z','finishedMonotonic':109.0,'cid':'9'*64,
        'exitCode':{'DECODED':0,'UNDETERMINED':2,'REJECTED':3}[reply['status']],'ownDecoderStopped':True,'attachCliReaped':True,'watchdogFired':False,
        'replySha256':c.digest(raw),'replyBytes':len(raw),'frameSha256':c.digest(loaded['frameBytes']),
        'descriptorSha256':c.digest(loaded['descriptorBytes']),'writersBeforeSha256':authority['lifecycle']['sha256'],
        'writersAfterSha256':after['sha256'],'originalRoleStopCallsAdded':0,'originalInitializerStopCallsAdded':0}
    return raw,{**p(record),'reply':p(raw=raw),'writersAfter':after}


def normalize(authority, loaded, reply, *, now=NOW):
    raw,decoder = decoder_for(reply,loaded,authority)
    return n.normalize_graph(raw,loaded,authority,decoder,PLANNER.read_bytes(),now=now,policy=POLICY,expected_authority_source_sha256=AUTH)


class PureContracts(unittest.TestCase):
    def test_future_request_is_derived_from_actual_same_run_pointer_and_map(self):
        request,a,loaded,reply,content,aliases = fixture()
        self.assertEqual(request,c.derive_request(a,AUTH))
        for suffix in ('future-one','future-two','future-three'):
            fresh = copy.deepcopy(a)
            old_uri = request['targetTable']['currentMetadataUri']
            new_uri = old_uri.replace('current.metadata.json',suffix+'.metadata.json')
            values = c.proof_value(fresh['captureMap'])
            for row in values:
                if row['key'].endswith('current.metadata.json'):
                    row['key'] = row['key'].replace('current.metadata.json',suffix+'.metadata.json')
                    row['copy'] = c.digest(row['key'].encode())+'.bin'
            fresh['captureMap'] = p(values)
            for entry in fresh['named']:
                entry['raw'] = entry['raw'].replace(old_uri.encode(),new_uri.encode()); entry['rawSha256'] = c.digest(entry['raw'])
                checkpoint = c.strict_json(entry['checkpoint'],65536)
                checkpoint.update(rawBytes=len(entry['raw']),rawSha256=entry['rawSha256'])
                entry.update(checkpoint=c.canonical(checkpoint),checkpointSha256=c.digest(c.canonical(checkpoint)))
            self.assertEqual(new_uri,c.derive_request(fresh,AUTH)['targetTable']['currentMetadataUri'])
        with self.assertRaises(ValueError): c.target_from_pointer(b'phase6|bronze|synthetic_events|x|y\n')
        with self.assertRaises(ValueError): c.target_from_pointer(b'phase6|bronze|synthetic_events|x/metadata/a/metadata/b|y\nphase6|silver|sensor_outcomes|z|\n')
        for key,value in (('catalog','1bad'),('tableLocation',request['targetTable']['tableLocation']+'/'),
                ('currentMetadataUri',request['targetTable']['tableLocation']+'/data/current.metadata.json')):
            bad = copy.deepcopy(request); bad['targetTable'][key] = value
            with patch.object(c,'_read_closed_files') as read:
                with self.assertRaises(ValueError): c.load_closed_copies(c.proof_value(a['lifecycle'])['attemptRoot'],bad,a,AUTH)
                read.assert_not_called()

    def test_exact_frame_map_identity_and_same_content_distinct_keys(self):
        request,a,loaded,reply,content,aliases = fixture()
        frame = loaded['frameBytes']; self.assertEqual(b'ICCPY001',frame[:8]); position = 8
        length, = struct.unpack('>I',frame[position:position+4]); position += 4
        self.assertEqual(loaded['descriptorBytes'],frame[position:position+length]); position += length
        count, = struct.unpack('>I',frame[position:position+4]); position += 4
        self.assertEqual(len(content),count)
        for row in loaded['descriptor']['objects']:
            length, = struct.unpack('>I',frame[position:position+4]); position += 4
            self.assertEqual(content[row['alias']],frame[position:position+length]); position += length
        self.assertEqual(position,len(frame))
        self.assertNotEqual(c.file_alias(c.BUCKET,'one'),c.file_alias(c.BUCKET,'two'))
        for mutate in (lambda rows:rows.append(dict(rows[0])), lambda rows:rows[0].update(size=True),
                lambda rows:rows[0].update(copy='../secret'),lambda rows:rows[0].update(key=c.PREFIX+'../secret')):
            values = c.proof_value(a['captureMap']); mutate(values); raw = c.canonical(values)
            with self.assertRaises(ValueError): c.validated_map(raw,c.digest(raw))

    def test_authority_recomputes_raw_selection_intents_clock_and_actor_gate(self):
        request,a,loaded,reply,content,aliases = fixture()
        self.assertEqual(['101','102','103'],c.validate_authority_bundle(a,AUTH)['validation']['snapshotIds'])
        changes = (
            lambda b:b['producerSummary'].update(sha256='0'*64),
            lambda b:replace_proof(b,'lifecycle',lambda v:v['roles'][0].update(running=True)),
            lambda b:replace_proof(b,'lifecycle',lambda v:v['roles'][0].update(pid=True)),
            lambda b:replace_proof(b,'lifecycle',lambda v:v.update(authoritySourceSha256='0'*64)),
            lambda b:replace_proof(b,'validation',lambda v:v.update(snapshotIds=['101','103'])),
            lambda b:b['namedSqlIntents'][0].update(raw=b'{"sqlSha256":"SYNTHETIC_SECRET"}'),
            lambda b:replace_proof(b,'clock',lambda v:v.update(budgetSeconds=601)),
        )
        for change in changes:
            bad = copy.deepcopy(a); change(bad)
            with self.assertRaises(ValueError): c.validate_authority_bundle(bad,AUTH)
        bad = copy.deepcopy(a); bad['named'][1]['raw'] += b'changed'; bad['named'][1]['rawSha256'] = c.digest(bad['named'][1]['raw'])
        with self.assertRaises(ValueError): c.validate_authority_bundle(bad,AUTH)
        with patch.object(c,'_read_closed_files') as read:
            bad = copy.deepcopy(a); replace_proof(bad,'lifecycle',lambda v:v['initializer'].update(running=True))
            with self.assertRaises(ValueError): c.load_closed_copies('/synthetic',request,bad,AUTH)
            read.assert_not_called()

    def test_shared_deleted_and_validation_pin_closure_all_keep(self):
        request,a,loaded,reply,content,aliases = fixture(); before = copy.deepcopy(reply)
        result = normalize(a,loaded,reply); plan = result['plan']; inv = result['inventory']
        self.assertEqual('DETERMINED',plan['status']); self.assertEqual(0,plan['snapshotCandidateCount'])
        self.assertEqual(['101','102','103'],inv['pins'][0]['snapshotIds'])
        self.assertIn(aliases['data1.parquet'],inv['pins'][0]['fileIds'])
        self.assertIn('SHARED_SNAPSHOT_FILE',next(r for r in plan['files'] if r['id'] == aliases['data1.parquet'])['reasons'])
        self.assertTrue(all(row['action'] == 'KEEP' for row in plan['files']))
        self.assertEqual(0,plan['objectCandidateCount']); self.assertFalse(plan['applyEnabled'])
        self.assertEqual(before,reply); self.assertEqual(10,len(result['privateReceipt']['allCapturedObjects']))

    def test_missing_or_tampered_closure_and_ref_kind_never_becomes_safe(self):
        request,a,loaded,reply,content,aliases = fixture()
        changes = (lambda g:g['snapshotNodes'][0]['fileIds'].remove(aliases['data1.parquet']),
            lambda g:g['edges'].remove(next(row for row in g['edges'] if row['kind'] == 'LIST_MANIFEST')),
            lambda g:g['refNodes'][0].update(kind='UNKNOWN'),
            lambda g:g['fileNodes'][0].update(sha256='0'*64),lambda g:g.update(extraPrivate='SYNTHETIC_SECRET'),
            lambda g:g['decoderProvenance']['outsideTarget'].clear())
        for change in changes:
            bad = copy.deepcopy(reply); change(bad['graph'])
            with self.assertRaises(ValueError): normalize(a,loaded,bad)
        partial = copy.deepcopy(reply); partial.update(status='UNDETERMINED',reasonCodes=['MISSING_APPROVED_CHILD'])
        partial['graph']['completeness']['snapshotFileClosureDecoded'] = False
        partial['graph'].update(tableId=None,currentSnapshotId=None)
        result = normalize(a,loaded,partial)
        self.assertIsNone(result['inventory']); self.assertIsNone(result['plan'])
        self.assertEqual('UNDETERMINED',result['privateReceipt']['status'])
        self.assertTrue(all(row['action'] == 'KEEP' for row in result['privateReceipt']['allCapturedObjects']))

    def test_capture_timestamp_not_parse_time_and_exact_300_second_boundary(self):
        request,a,loaded,reply,content,aliases = fixture()
        self.assertEqual(STAMP,normalize(a,loaded,reply)['inventory']['capturedAt'])
        self.assertEqual('DETERMINED',normalize(a,loaded,reply,now='2026-10-16T00:05:05Z')['plan']['status'])
        stale = normalize(a,loaded,reply,now='2026-10-16T00:05:05.000000001Z')['plan']
        self.assertEqual('UNDETERMINED',stale['status']); self.assertEqual(0,stale['snapshotCandidateCount'])
        self.assertIn('STALE_INVENTORY',stale['suppressionReasons'])
        early = normalize(a,loaded,reply,now='2026-10-16T00:00:04Z')['plan']
        self.assertIn('CLOCK_BEFORE_INVENTORY',early['suppressionReasons'])

    def test_decoder_lifecycle_after_drift_timeout_and_reply_hash_fail_closed(self):
        request,a,loaded,reply,content,aliases = fixture(); raw,decoder = decoder_for(reply,loaded,a)
        for change in (lambda d:replace_proof(d,'writersAfter',lambda v:v['roles'][0].update(configBindingSha256='0'*64)),
                lambda d:replace_proof(d,'reply',lambda v:v.update(status='REJECTED')),
                lambda d:d.update(sha256='0'*64)):
            bad = copy.deepcopy(decoder); change(bad)
            with self.assertRaises(ValueError): n.normalize_graph(raw,loaded,a,bad,PLANNER.read_bytes(),now=NOW,policy=POLICY,expected_authority_source_sha256=AUTH)
        bad = copy.deepcopy(decoder); value = c.proof_value({k:bad[k] for k in ('raw','sha256')}); value['watchdogFired'] = True
        bad.update(p(value))
        with self.assertRaises(ValueError): n.normalize_graph(raw,loaded,a,bad,PLANNER.read_bytes(),now=NOW,policy=POLICY,expected_authority_source_sha256=AUTH)

    def test_strict_json_privacy_duplicate_nonfinite_overflow_and_unknown_reply(self):
        marker = 'SYNTHETIC_SECRET_NEVER_ECHO'
        for raw in (b'{"a":1,"a":2}',b'{"a":NaN}',b'{"a":1e9999}',b'{"a":'+b'9'*5000+b'}',marker.encode(),b'"\xff"'):
            with self.assertRaises(ValueError) as caught: c.strict_json(raw,65536)
            self.assertNotIn(marker,str(caught.exception)); self.assertRegex(str(caught.exception),'^[A-Z0-9_]+$')
        request,a,loaded,reply,content,aliases = fixture(); reply['reasonCodes'] = [marker]
        with self.assertRaises(ValueError) as caught: normalize(a,loaded,reply)
        self.assertNotIn(marker,str(caught.exception))


@unittest.skipUnless(sys.platform == 'linux' and os.name == 'posix', 'Actual Linux openat/UID/mode semantics are not available on Windows')
class LinuxOpenatContracts(unittest.TestCase):
    @unittest.skipUnless(hasattr(os,'geteuid') and os.geteuid() == 0, 'Whole original UID185 fixture requires isolated Linux root/chown; not mocked')
    def test_whole_original_mode_ownership_layout_and_ancestor_symlink(self):
        request,a,loaded,reply,content,aliases = fixture()
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)/('cloud-trial9-private-'+'f'*32); root.mkdir(); root.chmod(0o700)
            proof = root/'proof'; proof.mkdir(); proof.chmod(0o777)
            objects = proof/'objects-after-trino'; objects.mkdir(); objects.chmod(0o755); os.chown(objects,185,185)
            map_path = proof/'warehouse-after-trino.json'; map_path.write_bytes(a['captureMap']['raw']); map_path.chmod(0o644); os.chown(map_path,185,185)
            for row in loaded['descriptor']['objects']:
                path = objects/row['copy']; path.write_bytes(content[row['alias']]); path.chmod(0o644); os.chown(path,185,185)
            actual_raw,actual_rows,actual_content = c._read_closed_files(root,a['captureMap']['sha256'])
            self.assertEqual(a['captureMap']['raw'],actual_raw); self.assertEqual(content,actual_content)
            self.assertEqual(loaded['descriptor']['objects'],actual_rows)
            objects.chmod(0o777)
            with self.assertRaises(ValueError): c._read_closed_files(root,a['captureMap']['sha256'])
            objects.chmod(0o755)
            moved = Path(temp)/'original'; root.rename(moved); root.symlink_to(moved,target_is_directory=True)
            with self.assertRaises(ValueError): c._read_closed_files(root,a['captureMap']['sha256'])

    def test_real_single_link_regular_file_symlink_hardlink_and_mode(self):
        with tempfile.TemporaryDirectory() as temp:
            parent = Path(temp); raw = b'SYNTHETIC'; (parent/'copy').write_bytes(raw); (parent/'copy').chmod(0o644)
            fd = os.open(parent,os.O_RDONLY|os.O_DIRECTORY)
            try:
                self.assertEqual(raw,c._read_file(fd,'copy',os.getuid(),0o644,100,len(raw),c.digest(raw))[0])
                (parent/'symlink').symlink_to(parent/'copy')
                with self.assertRaises(ValueError): c._read_file(fd,'symlink',os.getuid(),0o644,100)
                os.link(parent/'copy',parent/'hardlink')
                with self.assertRaises(ValueError): c._read_file(fd,'copy',os.getuid(),0o644,100)
                (parent/'hardlink').unlink(); (parent/'copy').chmod(0o600)
                with self.assertRaises(ValueError): c._read_file(fd,'copy',os.getuid(),0o644,100)
            finally: os.close(fd)

    def test_real_open_identity_replacement_and_read_mutation_are_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            parent = Path(temp); path = parent/'copy'; path.write_bytes(b'SYNTHETIC'); path.chmod(0o644)
            fd = os.open(parent,os.O_RDONLY|os.O_DIRECTORY); original_read = os.read
            def mutate(descriptor,size):
                raw = original_read(descriptor,size)
                if raw: path.write_bytes(b'CHANGED!!')
                return raw
            try:
                with patch.object(c.os,'read',side_effect=mutate):
                    with self.assertRaises(ValueError): c._read_file(fd,'copy',os.getuid(),0o644,100)
            finally: os.close(fd)


if __name__ == '__main__': unittest.main()
