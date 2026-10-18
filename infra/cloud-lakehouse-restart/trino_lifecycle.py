"""One explicit Trino replacement; the reviewed five-role factory is unchanged.

All records returned here are private. This module performs no work at import.
The caller must assume cleanup authority for returned B before creating Trino.
"""
import copy
import json
import re
from pathlib import Path

SURVIVORS = frozenset(("postgres", "garage", "spark"))
ROLES = SURVIVORS | {"trino", "reader"}
STATE_KEYS = {"id", "role", "running", "exitCode", "oom", "pid", "startedAt"}
ZERO_STARTED = "0001-01-01T00:00:00Z"
QUERIES = {"version", "bronze-double", "silver-double", "snapshot-1", "snapshot-2",
           "snapshot-3", "current-bronze", "current-silver", "snapshots", "files"}


def require(value, code):
    if not value:
        raise ValueError(code)


class BaseFacade:
    """Remap only fixed private proof leaves, retaining base.save exclusivity."""
    def __init__(self, base, physical_root, namespace):
        self.base, self.physical_root = base, Path(physical_root)
        require(self.physical_root.is_absolute() and namespace in
                ("lifecycle-initial", "lifecycle-resumed"), "FIXED_LIFECYCLE_NAMESPACE")
        self.proof_root = self.physical_root / namespace
        self.proof_root.mkdir(mode=0o700)  # exclusive, no parents/exist_ok

    def __getattr__(self, name):
        return getattr(self.base, name)

    def save(self, path, value, mode=0o600):
        path = Path(path)
        name = path.name
        allowed = bool(re.fullmatch(r"command-[0-9]{3,9}(?:-intent\.json|\.stdout|\.stderr)", name))
        allowed = allowed or name in {"start-" + role + "-intent.json" for role in ROLES}
        allowed = allowed or name in {"trino-" + query + "-intent.json" for query in QUERIES}
        allowed = allowed or name in {"trino-normal-stop-intent.json", "trino-normal-stop-result.json"}
        require(path.parent == self.physical_root and allowed and type(mode) is int
                and mode == 0o600, "ONLY_FIXED_PRIVATE_LIFECYCLE_PROOF_LEAF")
        return self.base.save(self.proof_root / name, value, mode)


def _inventory(values):
    require(type(values) is list and len(values) <= 5, "BOUNDED_FIXED_ROLE_INVENTORY")
    result = {}
    for value in values:
        require(type(value) is dict and set(value) == STATE_KEYS, "EXACT_ROLE_STATE_FIELDS")
        role = value["role"]
        require(role in ROLES and role not in result and type(value["id"]) is str
                and re.fullmatch(r"[a-f0-9]{64}", value["id"]), "UNIQUE_FIXED_ROLE_FULL_CID")
        require(type(value["running"]) is bool and type(value["oom"]) is bool
                and type(value["exitCode"]) is int and type(value["pid"]) is int
                and value["pid"] >= 0 and type(value["startedAt"]) is str,
                "EXACT_ROLE_STATE_TYPES")
        result[role] = copy.deepcopy(value)
    require(len({value["id"] for value in result.values()}) == len(result), "DISTINCT_ROLE_CIDS")
    return result


def _initializer(attempt):
    require(attempt.initializer_intended is True and
            attempt.initializer_name == attempt.project + "-volume-init", "CARRIED_INITIALIZER_SCOPE")
    value = attempt.initializer()
    require(type(value) is dict and set(value) == {"id", "running", "exitCode", "oom"}
            and type(value["id"]) is str and re.fullmatch(r"[a-f0-9]{64}", value["id"])
            and value["running"] is False and type(value["exitCode"]) is int
            and value["exitCode"] == 0 and value["oom"] is False, "SAME_STOPPED_SUCCESSFUL_INITIALIZER")
    checks = attempt.initializer_identity_checks
    require(type(checks) is dict and bool(checks) and all(v is True for v in checks.values()),
            "ALL_ORIGINAL_INITIALIZER_IDENTITY_CHECKS")
    return copy.deepcopy(value), copy.deepcopy(checks)


def _survivor_states(values):
    require(SURVIVORS.issubset(values), "ALL_THREE_SURVIVORS_PRESENT")
    for role in ("postgres", "garage"):
        require(values[role]["running"] is True and values[role]["oom"] is False
                and values[role]["pid"] > 1 and values[role]["startedAt"] != ZERO_STARTED,
                "LIVE_BASE_SERVICE_SURVIVOR")
    spark = values["spark"]
    require(spark["running"] is False and spark["exitCode"] == 0 and spark["oom"] is False
            and spark["pid"] == 0 and spark["startedAt"] != ZERO_STARTED,
            "EXACT_PREVIOUSLY_STARTED_SPARK_SUCCESS_STATE")


