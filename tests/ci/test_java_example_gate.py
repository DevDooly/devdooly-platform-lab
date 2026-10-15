"""Exercise the real pre-publication artifact guard without CI credentials or builds."""
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
PIPELINE = (ROOT / "Jenkinsfile").read_text(encoding="utf-8")


def archive_script():
    stage = PIPELINE.split("stage('Archive verified CI')", 1)[1].split("stage('Record success CI')", 1)[0]
    scripts = re.findall(r"script: '''(.*?)'''", stage, flags=re.DOTALL)
    if len(scripts) != 1:
        raise AssertionError("One mandatory artifact guard must precede publication")
    return scripts[0]


def shell():
    executable = shutil.which("sh")
    if executable:
        return executable
    # Keep local Windows verification equivalent to Ubuntu CI using existing Git Bash.
    candidate = Path(os.environ.get("ProgramFiles", "C:/Program Files")) / "Git/usr/bin/sh.exe"
    if candidate.is_file():
        return str(candidate)
    raise AssertionError("A POSIX shell is required to exercise the actual CI artifact guard")


class JavaExamplePublicationGateTest(unittest.TestCase):
    def test_example_verification_and_required_archive_precede_success_status(self):
        stages = re.findall(r"stage\('([^']+)'\)", PIPELINE)
        self.assertEqual(len(stages), len(set(stages)))
        self.assertLess(stages.index("Verify Java example"), stages.index("Archive verified CI"))
        self.assertLess(stages.index("Archive verified CI"), stages.index("Record success CI"))

    def test_actual_archive_guard_rejects_missing_or_empty_example_jar(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for relative in ("apps/api/target/platform-lab-api-test.jar", "apps/lab-web/dist/index.html",
                             "ci-build-info.txt", "artifacts/jenkins/status-pending.json"):
                path = root / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(b"synthetic-artifact-guard-fixture")

            def execute():
                return subprocess.run([shell()], input=archive_script(), cwd=root, text=True,
                                      capture_output=True, timeout=10).returncode

            self.assertNotEqual(0, execute(), "A missing example JAR must withhold publication")
            jar = root / "examples/java-window-analysis/target/benchmarks.jar"
            jar.parent.mkdir(parents=True)
            jar.touch()
            self.assertNotEqual(0, execute(), "An empty example JAR must withhold publication")
            jar.write_bytes(b"synthetic-example-jar")
            self.assertEqual(0, execute(), "All required nonempty fixture artifacts satisfy the guard")


if __name__ == "__main__":
    unittest.main()
