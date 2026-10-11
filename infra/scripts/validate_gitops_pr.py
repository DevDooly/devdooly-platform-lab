#!/usr/bin/env python3
"""Read public PR metadata and validate the only permitted deployment file.

The PR head is never checked out or executed, and no credentials are read.
Registry content, Helm rendering, and deployment are separate verification steps.
"""
import argparse
import base64
import json
from pathlib import Path
import re
import sys
from urllib.parse import urlencode

from ci_publication_gate import GateError, PublicGitHub, REPOSITORY, full_sha, repo_matches
from gitops_values import ValuesError, parse, validate_change

VALUES_PATH = "gitops/environments/home-lab/values.yaml"


def read_values(get, commit):
    document = get(f"contents/{VALUES_PATH}?{urlencode({'ref': commit})}")
    if document.get("type") != "file" or document.get("encoding") != "base64" or document.get("size", 32769) > 32768:
        raise ValuesError("INVALID_VALUES_FILE")
    content = base64.b64decode(document.get("content", ""), validate=False)
    if len(content) > 32768:
        raise ValuesError("VALUES_FILE_TOO_LARGE")
    return content.decode("utf-8")


def evaluate_pr(number, base, head, get):
    metadata = get(f"pulls/{number}")
    if metadata.get("state") != "open" or metadata.get("base", {}).get("ref") != "main" or not repo_matches(metadata.get("base", {}).get("repo")):
        raise ValuesError("WRONG_PULL_REQUEST_BASE")
    if metadata.get("base", {}).get("sha") != base or metadata.get("head", {}).get("sha") != head:
        raise ValuesError("PULL_REQUEST_MOVED_RETRY_WITH_CURRENT_EVENT")
    files = get(f"pulls/{number}/files?per_page=100&page=1")
    if not isinstance(files, list) or len(files) != 1 or files[0].get("filename") != VALUES_PATH or files[0].get("status") != "modified":
        raise ValuesError("PULL_REQUEST_MUST_CHANGE_ONLY_IMAGE_VALUES")
    before_text, after_text = read_values(get, base), read_values(get, head)
    fields = validate_change(parse(before_text), parse(after_text))
    return {
        "scope": "GITOPS_CHANGE_SCOPE_ONLY", "pullRequest": number, "baseCommit": base,
        "headCommit": head, "changedFields": fields,
        "registryContentsVerified": False, "helmRenderVerified": False, "deploymentVerified": False,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--number", required=True)
    parser.add_argument("--base", required=True)
    parser.add_argument("--head", required=True)
    parser.add_argument("--repository", required=True)
    args = parser.parse_args()
    try:
        if args.repository.lower() != REPOSITORY.lower() or not re.fullmatch(r"[1-9][0-9]*", args.number):
            raise ValuesError("INVALID_PR_INPUT")
        result = evaluate_pr(int(args.number), full_sha(args.base), full_sha(args.head), PublicGitHub())
        print(json.dumps(result, sort_keys=True))
        return 0
    except (GateError, ValuesError, OSError, ValueError, KeyError, TypeError, AttributeError):
        print("GitOps PR scope validation rejected the supplied change.", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
