"""Install a fresh, single-node Platform Lab and verify each stage."""

import argparse
import base64
from contextlib import contextmanager
import copy
from datetime import datetime, timezone
import fcntl
import hashlib
import ipaddress
import json
import os
from pathlib import Path
import re
import secrets
import select
import shutil
import stat
import subprocess
import sys
import tempfile
import time
from urllib.request import ProxyHandler, build_opener

ROOT = Path(__file__).resolve().parents[2]
BASE = Path("/var/lib/devdooly-platform-lab")
STATE = BASE / "fresh-install"
CONFIG = Path("/etc/rancher/k3s/config.yaml")
KUBECONFIG = Path("/etc/rancher/k3s/k3s.yaml")
BINARY = Path("/usr/local/bin/k3s")
UNIT = Path("/etc/systemd/system/k3s.service")
KUBECTL = STATE / "kubectl"
NS = "platform-lab"
RELEASE = "lab"
APP = "platform-lab-fresh"
PUBLIC_REPO = "https://github.com/DevDooly/devdooly-platform-lab.git"
SOURCE = "c7540354fca2bd65d4cdcb576e7fba9ddd483928"
API_IMAGE = {
    "repository": "ghcr.io/devdooly/devdooly-platform-lab-api",
    "digest": "sha256:a7fbcefb482c1bd6149663196845b33f30323b897261c567f3c82d583e457441",
}
WEB_IMAGE = {
    "repository": "ghcr.io/devdooly/devdooly-platform-lab-web",
    "digest": "sha256:ed9d743726a2b451cbd0dabcf6f41c10f821ec75808d1480491a0a59f22b553c",
}
TOPIC = "platform-lab-dispatch-v1"
BUCKET = "platform-lab-synthetic"
KEY_NAME = "platform-lab-worker"
RUN_ID = "lab-fixture-fresh-install-v1"
CONTAINER_PREFIX = "lab-platform-lab"
POD_CIDR = "10.42.0.0/16"
SERVICE_CIDR = "10.43.0.0/16"
ENV = {
    "PATH": os.environ["PATH"], "HOME": "/root", "LC_ALL": "C",
    "KUBECONFIG": str(KUBECONFIG), "KUBECTL": str(KUBECTL),
    "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": "/dev/null", "GIT_TERMINAL_PROMPT": "0",
    "HELM_CONFIG_HOME": str(STATE / "helm-config"),
    "HELM_CACHE_HOME": str(STATE / "helm-cache"),
    "HELM_DATA_HOME": str(STATE / "helm-data"),
}
STAGES = (
    "01-k3s", "02-helm-and-argocd", "03-mariadb", "04-api-and-astro",
    "05-kafka-topic", "06-garage-s3", "07-worker-and-fixture",
    "08-jenkins", "09-monitoring", "10-final-checks",
)
PRIVATE_NETWORKS = tuple(ipaddress.ip_network(network) for network in
                         ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16"))
HTTP = build_opener(ProxyHandler({}))
LOG = None


class InstallError(Exception):
    """A safe-to-print diagnostic."""


def need(condition, message):
    if not condition:
        raise InstallError(message)


def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def record(stage, status):
    row = {"at": now(), "stage": stage, "status": status}
    print(f"{row['at']} {status} {stage}", flush=True)
    with (STATE / "stages.jsonl").open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(row) + "\n")


def command(args, *, data=None, timeout=120, check=True, sensitive=False, extra_env=None):
    result = subprocess.run([str(arg) for arg in args], input=data, capture_output=True,
                            timeout=timeout, env=ENV | (extra_env or {}))
    if result.returncode and check:
        if LOG is not None and not sensitive:
            with LOG.open("ab") as stream:
                stream.write(result.stderr)
                stream.write(result.stdout)
        raise InstallError(f"{Path(args[0]).name} exited {result.returncode}")
    return result


def kubectl(*args, **options):
    return command((BINARY, "kubectl", *args), **options).stdout


def get(resource, name=None, namespace=None, *, optional=False):
    args = ["get", resource]
    if name:
        args.append(name)
    if namespace:
        args += ["-n", namespace]
    if optional:
        args.append("--ignore-not-found")
    raw = kubectl(*args, "-o", "json", sensitive=True)
    return json.loads(raw) if raw else None


def apply_json(document):
    kubectl("apply", "--server-side", "--field-manager=devdooly-fresh-lab", "-f", "-",
            data=json.dumps(document).encode(), sensitive=True)


def manifest(kind, name, namespace=None, api="v1"):
    metadata = {"name": name, "labels": {"app.kubernetes.io/managed-by": "devdooly-fresh-lab"}}
    if namespace:
        metadata["namespace"] = namespace
    return {"apiVersion": api, "kind": kind, "metadata": metadata}


def ensure_namespace(namespace):
    existing = get("namespace", namespace, optional=True)
    if existing:
        need(existing["metadata"].get("labels", {}).get("app.kubernetes.io/managed-by") ==
             "devdooly-fresh-lab", f"Namespace {namespace} has a different owner")
    else:
        apply_json(manifest("Namespace", namespace))


