"""Manual hosted-only fresh resources; one tagged snapshot expiration, no retry."""
import argparse
import copy
import hashlib
import importlib
import json
import math
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
SCOPE = "FRESH_CLOUD_ICEBERG_TAGGED_SNAPSHOT_EXPIRATION"
FROZEN_MANIFEST = "c63aded0a891bb66cb1fb2de591d67e237467681eb4a4e5a337b9d1d1b02d5e8"
OWN_FILES = {"run_expiration.py", "bootstrap_expiration.py", "contract.py", "test_contract.py", "README.ko.md"}
FROZEN_FILES = {"infra/cloud-lakehouse-ci/" + name for name in (
    "contract.py", "compose_trial9.py", "frozen_s3_primitives.py", "pinned_trino_configuration.py",
    "s3_readonly.py", "bootstrap_trial9.py", "run_trial9.py", "runtime-manifest.json")}
FROZEN_FILES |= {"infra/spark-ci/" + name for name in ("run_ci.py", "compose_plan.py", "bootstrap_spark.py")}
FROZEN_FILES |= {"infra/spark-silver/" + name for name in (
    "spark_silver.py", "silver_contract.py", "artifact-lock.downloaded.json", "synthetic-v1.ndjson", "Dockerfile.candidate")}


def require(value, code):
    if not value:
        raise ValueError(code)


def source_snapshot(expected):
    raw = (HERE / "runtime-manifest.json").read_bytes()
    require(type(expected) is str and re.fullmatch(r"[a-f0-9]{64}", expected)
            and hashlib.sha256(raw).hexdigest() == expected, "EXACT_REVIEWED_EXPIRATION_MANIFEST")
    manifest = json.loads(raw)
    require(set(manifest) == {"schemaVersion", "scope", "status", "files", "frozenSources", "frozenRuntimeManifestSha256"}
            and manifest["schemaVersion"] == 1 and manifest["scope"] == SCOPE
            and manifest["status"] == "SOURCE_ONLY_NOT_RUN"
            and manifest["frozenRuntimeManifestSha256"] == FROZEN_MANIFEST
            and set(manifest["files"]) == OWN_FILES and set(manifest["frozenSources"]) == FROZEN_FILES,
            "EXACT_NEW_FIVE_AND_FROZEN_SIXTEEN_SOURCE_INVENTORY")
    values = {"runtime-manifest.json": raw}
    for prefix, root, pins in (("own:", HERE, manifest["files"]), ("frozen:", REPO, manifest["frozenSources"])):
        for name, pin in pins.items():
            data = (root / name).read_bytes()
            require(type(pin) is dict and set(pin) == {"sha256", "bytes"}
                    and type(pin["bytes"]) is int and len(data) == pin["bytes"]
                    and hashlib.sha256(data).hexdigest() == pin["sha256"], "EXACT_PINNED_SOURCE_BYTES")
            values[prefix + name] = data
    return values


