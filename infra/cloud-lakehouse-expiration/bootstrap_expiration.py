"""One fresh synthetic table: tag S1, append S4, expire only S2 once."""
import datetime as dt
import json
import os
from pathlib import Path
import re
import signal
import sys
import time
import urllib.error

import expiration_contract as policy
from contract import FIELDS, require, row_sha, sha
from frozen_s3_primitives import xml
from s3_readonly import BUCKET, PREFIX, PROOF, Client, clock, new_json

TABLE = "phase6.bronze.synthetic_events"
TAG = "retained_first6"
SCOPE = "FRESH_CLOUD_ICEBERG_TAGGED_SNAPSHOT_EXPIRATION"


def key_of(location):
    prefix = "s3://" + BUCKET + "/"
    require(type(location) is str and location.startswith(prefix), "EXACT_FRESH_BUCKET_URI")
    key = location[len(prefix):]
    require(key.startswith(PREFIX) and re.fullmatch(r"[A-Za-z0-9._/-]{1,1024}", key)
                   and ".." not in key.split("/"), "CANONICAL_FRESH_OBJECT_KEY")
    return key


def capture_objects(client, name):
    require(name in ("before-expiration", "after-expiration", "after-expiration-trino"), "FIXED_CAPTURE_NAME")
    folder = PROOF / ("expiration-objects-" + name)
    folder.mkdir(mode=0o755)
    listed = client.listing()
    require(0 < len(listed) <= 128, "NONEMPTY_BOUNDED_FRESH_WAREHOUSE")
    result, total = [], 0
    for item in listed:
        raw = client.get(item["key"])
        total += len(raw)
        require(len(raw) == item["size"] and total <= 32 * 1024**2, "WHOLE_WAREHOUSE_CAPTURE_BOUND")
        with (folder / (sha(item["key"].encode()) + ".bin")).open("xb") as handle:
            handle.write(raw)
            handle.flush()
            os.fsync(handle.fileno())
        result.append({"key": item["key"], "bytes": len(raw), "sha256": sha(raw)})
    require(client.listing() == listed, "EXACT_LIST_BEFORE_AFTER_WHOLE_GETS")
    new_json(PROOF / (name + ".objects.private.json"), result)
    return result


def data_files(table, snapshot_id, deadline):
    tasks = table.newScan().useSnapshot(int(snapshot_id)).planFiles()
    result = []
    try:
        iterator = tasks.iterator()
        while iterator.hasNext():
            deadline.remaining(15, 90)
            require(len(result) < 2, "AT_MOST_TWO_LIVE_DATA_FILES_EACH_SNAPSHOT")
            task = iterator.next()
            value = task.file()
            require(int(value.content().id()) == 0 and int(task.deletes().size()) == 0
                           and str(value.format()) == "PARQUET", "ONLY_PARQUET_DATA_WITH_NO_DELETE_FILES")
            result.append({"key": key_of(str(value.path())), "records": int(value.recordCount()),
                           "bytes": int(value.fileSizeInBytes())})
    finally:
        tasks.close()
    return sorted(result, key=lambda value: value["key"])


