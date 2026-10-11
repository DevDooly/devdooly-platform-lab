"""Read-only Ubuntu inventory. Store stdout outside version control."""
import datetime
import json
import os
from pathlib import Path
import shutil
import subprocess

def command(args):
    if not shutil.which(args[0]):
        return {'available': False}
    try:
        result = subprocess.run(args, capture_output=True, text=True, timeout=15)
        return {'exitCode': result.returncode, 'stdout': result.stdout.strip(), 'stderr': result.stderr.strip()}
    except subprocess.TimeoutExpired:
        return {'error': 'timeout'}

disk = shutil.disk_usage(str(Path.home()))
report = {
    'observedAt': datetime.datetime.now(datetime.timezone.utc).isoformat(),
    'uid': os.getuid() if hasattr(os, 'getuid') else None,
    'osRelease': Path('/etc/os-release').read_text() if Path('/etc/os-release').exists() else 'not Linux',
    'cpu': command(['lscpu']),
    'memory': command(['free', '-h']),
    'filesystems': command(['df', '-hT']),
    'blockDevices': command(['lsblk', '-o', 'NAME,SIZE,TYPE,FSTYPE,MOUNTPOINTS']),
    'diskBytesAtHome': {'total': disk.total, 'used': disk.used, 'free': disk.free},
    'services': command(['systemctl', 'list-units', '--type=service', '--state=running', '--no-pager']),
    'listeningTcp': command(['ss', '-lnt']),
    'containers': command(['docker', 'ps', '--format', '{{.Names}} | {{.Image}} | {{.Ports}} | {{.Status}}']),
    'sudoWithoutPrompt': command(['sudo', '-n', 'true']),
    'k3sVersion': command(['k3s', '--version']),
}
print(json.dumps(report, ensure_ascii=False, indent=2))
