# Closed-copy decoder wire v1 (구현 공동 계약)

SOURCE_CONTRACT_NOT_RUN. Python loader/normalizer는 core, Java decoder는 runtime_integration, 실제 prep·composite·new decoder CID lifecycle은 job_observation 소유입니다. 과거73e/c63/127/ec1은 수정하지 않습니다.

## 실행·frame

Main class는 `org.apache.iceberg.ClosedCopyDecoder`, 유일 argv는 `--budget-millis <정수1..60000>`입니다. relative watchdog은 stdin/frame/decode/output 전체를 제한하며 host의 기존 started+600 절대 cutoff를 대신하지 않습니다. 정상/handled failure는 모든 열린 RAM stream을 finally로 닫습니다. hard watchdog/OOM은 완료 reply/close 증명 없이 nonzero로 끝날 수 있으며 host가 exact CID terminal/cleanup을 별도로 관측합니다.

stdin은 ASCII8 `ICCPY001` + u32BE descriptor byte length(1..524288) + strict UTF-8 JSON + u32BE object count(1..128) + 각 object의 u32BE size(0..4194304) 및 bytes + EOF입니다. objects는 key ASCII 오름차순이며 size 합계≤33554432. 전체 frame 상한은 `8+4+524288+4+128*4+33554432`로 payload 상한과 구별합니다. Java는 모든 size/whole SHA/alias/copy filename을 다시 검사합니다.

Descriptor exact10: `schemaVersion:1`, `scope:"CLOSED_COPY_ICEBERG_FORMAT2_DECODE"`, `sourceCommit`, `producerSha256`, `runtimeManifestSha256`, `captureMapSha256`, `approvedBucket`, `approvedPrefix`, `targetTable`, `objects`. sourceCommit40hex, producer/runtime은73e/c63, SHA는 lowercase64hex입니다. targetTable exact5는 `catalog`, `namespace`, `table`, `currentMetadataUri`, `tableLocation`; objects exact5는 `key`, `size`, `sha256`, `copy`, `alias`입니다. alias=`f-`+SHA256(canonical ASCII JSON `[bucket,key]`), copy=SHA256(key UTF-8)+`.bin`. URI는 정확한 `s3://bucket/key` map lookup만 지원합니다. 중복 JSON/비정상 수/UTF-8/unknown field/foreign URI/중복·충돌/EOF 뒤 bytes는 거부합니다. 외부 named/lifecycle/validation/clock authority는 이 descriptor만으로 검증됐다고 주장하지 않습니다.

## stdout reply

UTF-8 JSON 한 document+LF, 최대4MiB. top exact6: `schemaVersion:1`, `scope:"CLOSED_COPY_ICEBERG_FORMAT2_GRAPH"`, `status`, `reasonCodes`, `descriptorSha256`, `graph`. status는 DECODED(exit0), UNDETERMINED(exit2), REJECTED(exit3)뿐입니다. watchdog은 exit124이며 완성 JSON이 없을 수 있습니다. descriptorSha256은 읽은 descriptor bytes의 SHA 또는 descriptor를 확보하기 전 실패 시 null입니다. REJECTED graph는 null이고 가짜 inventory/count를 만들지 않습니다. UNDETERMINED는 확인된 map의 KEEP graph만 반환하며 completeness를 올리지 않습니다.

Graph exact10: `tableId`, `currentMetadataId`, `currentSnapshotId`, `metadataNodes`, `snapshotNodes`, `refNodes`, `fileNodes`, `edges`, `completeness`, `decoderProvenance`. tableId는 `t-`+SHA256(canonical ASCII JSON `[catalog,namespace,table,metadata UUID]`) 또는 UUID 미확인 null입니다(ASCII 이름만 지원하며 separators는 `(',', ':')`, ensure_ascii=true). currentSnapshotId는 실제 positive signed BIGINT decimal string 또는 미확인 null. currentMetadataId는 승인 file alias입니다.

