"""Synthetic pure boundaries only; no Spark, filesystem, network, or deletion."""
import copy
import unittest
import contract as c


def fixture():
    data = [c.BRONZE + 'data/' + name + '.parquet' for name in ('a1', 'a2', 'b1', 'a3')]
    manifests = [c.BRONZE + 'metadata/manifest-' + str(index) + '.avro' for index in range(1, 5)]
    lists = [c.BRONZE + 'metadata/snap-' + str(index) + '.avro' for index in range(1, 5)]
    metadata = c.BRONZE + 'metadata/00004.metadata.json'
    silver = c.SILVER + 'data/fixed.parquet'
    objects = [{'key': key, 'bytes': 128, 'sha256': 'a' * 64}
        for key in data + manifests + lists + [metadata, silver]]
    file = lambda index, records: {'key': data[index], 'records': records, 'bytes': 128}
    snapshots = []
    sets = [[file(0, 6)], [file(0, 6), file(1, 6)], [file(2, 12)], [file(2, 12), file(3, 6)]]
    manifest_sets = [[manifests[0]], manifests[:2], [manifests[2]], manifests[2:]]
    for index in range(4):
        snapshots.append({'id': str(index + 1), 'parentId': str(index) if index else None,
            'operation': 'replace' if index == 2 else 'append', 'committedAtMs': (index + 1) * 1000,
            'totalRecords': [6, 12, 12, 18][index], 'dataFiles': sets[index],
            'manifestList': lists[index], 'manifests': manifest_sets[index]})
    before = {'tableUuid': '00000000-0000-4000-8000-000000000001', 'currentSnapshotId': '4',
        'metadataKey': metadata, 'gcEnabled': True, 'tagRetentionDefault': True,
        'snapshots': snapshots, 'refs': [{'name': 'main', 'kind': 'BRANCH', 'snapshotId': '4'},
            {'name': 'retained_first6', 'kind': 'TAG', 'snapshotId': '1'}], 'objects': objects}
    after = copy.deepcopy(before)
    after['snapshots'].pop(1)
    removed = {data[1], manifests[1], lists[1]}
    after['objects'] = [item for item in after['objects'] if item['key'] not in removed]
    after['metadataKey'] = c.BRONZE + 'metadata/00005.metadata.json'
    after['objects'].append({'key': after['metadataKey'], 'bytes': 128, 'sha256': 'b' * 64})
    result = {'deleted_data_files_count': 1, 'deleted_position_delete_files_count': 0,
        'deleted_equality_delete_files_count': 0, 'deleted_manifest_files_count': 1,
        'deleted_manifest_lists_count': 1, 'deleted_statistics_files_count': 0}
    missing = {'status': 404, 'code': 'NoSuchKey', 'key': data[1]}
    return before, after, result, missing


