#!/usr/bin/env python3
"""Run the fixed 3-fork experiment once into a new directory; never overwrite evidence.

This script imposes a wall-clock deadline, not a CPU/memory cgroup. When running on
the mini PC, the operator must provide an isolated resource scope and reserve guard.
"""
import argparse
import hashlib
import json
import math
import os
import platform
from pathlib import Path
import re
import signal
import subprocess
import sys
from datetime import datetime, timezone

sys.dont_write_bytecode = True
MODULE = Path(__file__).resolve().parents[1]
BENCHMARK = "io.github.devdooly.examples.window.WindowBenchmark"
SIZES = {"128", "512", "2048", "4096"}
PROFILES = {"sparse", "nested"}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def artifact_identity(path):
    return {"jarSha256": sha(path.read_bytes()), "jarBytes": path.stat().st_size}


def write_json(path, value):
    with path.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write("\n")


def source_manifest():
    entries = []
    for path in sorted(MODULE.rglob("*")):
        relative = path.relative_to(MODULE)
        if path.is_file() and relative.parts[0] not in {"target", "results", ".git"} and "__pycache__" not in relative.parts:
            entries.append({"path": relative.as_posix(), "size": path.stat().st_size, "sha256": sha(path.read_bytes())})
    return entries


def validate_results(value):
    require(isinstance(value, list) and len(value) == 16, "Exactly 16 benchmark/parameter records are required")
    seen = set()
    for row in value:
        require(isinstance(row, dict) and row.get("jmhVersion") == "1.37", "JMH 1.37 is required")
        require(row.get("benchmark") in {BENCHMARK + ".quadratic", BENCHMARK + ".sweep"}, "Unexpected benchmark")
        require(row.get("mode") == "avgt" and row.get("threads") == 1 and row.get("forks") == 3, "Unexpected execution mode")
        require(row.get("warmupIterations") == 2 and row.get("measurementIterations") == 5,
                "Fixed warmup and measurement counts are required")
        require(row.get("warmupTime") == "500 ms" and row.get("measurementTime") == "500 ms",
                "Fixed 500ms iteration durations are required")
        require(set(row.get("jvmArgs", [])) == {"-Xms256m", "-Xmx256m", "-XX:+UseG1GC", "-Duser.timezone=Asia/Seoul"},
                "Fixed fork heap, GC and timezone are required")
        require(row.get("params", {}).get("size") in SIZES and row.get("params", {}).get("profile") in PROFILES,
                "Unexpected synthetic parameter")
        key = (row["benchmark"], row["params"]["profile"], row["params"]["size"])
        require(key not in seen, "Duplicate benchmark/parameter record")
        seen.add(key)
        metric = row.get("primaryMetric", {})
        require(metric.get("scoreUnit") == "us/op" and isinstance(metric.get("score"), (int, float))
                and math.isfinite(metric["score"]) and metric["score"] > 0, "Finite positive microseconds per operation required")
        samples = metric.get("rawData")
        require(isinstance(samples, list) and len(samples) == 3, "All three JVM fork measurements are required")
        for fork in samples:
            require(isinstance(fork, list) and len(fork) == 5
                    and all(type(sample) in (int, float) and math.isfinite(sample) and sample > 0 for sample in fork),
                    "Five finite positive measurements per fork required")
        secondary = row.get("secondaryMetrics", {})
        require("gc.alloc.rate.norm" in secondary and secondary["gc.alloc.rate.norm"].get("scoreUnit") == "B/op",
                "Allocation profiler result is required")
        allocation = secondary["gc.alloc.rate.norm"].get("score")
        require(type(allocation) in (int, float) and math.isfinite(allocation) and allocation >= 0,
                "Finite nonnegative allocation bytes per operation required")
    return True


