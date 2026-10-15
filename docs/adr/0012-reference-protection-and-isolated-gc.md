# ADR 0012: 운영 객체 참조 보호와 격리 GC 실험을 분리한다

상태: 채택, 실제 전체 참조 수집 19/19·별도 자연 GC 11/11 통과. 운영 삭제 실행기는 제공하지 않는다.

## 배경

현재 [보존 계획기](../../infra/maintenance/README.md)는 JOB/RAW/EXPORT를 상태·나이와 관계없이 보호한다. Kafka 재전달·pending export·명시적 resume·백업 복원에 필요한 객체를 나이만으로 지울 수 없기 때문이다. 공개 작업 observation은 최근 목록이므로 전체 DB 참조의 완전성을 증명하지도 않는다.

Garage의 DELETE 성공·GET 404·실제 블록 회수·metadata tombstone GC·metadata DB 축소는 서로 다른 상태다. 같은 payload의 서로 다른 S3 key는 물리 블록을 공유하므로 한 alias 삭제가 같은 크기의 공간 회수를 뜻하지 않는다. 운영 자료를 삭제해 이 차이를 시험하지 않는다.

## 결정

1. **운영 참조 계획은 항상 보호한다.** 순수 함수의 versioned inventory에 실제 전체 job/outbox/slot/runtime snapshot과 전체 bucket LIST의 완전성을 명시한다. production은 `canaries:[]`를 강제하고 모든 DB run raw/result prefix·unknown 객체를 KEEP한다. `applyEnabled:false`, `deletionExecutorImplemented:false`를 고정한다.
2. **수집 사실과 순수 판단을 구분한다.** 별도 root 전용 수집기가 read-only repeatable-read transaction의 COUNT·row 수와 schema를 확인한다. transaction 종료 후 S3 GET LIST를 완주하고 전후 전체 참조·원본 상태가 같아야 한다. LIST size는 content hash가 아니며 null hash/false verified를 유지한다. 최근 공개 API 목록을 certificate로 대체하지 않는다.
3. **물리 GC는 완전히 새 disposable Garage에서만 시험한다.** 새 internal network·fresh node/key/bucket·volume 2개에 고정 A/B/C/D 합성 객체를 만든다. 애플리케이션 DB가 없는 fixture라는 사실을 계약에 표시한다. B/D를 보호한 순수 계획과 exact A/C 두 key의 수동 실험만 수행하며 일반 apply/운영 GC executor는 만들지 않는다.
4. **실제 파일 회수로 판단한다.** DELETE 전 whole GET·뒤 404, B/D 불변, shared 블록 보존과 unique C 두 블록의 자연 회수를 각각 확인한다. clock/repair/vacuum/purge로 지연을 우회하지 않고 최대 관측 시간 안에 보이지 않으면 실패로 보존한다.

## 선택하지 않은 대안

- EXPORTED 또는 오래된 prefix를 바로 삭제: replay·resume·백업 의존성과 tombstone 경계가 없어 안전한 후보가 아니다.
- 공개 최근 작업 목록만 조회: 전체 참조 누락을 발견할 수 없다.
- DELETE 204/GET 404만 확인: 물리 회수·dedup 보호를 입증하지 못한다.
- 원래 Garage repair/vacuum 또는 시간 이동: 운영 자료와 서비스에 영향을 주고 자연 GC 동작의 검증 조건도 바꾼다.

## 결과와 한계

오프라인 정책/collector/guard 검증과 원격 실행 근거를 [별도 evidence](../evidence/object-reference-gc/README.md)에 기록한다. 공개 [순수 계획기와 합성 예시](../../infra/maintenance/OBJECT_REFERENCE_PLAN.md), 20개 회귀 검사로 보호 판단을 재현한다. 기존 보존 계획기 31개와 함께 maintenance suite 51개도 통과했다. 첫 준비 실패는 PUT·DELETE 0회이며 새 2차 소스·리소스로 분리했다.

실제 운영 전체 객체 21개는 모두 보호·후보 0개였고 운영 DELETE는 수행하지 않았다. 별도 새 Garage에서는 A/C 두 key만 삭제해 공유 블록을 보호하면서 고유 C 두 블록의 자연 회수와 B/D 전체 bytes 불변을 확인했다. GET 21회에는 LIST·404 검사도 포함되며 전체 객체 21개의 내용 검증으로 표현하지 않는다.

앞뒤 DB 참조 비교는 미래 TOCTOU를 해결하지 않는다. 운영 GC 전에 영속 job tombstone·삭제 intent, admission/worker 조율, run ID 재사용 금지, outbox/Kafka replay·백업 의존성, 재수집·조건부 확인과 unknown outcome 복구가 필요하다. 이 결정은 운영 데이터 삭제·metadata DB 축소·RF>1 정합성·고가용성 승인이 아니다.

## 근거

- [Garage v2.4.1 DeleteObject](https://github.com/deuxfleurs-org/garage/blob/v2.4.1/src/api/s3/delete.rs)
- [block refcount·GC 지연](https://github.com/deuxfleurs-org/garage/blob/v2.4.1/src/block/manager.rs), [resync의 재계산과 파일 제거](https://github.com/deuxfleurs-org/garage/blob/v2.4.1/src/block/resync.rs)
- [metadata table tombstone GC](https://github.com/deuxfleurs-org/garage/blob/v2.4.1/src/table/gc.rs), [Blake2b block hash](https://github.com/deuxfleurs-org/garage/blob/v2.4.1/src/util/data.rs)
- [MariaDB READ ONLY consistent snapshot](https://mariadb.com/docs/server/reference/sql-statements/transactions/start-transaction)
