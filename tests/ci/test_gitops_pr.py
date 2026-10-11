import base64
import copy
import importlib
from pathlib import Path
import sys
import unittest

SCRIPTS = Path(__file__).resolve().parents[2] / "infra/scripts"
sys.path.insert(0, str(SCRIPTS))
gate = importlib.import_module("ci_publication_gate")
values = importlib.import_module("gitops_values")
proposal = importlib.import_module("propose_gitops_pr")
validator = importlib.import_module("validate_gitops_pr")
SHA, BASE, ISSUER = "c" * 40, "a" * 40, "DevDooly"


class FakeGitHub:
    def __init__(self):
        self.main = SHA
        self.before = {"api": {"image": {"repository": values.REPOSITORIES["api"], "digest": "sha256:" + "a" * 64}, "sourceCommit": BASE},
                       "web": {"image": {"repository": values.REPOSITORIES["web"], "digest": "sha256:" + "b" * 64}},
                       "database": {"existingSecret": "platform-lab-db"}}
        self.manifest = {"schemaVersion": 1, "sourceCommit": SHA, "validationRunId": 100,
                         "publicationRunUrl": f"https://github.com/{gate.REPOSITORY}/actions/runs/300",
                         "jenkins": {"context": gate.CONTEXT, "statusId": 200, "buildNumber": 4, "issuer": ISSUER},
                         "images": {}}
        for component, letter in (("api", "c"), ("web", "d")):
            repository = values.REPOSITORIES[component]
            digest = "sha256:" + letter * 64
            self.manifest["images"][component] = {"repository": repository, "digest": digest,
                                                   "reference": f"{repository}@{digest}", "platform": "linux/amd64"}
        self.branch_exists = False
        self.branch_text = values.render(self.before)
        self.prs = []
        self.writes = []
        self.branch_files = [{"filename": validator.VALUES_PATH, "status": "modified"}]

    def get(self, route):
        if route == "git/ref/heads/main":
            return {"ref": "refs/heads/main", "object": {"type": "commit", "sha": self.main}}
        if route.startswith("actions/workflows/lab-ci.yml/runs?"):
            return {"workflow_runs": [{"id": 100, "name": "Validate Lab containers", "path": gate.WORKFLOW_PATH,
                                      "head_sha": SHA, "head_branch": "main", "event": "push", "status": "completed", "conclusion": "success",
                                      "created_at": "2026-10-11T12:00:00Z", "updated_at": "2026-10-11T12:05:00Z",
                                      "run_started_at": "2026-10-11T12:00:00Z",
                                      "repository": {"full_name": gate.REPOSITORY, "private": False},
                                      "head_repository": {"full_name": gate.REPOSITORY}}]}
        if route.startswith("commits/"):
            return [{"id": 200, "state": "success", "context": gate.CONTEXT, "creator": {"login": ISSUER},
                     "description": "Jenkins build #4: tests and artifacts verified"}]
        if route.startswith("git/ref/heads/automation/"):
            if not self.branch_exists:
                raise gate.GateError("PUBLIC_METADATA_HTTP_404")
            return {"object": {"type": "commit", "sha": "f" * 40}}
        if route.startswith("contents/"):
            text = values.render(self.before) if f"ref={SHA}" in route else self.branch_text
            return {"type": "file", "encoding": "base64", "size": len(text), "sha": "e" * 40,
                    "content": base64.b64encode(text.encode()).decode()}
        if route.startswith("compare/"):
            return {"files": self.branch_files}
        if route.startswith("pulls?"):
            return self.prs
        if route == "pulls/1":
            return self.prs[0]
        raise AssertionError(f"Unexpected metadata route: {route}")

    def write(self, method, route, document):
        self.writes.append((method, route, document))
        if route == "git/refs":
            self.branch_exists = True
            return {"ref": document["ref"]}
        if route.startswith("contents/"):
            self.branch_text = base64.b64decode(document["content"]).decode()
            return {"commit": {"sha": "f" * 40}}
        if route == "pulls":
            pr = {"number": 1, "html_url": f"https://github.com/{gate.REPOSITORY}/pull/1",
                  "state": "open", "draft": True, "auto_merge": None,
                  "base": {"ref": "main", "repo": {"full_name": gate.REPOSITORY}},
                  "head": {"ref": document["head"], "sha": "f" * 40, "repo": {"full_name": gate.REPOSITORY}}}
            self.prs = [pr]
            return pr
        raise AssertionError("Unexpected write route")


