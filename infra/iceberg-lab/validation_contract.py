"""Pure checks for FUTURE root-owned evidence. Does not collect or assert live facts."""
import hashlib
import json
import re
from pathlib import PurePosixPath
from render_plan import NAMESPACE
from sql_plan import BUCKET, verify_rows, verify_snapshots

MIB = 1024**2
GIB = 1024**3


def require(value, code):
    if not value:
        raise ValueError(code)


def preflight(record, baseline):
    fields = {"scope", "productionSourceCommit", "productionBaselineSha256", "originalJobs", "originalExports", "originalSlotFree",
              "originalKafkaOffset", "originalKafkaEnd", "originalPvcCount", "originalPodCount", "originalDockerCount",
              "originalRunningDockerCount", "namespaceAbsent", "bucketAbsent", "newCredentialIdentity", "existingVolumes",
              "memoryAvailableBytes", "diskAvailableBytes", "freeInodes", "heavyCiActive", "networkPolicyControllerPresent"}
    require(isinstance(record, dict) and set(record) == fields and record["scope"] == "PHASE6_LIVE_READONLY_PREFLIGHT", "EXACT_LIVE_PREFLIGHT_CONTRACT_REQUIRED")
    require(re.fullmatch(r"[0-9a-f]{40}", record["productionSourceCommit"]) and re.fullmatch(r"[0-9a-f]{64}", record["productionBaselineSha256"]), "CURRENT_PRODUCTION_PROOF_IDENTITY_REQUIRED")
    count_fields = {"originalJobs", "originalExports", "originalKafkaOffset", "originalKafkaEnd", "originalPvcCount", "originalPodCount", "originalDockerCount", "originalRunningDockerCount"}
    baseline_fields = count_fields | {"productionSourceCommit", "productionBaselineSha256", "existingVolumes"}
    require(isinstance(baseline, dict) and set(baseline) == baseline_fields
            and all(type(baseline[key]) is int and 0 <= baseline[key] <= 10000 for key in count_fields)
            and baseline["originalPvcCount"] > 0 and baseline["originalJobs"] > 0
            and baseline["originalKafkaOffset"] == baseline["originalKafkaEnd"], "INDEPENDENT_CURRENT_BASELINE_REQUIRED")
    require(all(record[key] == value and type(record[key]) is type(value) for key, value in baseline.items()), "CURRENT_ORIGINAL_BASELINE_CHANGED")
    require(all(record[key] is True for key in ("originalSlotFree", "namespaceAbsent", "bucketAbsent", "newCredentialIdentity", "networkPolicyControllerPresent"))
            and record["heavyCiActive"] is False, "FRESH_OWN_SCOPE_AND_QUIET_START_REQUIRED")
    require(type(record["memoryAvailableBytes"]) is int and record["memoryAvailableBytes"] >= 9 * GIB
            and type(record["diskAvailableBytes"]) is int and record["diskAvailableBytes"] >= 20 * GIB
            and type(record["freeInodes"]) is int and record["freeInodes"] >= 100000, "HOST_RESERVE_BEFORE_FIVE_GIB_TRIAL_REQUIRED")
    require(isinstance(record["existingVolumes"], list) and len(record["existingVolumes"]) == record["originalPvcCount"]
            and len(set(record["existingVolumes"])) == record["originalPvcCount"]
            and all(isinstance(path, str) and PurePosixPath(path).is_absolute() for path in record["existingVolumes"]), "CURRENT_EXISTING_VOLUME_PATH_ANCHORS_REQUIRED")
    return True


