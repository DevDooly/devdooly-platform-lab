"""Render a stopped, credential-free Kubernetes proposal. Never contacts Kubernetes."""
import argparse
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parent
NAMESPACE = "platform-lab-iceberg-plan2-20261016"
LABELS = {"devdooly.io/purpose": "iceberg-jdbc-trial", "devdooly.io/operation": "20261016-plan2"}
TRINO_IMAGE = "docker.io/trinodb/trino@sha256:db58cc93e593a2706553745f276bb119c9810e69918be56ecde088ba7ccb0534"
POSTGRES_IMAGE = "docker.io/library/postgres@sha256:3645570cccdfa447589da9f57dd740faa29b30938e861289a5574b6ca6b03826"


def metadata(name, role=None, namespace=True):
    labels = dict(LABELS)
    if role:
        labels["app.kubernetes.io/component"] = role
    value = {"name": name, "labels": labels}
    if namespace:
        value["namespace"] = NAMESPACE
    return value


def selector(role):
    return {"matchLabels": {**LABELS, "app.kubernetes.io/component": role}}


def resource(kind, name, spec=None, role=None, api="v1", **extra):
    result = {"apiVersion": api, "kind": kind, "metadata": metadata(name, role, kind != "Namespace"), **extra}
    if spec is not None:
        result["spec"] = spec
    return result


def secret_env(name, secret, key):
    return {"name": name, "valueFrom": {"secretKeyRef": {"name": secret, "key": key}}}


def pod_spec(role, uid, container, volumes):
    return {"automountServiceAccountToken": False, "enableServiceLinks": False, "serviceAccountName": "iceberg-trial", "terminationGracePeriodSeconds": 300,
            "securityContext": {"runAsNonRoot": True, "runAsUser": uid, "runAsGroup": uid, "fsGroup": uid,
                                "fsGroupChangePolicy": "OnRootMismatch", "seccompProfile": {"type": "RuntimeDefault"}},
            "containers": [container], "volumes": volumes, "nodeSelector": {"kubernetes.io/arch": "amd64", "kubernetes.io/os": "linux"}}


def security():
    return {"allowPrivilegeEscalation": False, "readOnlyRootFilesystem": True, "capabilities": {"drop": ["ALL"]}}


def resources(cpu, memory, request_cpu, request_memory):
    return {"requests": {"cpu": request_cpu, "memory": request_memory, "ephemeral-storage": "256Mi"},
            "limits": {"cpu": cpu, "memory": memory, "ephemeral-storage": "1Gi"}}


