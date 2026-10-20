"""Synthetic adapter contracts only. Every Docker, SQL, /proc, clock and save boundary is fake."""
import copy
from contextlib import ExitStack
import json
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch
import catalog_lifecycle as lifecycle


PROJECT = "cloud-catalog-restart-" + "a" * 32
ROOT = Path("/synthetic-owned-catalog-test")
PG, GARAGE, SPARK = "a" * 64, "b" * 64, "c" * 64
T0, T1, T2 = ("2026-10-20T00:00:0" + str(index) + ".000000000Z" for index in range(3))
BOOT = "01234567-89ab-cdef-0123-456789abcdef"
PREFIX = "s3://platform-lab-iceberg-20261015/warehouse/phase6/"


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False).encode("ascii")


def schema_fixture():
    # Hand-written PostgreSQL shape from frozen run_ci.pg_init / initialize-jdbc-v1.sql.
    # This never calls the adapter's _expected_schema, including in negative cases.
    definitions = [
        ("iceberg_namespace_properties", "catalog_name", 255, "NO", 1),
        ("iceberg_namespace_properties", "namespace", 255, "NO", 2),
        ("iceberg_namespace_properties", "property_key", 255, "NO", 3),
        ("iceberg_namespace_properties", "property_value", 1000, "YES", 4),
        ("iceberg_tables", "catalog_name", 255, "NO", 1),
        ("iceberg_tables", "table_namespace", 255, "NO", 2),
        ("iceberg_tables", "table_name", 255, "NO", 3),
        ("iceberg_tables", "metadata_location", 1000, "YES", 4),
        ("iceberg_tables", "previous_metadata_location", 1000, "YES", 5),
        ("iceberg_tables", "iceberg_type", 5, "YES", 6),
    ]
    columns = [dict(table_name=table, column_name=name, data_type="character varying",
        character_maximum_length=size, is_nullable=nullable, ordinal_position=ordinal,
        column_default=None, is_identity="NO", is_generated="NEVER")
        for table, name, size, nullable, ordinal in definitions]
    constraints = [
        dict(table_name="iceberg_namespace_properties", kind="p", validated=True, deferrable=False,
             initially_deferred=False, columns=["catalog_name", "namespace", "property_key"]),
        dict(table_name="iceberg_tables", kind="p", validated=True, deferrable=False,
             initially_deferred=False, columns=["catalog_name", "table_namespace", "table_name"]),
    ]
    indexes = [
        dict(tablename="iceberg_namespace_properties", indexname="iceberg_namespace_properties_pkey",
             indexdef="CREATE UNIQUE INDEX iceberg_namespace_properties_pkey ON public.iceberg_namespace_properties USING btree (catalog_name, namespace, property_key)"),
        dict(tablename="iceberg_tables", indexname="iceberg_tables_pkey",
             indexdef="CREATE UNIQUE INDEX iceberg_tables_pkey ON public.iceberg_tables USING btree (catalog_name, table_namespace, table_name)"),
    ]
    return dict(tables=["iceberg_namespace_properties", "iceberg_tables"], columns=columns,
                constraints=constraints, indexes=indexes, triggers=0)


def payload_fixture(after=False):
    rows = []
    for namespace, table in (("bronze", "synthetic_events"), ("silver", "sensor_outcomes")):
        location = PREFIX + namespace + "/" + table + "/metadata/"
        rows.append(dict(catalog_name="phase6", table_namespace=namespace, table_name=table,
                         metadata_location=location + "00002-current.metadata.json",
                         previous_metadata_location=location + "00001-previous.metadata.json", iceberg_type="TABLE"))
    return dict(system=dict(database="iceberg_lab", user="lab_bootstrap", version="17.11 (Debian)",
        systemIdentifier="1234567890123456789", postmasterStartedAt=T2 if after else T0, otherClientBackends=0),
        schema=schema_fixture(), tables=rows, namespaces=[
            dict(catalog_name="phase6", namespace="bronze", property_key="exists", property_value="true"),
            dict(catalog_name="phase6", namespace="silver", property_key="exists", property_value="true")])


def state(role, after=False, stopped=False):
    cid = {"postgres": PG, "garage": GARAGE, "spark": SPARK}[role]
    live = role != "spark" and not stopped
    pid = (303 if after else 101) if role == "postgres" else 202
    return dict(id=cid, role=role, running=live, exitCode=0, oom=False,
                pid=pid if live else 0, startedAt=T2 if role == "postgres" and after else T0)


