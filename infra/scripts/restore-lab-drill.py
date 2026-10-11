#!/usr/bin/env python3
"""Restore a selected Lab SQL backup into an isolated trial, then stop its Pods."""
from __future__ import annotations

import argparse
import copy
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import socket
import stat
import subprocess
import sys
import time
from urllib.request import urlopen

BASELINE_QUERY = (
    "SELECT * FROM demo_run ORDER BY id; "
    "SELECT * FROM demo_outcome ORDER BY run_id,input_sequence; "
    "SELECT * FROM flyway_schema_history ORDER BY installed_rank;"
)
PURPOSE = "devdooly.io/purpose"
BACKUP_ID = "devdooly.io/backup-id"
EXPECTED_COUNTS = {"inputCount": 12, "successCount": 7, "failureCount": 3,
                   "duplicateCount": 2, "pendingCount": 0}
SQL_SCRIPT = ('export MYSQL_PWD="$MARIADB_ROOT_PASSWORD"; '
              'exec mariadb -uroot --batch --raw --skip-column-names "$MARIADB_DATABASE" -e "$1"')


class DrillError(Exception):
    pass


def command(args: list[str], data: bytes | None = None, *, timeout: int = 90,
            check: bool = True) -> subprocess.CompletedProcess:
    result = subprocess.run(args, input=data, capture_output=True, timeout=timeout)
    if check and result.returncode:
        raise DrillError("A drill command failed; secret-bearing diagnostics were withheld.")
    return result


def kube(*args: str) -> dict:
    return json.loads(command(["k3s", "kubectl", *args, "-o", "json"]).stdout)


def get_optional(kind: str, name: str, namespace: str | None = None) -> dict | None:
    args = ["k3s", "kubectl"] + (["-n", namespace] if namespace else [])
    result = command(args + ["get", kind, name, "--ignore-not-found", "-o", "json"])
    return json.loads(result.stdout) if result.stdout.strip() else None


def private_path(path: Path, *, directory: bool = False) -> Path:
    if not path.is_absolute() or ".." in path.parts or path.resolve(strict=True) != path:
        raise DrillError("Private backup paths must be absolute and contain no symlinks or parent traversal.")
    details = path.lstat()
    valid_type = stat.S_ISDIR(details.st_mode) if directory else stat.S_ISREG(details.st_mode)
    if not valid_type or details.st_uid != 0 or details.st_mode & 0o077:
        raise DrillError("Selected backup paths must be root-owned and deny group/other access.")
    return path


def owner_labels(namespace: str) -> dict[str, str]:
    match = re.fullmatch(r"platform-lab-restore-(\d{14}(?:-[0-9a-f]{6})?)", namespace)
    if not match:
        raise DrillError("Trial namespace must use platform-lab-restore- followed by a generated trial ID.")
    return {PURPOSE: "restore-drill", BACKUP_ID: match.group(1)}


def require_owner(obj: dict, owner: dict[str, str]) -> None:
    labels = obj.get("metadata", {}).get("labels", {})
    if any(labels.get(key) != value for key, value in owner.items()):
        raise DrillError("Existing trial resources must carry matching purpose and trial ID ownership labels.")


def image_digest(image: str) -> bool:
    return bool(re.fullmatch(r"[^\s@]+@sha256:[0-9a-f]{64}", image))


