"""Pure actual-guard regressions; no Docker, network, SQL or workload executes."""
import copy
import json
from pathlib import Path
import subprocess
import types
import unittest
from unittest.mock import Mock, patch

import run_trial9 as runner
import test_startup_fix as fixture

PRIVATE = "SYNTHETIC_PRIVATE_HOST_VALUE_4319"


class EnabledOomTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        fixture.StartupFixTests.setUpClass()

    def engine(self):
        return fixture.StartupFixTests().engine()

    def test_only_present_null_or_exact_false_is_canonicalized_without_mutation(self):
        host = {"OomKillDisable": None, "Unknown": {PRIVATE: [True, 1, 1.0, None]}, "Memory": 123}
        before = copy.deepcopy(host)
        self.assertEqual(runner.canonical_host(host), runner.canonical_host({**host, "OomKillDisable": False}))
        self.assertEqual(host, before)
        self.assertIsNone(host["OomKillDisable"])
        self.assertEqual(json.loads(runner.canonical_host(host))["Unknown"], host["Unknown"])
        for bad in (True, 0, 1, "false", "", [], {}, 0.0):
            with self.assertRaisesRegex(ValueError, "^PRESENT_ENABLED_OOM_KILLER_REPRESENTATION_REQUIRED$"):
                runner.canonical_host({**host, "OomKillDisable": bad})
        with self.assertRaisesRegex(ValueError, "^PRESENT_ENABLED_OOM_KILLER_REPRESENTATION_REQUIRED$"):
            runner.canonical_host({"Memory": 123})
        for changed in ({**host, "Memory": 124}, {**host, "Memory": 123.0},
                        {**host, "Extra": PRIVATE}, {"OomKillDisable": None, "Memory": 123},
                        {**host, "Unknown": {PRIVATE: [True, 1, 1, None]}},
                        {**host, "Unknown": {PRIVATE: [1, True, 1.0, None]}}):
            self.assertNotEqual(runner.canonical_host(host), runner.canonical_host(changed))

    def test_all_roles_created_and_started_null_false_then_exact_normal_stop_remain_guarded(self):
        for representation in (None, False):
            attempt, rows, _, _ = self.engine()
            for row in rows.values(): row["HostConfig"]["OomKillDisable"] = representation
            self.assertEqual(len(attempt.containers()), 5)
        attempt, rows, calls, saved = self.engine()
        for role in ("postgres", "garage", "spark"):
            attempt.start(role)
            rows[role]["HostConfig"]["OomKillDisable"] = None
            self.assertEqual(len(attempt.containers()), 5)
        rows["spark"]["State"].update(Running=False, Pid=0, ExitCode=0)
        attempt.start("trino"); rows["trino"]["HostConfig"]["OomKillDisable"] = None
        original_command = attempt.command
        def command(args, **kwargs):
            if args[:3] == ["docker", "stop", "--time=30"]:
                self.assertEqual(args[3], rows["trino"]["Id"])
                calls.append(list(args)); rows["trino"]["State"].update(Running=False, Pid=0, ExitCode=143)
                return subprocess.CompletedProcess(args, 0, b"", b"")
            return original_command(args, **kwargs)
        attempt.command = command
        pid = rows["trino"]["State"]["Pid"]
        identity = {"pid": pid, "startTicks": 456, "hostBootId": "synthetic-boot", "cgroupSha256": "a"*64}
        base = types.SimpleNamespace(save=lambda path, value: saved.append((path, value)))
        with patch.object(runner, "process_identity", return_value=identity) as identities:
            stopped = runner.stop_normal_trino(attempt, base, Path("private-fixture"))
        self.assertEqual(identities.call_count, 2)
        self.assertEqual(stopped["exitCode"], 143)
        attempt.start("reader"); rows["reader"]["HostConfig"]["OomKillDisable"] = None
        self.assertEqual(len(attempt.containers()), 5)
        self.assertEqual([args for args in calls if args[:2] == ["docker", "start"]],
                         [["docker", "start", rows[role]["Id"]] for role in rows])
        self.assertEqual([args for args in calls if args[:2] == ["docker", "stop"]],
                         [["docker", "stop", "--time=30", rows["trino"]["Id"]]])
        self.assertTrue(all(row["HostConfig"]["OomKillDisable"] is None for row in rows.values()))

    def test_every_role_rejects_missing_disabled_and_nonbool_before_start_or_stop(self):
        absent = object()
        for role in runner.ROLES:
            for bad in (absent, True, 0, 1, "false", [], {}):
                attempt, rows, calls, saved = self.engine()
                attempt.containers()
                if bad is absent: del rows[role]["HostConfig"]["OomKillDisable"]
                else: rows[role]["HostConfig"]["OomKillDisable"] = bad
                with self.assertRaisesRegex(ValueError, "^PRESENT_ENABLED_OOM_KILLER_REPRESENTATION_REQUIRED$"):
                    attempt.start(role)
                # Same original inventory guard is used before cleanup/TERM.
                with self.assertRaisesRegex(ValueError, "^PRESENT_ENABLED_OOM_KILLER_REPRESENTATION_REQUIRED$"):
                    attempt.containers()
                self.assertFalse(any(args[:2] in (["docker", "start"], ["docker", "stop"]) for args in calls))
                self.assertEqual(saved, [])

    def test_other_host_fields_types_and_invalid_trino_state_never_bypass_stop(self):
        for role in runner.ROLES:
            for key, value in (("Unknown", {PRIVATE: [PRIVATE]}), ("OomScoreAdj", True), ("Memory", 1),
                               ("PidsLimit", False), ("SecurityOpt", [PRIVATE])):
                attempt, rows, calls, saved = self.engine(); attempt.containers()
                rows[role]["HostConfig"]["OomKillDisable"] = None
                rows[role]["HostConfig"][key] = value
                with self.assertRaises(ValueError): attempt.containers()
                self.assertFalse(any(args[:2] in (["docker", "start"], ["docker", "stop"]) for args in calls))
                self.assertEqual(saved, [])
        attempt, rows, calls, saved = self.engine()
        rows["trino"]["State"].update(Running=True, Pid=123, StartedAt="own-trino-start")
        attempt.containers(); rows["trino"]["HostConfig"]["OomKillDisable"] = True
        base = types.SimpleNamespace(save=Mock())
        with patch.object(runner, "process_identity") as identity:
            with self.assertRaisesRegex(ValueError, "PRESENT_ENABLED_OOM_KILLER_REPRESENTATION_REQUIRED"):
                runner.stop_normal_trino(attempt, base, Path("private-fixture"))
        identity.assert_not_called(); base.save.assert_not_called()
        self.assertFalse(any(args[:2] == ["docker", "stop"] for args in calls))


if __name__ == "__main__": unittest.main()