def configuration():
    catalog = """connector.name=iceberg
iceberg.catalog.type=jdbc
iceberg.jdbc-catalog.driver-class=org.postgresql.Driver
iceberg.jdbc-catalog.connection-url=jdbc:postgresql://postgres:5432/iceberg_lab?connectTimeout=5&socketTimeout=30&ApplicationName=phase6-trino
iceberg.jdbc-catalog.connection-user=iceberg_catalog
iceberg.jdbc-catalog.connection-password=${ENV:CATALOG_PASSWORD}
iceberg.jdbc-catalog.catalog-name=phase6
iceberg.jdbc-catalog.schema-version=V1
iceberg.jdbc-catalog.default-warehouse-dir=s3://${ENV:S3_BUCKET}/warehouse/phase6
fs.s3.enabled=true
s3.endpoint=${ENV:S3_ENDPOINT}
s3.region=garage
s3.path-style-access=true
s3.aws-access-key=${ENV:S3_ACCESS_KEY}
s3.aws-secret-key=${ENV:S3_SECRET_KEY}
s3.auth-type=DEFAULT
s3.streaming.part-size=5MB
s3.max-connections=8
s3.socket-connect-timeout=5s
s3.socket-timeout=15s
s3.max-error-retries=1
s3.retry-mode=STANDARD
"""
    return {
        "config.properties": """coordinator=true
node-scheduler.include-coordinator=true
http-server.http.port=8080
discovery.uri=http://127.0.0.1:8080
query.max-memory=256MB
query.max-memory-per-node=256MB
query.max-total-memory=512MB
memory.heap-headroom-per-node=512MB
query.max-run-time=30s
query.max-execution-time=30s
retry-policy=NONE
task.concurrency=1
task.max-worker-threads=2
""",
        "node.properties": "node.environment=phase6_lab\nnode.id=phase6-jdbc-single\nnode.data-dir=/data/trino\n",
        "jvm.config": "-server\n-Xms512m\n-Xmx2g\n-XX:+UseG1GC\n-XX:G1HeapRegionSize=8M\n-XX:+ExitOnOutOfMemoryError\n-XX:ReservedCodeCacheSize=128M\n-Djdk.attach.allowAttachSelf=true\n-Djdk.nio.maxCachedBufferSize=2000000\n-Djava.io.tmpdir=/tmp\n",
        "log.properties": "io.trino=INFO\n",
        "iceberg.properties": catalog,
        "resource-groups.properties": "resource-groups.configuration-manager=file\nresource-groups.config-file=/etc/trino/resource-groups.json\n",
        "resource-groups.json": json.dumps({"rootGroups": [{"name": "lab", "softMemoryLimit": "256MB", "hardConcurrencyLimit": 1, "maxQueued": 0}],
                                            "selectors": [{"user": "lab_operator", "group": "lab"}]}) + "\n",
    }


def postgres_init():
    # Password is read by the private PostgreSQL bootstrap session from a mounted
    # Secret file. It never appears as an argv value or public SQL literal.
    ddl = (ROOT / "sql/initialize-jdbc-v1.sql").read_text("utf-8")
    return """#!/bin/sh
set -eu
psql --no-psqlrc --set=ON_ERROR_STOP=1 --username=lab_bootstrap --dbname=iceberg_lab <<'SQL'
SELECT format('CREATE ROLE iceberg_catalog LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE PASSWORD %L', pg_read_file('/run/phase6-secrets/catalog-password')) \\gexec
ALTER DATABASE iceberg_lab OWNER TO iceberg_catalog;
REVOKE CREATE ON SCHEMA public FROM PUBLIC;
ALTER SCHEMA public OWNER TO iceberg_catalog;
SET ROLE iceberg_catalog;
""" + ddl + "\nSQL\n"


