#!/usr/bin/env python3
"""Fail closed unless the exact main commit passed both real CI paths.

Only public GitHub metadata is read. No registry, Git, or cluster mutation occurs.
The trusted version of this file must be checked out before using package rights.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import sys
from typing import Any, Callable
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qsl, quote, urlencode, urlsplit
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener

REPOSITORY = "DevDooly/devdooly-platform-lab"
CONTEXT = "ci/jenkins-test"
WORKFLOW_PATH = ".github/workflows/lab-ci.yml"
SHA = re.compile(r"[0-9a-f]{40}")
ISSUER = re.compile(r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,38})(?:\[bot\])?")
DESCRIPTION = re.compile(r"Jenkins build #([1-9][0-9]*): tests and artifacts verified")


class GateError(Exception):
    """A safe, predefined diagnostic; never contains HTTP bodies or secrets."""

    def __init__(self, code: str, diagnostics: dict[str, int] | None = None):
        super().__init__(code)
        self.diagnostics = diagnostics or {}


class GatePending(GateError):
    """A normal unmet prerequisite. No publication is permitted."""


def full_sha(value: Any) -> str:
    if not isinstance(value, str) or not SHA.fullmatch(value):
        raise GateError("INVALID_SOURCE_SHA")
    return value


def repo_matches(value: Any) -> bool:
    return isinstance(value, dict) and isinstance(value.get("full_name"), str) and value["full_name"].lower() == REPOSITORY.lower()


def valid_validation(run: dict[str, Any], source: str, require_success: bool = True) -> bool:
    path, separator, ref = str(run.get("path", "")).partition("@")
    valid = (
        run.get("name") == "Validate Lab containers"
        and path == WORKFLOW_PATH
        and (not separator or ref in {"main", "refs/heads/main", source})
        and run.get("head_sha") == source
        and run.get("head_branch") == "main"
        and run.get("event") in {"push", "workflow_dispatch"}
        and repo_matches(run.get("repository"))
        and run.get("repository", {}).get("private") is False
        and repo_matches(run.get("head_repository"))
        and isinstance(run.get("id"), int)
        and not isinstance(run.get("id"), bool)
        and run["id"] > 0
    )
    if require_success:
        valid = valid and run.get("status") == "completed" and run.get("conclusion") == "success"
    return valid


def validation_activity(run: dict[str, Any]) -> tuple:
    moments = {}
    for key in ("created_at", "updated_at", "run_started_at"):
        value = run.get(key)
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            if parsed.tzinfo is None:
                raise ValueError
            moments[key] = parsed.astimezone(timezone.utc)
        except (AttributeError, TypeError, ValueError):
            raise GateError("INVALID_VALIDATION_ACTIVITY_METADATA") from None
    attempt = run.get("run_attempt", 1)
    if not isinstance(attempt, int) or isinstance(attempt, bool) or attempt <= 0:
        raise GateError("INVALID_VALIDATION_ATTEMPT")
    # A rerun keeps its run ID but has a new attempt start. Completion time alone
    # is unsafe: an older slow success may finish after a newer failure.
    return moments["run_started_at"], moments["updated_at"], run["id"], attempt


def event_candidate(event_name: str, event: dict[str, Any], get: Callable[[str], Any]) -> str:
    if not repo_matches(event.get("repository")) or event.get("repository", {}).get("private") is not False:
        raise GateError("WRONG_EVENT_REPOSITORY")
    if event_name == "workflow_run":
        supplied = event.get("workflow_run", {})
        source = full_sha(supplied.get("head_sha"))
        if not valid_validation(supplied, source):
            raise GatePending("VALIDATION_EVENT_NOT_SUCCESSFUL")
        # Resolve the run again instead of trusting only the supplied event body.
        live = get(f"actions/runs/{supplied['id']}")
        if not valid_validation(live, source):
            raise GatePending("VALIDATION_RUN_NOT_SUCCESSFUL")
        return source
    if event_name == "status":
        if str(event.get("context", "")).lower() != CONTEXT or event.get("state") != "success":
            raise GatePending("UNRELATED_OR_UNSUCCESSFUL_STATUS")
        return full_sha(event.get("sha"))
    if event_name == "workflow_dispatch":
        run_id = event.get("inputs", {}).get("validation_run_id", "")
        if not isinstance(run_id, str) or not re.fullmatch(r"[1-9][0-9]*", run_id):
            raise GateError("INVALID_VALIDATION_RUN_ID")
        run = get(f"actions/runs/{run_id}")
        source = full_sha(run.get("head_sha"))
        if not valid_validation(run, source):
            raise GatePending("REQUESTED_VALIDATION_NOT_SUCCESSFUL")
        return source
    raise GateError("UNSUPPORTED_EVENT")


def latest_validation(source: str, get: Callable[[str], Any]) -> dict[str, Any]:
    query = urlencode({"head_sha": source, "branch": "main", "per_page": 100})
    document = get(f"actions/workflows/lab-ci.yml/runs?{query}")
    runs = document.get("workflow_runs")
    if not isinstance(runs, list):
        raise GateError("INVALID_VALIDATION_RUNS_RESPONSE")
    candidates = [run for run in runs if isinstance(run, dict) and valid_validation(run, source, False)]
    if not candidates:
        raise GatePending("NO_MATCHING_VALIDATION_RUN")
    # A queued/running/waiting retry invalidates old successes, regardless of
    # which run has the most recent completion timestamp.
    if any(run.get("status") != "completed" for run in candidates):
        raise GatePending("LATEST_VALIDATION_NOT_SUCCESSFUL")
    # Do not select an old success while a newer run for the same SHA fails or runs.
    latest = max(candidates, key=validation_activity)
    if not valid_validation(latest, source):
        raise GatePending("LATEST_VALIDATION_NOT_SUCCESSFUL")
    return latest


def latest_jenkins_status(source: str, get: Callable[[str], Any]) -> dict[str, Any]:
    # GitHub returns newest first. Never filter by issuer before choosing the latest
    # context: a newer failure or wrong issuer must not expose an older success.
    for page in range(1, 6):
        records = get(f"commits/{source}/statuses?per_page=100&page={page}")
        if not isinstance(records, list):
            raise GateError("INVALID_STATUS_RESPONSE")
        for record in records:
            if isinstance(record, dict) and str(record.get("context", "")).lower() == CONTEXT:
                return record
        if len(records) < 100:
            break
    raise GatePending("JENKINS_STATUS_MISSING")


def evaluate(event_name: str, event: dict[str, Any], issuer: str, get: Callable[[str], Any]) -> dict[str, str]:
    if not isinstance(issuer, str) or not ISSUER.fullmatch(issuer):
        raise GateError("JENKINS_STATUS_ISSUER_NOT_CONFIGURED")
    source = event_candidate(event_name, event, get)
    main = get("git/ref/heads/main")
    if main.get("ref") != "refs/heads/main" or main.get("object", {}).get("type") != "commit":
        raise GateError("INVALID_MAIN_REFERENCE")
    if full_sha(main.get("object", {}).get("sha")) != source:
        raise GatePending("SOURCE_IS_NOT_CURRENT_MAIN")
    validation = latest_validation(source, get)
    status = latest_jenkins_status(source, get)
    if status.get("state") != "success":
        raise GatePending("LATEST_JENKINS_NOT_SUCCESSFUL")
    if status.get("creator", {}).get("login", "").lower() != issuer.lower():
        raise GateError("UNEXPECTED_JENKINS_STATUS_ISSUER")
    if not isinstance(status.get("id"), int) or isinstance(status["id"], bool) or status["id"] <= 0:
        raise GateError("INVALID_JENKINS_STATUS_ID")
    description = DESCRIPTION.fullmatch(str(status.get("description", "")))
    if not description:
        raise GateError("JENKINS_VERIFICATION_METADATA_MISSING")
    return {
        "eligible": "true",
        "commit": source,
        "validation_run_id": str(validation["id"]),
        "jenkins_status_id": str(status["id"]),
        "jenkins_build_number": description.group(1),
        "jenkins_issuer": issuer,
        "api_image": f"ghcr.io/{REPOSITORY.lower()}-api",
        "web_image": f"ghcr.io/{REPOSITORY.lower()}-web",
    }


def already_published(source: str, current_run_id: str, get: Callable[[str], Any]) -> bool:
    if not re.fullmatch(r"[1-9][0-9]*", current_run_id):
        raise GateError("INVALID_PUBLICATION_RUN_ID")
    query = urlencode({"head_sha": source, "per_page": 100})
    records = get(f"actions/workflows/publish-images.yml/runs?{query}").get("workflow_runs")
    if not isinstance(records, list):
        raise GateError("INVALID_PUBLICATION_RUNS_RESPONSE")
    for run in records:
        path, separator, ref = str(run.get("path", "")).partition("@")
        if (not isinstance(run.get("id"), int) or isinstance(run["id"], bool) or run["id"] <= 0
                or str(run["id"]) == current_run_id or run.get("head_sha") != source
                or run.get("status") != "completed" or run.get("conclusion") != "success"
                or path != ".github/workflows/publish-images.yml"
                or (separator and ref not in {"main", "refs/heads/main", source})
                or not repo_matches(run.get("repository")) or not repo_matches(run.get("head_repository"))):
            continue
        artifacts = get(f"actions/runs/{run['id']}/artifacts?per_page=100").get("artifacts")
        if not isinstance(artifacts, list):
            raise GateError("INVALID_PUBLICATION_ARTIFACTS_RESPONSE")
        pattern = re.compile(rf"lab-images-{source}-{run['id']}-[1-9][0-9]*")
        if any(isinstance(item, dict) and item.get("expired") is False
               and isinstance(item.get("size_in_bytes"), int) and item["size_in_bytes"] > 0
               and pattern.fullmatch(str(item.get("name", ""))) for item in artifacts):
            return True
    return False


def metadata_route(path: str) -> bool:
    """Only the existing read-only routes of this repository may receive a token."""
    if not isinstance(path, str) or not 0 < len(path) <= 2048 or not path.isascii():
        return False
    if any(ord(character) < 33 or ord(character) > 126 for character in path):
        return False
    parsed = urlsplit(path)
    if parsed.scheme or parsed.netloc or parsed.fragment or not re.fullmatch(r"[A-Za-z0-9._/-]+", parsed.path):
        return False
    if parsed.path.startswith("/") or any(part in {"", ".", ".."} for part in parsed.path.split("/")):
        return False
    try:
        pairs = parse_qsl(parsed.query, keep_blank_values=True, strict_parsing=True)
    except ValueError:
        return False
    query = dict(pairs)
    if len(query) != len(pairs):
        return False
    source = r"[0-9a-f]{40}"
    branch = "automation/lab-images/" + source
    number = r"[1-9][0-9]{0,19}"
    route = parsed.path
    if not query:
        return bool(route == "git/ref/heads/main" or re.fullmatch(r"actions/runs/" + number, route)
                    or re.fullmatch(r"git/ref/heads/" + branch, route)
                    or re.fullmatch(r"compare/" + source + r"\.\.\." + branch, route)
                    or re.fullmatch(r"pulls/" + number, route))
    if route in {"actions/workflows/lab-ci.yml/runs", "actions/workflows/publish-images.yml/runs"}:
        keys = {"head_sha", "per_page"} | ({"branch"} if route.endswith("lab-ci.yml/runs") else set())
        return (set(query) == keys and bool(SHA.fullmatch(query.get("head_sha", "")))
                and query.get("per_page") == "100" and ("branch" not in keys or query["branch"] == "main"))
    if re.fullmatch(r"commits/" + source + r"/statuses", route):
        return set(query) == {"per_page", "page"} and query["per_page"] == "100" and query["page"] in {"1", "2", "3", "4", "5"}
    if re.fullmatch(r"actions/runs/" + number + r"/artifacts", route):
        return query == {"per_page": "100"}
    if route == "contents/gitops/environments/home-lab/values.yaml":
        return set(query) == {"ref"} and bool(re.fullmatch(source + "|" + branch, query["ref"]))
    if route == "pulls":
        return (set(query) == {"state", "base", "head", "per_page"} and query["state"] == "open"
                and query["base"] == "main" and query["per_page"] == "10"
                and bool(re.fullmatch("DevDooly:" + branch, query["head"])))
    if re.fullmatch(r"pulls/" + number + r"/files", route):
        return query == {"per_page": "100", "page": "1"}
    return False


def rate_diagnostics(error: HTTPError) -> dict[str, int]:
    if error.code not in {403, 429}:
        return {}
    result = {}
    for header, field in (("X-RateLimit-Remaining", "rate_limit_remaining"),
                          ("X-RateLimit-Reset", "rate_limit_reset"), ("Retry-After", "retry_after_seconds")):
        value = error.headers.get(header) if error.headers is not None else None
        if isinstance(value, str) and re.fullmatch(r"[0-9]{1,19}", value) and int(value) <= (1 << 63) - 1:
            result[field] = int(value)
    return result


def safe_error_message(error: Exception) -> str:
    if isinstance(error, GateError) and error.diagnostics:
        return str(error) + " " + json.dumps(error.diagnostics, sort_keys=True, separators=(",", ":"))
    return str(error)


class RejectMetadataRedirects(HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, message, headers, new_url):
        raise GateError("PUBLIC_METADATA_REDIRECT_REJECTED")


class PublicGitHub:
    def __init__(self, token: str | None = None):
        if token is not None and (not isinstance(token, str) or not re.fullmatch(r"[A-Za-z0-9_]{20,255}", token)):
            raise GateError("INVALID_METADATA_TOKEN")
        self._token = token
        self._opener = build_opener(ProxyHandler({}), RejectMetadataRedirects())

    def __call__(self, path: str) -> Any:
        if not metadata_route(path):
            raise GateError("PUBLIC_METADATA_ROUTE_REJECTED")
        headers = {"Accept": "application/vnd.github+json", "User-Agent": "devdooly-lab-ci-gate"}
        if self._token is not None:
            headers["Authorization"] = "Bearer " + self._token
        request = Request(
            f"https://api.github.com/repos/{quote(REPOSITORY, safe='/')}/{path}",
            headers=headers, method="GET",
        )
        try:
            with self._opener.open(request, timeout=30) as response:
                data = response.read(2 * 1024 * 1024 + 1)
            if len(data) > 2 * 1024 * 1024:
                raise GateError("PUBLIC_METADATA_RESPONSE_TOO_LARGE")
            return json.loads(data)
        except HTTPError as exc:
            raise GateError(f"PUBLIC_METADATA_HTTP_{exc.code}", rate_diagnostics(exc)) from None
        except (URLError, TimeoutError, json.JSONDecodeError):
            raise GateError("PUBLIC_METADATA_UNAVAILABLE") from None


def write_outputs(path: str, values: dict[str, str]) -> None:
    # Restrict GitHub output fields to one line, even if future metadata changes.
    for key, value in values.items():
        if not re.fullmatch(r"[a-z_]+", key) or not isinstance(value, str) or any(c in value for c in "\r\n"):
            raise GateError("UNSAFE_OUTPUT")
    with open(path, "a", encoding="utf-8", newline="\n") as handle:
        for key, value in values.items():
            handle.write(f"{key}={value}\n")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--event-file", required=True)
    parser.add_argument("--event-name", required=True)
    parser.add_argument("--repository", required=True)
    parser.add_argument("--expected-issuer", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--require-eligible", action="store_true")
    parser.add_argument("--skip-if-published", action="store_true")
    parser.add_argument("--publication-run-id", default="")
    args = parser.parse_args()
    try:
        if args.repository.lower() != REPOSITORY.lower():
            raise GateError("WRONG_WORKFLOW_REPOSITORY")
        if Path(args.event_file).stat().st_size > 2 * 1024 * 1024:
            raise GateError("EVENT_TOO_LARGE")
        event = json.loads(Path(args.event_file).read_text(encoding="utf-8"))
        if not isinstance(event, dict):
            raise GateError("INVALID_EVENT")
        metadata = PublicGitHub(os.environ.get("LAB_GITHUB_METADATA_TOKEN"))
        result = evaluate(args.event_name, event, args.expected_issuer, metadata)
        if args.skip_if_published and already_published(result["commit"], args.publication_run_id, metadata):
            raise GatePending("SOURCE_ALREADY_PUBLISHED")
        write_outputs(args.output, result)
        print(json.dumps({key: result[key] for key in ("eligible", "commit", "validation_run_id", "jenkins_status_id", "jenkins_build_number")}, sort_keys=True))
        return 0
    except GatePending as exc:
        write_outputs(args.output, {"eligible": "false", "reason": str(exc)})
        print(f"Publication withheld: {exc}")
        return 1 if args.require_eligible else 0
    except (OSError, ValueError, TypeError, KeyError, AttributeError):
        print("Publication gate failed: INVALID_LOCAL_INPUT", file=sys.stderr)
        return 1
    except GateError as exc:
        print(f"Publication gate failed: {safe_error_message(exc)}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
