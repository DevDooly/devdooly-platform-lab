"""One fresh hosted warehouse; two explicitly owned Trino lifecycles, no retry."""
import argparse
import hashlib
import importlib
import json
import os
from pathlib import Path
import re
import secrets
import shutil
import sys
import time
import uuid

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
FROZEN = REPO / "infra/cloud-lakehouse-ci"
SCOPE = "FRESH_CLOUD_SAME_WAREHOUSE_TRINO_NORMAL_RESTART"
FROZEN_MANIFEST = "c63aded0a891bb66cb1fb2de591d67e237467681eb4a4e5a337b9d1d1b02d5e8"
OWN_FILES = {"run_restart.py", "trino_lifecycle.py", "test_lifecycle.py", "README.ko.md"}
FROZEN_FILES = {
    "infra/cloud-lakehouse-ci/" + name for name in (
        "contract.py", "compose_trial9.py", "frozen_s3_primitives.py", "pinned_trino_configuration.py",
        "s3_readonly.py", "bootstrap_trial9.py", "run_trial9.py", "runtime-manifest.json")
} | {"infra/spark-ci/" + name for name in ("run_ci.py", "compose_plan.py", "bootstrap_spark.py")} | {
    "infra/spark-silver/" + name for name in (
        "spark_silver.py", "silver_contract.py", "artifact-lock.downloaded.json", "synthetic-v1.ndjson", "Dockerfile.candidate")
}


def require(value, code):
    if not value:
        raise ValueError(code)


def source_snapshot(expected):
    raw = (HERE / "runtime-manifest.json").read_bytes()
    require(re.fullmatch(r"[a-f0-9]{64}", expected) and hashlib.sha256(raw).hexdigest() == expected,
            "EXACT_RESTART_SOURCE_MANIFEST")
    manifest = json.loads(raw)
    require(set(manifest) == {"schemaVersion", "scope", "status", "files", "frozenSources", "frozenRuntimeManifestSha256"}
            and manifest["schemaVersion"] == 1 and manifest["scope"] == SCOPE
            and manifest["status"] == "SOURCE_ONLY_NOT_RUN"
            and manifest["frozenRuntimeManifestSha256"] == FROZEN_MANIFEST
            and set(manifest["files"]) == OWN_FILES and set(manifest["frozenSources"]) == FROZEN_FILES,
            "EXACT_NEW_AND_FROZEN_SOURCE_INVENTORY")
    values = {"runtime-manifest.json": raw}
    for prefix, root, rows in (("own:", HERE, manifest["files"]), ("frozen:", REPO, manifest["frozenSources"])):
        for name, pin in rows.items():
            data = (root / name).read_bytes()
            require(len(data) == pin["bytes"] and hashlib.sha256(data).hexdigest() == pin["sha256"],
                    "EXACT_RESTART_AND_UNCHANGED_FROZEN_SOURCE_BYTES")
            values[prefix + name] = data
    return values


