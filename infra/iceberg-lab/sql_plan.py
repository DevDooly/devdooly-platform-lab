"""Pure offline Bronze SQL plan and result validators. No SQL or network execution."""
import hashlib
import json
from pathlib import Path

BUCKET = "platform-lab-iceberg-plan2-20261016"
SOURCE_SHA = "39ba10d8c47dce790f3ccc9c9134fea593d6de31f1f3a7992ca61d9f554da3b5"
TABLE = "iceberg.bronze.synthetic_events"
ROOT = Path(__file__).resolve().parent


def require(value, code):
    if not value:
        raise ValueError(code)


def source_bytes():
    raw = (ROOT / "fixtures/synthetic-v1.ndjson").read_bytes()
    require(len(raw) == 1100 and hashlib.sha256(raw).hexdigest() == SOURCE_SHA, "PUBLIC_V1_FINGERPRINT_MISMATCH")
    return raw


def golden_rows(count=12):
    require(type(count) is int and count in (0, 6, 12), "FIXED_BRONZE_COUNT_REQUIRED")
    source = [json.loads(line) for line in source_bytes().decode().splitlines()]
    return [{"input_sequence": i + 1, "event_id": event["eventId"], "sensor_id": event["sensorId"],
             "event_time_raw": event["eventTime"], "sensor_value": event["value"], "source_sha256": SOURCE_SHA}
            for i, event in enumerate(source[:count])]


def rows_sha(rows):
    fields = ("input_sequence", "event_id", "sensor_id", "event_time_raw", "sensor_value", "source_sha256")
    require(isinstance(rows, list) and all(isinstance(row, dict) and set(row) == set(fields) for row in rows), "EXACT_ROW_FIELDS_FOR_HASH")
    ordered = [{key: row[key] for key in fields} for row in rows]
    return hashlib.sha256((json.dumps(ordered, separators=(",", ":"), ensure_ascii=True) + "\n").encode()).hexdigest()


def quote(value):
    # Only fixed reviewed public fixture strings reach SQL. No caller-provided SQL fragments.
    require(isinstance(value, str) and len(value) <= 256 and "\n" not in value and "\r" not in value, "BOUNDED_SQL_LITERAL_REQUIRED")
    return "'" + value.replace("'", "''") + "'"


def insert_batch(number):
    require(type(number) is int and number in (1, 2), "EXACTLY_TWO_FIXED_INSERTS_REQUIRED")
    rows = golden_rows()[0:6] if number == 1 else golden_rows()[6:12]
    values = []
    for row in rows:
        values.append("(" + ", ".join([str(row["input_sequence"]), quote(row["event_id"]), quote(row["sensor_id"]),
                                      quote(row["event_time_raw"]), str(row["sensor_value"]), quote(SOURCE_SHA)]) + ")")
    return "INSERT INTO " + TABLE + " VALUES\n" + ",\n".join(values) + ";\n"


def ordered_rows_query(snapshot_id=None):
    version = ""
    if snapshot_id is not None:
        require(type(snapshot_id) is int and 0 < snapshot_id <= (1 << 63) - 1, "POSITIVE_BIGINT_SNAPSHOT_REQUIRED")
        version = " FOR VERSION AS OF " + str(snapshot_id)
    return "SELECT input_sequence,event_id,sensor_id,event_time_raw,sensor_value,source_sha256 FROM " + TABLE + version + " ORDER BY input_sequence;"


