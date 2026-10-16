"""One fresh GitHub-hosted Cloud9 attempt. No SSH, K8s, GHCR push or retry."""
import argparse
import importlib.util
import json
import os
from pathlib import Path
import re
import secrets
import shutil
import subprocess
import sys
import time
import uuid
from contract import Deadline, SCOPE, TRINO, files, normal_exit, parse_cli, query_plan, require, rows, row_sha, sha, snapshot_chain
from compose_trial9 import plan
from pinned_trino_configuration import configuration

HERE = Path(__file__).resolve().parent
BASE_PINS = {
    "infra/spark-ci/run_ci.py": "d190d5f39ca9232f6417319033c1d4f645966e318468d601eaba32a9b3a3d144",
    "infra/spark-ci/compose_plan.py": "fcaa911c8dcb9c6b56821ed3ff40d71c282658c8f5beb88200bff07c25336ee5",
    "infra/spark-ci/bootstrap_spark.py": "e10ef3cca6a71b7ce362ab769fdb1436e2b84bf3705e584d6d14c9173b0ab816",
    "infra/spark-silver/spark_silver.py": "71bd63230704c6d880eb1208abc63ef5080448cfd46bf3295f1bc77f38ddd9f7",
    "infra/spark-silver/silver_contract.py": "889fdb91ec4613d19f62a622e4cc889a27e38012905019f05d4743130f8268df",
    "infra/spark-silver/artifact-lock.downloaded.json": "6ca247b283025189ecf36c67ae03fe9101b25a53fe7b62593725e076276e33e3",
    "infra/spark-silver/synthetic-v1.ndjson": "39ba10d8c47dce790f3ccc9c9134fea593d6de31f1f3a7992ca61d9f554da3b5",
    "infra/spark-silver/Dockerfile.candidate": "334b4865c926062d40f25801e6c05a6390b9c957c87c4c7b3416aed62001bf24",
}
ROLES = {"postgres": (500000000, 512*1024**2, 256), "garage": (500000000, 512*1024**2, 256),
         "spark": (1000000000, 3*1024**3, 512), "trino": (1000000000, 4*1024**3, 512), "reader": (100000000, 128*1024**2, 16)}
PHASES = {"SESSION", "GZIP_DEFAULT", "FROZEN_WRITE_AND_SILVER", "BEFORE_COMPACTION_WHOLE_CAPTURE",
          "COMPACTION_ONCE", "THREE_SNAPSHOTS_AND_SILVER_VERIFY", "AFTER_COMPACTION_WHOLE_CAPTURE", "STOP_SESSION", "COMPLETED"}
COMMAND_STAGES = {"PREPARE", "CREATE_BASE_SERVICES", "INITIALIZER", "START_POSTGRES", "START_GARAGE",
                  "BASE_SERVICE_READINESS", "GARAGE_SETUP", "SPARK", "TRINO", "READER", "FINAL_VERIFY",
                  "FAILURE_LOG_CAPTURE", "CLEANUP_INITIALIZER", "CLEANUP_CONTAINERS", "UNCLASSIFIED_STAGE"}


def command_category(args):
    # Return fixed labels only. Never return an argument, path, role or message.
    if type(args) not in (list, tuple) or len(args) < 2 or args[0] != "docker": return "UNCLASSIFIED_COMMAND"
    if args[1] == "compose":
        action = args[6] if len(args) > 6 else None
        if action == "start":
            return {"postgres": "COMPOSE_START_POSTGRES", "garage": "COMPOSE_START_GARAGE", "spark": "COMPOSE_START_SPARK",
                    "trino": "COMPOSE_START_TRINO", "reader": "COMPOSE_START_READER"}.get(args[7] if len(args) == 8 else None, "COMPOSE_START_OTHER")
        return {"create": "COMPOSE_CREATE", "exec": "COMPOSE_EXEC"}.get(action, "COMPOSE_OTHER")
    pair = tuple(args[1:3])
    if pair in (("image", "inspect"), ("network", "inspect"), ("volume", "inspect"), ("volume", "ls")):
        return {("image", "inspect"): "IMAGE_INSPECT", ("network", "inspect"): "NETWORK_INSPECT",
                ("volume", "inspect"): "VOLUME_INSPECT", ("volume", "ls"): "VOLUME_INVENTORY"}[pair]
    return {"ps": "CONTAINER_INVENTORY", "inspect": "CONTAINER_INSPECT", "pull": "IMAGE_PULL", "build": "IMAGE_BUILD",
            "create": "CONTAINER_CREATE", "start": "CONTAINER_START", "stop": "CONTAINER_STOP"}.get(args[1], "UNCLASSIFIED_COMMAND")


def command_observation(sequence, stage, args, check):
    return {"sequence": sequence, "stage": stage if stage in COMMAND_STAGES else "UNCLASSIFIED_STAGE",
            "category": command_category(args), "checkRequested": bool(check), "returnCode": None, "timedOut": False, "outcome": "STARTED"}


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