def prepare(trial, base, base_compose, oracle, root, project, image, images, attempt, checks, captures):
    # Explicit reuse of frozen run_trial9.py:438-549; physical root stays unchanged.
    repo = REPO
    require = trial.require
    sha = trial.sha
    configuration = trial.configuration
    plan = trial.plan
    TRINO = trial.TRINO
    Deadline = trial.Deadline
    memory_available = trial.memory_available
    read_proof = trial.read_proof
    snapshot_chain = trial.snapshot_chain
    files = trial.files
    jdbc = trial.jdbc
    checks["frozenInputs"] = True
    require(shutil.disk_usage(root).free >= 8*1024**3, "FRESH_CLOUD_DISK_RESERVE_8_GIB")
    for kind in ("container", "volume", "network"):
        prefix = ["docker", "ps", "-aq"] if kind == "container" else ["docker", kind, "ls", "-q"]
        require(not attempt.command([*prefix, "--filter", "label=com.docker.compose.project=" + project]).stdout.strip(), "UUID_PROJECT_ABSENT_BEFORE_CREATE")
    build = root / "build"; build.mkdir(mode=0o700)
    packet = repo / "infra/spark-silver"
    for name, digest in base.MODULES.items():
        raw = (packet / name).read_bytes(); require(sha(raw) == digest, "EXACT_SILVER_BUILD_INPUT"); base.save(build / name, raw)
    base.save(build / "base_bootstrap.py", (repo / "infra/spark-ci/bootstrap_spark.py").read_bytes())
    added = ("contract.py", "frozen_s3_primitives.py", "s3_readonly.py", "bootstrap_trial9.py")
    for name in added: base.save(build / name, (FROZEN / name).read_bytes())
    dockerfile = (build / "Dockerfile.candidate").read_bytes() + ("\nCOPY --chown=185:185 --chmod=0444 base_bootstrap.py " + " ".join(added) + " /opt/silver/\n").encode()
    base.save(build / "Dockerfile.trial9", dockerfile)
    base.vendor(base.validated_lock((packet / "artifact-lock.downloaded.json").read_bytes()), build / "vendor")
    checks["vendor"] = True
    for reference in (base.POSTGRES, base.GARAGE, base.SPARK, TRINO):
        attempt.command(["docker", "pull", "--platform=linux/amd64", reference], timeout=240)
        actual = json.loads(attempt.command(["docker", "image", "inspect", reference], sensitive=True).stdout)[0]
        require(actual["Architecture"] == "amd64" and actual["Os"] == "linux"
                and any(value.endswith("@" + reference.rsplit("@", 1)[1]) for value in actual["RepoDigests"]), "PINNED_AMD64_IMAGE_DIGEST")
        for role, expected in images.items():
            if reference == expected:
                attempt.identities[role] = actual["Id"]
                attempt.image_volumes[role] = set(actual["Config"].get("Volumes") or {})
    checks["pinnedImages"] = True
    attempt.command(["docker", "build", "--network=none", "--pull=false", "-f", str(build / "Dockerfile.trial9"), "-t", image, str(build)], timeout=240)
    built = json.loads(attempt.command(["docker", "image", "inspect", image], sensitive=True).stdout)[0]
    attempt.identities["spark"] = built["Id"]
    attempt.image_volumes["spark"] = set(built["Config"].get("Volumes") or {})
    password = secrets.token_hex(32)
    for name in ("postgres-secrets", "silver-secrets", "trino-config", "trino-config/catalog", "reader"):
        (root / name).mkdir(mode=0o755); os.chmod(root / name, 0o755)
    base.save(root / "postgres-secrets/bootstrap-password", secrets.token_hex(32).encode(), 0o444)
    base.save(root / "postgres-init.sql", base.pg_init(password), 0o444)
    base.save(root / "garage.toml", base.garage_config(), 0o444)
    for name, text in configuration().items():
        target = "catalog/iceberg.properties" if name == "iceberg.properties" else name
        base.save(root / "trino-config" / target, text.encode(), 0o444)
    for name in ("contract.py", "frozen_s3_primitives.py", "s3_readonly.py"):
        base.save(root / "reader" / name, (FROZEN / name).read_bytes(), 0o444)
    (root / "proof").mkdir(mode=0o777); os.chmod(root / "proof", 0o777)
    attempt.desired = plan(base_compose.plan, image, base.SPARK)
    base.save(root / "compose.json", attempt.desired)
    names = [project + "_" + value for value in ("postgres-data", "garage-meta", "garage-data")]
    found = attempt.command(["docker", "volume", "ls", "-q"], sensitive=True).stdout.decode().split()
    require(len(found) <= 512 and all(name not in found for name in names), "EXACT_NEW_NAMED_VOLUMES_ABSENT")
    attempt.prior_volumes = set(found)
    attempt.command_stage = "CREATE_BASE_SERVICES"
    attempt.cli("create", "--no-build", "postgres", "garage")
    network = json.loads(attempt.command(["docker", "network", "inspect", project + "_trial"]).stdout)[0]
    require(network["Internal"] is True and network["Labels"]["com.docker.compose.project"] == project, "ACTUAL_FRESH_INTERNAL_NETWORK")
    checks["internalNetwork"] = True
    for name in names:
        volume = json.loads(attempt.command(["docker", "volume", "inspect", name], sensitive=True).stdout)[0]
        require(volume["Name"] == name and volume["Driver"] == "local" and not volume["Options"]
                and volume["Labels"]["com.docker.compose.project"] == project, "FRESH_OWN_LOCAL_VOLUME_NO_EXTERNAL_SOURCE")
    checks["freshPhysicalVolumes"] = True
    attempt.command_stage = "INITIALIZER"
    base.save(root / "initializer-intent.json", {"name": attempt.initializer_name, "automaticRetry": False})
    attempt.initializer_intended = True
    attempt.command(["docker", "create", "--name", attempt.initializer_name, "--label", "devdooly.io.spark-ci-project=" + project,
                     "--cidfile", str(root / "initializer.cid"), "--network=none", "--read-only", "--memory=64m", "--cpus=0.1", "--pids-limit=16", "--cap-drop=ALL", "--cap-add=CHOWN",
                     "--security-opt=no-new-privileges:true", "--entrypoint=/bin/chown", "-v", names[1] + ":/meta", "-v", names[2] + ":/data", base.POSTGRES, "1000:1000", "/meta", "/data"])
    init = attempt.initializer(); require(init is not None and not init["running"], "BOUND_CREATED_VOLUME_INITIALIZER")
    attempt.command(["docker", "start", "-a", init["id"]])
    init = attempt.initializer(); require(init is not None and not init["running"] and init["exitCode"] == 0 and not init["oom"], "INITIALIZER_EXIT_ZERO")
    memory_available(); checks["actualMemAvailable7Gi"] = True
    started = time.monotonic(); attempt.deadline = Deadline(started)
    base.save(root / "proof/clock.json", {"startedMonotonic": started, "hostBootId": Path("/proc/sys/kernel/random/boot_id").read_text().strip(), "budgetSeconds": 600}, 0o444)
    checks["singleClock"] = True
    attempt.start("postgres"); attempt.start("garage")
    attempt.command_stage = "BASE_SERVICE_READINESS"
    until = time.monotonic() + attempt.deadline.remaining(60, 90)
    while True:
        require(time.monotonic() < until, "PG_AND_GARAGE_READY_DEADLINE")
        pg = attempt.cli("exec", "-T", "postgres", "pg_isready", "-h", "127.0.0.1", "-U", "lab_bootstrap", "-d", "iceberg_lab", check=False)
        node_result = attempt.cli("exec", "-T", "garage", "/garage", "-c", "/etc/garage.toml", "node", "id", "--quiet", check=False)
        if pg.returncode == node_result.returncode == 0: break
        time.sleep(1)
    attempt.command_stage = "GARAGE_SETUP"
    node = node_result.stdout.decode().strip().split("@")[0]
    require(re.fullmatch(r"[a-f0-9]{64}", node), "FRESH_GARAGE_NODE_ID")
    require(re.match(r"^17\.11(?:\s|$)", attempt.cli("exec", "-T", "postgres", "psql", "-X", "-A", "-t", "-U", "lab_bootstrap", "-d", "iceberg_lab", "-c", "SHOW server_version").stdout.decode().strip()), "POSTGRES_17_11")
    require(re.match(r"^garage v2\.4\.1(?:\s|$)", attempt.garage("--version").decode().strip()), "GARAGE_241")
    attempt.garage("layout", "assign", "-z", "fresh-cloud9", "-c", "128M", node)
    attempt.garage("layout", "apply", "--version", "1")
    bucket = json.loads(attempt.garage("json-api", "CreateBucket", '{"globalAlias":"platform-lab-iceberg-20261015"}'))
    require(re.fullmatch(r"[a-f0-9]{64}", bucket["id"]), "ACTUAL_NEW_PHYSICAL_BUCKET_ID")
    attempt.garage("json-api", "UpdateBucket", json.dumps({"id": bucket["id"], "body": {"quotas": {"maxSize": 64*1024**2, "maxObjects": 128}}}))
    key = json.loads(attempt.garage("json-api", "CreateKey", '{"name":"fresh-cloud-trial9"}', sensitive=True))
    attempt.garage("json-api", "AllowBucketKey", json.dumps({"bucketId": bucket["id"], "accessKeyId": key["accessKeyId"], "permissions": {"read": True, "write": True, "owner": False}}), sensitive=True)
    acl = json.loads(attempt.garage("json-api", "GetKeyInfo", json.dumps({"id": key["accessKeyId"], "showSecretKey": False}), sensitive=True))
    require(acl["accessKeyId"] == key["accessKeyId"] and acl["permissions"]["createBucket"] is False and len(acl["buckets"]) == 1
            and acl["buckets"][0]["id"] == bucket["id"] and acl["buckets"][0]["permissions"] == {"read": True, "write": True, "owner": False}, "ONE_FRESH_BUCKET_NONOWNER_READ_WRITE_KEY")
    endpoint = "http://garage.platform-lab.svc.cluster.local:3900"
    for name, value in {"catalog-password": password, "endpoint": endpoint, "access-key": key["accessKeyId"], "secret-key": key["secretAccessKey"]}.items():
        require(type(value) is str and re.fullmatch(r"[!-~]{1,512}", value), "ONE_LINE_PRIVATE_CREDENTIAL")
        base.save(root / "silver-secrets" / name, value.encode(), 0o444)
    env = {"CATALOG_PASSWORD": password, "S3_ENDPOINT": endpoint, "S3_BUCKET": "platform-lab-iceberg-20261015", "S3_ACCESS_KEY": key["accessKeyId"], "S3_SECRET_KEY": key["secretAccessKey"]}
    base.save(root / "trino.env", ("\n".join(name + "=" + value for name, value in env.items()) + "\n").encode(), 0o444)
    del key, password, env
    attempt.command_stage = "SPARK"
    attempt.cli("create", "--no-build", "spark")
    attempt.containers(); attempt.start("spark")
    captures["spark"] = attempt.wait_clean("spark", 180); checks["normalSparkExit"] = True
    spark = read_proof(root, "trial9-spark-result.json")
    diagnostic = read_proof(root, "trial9-spark-diagnostic.json")
    require(spark["passed"] is True and diagnostic["passed"] is True and diagnostic["sessionStopFailed"] is False
            and diagnostic["phase"] == "COMPLETED", "ACTUAL_SPARK_RESULT_AND_CLOSE_PROOF")
    snapshot_chain(spark["snapshots"], 3); files(spark["beforeFiles"], 2); files(spark["afterFiles"], 1)
    before_jdbc = jdbc(attempt); base.save(root / "jdbc-before-trino.private", before_jdbc)
    return spark, before_jdbc


