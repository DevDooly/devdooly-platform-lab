"""Source-only single local[1] Spark job candidate. Never imported by a live API.

Runtime is NOT_RUN. Only the exact public twelve-row Bronze snapshot is accepted.
One fixed MERGE is followed by a sequential persisted-batch replay without writes.
"""
import argparse
import json
from pathlib import Path
import re
from silver_contract import BATCH_ID,FIELDS,OUTPUT_FIELDS,SOURCE_TABLE,TARGET_TABLE,require,validate_bronze,validate_silver,replay_action

BUCKET='platform-lab-iceberg-20261015'
WAREHOUSE='s3://'+BUCKET+'/warehouse/phase6'
SECRET=Path('/run/silver-secrets')


def secret(name,pattern):
    raw=(SECRET/name).read_bytes();require(0<len(raw)<=1024,'BOUNDED_FIXED_SECRET_FILE')
    value=raw.decode('ascii');require(re.fullmatch(pattern,value),'EXACT_SINGLE_LINE_SECRET_FORMAT')
    return value


def session():
    from pyspark.sql import SparkSession
    values={
        'spark.sql.extensions':'org.apache.iceberg.spark.extensions.IcebergSparkSessionExtensions',
        'spark.sql.catalog.phase6':'org.apache.iceberg.spark.SparkCatalog',
        'spark.sql.catalog.phase6.type':'jdbc',
        'spark.sql.catalog.phase6.uri':'jdbc:postgresql://postgres.platform-lab-iceberg-20261015.svc.cluster.local:5432/iceberg_lab',
        'spark.sql.catalog.phase6.jdbc.user':'iceberg_catalog',
        'spark.sql.catalog.phase6.jdbc.password':secret('catalog-password',r'[a-f0-9]{64}'),
        'spark.sql.catalog.phase6.jdbc.init-catalog-tables':'false',
        'spark.sql.catalog.phase6.jdbc.schema-version':'V1',
        'spark.sql.catalog.phase6.cache-enabled':'false',
        'spark.sql.catalog.phase6.io-impl':'org.apache.iceberg.aws.s3.S3FileIO',
        'spark.sql.catalog.phase6.warehouse':WAREHOUSE,
        'spark.sql.catalog.phase6.s3.endpoint':secret('endpoint',r'http://garage\.platform-lab\.svc\.cluster\.local:3900'),
        'spark.sql.catalog.phase6.s3.access-key-id':secret('access-key',r'[A-Za-z0-9]{1,128}'),
        'spark.sql.catalog.phase6.s3.secret-access-key':secret('secret-key',r'[!-~]{1,512}'),
        'spark.sql.catalog.phase6.s3.path-style-access':'true',
        'spark.sql.catalog.phase6.client.region':'garage',
        'spark.sql.catalog.phase6.s3.crt.enabled':'false',
        'spark.sql.catalog.phase6.s3.chunked-encoding-enabled':'false',
        'spark.sql.catalog.phase6.s3.multipart.num-threads':'1',
        'spark.sql.catalog.phase6.s3.multipart.part-size-bytes':str(5*1024**2),
        'spark.sql.catalog.phase6.s3.retry.num-retries':'0',
        'spark.sql.session.timeZone':'UTC','spark.sql.shuffle.partitions':'1','spark.default.parallelism':'1',
        'spark.sql.adaptive.enabled':'false','spark.ui.enabled':'false','spark.eventLog.enabled':'false',
        'spark.logConf':'false','spark.redaction.regex':'(?i)secret|password|token|access[._-]?key|credential',
        'spark.driver.host':'127.0.0.1','spark.driver.bindAddress':'127.0.0.1','spark.driver.maxResultSize':'1m',
        'spark.local.dir':'/tmp/spark-local','spark.task.maxFailures':'1','spark.speculation':'false',
    }
    builder=SparkSession.builder.master('local[1]').appName('bounded-synthetic-silver-v1')
    for key,value in values.items():builder=builder.config(key,value)
    result=builder.getOrCreate();result.sparkContext.setLogLevel('WARN');return result


def transform(source):
    # Exact fixture validation precedes this expression. This is not a general
    # malformed-input parser; only public V1 rows, finite values, nonblank IDs.
    from pyspark.sql import functions as f,Window
    seen=Window.partitionBy('event_id').orderBy('input_sequence')
    prior=Window.partitionBy('sensor_id').orderBy('input_sequence').rowsBetween(Window.unboundedPreceding,-1)
    value=source.withColumn('_seen',f.row_number().over(seen)) \
        .withColumn('_time',f.try_to_timestamp(f.col('event_time_raw'),f.lit("yyyy-MM-dd'T'HH:mm:ssXXX")))
    candidate=f.when((f.col('_seen')==1)&f.col('_time').isNotNull()&f.col('sensor_value').between(0,100),f.col('_time'))
    value=value.withColumn('_candidate',candidate).withColumn('_previous',f.max('_candidate').over(prior))
    reason=f.when(f.col('_seen')>1,'DUPLICATE_EVENT_ID').when(f.col('_time').isNull(),'INVALID_TIMESTAMP') \
        .when(~f.col('sensor_value').between(0,100),'OUT_OF_RANGE').when(f.col('_time')<f.col('_previous'),'OUT_OF_ORDER').otherwise('ACCEPTED')
    value=value.withColumn('reason',reason).withColumn('status',f.when(f.col('reason')=='ACCEPTED','SUCCESS') \
        .when(f.col('reason')=='DUPLICATE_EVENT_ID','DUPLICATE').otherwise('FAILED')).withColumn('batch_id',f.lit(BATCH_ID))
    return value.select(*OUTPUT_FIELDS)


