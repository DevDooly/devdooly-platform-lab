"""No network/credentials: exercise the actual publication decision function."""
import copy
import importlib.util
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location("gate", ROOT / "infra/scripts/ci_publication_gate.py")
gate = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(gate)
SHA = "a" * 40
OTHER = "b" * 40
ISSUER = "platform-lab-ci[bot]"
REPO = {"full_name": gate.REPOSITORY, "private": False}


class Fixture:
    def __init__(self):
        self.run = {
            "id": 100, "name": "Validate Lab containers", "path": gate.WORKFLOW_PATH,
            "head_sha": SHA, "head_branch": "main", "event": "push",
            "status": "completed", "conclusion": "success", "run_attempt": 1,
            "created_at": "2026-10-11T12:00:00Z", "updated_at": "2026-10-11T12:05:00Z",
            "run_started_at": "2026-10-11T12:00:00Z",
            "repository": copy.deepcopy(REPO), "head_repository": copy.deepcopy(REPO),
        }
        self.runs = [self.run]
        self.statuses = [{
            "id": 200, "context": gate.CONTEXT, "state": "success", "creator": {"login": ISSUER},
            "description": "Jenkins build #4: tests and artifacts verified",
        }]
        self.head = SHA
        self.main_type = "commit"
        self.requests = []

    def get(self, route):
        self.requests.append(route)
        if route.startswith("actions/runs/"):
            return self.run
        if route == "git/ref/heads/main":
            return {"ref": "refs/heads/main", "object": {"type": self.main_type, "sha": self.head}}
        if route.startswith("actions/workflows/lab-ci.yml/runs?"):
            return {"workflow_runs": self.runs}
        if route.startswith(f"commits/{SHA}/statuses?"):
            return self.statuses
        raise AssertionError(f"Unexpected public metadata request: {route}")

    def event(self, name):
        result = {"repository": copy.deepcopy(REPO)}
        if name == "workflow_run":
            result["workflow_run"] = copy.deepcopy(self.run)
        elif name == "status":
            result.update({"sha": SHA, "state": "success", "context": gate.CONTEXT})
        elif name == "workflow_dispatch":
            result["inputs"] = {"validation_run_id": "100"}
        return result


