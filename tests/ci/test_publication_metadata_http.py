"""Exercise real Request/opener handling with an in-memory HTTPS transport only."""
import contextlib
from email.message import Message
import importlib.util
import io
import json
import os
from pathlib import Path
import re
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch
from urllib.error import HTTPError
from urllib.request import HTTPSHandler, ProxyHandler, build_opener
from urllib.response import addinfourl

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location("metadata_gate", ROOT / "infra/scripts/ci_publication_gate.py")
gate = importlib.util.module_from_spec(SPEC); SPEC.loader.exec_module(gate)
TOKEN = "ghs_" + "synthetic_not_a_real_token_" * 2
SOURCE = "a" * 40


class MemoryHTTPS(HTTPSHandler):
    def __init__(self, status=200, headers=None, body=b'{"ref":"refs/heads/main"}'):
        super().__init__(); self.status = status; self.headers = headers or {}; self.body = body; self.requests = []

    def https_open(self, request):
        self.requests.append(request)
        headers = Message()
        for key, value in self.headers.items(): headers[key] = value
        response = addinfourl(io.BytesIO(self.body), headers, request.full_url, self.status)
        response.msg = "synthetic transport response"
        return response


def client(transport, token=None):
    opener = build_opener(ProxyHandler({}), gate.RejectMetadataRedirects(), transport)
    with patch.object(gate, "build_opener", return_value=opener):
        return gate.PublicGitHub(token)


