import copy
import importlib.util
from pathlib import Path
import unittest
import tempfile

spec = importlib.util.spec_from_file_location("run_jmh", Path(__file__).with_name("run_jmh.py"))
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def fixture():
    return [{"jmhVersion": "1.37", "benchmark": module.BENCHMARK + "." + method, "mode": "avgt", "threads": 1,
             "forks": 3, "warmupIterations": 2, "measurementIterations": 5, "warmupTime": "500 ms", "measurementTime": "500 ms",
             "jvmArgs": ["-Xms256m", "-Xmx256m", "-XX:+UseG1GC", "-Duser.timezone=Asia/Seoul"], "params": {"size": size, "profile": profile},
             "primaryMetric": {"scoreUnit": "us/op", "score": 1.0, "rawData": [[1.0] * 5 for _ in range(3)]},
             "secondaryMetrics": {"gc.alloc.rate.norm": {"scoreUnit": "B/op", "score": 128.0}}}
            for method in ("quadratic", "sweep") for profile in sorted(module.PROFILES) for size in sorted(module.SIZES)]


class ResultValidationTest(unittest.TestCase):
    def test_real_artifact_size_is_an_integer_property_and_matches_bytes(self):
        with tempfile.TemporaryDirectory() as folder:
            jar = Path(folder) / "fixture.jar"
            jar.write_bytes(b"independent-test-artifact")
            self.assertEqual({"jarSha256": module.sha(jar.read_bytes()), "jarBytes": 25}, module.artifact_identity(jar))

    def test_complete_three_forks_pass(self):
        self.assertTrue(module.validate_results(fixture()))

    def test_partial_failed_or_wrong_experiment_is_rejected(self):
        mutations = [lambda rows: rows.pop(), lambda rows: rows[0].update(forks=1),
                     lambda rows: rows[0]["primaryMetric"].update(rawData=[[1.0] * 5]),
                     lambda rows: rows[0]["primaryMetric"].update(score=float("nan")),
                     lambda rows: rows[0]["primaryMetric"].update(scoreUnit="ns/op"),
                     lambda rows: rows[0].update(secondaryMetrics={}),
                     lambda rows: rows[0]["secondaryMetrics"]["gc.alloc.rate.norm"].update(score=float("nan")),
                     lambda rows: rows[0]["secondaryMetrics"]["gc.alloc.rate.norm"].pop("score"),
                     lambda rows: rows[0]["secondaryMetrics"]["gc.alloc.rate.norm"].update(score=-1),
                     lambda rows: rows[0].update(jmhVersion="1.38-SNAPSHOT"),
                     lambda rows: rows[0].update(warmupTime="100 ms"),
                     lambda rows: rows[0].update(jvmArgs=["-Xmx128m"]),
                     lambda rows: rows[0].update(params={"profile": "sparse", "size": "9999"}),
                     lambda rows: rows.__setitem__(0, copy.deepcopy(rows[1]))]
        for mutation in mutations:
            rows = fixture()
            mutation(rows)
            with self.assertRaises(ValueError):
                module.validate_results(rows)


if __name__ == "__main__":
    unittest.main()
