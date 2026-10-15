import copy
import importlib.util
import json
from pathlib import Path
import sys
import unittest

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import private_secrets
import render_plan
import resolve_images
import sql_plan
import validation_contract as contract


def snapshot_rows():
    return [{"snapshot_id": 5000000000000000000, "parent_id": None, "operation": "append", "added_records": None, "total_records": "0"},
            {"snapshot_id": 5000000000000000001, "parent_id": 5000000000000000000, "operation": "append", "added_records": "6", "total_records": "6"},
            {"snapshot_id": 5000000000000000002, "parent_id": 5000000000000000001, "operation": "append", "added_records": "6", "total_records": "12"}]


def preflight():
    return {"scope": "PHASE6_LIVE_READONLY_PREFLIGHT", "productionSourceCommit": "a" * 40, "productionBaselineSha256": "b" * 64,
            "originalJobs": 7, "originalExports": 14, "originalSlotFree": True, "originalKafkaOffset": 7, "originalKafkaEnd": 7,
            "originalPvcCount": 11, "originalPodCount": 6, "originalDockerCount": 38, "originalRunningDockerCount": 26,
            "namespaceAbsent": True, "bucketAbsent": True, "newCredentialIdentity": True,
            "existingVolumes": ["/owned/original-volume-%02d" % i for i in range(11)], "memoryAvailableBytes": 9 * contract.GIB,
            "diskAvailableBytes": 20 * contract.GIB, "freeInodes": 100000, "heavyCiActive": False, "networkPolicyControllerPresent": True}


def capability():
    plan = contract.store_plan()
    return {"scope": "OWN_FRESH_BUCKET_S3_CAPABILITY", "bucket": sql_plan.BUCKET,
            "keyPermissions": {"read": True, "write": True, "owner": False, "createBucket": False, "bucketCount": 1},
            "initialObjectCount": 0, "smallObjectWholeBytesVerified": True, "multipartUploadIdRecorded": True,
            "partNumbers": [1, 2], "partSizes": [5 * contract.MIB, contract.MIB], "multipartCompletedOnce": True,
            "multipartHeadBytes": 6 * contract.MIB, "multipartWholeSha256": plan["multipart"]["sha256"],
            "rangeRecords": [{**{key: value for key, value in item.items() if key != "expectedStatus"}, "status": 206} for item in plan["ranges"]],
            "listingEnded": True, "listedKeys": ["capability/metadata.json", "capability/multipart-6m.bin"],
            "requestAttemptsRecorded": True, "unknownOutcome": False, "trinoNativePathVerified": False}


def baseline():
    names = {"productionSourceCommit", "productionBaselineSha256", "originalJobs", "originalExports", "originalKafkaOffset", "originalKafkaEnd",
             "originalPvcCount", "originalPodCount", "originalDockerCount", "originalRunningDockerCount", "existingVolumes"}
    return {key: value for key, value in preflight().items() if key in names}


def restart_projection():
    return {"trinoPodUid": "11111111-1111-1111-1111-111111111111", "trinoContainerId": "containerd://" + "a" * 64,
            "trinoImageConfigDigest": "sha256:1a95bd13a3771179e2859fba98fc5831091a82f65ca12d193144be40d3bbd921",
            "postgresPodUid": "22222222-2222-2222-2222-222222222222", "postgresContainerId": "containerd://" + "d" * 64,
            "postgresProcessStartTicks": 12345, "postgresPvcUid": "33333333-3333-3333-3333-333333333333",
            "trinoPvcUid": "44444444-4444-4444-4444-444444444444", "catalogMetadataPointer": "s3://" + sql_plan.BUCKET + "/warehouse/phase6/bronze/synthetic_events/metadata/00002-test.metadata.json",
            "rows": sql_plan.golden_rows(), "snapshots": snapshot_rows(), "configSha256": "b" * 64}


