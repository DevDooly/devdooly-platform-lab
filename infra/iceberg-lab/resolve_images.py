"""Anonymous read-only OCI metadata resolution. Does not pull layers or start containers."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

IMAGES = {"trino": ("trinodb/trino", "483"), "postgres": ("library/postgres", "17.11-bookworm")}
ACCEPT = ", ".join(("application/vnd.oci.image.index.v1+json", "application/vnd.docker.distribution.manifest.list.v2+json",
                    "application/vnd.oci.image.manifest.v1+json", "application/vnd.docker.distribution.manifest.v2+json"))


def require(value, code):
    if not value:
        raise ValueError(code)


def digest(raw):
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def checked_json(raw, expected=None):
    require(0 < len(raw) <= 4 * 1024**2, "BOUNDED_OCI_DOCUMENT_REQUIRED")
    require(expected is None or re.fullmatch(r"sha256:[0-9a-f]{64}", expected) and digest(raw) == expected,
            "OCI_DIGEST_MISMATCH")
    value = json.loads(raw)
    require(isinstance(value, dict), "OCI_OBJECT_REQUIRED")
    return value


def amd64_descriptor(index):
    entries = [entry for entry in index.get("manifests", [])
               if entry.get("platform", {}).get("os") == "linux" and entry.get("platform", {}).get("architecture") == "amd64"]
    require(len(entries) == 1 and re.fullmatch(r"sha256:[0-9a-f]{64}", entries[0].get("digest", "")),
            "EXACT_ONE_LINUX_AMD64_CHILD_REQUIRED")
    return entries[0]


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args):
        return None


def request_bytes(url, token=None, config_blob=False, deadline=None):
    parsed = urllib.parse.urlsplit(url)
    require(parsed.scheme == "https" and not parsed.username and not parsed.password and not parsed.fragment,
            "HTTPS_REGISTRY_READ_ONLY_REQUIRED")
    require(parsed.hostname in {"registry-1.docker.io", "auth.docker.io"}, "FIXED_REGISTRY_HOST_REQUIRED")
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
    headers = {"Accept": ACCEPT, "User-Agent": "devdooly-phase6-readonly-metadata"}
    if token:
        headers["Authorization"] = "Bearer " + token
    timeout = min(20, max(1, (deadline or time.monotonic() + 20) - time.monotonic()))
    try:
        response = opener.open(urllib.request.Request(url, headers=headers), timeout=timeout)
    except urllib.error.HTTPError as failure:
        require(config_blob and failure.code in (302, 307), "REGISTRY_HTTP_READ_FAILED")
        location = failure.headers.get("Location", ""); redirected = urllib.parse.urlsplit(location)
        require(redirected.scheme == "https" and not redirected.username and not redirected.password
                and (redirected.hostname in {"production.cloudflare.docker.com", "production.cloudfront.docker.com"}
                     or (redirected.hostname or "").endswith(".r2.cloudflarestorage.com")), "CONFIG_CDN_REDIRECT_REJECTED")
        # Do not forward the registry token or log/store the signed CDN URL.
        response = opener.open(urllib.request.Request(location, headers={"User-Agent": headers["User-Agent"]}), timeout=timeout)
    with response:
        raw = response.read(4 * 1024**2 + 1)
        require(response.status == 200 and len(raw) <= 4 * 1024**2, "BOUNDED_HTTP_200_REQUIRED")
        return raw, response.headers.get("Docker-Content-Digest")


def resolve(name, deadline):
    repository, tag = IMAGES[name]
    query = urllib.parse.urlencode({"service": "registry.docker.io", "scope": "repository:" + repository + ":pull"})
    token_raw, _ = request_bytes("https://auth.docker.io/token?" + query, deadline=deadline)
    token = checked_json(token_raw).get("token")
    require(isinstance(token, str) and 0 < len(token) < 16384, "ANONYMOUS_READ_TOKEN_REQUIRED")
    base = "https://registry-1.docker.io/v2/" + repository
    index_raw, declared = request_bytes(base + "/manifests/" + tag, token, deadline=deadline)
    index = checked_json(index_raw, declared)
    index_sha = digest(index_raw)
    child = amd64_descriptor(index)
    manifest_raw, _ = request_bytes(base + "/manifests/" + child["digest"], token, deadline=deadline)
    manifest = checked_json(manifest_raw, child["digest"])
    require(child["size"] == len(manifest_raw), "CHILD_MANIFEST_SIZE_MISMATCH")
    config_digest = manifest.get("config", {}).get("digest")
    config_raw, _ = request_bytes(base + "/blobs/" + config_digest, token, config_blob=True, deadline=deadline)
    config = checked_json(config_raw, config_digest)
    require(manifest["config"]["size"] == len(config_raw) and config.get("architecture") == "amd64" and config.get("os") == "linux",
            "CONFIG_SIZE_PLATFORM_MISMATCH")
    settings = config.get("config", {})
    labels = settings.get("Labels") or {}
    require(isinstance(labels, dict) and all(isinstance(key, str) and isinstance(value, str) and len(key) <= 256
            and len(value) <= 4096 for key, value in labels.items()), "BOUNDED_PUBLIC_IMAGE_LABELS_REQUIRED")
    environment = dict(item.split("=", 1) for item in settings.get("Env", []) if "=" in item)
    if name == "trino":
        require(settings.get("User") == "trino:trino" and settings.get("Cmd") == ["/usr/lib/trino/bin/run-trino"], "EXPECTED_TRINO_IMAGE_CONFIG_REQUIRED")
    else:
        require(environment.get("PG_MAJOR") == "17" and environment.get("PG_VERSION", "").startswith("17.11")
                and settings.get("Entrypoint") == ["docker-entrypoint.sh"] and settings.get("Cmd") == ["postgres"],
                "EXPECTED_POSTGRES_IMAGE_CONFIG_REQUIRED")
    return {"repository": repository, "versionTag": tag, "reference": "docker.io/" + repository + "@" + index_sha,
            "indexDigest": index_sha, "amd64ManifestDigest": child["digest"], "configDigest": config_digest,
            "platform": "linux/amd64", "configUser": settings.get("User", ""), "entrypoint": settings.get("Entrypoint"),
            "command": settings.get("Cmd"), "labels": labels,
            "declaredEnvironment": {key: environment[key] for key in ("JAVA_HOME", "PG_MAJOR", "PG_VERSION", "PGDATA", "CATALOG_MANAGEMENT") if key in environment},
            "anonymousRegistryRead": True, "layersPulled": False, "containerStarted": False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    require(not args.output.exists(), "IMMUTABLE_NEW_OUTPUT_REQUIRED")
    deadline = time.monotonic() + 120
    value = {"schemaVersion": 1, "scope": "REGISTRY_METADATA_ONLY", "capturedAt": datetime.now(timezone.utc).isoformat(),
             "images": {name: resolve(name, deadline) for name in IMAGES}, "runtimeCompatibilityVerified": False}
    with args.output.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(value, stream, indent=2); stream.write("\n")
    print(json.dumps({"passed": True, "scope": value["scope"], "images": {key: image["reference"] for key, image in value["images"].items()},
                      "runtimeCompatibilityVerified": False}))


if __name__ == "__main__":
    main()
