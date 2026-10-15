"""One Spark application bootstraps synthetic Bronze then invokes frozen Silver.

This isolated Spark producer is not Trino and is not a mini-PC/Kubernetes test.
"""
import json
import os
from pathlib import Path
import re
import spark_silver as silver
from silver_contract import FIELDS, SOURCE_SHA, golden_bronze, require, row_sha


def main():
    spark = silver.session()
    try:
        from pyspark.sql import types as t
        require(spark.version == '4.1.1', 'ACTUAL_SPARK_VERSION')
        java = spark.sparkContext._jvm.java.lang.System.getProperty('java.version')
        scala = spark.sparkContext._jvm.scala.util.Properties.versionNumberString()
        require(re.match(r'^21(?:\.|\+|$)', java) and scala.startswith('2.13.'), 'ACTUAL_JAVA_SCALA_VERSIONS')
        require(not spark.catalog.tableExists(silver.SOURCE_TABLE) and not spark.catalog.tableExists(silver.TARGET_TABLE), 'FRESH_ISOLATED_TABLES_ONLY')
        spark.sql("CREATE NAMESPACE phase6.bronze LOCATION '" + silver.WAREHOUSE + "/bronze'")
        spark.sql('CREATE TABLE ' + silver.SOURCE_TABLE + ' (input_sequence INT,event_id STRING,sensor_id STRING,event_time_raw STRING,sensor_value DOUBLE,source_sha256 STRING) USING iceberg LOCATION '
            + "'" + silver.WAREHOUSE + "/bronze/synthetic_events' TBLPROPERTIES ('format-version'='2','commit.retry.num-retries'='0','write.metadata.delete-after-commit.enabled'='false')")
        schema = t.StructType([t.StructField(name, t.IntegerType() if name == 'input_sequence' else t.DoubleType() if name == 'sensor_value' else t.StringType(), False) for name in FIELDS])
        rows = golden_bronze()
        for subset in (rows[:6], rows[6:]):
            frame = spark.createDataFrame([tuple(float(row[name]) if name == 'sensor_value' else row[name] for name in FIELDS) for row in subset], schema)
            frame.writeTo(silver.SOURCE_TABLE).append()
        snapshots = [v.asDict() for v in spark.sql('SELECT snapshot_id,parent_id,operation FROM ' + silver.SOURCE_TABLE + '.snapshots ORDER BY committed_at,snapshot_id').limit(3).collect()]
        require(len(snapshots) == 2 and all(v['operation'] == 'append' for v in snapshots)
            and snapshots[0]['parent_id'] is None and snapshots[1]['parent_id'] == snapshots[0]['snapshot_id'], 'TWO_ACTUAL_APPEND_SNAPSHOT_CHAIN')
        for index, expected in enumerate((rows[:6], rows)):
            frame = spark.read.option('snapshot-id', str(snapshots[index]['snapshot_id'])).table(silver.SOURCE_TABLE).select(*FIELDS)
            require(silver.ordered(frame) == expected, 'ACTUAL_BRONZE_TIME_TRAVEL_ROWS')
        before = row_sha(silver.ordered(spark.table(silver.SOURCE_TABLE).select(*FIELDS)))
        result = silver.run(spark, snapshots[1]['snapshot_id'])
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
        path = Path('/proof/spark-result.json')
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o644)
        with os.fdopen(fd, 'w') as stream:
            json.dump(public, stream, sort_keys=True)
            stream.write('\n')
            stream.flush()
            os.fsync(stream.fileno())
    finally:
        spark.stop()


if __name__ == '__main__':
    main()