class MetadataHttpTest(unittest.TestCase):
    def test_explicit_ephemeral_token_only_in_header_for_fixed_tls_repository(self):
        transport = MemoryHTTPS(); remote = client(transport, TOKEN)
        self.assertEqual("refs/heads/main", remote("git/ref/heads/main")["ref"])
        request = transport.requests[0]
        self.assertEqual("https://api.github.com/repos/DevDooly/devdooly-platform-lab/git/ref/heads/main", request.full_url)
        self.assertEqual("GET", request.get_method())
        self.assertEqual("Bearer " + TOKEN, request.get_header("Authorization"))
        self.assertNotIn(TOKEN, request.full_url)

    def test_anonymous_client_ignores_other_token_environment_variables(self):
        transport = MemoryHTTPS()
        with patch.dict(os.environ, {"GH_TOKEN": TOKEN, "GITHUB_TOKEN": TOKEN, "LAB_GITHUB_METADATA_TOKEN": TOKEN}, clear=True):
            client(transport)("git/ref/heads/main")
        self.assertIsNone(transport.requests[0].get_header("Authorization"))

    def test_invalid_present_tokens_fail_before_any_request(self):
        for token in ("", "short", "a" * 256, TOKEN + "\r\nX-Injected: true", TOKEN + " ", "é" * 30, 123):
            with self.subTest(kind=type(token).__name__, length=len(token) if isinstance(token, str) else 0):
                with self.assertRaisesRegex(gate.GateError, "^INVALID_METADATA_TOKEN$"):
                    gate.PublicGitHub(token)

    def test_wrong_routes_and_url_injection_fail_before_transport(self):
        transport = MemoryHTTPS(); remote = client(transport, TOKEN)
        routes = ["https://evil.invalid/", "//evil.invalid/", "/git/ref/heads/main", "../another/repo", "git/ref/heads/../main",
                  "git/ref/heads/main#fragment", "git/ref/heads/main\n", "issues", "git/refs", "actions/runs/1?access_token=" + TOKEN,
                  "contents/.github/workflows/lab-ci.yml?ref=" + SOURCE, "commits/" + SOURCE + "/statuses?per_page=100&page=6",
                  "actions/workflows/lab-ci.yml/runs?head_sha=" + SOURCE + "&branch=main&per_page=100&per_page=1"]
        for route in routes:
            with self.subTest(route=route.split("?")[0]):
                with self.assertRaisesRegex(gate.GateError, "^PUBLIC_METADATA_ROUTE_REJECTED$"): remote(route)
        self.assertEqual([], transport.requests)

    def test_existing_gate_proposal_and_pr_validation_routes_remain_allowlisted(self):
        branch = "automation/lab-images/" + SOURCE
        routes = ["git/ref/heads/main", "actions/runs/123", "actions/runs/123/artifacts?per_page=100",
                  "actions/workflows/lab-ci.yml/runs?head_sha=" + SOURCE + "&branch=main&per_page=100",
                  "actions/workflows/publish-images.yml/runs?head_sha=" + SOURCE + "&per_page=100",
                  "commits/" + SOURCE + "/statuses?per_page=100&page=5", "git/ref/heads/" + branch,
                  "compare/" + SOURCE + "..." + branch, "contents/gitops/environments/home-lab/values.yaml?ref=" + SOURCE,
                  "contents/gitops/environments/home-lab/values.yaml?ref=automation%2Flab-images%2F" + SOURCE,
                  "pulls?state=open&base=main&head=DevDooly%3Aautomation%2Flab-images%2F" + SOURCE + "&per_page=10",
                  "pulls/1", "pulls/1/files?per_page=100&page=1"]
        for route in routes:
            with self.subTest(route=route): self.assertTrue(gate.metadata_route(route))

    def test_every_redirect_is_rejected_without_a_second_authenticated_request(self):
        for status in (301,302,303,307,308):
            for target in ("https://evil.invalid/leak", "http://evil.invalid/leak", "https://api.github.com/repos/other/repo"):
                transport = MemoryHTTPS(status, {"Location": target}, b"untrusted redirect body")
                with self.subTest(status=status, target=target):
                    with self.assertRaisesRegex(gate.GateError, "^PUBLIC_METADATA_REDIRECT_REJECTED$"):
                        client(transport, TOKEN)("git/ref/heads/main")
                    self.assertEqual(1, len(transport.requests))
                    self.assertEqual("api.github.com", transport.requests[0].host)

    def test_401_does_not_retry_anonymously_or_print_response(self):
        transport = MemoryHTTPS(401, {"X-RateLimit-Remaining":"999"}, ("secret echo " + TOKEN).encode())
        with self.assertRaises(gate.GateError) as failure: client(transport, TOKEN)("git/ref/heads/main")
        self.assertEqual("PUBLIC_METADATA_HTTP_401", str(failure.exception))
        self.assertEqual({}, failure.exception.diagnostics)
        self.assertEqual(1, len(transport.requests))
        self.assertNotIn(TOKEN, gate.safe_error_message(failure.exception))

    def test_403_and_429_emit_only_allowlisted_bounded_numeric_diagnostics(self):
        for status in (403,429):
            transport = MemoryHTTPS(status, {"X-RateLimit-Remaining":"0", "X-RateLimit-Reset":"1792067450", "Retry-After":"60",
                "Authorization":TOKEN, "X-Unknown-Header":TOKEN}, ("untrusted " + TOKEN).encode())
            with self.assertRaises(gate.GateError) as failure: client(transport, TOKEN)("git/ref/heads/main")
            self.assertEqual({"rate_limit_remaining":0,"rate_limit_reset":1792067450,"retry_after_seconds":60}, failure.exception.diagnostics)
            message = gate.safe_error_message(failure.exception)
            self.assertNotIn(TOKEN,message); self.assertNotIn("untrusted",message); self.assertNotIn("Authorization",message)
            self.assertEqual(1,len(transport.requests))

    def test_missing_or_malformed_rate_headers_do_not_imply_rate_limit_cause(self):
        for value in (None, "untrusted", "1\r\nprivate", "1.0", "-1", "9"*20, str(1 << 63), "Wed, 21 Oct 2026 07:28:00 GMT"):
            headers = Message()
            if value is not None:
                for name in ("X-RateLimit-Remaining","X-RateLimit-Reset","Retry-After"): headers[name] = value
            failure = HTTPError("https://api.github.com/",403,"untrusted",headers,None)
            self.assertEqual({},gate.rate_diagnostics(failure))

    def test_oversized_and_invalid_json_fail_closed(self):
        for raw, code in ((b"x"*(2*1024*1024+1),"PUBLIC_METADATA_RESPONSE_TOO_LARGE"),(b"not-json","PUBLIC_METADATA_UNAVAILABLE")):
            with self.assertRaisesRegex(gate.GateError,"^"+code+"$"):
                client(MemoryHTTPS(body=raw),TOKEN)("git/ref/heads/main")

    def test_one_main_client_is_reused_for_evaluation_and_deduplication(self):
        with tempfile.TemporaryDirectory() as folder:
            event = Path(folder)/"event.json"; event.write_text("{}",encoding="utf-8")
            output = Path(folder)/"out"; remote = Mock()
            result = {"eligible":"true","commit":SOURCE,"validation_run_id":"1","jenkins_status_id":"2","jenkins_build_number":"3"}
            arguments = ["gate","--event-file",str(event),"--event-name","status","--repository",gate.REPOSITORY,
                         "--expected-issuer","DevDooly","--output",str(output),"--skip-if-published","--publication-run-id","4"]
            with patch.object(sys,"argv",arguments),patch.dict(os.environ,{"LAB_GITHUB_METADATA_TOKEN":TOKEN},clear=True),\
                    patch.object(gate,"PublicGitHub",return_value=remote) as factory,patch.object(gate,"evaluate",return_value=result) as evaluate,\
                    patch.object(gate,"already_published",return_value=False) as dedup,contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(0,gate.main())
            factory.assert_called_once_with(TOKEN)
            self.assertIs(remote,evaluate.call_args.args[-1]);self.assertIs(remote,dedup.call_args.args[-1])

    def test_proposal_reader_and_writer_receive_separate_explicit_environment_values(self):
        sys.path.insert(0, str(ROOT / "infra/scripts"))
        import propose_gitops_pr as proposal
        for supplied in (True,False):
            with tempfile.TemporaryDirectory() as folder:
                manifest=Path(folder)/"manifest.json";manifest.write_text("{}",encoding="utf-8")
                env={"GH_TOKEN":"ghs_"+"writer_only_not_a_real_token_"*2}
                if supplied: env["LAB_GITHUB_METADATA_TOKEN"]=TOKEN
                reader,writer=Mock(),Mock()
                with patch.object(sys,"argv",["propose","--manifest",str(manifest),"--expected-issuer","DevDooly"]),\
                        patch.dict(os.environ,env,clear=True),patch.object(proposal,"PublicGitHub",return_value=reader) as factory,\
                        patch.object(proposal,"GitHubWriter",return_value=writer) as writer_factory,\
                        patch.object(proposal,"propose",return_value={"merged":False}) as propose,contextlib.redirect_stdout(io.StringIO()):
                    self.assertEqual(0,proposal.main())
                factory.assert_called_once_with(TOKEN if supplied else None)
                writer_factory.assert_called_once_with(env["GH_TOKEN"])
                self.assertIs(reader,propose.call_args.args[2]);self.assertIs(writer,propose.call_args.args[3])

    def test_workflow_token_is_step_local_to_all_four_metadata_readers(self):
        workflow = (ROOT/".github/workflows/publish-images.yml").read_text("utf-8")
        blocks = re.split(r"^      - name: ",workflow,flags=re.MULTILINE)[1:]
        readers=[]; token_steps=[]
        for block in blocks:
            reads = "python3 infra/scripts/ci_publication_gate.py" in block or "python3 .ci-tools/infra/scripts/ci_publication_gate.py" in block or "python3 infra/scripts/propose_gitops_pr.py" in block
            supplied = "          LAB_GITHUB_METADATA_TOKEN: ${{ github.token }}" in block
            if reads: readers.append(block.splitlines()[0]);self.assertTrue(supplied)
            if supplied: token_steps.append(block.splitlines()[0]);self.assertTrue(reads)
        self.assertEqual(4,len(readers));self.assertEqual(readers,token_steps)
        jobs=re.split(r"^  (gate|publish|propose-gitops):\n",workflow,flags=re.MULTILINE)
        expected={"gate":{"contents":"read","actions":"read","statuses":"read"},
                  "publish":{"contents":"read","packages":"write","actions":"read","statuses":"read"},
                  "propose-gitops":{"contents":"write","pull-requests":"write","actions":"read","statuses":"read"}}
        for index in range(1,len(jobs),2):
            permission=re.search(r"^    permissions:\n((?:      [a-z-]+: [a-z]+\n)+)",jobs[index+1],re.MULTILINE)
            self.assertIsNotNone(permission)
            self.assertEqual(expected[jobs[index]],dict(re.findall(r"      ([a-z-]+): ([a-z]+)",permission[1])))


if __name__ == "__main__": unittest.main()
