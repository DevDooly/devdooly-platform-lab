"""Synthetic adapter boundaries; no Docker, /proc, original driver or network.

Only temporary proof files are written by the exclusive-save fake.
"""
import copy
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest

from trino_lifecycle import (BaseFacade, SURVIVORS, ZERO_STARTED, freeze_survivors,
                             handoff_context, validate_resumed_container, verify_survivors)

ROLE_NAMES = ("postgres", "garage", "spark", "trino", "reader")
CID = {role: str(index) * 64 for index, role in enumerate(ROLE_NAMES, 1)}
OLD_VOLUME, SURVIVOR_VOLUME, FRESH_VOLUME = "a" * 64, "b" * 64, "c" * 64


def state(role, running=False, pid=0, started="2026-10-18T01:00:00Z"):
    return {"id": CID[role], "role": role, "running": running, "exitCode": 0,
            "oom": False, "pid": pid, "startedAt": started}


def signature(role, volume=None):
    mounts = [] if volume is None else [json.dumps({"Type": "volume", "Driver": "local", "Name": volume})]
    return {"id": CID[role], "imageId": "synthetic-image-" + role, "config": {"role": role},
            "host": "{}", "mounts": mounts, "created": "synthetic-created"}


class FakeBase:
    def __init__(self):
        self.saved = []

    def save(self, path, value, mode=0o600):
        self.saved.append((path, copy.deepcopy(value), mode))
        with path.open("xb") as stream:
            stream.write(b"synthetic-private-proof")


class FakeAttempt:
    def __init__(self, root, project, inventory):
        self.root, self.project, self.sequence = root, project, 0
        self.inventory = copy.deepcopy(inventory)
        self.bound = {v["role"]: signature(v["role"], SURVIVOR_VOLUME if v["role"] == "postgres"
                                              else OLD_VOLUME if v["role"] == "trino" else None) for v in inventory}
        self.started_roles = set(self.bound)
        self.deadline = SimpleNamespace(started=1.25, remaining=lambda maximum, reserve: maximum)
        self.safety_stop = False
        self.desired = {"services": {role: {"image": "synthetic:" + role} for role in ROLE_NAMES}}
        self.identities = {role: "synthetic-image-" + role for role in ROLE_NAMES}
        self.image_volumes = {role: set() for role in ROLE_NAMES}
        self.prior_volumes = {"preexisting-named-volume"}
        self.initializer_intended, self.initializer_name = True, project + "-volume-init"
        self.initializer_identity_checks = {"syntheticScope": True, "syntheticLimits": True}
        self.init = {"id": "f" * 64, "running": False, "exitCode": 0, "oom": False}
        self.command_failures, self.command_failures_truncated = [], False
        self.last_command, self.trino_stop = None, None
        self.calls = []

    def containers(self):
        self.sequence += 1
        return copy.deepcopy(self.inventory)

    def initializer(self):
        self.sequence += 1
        return copy.deepcopy(self.init)

    def command(self, args, **kwargs):
        self.sequence += 1
        self.calls.append((list(args), dict(kwargs)))
        if args == ["docker", "rm", CID["trino"]]:
            self.inventory = [v for v in self.inventory if v["role"] != "trino"]
            return SimpleNamespace(returncode=0, stdout=b"", stderr=b"")
        if args == ["docker", "volume", "ls", "-q"]:
            return SimpleNamespace(returncode=0, stdout=(OLD_VOLUME + "\n" + SURVIVOR_VOLUME + "\n").encode())
        raise AssertionError("UNEXPECTED_SYNTHETIC_COMMAND")


class FakeTrial:
    def __init__(self, initial):
        self.initial, self.created = initial, []
        self.process_generation = 1

    def process_identity(self, pid, cid):
        return {"pid": pid, "startTicks": self.process_generation, "hostBootId": "synthetic-boot",
                "cgroupSha256": cid}

    def normal_exit(self, role, value, stop):
        if not (role == "trino" and value["running"] is False and value["oom"] is False
                and value["exitCode"] in (0, 143) and stop["requestReturnedZero"] is True
                and stop["cid"] == value["id"] and stop["startedAt"] == value["startedAt"]):
            raise ValueError("SYNTHETIC_NORMAL_STOP_REJECTED")

    def make_attempt(self, facade, root, project, images):
        value = FakeAttempt(root, project, self.initial.inventory)
        value.bound, value.started_roles, value.trino_stop = {}, set(), None
        self.created.append(value)
        return value