def ensure_secret(name, values):
    document = manifest("Secret", name, NS)
    document["type"] = "Opaque"
    document["data"] = {key: base64.b64encode(value.encode()).decode() for key, value in values.items()}
    existing = get("secret", name, NS, optional=True)
    if existing:
        need(existing["metadata"].get("labels", {}).get("app.kubernetes.io/managed-by") ==
             "devdooly-fresh-lab" and existing.get("data") == document["data"],
             f"Secret {name} differs from the installer record")
    else:
        kubectl("create", "-f", "-", data=json.dumps(document).encode(), sensitive=True)


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path, document):
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def secure_path(path, *, directory=False):
    metadata = path.lstat()
    kind = stat.S_ISDIR if directory else stat.S_ISREG
    need(kind(metadata.st_mode) and metadata.st_uid == 0 and not metadata.st_mode & 0o022,
         f"Untrusted owner or permissions at {path}")


def preflight(node_ip):
    need(os.geteuid() == 0, "Run the reviewed command with sudo")
    need(sys.platform == "linux" and os.uname().machine == "x86_64", "Expected Linux amd64")
    os_release = dict(line.split("=", 1) for line in Path("/etc/os-release").read_text().splitlines()
                      if "=" in line and not line.startswith("#"))
    need(os_release.get("ID", "").strip('"') == "ubuntu" and
         os_release.get("VERSION_ID", "").strip('"') == "22.04" and
         Path("/run/systemd/system").is_dir(), "Expected Ubuntu 22.04 with systemd")
    for tool in ("bash", "curl", "git", "ip", "ss", "systemctl", "tar", "install"):
        need(shutil.which(tool, path=ENV["PATH"]), f"Install prerequisite command {tool} before proceeding")
    try:
        address = ipaddress.IPv4Address(node_ip)
    except ipaddress.AddressValueError:
        raise InstallError("Use the server's assigned stable RFC1918 IPv4 address") from None
    need(any(address in network for network in PRIVATE_NETWORKS), "Use an assigned RFC1918 IPv4 address")
    local = json.loads(command(("ip", "-j", "address", "show")).stdout)
    addresses = [interface["ifname"] for interface in local
                 for entry in interface.get("addr_info", []) if entry.get("local") == node_ip]
    need(len(addresses) == 1 and addresses[0] != "lo",
         "The requested node IPv4 must be assigned to exactly one non-loopback interface")
    owner = {"machineId": Path("/etc/machine-id").read_text().strip(), "nodeIp": node_ip,
             "interface": addresses[0], "schema": 1}
    need(re.fullmatch(r"[a-f0-9]{32}", owner["machineId"]), "A valid machine-id is required")
    memory = Path("/proc/meminfo").read_text().splitlines()
    total_kib = int(next(row.split()[1] for row in memory if row.startswith("MemTotal:")))
    need(total_kib >= 10 * 1024 * 1024, "At least 10 GiB of reported memory is required")
    if BASE.exists() or BASE.is_symlink():
        secure_path(BASE, directory=True)
        secure_path(STATE, directory=True)
        secure_path(STATE / "owner.json")
        need(read_json(STATE / "owner.json") == owner, "This is not the installer-owned host and node address")
        return owner, False

    need(shutil.disk_usage("/var/lib").free >= 65 * 1024 ** 3, "At least 65 GiB free under /var/lib is required")
    paths = [CONFIG.parent, KUBECONFIG, BINARY, UNIT, Path("/etc/rancher/rke2"), Path("/etc/kubernetes"),
             Path("/var/lib/rancher"), Path("/var/lib/kubelet"), Path("/etc/cni/net.d"), Path("/var/lib/cni"),
             Path("/run/k3s"), Path("/usr/local/bin/k3s-uninstall.sh"), Path("/usr/local/bin/k3s-killall.sh"),
             Path("/etc/systemd/system/k3s.service.env"), Path("/etc/systemd/system/k3s.service.d"),
             Path("/etc/default/k3s"), Path("/etc/sysconfig/k3s")]
    for path in paths:
        need(not path.exists() and not path.is_symlink(), f"Existing Kubernetes path requires review: {path}")
    need(not shutil.which("k3s", path=ENV["PATH"]), "Existing K3s binary requires review")
    if Path("/var/run/docker.sock").is_socket():
        need(shutil.which("docker", path=ENV["PATH"]), "Existing Docker socket requires independent review")
        need(not command(("docker", "ps", "-q")).stdout.strip(), "Running Docker containers require independent review")
    units = command(("systemctl", "list-unit-files", "k3s*", "rke2*", "kubelet*", "--no-legend")).stdout
    need(not units.strip(), "Existing Kubernetes unit requires review")
    for port in (6443, 6444, 10248, 10249, 10250, 10256, 10257, 10258, 10259, 10010):
        need(not command(("ss", "-H", "-lnt", f"sport = :{port}")).stdout, f"Required TCP port {port} is occupied")
    need(not command(("ss", "-H", "-lnu", "sport = :8472")).stdout, "VXLAN port 8472 is occupied")
    routes = json.loads(command(("ip", "-j", "-4", "route", "show", "table", "all")).stdout)
    for route in routes:
        destination = route.get("dst")
        if destination and destination != "default":
            network = ipaddress.IPv4Network(destination, strict=False)
            need(not any(network.overlaps(ipaddress.ip_network(candidate)) for candidate in (POD_CIDR, SERVICE_CIDR)),
                 "Existing route overlaps the planned Pod or Service CIDR")
    if CONFIG.parent.parent.exists() or CONFIG.parent.parent.is_symlink():
        secure_path(CONFIG.parent.parent, directory=True)
    return owner, True


