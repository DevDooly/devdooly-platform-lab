"""Pure three-service isolated CI proposal; no ports or deployment targets."""
import re

POSTGRES = 'docker.io/library/postgres@sha256:3645570cccdfa447589da9f57dd740faa29b30938e861289a5574b6ca6b03826'
GARAGE = 'docker.io/dxflrs/garage@sha256:0d7c74fc8ca6fef68a5a941c0e7558c8b1e92ba3588fa7505400e1350456c796'
SPARK = 'docker.io/apache/spark@sha256:0b8f5befe00d258df03b252158b3894b8654390f1958741accf98155539a662a'
POSTGRES_ALIAS = 'postgres.platform-lab-iceberg-20261015.svc.cluster.local'
GARAGE_ALIAS = 'garage.platform-lab.svc.cluster.local'


def plan(local_image):
    if not re.fullmatch(r'spark-isolated-ci:[a-f0-9]{32}', local_image):
        raise ValueError('EXACT_LOCAL_EPHEMERAL_IMAGE_TAG')
    limits = {'read_only': True, 'cap_drop': ['ALL'], 'security_opt': ['no-new-privileges:true'], 'restart': 'no', 'pids_limit': 256}
    return {
        'services': {
            'postgres': {**limits, 'image': POSTGRES, 'platform': 'linux/amd64', 'cpus': 0.5, 'mem_limit': '512m',
                'environment': {'POSTGRES_USER': 'lab_bootstrap', 'POSTGRES_DB': 'iceberg_lab', 'POSTGRES_PASSWORD_FILE': '/run/ci/bootstrap-password'},
                'volumes': ['./postgres-secrets:/run/ci:ro', './postgres-init.sql:/docker-entrypoint-initdb.d/01-catalog.sql:ro', 'postgres-data:/var/lib/postgresql/data'],
                'tmpfs': ['/tmp:size=64m', '/var/run/postgresql:size=16m'],
                # The official entrypoint needs only its documented privilege drop/init capabilities.
                'cap_add': ['CHOWN', 'FOWNER', 'SETUID', 'SETGID', 'DAC_OVERRIDE'],
                'networks': {'trial': {'aliases': [POSTGRES_ALIAS]}}},
            'garage': {**limits, 'image': GARAGE, 'platform': 'linux/amd64', 'user': '1000:1000', 'cpus': 0.5, 'mem_limit': '512m',
                'entrypoint': ['/garage'], 'command': ['-c', '/etc/garage.toml', 'server'],
                'volumes': ['./garage.toml:/etc/garage.toml:ro', 'garage-meta:/var/lib/garage/meta', 'garage-data:/var/lib/garage/data'],
                'tmpfs': ['/tmp:size=32m'], 'networks': {'trial': {'aliases': [GARAGE_ALIAS]}}},
            'spark': {**limits, 'image': local_image, 'platform': 'linux/amd64', 'user': '185:185', 'cpus': 1, 'mem_limit': '3g',
                'command': ['/usr/bin/tini', '-s', '--', '/opt/spark/bin/spark-submit', '--master', 'local[1]', '--driver-memory', '1536m', '/opt/silver/bootstrap_spark.py'],
                'entrypoint': [], 'environment': {'JAVA_TOOL_OPTIONS': '-XX:ActiveProcessorCount=1 -XX:MaxMetaspaceSize=384m -XX:ReservedCodeCacheSize=128m',
                    'SPARK_LOCAL_DIRS': '/tmp/spark-local', 'PYTHONHASHSEED': '0', 'HOME': '/tmp/spark-home'},
                'volumes': ['./silver-secrets:/run/silver-secrets:ro', './proof:/proof'],
                'tmpfs': ['/tmp:size=2g,uid=185,gid=185', '/opt/spark/work-dir:size=128m,uid=185,gid=185'],
                'networks': {'trial': {}}}},
        'volumes': {'postgres-data': {}, 'garage-meta': {}, 'garage-data': {}},
        'networks': {'trial': {'internal': True}}}
