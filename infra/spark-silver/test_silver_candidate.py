"""Offline synthetic-only oracle, replay, vendor gate and suspended Job checks."""
import copy
import ast
import json
from pathlib import Path
import unittest
import silver_contract as c
import render_plan as plan
import validate_vendor as vendor


class SilverCandidateTest(unittest.TestCase):
    def test_spark_connection_matches_frozen_phase6_role_region_and_catalog_contract(self):
        contract=json.loads(Path(__file__).with_name('phase6-connection-contract.json').read_bytes())
        tree=ast.parse(Path(__file__).with_name('spark_silver.py').read_text('utf-8'))
        method=next(v for v in tree.body if isinstance(v,ast.FunctionDef) and v.name=='session')
        config=next(v.value for v in method.body if isinstance(v,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='values' for t in v.targets))
        values={k.value:v.value for k,v in zip(config.keys,config.values) if isinstance(v,ast.Constant)}
        self.assertEqual(contract['jdbcUser'],values['spark.sql.catalog.phase6.jdbc.user'])
        self.assertEqual(contract['s3Region'],values['spark.sql.catalog.phase6.client.region'])
        self.assertEqual(contract['jdbcSchemaVersion'],values['spark.sql.catalog.phase6.jdbc.schema-version'])
        self.assertEqual('phase6',contract['catalogName']);self.assertEqual('false',values['spark.sql.catalog.phase6.jdbc.init-catalog-tables'])

    def test_fixed_fixture_and_full_ordered_manual_golden_statuses(self):
        rows=c.golden_bronze();c.validate_bronze(rows);out=c.classify(rows)
        self.assertEqual(['SUCCESS','SUCCESS','SUCCESS','DUPLICATE','FAILED','FAILED','FAILED','SUCCESS','SUCCESS','SUCCESS','DUPLICATE','SUCCESS'],[v['status'] for v in out])
        self.assertEqual(['ACCEPTED','ACCEPTED','ACCEPTED','DUPLICATE_EVENT_ID','INVALID_TIMESTAMP','OUT_OF_ORDER','OUT_OF_RANGE','ACCEPTED','ACCEPTED','ACCEPTED','DUPLICATE_EVENT_ID','ACCEPTED'],[v['reason'] for v in out])
        self.assertEqual(list(range(1,13)),[v['input_sequence'] for v in out])
        self.assertEqual({'SUCCESS':7,'FAILED':3,'DUPLICATE':2},{k:sum(v['status']==k for v in out) for k in ('SUCCESS','FAILED','DUPLICATE')})

    def test_reordering_extra_input_or_source_modification_cannot_be_accepted_as_bronze(self):
        rows=c.golden_bronze()
        for modified in (rows[::-1],rows+[rows[0]],rows[:11]):
            with self.assertRaises(ValueError):c.validate_bronze(modified)
        modified=copy.deepcopy(rows);modified[0]['sensor_value']=22.0
        with self.assertRaises(ValueError):c.validate_bronze(modified)

    def test_failed_timestamp_still_reserves_event_id_as_duplicate(self):
        rows=copy.deepcopy(c.golden_bronze()[:2]);rows[0]['event_time_raw']='invalid';rows[1]['event_id']=rows[0]['event_id']
        self.assertEqual(['INVALID_TIMESTAMP','DUPLICATE_EVENT_ID'],[v['reason'] for v in c.classify(rows)])

    def test_equal_times_accepted_and_failed_range_does_not_advance_sensor_clock(self):
        rows=copy.deepcopy(c.golden_bronze()[:3]);rows[1]['sensor_id']='sensor-a';rows[1]['event_time_raw']=rows[0]['event_time_raw']
        self.assertEqual('SUCCESS',c.classify(rows)[1]['status'])
        rows[1]['event_time_raw']='2026-01-01T01:00:00Z';rows[1]['sensor_value']=101
        self.assertEqual(['ACCEPTED','OUT_OF_RANGE','ACCEPTED'],[v['reason'] for v in c.classify(rows)])

    def test_invalid_sequence_and_boolean_sequence_are_rejected(self):
        for value in (0,True,2):
            rows=copy.deepcopy(c.golden_bronze()[:1]);rows[0]['input_sequence']=value
            with self.assertRaises(ValueError):c.classify(rows)

    def test_replay_only_accepts_complete_identical_persisted_batch(self):
        expected=c.classify(c.golden_bronze())
        self.assertEqual('MERGE_FIXED_BATCH_ONCE',c.replay_action([]))
        self.assertEqual('READ_ONLY_IDENTICAL_BATCH_NO_WRITE',c.replay_action(expected))
        wrong=copy.deepcopy(expected);wrong[0]['batch_id']='foreign'
        for rows in (expected[:7],expected+[expected[0]],wrong):
            with self.assertRaises(ValueError):c.replay_action(rows)

    def test_unresolved_vendor_checksums_block_before_any_vendor_file_access(self):
        lock=json.loads(Path(__file__).with_name('artifact-plan.json').read_bytes())
        with self.assertRaisesRegex(ValueError,'UNRESOLVED'):vendor.validate(lock,Path('NONEXISTENT_SYNTHETIC_PATH'))

    def test_proposal_is_suspended_no_pvc_service_token_or_runtime_package_download(self):
        value=plan.plan('ghcr.io/devdooly/devdooly-platform-lab-spark-silver@sha256:'+'a'*64,123,'b'*64)
        items=value['resources']['items'];job=next(v for v in items if v['kind']=='Job');spec=job['spec']['template']['spec']
        self.assertTrue(job['spec']['suspend']);self.assertEqual(0,job['spec']['backoffLimit']);self.assertEqual('Never',spec['restartPolicy'])
        self.assertFalse(spec['automountServiceAccountToken']);self.assertFalse(any(v['kind'] in ('Service','PersistentVolumeClaim','Secret') for v in items))
        self.assertNotIn('--packages',json.dumps(value));self.assertEqual({'cpu':'1','memory':'3Gi','ephemeral-storage':'3Gi'},spec['containers'][0]['resources']['limits'])

    def test_job_pin_and_positive_snapshot_are_required_no_tag_only_image(self):
        for image,snapshot in (('apache/spark:latest',123),('ghcr.io/devdooly/devdooly-platform-lab-spark-silver@sha256:'+'a'*64,0)):
            with self.assertRaises(ValueError):plan.plan(image,snapshot,'b'*64)

    def test_only_owned_postgres_ingress_is_proposed_outside_new_namespace(self):
        items=plan.plan('ghcr.io/devdooly/devdooly-platform-lab-spark-silver@sha256:'+'a'*64,123,'b'*64)['resources']['items']
        external=[v for v in items if v['metadata'].get('namespace') not in (None,plan.NAMESPACE)]
        self.assertEqual(1,len(external));self.assertEqual('NetworkPolicy',external[0]['kind'])
        self.assertEqual('platform-lab-iceberg-20261015',external[0]['metadata']['namespace'])
        self.assertEqual([{'protocol':'TCP','port':5432}],external[0]['spec']['ingress'][0]['ports'])


if __name__=='__main__':unittest.main()