def check_digest(path, expected):
    with path.open("rb") as stream:
        digest = hashlib.sha256()
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    need(digest.hexdigest() == expected, f"SHA256 mismatch for {path.name}")


def pinned_file(spec, destination):
    if not destination.exists():
        temporary = destination.with_suffix(destination.suffix + ".part")
        command(("curl", "--proto", "=https", "--tlsv1.2", "-fsSL", "--retry", "2",
                 "--connect-timeout", "15", "--max-time", "600", spec["url"], "-o", temporary), timeout=650)
        check_digest(temporary, spec["sha256"])
        temporary.replace(destination)
    check_digest(destination, spec["sha256"])
    return destination


def k3s_config(node_ip, interface):
    # JSON is valid YAML and retains Kubernetes-compatible primitive types.
    return {
        "data-dir": str(BASE / "k3s"), "default-local-storage-path": str(BASE / "storage"),
        "write-kubeconfig-mode": "0600", "secrets-encryption": True,
        "bind-address": node_ip, "advertise-address": node_ip, "node-ip": node_ip,
        "tls-san": ["127.0.0.1", node_ip], "cluster-cidr": POD_CIDR, "service-cidr": SERVICE_CIDR,
        "flannel-iface": interface, "disable": ["traefik", "servicelb"],
    }


def install_k3s(lock, node_ip, interface):
    spec = lock["k3s"]
    source_binary = pinned_file(spec["linuxAmd64"], STATE / "k3s.bin")
    sums = pinned_file(spec["checksumListAmd64"], STATE / "sha256sum-amd64.txt")
    need(any(line.split() == [spec["linuxAmd64"]["sha256"], "k3s"]
             for line in sums.read_text().splitlines()), "K3s release checksum list does not match")
    installer = pinned_file(spec["installer"], STATE / "k3s-installer.sh")
    command(("bash", "-n", installer))
    config = k3s_config(node_ip, interface)
    if CONFIG.exists():
        secure_path(CONFIG)
        need(read_json(CONFIG) == config, "K3s configuration changed since install preparation")
    else:
        CONFIG.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        write_json(CONFIG, config)
    if BINARY.exists():
        secure_path(BINARY)
        check_digest(BINARY, spec["linuxAmd64"]["sha256"])
    else:
        command(("install", "-m", "0755", source_binary, BINARY))
    if not UNIT.exists():
        command(("sh", installer), extra_env={
            "INSTALL_K3S_VERSION": spec["version"], "INSTALL_K3S_SKIP_DOWNLOAD": "true",
            "INSTALL_K3S_SKIP_ENABLE": "true", "INSTALL_K3S_SKIP_START": "true",
            "INSTALL_K3S_SKIP_SELINUX_RPM": "true", "INSTALL_K3S_SYMLINK": "skip",
            "INSTALL_K3S_BIN_DIR": str(BINARY.parent), "INSTALL_K3S_SYSTEMD_DIR": str(UNIT.parent),
            "INSTALL_K3S_EXEC": "server",
        })
    secure_path(UNIT)
    if not KUBECTL.exists():
        KUBECTL.write_text("#!/bin/sh\nexec /usr/local/bin/k3s kubectl \"$@\"\n", encoding="utf-8")
        KUBECTL.chmod(0o700)
    command(("systemctl", "daemon-reload"))
    command(("systemctl", "enable", UNIT.stem))
    command(("systemctl", "start", UNIT.stem), timeout=300)
    verify_k3s(lock, node_ip, interface)


def verify_k3s(lock, node_ip, interface):
    command(("systemctl", "is-active", "--quiet", "k3s"))
    secure_path(CONFIG)
    need(read_json(CONFIG) == k3s_config(node_ip, interface), "K3s configuration drifted from the reviewed installation")
    secure_path(BINARY)
    check_digest(BINARY, lock["k3s"]["linuxAmd64"]["sha256"])
    secure_path(KUBECONFIG)
    need(KUBECONFIG.stat().st_mode & 0o077 == 0, "K3s kubeconfig must be private")
    deadline = time.monotonic() + 180
    while time.monotonic() < deadline:
        ready = command((BINARY, "kubectl", "get", "--raw=/readyz", "--request-timeout=10s"),
                        timeout=15, check=False)
        if ready.returncode == 0 and get("nodes")["items"]:
            break
        time.sleep(3)
    else:
        raise InstallError("Kubernetes API or node registration did not arrive before timeout")
    kubectl("wait", "--for=condition=Ready", "nodes", "--all", "--timeout=300s", timeout=320)
    nodes = get("nodes")["items"]
    need(len(nodes) == 1 and nodes[0]["status"]["nodeInfo"]["kubeletVersion"] == lock["k3s"]["version"] and
         {"type": "InternalIP", "address": node_ip} in nodes[0]["status"]["addresses"],
         "Expected the pinned single Ready node with the assigned internal IP")
    for deployment in ("coredns", "local-path-provisioner"):
        resource = f"deployment/{deployment}"
        kubectl("wait", "--for=create", resource, "-n", "kube-system", "--timeout=180s", timeout=200)
        rollout(resource, "kube-system")
    kubectl("wait", "--for=create", "storageclass/local-path", "--timeout=120s", timeout=140)
    need(get("storageclass", "local-path")["provisioner"] == "rancher.io/local-path", "Unexpected storage class")


