"""One owned PostgreSQL stop/start; frozen factory guards remain unchanged.

All lifecycle records are private canonical bytes. Import performs no I/O.
"""
import copy
import datetime as dt
import json
from pathlib import Path
import re
import time

PROOF_SCOPE = "OWNED_POSTGRES_CATALOG_STOP_START"
PUBLIC_SCOPE = "SAME_OWNED_POSTGRES_NORMAL_STOP_START"
ROLES = frozenset(("postgres", "garage", "spark"))
TABLES = ("iceberg_namespace_properties", "iceberg_tables")
PREFIX = "s3://platform-lab-iceberg-20261015/warehouse/phase6/"
STATE_KEYS = {"id", "role", "running", "exitCode", "oom", "pid", "startedAt"}
MAX_RECORD = 1024**2

PRIVILEGE_SQL = """SET statement_timeout='5s'; SET lock_timeout='3s'; SET default_transaction_read_only=on;
SELECT json_build_object('database',current_database(),'user',current_user,
 'version',current_setting('server_version'),
 'controlReadable',has_function_privilege(current_user,'pg_catalog.pg_control_system()','EXECUTE'));"""

# Full 6+4 shape derives from the unchanged run_ci.pg_init Iceberg JDBC V1 DDL.
CATALOG_SQL = """SET statement_timeout='5s'; SET lock_timeout='3s'; SET default_transaction_read_only=on;
SELECT json_build_object(
 'system',json_build_object('database',current_database(),'user',current_user,
   'version',current_setting('server_version'),
   'systemIdentifier',(SELECT system_identifier::text FROM pg_catalog.pg_control_system()),
   'otherClientBackends',(SELECT count(*) FROM pg_stat_activity WHERE datname=current_database() AND backend_type='client backend' AND pid<>pg_backend_pid()),
   'postmasterStartedAt',to_char(pg_postmaster_start_time() AT TIME ZONE 'UTC','YYYY-MM-DD"T"HH24:MI:SS.US"Z"')),
 'schema',json_build_object(
   'tables',(SELECT coalesce(json_agg(table_name ORDER BY table_name),'[]'::json) FROM information_schema.tables WHERE table_schema='public' AND table_type='BASE TABLE'),
   'columns',(SELECT coalesce(json_agg(row_to_json(c) ORDER BY table_name,ordinal_position),'[]'::json) FROM (
     SELECT table_name,column_name,data_type,character_maximum_length,is_nullable,ordinal_position,column_default,is_identity,is_generated
     FROM information_schema.columns WHERE table_schema='public' AND table_name IN ('iceberg_tables','iceberg_namespace_properties')) c),
   'constraints',(SELECT coalesce(json_agg(row_to_json(c) ORDER BY table_name,kind),'[]'::json) FROM (
     SELECT r.relname AS table_name,k.contype::text AS kind,k.convalidated AS validated,
       k.condeferrable AS deferrable,k.condeferred AS initially_deferred,
       ARRAY(SELECT a.attname FROM unnest(k.conkey) WITH ORDINALITY v(attnum,ordinal) JOIN pg_attribute a ON a.attrelid=r.oid AND a.attnum=v.attnum ORDER BY v.ordinal) AS columns
     FROM pg_constraint k JOIN pg_class r ON r.oid=k.conrelid JOIN pg_namespace n ON n.oid=r.relnamespace
     WHERE n.nspname='public' AND r.relname IN ('iceberg_tables','iceberg_namespace_properties')) c),
   'indexes',(SELECT coalesce(json_agg(row_to_json(i) ORDER BY tablename,indexname),'[]'::json) FROM (
     SELECT tablename,indexname,indexdef FROM pg_indexes WHERE schemaname='public' AND tablename IN ('iceberg_tables','iceberg_namespace_properties')) i),
   'triggers',(SELECT count(*) FROM information_schema.triggers WHERE trigger_schema='public')),
 'tables',(SELECT coalesce(json_agg(row_to_json(t) ORDER BY catalog_name,table_namespace,table_name),'[]'::json) FROM (
   SELECT * FROM public.iceberg_tables ORDER BY catalog_name,table_namespace,table_name LIMIT 3) t),
 'namespaces',(SELECT coalesce(json_agg(row_to_json(n) ORDER BY catalog_name,namespace,property_key),'[]'::json) FROM (
   SELECT * FROM public.iceberg_namespace_properties ORDER BY catalog_name,namespace,property_key LIMIT 33) n));"""