def build_plan():
    config = configuration()
    result = [resource("Namespace", NAMESPACE),
              resource("ResourceQuota", "bounded-trial", {"hard": {"pods": "2", "persistentvolumeclaims": "2", "requests.storage": "3Gi",
                       "requests.cpu": "1", "requests.memory": "3Gi", "limits.cpu": "1500m", "limits.memory": "5Gi", "services": "2", "secrets": "2", "configmaps": "3"}}),
              resource("ServiceAccount", "iceberg-trial", automountServiceAccountToken=False),
              resource("ConfigMap", "trino-config", data=config),
              resource("ConfigMap", "postgres-init", data={"01-catalog.sh": postgres_init()})]
    for name, amount in (("postgres-data", "2Gi"), ("trino-data", "1Gi")):
        result.append(resource("PersistentVolumeClaim", name, {"accessModes": ["ReadWriteOnce"], "storageClassName": "local-path",
                      "resources": {"requests": {"storage": amount}}}))
    pg_container = {"name": "postgres", "image": POSTGRES_IMAGE, "imagePullPolicy": "IfNotPresent",
        "args": ["postgres", "-c", "shared_buffers=128MB", "-c", "max_connections=10", "-c", "max_worker_processes=2",
                 "-c", "max_parallel_workers=2", "-c", "fsync=on", "-c", "synchronous_commit=on", "-c", "full_page_writes=on",
                 "-c", "log_statement=none", "-c", "statement_timeout=30000", "-c", "lock_timeout=5000"],
        "securityContext": security(), "resources": resources("500m", "1Gi", "250m", "512Mi"),
        "env": [{"name": "POSTGRES_USER", "value": "lab_bootstrap"}, {"name": "POSTGRES_DB", "value": "iceberg_lab"},
                {"name": "POSTGRES_PASSWORD_FILE", "value": "/run/phase6-secrets/bootstrap-password"},
                {"name": "POSTGRES_INITDB_ARGS", "value": "--encoding=UTF8 --locale=C --auth-host=scram-sha-256"},
                {"name": "PGDATA", "value": "/var/lib/postgresql/data/pgdata"}],
        "ports": [{"name": "postgres", "containerPort": 5432}],
        "volumeMounts": [{"name": "data", "mountPath": "/var/lib/postgresql/data"}, {"name": "init", "mountPath": "/docker-entrypoint-initdb.d", "readOnly": True},
                         {"name": "secrets", "mountPath": "/run/phase6-secrets", "readOnly": True}, {"name": "run", "mountPath": "/var/run/postgresql"}, {"name": "tmp", "mountPath": "/tmp"}, {"name": "shm", "mountPath": "/dev/shm"}],
        "startupProbe": {"exec": {"command": ["pg_isready", "-U", "lab_bootstrap", "-d", "iceberg_lab"]}, "periodSeconds": 2, "failureThreshold": 60, "timeoutSeconds": 2},
        "readinessProbe": {"exec": {"command": ["pg_isready", "-U", "lab_bootstrap", "-d", "iceberg_lab"]}, "periodSeconds": 5, "timeoutSeconds": 2}}
    pg_volumes = [{"name": "data", "persistentVolumeClaim": {"claimName": "postgres-data"}},
                  {"name": "init", "configMap": {"name": "postgres-init", "defaultMode": 0o444}},
                  {"name": "secrets", "secret": {"secretName": "iceberg-postgres-credentials", "defaultMode": 0o440}},
                  {"name": "run", "emptyDir": {"sizeLimit": "16Mi"}}, {"name": "tmp", "emptyDir": {"sizeLimit": "64Mi"}},
                  {"name": "shm", "emptyDir": {"medium": "Memory", "sizeLimit": "128Mi"}}]
    pg_spec = {"replicas": 0, "serviceName": "postgres", "selector": selector("postgres"),
               "template": {"metadata": {"labels": metadata("postgres", "postgres")["labels"]}, "spec": pod_spec("postgres", 999, pg_container, pg_volumes)}}
    result.append(resource("StatefulSet", "postgres", pg_spec, "postgres", "apps/v1"))
    mounts = [{"key": name, "path": "catalog/iceberg.properties" if name == "iceberg.properties" else name} for name in config]
    trino_container = {"name": "trino", "image": TRINO_IMAGE, "imagePullPolicy": "IfNotPresent", "securityContext": security(),
        "resources": resources("1", "4Gi", "500m", "2Gi"), "ports": [{"name": "http", "containerPort": 8080}],
        "env": [secret_env("CATALOG_PASSWORD", "iceberg-postgres-credentials", "catalog-password"),
                secret_env("S3_ENDPOINT", "iceberg-s3-credentials", "endpoint"), secret_env("S3_BUCKET", "iceberg-s3-credentials", "bucket"),
                secret_env("S3_ACCESS_KEY", "iceberg-s3-credentials", "access-key"), secret_env("S3_SECRET_KEY", "iceberg-s3-credentials", "secret-key")],
        "volumeMounts": [{"name": "data", "mountPath": "/data/trino"}, {"name": "config", "mountPath": "/etc/trino", "readOnly": True}, {"name": "tmp", "mountPath": "/tmp"}],
        "startupProbe": {"exec": {"command": ["/usr/lib/trino/bin/health-check"]}, "periodSeconds": 2, "failureThreshold": 60, "timeoutSeconds": 2},
        "readinessProbe": {"exec": {"command": ["/usr/lib/trino/bin/health-check"]}, "periodSeconds": 5, "timeoutSeconds": 2}}
    trino_volumes = [{"name": "data", "persistentVolumeClaim": {"claimName": "trino-data"}},
                     {"name": "config", "configMap": {"name": "trino-config", "items": mounts}}, {"name": "tmp", "emptyDir": {"sizeLimit": "256Mi"}}]
    trino_spec = {"replicas": 0, "strategy": {"type": "Recreate"}, "selector": selector("trino"),
                  "template": {"metadata": {"labels": metadata("trino", "trino")["labels"]}, "spec": pod_spec("trino", 1000, trino_container, trino_volumes)}}
    result.append(resource("Deployment", "trino", trino_spec, "trino", "apps/v1"))
    for role, port in (("postgres", 5432), ("trino", 8080)):
        result.append(resource("Service", role, {"type": "ClusterIP", "selector": selector(role)["matchLabels"], "ports": [{"name": "postgres" if role == "postgres" else "http", "port": port, "targetPort": port, "protocol": "TCP"}]}))
    result.append(resource("NetworkPolicy", "default-deny", {"podSelector": {}, "policyTypes": ["Ingress", "Egress"]}, api="networking.k8s.io/v1"))
    result.append(resource("NetworkPolicy", "postgres-from-trino", {"podSelector": selector("postgres"), "policyTypes": ["Ingress"],
                  "ingress": [{"from": [{"podSelector": selector("trino")}], "ports": [{"protocol": "TCP", "port": 5432}]}]}, api="networking.k8s.io/v1"))
    result.append(resource("NetworkPolicy", "trino-outbound", {"podSelector": selector("trino"), "policyTypes": ["Egress"], "egress": [
        {"to": [{"podSelector": selector("postgres")}], "ports": [{"protocol": "TCP", "port": 5432}]},
        {"to": [{"namespaceSelector": {"matchLabels": {"kubernetes.io/metadata.name": "platform-lab"}},
                  "podSelector": {"matchLabels": {"app.kubernetes.io/component": "garage"}}}], "ports": [{"protocol": "TCP", "port": 3900}]},
        {"to": [{"namespaceSelector": {"matchLabels": {"kubernetes.io/metadata.name": "kube-system"}}, "podSelector": {"matchLabels": {"k8s-app": "kube-dns"}}}],
         "ports": [{"protocol": "UDP", "port": 53}, {"protocol": "TCP", "port": 53}]}]}, api="networking.k8s.io/v1"))
    return {"apiVersion": "v1", "kind": "List", "items": result}


