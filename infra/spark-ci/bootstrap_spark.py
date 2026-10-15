"""Same isolated synthetic computation, with bounded message-free diagnostics.

The imports/session are inside the failure boundary. Raw error messages and
stack traces are never copied into the public diagnostic file.
"""
import json
import os
from pathlib import Path
import re
import time

PROOF = Path('/proof')
PHASES = ('PYTHON_START', 'IMPORT_SILVER', 'SESSION', 'GZIP_DEFAULT', 'VERSIONS', 'FRESH_TABLES',
          'CREATE_BRONZE', 'APPEND_FIRST', 'APPEND_SECOND', 'VERIFY_BRONZE',
          'SILVER_RUN', 'VERIFY_RESULT', 'WRITE_RESULT', 'STOP_SESSION', 'COMPLETED')
PYTHON_EXCEPTIONS = frozenset(('Py4JJavaError', 'Py4JNetworkError', 'Py4JError',
    'AnalysisException', 'IllegalArgumentException', 'SparkRuntimeException',
    'ImportError', 'ModuleNotFoundError', 'PermissionError', 'FileNotFoundError',
    'RuntimeError', 'ValueError', 'OSError', 'TypeError', 'AssertionError'))
JAVA_CLASS = re.compile(r'(?:org\.apache\.(?:spark|iceberg)|java|org\.postgresql|software\.amazon)'
                        r'(?:\.[A-Za-z_$][A-Za-z0-9_$]*){1,12}')
CODEC_PROPERTY = 'write.parquet.compression-codec'
CODEC_DEFAULT = 'spark.sql.catalog.phase6.table-default.' + CODEC_PROPERTY
TABLES = ('phase6.bronze.synthetic_events', 'phase6.silver.sensor_outcomes')
NATIVE_LIBRARIES = ('zstd', 'snappy', 'lz4', 'hadoop')


def tmp_mount_flag(raw=None):
    """Return only the effective /tmp mount option, never mount names/paths."""
    try:
        if raw is None:
            with Path('/proc/self/mountinfo').open('rb') as stream:
                raw = stream.read(1024**2 + 1)
        if not isinstance(raw, bytes) or not 0 < len(raw) <= 1024**2:
            return 'UNOBSERVED'
        matches = []
        for line in raw.decode('ascii').splitlines():
            fields = line.split(); marker = fields.index('-')
            if marker < 6 or len(fields) < marker + 4:
                return 'UNOBSERVED'
            mount = fields[4]
            if mount == '/' or mount == '/tmp' or '/tmp'.startswith(mount.rstrip('/') + '/'):
                options = set(fields[5].split(',')) | set(fields[marker + 3].split(','))
                matches.append((len(mount), 'NOEXEC' if 'noexec' in options else 'EXEC'))
        if not matches:
            return 'UNOBSERVED'
        longest = max(length for length, flag in matches)
        flags = {flag for length, flag in matches if length == longest}
        return flags.pop() if len(flags) == 1 else 'UNOBSERVED'
    except Exception:
        return 'UNOBSERVED'


def gzip_property(spark, table):
    if table not in TABLES:
        raise ValueError('ONLY_FIXED_SYNTHETIC_TABLE_PROPERTY_READ')
    rows = [row.asDict() for row in spark.sql("SHOW TBLPROPERTIES " + table + " ('" + CODEC_PROPERTY + "')").limit(2).collect()]
    if rows != [{'key': CODEC_PROPERTY, 'value': 'gzip'}]:
        raise ValueError('ACTUAL_GZIP_TABLE_PROPERTY_NOT_VERIFIED')
    return 'gzip'


def write_new(path, value):
    raw = (json.dumps(value, sort_keys=True) + '\n').encode()
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o644)
    with os.fdopen(fd, 'wb') as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())


def write_progress(milestones, mount_flag, elapsed_millis):
    """Publish one complete fixed-field transition file; never a completion proof."""
    if (not 1 <= len(milestones) <= 32 or any(value not in PHASES for value in milestones)
            or milestones[0] != 'PYTHON_START' or len(set(milestones)) != len(milestones)
            or mount_flag not in ('NOEXEC', 'EXEC', 'UNOBSERVED')
            or type(elapsed_millis) is not int or not 0 <= elapsed_millis <= 3_600_000):
        raise ValueError('BOUNDED_FIXED_PROGRESS_ONLY')
    value = {'schemaVersion': 1, 'scope': 'ISOLATED_SPARK_BOOTSTRAP_PROGRESS',
        'sequence': len(milestones), 'lastPhase': milestones[-1], 'milestones': list(milestones),
        'elapsedMillis': elapsed_millis, 'tmpMountFlag': mount_flag, 'completionNotProven': True}
    name = 'bootstrap-progress-%02d.json' % len(milestones)
    temporary = PROOF / ('.' + name + '.tmp')
    write_new(temporary, value)
    # Link only after the complete bytes are fsynced. Both names are new and
    # private to this fresh proof directory; no prior transition is replaced.
    os.link(temporary, PROOF / name, follow_symlinks=False)
    temporary.unlink()