def require(value, code):
    if not value:
        raise ValueError(code)


def _pairs(pairs):
    value = {}
    for key, item in pairs:
        require(key not in value, "NO_DUPLICATE_PRIVATE_JSON_KEY")
        value[key] = item
    return value


def _nonfinite(value):
    raise ValueError("NO_NONFINITE_PRIVATE_JSON")


def _encode(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False).encode("ascii")


def _decode(raw):
    require(type(raw) is bytes and 0 < len(raw) <= MAX_RECORD, "BOUNDED_PRIVATE_RECORD")
    value = json.loads(raw.decode("ascii"), object_pairs_hook=_pairs, parse_constant=_nonfinite)
    require(type(value) is dict and _encode(value) == raw, "CANONICAL_PRIVATE_RECORD")
    return value


def _time_ns(value):
    require(type(value) is str, "UTC_TIME_REQUIRED")
    match = re.fullmatch(r"(\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d)(?:\.(\d{1,9}))?Z", value)
    require(match is not None, "EXACT_UTC_TIME")
    parsed = dt.datetime.strptime(match[1], "%Y-%m-%dT%H:%M:%S").replace(tzinfo=dt.timezone.utc)
    seconds = (parsed - dt.datetime(1970, 1, 1, tzinfo=dt.timezone.utc)).days * 86400
    seconds += parsed.hour * 3600 + parsed.minute * 60 + parsed.second
    return seconds * 10**9 + int((match[2] or "").ljust(9, "0"))


def _remaining(attempt, maximum=5, reserve=90):
    require(attempt.deadline is not None and attempt.safety_stop is False, "SAME_ACTIVE_WORKLOAD_CLOCK")
    return attempt.deadline.remaining(maximum, reserve)


def _inventory(attempt):
    values = attempt.containers()  # Includes the frozen whole config/mount/restart-policy guards.
    require(type(values) is list and len(values) <= 5, "BOUNDED_FIVE_ROLE_INVENTORY")
    result = {}
    for row in values:
        require(type(row) is dict and set(row) == STATE_KEYS and row["role"] not in result
                and row["role"] in ROLES | {"trino", "reader"}
                and type(row["id"]) is str and re.fullmatch(r"[a-f0-9]{64}", row["id"]), "EXACT_UNIQUE_ROLE_STATE")
        require(type(row["running"]) is bool and type(row["oom"]) is bool and type(row["exitCode"]) is int
                and type(row["pid"]) is int and row["pid"] >= 0 and type(row["startedAt"]) is str,
                "EXACT_ROLE_STATE_TYPES")
        require(row["role"] in attempt.bound and attempt.bound[row["role"]]["id"] == row["id"], "SAME_BOUND_FULL_CID")
        result[row["role"]] = copy.deepcopy(row)
    require(ROLES <= set(result) and len({row["id"] for row in result.values()}) == len(result), "ALL_BASE_ROLES_DISTINCT")
    pg, garage, spark = (result[name] for name in ("postgres", "garage", "spark"))
    require(garage["running"] is True and garage["oom"] is False and garage["pid"] > 1, "GARAGE_LIVE_SURVIVOR")
    require(spark["running"] is False and spark["exitCode"] == 0 and spark["oom"] is False
            and spark["pid"] == 0 and _time_ns(spark["startedAt"]) > 0, "SPARK_NORMAL_EXIT_BEFORE_PG_RESTART")
    _remaining(attempt)
    return result


