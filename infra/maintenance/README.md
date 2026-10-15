# 백업·시험 PVC 보관 계획기

`retention.py`는 versioned inventory와 `policy.json`을 받아 **계획만** 만든다. 삭제 실행기·`apply` 옵션·Kubernetes/S3 연결·하위 프로세스 호출은 없다. `build_plan(inventory, policy, now=UTC문자열)`은 파일을 읽지 않는 순수 함수이며 입력을 변경하지 않는다. 실제 collector는 별도이며 이 코드가 inventory의 주장과 현재 서버 상태를 직접 검증했다는 뜻은 아니다.

## 기본 보관 규칙

- 검증된 완전한 백업 중 `kind + compatibilityFamily`별 최신 1개를 나이와 무관하게 유지한다. DB/K3s/Jenkins/runtime이나 서로 다른 버전·복구 경계를 하나의 최신본으로 합치지 않는다.
- 최근 7일(7×24시간)의 검증 백업은 모두 유지한다. UTC 최근 7개 날짜의 일별 최신본과 현재 ISO 주를 포함한 최근 4개 주의 주별 최신본도 유지한다. 대표본 선택은 완료 시각 역순·동일 시각이면 ID 순이다. 일/주 구간이 겹치면 같은 백업이 여러 보관 이유를 가질 수 있다.
- 실패·상태 불명·고정·불완전한 그룹, 검증하지 않은 member, 키 사용 불가, 미래/불명 완료 시각, symlink/경로 불일치, 민감 자료나 다른 그룹과 공유한 파일은 보호한다. 완료 시각을 filesystem mtime에서 추정하지 않는다. `requiredMemberIds`와 실제 member 집합이 같고 ARCHIVE 1개·VERIFICATION 1개 이상이 있는 그룹만 완전한 단위가 된다. 그룹 일부만 후보로 분할하지 않는다.
- trial은 완료 후 최소 7일이 지나야 한다. namespace/기록 UID·canonical ownership label, PVC/PV UID·claimRef·새 저장 경로, 정상 중지·Pod 0·mount 없음·Retain, 검증된 백업과 근거가 모두 확인된 inventory만 후보가 된다. 원본 namespace/UID/경로, live/PENDING/PAUSED/UNKNOWN과 불명 소유권은 보호한다. trial이 참조한 백업은 해당 계획에서 보호한다.
- 암호화 키·config·credential은 항상 보호한다. JOB/RAW/EXPORT도 tombstone·GC 경계가 아직 없으므로 상태와 나이에 관계없이 전부 보호한다. 암호화 archive 안에 포함된 설정과 별도 평문 key/config 파일을 구분해 collector가 분류해야 한다.
- inventory가 5분 초과 오래됐으면 모든 후보를 억제한다. inventory 수집 시각보다 이른 clock, 알 수 없는 schema/필드/enum, 중복 JSON key, 비정상 UTC/경로는 입력 전체를 거부한다. 알려진 UNKNOWN 값은 보호 대상으로 수용한다.

`DELETE_CANDIDATE`는 실행 명령이 아니다. 실행기를 추가할 때는 현재 inventory를 다시 수집하고 계획을 다시 계산한 뒤, namespace/PVC/PV UID·claimRef·경로·member SHA/크기·근거 SHA 조건을 재검증해야 한다. 오래된 계획을 그대로 실행하거나 label만으로 namespace를 지우는 기능은 구현하지 않았다.

## Inventory v1 계약

모든 객체 경계는 아래 필드만 허용한다. 배열은 최대 10,000개이며 UID는 소문자 UUID, SHA는 소문자 SHA-256, 완료/수집 시각은 UTC RFC3339(`Z`/`+00:00`, 소수 초 최대 9자리)다. 경로는 실제 주소를 넣는 private inventory에서만 사용하며 canonical 절대 POSIX 경로여야 한다. public policy에는 host 경로가 없다.

