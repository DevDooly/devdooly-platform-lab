#!/usr/bin/env python3
"""Host capture + outbound Pages dispatch; never restarts any service."""
from __future__ import annotations

import argparse
from datetime import datetime,timezone
import ipaddress
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import sys
import tempfile
import time
from urllib.parse import urlsplit

from pages_uploader import (AutomationError, atomic_private_json, dispatch, load_job_snapshot, load_kafka_snapshot, load_snapshot, path_chain, public_report, regular_private)
from platform_contract import moment

CONFIG_KEYS={'k3s_path','kubeconfig','server','ca_file','collector_path','state_directory',
             'runtime_directory','pages_token_file'}
SAFE_ENV={'PATH':'/usr/sbin:/usr/bin:/sbin:/bin','HOME':'/root','LANG':'C.UTF-8',
          'PYTHONDONTWRITEBYTECODE':'1'}


def root_code(path: Path) -> None:
    try:
        path_chain(path,leaf_kind='file')
    except AutomationError:raise AutomationError('CONFIG_INVALID') from None


def loopback_server(value: str) -> None:
    try:
        url=urlsplit(value)
        if (url.scheme!='https' or url.username is not None or url.password is not None
                or url.path not in {'','/'} or url.query or url.fragment
                or url.port is None or not 1<=url.port<=65535
                or not ipaddress.ip_address(url.hostname).is_loopback):raise ValueError
    except (ValueError,TypeError):raise AutomationError('CONFIG_INVALID') from None


def read_config(path: Path) -> dict:
    regular_private(path,owner_root=True)
    try:
        with path.open('rb') as handle:raw=handle.read(8193)
        config=json.loads(raw)
        if len(raw)>8192 or not isinstance(config,dict) or not CONFIG_KEYS<=set(config)<=CONFIG_KEYS|{'jobs_enabled','kafka_enabled'}:raise ValueError
        if any(not isinstance(value,str) or not value or '\n' in value for value in config.values()):raise ValueError
        if any(config.get(key,'false') not in {'true','false'} for key in ('jobs_enabled','kafka_enabled')):raise ValueError
        loopback_server(config['server'])
        for key in CONFIG_KEYS-{'server'}:
            if not Path(config[key]).is_absolute():raise ValueError
        if Path(config['k3s_path']).name!='k3s':raise ValueError
        for key in ('k3s_path','collector_path'):root_code(Path(config[key]))
        root_code(Path(config['collector_path']).with_name('platform_contract.py'))
        if config.get('jobs_enabled')=='true':
            for name in ('job_collector.py','job_contract.py','pages_uploader.py'):
                root_code(Path(config['collector_path']).with_name(name))
        if config.get('kafka_enabled')=='true':
            for name in ('kafka_collector.py','kafka_contract.py','job_collector.py','job_contract.py','pages_uploader.py'):
                root_code(Path(config['collector_path']).with_name(name))
        regular_private(Path(config['kubeconfig']),owner_root=True)
        # The public CA is still supplied explicitly; no insecure TLS fallback.
        root_code(Path(config['ca_file']))
        return config
    except Exception:raise AutomationError('CONFIG_INVALID') from None


def private_directory(path: Path) -> None:
    path_chain(path,leaf_kind='directory',allow_missing_leaf=True)
    # A missing parent is a configuration error, never recursively created.
    path.mkdir(mode=0o700,exist_ok=True)
    info=path.lstat()
    if not stat.S_ISDIR(info.st_mode):raise AutomationError('PRIVATE_DIRECTORY_INVALID')
    if os.name=='posix' and (info.st_uid!=0 or stat.S_IMODE(info.st_mode)!=0o700):
        raise AutomationError('PRIVATE_DIRECTORY_INVALID')


