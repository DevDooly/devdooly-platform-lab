import copy
import importlib.util
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location("values", ROOT / "infra/scripts/gitops_values.py")
values = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(values)


class GitOpsValuesTest(unittest.TestCase):
    def setUp(self):
        self.before = {
            "api": {"image": {"repository": values.REPOSITORIES["api"], "digest": "sha256:" + "a" * 64}, "sourceCommit": "a" * 40},
            "web": {"image": {"repository": values.REPOSITORIES["web"], "digest": "sha256:" + "b" * 64}},
            "database": {"existingSecret": "platform-lab-db"},
        }
        self.after = values.update(self.before, "c" * 40, "sha256:" + "c" * 64, "sha256:" + "d" * 64)

    def test_valid_update_and_rollback_are_allowed(self):
        self.assertEqual(values.validate_change(self.before, self.after), ["api.image.digest", "api.sourceCommit", "web.image.digest"])
        self.assertEqual(values.validate_change(self.after, self.before), ["api.image.digest", "api.sourceCommit", "web.image.digest"])

    def test_output_roundtrips_and_preserves_database_reference(self):
        self.assertEqual(values.parse(values.render(self.after)), self.after)
        self.assertEqual(self.before["database"], self.after["database"])

    def test_secret_name_cannot_change(self):
        self.after["database"]["existingSecret"] = "another-secret"
        with self.assertRaisesRegex(values.ValuesError, "CHANGES_OUTSIDE_IMAGE_ALLOWLIST"):
            values.validate_change(self.before, self.after)

    def test_password_injection_is_rejected(self):
        self.after["database"]["password"] = "sample-not-a-secret"
        with self.assertRaises(values.ValuesError):
            values.validate_change(self.before, self.after)

    def test_replicas_and_other_chart_values_cannot_be_added(self):
        for component in ("api", "web"):
            altered = copy.deepcopy(self.after)
            altered[component]["replicaCount"] = "2"
            with self.assertRaises(values.ValuesError):
                values.validate_change(self.before, altered)

    def test_foreign_image_repository_is_rejected(self):
        self.after["api"]["image"]["repository"] = "ghcr.io/another/api"
        with self.assertRaises(values.ValuesError):
            values.validate_change(self.before, self.after)

    def test_mutable_tags_and_malformed_digests_are_rejected(self):
        for candidate in ("latest", "sha256:abc", "sha256:" + "G" * 64, "sha256:" + "a" * 64 + "\neligible=true"):
            self.after["api"]["image"]["digest"] = candidate
            with self.assertRaises(values.ValuesError):
                values.validate_change(self.before, self.after)

    def test_metadata_only_source_change_cannot_claim_new_release(self):
        altered = copy.deepcopy(self.before)
        altered["api"]["sourceCommit"] = "d" * 40
        with self.assertRaisesRegex(values.ValuesError, "SOURCE_CHANGED_WITHOUT_IMAGE_CHANGE"):
            values.validate_change(self.before, altered)

    def test_noop_is_rejected(self):
        with self.assertRaisesRegex(values.ValuesError, "NO_DEPLOYMENT_CHANGE"):
            values.validate_change(self.before, self.before)

    def test_duplicate_keys_are_rejected(self):
        text = values.render(self.before).replace("api:\n", "api:\napi:\n")
        with self.assertRaisesRegex(values.ValuesError, "DUPLICATE_VALUES_KEY"):
            values.parse(text)

    def test_alias_tag_flow_block_and_tab_syntax_are_rejected(self):
        for candidate in ("api: &x", "api: !!map", "api: {}", "api: |", "\tapi:", "api:\n    image:"):
            with self.assertRaises(values.ValuesError):
                values.parse(candidate)

    def test_nesting_under_scalar_is_rejected(self):
        with self.assertRaises(values.ValuesError):
            values.parse("api: text\n  image: invalid")


if __name__ == "__main__":
    unittest.main()
