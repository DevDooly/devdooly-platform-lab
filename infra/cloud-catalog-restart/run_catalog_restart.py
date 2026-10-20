"""One fresh catalog normal stop/start, quiescent writers and first fresh Trino. No retry."""
import argparse
import hashlib
import importlib
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import stat
import sys
import time
import uuid

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
FROZEN = REPO / "infra/cloud-lakehouse-ci"
SCOPE = "FRESH_CLOUD_POSTGRES_CATALOG_NORMAL_RESTART"
FROZEN_MANIFEST = "c63aded0a891bb66cb1fb2de591d67e237467681eb4a4e5a337b9d1d1b02d5e8"
OWN_FILES = {"run_catalog_restart.py", "catalog_lifecycle.py", "test_catalog_lifecycle.py", "test_run_catalog_restart.py", "README.ko.md"}
FROZEN_FILES = {
    "infra/cloud-lakehouse-ci/" + name for name in (
        "contract.py", "compose_trial9.py", "frozen_s3_primitives.py", "pinned_trino_configuration.py",
        "s3_readonly.py", "bootstrap_trial9.py", "run_trial9.py", "runtime-manifest.json")
} | {"infra/spark-ci/" + name for name in ("run_ci.py", "compose_plan.py", "bootstrap_spark.py")} | {
    "infra/spark-silver/" + name for name in (
        "spark_silver.py", "silver_contract.py", "artifact-lock.downloaded.json", "synthetic-v1.ndjson", "Dockerfile.candidate")
}


RESTART_DRIVER = "infra/cloud-lakehouse-restart/run_restart.py"
RESTART_MANIFEST = "infra/cloud-lakehouse-restart/runtime-manifest.json"
RESTART_MANIFEST_SHA256 = "6c9d7fd5e50f295aefc60191f9f3f49e745f166bb070c590f461c82dd4aed3b6"
FROZEN_FILES |= {RESTART_DRIVER, RESTART_MANIFEST}
PHASES = frozenset({"PREPARE", "CATALOG_BASELINE", "CATALOG_RESTART", "TRINO", "TERM_TRINO",
                    "READER", "FINAL_VERIFY", "COMPLETE"})
FAILURES = {phase: phase + "_UNVERIFIED" for phase in PHASES if phase != "COMPLETE"}
CATALOG_FIXED = {"schemaVersion": 1, "scope": "SAME_OWNED_POSTGRES_NORMAL_STOP_START",
    "sameContainer": True, "sameConfiguration": True, "sameDataVolume": True,
    "normalStopVerified": True, "actualExitCode": 0, "explicitStarts": 1,
    "actualDockerRestartCount": 0, "newPostmasterVerified": True, "sameSystemIdentifier": True,
    "catalogTables": 2, "logicalCatalogRowsPreserved": True, "sameGarageProcess": True,
    "sparkStopped": True, "trinoAbsentAtRestart": True, "stopSignalRequest": "CONFIGURED_SIGINT",
    "signalDeliveryDirectlyObserved": False}


def require(value, code):
    if not value:
        raise ValueError(code)


def pairs(values):
    require(len({key for key, _ in values}) == len(values), "NO_DUPLICATE_JSON_KEYS")
    return dict(values)


def regular_bytes(path, maximum=1048576):
    path = Path(path)
    before = path.lstat()
    require(stat.S_ISREG(before.st_mode) and before.st_nlink == 1 and 0 < before.st_size <= maximum,
            "BOUNDED_REGULAR_SOURCE_FILE")
    with os.fdopen(os.open(path, os.O_RDONLY | os.O_NOFOLLOW), "rb") as stream:
        opened = os.fstat(stream.fileno()); raw = stream.read(maximum + 1); after_fd = os.fstat(stream.fileno())
    identity = lambda value: (value.st_dev, value.st_ino, value.st_mode, value.st_nlink,
                              value.st_size, value.st_mtime_ns, value.st_ctime_ns)
    require(identity(before) == identity(opened) == identity(after_fd) == identity(path.lstat())
            and len(raw) == before.st_size, "SAME_SOURCE_FILE_BEFORE_AND_AFTER_READ")
    return raw