def load_backup(args: argparse.Namespace) -> tuple[dict, bytes, str, dict]:
    directory = private_path(args.backup_directory, directory=True)
    root = args.backup_root
    if not root.is_absolute() or root.resolve(strict=True) != root or root == Path(root.anchor):
        raise DrillError("Backup root must be an existing absolute directory without symlinks.")
    if root not in directory.parents:
        raise DrillError("Selected backup directory must be below the specified backup root.")
    manifest = json.loads(private_path(directory / "manifest.json").read_text("utf-8"))
    dump = private_path(directory / "mariadb.sql").read_bytes()
    baseline_bytes = private_path(directory / "database-baseline.tsv").read_bytes()
    if manifest.get("baselineQuery") != BASELINE_QUERY:
        raise DrillError("Unsupported baseline query; arbitrary SQL from a manifest is never executed.")
    for key, actual in (("dumpSha256", hashlib.sha256(dump).hexdigest()),
                        ("databaseBaselineSha256", hashlib.sha256(baseline_bytes).hexdigest())):
        if not re.fullmatch(r"[0-9a-f]{64}", manifest.get(key, "")) or manifest[key] != actual:
            raise DrillError("Selected backup content does not match its manifest SHA-256.")
    if not dump or b"CREATE TABLE" not in dump or len(dump) != manifest.get("dumpBytes"):
        raise DrillError("Logical SQL dump is empty, incomplete, or has the wrong byte count.")
    if not all(image_digest(manifest.get(key, "")) for key in ("databaseImage", "apiImage")):
        raise DrillError("Backup must identify DB and API images by immutable SHA-256 digest.")
    for field, selected in (("namespace", args.namespace), ("dbStatefulset", args.db_statefulset),
                            ("apiDeployment", args.api_deployment)):
        if field in manifest and manifest[field] != selected:
            raise DrillError("Selected production resource names differ from the backup manifest.")
    repository = args.repository
    if not repository.is_absolute() or repository.resolve(strict=True) != repository or not repository.is_dir():
        raise DrillError("Repository must be an existing absolute directory without symlinks.")
    scenario_path = repository / "tests/scenarios/sensor-validation-v1.json"
    if scenario_path.resolve(strict=True) != scenario_path:
        raise DrillError("Scenario file must not be symlinked.")
    scenario = json.loads(scenario_path.read_text("utf-8"))
    if scenario.get("expected") != EXPECTED_COUNTS or len(scenario.get("expectedOutcomes", [])) != 12:
        raise DrillError("This drill requires the canonical independent 12-event scenario.")
    return manifest, dump, baseline_bytes.decode("utf-8"), scenario


def mounted_claim(pod: dict) -> str:
    spec = pod["spec"]
    if spec.get("hostNetwork") or any("hostPath" in item for item in spec.get("volumes", [])):
        raise DrillError("DB Pods must not use host networking or direct hostPath volumes.")
    volumes = {item["name"]: item for item in spec.get("volumes", [])}
    mounts = spec["containers"][0].get("volumeMounts", [])
    data_mounts = [mount for mount in mounts if mount["mountPath"] == "/var/lib/mysql"]
    if len(data_mounts) != 1:
        raise DrillError("Expected exactly one DB data mount.")
    volume = volumes[data_mounts[0]["name"]]
    if "persistentVolumeClaim" not in volume:
        raise DrillError("DB data must come from an explicit PVC.")
    return volume["persistentVolumeClaim"]["claimName"]


def pv_path(pv: dict, data_root: Path) -> Path:
    spec = pv["spec"]
    raw = spec.get("hostPath", {}).get("path") or spec.get("local", {}).get("path")
    if not isinstance(raw, str):
        raise DrillError("The current recovery drill supports local-path PVs only.")
    path = Path(raw)
    storage_root = data_root / "storage"
    if (not path.is_absolute() or ".." in path.parts or path.resolve(strict=True) != path
            or not path.is_dir() or storage_root not in path.parents):
        raise DrillError("PV path must be a real directory below the selected Lab storage root.")
    return path


def independent_storage(production_pvc: dict, production_pv: dict,
                        trial_pvc: dict, trial_pv: dict, namespace: str,
                        data_root: Path) -> None:
    if trial_pvc["metadata"]["uid"] == production_pvc["metadata"]["uid"]:
        raise DrillError("Trial PVC must have a different UID from production.")
    if trial_pv["metadata"]["name"] == production_pv["metadata"]["name"]:
        raise DrillError("Trial PV must differ from production.")
    claim = trial_pv["spec"].get("claimRef", {})
    if (claim.get("namespace") != namespace or claim.get("name") != trial_pvc["metadata"]["name"]
            or claim.get("uid") != trial_pvc["metadata"]["uid"]):
        raise DrillError("Trial PV claimRef must match the owned trial PVC.")
    first, second = pv_path(production_pv, data_root), pv_path(trial_pv, data_root)
    if first == second or first in second.parents or second in first.parents:
        raise DrillError("Production and trial mount paths must be disjoint.")