def checkout_source(repo, source):
    require(re.fullmatch(r"[a-f0-9]{40}", source) and os.environ.get("GITHUB_SHA") == source, "EXACT_WORKFLOW_SOURCE_SHA")
    result = subprocess.run(["git", "-C", str(repo), "rev-parse", "HEAD"], stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE, timeout=5)
    require(result.returncode == 0 and len(result.stdout) <= 128 and len(result.stderr) <= 1024
            and result.stdout.decode("ascii").strip() == source, "ACTUAL_CHECKOUT_HEAD_MATCHES_WORKFLOW_SOURCE")


def source_inputs(repo, expected_manifest):
    require(re.fullmatch(r"[a-f0-9]{64}", expected_manifest), "EXPLICIT_NEW_PACKET_MANIFEST_SHA")
    raw = (HERE / "runtime-manifest.json").read_bytes()
    require(sha(raw) == expected_manifest, "EXACT_REVIEWED_CLOUD9_RUNTIME_MANIFEST")
    manifest = json.loads(raw)
    require(set(manifest) == {"schemaVersion", "scope", "status", "files", "basePins"}
            and manifest["schemaVersion"] == 1 and manifest["scope"] == SCOPE
            and manifest["status"] == "SOURCE_ONLY_NOT_RUN" and manifest["basePins"] == BASE_PINS, "EXACT_MANIFEST_SCOPE_AND_BASE_PINS")
    expected = {"contract.py", "compose_trial9.py", "frozen_s3_primitives.py", "pinned_trino_configuration.py", "s3_readonly.py", "bootstrap_trial9.py", "run_trial9.py"}
    require({value["path"] for value in manifest["files"]} == expected and len(manifest["files"]) == len(expected), "EXACT_SEVEN_RUNTIME_SOURCES")
    for row in manifest["files"]:
        value = (HERE / row["path"]).read_bytes()
        require(len(value) == row["bytes"] and sha(value) == row["sha256"], "ALL_REVIEWED_RUNTIME_BYTES")
    for name, digest in BASE_PINS.items():
        require(sha((repo / name).read_bytes()) == digest, "FROZEN_CLOUD8_INPUT_BYTES_UNCHANGED")
    sys.path.insert(0, str(repo / "infra/spark-ci"))
    base = load(repo / "infra/spark-ci/run_ci.py", "frozen_cloud8_helpers_only")
    base_compose = sys.modules["compose_plan"]
    require(Path(base_compose.__file__).resolve() == (repo / "infra/spark-ci/compose_plan.py").resolve(), "EXACT_BASE_COMPOSE_MODULE")
    sys.path.insert(0, str(repo / "infra/spark-silver"))
    oracle = load(repo / "infra/spark-silver/silver_contract.py", "frozen_cloud8_oracle")
    return base, base_compose, oracle


def memory_available():
    text = Path("/proc/meminfo").read_text("ascii")
    matches = re.findall(r"^MemAvailable:\s+([0-9]+) kB$", text, re.M)
    require(len(matches) == 1 and int(matches[0])*1024 >= 7*1024**3, "ACTUAL_MEMAVAILABLE_AT_LEAST_7_GIB")
    return int(matches[0])*1024


def mounts_verified(raw, desired, root, project, declared, prior_volumes):
    # Compose can use the Engine Mounts API instead of HostConfig.Binds. Bind to
    # actual mounts semantically, including image-declared fresh anonymous ones.
    expected = {}
    for item in desired["volumes"]:
        pieces = item.split(":")
        bind = pieces[0].startswith("./")
        source = str(root / pieces[0][2:]) if bind else project + "_" + pieces[0]
        expected[pieces[1]] = ("bind" if bind else "volume", source, pieces[2] != "ro" if len(pieces) == 3 else True)
    tmpfs = {item.split(":", 1)[0] for item in desired.get("tmpfs", [])}
    require(set(raw["HostConfig"].get("Tmpfs") or {}) == tmpfs, "EXACT_ROLE_TMPFS_TARGETS")
    seen = set()
    for mount in raw["Mounts"]:
        destination, kind = mount["Destination"], mount["Type"]
        require(destination not in seen and type(mount["RW"]) is bool, "UNIQUE_ACTUAL_MOUNT_TARGETS")
        seen.add(destination)
        if destination in expected:
            expected_kind, source, writable = expected[destination]
            require(kind == expected_kind and mount["RW"] == writable, "ACTUAL_MOUNT_TYPE_AND_RO_RW")
            if kind == "bind": require(mount["Source"] == source, "EXACT_PRIVATE_FRESH_BIND_PATH")
            else: require(mount["Name"] == source and mount["Driver"] == "local", "EXACT_OWN_NAMED_LOCAL_VOLUME")
        elif destination in tmpfs:
            require(kind == "tmpfs", "ONLY_DECLARED_TMPFS_MOUNT")
        else:
            require(destination in declared and kind == "volume" and mount["Driver"] == "local"
                    and re.fullmatch(r"[a-f0-9]{64}", mount["Name"]) and mount["Name"] not in prior_volumes,
                    "ONLY_FRESH_IMAGE_DECLARED_ANONYMOUS_VOLUME")
    require(set(expected).issubset(seen), "ALL_REQUESTED_MOUNTS_OBSERVED")