def source_snapshot(expected):
    raw = regular_bytes(HERE / "runtime-manifest.json")
    require(type(expected) is str and re.fullmatch(r"[a-f0-9]{64}", expected) and hashlib.sha256(raw).hexdigest() == expected,
            "EXACT_RESTART_SOURCE_MANIFEST")
    manifest = json.loads(raw, object_pairs_hook=pairs)
    require(type(manifest) is dict and set(manifest) == {"schemaVersion", "scope", "status", "files", "frozenSources",
            "frozenRuntimeManifestSha256", "frozenTrinoRestartManifestSha256"}
            and type(manifest["schemaVersion"]) is int and manifest["schemaVersion"] == 1 and manifest["scope"] == SCOPE
            and manifest["status"] == "SOURCE_ONLY_NOT_RUN"
            and manifest["frozenRuntimeManifestSha256"] == FROZEN_MANIFEST
            and manifest["frozenTrinoRestartManifestSha256"] == RESTART_MANIFEST_SHA256
            and type(manifest["files"]) is dict and type(manifest["frozenSources"]) is dict
            and set(manifest["files"]) == OWN_FILES and set(manifest["frozenSources"]) == FROZEN_FILES,
            "EXACT_NEW_AND_FROZEN_SOURCE_INVENTORY")
    values = {"runtime-manifest.json": raw}
    for prefix, root, rows in (("own:", HERE, manifest["files"]), ("frozen:", REPO, manifest["frozenSources"])):
        for name, pin in rows.items():
            path = root / name
            require(not any(parent.is_symlink() for parent in path.parents if parent.is_relative_to(root)),
                    "NO_SOURCE_PARENT_SYMLINK")
            require(type(pin) is dict and set(pin) == {"bytes", "sha256"}
                    and type(pin["bytes"]) is int and 0 < pin["bytes"] <= 1048576
                    and type(pin["sha256"]) is str and re.fullmatch(r"[a-f0-9]{64}", pin["sha256"]), "TYPED_SOURCE_PIN")
            data = regular_bytes(path)
            require(len(data) == pin["bytes"] and hashlib.sha256(data).hexdigest() == pin["sha256"],
                    "EXACT_RESTART_AND_UNCHANGED_FROZEN_SOURCE_BYTES")
            values[prefix + name] = data
    require(hashlib.sha256(values["frozen:infra/cloud-lakehouse-ci/runtime-manifest.json"]).hexdigest() == FROZEN_MANIFEST
            and hashlib.sha256(values["frozen:" + RESTART_MANIFEST]).hexdigest() == RESTART_MANIFEST_SHA256,
            "EXACT_BOTH_UNCHANGED_OLD_MANIFESTS")
    return values


def checked_module(path, raw, label):
    """Execute reviewed definitions from captured source, never an unverified bytecode cache."""
    require(regular_bytes(path) == raw, "MODULE_BYTES_STILL_MATCH_REVIEWED_SOURCE")
    module = importlib.util.module_from_spec(importlib.util.spec_from_file_location(label, path))
    exec(compile(raw, str(path), "exec"), module.__dict__)
    return module


def hosted(environment):
    require(sys.platform == "linux" and environment.get("GITHUB_ACTIONS") == "true"
            and environment.get("RUNNER_ENVIRONMENT") == "github-hosted"
            and environment.get("GITHUB_REPOSITORY") == "DevDooly/devdooly-platform-lab"
            and environment.get("GITHUB_EVENT_NAME") == "workflow_dispatch"
            and environment.get("GITHUB_REF") == "refs/heads/main"
            and environment.get("GITHUB_RUN_ATTEMPT") == "1"
            and environment.get("CLOUD_CATALOG_RESTART_OPT_IN") == "true",
            "FIRST_MANUAL_MAIN_OWN_GITHUB_HOSTED_LINUX_OPT_IN_ONLY")