def stable_detail(detail: dict) -> dict:
    # Collection time changes; stored run times and every outcome must not.
    return {key: value for key, value in detail.items() if key != "observedAt"}


def parser() -> argparse.ArgumentParser:
    value = argparse.ArgumentParser(description=__doc__)
    value.add_argument("--backup-directory", required=True, type=Path)
    value.add_argument("--repository", required=True, type=Path)
    value.add_argument("--data-root", type=Path, default=Path("/var/lib/devdooly-platform-lab"))
    value.add_argument("--backup-root", type=Path, default=Path("/var/backups/devdooly-platform-lab"))
    value.add_argument("--namespace", default="platform-lab", help="Production namespace; never mutated.")
    value.add_argument("--db-statefulset", default="lab-platform-lab-db")
    value.add_argument("--api-deployment", default="lab-platform-lab-api")
    value.add_argument("--reuse-trial", metavar="OWNED_NAMESPACE",
                       help="Explicitly reuse a previously owned trial; no automatic discovery or adoption.")
    return value


def execute_drill(args: argparse.Namespace) -> dict:
    manifest, dump, baseline, scenario = load_backup(args)
    for name in (args.namespace, args.db_statefulset, args.api_deployment):
        if not re.fullmatch(r"[a-z0-9](?:[-a-z0-9]*[a-z0-9])?", name) or len(name) > 63:
            raise DrillError("Production namespace and resource names must be DNS labels.")
    data_root = args.data_root
    if (not data_root.is_absolute() or data_root.resolve(strict=True) != data_root
            or not data_root.is_dir() or data_root == Path(data_root.anchor)):
        raise DrillError("Lab data root must be an existing absolute non-root directory without symlinks.")
    stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%d%H%M%S") + "-" + secrets.token_hex(3)
    namespace = args.reuse_trial or "platform-lab-restore-" + stamp
    owner = owner_labels(namespace)
    if namespace == args.namespace:
        raise DrillError("Production namespace cannot be used as a trial.")
    old_namespace = get_optional("namespace", namespace)
    if args.reuse_trial:
        if old_namespace is None:
            raise DrillError("Explicit reuse requires an existing owned trial namespace.")
        require_owner(old_namespace, owner)
    elif old_namespace is not None:
        raise DrillError("Generated trial already exists; refusing implicit reuse.")

    db_name, api_name = args.db_statefulset, args.api_deployment
    db_pod = db_name + "-0"
    db = kube("-n", args.namespace, "get", "statefulset", db_name)
    api = kube("-n", args.namespace, "get", "deployment", api_name)
    for obj, key in ((db, "databaseImage"), (api, "apiImage")):
        if (obj["spec"]["replicas"] != 1
                or len(obj["spec"]["template"]["spec"]["containers"]) != 1
                or obj["spec"]["template"]["spec"]["containers"][0]["image"] != manifest[key]):
            raise DrillError("Production DB/API replicas and image digests must match the selected backup.")
        template = obj["spec"]["template"]["spec"]
        if template.get("hostNetwork") or template.get("automountServiceAccountToken") is not False:
            raise DrillError("Trial source templates require host networking disabled and API token automount false.")
        if any("hostPath" in volume or "persistentVolumeClaim" in volume for volume in template.get("volumes", [])):
            raise DrillError("Trial source templates must not directly reference existing PVCs or host paths.")
    api_env = {entry["name"]: entry.get("value") for entry in api["spec"]["template"]["spec"]["containers"][0]["env"]}
    if api_env.get("DB_URL") != "jdbc:mariadb://db:3306/platform_lab":
        raise DrillError("API must use its namespace-local DB service.")
    secret_names = set()
    for obj in (db, api):
        for entry in obj["spec"]["template"]["spec"]["containers"][0].get("env", []):
            reference = entry.get("valueFrom", {}).get("secretKeyRef")
            if reference:
                secret_names.add(reference["name"])
    if len(secret_names) != 1:
        raise DrillError("Expected a single shared DB credential Secret reference.")
    secret_name = next(iter(secret_names))
    account_names = {obj["spec"]["template"]["spec"].get("serviceAccountName") for obj in (db, api)}
    if len(account_names) != 1 or None in account_names:
        raise DrillError("Expected one explicit Lab ServiceAccount.")
    account_name = next(iter(account_names))
    production_pod = kube("-n", args.namespace, "get", "pod", db_pod)
    production_claim_name = mounted_claim(production_pod)
    production_pvc = kube("-n", args.namespace, "get", "pvc", production_claim_name)
    production_pv = kube("get", "pv", production_pvc["spec"]["volumeName"])
    production_path = pv_path(production_pv, data_root)
    production_sql = command(["k3s", "kubectl", "-n", args.namespace, "exec", db_pod,
                              "--", "sh", "-c", SQL_SCRIPT, "sql", BASELINE_QUERY]).stdout

    def trial_command(*parts: str) -> list[str]:
        return ["k3s", "kubectl", "-n", namespace, *parts]

    def sql(query: str, *, check: bool = True) -> subprocess.CompletedProcess:
        return command(trial_command("exec", db_pod, "--", "sh", "-c", SQL_SCRIPT, "sql", query), check=check)

    def apply(obj: dict) -> None:
        command(["k3s", "kubectl", "apply", "-f", "-"], json.dumps(obj).encode("utf-8"))

    def clone(obj: dict) -> dict:
        return {"apiVersion": obj["apiVersion"], "kind": obj["kind"],
                "metadata": {"name": obj["metadata"]["name"], "namespace": namespace,
                             "labels": {**obj["metadata"].get("labels", {}), **owner}},
                "spec": copy.deepcopy(obj["spec"])}

    expected_resources = {
        "statefulset": {db_name}, "deployment": {api_name}, "secret": {secret_name},
        "serviceaccount": {account_name, "default"}, "service": {"db"},
        "resourcequota": {"restore-budget"}, "networkpolicy": {"restore-isolation"},
    }
    if args.reuse_trial:
        for kind, names in expected_resources.items():
            for obj in kube("-n", namespace, "get", kind)["items"]:
                name = obj["metadata"]["name"]
                if name not in names:
                    raise DrillError("Trial contains unexpected resources; automatic adoption is forbidden.")
                if kind == "serviceaccount" and name == "default":
                    continue
                require_owner(obj, owner)
        for obj in kube("-n", namespace, "get", "pods")["items"]:
            require_owner(obj, owner)
        old_claims = kube("-n", namespace, "get", "pvc")["items"]
        if len(old_claims) != 1:
            raise DrillError("Explicit reuse requires exactly one owned test PVC.")
        require_owner(old_claims[0], owner)
        old_pv = kube("get", "pv", old_claims[0]["spec"]["volumeName"])
        # Earlier manually executed drills labelled the namespace/PVC but not
        # their provisioned PV. Explicit reuse can label that PV only after its
        # exact claimRef UID and disjoint storage path have been verified.
        old_volume_labels = old_pv.get("metadata", {}).get("labels", {})
        if PURPOSE in old_volume_labels or BACKUP_ID in old_volume_labels:
            require_owner(old_pv, owner)
        independent_storage(production_pvc, production_pv, old_claims[0], old_pv, namespace, data_root)
        if get_optional("secret", secret_name, namespace) is None:
            raise DrillError("Explicit reuse requires the original owned trial Secret.")

    def retain_trial_pv() -> tuple[dict, dict] | None:
        claims = kube("-n", namespace, "get", "pvc")["items"]
        if not claims:
            return None
        if len(claims) != 1 or claims[0].get("status", {}).get("phase") != "Bound":
            raise DrillError("Expected one Bound trial PVC.")
        claim = claims[0]
        require_owner(claim, owner)
        volume = kube("get", "pv", claim["spec"]["volumeName"])
        independent_storage(production_pvc, production_pv, claim, volume, namespace, data_root)
        apply_patch = {"metadata": {"labels": owner}, "spec": {"persistentVolumeReclaimPolicy": "Retain"}}
        command(["k3s", "kubectl", "patch", "pv", volume["metadata"]["name"],
                 "--type=merge", "-p", json.dumps(apply_patch)])
        return claim, volume

    def stop_trial() -> None:
        for kind, name in (("deployment", api_name), ("statefulset", db_name)):
            current = get_optional(kind, name, namespace)
            if current:
                require_owner(current, owner)
                command(trial_command("scale", kind, name, "--replicas=0"))
        deadline = time.monotonic() + 120
        while True:
            pods = kube("-n", namespace, "get", "pods")["items"]
            for pod in pods:
                require_owner(pod, owner)
            if not pods:
                break
            if time.monotonic() > deadline:
                raise DrillError("Trial Pods did not stop in time; inspect the owned trial privately.")
            time.sleep(2)
        claims = kube("-n", namespace, "get", "pvc")["items"]
        if claims and claims[0].get("status", {}).get("phase") == "Bound":
            retain_trial_pv()

    def wait_ready(kind: str, name: str) -> None:
        command(trial_command("rollout", "status", kind + "/" + name, "--timeout=240s"), timeout=255)

    def check_http() -> dict:
        with socket.socket() as listener:
            listener.bind(("127.0.0.1", 0))
            port = listener.getsockname()[1]
        forward = subprocess.Popen(trial_command("port-forward", "deployment/" + api_name,
                                                 f"{port}:8080", "--address=127.0.0.1"),
                                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        try:
            for _ in range(30):
                if forward.poll() is not None:
                    raise DrillError("Trial port-forward exited before verification.")
                try:
                    with urlopen(f"http://127.0.0.1:{port}/api/demo/runs/synthetic-v1-seed-42", timeout=5) as response:
                        detail = json.load(response)
                    break
                except (OSError, ValueError):
                    time.sleep(1)
            else:
                raise DrillError("Restored API did not respond in time.")
            outcomes = [{key: item[key] for key in ("sequence", "status", "reason")} for item in detail["outcomes"]]
            if ({key: detail[key] for key in EXPECTED_COUNTS} != scenario["expected"]
                    or outcomes != scenario["expectedOutcomes"] or len(detail["series"]) != 7):
                raise DrillError("Restored HTTP response differs from the independent scenario.")
            return detail
        finally:
            forward.terminate()
            try:
                forward.wait(timeout=15)
            except subprocess.TimeoutExpired:
                forward.kill()
                forward.wait(timeout=15)

    started = time.monotonic()
    trusted_trial = old_namespace is not None
    try:
        if old_namespace is None:
            # create, rather than apply, refuses any concurrently created namespace.
            command(["k3s", "kubectl", "create", "-f", "-"], json.dumps({
                "apiVersion": "v1", "kind": "Namespace", "metadata": {"name": namespace, "labels": owner}
            }).encode("utf-8"))
            trusted_trial = True
        apply({"apiVersion": "v1", "kind": "ResourceQuota",
               "metadata": {"name": "restore-budget", "namespace": namespace, "labels": owner},
               "spec": {"hard": {"requests.cpu": "1", "limits.cpu": "2", "requests.memory": "1Gi",
                                   "limits.memory": "3Gi", "requests.storage": "3Gi",
                                   "persistentvolumeclaims": "1", "pods": "3"}}})
        apply({"apiVersion": "networking.k8s.io/v1", "kind": "NetworkPolicy",
               "metadata": {"name": "restore-isolation", "namespace": namespace, "labels": owner},
               "spec": {"podSelector": {}, "policyTypes": ["Ingress", "Egress"],
                        "ingress": [{"from": [{"podSelector": {}}]}],
                        "egress": [{"to": [{"podSelector": {}}]},
                                   {"to": [{"namespaceSelector": {"matchLabels": {"kubernetes.io/metadata.name": "kube-system"}},
                                             "podSelector": {"matchLabels": {"k8s-app": "kube-dns"}}}],
                                    "ports": [{"protocol": "UDP", "port": 53}, {"protocol": "TCP", "port": 53}]}]}})
        if not args.reuse_trial:
            apply({"apiVersion": "v1", "kind": "Secret", "type": "Opaque",
                   "metadata": {"name": secret_name, "namespace": namespace, "labels": owner},
                   "stringData": {"app-password": secrets.token_urlsafe(32), "root-password": secrets.token_urlsafe(32)}})
        apply({"apiVersion": "v1", "kind": "ServiceAccount",
               "metadata": {"name": account_name, "namespace": namespace, "labels": owner},
               "automountServiceAccountToken": False})
        service = clone(kube("-n", args.namespace, "get", "service", "db"))
        for key in ("clusterIP", "clusterIPs", "ipFamilies", "ipFamilyPolicy"):
            service["spec"].pop(key, None)
        service["spec"]["type"] = "ClusterIP"
        for key in ("externalIPs", "loadBalancerIP", "loadBalancerSourceRanges", "externalName", "externalTrafficPolicy"):
            service["spec"].pop(key, None)
        for port in service["spec"]["ports"]:
            port.pop("nodePort", None)
        apply(service)

        restore_db = clone(db)
        restore_db["spec"]["template"]["metadata"]["labels"].update(owner)
        claims = restore_db["spec"]["volumeClaimTemplates"]
        if len(claims) != 1 or claims[0]["spec"].get("storageClassName") != "local-path":
            raise DrillError("Trial requires one local-path volumeClaimTemplate.")
        for claim in claims:
            claim["metadata"] = {"name": claim["metadata"]["name"], "labels": owner}
            claim["spec"]["resources"]["requests"]["storage"] = "3Gi"
            claim["spec"].pop("volumeName", None)
            claim["spec"].pop("selector", None)
            claim["spec"].pop("dataSource", None)
            claim["spec"].pop("dataSourceRef", None)
            claim.pop("status", None)
        restore_db["spec"]["persistentVolumeClaimRetentionPolicy"] = {"whenDeleted": "Retain", "whenScaled": "Retain"}
        restore_api = clone(api)
        restore_api["spec"]["replicas"] = 0
        restore_api["spec"]["template"]["metadata"]["labels"].update(owner)
        apply(restore_api)
        apply(restore_db)
        wait_ready("statefulset", db_name)
        deadline = time.monotonic() + 90
        while True:
            pods = kube("-n", namespace, "get", "pods")["items"]
            for pod in pods:
                require_owner(pod, owner)
            if len(pods) == 1 and pods[0]["metadata"]["name"] == db_pod:
                break
            if time.monotonic() > deadline:
                raise DrillError("API must be fully stopped before SQL import.")
            time.sleep(2)
        volume_pair = retain_trial_pv()
        if volume_pair is None:
            raise DrillError("No owned trial PVC was provisioned.")
        trial_pvc, trial_pv = volume_pair
        if mounted_claim(kube("-n", namespace, "get", "pod", db_pod)) != trial_pvc["metadata"]["name"]:
            raise DrillError("Trial DB is not mounted to the validated independent PVC.")
        import_started = time.monotonic()
        command(trial_command("exec", "-i", db_pod, "--", "sh", "-c",
                              'export MYSQL_PWD="$MARIADB_ROOT_PASSWORD"; exec mariadb -uroot'), dump)
        import_seconds = round(time.monotonic() - import_started, 3)
        if sql(BASELINE_QUERY).stdout.decode("utf-8") != baseline:
            raise DrillError("Restored SQL must match before any API starts.")
        duplicate = sql("INSERT INTO demo_outcome (run_id,input_sequence,event_id,sensor_id,event_time,sensor_value,status,reason) SELECT run_id,input_sequence,event_id,sensor_id,event_time,sensor_value,status,reason FROM demo_outcome ORDER BY id LIMIT 1;", check=False)
        if not duplicate.returncode or b"1062" not in duplicate.stderr or b"outcome_sequence" not in duplicate.stderr:
            raise DrillError("Restored duplicate constraint did not reject the duplicate row.")
        if sql(BASELINE_QUERY).stdout.decode("utf-8") != baseline:
            raise DrillError("Duplicate rejection changed stored data.")
        command(trial_command("scale", "deployment", api_name, "--replicas=1"))
        wait_ready("deployment", api_name)
        first = check_http()
        if sql(BASELINE_QUERY).stdout.decode("utf-8") != baseline:
            raise DrillError("API bootstrap changed restored data.")
        command(trial_command("rollout", "restart", "deployment", api_name))
        wait_ready("deployment", api_name)
        second = check_http()
        if stable_detail(first) != stable_detail(second) or sql(BASELINE_QUERY).stdout.decode("utf-8") != baseline:
            raise DrillError("API restart changed stored timestamps, outcomes, or Flyway history.")
        current_production_pvc = kube("-n", args.namespace, "get", "pvc", production_claim_name)
        current_production_pv = kube("get", "pv", current_production_pvc["spec"]["volumeName"])
        current_production_sql = command(["k3s", "kubectl", "-n", args.namespace, "exec", db_pod,
                                          "--", "sh", "-c", SQL_SCRIPT, "sql", BASELINE_QUERY]).stdout
        if (current_production_pvc["metadata"]["uid"] != production_pvc["metadata"]["uid"]
                or pv_path(current_production_pv, data_root) != production_path
                or current_production_sql != production_sql):
            raise DrillError("Production PVC, mount path, or data changed during the drill.")
    finally:
        if trusted_trial:
            stop_trial()

    summary = {
        "sameMariaDbAndApiDigests": True, "separateNamespaceAndPvc": True,
        "newSecretUsed": not bool(args.reuse_trial), "ownedTrialSecretReused": bool(args.reuse_trial),
        "ingressOrNodePortAdded": False, "namespaceNetworkIsolation": True,
        "sqlMatchedBeforeApiStart": True, "runCount": 1, "outcomeCount": 12,
        "counts": scenario["expected"], "timestampsAndFlywayHistoryPreserved": True,
        "allOutcomeReasonsMatched": True, "duplicateConstraintRejected": True,
        "apiRestartPreservedData": True, "productionPvcPreserved": True,
        "productionMountAndDataPreserved": True, "importSeconds": import_seconds,
        "totalSeconds": round(time.monotonic() - started, 3),
        "testWorkloadsStopped": True, "testPvcRetainedForFollowUp": True,
    }
    report = {"observedAt": dt.datetime.now(dt.timezone.utc).isoformat(), "namespace": namespace,
              "productionPvcUid": production_pvc["metadata"]["uid"],
              "restorePvcUid": trial_pvc["metadata"]["uid"], "restorePvName": trial_pv["metadata"]["name"],
              "backupDirectory": str(args.backup_directory), "dumpSha256": manifest["dumpSha256"],
              "baselineSha256": manifest["databaseBaselineSha256"], "publicSummary": summary}
    report_path = args.backup_directory / ("restore-drill-" + owner[BACKUP_ID] + "-" + secrets.token_hex(3) + ".json")
    with report_path.open("x", encoding="utf-8") as output:
        json.dump(report, output, indent=2)
        output.write("\n")
    report_path.chmod(0o600)
    return summary


def main() -> int:
    args = parser().parse_args()
    try:
        if os.name != "posix" or os.geteuid() != 0:
            raise DrillError("Run locally as root on the Ubuntu Lab host.")
        os.umask(0o077)
        print(json.dumps(execute_drill(args)))
        return 0
    except (DrillError, OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError) as failure:
        message = str(failure) if isinstance(failure, DrillError) else "Restore drill failed; private diagnostics were withheld."
        print(message, file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