def run_bounded(command, stdout, stderr):
    # Own process group only. A timeout must not leave a benchmark fork orphaned.
    options = {"start_new_session": True} if os.name == "posix" else {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP}
    process = subprocess.Popen(command, cwd=MODULE, stdout=stdout, stderr=stderr, **options)
    try:
        return process.wait(timeout=420)
    except BaseException:
        if os.name == "posix":
            try:
                os.killpg(process.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait(timeout=10)
        else:
            subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"], stdout=stderr, stderr=stderr, timeout=15, check=False)
            process.wait(timeout=10)
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--java", required=True, help="Java 21 executable")
    parser.add_argument("--source-commit", help="Operator-provided actual committed source SHA; omit for a private uncommitted overlay")
    parser.add_argument("--output-dir", required=True, type=Path, help="New directory outside the source module")
    args = parser.parse_args()
    require(args.source_commit is None or re.fullmatch(r"[0-9a-f]{40}", args.source_commit) is not None,
            "A provided source commit must be a full SHA")
    output = args.output_dir.resolve()
    require(not output.is_relative_to(MODULE), "Results must be outside the immutable source module")
    jar = MODULE / "target" / "benchmarks.jar"
    require(jar.is_file(), "Build target/benchmarks.jar with mvn verify first")
    version = subprocess.run([args.java, "-version"], capture_output=True, timeout=10, check=True)
    version_text = (version.stdout + version.stderr).decode("utf-8", errors="replace")
    require(re.search(r'(?:openjdk|java) version "21(?:[.\"]|$)', version_text) is not None, "Java 21 is required")
    output.mkdir(mode=0o700, parents=False, exist_ok=False)
    manifest = source_manifest()
    metadata = {"schemaVersion": 1, "scope": "INDEPENDENT_SYNTHETIC_JMH", "sourceCommit": args.source_commit,
                "sourceCommitProvenance": "operator-provided; sourceFiles independently hashed" if args.source_commit else "UNCOMMITTED_PRIVATE_OVERLAY; sourceFiles independently hashed",
                "sourceFiles": manifest,
                "sourceManifestSha256": sha(json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode()),
                **artifact_identity(jar), "javaVersion": version_text,
                "hostOperatingSystem": {"system": platform.system(), "release": platform.release(), "version": platform.version(),
                                        "architecture": platform.machine(), "processor": platform.processor(), "logicalCpuCount": os.cpu_count()},
                "startedAt": datetime.now(timezone.utc).isoformat(), "passed": False,
                "productionEtlChanged": False, "companyDataUsed": False,
                "cpuMemoryIsolationProvidedByThisScript": False}
    write_json(output / "metadata-before.json", metadata)
    try:
        fixture = subprocess.run([args.java, "-cp", str(jar), "io.github.devdooly.examples.window.FixtureManifest"],
                                 capture_output=True, timeout=30, check=True)
        with (output / "fixtures.tsv").open("xb") as stream:
            stream.write(fixture.stdout)
        command = [args.java, "-jar", str(jar), "^" + BENCHMARK.replace(".", r"\.") + r"\.(quadratic|sweep)$",
                   "-f", "3", "-wf", "0", "-t", "1", "-bm", "avgt", "-tu", "us", "-wi", "2", "-w", "500ms",
                   "-i", "5", "-r", "500ms", "-to", "10s", "-foe", "true", "-prof", "gc",
                   "-jvmArgs", "-Xms256m -Xmx256m -XX:+UseG1GC -Duser.timezone=Asia/Seoul", "-rf", "json", "-rff", str(output / "jmh.json")]
        metadata["command"] = command
        with (output / "stdout.log").open("xb") as stdout, (output / "stderr.log").open("xb") as stderr:
            returncode = run_bounded(command, stdout, stderr)
        require(returncode == 0, "JMH exited unsuccessfully; raw evidence is preserved")
        raw_result = (output / "jmh.json").read_bytes()
        validate_results(json.loads(raw_result))
        require(source_manifest() == manifest, "Source files changed during measurement")
        require(sha(jar.read_bytes()) == metadata["jarSha256"], "Benchmark JAR changed during measurement")
        metadata.update({"passed": True, "resultSha256": sha(raw_result), "fixtureManifestSha256": sha(fixture.stdout),
                         "benchmarkRecords": 16, "forksPerRecord": 3, "measurementSamplesPerFork": 5})
    except Exception as failure:
        metadata["failureClass"] = type(failure).__name__
        raise
    finally:
        metadata["completedAt"] = datetime.now(timezone.utc).isoformat()
        write_json(output / "metadata-after.json", metadata)
    print(json.dumps({"passed": True, "scope": metadata["scope"], "benchmarkRecords": 16,
                      "sourceCommit": args.source_commit, "resultSha256": metadata["resultSha256"]}))


if __name__ == "__main__":
    main()