def failure_diagnostic(error, phase, sources):
    try:
        require(phase in PHASES, "KNOWN_DIAGNOSTIC_PHASE")
        selected, trace, count = None, error.__traceback__, 0
        while trace is not None and count < 64:
            source = sources.get(trace.tb_frame.f_code.co_filename)
            if (source in {"driver", "catalog", "cloud", "prepare", "base"}
                    and trace.tb_frame.f_code.co_name not in {"require", "need"}
                    and type(trace.tb_lineno) is int and 0 < trace.tb_lineno <= 10000):
                selected = {"phase": phase, "sourceFile": source, "sourceLine": trace.tb_lineno}
            trace = trace.tb_next; count += 1
        return selected
    except BaseException:
        return None


def tool_signature(path):
    path = Path(path).resolve(strict=True)
    before = path.stat()
    require(stat.S_ISREG(before.st_mode) and 0 < before.st_size <= 128 * 1024**2
            and not before.st_mode & 0o022, "BOUNDED_NON_WRITABLE_TOOL_BINARY")
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        opened = os.fstat(stream.fileno())
        for chunk in iter(lambda: stream.read(65536), b""):
            digest.update(chunk)
        closed = os.fstat(stream.fileno())
    identity = lambda value: (value.st_dev, value.st_ino, value.st_mode, value.st_nlink,
                              value.st_size, value.st_mtime_ns, value.st_ctime_ns)
    require(identity(before) == identity(opened) == identity(closed) == identity(path.stat()), "SAME_TOOL_DURING_READ")
    return {"path": str(path), "identity": list(identity(before)), "sha256": digest.hexdigest()}


def tool_snapshot(attempt):
    docker = shutil.which("docker")
    require(docker is not None, "ACTUAL_DOCKER_CLIENT_PATH")
    raw = attempt.command(["docker", "info", "--format", "{{json .ClientInfo.Plugins}}"],
                          timeout=10, sensitive=True).stdout
    require(0 < len(raw) <= 65536, "BOUNDED_CLIENT_PLUGIN_METADATA")
    plugins = json.loads(raw, object_pairs_hook=pairs)
    require(type(plugins) is list and len(plugins) <= 16, "BOUNDED_CLIENT_PLUGIN_INVENTORY")
    compose = [item for item in plugins if type(item) is dict and item.get("Name") == "compose"]
    require(len(compose) == 1 and type(compose[0].get("Path")) is str
            and Path(compose[0]["Path"]).is_absolute(), "EXACT_ACTUAL_COMPOSE_PLUGIN_PATH")
    return {"docker": tool_signature(docker), "compose": tool_signature(compose[0]["Path"]),
            "pathEnvironment": os.environ.get("PATH"), "dockerHost": os.environ.get("DOCKER_HOST"),
            "dockerConfig": os.environ.get("DOCKER_CONFIG"), "dockerContext": os.environ.get("DOCKER_CONTEXT")}


def catalog_public(value):
    require(type(value) is dict and set(value) == set(CATALOG_FIXED) | {"namespacePropertyRows"}
            and all(type(value[key]) is type(expected) and value[key] == expected for key, expected in CATALOG_FIXED.items())
            and type(value["namespacePropertyRows"]) is int and 2 <= value["namespacePropertyRows"] <= 32,
            "EXACT_FINITE_CATALOG_RESULT_ONLY")
    return value


def prepared_fixture(trial, attempt, spark, checks):
    values = {item["role"]: item for item in attempt.containers()}
    require(set(values) == {"postgres", "garage", "spark"} and set(attempt.started_roles) == set(values),
            "EXACT_BASE_SERVICES_AND_STOPPED_SPARK_WITH_NO_TRINO_OR_READER")
    trial.normal_exit("spark", values["spark"])
    require(checks["normalSparkExit"] is True and spark["passed"] is True
            and spark["oldWarehouseObjects"] == 14 and spark["afterWarehouseObjects"] == 20,
            "ACTUAL_STOPPED_SPARK_AND_TWENTY_WHOLE_OBJECT_BASELINE")
    trial.snapshot_chain(spark["snapshots"], 3); trial.files(spark["beforeFiles"], 2); trial.files(spark["afterFiles"], 1)
    require(all(values[role]["running"] is True and values[role]["oom"] is False for role in ("postgres", "garage")),
            "BASE_SERVICES_LIVE_BEFORE_CATALOG_RESTART")
    return values