def _owned_pg(attempt, running):
    state = _inventory(attempt)["postgres"]
    require(state["running"] is running and state["oom"] is False, "EXACT_POSTGRES_RUNNING_STATE")
    raw = attempt.command(["docker", "inspect", state["id"]], timeout=5, sensitive=True).stdout
    require(type(raw) is bytes and 0 < len(raw) <= MAX_RECORD, "BOUNDED_OWN_PG_INSPECT")
    items = json.loads(raw, object_pairs_hook=_pairs, parse_constant=_nonfinite)
    require(type(items) is list and len(items) == 1, "SINGLE_OWN_PG_INSPECT")
    value = items[0]; bound = attempt.bound["postgres"]
    require(value["Id"] == state["id"] == bound["id"] and value["Created"] == bound["created"]
            and value["Image"] == bound["imageId"] and value["Config"] == bound["config"], "SAME_PG_FULL_CONFIG_CREATED_IMAGE")
    host = value["HostConfig"]
    require("OomKillDisable" in host and (host["OomKillDisable"] is None or host["OomKillDisable"] is False), "PG_OOM_KILLER_ENABLED")
    require(json.dumps({**host, "OomKillDisable": False}, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False) == bound["host"]
            and sorted(json.dumps(item, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False) for item in value["Mounts"]) == bound["mounts"],
            "SAME_PG_WHOLE_HOST_AND_MOUNTS")
    require(type(value["RestartCount"]) is int and value["RestartCount"] == 0
            and host["RestartPolicy"]["Name"] == "no" and value["Config"].get("StopSignal") == "SIGINT",
            "EXACT_SIGINT_NO_AUTOMATIC_RESTART")
    observed = value["State"]
    require(observed["Running"] is running and observed["OOMKilled"] is False and observed["Paused"] is False
            and observed["Restarting"] is False and observed["Pid"] == state["pid"]
            and observed["StartedAt"] == state["startedAt"] and observed["ExitCode"] == state["exitCode"], "PG_INSPECT_STATE_TIED")
    if running:
        require(state["pid"] > 1 and _time_ns(state["startedAt"]) > 0, "LIVE_PG_PROCESS")
    else:
        require(state["pid"] == 0 and state["exitCode"] == 0
                and _time_ns(observed["FinishedAt"]) > _time_ns(state["startedAt"]), "ACTUAL_PG_STOP_EXIT_ZERO")
    _remaining(attempt)
    return state, copy.deepcopy(value)


def _volume(attempt, raw):
    mounts = [item for item in raw["Mounts"] if item["Destination"] == "/var/lib/postgresql/data"]
    require(len(mounts) == 1, "ONE_PGDATA_MOUNT")
    mount = mounts[0]; name = attempt.project + "_postgres-data"
    require(mount["Type"] == "volume" and mount["Name"] == name and mount["Driver"] == "local" and mount["RW"] is True,
            "EXACT_OWN_LOCAL_PGDATA_VOLUME")
    data = attempt.command(["docker", "volume", "inspect", name], timeout=5, sensitive=True).stdout
    require(type(data) is bytes and 0 < len(data) <= 131072, "BOUNDED_VOLUME_INSPECT")
    rows = json.loads(data, object_pairs_hook=_pairs, parse_constant=_nonfinite)
    require(type(rows) is list and len(rows) == 1, "SINGLE_OWN_VOLUME")
    value = rows[0]
    require(value["Name"] == name and value["Driver"] == "local" and not value["Options"]
            and value["Labels"]["com.docker.compose.project"] == attempt.project
            and mount["Source"] == value["Mountpoint"], "PGDATA_VOLUME_IDENTITY")
    return copy.deepcopy(value)  # Preserve the complete actual volume inspect JSON privately.


def _sql(attempt, query):
    _remaining(attempt, 10)
    result = attempt.cli("exec", "-T", "postgres", "psql", "-X", "-q", "-A", "-t", "-v", "ON_ERROR_STOP=1",
                         "-U", "lab_bootstrap", "-d", "iceberg_lab", "-c", query, timeout=10, sensitive=True)
    require(result.returncode == 0 and type(result.stdout) is bytes and 0 < len(result.stdout) <= 131072, "BOUNDED_SINGLE_READONLY_SQL_RESULT")
    value = json.loads(result.stdout.decode("utf8"), object_pairs_hook=_pairs, parse_constant=_nonfinite)
    require(type(value) is dict, "ONE_SQL_JSON_OBJECT")
    _remaining(attempt)
    return value