def ordered(frame):
    return [value.asDict() for value in frame.orderBy('input_sequence').limit(13).collect()]


def snapshots(spark):
    return [v.asDict() for v in spark.sql('SELECT snapshot_id,parent_id,operation FROM '+TARGET_TABLE+'.snapshots ORDER BY committed_at,snapshot_id').limit(3).collect()]


def run(spark,snapshot_id):
    require(not spark.catalog.tableExists(TARGET_TABLE),'NEW_SILVER_TARGET_MUST_BE_ABSENT_NO_UNKNOWN_RETRY')
    source=spark.read.option('versionAsOf',str(snapshot_id)).table(SOURCE_TABLE).select(*FIELDS)
    validate_bronze(ordered(source));outcomes=transform(source);expected=ordered(outcomes);validate_silver(expected)
    spark.sql("CREATE NAMESPACE phase6.silver LOCATION '"+WAREHOUSE+"/silver'")
    spark.sql('CREATE TABLE '+TARGET_TABLE+' (batch_id STRING,input_sequence INT,event_id STRING,sensor_id STRING,event_time_raw STRING,sensor_value DOUBLE,source_sha256 STRING,status STRING,reason STRING) USING iceberg LOCATION '\
        +"'"+WAREHOUSE+"/silver/sensor_outcomes' TBLPROPERTIES ('format-version'='2','commit.retry.num-retries'='0','write.metadata.delete-after-commit.enabled'='false','write.target-file-size-bytes'='262144')")
    outcomes.createOrReplaceTempView('fixed_silver_outcomes')
    require(replay_action(ordered(spark.table(TARGET_TABLE)))=='MERGE_FIXED_BATCH_ONCE','FRESH_TARGET_EMPTY_REQUIRED')
    spark.sql('MERGE INTO '+TARGET_TABLE+' t USING fixed_silver_outcomes s ON t.batch_id=s.batch_id AND t.input_sequence=s.input_sequence WHEN NOT MATCHED THEN INSERT *')
    spark.catalog.refreshTable(TARGET_TABLE);first=ordered(spark.table(TARGET_TABLE));fingerprint=validate_silver(first)
    first_snapshots=snapshots(spark);require(len(first_snapshots)==1,'ONE_FIXED_BATCH_SNAPSHOT_REQUIRED')
    # Explicit second invocation of batch handling sees persisted output and
    # performs no MERGE/INSERT/DDL. This is sequential replay, not concurrency.
    spark.catalog.refreshTable(TARGET_TABLE);persisted=ordered(spark.table(TARGET_TABLE))
    require(replay_action(persisted)=='READ_ONLY_IDENTICAL_BATCH_NO_WRITE','PERSISTED_BATCH_REPLAY_MUST_BE_IDENTICAL')
    after_snapshots=snapshots(spark);require(persisted==first and after_snapshots==first_snapshots,'SEQUENTIAL_REPLAY_ROWS_AND_SNAPSHOT_UNCHANGED')
    return {'schemaVersion':1,'scope':'SINGLE_LOCAL_SPARK_PUBLIC_V1_SILVER_AND_SEQUENTIAL_BATCH_REPLAY','passed':True,
        'inputCount':12,'successCount':7,'failureCount':3,'duplicateCount':2,'pendingCount':0,'batchId':BATCH_ID,
        'sourceSnapshotId':snapshot_id,'silverRowsSha256':fingerprint,'silverSnapshots':after_snapshots,
        'operatorJobRetries':0,'mergeInvocations':1,'sequentialReplayInvocations':1,'replayWriteInvocations':0,
        'distributedConcurrencyOrCrashRecoveryVerified':False,'productionPreservationVerifiedByThisJob':False}


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--bronze-snapshot-id',type=int,required=True);args=parser.parse_args()
    require(0<args.bronze_snapshot_id<2**63,'ACTUAL_VERIFIED_BRONZE_SNAPSHOT_ID_REQUIRED');spark=session()
    try:
        result=run(spark,args.bronze_snapshot_id);print('SILVER_PROOF_JSON '+json.dumps(result,sort_keys=True))
        Path('/dev/termination-log').write_text(json.dumps(result,sort_keys=True)+'\n',encoding='utf-8')
    finally:spark.stop()


if __name__=='__main__':main()
