"""Bounded byte-transparent loopback relay; no payload inspection or logging."""
import ipaddress
import selectors
import socket
import threading
import time


class RelayError(RuntimeError):
    pass


class LoopbackRelay:
    def __init__(self, target_ip, target_port, verify_target, *, lifetime=360,
                 max_active=16, max_connections=512, max_connection_bytes=16*1024**2,
                 max_total_bytes=64*1024**2, idle_timeout=60, connection_timeout=180):
        address = ipaddress.ip_address(target_ip)
        if (address.version != 4 or not address.is_private or address.is_loopback
                or address.is_unspecified or address.is_multicast or target_port not in (3306, 3900)):
            raise RelayError('ONLY_VERIFIED_PRIVATE_IPV4_FIXED_TARGET')
        bounds = ((lifetime, 360), (max_active, 16), (max_connections, 512),
                  (max_connection_bytes, 16*1024**2), (max_total_bytes, 64*1024**2),
                  (idle_timeout, 60), (connection_timeout, 180))
        if any(isinstance(value, bool) or not isinstance(value, (int, float))
               or not 0 < value <= upper for value, upper in bounds):
            raise RelayError('FINITE_POSITIVE_RELAY_BOUNDS_REQUIRED')
        if any(type(value) is not int for value in (max_active, max_connections, max_connection_bytes, max_total_bytes)):
            raise RelayError('INTEGER_RELAY_COUNTS_REQUIRED')
        self.target = (str(address), target_port)
        self.verify_target = verify_target
        self.lifetime, self.max_active, self.max_connections = lifetime, max_active, max_connections
        self.max_connection_bytes, self.max_total_bytes = max_connection_bytes, max_total_bytes
        self.idle_timeout, self.connection_timeout = idle_timeout, connection_timeout
        self.lock = threading.Lock()
        self.stop_event = threading.Event()
        self.listener = None
        self.accept_thread = None
        self.workers = set()
        self.sockets = set()
        self.started = False
        self.stopped = False
        self.accepted = self.connected = self.closed = self.bytes_read = self.peak_active = 0
        self.failure = None
        self.positive_control = False
        self.port = None

    def fail(self, code):
        with self.lock:
            if self.failure is None:
                self.failure = code
        self.stop_event.set()

    def start(self):
        if self.started or self.stopped:
            raise RelayError('RELAY_SINGLE_START_REQUIRED')
        if self.verify_target() != self.target:
            raise RelayError('EXACT_VERIFIED_TARGET_REQUIRED')
        listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            listener.bind(('127.0.0.1', 0))
            listener.listen(self.max_active)
            listener.settimeout(.2)
            if listener.getsockname()[0] != '127.0.0.1':
                raise RelayError('ONLY_LOOPBACK_LISTENER_ALLOWED')
            self.listener = listener
            self.port = listener.getsockname()[1]
            self.deadline = time.monotonic() + self.lifetime
            self.started = True
            self.accept_thread = threading.Thread(target=self.accept_loop, name='owned-loopback-relay', daemon=False)
            self.accept_thread.start()
        except Exception:
            listener.close()
            raise
        return self.port

    def accept_loop(self):
        while not self.stop_event.is_set():
            if time.monotonic() >= self.deadline:
                self.fail('RELAY_LIFETIME_BOUND_EXCEEDED')
                break
            try:
                client, peer = self.listener.accept()
            except socket.timeout:
                continue
            except OSError:
                if not self.stop_event.is_set():
                    self.fail('RELAY_LISTENER_UNOBSERVED')
                break
            with self.lock:
                allowed = (peer[0] == '127.0.0.1' and len(self.workers) < self.max_active
                           and self.accepted < self.max_connections)
                if allowed:
                    self.accepted += 1
                    worker = threading.Thread(target=self.forward, args=(client,), name='owned-relay-connection', daemon=False)
                    self.workers.add(worker)
                    self.sockets.add(client)
                    self.peak_active = max(self.peak_active, len(self.workers))
            if not allowed:
                client.close()
                self.fail('RELAY_CONNECTION_BOUND_EXCEEDED')
                break
            worker.start()

    def forward(self, client):
        upstream = None
        selector = None
        try:
            try:
                target = self.verify_target()
            except Exception:
                self.fail('RELAY_TARGET_SCOPE_UNVERIFIED')
                return
            if target != self.target:
                self.fail('RELAY_TARGET_SCOPE_CHANGED')
                return
            try:
                upstream = socket.create_connection(self.target, timeout=3)
            except OSError:
                self.fail('RELAY_TARGET_CONNECT_FAILED')
                return
            with self.lock:
                self.connected += 1
                self.sockets.add(upstream)
            client.setblocking(False)
            upstream.setblocking(False)
            peers = {client: upstream, upstream: client}
            pending = {client: bytearray(), upstream: bytearray()}
            read_open = {client: True, upstream: True}
            write_closed = set()
            selector = selectors.DefaultSelector()
            started = touched = time.monotonic()
            connection_bytes = 0
            while not self.stop_event.is_set():
                now = time.monotonic()
                if now >= self.deadline or now-started >= self.connection_timeout or now-touched >= self.idle_timeout:
                    self.fail('RELAY_TIME_BOUND_EXCEEDED')
                    break
                for sock, peer in peers.items():
                    if not read_open[sock] and not pending[peer] and peer not in write_closed:
                        try:
                            peer.shutdown(socket.SHUT_WR)
                        except OSError:
                            pass
                        write_closed.add(peer)
                    events = (selectors.EVENT_READ if read_open[sock] and len(pending[peer]) < 65536 else 0)
                    if pending[sock]:
                        events |= selectors.EVENT_WRITE
                    try:
                        selector.get_key(sock)
                    except KeyError:
                        if events:
                            selector.register(sock, events)
                    else:
                        if events:
                            selector.modify(sock, events)
                        else:
                            selector.unregister(sock)
                if not any(read_open.values()) and not any(pending.values()):
                    break
                for key, events in selector.select(.2):
                    sock, peer = key.fileobj, peers[key.fileobj]
                    if events & selectors.EVENT_READ:
                        try:
                            # Nonblocking recv under the short accounting lock keeps
                            # concurrent readers within the shared budget (+1 byte
                            # needed to observe an attempted overflow).
                            with self.lock:
                                if self.stop_event.is_set():
                                    break
                                remaining = min(self.max_connection_bytes-connection_bytes,
                                                self.max_total_bytes-self.bytes_read)
                                data = sock.recv(min(16384, 65536-len(pending[peer]), max(1, remaining+1)))
                                connection_bytes += len(data)
                                self.bytes_read += len(data)
                                exceeded = connection_bytes > self.max_connection_bytes or self.bytes_read > self.max_total_bytes
                                if exceeded:
                                    self.failure = self.failure or 'RELAY_BYTE_BOUND_EXCEEDED'
                                    self.stop_event.set()
                        except BlockingIOError:
                            continue
                        if not data:
                            read_open[sock] = False
                        else:
                            touched = time.monotonic()
                            if exceeded:
                                break
                            pending[peer].extend(data)
                    if events & selectors.EVENT_WRITE and pending[sock]:
                        try:
                            count = sock.send(pending[sock])
                        except BlockingIOError:
                            continue
                        del pending[sock][:count]
                        if count:
                            touched = time.monotonic()
        except OSError:
            # Clients may close/abort a legitimate SDK read. No payload/message is
            # inspected, logged or turned into an invented application outcome.
            pass
        except Exception:
            self.fail('RELAY_UNOBSERVED_TRANSPORT_STATE')
        finally:
            if selector is not None:
                selector.close()
            for sock in (client, upstream):
                if sock is not None:
                    try:
                        sock.shutdown(socket.SHUT_RDWR)
                    except OSError:
                        pass
                    sock.close()
            with self.lock:
                self.sockets.discard(client)
                self.sockets.discard(upstream)
                self.workers.discard(threading.current_thread())
                self.closed += 1

    def probe(self):
        if not self.started or self.stopped:
            raise RelayError('RUNNING_RELAY_REQUIRED_FOR_CONTROL')
        with self.lock:
            before = self.connected
        # Pure TCP: do not parse or emit S3/SQL data or put credentials on a probe.
        with socket.create_connection(('127.0.0.1', self.port), timeout=3):
            until = min(self.deadline, time.monotonic()+8)
            while time.monotonic() < until:
                with self.lock:
                    connected, failure = self.connected, self.failure
                if failure is not None:
                    break
                if connected > before:
                    self.positive_control = True
                    return
                time.sleep(.02)
        raise RelayError('OWNED_TARGET_TCP_POSITIVE_CONTROL_FAILED')

    def close(self):
        self.stop_event.set()
        if self.listener is not None:
            self.listener.close()
        with self.lock:
            sockets = list(self.sockets)
        for sock in sockets:
            try:
                sock.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
        until = time.monotonic()+12
        if self.accept_thread is not None:
            self.accept_thread.join(max(0, until-time.monotonic()))
        with self.lock:
            workers = list(self.workers)
        for thread in workers:
            thread.join(max(0, until-time.monotonic()))
        with self.lock:
            self.stopped = not self.workers and (self.accept_thread is None or not self.accept_thread.is_alive())
        return self.stopped

    def summary(self):
        with self.lock:
            return {'schemaVersion': 1, 'scope': 'OWNED_INTERNAL_BRIDGE_HOST_LOOPBACK_TCP_RELAY',
                    'started': self.started, 'stoppedAndJoined': self.stopped,
                    'loopbackListenerVerified': self.started, 'tcpPositiveControlPassed': self.positive_control,
                    'acceptedConnections': self.accepted, 'targetConnections': self.connected,
                    'closedConnections': self.closed, 'observedPeakActiveConnections': self.peak_active,
                    'observedBidirectionalBytesRead': self.bytes_read, 'failureCode': self.failure,
                    'payloadInspectedOrLogged': False, 'maxActiveConnections': self.max_active,
                    'maxConnections': self.max_connections, 'maxConnectionBytes': self.max_connection_bytes,
                    'maxTotalBytes': self.max_total_bytes, 'maxLifetimeSeconds': self.lifetime,
                    'idleTimeoutSeconds': self.idle_timeout, 'connectionTimeoutSeconds': self.connection_timeout}
