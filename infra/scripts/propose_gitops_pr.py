#!/usr/bin/env python3
"""Propose an image-only draft PR using the current Actions job token.

No merge, cluster command, SSH, developer CLI token, or registry credential is
used. The caller must explicitly enable the optional proposal job.
"""
from __future__ import annotations

import argparse
import base64
import json
import os
from pathlib import Path
import re
import sys
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode
from urllib.request import HTTPRedirectHandler, Request, build_opener

from ci_publication_gate import CONTEXT, GateError, PublicGitHub, REPOSITORY, evaluate, full_sha, repo_matches
from gitops_values import REPOSITORIES, ValuesError, parse, render, update, validate_change
from validate_gitops_pr import VALUES_PATH, read_values


class ProposalError(Exception):
    pass


class RejectRedirects(HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, message, headers, new_url):
        raise ProposalError("WRITE_REDIRECT_REJECTED")


class GitHubWriter:
    def __init__(self, token: str):
        if not token or any(character in token for character in "\r\n"):
            raise ProposalError("ACTIONS_JOB_TOKEN_MISSING")
        self.token = token

    def __call__(self, method: str, path: str, document: dict) -> dict:
        if method not in {"POST", "PUT"}:
            raise ProposalError("UNSUPPORTED_WRITE_METHOD")
        request = Request(
            f"https://api.github.com/repos/{REPOSITORY}/{path}",
            data=json.dumps(document).encode("utf-8"), method=method,
            headers={"Accept": "application/vnd.github+json", "Content-Type": "application/json",
                     "User-Agent": "devdooly-lab-gitops-proposal", "Authorization": f"Bearer {self.token}"},
        )
        try:
            with build_opener(RejectRedirects()).open(request, timeout=30) as response:
                data = response.read(2 * 1024 * 1024 + 1)
            if len(data) > 2 * 1024 * 1024:
                raise ProposalError("WRITE_RESPONSE_TOO_LARGE")
            result = json.loads(data)
            if not isinstance(result, dict):
                raise ProposalError("INVALID_WRITE_RESPONSE")
            return result
        except HTTPError as exc:
            raise ProposalError(f"WRITE_HTTP_{exc.code}") from None
        except (URLError, TimeoutError, json.JSONDecodeError):
            # Do not automatically retry an unknown mutation outcome. A later
            # explicit run reads the branch/PR and reuses confirmed existing work.
            raise ProposalError("WRITE_OUTCOME_UNCONFIRMED_CHECK_EXISTING_BRANCH_AND_PR") from None


def positive_integer(value) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value > 0


def prepare(manifest: dict, current_main: str, before_text: str, issuer: str) -> tuple[dict, str]:
    source = full_sha(manifest.get("sourceCommit"))
    if current_main != source:
        raise ProposalError("PUBLISHED_SOURCE_IS_NOT_CURRENT_MAIN")
    if manifest.get("schemaVersion") != 1 or not positive_integer(manifest.get("validationRunId")):
        raise ProposalError("INVALID_PUBLICATION_METADATA")
    publication_url = manifest.get("publicationRunUrl", "")
    if not isinstance(publication_url, str) or not re.fullmatch(r"https://github\.com/DevDooly/devdooly-platform-lab/actions/runs/[1-9][0-9]*", publication_url):
        raise ProposalError("INVALID_PUBLICATION_RUN_URL")
    jenkins = manifest.get("jenkins", {})
    if (jenkins.get("context") != CONTEXT or not positive_integer(jenkins.get("statusId"))
            or not positive_integer(jenkins.get("buildNumber"))
            or jenkins.get("issuer", "").lower() != issuer.lower()):
        raise ProposalError("INVALID_JENKINS_PUBLICATION_METADATA")
    images = manifest.get("images", {})
    if not isinstance(images, dict) or set(images) != {"api", "web"}:
        raise ProposalError("INVALID_PUBLICATION_IMAGES")
    for component, repository in REPOSITORIES.items():
        image = images[component]
        if not isinstance(image, dict) or image.get("repository") != repository or image.get("platform") != "linux/amd64":
            raise ProposalError("INVALID_PUBLICATION_IMAGE_REPOSITORY")
        if image.get("reference") != f"{repository}@{image.get('digest', '')}":
            raise ProposalError("INVALID_PUBLICATION_IMAGE_REFERENCE")
    before = parse(before_text)
    after = update(before, source, images["api"].get("digest"), images["web"].get("digest"))
    return after, "automation/lab-images/" + source


