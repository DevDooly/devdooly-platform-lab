"""Separate source-only PG/Garage configuration readback; no heavy workload or retry."""
import argparse
import ast
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import secrets
import stat
import subprocess
import sys
import time
import uuid

HERE = Path(__file__).resolve().parent
SCOPE = "ISOLATED_CLOUD_PG_GARAGE_CONFIG_READBACK_DIAGNOSTIC"
PINS = {
    "infra/cloud-lakehouse-ci/run_trial9.py": "bc5d6afb086b6ba32c1fd98586f197c3c41d1533a02bebb9b43d84a286b3c852",
    "infra/cloud-lakehouse-ci/contract.py": "e88d2bedfeb95b71b22e2b5b04701119e8203431d3c8e8cc521958f2dcfad98a",
    "infra/cloud-lakehouse-ci/compose_trial9.py": "cd2e98131046913d7dafbdfe2716af8ac350a56235406a9c5b5bb06613b58f76",
    "infra/cloud-lakehouse-ci/pinned_trino_configuration.py": "1cabbc33a9a1fddbb28562514ad24d240eb09dc7219fcc5f1483429c6b4de17b",
    "infra/spark-ci/run_ci.py": "d190d5f39ca9232f6417319033c1d4f645966e318468d601eaba32a9b3a3d144",
    "infra/spark-ci/compose_plan.py": "fcaa911c8dcb9c6b56821ed3ff40d71c282658c8f5beb88200bff07c25336ee5",
}
PRIOR_SOURCE = "d4bd48aaa5bb68154970600a5c50ac0e3fc5ee54"
PRIOR_SUMMARY = "570805bc765ac6437f07f546b3b77a153c9cb91ea097c265ba91ec22d3323aac"
FIRST_SUMMARY = "a42f34aba82140189f08f530574b10c6911a5ae229ff13ebca63b2b82b3ffe21"
PRIOR_STARTUP_SOURCE = "98833225a62ca21660a94935ee0f1ab077f93be2"
PRIOR_STARTUP_SUMMARY = "a3b24f385c812f5a404c012d81113a88e3b851fec53ffa51eb73a7f67a4d45da"
PRIOR_MOUNT_SOURCE = "f3f5c52993ceb00fd70f73c17f0ec6d2d236b26e"
PRIOR_MOUNT_SUMMARY = "c41ce401a46e061bb829902de97b7399cbf20288ad274612d6f8703a4ae8b07d"
PRIOR_FULL_SOURCE = "8e55f467faee38cee124690af1e80e65f69fc18c"
PRIOR_FULL_SUMMARY = "eebb19a8bed2a663d8216f3583d95e7d1a9956f6e5d4d279701a615bc441357b"
SIGNATURE_KEYS = ("id", "imageId", "config", "host", "mounts", "created")
CONFIG_KEYS = ("Hostname", "Domainname", "User", "AttachStdin", "AttachStdout", "AttachStderr", "ExposedPorts",
               "Tty", "OpenStdin", "StdinOnce", "Env", "Cmd", "Healthcheck", "ArgsEscaped", "Image", "Volumes",
               "WorkingDir", "Entrypoint", "NetworkDisabled", "MacAddress", "OnBuild", "Labels", "StopSignal", "StopTimeout", "Shell")
HOST_KEYS = ("Binds", "ContainerIDFile", "LogConfig", "NetworkMode", "PortBindings", "RestartPolicy", "AutoRemove",
             "VolumeDriver", "VolumesFrom", "ConsoleSize", "CapAdd", "CapDrop", "CgroupnsMode", "Dns", "DnsOptions",
             "DnsSearch", "ExtraHosts", "GroupAdd", "IpcMode", "Cgroup", "Links", "OomScoreAdj", "PidMode", "Privileged",
             "PublishAllPorts", "ReadonlyRootfs", "SecurityOpt", "UTSMode", "UsernsMode", "ShmSize", "Runtime", "Isolation",
             "CpuShares", "Memory", "NanoCpus", "MemorySwap", "PidsLimit", "Tmpfs", "Mounts", "MaskedPaths", "ReadonlyPaths", "Init")
