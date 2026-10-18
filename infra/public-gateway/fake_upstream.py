"""Public synthetic HTTP fixture only; no DB/Kafka/S3/runtime clients."""
import json
import socket
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

LOCK = threading.Lock()
STATE = {"mode": "ok", "records": []}
MODES = {"ok", "redirect", "error", "close", "slow", "hold"}


class Fixture(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *args):
        pass

    def respond(self, status, value, upstream_headers=False):
        raw = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("Connection", "close")
        if upstream_headers:
            # Must be hidden/ignored by the gateway even on an otherwise valid 200.
            self.send_header("Set-Cookie", "synthetic-fixture=1")
            self.send_header("Location", "http://private.invalid/never-follow")
            self.send_header("Refresh", "0; url=http://private.invalid/never-follow")
            self.send_header("X-Accel-Redirect", "/private-fixture")
            self.send_header("Cache-Control", "public, max-age=3600")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Access-Control-Allow-Credentials", "true")
        self.end_headers()
        try:
            self.wfile.write(raw)
        except (BrokenPipeError, ConnectionResetError):
            pass
        self.close_connection = True

    def do_POST(self):
        # Fixture control is reachable only within the owned internal network.
        if self.path != "/__fixture__/mode":
            self.respond(404, {"fixture": True})
            return
        size = int(self.headers.get("Content-Length", "0"))
        if not 0 < size <= 128:
            self.respond(400, {"fixture": True})
            return
        try:
            value = json.loads(self.rfile.read(size))
            if set(value) != {"mode"} or value["mode"] not in MODES:
                raise ValueError()
        except (ValueError, TypeError):
            self.respond(400, {"fixture": True})
            return
        with LOCK:
            STATE["mode"] = value["mode"]
        self.respond(200, {"fixture": True})

    def do_GET(self):
        if self.path == "/__fixture__/stats":
            with LOCK:
                value = {"count": len(STATE["records"]), "records": list(STATE["records"])}
            self.respond(200, value)
            return
        length = int(self.headers.get("Content-Length", "0"))
        if not 0 <= length <= 1024:
            self.respond(400, {"fixture": True})
            return
        body = self.rfile.read(length)
        row = {"method": self.command, "path": self.path,
               "headers": {key.lower(): value for key, value in self.headers.items()},
               "bodyBytes": len(body)}
        with LOCK:
            if len(STATE["records"]) >= 512:
                self.respond(503, {"fixture": True})
                return
            STATE["records"].append(row)
            mode = STATE["mode"]
        if mode == "close":
            self.close_connection = True
            self.connection.shutdown(socket.SHUT_RDWR)
            self.connection.close()
            return
        if mode == "slow":
            time.sleep(13)
        if mode == "hold":
            time.sleep(2)
        status = {"redirect": 302, "error": 500}.get(mode, 200)
        self.respond(status, {"fixture": True, "kind": "public-gateway-fixture", "request": row}, True)


if __name__ == "__main__":
    server = ThreadingHTTPServer(("0.0.0.0", 8080), Fixture)
    server.daemon_threads = True
    server.serve_forever(poll_interval=0.2)