def require_current_main(source, get):
    live = get("git/ref/heads/main")
    if live.get("ref") != "refs/heads/main" or live.get("object", {}).get("type") != "commit" or live.get("object", {}).get("sha") != source:
        raise ProposalError("MAIN_MOVED_REVALIDATE_BEFORE_PROPOSING")


def require_draft_pr(pr, branch, head_sha=None):
    if (not isinstance(pr, dict) or pr.get("state") != "open" or pr.get("draft") is not True
            or "auto_merge" not in pr or pr["auto_merge"] is not None
            or pr.get("base", {}).get("ref") != "main" or not repo_matches(pr.get("base", {}).get("repo"))
            or pr.get("head", {}).get("ref") != branch or not repo_matches(pr.get("head", {}).get("repo"))
            or not positive_integer(pr.get("number"))
            or pr.get("html_url") != f"https://github.com/{REPOSITORY}/pull/{pr.get('number')}"):
        raise ProposalError("EXISTING_PR_IS_NOT_AN_UNMERGED_SAFE_DRAFT")
    if head_sha is not None and pr.get("head", {}).get("sha") != head_sha:
        raise ProposalError("EXISTING_PR_HEAD_MOVED")


def propose(manifest: dict, issuer: str, get, write) -> dict:
    source = full_sha(manifest.get("sourceCommit"))
    require_current_main(source, get)
    gate_event = {"repository": {"full_name": REPOSITORY, "private": False},
                  "context": CONTEXT, "state": "success", "sha": source}
    gate = evaluate("status", gate_event, issuer, get)
    # A later CI rerun invalidates the proposal of an older publication artifact.
    if (str(manifest.get("validationRunId")) != gate["validation_run_id"]
            or str(manifest.get("jenkins", {}).get("statusId")) != gate["jenkins_status_id"]):
        raise ProposalError("PUBLICATION_CI_EVIDENCE_IS_NO_LONGER_CURRENT")
    before_text = read_values(get, source)
    after, branch = prepare(manifest, source, before_text, issuer)
    before = parse(before_text)
    query = urlencode({"state": "open", "base": "main", "head": "DevDooly:" + branch, "per_page": 10})
    existing_prs = get("pulls?" + query)
    if not isinstance(existing_prs, list) or len(existing_prs) > 1:
        raise ProposalError("AMBIGUOUS_EXISTING_PULL_REQUEST")
    existing_pr = existing_prs[0] if existing_prs else None
    if existing_pr is not None:
        # A ready PR may already have auto-merge configured. Never update its
        # branch and accidentally make a deployment eligible for merging.
        require_draft_pr(existing_pr, branch)
    branch_ref = "git/ref/heads/" + branch
    try:
        existing = get(branch_ref)
    except GateError as exc:
        if str(exc) != "PUBLIC_METADATA_HTTP_404":
            raise
        existing = None
    if existing is None:
        if existing_pr is not None:
            raise ProposalError("EXISTING_PR_BRANCH_IS_MISSING")
        require_current_main(source, get)
        write("POST", "git/refs", {"ref": "refs/heads/" + branch, "sha": source})
        branch_text = before_text
    else:
        branch_head = full_sha(existing.get("object", {}).get("sha"))
        if existing_pr is not None:
            require_draft_pr(existing_pr, branch, branch_head)
        comparison = get(f"compare/{source}...{quote(branch, safe='/')}")
        files = comparison.get("files")
        if not isinstance(files, list) or len(files) > 1 or any(item.get("filename") != VALUES_PATH or item.get("status") != "modified" for item in files):
            raise ProposalError("EXISTING_BRANCH_CONTAINS_UNRELATED_CHANGES")
        branch_text = read_values(get, branch)
    branch_values = parse(branch_text)
    if branch_values != after:
        # Validate against main AND an existing proposal before updating one file.
        validate_change(before, after)
        if branch_values != before:
            validate_change(before, branch_values)
            validate_change(branch_values, after)
        current_file = get(f"contents/{VALUES_PATH}?{urlencode({'ref': branch})}")
        blob_sha = full_sha(current_file.get("sha"))
        require_current_main(source, get)
        if existing_pr is not None:
            latest_pr = get(f"pulls/{existing_pr['number']}")
            require_draft_pr(latest_pr, branch, branch_head)
        write("PUT", f"contents/{VALUES_PATH}", {
            "message": f"Lab 배포 이미지 {source[:12]} 반영",
            "content": base64.b64encode(render(after).encode("utf-8")).decode("ascii"),
            "sha": blob_sha, "branch": branch,
        })
    if existing_pr is not None:
        pr = existing_pr
        reused = True
    else:
        require_current_main(source, get)
        jenkins = manifest["jenkins"]
        body = (
            "검증한 합성 데이터 Lab의 API·웹 이미지 digest만 갱신합니다. 비밀번호와 DB 설정은 변경하지 않습니다.\n\n"
            f"- 소스: `{source}`\n"
            f"- Jenkins: build {jenkins['buildNumber']}, status {jenkins['statusId']}, `{jenkins['context']}`\n"
            f"- 컨테이너 검증: https://github.com/{REPOSITORY}/actions/runs/{manifest['validationRunId']}\n"
            f"- 이미지 게시: {manifest['publicationRunUrl']}\n"
            f"- API: `{after['api']['image']['repository']}@{after['api']['image']['digest']}`\n"
            f"- 웹: `{after['web']['image']['repository']}@{after['web']['image']['digest']}`\n\n"
            "이 PR은 초안입니다. registry 출처·Helm 렌더링·변경 범위를 확인한 뒤 병합합니다. "
            "병합 후 Argo CD 동기화와 실제 HTTP·DB 결과를 별도로 확인해야 합니다. 자동 병합하지 않습니다.\n"
        )
        pr = write("POST", "pulls", {"title": f"[배포] Lab 이미지 {source[:12]}", "body": body,
                                     "head": branch, "base": "main", "draft": True})
        require_draft_pr(pr, branch)
        reused = False
    if not positive_integer(pr.get("number")) or pr.get("html_url") != f"https://github.com/{REPOSITORY}/pull/{pr.get('number')}":
        raise ProposalError("INVALID_PULL_REQUEST_RESPONSE")
    return {"sourceCommit": source, "branch": branch, "pullRequest": pr["number"],
            "url": pr["html_url"], "reused": reused, "merged": False, "deployed": False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--expected-issuer", required=True)
    args = parser.parse_args()
    try:
        manifest_path = Path(args.manifest)
        if manifest_path.stat().st_size > 32768:
            raise ProposalError("PUBLICATION_MANIFEST_TOO_LARGE")
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if not isinstance(manifest, dict):
            raise ProposalError("INVALID_PUBLICATION_MANIFEST")
        result = propose(manifest, args.expected_issuer, PublicGitHub(), GitHubWriter(os.environ.get("GH_TOKEN", "")))
        print(json.dumps(result, sort_keys=True))
        return 0
    except (GateError, ValuesError, ProposalError) as exc:
        print(f"GitOps proposal withheld: {exc}", file=sys.stderr)
        return 1
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        print("GitOps proposal withheld: INVALID_INPUT", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