STAGES = {"PREPARE", "CREATE_BASE_SERVICES", "INITIALIZER", "START_POSTGRES", "START_GARAGE",
          "BASE_SERVICE_READINESS", "CLEANUP_INITIALIZER", "CLEANUP_CONTAINERS"}
LOCAL_CODES = {"STARTUP_PROBE_DEADLINE", "ONLY_TWO_BASE_ROLES", "FRESH_PRIVATE_ROOT", "FULL_MODEL_UNCHANGED",
               "NO_HEAVY_START_OR_CREATE", "BASE_READY_DEADLINE", "BASE_STARTED_AND_RUNNING",
               "VERSION_SHAPE", "UNOBSERVED_VALIDATION_FAILURE", "PROBE_SOURCE_BYTES"}


def require(value, code):
    if not value:
        raise RuntimeError(code)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def source_codes(raw):
    result = set()
    for node in ast.walk(ast.parse(raw)):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "require" and len(node.args) >= 2:
            code = node.args[1]
            if isinstance(code, ast.Constant) and isinstance(code.value, str) and re.fullmatch(r"[A-Z0-9_]{1,128}", code.value):
                result.add(code.value)
    return result


def dependencies(repo):
    codes = set(LOCAL_CODES)
    for name, expected in PINS.items():
        raw = (repo / name).read_bytes()
        require(sha(raw) == expected, "PROBE_SOURCE_BYTES")
        codes.update(source_codes(raw))
    sys.path.insert(0, str(repo / "infra/spark-ci"))
    base = load(repo / "infra/spark-ci/run_ci.py", "config_readback_frozen_cloud8")
    base_compose = sys.modules["compose_plan"]
    sys.path.insert(0, str(repo / "infra/cloud-lakehouse-ci"))
    cloud = load(repo / "infra/cloud-lakehouse-ci/run_trial9.py", "config_readback_frozen_cloud9")
    for name, path in (("compose_plan", "infra/spark-ci/compose_plan.py"), ("contract", "infra/cloud-lakehouse-ci/contract.py"),
                       ("compose_trial9", "infra/cloud-lakehouse-ci/compose_trial9.py"),
                       ("pinned_trino_configuration", "infra/cloud-lakehouse-ci/pinned_trino_configuration.py")):
        require(Path(sys.modules[name].__file__).resolve() == (repo / path).resolve(), "PROBE_SOURCE_BYTES")
    return base, base_compose, cloud, codes


def reason_signatures(raw):
    # A signature is observed text, never a conclusion about the cause.
    require(type(raw) is bytes and len(raw) <= 8 * 1024**2, "PROBE_SOURCE_BYTES")
    patterns = (
        ("ENV_FILE_MISSING_SIGNATURE", rb"(?i)(?:env(?:ironment)?[ _-]?file[^\r\n]{0,200}(?:not found|no such file)|(?:not found|no such file)[^\r\n]{0,100}env(?:ironment)?[ _-]?file)"),
        ("READ_ONLY_FILESYSTEM_SIGNATURE", rb"(?i)read-only file system"),
        ("PERMISSION_DENIED_SIGNATURE", rb"(?i)(?:permission denied|operation not permitted)"),
        ("MOUNT_FAILURE_SIGNATURE", rb"(?i)(?:error mounting|mount[^\r\n]{0,100}(?:failed|invalid|not found|no such file))"),
        ("OCI_RUNTIME_SIGNATURE", rb"(?i)(?:OCI runtime|runc create|failed to create (?:task|shim)|container init)"),
        ("NETWORK_ENDPOINT_SIGNATURE", rb"(?i)(?:failed to (?:create|connect).{0,30}(?:endpoint|network)|network[^\r\n]{0,100}not found)"),
        ("EXECUTABLE_SIGNATURE", rb"(?i)(?:exec format error|executable file not found|exec:[^\r\n]{0,100}no such file)"),
        ("NO_SPACE_SIGNATURE", rb"(?i)(?:no space left on device|disk quota exceeded)"),
    )
    found = [name for name, pattern in patterns if re.search(pattern, raw)]
    return found or ["NO_RECOGNIZED_SIGNATURE"]