def stop_owned_resources(attempt):
    result = {"initializerStopped": False, "ownedBoundContainersStopped": False, "unboundContainerObserved": False}
    attempt.safety_stop = True
    try:
        initializer = attempt.initializer()
        if initializer and initializer["running"]:
            attempt.command(["docker", "stop", "--time=10", initializer["id"]], timeout=15)
        initializer = attempt.initializer()
        result["initializerStopped"] = initializer is None or not initializer["running"]
    except BaseException:
        pass
    try:
        bound_ids = {signature["id"] for signature in attempt.bound.values()}
        values = attempt.containers()
        result["unboundContainerObserved"] = any(value["id"] not in bound_ids for value in values)
        for value in values:
            if value["running"] and value["id"] in bound_ids:
                attempt.command(["docker", "stop", "--time=10", value["id"]], timeout=15)
        result["ownedBoundContainersStopped"] = all(not value["running"] for value in attempt.containers())
    except BaseException:
        pass
    return result


def final_pass(passed, source_unchanged, tools_unchanged, cleanup, elapsed, clock_in_budget):
    return (passed is True and source_unchanged is True and tools_unchanged is True
            and type(cleanup) is dict and set(cleanup) == {"initializerStopped", "ownedBoundContainersStopped", "unboundContainerObserved"}
            and all(type(value) is bool for value in cleanup.values())
            and cleanup == {"initializerStopped": True, "ownedBoundContainersStopped": True, "unboundContainerObserved": False}
            and type(elapsed) is int and 0 <= elapsed <= 600000 and clock_in_budget is True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-manifest-sha256", required=True)
    parser.add_argument("--ack-fresh-cloud-postgres-catalog-restart", action="store_true", required=True)
    args = parser.parse_args()
    hosted(os.environ)
    before = source_snapshot(args.source_manifest_sha256)
    sys.path.insert(0, str(FROZEN))
    trial = importlib.import_module("run_trial9")
    require(Path(trial.__file__).resolve() == FROZEN / "run_trial9.py", "EXACT_FROZEN_DRIVER_MODULE")
    prepared = checked_module(REPO / RESTART_DRIVER, before["frozen:" + RESTART_DRIVER], "reviewed_catalog_fixture")
    catalog = checked_module(HERE / "catalog_lifecycle.py", before["own:catalog_lifecycle.py"], "reviewed_catalog_lifecycle")
    # Do not call prepared.main/source_snapshot or import old trino_lifecycle: closure is exactly 18 frozen files.
    source = os.environ.get("SOURCE_COMMIT", "")
    trial.checkout_source(REPO, source)
    base, base_compose, oracle = trial.source_inputs(REPO, FROZEN_MANIFEST)
    os.umask(0o077)
    local = REPO / ".local"; local.mkdir(exist_ok=True)
    public = local / "cloud-catalog-restart-public"; public.mkdir(mode=0o700)
    nonce = uuid.uuid4().hex
    root = local / ("cloud-catalog-restart-private-" + nonce); root.mkdir(mode=0o700)
    require(os.environ.get("DOCKER_HOST") in (None, "", "unix:///var/run/docker.sock")
            and os.environ.get("DOCKER_CONTEXT") in (None, ""), "ONLY_LOCAL_HOSTED_DOCKER_DAEMON")
    docker_config = root / "docker-config"; docker_config.mkdir(mode=0o700)
    os.environ["DOCKER_HOST"] = "unix:///var/run/docker.sock"
    os.environ["DOCKER_CONFIG"] = str(docker_config)
    os.environ.pop("DOCKER_CONTEXT", None)
    project = "cloud-catalog-restart-" + nonce
    image = "spark-isolated-ci:" + nonce
    images = {"postgres": base.POSTGRES, "garage": base.GARAGE, "spark": image, "trino": trial.TRINO, "reader": base.SPARK}
    current = trial.make_attempt(base, root, project, images)
    checks = {name: False for name in (
        "frozenInputs", "vendor", "pinnedImages", "freshPhysicalVolumes", "actualMemAvailable7Gi", "internalNetwork",
        "singleClock", "normalSparkExit", "sparkStoppedAndTrinoNotStartedAtFault", "oneOwnedCatalogRestart",
        "catalogLogicalRowsPreserved", "catalogIdentityPreserved", "queryContract", "normalTrinoExit",
        "pythonReaderExit", "jdbcAndWholeObjectsUnchanged", "survivingProcessesUnchanged", "toolsUnchanged")}
    captures, result = {}, {}
    passed, source_unchanged, tools_unchanged = False, False, False
    phase, failure, diagnostic, before_tools = "PREPARE", None, None, None
    sources = {__file__: "driver", str(HERE / "catalog_lifecycle.py"): "catalog",
               str(FROZEN / "run_trial9.py"): "cloud", str(REPO / RESTART_DRIVER): "prepare",
               str(REPO / "infra/spark-ci/run_ci.py"): "base"}
    try:
        before_tools = tool_snapshot(current); base.save(root / "tools-before.private.json", before_tools)
        spark, before_jdbc = prepared.prepare(trial, base, base_compose, oracle, root, project, image, images,
                                             current, checks, captures)
        phase = "CATALOG_BASELINE"
        prepared_fixture(trial, current, spark, checks)
        checks["sparkStoppedAndTrinoNotStartedAtFault"] = True
        before_catalog = catalog.capture_catalog(current)
        base.save(root / "catalog-baseline.private.json", before_catalog)
        require(trial.jdbc(current) == before_jdbc, "PRE_RESTART_JDBC_POINTERS_SAME_AS_STOPPED_SPARK")
        require(current.deadline.remaining(330, 90) == 330, "CATALOG_TRINO_READER_AND_CLEANUP_RESERVE_REQUIRED")
        phase = "CATALOG_RESTART"
        proof = catalog.restart_catalog(trial, base, current, root, before_catalog)
        require(catalog.verify_post_restart(trial, current, proof) is True, "POST_RESTART_IDENTITY_AND_SQL_VERIFIED")
        pg_result = catalog_public(catalog.public_result(proof))
        checks["oneOwnedCatalogRestart"] = True
        checks["catalogLogicalRowsPreserved"] = True
        checks["catalogIdentityPreserved"] = True
        require(trial.jdbc(current) == before_jdbc, "POST_RESTART_JDBC_POINTERS_UNCHANGED")
        phase = "TRINO"
        trial.memory_available()
        current.cli("create", "--no-build", "trino")
        current.containers(); current.start("trino")
        prepared.ready(trial, current)
        read_result = trial.verify_trino(current, spark, oracle, base, root)
        require(trial.jdbc(current) == before_jdbc, "FRESH_TRINO_JDBC_POINTERS_UNCHANGED")
        require(catalog.verify_post_restart(trial, current, proof) is True, "POST_TRINO_IDENTITY_AND_SQL_VERIFIED")
        checks["queryContract"] = True
        phase = "TERM_TRINO"
        stop = trial.stop_normal_trino(current, base, root)
        checks["normalTrinoExit"] = True
        phase = "READER"
        current.command_stage = "READER"
        current.cli("create", "--no-build", "reader")
        current.containers(); current.start("reader"); current.wait_clean("reader", 60)
        checks["pythonReaderExit"] = True
        reader = trial.read_proof(root, "reader-result.json")
        require(reader["passed"] is True and reader["allPreTrinoBytesEqual"] is True and reader["onlyGetAndList"] is True
                and type(reader["oldObjects"]) is int and reader["oldObjects"] == spark["oldWarehouseObjects"] == 14
                and type(reader["wholeObjects"]) is int and reader["wholeObjects"] == spark["afterWarehouseObjects"] == 20,
                "ACTUAL_WHOLE_WAREHOUSE_GETS_EQUAL_PRE_RESTART_SPARK_CAPTURE")
        phase = "FINAL_VERIFY"
        require(trial.jdbc(current) == before_jdbc, "FINAL_JDBC_POINTERS_UNCHANGED")
        require(catalog.verify_post_restart(trial, current, proof) is True, "FINAL_IDENTITY_AND_SQL_VERIFIED")
        require(catalog_public(catalog.public_result(proof)) == pg_result, "SAME_FINITE_RESTART_RESULT")
        checks["survivingProcessesUnchanged"] = True
        checks["jdbcAndWholeObjectsUnchanged"] = True
        result = {"catalogRestart": pg_result, "read": read_result, "trinoActualExitCode": stop["exitCode"],
                  "trinoStopRequested": True, "signalDeliveryDirectlyObserved": False,
                  "oldWarehouseObjects": reader["oldObjects"], "wholeWarehouseObjects": reader["wholeObjects"]}
        passed = all(value is True for key, value in checks.items() if key != "toolsUnchanged")
    except BaseException as error:
        failure = FAILURES[phase]
        diagnostic = failure_diagnostic(error, phase, sources)
    finally:
        cleanup = stop_owned_resources(current)
        try:
            source_unchanged = source_snapshot(args.source_manifest_sha256) == before
        except BaseException as error:
            if diagnostic is None:
                diagnostic = failure_diagnostic(error, "FINAL_VERIFY", sources)
        try:
            tools_unchanged = before_tools is not None and tool_snapshot(current) == before_tools
        except BaseException as error:
            if diagnostic is None:
                diagnostic = failure_diagnostic(error, "FINAL_VERIFY", sources)
        checks["toolsUnchanged"] = tools_unchanged
        clock_in_budget = False
        try:
            if current.deadline is not None:
                current.deadline.remaining(.001, 0)
                clock_in_budget = True
        except BaseException as error:
            if diagnostic is None:
                diagnostic = failure_diagnostic(error, "FINAL_VERIFY", sources)
        elapsed = None if current.deadline is None else int((time.monotonic() - current.deadline.started) * 1000)
        # Compare the actual monotonic clock too; integer millisecond truncation must not create a late PASS.
        passed = final_pass(passed, source_unchanged, tools_unchanged, cleanup, elapsed,
                            clock_in_budget and time.monotonic() - current.deadline.started <= 600)
        if not passed and failure is None:
            failure = "FINAL_DEADLINE_CLEANUP_SOURCE_OR_TOOL_UNVERIFIED"
        summary = {"schemaVersion": 1, "scope": SCOPE, "passed": passed, "sourceCommit": source,
            "runtimeManifestSha256": args.source_manifest_sha256, "capturedAt": base.utc(),
            "phase": "COMPLETE" if passed else phase, "failureCode": failure, "selectedFailure": diagnostic,
            "checks": checks, "result": result if passed else {}, "cleanup": cleanup,
            "sourceBeforeAfterSame": source_unchanged, "toolsBeforeAfterSame": tools_unchanged,
            "workloadElapsedMillis": elapsed, "workloadBudgetSeconds": 600, "buildAndPullExcludedFromWorkloadClock": True,
            "plannedSequentialPeakMemoryBytes": 5 * 1024**3, "requiredActualMemAvailableBytes": 7 * 1024**3,
            "onlyFreshCloudResources": True, "miniPcContacted": False, "automaticRetryPerformed": False,
            "priorEvidenceModified": False, "rawLogsOrCredentialsUploaded": False, "volumesDeleted": False,
            "snapshotExpirationOrObjectGcPerformed": False, "runtimeAvailabilityOrPerformanceClaimed": False,
            "runnerStorageIsEphemeral": True}
        base.save(public / "summary.json", summary)
        print(json.dumps({"passed": passed, "scope": SCOPE, "phase": summary["phase"]}))
    return 0 if passed else 1


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as error:
        print(json.dumps({"passed": False, "scope": SCOPE, "phase": "PREPARE",
                          "failureCode": "SOURCE_OR_INPUT_UNVERIFIED", "selectedFailure": None}))
        raise SystemExit(1)


