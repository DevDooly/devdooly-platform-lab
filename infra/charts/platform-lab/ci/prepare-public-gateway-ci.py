"""Prepare public, pinned Linux Helm inputs; never access or change a cluster."""
from pathlib import Path
import argparse, hashlib, json, os, re, shutil, subprocess, sys, tarfile, time
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[4]
MAIN = '13447fa88987050f64e47c01684ecb9c233b34fb'
MANIFEST_SHA = '4f385f7011eee90b62a66976f20bb46225a21dc95956867b504d228faf9bf282'
ARCHIVE_SHA = '86584a54def73570558f66f5111cc53dfed56689637ae32c1201205d494f54fb'
URL = 'https://get.helm.sh/helm-v4.3.0-linux-amd64.tar.gz'
BASELINE_SHA = '1862ec4a796a4ec860a78e84c35bb8ebf2db483ffe432974cd62ee88a0173a32'
parser = argparse.ArgumentParser()
parser.add_argument('--output', required=True)
options = parser.parse_args()
output = Path(options.output).resolve()
runner_temp = Path(os.environ['RUNNER_TEMP']).resolve()
assert sys.platform == 'linux'
assert output != runner_temp and output.is_relative_to(runner_temp)
assert not output.exists() and not output.is_relative_to(ROOT)
output.mkdir()
report = {
    'schemaVersion':1,'scope':'PUBLIC_PINNED_LINUX_HELM_CI_INPUT_PREPARATION',
    'passed':False,'phase':'SOURCE_PINS','failureCode':'NONE',
    'helmTemplateInvocations':0,'downloadRequests':0,'sourceFilesCopied':0,
    'clusterAccessRequested':False,'appliedToCluster':False,
    'dependencyUpdateRequested':False,'rawStderrPersisted':False,
}
sha = lambda data: hashlib.sha256(data).hexdigest()

def write_new(file, data):
    file.parent.mkdir(parents=True,exist_ok=True)
    with file.open('xb') as stream: stream.write(data)

def write_json(file, value):
    write_new(file,(json.dumps(value,indent=2,sort_keys=True)+'\n').encode())

