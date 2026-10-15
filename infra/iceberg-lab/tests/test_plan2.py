"""Offline synthetic fixtures; no actual DB, Kubernetes, SQL or network proof."""
import copy
import hashlib
import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import http_sql
import network_control_plan as network
import render_plan
import sql_plan
import validation_contract as contract
from test_preparation import baseline, preflight, restart_projection, snapshot_rows


def target():
    uid = lambda n: ('%08d' % n)+'-1111-1111-1111-111111111111'
    ns = {'metadata': {'name': 'platform-lab', 'uid': uid(1), 'labels': {'kubernetes.io/metadata.name': 'platform-lab'}}}
    service = {'metadata': {'name': 'api', 'namespace': 'platform-lab', 'uid': uid(2)},
        'spec': {'type': 'ClusterIP', 'clusterIP': '10.1.2.3', 'selector': {'component': 'api', 'instance': 'test'},
                 'ports': [{'port': 8080, 'targetPort': 'http'}]}}
    pod = {'metadata': {'name': 'api-fixture', 'namespace': 'platform-lab', 'uid': uid(3), 'labels': {'component': 'api', 'instance': 'test'}},
        'spec': {'containers': [{'ports': [{'name': 'http', 'containerPort': 8080}]}]},
        'status': {'phase': 'Running', 'podIP': '10.2.3.4', 'containerStatuses': [{'ready': True,
            'containerID': 'containerd://'+'a'*64, 'state': {'running': {'startedAt': 'synthetic'}}}]}}
    ep = {'metadata': {'name': 'api', 'namespace': 'platform-lab', 'uid': uid(4)}, 'subsets': [
        {'addresses': [{'ip': '10.2.3.4', 'targetRef': {'kind': 'Pod', 'namespace': 'platform-lab', 'name': 'api-fixture', 'uid': uid(3)}}],
         'ports': [{'port': 8080}]}]}
    return ns, service, pod, ep, []


