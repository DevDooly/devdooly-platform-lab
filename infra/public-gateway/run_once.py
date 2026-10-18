"""Linux-only isolated real-Nginx check. Never operates on a deployment or host port."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import shutil
import stat
import subprocess
import sys
import time
import uuid

NGINX = "nginx:stable-alpine@sha256:0985e772fb9f729e6fa0980da05fca5d9c468e870eed43071545afa9d2e27d94"
# Reuse the existing Spark CI base ONLY for its installed stdlib Python3.
# This command overrides the entrypoint; no Spark/JVM process is launched.
PYTHON_FIXTURE = "docker.io/apache/spark@sha256:0b8f5befe00d258df03b252158b3894b8654390f1958741accf98155539a662a"
LABEL = "io.github.devdooly.public-gateway-attempt"
FILES = {"nginx.conf", "proxy.inc", "fake_upstream.py", "verify_http.py", "run_once.py", "README.md", "ci-step-proposal.yml", "source-image-evidence.json"}
PHASE = "SOURCE"


class Rejected(Exception):
    pass


def require(value):
    if not value:
        raise Rejected()


def read(path, maximum=131072):
    before = path.lstat()
    require(stat.S_ISREG(before.st_mode) and before.st_nlink == 1 and 0 < before.st_size <= maximum)
    with os.fdopen(os.open(path, os.O_RDONLY | os.O_NOFOLLOW), "rb") as stream:
        opened = os.fstat(stream.fileno())
        raw = stream.read(maximum + 1)
        after_fd = os.fstat(stream.fileno())
    after = path.lstat()
    identity = lambda value: (value.st_dev, value.st_ino, value.st_mode, value.st_nlink,
                              value.st_size, value.st_mtime_ns, value.st_ctime_ns)
    require(identity(before) == identity(opened) == identity(after_fd) == identity(after) and len(raw) == before.st_size)
    return raw


def unique(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result)
        result[key] = value
    return result


def source_gate(folder, expected):
    require(re.fullmatch("[a-f0-9]{64}", expected) is not None)
    raw = read(folder / "runtime-manifest.json")
    require(hashlib.sha256(raw).hexdigest() == expected)
    manifest = json.loads(raw, object_pairs_hook=unique)
    require(set(manifest) == {"schemaVersion", "scope", "files", "images"}
            and manifest["schemaVersion"] == 1 and manifest["scope"] == "ISOLATED_PUBLIC_READ_GATEWAY_PROTOTYPE"
            and manifest["images"] == {"nginx": NGINX, "pythonFixtureOnly": PYTHON_FIXTURE})
    require(isinstance(manifest["files"], list) and len(manifest["files"]) == len(FILES))
    sources = {}
    for item in manifest["files"]:
        require(set(item) == {"path", "sha256", "bytes"} and item["path"] in FILES and item["path"] not in sources)
        value = read(folder / item["path"])
        require(type(item["bytes"]) is int and len(value) == item["bytes"]
                and hashlib.sha256(value).hexdigest() == item["sha256"])
        sources[item["path"]] = value
    require(set(sources) == FILES)
    return sources


class Attempt:
    def __init__(self, folder, sources):
        self.folder = folder
        self.sources = sources
        self.nonce = uuid.uuid4().hex
        self.network = "pl-public-read-" + self.nonce
        self.names = {"fake": self.network + "-fake", "gateway": self.network + "-gateway"}
        self.ids = {}
        self.docker_ready = False
        self.output_owned = False
        self.deadline = time.monotonic() + 600
        self.docker = shutil.which("docker")
        require(self.docker is not None)
        self.output = folder.parents[1] / ".local/public-gateway-public"
        self.kit = self.output / "fixture-input"

    def command(self, args, maximum_seconds=30, *, allow_failure=False, quiet=False, cleanup=False):
        timeout = maximum_seconds if cleanup else min(maximum_seconds, self.deadline - time.monotonic())
        require(timeout > 0)
        result = subprocess.run([self.docker, *args], stdin=subprocess.DEVNULL,
                                stdout=subprocess.DEVNULL if quiet else subprocess.PIPE,
                                stderr=subprocess.DEVNULL, timeout=timeout, check=False)
        raw = b"" if quiet else result.stdout
        # Commands are fixed inspect/exec/limited-log selectors, never unrestricted service logs.
        require(len(raw) <= 262144)
        require(allow_failure or result.returncode == 0)
        return result.returncode, raw

    def inspect_container(self, name, *, optional=False, cleanup=False):
        code, raw = self.command(["container", "inspect", "--format", "{{json .}}", name],
                                 allow_failure=optional, cleanup=cleanup)
        if code:
            # A failed inspect alone does not prove absence (the daemon could be down).
            _, names = self.command(["container", "ls", "--all", "--filter", LABEL + "=" + self.nonce,
                                     "--format", "{{.Names}}"], cleanup=cleanup)
            require(name not in names.decode("ascii").splitlines())
            return None
        value = json.loads(raw)
        require(value["Name"] == "/" + name and value["Config"]["Labels"].get(LABEL) == self.nonce
                and re.fullmatch("[a-f0-9]{64}", value["Id"]) is not None)
        if name in self.ids:
            require(value["Id"] == self.ids[name])
        return value

    def assert_container(self, role):
        name = self.names[role]
        value = self.inspect_container(name)
        host = value["HostConfig"]
        uid = "185:185" if role == "fake" else "101:101"
        image = PYTHON_FIXTURE if role == "fake" else NGINX
        require(value["Config"]["User"] == uid and value["Config"]["Image"] == image)
        require(host["NetworkMode"] == self.network and set(value["NetworkSettings"]["Networks"]) == {self.network}
                and host["ReadonlyRootfs"] is True and host["Privileged"] is False
                and set(host["CapDrop"]) == {"ALL"} and host["CapAdd"] in (None, [])
                and host["PortBindings"] in ({}, None) and host["PublishAllPorts"] is False
                and host["PidMode"] == "" and host["IpcMode"] != "host"
                and host["Memory"] == 134217728 and host["NanoCpus"] == 250000000
                and host["PidsLimit"] == 64 and host["RestartPolicy"]["Name"] == "no"
                and any(item.startswith("no-new-privileges") for item in host["SecurityOpt"]))
        expected_mount = "/fixture" if role == "fake" else "/etc/public-gateway"
        mounts = value["Mounts"]
        binds = [item for item in mounts if item["Type"] == "bind"]
        require(all(item["Type"] in {"bind", "tmpfs"} for item in mounts)
                and all(item["Destination"] == "/tmp" for item in mounts if item["Type"] == "tmpfs")
                and len(binds) == 1 and binds[0]["RW"] is False and binds[0]["Destination"] == expected_mount
                and Path(binds[0]["Source"]).resolve() == self.kit.resolve())
        require(set(host["Tmpfs"]) == {"/tmp"})
        self.ids[name] = value["Id"]

    def network_info(self, *, optional=False, cleanup=False):
        code, raw = self.command(["network", "inspect", "--format", "{{json .}}", self.network],
                                 allow_failure=optional, cleanup=cleanup)
        if code:
            _, names = self.command(["network", "ls", "--filter", LABEL + "=" + self.nonce,
                                     "--format", "{{.Name}}"], cleanup=cleanup)
            require(self.network not in names.decode("ascii").splitlines())
            return None
        value = json.loads(raw)
        require(value["Name"] == self.network and value["Internal"] is True
                and value["Driver"] == "bridge" and value["Labels"].get(LABEL) == self.nonce
                and re.fullmatch("[a-f0-9]{64}", value["Id"]) is not None)
        return value

    def start(self):
        global PHASE
        require(sys.platform == "linux" and platform.machine() in {"x86_64", "amd64"})
        require(not any(os.environ.get(name) for name in ("DOCKER_HOST", "DOCKER_CONTEXT", "DOCKER_TLS_VERIFY", "DOCKER_CERT_PATH")))
        require(self.command(["context", "show"])[1].strip() == b"default")
        require(self.command(["info", "--format", "{{.OSType}}"])[1].strip() == b"linux")
        self.docker_ready = True
        self.output.mkdir(parents=True, exist_ok=False, mode=0o700)
        self.output_owned = True
        self.kit.mkdir(mode=0o755)
        for name in ("nginx.conf", "proxy.inc", "fake_upstream.py", "verify_http.py"):
            path = self.kit / name
            with path.open("xb") as stream:
                stream.write(self.sources[name])
            path.chmod(0o644)
        # Only public fixture input traverses this directory; no credential/config mounts.
        self.output.chmod(0o755)
        PHASE = "PINNED_IMAGES"
        for image in (NGINX, PYTHON_FIXTURE):
            code, _ = self.command(["image", "inspect", "--format", "{{.Id}}", image], allow_failure=True)
            if code:
                self.command(["pull", "--platform", "linux/amd64", image], 180, quiet=True)
        PHASE = "OWNED_NETWORK"
        self.command(["network", "create", "--internal", "--label", LABEL + "=" + self.nonce, self.network])
        require(self.network_info()["Containers"] == {})
        for role in ("fake", "gateway"):
            uid = "185" if role == "fake" else "101"
            destination = "/fixture" if role == "fake" else "/etc/public-gateway"
            image = PYTHON_FIXTURE if role == "fake" else NGINX
            alias = "api.platform-lab.svc.cluster.local" if role == "fake" else "gateway"
            argv = ["python3", "-I", "-B", "/fixture/fake_upstream.py"] if role == "fake" else ["nginx", "-c", "/etc/public-gateway/nginx.conf", "-g", "daemon off;"]
            self.command(["container", "create", "--name", self.names[role], "--label", LABEL + "=" + self.nonce,
                          "--platform", "linux/amd64", "--network", self.network, "--network-alias", alias,
                          "--read-only", "--user", uid + ":" + uid, "--cap-drop", "ALL",
                          "--security-opt", "no-new-privileges:true", "--memory", "128m", "--cpus", "0.25",
                          "--pids-limit", "64", "--restart", "no", "--log-driver", "json-file",
                          "--log-opt", "max-size=1m", "--log-opt", "max-file=1",
                          "--tmpfs", "/tmp:rw,noexec,nosuid,nodev,size=16m,mode=0700,uid=" + uid + ",gid=" + uid,
                          "--mount", "type=bind,src=" + str(self.kit) + ",dst=" + destination + ",readonly",
                          "--entrypoint", argv[0], image, *argv[1:]])
            self.assert_container(role)
            self.command(["container", "start", self.ids[self.names[role]]])
        PHASE = "ISOLATION_AND_NGINX_SYNTAX"
        require(set(self.network_info()["Containers"]) == set(self.ids.values()))
        self.assert_container("fake")
        self.assert_container("gateway")
        self.command(["exec", self.ids[self.names["gateway"]], "nginx", "-t", "-c", "/etc/public-gateway/nginx.conf"])

    def check_http(self):
        global PHASE
        command = ["exec", self.ids[self.names["fake"]], "python3", "-I", "-B", "/fixture/verify_http.py"]
        PHASE = "HTTP_READINESS"
        end = time.monotonic() + 30
        ready = False
        while time.monotonic() < end:
            code, raw = self.command([*command, "--ready"], 5, allow_failure=True)
            if code == 0 and json.loads(raw).get("passed") is True:
                ready = True
                break
            time.sleep(0.25)
        require(ready)
        PHASE = "ACTUAL_HTTP_PROBES"
        code, raw = self.command(command, 180, allow_failure=True)
        result = json.loads(raw, object_pairs_hook=unique)
        require(code == 0 and result.get("passed") is True and result.get("phase") == "COMPLETE")
        PHASE = "ACTUAL_LIMIT_SIGNALS"
        _, raw = self.command(["logs", "--tail", "256", self.ids[self.names["gateway"]]])
        lines = raw.decode("ascii").splitlines()
        pattern = re.compile(r"public-gateway [0-9]{3} (PASSED|REJECTED|-|DELAYED) (PASSED|REJECTED|-)$")
        matched = [pattern.fullmatch(line) for line in lines]
        require(lines and all(matched))
        rate = sum(item.group(1) == "REJECTED" for item in matched)
        connection = sum(item.group(2) == "REJECTED" for item in matched)
        require(rate > 0 and connection > 0)
        require(set(self.network_info()["Containers"]) == set(self.ids.values()))
        self.assert_container("fake")
        self.assert_container("gateway")
        return {"httpChecks": result["checks"], "allowlistedRoutePatterns": result["allowlistedRoutePatterns"],
                "deniedUriCases": result["deniedUriCases"], "methodCases": result["methodCases"],
                "rateRejectionsObserved": rate, "connectionRejectionsObserved": connection,
                "globalMultiPeerLimitIndependentlyExercised": False}

    def cleanup(self):
        # Exact nonce names + labels + recorded IDs. No prune/down/global listing or filesystem deletion.
        if not self.docker_ready:
            return True
        okay = True
        for role in ("gateway", "fake"):
            try:
                value = self.inspect_container(self.names[role], optional=True, cleanup=True)
                if value is not None:
                    self.command(["container", "rm", "--force", "--volumes", value["Id"]], 15, cleanup=True)
                    require(self.inspect_container(self.names[role], optional=True, cleanup=True) is None)
            except Exception:
                okay = False
        try:
            value = self.network_info(optional=True, cleanup=True)
            if value is not None:
                require(value["Containers"] == {})  # Never remove a network containing a foreign endpoint.
                self.command(["network", "rm", value["Id"]], 15, cleanup=True)
                require(self.network_info(optional=True, cleanup=True) is None)
        except Exception:
            okay = False
        return okay


def main():
    global PHASE
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-manifest-sha256", required=True)
    parser.add_argument("--ack-isolated-public-gateway", action="store_true", required=True)
    args = parser.parse_args()
    attempt = None
    result = {"schemaVersion": 1, "scope": "ISOLATED_PUBLIC_READ_GATEWAY_PROTOTYPE", "passed": False,
              "phase": PHASE, "realMiniPcContacted": False, "publicEndpointExposed": False,
              "dbOrKafkaStarted": False, "sparkOrJvmStarted": False, "hostPortsPublished": False,
              "ownedContainerMaximum": 2, "ownedInternalNetworkMaximum": 1}
    try:
        folder = Path(__file__).resolve().parent
        sources = source_gate(folder, args.source_manifest_sha256)
        attempt = Attempt(folder, sources)
        attempt.start()
        result.update(attempt.check_http())
        require(source_gate(folder, args.source_manifest_sha256) == sources)
        result.update(passed=True, phase="COMPLETE", sourceManifestSha256=args.source_manifest_sha256)
    except Exception:
        result.update(passed=False, phase=PHASE)
    finally:
        if attempt is not None:
            result["ownedResourcesRemoved"] = attempt.cleanup()
            result["passed"] = result["passed"] and result["ownedResourcesRemoved"]
            if not result["ownedResourcesRemoved"]:
                result["phase"] = "CLEANUP"
            if attempt.output_owned:
                with (attempt.output / "summary.json").open("x", encoding="utf-8") as stream:
                    json.dump(result, stream, sort_keys=True, indent=2)
                    stream.write("\n")
        print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
