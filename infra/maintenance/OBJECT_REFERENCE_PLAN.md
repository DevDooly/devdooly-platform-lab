# 객체 참조 보호 계획기

[`object_reference_plan.py`](object_reference_plan.py)는 versioned inventory를 분류하는 **순수 dry-run**이다. `build_plan(inventory, now=UTC문자열)`은 입력을 변경하지 않고 network·subprocess·DB/S3 연결·삭제를 수행하지 않는다. `apply` 옵션과 삭제 실행기가 없다. [기존 백업/PVC 보존 계획](README.md), [객체 보호·격리 GC 절차](../../docs/runbooks/object-reference-gc.md), [실행 근거](../../docs/evidence/object-reference-gc/README.md)를 구분한다.

## 두 입력 범위

| scope | database | 동작 |
| --- | --- | --- |
| `PRODUCTION_REFERENCES` | 실제 전체 DB snapshot, `noApplicationDatabase:false` | `canaries:[]` 필수. DB run의 raw/result prefix와 unknown 객체를 모두 KEEP하며 후보 0개 |
| `ISOLATED_CANARY_REFERENCE_FIXTURE` | `database:null`, `noApplicationDatabase:true` | 하나의 disposable store listing에서 정확히 등록·검증한 canary만 후보. protected reference는 항상 KEEP |

계획기는 inventory의 `complete`, `consistentSnapshot`, `contentVerified` 같은 주장을 직접 조회하지 않는다. 실제 수집기가 전체 DB row count·snapshot·S3 pagination·현재 identity를 확인해야 한다. `collectorClaimsIndependentlyVerified:false`를 결과에 명시한다. 공개 최근 job 목록은 전체 DB snapshot이 아니다.

DB job이 남으면 EXPORTED·TERMINATED를 포함해 상태·나이와 관계없이 `raw/<run>/`와 `result/<run>/` 전체를 보호한다. pending job/outbox, 점유 slot, PAUSED_OPERATOR·UNKNOWN, incomplete inventory와 5분 초과 stale은 보호 이유다. unknown·미등록 객체도 orphan으로 추정하지 않는다. 동일 payload hash를 가진 다른 key는 같은 참조가 아니다.

## Inventory v1

모든 경계는 아래 필드만 받는다. unknown field/schema/enum, 중복 JSON key/identity, 비정상 타입/UTC/key는 거부한다. 배열과 전체 object는 최대 10,000개, source commit은 40hex, hash는 SHA-256 64hex다. UTC `Z`/`+00:00`와 소수 초 최대 9자리를 허용하고 300초 경계를 나노초까지 비교한다. S3 key는 합성 Lab의 ASCII key만 받으며 절대경로·빈 segment·`.`/`..`·control 문자를 거부한다. host 파일 경로는 inventory에 넣지 않는다.

| 객체 | exact fields |
| --- | --- |
| top | `schemaVersion:1`, `kind:"object-reference-inventory"`, `scope`, `noApplicationDatabase`, `capturedAt`, `database`, `listings`, `canaries`, `protectedReferences` |
| database | `storeId`, `bucket`, `sourceCommit`, `complete`, `consistentSnapshot`, `expectedJobCount`, `expectedOutboxCount`, `expectedSlotCount`, `jobs`, `outbox`, `slotRunId`, `runtimeStatus` |
| job | `runId`, `scenarioVersion`, `sourceSha256`, `status`, `exportStatus` |
| outbox | `jobRunId`, `eventType`, `status` |
| listing | `storeId`, `bucket`, `complete`, `objects` |
| object | `key`, `size`, `sha256`(nullable), `contentVerified` |
| canary | `storeId`, `bucket`, `key`, `size`, `sha256`, `deleteEligible` |
| protected reference | `storeId`, `bucket`, `key`, `reason` |

- runtime: NOT_STARTED/RUNNING/STOPPED/PAUSED_OPERATOR/UNKNOWN.
- scenario: sensor-validation-v1/sensor-validation-v2/UNKNOWN.
- job/export: STAGING·QUEUED/NOT_REQUESTED, COMPLETED/PENDING·EXPORTED·CANCELLED, TERMINATED/NOT_REQUESTED. 알려진 UNKNOWN은 보호하고 불가능한 조합은 거부한다.
- outbox: DISPATCH/EXPORT/UNKNOWN, PENDING/ACKNOWLEDGED/CANCELLED/UNKNOWN. `(jobRunId,eventType)`는 유일하고 FK/slot은 알려진 job을 참조해야 한다.
- protected reason: BACKUP/EVIDENCE/FIXTURE_EXPORTED/FIXTURE_PENDING.