class GitOpsProposalTest(unittest.TestCase):
    def setUp(self):
        self.remote = FakeGitHub()

    def run_proposal(self):
        return proposal.propose(self.remote.manifest, ISSUER, self.remote.get, self.remote.write)

    def test_draft_proposal_mutates_only_dedicated_branch_file_and_pr(self):
        result = self.run_proposal()
        self.assertFalse(result["merged"])
        self.assertFalse(result["deployed"])
        self.assertEqual([item[:2] for item in self.remote.writes], [
            ("POST", "git/refs"), ("PUT", "contents/" + validator.VALUES_PATH), ("POST", "pulls")])
        branch = "automation/lab-images/" + SHA
        self.assertEqual(self.remote.writes[0][2], {"ref": "refs/heads/" + branch, "sha": SHA})
        self.assertEqual(self.remote.writes[1][2]["branch"], branch)
        self.assertEqual(self.remote.writes[2][2]["base"], "main")
        self.assertTrue(self.remote.writes[2][2]["draft"])
        after = values.parse(self.remote.branch_text)
        self.assertEqual(after["database"], self.remote.before["database"])

    def test_confirmed_existing_branch_and_pr_are_reused_without_writes(self):
        self.run_proposal()
        self.remote.writes = []
        self.assertTrue(self.run_proposal()["reused"])
        self.assertEqual(self.remote.writes, [])

    def test_stale_main_blocks_before_any_mutation(self):
        self.remote.main = "f" * 40
        with self.assertRaisesRegex(proposal.ProposalError, "MAIN_MOVED"):
            self.run_proposal()
        self.assertEqual(self.remote.writes, [])

    def test_stale_ci_artifact_blocks_before_any_mutation(self):
        self.remote.manifest["jenkins"]["statusId"] = 199
        with self.assertRaisesRegex(proposal.ProposalError, "CI_EVIDENCE_IS_NO_LONGER_CURRENT"):
            self.run_proposal()
        self.assertEqual(self.remote.writes, [])

    def test_foreign_image_repository_is_rejected_without_write(self):
        self.remote.manifest["images"]["api"]["repository"] = "ghcr.io/other/api"
        with self.assertRaises(proposal.ProposalError):
            self.run_proposal()
        self.assertEqual(self.remote.writes, [])

    def test_other_publication_url_and_issuer_are_rejected(self):
        for field in ("url", "issuer"):
            data = copy.deepcopy(self.remote.manifest)
            if field == "url":
                data["publicationRunUrl"] = "https://example.invalid/"
            else:
                data["jenkins"]["issuer"] = "other-bot"
            with self.assertRaises(proposal.ProposalError):
                proposal.prepare(data, SHA, values.render(self.remote.before), ISSUER)

    def test_existing_branch_with_other_changes_is_not_overwritten(self):
        self.run_proposal()
        self.remote.writes = []
        self.remote.branch_files.append({"filename": "README.md", "status": "modified"})
        with self.assertRaisesRegex(proposal.ProposalError, "UNRELATED_CHANGES"):
            self.run_proposal()
        self.assertEqual(self.remote.writes, [])

    def test_ready_or_auto_merge_pr_is_not_updated(self):
        for alteration in ({"draft": False}, {"auto_merge": {"merge_method": "squash"}}):
            self.remote = FakeGitHub()
            self.run_proposal()
            self.remote.writes = []
            self.remote.prs[0].update(alteration)
            self.remote.manifest["images"]["api"].update({"digest": "sha256:" + "e" * 64,
                "reference": values.REPOSITORIES["api"] + "@sha256:" + "e" * 64})
            with self.assertRaisesRegex(proposal.ProposalError, "SAFE_DRAFT"):
                self.run_proposal()
            self.assertEqual(self.remote.writes, [])

    def test_pr_with_foreign_head_repository_is_not_reused(self):
        self.run_proposal()
        self.remote.writes = []
        self.remote.prs[0]["head"]["repo"]["full_name"] = "other/fork"
        with self.assertRaisesRegex(proposal.ProposalError, "SAFE_DRAFT"):
            self.run_proposal()
        self.assertEqual(self.remote.writes, [])


class GitOpsPrScopeTest(unittest.TestCase):
    def setUp(self):
        self.before = FakeGitHub().before
        self.after = values.update(self.before, SHA, "sha256:" + "c" * 64, "sha256:" + "d" * 64)
        self.files = [{"filename": validator.VALUES_PATH, "status": "modified"}]
        self.metadata = {"state": "open", "base": {"ref": "main", "sha": BASE, "repo": {"full_name": gate.REPOSITORY}},
                         "head": {"sha": SHA}}
        self.requests = []

    def get(self, route):
        self.requests.append(route)
        if route == "pulls/1":
            return self.metadata
        if route.startswith("pulls/1/files?"):
            return self.files
        if route.startswith("contents/"):
            document = self.before if f"ref={BASE}" in route else self.after
            text = values.render(document)
            return {"type": "file", "size": len(text), "encoding": "base64", "content": base64.b64encode(text.encode()).decode()}
        raise AssertionError("Unexpected public metadata route")

    def evaluate(self):
        return validator.evaluate_pr(1, BASE, SHA, self.get)

    def test_valid_pr_reports_scope_only_and_reads_no_untrusted_scripts(self):
        result = self.evaluate()
        self.assertEqual(result["changedFields"], ["api.image.digest", "api.sourceCommit", "web.image.digest"])
        self.assertFalse(result["registryContentsVerified"])
        self.assertFalse(result["helmRenderVerified"])
        self.assertFalse(result["deploymentVerified"])
        self.assertTrue(all("Jenkinsfile" not in route and "scripts/" not in route for route in self.requests))

    def test_mixed_app_and_values_change_is_rejected(self):
        self.files.append({"filename": "apps/api/pom.xml", "status": "modified"})
        with self.assertRaises(values.ValuesError):
            self.evaluate()

    def test_deleted_or_renamed_values_file_is_rejected(self):
        for status in ("removed", "renamed", "added"):
            self.files[0]["status"] = status
            with self.assertRaises(values.ValuesError):
                self.evaluate()

    def test_updated_pr_head_cannot_use_stale_event_data(self):
        self.metadata["head"]["sha"] = "f" * 40
        with self.assertRaisesRegex(values.ValuesError, "PULL_REQUEST_MOVED"):
            self.evaluate()


if __name__ == "__main__":
    unittest.main()