class PreparationTest(unittest.TestCase):
    def test_fixture_fingerprint_and_bronze_counts_are_independent_of_processor(self):
        self.assertEqual(1100, len(sql_plan.source_bytes()))
        for count, distinct, a, b in ((6, 5, 5, 1), (12, 10, 8, 4)):
            rows = sql_plan.golden_rows(count)
            self.assertEqual(distinct, len({row["event_id"] for row in rows}))
            self.assertEqual(a, sum(row["sensor_id"] == "sensor-a" for row in rows))
            self.assertEqual(b, sum(row["sensor_id"] == "sensor-b" for row in rows))
            self.assertEqual(sql_plan.rows_sha(rows), sql_plan.verify_rows(rows, count))
        self.assertEqual(1, sum(row["event_time_raw"] == "not-a-timestamp" for row in sql_plan.golden_rows()))
        self.assertEqual(1, sum(row["sensor_value"] > 100 for row in sql_plan.golden_rows()))

    def test_exact_rows_reject_reordering_deduplication_and_normalized_error_timestamp(self):
        rows = sql_plan.golden_rows()
        for changed in (rows[::-1], rows[:-1], [{**row, "event_time_raw": "2026-01-01T00:00:00Z"} if row["input_sequence"] == 5 else row for row in rows]):
            with self.assertRaises(ValueError): sql_plan.verify_rows(changed, 12)

    def test_only_two_fixed_inserts_and_no_destructive_or_existing_database_sql(self):
        plan = sql_plan.plan()
        self.assertFalse(plan["runtimeResultsVerified"])
        self.assertFalse(plan["silverProcessorImplemented"])
        self.assertEqual(2, sum(row["sql"].startswith("INSERT INTO ") for row in plan["statements"]))
        for row in plan["statements"]:
            self.assertNotRegex(row["sql"], r"(?i)DROP |DELETE |TRUNCATE |platform_lab|EXPIRE|OPTIMIZE")
        self.assertEqual(6, sql_plan.insert_batch(1).count(sql_plan.SOURCE_SHA))
        for value in (0, 3, True, "1"):
            with self.assertRaises(ValueError): sql_plan.insert_batch(value)

    def test_time_travel_accepts_only_positive_bigint_snapshot_ids(self):
        self.assertIn("FOR VERSION AS OF 5000000000000000001", sql_plan.ordered_rows_query(5000000000000000001))
        for value in (0, -1, True, (1 << 63), "1; DROP TABLE x"):
            with self.assertRaises(ValueError): sql_plan.ordered_rows_query(value)

    def test_snapshot_chain_rejects_overwrite_missing_or_duplicate_append(self):
        self.assertEqual([5000000000000000000, 5000000000000000001, 5000000000000000002], sql_plan.verify_snapshots(snapshot_rows()))
        for key, value in (("parent_id", None), ("snapshot_id", 5000000000000000001), ("operation", "overwrite"), ("total_records", "6")):
            rows = snapshot_rows(); rows[2][key] = value
            with self.assertRaises(ValueError): sql_plan.verify_snapshots(rows)

    def test_plan_is_stopped_internal_new_namespace_and_unprivileged(self):
        plan = render_plan.build_plan(); objects = plan["items"]
        self.assertEqual(14, len(objects))
        self.assertEqual(len(objects), len({(row["kind"], row["metadata"]["name"]) for row in objects}))
        self.assertFalse(any(row["kind"] in ("Secret", "Ingress", "ClusterRole", "ClusterRoleBinding", "RoleBinding") for row in objects))
        for row in objects:
            self.assertEqual(render_plan.LABELS, {key: row["metadata"]["labels"][key] for key in render_plan.LABELS})
            if row["kind"] != "Namespace": self.assertEqual(render_plan.NAMESPACE, row["metadata"]["namespace"])
            if row["kind"] == "Service": self.assertEqual("ClusterIP", row["spec"]["type"])
            if row["kind"] in ("StatefulSet", "Deployment"):
                self.assertEqual(0, row["spec"]["replicas"])
                pod = row["spec"]["template"]["spec"]
                self.assertIs(pod["automountServiceAccountToken"], False)
                self.assertTrue(pod["securityContext"]["runAsNonRoot"])
                self.assertFalse(pod.get("hostNetwork", False))
                self.assertFalse(any("hostPath" in volume for volume in pod["volumes"]))
                self.assertRegex(pod["containers"][0]["image"], r"@sha256:[0-9a-f]{64}$")
                self.assertEqual(["ALL"], pod["containers"][0]["securityContext"]["capabilities"]["drop"])

    def test_jdbc_secret_refs_v1_and_small_budget_are_explicit(self):
        config = render_plan.configuration()
        self.assertIn("iceberg.jdbc-catalog.schema-version=V1", config["iceberg.properties"])
        self.assertIn("fs.s3.enabled=true", config["iceberg.properties"])
        self.assertNotIn("fs.native-s3.enabled", config["iceberg.properties"])
        self.assertIn("${ENV:CATALOG_PASSWORD}", config["iceberg.properties"])
        self.assertIn("s3.max-error-retries=1", config["iceberg.properties"])
        self.assertNotIn("s3.max-error-retries=0", config["iceberg.properties"])
        self.assertIn("-Xmx2g", config["jvm.config"])
        self.assertNotIn("InitialRAMPercentage=80", config["jvm.config"])
        groups = json.loads(config["resource-groups.json"])
        self.assertEqual(1, groups["rootGroups"][0]["hardConcurrencyLimit"])
        self.assertEqual(0, groups["rootGroups"][0]["maxQueued"])
        self.assertNotIn("PASSWORD '", render_plan.postgres_init())
        self.assertIn("pg_read_file('/run/phase6-secrets/catalog-password')", render_plan.postgres_init())

    def test_namespace_quota_reserves_auto_root_ca_and_binders_start_no_database(self):
        items = render_plan.build_plan()["items"]
        quota = next(row["spec"]["hard"] for row in items if row["kind"] == "ResourceQuota")
        own_maps = sum(row["kind"] == "ConfigMap" for row in items)
        self.assertGreaterEqual(int(quota["configmaps"]), own_maps + 1, "The namespace root CA ConfigMap also consumes quota")
        for pod in render_plan.binding_pods()["items"]:
            self.assertEqual("Never", pod["spec"]["restartPolicy"])
            self.assertEqual(["/bin/bash", "-c", "exit 0"], pod["spec"]["containers"][0]["command"])
            self.assertNotIn("env", pod["spec"]["containers"][0])

    def test_readiness_uses_starting_false_healthcheck_not_http_200_only(self):
        deployment = next(row for row in render_plan.build_plan()["items"] if row["kind"] == "Deployment")
        container = deployment["spec"]["template"]["spec"]["containers"][0]
        self.assertEqual(["/usr/lib/trino/bin/health-check"], container["readinessProbe"]["exec"]["command"])

    def test_oci_hash_and_amd64_selection_fail_closed(self):
        raw = b'{"schemaVersion":2}'
        self.assertEqual({"schemaVersion": 2}, resolve_images.checked_json(raw, resolve_images.digest(raw)))
        with self.assertRaises(ValueError): resolve_images.checked_json(raw, "sha256:" + "0" * 64)
        child = {"platform": {"os": "linux", "architecture": "amd64"}, "digest": "sha256:" + "1" * 64}
        self.assertEqual(child, resolve_images.amd64_descriptor({"manifests": [child]}))
        for entries in ([], [child, child], [{**child, "platform": {"os": "linux", "architecture": "arm64"}}]):
            with self.assertRaises(ValueError): resolve_images.amd64_descriptor({"manifests": entries})

    def test_private_secret_shape_rejects_existing_bucket_or_endpoint_injection(self):
        value = {"bootstrapPassword": "a" * 64, "catalogPassword": "b" * 64, "s3Endpoint": "http://garage.platform-lab.svc.cluster.local:3900",
                 "bucket": sql_plan.BUCKET, "accessKey": "SYNTHETIC_TEST_KEY", "secretKey": "synthetic-only"}
        # Garage access IDs are alphanumeric; this intentional invalid fixture is rejected.
        with self.assertRaises(ValueError): private_secrets.secret_documents(value)
        value["accessKey"] = "TESTKEY123"
        self.assertEqual(2, len(private_secrets.secret_documents(value)["items"]))
        for key, changed in (("bucket", "platform-lab-synthetic"), ("s3Endpoint", "http://external.invalid:3900"),
                             ("bootstrapPassword", "weak"), ("catalogPassword", "a" * 64), ("secretKey", "bad\nline")):
            case = dict(value); case[key] = changed
            with self.assertRaises(ValueError): private_secrets.secret_documents(case)

    def test_preflight_requires_fresh_scope_idle_slot_and_reserves(self):
        self.assertTrue(contract.preflight(preflight(), baseline()))
        for key, value in (("originalSlotFree", False), ("namespaceAbsent", False), ("bucketAbsent", False),
                           ("memoryAvailableBytes", 9 * contract.GIB - 1), ("diskAvailableBytes", 20 * contract.GIB - 1),
                           ("freeInodes", 99999), ("originalJobs", 6), ("heavyCiActive", True), ("networkPolicyControllerPresent", False)):
            case = preflight(); case[key] = value
            with self.assertRaises(ValueError): contract.preflight(case, baseline())

    def test_s3_multipart_requires_exact_bytes_ranges_nonowner_acl_and_no_native_claim(self):
        self.assertTrue(contract.verify_store_capability(capability()))
        for key, value in (("partSizes", [contract.MIB, 5 * contract.MIB]), ("unknownOutcome", True), ("listingEnded", False),
                           ("multipartWholeSha256", "0" * 64), ("trinoNativePathVerified", True)):
            case = capability(); case[key] = value
            with self.assertRaises(ValueError): contract.verify_store_capability(case)
        case = capability(); case["rangeRecords"][0]["status"] = 200
        with self.assertRaises(ValueError): contract.verify_store_capability(case)
        case = capability(); case["keyPermissions"]["owner"] = True
        with self.assertRaises(ValueError): contract.verify_store_capability(case)

    def test_trino_restart_requires_new_identity_but_same_postgres_pvcs_rows_and_snapshots(self):
        before = restart_projection(); after = copy.deepcopy(before)
        after["trinoPodUid"] = "55555555-5555-5555-5555-555555555555"; after["trinoContainerId"] = "containerd://" + "c" * 64
        self.assertTrue(contract.verify_restart(before, after))
        with self.assertRaises(ValueError): contract.verify_restart(before, before)
        after["postgresPvcUid"] = "66666666-6666-6666-6666-666666666666"
        with self.assertRaises(ValueError): contract.verify_restart(before, after)


if __name__ == "__main__":
    unittest.main()