def _expected_schema():
    definitions = {
        "iceberg_namespace_properties": (("catalog_name", 255, "NO"), ("namespace", 255, "NO"), ("property_key", 255, "NO"), ("property_value", 1000, "YES")),
        "iceberg_tables": (("catalog_name", 255, "NO"), ("table_namespace", 255, "NO"), ("table_name", 255, "NO"),
                           ("metadata_location", 1000, "YES"), ("previous_metadata_location", 1000, "YES"), ("iceberg_type", 5, "YES")),
    }
    columns, constraints, indexes = [], [], []
    for table in TABLES:
        for ordinal, (name, size, nullable) in enumerate(definitions[table], 1):
            columns.append(dict(table_name=table, column_name=name, data_type="character varying", character_maximum_length=size,
                                is_nullable=nullable, ordinal_position=ordinal, column_default=None, is_identity="NO", is_generated="NEVER"))
        keys = [row[0] for row in definitions[table][:3]]
        constraints.append(dict(table_name=table, kind="p", validated=True, deferrable=False, initially_deferred=False, columns=keys))
        indexes.append(dict(tablename=table, indexname=table + "_pkey",
                            indexdef="CREATE UNIQUE INDEX " + table + "_pkey ON public." + table + " USING btree (" + ", ".join(keys) + ")"))
    return dict(tables=list(TABLES), columns=columns, constraints=constraints, indexes=indexes, triggers=0)


def _payload(value):
    require(set(value) == {"system", "schema", "tables", "namespaces"}, "EXACT_WHOLE_CATALOG_FIELDS")
    system = value["system"]
    require(type(system) is dict and set(system) == {"database", "user", "version", "systemIdentifier", "postmasterStartedAt", "otherClientBackends"}
            and system["database"] == "iceberg_lab" and system["user"] == "lab_bootstrap"
            and type(system["version"]) is str and re.match(r"^17\.11(?:\s|$)", system["version"]), "EXACT_PG17_11_OWN_DATABASE")
    identifier = system["systemIdentifier"]
    require(type(identifier) is str and re.fullmatch(r"[1-9][0-9]{0,19}", identifier)
            and int(identifier) < 2**64 and _time_ns(system["postmasterStartedAt"]) > 0, "REAL_SYSTEM_AND_POSTMASTER_IDENTITY")
    require(type(system["otherClientBackends"]) is int and 0 <= system["otherClientBackends"] <= 16, "BOUNDED_OTHER_CLIENT_BACKENDS")
    require(type(value["schema"]) is dict and _encode(value["schema"]) == _encode(_expected_schema()), "EXACT_WHOLE_JDBC_V1_SCHEMA")
    tables = value["tables"]
    require(type(tables) is list and len(tables) == 2, "EXACT_TWO_CATALOG_TABLE_ROWS")
    expected = [("bronze", "synthetic_events"), ("silver", "sensor_outcomes")]
    for row, (namespace, table) in zip(tables, expected):
        require(type(row) is dict and set(row) == {"catalog_name", "table_namespace", "table_name", "metadata_location", "previous_metadata_location", "iceberg_type"}
                and (row["catalog_name"], row["table_namespace"], row["table_name"]) == ("phase6", namespace, table)
                and row["iceberg_type"] == "TABLE", "EXACT_WHOLE_FIXED_CATALOG_ROW")
        for name in ("metadata_location", "previous_metadata_location"):
            location = row[name]
            require(location is None and name == "previous_metadata_location" or type(location) is str
                    and 0 < len(location) <= 1000 and location.startswith(PREFIX + namespace + "/" + table + "/metadata/")
                    and re.fullmatch(r"[A-Za-z0-9._/-]+", location[len("s3://"):]) and ".." not in location.split("/")
                    and location.endswith(".metadata.json"), "OWNED_FIXED_METADATA_POINTER")
    namespaces = value["namespaces"]
    require(type(namespaces) is list and 2 <= len(namespaces) <= 32, "BOUNDED_WHOLE_NAMESPACE_ROWS")
    keys = []
    for row in namespaces:
        require(type(row) is dict and set(row) == {"catalog_name", "namespace", "property_key", "property_value"}
                and row["catalog_name"] == "phase6" and row["namespace"] in ("bronze", "silver")
                and type(row["property_key"]) is str and 0 < len(row["property_key"]) <= 255
                and (row["property_value"] is None or type(row["property_value"]) is str and len(row["property_value"]) <= 1000),
                "EXACT_NAMESPACE_WHOLE_ROW")
        keys.append((row["catalog_name"], row["namespace"], row["property_key"]))
    require(keys == sorted(set(keys)) and {row["namespace"] for row in namespaces} == {"bronze", "silver"}, "ORDERED_UNIQUE_NAMESPACE_PRIMARY_KEYS")
    return value