def canonical_mounts(mounts):
    require(type(mounts) is list and all(type(member) is dict for member in mounts), "WHOLE_MOUNT_MEMBERS_REQUIRED")
    # Preserve every field, JSON type and duplicate. Only the member ordering
    # is removed; raw mounts still undergo all semantic/ownership checks.
    return sorted(json.dumps(member, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False)
                  for member in mounts)


def canonical_host(host):
    require(type(host) is dict and "OomKillDisable" in host
            and (host["OomKillDisable"] is None or host["OomKillDisable"] is False),
            "PRESENT_ENABLED_OOM_KILLER_REPRESENTATION_REQUIRED")
    # Only present null/false mean no OOM-killer disabling. Keep every other
    # field, nested value, JSON type, duplicate array member and array order.
    # A new dict leaves the actual inspect object untouched.
    return json.dumps({**host, "OomKillDisable": False}, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True, allow_nan=False)


def make_attempt(base, root, project, images):
    class Attempt(base.Attempt):
        def __init__(self):
            super().__init__(root, project)
            self.deadline = None
            self.started_roles = set()
            self.bound = {}
            self.identities = {}
            self.safety_stop = False
            self.desired = None
            self.image_volumes = {}
            self.prior_volumes = set()
            self.trino_stop = None
            self.command_stage = "PREPARE"
            self.last_command = None
            self.command_failures = []
            self.command_failures_truncated = False

        def command_diagnostics(self):
            return {"lastCommand": dict(self.last_command) if self.last_command else None,
                    "failures": [dict(value) for value in self.command_failures],
                    "failuresTruncated": self.command_failures_truncated}

        def remember_command_failure(self, observation):
            if len(self.command_failures) < 16: self.command_failures.append(dict(observation))
            else: self.command_failures_truncated = True

        def command(self, args, timeout=60, sensitive=False, check=True):
            if self.deadline and not self.safety_stop:
                timeout = self.deadline.remaining(timeout, 60)
            elif self.safety_stop:
                timeout = min(timeout, 15 if args[:2] == ["docker", "stop"] else 5)
            self.sequence += 1
            observation = command_observation(self.sequence, self.command_stage, args, check)
            self.last_command = observation
            base.save(root / ("command-%03d-intent.json" % self.sequence), {"sequence": self.sequence,
                      "timeoutSeconds": timeout, "outputPrivateOnly": True, "sensitiveOutputSkipped": sensitive, "automaticRetry": False})
            try:
                result = subprocess.run(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=timeout)
                observation["returnCode"] = result.returncode
                observation["outcome"] = "RETURNED_ZERO" if result.returncode == 0 else "RETURNED_NONZERO"
                if len(result.stdout) > 8*1024**2 or len(result.stderr) > 8*1024**2: observation["outcome"] = "OUTPUT_BOUND_EXCEEDED"
                require(len(result.stdout) <= 8*1024**2 and len(result.stderr) <= 8*1024**2, "COMMAND_OUTPUT_BOUND")
                if not sensitive:
                    base.save(root / ("command-%03d.stdout" % self.sequence), result.stdout)
                    base.save(root / ("command-%03d.stderr" % self.sequence), result.stderr)
                require(not check or result.returncode == 0, "OWN_FRESH_COMMAND_FAILED_NO_RETRY")
                return result
            except subprocess.TimeoutExpired:
                observation.update(outcome="TIMED_OUT", timedOut=True)
                self.remember_command_failure(observation)
                raise
            except Exception:
                if observation["outcome"] == "STARTED": observation["outcome"] = "START_FAILED"
                elif observation["outcome"] == "RETURNED_ZERO": observation["outcome"] = "COMMAND_PROCESSING_FAILED"
                self.remember_command_failure(observation)
                raise

        def containers(self):
            ids = self.command(["docker", "ps", "-aq", "--no-trunc", "--filter", "label=com.docker.compose.project=" + project]).stdout.decode().split()
            require(len(ids) <= 5 and all(re.fullmatch(r"[a-f0-9]{64}", value) for value in ids), "ONLY_FIVE_FRESH_PROJECT_ROLES")
            values = []
            for cid in ids:
                raw = json.loads(self.command(["docker", "inspect", cid], sensitive=True).stdout)[0]
                labels, host = raw["Config"]["Labels"], raw["HostConfig"]
                role = labels.get("com.docker.compose.service")
                require(raw["Id"] == cid and labels.get("com.docker.compose.project") == project and role in ROLES,
                        "EXACT_OWN_ROLE_AND_FULL_CID")
                require(raw["Config"]["Image"] == images[role] and raw["Image"] == self.identities[role]
                        and host["ReadonlyRootfs"] is True and host["Privileged"] is False
                        and not host.get("PortBindings") and host["NetworkMode"] == project + "_trial"
                        and list(raw["NetworkSettings"]["Networks"]) == [project + "_trial"], "PINNED_IMAGE_AND_ONLY_OWN_INTERNAL_NETWORK")
                require((host["NanoCpus"], host["Memory"], host["PidsLimit"]) == ROLES[role]
                        and type(host["PidsLimit"]) is int, "EXACT_ROLE_CPU_MEMORY_PID_LIMITS")
                require(raw["RestartCount"] == 0 and host["RestartPolicy"]["Name"] == "no", "NO_AUTOMATIC_CONTAINER_RESTART")
                if role == "trino":
                    require(raw["Config"].get("StopSignal") in (None, "", "SIGTERM", "15"), "TRINO_CONFIGURED_OR_DEFAULT_TERM_ONLY")
                desired = self.desired["services"][role]
                require("command" not in desired or raw["Config"]["Cmd"] == desired["command"], "ACTUAL_FIXED_ROLE_COMMAND")
                if "entrypoint" in desired:
                    actual_entrypoint = raw["Config"]["Entrypoint"]
                    require(actual_entrypoint == desired["entrypoint"] or desired["entrypoint"] == []
                            and actual_entrypoint is None, "EXACT_ROLE_ENTRYPOINT")
                require("user" not in desired or raw["Config"]["User"] == desired["user"], "ACTUAL_ROLE_UID_GID")
                mounts_verified(raw, desired, root, project, self.image_volumes[role], self.prior_volumes)
                signature = {"id": cid, "imageId": raw["Image"], "config": raw["Config"], "host": canonical_host(host),
                             "mounts": canonical_mounts(raw["Mounts"]), "created": raw["Created"]}
                if role in self.bound:
                    require(self.bound[role] == signature, "SAME_OWN_CONTAINER_FULL_CONFIGURATION")
                else:
                    self.bound[role] = signature
                values.append({"id": cid, "role": role, "running": raw["State"]["Running"],
                               "exitCode": raw["State"]["ExitCode"], "oom": raw["State"]["OOMKilled"],
                               "pid": raw["State"]["Pid"], "startedAt": raw["State"]["StartedAt"]})
            require(len({value["role"] for value in values}) == len(values), "ONE_CONTAINER_EACH_ROLE")
            require(sum(value["running"] for value in values if value["role"] in ("spark", "trino")) <= 1, "NO_CONCURRENT_HEAVY_JVMS")
            if any(value["running"] for value in values if value["role"] == "reader"):
                require(not any(value["running"] for value in values if value["role"] in ("spark", "trino")), "PYTHON_READER_ONLY_AFTER_HEAVY_STOP")
            if values:
                network = json.loads(self.command(["docker", "network", "inspect", project + "_trial"], sensitive=True).stdout)[0]
                require(network["Internal"] is True and network["Labels"]["com.docker.compose.project"] == project
                        and set(network["Containers"]).issubset(set(ids)), "NO_FOREIGN_CONTAINER_ON_FRESH_INTERNAL_NETWORK")
            return values

        def start(self, role):
            require(role in ROLES and role not in self.started_roles, "ONE_EXPLICIT_START_EACH_FRESH_ROLE")
            self.command_stage = {"postgres": "START_POSTGRES", "garage": "START_GARAGE", "spark": "SPARK", "trino": "TRINO", "reader": "READER"}[role]
            self.deadline.remaining(180, 90)
            existing = {value["role"]: value for value in self.containers()}
            if role == "trino":
                require("spark" in existing and not existing["spark"]["running"]
                        and existing["spark"]["exitCode"] == 0 and existing["spark"]["oom"] is False, "SPARK_NORMAL_EXIT_BEFORE_TRINO")
            if role == "reader":
                require(all(name in existing for name in ("spark", "trino")), "BOTH_HEAVY_ROLES_EXIST_BEFORE_READER")
                normal_exit("spark", existing["spark"])
                normal_exit("trino", existing["trino"], self.trino_stop)
            target = existing.get(role)
            require(target is not None and re.fullmatch(r"[a-f0-9]{64}", target["id"])
                    and role in self.bound and target["id"] == self.bound[role]["id"]
                    and target["running"] is False and target["oom"] is False and target["exitCode"] == 0
                    and type(target["pid"]) is int and target["pid"] == 0
                    and target["startedAt"] == "0001-01-01T00:00:00Z", "EXACT_BOUND_CREATED_CONTAINER_BEFORE_FIRST_START")
            base.save(root / ("start-" + role + "-intent.json"), {"role": role, "automaticRetry": False})
            self.started_roles.add(role)
            self.command(["docker", "start", target["id"]])

        def wait_clean(self, role, maximum):
            until = time.monotonic() + self.deadline.remaining(maximum, 90)
            while True:
                require(time.monotonic() < until, "ROLE_WAIT_DEADLINE_NO_RETRY")
                current = next(value for value in self.containers() if value["role"] == role)
                if not current["running"]:
                    return normal_exit(role, current, self.trino_stop)
                time.sleep(min(1, self.deadline.remaining(1, 90)))

    return Attempt()


