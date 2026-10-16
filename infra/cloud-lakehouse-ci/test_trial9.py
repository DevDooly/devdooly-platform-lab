"""Meaningful offline contract/lifecycle regressions; no Docker, Spark or S3."""
import ast
import copy
import hashlib
import importlib.util
import json
from pathlib import Path, PurePosixPath
import subprocess
import sys
import tempfile
import types
import unittest
from unittest.mock import Mock, patch

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import contract as c
import compose_trial9
import run_trial9 as runner
import s3_readonly


def chain():
    # Deliberately descending IDs and unordered input; parent links define order.
    return [{"snapshot_id": "3", "parent_id": "9", "operation": "replace", "total_records": "12"},
            {"snapshot_id": "9", "parent_id": "99", "operation": "append", "total_records": "12"},
            {"snapshot_id": "99", "parent_id": None, "operation": "append", "total_records": "6"}]


class Contracts(unittest.TestCase):
    def test_parent_chain_not_numeric_order_and_fixed_three_states(self):
        self.assertEqual([row["snapshot_id"] for row in c.snapshot_chain(chain(), 3)], ["99", "9", "3"])
        for field, value in (("parent_id", "3"), ("operation", "append"), ("total_records", "13"), ("snapshot_id", "9;DROP TABLE x")):
            actual = chain(); actual[0][field] = value
            with self.assertRaises(ValueError): c.snapshot_chain(actual, 3)

    def test_file_two_to_one_and_procedure_are_actual_not_options_claim(self):
        prefix = "s3://platform-lab-iceberg-20261015/warehouse/phase6/bronze/synthetic_events/data/"
        two = [{"file_path": prefix + name, "record_count": 6, "file_size_in_bytes": 100, "content": 0} for name in ("a.parquet", "b.parquet")]
        self.assertEqual(len(c.files(two, 2)), 2)
        bad = copy.deepcopy(two); bad[1]["file_path"] = bad[0]["file_path"]
        with self.assertRaises(ValueError): c.files(bad, 2)
        output = {"rewritten_data_files_count": 2, "added_data_files_count": 1, "rewritten_bytes_count": 200, "failed_data_files_count": 0, "removed_delete_files_count": 0}
        c.procedure_result(output)
        for name, value in (("added_data_files_count", 2), ("failed_data_files_count", 1), ("removed_delete_files_count", True)):
            bad = dict(output); bad[name] = value
            with self.assertRaises(ValueError): c.procedure_result(bad)

    def test_real_cloud_hash_roundtrip_and_double_projection(self):
        # Execute the actual frozen function body without importing any IO client.
        workspace = HERE.parents[3]
        old = workspace / "platform-spark-pid-budget-20261016/public/infra/spark-silver/silver_contract.py"
        if not old.exists():
            old = HERE.parent / "spark-silver/silver_contract.py"
        text = old.read_text("utf-8")
        self.assertEqual(hashlib.sha256(text.encode()).hexdigest(), "889fdb91ec4613d19f62a622e4cc889a27e38012905019f05d4743130f8268df")
        node = next(value for value in ast.parse(text).body if isinstance(value, ast.FunctionDef) and value.name == "row_sha")
        namespace = {"hashlib": hashlib, "json": json}
        exec(compile(ast.Module(body=[node], type_ignores=[]), str(old), "exec"), namespace)
        golden = [{"input_sequence": i, "event_id": str(i), "sensor_id": "s", "event_time_raw": "2026-10-15T00:00:00Z", "sensor_value": 1, "source_sha256": "a"*64} for i in range(1, 7)]
        float_rows = copy.deepcopy(golden)
        for value in float_rows: value["sensor_value"] = 1.0
        restored = json.loads(json.dumps(float_rows, sort_keys=True))
        projected = c.rows(restored, golden)
        self.assertEqual(c.row_sha(projected), namespace["row_sha"](float_rows))
        self.assertEqual(c.row_sha(c.rows(golden, golden)), c.row_sha(projected))
        self.assertIs(type(golden[0]["sensor_value"]), int)
        restored[0]["sensor_value"] = 1.1
        with self.assertRaises(ValueError): c.rows(restored, golden)

    def test_fixed_ten_trino_selects_and_json_boundaries(self):
        query = c.query_plan(chain())
        self.assertEqual(len(query), 10)
        self.assertTrue(all(value.startswith("SELECT ") and ";" not in value for _, value in query))
        self.assertEqual(c.parse_cli(b'{"value":1}\n'), [{"value": 1}])
        for raw in (b'{"v":1,"v":2}\n', b'{"v":NaN}\n', b'warning\n', b'{}\n'*14):
            with self.assertRaises((ValueError, json.JSONDecodeError)): c.parse_cli(raw)

    def test_one_clock_reserve_and_future_clock_rejected(self):
        current = [10.0]
        deadline = c.Deadline(0, lambda: current[0])
        self.assertEqual(deadline.remaining(600, 60), 530)
        current[0] = 541
        with self.assertRaises(ValueError): deadline.remaining(10, 60)
        with self.assertRaises(ValueError): c.Deadline(20, lambda: 10)
        with self.assertRaises(ValueError): c.Deadline(float("nan"), lambda: 10)

    def test_compose_preserves_old_roles_and_python_reader_no_java(self):
        base = {"services": {"postgres": {"old": "pg"}, "garage": {"old": "garage"}, "spark": {"command": ["old-bootstrap"], "pids_limit": 512}}, "volumes": {}, "networks": {"trial": {"internal": True}}}
        actual = compose_trial9.plan(lambda _: copy.deepcopy(base), "spark-isolated-ci:" + "a"*32, "pinned-spark")
        self.assertEqual(actual["services"]["postgres"], base["services"]["postgres"])
        self.assertEqual(actual["services"]["garage"], base["services"]["garage"])
        self.assertEqual(actual["services"]["reader"]["command"], ["python3", "/reader/s3_readonly.py"])
        self.assertEqual((actual["services"]["reader"]["mem_limit"], actual["services"]["reader"]["pids_limit"]), ("128m", 16))
        self.assertEqual(actual["services"]["trino"]["mem_limit"], "4g")

    def test_s3_scope_rejects_unknown_key_before_transport(self):
        client = s3_readonly.Client.__new__(s3_readonly.Client)
        client.open = Mock(side_effect=AssertionError("transport must not run"))
        for key in ("raw/original.json", "warehouse/phase6/../secret", "/warehouse/phase6/a", "warehouse/phase6/a?token=x"):
            with self.assertRaises(ValueError): client.get(key)
        client.open.assert_not_called()
        methods = [node.args[0].value for node in ast.walk(ast.parse((HERE / "s3_readonly.py").read_text()))
                   if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "signature"]
        self.assertEqual(methods, ["GET"])