def _catalog(raw):
    value = _decode(raw)
    require(set(value) == {"schemaVersion", "context", "bound", "state", "volume", "catalog"}
            and type(value["schemaVersion"]) is int and value["schemaVersion"] == 1, "EXACT_PRIVATE_CATALOG_RECORD")
    context, bound, state = value["context"], value["bound"], value["state"]
    require(type(context) is dict and set(context) == {"root", "project", "deadlineStarted"}
            and type(context["root"]) is str and Path(context["root"]).is_absolute()
            and type(context["project"]) is str and re.fullmatch(r"cloud-catalog-restart-[a-f0-9]{32}", context["project"])
            and type(context["deadlineStarted"]) in (int, float) and context["deadlineStarted"] > 0,
            "EXACT_PRIVATE_ROOT_PROJECT_CLOCK")
    require(type(bound) is dict and set(bound) == {"id", "imageId", "config", "host", "mounts", "created"}
            and type(bound["id"]) is str and re.fullmatch(r"[a-f0-9]{64}", bound["id"])
            and type(bound["config"]) is dict and bound["config"].get("StopSignal") == "SIGINT"
            and type(bound["host"]) is str and type(bound["mounts"]) is list
            and type(value["volume"]) is dict and value["volume"].get("Name") == context["project"] + "_postgres-data",
            "EXACT_PRIVATE_PG_FULL_BINDING")
    require(type(state) is dict and set(state) == STATE_KEYS and state["role"] == "postgres"
            and state["id"] == bound["id"] and state["running"] is True and state["oom"] is False
            and type(state["exitCode"]) is int and state["exitCode"] == 0
            and type(state["pid"]) is int and state["pid"] > 1 and _time_ns(state["startedAt"]) > 0,
            "EXACT_PRIVATE_LIVE_PG_STATE")
    _payload(value["catalog"])
    return value


def capture_catalog(attempt):
    state, raw = _owned_pg(attempt, True)
    privilege = _sql(attempt, PRIVILEGE_SQL)
    require(set(privilege) == {"database", "user", "version", "controlReadable"}
            and privilege["database"] == "iceberg_lab" and privilege["user"] == "lab_bootstrap"
            and type(privilege["version"]) is str and re.match(r"^17\.11(?:\s|$)", privilege["version"])
            and privilege["controlReadable"] is True, "EXPLICIT_CONTROL_SYSTEM_PRIVILEGE_NO_GRANT")
    payload = _payload(_sql(attempt, CATALOG_SQL))
    inventory = _inventory(attempt)
    if "trino" not in inventory or not inventory["trino"]["running"]:
        require(payload["system"]["otherClientBackends"] == 0, "NO_OTHER_CLIENT_BACKEND_AFTER_CONTROL_QUERY")
    volume = _volume(attempt, raw)
    again, _ = _owned_pg(attempt, True)
    require(again == state, "PG_IDENTITY_STABLE_ACROSS_WHOLE_CATALOG_READ")
    value = dict(schemaVersion=1, context=dict(root=str(attempt.root), project=attempt.project, deadlineStarted=attempt.deadline.started),
                 bound=copy.deepcopy(attempt.bound["postgres"]), state=state, volume=volume, catalog=payload)
    raw = _encode(value); _catalog(raw)
    return raw


def verify_catalog_preserved(before, after):
    first, second = _catalog(before), _catalog(after)
    for key in ("context", "bound", "volume"):
        require(_encode(first[key]) == _encode(second[key]), "SAME_CATALOG_PHYSICAL_BINDING")
    left, right = copy.deepcopy(first["catalog"]), copy.deepcopy(second["catalog"])
    for value in (left, right):
        value["system"].pop("postmasterStartedAt"); value["system"].pop("otherClientBackends")
    require(_encode(left) == _encode(right), "WHOLE_LOGICAL_CATALOG_AND_SYSTEM_IDENTIFIER_PRESERVED")
    return True