def observe(spark, client, name):
    deadline = client.deadline
    table = spark.sparkContext._jvm.org.apache.iceberg.spark.Spark3Util.loadIcebergTable(spark._jsparkSession, TABLE)
    table.refresh()
    metadata = table.operations().current()
    location = str(metadata.metadataFileLocation())
    metadata_key = key_of(location)
    raw = client.get(metadata_key)
    document = json.loads(raw)
    require(document.get("format-version") == 2 and document.get("table-uuid") == str(metadata.uuid())
                   and not document.get("statistics") and not document.get("partition-statistics"),
                   "FORMAT_TWO_WITHOUT_STATISTICS_FILES")
    properties = document.get("properties", {})
    require(type(properties) is dict and properties.get("write.metadata.delete-after-commit.enabled") == "false"
                   and properties.get("commit.retry.num-retries") == "0", "UNCHANGED_NO_OLD_METADATA_AUTO_DELETE_POLICY")
    refs = []
    iterator = table.refs().entrySet().iterator()
    while iterator.hasNext():
        require(len(refs) < 2, "AT_MOST_MAIN_AND_OWN_TAG")
        entry = iterator.next()
        ref = entry.getValue()
        require(ref.maxRefAgeMs() is None and ref.minSnapshotsToKeep() is None
                       and ref.maxSnapshotAgeMs() is None, "NO_REF_SPECIFIC_RETENTION_OVERRIDE")
        refs.append({"name": str(entry.getKey()), "kind": "TAG" if ref.isTag() else "BRANCH",
                     "snapshotId": str(ref.snapshotId())})
    snapshots = []
    iterator = table.snapshots().iterator()
    while iterator.hasNext():
        deadline.remaining(15, 90)
        require(len(snapshots) < 4, "AT_MOST_FOUR_OWN_SNAPSHOTS")
        snapshot = iterator.next()
        sid = str(snapshot.snapshotId())
        manifests = snapshot.allManifests(table.io())
        require(int(manifests.size()) <= 32, "BOUNDED_MANIFEST_CLOSURE")
        keys = []
        for index in range(int(manifests.size())):
            manifest = manifests.get(index)
            require(int(manifest.content().id()) == 0, "NO_DELETE_MANIFESTS")
            keys.append(key_of(str(manifest.path())))
        records = snapshot.summary().get("total-records")
        require(records is not None and re.fullmatch(r"[0-9]{1,2}", str(records)), "ACTUAL_TOTAL_RECORDS_SUMMARY")
        snapshots.append({"id": sid, "parentId": None if snapshot.parentId() is None else str(snapshot.parentId()),
                          "operation": str(snapshot.operation()), "committedAtMs": int(snapshot.timestampMillis()),
                          "totalRecords": int(records), "dataFiles": data_files(table, sid, deadline),
                          "manifestList": key_of(str(snapshot.manifestListLocation())), "manifests": sorted(keys)})
    objects = capture_objects(client, name)
    table.refresh()
    require(str(table.operations().current().metadataFileLocation()) == location and client.get(metadata_key) == raw,
                   "ACTUAL_METADATA_POINTER_AND_BYTES_STABLE_DURING_CAPTURE")
    state = {"tableUuid": str(metadata.uuid()), "currentSnapshotId": str(metadata.currentSnapshot().snapshotId()),
             "metadataKey": metadata_key, "gcEnabled": properties.get("gc.enabled", "true") == "true",
             "tagRetentionDefault": "history.expire.max-ref-age-ms" not in properties,
             "snapshots": snapshots, "refs": sorted(refs, key=lambda value: value["name"]), "objects": objects}
    new_json(PROOF / (name + ".state.private.json"), state)
    return state


def absent_data(client, key):
    try:
        client.get(key)
    except urllib.error.HTTPError as error:
        try:
            raw = error.read(4097)
            require(error.code == 404 and len(raw) <= 4096, "EXACT_SMALL_404_REQUIRED")
            tree = xml(raw, "Error")
            require(tree.findtext("Code") == "NoSuchKey", "EXACT_NOSUCHKEY_NOT_PERMISSION_OR_BUCKET_FAILURE")
            return {"status": 404, "code": "NoSuchKey", "key": key}
        finally:
            error.close()
    require(False, "EXPIRED_DATA_OBJECT_STILL_PRESENT")


def third_fixture(golden):
    values = []
    for index, source in enumerate(golden[:6], 13):
        values.append({**{key: value for key, value in source.items() if key != "source_sha256"},
                       "input_sequence": index, "event_id": "expiration-third-%d" % index})
    raw = ("\n".join(json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False) for value in values) + "\n").encode()
    with (PROOF / "expiration-third-fixture.ndjson").open("xb") as handle:
        handle.write(raw)
        handle.flush()
        os.fsync(handle.fileno())
    return [{**value, "source_sha256": sha(raw)} for value in values]


