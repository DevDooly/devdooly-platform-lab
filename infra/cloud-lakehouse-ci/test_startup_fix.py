"""Pure whole-mount and verified-CID startup regressions; no command executes."""
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import types
import unittest
from unittest.mock import Mock, patch

import contract as c
import compose_trial9
import run_trial9 as runner

HERE = Path(__file__).resolve().parent
PRIVATE = "SYNTHETIC_PRIVATE_MOUNT_VALUE_7191"


class StartupFixTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        source = HERE.parents[3] / "platform-spark-pid-budget-20261016/public/infra/spark-ci/compose_plan.py"
        if not source.exists(): source = HERE.parent / "spark-ci/compose_plan.py"
        raw = source.read_bytes()
        if hashlib.sha256(raw).hexdigest() != "fcaa911c8dcb9c6b56821ed3ff40d71c282658c8f5beb88200bff07c25336ee5":
            raise AssertionError("Exact frozen pure Compose source required")
        spec = importlib.util.spec_from_file_location("fixed_start_base_compose", source)
        cls.compose = importlib.util.module_from_spec(spec); spec.loader.exec_module(cls.compose)

    def engine(self):
        class BaseAttempt:
            def __init__(self, root, project): self.root, self.project, self.sequence = root, project, 0
        saved, calls = [], []
        base = types.SimpleNamespace(Attempt=BaseAttempt, save=lambda path, value: saved.append((path, value)))
        project = "synthetic-fixed-start"
        images = {"postgres": self.compose.POSTGRES, "garage": self.compose.GARAGE, "spark": "spark-isolated-ci:"+"a"*32,
                  "trino": c.TRINO, "reader": self.compose.SPARK}
        attempt = runner.make_attempt(base, Path("private-fixture"), project, images)
        attempt.deadline = c.Deadline(0, lambda: 0)
        attempt.desired = compose_trial9.plan(self.compose.plan, images["spark"], self.compose.SPARK)
        attempt.identities = {role: "sha256:" + str(index)*64 for index, role in enumerate(images, 1)}
        attempt.image_volumes = {role: set() for role in images}
        fixtures = {}
        for index, role in enumerate(images, 1):
            desired = attempt.desired["services"][role]
            mounts = []
            for value in desired["volumes"]:
                items = value.split(":")
                common = {"Destination": items[1], "RW": len(items) < 3 or items[2] != "ro"}
                if items[0].startswith("./"):
                    mounts.append({**common, "Type": "bind", "Source": str(attempt.root/items[0][2:])})
                else:
                    mounts.append({**common, "Type": "volume", "Name": project+"_"+items[0], "Driver": "local"})
            cpu, memory, pids = runner.ROLES[role]
            fixtures[role] = {"Id": str(index)*64, "Image": attempt.identities[role], "Created": "fixed-created",
                "Config": {"Image": images[role], "Labels": {"com.docker.compose.project": project, "com.docker.compose.service": role},
                           "Cmd": desired.get("command", []), "Entrypoint": desired.get("entrypoint"), "User": desired.get("user", ""), "Env": [PRIVATE]},
                "HostConfig": {"ReadonlyRootfs": True, "Privileged": False, "PortBindings": {}, "NetworkMode": project+"_trial",
                    "NanoCpus": cpu, "Memory": memory, "PidsLimit": pids, "OomKillDisable": False, "RestartCount": 0, "RestartPolicy": {"Name": "no"},
                    "Tmpfs": {value.split(":")[0]: "" for value in desired["tmpfs"]}},
                "Mounts": mounts, "RestartCount": 0, "NetworkSettings": {"Networks": {project+"_trial": {}}},
                "State": {"Running": False, "ExitCode": 0, "OOMKilled": False, "Pid": 0, "StartedAt": "0001-01-01T00:00:00Z"}}
        def command(args, **kwargs):
            calls.append(list(args))
            if args[:2] == ["docker", "ps"]:
                raw = ("\n".join(row["Id"] for row in fixtures.values())+"\n").encode()
            elif args[:2] == ["docker", "inspect"]:
                raw = json.dumps([next(row for row in fixtures.values() if row["Id"] == args[2])]).encode()
            elif args[:3] == ["docker", "network", "inspect"]:
                raw = json.dumps([{"Internal": True, "Labels": {"com.docker.compose.project": project}, "Containers": {row["Id"]: {} for row in fixtures.values()}}]).encode()
            elif args[:2] == ["docker", "start"]:
                row = next(row for row in fixtures.values() if row["Id"] == args[2])
                row["State"].update(Running=True, Pid=100+int(args[2][0]), StartedAt="own-started-"+args[2][0])
                raw = (args[2]+"\n").encode()
            else: raise AssertionError("No other synthetic command permitted")
            return subprocess.CompletedProcess(args, 0, raw, b"")
        attempt.command = command
        return attempt, fixtures, calls, saved

    def test_whole_member_order_is_stable_types_duplicates_and_unknown_fields_retained(self):
        values = [{"Source": PRIVATE, "RW": True, "Future": {"nested": [1, False]}}, {"Destination": "/data"}]
        self.assertEqual(runner.canonical_mounts(values), runner.canonical_mounts(list(reversed(values))))
        for change in (values+[copy.deepcopy(values[0])], values[:1], [{**values[0], "RW": 1}, values[1]],
                       [{**values[0], "Other": PRIVATE}, values[1]], [{**values[0], "Future": {"nested": [1, True]}}, values[1]]):
            self.assertNotEqual(runner.canonical_mounts(values), runner.canonical_mounts(change))
        with self.assertRaises(ValueError): runner.canonical_mounts([{"value": float("nan")}])
        attempt, fixtures, calls, saved = self.engine()
        attempt.containers()
        for row in fixtures.values(): row["Mounts"].reverse()
        self.assertEqual(len(attempt.containers()), 5)
        self.assertFalse(any(args[:2] in (["docker", "start"], ["docker", "stop"]) for args in calls))

    def test_content_owner_source_cid_ro_and_limits_drift_rejected_before_mutation(self):
        mutations = (
            lambda row: row["Mounts"][0].__setitem__("Source", "/foreign"),
            lambda row: row["Mounts"][0].__setitem__("RW", not row["Mounts"][0]["RW"]),
            lambda row: row["Mounts"][0].__setitem__("UnknownMember", {"value": PRIVATE}),
            lambda row: row["Mounts"].append(copy.deepcopy(row["Mounts"][0])),
            lambda row: row["Config"]["Labels"].__setitem__("com.docker.compose.project", "foreign"),
            lambda row: row.__setitem__("Id", "f"*64),
            lambda row: row["Config"].__setitem__("Image", "foreign-image"),
            lambda row: row["HostConfig"].__setitem__("ReadonlyRootfs", False),
            lambda row: row["HostConfig"].__setitem__("PidsLimit", 999),
            lambda row: row["State"].__setitem__("Pid", 456),
            lambda row: row["State"].__setitem__("StartedAt", "external-start"),
            lambda row: row["State"].__setitem__("Running", True),
        )
        for mutate in mutations:
            attempt, fixtures, calls, saved = self.engine()
            attempt.containers(); mutate(fixtures["postgres"])
            with self.assertRaises(ValueError): attempt.start("postgres")
            self.assertFalse(any(args[:2] in (["docker", "start"], ["docker", "stop"]) for args in calls))
            self.assertEqual(saved, [])
        # The actual pre-stop semantic/config guard also rejects content drift.
        attempt, fixtures, calls, saved = self.engine(); attempt.containers()
        fixtures["garage"]["Mounts"][0]["UnknownMember"] = PRIVATE
        with self.assertRaisesRegex(ValueError, "SAME_OWN_CONTAINER_FULL_CONFIGURATION"):
            attempt.containers()
        self.assertFalse(any(args[:2] == ["docker", "stop"] for args in calls))

    def test_all_five_roles_start_only_exact_bound_cid_once_with_original_heavy_gates(self):
        attempt, fixtures, calls, saved = self.engine()
        for role in ("postgres", "garage", "spark"):
            attempt.start(role)
            with self.assertRaises(ValueError): attempt.start(role)
        with self.assertRaises(ValueError): attempt.start("trino")
        with self.assertRaises(ValueError): attempt.start("reader")
        fixtures["spark"]["State"].update(Running=False, Pid=0, ExitCode=0)
        attempt.start("trino")
        with self.assertRaises(ValueError): attempt.start("reader")
        fixtures["trino"]["State"].update(Running=False, Pid=0, ExitCode=143)
        attempt.trino_stop = {"cid": fixtures["trino"]["Id"], "startedAt": fixtures["trino"]["State"]["StartedAt"],
                             "requestReturnedZero": True, "signalScope": "CONFIGURED_OR_DEFAULT_SIGTERM"}
        attempt.start("reader")
        for role in fixtures:
            with self.assertRaises(ValueError): attempt.start(role)
        starts = [args for args in calls if args[:2] == ["docker", "start"]]
        self.assertEqual(starts, [["docker", "start", fixtures[role]["Id"]] for role in fixtures])
        self.assertFalse(any(args[:2] == ["docker", "compose"] for args in calls))
        self.assertEqual(len(saved), 5)

    def test_existing_normal_trino_stop_rejects_pid_cid_and_start_ticks_drift(self):
        before = {"role": "trino", "id": "a"*64, "running": True, "oom": False, "pid": 123, "startedAt": "fixed"}
        identity = {"pid": 123, "startTicks": 456, "hostBootId": "boot", "cgroupSha256": "b"*64}
        for current, after_identity in (({**before, "id": "c"*64}, identity), ({**before, "pid": 124}, identity),
                                        (before, {**identity, "startTicks": 457})):
            attempt = types.SimpleNamespace(containers=Mock(side_effect=[[before], [current]]), command=Mock())
            base = types.SimpleNamespace(save=Mock())
            with patch.object(runner, "process_identity", side_effect=[identity, after_identity]):
                with self.assertRaisesRegex(ValueError, "SAME_TRINO_CID_PID_BEFORE_STOP"):
                    runner.stop_normal_trino(attempt, base, Path("unused"))
            attempt.command.assert_not_called(); base.save.assert_not_called()


if __name__ == "__main__": unittest.main()
