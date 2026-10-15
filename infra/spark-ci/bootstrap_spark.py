"""Same isolated synthetic computation, with bounded message-free diagnostics.

The imports/session are inside the failure boundary. Raw error messages and
stack traces are never copied into the public diagnostic file.
"""
import json
import os
from pathlib import Path
import re

PROOF = Path('/proof')
PHASES = ('PYTHON_START', 'IMPORT_SILVER', 'SESSION', 'VERSIONS', 'FRESH_TABLES',
          'CREATE_BRONZE', 'APPEND_FIRST', 'APPEND_SECOND', 'VERIFY_BRONZE',
          'SILVER_RUN', 'VERIFY_RESULT', 'WRITE_RESULT', 'STOP_SESSION', 'COMPLETED')
PYTHON_EXCEPTIONS = frozenset(('Py4JJavaError', 'Py4JNetworkError', 'Py4JError',
    'AnalysisException', 'IllegalArgumentException', 'SparkRuntimeException',
    'ImportError', 'ModuleNotFoundError', 'PermissionError', 'FileNotFoundError',
    'RuntimeError', 'ValueError', 'OSError', 'TypeError', 'AssertionError'))
JAVA_CLASS = re.compile(r'(?:org\.apache\.(?:spark|iceberg)|java|org\.postgresql|software\.amazon)'
                        r'(?:\.[A-Za-z_$][A-Za-z0-9_$]*){1,12}')


def write_new(path, value):
    raw = (json.dumps(value, sort_keys=True) + '\n').encode()
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o644)
    with os.fdopen(fd, 'wb') as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())


def exception_classes(error):
    name = type(error).__name__
    python = name if name in PYTHON_EXCEPTIONS else 'OTHER'
    names = []
    try:
        current = getattr(error, 'java_exception', None)
        for _ in range(8):
            if current is None:
                break
            name = current.getClass().getName()
            if not isinstance(name, str) or len(name) > 160 or not JAVA_CLASS.fullmatch(name):
                break
            if name in names:
                break
            names.append(name)
            current = current.getCause()
    except Exception:
        pass
    return {'pythonExceptionClass': python, 'javaCauseClasses': names}