- metadataNodes exact `{id,role}`: role CURRENT/HISTORICAL; old metadata whole bytes KEEP, 역사 복구 검증 아님.
- snapshotNodes exact `{id,parentId,committedAt,manifestListId,fileIds}`: 실제 timestamp-ms→UTC, root만 parent null, manifestListId는 실제 manifest-list alias이며 fileIds는 manifest-list/manifest/all entries/delete-reference **전이 closure 전체**. Python은 edges를 독립 순회해 closure를 재계산하고 Java fileIds와 비교합니다.
- refNodes exact `{name,kind,snapshotId}`: name은 r-SHA(raw ref UTF-8), kind TAG/BRANCH. unknown은 추측하지 않음.
- fileNodes exact `{id,kind,size,sha256}`: 선택 table prefix의 모든 승인 객체. kind DATA/DELETE/MANIFEST/MANIFEST_LIST/METADATA/UNKNOWN; UNKNOWN이 있으면 UNDETERMINED.
- edges exact `{source,target,kind,status}`: source는 실제 snapshot decimal string 또는 file alias; kind SNAPSHOT_MANIFEST_LIST/LIST_MANIFEST/MANIFEST_DATA/MANIFEST_DELETE/DELETE_REFERENCED_DATA/METADATA_LOG. MANIFEST_DATA/MANIFEST_DELETE만 status ADDED/EXISTING/DELETED이며 나머지는 반드시 null. 공유·DELETED 관계를 제거하지 않음.
- completeness exact `{metadataDecoded,refsDecoded,snapshotFileClosureDecoded}` bool. writer/pin/freshness authority 아님.
- decoderProvenance exact `{formatVersion,schemaCount,partitionSpecCount,sortOrderCount,mainRefDefaulted,allEntriesIncludingDeleted,streamsClosed,outsideTarget,networkImplemented,fileIoCreateDeleteSupported,parquetContentsVerified,historicalMetadataRestoreVerified}`. 미해석 count/version은 null, outsideTarget은 선택 table 밖 승인 객체의 exact `{id,size,sha256,action:"KEEP"}` ledger이며 Bronze UNKNOWN과 섞지 않음. 마지막4개 기능 flag는 false입니다.

reasonCodes는 아래20개 fixed enum에서 선택한 최대16개 entry입니다: FRAME_MAGIC, FRAME_BOUND, FRAME_EOF, DESCRIPTOR_INVALID, OBJECT_MAP_INVALID, OBJECT_BYTES_MISMATCH, METADATA_INVALID, UNSUPPORTED_FORMAT, UNSUPPORTED_METADATA_FEATURE, UNSUPPORTED_CODEC, UNSUPPORTED_SCHEMA, UNSUPPORTED_ENTRY_CONTENT, MISSING_APPROVED_CHILD, FOREIGN_REFERENCE, GRAPH_CONFLICT, MISSING_SNAPSHOT_REFERENCE, REFERENCE_CYCLE, GRAPH_BOUND, DECODER_INTERNAL, DECODER_BUDGET_EXPIRED. 입력/URI/key/exception message를 reason에 넣지 않습니다. stdout 전체는 private graph이고 public artifact가 아닙니다. Source가 handled diagnostic으로 쓰는 stderr만 fixed code이며 JVM/provider의 출력까지 fixed라고 주장하지 않습니다. Host는 private64KiB cap을 적용하고 public으로 내보내지 않습니다. Compile stderr0와 read의 bounded private provider warning을 구분합니다.

## prep·lifecycle·정규화

Prep는 original main/600 clock 전에 별도로 실제 source/classpath compile·classes wholeSHA/allowed class-set·image identity를 attestation합니다. Runtime image의 javac 존재를 가정하지 않습니다. 로컬 Microsoft JDK21+Iceberg1.11+SLF4J2.0.18 합성 compile/read는 Cloud classpath parity 증명이 아닙니다. 권고 decoder container: CPU1/512MiB/PID64/network-none/read-only input, JVM heap256MiB/ActiveProcessorCount1. Host는 시작 전 cutoff=min(now+60s, original started+600s-40s reserve)를 계산하고 exact-owned CID의 stop/wait/inspect/CLI reap을 원래600초 안에서 확인합니다. CLI timeout만으로 STOPPED를 주장하지 않습니다.

Core normalizer는 graph와 frozen planner exact DTO를 분리합니다. files에는 id/kind만, snapshot에는 id/parentId/committedAt/fileIds만; manifestListId/size/SHA/edges/provenance는 private receipt+DTO SHA로 보존합니다. unknown current ID/시각을 발명하지 않으며 DECODED만으로 pinsComplete/writersQuiescent를 true로 만들지 않습니다. original capture timestamp/동일 pointer/전체600 clock gate는 composite authority로 연결합니다. 실제 snapshot IDs/counts를 하드코딩하지 않습니다.