def _initializer(attempt):
    require(attempt.initializer_intended is True and attempt.initializer_name == attempt.project + "-volume-init", "SAME_OWN_INITIALIZER")
    value = attempt.initializer()
    require(type(value) is dict and set(value) == {"id", "running", "exitCode", "oom"}
            and re.fullmatch(r"[a-f0-9]{64}", value["id"]) and value["running"] is False
            and type(value["exitCode"]) is int and value["exitCode"] == 0 and value["oom"] is False,
            "INITIALIZER_STOPPED_NON_OOM_EXIT_ZERO")
    checks = attempt.initializer_identity_checks
    require(type(checks) is dict and bool(checks) and all(item is True for item in checks.values()), "ALL_INITIALIZER_GUARDS")
    return dict(state=copy.deepcopy(value), checks=copy.deepcopy(checks))


def _old_process_gone(identity):
    require(type(identity) is dict and type(identity["pid"]) is int and identity["pid"] > 1, "KNOWN_OLD_OWN_PROCESS")
    require(Path("/proc/sys/kernel/random/boot_id").read_text().strip() == identity["hostBootId"], "SAME_HOST_BOOT_DURING_RESTART")
    try:
        raw = (Path("/proc") / str(identity["pid"]) / "stat").read_bytes()
    except FileNotFoundError:
        return True
    require(0 < len(raw) <= 16384, "BOUNDED_OLD_PROC_STAT")
    text = raw.decode("ascii"); require(text.split(" ", 1)[0] == str(identity["pid"]) and ") " in text, "OLD_PID_STAT_SHAPE")
    fields = text.rsplit(") ", 1)[1].split()
    require(len(fields) >= 20 and fields[19].isdecimal(), "OLD_PROC_START_TICKS")
    return fields[0] in ("Z", "X") or int(fields[19]) != identity["startTicks"]


def _proof(raw):
    value = _decode(raw)
    require(set(value) == {"schemaVersion", "scope", "before", "after", "boundSurvivors", "statesBefore", "processBefore", "processAfter", "initializer", "finishedAt", "actualExitCode", "explicitStarts", "restartCount"}
            and type(value["schemaVersion"]) is int and value["schemaVersion"] == 1 and value["scope"] == PROOF_SCOPE,
            "EXACT_PRIVATE_RESTART_PROOF")
    require(type(value["explicitStarts"]) is int and value["explicitStarts"] == 1 and type(value["actualExitCode"]) is int
            and value["actualExitCode"] == 0 and type(value["restartCount"]) is int and value["restartCount"] == 0,
            "ONE_NORMAL_MANUAL_RESTART_NOT_COUNTER_ONE")
    verify_catalog_preserved(_encode(value["before"]), _encode(value["after"]))
    before, after = value["before"], value["after"]
    states, survivors = value["statesBefore"], value["boundSurvivors"]
    require(type(states) is dict and set(states) == ROLES and type(survivors) is dict and set(survivors) == ROLES
            and states["postgres"] == before["state"] and survivors["postgres"] == before["bound"],
            "BASELINE_THREE_ROLES_TRINO_AND_READER_ABSENT")
    for role in ROLES:
        row = states[role]
        require(type(row) is dict and set(row) == STATE_KEYS and row["role"] == role
                and row["id"] == survivors[role]["id"] and row["oom"] is False
                and type(row["exitCode"]) is int and row["exitCode"] == 0 and _time_ns(row["startedAt"]) > 0,
                "EXACT_PROOF_BASELINE_SURVIVOR")
    require(states["garage"]["running"] is True and type(states["garage"]["pid"]) is int and states["garage"]["pid"] > 1
            and states["spark"]["running"] is False and type(states["spark"]["pid"]) is int and states["spark"]["pid"] == 0,
            "GARAGE_LIVE_AND_SPARK_NORMAL_STOPPED")
    require(type(value["processBefore"]) is dict and set(value["processBefore"]) == {"postgres", "garage"},
            "EXACT_TWO_LIVE_BASELINE_PROCESS_IDENTITIES")
    initializer = value["initializer"]
    require(type(initializer) is dict and set(initializer) == {"state", "checks"}
            and type(initializer["state"]) is dict and set(initializer["state"]) == {"id", "running", "exitCode", "oom"}
            and type(initializer["state"]["id"]) is str and re.fullmatch(r"[a-f0-9]{64}", initializer["state"]["id"])
            and initializer["state"]["running"] is False and initializer["state"]["oom"] is False
            and type(initializer["state"]["exitCode"]) is int and initializer["state"]["exitCode"] == 0
            and type(initializer["checks"]) is dict and bool(initializer["checks"])
            and all(item is True for item in initializer["checks"].values()), "EXACT_STOPPED_VERIFIED_INITIALIZER_PROOF")
    for identity, pid in ((value["processBefore"]["postgres"], before["state"]["pid"]),
                          (value["processBefore"]["garage"], states["garage"]["pid"]),
                          (value["processAfter"], after["state"]["pid"])):
        require(type(identity) is dict and set(identity) == {"pid", "startTicks", "hostBootId", "cgroupSha256"}
                and type(identity["pid"]) is int and identity["pid"] == pid and type(identity["startTicks"]) is int
                and identity["startTicks"] > 0 and type(identity["hostBootId"]) is str
                and re.fullmatch(r"[a-f0-9-]{36}", identity["hostBootId"])
                and type(identity["cgroupSha256"]) is str and re.fullmatch(r"[a-f0-9]{64}", identity["cgroupSha256"]),
                "EXACT_OWN_LIVE_PROCESS_IDENTITY")
    require(_time_ns(before["state"]["startedAt"]) < _time_ns(value["finishedAt"]) < _time_ns(after["state"]["startedAt"])
            and _time_ns(before["catalog"]["system"]["postmasterStartedAt"]) < _time_ns(after["catalog"]["system"]["postmasterStartedAt"]),
            "ACTUAL_STOP_START_AND_NEW_POSTMASTER_TIMES")
    require(value["processBefore"]["postgres"]["hostBootId"] == value["processAfter"]["hostBootId"]
            and (value["processBefore"]["postgres"]["pid"], value["processBefore"]["postgres"]["startTicks"])
            != (value["processAfter"]["pid"], value["processAfter"]["startTicks"]), "NEW_ACTUAL_POSTMASTER_PROCESS")
    return value