class ExpirationContractTest(unittest.TestCase):
    def rejected(self, call):
        with self.assertRaises(ValueError) as failure:
            call()
        self.assertIn(str(failure.exception), c.CODES)

    def test_shared_tag_and_recent_snapshots_survive_with_only_expired_parent_missing(self):
        before, after, result, missing = fixture()
        saved = copy.deepcopy((before, after, result, missing))
        plan = c.preflight(before, 5000)
        self.assertEqual(['1', '2', '3', '4'], plan['snapshotOrder'])
        self.assertEqual('2', plan['expiredSnapshotId'])
        self.assertEqual(3000, plan['cutoffMs'])
        self.assertEqual(missing['key'], plan['removedDataKey'])
        self.assertEqual(3, len(plan['allowedRemovedKeys']))
        self.assertIn(before['snapshots'][0]['dataFiles'][0]['key'], plan['protectedKeys'])
        self.assertTrue(c.verify_expiration(before, after, result, missing)['passed'])
        self.assertEqual(saved, (before, after, result, missing))
        # Input ordering is not evidence of snapshot/manifest identity or file changes.
        after['snapshots'].reverse()
        after['objects'].reverse()
        after['snapshots'][0]['dataFiles'].reverse()
        self.assertTrue(c.verify_expiration(before, after, result, missing)['passed'])
        self.assertEqual(saved[0], before)
        self.assertEqual(saved[2:], (result, missing))

    def test_changed_ref_extra_pin_gc_or_noncanonical_identity_blocks_preflight(self):
        for change in ('tag', 'main', 'pin', 'gc', 'tagRetention', 'uuid'):
            with self.subTest(change=change):
                state = fixture()[0]
                if change == 'tag':
                    state['refs'][1]['snapshotId'] = '2'
                elif change == 'main':
                    state['currentSnapshotId'] = '3'
                elif change == 'pin':
                    state['refs'].append({'name': 'unknown', 'kind': 'TAG', 'snapshotId': '2'})
                elif change == 'gc':
                    state['gcEnabled'] = False
                elif change == 'tagRetention':
                    state['tagRetentionDefault'] = False
                else:
                    state['tableUuid'] = state['tableUuid'].upper().replace('4000', '400A')
                self.rejected(lambda: c.preflight(state, 5000))

    def test_future_equal_times_boolean_overflow_and_wrong_file_shape_fail_closed(self):
        for change in ('future', 'equal', 'boolTime', 'timeOverflow', 'idOverflow', 'recordBool', 'bytesOverflow', 'shape'):
            with self.subTest(change=change):
                state = fixture()[0]
                if change == 'future':
                    state['snapshots'][3]['committedAtMs'] = 5001
                elif change == 'equal':
                    state['snapshots'][2]['committedAtMs'] = 2000
                elif change == 'boolTime':
                    state['snapshots'][0]['committedAtMs'] = True
                elif change == 'timeOverflow':
                    state['snapshots'][0]['committedAtMs'] = 2**63
                elif change == 'idOverflow':
                    state['snapshots'][0]['id'] = str(2**63)
                elif change == 'recordBool':
                    state['snapshots'][0]['dataFiles'][0]['records'] = True
                elif change == 'bytesOverflow':
                    state['objects'][0]['bytes'] = 2**63
                else:
                    state['snapshots'][1]['operation'] = []
                self.rejected(lambda: c.preflight(state, 5000))

        for count in (128, 129):
            with self.subTest(objectCount=count):
                state = fixture()[0]
                for index in range(count - len(state['objects'])):
                    state['objects'].append({'key': c.BRONZE + 'metadata/extra-' + str(index) + '.metadata.json',
                        'bytes': 128, 'sha256': 'e' * 64})
                self.assertEqual(count, len(state['objects']))
                if count == 128:
                    self.assertEqual('2', c.preflight(state, 5000)['expiredSnapshotId'])
                else:
                    self.rejected(lambda: c.preflight(state, 5000))

    def test_bad_scope_closure_reused_file_or_unknown_parent_is_not_a_deletion_plan(self):
        for change in ('scope', 'closure', 'reuse', 'parent'):
            with self.subTest(change=change):
                state = fixture()[0]
                if change == 'scope':
                    state['objects'][0]['key'] = c.BRONZE + '../outside.parquet'
                elif change == 'closure':
                    state['objects'] = [item for item in state['objects']
                        if item['key'] != state['snapshots'][1]['manifestList']]
                elif change == 'reuse':
                    state['snapshots'][3]['dataFiles'][1] = copy.deepcopy(state['snapshots'][0]['dataFiles'][0])
                else:
                    state['snapshots'][2]['parentId'] = '99'
                self.rejected(lambda: c.preflight(state, 5000))

    def test_unexpected_deletion_survivor_mutation_or_new_nonmetadata_object_is_rejected(self):
        for change in ('shared', 'silver', 'oldMetadata', 'hash', 'newData', 'parent'):
            with self.subTest(change=change):
                before, after, result, missing = fixture()
                if change in {'shared', 'silver', 'oldMetadata'}:
                    key = (before['snapshots'][0]['dataFiles'][0]['key'] if change == 'shared'
                        else before['metadataKey'] if change == 'oldMetadata'
                        else next(item['key'] for item in before['objects'] if item['key'].startswith(c.SILVER)))
                    after['objects'] = [item for item in after['objects'] if item['key'] != key]
                elif change == 'hash':
                    after['objects'][0]['sha256'] = 'c' * 64
                elif change == 'newData':
                    after['objects'].append({'key': c.BRONZE + 'data/unknown.parquet', 'bytes': 128, 'sha256': 'd' * 64})
                else:
                    after['snapshots'][1]['parentId'] = '99'
                self.rejected(lambda: c.verify_expiration(before, after, result, missing))

    def test_partial_commit_delete_unknown_missing_or_wrong_counts_never_return_pass(self):
        for change in ('snapshotRetained', 'dataRetained', 'missingNone', 'missing403', 'wrongCode',
                       'dataCount', 'manifestCount', 'counterBool', 'counterOverflow', 'unknownCounter'):
            with self.subTest(change=change):
                before, after, result, missing = fixture()
                if change == 'snapshotRetained':
                    after['snapshots'].append(copy.deepcopy(before['snapshots'][1]))
                elif change == 'dataRetained':
                    after['objects'].append(copy.deepcopy(next(item for item in before['objects'] if item['key'] == missing['key'])))
                elif change == 'missingNone':
                    missing = None
                elif change == 'missing403':
                    missing['status'] = 403
                elif change == 'wrongCode':
                    missing['code'] = 'AccessDenied'
                elif change == 'dataCount':
                    result['deleted_data_files_count'] = 0
                elif change == 'manifestCount':
                    result['deleted_manifest_files_count'] = 0
                elif change == 'counterBool':
                    result['deleted_data_files_count'] = True
                elif change == 'counterOverflow':
                    result['deleted_data_files_count'] = 2**63
                else:
                    result['unknown'] = 1
                self.rejected(lambda: c.verify_expiration(before, after, result, missing))


if __name__ == '__main__':
    unittest.main(verbosity=2)
