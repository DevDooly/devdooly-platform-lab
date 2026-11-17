#!/usr/bin/env bash
# Install or verify the private, single-node Platform Lab monitoring stack.
set -Eeuo pipefail
set +x
umask 077

dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)
kubectl_bin=${KUBECTL:-kubectl}
ns=platform-lab-monitoring
scopes=(platform-lab jenkins argocd "$ns")
components=(kube-state-metrics prometheus loki alloy grafana)

usage() {
  printf 'Usage: %s [--apply|--verify]\n' "$0"
}

mode=${1:---apply}
if [[ $# -gt 1 ]]; then
  usage >&2
  exit 2
fi
case "$mode" in
  --apply|--verify) ;;
  --help|-h) usage; exit 0 ;;
  *) usage >&2; exit 2 ;;
esac

for tool in "$kubectl_bin" curl python3; do
  command -v "$tool" >/dev/null || { printf 'Required command unavailable: %s\n' "$tool" >&2; exit 1; }
done

work=$(mktemp -d)
forward_pid=
cleanup() {
  if [[ -n "$forward_pid" ]]; then
    kill "$forward_pid" 2>/dev/null || true
    wait "$forward_pid" 2>/dev/null || true
  fi
  rm -rf -- "$work"
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

kubectl() {
  command "$kubectl_bin" "$@"
}

kubectl get namespace platform-lab jenkins argocd -o name >/dev/null
owner=$(kubectl get namespace "$ns" --ignore-not-found -o go-template='{{index .metadata.labels "app.kubernetes.io/part-of"}}')
if [[ -z "$owner" ]]; then
  if [[ "$mode" != --apply ]]; then
    printf 'Monitoring namespace has not been installed.\n' >&2
    exit 1
  fi
  kubectl create -f "$dir/namespace.yaml"
elif [[ "$owner" != "$ns" ]]; then
  printf 'Monitoring namespace is not marked as owned by this project.\n' >&2
  exit 1
fi

verify() {
  local component port password deadline
  for component in "${components[@]}"; do
    kubectl -n "$ns" rollout status "deployment/$component" --timeout=240s
  done
  kubectl -n "$ns" port-forward --address 127.0.0.1 service/grafana :3000 >"$work/port-forward.log" 2>&1 &
  forward_pid=$!
  deadline=$((SECONDS + 20))
  while (( SECONDS < deadline )); do
    port=$(sed -nE 's/^Forwarding from 127\.0\.0\.1:([0-9]+) -> 3000$/\1/p' "$work/port-forward.log")
    [[ "$port" =~ ^[0-9]+$ ]] && break
    kill -0 "$forward_pid" 2>/dev/null || break
    sleep 1
  done
  if [[ ! "$port" =~ ^[0-9]+$ ]]; then
    printf 'Grafana loopback forwarding did not become ready.\n' >&2
    return 1
  fi
  password=$(kubectl -n "$ns" get secret grafana-admin -o jsonpath='{.data.admin-password}' | base64 --decode)
  if [[ ! "$password" =~ ^[0-9a-f]{64}$ ]]; then
    printf 'Grafana administrator Secret has an invalid value or is missing.\n' >&2
    return 1
  fi
  printf 'machine 127.0.0.1 login admin password %s\n' "$password" >"$work/netrc"
  unset password

  local base="http://127.0.0.1:$port"
  local prom="$base/api/datasources/proxy/uid/platform-lab-prometheus/api/v1/query"
  local loki="$base/api/datasources/proxy/uid/platform-lab-loki/loki/api/v1/query_range"
  local options=(--netrc-file "$work/netrc" --silent --fail --max-time 5)
  deadline=$((SECONDS + 150))
  while (( SECONDS < deadline )); do
    # The router logs Grafana's health request so the verification can read it from Loki.
    if curl "${options[@]}" "$base/api/health" >"$work/grafana.json" &&
       curl "${options[@]}" "$base/api/dashboards/uid/platform-lab-services" >"$work/dashboard.json" &&
       curl "${options[@]}" --get --data-urlencode 'query=up{job="kube-state-metrics"}' "$prom" >"$work/up.json" &&
       curl "${options[@]}" --get --data-urlencode 'query=platform_lab:workload_state' "$prom" >"$work/workloads.json" &&
       curl "${options[@]}" --get --data-urlencode 'query={namespace="platform-lab-monitoring",container="grafana"}' \
         --data-urlencode 'limit=10' "$loki" >"$work/logs.json" &&
       python3 - "$work" <<'PY'
import json
import sys
from pathlib import Path

root = Path(sys.argv[1])


def read(name):
    return json.loads((root / f"{name}.json").read_text())


try:
    assert read("grafana")["database"] == "ok"
    assert read("dashboard")["dashboard"]["uid"] == "platform-lab-services"
    up = read("up")["data"]["result"]
    assert len(up) == 1 and up[0]["value"][1] == "1"
    workloads = read("workloads")["data"]["result"]
    observed = {(row["metric"]["namespace"], row["metric"]["kind"]) for row in workloads}
    assert {namespace for namespace, _ in observed} == {
        "platform-lab", "jenkins", "argocd", "platform-lab-monitoring"
    }
    assert {
        ("platform-lab", "Deployment"), ("platform-lab", "StatefulSet")
    }.issubset(observed)
    logs = read("logs")["data"]["result"]
    assert any(row["stream"]["namespace"] == "platform-lab-monitoring"
               and row["stream"]["container"] == "grafana" and row["values"] for row in logs)
except (AssertionError, KeyError, TypeError, ValueError):
    sys.exit(1)
print(f"Dashboard, four namespaces ({len(workloads)} workloads), and Grafana container log verified.")
PY
    then
      return 0
    fi
    sleep 5
  done
  printf 'Monitoring did not verify through Grafana (health, dashboard, metrics, or Loki logs).\n' >&2
  return 1
}

if [[ "$mode" == --apply ]]; then
  if [[ -z "$(kubectl -n "$ns" get secret grafana-admin --ignore-not-found -o name)" ]]; then
    python3 -c 'import secrets; print(secrets.token_hex(32), end="")' >"$work/admin-password"
    kubectl -n "$ns" create secret generic grafana-admin --from-file="admin-password=$work/admin-password"
  fi
  for scope in "${scopes[@]}"; do
    kubectl -n "$scope" apply -f "$dir/access.yaml"
  done
  kubectl apply -k "$dir"
fi

verify
printf 'Grafana is available through the port-forward in infra/lab-monitoring/README.md.\n'