def restart_catalog(trial, base, attempt, root, before_catalog):
    root = Path(root)
    require(root.is_absolute() and root == attempt.root, "SAME_PRIVATE_PHYSICAL_ROOT")
    before = _catalog(before_catalog)
    require(capture_catalog(attempt) == before_catalog, "EXACT_BASELINE_STILL_CURRENT_BEFORE_RESTART")
    states = _inventory(attempt)
    require(set(states) == ROLES and attempt.started_roles == set(ROLES) and set(attempt.bound) == ROLES,
            "SPARK_STOPPED_TRINO_AND_READER_NEVER_STARTED")
    require(set(attempt.identities) == ROLES | {"trino", "reader"}, "FIXED_FIVE_ROLE_IMAGES")
    require(_remaining(attempt, 180, 90) == 180, "FULL_RESTART_STAGE_AND_CLEANUP_BUDGET_REQUIRED")
    state, raw = _owned_pg(attempt, True)
    processes = {role: trial.process_identity(states[role]["pid"], states[role]["id"]) for role in ("postgres", "garage")}
    survivors = {role: copy.deepcopy(attempt.bound[role]) for role in ROLES}
    initializer = _initializer(attempt)
    intent = root / "postgres-normal-restart-intent.json"
    require(not intent.exists(), "ONE_EXCLUSIVE_PG_RESTART_INTENT")
    base.save(intent, dict(cid=state["id"], process=processes["postgres"], configuredSignal="SIGINT", graceSeconds=30,
                           signalDeliveryDirectlyObserved=False, automaticRetry=False))
    attempt.command_stage = "POSTGRES_STOP"
    stopped = attempt.command(["docker", "stop", "--time=30", state["id"]], timeout=40, sensitive=True)
    require(stopped.returncode == 0, "ONE_NORMAL_PG_STOP_RETURNED_ZERO")
    stopped_state, stopped_raw = _owned_pg(attempt, False)
    require(stopped_state["id"] == state["id"] and stopped_state["startedAt"] == state["startedAt"]
            and _old_process_gone(processes["postgres"]), "ORIGINAL_POSTMASTER_EXITED")
    require(_volume(attempt, stopped_raw) == before["volume"], "SAME_PGDATA_VOLUME_AFTER_STOP")
    finished = stopped_raw["State"]["FinishedAt"]
    require(_remaining(attempt, 90, 90) == 90, "FULL_POST_STOP_START_AND_CLEANUP_BUDGET_REQUIRED")
    attempt.command_stage = "POSTGRES_EXPLICIT_START"
    # Do not alter started_roles or call/relax its one-first-start method.
    started = attempt.command(["docker", "start", state["id"]], timeout=15, sensitive=True)
    require(started.returncode == 0, "ONE_EXPLICIT_PG_START_RETURNED_ZERO")
    until = time.monotonic() + _remaining(attempt, 60, 90)
    while True:
        require(time.monotonic() < until, "BOUNDED_POST_RESTART_SQL_READINESS")
        current, _ = _owned_pg(attempt, True)
        require(current["id"] == state["id"] and _time_ns(current["startedAt"]) > _time_ns(finished), "SAME_CID_NEW_START_TIME")
        ready = attempt.cli("exec", "-T", "postgres", "pg_isready", "-h", "127.0.0.1", "-U", "lab_bootstrap", "-d", "iceberg_lab", timeout=5, check=False, sensitive=True)
        if ready.returncode == 0:
            require(time.monotonic() < until, "READINESS_OBSERVED_WITHIN_PHASE_DEADLINE")
            break
        time.sleep(min(1, max(0, until - time.monotonic())))
    after_raw = capture_catalog(attempt)
    require(time.monotonic() < until, "WHOLE_SQL_READY_WITHIN_PHASE_DEADLINE")
    verify_catalog_preserved(before_catalog, after_raw)
    after = _catalog(after_raw)
    post_process = trial.process_identity(after["state"]["pid"], after["state"]["id"])
    proof = _encode(dict(schemaVersion=1, scope=PROOF_SCOPE, before=before, after=after,
        boundSurvivors=survivors, statesBefore=states, processBefore=processes, processAfter=post_process,
        initializer=initializer, finishedAt=finished, actualExitCode=0, explicitStarts=1, restartCount=0))
    _proof(proof)
    verify_post_restart(trial, attempt, proof)
    base.save(root / "postgres-normal-restart-result.private.json", proof)
    return proof


