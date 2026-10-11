#!/usr/bin/env python3
"""Authenticate and optionally decrypt a DDPLAB01 AES-256-GCM backup.

Requires the third-party ``cryptography`` package. No server connection is made.
"""

from __future__ import annotations

import argparse
import ctypes
import errno
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import sys
import tempfile

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

MAGIC = b"DDPLAB01"
NONCE_BYTES = 12
TAG_BYTES = 16
HEADER_BYTES = len(MAGIC) + NONCE_BYTES
CHUNK_BYTES = 4 * 1024 * 1024


class BackupError(Exception):
    """An expected failure whose message contains no secret or source path."""


def expected_sha256(value: str) -> str:
    if not re.fullmatch(r"[0-9a-fA-F]{64}", value):
        raise argparse.ArgumentTypeError("Expected a 64-character SHA-256 hex digest.")
    return value.lower()


def open_regular(path: Path):
    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(path, flags)
    try:
        if not stat.S_ISREG(os.fstat(fd).st_mode):
            raise BackupError("Input and key must be regular files.")
        return os.fdopen(fd, "rb")
    except BaseException:
        os.close(fd)
        raise


def read_key(path: Path) -> bytes:
    with open_regular(path) as handle:
        if os.name != "nt" and os.fstat(handle.fileno()).st_mode & 0o077:
            raise BackupError("Key permissions must deny access to group and others.")
        key = handle.read(33)
    if len(key) != 32:
        raise BackupError("Key file must contain exactly 32 raw bytes.")
    return key


def restrict_plaintext(path: Path) -> None:
    os.chmod(path, 0o600)
    if os.name == "nt":
        # chmod(0600) alone does not restrict NTFS access permissions.
        sid = subprocess.check_output(
            ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command",
             "[System.Security.Principal.WindowsIdentity]::GetCurrent().User.Value"],
            text=True, stderr=subprocess.DEVNULL,
        ).strip()
        if not re.fullmatch(r"S-1-(?:\d+-)*\d+", sid):
            raise BackupError("Unable to determine the current Windows security identity.")
        subprocess.run(
            ["icacls.exe", str(path), "/inheritance:r", "/grant:r",
             f"*{sid}:F", "*S-1-5-18:F"],
            check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )


def publish_without_overwrite(temporary: Path, destination: Path) -> None:
    """Publish in the same directory, atomically and without replacing a name."""
    if os.name == "nt":
        # Unlike POSIX rename, Windows rename fails if the destination exists.
        os.rename(temporary, destination)
    elif sys.platform.startswith("linux"):
        # Ubuntu's renameat2 provides atomic rename with no-clobber semantics.
        libc = ctypes.CDLL(None, use_errno=True)
        renameat2 = getattr(libc, "renameat2", None)
        if renameat2 is None:
            raise BackupError("Atomic no-overwrite rename is unavailable on this platform.")
        renameat2.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_int,
                             ctypes.c_char_p, ctypes.c_uint]
        renameat2.restype = ctypes.c_int
        if renameat2(-100, os.fsencode(temporary), -100, os.fsencode(destination), 1):
            failure = ctypes.get_errno()
            if failure == errno.EEXIST:
                raise BackupError("Output already exists; refusing to overwrite it.")
            raise OSError(failure, "Atomic no-overwrite rename failed.")
    else:
        raise BackupError("Atomic output is supported on Linux and Windows only; use --verify-only.")


def process_backup(source: Path, key_file: Path, output: Path | None,
                   expected: str | None) -> dict[str, str | int]:
    key = read_key(key_file)
    temporary: Path | None = None
    destination = output.absolute() if output is not None else None
    writer = None
    try:
        with open_regular(source) as reader:
            size = os.fstat(reader.fileno()).st_size
            if size < HEADER_BYTES + TAG_BYTES:
                raise BackupError("Backup is shorter than its header and authentication tag.")
            header = reader.read(HEADER_BYTES)
            if header[:len(MAGIC)] != MAGIC:
                raise BackupError("Unsupported backup format.")
            reader.seek(-TAG_BYTES, os.SEEK_END)
            tag = reader.read(TAG_BYTES)
            reader.seek(HEADER_BYTES)
            decryptor = Cipher(algorithms.AES(key), modes.GCM(header[len(MAGIC):], tag)).decryptor()
            decryptor.authenticate_additional_data(header)

            if destination is not None:
                if os.path.lexists(destination):
                    raise BackupError("Output already exists; refusing to overwrite it.")
                if not destination.parent.is_dir():
                    raise BackupError("Output parent directory must already exist.")
                fd, name = tempfile.mkstemp(prefix=".ddplab-decrypt-", suffix=".tmp",
                                            dir=destination.parent)
                temporary = Path(name)
                writer = os.fdopen(fd, "wb")
                # Restrict access before writing any unauthenticated plaintext.
                restrict_plaintext(temporary)

            digest = hashlib.sha256()
            count = 0
            remaining = size - HEADER_BYTES - TAG_BYTES
            while remaining:
                chunk = reader.read(min(CHUNK_BYTES, remaining))
                if not chunk:
                    raise BackupError("Backup was truncated while reading.")
                remaining -= len(chunk)
                plaintext = decryptor.update(chunk)
                digest.update(plaintext)
                count += len(plaintext)
                if writer is not None:
                    writer.write(plaintext)
            plaintext = decryptor.finalize()  # Never publish before GCM authentication.
            digest.update(plaintext)
            count += len(plaintext)
            if writer is not None:
                writer.write(plaintext)
            actual = digest.hexdigest()
            if expected is not None and actual != expected:
                raise BackupError("Authenticated plaintext SHA-256 does not match the expected digest.")
            if os.fstat(reader.fileno()).st_size != size:
                raise BackupError("Backup size changed while reading.")

        if writer is not None:
            writer.flush()
            os.fsync(writer.fileno())
            writer.close()
            writer = None
            publish_without_overwrite(temporary, destination)
            temporary = None
        return {"sha256": actual, "plaintextBytes": count}
    finally:
        try:
            if writer is not None:
                writer.close()
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path, help="Encrypted DDPLAB01 backup.")
    parser.add_argument("--key-file", required=True, type=Path, help="File containing exactly 32 raw key bytes.")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--output", type=Path, help="New plaintext file; existing files are never overwritten.")
    mode.add_argument("--verify-only", action="store_true", help="Authenticate and hash without writing plaintext.")
    parser.add_argument("--expected-sha256", type=expected_sha256, help="Expected plaintext SHA-256 digest.")
    args = parser.parse_args()
    try:
        result = process_backup(args.input, args.key_file, args.output, args.expected_sha256)
    except InvalidTag:
        print("Authentication failed; no output was published.", file=sys.stderr)
        return 2
    except BackupError as failure:
        print(str(failure), file=sys.stderr)
        return 1
    except (OSError, subprocess.SubprocessError):
        print("Unable to process backup; check files, permissions, and available disk space.", file=sys.stderr)
        return 1
    print(json.dumps(result, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