def process_identity(pid, cid):
    require(type(pid) is int and pid > 1, "EXACT_LIVE_TRINO_HOST_PID")
    require(re.fullmatch(r"[a-f0-9]{64}", cid), "EXACT_TRINO_FULL_CONTAINER_ID")
    path = Path("/proc") / str(pid) / "stat"
    cgroup_path = path.with_name("cgroup")
    first = path.read_text("ascii"); group = cgroup_path.read_text("ascii")
    second = path.read_text("ascii"); group_after = cgroup_path.read_text("ascii")
    def fields(text):
        require(text.split(" ", 1)[0] == str(pid) and ") " in text, "PROC_STAT_EXACT_PID")
        values = text.rsplit(") ", 1)[1].split()
        require(len(values) >= 20 and values[0] not in ("Z", "X") and values[19].isdecimal(), "LIVE_PROC_START_TICKS")
        return int(values[19])
    ticks = fields(first)
    require(ticks == fields(second), "SAME_LIVE_TRINO_PID_START_TICKS")
    require(group == group_after and 0 < len(group) <= 16384 and 1 <= len(group.splitlines()) <= 32
            and all(len(line.split(":", 2)) == 3 for line in group.splitlines()), "STABLE_BOUNDED_OWN_PROCESS_CGROUP")
    component = re.compile(r"(?:^|/)(?:docker-|cri-containerd-)?" + cid + r"(?:\.scope)?(?:/|$)")
    require(any(component.search(line.split(":", 2)[2]) for line in group.splitlines()), "HOST_PID_BELONGS_TO_EXACT_OWN_CONTAINER_CGROUP")
    return {"pid": pid, "startTicks": ticks, "hostBootId": Path("/proc/sys/kernel/random/boot_id").read_text().strip(),
            "cgroupSha256": sha(group.encode())}


