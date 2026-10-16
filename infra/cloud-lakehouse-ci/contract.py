"""Fixed synthetic cross-engine contract; no network, Spark or subprocess imports."""
import hashlib
import json
import math
import re
import time

SCOPE = "FRESH_CLOUD_SPARK_TRINO_BRONZE_TWO_FILE_COMPACTION"
FIELDS = ("input_sequence", "event_id", "sensor_id", "event_time_raw", "sensor_value", "source_sha256")
OUTPUT_FIELDS = ("batch_id", *FIELDS, "status", "reason")
TRINO = "docker.io/trinodb/trino@sha256:db58cc93e593a2706553745f276bb119c9810e69918be56ecde088ba7ccb0534"
PROCEDURE = """CALL phase6.system.rewrite_data_files(
table => 'bronze.synthetic_events', strategy => 'binpack',
options => map('min-input-files','2','rewrite-all','true',
'target-file-size-bytes','262144','max-file-group-size-bytes','1048576',
'max-concurrent-file-group-rewrites','1','partial-progress.enabled','false',
'remove-dangling-deletes','false','max-files-to-rewrite','2'))"""


def require(value, code):
    if not value:
        raise ValueError(code)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def row_sha(rows):
    # Same public serialization as the frozen Cloud8 silver_contract.row_sha.
    return sha((json.dumps(rows, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n").encode())


def rows(values, golden, silver=False):
    fields = OUTPUT_FIELDS if silver else FIELDS
    require(type(values) is list and len(values) == len(golden) and len(values) in (6, 12), "EXACT_FIXED_ROW_COUNT")
    result = []
    for index, (value, expected) in enumerate(zip(values, golden), 1):
        require(type(value) is dict and set(value) == set(fields) and type(value["input_sequence"]) is int
                and value["input_sequence"] == index, "EXACT_COLUMNS_AND_ORDERED_SEQUENCE")
        number = value["sensor_value"]
        require(type(number) in (int, float) and math.isfinite(number), "FINITE_DOUBLE_RESPONSE_VALUE")
        require(value == expected, "ACTUAL_VALUES_EQUAL_FROZEN_GOLDEN")
        normalized = {name: value[name] for name in fields}
        # Projection follows independently observed SQL DOUBLE schema. It only
        # normalizes JSON representation; equality above preserves actual value.
        normalized["sensor_value"] = float(number)
        result.append(normalized)
    return result


def snapshot_chain(values, count):
    require(type(values) is list and len(values) == count and count in (2, 3), "EXACT_SNAPSHOT_COUNT")
    lookup = {}
    for value in values:
        require(set(value) == {"snapshot_id", "parent_id", "operation", "total_records"}, "SNAPSHOT_FIELD_SET")
        sid, parent = value["snapshot_id"], value["parent_id"]
        require(type(sid) is str and re.fullmatch(r"[1-9][0-9]{0,18}", sid) and int(sid) < 2**63, "POSITIVE_BIGINT_STRING")
        require(parent is None or type(parent) is str and re.fullmatch(r"[1-9][0-9]{0,18}", parent) and int(parent) < 2**63, "PARENT_BIGINT_STRING_OR_NULL")
        require(sid not in lookup and type(value["total_records"]) is str, "UNIQUE_SNAPSHOT_ACTUAL_SUMMARY")
        lookup[sid] = value
    roots = [value for value in values if value["parent_id"] is None]
    require(len(roots) == 1, "ONE_ACTUAL_ROOT_SNAPSHOT")
    chain = roots
    while len(chain) < count:
        following = [value for value in values if value["parent_id"] == chain[-1]["snapshot_id"]]
        require(len(following) == 1 and following[0] not in chain, "UNIQUE_ACTUAL_PARENT_CHAIN")
        chain.append(following[0])
    require([value["operation"] for value in chain] == ["append", "append", "replace"][:count]
            and [value["total_records"] for value in chain] == ["6", "12", "12"][:count], "EXACT_APPEND_APPEND_REPLACE_ROWS")
    return chain


def files(values, count):
    require(type(values) is list and len(values) == count and count in (1, 2), "EXACT_CURRENT_DATA_FILE_COUNT")
    paths = set()
    for value in values:
        require(set(value) == {"file_path", "record_count", "file_size_in_bytes", "content"}, "EXACT_DATA_FILE_FIELDS")
        path = value["file_path"]
        require(type(path) is str and path.startswith("s3://platform-lab-iceberg-20261015/warehouse/phase6/bronze/synthetic_events/data/")
                and ".." not in path.split("/") and path not in paths, "ONLY_FRESH_BRONZE_UNIQUE_DATA_PATH")
        require(type(value["content"]) is int and value["content"] == 0
                and type(value["record_count"]) is int and value["record_count"] == (6 if count == 2 else 12)
                and type(value["file_size_in_bytes"]) is int and 0 < value["file_size_in_bytes"] <= 262144, "SMALL_DATA_ONLY_EXACT_RECORDS")
        paths.add(path)
    return sorted(values, key=lambda value: value["file_path"])


def procedure_result(value):
    require(type(value) is dict and set(value) == {"rewritten_data_files_count", "added_data_files_count", "rewritten_bytes_count", "failed_data_files_count", "removed_delete_files_count"}, "PINNED_ICEBERG_111_PROCEDURE_OUTPUT")
    require(all(type(number) is int and 0 <= number <= 1048576 for number in value.values())
            and value["rewritten_data_files_count"] == 2 and value["added_data_files_count"] == 1
            and value["rewritten_bytes_count"] > 0 and value["failed_data_files_count"] == value["removed_delete_files_count"] == 0, "ACTUAL_TWO_TO_ONE_NO_FAILED_OR_DELETE_FILES")
    return value


def query_plan(chain):
    chain = snapshot_chain(chain, 3)
    columns = ",".join(FIELDS)
    base = "iceberg.bronze.synthetic_events"
    queries = [("version", "SELECT version() AS version"),
               ("bronze-double", "SELECT typeof(sensor_value) AS kind FROM " + base + " LIMIT 1"),
               ("silver-double", "SELECT typeof(sensor_value) AS kind FROM iceberg.silver.sensor_outcomes LIMIT 1")]
    for index, item in enumerate(chain, 1):
        queries.append(("snapshot-%d" % index, "SELECT " + columns + " FROM " + base + " FOR VERSION AS OF " + item["snapshot_id"] + " ORDER BY input_sequence"))
    queries.extend([("current-bronze", "SELECT " + columns + " FROM " + base + " ORDER BY input_sequence"),
                    ("current-silver", "SELECT " + ",".join(OUTPUT_FIELDS) + " FROM iceberg.silver.sensor_outcomes ORDER BY input_sequence"),
                    ("snapshots", "SELECT CAST(snapshot_id AS VARCHAR) AS snapshot_id,CAST(parent_id AS VARCHAR) AS parent_id,operation,element_at(summary,'total-records') AS total_records FROM iceberg.bronze.\"synthetic_events$snapshots\""),
                    ("files", "SELECT file_path,record_count,file_size_in_bytes,content FROM iceberg.bronze.\"synthetic_events$files\"")])
    require(len(queries) == 10 and all(sql.startswith("SELECT ") and ";" not in sql for _, sql in queries), "TEN_FIXED_SELECTS_ONLY")
    return queries


def parse_cli(raw, maximum_rows=13):
    require(type(raw) is bytes and 0 < len(raw) <= 65536, "BOUNDED_TRINO_JSON_LINES")
    values = []
    def pairs(items):
        require(len({key for key, _ in items}) == len(items), "NO_DUPLICATE_JSON_FIELDS")
        return dict(items)
    for line in raw.decode("utf-8").splitlines():
        require(line.strip(), "NO_EMPTY_OR_DIAGNOSTIC_JSON_LINE")
        value = json.loads(line, object_pairs_hook=pairs, parse_constant=lambda _: require(False, "NO_NONFINITE_JSON"))
        require(type(value) is dict, "JSON_OBJECT_EACH_ROW")
        values.append(value)
        require(len(values) <= maximum_rows, "TRINO_ROW_LIMIT")
    return values


def normal_exit(role, value, stop=None):
    require(type(value["running"]) is bool and value["running"] is False
            and type(value["exitCode"]) is int and value["oom"] is False, "OBSERVED_TERMINATED_NON_OOM")
    if role == "trino":
        require(type(stop) is dict and stop["requestReturnedZero"] is True
                and stop["cid"] == value["id"] and stop["startedAt"] == value["startedAt"]
                and stop["signalScope"] == "CONFIGURED_OR_DEFAULT_SIGTERM"
                and value["exitCode"] in (0, 143), "OWN_REQUESTED_TRINO_TERM_EXIT_0_OR_143")
    else:
        require(value["exitCode"] == 0, "OWN_SPARK_OR_READER_EXIT_ZERO")
    return value


class Deadline:
    def __init__(self, started, now=time.monotonic):
        require(type(started) in (int, float) and math.isfinite(started)
                and now() >= started, "OBSERVED_NONFUTURE_MONOTONIC_CLOCK")
        self.started, self.now = started, now

    def remaining(self, maximum, reserve=0):
        value = 600 - (self.now() - self.started) - reserve
        require(value > 0 and 0 < maximum <= 600 and reserve >= 0, "SINGLE_WORKLOAD_DEADLINE_NO_RESET")
        return min(maximum, value)
