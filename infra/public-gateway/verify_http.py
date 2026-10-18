"""Actual HTTP probes inside the fake container, against the owned Nginx only."""
import concurrent.futures
import http.client
import json
import sys
import time

ORIGIN = "https://devdooly.github.io"
CHECKS = 0
PHASE = "START"
CASE = "START"
OBSERVED_STATUS = None
UPSTREAM_DELTA = None


class CheckFailed(Exception):
    pass


def need(value):
    global CHECKS
    if not value:
        raise CheckFailed()
    CHECKS += 1


def request(path, *, method="GET", headers=None, body=None, fixture=False, timeout=18):
    host = "127.0.0.1" if fixture else "gateway"
    connection = http.client.HTTPConnection(host, 8080, timeout=timeout)
    try:
        connection.request(method, path, body=body, headers=headers or {})
        response = connection.getresponse()
        raw = response.read(262145)
        need(len(raw) <= 262144)
        return response.status, {key.lower(): value for key, value in response.getheaders()}, raw
    finally:
        connection.close()


def stats():
    status, _, raw = request("/__fixture__/stats", fixture=True)
    need(status == 200)
    return json.loads(raw)


def mode(value):
    status, _, _ = request("/__fixture__/mode", method="POST", fixture=True,
                           body=json.dumps({"mode": value}), headers={"Content-Type": "application/json"})
    need(status == 200)


def begin_case(case):
    global CASE, OBSERVED_STATUS, UPSTREAM_DELTA
    CASE, OBSERVED_STATUS, UPSTREAM_DELTA = case, None, None


def record_observation(status, before=None):
    global OBSERVED_STATUS, UPSTREAM_DELTA
    if type(status) is not int or not 100 <= status <= 599:
        raise CheckFailed()
    OBSERVED_STATUS = status
    if before is not None:
        delta = stats()["count"] - before
        if type(delta) is not int or not -512 <= delta <= 512:
            raise CheckFailed()
        UPSTREAM_DELTA = delta


def public_headers(headers, origin=True):
    need(headers.get("cache-control") == "no-store")
    need(headers.get("vary") == "Origin")
    need(headers.get("access-control-allow-origin") == (ORIGIN if origin else None))
    need("access-control-allow-credentials" not in headers)
    need(all(key not in headers for key in ("set-cookie", "location", "refresh", "x-accel-redirect")))


def good(path, headers=None):
    actual_headers = {"Origin": ORIGIN, "Accept": "application/json", "X-Forwarded-For": "192.0.2.123"}
    if headers is not None:
        actual_headers = headers
    status, output_headers, raw = request(path, headers=actual_headers)
    record_observation(status)
    need(status == 200)
    public_headers(output_headers, actual_headers.get("Origin") == ORIGIN)
    row = json.loads(raw)["request"]
    need(row["method"] == "GET" and row["path"] == path and row["bodyBytes"] == 0)
    need(row["headers"] == {"accept": "application/json", "connection": "close", "host": "api.platform-lab.svc.cluster.local"})


def reject(path, expected, **kwargs):
    before = stats()["count"]
    status, headers, raw = request(path, **kwargs)
    record_observation(status, before)
    need(status == expected)
    if expected == 405:
        need(headers.get("allow") == "GET")
    need(UPSTREAM_DELTA == 0)
    need(json.loads(raw)["kind"] == "public-gateway-error")
    need(headers.get("cache-control") == "no-store")