def validation_code(error, codes):
    # Even uppercase secret-bearing exception strings are withheld unless the
    # complete string is one of the pinned source's literal guard codes.
    value = str(error)
    return value if type(error) in (ValueError, RuntimeError) and value in codes else "UNOBSERVED_VALIDATION_FAILURE"


def signature(raw):
    return {"id": raw["Id"], "imageId": raw["Image"], "config": raw["Config"], "host": raw["HostConfig"],
            "mounts": sorted(json.dumps(member, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False)
                             for member in raw["Mounts"]), "created": raw["Created"]}


def known_key_differences(previous, current, keys):
    """Fixed names only; unknown names and every actual value stay in RAM."""
    require(type(current) is dict and (previous is None or type(previous) is dict), "PROBE_SOURCE_BYTES")
    if previous is None:
        return {key: None for key in keys}, None
    encode = lambda value: json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False)
    changes = {key: (key in previous) != (key in current)
               or (key in previous and encode(previous[key]) != encode(current[key])) for key in keys}
    unknown = encode({key: value for key, value in previous.items() if key not in keys}) != encode(
                     {key: value for key, value in current.items() if key not in keys})
    return changes, unknown


def mount_differences(previous, current):
    require(type(current) is list and all(type(member) is dict for member in current), "PROBE_SOURCE_BYTES")
    if previous is None:
        return {"mountOrderOnlyChanged": None, "mountContentChanged": None}
    require(type(previous) is list and all(type(member) is dict for member in previous), "PROBE_SOURCE_BYTES")
    def canonical_members(value):
        # Comparison only, never used to normalize the original guard's input.
        # Include every member field and preserve duplicates as a sorted list.
        return sorted(json.dumps(member, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False)
                      for member in value)
    content_same = canonical_members(previous) == canonical_members(current)
    return {"mountOrderOnlyChanged": previous != current and content_same, "mountContentChanged": not content_same}


def inspect_projection(raw, bound, project, images, identities, raw_mount_baselines):
    labels = raw.get("Config", {}).get("Labels") or {}
    role = labels.get("com.docker.compose.service")
    require(role in ("postgres", "garage") and labels.get("com.docker.compose.project") == project
            and re.fullmatch(r"[a-f0-9]{64}", raw.get("Id", ""))
            and raw["Config"].get("Image") == images[role] and raw.get("Image") == identities[role], "ONLY_TWO_BASE_ROLES")
    previous = bound.get(role)
    current = signature(raw)
    changes = {key + "Changed": None if previous is None else previous[key] != current[key] for key in SIGNATURE_KEYS}
    config_changes, config_unknown = known_key_differences(None if previous is None else previous["config"], raw["Config"], CONFIG_KEYS)
    host_changes, host_unknown = known_key_differences(None if previous is None else previous["host"], raw["HostConfig"], HOST_KEYS)
    state = raw.get("State", {})
    error = state.get("Error")
    require(type(error) is str and len(error.encode()) <= 65536, "PROBE_SOURCE_BYTES")
    status = state.get("Status")
    require(status in {"created", "running", "paused", "restarting", "removing", "exited", "dead"}
            and type(state.get("Running")) is bool and type(state.get("OOMKilled")) is bool
            and type(state.get("ExitCode")) is int and -255 <= state["ExitCode"] <= 255, "PROBE_SOURCE_BYTES")
    return {"role": role, "identityBound": previous is not None and previous["id"] == raw["Id"],
            "status": status, "running": state["Running"], "exitCode": state["ExitCode"], "oomKilled": state["OOMKilled"],
            "stateErrorPresent": bool(error), "stateErrorSignatures": reason_signatures(error.encode()) if error else [],
            "signatureDifferences": changes,
            "configKnownKeyChanged": config_changes, "configUnknownKeysChanged": config_unknown,
            "hostConfigKnownKeyChanged": host_changes, "hostConfigUnknownKeysChanged": host_unknown,
            **mount_differences(raw_mount_baselines.get(role), raw["Mounts"])}


