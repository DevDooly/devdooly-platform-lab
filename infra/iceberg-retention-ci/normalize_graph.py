"""Pure private graph validation and frozen-planner projection; no OS reads."""
import re

from copy_loader import (HEX, FILE_ALIAS, canonical, digest, exact, number, proof_value,
    require, source_header, strict_json, utc_ns, validate_authority_bundle,
    validate_stopped, descriptor_from_map)

PLANNER_SHA = 'ec1ff5dc06d9da666d9ef1d32557937e36e0a63bc124f08ad6ed39edbf0224ae'
SPARK = 'docker.io/apache/spark@sha256:0b8f5befe00d258df03b252158b3894b8654390f1958741accf98155539a662a'
ICEBERG_SHA = 'd6ea6c5d099288daeb7d5a92061bd3d7d8f296492632b42378e5f2f0e3066242'
REASONS = set(('FRAME_MAGIC FRAME_BOUND FRAME_EOF DESCRIPTOR_INVALID OBJECT_MAP_INVALID OBJECT_BYTES_MISMATCH '
    'METADATA_INVALID UNSUPPORTED_FORMAT UNSUPPORTED_METADATA_FEATURE UNSUPPORTED_CODEC UNSUPPORTED_SCHEMA '
    'UNSUPPORTED_ENTRY_CONTENT MISSING_APPROVED_CHILD FOREIGN_REFERENCE GRAPH_CONFLICT MISSING_SNAPSHOT_REFERENCE '
    'REFERENCE_CYCLE GRAPH_BOUND DECODER_INTERNAL DECODER_BUDGET_EXPIRED').split())
KINDS = {'DATA','DELETE','MANIFEST','MANIFEST_LIST','METADATA','UNKNOWN'}
EDGE_KINDS = {'SNAPSHOT_MANIFEST_LIST','LIST_MANIFEST','MANIFEST_DATA','MANIFEST_DELETE','DELETE_REFERENCED_DATA','METADATA_LOG'}


NORMALIZATION_PHASE_CODES = frozenset((
    'NORMALIZE_AUTHORITY_UNVERIFIED',
    'NORMALIZE_DESCRIPTOR_UNVERIFIED',
    'NORMALIZE_DECODER_LIFECYCLE_UNVERIFIED',
    'NORMALIZE_PLANNER_SOURCE_UNVERIFIED',
    'NORMALIZE_REPLY_UNVERIFIED',
    'NORMALIZE_GRAPH_UNVERIFIED',
    'NORMALIZE_EXIT_BINDING_UNVERIFIED',
    'NORMALIZE_CLOCK_UNVERIFIED',
    'NORMALIZE_INVENTORY_UNVERIFIED',
    'NORMALIZE_PLAN_UNVERIFIED',
    'NORMALIZE_RESULT_UNVERIFIED',
))


class NormalizationFailure(ValueError):
    """Only an attempted source-owned phase, never an original error message."""
    def __init__(self, phase_code):
        require(type(phase_code) is str and phase_code in NORMALIZATION_PHASE_CODES,
            'EXACT_NORMALIZATION_PHASE_REQUIRED')
        self.phaseCode = phase_code
        super().__init__(phase_code)


def sid(value):
    require(type(value) is str and re.fullmatch('[1-9][0-9]{0,18}', value)
        and int(value) < 2**63, 'GRAPH_POSITIVE_BIGINT_STRING_REQUIRED')


def bounded(value, maximum=10000):
    require(type(value) is list and len(value) <= maximum, 'GRAPH_ARRAY_BOUND_REQUIRED')


def alias(value, prefix='f'):
    require(type(value) is str and re.fullmatch(prefix+'-[a-f0-9]{64}', value), 'GRAPH_IDENTITY_ALIAS_REQUIRED')


