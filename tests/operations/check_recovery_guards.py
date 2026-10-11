"""Offline guard regressions; no Kubernetes command or server access is made."""
from pathlib import Path
import copy
import importlib.util
import json
import subprocess
import sys
import tempfile

stage = Path(__file__).resolve().parents[2] / 'infra/scripts'


def load(name):
    spec = importlib.util.spec_from_file_location(name.replace('-', '_'), stage / (name + '.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


backup = load('backup-lab')
restore = load('restore-lab-drill')
passed = []


def rejected(label, callback, error):
    try:
        callback()
    except error:
        passed.append(label)
    else:
        raise AssertionError(label + ': input was incorrectly accepted')


for file in ['backup-lab.py', 'restore-lab-drill.py']:
    result = subprocess.run([sys.executable, str(stage / file), '--help'], capture_output=True, text=True)
    assert result.returncode == 0 and '--backup-root' in result.stdout
    passed.append(file + '-help-needs-no-root-or-cluster')
result = subprocess.run([sys.executable, str(stage / 'restore-lab-drill.py')], capture_output=True, text=True)
assert result.returncode == 2 and not result.stdout
assert '--backup-directory' in result.stderr and '--repository' in result.stderr
passed.append('restore-requires-explicit-backup-and-repository')

for namespace in ['platform-lab', 'jenkins', 'argocd', 'platform-lab-restore-',
                  'platform-lab-restore-../../platform-lab', 'platform-lab-restore-20000101000000-ABCDEF']:
    rejected('reject-trial-' + namespace.replace('/', '_'),
             lambda n=namespace: restore.owner_labels(n), restore.DrillError)
owner = restore.owner_labels('platform-lab-restore-20000101000000-a1b2c3')
restore.require_owner({'metadata': {'labels': owner}}, owner)
passed.append('matching-namespace-purpose-and-trial-id-accepted')
for label, labels in [('missing-both', {}), ('missing-id', {restore.PURPOSE: 'restore-drill'}),
                      ('wrong-purpose', {restore.PURPOSE: 'other', restore.BACKUP_ID: owner[restore.BACKUP_ID]}),
                      ('wrong-id', {restore.PURPOSE: 'restore-drill', restore.BACKUP_ID: 'wrong'})]:
    rejected(label + '-owner-label-rejected',
             lambda labels=labels: restore.require_owner({'metadata': {'labels': labels}}, owner),
             restore.DrillError)

rejected('relative-backup-root-rejected', lambda: backup.checked_path(Path('relative')),
         backup.BackupError)
rejected('filesystem-root-rejected', lambda: backup.checked_path(Path(Path.cwd().anchor)),
         backup.BackupError)
assert not restore.image_digest('mariadb:11.8.9')
passed.append('mutable-image-tag-rejected')
assert restore.image_digest('example.invalid/lab@sha256:' + '0' * 64)
passed.append('immutable-image-digest-accepted')

base = {'observedAt': 'collection-one', 'startedAt': 'stored-start',
        'completedAt': 'stored-end', 'outcomes': [{'status': 'SUCCESS'}]}
later = {**base, 'observedAt': 'collection-two'}
assert restore.stable_detail(base) == restore.stable_detail(later)
passed.append('only-observedAt-is-excluded-from-restart-comparison')
for key in ['startedAt', 'completedAt', 'outcomes']:
    changed = {**base, key: 'changed'}
    assert restore.stable_detail(base) != restore.stable_detail(changed)
    passed.append(key + '-changes-remain-detectable')

pod = {'spec': {'containers': [{'volumeMounts': [{'name': 'data', 'mountPath': '/var/lib/mysql'}]}],
                'volumes': [{'name': 'data', 'persistentVolumeClaim': {'claimName': 'test-claim'}}]}}
assert restore.mounted_claim(pod) == 'test-claim'
passed.append('explicit-database-pvc-mount-accepted')
for field, value in [('hostNetwork', True), ('volumes', [{'name': 'data', 'hostPath': {'path': '/tmp'}}])]:
    changed = copy.deepcopy(pod)
    changed['spec'][field] = value
    rejected('unsafe-db-' + field + '-rejected', lambda changed=changed: restore.mounted_claim(changed),
             restore.DrillError)

with tempfile.TemporaryDirectory(prefix='ddplab-recovery-guards-') as folder:
    root = Path(folder)
    storage = root / 'storage'
    production_path = storage / 'production'
    trial_path = storage / 'trial'
    production_path.mkdir(parents=True)
    trial_path.mkdir()
    ns = 'platform-lab-restore-20000101000000-a1b2c3'
    production_pvc = {'metadata': {'uid': 'production-uid', 'name': 'production-claim'}}
    production_pv = {'metadata': {'name': 'production-volume'}, 'spec': {'hostPath': {'path': str(production_path)}}}
    trial_pvc = {'metadata': {'uid': 'trial-uid', 'name': 'trial-claim'}}
    trial_pv = {'metadata': {'name': 'trial-volume'},
                'spec': {'hostPath': {'path': str(trial_path)},
                         'claimRef': {'namespace': ns, 'name': 'trial-claim', 'uid': 'trial-uid'}}}
    restore.independent_storage(production_pvc, production_pv, trial_pvc, trial_pv, ns, root)
    passed.append('disjoint-owned-pvc-pv-and-local-storage-accepted')
    same_uid = copy.deepcopy(trial_pvc)
    same_uid['metadata']['uid'] = 'production-uid'
    rejected('production-pvc-uid-reuse-rejected',
             lambda: restore.independent_storage(production_pvc, production_pv, same_uid, trial_pv, ns, root),
             restore.DrillError)
    wrong_claim = copy.deepcopy(trial_pv)
    wrong_claim['spec']['claimRef']['uid'] = 'unrelated-uid'
    rejected('pv-claimref-uid-mismatch-rejected',
             lambda: restore.independent_storage(production_pvc, production_pv, trial_pvc, wrong_claim, ns, root),
             restore.DrillError)
    same_path = copy.deepcopy(trial_pv)
    same_path['spec']['hostPath']['path'] = str(production_path)
    rejected('production-mount-path-reuse-rejected',
             lambda: restore.independent_storage(production_pvc, production_pv, trial_pvc, same_path, ns, root),
             restore.DrillError)
    nested_path = production_path / 'nested'
    nested_path.mkdir()
    nested = copy.deepcopy(trial_pv)
    nested['spec']['hostPath']['path'] = str(nested_path)
    rejected('nested-production-mount-path-rejected',
             lambda: restore.independent_storage(production_pvc, production_pv, trial_pvc, nested, ns, root),
             restore.DrillError)
    outside = root / 'outside-storage'
    outside.mkdir()
    outside_pv = copy.deepcopy(trial_pv)
    outside_pv['spec']['hostPath']['path'] = str(outside)
    rejected('mount-outside-lab-storage-rejected',
             lambda: restore.independent_storage(production_pvc, production_pv, trial_pvc, outside_pv, ns, root),
             restore.DrillError)

print(json.dumps({'scope': 'OFFLINE_RECOVERY_CLI_GUARD_CHECKS', 'checksPassed': len(passed),
                  'checks': passed, 'clusterCommandsExecuted': False}, indent=2))