def _anonymous(bound):
    names = set()
    for signature in bound.values():
        require(type(signature) is dict and type(signature.get("mounts")) is list,
                "ORIGINAL_CANONICAL_BOUND_MOUNTS")
        for encoded in signature["mounts"]:
            require(type(encoded) is str, "CANONICAL_MOUNT_JSON_STRING")
            mount = json.loads(encoded)
            require(type(mount) is dict, "CANONICAL_MOUNT_OBJECT")
            name = mount.get("Name")
            if mount.get("Type") == "volume" and type(name) is str and re.fullmatch(r"[a-f0-9]{64}", name):
                require(mount.get("Driver") == "local", "LOCAL_SURVIVOR_ANONYMOUS_VOLUME")
                names.add(name)
    return names


def freeze_survivors(trial, attempt):
    values = _inventory(attempt.containers())
    require(set(values) == SURVIVORS | {"trino"} and set(attempt.bound) == set(values)
            and attempt.started_roles == set(values), "EXACT_INITIAL_FOUR_STARTED_BOUND_ROLES")
    _survivor_states(values)
    trino = values["trino"]
    require(trino["running"] is True and trino["oom"] is False and trino["pid"] > 1,
            "LIVE_INITIAL_TRINO_BEFORE_HANDOFF")
    processes = {role: trial.process_identity(values[role]["pid"], values[role]["id"])
                 for role in ("postgres", "garage", "trino")}
    initializer, checks = _initializer(attempt)
    require(attempt.deadline is not None and attempt.safety_stop is False,
            "SAME_ACTIVE_WORKLOAD_CLOCK")
    frozen = {"schemaVersion": 1, "root": str(attempt.root), "project": attempt.project,
              "states": {role: values[role] for role in SURVIVORS},
              "bound": {role: copy.deepcopy(attempt.bound[role]) for role in SURVIVORS},
              "processes": processes, "initialTrino": trino,
              "initializer": initializer, "initializerChecks": checks,
              "desired": copy.deepcopy(attempt.desired), "identities": copy.deepcopy(attempt.identities),
              "imageVolumes": {role: sorted(value) for role, value in attempt.image_volumes.items()},
              "priorVolumes": sorted(attempt.prior_volumes), "deadlineStarted": attempt.deadline.started,
              "sequence": attempt.sequence}
    raw = json.dumps(frozen, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
    require(len(raw) <= 1024**2, "BOUNDED_PRIVATE_HANDOFF_EVIDENCE")
    return raw  # immutable; never export as a public result


def _same_survivors(trial, current, frozen, values):
    _survivor_states(values)
    require(current.deadline is not None and current.deadline.started == frozen["deadlineStarted"]
            and str(current.root) == frozen["root"] and current.project == frozen["project"],
            "SAME_PHYSICAL_CONTEXT_AND_WORKLOAD_CLOCK")
    for role in SURVIVORS:
        require(values[role] == frozen["states"][role] and current.bound.get(role) == frozen["bound"][role],
                "SURVIVOR_FULL_BOUND_AND_STATE_UNCHANGED")
    for role in ("postgres", "garage"):
        require(trial.process_identity(values[role]["pid"], values[role]["id"]) == frozen["processes"][role],
                "SURVIVOR_PROCESS_IDENTITY_UNCHANGED")
    initializer, checks = _initializer(current)
    require(initializer == frozen["initializer"] and checks == frozen["initializerChecks"],
            "INITIALIZER_ACTUAL_IDENTITY_UNCHANGED")


def handoff_context(trial, base, attempt, root, project, images, evidence, stopped):
    require(type(evidence) is bytes and 0 < len(evidence) <= 1024**2, "IMMUTABLE_PRIVATE_HANDOFF_BYTES")
    frozen = json.loads(evidence)
    require(json.dumps(frozen, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8") == evidence,
            "CANONICAL_INTERNAL_HANDOFF_EVIDENCE")
    require(frozen["schemaVersion"] == 1 and Path(root) == attempt.root
            and project == attempt.project and attempt.safety_stop is False
            and attempt.sequence >= frozen["sequence"], "EXACT_ACTIVE_HANDOFF_CONTEXT")
    require(attempt.desired == frozen["desired"] and attempt.identities == frozen["identities"]
            and {role: sorted(v) for role, v in attempt.image_volumes.items()} == frozen["imageVolumes"]
            and sorted(attempt.prior_volumes) == frozen["priorVolumes"], "UNCHANGED_FACTORY_CONFIGURATION")
    require(set(images) == ROLES and all(attempt.desired["services"][role]["image"] == images[role]
            for role in ROLES), "SAME_FIVE_PINNED_FACTORY_IMAGES")
    before = _inventory(attempt.containers())
    require(set(before) == SURVIVORS | {"trino"} and set(attempt.bound) == set(before)
            and attempt.started_roles == set(before), "EXACT_FOUR_ROLE_HANDOFF_PRECONDITION")
    _same_survivors(trial, attempt, frozen, before)
    old = frozen["initialTrino"]
    trial.normal_exit("trino", stopped, attempt.trino_stop)
    require(before["trino"] == stopped and stopped["id"] == old["id"]
            and stopped["startedAt"] == old["startedAt"] and stopped["pid"] == 0
            and attempt.bound["trino"]["id"] == old["id"]
            and all(attempt.trino_stop.get(k) == v for k, v in frozen["processes"]["trino"].items()),
            "EXACT_FIRST_TRINO_NORMAL_STOP_IDENTITY")
    attempt.deadline.remaining(180, 90)
    removed = attempt.command(["docker", "rm", old["id"]], timeout=10)
    require(removed.returncode == 0, "ONE_STOPPED_OWN_TRINO_REMOVAL_CONFIRMED")
    after = _inventory(attempt.containers())
    require(set(after) == SURVIVORS and old["id"] not in {v["id"] for v in after.values()},
            "OLD_TRINO_ABSENT_EXACT_THREE_SURVIVORS")
    _same_survivors(trial, attempt, frozen, after)
    raw = attempt.command(["docker", "volume", "ls", "-q"], sensitive=True).stdout
    require(type(raw) is bytes and len(raw) <= 131072, "BOUNDED_PRECREATE_VOLUME_INVENTORY")
    names = raw.decode("ascii").split()
    require(len(names) <= 512 and len(set(names)) == len(names) and
            all(re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,254}", n) for n in names),
            "EXACT_PRECREATE_VOLUME_NAMES")
    volumes, survivor_anon = set(names), _anonymous(frozen["bound"])
    require(survivor_anon.issubset(volumes), "ALL_PINNED_SURVIVOR_ANONYMOUS_VOLUMES_PRESENT")
    facade = BaseFacade(base, root, "lifecycle-resumed")
    resumed = trial.make_attempt(facade, root, project, copy.deepcopy(images))
    resumed.bound = copy.deepcopy(frozen["bound"])
    resumed.started_roles = set(SURVIVORS)
    resumed.desired = copy.deepcopy(frozen["desired"])
    resumed.identities = copy.deepcopy(frozen["identities"])
    resumed.image_volumes = {role: set(v) for role, v in frozen["imageVolumes"].items()}
    resumed.prior_volumes = volumes - survivor_anon
    resumed.deadline, resumed.sequence = attempt.deadline, attempt.sequence
    resumed.initializer_intended = attempt.initializer_intended
    resumed.initializer_name = attempt.initializer_name
    resumed.initializer_identity_checks = copy.deepcopy(frozen["initializerChecks"])
    resumed.command_failures = copy.deepcopy(attempt.command_failures)
    resumed.command_failures_truncated = attempt.command_failures_truncated
    resumed.last_command = copy.deepcopy(attempt.last_command)
    current = _inventory(resumed.containers())
    require(set(current) == SURVIVORS and set(resumed.bound) == SURVIVORS
            and resumed.trino_stop is None, "NEW_CONTEXT_HAS_ONLY_CARRIED_SURVIVORS")
    _same_survivors(trial, resumed, frozen, current)
    handoff = copy.deepcopy(frozen)
    handoff.update(oldTrinoId=old["id"], precreateVolumes=sorted(volumes),
                   survivorAnonymousVolumes=sorted(survivor_anon))
    return resumed, facade, handoff  # caller assigns cleanup authority BEFORE create


def validate_resumed_container(current, handoff, values):
    """Pure pre-start check of the inventory already verified by original factory."""
    inventory = _inventory(values)
    require(set(inventory) == SURVIVORS | {"trino"} and set(current.bound) == set(inventory)
            and current.started_roles == SURVIVORS and current.trino_stop is None,
            "ONLY_FRESH_UNSTARTED_REPLACEMENT_TRINO")
    for role in SURVIVORS:
        require(inventory[role] == handoff["states"][role] and current.bound[role] == handoff["bound"][role],
                "PRESTART_SURVIVORS_EXACT")
    value = inventory["trino"]
    require(value["id"] == current.bound["trino"]["id"] and
            handoff["oldTrinoId"] not in {v["id"] for v in inventory.values()}
            and value["running"] is False and value["oom"] is False and value["exitCode"] == 0
            and value["pid"] == 0 and value["startedAt"] == ZERO_STARTED,
            "DISTINCT_NEW_CREATED_TRINO_BEFORE_FIRST_START")
    require(not (_anonymous({"trino": current.bound["trino"]}) & set(handoff["precreateVolumes"])),
            "NEW_TRINO_CANNOT_ADOPT_ANY_PRECREATE_ANONYMOUS_VOLUME")
    require(current.prior_volumes == set(handoff["precreateVolumes"]) - set(handoff["survivorAnonymousVolumes"]),
            "EXACT_TWO_SET_VOLUME_FRESHNESS_GUARD")
    return copy.deepcopy(value)


def verify_survivors(trial, current, handoff, values):
    """Recheck original survivors after resumed reads and after final reader."""
    inventory = _inventory(values)
    require(SURVIVORS.issubset(inventory) and SURVIVORS.issubset(current.started_roles),
            "SURVIVORS_REMAIN_STARTED_AND_BOUND")
    _same_survivors(trial, current, handoff, inventory)
    return True