def helm(*args, **options):
    return command((STATE / "helm", *args), **options).stdout


def helm_archive(lock, key):
    spec = lock["charts"][key]
    name = "argo-cd" if key == "argocd" else key
    file_name = f"{name}-{spec['version']}.tgz"
    path = STATE / file_name
    if not path.exists():
        with tempfile.TemporaryDirectory(dir=STATE) as directory:
            helm("pull", name, "--repo", spec["repository"], "--version", spec["version"],
                 "--destination", directory, timeout=300)
            downloaded = Path(directory) / file_name
            check_digest(downloaded, spec["sha256"])
            downloaded.replace(path)
    check_digest(path, spec["sha256"])
    return path


def prepare_helm(lock):
    archive = pinned_file(lock["helm"]["linuxAmd64"], STATE / "helm-linux-amd64.tar.gz")
    expected = command(("tar", "-xOf", archive, "linux-amd64/helm")).stdout
    binary = STATE / "helm"
    if not binary.exists():
        binary.write_bytes(expected)
        binary.chmod(0o700)
    else:
        secure_path(binary)
        need(binary.read_bytes() == expected, "The installer-owned Helm binary changed")
    need(helm("version", "--template", "{{.Version}}").decode().strip() == lock["helm"]["version"],
         "Helm version verification failed")


def install_chart(lock, name, namespace):
    ensure_namespace(namespace)
    file = helm_archive(lock, name)
    helm("upgrade", "--install", name, file, "--namespace", namespace, "--values",
         ROOT / f"infra/platform/{name}-values.yaml", "--wait", "--timeout", "15m", timeout=930)


def rollout(resource, namespace=NS):
    kubectl("rollout", "status", resource, "-n", namespace, "--timeout=420s", timeout=440)


def setup_argocd(lock):
    prepare_helm(lock)
    install_chart(lock, "argocd", "argocd")
    rollout("deployment/argocd-server", "argocd")
    rollout("deployment/argocd-repo-server", "argocd")
    rollout("statefulset/argocd-application-controller", "argocd")


def secrets_for_lab():
    path = STATE / "cluster-secrets.json"
    if not path.exists():
        write_json(path, {"db": secrets.token_hex(32), "rootDb": secrets.token_hex(32),
                          "garageRpc": secrets.token_hex(32), "clusterId": secrets.token_urlsafe(16)})
    secure_path(path)
    return read_json(path)


def pinned_chart():
    clone = STATE / "chart-source"
    path = clone / "infra/charts/platform-lab"
    if not (clone / ".git").exists():
        command(("git", "init", "-q", clone))
    oid = command(("git", "-C", clone, "rev-parse", "HEAD"), check=False)
    if oid.returncode:
        command(("git", "-C", clone, "fetch", "--no-tags", "--depth=1", PUBLIC_REPO, SOURCE), timeout=300)
        need(command(("git", "-C", clone, "rev-parse", "FETCH_HEAD")).stdout.decode().strip() == SOURCE,
             "Pinned chart source fetched with a different SHA")
        command(("git", "-C", clone, "checkout", "--detach", SOURCE), timeout=300)
    need(command(("git", "-C", clone, "rev-parse", "HEAD")).stdout.decode().strip() == SOURCE and
         not command(("git", "-C", clone, "status", "--porcelain", "--", "infra/charts/platform-lab")).stdout,
         "The pinned chart source changed locally")
    return path


def values(level):
    config = {
        "api": {"image": API_IMAGE, "sourceCommit": SOURCE, "environment": "k3s"},
        "web": {"image": WEB_IMAGE}, "database": {"existingSecret": "platform-lab-db"},
    }
    if level >= 1:
        config["runtime"] = {"kafka": {"enabled": True, "existingSecret": "platform-lab-kafka"}}
    if level >= 2:
        config["runtime"]["garage"] = {"enabled": True, "existingConfigSecret": "platform-lab-garage"}
    if level >= 3:
        # The upstream schema names the continuous-runtime profile "mini-pc".
        config["api"].update(environment="mini-pc", kafkaObservation={"enabled": True})
        config["runtime"]["worker"] = {
            "enabled": True, "progressProbeEnabled": True, "environment": "mini-pc",
            "sourceCommit": SOURCE, "image": API_IMAGE, "existingS3Secret": "platform-lab-runtime-s3",
        }
    return config