def checked_descriptor(loaded, authority):
    exact(loaded, 'descriptor descriptorBytes frameBytes privateReceipt')
    require(type(loaded['descriptorBytes']) is bytes and type(loaded['frameBytes']) is bytes, 'LOADED_FRAME_BYTES_REQUIRED')
    value = strict_json(loaded['descriptorBytes'], 512*1024)
    request = {k:value[k] for k in ('sourceCommit','captureMapSha256','approvedBucket','approvedPrefix','targetTable')}
    expected, encoded = descriptor_from_map(authority['captureMap']['raw'], request)
    require(canonical(loaded['descriptor']) == canonical(value) == encoded and loaded['descriptorBytes'] == encoded
        and value == expected and value['sourceCommit'] == authority['sourceCommit']
        and value['captureMapSha256'] == authority['captureMap']['sha256'], 'EXACT_SOURCE_BOUND_LOADED_DESCRIPTOR_REQUIRED')
    receipt = loaded['privateReceipt']
    require(receipt['descriptorSha256'] == digest(encoded) and receipt['frameSha256'] == digest(loaded['frameBytes'])
        and receipt['lifecycleSha256'] == authority['lifecycle']['sha256']
        and receipt['validationSha256'] == authority['validation']['sha256'], 'LOADER_PRIVATE_RECEIPT_BINDING_REQUIRED')
    return value


def checked_decoder(reply_bytes, loaded, authority, decoder, verified, expected_authority_source_sha256):
    exact(decoder, 'raw sha256 reply writersAfter')
    record = proof_value({k:decoder[k] for k in ('raw','sha256')})
    exact(record, 'schemaVersion scope authoritySourceSha256 sourceCommit producerSha256 runtimeManifestSha256 prepProofSha256 decoderSourceSha256 runtimeImageReference runtimeImageId icebergJarSha256 mainClass clockSha256 originalStartedMonotonic originalAbsoluteCutoff decodeCutoff cleanupReserveSeconds capturedAt finishedMonotonic cid exitCode ownDecoderStopped attachCliReaped watchdogFired replySha256 replyBytes frameSha256 descriptorSha256 writersBeforeSha256 writersAfterSha256 originalRoleStopCallsAdded originalInitializerStopCallsAdded')
    source_header(record, authority['sourceCommit'], expected_authority_source_sha256)
    require(type(record['schemaVersion']) is int and record['schemaVersion'] == 1
        and record['scope'] == 'OWN_DECODER_CONTAINER_BOUNDED_STOPPED_AND_REAPED'
        and record['runtimeImageReference'] == SPARK and record['icebergJarSha256'] == ICEBERG_SHA
        and record['mainClass'] == 'org.apache.iceberg.ClosedCopyDecoder'
        and type(record['runtimeImageId']) is str and re.fullmatch('sha256:[a-f0-9]{64}', record['runtimeImageId'])
        and all(type(record[k]) is str and HEX.fullmatch(record[k]) for k in ('prepProofSha256','decoderSourceSha256','cid'))
        and record['cid'] not in {row['id'] for row in verified['stopped']['roles']}
        and record['cid'] != verified['stopped']['initializer']['id'], 'EXACT_SEPARATE_DECODER_IDENTITY_REQUIRED')
    clock = verified['clock']; start = clock['startedMonotonic']
    require(record['clockSha256'] == authority['clock']['sha256'] and record['originalStartedMonotonic'] == start
        and number(record['originalAbsoluteCutoff']) and record['originalAbsoluteCutoff'] == start+600
        and type(record['cleanupReserveSeconds']) is int and record['cleanupReserveSeconds'] == 40
        and number(record['decodeCutoff']) and verified['stopped']['monotonic'] < record['decodeCutoff'] <= start+560
        and number(record['finishedMonotonic']) and verified['stopped']['monotonic'] <= record['finishedMonotonic'] < start+600
        and all(type(record[k]) is int and record[k] == 0 for k in ('originalRoleStopCallsAdded','originalInitializerStopCallsAdded'))
        and record['ownDecoderStopped'] is True and record['attachCliReaped'] is True and record['watchdogFired'] is False
        and type(record['exitCode']) is int and record['exitCode'] in (0,2,3), 'ORIGINAL_CLOCK_DECODER_STOP_AND_REAP_REQUIRED')
    proof_value(decoder['reply'], 4*1024**2)
    require(decoder['reply']['raw'] == reply_bytes and record['replySha256'] == decoder['reply']['sha256']
        and type(record['replyBytes']) is int and record['replyBytes'] == len(reply_bytes)
        and record['descriptorSha256'] == digest(loaded['descriptorBytes']) and record['frameSha256'] == digest(loaded['frameBytes'])
        and record['writersBeforeSha256'] == authority['lifecycle']['sha256']
        and record['writersAfterSha256'] == decoder['writersAfter']['sha256'], 'DECODER_WHOLE_REPLY_FRAME_AND_ACTOR_PROOF_BINDING')
    after = validate_stopped(decoder['writersAfter'], authority, clock, expected_authority_source_sha256, after=True)
    before = verified['stopped']
    require(after['roles'] == before['roles'] and after['initializer'] == before['initializer']
        and after['project'] == before['project'] and after['attemptRoot'] == before['attemptRoot']
        and before['monotonic'] <= after['monotonic'] <= record['finishedMonotonic']
        and utc_ns(before['capturedAt']) <= utc_ns(after['capturedAt']) <= utc_ns(record['capturedAt']),
        'SAME_ALL_FIVE_STOPPED_ACTORS_AFTER_DECODER')
    return record