class PublicationGateTest(unittest.TestCase):
    def setUp(self):
        self.f = Fixture()

    def evaluate(self, name="workflow_run", event=None, issuer=ISSUER):
        return gate.evaluate(name, event or self.f.event(name), issuer, self.f.get)

    def denied(self, reason, name="workflow_run", event=None, issuer=ISSUER):
        with self.assertRaises(gate.GateError) as caught:
            self.evaluate(name, event, issuer)
        self.assertEqual(str(caught.exception), reason)

    def test_both_success_exact_main_workflow_event(self):
        result = self.evaluate()
        self.assertEqual(result["eligible"], "true")
        self.assertEqual(result["commit"], SHA)
        self.assertEqual(result["jenkins_status_id"], "200")
        self.assertEqual(result["jenkins_build_number"], "4")

    def test_jenkins_finishing_last_status_event_uses_event_sha(self):
        self.assertEqual(self.evaluate("status")["commit"], SHA)

    def test_manual_event_has_no_gate_bypass(self):
        self.assertEqual(self.evaluate("workflow_dispatch")["validation_run_id"], "100")
        self.f.statuses[0]["state"] = "failure"
        self.denied("LATEST_JENKINS_NOT_SUCCESSFUL", "workflow_dispatch")

    def test_missing_issuer_fails_before_any_network(self):
        self.denied("JENKINS_STATUS_ISSUER_NOT_CONFIGURED", issuer="")
        self.assertEqual(self.f.requests, [])

    def test_issuer_cannot_inject_output_lines(self):
        self.denied("JENKINS_STATUS_ISSUER_NOT_CONFIGURED", issuer="actor\neligible=true")

    def test_outdated_main_is_not_published(self):
        self.f.head = OTHER
        self.denied("SOURCE_IS_NOT_CURRENT_MAIN")

    def test_tag_object_cannot_stand_in_for_main_commit(self):
        self.f.main_type = "tag"
        self.denied("INVALID_MAIN_REFERENCE")

    def test_jenkins_missing_is_not_assumed_success(self):
        self.f.statuses = []
        self.denied("JENKINS_STATUS_MISSING")

    def test_jenkins_failure_blocks_after_successful_actions(self):
        self.f.statuses[0]["state"] = "failure"
        self.denied("LATEST_JENKINS_NOT_SUCCESSFUL")

    def test_jenkins_pending_blocks_after_successful_actions(self):
        self.f.statuses[0]["state"] = "pending"
        self.denied("LATEST_JENKINS_NOT_SUCCESSFUL")

    def test_a_newer_failure_does_not_fall_back_to_older_success(self):
        latest = copy.deepcopy(self.f.statuses[0])
        latest.update({"id": 201, "state": "failure"})
        self.f.statuses.insert(0, latest)
        self.denied("LATEST_JENKINS_NOT_SUCCESSFUL")

    def test_wrong_issuer_cannot_fall_back_to_older_trusted_success(self):
        latest = copy.deepcopy(self.f.statuses[0])
        latest.update({"id": 201, "creator": {"login": "other-bot"}})
        self.f.statuses.insert(0, latest)
        self.denied("UNEXPECTED_JENKINS_STATUS_ISSUER")

    def test_false_boolean_cannot_stand_in_for_status_id(self):
        self.f.statuses[0]["id"] = True
        self.denied("INVALID_JENKINS_STATUS_ID")

    def test_noop_success_without_verification_metadata_is_rejected(self):
        self.f.statuses[0]["description"] = "SUCCESS"
        self.denied("JENKINS_VERIFICATION_METADATA_MISSING")

    def test_latest_actions_failure_blocks_older_success(self):
        newer = copy.deepcopy(self.f.run)
        newer.update({"id": 101, "conclusion": "failure"})
        self.f.runs.insert(0, newer)
        self.denied("LATEST_VALIDATION_NOT_SUCCESSFUL")

    def test_older_run_id_rerun_failure_supersedes_newer_run_success(self):
        later_rerun = copy.deepcopy(self.f.run)
        later_rerun.update({"id": 99, "run_attempt": 2, "conclusion": "failure",
                            "run_started_at": "2026-10-11T12:10:00Z", "updated_at": "2026-10-11T12:15:00Z"})
        self.f.runs.append(later_rerun)
        self.denied("LATEST_VALIDATION_NOT_SUCCESSFUL")

    def test_older_run_id_queued_rerun_does_not_expose_old_success(self):
        later_rerun = copy.deepcopy(self.f.run)
        later_rerun.update({"id": 99, "run_attempt": 2, "status": "queued", "conclusion": None,
                            "run_started_at": None, "updated_at": "2026-10-11T12:10:00Z"})
        self.f.runs.append(later_rerun)
        self.denied("LATEST_VALIDATION_NOT_SUCCESSFUL")

    def test_newer_queued_run_blocks_later_completion_of_old_success(self):
        self.f.run["updated_at"] = "2026-10-11T12:10:00Z"
        newer = copy.deepcopy(self.f.run)
        newer.update({"id": 101, "status": "queued", "conclusion": None,
                      "created_at": "2026-10-11T12:05:00Z", "updated_at": "2026-10-11T12:05:00Z",
                      "run_started_at": None})
        self.f.runs.append(newer)
        self.denied("LATEST_VALIDATION_NOT_SUCCESSFUL")

    def test_newer_failed_attempt_blocks_later_completion_of_old_success(self):
        self.f.run["updated_at"] = "2026-10-11T12:20:00Z"
        newer = copy.deepcopy(self.f.run)
        newer.update({"id": 101, "conclusion": "failure", "run_started_at": "2026-10-11T12:05:00Z",
                      "updated_at": "2026-10-11T12:10:00Z"})
        self.f.runs.append(newer)
        self.denied("LATEST_VALIDATION_NOT_SUCCESSFUL")

    def test_missing_execution_timestamp_fails_closed(self):
        self.f.run.pop("updated_at")
        self.denied("INVALID_VALIDATION_ACTIVITY_METADATA")

    def test_latest_actions_running_blocks_older_success(self):
        newer = copy.deepcopy(self.f.run)
        newer.update({"id": 101, "status": "in_progress", "conclusion": None})
        self.f.runs.insert(0, newer)
        self.denied("LATEST_VALIDATION_NOT_SUCCESSFUL")

    def test_same_run_rerun_failure_is_not_hidden(self):
        self.f.run.update({"run_attempt": 2, "conclusion": "failure"})
        self.denied("VALIDATION_EVENT_NOT_SUCCESSFUL")

    def test_no_matching_actions_sha_is_not_accepted(self):
        self.f.runs = [{**self.f.run, "head_sha": OTHER}]
        self.denied("NO_MATCHING_VALIDATION_RUN")

    def test_fork_validation_is_rejected(self):
        self.f.run["head_repository"] = {"full_name": "someone/fork"}
        self.denied("VALIDATION_EVENT_NOT_SUCCESSFUL")

    def test_wrong_workflow_path_is_rejected(self):
        self.f.run["path"] = ".github/workflows/another.yml"
        self.denied("VALIDATION_EVENT_NOT_SUCCESSFUL")

    def test_official_workflow_path_with_main_ref_suffix_is_supported(self):
        for suffix in ("@main", "@refs/heads/main", "@" + SHA):
            self.f.run["path"] = gate.WORKFLOW_PATH + suffix
            self.assertEqual(self.evaluate()["eligible"], "true")

    def test_workflow_path_with_different_ref_is_rejected(self):
        self.f.run["path"] = gate.WORKFLOW_PATH + "@another-branch"
        self.denied("VALIDATION_EVENT_NOT_SUCCESSFUL")

    def test_pull_request_run_is_not_publishable(self):
        self.f.run["event"] = "pull_request"
        self.denied("VALIDATION_EVENT_NOT_SUCCESSFUL")

    def test_event_payload_success_cannot_override_live_failure(self):
        event = self.f.event("workflow_run")
        self.f.run["conclusion"] = "failure"
        self.denied("VALIDATION_RUN_NOT_SUCCESSFUL", event=event)

    def test_foreign_event_repository_is_rejected(self):
        event = self.f.event("status")
        event["repository"]["full_name"] = "someone/another"
        self.denied("WRONG_EVENT_REPOSITORY", "status", event)

    def test_unrelated_status_does_not_publish(self):
        event = self.f.event("status")
        event["context"] = "unrelated"
        self.denied("UNRELATED_OR_UNSUCCESSFUL_STATUS", "status", event)

    def test_failed_status_event_does_not_publish(self):
        event = self.f.event("status")
        event["state"] = "failure"
        self.denied("UNRELATED_OR_UNSUCCESSFUL_STATUS", "status", event)

    def test_unknown_sha_and_output_injection_are_rejected(self):
        event = self.f.event("status")
        event["sha"] = "unknown\neligible=true"
        self.denied("INVALID_SOURCE_SHA", "status", event)

    def test_manual_run_id_must_be_numeric(self):
        event = self.f.event("workflow_dispatch")
        event["inputs"]["validation_run_id"] = "../other"
        self.denied("INVALID_VALIDATION_RUN_ID", "workflow_dispatch", event)

    def test_ci_issuer_and_context_are_case_insensitive(self):
        self.f.statuses[0]["context"] = gate.CONTEXT.upper()
        self.f.statuses[0]["creator"]["login"] = ISSUER.upper()
        self.assertEqual(self.evaluate()["eligible"], "true")

    def test_other_newer_context_does_not_replace_jenkins(self):
        self.f.statuses.insert(0, {"context": "security/scan", "state": "failure"})
        self.assertEqual(self.evaluate()["eligible"], "true")

    def test_output_is_single_line_and_rejects_multiline_values(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "github-output"
            gate.write_outputs(str(output), {"eligible": "false", "reason": "JENKINS_STATUS_MISSING"})
            self.assertEqual(output.read_text(), "eligible=false\nreason=JENKINS_STATUS_MISSING\n")
            with self.assertRaises(gate.GateError):
                gate.write_outputs(str(output), {"commit": "abc\neligible=true"})


class PublicationDeduplicationTest(unittest.TestCase):
    def setUp(self):
        self.run = {"id": 300, "head_sha": SHA, "status": "completed", "conclusion": "success",
                    "path": ".github/workflows/publish-images.yml", "repository": REPO, "head_repository": REPO}
        self.artifacts = [{"name": f"lab-images-{SHA}-300-1", "expired": False, "size_in_bytes": 100}]

    def get(self, route):
        if route.startswith("actions/workflows/publish-images.yml/runs?"):
            return {"workflow_runs": [self.run]}
        if route == "actions/runs/300/artifacts?per_page=100":
            return {"artifacts": self.artifacts}
        raise AssertionError("Unexpected publication metadata route")

    def test_verified_publication_artifact_prevents_same_source_republication(self):
        self.assertTrue(gate.already_published(SHA, "301", self.get))

    def test_noop_workflow_success_without_artifact_is_not_publication(self):
        self.artifacts = []
        self.assertFalse(gate.already_published(SHA, "301", self.get))

    def test_current_run_does_not_deduplicate_itself(self):
        self.assertFalse(gate.already_published(SHA, "300", self.get))

    def test_expired_or_other_source_artifact_is_not_reused(self):
        self.artifacts[0]["expired"] = True
        self.assertFalse(gate.already_published(SHA, "301", self.get))
        self.artifacts[0].update({"expired": False, "name": f"lab-images-{OTHER}-300-1"})
        self.assertFalse(gate.already_published(SHA, "301", self.get))

    def test_failed_or_foreign_workflow_is_not_publication(self):
        self.run["conclusion"] = "failure"
        self.assertFalse(gate.already_published(SHA, "301", self.get))
        self.run["conclusion"] = "success"
        self.run["head_repository"] = {"full_name": "someone/fork"}
        self.assertFalse(gate.already_published(SHA, "301", self.get))


if __name__ == "__main__":
    unittest.main()