def binding_pods():
    # Optional once-only binders for WaitForFirstConsumer storage classes. No SQL,
    # credentials, network access or file writes; record UID/PV paths before deletion.
    objects = []
    for role, uid, image in (("postgres", 999, POSTGRES_IMAGE), ("trino", 1000, TRINO_IMAGE)):
        container = {"name": "bind", "image": image, "imagePullPolicy": "IfNotPresent", "command": ["/bin/bash", "-c", "exit 0"],
                     "securityContext": security(), "resources": resources("100m", "64Mi", "100m", "64Mi"),
                     "volumeMounts": [{"name": "data", "mountPath": "/volume"}]}
        spec = pod_spec("binding", uid, container, [{"name": "data", "persistentVolumeClaim": {"claimName": role + "-data"}}])
        spec["restartPolicy"] = "Never"
        objects.append(resource("Pod", "bind-" + role, spec, "binding"))
    return {"apiVersion": "v1", "kind": "List", "items": objects}


def main():
    parser = argparse.ArgumentParser(description=__doc__); parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    with args.output.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(build_plan(), stream, indent=2); stream.write("\n")
    print(json.dumps({"status": "PREPARED_NOT_RUN", "namespace": NAMESPACE, "resources": len(build_plan()["items"]),
                      "workloadReplicas": 0, "serverContacted": False, "secretsIncluded": False}))


if __name__ == "__main__":
    main()