class CycleLock:
    def __init__(self,path):self.path=path;self.descriptor=None
    def __enter__(self):
        if os.name!='posix':raise AutomationError('PLATFORM_UNSUPPORTED')
        path_chain(self.path,leaf_kind='file',allow_missing_leaf=True)
        import fcntl
        self.descriptor=os.open(self.path,os.O_RDWR|os.O_CREAT|getattr(os,'O_NOFOLLOW',0),0o600)
        info=os.fstat(self.descriptor)
        if not stat.S_ISREG(info.st_mode) or info.st_nlink!=1 or info.st_uid!=0 or stat.S_IMODE(info.st_mode)!=0o600:
            os.close(self.descriptor);self.descriptor=None
            raise AutomationError('LOCK_INVALID')
        try:fcntl.flock(self.descriptor,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:
            os.close(self.descriptor);self.descriptor=None
            raise AutomationError('CYCLE_ALREADY_RUNNING') from None
        return self
    def __exit__(self,*unused):
        if self.descriptor is not None:os.close(self.descriptor)


class CycleDeadline:
    """Host-only 145s alarm backstop, independent of per-operation socket timeouts."""
    def __init__(self,seconds):self.seconds=seconds;self.signal=None;self.previous=None
    def __enter__(self):
        if os.name!='posix':return self  # Offline tests; host main rejects non-POSIX.
        import signal
        if signal.getitimer(signal.ITIMER_REAL)!=(0.0,0.0):raise AutomationError('PRECONDITION_FAILED')
        self.signal=signal;self.previous=signal.getsignal(signal.SIGALRM)
        def expired(unused_signal,unused_frame):raise subprocess.TimeoutExpired('host-cycle',self.seconds)
        signal.signal(signal.SIGALRM,expired)
        try:signal.setitimer(signal.ITIMER_REAL,self.seconds)
        except BaseException:
            signal.signal(signal.SIGALRM,self.previous);self.signal=None
            raise
        return self
    def __exit__(self,*unused):
        if self.signal is not None:
            self.signal.setitimer(self.signal.ITIMER_REAL,0)
            self.signal.signal(self.signal.SIGALRM,self.previous)


def run_cycle(config: dict, *, runner=subprocess.run, uploader=dispatch, lock_class=CycleLock,
              deadline_class=CycleDeadline, monotonic=time.monotonic) -> dict:
    state=Path(config['state_directory']);runtime=Path(config['runtime_directory'])
    with deadline_class(145):
        cutoff=monotonic()+145
        private_directory(state);private_directory(runtime)
        with lock_class(state/'cycle.lock'):
            def remaining(maximum,reserve=15):
                value=cutoff-monotonic()-reserve
                if value<=0:raise subprocess.TimeoutExpired('host-cycle',145)
                return min(maximum,value)
            started=datetime.now(timezone.utc)
            started_precise=(started.replace(microsecond=0),started.microsecond*1000)
            token_path=None
            try:
                issued=runner([config['k3s_path'],'kubectl','--kubeconfig',config['kubeconfig'],
                    '-n','platform-lab','create','token','platform-public-observer','--duration=10m'],
                    stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,timeout=remaining(15),check=False,env=SAFE_ENV)
                if issued.returncode!=0 or len(issued.stdout)>16384:
                    return public_report('SA_TOKEN_UNAVAILABLE')
                token=issued.stdout.strip()
                if not re.fullmatch(rb'[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+',token):
                    return public_report('SA_TOKEN_UNAVAILABLE')
                descriptor,filename=tempfile.mkstemp(prefix='sa-',suffix='.token',dir=runtime)
                token_path=Path(filename);os.chmod(token_path,0o600)
                with os.fdopen(descriptor,'wb') as handle:handle.write(token);handle.flush();os.fsync(handle.fileno())
                output=state/'platform-observation.json'
                captured=runner([sys.executable,'-B',config['collector_path'],
                    '--server',config['server'],'--ca-file',config['ca_file'],
                    '--token-file',str(token_path),'--output',str(output),'--deadline-seconds','60'],
                    stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=remaining(80),check=False,env=SAFE_ENV)
                if captured.returncode not in {0,1}:return public_report('CAPTURE_FAILED')
                snapshot=load_snapshot(output,datetime.now(timezone.utc))
                completed=moment(snapshot['latestAttempt']['attemptedAt'],datetime.now(timezone.utc))
                if completed<started_precise:return public_report('CAPTURE_FAILED')
                jobs=None
                if config.get('jobs_enabled')=='true':
                    job_output=state/'jobs-observation.json'
                    code='JOB_CAPTURE_FAILED'
                    try:
                        job_capture=runner([sys.executable,'-B',str(Path(config['collector_path']).with_name('job_collector.py')),
                            '--server',config['server'],'--ca-file',config['ca_file'],
                            '--token-file',str(token_path),'--output',str(job_output),'--deadline-seconds','15'],
                            stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=remaining(20),check=False,env=SAFE_ENV)
                        if job_capture.returncode==0:
                            candidate=load_job_snapshot(job_output,datetime.now(timezone.utc))
                            captured_at=moment(candidate['capturedAt'],datetime.now(timezone.utc))
                            if captured_at>=started_precise:jobs=candidate;code='NONE'
                    except Exception:pass
                    # Failure does not rewrite the last job record or block a valid
                    # platform envelope. Missing input makes Pages retain last-good.
                    atomic_private_json(state/'jobs-capture.json',{'attemptedAt':datetime.now(timezone.utc).isoformat().replace('+00:00','Z'),
                        'status':'success' if jobs is not None else 'failure','errorCode':code,
                        'capturedAt':jobs['capturedAt'] if jobs is not None else None})
                kafka=None
                if config.get('kafka_enabled')=='true':
                    kafka_output=state/'kafka-observation.json';code='KAFKA_CAPTURE_FAILED'
                    try:
                        # Optional work must leave the full dispatch reserve untouched.
                        if cutoff-monotonic()>=27:
                            captured_kafka=runner([sys.executable,'-B',str(Path(config['collector_path']).with_name('kafka_collector.py')),
                                '--server',config['server'],'--ca-file',config['ca_file'],
                                '--token-file',str(token_path),'--output',str(kafka_output),'--deadline-seconds','10'],
                                stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=remaining(12),check=False,env=SAFE_ENV)
                            if captured_kafka.returncode==0:
                                candidate=load_kafka_snapshot(kafka_output,datetime.now(timezone.utc))
                                if moment(candidate['captureStartedAt'],datetime.now(timezone.utc))>=started_precise:
                                    kafka=candidate;code='NONE'
                    except Exception:pass
                    try:
                        atomic_private_json(state/'kafka-capture.json',{'attemptedAt':datetime.now(timezone.utc).isoformat().replace('+00:00','Z'),
                            'status':'success' if kafka is not None else 'failure','errorCode':code,
                            'capturedAt':kafka['capturedAt'] if kafka is not None else None})
                    except Exception:pass  # Optional diagnostics cannot block the existing publication.
                # A collection-failure envelope is publishable and retains lastSuccess.
                remaining(15,reserve=0)
                options={}
                if jobs is not None:options['job_snapshot']=jobs
                if kafka is not None:options['kafka_snapshot']=kafka
                if uploader is dispatch:options['deadline']=cutoff
                return uploader(snapshot,Path(config['pages_token_file']),state/'pages-dispatch.json',**options)
            except subprocess.TimeoutExpired:return public_report('CAPTURE_TIMEOUT')
            except AutomationError as error:
                if str(error)=='CAPTURE_TIMEOUT':return public_report('CAPTURE_TIMEOUT')
                raise
            finally:
                if token_path is not None:
                    try:token_path.unlink()
                    except OSError:pass


def main(argv=None) -> int:
    parser=argparse.ArgumentParser(description='Root-owned host capture; no service restart or inbound listener.')
    parser.add_argument('--config',required=True,type=Path)
    args=parser.parse_args(argv)
    try:
        if os.name!='posix' or os.geteuid()!=0:raise AutomationError('ROOT_REQUIRED')
        config=read_config(args.config)
        report=run_cycle(config)
    except subprocess.TimeoutExpired:report=public_report('CAPTURE_TIMEOUT')
    except AutomationError as error:
        allowed={'CYCLE_ALREADY_RUNNING','ROOT_REQUIRED','SNAPSHOT_INVALID','PAGES_CREDENTIAL_UNAVAILABLE'}
        report=public_report(str(error) if str(error) in allowed else 'PRECONDITION_FAILED')
    except Exception:report=public_report('PRECONDITION_FAILED')
    print(json.dumps(report))
    return 0 if report['attemptStatus']=='DISPATCHED' else 1


if __name__=='__main__':raise SystemExit(main())
