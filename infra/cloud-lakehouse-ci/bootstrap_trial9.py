"""One Spark application, frozen Silver.run, then exactly one Bronze rewrite."""
import json
import os
from pathlib import Path
import re
import time
import base_bootstrap as base
from contract import PROCEDURE, files, procedure_result, require, rows, row_sha, snapshot_chain
from s3_readonly import Client, clock, new_json


def snapshots(spark, table):
    values = [row.asDict() for row in spark.sql("SELECT CAST(snapshot_id AS STRING) AS snapshot_id,CAST(parent_id AS STRING) AS parent_id,operation,element_at(summary,'total-records') AS total_records FROM " + table + ".snapshots").limit(4).collect()]
    return values


def current_files(spark, table):
    return [row.asDict() for row in spark.sql("SELECT file_path,record_count,file_size_in_bytes,content FROM " + table + ".files").limit(3).collect()]


def execute(spark, advance=lambda phase: None):
    import spark_silver as silver
    from silver_contract import FIELDS, SOURCE_SHA, classify, golden_bronze, row_sha as frozen_row_sha
    deadline = clock()
    client = Client(deadline)
    require(client.listing() == [], "ACTUAL_FRESH_BUCKET_WAREHOUSE_EMPTY_BEFORE_CATALOG")
    require(row_sha(golden_bronze()) == frozen_row_sha(golden_bronze()), "UNCHANGED_CLOUD8_ROW_FINGERPRINT_FUNCTION")
    # Exact frozen computation makes Bronze and Silver, validates time travel,
    # one MERGE and same-application replay. Its original proof stays private.
    advance("FROZEN_WRITE_AND_SILVER")
    base.execute(spark, silver, FIELDS, SOURCE_SHA, golden_bronze, require, frozen_row_sha, lambda phase: deadline.remaining(180, 90))
    require(spark.table(silver.SOURCE_TABLE).schema["sensor_value"].dataType.simpleString() == "double"
            and spark.table(silver.TARGET_TABLE).schema["sensor_value"].dataType.simpleString() == "double", "ACTUAL_SPARK_DOUBLE_SCHEMAS")
    golden = golden_bronze()
    before_snapshots = snapshot_chain(snapshots(spark, silver.SOURCE_TABLE), 2)
    before_files = files(current_files(spark, silver.SOURCE_TABLE), 2)
    before_silver = rows(silver.ordered(spark.table(silver.TARGET_TABLE)), classify(golden), True)
    silver_snapshots = silver.snapshots(spark)
    require(len(silver_snapshots) == 1, "ONE_SILVER_SNAPSHOT_BEFORE_COMPACTION")
    advance("BEFORE_COMPACTION_WHOLE_CAPTURE")
    old_objects = client.capture("before-compaction")
    deadline.remaining(180, 90)
    advance("COMPACTION_ONCE")
    new_json(Path("/proof/procedure-intent.json"), {"sqlSha256": __import__("hashlib").sha256(PROCEDURE.encode()).hexdigest(), "invocations": 1, "automaticRetry": False})
    outputs = [value.asDict() for value in spark.sql(PROCEDURE).limit(2).collect()]
    require(len(outputs) == 1, "EXACTLY_ONE_PROCEDURE_RESULT_ROW")
    procedure = procedure_result(outputs[0])
    advance("THREE_SNAPSHOTS_AND_SILVER_VERIFY")
    spark.catalog.refreshTable(silver.SOURCE_TABLE)
    chain = snapshot_chain(snapshots(spark, silver.SOURCE_TABLE), 3)
    require(chain[:2] == before_snapshots, "TWO_OLD_SNAPSHOTS_UNCHANGED")
    after_files = files(current_files(spark, silver.SOURCE_TABLE), 1)
    require(after_files[0]["file_path"] not in {value["file_path"] for value in before_files}, "NEW_REWRITE_DATA_FILE")
    fingerprints = []
    for index, value in enumerate(chain):
        expected = golden[:6] if index == 0 else golden
        frame = spark.read.option("versionAsOf", value["snapshot_id"]).table(silver.SOURCE_TABLE).select(*FIELDS)
        require(frame.schema["sensor_value"].dataType.simpleString() == "double", "SNAPSHOT_DOUBLE_SCHEMA")
        fingerprints.append(row_sha(rows(silver.ordered(frame), expected)))
    require(fingerprints[1] == fingerprints[2], "TWELVE_ROWS_UNCHANGED_BY_REWRITE")
    require(rows(silver.ordered(spark.table(silver.TARGET_TABLE)), classify(golden), True) == before_silver
            and silver.snapshots(spark) == silver_snapshots, "SILVER_WHOLE_ROWS_AND_SNAPSHOT_UNCHANGED")
    advance("AFTER_COMPACTION_WHOLE_CAPTURE")
    after_objects = client.capture("after-compaction", old_objects)
    return {"passed": True, "snapshots": chain, "rowFingerprints": fingerprints,
            "silverRowsSha256": row_sha(before_silver), "silverSnapshotIds": [str(value["snapshot_id"]) for value in silver_snapshots],
            "beforeFiles": before_files, "afterFiles": after_files, "procedure": procedure,
            "oldWarehouseObjects": len(old_objects), "afterWarehouseObjects": len(after_objects),
            "mergeInvocations": 1, "sequentialReplayInvocations": 1, "replayWriteInvocations": 0}