class Plan2(unittest.TestCase):
    def test_initial_absent_added_summary_is_null_and_three_parented_snapshots(self):
        rows = snapshot_rows(); self.assertEqual(3, len(sql_plan.verify_snapshots(rows)))
        self.assertEqual([], sql_plan.golden_rows(0)); self.assertEqual(sql_plan.rows_sha([]), sql_plan.verify_rows([], 0))
        for bad in ('0', '6'):
            changed = copy.deepcopy(rows); changed[0]['added_records'] = bad
            with self.assertRaises(ValueError): sql_plan.verify_snapshots(changed)
        with self.assertRaises(ValueError): sql_plan.verify_snapshots(rows[1:])

    def test_empty_read_precedes_first_insert_and_missing_key_uses_safe_inspection(self):
        plan = sql_plan.plan(); names = [v['name'] for v in plan['statements']]
        self.assertLess(names.index('create_table'), names.index('read_initial_empty'))
        self.assertLess(names.index('read_initial_empty'), names.index('insert_six_1'))
        self.assertEqual([0, 6, 12], plan['timeTravelExpectedRows'])
        self.assertIn("element_at(summary,'added-records')", plan['inspection']['snapshots'])
        self.assertNotIn("summary['added-records']", plan['inspection']['snapshots'])
        self.assertEqual((1, 2, 3), tuple(plan[k] for k in ('initialEmptySnapshots', 'dataAppendSnapshots', 'totalSnapshots')))

    def test_row_hash_keeps_original_golden_and_survives_sorted_receipt_serialization(self):
        for count, expected in [(6, '411dc42e274b9c0e73e08b1725fd08fcc75cc3217c1f10d3102f79c8319b48ec'),
                (12, '1c31bc6976083c78549cb0a6b1a48517d16e5bd683da474d75bea1756f1d8514')]:
            rows = sql_plan.golden_rows(count)
            self.assertEqual(expected, sql_plan.rows_sha(rows))
            self.assertEqual(expected, sql_plan.rows_sha(json.loads(json.dumps(rows, sort_keys=True))))
        changed = sql_plan.golden_rows(); changed[0]['private'] = 'unexpected'
        with self.assertRaises(ValueError): sql_plan.rows_sha(changed)

    def test_http_removes_one_delimiter_and_preserves_original_and_interior_literal(self):
        text = "SELECT ';' AS value;\n\t"
        value = http_sql.prepare(text)
        self.assertEqual("SELECT ';' AS value\n\t", value['wireSql'])
        self.assertEqual(text, value['originalSql'])
        self.assertEqual(hashlib.sha256(text.encode()).hexdigest(), value['originalSha256'])
        self.assertEqual(hashlib.sha256(value['wireSql'].encode()).hexdigest(), value['wireSha256'])
        self.assertFalse(value['submitted']); self.assertIsNone(value['queryId'])
        self.assertEqual('SELECT 1', http_sql.prepare('SELECT 1')['wireSql'])
        with self.assertRaises(ValueError): http_sql.prepare('SELECT 1;;\n')

    def test_http_plan_covers_fixed_sql_without_posting_or_inventing_query_identity(self):
        result = http_sql.request_plan()
        self.assertEqual(0, result['networkRequestsPerformed']); self.assertFalse(result['driverImplemented'])
        self.assertEqual(2, sum(v['mutation'] and v['originalSql'].startswith('INSERT') for v in result['statements']))
        self.assertTrue(all(v['automaticRetries'] == 0 and not v['submitted'] and v['queryId'] is None
            and not v['wireSql'].rstrip().endswith(';') for v in result['statements']+result['inspection']))

    def test_api_policy_combines_namespace_and_actual_selector_in_one_peer(self):
        record = target(); actual = network.target_binding(*record)
        plan = network.build(actual['selector']); policy = plan['policy']
        self.assertEqual(render_plan.NAMESPACE, policy['metadata']['namespace'])
        peers = policy['spec']['egress'][0]['to']; self.assertEqual(1, len(peers))
        self.assertEqual({'namespaceSelector', 'podSelector'}, set(peers[0]))
        self.assertEqual(record[1]['spec']['selector'], peers[0]['podSelector']['matchLabels'])
        self.assertNotIn('ipBlock', json.dumps(policy)); self.assertFalse(plan['liveTargetBindingVerified'])

    def test_api_binding_rejects_different_endpoint_pod_or_ingress_isolation(self):
        for mutate in (lambda r: r[3]['subsets'][0]['addresses'][0]['targetRef'].update(uid='00000009-1111-1111-1111-111111111111'),
                lambda r: r[2]['metadata']['labels'].update(instance='foreign'),
                lambda r: r[2]['status']['containerStatuses'][0].update(ready=False),
                lambda r: r[4].append({'spec': {'policyTypes': ['Ingress']}})):
            record = target(); mutate(record)
            with self.assertRaises(ValueError): network.target_binding(*record)
        for value in ({}, {'component': 'api\n'}, {'component': ''}):
            with self.assertRaises(ValueError): network.build(value)

    def test_plan2_is_disjoint_from_retained_old_scope_and_stays_stopped(self):
        self.assertNotEqual('platform-lab-iceberg-20261015', render_plan.NAMESPACE)
        self.assertNotEqual('platform-lab-iceberg-20261015', sql_plan.BUCKET)
        for item in render_plan.build_plan()['items']:
            if item['kind'] in ('StatefulSet', 'Deployment'): self.assertEqual(0, item['spec']['replicas'])
        self.assertIn('s3.max-error-retries=1\n', render_plan.configuration()['iceberg.properties'])

    def test_preflight_compares_independent_current_baseline_not_historical_seven(self):
        current, expected = preflight(), baseline()
        for value in (current, expected):
            value.update(originalJobs=8, originalExports=16, originalKafkaOffset=8, originalKafkaEnd=8,
                originalPvcCount=13, existingVolumes=['/synthetic/current-%d' % n for n in range(13)])
        self.assertTrue(contract.preflight(current, expected))
        changed = copy.deepcopy(current); changed['originalKafkaOffset'] = 7
        with self.assertRaises(ValueError): contract.preflight(changed, expected)
        with self.assertRaises(ValueError): contract.preflight(current, {})

    def test_same_postgres_pod_rejects_container_or_process_restart(self):
        before = restart_projection(); after = copy.deepcopy(before)
        after.update(trinoPodUid='55555555-5555-5555-5555-555555555555', trinoContainerId='containerd://'+'c'*64)
        self.assertTrue(contract.verify_restart(before, after))
        for key, value in (('postgresContainerId', 'containerd://'+'e'*64), ('postgresProcessStartTicks', 12346),
                ('postgresContainerId', 'foreign'), ('postgresProcessStartTicks', 0), ('postgresProcessStartTicks', True)):
            changed = copy.deepcopy(after); changed[key] = value
            with self.assertRaises(ValueError): contract.verify_restart(before, changed)


if __name__ == '__main__': unittest.main()