def graph_projection(reply, descriptor):
    """Validate exact private graph and independently recompute edge closure."""
    exact(reply, 'schemaVersion scope status reasonCodes descriptorSha256 graph')
    require(type(reply['schemaVersion']) is int and reply['schemaVersion'] == 1
        and reply['scope'] == 'CLOSED_COPY_ICEBERG_FORMAT2_GRAPH'
        and reply['status'] in ('DECODED','UNDETERMINED','REJECTED'), 'EXACT_DECODER_REPLY_REQUIRED')
    bounded(reply['reasonCodes'], 16)
    require(all(type(code) is str and code in REASONS for code in reply['reasonCodes'])
        and len(set(reply['reasonCodes'])) == len(reply['reasonCodes']), 'FIXED_DECODER_REASON_CODES_ONLY')
    if reply['status'] == 'REJECTED':
        require(reply['graph'] is None and reply['reasonCodes'], 'REJECTED_GRAPH_MUST_BE_ABSENT')
        return None
    graph = reply['graph']; exact(graph, 'tableId currentMetadataId currentSnapshotId metadataNodes snapshotNodes refNodes fileNodes edges completeness decoderProvenance')
    if graph['tableId'] is not None: alias(graph['tableId'], 't')
    if graph['currentSnapshotId'] is not None: sid(graph['currentSnapshotId'])
    alias(graph['currentMetadataId'])
    records = {row['alias']:row for row in descriptor['objects']}
    location = descriptor['targetTable']['tableLocation'].rstrip('/')+'/'
    target_ids = {row['alias'] for row in records.values() if ('s3://'+descriptor['approvedBucket']+'/'+row['key']).startswith(location)}
    current_id = next(row['alias'] for row in records.values()
        if 's3://'+descriptor['approvedBucket']+'/'+row['key'] == descriptor['targetTable']['currentMetadataUri'])
    require(graph['currentMetadataId'] == current_id, 'ACTUAL_CURRENT_METADATA_ALIAS_REQUIRED')
    exact(graph['completeness'], 'metadataDecoded refsDecoded snapshotFileClosureDecoded')
    require(all(type(v) is bool for v in graph['completeness'].values()), 'TYPED_GRAPH_COMPLETENESS_REQUIRED')
    provenance = graph['decoderProvenance']
    exact(provenance, 'formatVersion schemaCount partitionSpecCount sortOrderCount mainRefDefaulted allEntriesIncludingDeleted streamsClosed outsideTarget networkImplemented fileIoCreateDeleteSupported parquetContentsVerified historicalMetadataRestoreVerified')
    for key in ('formatVersion','schemaCount','partitionSpecCount','sortOrderCount'):
        require(provenance[key] is None or type(provenance[key]) is int and 0 <= provenance[key] <= 10000, 'OBSERVED_DECODER_COUNT_OR_NULL_REQUIRED')
    require(all(type(provenance[k]) is bool for k in ('mainRefDefaulted','allEntriesIncludingDeleted','streamsClosed'))
        and all(provenance[k] is False for k in ('networkImplemented','fileIoCreateDeleteSupported','parquetContentsVerified','historicalMetadataRestoreVerified')),
        'NO_INVENTED_DECODER_FEATURE_VERIFICATION')
    bounded(provenance['outsideTarget'], 128)
    outside = set()
    for row in provenance['outsideTarget']:
        exact(row, 'id size sha256 action'); alias(row['id'])
        require(row['id'] in records and row['id'] not in target_ids and row['id'] not in outside
            and row['size'] == records[row['id']]['size'] and type(row['size']) is int
            and row['sha256'] == records[row['id']]['sha256'] and row['action'] == 'KEEP', 'EXACT_OUTSIDE_TARGET_KEEP_LEDGER_REQUIRED')
        outside.add(row['id'])
    bounded(graph['fileNodes'], 128); files = {}
    for row in graph['fileNodes']:
        exact(row, 'id kind size sha256'); alias(row['id'])
        require(row['id'] in target_ids and row['id'] not in files and row['kind'] in KINDS
            and type(row['size']) is int and row['size'] == records[row['id']]['size']
            and row['sha256'] == records[row['id']]['sha256'], 'EXACT_APPROVED_FILE_NODE_REQUIRED')
        files[row['id']] = row
    require(set(files) == target_ids and set(files)|outside == set(records), 'ALL_CAPTURED_OBJECTS_ACCOUNTED_FOR')
    bounded(graph['metadataNodes'], 128); metadata = {}
    for row in graph['metadataNodes']:
        exact(row, 'id role'); alias(row['id'])
        require(row['id'] in files and files[row['id']]['kind'] == 'METADATA' and row['id'] not in metadata
            and row['role'] in ('CURRENT','HISTORICAL'), 'EXACT_METADATA_NODE_REQUIRED')
        metadata[row['id']] = row['role']
    require(list(metadata.values()).count('CURRENT') <= 1 and
        (not any(v == 'CURRENT' for v in metadata.values()) or metadata.get(current_id) == 'CURRENT'),
        'CURRENT_METADATA_NODE_IDENTITY_REQUIRED')
    bounded(graph['snapshotNodes']); snapshots = {}
    for row in graph['snapshotNodes']:
        exact(row, 'id parentId committedAt manifestListId fileIds'); sid(row['id'])
        if row['parentId'] is not None: sid(row['parentId'])
        utc_ns(row['committedAt']); alias(row['manifestListId']); bounded(row['fileIds'])
        for identity in row['fileIds']: alias(identity)
        require(row['id'] not in snapshots and len(set(row['fileIds'])) == len(row['fileIds']), 'UNIQUE_SNAPSHOT_AND_CLOSURE_IDS_REQUIRED')
        snapshots[row['id']] = row
    bounded(graph['refNodes']); refs = set()
    for row in graph['refNodes']:
        exact(row, 'name kind snapshotId'); alias(row['name'], 'r'); sid(row['snapshotId'])
        require(row['name'] not in refs and row['kind'] in ('TAG','BRANCH'), 'EXACT_TAG_OR_BRANCH_REFERENCE_REQUIRED')
        refs.add(row['name'])
    bounded(graph['edges'], 100000); seen = set(); adjacency = {}
    source_kinds = {'LIST_MANIFEST':'MANIFEST_LIST','MANIFEST_DATA':'MANIFEST','MANIFEST_DELETE':'MANIFEST',
        'DELETE_REFERENCED_DATA':'DELETE','METADATA_LOG':'METADATA'}
    target_kinds = {'SNAPSHOT_MANIFEST_LIST':'MANIFEST_LIST','LIST_MANIFEST':'MANIFEST','MANIFEST_DATA':'DATA',
        'MANIFEST_DELETE':'DELETE','DELETE_REFERENCED_DATA':'DATA','METADATA_LOG':'METADATA'}
    for row in graph['edges']:
        exact(row, 'source target kind status'); alias(row['target'])
        require(row['kind'] in EDGE_KINDS and row['target'] in files, 'APPROVED_GRAPH_EDGE_TARGET_REQUIRED')
        if row['kind'] in ('MANIFEST_DATA','MANIFEST_DELETE'):
            require(row['status'] in ('ADDED','EXISTING','DELETED'), 'ACTUAL_MANIFEST_ENTRY_STATUS_REQUIRED')
        else: require(row['status'] is None, 'NO_ENTRY_STATUS_ON_OTHER_EDGE_KINDS')
        if row['kind'] == 'SNAPSHOT_MANIFEST_LIST': sid(row['source'])
        else:
            alias(row['source']); require(row['source'] in files and files[row['source']]['kind'] == source_kinds[row['kind']], 'GRAPH_EDGE_SOURCE_KIND_REQUIRED')
        require(files[row['target']]['kind'] == target_kinds[row['kind']], 'GRAPH_EDGE_TARGET_KIND_REQUIRED')
        identity = tuple(row[k] for k in ('source','target','kind','status'))
        require(identity not in seen, 'DUPLICATE_GRAPH_EDGE_REJECTED'); seen.add(identity)
        if row['kind'] != 'METADATA_LOG': adjacency.setdefault(row['source'], set()).add(row['target'])
    # A handled partial decode has no planner DTO: no guessed current ID,
    # repaired root, unknown ref kind, or incomplete Java closure is substituted.
    if reply['status'] == 'UNDETERMINED':
        require(reply['reasonCodes'] and not all(graph['completeness'].values()), 'PARTIAL_DECODE_CANNOT_CLAIM_COMPLETE')
        return None
    require(not reply['reasonCodes'] and all(graph['completeness'].values())
        and graph['tableId'] is not None and graph['currentSnapshotId'] in snapshots
        and metadata.get(current_id) == 'CURRENT'
        and provenance['formatVersion'] == 2 and all(type(provenance[k]) is int and provenance[k] > 0
            for k in ('schemaCount','partitionSpecCount','sortOrderCount'))
        and provenance['allEntriesIncludingDeleted'] is True and provenance['streamsClosed'] is True
        and all(row['kind'] != 'UNKNOWN' for row in files.values()), 'COMPLETE_SUPPORTED_FORMAT2_GRAPH_REQUIRED')
    require(all(row['snapshotId'] in snapshots for row in graph['refNodes'])
        and all(row['source'] in snapshots for row in graph['edges'] if row['kind'] == 'SNAPSHOT_MANIFEST_LIST'), 'ALL_SNAPSHOT_REFERENCE_TARGETS_REQUIRED')
    for row in snapshots.values():
        require(row['manifestListId'] in files and files[row['manifestListId']]['kind'] == 'MANIFEST_LIST'
            and adjacency.get(row['id']) == {row['manifestListId']}, 'ACTUAL_SNAPSHOT_MANIFEST_LIST_EDGE_REQUIRED')
        closure, visiting, done = set(), set(), set()
        def visit(node):
            require(node not in visiting, 'GRAPH_REFERENCE_CYCLE_REJECTED')
            if node in done: return
            visiting.add(node)
            for target in adjacency.get(node, ()):
                closure.add(target); visit(target)
            visiting.remove(node); done.add(node)
        visit(row['id'])
        require(closure == set(row['fileIds']), 'INDEPENDENT_TRANSITIVE_CLOSURE_MISMATCH')
    return {'tableId':graph['tableId'],'currentSnapshotId':graph['currentSnapshotId'],
        'snapshots':[{k:row[k] for k in ('id','parentId','committedAt','fileIds')} for row in graph['snapshotNodes']],
        'refs':[dict(row) for row in graph['refNodes']], 'files':[{'id':row['id'],'kind':row['kind']} for row in graph['fileNodes']]}