def stop_normal_trino(attempt, base, root):
    before = next(value for value in attempt.containers() if value["role"] == "trino")
    require(before["running"] is True and before["oom"] is False, "EXACT_TRINO_RUNNING_BEFORE_EXPLICIT_STOP")
    identity = process_identity(before["pid"], before["id"])
    again = next(value for value in attempt.containers() if value["role"] == "trino")
    require((again["id"], again["pid"], again["startedAt"], again["running"]) == (before["id"], before["pid"], before["startedAt"], True)
            and process_identity(again["pid"], again["id"]) == identity, "SAME_TRINO_CID_PID_BEFORE_STOP")
    record = {"cid": before["id"], "startedAt": before["startedAt"], **identity,
              "signalScope": "CONFIGURED_OR_DEFAULT_SIGTERM", "graceSeconds": 30,
              "signalDeliveryDirectlyObserved": False, "automaticRetry": False}
    base.save(root / "trino-normal-stop-intent.json", record)
    result = attempt.command(["docker", "stop", "--time=30", before["id"]], timeout=40)
    require(result.returncode == 0, "EXPLICIT_TRINO_STOP_RETURNED_ZERO")
    attempt.trino_stop = dict(record, requestReturnedZero=True)
    after = attempt.wait_clean("trino", 10)
    base.save(root / "trino-normal-stop-result.json", dict(attempt.trino_stop, actualExitCode=after["exitCode"], nonOom=True))
    return after


def read_proof(root, name, maximum=65536):
    path = root / "proof" / name
    require(path.is_file() and not path.is_symlink(), "REGULAR_NEW_PRIVATE_PROOF")
    raw = path.read_bytes()
    require(0 < len(raw) <= maximum, "BOUNDED_NEW_PRIVATE_PROOF")
    return json.loads(raw)


def jdbc(attempt):
    query = "SELECT catalog_name,table_namespace,table_name,metadata_location,previous_metadata_location FROM iceberg_tables ORDER BY catalog_name,table_namespace,table_name"
    raw = attempt.cli("exec", "-T", "postgres", "psql", "-X", "-A", "-t", "-U", "lab_bootstrap", "-d", "iceberg_lab", "-c", query).stdout
    require(0 < len(raw) < 16384 and len(raw.decode().splitlines()) == 2, "EXACT_TWO_JDBC_TABLE_POINTERS")
    return raw


