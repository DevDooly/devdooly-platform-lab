"""Materialize only NEW trial Secrets in a root-private file; no kubectl/network calls."""
import argparse
import base64
import json
import os
from pathlib import Path
import re
import stat
from render_plan import LABELS, NAMESPACE
from sql_plan import BUCKET


def require(value, code):
    if not value:
        raise ValueError(code)


def secret_documents(value):
    require(isinstance(value, dict) and set(value) == {"bootstrapPassword", "catalogPassword", "s3Endpoint", "bucket", "accessKey", "secretKey"},
            "EXACT_PRIVATE_CONNECTION_FIELDS_REQUIRED")
    require(all(isinstance(item, str) for item in value.values()), "STRING_ONLY_PRIVATE_FIELDS_REQUIRED")
    require(re.fullmatch(r"[0-9a-f]{64}", value["bootstrapPassword"]) and re.fullmatch(r"[0-9a-f]{64}", value["catalogPassword"])
            and value["bootstrapPassword"] != value["catalogPassword"], "TWO_DISTINCT_RANDOM_HEX_PASSWORDS_REQUIRED")
    require(value["bucket"] == BUCKET and value["s3Endpoint"] == "http://garage.platform-lab.svc.cluster.local:3900",
            "DEDICATED_BUCKET_AND_OWN_INTERNAL_GARAGE_DNS_REQUIRED")
    require(re.fullmatch(r"[A-Za-z0-9]{1,128}", value["accessKey"]) and 1 <= len(value["secretKey"]) <= 512
            and all(33 <= ord(char) <= 126 for char in value["secretKey"]), "BOUNDED_SINGLE_LINE_CREDENTIALS_REQUIRED")
    objects = []
    for name, fields in (("iceberg-postgres-credentials", {"bootstrap-password": value["bootstrapPassword"], "catalog-password": value["catalogPassword"]}),
                         ("iceberg-s3-credentials", {"endpoint": value["s3Endpoint"], "bucket": value["bucket"], "access-key": value["accessKey"], "secret-key": value["secretKey"]})):
        objects.append({"apiVersion": "v1", "kind": "Secret", "metadata": {"name": name, "namespace": NAMESPACE, "labels": LABELS},
                        "type": "Opaque", "data": {key: base64.b64encode(item.encode()).decode() for key, item in fields.items()}})
    return {"apiVersion": "v1", "kind": "List", "items": objects}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True); parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    require(os.name == "posix" and os.geteuid() == 0, "ROOT_PRIVATE_MATERIALIZATION_ONLY")
    info = args.input.lstat()
    require(stat.S_ISREG(info.st_mode) and not args.input.is_symlink() and info.st_uid == 0
            and stat.S_IMODE(info.st_mode) == 0o600 and info.st_size <= 8192, "ROOT_0600_BOUNDED_INPUT_REQUIRED")
    parent = args.output.parent.resolve(strict=True)
    require(parent.is_dir() and parent.stat().st_uid == 0 and stat.S_IMODE(parent.stat().st_mode) == 0o700
            and args.output.parent == parent, "EXACT_ROOT_0700_OUTPUT_PARENT_REQUIRED")
    require(not any((directory / ".git").exists() for directory in (parent, *parent.parents)), "SECRET_OUTPUT_MUST_STAY_OUTSIDE_GIT_CHECKOUT")
    objects = secret_documents(json.loads(args.input.read_text("utf-8")))
    descriptor = os.open(args.output, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
        json.dump(objects, stream); stream.write("\n"); stream.flush(); os.fsync(stream.fileno())
    print(json.dumps({"status": "PRIVATE_FILES_ONLY", "secretCount": 2, "serverContacted": False, "credentialValuesPrinted": False}))


if __name__ == "__main__":
    main()