class Lifecycle(unittest.TestCase):
    def setUp(self):
        class BaseAttempt:
            def __init__(self, root, project):
                self.root, self.project, self.sequence = root, project, 0
        self.saved = []
        self.base = types.SimpleNamespace(Attempt=BaseAttempt, save=lambda path, value: self.saved.append((path, value)))

    def test_start_blocks_live_spark_and_reader_before_normal_trino_exit(self):
        attempt = runner.make_attempt(self.base, Path("unused"), "project", {})
        attempt.deadline = c.Deadline(0, lambda: 0)
        attempt.containers = lambda: [{"role": "spark", "running": True, "exitCode": 0, "oom": False}]
        attempt.cli = Mock()
        with self.assertRaises(ValueError): attempt.start("trino")
        with self.assertRaises(ValueError): attempt.start("reader")
        attempt.cli.assert_not_called(); self.assertEqual(self.saved, [])
        role_ids = {"spark": "a"*64, "trino": "b"*64, "reader": "c"*64}
        attempt.containers = lambda: [{"role": role, "running": False, "exitCode": 0, "oom": False,
                                     "id": role_ids[role], "startedAt": "fixed" if role != "reader" else "0001-01-01T00:00:00Z",
                                     "pid": 0} for role in ("spark", "trino", "reader")]
        attempt.bound = {"reader": {"id": role_ids["reader"]}}
        attempt.command = Mock()
        attempt.trino_stop = {"cid": role_ids["trino"], "startedAt": "fixed", "requestReturnedZero": True,
                              "signalScope": "CONFIGURED_OR_DEFAULT_SIGTERM"}
        attempt.start("reader")
        with self.assertRaises(ValueError): attempt.start("reader")
        attempt.command.assert_called_once_with(["docker", "start", role_ids["reader"]])
        attempt.cli.assert_not_called()

    def test_actual_completedprocess_log_contract_and_full_cid_binding(self):
        result = subprocess.CompletedProcess([], 0, b"private stdout", b"private stderr")
        result.capture_truncated = False; result.capture_timed_out = False
        base = types.SimpleNamespace(bounded_deadline_logs=Mock(return_value=result), save=lambda path, value: self.saved.append((path, value)))
        row = {"role": "trino", "id": "a"*64}
        attempt = types.SimpleNamespace(containers=Mock(return_value=[row]))
        runner.capture_private_tail(base, Path("unused"), attempt, row)
        self.assertEqual([value for _, value in self.saved], [b"private stdout", b"private stderr"])
        self.saved.clear(); attempt.containers = Mock(side_effect=[[row], [{"role": "trino", "id": "b"*64}]])
        with self.assertRaises(ValueError): runner.capture_private_tail(base, Path("unused"), attempt, row)
        self.assertEqual(self.saved, [])

    def test_trino_configuration_has_existing_native_guards(self):
        config = runner.configuration()
        self.assertIn("-Xmx2g\n", config["jvm.config"])
        self.assertIn("s3.max-error-retries=1\n", config["iceberg.properties"])
        self.assertIn("iceberg.jdbc-catalog.catalog-name=phase6\n", config["iceberg.properties"])
        self.assertIn("iceberg.jdbc-catalog.schema-version=V1\n", config["iceberg.properties"])
        self.assertIn("retry-policy=NONE\n", config["config.properties"])
        self.assertIn("hardConcurrencyLimit", config["resource-groups.json"])

    def test_engine_mounts_api_and_fresh_declared_volume_no_foreign_bind(self):
        desired = {"volumes": ["./reader:/reader:ro", "./proof:/proof"], "tmpfs": ["/tmp:size=16m"]}
        raw = {"HostConfig": {"Tmpfs": {"/tmp": "size=16m"}}, "Mounts": [
            {"Type": "bind", "Source": "/new/reader", "Destination": "/reader", "RW": False},
            {"Type": "bind", "Source": "/new/proof", "Destination": "/proof", "RW": True},
            {"Type": "volume", "Name": "a"*64, "Driver": "local", "Destination": "/image-declared", "RW": True}]}
        runner.mounts_verified(raw, desired, PurePosixPath("/new"), "project", {"/image-declared"}, set())
        with self.assertRaises(ValueError): runner.mounts_verified(raw, desired, PurePosixPath("/new"), "project", {"/image-declared"}, {"a"*64})
        altered = copy.deepcopy(raw); altered["Mounts"][0]["Source"] = "/production"
        with self.assertRaises(ValueError): runner.mounts_verified(altered, desired, PurePosixPath("/new"), "project", {"/image-declared"}, set())
        altered = copy.deepcopy(raw); altered["Mounts"][0]["RW"] = True
        with self.assertRaises(ValueError): runner.mounts_verified(altered, desired, PurePosixPath("/new"), "project", {"/image-declared"}, set())

    def test_trino_term_requires_exact_explicit_stop_and_never_blesses_137(self):
        value = {"id": "a"*64, "startedAt": "fixed", "running": False, "exitCode": 143, "oom": False}
        stop = {"cid": "a"*64, "startedAt": "fixed", "requestReturnedZero": True, "signalScope": "CONFIGURED_OR_DEFAULT_SIGTERM"}
        c.normal_exit("trino", value, stop)
        for changed in ({**value, "exitCode": 137}, {**value, "oom": True}, {**value, "id": "b"*64}, {**value, "startedAt": "other"}):
            with self.assertRaises(ValueError): c.normal_exit("trino", changed, stop)
        with self.assertRaises(ValueError): c.normal_exit("trino", value)
        with self.assertRaises(ValueError): c.normal_exit("spark", value)

    def test_source_environment_requires_actual_checkout_head(self):
        source = "a"*40
        with patch.dict(runner.os.environ, {"GITHUB_SHA": source}), patch.object(runner.subprocess, "run") as command:
            command.return_value = subprocess.CompletedProcess([], 0, (source + "\n").encode(), b"")
            runner.checkout_source(Path("repo"), source)
            self.assertEqual(command.call_args.args[0], ["git", "-C", "repo", "rev-parse", "HEAD"])
            command.return_value = subprocess.CompletedProcess([], 0, ("b"*40 + "\n").encode(), b"")
            with self.assertRaises(ValueError): runner.checkout_source(Path("repo"), source)
        with patch.dict(runner.os.environ, {"GITHUB_SHA": "b"*40}), patch.object(runner.subprocess, "run") as command:
            with self.assertRaises(ValueError): runner.checkout_source(Path("repo"), source)
            command.assert_not_called()

    def test_public_diagnostic_drops_private_code_and_partial_progress(self):
        direct_phases = [node.value.value for node in ast.walk(ast.parse((HERE / "bootstrap_trial9.py").read_text()))
                         if isinstance(node, ast.Assign) and isinstance(node.value, ast.Constant)
                         and type(node.value.value) is str and any(isinstance(target, ast.Name) and target.id == "phase" for target in node.targets)]
        self.assertTrue(set(direct_phases).issubset(runner.PHASES))
        base = types.SimpleNamespace(PYTHON_EXCEPTIONS={"ValueError", "OTHER"}, JAVA_CLASS=__import__("re").compile(r"java\.[A-Za-z.]+"))
        value = {"passed": False, "phase": "COMPACTION_ONCE", "sessionStopFailed": False,
                 "exceptionClassesOnly": {"pythonExceptionClass": "ValueError", "javaCauseClasses": ["java.lang.IllegalArgumentException"],
                                          "nativeLibraryCategories": [], "failedMapSegmentObserved": False},
                 "fixedFailureCode": "SYNTHETIC_PRIVATE_TEXT", "elapsedMillis": 10}
        projected = runner.safe_bootstrap(base, value)
        self.assertNotIn("fixedFailureCode", projected)
        self.assertNotIn("SYNTHETIC_PRIVATE_TEXT", json.dumps(projected))
        with self.assertRaises(ValueError): runner.safe_bootstrap(base, dict(value, rawMessage="secret"))
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); (root / "proof").mkdir()
            record = {"phase": "SESSION", "sequence": 1, "completionNotProven": True, "elapsedMillis": 0}
            (root / "proof/trial9-progress-01.json").write_text(json.dumps(record))
            (root / "proof/.trial9-progress-02.json.tmp").write_text('{"partial":')
            self.assertEqual(runner.safe_progress(root), record)
            (root / "proof/trial9-progress-03.json").write_text(json.dumps(dict(record, sequence=3)))
            with self.assertRaises(ValueError): runner.safe_progress(root)

    def test_host_pid_cgroup_must_contain_exact_full_container_id(self):
        fields = ["R"] + ["0"]*19; fields[19] = "456"
        stat = "123 (java) " + " ".join(fields)
        own = "0::/system.slice/docker-" + "a"*64 + ".scope\n"
        foreign = "0::/system.slice/docker-" + "b"*64 + ".scope\n"
        with patch.object(runner.Path, "read_text", side_effect=[stat, own, stat, own, "boot"]):
            value = runner.process_identity(123, "a"*64)
            self.assertEqual((value["pid"], value["startTicks"]), (123, 456))
        with patch.object(runner.Path, "read_text", side_effect=[stat, foreign, stat, foreign]):
            with self.assertRaises(ValueError): runner.process_identity(123, "a"*64)
        reused = stat.rsplit("456", 1)[0] + "457"
        with patch.object(runner.Path, "read_text", side_effect=[stat, own, reused, own]):
            with self.assertRaises(ValueError): runner.process_identity(123, "a"*64)


if __name__ == "__main__":
    unittest.main()