def verify_post_restart(trial, attempt, proof):
    value = _proof(proof)
    current = _inventory(attempt)
    require(attempt.root == Path(value["before"]["context"]["root"]) and attempt.project == value["before"]["context"]["project"]
            and attempt.deadline.started == value["before"]["context"]["deadlineStarted"], "UNCHANGED_PRIVATE_CONTEXT_CLOCK")
    for role in ROLES:
        require(attempt.bound[role] == value["boundSurvivors"][role], "SAME_SURVIVOR_FULL_BINDING")
    require(current["postgres"] == value["after"]["state"] and current["garage"] == value["statesBefore"]["garage"]
            and current["spark"] == value["statesBefore"]["spark"], "PG_NEW_PROCESS_STABLE_OTHER_ROLES_UNCHANGED")
    require(trial.process_identity(current["postgres"]["pid"], current["postgres"]["id"]) == value["processAfter"]
            and trial.process_identity(current["garage"]["pid"], current["garage"]["id"]) == value["processBefore"]["garage"],
            "POSTGRES_AND_GARAGE_PROCESS_IDENTITY")
    require(_initializer(attempt) == value["initializer"], "SAME_INITIALIZER_IDENTITY")
    actual = capture_catalog(attempt)
    verify_catalog_preserved(_encode(value["after"]), actual)
    require(_catalog(actual)["catalog"]["system"]["postmasterStartedAt"] == value["after"]["catalog"]["system"]["postmasterStartedAt"], "POST_RESTART_POSTMASTER_TIME_STABLE")
    _remaining(attempt)
    return True


def public_result(proof):
    value = _proof(proof)
    return dict(schemaVersion=1, scope=PUBLIC_SCOPE, sameContainer=True, sameConfiguration=True, sameDataVolume=True,
        normalStopVerified=True, actualExitCode=value["actualExitCode"], explicitStarts=value["explicitStarts"],
        actualDockerRestartCount=value["restartCount"], newPostmasterVerified=True, sameSystemIdentifier=True,
        catalogTables=len(value["after"]["catalog"]["tables"]), namespacePropertyRows=len(value["after"]["catalog"]["namespaces"]),
        logicalCatalogRowsPreserved=True, sameGarageProcess=True, sparkStopped=True, trinoAbsentAtRestart=True,
        stopSignalRequest="CONFIGURED_SIGINT", signalDeliveryDirectlyObserved=False)