def execute(spark, silver, FIELDS, SOURCE_SHA, golden_bronze, require, row_sha, advance):
    from pyspark.sql import types as t
    advance('VERSIONS')
    require(spark.version == '4.1.1', 'ACTUAL_SPARK_VERSION')
    java = spark.sparkContext._jvm.java.lang.System.getProperty('java.version')
    scala = spark.sparkContext._jvm.scala.util.Properties.versionNumberString()
    require(re.match(r'^21(?:\.|\+|$)', java) and scala.startswith('2.13.'), 'ACTUAL_JAVA_SCALA_VERSIONS')
    advance('FRESH_TABLES')
    require(not spark.catalog.tableExists(silver.SOURCE_TABLE) and not spark.catalog.tableExists(silver.TARGET_TABLE), 'FRESH_ISOLATED_TABLES_ONLY')
    advance('CREATE_BRONZE')
    spark.sql("CREATE NAMESPACE phase6.bronze LOCATION '" + silver.WAREHOUSE + "/bronze'")
    spark.sql('CREATE TABLE ' + silver.SOURCE_TABLE + ' (input_sequence INT,event_id STRING,sensor_id STRING,event_time_raw STRING,sensor_value DOUBLE,source_sha256 STRING) USING iceberg LOCATION '
        + "'" + silver.WAREHOUSE + "/bronze/synthetic_events' TBLPROPERTIES ('format-version'='2','commit.retry.num-retries'='0','write.metadata.delete-after-commit.enabled'='false')")
    schema = t.StructType([t.StructField(name, t.IntegerType() if name == 'input_sequence' else t.DoubleType() if name == 'sensor_value' else t.StringType(), False) for name in FIELDS])
    rows = golden_bronze()
    for batch, subset in enumerate((rows[:6], rows[6:])):
        advance('APPEND_FIRST' if batch == 0 else 'APPEND_SECOND')
        frame = spark.createDataFrame([tuple(float(row[name]) if name == 'sensor_value' else row[name] for name in FIELDS) for row in subset], schema)
        frame.writeTo(silver.SOURCE_TABLE).append()
    advance('VERIFY_BRONZE')
    snapshots = [v.asDict() for v in spark.sql('SELECT snapshot_id,parent_id,operation FROM ' + silver.SOURCE_TABLE + '.snapshots ORDER BY committed_at,snapshot_id').limit(3).collect()]
    require(len(snapshots) == 2 and all(v['operation'] == 'append' for v in snapshots)
        and snapshots[0]['parent_id'] is None and snapshots[1]['parent_id'] == snapshots[0]['snapshot_id'], 'TWO_ACTUAL_APPEND_SNAPSHOT_CHAIN')
    for index, expected in enumerate((rows[:6], rows)):
        frame = spark.read.option('snapshot-id', str(snapshots[index]['snapshot_id'])).table(silver.SOURCE_TABLE).select(*FIELDS)
        require(silver.ordered(frame) == expected, 'ACTUAL_BRONZE_TIME_TRAVEL_ROWS')
    before = row_sha(silver.ordered(spark.table(silver.SOURCE_TABLE).select(*FIELDS)))
    advance('SILVER_RUN')
    result = silver.run(spark, snapshots[1]['snapshot_id'])
    advance('VERIFY_RESULT')
    require(row_sha(silver.ordered(spark.table(silver.SOURCE_TABLE).select(*FIELDS))) == before, 'BRONZE_ROWS_PRESERVED_AFTER_SILVER')
    after = [v.asDict() for v in spark.sql('SELECT snapshot_id,parent_id,operation FROM ' + silver.SOURCE_TABLE + '.snapshots ORDER BY committed_at,snapshot_id').limit(3).collect()]
    require(after == snapshots, 'BRONZE_SNAPSHOT_CHAIN_PRESERVED_AFTER_SILVER')
    require(result['passed'] is True and result['inputCount'] == 12 and result['successCount'] == 7 and result['failureCount'] == 3
        and result['duplicateCount'] == 2 and result['pendingCount'] == 0 and result['mergeInvocations'] == result['sequentialReplayInvocations'] == 1
        and result['replayWriteInvocations'] == 0 and len(result['silverSnapshots']) == 1, 'ACTUAL_FIXED_SILVER_RESULT')
    public = {'schemaVersion': 1, 'passed': True, 'scope': 'ISOLATED_GITHUB_RUNNER_SPARK_JDBC_GARAGE',
        'spark': spark.version, 'java': java, 'scala': scala, 'fixtureSha256': SOURCE_SHA,
        'bronzeRows': 12, 'bronzeSnapshotCount': 2, 'bronzeRowsSha256': before,
        'bronzeSnapshotIds': [str(v['snapshot_id']) for v in snapshots],
        'silverRows': 12, 'success': 7, 'failure': 3, 'duplicate': 2, 'pending': 0,
        'silverRowsSha256': result['silverRowsSha256'], 'silverSnapshotCount': 1,
        'mergeInvocations': 1, 'sequentialReplayInvocations': 1, 'replayWriteInvocations': 0,
        'sparkApplicationCount': 1, 'nativeTrinoVerified': False, 'miniPcPreservationVerified': False,
        'kubernetesVerified': False, 'distributedConcurrencyOrCrashRecoveryVerified': False}
    advance('WRITE_RESULT')
    path = PROOF / 'spark-result.json'
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o644)
    with os.fdopen(fd, 'w') as stream:
        json.dump(public, stream, sort_keys=True)
        stream.write('\n')
        stream.flush()
        os.fsync(stream.fileno())


def main():
    spark, failure, failure_phase = None, None, None
    phase, milestones, stop_failed = 'PYTHON_START', [], False

    def advance(value):
        nonlocal phase
        if value not in PHASES or len(milestones) >= 32:
            raise RuntimeError('BOUNDED_FIXED_BOOTSTRAP_MILESTONE')
        phase = value
        milestones.append(value)

    try:
        advance('PYTHON_START')
        advance('IMPORT_SILVER')
        import spark_silver as silver
        from silver_contract import FIELDS, SOURCE_SHA, golden_bronze, require, row_sha
        advance('SESSION')
        spark = silver.session()
        execute(spark, silver, FIELDS, SOURCE_SHA, golden_bronze, require, row_sha, advance)
    except Exception as error:
        failure_phase, failure = phase, exception_classes(error)
    finally:
        if spark is not None:
            try:
                advance('STOP_SESSION')
                spark.stop()
            except Exception as error:
                stop_failed = True
                if failure is None:
                    failure_phase, failure = phase, exception_classes(error)
    if failure is None:
        advance('COMPLETED')
    diagnostic = {'schemaVersion': 1, 'scope': 'ISOLATED_SPARK_BOOTSTRAP_DIAGNOSTIC',
        'passed': failure is None, 'lastPhase': failure_phase if failure else phase,
        'milestones': milestones, 'pythonExceptionClass': None if failure is None else failure['pythonExceptionClass'],
        'javaCauseClasses': [] if failure is None else failure['javaCauseClasses'],
        'sessionStopFailed': stop_failed}
    try:
        write_new(PROOF / 'bootstrap-diagnostic.json', diagnostic)
    except Exception:
        # This fixed marker is diagnostic only; missing output is never success.
        print('BOOTSTRAP_DIAGNOSTIC_WRITE_UNAVAILABLE', flush=True)
        return 1
    return 0 if failure is None else 1


if __name__ == '__main__':
    raise SystemExit(main())