def bootstrap_database():
    ensure_namespace(NS)
    credentials = secrets_for_lab()
    ensure_secret("platform-lab-db", {"app-password": credentials["db"], "root-password": credentials["rootDb"]})
    path = STATE / "db-values.json"
    write_json(path, values(0))
    # The chart requires one API/web replica. Apply only the exact DB workload
    # and service definitions before handing ownership to the Argo application.
    rendered = helm("template", RELEASE, pinned_chart(), "-n", NS, "-f", path,
                    "--show-only", "templates/serviceaccount.yaml",
                    "--show-only", "templates/services.yaml",
                    "--show-only", "templates/database-statefulset.yaml")
    kubectl("apply", "--server-side", "--field-manager=devdooly-fresh-lab",
            "-n", NS, "-f", "-", data=rendered)
    verify_database()


def verify_database():
    rollout(f"statefulset/{CONTAINER_PREFIX}-db")
    kubectl("wait", "--for=jsonpath={.status.phase}=Bound", f"pvc/data-{CONTAINER_PREFIX}-db-0",
            "-n", NS, "--timeout=120s", timeout=140)
    kubectl("exec", "-n", NS, f"{CONTAINER_PREFIX}-db-0", "--",
            "healthcheck.sh", "--connect", "--innodb_initialized")


def project():
    document = manifest("AppProject", APP, "argocd", "argoproj.io/v1alpha1")
    kinds = {"apps": ("Deployment", "StatefulSet"),
             "": ("Service", "PersistentVolumeClaim", "ServiceAccount", "ConfigMap")}
    document["spec"] = {
        "sourceRepos": [PUBLIC_REPO],
        "destinations": [{"namespace": NS, "server": "https://kubernetes.default.svc"}],
        "clusterResourceWhitelist": [],
        "namespaceResourceWhitelist": [{"group": group, "kind": kind} for group, members in kinds.items()
                                       for kind in members],
    }
    return document


def application(level):
    document = manifest("Application", APP, "argocd", "argoproj.io/v1alpha1")
    document["spec"] = {
        "project": APP,
        "source": {"repoURL": PUBLIC_REPO, "targetRevision": SOURCE,
                   "path": "infra/charts/platform-lab", "helm": {"releaseName": RELEASE, "valuesObject": values(level)}},
        "destination": {"namespace": NS, "server": "https://kubernetes.default.svc"},
        "syncPolicy": {"automated": {"prune": False, "selfHeal": True},
                       "retry": {"limit": 3}},
    }
    return document


def sync(level):
    apply_json(application(level))
    verify_sync(level)


def verify_sync(level):
    deadline = time.monotonic() + 480
    expected = application(level)["spec"]
    while time.monotonic() < deadline:
        value = get("applications.argoproj.io", APP, "argocd")
        status = value.get("status", {})
        compared = status.get("sync", {})
        if (value["spec"]["source"] == expected["source"] and
                compared.get("revision") == SOURCE and compared.get("status") == "Synced" and
                compared.get("comparedTo", {}).get("source", {}).get("helm", {}).get("valuesObject") == values(level) and
                status.get("health", {}).get("status") == "Healthy"):
            return
        time.sleep(5)
    raise InstallError("Argo CD did not confirm the exact pinned revision and current stage values")


