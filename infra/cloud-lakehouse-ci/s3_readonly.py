"""Fresh Cloud-only warehouse GET/LIST. No PUT, HEAD, DELETE, proxy or redirect."""
import datetime as dt
import json
import os
from pathlib import Path
import re
import urllib.parse
import urllib.request
from contract import Deadline, require, sha
from frozen_s3_primitives import NoRedirect, canonical_query, signature, xml

BUCKET = "platform-lab-iceberg-20261015"
ENDPOINT = "http://garage.platform-lab.svc.cluster.local:3900"
PREFIX = "warehouse/phase6/"
PROOF = Path("/proof")


def new_json(path, value):
    raw = (json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n").encode()
    with os.fdopen(os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o644), "wb") as stream:
        stream.write(raw); stream.flush(); os.fsync(stream.fileno())


def clock():
    raw = (PROOF / "clock.json").read_bytes()
    require(0 < len(raw) < 1024, "BOUNDED_SINGLE_WORKLOAD_CLOCK")
    value = json.loads(raw)
    require(set(value) == {"startedMonotonic", "hostBootId", "budgetSeconds"}
            and value["budgetSeconds"] == 600 and type(value["startedMonotonic"]) in (int, float)
            and value["hostBootId"] == Path("/proc/sys/kernel/random/boot_id").read_text().strip(), "ACTUAL_SAME_HOST_GLOBAL_CLOCK")
    return Deadline(value["startedMonotonic"])


class Client:
    def __init__(self, deadline):
        secrets = Path("/run/silver-secrets")
        self.access = (secrets / "access-key").read_text("ascii")
        self.secret = (secrets / "secret-key").read_text("ascii")
        endpoint = (secrets / "endpoint").read_text("ascii")
        require(endpoint == ENDPOINT and re.fullmatch(r"[A-Za-z0-9]{1,128}", self.access)
                and re.fullmatch(r"[!-~]{1,512}", self.secret), "ONLY_FRESH_COMPOSE_GARAGE_ALIAS")
        self.deadline = deadline
        self.open = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect()).open

    def get(self, key=None):
        require(key is None or type(key) is str and key.startswith(PREFIX)
                and re.fullmatch(r"[A-Za-z0-9._/-]{1,1024}", key) and ".." not in key.split("/"), "ONLY_FIXED_WAREHOUSE_GET_OR_LIST")
        query = canonical_query([("list-type", "2"), ("max-keys", "129"), ("prefix", PREFIX)]) if key is None else ""
        uri = "/" + BUCKET + "/" + urllib.parse.quote(key or "", safe="/-_.~")
        headers, _ = signature("GET", urllib.parse.urlsplit(ENDPOINT).netloc, uri, query, b"", self.access, self.secret, dt.datetime.now(dt.timezone.utc))
        request = urllib.request.Request(ENDPOINT + uri + ("?" + query if query else ""), method="GET", headers=headers)
        maximum = 1024**2 if key is None else 4 * 1024**2
        with self.open(request, timeout=self.deadline.remaining(15, 60)) as response:
            require(response.status == 200, "S3_GET_EXACT_200_NO_RETRY")
            declared = response.headers.get("Content-Length")
            require(declared is not None and declared.isdecimal() and 0 <= int(declared) <= maximum, "S3_LENGTH_HEADER_BOUND")
            chunks, count = [], 0
            read = getattr(response, "read1", response.read)
            while True:
                self.deadline.remaining(15, 60)
                chunk = read(min(65536, maximum + 1 - count))
                if not chunk:
                    break
                chunks.append(chunk); count += len(chunk)
                require(count <= maximum, "WHOLE_S3_BODY_BOUND")
            raw = b"".join(chunks)
            require(len(raw) == int(declared), "WHOLE_GET_LENGTH_AND_EOF")
            return raw

    def listing(self):
        tree = xml(self.get(), "ListBucketResult")
        require(tree.findtext("Name") == BUCKET and tree.findtext("IsTruncated") == "false", "EXACT_FRESH_BUCKET_SINGLE_BOUNDED_LIST")
        result = []
        for value in tree.findall("Contents"):
            key, size = value.findtext("Key"), value.findtext("Size")
            require(type(key) is str and key.startswith(PREFIX) and re.fullmatch(r"[A-Za-z0-9._/-]{1,1024}", key)
                    and ".." not in key.split("/") and type(size) is str and size.isdecimal() and int(size) <= 4 * 1024**2, "BOUNDED_WAREHOUSE_LIST_ITEM")
            result.append({"key": key, "size": int(size)})
        require(len(result) <= 128 and len({value["key"] for value in result}) == len(result), "UNIQUE_WAREHOUSE_KEYS_AT_MOST_128")
        return sorted(result, key=lambda value: value["key"])

    def capture(self, name, prior=None):
        require(name in ("before-compaction", "after-compaction", "after-trino"), "FIXED_NEW_CAPTURE_NAME")
        folder = PROOF / ("objects-" + name)
        folder.mkdir(mode=0o755)
        listed = self.listing()
        require(0 < len(listed) <= 128, "NONEMPTY_FRESH_WAREHOUSE")
        result, total = [], 0
        old = {value["key"]: value for value in prior or []}
        for value in listed:
            raw = self.get(value["key"])
            total += len(raw)
            require(len(raw) == value["size"] and total <= 32 * 1024**2, "WAREHOUSE_WHOLE_TOTAL_BOUND")
            filename = sha(value["key"].encode()) + ".bin"
            with (folder / filename).open("xb") as stream:
                stream.write(raw); stream.flush(); os.fsync(stream.fileno())
            record = {**value, "sha256": sha(raw), "copy": filename}
            if value["key"] in old:
                previous = old[value["key"]]
                require(record == previous and raw == (PROOF / "objects-before-compaction" / previous["copy"]).read_bytes(), "OLD_WAREHOUSE_WHOLE_BYTES_PRESERVED")
            result.append(record)
        require(set(old).issubset({value["key"] for value in result}) and self.listing() == listed, "OLD_KEYS_PRESERVED_AND_LIST_STABLE")
        new_json(PROOF / ("warehouse-" + name + ".json"), result)
        return result


def main():
    # This is the only Python-reader entrypoint, run after both heavy JVMs exit.
    deadline = clock()
    client = Client(deadline)
    prior = json.loads((PROOF / "warehouse-after-compaction.json").read_bytes())
    before = json.loads((PROOF / "warehouse-before-compaction.json").read_bytes())
    actual = client.capture("after-trino", before)
    require(actual == prior, "EXACT_WAREHOUSE_UNCHANGED_AFTER_SELECT_ONLY_TRINO")
    for value in actual:
        require((PROOF / "objects-after-compaction" / value["copy"]).read_bytes()
                == (PROOF / "objects-after-trino" / value["copy"]).read_bytes(), "ALL_PRE_TRINO_WHOLE_COPIES_EQUAL")
    new_json(PROOF / "reader-result.json", {"passed": True, "wholeObjects": len(actual),
             "oldObjects": len(before), "allPreTrinoBytesEqual": True, "onlyGetAndList": True})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
