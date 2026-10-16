"""Exact native-plan configuration function only; no K8s resources or executor."""
import json


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