def process(pid):
    return dict(pid=pid, startTicks=pid * 10, hostBootId=BOOT, cgroupSha256="d" * 64)


class FakeClock:
    def __init__(self): self.now = 10.0
    def sleep(self, seconds): self.now += seconds


class FakeDeadline:
    started = 1.25
    def remaining(self, maximum, reserve): return maximum


class FakeAttempt:
    def __init__(self, clock):
        self.root, self.project, self.clock = ROOT, PROJECT, clock
        self.deadline, self.safety_stop = FakeDeadline(), False
        self.phase, self.command_stage = "before", "TEST"
        self.started_roles = {"postgres", "garage", "spark"}
        self.identities = dict.fromkeys(("postgres", "garage", "spark", "trino", "reader"), "sha256:" + "e" * 64)
        self.initializer_intended, self.initializer_name = True, PROJECT + "-volume-init"
        self.initializer_identity_checks = dict(config=True, mounts=True, image=True)
        self.volume = dict(Name=PROJECT + "_postgres-data", Driver="local", Options=None,
            Labels={"com.docker.compose.project": PROJECT, "com.docker.compose.volume": "postgres-data"},
            Mountpoint="/synthetic/docker/volumes/" + PROJECT + "_postgres-data/_data", Scope="local", CreatedAt=T0)
        self.mounts = [dict(Type="volume", Name=self.volume["Name"], Source=self.volume["Mountpoint"],
            Destination="/var/lib/postgresql/data", Driver="local", Mode="rw", RW=True, Propagation="")]
        host = dict(OomKillDisable=False, RestartPolicy=dict(Name="no", MaximumRetryCount=0))
        self.bound = {role: dict(id=cid, imageId="sha256:" + "e" * 64, config=dict(StopSignal="SIGINT"),
            host=canonical(host).decode("ascii"), mounts=sorted(canonical(item).decode("ascii") for item in self.mounts), created=T0)
            for role, cid in (("postgres", PG), ("garage", GARAGE), ("spark", SPARK))}
        self.commands, self.sql_queries, self.readiness_calls = [], [], []
        self.privilege = dict(database="iceberg_lab", user="lab_bootstrap", version="17.11 (Debian)", controlReadable=True)
        self.other_backends, self.foreign_role = 0, False
        self.stop_code, self.stopped_exit, self.start_ambiguous = 0, 0, False
        self.late_readiness, self.late_sql = False, False
        self.inspect_change = lambda raw: None

    def containers(self):
        pg = state("postgres", after=self.phase == "after", stopped=self.phase == "stopped")
        if self.phase == "stopped": pg["exitCode"] = self.stopped_exit
        rows = [pg, state("garage"), state("spark")]
        if self.foreign_role:
            rows.append(dict(id="f" * 64, role="unowned", running=False, exitCode=0, oom=False, pid=0, startedAt=T0))
        return rows

    def inspect(self):
        pg = self.containers()[0]
        raw = dict(Id=PG, Created=T0, Image=self.bound["postgres"]["imageId"],
            Config=copy.deepcopy(self.bound["postgres"]["config"]), HostConfig=json.loads(self.bound["postgres"]["host"]),
            Mounts=copy.deepcopy(self.mounts), RestartCount=0,
            State=dict(Running=pg["running"], OOMKilled=False, Paused=False, Restarting=False, Pid=pg["pid"],
                       StartedAt=pg["startedAt"], ExitCode=pg["exitCode"], FinishedAt=T1))
        self.inspect_change(raw)
        return raw

    def command(self, arguments, **options):
        self.commands.append((list(arguments), dict(options)))
        if arguments == ["docker", "inspect", PG]:
            return SimpleNamespace(returncode=0, stdout=canonical([self.inspect()]))
        if arguments == ["docker", "volume", "inspect", self.volume["Name"]]:
            return SimpleNamespace(returncode=0, stdout=canonical([self.volume]))
        if arguments == ["docker", "stop", "--time=30", PG]:
            self.phase = "stopped"
            return SimpleNamespace(returncode=self.stop_code, stdout=b"stopped")
        if arguments == ["docker", "start", PG]:
            if self.start_ambiguous: raise TimeoutError("SYNTHETIC_AMBIGUOUS_START")
            self.phase = "after"
            return SimpleNamespace(returncode=0, stdout=b"started")
        raise AssertionError("NO_REAL_OR_UNEXPECTED_COMMAND")

    def cli(self, *arguments, **options):
        if "pg_isready" in arguments:
            self.readiness_calls.append((arguments, options))
            if self.late_readiness: self.clock.now = 71.0
            return SimpleNamespace(returncode=0, stdout=b"")
        if "psql" in arguments and "-c" in arguments:
            query = arguments[arguments.index("-c") + 1]; self.sql_queries.append(query)
            if query == lifecycle.PRIVILEGE_SQL: value = self.privilege
            elif query == lifecycle.CATALOG_SQL:
                value = payload_fixture(self.phase == "after"); value["system"]["otherClientBackends"] = self.other_backends
                if self.late_sql and self.phase == "after": self.clock.now = 71.0
            else: raise AssertionError("NO_UNKNOWN_SQL")
            return SimpleNamespace(returncode=0, stdout=canonical(value))
        raise AssertionError("NO_REAL_OR_UNEXPECTED_CLI")

    def initializer(self):
        return dict(id="f" * 64, running=False, exitCode=0, oom=False)

    def mutations(self):
        return [args for args, options in self.commands if args[:2] in (["docker", "stop"], ["docker", "start"])]