def prepare(trial, base, base_compose, root, project, image, images, attempt, checks):
    # Required setup only, adapted explicitly from run_restart.prepare:60-172.
    # Its Spark execution and legacy three-snapshot verification are not reused.
    require(shutil.disk_usage(root).free >= 8 * 1024**3, "FRESH_CLOUD_DISK_RESERVE_8_GIB")
    for kind in ("container", "volume", "network"):
        prefix = ["docker", "ps", "-aq"] if kind == "container" else ["docker", kind, "ls", "-q"]
        require(not attempt.command([*prefix, "--filter", "label=com.docker.compose.project=" + project]).stdout.strip(),
                "UUID_PROJECT_ABSENT_BEFORE_CREATE")
    build = root / "build"
    build.mkdir(mode=0o700)
    packet = REPO / "infra/spark-silver"
    for name, digest in base.MODULES.items():
        raw = (packet / name).read_bytes()
        require(trial.sha(raw) == digest, "EXACT_SILVER_BUILD_INPUT")
        base.save(build / name, raw)
    base.save(build / "base_bootstrap.py", (REPO / "infra/spark-ci/bootstrap_spark.py").read_bytes())
    added = ("contract.py", "frozen_s3_primitives.py", "s3_readonly.py", "bootstrap_trial9.py")
    for name in added:
        base.save(build / name, (FROZEN / name).read_bytes())
    base.save(build / "expiration_contract.py", (HERE / "contract.py").read_bytes())
    base.save(build / "bootstrap_expiration.py", (HERE / "bootstrap_expiration.py").read_bytes())
    dockerfile = (build / "Dockerfile.candidate").read_bytes() + (
        "\nCOPY --chown=185:185 --chmod=0444 base_bootstrap.py " + " ".join(added)
        + " expiration_contract.py bootstrap_expiration.py /opt/silver/\n").encode()
    base.save(build / "Dockerfile.expiration", dockerfile)
    base.vendor(base.validated_lock((packet / "artifact-lock.downloaded.json").read_bytes()), build / "vendor")
    checks["vendor"] = True
    for reference in (base.POSTGRES, base.GARAGE, base.SPARK, trial.TRINO):
        attempt.command(["docker", "pull", "--platform=linux/amd64", reference], timeout=240)
        actual = json.loads(attempt.command(["docker", "image", "inspect", reference], sensitive=True).stdout)[0]
        require(actual["Architecture"] == "amd64" and actual["Os"] == "linux"
                and any(value.endswith("@" + reference.rsplit("@", 1)[1]) for value in actual["RepoDigests"]),
                "PINNED_AMD64_IMAGE_DIGEST")
        for role, expected in images.items():
            if reference == expected:
                attempt.identities[role] = actual["Id"]
                attempt.image_volumes[role] = set(actual["Config"].get("Volumes") or {})
    checks["pinnedImages"] = True
    attempt.command(["docker", "build", "--network=none", "--pull=false", "-f", str(build / "Dockerfile.expiration"),
                     "-t", image, str(build)], timeout=240)
    built = json.loads(attempt.command(["docker", "image", "inspect", image], sensitive=True).stdout)[0]
    attempt.identities["spark"] = built["Id"]
    attempt.image_volumes["spark"] = set(built["Config"].get("Volumes") or {})
    password = secrets.token_hex(32)
    for name in ("postgres-secrets", "silver-secrets", "trino-config", "trino-config/catalog", "reader"):
        (root / name).mkdir(mode=0o755)
        os.chmod(root / name, 0o755)
    base.save(root / "postgres-secrets/bootstrap-password", secrets.token_hex(32).encode(), 0o444)
    base.save(root / "postgres-init.sql", base.pg_init(password), 0o444)
    base.save(root / "garage.toml", base.garage_config(), 0o444)
    for name, text in trial.configuration().items():
        target = "catalog/iceberg.properties" if name == "iceberg.properties" else name
        base.save(root / "trino-config" / target, text.encode(), 0o444)
    for name in ("contract.py", "frozen_s3_primitives.py", "s3_readonly.py"):
        base.save(root / "reader" / name, (FROZEN / name).read_bytes(), 0o444)
    for name, target in (("contract.py", "expiration_contract.py"), ("bootstrap_expiration.py", "bootstrap_expiration.py")):
        base.save(root / "reader" / target, (HERE / name).read_bytes(), 0o444)
    (root / "proof").mkdir(mode=0o777)
    os.chmod(root / "proof", 0o777)
    attempt.desired = copy.deepcopy(trial.plan(base_compose.plan, image, base.SPARK))
    require(attempt.desired["services"]["spark"]["command"][-1] == "/opt/silver/bootstrap_trial9.py"
            and attempt.desired["services"]["reader"]["command"] == ["python3", "/reader/s3_readonly.py"],
            "EXACT_ORIGINAL_COMMANDS_BEFORE_EXPLICIT_NEW_ENTRYPOINTS")
    attempt.desired["services"]["spark"]["command"][-1] = "/opt/silver/bootstrap_expiration.py"
    attempt.desired["services"]["reader"]["command"] = ["python3", "-B", "/reader/bootstrap_expiration.py", "--reader"]
    base.save(root / "compose.json", attempt.desired)
    names = [project + "_" + value for value in ("postgres-data", "garage-meta", "garage-data")]
    found = attempt.command(["docker", "volume", "ls", "-q"], sensitive=True).stdout.decode().split()
    require(len(found) <= 512 and all(name not in found for name in names), "EXACT_NEW_NAMED_VOLUMES_ABSENT")
    attempt.prior_volumes = set(found)
    attempt.cli("create", "--no-build", "postgres", "garage")
    network = json.loads(attempt.command(["docker", "network", "inspect", project + "_trial"], sensitive=True).stdout)[0]
    require(network["Internal"] is True and network["Labels"]["com.docker.compose.project"] == project,
            "ACTUAL_FRESH_INTERNAL_NETWORK")
    checks["internalNetwork"] = True
    for name in names:
        volume = json.loads(attempt.command(["docker", "volume", "inspect", name], sensitive=True).stdout)[0]
        require(volume["Name"] == name and volume["Driver"] == "local" and not volume["Options"]
                and volume["Labels"]["com.docker.compose.project"] == project, "FRESH_OWN_LOCAL_VOLUME_NO_EXTERNAL_SOURCE")
    checks["freshPhysicalVolumes"] = True
    base.save(root / "initializer-intent.json", {"name": attempt.initializer_name, "automaticRetry": False})
    attempt.initializer_intended = True
    attempt.command(["docker", "create", "--name", attempt.initializer_name, "--label", "devdooly.io.spark-ci-project=" + project,
                     "--cidfile", str(root / "initializer.cid"), "--network=none", "--read-only", "--memory=64m", "--cpus=0.1",
                     "--pids-limit=16", "--cap-drop=ALL", "--cap-add=CHOWN", "--security-opt=no-new-privileges:true",
                     "--entrypoint=/bin/chown", "-v", names[1] + ":/meta", "-v", names[2] + ":/data", base.POSTGRES,
                     "1000:1000", "/meta", "/data"])
    init = attempt.initializer()
    require(init is not None and not init["running"], "BOUND_CREATED_VOLUME_INITIALIZER")
    attempt.command(["docker", "start", "-a", init["id"]])
    init = attempt.initializer()
    require(init is not None and not init["running"] and init["exitCode"] == 0 and not init["oom"], "INITIALIZER_EXIT_ZERO")
    trial.memory_available()
    checks["actualMemAvailable7Gi"] = True
    started = time.monotonic()
    attempt.deadline = trial.Deadline(started)
    base.save(root / "proof/clock.json", {"startedMonotonic": started,
              "hostBootId": Path("/proc/sys/kernel/random/boot_id").read_text().strip(), "budgetSeconds": 600}, 0o444)
    checks["singleClock"] = True
    attempt.start("postgres")
    attempt.start("garage")
    until = time.monotonic() + attempt.deadline.remaining(60, 90)
    while True:
        require(time.monotonic() < until, "PG_AND_GARAGE_READY_DEADLINE")
        pg = attempt.cli("exec", "-T", "postgres", "pg_isready", "-h", "127.0.0.1", "-U", "lab_bootstrap", "-d", "iceberg_lab", check=False)
        node_result = attempt.cli("exec", "-T", "garage", "/garage", "-c", "/etc/garage.toml", "node", "id", "--quiet", check=False)
        if pg.returncode == node_result.returncode == 0:
            break
        time.sleep(1)
    node = node_result.stdout.decode().strip().split("@")[0]
    require(re.fullmatch(r"[a-f0-9]{64}", node), "FRESH_GARAGE_NODE_ID")
    require(re.match(r"^17\.11(?:\s|$)", attempt.cli("exec", "-T", "postgres", "psql", "-X", "-A", "-t", "-U", "lab_bootstrap", "-d", "iceberg_lab", "-c", "SHOW server_version").stdout.decode().strip()), "POSTGRES_17_11")
    require(re.match(r"^garage v2\.4\.1(?:\s|$)", attempt.garage("--version").decode().strip()), "GARAGE_241")
    attempt.garage("layout", "assign", "-z", "fresh-expiration", "-c", "128M", node)
    attempt.garage("layout", "apply", "--version", "1")
    bucket = json.loads(attempt.garage("json-api", "CreateBucket", '{"globalAlias":"platform-lab-iceberg-20261015"}'))
    require(re.fullmatch(r"[a-f0-9]{64}", bucket["id"]), "ACTUAL_NEW_PHYSICAL_BUCKET_ID")
    attempt.garage("json-api", "UpdateBucket", json.dumps({"id": bucket["id"], "body": {"quotas": {"maxSize": 64 * 1024**2, "maxObjects": 128}}}))
    key = json.loads(attempt.garage("json-api", "CreateKey", '{"name":"fresh-expiration"}', sensitive=True))
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


