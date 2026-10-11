#!/usr/bin/env python3
"""Restrict this small GitOps values file to its explicitly supported shape.

This is deliberately not a general YAML parser. Aliases, tags, flow mappings,
multiline strings, duplicate keys, and arbitrary Helm values are rejected.
"""
from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path
import re
import sys

REPOSITORIES = {
    "api": "ghcr.io/devdooly/devdooly-platform-lab-api",
    "web": "ghcr.io/devdooly/devdooly-platform-lab-web",
}
ALLOWED_CHANGES = {
    ("api", "image", "repository"), ("api", "image", "digest"), ("api", "sourceCommit"),
    ("web", "image", "repository"), ("web", "image", "digest"),
}
SHA = re.compile(r"[0-9a-f]{40}")
DIGEST = re.compile(r"sha256:[0-9a-f]{64}")
SECRET_NAME = re.compile(r"[a-z0-9](?:[-a-z0-9]{0,251}[a-z0-9])?")


class ValuesError(Exception):
    pass


def parse(text: str) -> dict:
    if not isinstance(text, str) or len(text.encode("utf-8")) > 32768 or "\t" in text or "\ufeff" in text:
        raise ValuesError("INVALID_VALUES_DOCUMENT")
    result = {}
    stack = [(-2, result)]
    previous_indent = -2
    previous_mapping = True
    for line in text.splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        match = re.fullmatch(r"( *)([A-Za-z][A-Za-z0-9]*):(?: ([A-Za-z0-9:/@_.-]+))?", line)
        if not match:
            raise ValuesError("UNSUPPORTED_VALUES_SYNTAX")
        indent = len(match.group(1))
        if indent not in (0, 2, 4) or (indent > previous_indent and (indent != previous_indent + 2 or not previous_mapping)):
            raise ValuesError("INVALID_VALUES_INDENTATION")
        while stack[-1][0] >= indent:
            stack.pop()
        if stack[-1][0] != indent - 2:
            raise ValuesError("INVALID_VALUES_PARENT")
        key, value = match.group(2), match.group(3)
        parent = stack[-1][1]
        if key in parent:
            raise ValuesError("DUPLICATE_VALUES_KEY")
        parent[key] = {} if value is None else value
        if value is None:
            stack.append((indent, parent[key]))
        previous_indent, previous_mapping = indent, value is None
    validate_shape(result)
    return result


def validate_shape(document: dict) -> None:
    if not isinstance(document, dict) or set(document) != {"api", "web", "database"}:
        raise ValuesError("UNEXPECTED_VALUES_KEYS")
    for component in ("api", "web"):
        item = document[component]
        expected = {"image", "sourceCommit"} if component == "api" else {"image"}
        if not isinstance(item, dict) or set(item) != expected:
            raise ValuesError("UNEXPECTED_COMPONENT_KEYS")
        image = item["image"]
        if not isinstance(image, dict) or set(image) != {"repository", "digest"}:
            raise ValuesError("UNEXPECTED_IMAGE_KEYS")
        if image["repository"] != REPOSITORIES[component] or not DIGEST.fullmatch(str(image["digest"])):
            raise ValuesError("INVALID_IMAGE_REFERENCE")
    if not SHA.fullmatch(str(document["api"]["sourceCommit"])):
        raise ValuesError("INVALID_SOURCE_COMMIT")
    database = document["database"]
    if not isinstance(database, dict) or set(database) != {"existingSecret"} or not SECRET_NAME.fullmatch(str(database["existingSecret"])):
        raise ValuesError("INVALID_EXISTING_SECRET_REFERENCE")


def flatten(document: dict, prefix=()) -> dict:
    result = {}
    for key, value in document.items():
        location = prefix + (key,)
        if isinstance(value, dict):
            result.update(flatten(value, location))
        else:
            result[location] = value
    return result


def validate_change(before: dict, after: dict) -> list[str]:
    validate_shape(before)
    validate_shape(after)
    old, new = flatten(before), flatten(after)
    changed = {key for key in old.keys() | new.keys() if old.get(key) != new.get(key)}
    if not changed:
        raise ValuesError("NO_DEPLOYMENT_CHANGE")
    if not changed <= ALLOWED_CHANGES:
        raise ValuesError("CHANGES_OUTSIDE_IMAGE_ALLOWLIST")
    if not any(path[-1] == "digest" for path in changed):
        raise ValuesError("SOURCE_CHANGED_WITHOUT_IMAGE_CHANGE")
    return sorted(".".join(path) for path in changed)


def update(before: dict, source_commit: str, api_digest: str, web_digest: str) -> dict:
    after = copy.deepcopy(before)
    after["api"]["sourceCommit"] = source_commit
    after["api"]["image"]["digest"] = api_digest
    after["web"]["image"]["digest"] = web_digest
    validate_change(before, after)
    return after


def render(document: dict) -> str:
    validate_shape(document)
    return (
        "# Image-only GitOps input. Credentials stay in the destination namespace.\n"
        "api:\n  image:\n"
        f"    repository: {document['api']['image']['repository']}\n"
        f"    digest: {document['api']['image']['digest']}\n"
        f"  sourceCommit: {document['api']['sourceCommit']}\n"
        "web:\n  image:\n"
        f"    repository: {document['web']['image']['repository']}\n"
        f"    digest: {document['web']['image']['digest']}\n"
        "database:\n"
        f"  existingSecret: {document['database']['existingSecret']}\n"
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    check = sub.add_parser("validate")
    check.add_argument("--before", required=True)
    check.add_argument("--after", required=True)
    prepare = sub.add_parser("prepare")
    prepare.add_argument("--before", required=True)
    prepare.add_argument("--source-commit", required=True)
    prepare.add_argument("--api-digest", required=True)
    prepare.add_argument("--web-digest", required=True)
    prepare.add_argument("--output", required=True)
    args = parser.parse_args()
    try:
        before = parse(Path(args.before).read_text(encoding="utf-8"))
        if args.command == "validate":
            after = parse(Path(args.after).read_text(encoding="utf-8"))
        else:
            after = update(before, args.source_commit, args.api_digest, args.web_digest)
            Path(args.output).write_text(render(after), encoding="utf-8", newline="\n")
        print(json.dumps({"scope": "IMAGE_VALUES_ONLY", "changedFields": validate_change(before, after)}, sort_keys=True))
        return 0
    except (ValuesError, OSError, UnicodeError):
        print("GitOps values rejected: invalid document or change outside the image allowlist.", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