def payload():
    return bytes(range(256)) * (6 * MIB // 256)


def store_plan():
    body = payload()
    return {"schemaVersion": 1, "status": "PREPARED_NOT_RUN", "bucket": BUCKET, "region": "garage", "requestRetries": 0,
            "smallObject": {"key": "capability/metadata.json", "body": '{"fixture":"phase6","schemaVersion":1}\n'},
            "multipart": {"key": "capability/multipart-6m.bin", "bytes": len(body), "sha256": hashlib.sha256(body).hexdigest(),
                          "parts": [{"number": 1, "bytes": 5 * MIB, "sha256": hashlib.sha256(body[:5 * MIB]).hexdigest()},
                                    {"number": 2, "bytes": MIB, "sha256": hashlib.sha256(body[5 * MIB:]).hexdigest()}]},
            "ranges": [{"start": start, "endInclusive": end, "expectedStatus": 206,
                        "contentRange": "bytes %d-%d/%d" % (start, end, len(body)),
                        "sha256": hashlib.sha256(body[start:end + 1]).hexdigest()}
                       for start, end in ((0, 255), (5 * MIB - 16, 5 * MIB + 15))],
            "requiredMethods": ["PutObject", "HeadObject", "GetObject", "CreateMultipartUpload", "UploadPart", "CompleteMultipartUpload", "ListObjectsV2"],
            "etagIsSha256": False, "deleteOrAbortPlanned": False, "trinoNativePathVerified": False}


def verify_store_capability(record):
    require(isinstance(record, dict) and set(record) == {"scope", "bucket", "keyPermissions", "initialObjectCount", "smallObjectWholeBytesVerified",
        "multipartUploadIdRecorded", "partNumbers", "partSizes", "multipartCompletedOnce", "multipartHeadBytes", "multipartWholeSha256",
        "rangeRecords", "listingEnded", "listedKeys", "requestAttemptsRecorded", "unknownOutcome", "trinoNativePathVerified"}, "EXACT_CAPABILITY_RECEIPT_REQUIRED")
    expected = store_plan()
    require(record["scope"] == "OWN_FRESH_BUCKET_S3_CAPABILITY" and record["bucket"] == BUCKET
            and record["keyPermissions"] == {"read": True, "write": True, "owner": False, "createBucket": False, "bucketCount": 1}
            and type(record["initialObjectCount"]) is int and record["initialObjectCount"] == 0, "FRESH_BUCKET_SCOPED_GARAGE_ACL_REQUIRED")
    require(all(record[key] is True for key in ("smallObjectWholeBytesVerified", "multipartUploadIdRecorded", "multipartCompletedOnce", "listingEnded", "requestAttemptsRecorded"))
            and record["unknownOutcome"] is False and record["trinoNativePathVerified"] is False, "RECORDED_REQUESTS_WITHOUT_NATIVE_TRINO_CLAIM_REQUIRED")
    require(record["partNumbers"] == [1, 2] and record["partSizes"] == [5 * MIB, MIB]
            and record["multipartHeadBytes"] == 6 * MIB and record["multipartWholeSha256"] == expected["multipart"]["sha256"], "ACTUAL_TWO_PART_SIX_MIB_BYTES_REQUIRED")
    ranges = [{**{key: value for key, value in item.items() if key != "expectedStatus"}, "status": item["expectedStatus"]} for item in expected["ranges"]]
    require(record["rangeRecords"] == ranges
            and record["listedKeys"] == ["capability/metadata.json", "capability/multipart-6m.bin"], "EXACT_RANGE_AND_COMPLETE_LIST_REQUIRED")
    return True


def verify_restart(before, after):
    fields = {"trinoPodUid", "trinoContainerId", "trinoImageConfigDigest", "postgresPodUid", "postgresContainerId", "postgresProcessStartTicks", "postgresPvcUid", "trinoPvcUid",
              "catalogMetadataPointer", "rows", "snapshots", "configSha256"}
    require(set(before) == set(after) == fields, "EXACT_RESTART_PROJECTION_REQUIRED")
    for record in (before, after):
        verify_rows(record["rows"], 12); verify_snapshots(record["snapshots"])
        require(all(isinstance(record[key], str) and re.fullmatch(r"[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}", record[key])
                    for key in ("trinoPodUid", "postgresPodUid", "postgresPvcUid", "trinoPvcUid"))
                and re.fullmatch(r"containerd://[0-9a-f]{64}", record["trinoContainerId"])
                and isinstance(record["postgresContainerId"], str) and re.fullmatch(r"containerd://[0-9a-f]{64}", record["postgresContainerId"])
                and type(record["postgresProcessStartTicks"]) is int and record["postgresProcessStartTicks"] > 0
                and record["trinoImageConfigDigest"] == "sha256:1a95bd13a3771179e2859fba98fc5831091a82f65ca12d193144be40d3bbd921"
                and re.fullmatch(r"[0-9a-f]{64}", record["configSha256"]), "BOUNDED_REAL_RESOURCE_IDENTITY_REQUIRED")
        require(isinstance(record["catalogMetadataPointer"], str) and record["catalogMetadataPointer"].startswith("s3://" + BUCKET + "/warehouse/phase6/bronze/synthetic_events/metadata/")
                and ".." not in record["catalogMetadataPointer"] and record["catalogMetadataPointer"].endswith(".metadata.json"), "OWN_CATALOG_POINTER_REQUIRED")
    require(before["trinoPodUid"] != after["trinoPodUid"] and before["trinoContainerId"] != after["trinoContainerId"], "ACTUAL_NEW_TRINO_PROCESS_IDENTITY_REQUIRED")
    require(all(before[key] == after[key] for key in fields - {"trinoPodUid", "trinoContainerId"}), "SAME_CATALOG_VOLUMES_ROWS_SNAPSHOTS_CONFIG_REQUIRED")
    return True


if __name__ == "__main__":
    print(json.dumps(store_plan(), indent=2))