def main():
    spark, result, error, stop_failed = None, None, None, False
    started = time.monotonic()
    phase = "SESSION"
    failure_code = None
    sequence = 0
    def advance(value):
        nonlocal phase, sequence
        require(value in ("SESSION", "GZIP_DEFAULT", "FROZEN_WRITE_AND_SILVER", "BEFORE_COMPACTION_WHOLE_CAPTURE", "COMPACTION_ONCE", "THREE_SNAPSHOTS_AND_SILVER_VERIFY", "AFTER_COMPACTION_WHOLE_CAPTURE", "STOP_SESSION", "COMPLETED"), "FIXED_TRIAL9_DIAGNOSTIC_PHASE")
        phase = value
        sequence += 1
        require(sequence <= 9, "FIXED_PROGRESS_TRANSITION_BOUND")
        final = Path("/proof/trial9-progress-%02d.json" % sequence)
        temporary = final.with_name("." + final.name + ".tmp")
        new_json(temporary, {"phase": value, "sequence": sequence, "completionNotProven": True,
                            "elapsedMillis": int((time.monotonic() - started) * 1000)})
        os.link(temporary, final, follow_symlinks=False)
        temporary.unlink()
    try:
        import spark_silver as silver
        advance("SESSION")
        spark = silver.session()
        advance("GZIP_DEFAULT")
        spark.conf.set(base.CODEC_DEFAULT, "gzip")
        require(spark.conf.get(base.CODEC_DEFAULT) == "gzip", "FROZEN_GZIP_DEFAULT_BEFORE_CATALOG")
        result = execute(spark, advance)
    except Exception as failure:
        error = base.exception_classes(failure)
        failure_code = failure.args[0] if type(failure) in (ValueError, RuntimeError) and len(failure.args) == 1 and type(failure.args[0]) is str and re.fullmatch(r"[A-Z0-9_]{1,128}", failure.args[0]) else "TRIAL9_RUNTIME_FAILURE_OR_UNKNOWN"
    finally:
        if spark is not None:
            try:
                if error is None: advance("STOP_SESSION")
                spark.stop()
            except Exception as failure:
                stop_failed = True
                if error is None:
                    error = base.exception_classes(failure)
    if error is None and not stop_failed: advance("COMPLETED")
    diagnostic = {"passed": error is None and not stop_failed, "phase": "COMPLETED" if error is None else phase,
                  "sessionStopFailed": stop_failed, "exceptionClassesOnly": error,
                  "fixedFailureCode": failure_code,
                  "elapsedMillis": int((time.monotonic() - started) * 1000)}
    new_json(Path("/proof/trial9-spark-diagnostic.json"), diagnostic)
    if error is None and result is not None and not stop_failed:
        new_json(Path("/proof/trial9-spark-result.json"), result)
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
