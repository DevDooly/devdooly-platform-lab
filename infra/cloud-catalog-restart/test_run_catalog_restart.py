"""Pure driver fixtures. No Docker, SQL, network, images, JARs or credentials."""
import copy
import hashlib
import json
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import run_catalog_restart as driver


def catalog_result():
    return dict(driver.CATALOG_FIXED, namespacePropertyRows=2)


def source_fixture(root):
    here = root / "infra/cloud-catalog-restart"
    cloud_raw, restart_raw = b"old-cloud-manifest\n", b"old-trino-manifest\n"
    data = {root / name: b"frozen:" + name.encode() for name in driver.FROZEN_FILES}
    data.update({here / name: b"new:" + name.encode() for name in driver.OWN_FILES})
    data[root / "infra/cloud-lakehouse-ci/runtime-manifest.json"] = cloud_raw
    data[root / driver.RESTART_MANIFEST] = restart_raw
    pin = lambda raw: dict(bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest())
    manifest = dict(schemaVersion=1, scope=driver.SCOPE, status="SOURCE_ONLY_NOT_RUN",
        files={name: pin(data[here / name]) for name in driver.OWN_FILES},
        frozenSources={name: pin(data[root / name]) for name in driver.FROZEN_FILES},
        frozenRuntimeManifestSha256=hashlib.sha256(cloud_raw).hexdigest(),
        frozenTrinoRestartManifestSha256=hashlib.sha256(restart_raw).hexdigest())
    return here, data, manifest


