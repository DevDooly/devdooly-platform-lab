#!/usr/bin/env python3
"""Back up the Lab DB and K3s SQLite state locally; no restart or off-host copy."""
from __future__ import annotations

import argparse
from contextlib import closing
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import shutil
import sqlite3
import stat
import subprocess
import sys
import time

BASELINE_QUERY = (
    "SELECT * FROM demo_run ORDER BY id; "
    "SELECT * FROM demo_outcome ORDER BY run_id,input_sequence; "
    "SELECT * FROM flyway_schema_history ORDER BY installed_rank;"
)
DEFAULT_DATA_ROOT = Path("/var/lib/devdooly-platform-lab")
DEFAULT_BACKUP_ROOT = Path("/var/backups/devdooly-platform-lab")


class BackupError(Exception):
    pass


def checked_path(path: Path, *, existing: bool = True) -> Path:
    if not path.is_absolute() or ".." in path.parts or path == Path(path.anchor):
        raise BackupError("Use an absolute, non-root path without parent traversal.")
    if path.resolve(strict=existing) != path:
        raise BackupError("Symlinked paths are not accepted.")
    return path


def require_private(path: Path, *, directory: bool = False) -> None:
    details = path.lstat()
    correct_type = stat.S_ISDIR(details.st_mode) if directory else stat.S_ISREG(details.st_mode)
    if not correct_type or details.st_uid != 0 or details.st_mode & 0o077:
        raise BackupError("Backup paths must be root-owned and deny group/other access.")