def run():
    global PHASE
    PHASE = "READY"
    begin_case("READY")
    if sys.argv[1:] == ["--ready"]:
        need(stats()["count"] >= 0)
        need(request("/api/platform/summary")[0] == 200)
        return {"passed": True, "phase": "READY", "checks": CHECKS}
    need(not sys.argv[1:])
    PHASE = "ALLOWED_GET"
    begin_case("ALLOWED_GET")
    paths = ["/api/platform/summary", "/api/platform/releases", "/api/demo/runs",
             "/api/jobs/observation", "/api/kafka/observation", "/api/demo/runs/synthetic-v1-seed-42"]
    for path in paths:
        good(path)
        time.sleep(0.55)
    good("/api/demo/runs/" + "a" * 80)
    time.sleep(0.55)
    good("/api/platform/summary", headers={})
    # Nginx variables cannot distinguish an absent header from an empty value.
    # Empty values cannot carry credentials and are never forwarded.
    time.sleep(0.55)
    good("/api/platform/summary", headers={"Content-Length": "0", "Authorization": "", "Cookie": ""})

    PHASE = "DENIED_URI"
    begin_case("DENIED_URI")
    bad_paths = ["/", "/api", "/api/", "/api/jobs", "/api/jobs/start", "/actuator/health", "/metrics",
                 "/__fixture__/stats", "/api/kafka/observation/topics", "/api/platform/summary/",
                 "/api/platform/summary?", "/api/platform/summary?x=1", "/api//platform/summary",
                 "/api/./platform/summary", "/api/private/../platform/summary", "/api/platform/%73ummary",
                 "/api/demo/runs/", "/api/demo/runs/A", "/api/demo/runs/" + "a" * 81,
                 "/api/demo/runs/..", "/api/demo/runs/a%2fb", "/api/demo/runs/a/b", "/API/platform/summary", "/api/Platform/summary", "/api/demo/RUNS"]
    for path in bad_paths:
        reject(path, 404)
    PHASE = "DENIED_METHOD"
    begin_case("DENIED_METHOD")
    for method in ("HEAD", "OPTIONS", "POST", "PUT", "PATCH", "DELETE"):
        begin_case("METHOD_" + method)
        # HEAD has no entity in its response regardless of error_page's JSON body.
        if method == "HEAD":
            before = stats()["count"]
            status, headers, raw = request(paths[0], method=method)
            record_observation(status, before)
            need(status == 405 and headers.get("allow") == "GET" and UPSTREAM_DELTA == 0)
            need(raw == b"" and headers.get("cache-control") == "no-store")
        else:
            reject(paths[0], 405, method=method)
    begin_case("PARSER_TRACE")
    before = stats()["count"]
    status, headers, _ = request(paths[0], method="TRACE")
    record_observation(status, before)
    need(status == 405 and headers.get("allow") == "GET" and UPSTREAM_DELTA == 0)
    for case, target in (("CONNECT_ORIGIN", paths[0]),
                         ("CONNECT_AUTHORITY", "api.platform-lab.svc.cluster.local:8080")):
        begin_case(case)
        before = stats()["count"]
        status, headers, _ = request(target, method="CONNECT")
        record_observation(status, before)
        need(status in {400, 405} and UPSTREAM_DELTA == 0)
        if status == 405:
            need(headers.get("allow") == "GET")
    PHASE = "PARSER_METHOD_REJECTION"
    begin_case("PARSER_METHOD_REJECTION")
    before = stats()["count"]
    status, _, _ = request(paths[0], method="get")
    record_observation(status, before)
    need(status == 400 and UPSTREAM_DELTA == 0)  # native parser body is not asserted
    PHASE = "DENIED_INPUT"
    begin_case("DENIED_INPUT")
    for headers in ({"Authorization": "Bearer synthetic-test"}, {"Cookie": "synthetic-test=1"},
                    {"Content-Type": "application/json"}, {"Transfer-Encoding": "chunked"},
                    {"Expect": "100-continue"}):
        reject(paths[0], 400, headers=headers)
    reject(paths[0], 400, headers={"Content-Length": "1"}, body=b"x")
    for origin in ("null", "https://devdooly.github.io.evil.invalid", "http://devdooly.github.io", "https://devdooly.github.io/",
                   "HTTPS://devdooly.github.io", "https://DevDooly.github.io"):
        reject(paths[0], 403, headers={"Origin": origin})

    PHASE = "RATE"
    begin_case("RATE")
    time.sleep(4)
    with concurrent.futures.ThreadPoolExecutor(max_workers=16) as pool:
        responses = list(pool.map(lambda _: request(paths[0], headers={"Origin": ORIGIN}), range(40)))
    need(any(row[0] == 429 for row in responses))
    need(all(row[0] in {200, 429} for row in responses))
    PHASE = "CONNECTION"
    begin_case("CONNECTION")
    time.sleep(4)
    mode("hold")
    before = stats()["count"]
    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
        pending = [pool.submit(request, paths[0]) for _ in range(6)]
        end = time.monotonic() + 1.5
        while stats()["count"] < before + 6 and time.monotonic() < end:
            time.sleep(0.03)
        need(stats()["count"] == before + 6)
        status, headers, raw = request(paths[0])
        record_observation(status)
        need(status == 429 and json.loads(raw)["code"] == "READ_LIMITED")
        need(all(future.result()[0] == 200 for future in pending))
    mode("ok")

    PHASE = "FAILURE_FALLBACK"
    begin_case("FAILURE_FALLBACK")
    for selected in ("redirect", "error", "close", "slow"):
        begin_case({"redirect": "UPSTREAM_REDIRECT", "error": "UPSTREAM_ERROR",
                    "close": "UPSTREAM_CLOSE", "slow": "UPSTREAM_SLOW"}[selected])
        time.sleep(1)
        mode(selected)
        before = stats()["count"]
        started = time.monotonic()
        status, headers, raw = request(paths[0], headers={"Origin": ORIGIN})
        elapsed = time.monotonic() - started
        record_observation(status, before)
        need(status == 503 and json.loads(raw) == {"kind": "public-gateway-error", "code": "READ_UNAVAILABLE"})
        public_headers(headers)
        need(UPSTREAM_DELTA == 1)  # exactly one attempt, never a retry
        if selected == "slow":
            need(10 <= elapsed <= 17)  # idle timeout, not a claim about whole-response duration
    mode("ok")
    PHASE = "COMPLETE"
    return {"passed": True, "phase": PHASE, "checks": CHECKS, "allowlistedRoutePatterns": 6,
            "deniedUriCases": len(bad_paths), "methodCases": 10, "noHostPorts": True,
            "realNginxHttpExercised": True, "backendWasSyntheticFixture": True,
            "globalMultiPeerLimitIndependentlyExercised": False,
            "failingCase": None, "observedStatus": None, "upstreamDelta": None}


if __name__ == "__main__":
    try:
        result = run()
    except Exception:
        result = {"passed": False, "phase": PHASE, "checks": CHECKS,
                  "failingCase": CASE, "observedStatus": OBSERVED_STATUS, "upstreamDelta": UPSTREAM_DELTA}
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    raise SystemExit(0 if result["passed"] else 1)