def version(raw):
    require(type(raw) is bytes and 0 < len(raw) <= 128, "VERSION_SHAPE")
    text = raw.decode("ascii").strip()
    require(re.fullmatch(r"v?[0-9]{1,3}(?:\.[0-9]{1,3}){1,3}(?:[-+][A-Za-z0-9._-]{1,32})?", text), "VERSION_SHAPE")
    return text


def initial_checks():
    return {name: False for name in ("fullFiveServiceComposeModel", "trinoEnvFileAbsent", "onlyTwoCreatedBaseRoles",
            "pinnedBaseImages", "freshPhysicalVolumes", "internalNetwork", "initializerExitZero", "actualMemAvailable7Gi")}


class ProbeDeadline:
    def __init__(self, started, now=time.monotonic):
        self.started, self.now = started, now

    def remaining(self, maximum, reserve=0):
        remaining = 180 - (self.now() - self.started) - reserve
        require(remaining > 0, "STARTUP_PROBE_DEADLINE")
        return min(maximum, remaining)


class Diagnostics:
    def __init__(self, codes):
        self.codes, self.validations, self.reasons, self.states = codes, [], [], {}
        self.observation_failures = []
        # Readback observations only, never included in the public summary.
        self._raw_mount_baselines = {}

    def failure(self, stage, error):
        value = {"stage": stage if stage in STAGES else "PREPARE", "validationFailureCode": validation_code(error, self.codes)}
        if len(self.validations) < 8:
            self.validations.append(value)
        return value

    def observe(self, attempt, args, result):
        if result.returncode != 0 and len(self.reasons) < 16:
            self.reasons.append({**attempt.last_command, "stderrSignatures": reason_signatures(result.stderr)})
        if len(args) == 3 and args[:2] == ["docker", "inspect"] and re.fullmatch(r"[a-f0-9]{64}", args[2]) and result.returncode == 0:
            raw = json.loads(result.stdout)
            require(type(raw) is list and len(raw) == 1 and raw[0]["Id"] == args[2], "ONLY_TWO_BASE_ROLES")
            value = inspect_projection(raw[0], attempt.bound, attempt.project, attempt.probe_images, attempt.identities,
                                       self._raw_mount_baselines)
            if value["role"] not in self._raw_mount_baselines:
                self._raw_mount_baselines[value["role"]] = raw[0]["Mounts"]
            self.states[value["role"]] = value

    def install(self, attempt):
        original = attempt.command
        def observed(args, timeout=60, sensitive=False, check=True):
            # Reject accidental heavy create/start even if a future caller
            # passes it through the otherwise unchanged full Compose model.
            if args[:2] == ["docker", "compose"] and len(args) > 6:
                action = args[6]
                if action in ("create", "start"):
                    roles = [value for value in args[7:] if not value.startswith("--")]
                    require(roles and set(roles) <= {"postgres", "garage"}, "NO_HEAVY_START_OR_CREATE")
            if args[:2] == ["docker", "start"] and len(args) == 3:
                require(args[2] in {value["id"] for role, value in attempt.bound.items() if role in ("postgres", "garage")},
                        "NO_HEAVY_START_OR_CREATE")
            try:
                result = original(args, timeout=timeout, sensitive=sensitive, check=check)
            except Exception as error:
                # Frozen command already saved non-sensitive stderr before
                # raising. The known private file is only classified in RAM.
                path = attempt.root / ("command-%03d.stderr" % attempt.sequence)
                try:
                    raw = error.stderr if isinstance(error, subprocess.TimeoutExpired) else path.read_bytes() if not sensitive else b""
                    if type(raw) is bytes and len(raw) <= 8*1024**2 and len(self.reasons) < 16:
                        self.reasons.append({**attempt.last_command, "stderrSignatures": reason_signatures(raw)})
                except Exception:
                    pass
                raise
            try:
                self.observe(attempt, args, result)
            except Exception as error:
                if len(self.observation_failures) < 8:
                    self.observation_failures.append({"stage": attempt.command_stage if attempt.command_stage in STAGES else "PREPARE",
                                                      "validationFailureCode": validation_code(error, self.codes)})
            return result
        attempt.command = observed


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--self-sha256", required=True)
    parser.add_argument("--ack-fresh-base-config-readback", action="store_true", required=True)
    args = parser.parse_args()
    require(sha(Path(__file__).read_bytes()) == args.self_sha256, "PROBE_SOURCE_BYTES")
    require(sys.platform == "linux" and os.environ.get("GITHUB_ACTIONS") == "true"
            and os.environ.get("RUNNER_ENVIRONMENT") == "github-hosted", "PROBE_SOURCE_BYTES")
    os.umask(0o077)
    repo = HERE.parents[1]
    base, base_compose, cloud, codes = dependencies(repo)
    source = os.environ.get("SOURCE_COMMIT", "")
    cloud.checkout_source(repo, source)
    local = repo / ".local"
    local.mkdir(exist_ok=True)
    nonce = uuid.uuid4().hex
    root = local / ("cloud-base-config-private-" + nonce)
    root.mkdir(mode=0o700)
    public = local / "cloud-base-config-public"
    public.mkdir(mode=0o700)
    require(stat.S_IMODE(root.stat().st_mode) == 0o700, "FRESH_PRIVATE_ROOT")
    project = "cloud-base-config-" + nonce
    unused_image = "spark-isolated-ci:" + nonce
    images = {"postgres": base.POSTGRES, "garage": base.GARAGE, "spark": unused_image,
              "trino": cloud.TRINO, "reader": base.SPARK}
    attempt = cloud.make_attempt(base, root, project, images)
    attempt.probe_images = images
    diagnostics = Diagnostics(codes)
    diagnostics.install(attempt)
    primary, ready, stopped, init_stopped = None, False, False, False
    versions, started = {}, None
    checks = initial_checks()
    try:
        versions["dockerClient"] = version(attempt.command(["docker", "version", "--format={{.Client.Version}}"]).stdout)
        versions["dockerServer"] = version(attempt.command(["docker", "version", "--format={{.Server.Version}}"]).stdout)
        versions["compose"] = version(attempt.command(["docker", "compose", "version", "--short"]).stdout)
        for kind in ("container", "volume", "network"):
            prefix = ["docker", "ps", "-aq"] if kind == "container" else ["docker", kind, "ls", "-q"]
            require(not attempt.command([*prefix, "--filter", "label=com.docker.compose.project=" + project]).stdout.strip(), "FRESH_PRIVATE_ROOT")
        for role in ("postgres", "garage"):
            reference = images[role]
            attempt.command(["docker", "pull", "--platform=linux/amd64", reference], timeout=120)
            raw = json.loads(attempt.command(["docker", "image", "inspect", reference], sensitive=True).stdout)[0]
            require(raw["Os"] == "linux" and raw["Architecture"] == "amd64"
                    and any(value.endswith("@" + reference.rsplit("@", 1)[1]) for value in raw["RepoDigests"]), "PROBE_SOURCE_BYTES")
            attempt.identities[role] = raw["Id"]
            attempt.image_volumes[role] = set(raw["Config"].get("Volumes") or {})
        checks["pinnedBaseImages"] = True
        (root / "postgres-secrets").mkdir(mode=0o755)
        os.chmod(root / "postgres-secrets", 0o755)
        base.save(root / "postgres-secrets/bootstrap-password", secrets.token_hex(32).encode(), 0o444)
        base.save(root / "postgres-init.sql", base.pg_init(secrets.token_hex(32)), 0o444)
        base.save(root / "garage.toml", base.garage_config(), 0o444)
        attempt.desired = cloud.plan(base_compose.plan, unused_image, base.SPARK)
        require(set(attempt.desired["services"]) == {"postgres", "garage", "spark", "trino", "reader"}
                and attempt.desired["services"]["trino"]["env_file"] == ["./trino.env"]
                and not (root / "trino.env").exists(), "FULL_MODEL_UNCHANGED")
        checks["fullFiveServiceComposeModel"] = checks["trinoEnvFileAbsent"] = True
        base.save(root / "compose.json", attempt.desired)
        names = [project + "_" + value for value in ("postgres-data", "garage-meta", "garage-data")]
        prior = attempt.command(["docker", "volume", "ls", "-q"], sensitive=True).stdout.decode().split()
        require(len(prior) <= 512 and not set(names).intersection(prior), "FRESH_PRIVATE_ROOT")
        attempt.prior_volumes = set(prior)
        attempt.command_stage = "CREATE_BASE_SERVICES"
        attempt.cli("create", "--no-build", "postgres", "garage")
        network = json.loads(attempt.command(["docker", "network", "inspect", project + "_trial"], sensitive=True).stdout)[0]
        require(network["Internal"] is True and network["Labels"]["com.docker.compose.project"] == project, "FULL_MODEL_UNCHANGED")
        checks["internalNetwork"] = True
        for name in names:
            volume = json.loads(attempt.command(["docker", "volume", "inspect", name], sensitive=True).stdout)[0]
            require(volume["Name"] == name and volume["Driver"] == "local" and not volume["Options"]
                    and volume["Labels"]["com.docker.compose.project"] == project, "FRESH_PRIVATE_ROOT")
        checks["freshPhysicalVolumes"] = True
        attempt.command_stage = "INITIALIZER"
        base.save(root / "initializer-intent.json", {"name": attempt.initializer_name, "automaticRetry": False})
        attempt.initializer_intended = True
        attempt.command(["docker", "create", "--name", attempt.initializer_name, "--label", "devdooly.io.spark-ci-project=" + project,
            "--cidfile", str(root / "initializer.cid"), "--network=none", "--read-only", "--memory=64m", "--cpus=0.1", "--pids-limit=16",
            "--cap-drop=ALL", "--cap-add=CHOWN", "--security-opt=no-new-privileges:true", "--entrypoint=/bin/chown",
            "-v", names[1] + ":/meta", "-v", names[2] + ":/data", base.POSTGRES, "1000:1000", "/meta", "/data"])
        init = attempt.initializer()
        require(init is not None and not init["running"], "PROBE_SOURCE_BYTES")
        attempt.command(["docker", "start", "-a", init["id"]])
        init = attempt.initializer()
        require(init is not None and not init["running"] and init["exitCode"] == 0 and not init["oom"], "PROBE_SOURCE_BYTES")
        checks["initializerExitZero"] = True
        cloud.memory_available()
        checks["actualMemAvailable7Gi"] = True
        started = time.monotonic()
        attempt.deadline = ProbeDeadline(started)
        base.save(root / "startup-clock.json", {"startedMonotonic": started, "budgetSeconds": 180,
                  "hostBootId": Path("/proc/sys/kernel/random/boot_id").read_text().strip()})
        require({value["role"] for value in attempt.containers()} == {"postgres", "garage"}, "ONLY_TWO_BASE_ROLES")
        checks["onlyTwoCreatedBaseRoles"] = True
        attempt.start("postgres")
        attempt.start("garage")
        attempt.command_stage = "BASE_SERVICE_READINESS"
        until = time.monotonic() + attempt.deadline.remaining(30, 60)
        while True:
            require(time.monotonic() < until, "BASE_READY_DEADLINE")
            values = attempt.containers()
            require(len(values) == 2 and all(value["running"] and not value["oom"] for value in values), "BASE_STARTED_AND_RUNNING")
            pg = attempt.cli("exec", "-T", "postgres", "pg_isready", "-h", "127.0.0.1", "-U", "lab_bootstrap", "-d", "iceberg_lab", timeout=5, check=False)
            garage = attempt.cli("exec", "-T", "garage", "/garage", "-c", "/etc/garage.toml", "node", "id", "--quiet", timeout=5, check=False)
            if pg.returncode == garage.returncode == 0:
                ready = True
                break
            time.sleep(min(1, attempt.deadline.remaining(1, 60)))
    except Exception as error:
        primary = diagnostics.failure(attempt.command_stage, error)
    finally:
        attempt.safety_stop = True
        attempt.command_stage = "CLEANUP_INITIALIZER"
        try:
            init = attempt.initializer()
            if init and init["running"]:
                attempt.command(["docker", "stop", "--time=10", init["id"]], timeout=15)
            require(attempt.initializer() is None or not attempt.initializer()["running"], "PROBE_SOURCE_BYTES")
            init_stopped = True
        except Exception as error:
            diagnostics.failure(attempt.command_stage, error)
        attempt.command_stage = "CLEANUP_CONTAINERS"
        try:
            # Use the original strict whole-signature guard. Observability
            # does not grant cleanup when that guard rejects current state.
            values = attempt.containers()
            require(all(value["role"] in ("postgres", "garage") for value in values), "ONLY_TWO_BASE_ROLES")
            for value in values:
                if value["running"]:
                    attempt.command(["docker", "stop", "--time=10", value["id"]], timeout=15)
            require(all(not value["running"] for value in attempt.containers()), "PROBE_SOURCE_BYTES")
            stopped = True
        except Exception as error:
            diagnostics.failure(attempt.command_stage, error)
    elapsed = None if started is None else int((time.monotonic() - started) * 1000)
    diagnostic_complete = not diagnostics.observation_failures and set(diagnostics.states) == {"postgres", "garage"}
    passed = primary is None and ready and stopped and init_stopped and all(checks.values()) and diagnostic_complete and elapsed is not None and elapsed <= 180000
    summary = {"schemaVersion": 1, "scope": SCOPE, "passed": passed, "capturedAt": base.utc(), "sourceCommit": source,
        "priorFailedSourceCommit": PRIOR_SOURCE, "priorFailedSummarySha256": PRIOR_SUMMARY, "firstFailedSummarySha256": FIRST_SUMMARY,
        "priorStartupSourceCommit": PRIOR_STARTUP_SOURCE, "priorStartupSummarySha256": PRIOR_STARTUP_SUMMARY,
        "priorMountDiagnosticSourceCommit": PRIOR_MOUNT_SOURCE, "priorMountDiagnosticSummarySha256": PRIOR_MOUNT_SUMMARY,
        "priorFullSourceCommit": PRIOR_FULL_SOURCE, "priorFullSummarySha256": PRIOR_FULL_SUMMARY,
        "failure": primary, "versions": versions, "startupReadyObserved": ready, "startupBudgetSeconds": 180,
        "startupElapsedMillis": elapsed, "imagePullsExcludedFromStartupClock": True,
        "checks": checks,
        "fullFiveServiceComposeModelPreserved": checks["fullFiveServiceComposeModel"],
        "trinoEnvFileIntentionallyAbsent": checks["trinoEnvFileAbsent"],
        "unusedSparkImageNotBuiltOrPulled": True, "composeRoleStartsLimitedToPostgresGarage": True,
        "commandDiagnostics": attempt.command_diagnostics(), "stderrReasonObservations": diagnostics.reasons,
        "validationFailures": diagnostics.validations, "diagnosticObservationFailures": diagnostics.observation_failures,
        "latestBaseContainerDiagnostics": diagnostics.states,
        "ownedContainersStopped": stopped, "ownedInitializerStopped": init_stopped,
        "sparkTrinoReaderStartRequested": False, "vendorOrApplicationJarRead": False, "bucketOrKeyCreated": False,
        "businessDataSubmitted": False, "miniPcContacted": False, "rawLogsOrCredentialsUploaded": False,
        "automaticRetryPerformed": False, "volumesDeleted": False, "priorRuntimeOrEvidenceModified": False,
        "failureSoleCauseProven": False}
    base.save(public / "summary.json", summary)
    print(json.dumps({"passed": passed, "scope": SCOPE, "ownedContainersStopped": stopped}))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