def verify_trino(attempt, spark, oracle, base, root):
    chain = snapshot_chain(spark["snapshots"], 3)
    results = {}
    for name, sql in query_plan(chain):
        base.save(root / ("trino-" + name + "-intent.json"), {"sqlSha256": sha(sql.encode()), "automaticRetry": False})
        raw = attempt.cli("exec", "-T", "trino", "/usr/bin/trino", "--server", "http://127.0.0.1:8080", "--user", "lab_operator", "--output-format", "JSON", "--execute", sql, timeout=35).stdout
        results[name] = parse_cli(raw)
    require(results["version"] == [{"version": "483"}] and results["bronze-double"] == results["silver-double"] == [{"kind": "double"}], "ACTUAL_TRINO_483_AND_DOUBLE_SCHEMAS")
    golden = oracle.golden_bronze()
    fingerprints = []
    for index in range(3):
        actual = rows(results["snapshot-%d" % (index + 1)], golden[:6] if index == 0 else golden)
        fingerprints.append(row_sha(actual))
    require(fingerprints == spark["rowFingerprints"] and row_sha(rows(results["current-bronze"], golden)) == fingerprints[-1], "ALL_THREE_CROSS_ENGINE_ROWS_AND_HASHES")
    require(row_sha(rows(results["current-silver"], oracle.classify(golden), True)) == spark["silverRowsSha256"], "CROSS_ENGINE_EXACT_SILVER_OUTCOMES")
    require(snapshot_chain(results["snapshots"], 3) == chain and files(results["files"], 1) == spark["afterFiles"], "TRINO_CURRENT_SNAPSHOT_AND_FILE_METADATA")
    return {"queryCount": len(results), "rowCounts": [6, 12, 12], "rowFingerprints": fingerprints,
            "snapshotIds": [value["snapshot_id"] for value in chain], "currentFiles": 1, "silverRows": 12}


def capture_private_tail(base, root, attempt, expected):
    before = next(value for value in attempt.containers() if value["role"] == expected["role"])
    require(before["id"] == expected["id"], "EXACT_OWN_LOG_FULL_CID")
    captured = base.bounded_deadline_logs(before["id"])
    after = next(value for value in attempt.containers() if value["role"] == expected["role"])
    require(after["id"] == before["id"], "SAME_OWN_LOG_FULL_CID_AFTER_CAPTURE")
    require(captured.returncode == 0 and not captured.capture_truncated and not captured.capture_timed_out,
            "COMPLETE_BOUNDED_PRIVATE_LOG_CAPTURE")
    base.save(root / ("failure-tail-" + before["role"] + ".stdout.private"), captured.stdout)
    base.save(root / ("failure-tail-" + before["role"] + ".stderr.private"), captured.stderr)


def safe_bootstrap(base, value):
    require(type(value) is dict and set(value) == {"passed", "phase", "sessionStopFailed", "exceptionClassesOnly", "fixedFailureCode", "elapsedMillis"}, "EXACT_NEW_BOOTSTRAP_DIAGNOSTIC_FIELDS")
    require(type(value["passed"]) is bool and type(value["sessionStopFailed"]) is bool and value["phase"] in PHASES
            and type(value["elapsedMillis"]) is int and 0 <= value["elapsedMillis"] <= 3600000, "FIXED_SAFE_BOOTSTRAP_PHASE_AND_COUNTS")
    error = value["exceptionClassesOnly"]
    if error is not None:
        require(type(error) is dict and set(error) == {"pythonExceptionClass", "javaCauseClasses", "nativeLibraryCategories", "failedMapSegmentObserved"}
                and error["pythonExceptionClass"] in base.PYTHON_EXCEPTIONS
                and type(error["javaCauseClasses"]) is list and len(error["javaCauseClasses"]) <= 8
                and all(type(item) is str and len(item) <= 160 and base.JAVA_CLASS.fullmatch(item) for item in error["javaCauseClasses"])
                and type(error["nativeLibraryCategories"]) is list and set(error["nativeLibraryCategories"]).issubset({"zstd", "snappy", "lz4", "hadoop"})
                and type(error["failedMapSegmentObserved"]) is bool, "MESSAGE_FREE_EXCEPTION_CLASS_ALLOWLIST")
    require(value["passed"] == (error is None and not value["sessionStopFailed"]), "DIAGNOSTIC_PASS_AND_ERROR_CONSISTENT")
    return {key: value[key] for key in ("passed", "phase", "sessionStopFailed", "exceptionClassesOnly", "elapsedMillis")}


