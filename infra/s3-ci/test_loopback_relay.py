"""Real local TCP fixtures exercise transfer/bounds; Docker proof is tested separately."""
import json
import socket
import threading
import time
import unittest
from unittest import mock

import loopback_relay as relay


class LocalServer:
    def __init__(self, mode='echo'):
        self.listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.listener.bind(('127.0.0.1', 0))
        self.listener.listen(16)
        self.listener.settimeout(.1)
        self.address = self.listener.getsockname()
        self.stop = threading.Event()
        self.connections = []
        self.workers = []
        self.mode = mode
        self.thread = threading.Thread(target=self.run)
        self.thread.start()

    def run(self):
        while not self.stop.is_set():
            try:
                connection, _ = self.listener.accept()
            except socket.timeout:
                continue
            except OSError:
                break
            self.connections.append(connection)
            worker = threading.Thread(target=self.serve, args=(connection,))
            self.workers.append(worker)
            worker.start()

    def serve(self, connection):
        connection.settimeout(.1)
        payload = bytearray()
        try:
            while not self.stop.is_set():
                try:
                    chunk = connection.recv(4096)
                except socket.timeout:
                    continue
                if not chunk:
                    if self.mode == 'after-half-close':
                        connection.sendall(b'ack:'+payload)
                    break
                payload.extend(chunk)
                if self.mode == 'echo':
                    connection.sendall(chunk)
        except OSError:
            pass
        finally:
            connection.close()

    def close(self):
        self.stop.set()
        self.listener.close()
        for connection in self.connections:
            try:
                connection.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
        self.thread.join(2)
        for worker in self.workers:
            worker.join(2)
        assert not self.thread.is_alive() and not any(t.is_alive() for t in self.workers)


class RelayBoundaries(unittest.TestCase):
    def local(self, server, **bounds):
        # Only the unit fixture replaces the validated Docker target with its
        # loopback test listener. Production has no env/CLI bypass for this.
        value = relay.LoopbackRelay('172.25.0.2', 3900, lambda: server.address, **bounds)
        value.target = server.address
        self.addCleanup(value.close)
        value.start()
        return value

    def until(self, condition):
        deadline = time.monotonic()+3
        while time.monotonic() < deadline and not condition():
            time.sleep(.01)
        self.assertTrue(condition())

    def test_real_tcp_bytes_and_half_close_are_preserved_and_all_threads_join(self):
        server = LocalServer('after-half-close'); self.addCleanup(server.close)
        value = self.local(server)
        value.probe()
        data = b'\x00\xffsynthetic-mysql-or-s3-byte-stream\r\n'*400
        with socket.create_connection(('127.0.0.1', value.port), timeout=2) as connection:
            connection.sendall(data); connection.shutdown(socket.SHUT_WR)
            result = bytearray()
            while chunk := connection.recv(4096):
                result.extend(chunk)
        self.assertEqual(bytes(result), b'ack:'+data)
        self.assertTrue(value.close())
        report = value.summary()
        self.assertTrue(report['tcpPositiveControlPassed'])
        self.assertTrue(report['stoppedAndJoined'])
        self.assertIsNone(report['failureCode'])
        self.assertEqual(report['acceptedConnections'], report['closedConnections'])

    def test_real_tcp_per_connection_and_aggregate_bytes_fail_closed(self):
        for bounds in ({'max_connection_bytes': 64}, {'max_total_bytes': 64}):
            with self.subTest(bounds=bounds):
                server = LocalServer(); self.addCleanup(server.close)
                value = self.local(server, **bounds)
                with socket.create_connection(('127.0.0.1', value.port), timeout=2) as connection:
                    connection.sendall(b'x'*1024)
                    self.until(lambda: value.summary()['failureCode'] is not None)
                self.assertTrue(value.close())
                self.assertEqual(value.summary()['failureCode'], 'RELAY_BYTE_BOUND_EXCEEDED')
                self.assertLessEqual(value.summary()['observedBidirectionalBytesRead'], 65)

    def test_real_idle_connection_has_a_deadline_and_does_not_survive_close(self):
        server = LocalServer('hold'); self.addCleanup(server.close)
        value = self.local(server, idle_timeout=.15)
        with socket.create_connection(('127.0.0.1', value.port), timeout=2):
            self.until(lambda: value.summary()['failureCode'] == 'RELAY_TIME_BOUND_EXCEEDED')
        self.assertTrue(value.close())

    def test_active_connection_and_total_connection_caps_are_enforced(self):
        for bounds in ({'max_active': 1}, {'max_connections': 1}):
            with self.subTest(bounds=bounds):
                server = LocalServer('hold'); self.addCleanup(server.close)
                value = self.local(server, **bounds)
                with socket.create_connection(('127.0.0.1', value.port), timeout=2):
                    self.until(lambda: value.summary()['targetConnections'] == 1)
                    with socket.create_connection(('127.0.0.1', value.port), timeout=2):
                        self.until(lambda: value.summary()['failureCode'] == 'RELAY_CONNECTION_BOUND_EXCEEDED')
                self.assertTrue(value.close())
                self.assertEqual(value.summary()['observedPeakActiveConnections'], 1)

    def test_fresh_verifier_failure_prevents_target_connect(self):
        server = LocalServer(); self.addCleanup(server.close)
        value = self.local(server)
        value.verify_target = mock.Mock(side_effect=RuntimeError('private-detail-must-not-publish'))
        with socket.create_connection(('127.0.0.1', value.port), timeout=2):
            self.until(lambda: value.summary()['failureCode'] == 'RELAY_TARGET_SCOPE_UNVERIFIED')
        self.assertTrue(value.close())
        report = value.summary()
        self.assertEqual(report['targetConnections'], 0)
        self.assertNotIn('private-detail', json.dumps(report))

    def test_public_summary_has_no_addresses_ports_payloads_or_container_identity(self):
        server = LocalServer(); self.addCleanup(server.close)
        value = self.local(server); value.probe(); self.assertTrue(value.close())
        report = value.summary(); encoded = json.dumps(report)
        self.assertTrue(all(isinstance(v, (str, int, float, bool, type(None))) for v in report.values()))
        for raw in ('127.0.0.1', '172.25.0.2', 'HostIp', 'HostPort', 'password', 'containerId'):
            self.assertNotIn(raw, encoded)
        self.assertFalse(report['payloadInspectedOrLogged'])

    def test_unbounded_or_nonprivate_targets_are_not_configuration_options(self):
        for address, port in (('127.0.0.1',3900), ('0.0.0.0',3900), ('8.8.8.8',3900), ('172.25.0.2',22)):
            with self.assertRaises(relay.RelayError):
                relay.LoopbackRelay(address, port, lambda: (address,port))
        for bounds in ({'lifetime': float('nan')}, {'max_active':17}, {'idle_timeout':61}, {'max_total_bytes':0}):
            with self.assertRaises(relay.RelayError):
                relay.LoopbackRelay('172.25.0.2',3900,lambda:('172.25.0.2',3900),**bounds)


if __name__ == '__main__':
    unittest.main()
