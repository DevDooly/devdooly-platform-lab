"""Historical artifact provenance and adversarial DTO contracts; no service execution."""
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

import spark_public as p

ROOT = Path(__file__).resolve().parents[2]
SUMMARY = ROOT / 'docs/evidence/spark-silver/summary.json'
ASSET = ROOT / 'apps/lab-web/public/observations/spark.latest.json'


def asset():
    return json.loads(ASSET.read_bytes())


class PublicSparkTrial(unittest.TestCase):
    def test_actual_saved_summary_projects_to_the_complete_public_asset(self):
        raw = SUMMARY.read_bytes()
        self.assertEqual(p.SUMMARY_BYTES, len(raw))
        self.assertEqual(p.SUMMARY_SHA, hashlib.sha256(raw).hexdigest())
        self.assertEqual(asset(), p.project(raw))

    def test_complete_typed_record_survives_json_key_reordering(self):
        value = json.loads(json.dumps(asset(), sort_keys=True))
        self.assertIs(value, p.validate(value))

    def test_source_bytes_cannot_be_reformatted_or_replaced_by_a_failed_prior_run(self):
        raw = SUMMARY.read_bytes()
        for changed in (raw + b'\n', raw.replace(p.SOURCE.encode(), b'a' * 40),
                json.dumps({**json.loads(raw), 'passed': False}).encode()):
            with self.assertRaises(ValueError): p.project(changed)

    def test_result_counts_must_preserve_all_twelve_ordered_outcomes(self):
        for field, wrong in (('rows', 11), ('success', 8), ('failure', 2), ('duplicate', 0), ('pending', 1), ('rows', True)):
            value = asset(); value['silver'][field] = wrong
            with self.subTest(field=field), self.assertRaises(ValueError): p.validate(value)

    def test_partial_or_abnormal_stop_cannot_claim_verified_completion(self):
        for field, wrong in (('bootstrapCompleted', False), ('sessionStopFailed', True), ('exitCode', 137),
                ('oomKilled', True), ('ownedComposeStopped', False), ('ownedInitializerStopped', False), ('exitCode', False)):
            value = asset(); value['stop'][field] = wrong
            with self.subTest(field=field), self.assertRaises(ValueError): p.validate(value)

    def test_cloud_record_cannot_gain_minipc_native_or_concurrent_scope(self):
        for field in asset()['exclusions']:
            value = asset(); value['exclusions'][field] = True
            with self.subTest(field=field), self.assertRaises(ValueError): p.validate(value)
        value = asset(); value['scope'] = 'DEPLOYED_RUNTIME'
        with self.assertRaises(ValueError): p.validate(value)

    def test_bigint_snapshot_identity_refuses_numeric_rounding_duplicates_and_overflow(self):
        for ids in ([int(p.SNAPSHOT_IDS[0]), p.SNAPSHOT_IDS[1]], [p.SNAPSHOT_IDS[0]] * 2,
                ['9223372036854775808', p.SNAPSHOT_IDS[1]], ['01', p.SNAPSHOT_IDS[1]],
                ['1', p.SNAPSHOT_IDS[1]], p.SNAPSHOT_IDS[:1]):
            value = asset(); value['bronze']['snapshotIds'] = ids
            with self.subTest(ids=ids), self.assertRaises(ValueError): p.validate(value)

    def test_budget_cannot_be_recast_as_unlimited_or_broader_resources(self):
        for field, wrong in (('sparkPidLimit', 0), ('sparkPidLimit', -1), ('postgresGaragePidLimit', 512),
                ('sparkCpu', 2), ('sparkMemoryBytes', 4 * 1024**3), ('sparkDriverHeapMiB', 2048),
                ('deadlineSeconds', 601), ('hostPublishedPorts', 1)):
            value = asset(); value['resources'][field] = wrong
            with self.subTest(field=field), self.assertRaises(ValueError): p.validate(value)

    def test_elapsed_value_cannot_become_per_stage_time_or_throughput(self):
        for field, wrong in (('bootstrapCompletedElapsedMillis', -1), ('bootstrapCompletedElapsedMillis', 1),
                ('scope', 'PER_JOB_PURE_TRANSFORM'), ('stageDurationsOrThroughputMeasured', True)):
            value = asset(); value['timing'][field] = wrong
            with self.subTest(field=field), self.assertRaises(ValueError): p.validate(value)

    def test_extra_unknown_private_fields_are_rejected_at_every_depth(self):
        for section in (None, 'run', 'summary', 'fixture', 'versions', 'bronze', 'silver', 'stop', 'resources', 'timing', 'exclusions'):
            value = asset(); target = value if section is None else value[section]
            target['privateConnection'] = 'must-not-be-published'
            with self.subTest(section=section), self.assertRaises(ValueError): p.validate(value)

    def test_source_run_origin_and_summary_are_bound_to_this_actual_record(self):
        changes = [('sourceCommit', 'a' * 40), ('schemaVersion', 2), ('status', 'RUNNING')]
        for field, wrong in changes:
            value = asset(); value[field] = wrong
            with self.assertRaises(ValueError): p.validate(value)
        for section, field, wrong in (('run', 'url', 'https://foreign.invalid/run'), ('run', 'id', '38801841777'),
                ('run', 'attempt', 7), ('summary', 'sha256', '0' * 64), ('summary', 'bytes', 5388)):
            value = asset(); value[section][field] = wrong
            with self.assertRaises(ValueError): p.validate(value)

    def test_cli_creates_only_a_new_artifact_and_preserves_an_existing_output(self):
        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder) / 'spark.latest.json'
            self.assertEqual(0, p.main(['--summary', str(SUMMARY), '--output', str(output)]))
            before = output.read_bytes()
            self.assertEqual(asset(), json.loads(before))
            with self.assertRaises(FileExistsError): p.main(['--summary', str(SUMMARY), '--output', str(output)])
            self.assertEqual(before, output.read_bytes())


if __name__ == '__main__':
    unittest.main()