def digest_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(4 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def command(args: list[str], *, timeout: int = 120) -> bytes:
    result = subprocess.run(args, capture_output=True, timeout=timeout)
    if result.returncode:
        raise BackupError("A backup command failed; secret-bearing diagnostics were withheld.")
    return result.stdout


def kube(*args: str) -> dict:
    return json.loads(command(["k3s", "kubectl", *args, "-o", "json"]))


def parser() -> argparse.ArgumentParser:
    value = argparse.ArgumentParser(description=__doc__)
    value.add_argument("--data-root", type=Path, default=DEFAULT_DATA_ROOT)
    value.add_argument("--backup-root", type=Path, default=DEFAULT_BACKUP_ROOT)
    value.add_argument("--namespace", default="platform-lab")
    value.add_argument("--db-statefulset", default="lab-platform-lab-db")
    value.add_argument("--api-deployment", default="lab-platform-lab-api")
    return value


def validate_names(args: argparse.Namespace) -> None:
    for name in (args.namespace, args.db_statefulset, args.api_deployment):
        if not re.fullmatch(r"[a-z0-9](?:[-a-z0-9]*[a-z0-9])?", name) or len(name) > 63:
            raise BackupError("Namespace and resource names must be DNS labels of at most 63 characters.")


def require_standalone_snapshot(database: Path) -> None:
    if any(os.path.lexists(Path(str(database) + suffix)) for suffix in ("-wal", "-shm", "-journal")):
        raise BackupError("SQLite snapshot has journal companions; archive was not created.")


def sqlite_snapshot(source_db: Path, destination_db: Path, progress) -> None:
    if os.path.lexists(destination_db):
        raise BackupError("SQLite snapshot destination must be new.")
    require_standalone_snapshot(destination_db)
    with closing(sqlite3.connect(source_db.as_uri() + "?mode=ro", uri=True)) as source:
        with closing(sqlite3.connect(destination_db)) as destination:
            source.backup(destination, pages=256, progress=progress, sleep=0.05)
            # Backup may copy WAL journal mode in the database header. Change
            # only this new, exclusively owned destination after backup ends.
            if destination.execute("PRAGMA journal_mode=DELETE").fetchall() != [("delete",)]:
                raise BackupError("SQLite snapshot DELETE journal mode was not confirmed.")
            if destination.execute("PRAGMA quick_check").fetchall() != [("ok",)]:
                raise BackupError("SQLite snapshot integrity check failed.")
    require_standalone_snapshot(destination_db)


def validate_demo_counts(counts: str) -> None:
    """Validate count query rows without assuming an initial seed dataset."""
    message = "Demo counts must contain consistent nonnegative integer totals and per-run metrics."
    if type(counts) is not str:
        raise BackupError(message)
    rows = counts.splitlines()
    if len(rows) < 2:
        raise BackupError(message)
    fields = [row.split("\t") for row in rows]
    if any(len(row) != (1 if index < 2 else 5) for index, row in enumerate(fields)):
        raise BackupError(message)
    if any(re.fullmatch(r"[0-9]+", field) is None for row in fields for field in row):
        raise BackupError(message)
    try:
        values = [[int(field) for field in row] for row in fields]
    except ValueError:
        raise BackupError(message) from None
    run_count, outcome_count = values[0][0], values[1][0]
    metrics = values[2:]
    if len(metrics) != run_count:
        raise BackupError(message)
    if any(input_count != success + failure + duplicate + pending
           for input_count, success, failure, duplicate, pending in metrics):
        raise BackupError(message)
    if sum(row[0] for row in metrics) != outcome_count:
        raise BackupError(message)


def create_backup(args: argparse.Namespace) -> dict:
    validate_names(args)
    root = checked_path(args.data_root)
    backup_root = checked_path(args.backup_root, existing=False)
    if root == backup_root or root in backup_root.parents or backup_root in root.parents:
        raise BackupError("Data and backup roots must be separate directories.")
    if not root.is_dir() or shutil.disk_usage(root).free < 10 * 1024**3:
        raise BackupError("The Lab data root needs at least 10 GiB available.")
    source_db = checked_path(root / "k3s/server/db/state.db")
    token = checked_path(root / "k3s/server/token")
    if not source_db.is_file() or not token.is_file():
        raise BackupError("Expected a K3s SQLite database and server token under the selected data root.")
    if not backup_root.exists():
        backup_root.mkdir(mode=0o700, parents=False)
    require_private(backup_root, directory=True)
    if shutil.disk_usage(backup_root).free < 10 * 1024**3:
        raise BackupError("The backup filesystem needs at least 10 GiB available.")

    prefix = ["k3s", "kubectl", "-n", args.namespace, "exec", args.db_statefulset + "-0", "--", "sh", "-c"]
    sql_script = ('export MYSQL_PWD="$MARIADB_ROOT_PASSWORD"; '
                  'exec mariadb -uroot --batch --raw --skip-column-names "$MARIADB_DATABASE" -e "$1"')
    def sql(query: str) -> str:
        return command(prefix + [sql_script, "sql", query]).decode("utf-8")

    db = kube("-n", args.namespace, "get", "statefulset", args.db_statefulset)
    api = kube("-n", args.namespace, "get", "deployment", args.api_deployment)
    if db["spec"]["replicas"] != 1 or api["spec"]["replicas"] != 1:
        raise BackupError("Expected exactly one production DB replica and one API replica.")
    images = [obj["spec"]["template"]["spec"]["containers"][0]["image"] for obj in (db, api)]
    if not all(re.fullmatch(r"[^\s@]+@sha256:[0-9a-f]{64}", image) for image in images):
        raise BackupError("Production DB and API images must be pinned by SHA-256 digest.")

    engines = sql("SELECT TABLE_NAME,ENGINE FROM information_schema.TABLES WHERE TABLE_SCHEMA=DATABASE() ORDER BY TABLE_NAME;")
    if not engines.strip() or any(row.split("\t")[-1] != "InnoDB" for row in engines.strip().splitlines()):
        raise BackupError("Online logical backup currently supports InnoDB tables only.")
    baseline = sql(BASELINE_QUERY)
    counts = sql("SELECT COUNT(*) FROM demo_run; SELECT COUNT(*) FROM demo_outcome; SELECT input_count,success_count,failure_count,duplicate_count,pending_count FROM demo_run ORDER BY id;")
    validate_demo_counts(counts)

    backup = backup_root / ("operations-" + dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + secrets.token_hex(3))
    backup.mkdir(mode=0o700)
    started = time.monotonic()
    dump_path = backup / "mariadb.sql"
    with dump_path.open("xb") as output:
        result = subprocess.run(prefix + [
            'export MYSQL_PWD="$MARIADB_ROOT_PASSWORD"; '
            'exec mariadb-dump -uroot --single-transaction --quick --routines --events --triggers --hex-blob --databases "$MARIADB_DATABASE"'
        ], stdout=output, stderr=subprocess.PIPE, timeout=120)
        output.flush()
        os.fsync(output.fileno())
    if result.returncode or not dump_path.stat().st_size:
        raise BackupError("Logical dump failed; incomplete private files were retained without a success manifest.")
    if sql(BASELINE_QUERY) != baseline:
        raise BackupError("Source data changed during backup; retry without concurrent writes or DDL.")
    with (backup / "database-baseline.tsv").open("x", encoding="utf-8", newline="") as output:
        output.write(baseline)

    snapshot = backup / "k3s-datastore"
    snapshot.mkdir(mode=0o700)
    deadline = time.monotonic() + 120
    def progress(_status: int, _remaining: int, _total: int) -> None:
        if time.monotonic() > deadline:
            raise BackupError("SQLite online backup exceeded its time budget.")
    sqlite_snapshot(source_db, snapshot / "state.db", progress)
    shutil.copy2(token, snapshot / "server-token")
    for name in ("cred", "tls"):
        location = checked_path(root / "k3s/server" / name)
        if not location.is_dir():
            raise BackupError("Expected K3s credential and TLS directories.")
        shutil.copytree(location, snapshot / name)
    shutil.copytree("/etc/rancher/k3s", snapshot / "config")
    shutil.copy2("/etc/systemd/system/k3s.service", snapshot / "k3s.service")
    service_env = Path("/etc/systemd/system/k3s.service.env")
    if service_env.exists():
        shutil.copy2(service_env, snapshot / service_env.name)
    for item in backup.rglob("*"):
        item.chmod(0o700 if item.is_dir() else 0o600)
    require_standalone_snapshot(snapshot / "state.db")
    command(["tar", "-czf", str(backup / "k3s-datastore.tar.gz"), "-C", str(snapshot), "."])

    summary = {
        "logicalDumpCreated": True, "dumpBytes": dump_path.stat().st_size,
        "innodbOnly": True, "singleTransaction": True, "sourceUnchangedDuringDump": True,
        "sqliteOnlineBackupQuickCheck": "ok", "k3sTokenAndConfigurationIncluded": True,
        "seconds": round(time.monotonic() - started, 3),
    }
    manifest = {
        "schemaVersion": 1, "scope": "LAB_DB_AND_K3S_SQLITE_LOCAL_BACKUP",
        "createdAt": dt.datetime.now(dt.timezone.utc).isoformat(),
        "backupDirectory": str(backup), "databaseDump": str(dump_path),
        "dumpSha256": digest_file(dump_path), "dumpBytes": dump_path.stat().st_size,
        "databaseBaselineSha256": hashlib.sha256(baseline.encode("utf-8")).hexdigest(),
        "baselineQuery": BASELINE_QUERY, "tableEngines": engines, "counts": counts,
        "k3sSnapshotSha256": digest_file(backup / "k3s-datastore.tar.gz"),
        "databaseImage": images[0], "apiImage": images[1], "namespace": args.namespace,
        "dbStatefulset": args.db_statefulset, "apiDeployment": args.api_deployment,
        "publicSummary": summary,
        "limits": ["Local backup only; no off-host copy or encryption performed.",
                   "No K3s/Jenkins restoration, Jenkins backup, or host reboot performed."],
    }
    with (backup / "manifest.json").open("x", encoding="utf-8") as output:
        json.dump(manifest, output, indent=2)
        output.write("\n")
    return summary


def main() -> int:
    args = parser().parse_args()
    try:
        if os.name != "posix" or os.geteuid() != 0:
            raise BackupError("Run locally as root on the Ubuntu Lab host.")
        os.umask(0o077)
        print(json.dumps(create_backup(args)))
        return 0
    except (BackupError, OSError, ValueError, KeyError, subprocess.SubprocessError, sqlite3.Error) as failure:
        message = str(failure) if isinstance(failure, BackupError) else "Backup failed; private diagnostics were withheld."
        print(message, file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