| 객체 | exact 필드 |
| --- | --- |
| 최상위 | `schemaVersion:1`, `kind:"retention-inventory"`, `capturedAt`, `backupRoots`, `storageRoots`, `originalNamespaces`, `originalVolumes`, `backupGroups`, `trialGroups`, `protectedArtifacts` |
| root | `path`, `resolvedPath`, `isSymlink` |
| original namespace | `name`, `uid` |
| original volume | `pvcUid`, `pvUid`, `path` |
| backup group | `id`, `kind`, `compatibilityFamily`, `completedAt`, `state`, `complete`, `pinned`, `keyAvailable`, `requiredMemberIds`, `members` |
| backup member | `id`, `role`, `path`, `resolvedPath`, `isSymlink`, `size`, `sha256`, `verified` |
| trial group | `id`, `operation`, `completedAt`, `state`, `pinned`, `original`, `namespace`, `podsPresent`, `workloadsStopped`, `backupGroupId`, `evidenceSha256`, `evidenceVerified`, `volumes` |
| trial namespace | `name`, `uid`, `expectedUid`, `labels` |
| trial volume | `pvcName`, `pvcUid`, `expectedPvcUid`, `namespace`, `pvName`, `pvUid`, `expectedPvUid`, `claimRef`, `path`, `resolvedPath`, `isSymlink`, `mounted`, `bound`, `reclaimPolicy` |
| claimRef | `name`, `namespace`, `uid` |
| protected artifact | `id`, `kind`, `state`, `path` |

- backup `kind`: DB/K3S/JENKINS/RUNTIME/UNKNOWN. UNKNOWN kind는 UNKNOWN state만 허용한다. `compatibilityFamily`는 collector가 확인한 호환 경계의 slug다. `state`: VERIFIED/FAILED/UNKNOWN. 완료를 모르면 `completedAt:null`로 둔다.
- member `role`: ARCHIVE/VERIFICATION/MANIFEST/KEY/CONFIG/CREDENTIAL/UNKNOWN. `size`·`sha256`는 실제 파일을 확인한 값이다. directory나 불명 항목을 member로 추정하지 말고 UNKNOWN protected artifact 또는 불완전 UNKNOWN group으로 보관한다.
- trial `state`: STOPPED/RUNNING/PENDING/PAUSED/UNKNOWN. `operation`은 8자리 유효 날짜다. namespace labels의 `devdooly.io/purpose=runtime-pvc-restore`, `devdooly.io/operation=operation`을 확인한다. 이전 DB 시험처럼 다른 label 체계는 거부할 schema 오류가 아니라 `OWNERSHIP_UNVERIFIED`로 KEEP한다. 현재 UID와 기록 UID가 다르면 KEEP한다.
- trial `backupGroupId`·`evidenceSha256`는 모르면 null이다. `evidenceVerified`는 collector가 실제 private 근거를 확인한 결과다. `reclaimPolicy`: Retain/Delete/UNKNOWN. `bound`·`mounted`·`workloadsStopped` 등은 실제 리소스 전체를 확인한 boolean이다.
- protected artifact `kind`: KEY/CONFIG/CREDENTIAL/JOB/RAW/EXPORT/UNKNOWN. `state`: LIVE/PENDING/PAUSED/COMPLETED/UNKNOWN. 객체처럼 filesystem 경로가 없으면 `path:null`; 있는 경로는 후보와의 중첩까지 보호한다.

기록에 없는 원본·mount·Secret을 이 함수가 발견할 수는 없다. collector는 알려진 원본 전체와 모든 namespace의 해당 mount를 수집해야 한다. 경로 안전성은 inventory의 `resolvedPath/isSymlink` 관측을 전제로 한다. 계획 후 실제 경로가 달라지는 race를 방어하는 삭제 실행기는 없다.

## 실행과 검증

private 디렉터리를 0700, inventory를 0600으로 준비하고 새 출력 파일을 지정한다. CLI는 기존 파일을 덮어쓰지 않으며 계획은 0600·O_EXCL로 저장하고 stdout에는 수량만 출력한다.

```sh
python3 infra/maintenance/retention.py \
  --inventory "$PRIVATE_DIR/inventory.json" \
  --output "$PRIVATE_DIR/retention-plan.json"
python3 -m unittest discover -s tests/maintenance -p 'test_*.py' -v
```

`--now`로 지정한 시각은 결과에 `EXPLICIT_HYPOTHETICAL`로 표시된다. 과거 inventory의 완료 시각만 바꿔 실제 자료가 만료됐다고 주장하지 않는다. 합성 fixture는 현재 수집 시각과 별도 완료 시각을 명시해 일/주 경계·7일 경과·소유권/키/정지 조건을 검증한다. 실제 dry-run 결과와 합성 만료 후보를 구분한다. 정책/계획의 `applyEnabled`·`deletionExecutorImplemented`는 false이며 삭제는 수행하지 않는다.
