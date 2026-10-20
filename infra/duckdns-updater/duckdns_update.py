"""One fixed DuckDNS IPv4 update. No work occurs at import."""
from contextlib import ExitStack
import json
import os
import re
import selectors
import stat
import subprocess
import time
from urllib.parse import quote_from_bytes

DIRECTORIES = ("etc", "devdooly-platform-lab", "duckdns")
ENV = {"PATH": "/usr/bin:/bin", "LANG": "C", "LC_ALL": "C"}
CURL_ARGS = ("/usr/bin/curl", "--disable", "--config", "-", "--ipv4", "--http1.1", "--proto", "=https",
             "--noproxy", "*", "--proxy", "", "--connect-timeout", "5", "--max-time", "15",
             "--max-filesize", "64", "--retry", "0", "--silent", "--write-out", "\n%{http_code}")


class Rejected(Exception):
    """Fixed codes only; never attach an input, response or native exception."""


def need(condition, code):
    if not condition:
        raise Rejected(code)


def identity(value):
    return (value.st_dev, value.st_ino, value.st_mode, value.st_uid, value.st_gid,
            value.st_nlink, value.st_size, value.st_mtime_ns, value.st_ctime_ns)


def read_leaf(directory_fd, name, maximum):
    flags = os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC | os.O_NONBLOCK
    descriptor = os.open(name, flags, dir_fd=directory_fd)
    try:
        before = os.fstat(descriptor)
        need(stat.S_ISREG(before.st_mode) and before.st_uid == 0 and before.st_nlink == 1
             and stat.S_IMODE(before.st_mode) == 0o600 and 0 < before.st_size <= maximum,
             "PRIVATE_FILE_UNVERIFIED")
        raw = os.read(descriptor, maximum + 1)
        need(len(raw) == before.st_size and len(raw) <= maximum and os.read(descriptor, 1) == b"",
             "PRIVATE_FILE_SIZE_UNVERIFIED")
        after = os.fstat(descriptor)
        path_after = os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
        need(identity(before) == identity(after) == identity(path_after), "PRIVATE_FILE_CHANGED")
        return raw
    finally:
        os.close(descriptor)


def read_inputs():
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC
    with ExitStack() as stack:
        descriptor = os.open("/", flags)
        stack.callback(os.close, descriptor)
        root = os.fstat(descriptor)
        need(stat.S_ISDIR(root.st_mode) and root.st_uid == 0 and not root.st_mode & 0o022,
             "PRIVATE_DIRECTORY_UNVERIFIED")
        opened = []
        for index, name in enumerate(DIRECTORIES):
            parent = descriptor
            descriptor = os.open(name, flags, dir_fd=parent)
            stack.callback(os.close, descriptor)
            value = os.fstat(descriptor)
            need(stat.S_ISDIR(value.st_mode) and value.st_uid == 0 and not value.st_mode & 0o022
                 and (index != len(DIRECTORIES) - 1 or stat.S_IMODE(value.st_mode) == 0o700),
                 "PRIVATE_DIRECTORY_UNVERIFIED")
            opened.append((parent, name, (value.st_dev, value.st_ino, value.st_mode, value.st_uid, value.st_gid)))
        domain, token = read_leaf(descriptor, "domain", 96), read_leaf(descriptor, "token", 257)
        for parent, name, expected in opened:
            value = os.stat(name, dir_fd=parent, follow_symlinks=False)
            need((value.st_dev, value.st_ino, value.st_mode, value.st_uid, value.st_gid) == expected,
                 "PRIVATE_DIRECTORY_CHANGED")
        return domain, token


def build_config(domain, token):
    need(type(domain) is bytes and type(token) is bytes, "PRIVATE_INPUT_INVALID")
    host = domain[:-1] if domain.endswith(b"\n") else domain
    secret = token[:-1] if token.endswith(b"\n") else token
    need(len(domain) <= 96 and re.fullmatch(rb"([a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?)\.duckdns\.org", host),
         "SINGLE_DUCKDNS_HOST_REQUIRED")
    need(1 <= len(secret) <= 256 and all(33 <= byte <= 126 for byte in secret), "PRIVATE_TOKEN_INVALID")
    label = host.removesuffix(b".duckdns.org").decode("ascii")
    url = "https://www.duckdns.org/update?domains=" + label + "&token=" + quote_from_bytes(secret, safe="") + "&ip="
    return ('url = "' + url + '"\n').encode("ascii")


def validate_result(returncode, raw):
    need(type(returncode) is int and returncode == 0, "UPDATE_UNVERIFIED")
    need(type(raw) is bytes and len(raw) <= 128, "UPDATE_OUTPUT_BOUND")
    body, separator, status = raw.rpartition(b"\n")
    need(separator == b"\n" and status == b"200", "HTTP_RESPONSE_UNVERIFIED")
    need(body in (b"OK", b"OK\n", b"OK\r\n"), "UPDATE_NOT_ACCEPTED")


def run_curl(config):
    need(type(config) is bytes and 0 < len(config) <= 2048, "PRIVATE_CONFIG_BOUND")
    deadline = time.monotonic() + 20
    child = subprocess.Popen(CURL_ARGS, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                             stderr=subprocess.DEVNULL, env=dict(ENV), close_fds=True, start_new_session=True)
    joined = False
    try:
        child.stdin.write(config)  # bounded below PIPE_BUF; token never enters argv/env
        child.stdin.close()
        os.set_blocking(child.stdout.fileno(), False)
        raw = bytearray()
        with selectors.DefaultSelector() as selector:
            selector.register(child.stdout, selectors.EVENT_READ)
            while True:
                remaining = deadline - time.monotonic()
                need(remaining > 0, "UPDATE_TIMEOUT_OUTCOME_UNKNOWN")
                if not selector.select(min(remaining, 0.5)):
                    continue
                chunk = os.read(child.stdout.fileno(), 129 - len(raw))
                if not chunk:
                    break
                need(len(raw) + len(chunk) <= 128, "UPDATE_OUTPUT_BOUND")
                raw.extend(chunk)
        remaining = deadline - time.monotonic()
        need(remaining > 0, "UPDATE_TIMEOUT_OUTCOME_UNKNOWN")
        try:
            returncode = child.wait(timeout=remaining)
            joined = True
        except subprocess.TimeoutExpired:
            raise Rejected("UPDATE_TIMEOUT_OUTCOME_UNKNOWN") from None
        need(time.monotonic() < deadline, "UPDATE_TIMEOUT_OUTCOME_UNKNOWN")
        validate_result(returncode, bytes(raw))
    finally:
        try:
            if not joined:
                if child.poll() is None:
                    child.kill()
                try:
                    child.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    raise Rejected("CHILD_EXIT_UNVERIFIED") from None
        finally:
            for stream in (child.stdin, child.stdout):
                try:
                    stream.close()
                except Exception:
                    pass


def main():
    passed, result = False, "UPDATE_UNVERIFIED"
    try:
        run_curl(build_config(*read_inputs()))
        passed, result = True, "UPDATE_ACCEPTED"
    except Rejected as error:
        result = error.args[0]
    except Exception:
        pass  # never emit native exceptions, private paths, URL, token or response
    print(json.dumps({"schemaVersion": 1, "scope": "DUCKDNS_SINGLE_HOST_IPV4_UPDATE", "passed": passed,
                      "result": result, "automaticRetryPerformed": False}))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
