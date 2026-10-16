# Iceberg snapshot 보존 dry-run

[`iceberg_retention_plan.py`](../../infra/maintenance/iceberg_retention_plan.py)의 `build_plan(inventory, policy, now=UTC문자열)`은 입력만 읽는 순수 함수입니다. Collector·파일 I/O·network·SQL·만료/삭제 실행기·`apply`·자동 스케줄링은 없습니다. 실제 Cloud 성공의 inventory를 새로 수집하거나 만들어 넣지 않았습니다. [기존 Cloud 성공](../evidence/cloud-lakehouse/FULL_SUCCESS.md)의 compaction은 현재 파일 2→1개이며 snapshot 만료·객체 GC의 근거가 아닙니다.

첫 버전은 current snapshot, 모든 tag/branch ref, 백업·검증 pin의 **조상 snapshot까지 전부 KEEP**합니다. 최소 보관 수와 최소 나이도 적용하며, 이 보호 범위 밖의 오래된 detached snapshot만 `EXPIRATION_CANDIDATE`가 됩니다. 일반 선형 history의 오래된 조상을 만료시켜 의미 있는 공간이 생긴다고 예측하지 않습니다. 이는 Iceberg의 ref별 자동 만료 규칙을 구현한 엔진이 아닙니다.

모든 파일은 KEEP이며 `objectCandidateCount`는 항상 0입니다. Snapshot 후보가 참조한 파일도 실제 snapshot이 만료된 것은 아니므로 보호합니다. 다른 snapshot과 공유한 파일, metadata·unknown·직접 pin 파일과 참조가 없는 파일도 삭제 허가로 바꾸지 않습니다. Orphan 판단·회수량·실제 내용 GET 검증은 수행하지 않습니다.

## 정규화 입력 v1

모든 객체는 아래 필드만 허용합니다. 배열은 최대 10,000개, snapshot/file pin 관계는 합계 100,000개입니다. ID는 경로·URL이 아닌 1~80자 ASCII alias(`A–Z a–z 0–9 . _ -`, 첫 글자는 영숫자)입니다. 같은 실제 객체에는 항상 같은 alias를 쓰고 서로 다른 객체에 같은 alias를 부여하면 안 됩니다. Alias 매핑은 미래 collector의 책임이며 계획기는 이를 조회하지 않습니다. Snapshot ID는 양의 signed BIGINT 범위의 십진 **문자열**입니다. UTC는 `Z`/`+00:00`, 소수 초 최대 9자리입니다.

| 경계 | exact 필드·뜻 |
| --- | --- |
| inventory | `schemaVersion:1`, `kind:"iceberg-retention-inventory"`, `scope`, `tableId`, `capturedAt`, `observations`, `currentSnapshotId`, `snapshots`, `refs`, `pins`, `files` |
| scope | `SYNTHETIC_REFERENCE_FIXTURE` 또는 `CAPTURED_TABLE_METADATA`. 후자도 live 검증 성공이라는 뜻이 아닙니다. |
| observations | `complete`, `refsComplete`, `pinsComplete`, `snapshotFileClosureComplete`, `writersQuiescent` boolean; `metadataBeforeId`, `metadataAfterId` pointer alias; `metadataBeforeSha256`, `metadataAfterSha256`의 전체 metadata bytes SHA-256 |
| snapshot | `id`, `parentId`(없으면 null), `committedAt`, `fileIds`. File 목록은 manifest-list·manifest·data/delete 파일의 **전이 참조 전체**를 정규화한 목록입니다. |
| ref | `name`, `kind:TAG\|BRANCH`, `snapshotId` |
| pin | `id`, `kind:BACKUP\|VALIDATION`, `snapshotIds`, `fileIds`. 검증용 시점 조회와 백업 의존성을 빠뜨리지 않습니다. |
| file | `id`, `kind:DATA\|DELETE\|MANIFEST\|MANIFEST_LIST\|METADATA\|UNKNOWN` |
| policy | `schemaVersion:1`, `maxInventoryAgeSeconds`(1~300), `minSnapshotAgeSeconds`(1초~3,650일), `minimumSnapshotsToKeep`(1~10,000) |

`complete`는 해당 table의 snapshot·metadata/file inventory와 각 snapshot의 전체 참조가 빠짐없다는 주장입니다. `refsComplete`는 모든 tag/branch, `pinsComplete`는 모든 백업·검증 의존성을 확인했다는 주장입니다. 동일 table의 실제 catalog pointer identity와 그 metadata 전체 bytes를 수집 전후 대조해야 하며, 같은 SHA라도 pointer가 다르면 안정된 inventory가 아닙니다. `writersQuiescent`는 외부 writer의 정지 상태에 관한 주장입니다. 단지 마지막 commit이 같다고 writer 중단을 추정하지 않습니다.

이 주장들은 계획기가 독립 확인하지 않습니다. 결과의 `inventoryClaimsIndependentlyVerified:false`를 유지합니다. 향후 실제 collector가 table identity·현재 pointer·모든 refs/pins·전체 manifest 참조·private alias 매핑·수집 전후 안정성을 확인하기 전에는 합성 검사만 가능합니다. Public 최근 기록이나 `LIST` 크기를 전체 참조·내용 검증으로 사용하지 않습니다.

## 결과와 억제 조건

결과는 `DETERMINED` 또는 `UNDETERMINED`, 평가 시각·입력 fingerprint, snapshot별 KEEP/후보와 고정 reason, 파일별 KEEP reason, 두 후보 수를 제공합니다. 평가 시각은 caller 입력이며 실제 시계나 실제 수집을 인증하지 않습니다. `applyEnabled:false`, `deletionExecutorImplemented:false`는 항상 유지합니다.

- 불완전한 관측 주장, 비유휴 writer, metadata pointer/SHA 변화, 300초 이내의 정책 기한 초과, 미래 수집/commit 시각이면 `UNDETERMINED`, 모든 후보 0개입니다.
- current/ref/pin/file 참조 누락, 부모 누락·cycle·부모가 자식보다 늦은 시각, UNKNOWN 파일 종류도 같은 방식으로 억제합니다. 이미 만료되어 metadata에 없는 부모를 안전하다고 추정하지 않는 지원 범위입니다.
- unknown/private 필드·잘못된 타입/시각·중복 identity·비정상 ID는 고정 코드의 `ValueError`로 입력 전체를 거부합니다. 선택적 순수 `parse_json`은 1MiB 이내 UTF-8, 중복 JSON key·NaN 거부를 제공합니다. 실제 파일은 읽지 않습니다.
- 후보는 만료 허가나 SQL이 아닙니다. 새 실행기를 붙이지 않으며, 오래된 계획을 실제 대상으로 사용할 수 없습니다. 이후 실제 만료 검토는 새 수집·ref/pin 재검증·동시 writer 경계·복구 의존성을 별도로 설계해야 합니다.

## 로컬 검증

```sh
python3 -B -m unittest discover -s tests/maintenance -p 'test_iceberg_retention_plan.py' -v
```

합성 검사는 detached 후보와 current/ref/pin 조상 보호, 공유 파일 보호, 불완전·pointer race·dangling/cycle·나노초 경계, 타입·비공개 필드 거부와 입력 불변성을 확인합니다. 이것은 실제 Iceberg metadata 읽기·snapshot expiration·Garage GC·공간 회수나 운영 안정성의 증거가 아닙니다. 기존 [일반 객체 참조 계획](../../infra/maintenance/OBJECT_REFERENCE_PLAN.md)과 [백업/PVC 보존 기준](retention-resource-budget.md)을 대체하지 않습니다.
