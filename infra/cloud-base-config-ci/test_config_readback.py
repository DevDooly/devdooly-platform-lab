"""Pure tests: pinned source imports and synthetic metadata; no command runs."""
import copy
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest import mock

HERE = Path(__file__).resolve().parent
REPO = Path(os.environ.get("PROBE_TEST_REPO", str(HERE.parents[1]))).resolve()
spec = importlib.util.spec_from_file_location("config_readback_under_test", HERE / "run_config_readback.py")
probe = importlib.util.module_from_spec(spec)
spec.loader.exec_module(probe)
PRIVATE = "SYNTHETIC_PRIVATE_TOKEN_7857"


class ConfigReadbackTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.base, cls.compose, cls.cloud, cls.codes = probe.dependencies(REPO)

    def attempt(self, root):
        project = "cloud-base-startup-" + "b" * 32
        images = {"postgres": self.base.POSTGRES, "garage": self.base.GARAGE, "spark": "spark-isolated-ci:" + "b" * 32,
                  "trino": self.cloud.TRINO, "reader": self.base.SPARK}
        attempt = self.cloud.make_attempt(self.base, root, project, images)
        attempt.probe_images = images
        attempt.desired = self.cloud.plan(self.compose.plan, images["spark"], self.base.SPARK)
        attempt.identities = {"postgres": "sha256:" + "a" * 64, "garage": "sha256:" + "c" * 64}
        attempt.image_volumes = {"postgres": set(), "garage": set()}
        return attempt

    def raw(self, attempt, role):
        desired = attempt.desired["services"][role]
        mounts = []
        for item in desired["volumes"]:
            pieces = item.split(":")
            if pieces[0].startswith("./"):
                mounts.append({"Type": "bind", "Source": str(attempt.root / pieces[0][2:]), "Destination": pieces[1], "RW": len(pieces) < 3 or pieces[2] != "ro"})
            else:
                mounts.append({"Type": "volume", "Name": attempt.project + "_" + pieces[0], "Driver": "local",
                               "Destination": pieces[1], "RW": True})
        return {"Id": ("d" if role == "postgres" else "e") * 64, "Image": attempt.identities[role], "Created": "2026-10-16T00:00:00Z",
            "Config": {"Image": attempt.probe_images[role], "Labels": {"com.docker.compose.project": attempt.project, "com.docker.compose.service": role},
                       "Cmd": desired.get("command", []), "Entrypoint": desired.get("entrypoint"), "User": desired.get("user", ""),
                       "Env": ["PRIVATE=" + PRIVATE]},
            "HostConfig": {"ReadonlyRootfs": True, "Privileged": False, "PortBindings": {}, "NetworkMode": attempt.project + "_trial",
                           "NanoCpus": 500000000, "Memory": 512*1024**2, "PidsLimit": 256,
                           "RestartPolicy": {"Name": "no"}, "Tmpfs": {value.split(":")[0]: "" for value in desired["tmpfs"]}},
            "Mounts": mounts, "RestartCount": 0, "NetworkSettings": {"Networks": {attempt.project + "_trial": {}}},
            "State": {"Error": "", "Status": "created", "Running": False, "ExitCode": 0, "OOMKilled": False, "Pid": 0, "StartedAt": "0001-01-01T00:00:00Z"}}

    def fake_inventory(self, attempt, fixtures, after_start=None):
        calls = []
        def command(args, timeout=60, sensitive=False, check=True):
            calls.append(list(args)); attempt.sequence += 1
            attempt.last_command = self.cloud.command_observation(attempt.sequence, attempt.command_stage, args, check)
            attempt.last_command.update(returnCode=0, outcome="RETURNED_ZERO")
            if args[:2] == ["docker", "ps"]:
                raw = ("\n".join(row["Id"] for row in fixtures.values()) + "\n").encode()
            elif args[:2] == ["docker", "inspect"]:
                raw = json.dumps([next(row for row in fixtures.values() if row["Id"] == args[2])]).encode()
            elif args[:3] == ["docker", "network", "inspect"]:
                raw = json.dumps([{"Internal": True, "Labels": {"com.docker.compose.project": attempt.project},
                                   "Containers": {row["Id"]: {} for row in fixtures.values()}}]).encode()
            elif args[:2] == ["docker", "start"] and len(args) == 3:
                row = next(row for row in fixtures.values() if row["Id"] == args[2])
                row["State"].update(Running=True, Status="running", Pid=1234, StartedAt="2026-10-16T01:00:00Z")
                if after_start: after_start(row)
                raw = b""
            else:
                raise AssertionError("A synthetic inventory must not execute another command")
            return subprocess.CompletedProcess(args, 0, raw, b"")
        attempt.command = command
        return calls

    def test_exact_valueerror_and_runtimeerror_guard_only_not_secret_text(self):
        known = "SAME_OWN_CONTAINER_FULL_CONFIGURATION"
        self.assertIn(known, self.codes)
        for error in (ValueError(known), RuntimeError(known)):
            self.assertEqual(probe.validation_code(error, self.codes), known)
        for error in (ValueError(PRIVATE), RuntimeError(PRIVATE), OSError(known), KeyError(known)):
            self.assertEqual(probe.validation_code(error, self.codes), "UNOBSERVED_VALIDATION_FAILURE")

    def test_complete_original_five_role_model_and_early_checks_are_unobserved(self):
        tag = "spark-isolated-ci:" + "b" * 32
        original = self.compose.plan(tag)
        frozen_copy = copy.deepcopy(original)
        desired = self.cloud.plan(self.compose.plan, tag, self.base.SPARK)
        self.assertEqual(original, frozen_copy)
        self.assertEqual(set(desired["services"]), {"postgres", "garage", "spark", "trino", "reader"})
        for role in ("postgres", "garage"):
            self.assertEqual(desired["services"][role], original["services"][role])
        self.assertEqual(desired["services"]["trino"]["env_file"], ["./trino.env"])
        self.assertEqual(desired["networks"], {"trial": {"internal": True}})
        self.assertFalse(any(probe.initial_checks().values()))
        self.assertFalse(any("depends_on" in item or "ports" in item for item in desired["services"].values()))

    def test_actual_frozen_mount_signature_drift_is_visible_but_still_rejected(self):
        attempt = self.attempt(Path("synthetic-private-root"))
        fixtures = {role: self.raw(attempt, role) for role in ("postgres", "garage")}
        calls = self.fake_inventory(attempt, fixtures)
        diagnostics = probe.Diagnostics(self.codes); diagnostics.install(attempt)
        self.assertEqual(len(attempt.containers()), 2)
        primary = diagnostics.failure("START_POSTGRES", ValueError("OWN_FRESH_COMMAND_FAILED_NO_RETRY"))
        fixtures["postgres"]["Mounts"].append({"Type": "tmpfs", "Destination": "/tmp", "RW": True})
        fixtures["postgres"]["State"].update(Error="OCI runtime permission denied " + PRIVATE, Status="exited", ExitCode=1)
        attempt.command_stage = "CLEANUP_CONTAINERS"
        with self.assertRaisesRegex(ValueError, "^SAME_OWN_CONTAINER_FULL_CONFIGURATION$") as caught:
            attempt.containers()
        diagnostics.failure(attempt.command_stage, caught.exception)
        value = diagnostics.states["postgres"]
        self.assertTrue(value["signatureDifferences"]["mountsChanged"])
        self.assertFalse(value["signatureDifferences"]["configChanged"])
        self.assertTrue(value["identityBound"])
        self.assertIn("OCI_RUNTIME_SIGNATURE", value["stateErrorSignatures"])
        self.assertEqual(primary, diagnostics.validations[0])
        self.assertEqual(diagnostics.validations[1]["validationFailureCode"], "SAME_OWN_CONTAINER_FULL_CONFIGURATION")
        self.assertFalse(any(command[:2] == ["docker", "stop"] for command in calls))
        self.assertNotIn(PRIVATE, json.dumps({"states": diagnostics.states, "failures": diagnostics.validations, "reasons": diagnostics.reasons, "observations": diagnostics.observation_failures}))

    def test_foreign_owner_and_changed_pids_fail_original_guard_before_stop(self):
        attempt = self.attempt(Path("synthetic-private-root"))
        fixtures = {role: self.raw(attempt, role) for role in ("postgres", "garage")}
        calls = self.fake_inventory(attempt, fixtures)
        attempt.containers()
        fixtures["postgres"]["HostConfig"]["PidsLimit"] = 512
        with self.assertRaisesRegex(ValueError, "EXACT_ROLE_CPU_MEMORY_PID_LIMITS"):
            attempt.containers()
        fixtures["postgres"]["HostConfig"]["PidsLimit"] = 256
        fixtures["postgres"]["Config"]["Labels"]["com.docker.compose.project"] = "foreign"
        with self.assertRaisesRegex(ValueError, "EXACT_OWN_ROLE_AND_FULL_CID"):
            attempt.containers()
        self.assertFalse(any(command[:2] == ["docker", "stop"] for command in calls))

    def test_timeout_cmd_args_and_private_stderr_cannot_escape_projection(self):
        with tempfile.TemporaryDirectory() as folder:
            attempt = self.attempt(Path(folder))
            diagnostics = probe.Diagnostics(self.codes); diagnostics.install(attempt)
            argv = [*attempt.compose, "start", "postgres"]
            failure = subprocess.TimeoutExpired([*argv, PRIVATE], 3, output=PRIVATE.encode(), stderr=("permission denied " + PRIVATE).encode())
            def save(path, value, mode=0o600):
                raw = value if type(value) is bytes else json.dumps(value).encode()
                with path.open("xb") as stream: stream.write(raw)
            with mock.patch.object(self.base, "save", side_effect=save), mock.patch.object(self.cloud.subprocess, "run", side_effect=failure) as run:
                with self.assertRaises(subprocess.TimeoutExpired): attempt.command(argv)
            public = {"commands": attempt.command_diagnostics(), "reasons": diagnostics.reasons,
                      "failure": diagnostics.failure("START_POSTGRES", failure)}
            encoded = json.dumps(public)
            self.assertEqual(run.call_count, 1)
            self.assertNotIn(PRIVATE, encoded)
            self.assertNotIn(str(attempt.root), encoded)
            self.assertEqual(diagnostics.reasons[0]["stderrSignatures"], ["PERMISSION_DENIED_SIGNATURE"])
            self.assertTrue(diagnostics.reasons[0]["timedOut"])

    def test_checkfalse_nonzero_remains_nonfatal_checked_failure_is_preserved(self):
        with tempfile.TemporaryDirectory() as folder:
            attempt = self.attempt(Path(folder))
            diagnostics = probe.Diagnostics(self.codes); diagnostics.install(attempt)
            def save(path, value, mode=0o600):
                with path.open("xb") as stream: stream.write(value if type(value) is bytes else json.dumps(value).encode())
            response = subprocess.CompletedProcess([PRIVATE], 1, b"", ("permission denied " + PRIVATE).encode())
            with mock.patch.object(self.base, "save", side_effect=save), mock.patch.object(self.cloud.subprocess, "run", return_value=response):
                attempt.cli("exec", "-T", "postgres", "pg_isready", check=False)
                self.assertEqual(attempt.command_diagnostics()["failures"], [])
                with self.assertRaisesRegex(ValueError, "OWN_FRESH_COMMAND_FAILED_NO_RETRY"):
                    attempt.cli("start", "postgres")
            self.assertFalse(diagnostics.reasons[0]["checkRequested"])
            self.assertTrue(diagnostics.reasons[1]["checkRequested"])
            self.assertEqual(len(attempt.command_diagnostics()["failures"]), 1)
            self.assertNotIn(PRIVATE, json.dumps(diagnostics.reasons))

    def test_heavy_create_or_start_rejected_before_subprocess_and_bad_diagnostic_does_not_relax_guard(self):
        attempt = self.attempt(Path("synthetic-private-root"))
        called = []
        def command(args, **kwargs):
            called.append(args)
            return subprocess.CompletedProcess(args, 0, b"not-json", b"")
        attempt.command = command
        diagnostics = probe.Diagnostics(self.codes); diagnostics.install(attempt)
        for action in ("create", "start"):
            for role in ("spark", "trino", "reader"):
                with self.assertRaisesRegex(RuntimeError, "NO_HEAVY_START_OR_CREATE"):
                    attempt.command([*attempt.compose, action, role])
        self.assertEqual(called, [])
        result = attempt.command(["docker", "inspect", "d" * 64])
        self.assertEqual(result.stdout, b"not-json")
        self.assertEqual(len(diagnostics.observation_failures), 1)

    def test_strict_version_and_fixed_clock_never_reset_after_expiry(self):
        for value in (b"29.3.1\n", b"v5.5.1\n", b"29.1.3-ubuntu.1\n"):
            self.assertTrue(probe.version(value))
        for value in (("1.2\n" + PRIVATE).encode(), PRIVATE.encode(), b"1.2\x00", b"\xff"):
            with self.assertRaises((RuntimeError, UnicodeError)):
                probe.version(value)
        now = [10]
        deadline = probe.ProbeDeadline(10, lambda: now[0])
        self.assertEqual(deadline.remaining(60, 60), 60)
        now[0] = 191
        for _ in range(2):
            with self.assertRaisesRegex(RuntimeError, "STARTUP_PROBE_DEADLINE"):
                deadline.remaining(1)


    def test_canonical_order_only_readback_matches_current_guard_without_normalizing_raw(self):
        attempt = self.attempt(Path("synthetic-private-root"))
        fixtures = {role: self.raw(attempt, role) for role in ("postgres", "garage")}
        calls = self.fake_inventory(attempt, fixtures)
        diagnostics = probe.Diagnostics(self.codes); diagnostics.install(attempt)
        attempt.containers()
        before = copy.deepcopy(fixtures["postgres"]["Mounts"])
        fixtures["postgres"]["Mounts"].reverse()
        self.assertEqual(len(attempt.containers()), 2)
        observed = diagnostics.states["postgres"]
        self.assertFalse(observed["signatureDifferences"]["mountsChanged"])
        self.assertTrue(observed["mountOrderOnlyChanged"])
        self.assertFalse(observed["mountContentChanged"])
        self.assertEqual(fixtures["postgres"]["Mounts"], list(reversed(before)))
        self.assertEqual(probe.signature(fixtures["postgres"])["mounts"], self.cloud.canonical_mounts(before))
        self.assertFalse(any(command[:2] == ["docker", "start"] for command in calls))

    def test_mount_comparison_keeps_unknown_fields_duplicate_members_and_json_types(self):
        previous = [{"Source": "/private/" + PRIVATE, "Destination": "/data", "RW": True,
                     "FutureField": {"unknown": [1, {"token": PRIVATE}]}},
                    {"Destination": "/other", "RW": False, "Source": "/private/second"}]
        same = [{key: member[key] for key in reversed(member)} for member in previous]
        self.assertEqual(probe.mount_differences(previous, same), {"mountOrderOnlyChanged": False, "mountContentChanged": False})
        self.assertEqual(probe.mount_differences(previous, list(reversed(same))), {"mountOrderOnlyChanged": True, "mountContentChanged": False})
        changed = []
        missing = copy.deepcopy(previous); del missing[0]["FutureField"]; changed.append(missing)
        added = copy.deepcopy(previous); added[0]["UnknownExtra"] = PRIVATE; changed.append(added)
        nested = copy.deepcopy(previous); nested[0]["FutureField"]["unknown"][1]["token"] += "x"; changed.append(nested)
        typed = copy.deepcopy(previous); typed[0]["RW"] = 1; changed.append(typed)
        changed.extend([previous[:1], previous + [copy.deepcopy(previous[0])]])
        for value in changed:
            result = probe.mount_differences(previous, value)
            self.assertEqual(result, {"mountOrderOnlyChanged": False, "mountContentChanged": True})
            self.assertNotIn(PRIVATE, json.dumps(result))
            self.assertNotIn("FutureField", json.dumps(result))

    def test_mount_diagnostics_unbound_are_null_and_existing_content_change_is_distinct(self):
        self.assertEqual(probe.mount_differences(None, []), {"mountOrderOnlyChanged": None, "mountContentChanged": None})
        attempt = self.attempt(Path("synthetic-private-root"))
        fixtures = {role: self.raw(attempt, role) for role in ("postgres", "garage")}
        self.fake_inventory(attempt, fixtures)
        diagnostics = probe.Diagnostics(self.codes); diagnostics.install(attempt)
        attempt.containers()
        self.assertIsNone(diagnostics.states["garage"]["mountOrderOnlyChanged"])
        self.assertIsNone(diagnostics.states["garage"]["mountContentChanged"])
        fixtures["postgres"]["Mounts"][0]["RW"] = not fixtures["postgres"]["Mounts"][0]["RW"]
        with self.assertRaisesRegex(ValueError, "ACTUAL_MOUNT_TYPE_AND_RO_RW"):
            attempt.containers()
        observed = diagnostics.states["postgres"]
        self.assertFalse(observed["mountOrderOnlyChanged"])
        self.assertTrue(observed["mountContentChanged"])

    def test_after_start_mac_change_is_observed_but_original_guard_still_rejects(self):
        attempt = self.attempt(Path("synthetic-private-root"))
        fixtures = {role: self.raw(attempt, role) for role in ("postgres", "garage")}
        def changed(row): row["Config"]["MacAddress"] = "02:00:00:PRIVATE:VALUE"
        calls = self.fake_inventory(attempt, fixtures, changed)
        diagnostics = probe.Diagnostics(self.codes); diagnostics.install(attempt)
        attempt.deadline = probe.ProbeDeadline(probe.time.monotonic())
        with mock.patch.object(self.base, "save") as save:
            attempt.start("postgres")
        save.assert_called_once_with(attempt.root / "start-postgres-intent.json", {"role": "postgres", "automaticRetry": False})
        with self.assertRaisesRegex(ValueError, "^SAME_OWN_CONTAINER_FULL_CONFIGURATION$"):
            attempt.start("garage")
        observed = diagnostics.states["postgres"]
        self.assertTrue(observed["signatureDifferences"]["configChanged"])
        self.assertTrue(observed["configKnownKeyChanged"]["MacAddress"])
        self.assertFalse(observed["configUnknownKeysChanged"])
        self.assertFalse(any(observed["hostConfigKnownKeyChanged"].values()))
        self.assertEqual([args for args in calls if args[:2] == ["docker", "start"]], [["docker", "start", fixtures["postgres"]["Id"]]])
        self.assertEqual(attempt.started_roles, {"postgres"})
        self.assertFalse(any(args[:2] == ["docker", "stop"] for args in calls))
        self.assertNotIn("02:00:00:PRIVATE:VALUE", json.dumps(observed))

    def test_fixed_key_projection_retains_missing_null_types_and_unknown_content_without_names(self):
        current = {"Env": ["TOKEN=" + PRIVATE], "MacAddress": PRIVATE, PRIVATE: {"nested": PRIVATE}}
        known, unknown = probe.known_key_differences(None, current, probe.CONFIG_KEYS)
        self.assertTrue(all(value is None for value in known.values())); self.assertIsNone(unknown)
        before = copy.deepcopy(current)
        current["Env"].append("PASSWORD=" + PRIVATE)
        current[PRIVATE]["nested"] += "changed"
        known, unknown = probe.known_key_differences(before, current, probe.CONFIG_KEYS)
        self.assertTrue(known["Env"]); self.assertFalse(known["MacAddress"]); self.assertTrue(unknown)
        encoded = json.dumps({"known": known, "unknown": unknown})
        self.assertNotIn(PRIVATE, encoded)
        known, unknown = probe.known_key_differences({"Init": None, "Privileged": True}, {"Privileged": 1}, probe.HOST_KEYS)
        self.assertTrue(known["Init"]); self.assertTrue(known["Privileged"]); self.assertFalse(unknown)

    def test_host_known_unknown_diff_does_not_relax_original_configuration_or_resource_guard(self):
        for key, value, code in (("SecurityOpt", [PRIVATE], "SAME_OWN_CONTAINER_FULL_CONFIGURATION"),
                                 (PRIVATE, {"credential": PRIVATE}, "SAME_OWN_CONTAINER_FULL_CONFIGURATION"),
                                 ("Memory", 1, "EXACT_ROLE_CPU_MEMORY_PID_LIMITS")):
            attempt = self.attempt(Path("synthetic-private-root"))
            fixtures = {role: self.raw(attempt, role) for role in ("postgres", "garage")}
            calls = self.fake_inventory(attempt, fixtures)
            diagnostics = probe.Diagnostics(self.codes); diagnostics.install(attempt)
            attempt.containers()
            fixtures["postgres"]["HostConfig"][key] = value
            with self.assertRaisesRegex(ValueError, "^" + code + "$" ): attempt.containers()
            observed = diagnostics.states["postgres"]
            self.assertTrue(observed["signatureDifferences"]["hostChanged"])
            if key in probe.HOST_KEYS: self.assertTrue(observed["hostConfigKnownKeyChanged"][key])
            else: self.assertTrue(observed["hostConfigUnknownKeysChanged"])
            self.assertNotIn(PRIVATE, json.dumps(observed))
            self.assertFalse(any(args[:2] == ["docker", "start"] or args[:2] == ["docker", "stop"] for args in calls))

    def test_full_docker_28_host_fields_include_embedded_resources_but_do_not_relax_guard(self):
        # Public API field names from Docker v28.0.4 hostconfig.go: direct HostConfig
        # plus its embedded Resources, with explicit JSON aliases (Cpu*, NanoCpus, Dns*).
        direct = "Binds ContainerIDFile LogConfig NetworkMode PortBindings RestartPolicy AutoRemove VolumeDriver VolumesFrom ConsoleSize Annotations CapAdd CapDrop CgroupnsMode Dns DnsOptions DnsSearch ExtraHosts GroupAdd IpcMode Cgroup Links OomScoreAdj PidMode Privileged PublishAllPorts ReadonlyRootfs SecurityOpt StorageOpt Tmpfs UTSMode UsernsMode ShmSize Sysctls Runtime Isolation Mounts MaskedPaths ReadonlyPaths Init".split()
        resources = "CpuShares Memory NanoCpus CgroupParent BlkioWeight BlkioWeightDevice BlkioDeviceReadBps BlkioDeviceWriteBps BlkioDeviceReadIOps BlkioDeviceWriteIOps CpuPeriod CpuQuota CpuRealtimePeriod CpuRealtimeRuntime CpusetCpus CpusetMems Devices DeviceCgroupRules DeviceRequests KernelMemory KernelMemoryTCP MemoryReservation MemorySwap MemorySwappiness OomKillDisable PidsLimit Ulimits CpuCount CpuPercent IOMaximumIOps IOMaximumBandwidth".split()
        self.assertEqual(len(direct), 40); self.assertEqual(len(resources), 31)
        self.assertEqual(probe.HOST_KEYS, tuple(direct + resources))
        self.assertEqual(len(set(probe.HOST_KEYS)), 71)
        for key in probe.HOST_KEYS:
            changes, unknown = probe.known_key_differences({}, {key: {PRIVATE: [PRIVATE, None, 1, True]}}, probe.HOST_KEYS)
            self.assertEqual([name for name, changed in changes.items() if changed], [key])
            self.assertFalse(unknown); self.assertNotIn(PRIVATE, json.dumps(changes))
        for key, value in (("Ulimits", [{"Name": PRIVATE, "Soft": 1, "Hard": 1}]),
                           ("CgroupParent", PRIVATE), ("OomKillDisable", True), ("Sysctls", {PRIVATE: PRIVATE})):
            attempt = self.attempt(Path("synthetic-private-root"))
            fixtures = {role: self.raw(attempt, role) for role in ("postgres", "garage")}
            calls = self.fake_inventory(attempt, fixtures)
            diagnostics = probe.Diagnostics(self.codes); diagnostics.install(attempt)
            attempt.containers()
            fixtures["postgres"]["HostConfig"][key] = value
            with self.assertRaisesRegex(ValueError, "^SAME_OWN_CONTAINER_FULL_CONFIGURATION$"):
                attempt.containers()
            observed = diagnostics.states["postgres"]
            self.assertTrue(observed["hostConfigKnownKeyChanged"][key])
            self.assertFalse(observed["hostConfigUnknownKeysChanged"])
            self.assertTrue(observed["signatureDifferences"]["hostChanged"])
            self.assertNotIn(PRIVATE, json.dumps(observed))
            self.assertFalse(any(args[:2] in (["docker", "start"], ["docker", "stop"]) for args in calls))

    def test_direct_start_unknown_or_heavy_cid_is_rejected_before_command(self):
        attempt = self.attempt(Path("synthetic-private-root")); calls = []
        attempt.command = lambda args, **kwargs: calls.append(args)
        diagnostics = probe.Diagnostics(self.codes); diagnostics.install(attempt)
        attempt.bound = {"trino": {"id": "f"*64}}
        for cid in ("f"*64, "a"*64, PRIVATE):
            with self.assertRaisesRegex(RuntimeError, "^NO_HEAVY_START_OR_CREATE$"):
                attempt.command(["docker", "start", cid])
        self.assertEqual(calls, [])


if __name__ == "__main__":
    unittest.main()
