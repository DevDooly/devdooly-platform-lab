#!/usr/bin/env python3
"""Dispatch only the fixed Pages workflow, once per validated snapshot intent."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import ssl
import stat
import sys
import tempfile
from urllib.error import HTTPError, URLError
from urllib.request import HTTPRedirectHandler, HTTPSHandler, ProxyHandler, Request, build_opener

from platform_contract import SAFE_INTEGER, validate_snapshot
from job_contract import MAX_JOB_SNAPSHOT, validate_job_snapshot

REPOSITORY = 'DevDooly/devdooly-platform-lab'
ENDPOINT = 'https://api.github.com/repos/' + REPOSITORY + '/actions/workflows/pages.yml/dispatches'
API_VERSION = '2026-03-10'
MAX_SNAPSHOT = 16 * 1024
MAX_RESPONSE = 64 * 1024


class AutomationError(Exception):
    """Only fixed codes may leave this module."""


def public_report(status: str, run_id: int | None = None) -> dict:
    return {'attemptStatus':status,'runId':run_id,
            'runUrl':f'https://github.com/{REPOSITORY}/actions/runs/{run_id}' if run_id else None}


def root_owned(info) -> bool:
    return os.name!='posix' or info.st_uid==0


def path_chain(path: Path, *, owner_uids=frozenset({0}), leaf_kind=None,
               allow_missing_leaf: bool = False) -> None:
    """Reject replaceable ancestors before privileged reads, writes or execution.

    Root-managed paths may only descend through root-owned, non-writable
    directories. The credential is the sole exception: its owner may also own
    ancestors. Symlinks are rejected at every component on every platform.
    """
    if not path.is_absolute():raise AutomationError('PATH_UNTRUSTED')
    parts=list(reversed(path.parents))+[path]
    try:
        for index,component in enumerate(parts):
            final=index==len(parts)-1
            try:info=component.lstat()
            except FileNotFoundError:
                if final and allow_missing_leaf:return
                raise
            if stat.S_ISLNK(info.st_mode):raise AutomationError('PATH_UNTRUSTED')
            if not final and not stat.S_ISDIR(info.st_mode):raise AutomationError('PATH_UNTRUSTED')
            if final and leaf_kind=='directory' and not stat.S_ISDIR(info.st_mode):raise AutomationError('PATH_UNTRUSTED')
            if final and leaf_kind=='file' and not stat.S_ISREG(info.st_mode):raise AutomationError('PATH_UNTRUSTED')
            if os.name=='posix' and (info.st_uid not in owner_uids or stat.S_IMODE(info.st_mode)&0o022):
                raise AutomationError('PATH_UNTRUSTED')
    except OSError:raise AutomationError('PATH_UNTRUSTED') from None


def regular_private(path: Path, *, owner_root: bool = True) -> None:
    try:
        info=path.lstat()
        path_chain(path,owner_uids={0} if owner_root else {0,info.st_uid},leaf_kind='file')
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
            raise AutomationError('PRIVATE_FILE_INVALID')
        if os.name == 'posix' and (stat.S_IMODE(info.st_mode) != 0o600 or (owner_root and not root_owned(info))):
            raise AutomationError('PRIVATE_FILE_INVALID')
    except OSError:
        raise AutomationError('PRIVATE_FILE_UNAVAILABLE') from None


def credential_bytes(path: Path, owner_uid: int) -> bytes:
    """Read through held directory descriptors; user ancestors cannot be swapped.

    This POSIX path is used by the root-only host cycle. The Windows branch is
    exclusively for offline tests; the host cycle rejects Windows execution.
    """
    if os.name!='posix':
        with path.open('rb') as handle:return handle.read(257)
    descriptor=None
    allowed={0,owner_uid}
    try:
        directory_flags=os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW|os.O_CLOEXEC
        descriptor=os.open(path.anchor,directory_flags)
        for component in path.parts[1:-1]:
            info=os.fstat(descriptor)
            if not stat.S_ISDIR(info.st_mode) or info.st_uid not in allowed or stat.S_IMODE(info.st_mode)&0o022:
                raise AutomationError('PAGES_CREDENTIAL_UNAVAILABLE')
            following=os.open(component,directory_flags,dir_fd=descriptor)
            os.close(descriptor);descriptor=following
        info=os.fstat(descriptor)
        if not stat.S_ISDIR(info.st_mode) or info.st_uid not in allowed or stat.S_IMODE(info.st_mode)&0o022:
            raise AutomationError('PAGES_CREDENTIAL_UNAVAILABLE')
        following=os.open(path.name,os.O_RDONLY|os.O_NOFOLLOW|os.O_CLOEXEC,dir_fd=descriptor)
        os.close(descriptor);descriptor=following
        info=os.fstat(descriptor)
        if (not stat.S_ISREG(info.st_mode) or info.st_nlink!=1 or info.st_uid!=owner_uid
                or stat.S_IMODE(info.st_mode)!=0o600):
            raise AutomationError('PAGES_CREDENTIAL_UNAVAILABLE')
        return os.read(descriptor,257)
    finally:
        if descriptor is not None:os.close(descriptor)


def read_pages_token(path: Path) -> str:
    # A separate exact credential path prevents accidental status-PAT reuse.
    if (not path.is_absolute() or path.name != 'github-pages.token'
            or path.parent.name != 'devdooly-platform-lab' or path.parent.parent.name != '.config'):
        raise AutomationError('PAGES_CREDENTIAL_UNAVAILABLE')
    regular_private(path,owner_root=False)
    try:
        data=credential_bytes(path,path.lstat().st_uid)
        token=data.decode('ascii').strip()
        if len(data)>256 or not re.fullmatch(r'github_pat_[A-Za-z0-9_]{20,240}',token):
            raise ValueError
        return token
    except (OSError, ValueError, UnicodeError):
        raise AutomationError('PAGES_CREDENTIAL_UNAVAILABLE') from None


def load_snapshot(path: Path, now: datetime) -> dict:
    regular_private(path)
    try:
        with path.open('rb') as handle: data=handle.read(MAX_SNAPSHOT+1)
        if len(data)>MAX_SNAPSHOT:raise ValueError
        return validate_snapshot(json.loads(data),now)
    except Exception:
        raise AutomationError('SNAPSHOT_INVALID') from None


def load_job_snapshot(path: Path, now: datetime) -> dict:
    regular_private(path)
    try:
        with path.open('rb') as handle: data=handle.read(MAX_JOB_SNAPSHOT+1)
        if len(data)>MAX_JOB_SNAPSHOT:raise ValueError
        return validate_job_snapshot(json.loads(data,object_pairs_hook=unique_object),now)
    except Exception:
        raise AutomationError('JOB_SNAPSHOT_INVALID') from None


def unique_object(pairs):
    result={}
    for key,value in pairs:
        if key in result:raise AutomationError('JOB_SNAPSHOT_INVALID')
        result[key]=value
    return result


def atomic_private_json(path: Path, value: dict) -> None:
    path_chain(path,leaf_kind='file',allow_missing_leaf=True)
    if path.exists() or path.is_symlink():regular_private(path)
    descriptor, temporary=tempfile.mkstemp(prefix='.'+path.name+'.',dir=path.parent)
    try:
        os.chmod(temporary,0o600)
        with os.fdopen(descriptor,'w',encoding='utf-8',newline='\n') as handle:
            json.dump(value,handle,sort_keys=True,allow_nan=False)
            handle.write('\n');handle.flush();os.fsync(handle.fileno())
        os.replace(temporary,path)
        if os.name=='posix':
            descriptor=os.open(path.parent,os.O_RDONLY|getattr(os,'O_DIRECTORY',0))
            try:os.fsync(descriptor)
            finally:os.close(descriptor)
    finally:
        if os.path.exists(temporary):os.unlink(temporary)


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self,request,fp,code,message,headers,newurl):return None


def send_once(request: Request) -> tuple[int, bytes]:
    opener=build_opener(ProxyHandler({}),NoRedirect(),HTTPSHandler(context=ssl.create_default_context()))
    try:
        with opener.open(request,timeout=15) as response:
            code=response.status;body=response.read(MAX_RESPONSE+1)
        if len(body)>MAX_RESPONSE:raise AutomationError('DISPATCH_AMBIGUOUS')
        return code,body
    except HTTPError as error:
        # No HTTP error body is read, printed or persisted.
        raise AutomationError('DISPATCH_AMBIGUOUS' if error.code>=500 else 'DISPATCH_REJECTED') from None
    except (URLError, TimeoutError, OSError):
        raise AutomationError('DISPATCH_AMBIGUOUS') from None


class DispatchLock:
    """OS lock releases on process death; the inode is never unlinked."""
    def __init__(self,path):self.path=path;self.descriptor=None
    def __enter__(self):
        path_chain(self.path,leaf_kind='file',allow_missing_leaf=True)
        self.descriptor=os.open(self.path,os.O_RDWR|os.O_CREAT|getattr(os,'O_NOFOLLOW',0),0o600)
        info=os.fstat(self.descriptor)
        if not stat.S_ISREG(info.st_mode) or info.st_nlink!=1:
            os.close(self.descriptor);self.descriptor=None
            raise AutomationError('DISPATCH_BUSY')
        if os.name=='posix' and (not root_owned(info) or stat.S_IMODE(info.st_mode)!=0o600):
            os.close(self.descriptor);self.descriptor=None
            raise AutomationError('DISPATCH_BUSY')
        try:
            if os.name=='posix':
                import fcntl
                fcntl.flock(self.descriptor,fcntl.LOCK_EX|fcntl.LOCK_NB)
            else:
                import msvcrt
                if info.st_size==0:os.write(self.descriptor,b'\0')
                os.lseek(self.descriptor,0,os.SEEK_SET)
                msvcrt.locking(self.descriptor,msvcrt.LK_NBLCK,1)
        except OSError:
            os.close(self.descriptor);self.descriptor=None
            raise AutomationError('DISPATCH_BUSY') from None
        return self
    def __exit__(self,*unused):
        if self.descriptor is not None:os.close(self.descriptor)


def dispatch(snapshot: dict, token_file: Path, journal: Path, *, sender=send_once,
             now: datetime | None = None, job_snapshot: dict | None = None) -> dict:
    with DispatchLock(journal.with_name(journal.name+'.lock')):
        return _dispatch(snapshot,token_file,journal,sender=sender,now=now,job_snapshot=job_snapshot)


def _dispatch(snapshot: dict, token_file: Path, journal: Path, *, sender=send_once,
             now: datetime | None = None, job_snapshot: dict | None = None) -> dict:
    clock=now or datetime.now(timezone.utc)
    try:validate_snapshot(snapshot,clock)
    except Exception:raise AutomationError('SNAPSHOT_INVALID') from None
    encoded=json.dumps(snapshot,separators=(',',':'),sort_keys=True,ensure_ascii=True,allow_nan=False)
    if len(encoded.encode('ascii'))>MAX_SNAPSHOT:raise AutomationError('SNAPSHOT_INVALID')
    inputs={'platform_snapshot':encoded}
    fingerprint_source=encoded
    if job_snapshot is not None:
        try:validate_job_snapshot(job_snapshot,clock)
        except Exception:raise AutomationError('JOB_SNAPSHOT_INVALID') from None
        jobs_encoded=json.dumps(job_snapshot,separators=(',',':'),sort_keys=True,ensure_ascii=True,allow_nan=False)
        if len(jobs_encoded.encode('ascii'))>MAX_JOB_SNAPSHOT:raise AutomationError('JOB_SNAPSHOT_INVALID')
        inputs['jobs_snapshot']=jobs_encoded
        fingerprint_source=json.dumps(inputs,separators=(',',':'),sort_keys=True)
    payload={'ref':'main','inputs':inputs}
    payload_bytes=json.dumps(payload).encode('utf-8')
    if len(payload_bytes)>65536:raise AutomationError('SNAPSHOT_INVALID')
    fingerprint=hashlib.sha256(fingerprint_source.encode('ascii')).hexdigest()
    if journal.exists() or journal.is_symlink():
        regular_private(journal)
        try:
            with journal.open('rb') as handle:prior=json.loads(handle.read(4097))
            if not isinstance(prior,dict):raise ValueError
            if prior.get('snapshotSha256')==fingerprint:
                return public_report('SAME_ATTEMPT_NOT_RETRIED')
        except (OSError,ValueError):raise AutomationError('JOURNAL_INVALID') from None
    token=read_pages_token(token_file)
    intent={'snapshotSha256':fingerprint,'attemptStatus':'DISPATCH_INTENT_RECORDED',
            'dispatchAttemptedAt':clock.isoformat().replace('+00:00','Z'),'runId':None,'runUrl':None}
    # Persist before POST. A timeout, process crash or ambiguous success may
    # have created a run; this exact intent is never blindly sent twice.
    atomic_private_json(journal,intent)
    # API 2026-03-10 always returns run details. return_run_details was removed
    # in this version; the older API's boolean must not be sent here.
    request=Request(ENDPOINT,data=payload_bytes,method='POST',headers={
        'Authorization':'Bearer '+token,'Accept':'application/vnd.github+json',
        'Content-Type':'application/json','X-GitHub-Api-Version':API_VERSION,
        'User-Agent':'devdooly-platform-observer-pages/1'})
    try:
        code,body=sender(request)
        if code!=200:raise AutomationError('DISPATCH_AMBIGUOUS')
        result=json.loads(body)
        run_id=result.get('workflow_run_id')
        if not isinstance(run_id,int) or isinstance(run_id,bool) or not 1<=run_id<=SAFE_INTEGER:
            raise ValueError
        if str(result.get('html_url','')).lower()!=f'https://github.com/{REPOSITORY}/actions/runs/{run_id}'.lower():
            raise ValueError
        if str(result.get('run_url','')).lower()!=f'https://api.github.com/repos/{REPOSITORY}/actions/runs/{run_id}'.lower():
            raise ValueError
        report=public_report('DISPATCHED',run_id)
    except AutomationError as error:
        report=public_report(str(error) if str(error) in {'DISPATCH_AMBIGUOUS','DISPATCH_REJECTED'} else 'DISPATCH_AMBIGUOUS')
    except Exception:
        report=public_report('DISPATCH_AMBIGUOUS')
    atomic_private_json(journal,{**intent,**report})
    return report


def main(argv=None) -> int:
    parser=argparse.ArgumentParser(description='Dispatch one validated public snapshot; no credential or raw output.')
    parser.add_argument('--snapshot',required=True,type=Path)
    parser.add_argument('--token-file',required=True,type=Path)
    parser.add_argument('--journal',required=True,type=Path)
    args=parser.parse_args(argv)
    try:
        snapshot=load_snapshot(args.snapshot,datetime.now(timezone.utc))
        report=dispatch(snapshot,args.token_file,args.journal)
    except AutomationError as error:
        report=public_report(str(error) if str(error) in {'PAGES_CREDENTIAL_UNAVAILABLE','SNAPSHOT_INVALID'} else 'PRECONDITION_FAILED')
    except Exception:report=public_report('PRECONDITION_FAILED')
    print(json.dumps(report))
    return 0 if report['attemptStatus']=='DISPATCHED' else 1


if __name__=='__main__':raise SystemExit(main())