def normalize_graph(reply_bytes, loaded, authority_bundle, decoder_bundle, planner_source, *, now, policy, expected_authority_source_sha256):
    phase = 'NORMALIZE_AUTHORITY_UNVERIFIED'
    try:
        verified = validate_authority_bundle(authority_bundle, expected_authority_source_sha256)
        phase = 'NORMALIZE_DESCRIPTOR_UNVERIFIED'
        descriptor = checked_descriptor(loaded, authority_bundle)
        phase = 'NORMALIZE_DECODER_LIFECYCLE_UNVERIFIED'
        decoder = checked_decoder(reply_bytes, loaded, authority_bundle, decoder_bundle, verified, expected_authority_source_sha256)
        phase = 'NORMALIZE_PLANNER_SOURCE_UNVERIFIED'
        require(type(planner_source) is bytes and digest(planner_source) == PLANNER_SHA, 'EXACT_FROZEN_PURE_PLANNER_BYTES_REQUIRED')
        planner = {}; exec(compile(planner_source, '<pinned-pure-retention-planner>', 'exec'), planner)
        phase = 'NORMALIZE_REPLY_UNVERIFIED'
        reply = strict_json(reply_bytes, 4*1024**2)
        require(reply['descriptorSha256'] == digest(loaded['descriptorBytes']), 'ACTUAL_DECODED_DESCRIPTOR_SHA_REQUIRED')
        phase = 'NORMALIZE_GRAPH_UNVERIFIED'
        projection = graph_projection(reply, descriptor)
        phase = 'NORMALIZE_EXIT_BINDING_UNVERIFIED'
        require(decoder['exitCode'] == {'DECODED':0,'UNDETERMINED':2,'REJECTED':3}[reply['status']], 'DECODER_EXIT_AND_REPLY_STATUS_REQUIRED')
        phase = 'NORMALIZE_CLOCK_UNVERIFIED'
        utc_ns(now)
        phase = 'NORMALIZE_INVENTORY_UNVERIFIED'
        inventory = plan = None
        if projection is not None:
            validated = verified['validation']['snapshotIds']; snapshots = {r['id']:r for r in projection['snapshots']}
            require(all(s in snapshots for s in validated), 'VALIDATED_SNAPSHOT_SELECTION_NOT_IN_GRAPH')
            pinned_files = sorted({fid for s in validated for fid in snapshots[s]['fileIds']})
            current = reply['graph']['currentMetadataId']
            metadata = next(row for row in descriptor['objects'] if row['alias'] == current)
            inventory = {'schemaVersion':1,'kind':'iceberg-retention-inventory','scope':'CAPTURED_TABLE_METADATA',
                'tableId':projection['tableId'],'capturedAt':verified['validation']['capturedAt'],
                'observations':{'complete':True,'refsComplete':True,'pinsComplete':True,'snapshotFileClosureComplete':True,
                    'writersQuiescent':True,'metadataBeforeId':current,'metadataAfterId':current,
                    'metadataBeforeSha256':metadata['sha256'],'metadataAfterSha256':metadata['sha256']},
                'currentSnapshotId':projection['currentSnapshotId'],'snapshots':projection['snapshots'],'refs':projection['refs'],
                'pins':[{'id':'v-'+authority_bundle['validation']['sha256'],'kind':'VALIDATION','snapshotIds':list(validated),'fileIds':pinned_files}],
                'files':projection['files']}
            phase = 'NORMALIZE_PLAN_UNVERIFIED'
            plan = planner['build_plan'](inventory, policy, now=now)
        phase = 'NORMALIZE_RESULT_UNVERIFIED'
        return {'inventory':inventory,'plan':plan,'privateReceipt':{'schemaVersion':1,
            'scope':'SOURCE_BOUND_CAPTURED_GRAPH_NORMALIZATION_NOT_LIVE_TABLE_VERIFICATION',
            'status':'UNDETERMINED' if plan is None else plan['status'],
            'decoderStatus':reply['status'],'decoderReasonCodes':reply['reasonCodes'],
            'authoritySourceSha256':expected_authority_source_sha256,'decoderLifecycleSha256':decoder_bundle['sha256'],
            'validationSha256':authority_bundle['validation']['sha256'],'writersBeforeSha256':authority_bundle['lifecycle']['sha256'],
            'writersAfterSha256':decoder_bundle['writersAfter']['sha256'],'descriptorSha256':digest(loaded['descriptorBytes']),
            'replySha256':digest(reply_bytes),'graphSha256':None if reply['graph'] is None else digest(canonical(reply['graph'])),
            'inventorySha256':None if inventory is None else digest(canonical(inventory)),
            'capturedAt':verified['validation']['capturedAt'],'evaluatedAt':now,
            'allCapturedObjects':[{'id':row['alias'],'action':'KEEP'} for row in descriptor['objects']],
            'objectCandidateCount':0,'applyEnabled':False,'independentlyVerifiedLiveTable':False,
            'actualDataContentsVerifiedByDecoder':False,'historicalMetadataRestoreVerified':False}}
    except BaseException:
        raise NormalizationFailure(phase) from None