class FakeTrial:
    def __init__(self): self.drift = False
    def process_identity(self, pid, cid):
        if (pid, cid) not in ((101, PG), (303, PG), (202, GARAGE)):
            raise AssertionError("NO_REAL_OR_UNKNOWN_PROCESS")
        value = process(pid)
        if self.drift and pid == 303: value["startTicks"] += 1
        return value


def private_fixture(attempt, after=False):
    return dict(schemaVersion=1, context=dict(root=str(ROOT), project=PROJECT, deadlineStarted=1.25),
        bound=copy.deepcopy(attempt.bound["postgres"]), state=state("postgres", after=after),
        volume=copy.deepcopy(attempt.volume), catalog=payload_fixture(after))


class CatalogLifecycleTest(unittest.TestCase):
    def setUp(self):
        self.clock = FakeClock(); self.attempt = FakeAttempt(self.clock); self.trial = FakeTrial()
        self.base = SimpleNamespace(save=Mock())
        self.stack = ExitStack(); self.addCleanup(self.stack.close)
        self.stack.enter_context(patch.object(lifecycle.time, "monotonic", side_effect=lambda: self.clock.now))
        self.stack.enter_context(patch.object(lifecycle.time, "sleep", side_effect=self.clock.sleep))
        self.stack.enter_context(patch.object(lifecycle.Path, "exists", return_value=False))
        self.gone = self.stack.enter_context(patch.object(lifecycle, "_old_process_gone", return_value=True))

    def proof(self):
        before = canonical(private_fixture(self.attempt))
        return lifecycle.restart_catalog(self.trial, self.base, self.attempt, ROOT, before)

    def test_capture_binds_handwritten_full_schema_all_rows_and_complete_volume(self):
        value = json.loads(lifecycle.capture_catalog(self.attempt))
        self.assertEqual(schema_fixture(), value["catalog"]["schema"])
        self.assertEqual((6, 4), (sum(row["table_name"] == "iceberg_tables" for row in value["catalog"]["schema"]["columns"]),
                                  sum(row["table_name"] == "iceberg_namespace_properties" for row in value["catalog"]["schema"]["columns"])))
        self.assertEqual(payload_fixture(), value["catalog"])
        self.assertEqual(self.attempt.volume, value["volume"])
        self.assertEqual(T0, value["volume"]["CreatedAt"])
        self.assertEqual([lifecycle.PRIVILEGE_SQL, lifecycle.CATALOG_SQL], self.attempt.sql_queries)
        for query in self.attempt.sql_queries:
            self.assertIn("default_transaction_read_only=on", query)
            self.assertNotIn("GRANT ", query); self.assertNotIn("UPDATE ", query)
        self.assertEqual([], self.attempt.mutations()); self.base.save.assert_not_called()

    def test_exact_schema_rows_types_and_fixed_table_kind_fail_closed(self):
        before = private_fixture(self.attempt)
        mutations = [
            lambda row: row["catalog"]["schema"]["columns"].pop(),
            lambda row: row["catalog"]["schema"]["columns"][0].update(ordinal_position=True),
            lambda row: row["catalog"]["schema"].update(triggers=False),
            lambda row: row["catalog"]["tables"][0].update(iceberg_type=None),
            lambda row: row["catalog"]["tables"][0].update(unobserved="private-canary"),
            lambda row: row["catalog"]["tables"][0].update(metadata_location="s3://foreign/private.metadata.json"),
            lambda row: row["catalog"]["namespaces"][0].update(property_value=False),
            lambda row: row["catalog"]["system"].update(systemIdentifier=123),
            lambda row: row["catalog"]["system"].update(otherClientBackends=True),
        ]
        for mutate in mutations:
            changed = copy.deepcopy(before); mutate(changed)
            with self.subTest(mutation=mutations.index(mutate)), self.assertRaises(ValueError):
                lifecycle.verify_catalog_preserved(canonical(before), canonical(changed))
        self.assertEqual([], self.attempt.commands)

    def test_preservation_checks_nonpointer_rows_json_types_and_physical_binding(self):
        before = private_fixture(self.attempt); after = private_fixture(self.attempt, after=True)
        self.assertTrue(lifecycle.verify_catalog_preserved(canonical(before), canonical(after)))
        mutations = [
            lambda row: row["catalog"]["namespaces"][0].update(property_value="changed"),
            lambda row: row["catalog"]["tables"][1].update(previous_metadata_location=PREFIX + "silver/sensor_outcomes/metadata/another.metadata.json"),
            lambda row: row["volume"].update(CreatedAt=T1),
            lambda row: row["volume"].update(Options={}),
            lambda row: row["bound"]["config"].update(Unobserved=False),
            lambda row: row["context"].update(deadlineStarted=True),
            lambda row: row["catalog"]["system"].update(systemIdentifier="2234567890123456789"),
        ]
        for mutate in mutations:
            changed = copy.deepcopy(after); mutate(changed)
            with self.subTest(mutation=mutations.index(mutate)), self.assertRaises(ValueError):
                lifecycle.verify_catalog_preserved(canonical(before), canonical(changed))
        typed_before = copy.deepcopy(before); typed_after = copy.deepcopy(after)
        typed_before["bound"]["config"]["SyntheticFlag"] = False; typed_after["bound"]["config"]["SyntheticFlag"] = 0
        with self.assertRaises(ValueError): lifecycle.verify_catalog_preserved(canonical(typed_before), canonical(typed_after))

    def test_denied_control_privilege_busy_backend_and_foreign_role_never_stop_or_start(self):
        variants = ("privilege", "backend", "role")
        for variant in variants:
            attempt = FakeAttempt(self.clock); before = canonical(private_fixture(attempt)); base = SimpleNamespace(save=Mock())
            if variant == "privilege": attempt.privilege["controlReadable"] = False
            if variant == "backend": attempt.other_backends = 1
            if variant == "role": attempt.foreign_role = True
            with self.subTest(variant=variant), self.assertRaises(ValueError):
                lifecycle.restart_catalog(self.trial, base, attempt, ROOT, before)
            self.assertEqual([], attempt.mutations()); base.save.assert_not_called()

    def test_one_stop_one_start_same_cid_counter_zero_and_exact_finite_public_projection(self):
        proof = self.proof()
        self.assertEqual([["docker", "stop", "--time=30", PG], ["docker", "start", PG]], self.attempt.mutations())
        self.assertEqual(2, self.base.save.call_count)
        intent = self.base.save.call_args_list[0].args[1]
        self.assertIs(intent["automaticRetry"], False); self.assertIs(intent["signalDeliveryDirectlyObserved"], False)
        self.assertEqual(dict(schemaVersion=1, scope="SAME_OWNED_POSTGRES_NORMAL_STOP_START",
            sameContainer=True, sameConfiguration=True, sameDataVolume=True, normalStopVerified=True,
            actualExitCode=0, explicitStarts=1, actualDockerRestartCount=0, newPostmasterVerified=True,
            sameSystemIdentifier=True, catalogTables=2, namespacePropertyRows=2, logicalCatalogRowsPreserved=True,
            sameGarageProcess=True, sparkStopped=True, trinoAbsentAtRestart=True,
            stopSignalRequest="CONFIGURED_SIGINT", signalDeliveryDirectlyObserved=False), lifecycle.public_result(proof))
        result = lifecycle.public_result(proof); self.assertEqual(19, len(result))
        for private_value in (PG, GARAGE, BOOT, "lab_bootstrap", PREFIX, "private-canary"):
            self.assertNotIn(private_value, json.dumps(result))

    def test_unverified_stop_and_ambiguous_start_are_not_retried(self):
        for variant, expected_starts in (("stop-error", 0), ("stop-exit", 0), ("old-alive", 0), ("start-ambiguous", 1)):
            attempt = FakeAttempt(self.clock); base = SimpleNamespace(save=Mock())
            if variant == "stop-error": attempt.stop_code = 1
            if variant == "stop-exit": attempt.stopped_exit = 137
            if variant == "start-ambiguous": attempt.start_ambiguous = True
            self.gone.return_value = variant != "old-alive"
            with self.subTest(variant=variant), self.assertRaises((ValueError, TimeoutError)):
                lifecycle.restart_catalog(self.trial, base, attempt, ROOT, canonical(private_fixture(attempt)))
            mutations = attempt.mutations()
            self.assertEqual(1, sum(args[1] == "stop" for args in mutations))
            self.assertEqual(expected_starts, sum(args[1] == "start" for args in mutations))
            self.assertEqual(1, base.save.call_count)

    def test_late_pg_ready_and_late_whole_sql_snapshot_cannot_pass_the_phase(self):
        for variant, code in (("readiness", "READINESS_OBSERVED_WITHIN_PHASE_DEADLINE"),
                              ("sql", "WHOLE_SQL_READY_WITHIN_PHASE_DEADLINE")):
            self.clock.now = 10.0; attempt = FakeAttempt(self.clock); base = SimpleNamespace(save=Mock())
            attempt.late_readiness = variant == "readiness"; attempt.late_sql = variant == "sql"
            with self.subTest(variant=variant), self.assertRaisesRegex(ValueError, code):
                lifecycle.restart_catalog(self.trial, base, attempt, ROOT, canonical(private_fixture(attempt)))
            self.assertEqual(2, len(attempt.mutations())); self.assertEqual(1, base.save.call_count)

    def test_post_restart_rejects_process_volume_and_full_survivor_binding_drift(self):
        for variant in ("process", "volume", "garage-binding", "pg-pid"):
            self.attempt = FakeAttempt(self.clock); self.trial = FakeTrial(); self.base = SimpleNamespace(save=Mock())
            proof = self.proof()
            if variant == "process": self.trial.drift = True
            if variant == "volume": self.attempt.volume["CreatedAt"] = T1
            if variant == "garage-binding": self.attempt.bound["garage"]["config"]["Env"] = ["changed"]
            if variant == "pg-pid":
                original = self.attempt.containers
                def changed_states():
                    rows = original(); rows[0]["pid"] = 404; return rows
                self.attempt.containers = changed_states
            with self.subTest(variant=variant), self.assertRaises(ValueError):
                lifecycle.verify_post_restart(self.trial, self.attempt, proof)

    def test_public_projection_rejects_forged_nested_proof_and_boolean_counters(self):
        original = json.loads(self.proof())
        mutations = [
            lambda value: value.update(schemaVersion=True), lambda value: value.update(actualExitCode=False),
            lambda value: value.update(explicitStarts=True), lambda value: value.update(restartCount=1),
            lambda value: value["processAfter"].update(pid=True),
            lambda value: value["processAfter"].update(hostBootId="11234567-89ab-cdef-0123-456789abcdef"),
            lambda value: value["statesBefore"]["spark"].update(running=True),
            lambda value: value["initializer"]["state"].update(running=True),
            lambda value: value["initializer"]["checks"].update(config=False),
        ]
        for mutate in mutations:
            value = copy.deepcopy(original); mutate(value)
            with self.subTest(mutation=mutations.index(mutate)), self.assertRaises(ValueError):
                lifecycle.public_result(canonical(value))

    def test_automatic_restart_signal_or_owned_mount_drift_fails_before_mutation(self):
        for variant in ("restart", "signal", "mount", "volume-owner"):
            attempt = FakeAttempt(self.clock); base = SimpleNamespace(save=Mock()); before = canonical(private_fixture(attempt))
            if variant == "restart": attempt.inspect_change = lambda raw: raw.update(RestartCount=1)
            if variant == "signal": attempt.inspect_change = lambda raw: raw["Config"].update(StopSignal="SIGTERM")
            if variant == "mount": attempt.inspect_change = lambda raw: raw["Mounts"][0].update(Source="/foreign")
            if variant == "volume-owner": attempt.volume["Labels"]["com.docker.compose.project"] = "foreign"
            with self.subTest(variant=variant), self.assertRaises(ValueError):
                lifecycle.restart_catalog(self.trial, base, attempt, ROOT, before)
            self.assertEqual([], attempt.mutations()); base.save.assert_not_called()


if __name__ == "__main__":
    unittest.main()