def safe_progress(root):
    candidates = sorted((root / "proof").glob("trial9-progress-*.json"))
    require(len(candidates) <= 9, "AT_MOST_NINE_PROGRESS_FILES")
    result = None
    for index, path in enumerate(candidates, 1):
        require(path.name == "trial9-progress-%02d.json" % index and not path.is_symlink(), "CONTIGUOUS_COMPLETE_PROGRESS_FILES")
        raw = path.read_bytes(); require(0 < len(raw) <= 1024, "BOUNDED_FIXED_PROGRESS")
        value = json.loads(raw)
        require(set(value) == {"phase", "sequence", "completionNotProven", "elapsedMillis"} and value["phase"] in PHASES
                and type(value["sequence"]) is int and value["sequence"] == index and value["completionNotProven"] is True
                and type(value["elapsedMillis"]) is int and 0 <= value["elapsedMillis"] <= 3600000, "FIXED_PROGRESS_SCOPE_ONLY")
        result = value
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-manifest-sha256", required=True)
    parser.add_argument("--ack-fresh-cloud-trial9", action="store_true", required=True)
    args = parser.parse_args()
    require(sys.platform == "linux" and os.environ.get("GITHUB_ACTIONS") == "true"
            and os.environ.get("RUNNER_ENVIRONMENT") == "github-hosted", "GITHUB_HOSTED_LINUX_ONLY")
    source = os.environ.get("SOURCE_COMMIT", "")
    require(re.fullmatch(r"[a-f0-9]{40}", source), "ACTUAL_CHECKOUT_SOURCE_COMMIT")
    os.umask(0o077)
    repo = HERE.parents[1]
    checkout_source(repo, source)
    base, base_compose, oracle = source_inputs(repo, args.source_manifest_sha256)
    local = repo / ".local"; local.mkdir(exist_ok=True)
    public = local / "cloud-trial9-public"; public.mkdir(mode=0o700)
    nonce = uuid.uuid4().hex
    root = local / ("cloud-trial9-private-" + nonce); root.mkdir(mode=0o700)
    project, image = "cloud-trial9-" + nonce, "spark-isolated-ci:" + nonce
    images = {"postgres": base.POSTGRES, "garage": base.GARAGE, "spark": image, "trino": TRINO, "reader": base.SPARK}
    attempt = make_attempt(base, root, project, images)
    passed, stopped, initializer_stopped, failure, result = False, False, False, None, {}
    captures, started = {}, None
    public_diagnostic, progress = None, None
    cleanup_diagnostics = {"initializer": "NOT_OBSERVED", "containers": "NOT_OBSERVED"}
    checks = {name: False for name in ("frozenInputs", "vendor", "pinnedImages", "freshPhysicalVolumes", "actualMemAvailable7Gi", "internalNetwork", "singleClock", "normalSparkExit", "normalTrinoExit", "pythonReaderExit", "jdbcAndWholeObjectsUnchanged")}
    try:
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
        for name in added: base.save(build / name, (HERE / name).read_bytes())
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
            base.save(root / "reader" / name, (HERE / name).read_bytes(), 0o444)
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
        attempt.command_stage = "TRINO"
        attempt.cli("create", "--no-build", "trino"); attempt.containers(); attempt.start("trino")
        until = time.monotonic() + attempt.deadline.remaining(90, 90)
        while True:
            require(time.monotonic() < until, "TRINO_READY_DEADLINE")
            active = next(value for value in attempt.containers() if value["role"] == "trino")
            require(active["running"] and not active["oom"], "TRINO_RUNNING_DURING_STARTUP")
            health = attempt.cli("exec", "-T", "trino", "/usr/lib/trino/bin/health-check", timeout=5, check=False)
            if health.returncode == 0: break
            time.sleep(1)
        result = verify_trino(attempt, spark, oracle, base, root)
        require(jdbc(attempt) == before_jdbc, "JDBC_POINTERS_UNCHANGED_BY_TRINO_SELECTS")
        captures["trino"] = stop_normal_trino(attempt, base, root); checks["normalTrinoExit"] = True
        attempt.command_stage = "READER"
        attempt.cli("create", "--no-build", "reader"); attempt.containers(); attempt.start("reader")
        captures["reader"] = attempt.wait_clean("reader", 60); checks["pythonReaderExit"] = True
        reader = read_proof(root, "reader-result.json")
        require(reader["passed"] is True and reader["allPreTrinoBytesEqual"] is True and reader["onlyGetAndList"] is True
                and reader["oldObjects"] == spark["oldWarehouseObjects"] and reader["wholeObjects"] == spark["afterWarehouseObjects"], "ACTUAL_WHOLE_OBJECT_COMPARISON_AFTER_TRINO")
        attempt.command_stage = "FINAL_VERIFY"
        require(jdbc(attempt) == before_jdbc, "FINAL_JDBC_POINTERS_UNCHANGED")
        checks["jdbcAndWholeObjectsUnchanged"] = True
        result.update({"oldWarehouseObjects": reader["oldObjects"], "postTrinoWholeObjects": reader["wholeObjects"],
                       "procedureInvocations": 1, "rewrittenDataFiles": 2, "addedDataFiles": 1,
                       "silverSuccess": 7, "silverFailure": 3, "silverDuplicate": 2, "silverPending": 0,
                       "trinoStop": {"requestedSeconds": 30, "requestReturnedZero": True,
                                     "actualExitCode": captures["trino"]["exitCode"], "nonOom": True,
                                     "signalScope": "CONFIGURED_OR_DEFAULT_SIGTERM", "signalDeliveryDirectlyObserved": False}})
        passed = True
    except Exception as error:
        text = str(error)
        failure = {"type": type(error).__name__, "code": text if re.fullmatch(r"[A-Z0-9_]{1,128}", text) else "CLOUD9_FAILED_OR_UNKNOWN_NO_RETRY"}
    finally:
        attempt.safety_stop = True
        try:
            progress = safe_progress(root)
        except Exception:
            progress = None
        try:
            public_diagnostic = safe_bootstrap(base, read_proof(root, "trial9-spark-diagnostic.json"))
        except Exception:
            public_diagnostic = None
        try:
            # Private bounded diagnostics precede any owned stop. No message is public.
            if not passed:
                attempt.command_stage = "FAILURE_LOG_CAPTURE"
                for value in attempt.containers():
                    if value["role"] in ("spark", "trino", "reader"):
                        capture_private_tail(base, root, attempt, value)
        except Exception:
            pass
        try:
            attempt.command_stage = "CLEANUP_INITIALIZER"
            init = attempt.initializer()
            if init and init["running"]: attempt.command(["docker", "stop", "--time=10", init["id"]], timeout=15)
            require(attempt.initializer() is None or not attempt.initializer()["running"], "OWN_INITIALIZER_STOPPED")
            initializer_stopped = True
            cleanup_diagnostics["initializer"] = "STOPPED_VERIFIED"
        except Exception:
            passed = False
            cleanup_diagnostics["initializer"] = "FAILED_OR_UNOBSERVED"
        try:
            attempt.command_stage = "CLEANUP_CONTAINERS"
            for value in attempt.containers():
                if value["running"]: attempt.command(["docker", "stop", "--time=10", value["id"]], timeout=15)
            require(all(not value["running"] for value in attempt.containers()), "ALL_EXACT_OWN_PROJECT_CONTAINERS_STOPPED")
            stopped = True
            cleanup_diagnostics["containers"] = "STOPPED_VERIFIED"
        except Exception:
            passed = False
            cleanup_diagnostics["containers"] = "FAILED_OR_UNOBSERVED"
    elapsed = None if started is None else int((time.monotonic() - started)*1000)
    if passed and elapsed is not None and elapsed > 600000:
        failure = {"type": "Deadline", "code": "WHOLE_WORKLOAD_600_SECONDS_EXCEEDED"}
    if failure is None and (not stopped or not initializer_stopped):
        failure = {"type": "Observation", "code": "OWN_STOP_OUTCOME_UNOBSERVED_NO_RETRY"}
    passed = passed and stopped and initializer_stopped and all(checks.values()) and elapsed is not None and elapsed <= 600000
    passed = passed and public_diagnostic is not None and public_diagnostic["passed"] is True
    summary = {"schemaVersion": 2, "scope": SCOPE, "passed": passed, "capturedAt": base.utc(), "sourceCommit": source,
               "failure": failure, "result": result if passed else {}, "checks": checks, "workloadElapsedMillis": elapsed,
               "commandDiagnostics": attempt.command_diagnostics(), "cleanupDiagnostics": cleanup_diagnostics,
               "bootstrapDiagnostic": public_diagnostic, "bootstrapProgress": progress,
               "workloadBudgetSeconds": 600, "buildAndPullExcludedFromWorkloadClock": True,
               "plannedSequentialPeakMemoryBytes": 5*1024**3, "requiredActualMemAvailableBytes": 7*1024**3,
               "ownedContainersStopped": stopped, "ownedInitializerStopped": initializer_stopped,
               "enabledOomKillerRepresentationsVerified": True if passed else None,
               "concurrentHeavyJvmAbsenceVerified": True if passed else None,
               "readerJavaInvocationPlanned": False, "onlyFreshCloudResources": True,
               "priorCloud8OrNative7EvidenceModified": False, "miniPcContacted": False, "kubernetesVerified": False,
               "automaticRetryPerformed": False, "snapshotExpirationOrObjectGcPerformed": False,
               "runtimeAvailabilityOrPerformanceClaimed": False, "rawLogsOrCredentialsUploaded": False,
               "volumesDeleted": False, "runnerStorageIsEphemeral": True}
    base.save(public / "summary.json", summary)
    print(json.dumps({"passed": passed, "scope": SCOPE, "ownedContainersStopped": stopped}))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