class LifecycleTest(unittest.TestCase):
    def setUp(self):
        self.temporary = TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root, self.base = Path(self.temporary.name), FakeBase()
        self.a = FakeAttempt(self.root, "synthetic-project", [state("postgres", True, 101),
            state("garage", True, 102), state("spark"), state("trino", True, 104)])
        self.trial = FakeTrial(self.a)
        self.images = {role: "synthetic:" + role for role in ROLE_NAMES}

    def stop_fixture(self):
        evidence = freeze_survivors(self.trial, self.a)
        old = next(v for v in self.a.inventory if v["role"] == "trino")
        self.a.trino_stop = {"cid": old["id"], "startedAt": old["startedAt"],
                            **self.trial.process_identity(old["pid"], old["id"]),
                            "requestReturnedZero": True}
        old.update(running=False, pid=0, exitCode=143)
        return evidence, copy.deepcopy(old)

    def handoff_fixture(self):
        evidence, stopped = self.stop_fixture()
        return handoff_context(self.trial, self.base, self.a, self.root, self.a.project,
                               self.images, evidence, stopped)

    def add_new_trino(self, current, volume=FRESH_VOLUME):
        value = state("trino", started=ZERO_STARTED)
        value["id"] = "e" * 64
        current.inventory.append(value)
        current.bound["trino"] = signature("trino", volume)
        current.bound["trino"]["id"] = value["id"]
        return current.containers()

    def test_handoff_preserves_survivors_clock_and_start_authority(self):
        before_bound = copy.deepcopy(self.a.bound)
        resumed, facade, handoff = self.handoff_fixture()
        self.assertEqual(self.a.bound, before_bound)
        self.assertIs(resumed.deadline, self.a.deadline)
        self.assertGreater(resumed.sequence, self.a.sequence)
        self.assertEqual(resumed.started_roles, SURVIVORS)
        self.assertEqual(resumed.prior_volumes, {OLD_VOLUME})
        self.assertEqual(resumed.inventory, [v for v in self.a.inventory])
        self.assertEqual([args for args, _ in self.a.calls],
                         [["docker", "rm", CID["trino"]], ["docker", "volume", "ls", "-q"]])
        self.assertEqual(facade.proof_root, self.root / "lifecycle-resumed")
        self.assertTrue(verify_survivors(self.trial, resumed, handoff, resumed.containers()))

    def test_role_or_stopped_spark_drift_rejects_before_removal(self):
        evidence, stopped = self.stop_fixture()
        spark = next(v for v in self.a.inventory if v["role"] == "spark")
        spark["startedAt"] = ZERO_STARTED
        with self.assertRaisesRegex(ValueError, "SPARK_SUCCESS_STATE"):
            handoff_context(self.trial, self.base, self.a, self.root, self.a.project,
                            self.images, evidence, stopped)
        self.assertEqual(self.a.calls, [])
        spark["startedAt"] = "2026-10-18T01:00:00Z"
        self.a.inventory.append(state("reader"))
        with self.assertRaisesRegex(ValueError, "FOUR_ROLE_HANDOFF"):
            handoff_context(self.trial, self.base, self.a, self.root, self.a.project,
                            self.images, evidence, stopped)
        self.assertEqual(self.trial.created, [])

    def test_unverified_stop_or_removal_never_creates_resumed_context(self):
        for case in ("unconfirmed-stop", "stop-cid-mismatch", "remove-nonzero", "remove-not-absent"):
            with self.subTest(case=case):
                root = self.root / case
                root.mkdir()
                initial = FakeAttempt(root, "synthetic-project", [state("postgres", True, 101),
                    state("garage", True, 102), state("spark"), state("trino", True, 104)])
                trial = FakeTrial(initial)
                evidence = freeze_survivors(trial, initial)
                old = next(v for v in initial.inventory if v["role"] == "trino")
                initial.trino_stop = {"cid": old["id"], "startedAt": old["startedAt"],
                                     **trial.process_identity(old["pid"], old["id"]),
                                     "requestReturnedZero": True}
                old.update(running=False, pid=0, exitCode=143)
                stopped = copy.deepcopy(old)
                if case == "unconfirmed-stop":
                    initial.trino_stop["requestReturnedZero"] = False
                elif case == "stop-cid-mismatch":
                    initial.trino_stop["cid"] = "d" * 64
                else:
                    original_command = initial.command

                    def failed_removal(args, **kwargs):
                        if args == ["docker", "rm", CID["trino"]]:
                            initial.sequence += 1
                            initial.calls.append((list(args), dict(kwargs)))
                            # Even rc0 does not establish actual absence.
                            return SimpleNamespace(returncode=1 if case == "remove-nonzero" else 0,
                                                   stdout=b"", stderr=b"")
                        return original_command(args, **kwargs)

                    initial.command = failed_removal
                with self.assertRaises(ValueError):
                    handoff_context(trial, self.base, initial, root, initial.project,
                                    self.images, evidence, stopped)
                self.assertEqual(trial.created, [])
                self.assertFalse((root / "lifecycle-resumed").exists())
                expected = [] if case in ("unconfirmed-stop", "stop-cid-mismatch") else [
                    ["docker", "rm", CID["trino"]]]
                self.assertEqual([args for args, _ in initial.calls], expected)

    def test_prestart_rejects_old_and_survivor_anonymous_volumes(self):
        resumed, _, handoff = self.handoff_fixture()
        values = self.add_new_trino(resumed)
        self.assertEqual(validate_resumed_container(resumed, handoff, values)["id"], "e" * 64)
        for volume in (OLD_VOLUME, SURVIVOR_VOLUME):
            with self.subTest(volume_kind="old" if volume == OLD_VOLUME else "survivor"):
                resumed.bound["trino"]["mounts"] = signature("trino", volume)["mounts"]
                with self.assertRaisesRegex(ValueError, "ANY_PRECREATE_ANONYMOUS_VOLUME"):
                    validate_resumed_container(resumed, handoff, values)
        self.assertNotIn("trino", resumed.started_roles)

    def test_prestart_rejects_reused_cid_or_already_started_replacement(self):
        resumed, _, handoff = self.handoff_fixture()
        values = self.add_new_trino(resumed)
        for field, changed in (("id", CID["trino"]), ("startedAt", "2026-10-18T02:00:00Z"), ("pid", True)):
            invalid = copy.deepcopy(values)
            next(v for v in invalid if v["role"] == "trino")[field] = changed
            with self.subTest(field=field), self.assertRaises(ValueError):
                validate_resumed_container(resumed, handoff, invalid)

    def test_later_process_or_initializer_drift_rejects(self):
        resumed, _, handoff = self.handoff_fixture()
        self.trial.process_generation += 1
        with self.assertRaisesRegex(ValueError, "PROCESS_IDENTITY_UNCHANGED"):
            verify_survivors(self.trial, resumed, handoff, resumed.containers())
        self.trial.process_generation -= 1
        resumed.init["id"] = "d" * 64
        with self.assertRaisesRegex(ValueError, "INITIALIZER_ACTUAL_IDENTITY_UNCHANGED"):
            verify_survivors(self.trial, resumed, handoff, resumed.containers())

    def test_facade_rejects_unknown_paths_and_delegates_exclusive_save(self):
        facade = BaseFacade(self.base, self.root, "lifecycle-initial")
        for path in (self.root / "compose.json", self.root / "trino.env",
                     self.root / "nested/../command-001.stdout", self.root / "proof/clock.json"):
            with self.subTest(leaf=path.name), self.assertRaisesRegex(ValueError, "FIXED_PRIVATE"):
                facade.save(path, b"synthetic")
        self.assertEqual(self.base.saved, [])
        path = self.root / "start-trino-intent.json"
        facade.save(path, {"synthetic": True})
        self.assertEqual(self.base.saved[0][0], self.root / "lifecycle-initial" / path.name)
        with self.assertRaises(FileExistsError):
            facade.save(path, {"synthetic": False})


if __name__ == "__main__":
    unittest.main()