def bronze_rows(frame):
    values = [value.asDict() for value in frame.orderBy("input_sequence").limit(19).collect()]
    require(0 < len(values) <= 18 and all(set(value) == set(FIELDS)
            and type(value["input_sequence"]) is int for value in values)
            and [value["input_sequence"] for value in values] == list(range(1, len(values) + 1)),
            "EXACT_BOUNDED_BRONZE_SEQUENCE")
    return values


def verify_rows(spark, silver, golden, before, after):
    chain = sorted(before["snapshots"], key=lambda value: value["committedAtMs"])
    retained = {value["id"] for value in after["snapshots"]}
    expected = {chain[0]["id"]: golden[:6], chain[2]["id"]: golden[:12], chain[3]["id"]: golden}
    fingerprints = {}
    for sid, rows in expected.items():
        require(sid in retained, "EXACT_RETAINED_SNAPSHOT_FOR_TIME_TRAVEL")
        frame = spark.read.option("versionAsOf", sid).table(TABLE).select(*FIELDS)
        actual = bronze_rows(frame)
        require(frame.schema["sensor_value"].dataType.simpleString() == "double" and actual == rows,
                       "RETAINED_SIX_TWELVE_EIGHTEEN_ROWS_EQUAL_ORACLE")
        fingerprints[sid] = row_sha(actual)
    require(bronze_rows(spark.table(TABLE).select(*FIELDS)) == golden, "CURRENT_EIGHTEEN_ROWS_EQUAL_ORACLE")
    return fingerprints