class DriverTest(unittest.TestCase):
    def test_source_manifest_binds_exact_five_new_eighteen_frozen_and_both_old_manifests(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve(); here, data, value = source_fixture(root)
            raw = json.dumps(value).encode(); data[here / "runtime-manifest.json"] = raw
            self.assertEqual((5, 18), (len(driver.OWN_FILES), len(driver.FROZEN_FILES)))
            with patch.object(driver, "HERE", here), patch.object(driver, "REPO", root), \
                 patch.object(driver, "FROZEN_MANIFEST", value["frozenRuntimeManifestSha256"]), \
                 patch.object(driver, "RESTART_MANIFEST_SHA256", value["frozenTrinoRestartManifestSha256"]), \
                 patch.object(driver, "regular_bytes", side_effect=lambda path: data[Path(path)]):
                snapshot = driver.source_snapshot(hashlib.sha256(raw).hexdigest())
                self.assertEqual(24, len(snapshot))  # 23 source entries plus the new manifest itself.
                with self.assertRaises(ValueError):
                    driver.source_snapshot("0" * 64)
                data[root / "infra/cloud-lakehouse-ci/contract.py"] += b"changed"
                with self.assertRaises(ValueError):
                    driver.source_snapshot(hashlib.sha256(raw).hexdigest())

    def test_source_manifest_rejects_extra_import_closure_duplicate_keys_and_boolean_sizes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve(); here, data, value = source_fixture(root)
            variants = []
            extra = copy.deepcopy(value); extra["frozenSources"]["infra/cloud-lakehouse-restart/trino_lifecycle.py"] = dict(bytes=1, sha256="a"*64); variants.append(json.dumps(extra).encode())
            boolean = copy.deepcopy(value); boolean["schemaVersion"] = True; variants.append(json.dumps(boolean).encode())
            size = copy.deepcopy(value); size["files"]["README.ko.md"]["bytes"] = True; variants.append(json.dumps(size).encode())
            variants.append(b'{"schemaVersion":1,"schemaVersion":1}')
            with patch.object(driver, "HERE", here), patch.object(driver, "REPO", root), \
                 patch.object(driver, "FROZEN_MANIFEST", value["frozenRuntimeManifestSha256"]), \
                 patch.object(driver, "RESTART_MANIFEST_SHA256", value["frozenTrinoRestartManifestSha256"]), \
                 patch.object(driver, "regular_bytes", side_effect=lambda path: data[Path(path)]):
                for raw in variants:
                    data[here / "runtime-manifest.json"] = raw
                    with self.subTest(raw=raw[:30]), self.assertRaises(ValueError):
                        driver.source_snapshot(hashlib.sha256(raw).hexdigest())

    @unittest.skipUnless(hasattr(os, "O_NOFOLLOW"), "POSIX source-file guard runs in hosted Linux")
    def test_regular_source_reader_rejects_size_symlink_and_hardlink_alias(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "source.py"; path.write_bytes(b"actual")
            self.assertEqual(b"actual", driver.regular_bytes(path, 6))
            with self.assertRaises(ValueError): driver.regular_bytes(path, 5)
            link = Path(directory) / "symlink.py"; link.symlink_to(path)
            with self.assertRaises(ValueError): driver.regular_bytes(link)
            os.link(path, Path(directory) / "hardlink.py")
            with self.assertRaises(ValueError): driver.regular_bytes(path)

    def test_checked_module_never_executes_bytes_that_differ_from_verified_snapshot(self):
        with patch.object(driver, "regular_bytes", return_value=b"raise AssertionError('must not run')"):
            with self.assertRaises(ValueError):
                driver.checked_module(Path("/unused/fixture.py"), b"PURE=True\n", "pure_fixture")
        with patch.object(driver, "regular_bytes", return_value=b"PURE=True\n"):
            module = driver.checked_module(Path("/unused/fixture.py"), b"PURE=True\n", "pure_fixture")
            self.assertIs(module.PURE, True)

    def test_hosted_guard_rejects_pr_other_repo_attempt_and_implicit_execution(self):
        env = dict(GITHUB_ACTIONS="true", RUNNER_ENVIRONMENT="github-hosted", GITHUB_REPOSITORY="DevDooly/devdooly-platform-lab",
            GITHUB_EVENT_NAME="workflow_dispatch", GITHUB_REF="refs/heads/main", GITHUB_RUN_ATTEMPT="1", CLOUD_CATALOG_RESTART_OPT_IN="true")
        with patch.object(driver.sys, "platform", "linux"):
            driver.hosted(env)
            for key, value in (("GITHUB_EVENT_NAME", "pull_request"), ("GITHUB_REPOSITORY", "foreign/repo"),
                               ("GITHUB_REF", "refs/heads/feature"), ("GITHUB_RUN_ATTEMPT", "2"),
                               ("CLOUD_CATALOG_RESTART_OPT_IN", "false"), ("RUNNER_ENVIRONMENT", "self-hosted")):
                with self.subTest(key=key), self.assertRaises(ValueError):
                    driver.hosted(dict(env, **{key: value}))

    def test_catalog_projection_keeps_actual_restart_count_and_never_publishes_private_identity(self):
        for count in (2, 32):
            value = dict(catalog_result(), namespacePropertyRows=count)
            self.assertEqual(value, driver.catalog_public(value))
        for changes in ({"actualDockerRestartCount": 1}, {"actualDockerRestartCount": False}, {"actualExitCode": 143},
                        {"explicitStarts": True}, {"sameSystemIdentifier": False}, {"newPostmasterVerified": False},
                        {"namespacePropertyRows": 1}, {"namespacePropertyRows": 33}, {"namespacePropertyRows": True},
                        {"systemIdentifier": "private"}, {"stopSignalRequest": "SIGTERM"},
                        {"signalDeliveryDirectlyObserved": True}, {"trinoAbsentAtRestart": False}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                driver.catalog_public(dict(catalog_result(), **changes))

    def test_prepared_fixture_requires_stopped_spark_and_trino_not_even_created(self):
        base = [dict(role="postgres", running=True, oom=False), dict(role="garage", running=True, oom=False),
                dict(role="spark", running=False, oom=False, exitCode=0)]
        class Trial:
            def normal_exit(self, role, row):
                if row["running"] or row["exitCode"] != 0 or row["oom"]: raise ValueError("not stopped")
            def snapshot_chain(self, rows, count): self.chain = count
            def files(self, rows, count): pass
        trial = Trial()
        spark = dict(passed=True, oldWarehouseObjects=14, afterWarehouseObjects=20, snapshots=[], beforeFiles=[], afterFiles=[])
        attempt = SimpleNamespace(started_roles={"postgres", "garage", "spark"}, containers=lambda: copy.deepcopy(base))
        self.assertEqual(3, len(driver.prepared_fixture(trial, attempt, spark, {"normalSparkExit": True})))
        self.assertEqual(3, trial.chain)
        for values in ([*base, dict(role="trino", running=False, oom=False)],
                       [*base[:2], dict(role="spark", running=True, oom=False, exitCode=0)],
                       [*base[:2], dict(role="spark", running=False, oom=True, exitCode=0)]):
            attempt.containers = lambda: copy.deepcopy(values)
            with self.assertRaises(ValueError): driver.prepared_fixture(trial, attempt, spark, {"normalSparkExit": True})
        attempt.containers = lambda: copy.deepcopy(base)
        with self.assertRaises(ValueError):
            driver.prepared_fixture(trial, attempt, dict(spark, afterWarehouseObjects=19), {"normalSparkExit": True})

    def test_cleanup_does_not_adopt_or_stop_unbound_live_container(self):
        class Attempt:
            bound = {"postgres": {"id": "owned"}}
            safety_stop = False
            calls = []
            values = [dict(id="owned", running=True), dict(id="unbound", running=True)]
            def initializer(self): return None
            def containers(self): return copy.deepcopy(self.values)
            def command(self, args, timeout):
                self.calls.append(args)
                if args == ["docker", "stop", "--time=10", "owned"]: self.values[0]["running"] = False
        attempt = Attempt(); value = driver.stop_owned_resources(attempt)
        self.assertIs(attempt.safety_stop, True)
        self.assertEqual([["docker", "stop", "--time=10", "owned"]], attempt.calls)
        self.assertEqual(dict(initializerStopped=True, ownedBoundContainersStopped=False, unboundContainerObserved=True), value)

    def test_pass_requires_cleanup_source_tools_and_actual_clock_without_integer_truncation(self):
        cleanup = dict(initializerStopped=True, ownedBoundContainersStopped=True, unboundContainerObserved=False)
        self.assertTrue(driver.final_pass(True, True, True, cleanup, 600000, True))
        for elapsed, clock in ((600001, True), (600000, False), (True, True), (None, True), (-1, True)):
            self.assertFalse(driver.final_pass(True, True, True, cleanup, elapsed, clock))
        for changed in (dict(cleanup, initializerStopped=1), dict(cleanup, unboundContainerObserved=True), dict(cleanup, extra=False)):
            self.assertFalse(driver.final_pass(True, True, True, changed, 1, True))
        self.assertFalse(driver.final_pass(True, False, True, cleanup, 1, True))
        self.assertFalse(driver.final_pass(True, True, False, cleanup, 1, True))

    def test_failure_diagnostic_exports_known_line_only_and_skips_guard_frame(self):
        try:
            driver.catalog_public(dict(catalog_result(), actualExitCode=137))
        except ValueError as error:
            error.args = ("PRIVATE_CANARY",)
            value = driver.failure_diagnostic(error, "CATALOG_RESTART", {driver.__file__: "driver"})
            self.assertEqual({"phase", "sourceFile", "sourceLine"}, set(value))
            self.assertEqual("driver", value["sourceFile"])
            self.assertIs(type(value["sourceLine"]), int)
            for private in ("PRIVATE_CANARY", "ValueError", driver.__file__): self.assertNotIn(private, json.dumps(value))
            self.assertIsNone(driver.failure_diagnostic(error, "PRIVATE_CANARY", {driver.__file__: "driver"}))
            self.assertIsNone(driver.failure_diagnostic(error, "CATALOG_RESTART", {}))

    def test_tool_signature_detects_bytes_drift_and_rejects_group_writable_binary(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "docker"; path.write_bytes(b"first"); path.chmod(0o555)
            before = driver.tool_signature(path)
            path.chmod(0o755); path.write_bytes(b"second"); path.chmod(0o555)
            self.assertNotEqual(before, driver.tool_signature(path))
            if os.name == "posix":
                path.chmod(0o775)
                with self.assertRaises(ValueError): driver.tool_signature(path)
            path.chmod(0o755)

    @unittest.skipUnless(os.name == "posix", "Hosted Linux plugin paths are POSIX absolute paths")
    def test_compose_plugin_metadata_must_be_unique_and_have_absolute_actual_path(self):
        class Attempt:
            def __init__(self, plugins): self.plugins = plugins
            def command(self, args, **kwargs): return SimpleNamespace(stdout=json.dumps(self.plugins).encode())
        with patch.object(driver.shutil, "which", return_value="/usr/bin/docker"), \
             patch.object(driver, "tool_signature", side_effect=lambda path: dict(path=str(path), sha256="a"*64)):
            value = driver.tool_snapshot(Attempt([dict(Name="compose", Path="/usr/bin/docker-compose")]))
            self.assertEqual("/usr/bin/docker-compose", value["compose"]["path"])
            for plugins in ([], [dict(Name="compose", Path="relative")],
                            [dict(Name="compose", Path="/a"), dict(Name="compose", Path="/b")]):
                with self.assertRaises(ValueError): driver.tool_snapshot(Attempt(plugins))


if __name__ == "__main__":
    unittest.main()