LIST size만 확인했다면 `sha256:null`, `contentVerified:false`다. 이를 ETag·파일 이름이나 이전 DB 값으로 채워 현재 내용 검증으로 표현하지 않는다. 등록 canary와 실제 whole-content 검증의 size/hash가 다르면 KEEP한다. production은 검증한 canary를 등록하는 것 자체를 거부한다.

## 재현 가능한 합성 예시

아래는 **DB·S3에 연결하지 않는 in-memory fixture**다. 실제 bucket/object의 존재·전체 GET·DB 참조를 주장하지 않는다. B/D의 EXPORTED/PENDING도 합성 참조이며, A/C 후보 두 개가 나와도 삭제는 수행하지 않는다.

CLI는 POSIX private 파일 권한을 확인한다. 사용자 소유의 canonical absolute 경로, 입력 `0600`, 출력 부모 `0700`이 필요하며 symlink와 기존 출력 파일을 거부한다. Windows에서도 순수 함수 테스트는 실행할 수 있지만 이 POSIX CLI 예시는 Linux에서 사용한다.

```sh
umask 077
OBJECT_PLAN_DIR="$(mktemp -d)"
python3 - "$OBJECT_PLAN_DIR/inventory.json" <<'PY'
import datetime, hashlib, json, os, sys
from pathlib import Path

# 고정 합성 bytes에 대한 fixture hash다. 실제 S3 GET 검증이 아니다.
payload = b'synthetic-reference-example-only'
digest = hashlib.sha256(payload).hexdigest()
objects = [{'key': 'example/' + name, 'size': len(payload),
            'sha256': digest, 'contentVerified': True} for name in 'abcd']
inventory = {
    'schemaVersion': 1, 'kind': 'object-reference-inventory',
    'scope': 'ISOLATED_CANARY_REFERENCE_FIXTURE',
    'noApplicationDatabase': True,
    'capturedAt': datetime.datetime.now(datetime.timezone.utc).isoformat(),
    'database': None,
    'listings': [{'storeId': 'synthetic-example', 'bucket': 'synthetic-example-bucket',
                  'complete': True, 'objects': objects}],
    'canaries': [{'storeId': 'synthetic-example', 'bucket': 'synthetic-example-bucket',
                 **{key: obj[key] for key in ('key', 'size', 'sha256')},
                 'deleteEligible': True} for obj in objects],
    'protectedReferences': [
        {'storeId': 'synthetic-example', 'bucket': 'synthetic-example-bucket',
         'key': 'example/b', 'reason': 'FIXTURE_EXPORTED'},
        {'storeId': 'synthetic-example', 'bucket': 'synthetic-example-bucket',
         'key': 'example/d', 'reason': 'FIXTURE_PENDING'}]
}
target = Path(sys.argv[1])
fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
with os.fdopen(fd, 'w') as stream:
    json.dump(inventory, stream)
PY
python3 infra/maintenance/object_reference_plan.py \
  --inventory "$OBJECT_PLAN_DIR/inventory.json" \
  --output "$OBJECT_PLAN_DIR/plan.json"
```

새 fixture를 만든 뒤 5분 안에 실행하면 `candidateCount:2`, `protectedCount:2`, `applyEnabled:false`를 출력한다. 시간이 지났거나 참조·검증 조건이 달라지면 후보는 억제된다. CLI는 결과를 `0600`·`O_EXCL`로 쓰고 stdout에는 수량만 출력한다. 기존 파일을 덮어쓰거나 후보를 삭제하는 후속 명령은 없다.

```sh
python3 -m unittest discover -s tests/maintenance \
  -p 'test_object_reference_plan.py' -v
python3 -m unittest discover -s tests/maintenance -p 'test_*.py' -v
```

20개 객체 계획기 검사는 상태·scope·stale 나노초 경계·중복·FK·traversal·hash/size·보호 참조·동일 payload/다른 key·입력 불변성을 다룬다. 기존 보존 계획기의 31개 검사와 별도로 구분한다. CI의 credential 없는 `tests/maintenance` discover에 함께 포함된다.

영속 job tombstone·삭제 intent·worker/admission 조율·Kafka replay와 백업 의존성·삭제 직전 재수집/재계산·unknown outcome 복구가 없다. 이 코드는 실제 운영 GC나 TOCTOU 방어를 구현한 것이 아니다.
