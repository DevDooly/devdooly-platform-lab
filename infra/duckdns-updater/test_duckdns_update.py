"""Synthetic fd/stat/child tests; never invoke curl, DNS or systemd."""
from contextlib import redirect_stdout
import io
import os
import stat
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

import duckdns_update as update


def info(mode=stat.S_IFREG | 0o600, uid=0, links=1, size=5, inode=14):
    return SimpleNamespace(st_dev=1, st_ino=inode, st_mode=mode, st_uid=uid, st_gid=0,
                           st_nlink=links, st_size=size, st_mtime_ns=1, st_ctime_ns=1)


class DuckDnsUpdateTest(unittest.TestCase):
    def setUp(self):
        # Missing Linux flag names are synthetic only; all related IO is mocked.
        for name, value in (("O_NOFOLLOW", 0x20000), ("O_DIRECTORY", 0x10000),
                            ("O_CLOEXEC", 0x80000), ("O_NONBLOCK", 0x800)):
            if not hasattr(update.os, name):
                replacement = patch.object(update.os, name, value, create=True)
                replacement.start()
                self.addCleanup(replacement.stop)

    def native_case(self, raw, returncode=0, clock=None, wait_elapsed=None):
        child, selector = Mock(), Mock()
        child.stdout.fileno.return_value = 41
        child.wait.return_value = returncode
        if wait_elapsed is not None:
            current = [1.0]
            def completed_wait(**unused):
                current[0] = 1.0 + wait_elapsed
                return returncode
            child.wait.side_effect = completed_wait
            clock = lambda: current[0]
        child.poll.return_value = None
        selector.select.return_value = [(object(), update.selectors.EVENT_READ)]
        config = update.build_config(b"synthetic-example.duckdns.org\n", b"SYNTHETIC&PRIVATE_MARKER\n")
        with patch.object(update.subprocess, "Popen", return_value=child) as spawn, \
             patch.object(update.selectors, "DefaultSelector") as factory, \
             patch.object(update.os, "set_blocking"), \
             patch.object(update.os, "read", side_effect=[raw, b""]) as read, \
             patch.object(update.time, "monotonic", side_effect=clock, return_value=1.0):
            factory.return_value.__enter__.return_value = selector
            failure = None
            try:
                update.run_curl(config)
            except update.Rejected as error:
                failure = error.args[0]
        return child, spawn, read, config, failure

    def test_private_fd_metadata_and_replacement_reject_before_request(self):
        domain, token = b"synthetic-example.duckdns.org\n", b"SYNTHETIC_TOKEN\n"
        parents = [info(stat.S_IFDIR | 0o755, inode=n) for n in (10, 11, 12)]
        final = info(stat.S_IFDIR | 0o700, inode=13)
        domain_info, token_info = info(size=len(domain)), info(size=len(token), inode=15)
        with patch.object(update.os, "open", side_effect=range(10, 16)) as opened, \
             patch.object(update.os, "close"), \
             patch.object(update.os, "fstat", side_effect=[*parents, final, domain_info, domain_info,
                                                            token_info, token_info]), \
             patch.object(update.os, "stat", side_effect=[domain_info, token_info, *parents[1:], final]), \
             patch.object(update.os, "read", side_effect=[domain, b"", token, b""]), \
             patch.object(update.subprocess, "Popen") as spawn:
            self.assertEqual(update.read_inputs(), (domain, token))
            self.assertTrue(all(call.args[1] & os.O_NOFOLLOW for call in opened.call_args_list))
            spawn.assert_not_called()
        for invalid in (info(uid=1), info(mode=stat.S_IFREG | 0o644), info(links=2),
                        info(mode=stat.S_IFIFO | 0o600)):
            with self.subTest(metadata=(invalid.st_uid, invalid.st_mode, invalid.st_nlink)), \
                 patch.object(update.os, "open", return_value=41), patch.object(update.os, "close"), \
                 patch.object(update.os, "fstat", return_value=invalid), \
                 patch.object(update.os, "read") as read, patch.object(update.subprocess, "Popen") as spawn:
                with self.assertRaisesRegex(update.Rejected, "PRIVATE_FILE_UNVERIFIED"):
                    update.read_leaf(13, "token", 257)
                read.assert_not_called()
                spawn.assert_not_called()
        with patch.object(update.os, "open", return_value=41), patch.object(update.os, "close"), \
             patch.object(update.os, "fstat", return_value=info()), \
             patch.object(update.os, "read", side_effect=[b"value", b""]), \
             patch.object(update.os, "stat", return_value=info(inode=99)):
            with self.assertRaisesRegex(update.Rejected, "PRIVATE_FILE_CHANGED"):
                update.read_leaf(13, "token", 257)
        with patch.object(update.os, "open", side_effect=OSError("SYNTHETIC_SYMLINK_REJECTED")):
            with self.assertRaises(OSError):
                update.read_leaf(13, "token", 257)
        with patch.object(update.os, "open", return_value=41), patch.object(update.os, "close"), \
             patch.object(update.os, "fstat", return_value=info(stat.S_IFDIR | 0o777)):
            with self.assertRaisesRegex(update.Rejected, "PRIVATE_DIRECTORY_UNVERIFIED"):
                update.read_inputs()

    def test_single_host_and_token_are_validated_and_config_only(self):
        config = update.build_config(b"synthetic-example.duckdns.org", b'SYNTHETIC&"\\SECRET')
        self.assertEqual(config, b'url = "https://www.duckdns.org/update?domains=synthetic-example'
                         b'&token=SYNTHETIC%26%22%5CSECRET&ip="\n')
        for host in (b"", b"x.y.duckdns.org", b"one,two.duckdns.org", b"https://one.duckdns.org",
                     b"-one.duckdns.org", b"one.duckdns.org?x=1", b"one.duckdns.org\n\n"):
            with self.subTest(host=host), self.assertRaises(update.Rejected):
                update.build_config(host, b"SYNTHETIC_TOKEN")
        for secret in (b"", b"value\r\n", b"value with space", b"value\x00tail", b"x" * 257):
            with self.subTest(secret_kind=len(secret)), self.assertRaises(update.Rejected):
                update.build_config(b"one.duckdns.org", secret)
        child, spawn, _, config, failure = self.native_case(b"OK\n200")
        self.assertIsNone(failure)
        args, kwargs = spawn.call_args
        self.assertEqual(args, (update.CURL_ARGS,))
        self.assertEqual(args[0][:2], ("/usr/bin/curl", "--disable"))
        self.assertIn("--http1.1", args[0])
        self.assertEqual(args[0][args[0].index("--proto") + 1], "=https")
        self.assertEqual(args[0][args[0].index("--retry") + 1], "0")
        self.assertFalse({"--location", "-L", "--insecure", "-k", "--verbose", "--trace", "--netrc"} & set(args[0]))
        self.assertNotIn(b"PRIVATE_MARKER", repr((args, kwargs)).encode())
        self.assertEqual(kwargs["env"], {"PATH": "/usr/bin:/bin", "LANG": "C", "LC_ALL": "C"})
        self.assertEqual(kwargs["stderr"], update.subprocess.DEVNULL)
        child.stdin.write.assert_called_once_with(config)
        child.wait.assert_called_once()
        child.kill.assert_not_called()

    def test_only_http_200_exact_ok_and_exit_zero_succeed(self):
        for raw in (b"OK\n200", b"OK\n\n200", b"OK\r\n\n200"):
            with self.subTest(raw=raw):
                self.assertIsNone(self.native_case(raw)[-1])
        for raw, returncode in ((b"KO\n200", 0), (b"OK\n302", 0), (b"OK\n500", 0),
                                (b"OK\n200", 7), (b" OK\n200", 0), (b"OK\n200\n", 0),
                                (b"x" * 129, 0)):
            with self.subTest(response_kind=(len(raw), returncode)):
                child, spawn, read, _, failure = self.native_case(raw, returncode)
                self.assertIsNotNone(failure)
                spawn.assert_called_once()
                self.assertTrue(all(call.args[1] <= 129 for call in read.call_args_list))
                if len(raw) > 128:
                    child.kill.assert_called_once()
                    child.wait.assert_called_once_with(timeout=2)

    def test_timeout_kills_joins_once_and_native_exception_is_not_exported(self):
        child, spawn, read, _, failure = self.native_case(b"", clock=[1.0, 22.0])
        self.assertEqual(failure, "UPDATE_TIMEOUT_OUTCOME_UNKNOWN")
        spawn.assert_called_once()
        read.assert_not_called()
        child.kill.assert_called_once()
        child.wait.assert_called_once_with(timeout=2)
        output = io.StringIO()
        with patch.object(update, "read_inputs", return_value=(b"one.duckdns.org", b"SYNTHETIC_TOKEN")), \
             patch.object(update, "run_curl", side_effect=OSError("SYNTHETIC_PRIVATE_URL_TOKEN_CANARY")), \
             redirect_stdout(output):
            self.assertEqual(update.main(), 1)
        self.assertNotIn("CANARY", output.getvalue())
        self.assertIn('"passed": false', output.getvalue())
        self.assertIn('"result": "UPDATE_UNVERIFIED"', output.getvalue())

    def test_successful_wait_return_at_or_after_total_deadline_is_not_accepted_or_joined_twice(self):
        for elapsed, expected in ((19.999, None), (20.0, "UPDATE_TIMEOUT_OUTCOME_UNKNOWN"),
                                  (20.001, "UPDATE_TIMEOUT_OUTCOME_UNKNOWN")):
            with self.subTest(wait_elapsed_seconds=elapsed):
                child, spawn, read, _, failure = self.native_case(b"OK\n200", wait_elapsed=elapsed)
                self.assertEqual(failure, expected)
                spawn.assert_called_once()
                child.wait.assert_called_once_with(timeout=20.0)
                child.kill.assert_not_called()
                child.poll.assert_not_called()
                child.stdout.close.assert_called_once()
                self.assertEqual(read.call_count, 2)


if __name__ == "__main__":
    unittest.main()