def survivors(trial, attempt):
    values = {value["role"]: value for value in attempt.containers()}
    result = {}
    for role in ("postgres", "garage"):
        value = values[role]
        require(value["running"] is True and value["oom"] is False and type(value["pid"]) is int and value["pid"] > 0,
                "FRESH_PG_GARAGE_STILL_RUNNING")
        result[role] = {"id": value["id"], "pid": value["pid"], "startedAt": value["startedAt"],
                        "process": trial.process_identity(value["pid"], value["id"])}
    initializer = attempt.initializer()
    require(initializer is not None and not initializer["running"] and initializer["exitCode"] == 0 and not initializer["oom"],
            "SAME_SUCCESSFUL_OWN_INITIALIZER")
    result["initializer"] = initializer
    return result


def verify_trino(trial, attempt, spark, oracle, base, root):
    def query(name, sql, limit=19):
        require(sql.startswith("SELECT ") and ";" not in sql, "FIXED_TRINO_SELECT_ONLY")
        raw = attempt.cli("exec", "-T", "trino", "trino", "--server", "http://127.0.0.1:8080", "--user", "lab_operator",
                          "--output-format", "JSON", "--execute", sql, timeout=35).stdout
        base.save(root / ("expiration-trino-" + name + ".private.jsonl"), raw)
        return trial.parse_cli(raw, limit)
    require(query("version", "SELECT version() AS version") == [{"version": "483"}], "ACTUAL_TRINO_483")
    columns = ",".join(oracle.FIELDS)
    actual = query("current", "SELECT " + columns + " FROM iceberg.bronze.synthetic_events ORDER BY input_sequence")
    expected = spark["expectedRows"]
    require(type(expected) is list and len(expected) == 18 and len(actual) == 18, "EXACT_EIGHTEEN_CURRENT_ROWS")
    for value, golden in zip(actual, expected):
        require(set(value) == set(oracle.FIELDS) and type(value["input_sequence"]) is int
                and type(value["sensor_value"]) in (int, float) and math.isfinite(value["sensor_value"])
                and value == golden, "TRINO_CURRENT_ROWS_EQUAL_SPARK_ORACLE")
    require(query("double", "SELECT typeof(sensor_value) AS kind FROM iceberg.bronze.synthetic_events LIMIT 1") == [{"kind": "double"}], "TRINO_DOUBLE_SCHEMA")
    silver_rows = query("silver", "SELECT " + ",".join(oracle.OUTPUT_FIELDS) + " FROM iceberg.silver.sensor_outcomes ORDER BY input_sequence")
    normalized_silver = trial.rows(silver_rows, oracle.classify(oracle.golden_bronze()), True)
    require(trial.row_sha(normalized_silver) == spark["silverRowsSha256"], "TRINO_SILVER_ROWS_UNCHANGED")
    return {"currentRows": 18, "silverRows": 12, "selectInvocations": 4, "currentRowsSha256": trial.row_sha(actual)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-manifest-sha256", required=True)
    parser.add_argument("--ack-fresh-expiration", action="store_true", required=True)
    args = parser.parse_args()
    require(sys.platform == "linux" and os.environ.get("GITHUB_ACTIONS") == "true"
            and os.environ.get("RUNNER_ENVIRONMENT") == "github-hosted"
            and os.environ.get("GITHUB_REPOSITORY") == "DevDooly/devdooly-platform-lab"
            and os.environ.get("GITHUB_EVENT_NAME") == "workflow_dispatch"
            and os.environ.get("GITHUB_REF") == "refs/heads/main" and os.environ.get("GITHUB_RUN_ATTEMPT") == "1",
            "FIRST_MANUAL_MAIN_OWN_GITHUB_HOSTED_LINUX_ONLY")
    before = source_snapshot(args.source_manifest_sha256)
    sys.path.insert(0, str(FROZEN))
    trial = importlib.import_module("run_trial9")
    require(Path(trial.__file__).resolve() == FROZEN / "run_trial9.py", "EXACT_FROZEN_DRIVER_MODULE")
    source = os.environ.get("SOURCE_COMMIT", "")
    trial.checkout_source(REPO, source)
    base, base_compose, oracle = trial.source_inputs(REPO, FROZEN_MANIFEST)
    os.umask(0o077)
    local = REPO / ".local"
    local.mkdir(exist_ok=True)
    public = local / "cloud-expiration-public"
    public.mkdir(mode=0o700)
    nonce = uuid.uuid4().hex
    root = local / ("cloud-expiration-private-" + nonce)
    root.mkdir(mode=0o700)
    project, image = "cloud-expiration-" + nonce, "spark-isolated-ci:" + nonce
    images = {"postgres": base.POSTGRES, "garage": base.GARAGE, "spark": image, "trino": trial.TRINO, "reader": base.SPARK}
    attempt = trial.make_attempt(base, root, project, images)
    checks = {name: False for name in ("sourcePins", "vendor", "pinnedImages", "freshPhysicalVolumes", "actualMemAvailable7Gi",
        "internalNetwork", "singleClock", "normalSparkExit", "expirationVerified", "normalTrinoExit", "pythonReaderExit",
        "jdbcAndWholePostExpirationObjectsUnchanged", "survivingProcessesUnchanged")}
    checks["sourcePins"] = True
    phase, failure, passed, result = "PREPARE", None, False, {}
    cleanup = {"initializerStopped": False, "ownedBoundContainersStopped": False, "unboundContainerObserved": False}
    source_same, diagnostic, spark_start_requested = False, None, False
    try:
        prepare(trial, base, base_compose, root, project, image, images, attempt, checks)
        phase = "SPARK_EXPIRATION"
        attempt.cli("create", "--no-build", "spark")
        attempt.containers()
        spark_start_requested = True
        attempt.start("spark")
        attempt.wait_clean("spark", 180)
        checks["normalSparkExit"] = True
        diagnostic = trial.read_proof(root, "expiration-spark-diagnostic.json")
        spark = trial.read_proof(root, "expiration-spark-result.private.json")
        require(diagnostic["passed"] is True and diagnostic["expirationOutcome"] == "VERIFIED"
                and diagnostic["sessionStopFailed"] is False and spark["passed"] is True, "ACTUAL_EXPIRATION_AND_SPARK_CLOSE_VERIFIED")
        checks["expirationVerified"] = True
        before_jdbc = trial.jdbc(attempt)
        identity = survivors(trial, attempt)
        base.save(root / "pre-trino-survivors.private.json", identity)
        phase = "TRINO_READ_ONLY"
        attempt.cli("create", "--no-build", "trino")
        attempt.containers()
        attempt.start("trino")
        until = time.monotonic() + attempt.deadline.remaining(90, 90)
        while True:
            require(time.monotonic() < until, "TRINO_READY_DEADLINE")
            value = next(value for value in attempt.containers() if value["role"] == "trino")
            require(value["running"] and not value["oom"], "TRINO_RUNNING_DURING_READINESS")
            if attempt.cli("exec", "-T", "trino", "/usr/lib/trino/bin/health-check", timeout=5, check=False).returncode == 0:
                break
            time.sleep(1)
        trino = verify_trino(trial, attempt, spark, oracle, base, root)
        require(trial.jdbc(attempt) == before_jdbc and survivors(trial, attempt) == identity, "READ_ONLY_TRINO_PRESERVES_JDBC_AND_SURVIVORS")
        trial.stop_normal_trino(attempt, base, root)
        checks["normalTrinoExit"] = True
        phase = "READER_PRESERVATION"
        attempt.cli("create", "--no-build", "reader")
        attempt.containers()
        attempt.start("reader")
        attempt.wait_clean("reader", 60)
        checks["pythonReaderExit"] = True
        reader = trial.read_proof(root, "expiration-reader-result.json")
        require(reader["passed"] is True and reader["allPostExpirationBytesEqual"] is True
                and reader["removedDataStillNoSuchKey"] is True and reader["onlyGetAndList"] is True
                and trial.jdbc(attempt) == before_jdbc, "FINAL_POST_EXPIRATION_OBJECTS_AND_JDBC_PRESERVED")
        require(survivors(trial, attempt) == identity, "FINAL_PG_GARAGE_AND_INITIALIZER_UNCHANGED")
        checks["jdbcAndWholePostExpirationObjectsUnchanged"] = True
        checks["survivingProcessesUnchanged"] = True
        result = {key: spark[key] for key in ("expiredSnapshotCount", "retainedSnapshotCount", "deletedDataFiles",
                  "deletedManifests", "deletedManifestLists", "protectedObjectCount", "oldSurvivorObjectCount", "newMetadataObjectCount")}
        result.update(currentRows=trino["currentRows"], tagRows=6, retainedPreviousRows=12, silverRows=12,
                      trinoSelectInvocations=trino["selectInvocations"], postExpirationWholeObjects=reader["wholeObjects"])
        passed = all(checks.values())
    except Exception as error:
        text = str(error)
        failure = text if re.fullmatch(r"[A-Z0-9_]{1,128}", text) else "EXPIRATION_DRIVER_FAILED_OR_UNKNOWN_NO_RETRY"
        try:
            diagnostic = trial.read_proof(root, "expiration-spark-diagnostic.json")
        except Exception:
            diagnostic = None
    finally:
        attempt.safety_stop = True
        try:
            initializer = attempt.initializer()
            if initializer and initializer["running"]:
                attempt.command(["docker", "stop", "--time=10", initializer["id"]], timeout=15)
            initializer = attempt.initializer()
            cleanup["initializerStopped"] = initializer is None or not initializer["running"]
        except Exception:
            pass
        try:
            bound_ids = {value["id"] for value in attempt.bound.values()}
            values = attempt.containers()
            cleanup["unboundContainerObserved"] = any(value["id"] not in bound_ids for value in values)
            for value in values:
                if value["running"] and value["id"] in bound_ids:
                    attempt.command(["docker", "stop", "--time=10", value["id"]], timeout=15)
            cleanup["ownedBoundContainersStopped"] = all(not value["running"] for value in attempt.containers())
        except Exception:
            pass
        try:
            source_same = source_snapshot(args.source_manifest_sha256) == before
        except Exception:
            pass
        elapsed = None if attempt.deadline is None else int((time.monotonic() - attempt.deadline.started) * 1000)
        passed = passed and source_same and cleanup["initializerStopped"] and cleanup["ownedBoundContainersStopped"]
        passed = passed and not cleanup["unboundContainerObserved"] and elapsed is not None and elapsed <= 600000
        outcome = "UNKNOWN" if spark_start_requested else "NOT_ATTEMPTED"
        if diagnostic is not None and diagnostic.get("expirationVerified") is True and diagnostic.get("expirationOutcome") == "VERIFIED":
            outcome = "VERIFIED"
        elif diagnostic is not None and diagnostic.get("expirationInvoked") is False:
            outcome = "NOT_ATTEMPTED"
        if not passed and failure is None:
            failure = "FINAL_CLEANUP_DEADLINE_OR_SOURCE_UNVERIFIED"
        summary = {"schemaVersion": 1, "scope": SCOPE, "passed": passed, "sourceCommit": source,
                   "capturedAt": base.utc(), "phase": "COMPLETE" if passed else phase, "failureCode": failure,
                   "checks": checks, "result": result if passed else {}, "cleanup": cleanup,
                   "snapshotExpirationOutcome": outcome, "sparkStartRequested": spark_start_requested, "sourceBeforeAfterSame": source_same,
                   "workloadElapsedMillis": elapsed, "workloadBudgetSeconds": 600,
                   "buildAndPullExcludedFromWorkloadClock": True, "plannedSequentialPeakMemoryBytes": 5 * 1024**3,
                   "requiredActualMemAvailableBytes": 7 * 1024**3, "onlyFreshCloudResources": True,
                   "miniPcContacted": False, "priorEvidenceModified": False, "automaticRetryPerformed": False,
                   "rawLogsOrCredentialsUploaded": False, "volumesDeleted": False, "physicalStorageGcVerified": False,
                   "productionPlannerApplyEnabled": False, "runtimeAvailabilityOrPerformanceClaimed": False}
        base.save(public / "summary.json", summary)
        print(json.dumps({"passed": passed, "scope": SCOPE, "phase": summary["phase"]}))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
