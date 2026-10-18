"""Source binding and finite projection for one hosted reproduction; never runs Java itself."""
import argparse
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import re
import subprocess

ROOT = Path(__file__).resolve().parents[3]
MODULE = ROOT / 'examples/java-window-analysis'
PIN_FILE = Path(__file__).with_name('source-pins.json')
PIN_SHA256 = '3975bea55b2b03c0ed3c2b9c87ea781c9c7de527dc9df122a3b1cb5fe0b3d8f0'
FIXTURE_HEADER = 'profile\tsize\tseed\trawSha256\tnormalizedSha256\tresultSha256\tcoveredNanos\tpeakConcurrentSessions'

def need(value):
    if not value: raise ValueError('HOSTED_JMH_UNVERIFIED')

def sha(raw): return hashlib.sha256(raw).hexdigest()

def unique(pairs):
    result = {}
    for key, value in pairs:
        need(key not in result); result[key] = value
    return result

def read(path, maximum):
    need(path.is_file() and not path.is_symlink() and 0 < path.stat().st_size <= maximum)
    raw = path.read_bytes(); need(len(raw) <= maximum); return raw

def decoded(path):
    return json.loads(read(path, 1048576).decode('utf-8'), object_pairs_hook=unique)

def write_new(path, value):
    raw = (json.dumps(value, sort_keys=True, indent=2, allow_nan=False) + '\n').encode()
    need(len(raw) <= 131072)
    with path.open('xb') as stream: stream.write(raw)

def sources(expected):
    need(re.fullmatch('[0-9a-f]{40}', expected) is not None)
    process = subprocess.run(['git','rev-parse','HEAD'], cwd=ROOT, stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=10)
    need(process.returncode == 0 and process.stdout.strip().decode('ascii') == expected)
    raw = read(PIN_FILE, 32768); need(sha(raw) == PIN_SHA256)
    pin = json.loads(raw.decode(), object_pairs_hook=unique)
    need(pin['schemaVersion'] == 1 and len(pin['files']) == 16)
    # Reject additional or linked source before Maven can compile anything.
    need(MODULE.is_dir() and not MODULE.is_symlink())
    names = []
    for folder, directories, files in os.walk(MODULE, followlinks=False):
        need(all(not (Path(folder)/name).is_symlink() for name in directories + files))
        directories[:] = [name for name in directories if name != '__pycache__'
            and not (Path(folder) == MODULE and name in {'target','results','.git'})]
        for name in files:
            path = Path(folder)/name
            names.append(path.relative_to(MODULE).as_posix()); need(len(names) <= 64)
    need(sorted(names) == [item['path'] for item in pin['files']])
    actual = []
    for item in pin['files']:
        relative = Path(item['path']); need(not relative.is_absolute() and '..' not in relative.parts)
        data = read(MODULE / relative, item['size'])
        need(len(data) == item['size'] and sha(data) == item['sha256'])
        actual.append({'path':relative.as_posix(),'size':len(data),'sha256':sha(data)})
    return actual

def fixture_valid(raw):
    lines = raw.decode('ascii').splitlines(); need(len(lines) == 9 and lines[0] == FIXTURE_HEADER)
    seen = set()
    for line in lines[1:]:
        columns = line.split('\t'); need(len(columns) == 8)
        profile, size_text, seed_text, *remaining = columns
        need(profile in {'sparse','nested'} and size_text in {'128','512','2048','4096'})
        size, seed = int(size_text), int(seed_text)
        need(seed == 20261015 + size + (1000000 if profile == 'nested' else 0))
        need(all(re.fullmatch('[a-f0-9]{64}', value) is not None for value in remaining[:3]))
        need(int(remaining[3]) == size * (11000000 if profile == 'sparse' else 1000000))
        need(int(remaining[4]) == (1 if profile == 'sparse' else size))
        need((profile,size) not in seen); seen.add((profile,size))
    need(len(seen) == 8)

def finite(value, positive=False):
    need(type(value) in (int,float) and math.isfinite(value) and (value > 0 if positive else value >= 0))
    return value