def execute(spark, progress):
    import bootstrap_trial9 as frozen
    import spark_silver as silver
    from pyspark.sql import types as types
    from silver_contract import classify, golden_bronze
    client = Client(clock())
    progress["phase"] = "FROZEN_APPEND_AND_COMPACTION"
    initial = frozen.execute(spark, lambda phase: progress.update(phase=phase))
    new_json(PROOF / "initial-compaction.private.json", initial)
    first = initial["snapshots"][0]["snapshot_id"]
    require(re.fullmatch(r"[1-9][0-9]{0,18}", first) and int(first) < 2**63, "BOUND_FIRST_SNAPSHOT_ID")
    progress["phase"] = "TAG_AND_THIRD_APPEND"
    spark.sql("ALTER TABLE " + TABLE + " CREATE TAG " + TAG + " AS OF VERSION " + first)
    base = golden_bronze()
    extra = third_fixture(base)
    schema = types.StructType([types.StructField(name, types.IntegerType() if name == "input_sequence"
                              else types.DoubleType() if name == "sensor_value" else types.StringType(), False) for name in FIELDS])
    spark.createDataFrame([tuple(float(row[name]) if name == "sensor_value" else row[name] for name in FIELDS)
                           for row in extra], schema).coalesce(1).writeTo(TABLE).append()
    progress["phase"] = "FRESH_EXPIRATION_PREFLIGHT"
    before = observe(spark, client, "before-expiration")
    plan = policy.preflight(before, int(time.time_ns() // 1000000))
    require(bronze_rows(spark.table(TABLE).select(*FIELDS)) == base + extra
                   and silver.ordered(spark.table(silver.TARGET_TABLE)) == classify(base), "ROWS_AND_SILVER_BEFORE_EXPIRATION")
    # A fixed, sole Spark writer owns the new table; the other two running roles
    # are its fresh PG/Garage. Trino and reader have not been created yet.
    call_budget = client.deadline.remaining(60, 90)
    cutoff = dt.datetime(1970, 1, 1, tzinfo=dt.timezone.utc) + dt.timedelta(milliseconds=plan["cutoffMs"])
    sql = ("CALL phase6.system.expire_snapshots(table => 'bronze.synthetic_events', older_than => TIMESTAMP '"
           + cutoff.strftime("%Y-%m-%d %H:%M:%S.%f") + "', retain_last => 2, max_concurrent_deletes => 1, stream_results => true)")
    new_json(PROOF / "expiration-intent.private.json", {"plan": plan, "sqlSha256": sha(sql.encode()), "invocations": 1,
             "automaticRetry": False, "callBudgetSeconds": call_budget, "bulkDeletionConcurrencyGuaranteed": False})
    progress.update(phase="EXPIRATION_ONCE", expirationInvoked=True)
    previous = signal.signal(signal.SIGALRM, lambda *_: (_ for _ in ()).throw(TimeoutError("EXPIRATION_CALL_DEADLINE_UNKNOWN")))
    signal.setitimer(signal.ITIMER_REAL, call_budget)
    try:
        output = [row.asDict() for row in spark.sql(sql).limit(2).collect()]
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, previous)
    progress["expirationReturned"] = True
    require(len(output) == 1, "ONE_EXPIRATION_RESULT_ROW")
    progress["phase"] = "EXPIRATION_POSTCONDITIONS"
    after = observe(spark, client, "after-expiration")
    missing = absent_data(client, plan["removedDataKey"])
    result = policy.verify_expiration(before, after, output[0], missing)
    fingerprints = verify_rows(spark, silver, base + extra, before, after)
    actual_silver = silver.ordered(spark.table(silver.TARGET_TABLE))
    require(actual_silver == classify(base) and row_sha(actual_silver) == initial["silverRowsSha256"], "SILVER_ROWS_UNCHANGED")
    result.update(rowFingerprints=fingerprints, expectedRows=base + extra, silverRowsSha256=initial["silverRowsSha256"],
                  missingDataKey=plan["removedDataKey"], tableUuid=before["tableUuid"])
    progress["expirationVerified"] = True
    return result


def reader_main():
    client = Client(clock())
    before = json.loads((PROOF / "after-expiration.objects.private.json").read_bytes())
    actual = capture_objects(client, "after-expiration-trino")
    require(actual == before, "WHOLE_POST_EXPIRATION_BYTES_UNCHANGED_BY_TRINO")
    for item in actual:
        leaf = sha(item["key"].encode()) + ".bin"
        require((PROOF / "expiration-objects-after-expiration" / leaf).read_bytes()
                       == (PROOF / "expiration-objects-after-expiration-trino" / leaf).read_bytes(), "WHOLE_GET_BYTES_EQUAL")
    result = json.loads((PROOF / "expiration-spark-result.private.json").read_bytes())
    absent_data(client, result["missingDataKey"])
    new_json(PROOF / "expiration-reader-result.json", {"passed": True, "wholeObjects": len(actual),
             "allPostExpirationBytesEqual": True, "removedDataStillNoSuchKey": True, "onlyGetAndList": True})
    return 0


def main():
    if sys.argv[1:] == ["--reader"]:
        return reader_main()
    require(sys.argv[1:] == [], "FIXED_EXPIRATION_SPARK_ENTRYPOINT")
    import spark_silver as silver
    spark, result, failure, close_failed = None, None, None, False
    progress = {"phase": "SESSION", "expirationInvoked": False, "expirationReturned": False, "expirationVerified": False}
    try:
        spark = silver.session()
        import base_bootstrap as base
        spark.conf.set(base.CODEC_DEFAULT, "gzip")
        require(spark.conf.get(base.CODEC_DEFAULT) == "gzip", "FROZEN_GZIP_DEFAULT_BEFORE_CATALOG")
        result = execute(spark, progress)
    except Exception as error:
        text = str(error)
        failure = text if re.fullmatch(r"[A-Z0-9_]{1,128}", text) else "EXPIRATION_BOOTSTRAP_FAILED_OR_UNKNOWN"
    finally:
        if spark is not None:
            try:
                spark.stop()
            except Exception:
                close_failed = True
        passed = result is not None and failure is None and not close_failed
        new_json(PROOF / "expiration-spark-diagnostic.json", {"scope": SCOPE, "passed": passed, **progress,
                 "sessionStopFailed": close_failed, "failureCode": failure, "automaticRetryPerformed": False,
                 "expirationOutcome": "VERIFIED" if progress["expirationVerified"] else "UNKNOWN" if progress["expirationInvoked"] else "NOT_ATTEMPTED"})
        if result is not None:
            new_json(PROOF / "expiration-spark-result.private.json", result)
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