@contextmanager
def forward(namespace, service, remote_port):
    process = subprocess.Popen((str(BINARY), "kubectl", "-n", namespace, "port-forward",
                                "--address", "127.0.0.1", f"service/{service}", f":{remote_port}"),
                               stdout=subprocess.PIPE, stderr=subprocess.STDOUT, env=ENV)
    try:
        deadline = time.monotonic() + 25
        while time.monotonic() < deadline:
            if not select.select([process.stdout], [], [], 1)[0]:
                continue
            line = process.stdout.readline()
            match = re.fullmatch(rb"Forwarding from 127\.0\.0\.1:(\d+) -> \d+\n", line)
            if match:
                yield f"http://127.0.0.1:{int(match[1])}"
                return
            if not line:
                break
        raise InstallError(f"Local port-forward failed for {namespace}/{service}")
    finally:
        process.terminate()
        try:
            process.wait(5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(5)
        process.stdout.close()


def web_read(base, path):
    with HTTP.open(base + path, timeout=10) as response:
        need(response.status == 200, f"Unexpected HTTP status at {path}")
        return response.read(4 * 1024 * 1024)


def image_ref(image):
    return f"{image['repository']}@{image['digest']}"


def verify_image(component, image):
    deployment = get("deployment", f"{CONTAINER_PREFIX}-{component}", NS)
    containers = deployment["spec"]["template"]["spec"]["containers"]
    need(any(container["name"] == component and container["image"] == image_ref(image) for container in containers),
         f"The {component} Deployment uses a different image")
    pods = get("pods", namespace=NS)["items"]
    statuses = [container for pod in pods if pod["metadata"].get("labels", {}).get("app.kubernetes.io/component") == component
                and not pod["metadata"].get("deletionTimestamp")
                for container in pod.get("status", {}).get("containerStatuses", []) if container["name"] == component]
    need(len(statuses) == 1 and statuses[0]["ready"] and
         statuses[0]["imageID"].removeprefix("docker-pullable://") == image_ref(image),
         f"The running {component} container does not match the pinned digest")


def verify_web():
    verify_image("api", API_IMAGE)
    verify_image("web", WEB_IMAGE)
    with forward(NS, "web", 8080) as base:
        need(b"DevDooly" in web_read(base, "/"), "Astro content was not served by the web workload")
        summary = json.loads(web_read(base, "/api/platform/summary"))
        database = next((row for row in summary["components"] if row["name"] == "DATABASE"), {})
        need(summary["status"] == "UP" and summary["sourceCommit"] == SOURCE and
             summary["publicExecutionEnabled"] is False and database.get("status") == "RUNNING" and
             database.get("detail") == "MariaDB", "API summary did not confirm the pinned source and MariaDB")
        sample = json.loads(web_read(base, "/api/demo/runs/synthetic-v1-seed-42"))
        expected = read_json(ROOT / "tests/scenarios/sensor-validation-v1.json")["expected"]
        need(all(sample.get(key) == value for key, value in expected.items()), "API seed sample totals differ")
        # The additional job observation endpoint reads current DB-backed runtime state.
        jobs = json.loads(web_read(base, "/api/jobs/observation"))
        need(jobs["sourceCommit"] == SOURCE and jobs["publicExecutionEnabled"] is False,
             "API job observation does not match the pinned source")


def verify_migrations():
    query = "SELECT version, success FROM flyway_schema_history WHERE version IS NOT NULL ORDER BY installed_rank"
    migrations = kubectl(
        "exec", "-n", NS, f"{CONTAINER_PREFIX}-db-0", "--", "sh", "-ec",
        'MYSQL_PWD="$MARIADB_PASSWORD" mariadb --protocol=tcp --host=127.0.0.1 '
        '--user="$MARIADB_USER" --database="$MARIADB_DATABASE" --batch --skip-column-names --execute="$1"',
        "mariadb", query, sensitive=True,
    ).decode().splitlines()
    need(migrations == [f"{version}\t1" for version in range(1, 5)], "Expected successful Flyway migrations V1 through V4")


def setup_api():
    apply_json(project())
    sync(0)
    rollout(f"deployment/{CONTAINER_PREFIX}-api")
    rollout(f"deployment/{CONTAINER_PREFIX}-web")
    verify_migrations()
    verify_web()


def kafka(*args):
    return kubectl("exec", "-n", NS, f"{CONTAINER_PREFIX}-kafka-0", "--",
                   "/opt/kafka/bin/kafka-topics.sh", "--bootstrap-server",
                   "kafka.platform-lab.svc.cluster.local:9092", *args, timeout=120).decode()


def verify_kafka():
    description = kafka("--describe", "--topic", TOPIC)
    need(re.search(r"PartitionCount:\s*1\b", description) and
         re.search(r"ReplicationFactor:\s*1\b", description) and
         all(value in description for value in ("min.insync.replicas=1", "retention.ms=604800000",
                                               "retention.bytes=134217728", "max.message.bytes=1024")),
         "Kafka topic partition, replication, or retention settings differ")


def setup_kafka():
    ensure_secret("platform-lab-kafka", {"cluster-id": secrets_for_lab()["clusterId"]})
    sync(1)
    rollout(f"statefulset/{CONTAINER_PREFIX}-kafka")
    kafka("--create", "--if-not-exists", "--topic", TOPIC, "--partitions", "1", "--replication-factor", "1",
          "--config", "min.insync.replicas=1", "--config", "retention.ms=604800000",
          "--config", "retention.bytes=134217728", "--config", "max.message.bytes=1024")
    verify_kafka()


def garage(*args):
    return kubectl("exec", "-n", NS, f"{CONTAINER_PREFIX}-garage-0", "--",
                   "/garage", "-c", "/etc/garage/garage.toml", *args, timeout=120, sensitive=True)


def garage_json(operation, payload):
    return json.loads(garage("json-api", operation, json.dumps(payload)))


def verify_s3():
    bucket = garage_json("GetBucketInfo", {"globalAlias": BUCKET})
    path = STATE / "garage-key.json"
    secure_path(path)
    key = read_json(path)
    acl = garage_json("GetKeyInfo", {"id": key["accessKeyId"], "showSecretKey": False})
    need(acl["accessKeyId"] == key["accessKeyId"] and not acl["expired"] and
         acl["permissions"]["createBucket"] is False and len(acl["buckets"]) == 1 and
         acl["buckets"][0]["id"] == bucket["id"] and
         acl["buckets"][0]["permissions"] == {"read": True, "write": True, "owner": False},
         "Garage synthetic bucket key does not have the scoped read/write permissions")


def setup_garage():
    rpc = secrets_for_lab()["garageRpc"]
    config = (
        'metadata_dir="/var/lib/garage/meta"\ndata_dir="/var/lib/garage/data"\ndb_engine="sqlite"\n'
        'replication_factor=1\nrpc_bind_addr="127.0.0.1:3901"\nrpc_public_addr="127.0.0.1:3901"\n'
        f'rpc_secret="{rpc}"\n[s3_api]\ns3_region="garage"\napi_bind_addr="0.0.0.0:3900"\n'
    )
    ensure_secret("platform-lab-garage", {"garage.toml": config})
    sync(2)
    rollout(f"statefulset/{CONTAINER_PREFIX}-garage")
    node = garage("node", "id", "--quiet").decode().strip().split("@", 1)[0]
    need(re.fullmatch(r"[a-f0-9]{64}", node), "Garage did not return a valid node ID")
    layout = garage_json("GetClusterLayout", {})
    need(layout["version"] in (0, 1), "Garage layout is not the fresh single-node layout")
    if layout["version"] == 0:
        need(not layout["roles"] and all(row["id"] == node for row in layout["stagedRoleChanges"]),
             "Garage has layout changes for another node")
        garage("layout", "assign", "-z", "fresh-lab", "-c", "8G", node)
        garage("layout", "apply", "--version", "1")
    layout = garage_json("GetClusterLayout", {})
    need(layout["version"] == 1 and len(layout["roles"]) == 1 and
         layout["roles"][0]["id"] == node and layout["roles"][0]["zone"] == "fresh-lab" and
         layout["roles"][0]["capacity"], "Garage layout does not exclusively assign the expected node")
    matches = [row for row in garage_json("ListBuckets", {}) if BUCKET in row["globalAliases"]]
    need(len(matches) <= 1, "Garage bucket alias is ambiguous")
    bucket = (garage_json("GetBucketInfo", {"globalAlias": BUCKET}) if matches else
              garage_json("CreateBucket", {"globalAlias": BUCKET}))
    path = STATE / "garage-key.json"
    if not path.exists():
        keys = [row for row in garage_json("ListKeys", {}) if row["name"] == KEY_NAME]
        need(len(keys) <= 1, "Garage worker key name is ambiguous")
        # A GET after an interrupted local save recovers the same key.
        key = (garage_json("GetKeyInfo", {"id": keys[0]["id"], "showSecretKey": True}) if keys else
               garage_json("CreateKey", {"name": KEY_NAME}))
        write_json(path, {name: key[name] for name in ("accessKeyId", "secretAccessKey")})
    secure_path(path)
    key = read_json(path)
    garage_json("AllowBucketKey", {"bucketId": bucket["id"], "accessKeyId": key["accessKeyId"],
                                  "permissions": {"read": True, "write": True, "owner": False}})
    ensure_secret("platform-lab-runtime-s3", {"access-key-id": key["accessKeyId"],
                                              "secret-access-key": key["secretAccessKey"]})
    verify_s3()


def start_fixture():
    name = "platform-lab-fresh-fixture"
    existing = get("job", name, NS, optional=True)
    if existing:
        need(existing["metadata"].get("labels", {}).get("app.kubernetes.io/managed-by") ==
             "devdooly-fresh-lab", "Existing fixture Job has a different owner")
    else:
        worker = get("deployment", f"{CONTAINER_PREFIX}-worker", NS)
        pod_spec = copy.deepcopy(worker["spec"]["template"]["spec"])
        pod_spec["restartPolicy"] = "Never"
        pod_spec["terminationGracePeriodSeconds"] = 30
        container = pod_spec["containers"][0]
        container["name"] = "stage"
        container["args"] = ["--lab-runtime=stage"]
        container.pop("readinessProbe", None)
        container["env"] = [row for row in container["env"] if row["name"] not in
                            ("LAB_RUNTIME_PROGRESS_FILE", "LAB_RUNTIME_POD_UID")]
        container["env"].append({"name": "LAB_RUNTIME_STAGE_RUN_ID", "value": RUN_ID})
        job = manifest("Job", name, NS, "batch/v1")
        job["spec"] = {"backoffLimit": 0, "activeDeadlineSeconds": 300, "template": {"spec": pod_spec}}
        kubectl("create", "-f", "-", data=json.dumps(job).encode(), sensitive=True)
    deadline = time.monotonic() + 330
    while time.monotonic() < deadline:
        job = get("job", name, NS)
        conditions = {entry["type"]: entry["status"] for entry in job.get("status", {}).get("conditions", [])}
        if conditions.get("Complete") == "True":
            return
        need(conditions.get("Failed") != "True" and conditions.get("FailureTarget") != "True",
             "The owned fixture Job failed; inspect its logs before deciding whether to retry")
        time.sleep(5)
    raise InstallError("The owned fixture Job did not reach Complete before timeout")


def verify_fixture():
    with forward(NS, "web", 8080) as base:
        deadline = time.monotonic() + 300
        while time.monotonic() < deadline:
            view = json.loads(web_read(base, "/api/jobs/observation"))
            runtime = view["runtime"]
            need(runtime["status"] != "PAUSED_OPERATOR", "Worker is paused and needs explicit operator review")
            rows = [job for job in view["jobs"] if job["runId"] == RUN_ID]
            if rows and rows[0]["exportStatus"] == "EXPORTED":
                job = rows[0]
                need(runtime["status"] == "RUNNING" and runtime["sourceCommit"] == SOURCE and
                     not runtime["stale"] and view["slot"]["occupiedRunId"] is None and
                     job["counts"] == {"input": 12, "success": 7, "failure": 3, "duplicate": 2, "pending": 0} and
                     job["fileEvidence"] == "VERIFIED_AT_EXPORT_COMMIT" and
                     all(re.fullmatch(r"[a-f0-9]{64}", item["sha256"]) and item["size"] > 0
                         for item in (job["files"]["result"], job["files"]["failures"])),
                     "Fixture export, slot release, or active worker evidence is incomplete")
                return
            time.sleep(5)
    raise InstallError("Worker did not consume and export the fixed fixture before timeout")


def setup_worker():
    sync(3)
    rollout(f"deployment/{CONTAINER_PREFIX}-worker")
    verify_image("worker", API_IMAGE)
    start_fixture()
    verify_fixture()


def verify_jenkins(lock):
    rollout("statefulset/jenkins", "jenkins")
    with forward("jenkins", "jenkins", 8080) as base:
        with HTTP.open(base + "/login", timeout=15) as response:
            need(response.status == 200 and response.headers.get("X-Jenkins") ==
                 lock["charts"]["jenkins"]["appVersion"], "Jenkins login or pinned version did not verify")


def setup_jenkins(lock):
    install_chart(lock, "jenkins", "jenkins")
    verify_jenkins(lock)


def monitoring():
    result = command(("bash", ROOT / "infra/lab-monitoring/install.sh"), timeout=1200)
    with LOG.open("ab") as stream:
        stream.write(result.stdout)


def final_checks(lock, node_ip, interface):
    verify_k3s(lock, node_ip, interface)
    verify_sync(3)
    verify_database()
    verify_migrations()
    verify_web()
    verify_kafka()
    verify_s3()
    verify_image("worker", API_IMAGE)
    verify_fixture()
    verify_jenkins(lock)
    rollout("deployment/grafana", "platform-lab-monitoring")
    with forward("platform-lab-monitoring", "grafana", 3000) as base:
        need(json.loads(web_read(base, "/api/health"))["database"] == "ok", "Grafana health check failed")
    write_json(STATE / "verification.json", {
        "observedAt": now(), "chartSource": SOURCE,
        "scope": "fresh-single-node-k3s", "argo": {"application": APP, "state": "Synced/Healthy"},
        "images": {"api": image_ref(API_IMAGE), "web": image_ref(WEB_IMAGE), "worker": image_ref(API_IMAGE)},
        "fixture": {"id": RUN_ID, "exportStatus": "EXPORTED", "input": 12, "success": 7,
                    "failure": 3, "duplicate": 2, "pending": 0},
        "jenkins": {"verified": "login/version", "version": lock["charts"]["jenkins"]["appVersion"]},
        "grafana": {"verified": "workload health"},
    })


def install(owner, fresh, lock):
    global LOG
    if fresh:
        BASE.mkdir(mode=0o700)
        STATE.mkdir(mode=0o700)
        write_json(STATE / "owner.json", owner)
    stage_file = STATE / "completed.json"
    with (STATE / "install.lock").open("a") as mutex:
        try:
            fcntl.flock(mutex, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise InstallError("Another installation is running") from None
        completed = read_json(stage_file) if stage_file.exists() else []
        need(completed == list(STAGES[:len(completed)]), "Installer stage history is inconsistent")
        node_ip, interface = owner["nodeIp"], owner["interface"]
        steps = (
            lambda: install_k3s(lock, node_ip, interface), lambda: setup_argocd(lock), bootstrap_database,
            setup_api, setup_kafka, setup_garage, setup_worker, lambda: setup_jenkins(lock), monitoring,
            lambda: final_checks(lock, node_ip, interface),
        )
        if completed:
            verify_k3s(lock, node_ip, interface)
        for stage, action in zip(STAGES, steps):
            if stage in completed and stage != STAGES[-1]:
                print(f"{now()} RECORDED {stage}", flush=True)
                continue
            LOG = STATE / f"{stage}.log"
            record(stage, "START")
            try:
                action()
            except Exception as error:
                record(stage, "FAILED")
                with LOG.open("a", encoding="utf-8") as stream:
                    stream.write(f"{now()} {type(error).__name__}: {error}\n")
                raise InstallError(f"{stage} stopped. Inspect the private log {LOG}") from None
            if stage not in completed:
                completed.append(stage)
                write_json(stage_file, completed)
            record(stage, "OK")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check", action="store_true", help="Read-only preflight")
    mode.add_argument("--apply", action="store_true", help="Install on the reviewed dedicated VM")
    parser.add_argument("--node-ip", required=True, help="Existing stable private node IPv4")
    args = parser.parse_args()
    os.umask(0o077)
    try:
        lock = read_json(ROOT / "infra/platform/versions.lock.json")
        owner, fresh = preflight(args.node_ip)
        if args.check:
            print("Preflight passed for " + ("a dedicated fresh host" if fresh else "this installer-owned host"))
            for stage in STAGES:
                print(stage)
            return 0
        install(owner, fresh, lock)
    except (InstallError, OSError, ValueError, subprocess.SubprocessError) as error:
        print(f"STOP: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