def plan():
    return {
        "schemaVersion": 2, "status": "PREPARED_NOT_RUN", "scope": "BRONZE_RAW_ONLY",
        "catalog": "phase6", "bucket": BUCKET, "sourceSha256": SOURCE_SHA,
        "sourceBytes": len(source_bytes()), "logicalRows": 12,
        "statements": [
            {"name": "create_schema", "mutation": True, "sql": "CREATE SCHEMA iceberg.bronze WITH (location='s3://" + BUCKET + "/warehouse/phase6/bronze');"},
            {"name": "create_table", "mutation": True, "sql": "CREATE TABLE " + TABLE + " (input_sequence INTEGER,event_id VARCHAR,sensor_id VARCHAR,event_time_raw VARCHAR,sensor_value DOUBLE,source_sha256 VARCHAR) WITH (format='PARQUET',format_version=2,location='s3://" + BUCKET + "/warehouse/phase6/bronze/synthetic_events');"},
            {"name": "read_initial_empty", "mutation": False, "sql": ordered_rows_query()},
            {"name": "insert_six_1", "mutation": True, "sql": insert_batch(1)},
            {"name": "read_snapshot_1", "mutation": False, "sql": ordered_rows_query()},
            {"name": "insert_six_2", "mutation": True, "sql": insert_batch(2)},
            {"name": "read_snapshot_2", "mutation": False, "sql": ordered_rows_query()},
        ],
        "inspection": {
            "snapshots": "SELECT snapshot_id,parent_id,operation,element_at(summary,'added-records') AS added_records,element_at(summary,'total-records') AS total_records FROM iceberg.bronze.\"synthetic_events$snapshots\" ORDER BY committed_at,snapshot_id;",
            "history": "SELECT * FROM iceberg.bronze.\"synthetic_events$history\" ORDER BY made_current_at;",
            "files": "SELECT file_path,file_format,record_count,file_size_in_bytes FROM iceberg.bronze.\"synthetic_events$files\" ORDER BY file_path;",
            "counts": "SELECT count(*) AS input_rows,count(DISTINCT event_id) AS distinct_event_ids,count_if(sensor_id='sensor-a') AS sensor_a,count_if(sensor_id='sensor-b') AS sensor_b,count_if(try(from_iso8601_timestamp(event_time_raw)) IS NULL) AS bad_timestamp,count_if(sensor_value<0 OR sensor_value>100) AS out_of_range FROM " + TABLE + ";",
        },
        "expected": {
            "initial": {"rows": 0, "distinctEventIds": 0, "sensorA": 0, "sensorB": 0, "addedRecordsSummary": None, "goldenRowsSha256": rows_sha([])},
            "first": {"rows": 6, "distinctEventIds": 5, "sensorA": 5, "sensorB": 1, "goldenRowsSha256": rows_sha(golden_rows(6))},
            "second": {"rows": 12, "distinctEventIds": 10, "sensorA": 8, "sensorB": 4, "badTimestamp": 1, "outOfRange": 1, "goldenRowsSha256": rows_sha(golden_rows())},
        },
        "snapshotInspectionMode": "INITIAL_EMPTY_PLUS_TWO_DATA_APPENDS", "initialEmptySnapshots": 1, "dataAppendSnapshots": 2, "totalSnapshots": 3,
        "timeTravelExpectedRows": [0, 6, 12], "httpWireNormalization": "ONE_TERMINAL_SEMICOLON_ONLY",
        "operatorQueryResubmissionRetries": 0, "dropOrExpireOrGcPlanned": False, "silverProcessorImplemented": False,
        "runtimeResultsVerified": False,
    }


def verify_rows(rows, count):
    require(rows == golden_rows(count), "EXACT_ORDERED_BRONZE_RAW_ROWS_REQUIRED")
    return rows_sha(rows)


def verify_snapshots(rows):
    require(isinstance(rows, list) and len(rows) == 3, "INITIAL_EMPTY_PLUS_TWO_DATA_APPENDS_REQUIRED")
    ids = []
    for number, row in enumerate(rows):
        require(set(row) == {"snapshot_id", "parent_id", "operation", "added_records", "total_records"}, "ALLOWLISTED_SNAPSHOT_FIELDS_REQUIRED")
        sid = row["snapshot_id"]
        require(type(sid) is int and 0 < sid <= (1 << 63) - 1 and sid not in ids, "UNIQUE_POSITIVE_SNAPSHOT_ID_REQUIRED")
        require(row["operation"] == "append" and row["added_records"] == (None if number == 0 else "6")
                and row["total_records"] == str(number * 6), "INITIAL_NULL_AND_SIX_PLUS_SIX_SUMMARY_REQUIRED")
        require(row["parent_id"] == (None if number == 0 else ids[-1]), "SNAPSHOT_PARENT_CHAIN_REQUIRED")
        ids.append(sid)
    return ids


if __name__ == "__main__":
    print(json.dumps(plan(), indent=2))