def load_runner():
    spec = importlib.util.spec_from_file_location('reviewed_window_jmh', MODULE / 'scripts/run_jmh.py')
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module); return module

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('mode', choices=('preflight','finalize'))
    parser.add_argument('--source-sha', required=True)
    parser.add_argument('--result-dir', required=True, type=Path)
    parser.add_argument('--public-dir', required=True, type=Path)
    args = parser.parse_args()
    manifest = sources(args.source_sha)
    result, public = args.result_dir.resolve(), args.public_dir.resolve()
    need(not result.is_relative_to(MODULE) and not public.is_relative_to(MODULE) and result != public)
    if args.mode == 'preflight':
        need(not result.exists() and not public.exists())
        public.mkdir(mode=0o700, parents=False, exist_ok=False)
        write_new(public / 'preflight.json', {'sourceCommit':args.source_sha,'sourceFiles':manifest,
            'startedAt':datetime.now(timezone.utc).isoformat(),'measurementRequested':False})
        return 0
    preflight = decoded(public / 'preflight.json')
    need(preflight['sourceCommit'] == args.source_sha and preflight['sourceFiles'] == manifest)
    summary = {'schemaVersion':1,'scope':'INDEPENDENT_SYNTHETIC_GITHUB_HOSTED_LINUX_JAVA21',
        'status':'FAILED_OR_PARTIAL','sourceCommit':args.source_sha,'sourceFiles':manifest,
        'measuredRecords':None,'forksPerRecord':None,'samplesPerFork':None,'measurements':[],
        'sourceAndJarUnchanged':False,'fixtureManifestSha256':None,'jarSha256':None,'jarBytes':None,
        'completedAt':datetime.now(timezone.utc).isoformat(),'historicalWindowsRecordReplaced':False,
        'runnerLabel':'ubuntu-24.04','javaVersion':None,'vmVersion':None,
        'parentCpuAffinityRequestedCount':1,'forkCpuAffinityIndependentlyMeasured':False,
        'cpuQuotaEnforced':False,'exclusivePhysicalCoreProvided':False,'heapMiBPerFork':256,
        'rssMemoryLimitEnforced':False,'productionOrMiniPcChanged':False,'companyDataUsed':False,
        'operationalSlaProven':False,'humanReviewCompleted':False}
    try:
        before, after = decoded(result/'metadata-before.json'), decoded(result/'metadata-after.json')
        need(before['sourceCommit'] == after['sourceCommit'] == args.source_sha)
        need(before['sourceFiles'] == after['sourceFiles'] == manifest and after['passed'] is True)
        jar = read(MODULE/'target/benchmarks.jar', 8388608)
        need(before['jarSha256'] == after['jarSha256'] == sha(jar)
            and type(before['jarBytes']) is int and before['jarBytes'] == after['jarBytes'] == len(jar))
        need(after['productionEtlChanged'] is False and after['companyDataUsed'] is False
            and after['cpuMemoryIsolationProvidedByThisScript'] is False)
        fixture = read(result/'fixtures.tsv', 65536); fixture_valid(fixture)
        need(after['fixtureManifestSha256'] == sha(fixture))
        raw = read(result/'jmh.json', 1048576); need(after['resultSha256'] == sha(raw))
        rows = json.loads(raw.decode('utf-8'), object_pairs_hook=unique)
        load_runner().validate_results(rows)
        version, vm_version = rows[0].get('jdkVersion'), rows[0].get('vmVersion')
        need(type(version) is str and re.fullmatch(r'21[.0-9A-Za-z+_-]{0,80}', version))
        need(type(vm_version) is str and re.fullmatch(r'[0-9A-Za-z._+() -]{1,100}', vm_version))
        need(all(row.get('jdkVersion') == version and row.get('vmVersion') == vm_version for row in rows))
        projected = []
        for row in rows:
            metric, allocation = row['primaryMetric'], row['secondaryMetrics']['gc.alloc.rate.norm']
            error = metric.get('scoreError')
            error = finite(error) if type(error) in (int,float) and math.isfinite(error) else None
            projected.append({'method':row['benchmark'].rsplit('.',1)[1],'profile':row['params']['profile'],
                'size':int(row['params']['size']),'scoreUsPerOp':finite(metric['score'],True),
                'scoreErrorUsPerOp':error,'rawDataUsPerOp':[[finite(v,True) for v in fork] for fork in metric['rawData']],
                'allocationBytesPerOp':finite(allocation['score'])})
        need(sources(args.source_sha) == manifest)
        with (public/'fixtures.tsv').open('xb') as stream: stream.write(fixture)
        summary.update(status='VERIFIED_HOSTED_REPRODUCTION',measuredRecords=16,forksPerRecord=3,
            samplesPerFork=5,measurements=projected,sourceAndJarUnchanged=True,
            fixtureManifestSha256=sha(fixture),jarSha256=sha(jar),jarBytes=len(jar),
            javaVersion=version,vmVersion=vm_version)
    except Exception:
        pass  # No raw metadata, exception text, command, host identity or logs enter public output.
    write_new(public/'public-summary.json',summary)
    return 0 if summary['status'] == 'VERIFIED_HOSTED_REPRODUCTION' else 1

if __name__ == '__main__': raise SystemExit(main())