try:
    lock = json.loads((ROOT/'infra/platform/versions.lock.json').read_bytes())
    assert lock['helm']['version'] == 'v4.3.0'
    assert lock['helm']['linuxAmd64'] == {'url':URL,'sha256':ARCHIVE_SHA}
    manifest_bytes = (ROOT/'infra/charts/platform-lab/ci/public-gateway-main-k-source.json').read_bytes()
    assert sha(manifest_bytes) == MANIFEST_SHA
    manifest = json.loads(manifest_bytes)
    assert manifest['mainCommit'] == MAIN and len(manifest['files']) == 23
    git = shutil.which('git')
    assert git is not None
    source_records = []
    workspace = output/'baseline-source'
    git_env = {key:os.environ[key] for key in ('HOME','USERPROFILE','SystemRoot','WINDIR') if key in os.environ}
    git_env.update(GIT_CONFIG_NOSYSTEM='1',GIT_CONFIG_GLOBAL='/dev/null',GIT_TERMINAL_PROMPT='0')
    for item in manifest['files']:
        name = item['path']
        parts = Path(name).parts
        assert not Path(name).is_absolute() and '..' not in parts
        assert name.startswith(('infra/charts/platform-lab/','gitops/bootstrap/','gitops/environments/home-lab/'))
        assert all(not part.startswith('.') or part == '.helmignore' for part in parts)
        result = subprocess.run([git,'--no-optional-locks','cat-file','blob',MAIN+':'+name],
                                cwd=ROOT,env=git_env,capture_output=True,timeout=10,check=False)
        assert result.returncode == 0 and not result.stderr
        assert len(result.stdout) <= 524288 and len(result.stdout) == item['bytes']
        assert sha(result.stdout) == item['sha256']
        write_new(workspace/name,result.stdout)
        source_records.append({'path':name,'bytes':len(result.stdout),'sha256':sha(result.stdout)})
    assert sum(item['bytes'] for item in source_records) <= 2*1024*1024
    report['sourceFilesCopied'] = len(source_records)
    report['phase'] = 'PINNED_TOOL_DOWNLOAD'
    archive = output/'helm-linux-amd64.tar.gz'
    started = time.monotonic()
    report['downloadRequests'] = 1
    total = 0
    with urlopen(Request(URL,headers={'User-Agent':'platform-lab-public-helm-ci'}),timeout=30) as response, archive.open('xb') as stream:
        assert response.status == 200 and response.geturl() == URL
        while True:
            chunk = response.read(128*1024)
            if not chunk: break
            total += len(chunk)
            assert total <= 32*1024*1024 and time.monotonic()-started <= 60
            stream.write(chunk)
    assert sha(archive.read_bytes()) == ARCHIVE_SHA
    report['downloadBytes'] = total
    report['helmArchiveSha256'] = ARCHIVE_SHA
    report['phase'] = 'PINNED_TOOL_MEMBER'
    with tarfile.open(archive,'r:gz') as package:
        members = package.getmembers()
        assert len(members) <= 16
        selected = [member for member in members if member.name == 'linux-amd64/helm']
        assert len(selected) == 1 and selected[0].isfile()
        assert 0 < selected[0].size <= 80*1024*1024
        with package.extractfile(selected[0]) as stream:
            binary_bytes = stream.read(80*1024*1024+1)
        assert len(binary_bytes) == selected[0].size
    binary = output/'helm'
    write_new(binary,binary_bytes)
    binary.chmod(0o755)
    binary_sha = sha(binary_bytes)
    report['helmExecutableSha256'] = binary_sha
    report['phase'] = 'MAIN_K_OFFLINE_TEMPLATE'
    home = output/'helm-home'
    for name in ('cache','config','data','plugins','tmp'): (home/name).mkdir(parents=True)
    write_new(home/'config/repositories.yaml',b'apiVersion: v1\nrepositories: []\n')
    write_new(home/'config/registry.json',b'{}\n')
    env = {key:os.environ[key] for key in ('HOME','USERPROFILE','SystemRoot','WINDIR') if key in os.environ}
    env.update(HELM_CACHE_HOME=str(home/'cache'),HELM_CONFIG_HOME=str(home/'config'),
               HELM_DATA_HOME=str(home/'data'),HELM_PLUGINS=str(home/'plugins'),
               HELM_REPOSITORY_CONFIG=str(home/'config/repositories.yaml'),
               HELM_REPOSITORY_CACHE=str(home/'cache/repository'),
               HELM_REGISTRY_CONFIG=str(home/'config/registry.json'),
               KUBECONFIG=str(home/'no-cluster-config'),TMP=str(home/'tmp'),
               TEMP=str(home/'tmp'),TMPDIR=str(home/'tmp'))
    command = [str(binary),'template','lab',str(workspace/'infra/charts/platform-lab'),
               '--namespace','platform-lab','--kube-version','1.36.5',
               '--values',str(workspace/'gitops/environments/home-lab/values.yaml'),
               '--values',str(workspace/'gitops/environments/home-lab/runtime.yaml')]
    report['helmTemplateInvocations'] = 1
    result = subprocess.run(command,cwd=workspace,env=env,capture_output=True,timeout=30,check=False)
    report['returnCode'] = result.returncode
    report['stderrBytesDiscarded'] = len(result.stderr)
    assert result.returncode == 0 and not result.stderr and len(result.stdout) == 25810
    assert sha(result.stdout) == BASELINE_SHA
    assert len(re.findall(rb'^kind: [A-Za-z0-9]+\r?$',result.stdout,re.M)) == 12
    source_unchanged = all(sha((workspace/item['path']).read_bytes()) == item['sha256'] for item in source_records)
    assert source_unchanged and sha(binary.read_bytes()) == binary_sha
    write_new(output/'baseline.yaml',result.stdout)
    write_json(output/'baseline-receipt.json',{
        'schemaVersion':1,'scope':'PINNED_MAIN_K_LINUX_OFFLINE_BASELINE',
        'passed':True,'mainCommit':MAIN,'sourceManifestSha256':MANIFEST_SHA,
        'namespaceInput':'platform-lab','releaseName':'lab','kubeVersionInput':'1.36.5',
        'objectCount':12,'renderBytes':25810,'renderSha256':BASELINE_SHA,
        'helmArchiveSha256':ARCHIVE_SHA,'helmExecutableSha256':binary_sha,
        'returnCode':0,'stderrBytesDiscarded':0,'sourceBytesUnchanged':True,
        'clusterAccessRequested':False,'appliedToCluster':False,
    })
    report.update(passed=True,phase='COMPLETE',baselineRenderSha256=BASELINE_SHA,
                  sourceBytesUnchanged=source_unchanged,helmExecutableUnchanged=True)
except Exception:
    # Only the finite phase/code is emitted. No command output or exception paths.
    report['failureCode'] = 'PUBLIC_INPUT_PREPARATION_FAILED'
finally:
    write_json(output/'preparation-public-result.json',report)
    print(json.dumps(report,sort_keys=True))
if not report['passed']: raise SystemExit(1)