def ready(trial, attempt):
    until = time.monotonic() + attempt.deadline.remaining(90, 90)
    while True:
        require(time.monotonic() < until, "TRINO_READY_DEADLINE")
        active = next(value for value in attempt.containers() if value["role"] == "trino")
        require(active["running"] and not active["oom"], "TRINO_RUNNING_DURING_STARTUP")
        health = attempt.cli("exec", "-T", "trino", "/usr/lib/trino/bin/health-check", timeout=5, check=False)
        if health.returncode == 0:
            return
        time.sleep(min(1, attempt.deadline.remaining(1, 90)))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-manifest-sha256", required=True)
    parser.add_argument("--ack-fresh-cloud-trino-restart", action="store_true", required=True)
    args = parser.parse_args()
    require(sys.platform == "linux" and os.environ.get("GITHUB_ACTIONS") == "true"
            and os.environ.get("RUNNER_ENVIRONMENT") == "github-hosted"
            and os.environ.get("GITHUB_REPOSITORY") == "DevDooly/devdooly-platform-lab"
            and os.environ.get("GITHUB_EVENT_NAME") == "workflow_dispatch"
            and os.environ.get("GITHUB_REF") == "refs/heads/main"
            and os.environ.get("GITHUB_RUN_ATTEMPT") == "1", "FIRST_MANUAL_MAIN_OWN_GITHUB_HOSTED_LINUX_ONLY")
    before = source_snapshot(args.source_manifest_sha256)
    sys.path.insert(0, str(FROZEN))
    trial = importlib.import_module("run_trial9")
    require(Path(trial.__file__).resolve() == FROZEN / "run_trial9.py", "EXACT_FROZEN_DRIVER_MODULE")
    from trino_lifecycle import BaseFacade, freeze_survivors, handoff_context, validate_resumed_container, verify_survivors
    source = os.environ.get("SOURCE_COMMIT", "")
    trial.checkout_source(REPO, source)
    base, base_compose, oracle = trial.source_inputs(REPO, FROZEN_MANIFEST)
    os.umask(0o077)
    local = REPO / ".local"
    local.mkdir(exist_ok=True)
    public = local / "cloud-trino-restart-public"
    public.mkdir(mode=0o700)
    nonce = uuid.uuid4().hex
    root = local / ("cloud-trino-restart-private-" + nonce)
    root.mkdir(mode=0o700)
    project = "cloud-trino-restart-" + nonce
    image = "spark-isolated-ci:" + nonce
    images = {"postgres": base.POSTGRES, "garage": base.GARAGE, "spark": image, "trino": trial.TRINO, "reader": base.SPARK}
    first_base = BaseFacade(base, root, "lifecycle-initial")
    current = trial.make_attempt(first_base, root, project, images)
    checks = {name: False for name in (
        "frozenInputs", "vendor", "pinnedImages", "freshPhysicalVolumes", "actualMemAvailable7Gi", "internalNetwork",
        "singleClock", "normalSparkExit", "normalTrinoExit", "pythonReaderExit", "jdbcAndWholeObjectsUnchanged",
        "oneOwnedTrinoReplacement", "survivingProcessesUnchanged", "bothTrinoReadContractsEqual")}
    captures = {}
    passed = False
    phase = "PREPARE"
    failure = None
    result = {}
    cleanup = {"initializerStopped": False, "ownedBoundContainersStopped": False, "unboundContainerObserved": False}
    source_unchanged = False
    try:
        spark, before_jdbc = prepare(trial, base, base_compose, oracle, root, project, image, images, current, checks, captures)
        phase = "TRINO_INITIAL"
        current.cli("create", "--no-build", "trino")
        current.containers()
        current.start("trino")
        ready(trial, current)
        initial = trial.verify_trino(current, spark, oracle, first_base, root)
        require(trial.jdbc(current) == before_jdbc, "INITIAL_JDBC_POINTERS_UNCHANGED")
        evidence = freeze_survivors(trial, current)
        base.save(root / "handoff-before.private.json", evidence)
        phase = "TERM_INITIAL"
        first_stop = trial.stop_normal_trino(current, first_base, root)
        phase = "HANDOFF"
        require(current.deadline.remaining(180, 90) == 180, "RESTART_STAGE_AND_CLEANUP_BUDGET_REQUIRED")
        current, resumed_base, handoff = handoff_context(trial, base, current, root, project, images, evidence, first_stop)
        # B owns cleanup before create; no original Attempt A method is called again.
        base.save(root / "handoff-after.private.json", handoff)
        trial.memory_available()
        require(current.deadline.remaining(180, 90) == 180, "RESTART_STAGE_AND_CLEANUP_BUDGET_REQUIRED")
        phase = "TRINO_RESUMED"
        current.cli("create", "--no-build", "trino")
        values = current.containers()
        validate_resumed_container(current, handoff, values)
        current.start("trino")
        checks["oneOwnedTrinoReplacement"] = True
        ready(trial, current)
        resumed = trial.verify_trino(current, spark, oracle, resumed_base, root)
        require(resumed == initial and trial.jdbc(current) == before_jdbc, "RESUMED_ROWS_METADATA_AND_JDBC_EQUAL")
        verify_survivors(trial, current, handoff, current.containers())
        checks["bothTrinoReadContractsEqual"] = True
        phase = "TERM_RESUMED"
        second_stop = trial.stop_normal_trino(current, resumed_base, root)
        checks["normalTrinoExit"] = True
        phase = "READER"
        current.command_stage = "READER"
        current.cli("create", "--no-build", "reader")
        current.containers()
        current.start("reader")
        current.wait_clean("reader", 60)
        checks["pythonReaderExit"] = True
        reader = trial.read_proof(root, "reader-result.json")
        require(reader["passed"] is True and reader["allPreTrinoBytesEqual"] is True and reader["onlyGetAndList"] is True
                and reader["oldObjects"] == spark["oldWarehouseObjects"] == 14
                and reader["wholeObjects"] == spark["afterWarehouseObjects"] == 20,
                "EXACT_ALL_WAREHOUSE_BYTES_UNCHANGED_AFTER_BOTH_LIFECYCLES")
        phase = "FINAL_VERIFY"
        require(trial.jdbc(current) == before_jdbc, "FINAL_JDBC_POINTERS_UNCHANGED")
        verify_survivors(trial, current, handoff, current.containers())
        checks["survivingProcessesUnchanged"] = True
        checks["jdbcAndWholeObjectsUnchanged"] = True
        result = {"initial": initial, "resumed": resumed, "intentionalTrinoReplacements": 1,
                  "initialActualExitCode": first_stop["exitCode"], "resumedActualExitCode": second_stop["exitCode"],
                  "bothStopsRequestedTerm": True, "signalDeliveryDirectlyObserved": False,
                  "oldWarehouseObjects": reader["oldObjects"], "wholeWarehouseObjects": reader["wholeObjects"]}
        passed = all(checks.values())
    except Exception as error:
        code = str(error)
        failure = code if re.fullmatch(r"[A-Z0-9_]{1,128}", code) else "CLOUD_RESTART_FAILED_OR_UNKNOWN_NO_RETRY"
    finally:
        current.safety_stop = True
        try:
            initializer = current.initializer()
            if initializer and initializer["running"]:
                current.command(["docker", "stop", "--time=10", initializer["id"]], timeout=15)
            initializer = current.initializer()
            cleanup["initializerStopped"] = initializer is None or not initializer["running"]
        except Exception:
            pass
        try:
            # Unbound live observations are never adopted as cleanup targets.
            bound_ids = {signature["id"] for signature in current.bound.values()}
            values = current.containers()
            cleanup["unboundContainerObserved"] = any(value["id"] not in bound_ids for value in values)
            for value in values:
                if value["running"] and value["id"] in bound_ids:
                    current.command(["docker", "stop", "--time=10", value["id"]], timeout=15)
            cleanup["ownedBoundContainersStopped"] = all(not value["running"] for value in current.containers())
        except Exception:
            pass
        try:
            source_unchanged = source_snapshot(args.source_manifest_sha256) == before
        except Exception:
            source_unchanged = False
        elapsed = None if current.deadline is None else int((time.monotonic() - current.deadline.started) * 1000)
        passed = passed and source_unchanged and cleanup["initializerStopped"] and cleanup["ownedBoundContainersStopped"]
        passed = passed and not cleanup["unboundContainerObserved"] and elapsed is not None and elapsed <= 600000
        if not passed and failure is None:
            failure = "FINAL_DEADLINE_CLEANUP_OR_SOURCE_UNVERIFIED"
        summary = {"schemaVersion": 1, "scope": SCOPE, "passed": passed, "sourceCommit": source,
                   "capturedAt": base.utc(), "phase": "COMPLETE" if passed else phase, "failureCode": failure,
                   "checks": checks, "result": result if passed else {}, "cleanup": cleanup,
                   "sourceBeforeAfterSame": source_unchanged, "workloadElapsedMillis": elapsed,
                   "workloadBudgetSeconds": 600, "buildAndPullExcludedFromWorkloadClock": True,
                   "plannedSequentialPeakMemoryBytes": 5 * 1024**3, "requiredActualMemAvailableBytes": 7 * 1024**3,
                   "onlyFreshCloudResources": True, "miniPcContacted": False, "automaticRetryPerformed": False,
                   "priorEvidenceModified": False, "rawLogsOrCredentialsUploaded": False,
                   "volumesDeleted": False, "snapshotExpirationOrObjectGcPerformed": False,
                   "runtimeAvailabilityOrPerformanceClaimed": False, "runnerStorageIsEphemeral": True}
        base.save(public / "summary.json", summary)
        print(json.dumps({"passed": passed, "scope": SCOPE, "phase": summary["phase"]}))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