def exception_classes(error):
    name = type(error).__name__
    python = name if name in PYTHON_EXCEPTIONS else 'OTHER'
    names, libraries, failed_map = [], set(), False
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
            # Message text is transient classification input only. No message,
            # native path or stack trace is returned or written by this helper.
            try:
                message = current.getMessage()
            except Exception:
                message = None
            if isinstance(message, str):
                message = message[:8192]
                for library in NATIVE_LIBRARIES:
                    if re.search(r'(?:^|[^a-z])(?:lib)?' + library + r'(?:[-_.0-9]|$)', message, re.I):
                        libraries.add(library)
                failed_map |= bool(re.search(r'\bfailed to map segment\b', message, re.I))
            current = current.getCause()
    except Exception:
        pass
    return {'pythonExceptionClass': python, 'javaCauseClasses': names,
        'nativeLibraryCategories': sorted(libraries), 'failedMapSegmentObserved': failed_map}


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
    bronze_before = gzip_property(spark, silver.SOURCE_TABLE)
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
        frame = spark.read.option('versionAsOf', str(snapshots[index]['snapshot_id'])).table(silver.SOURCE_TABLE).select(*FIELDS)
        require(silver.ordered(frame) == expected, 'ACTUAL_BRONZE_TIME_TRAVEL_ROWS')
    before = row_sha(silver.ordered(spark.table(silver.SOURCE_TABLE).select(*FIELDS)))
    advance('SILVER_RUN')
    result = silver.run(spark, snapshots[1]['snapshot_id'])
    # Frozen run creates Silver and performs its MERGE + sequential replay.
    # This is an after-write property observation, not a Silver pre-write probe.
    bronze_after = gzip_property(spark, silver.SOURCE_TABLE)
    silver_after = gzip_property(spark, silver.TARGET_TABLE)
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
        'kubernetesVerified': False, 'distributedConcurrencyOrCrashRecoveryVerified': False,
        'compressionExperiment': {'requestedCodec': 'gzip', 'catalogDefaultSetBeforeFirstCatalogAccess': True,
            'bronzePropertyBeforeAppend': bronze_before, 'bronzePropertyAfterRun': bronze_after,
            'silverPropertyAfterWriteAndReplay': silver_after, 'silverPropertyBeforeWriteObserved': False,
            'verification': 'SHOW_TBLPROPERTIES_ONLY', 'actualParquetFooterCodecVerified': False,
            'priorFailureSoleCauseProven': False}}
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
    mount_flag = tmp_mount_flag()
    progress_started = time.monotonic()

    def advance(value):
        nonlocal phase
        if value not in PHASES or len(milestones) >= 32:
            raise RuntimeError('BOUNDED_FIXED_BOOTSTRAP_MILESTONE')
        phase = value
        milestones.append(value)
        try:
            write_progress(milestones, mount_flag, int((time.monotonic() - progress_started) * 1000))
        except Exception:
            # Missing transition evidence is never repaired into a success claim.
            print('BOOTSTRAP_PROGRESS_WRITE_UNAVAILABLE', flush=True)

    try:
        advance('PYTHON_START')
        advance('IMPORT_SILVER')
        import spark_silver as silver
        from silver_contract import FIELDS, SOURCE_SHA, golden_bronze, require, row_sha
        advance('SESSION')
        spark = silver.session()
        advance('GZIP_DEFAULT')
        spark.conf.set(CODEC_DEFAULT, 'gzip')
        if spark.conf.get(CODEC_DEFAULT) != 'gzip':
            raise ValueError('GZIP_DEFAULT_NOT_SET_BEFORE_CATALOG_ACCESS')
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
        'sessionStopFailed': stop_failed,
        'nativeLibraryCategories': [] if failure is None else failure['nativeLibraryCategories'],
        'failedMapSegmentObserved': False if failure is None else failure['failedMapSegmentObserved'],
        'tmpMountFlag': mount_flag}
    try:
        write_new(PROOF / 'bootstrap-diagnostic.json', diagnostic)
    except Exception:
        # This fixed marker is diagnostic only; missing output is never success.
        print('BOOTSTRAP_DIAGNOSTIC_WRITE_UNAVAILABLE', flush=True)
        return 1
    return 0 if failure is None else 1


if __name__ == '__main__':
    raise SystemExit(main())
