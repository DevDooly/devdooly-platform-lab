# DB 작업·outbox 기반 코드 사용과 검증

2026-10-12 KST. [4단계 계획](../plans/phase4-messaging-storage.md)의 첫 구현인 내부 Java 서비스와 DB 트랜잭션 경계를 설명한다. 기본 verify 35개와 격리 MariaDB의 업그레이드·최초 설치·반복 시작 각각 17개 검증을 통과했다. [실제 결과와 한계](../evidence/db-job-foundation/README.md)를 별도로 연결한다. 운영 DB에는 V2를 적용하지 않았고 기존 GitOps image pin을 유지한다.

## 현재 범위

`apps/api/src/main/java/io/github/devdooly/platformlab/jobs/`의 `LabJobService`와 `CanonicalSource`, Flyway `V2__create_lab_job_outbox.sql`이 대상이다. 외부에서 호출할 job HTTP API·관리자 CLI·스케줄러·Kafka producer/consumer·S3 adapter는 없다. 기존 [조회 API 계약](../contracts/demo-api.md)의 GET과 `POST /api/demo/runs` 거부(405), `publicExecutionEnabled: false`를 유지한다. 내부 메서드의 존재를 공개 실행이나 Kafka·S3 연결 완료로 표시하지 않는다.

원본은 공개 합성 시나리오 `sensor-validation-v1`의 **순서가 고정된 12개 입력**만 허용한다. 최대 크기는 1 MiB(1,048,576 bytes)다. UTF-8 NDJSON의 중복 JSON key·추가 필드·trailing token·입력 순서나 값 변경을 거부한다. 잘못된 시각 문자열과 업무상 중복 ID는 원본대로 보존한다. 공백·LF/CRLF처럼 표현만 다른 유효 원본도 byte가 다르면 SHA-256이 다르다. 이름에 canonical이 있어도 byte 표현을 하나로 정규화하거나 hash를 같게 만들지는 않는다.

`prepareSource()`는 원본 byte를 복사해 DB에 보관한다. run ID는 소문자 ASCII·숫자·`.`·`_`·`-`의 허용 형식과 80자 상한을 따르며, 기존 seed ID `synthetic-v1-seed-42`와 기존 결과 ID를 새 작업으로 사용하는 것을 거부한다. 같은 run·같은 원본은 기존 작업을 반환하고 다른 원본 hash는 충돌로 거부한다. `sourceObjectKey()`는 향후 adapter용 결정적 key이며 현재 S3에 객체를 만들었다는 뜻이 아니다.

## 상태와 실행 슬롯

V2는 기존 V1·`demo_run`·`demo_outcome`을 수정하지 않고 `lab_job`, `lab_job_slot`, `lab_outbox`를 추가한다. `lab_job_slot`의 고정 행 `id=1`은 전체 진행 작업 1개를 관리한다. 변경 트랜잭션은 **slot 행 → job 행** 순서로 `FOR UPDATE` 잠금을 얻는다.

| 내부 메서드 | DB 효과와 호출 조건 |
| --- | --- |
| `prepareSource(runId, scenarioVersion, rawNdjson)` | 슬롯이 비어 있을 때 `STAGING / NOT_REQUESTED` 작업·원본·hash를 저장하고 슬롯을 점유한다. 같은 작업의 멱등 재요청은 새 슬롯을 만들지 않는다. |
| `markSourceVerified(runId, hash)` | `STAGING → QUEUED`와 `DISPATCH / PENDING` outbox를 같은 트랜잭션으로 저장한다. 호출자는 먼저 외부 원본의 영속 보관·조회·hash를 검증해야 한다. |
| `process(runId, hash)` | `QUEUED` 작업의 DB 원본 hash·크기를 다시 확인하고 12개를 한 묶음으로 판정한다. 결과·전체 outcomes·`COMPLETED / PENDING`·`EXPORT / PENDING` outbox를 함께 저장한다. 완료 작업의 재전달은 저장된 결과·시각을 덮어쓰지 않는다. |
| `acknowledgeDispatch(runId, hash)` | broker가 발행을 ACK한 뒤 `DISPATCH` outbox를 `ACKNOWLEDGED`로 표시한다. 슬롯은 유지한다. |
| `completeExport(runId, hash)` | 완료 결과의 export를 독립적으로 확인한 뒤 `EXPORT` outbox ACK·`EXPORTED`·완료 시각을 함께 저장하고 슬롯을 해제한다. 반복 확인은 기존 시각을 보존한다. |
| `terminate(runId, hash)` | 운영자가 원본·결과 보존을 확인한 뒤 명시적으로 종료한다. 미완료 작업은 `TERMINATED`, 완료 결과는 유지하면서 export를 `CANCELLED`로 기록한다. 대기 outbox를 취소하고 슬롯을 해제하며 성공 export로 기록하지 않는다. |
| `get(runId)`, `pendingOutbox(limit)` | 내부 조회용이다. pending 목록의 조회만으로 발행·처리 선점이나 외부 성공이 보장되지는 않는다. |

**최초 정책은 결과·실패 파일 export 완료까지 슬롯을 보유**한다. DB 연산이 완료되어도 export pending이면 다른 run을 받지 않는다. 이는 미완료 작업 누적을 억제하는 대신, 해당 작업이 막히면 다음 작업도 시작하지 못하는 제한이다. 완료 전 종료나 export 취소는 원본·결과를 보존한 명시적 운영자 종료로 처리한다.

현재 `markSourceVerified()`·`acknowledgeDispatch()`·`completeExport()`는 **미래 adapter가 외부 성공을 검증한 뒤 호출할 신뢰 경계**다. DB 시험에서는 상태 전이를 검증하기 위해 호출하며, 이 호출로 S3 Put/Get·Kafka ACK·결과 파일의 실제 export를 검증했다고 주장하지 않는다. 외부 증거를 검증하는 adapter와 재시도·중단·복구는 후속 구현이다.

## 결과 저장과 기존 계약 보존

`LabJobService`의 `TransactionTemplate`과 `DemoService.persistProcessedRun()`의 `MANDATORY` 전파를 통해 JDBC 작업 상태와 JPA 결과 저장이 같은 트랜잭션에 참여한다. 완료 전에 실패하면 결과·outcomes·job 완료 상태·export intent가 함께 rollback되어야 한다. JDBC timestamp는 명시적 UTC Calendar로 bind/read하고 JPA의 기존 UTC 매핑과 맞춘다. 비UTC JVM에서도 같은 완료 Instant가 DB 결과·작업 상태에서 일치하는지는 실제 DB 검증 조건에 포함한다.

업무상 중복 2건은 기존 `SensorProcessor`의 판정이다. 같은 작업의 재전달을 억제하는 DB 멱등과 구분한다. Kafka offset·전달 횟수·lag는 현재 수집하거나 검증하지 않는다. 입력 회계식과 판정 순서는 [독립 시나리오](../../tests/scenarios/sensor-validation-v1.json)의 12 = 성공 7 + 실패 3 + 중복 2 + 대기 0을 유지한다.

기존 완료 결과 GET에 진행 중 job을 섞지 않는다. 별도 job 조회·공개 관측 계약은 아직 없으며, 기존 `lab-observation v1`의 고정 seed와 `platform-observation v1`을 변경하지 않는다. `SampleBootstrap`은 `worker` 또는 `admin` profile에서 자동 실행되지 않는다. 이 profile 구분 자체가 Flyway 비활성화나 실제 worker 배포·웹 서버 비활성화를 구현한 것은 아니다.

## 기본 H2 검증

Java 21 환경에서 저장소의 `apps/api` 디렉터리에서 실행한다.

```sh
./mvnw -B -ntp verify
```

Windows에서는 `mvnw.cmd`를 사용한다. 기존 API 검사는 기존 H2 DB를 사용하고, job 검사는 별도 `job_foundation_tests` H2 DB를 사용한다. 실제 MariaDB의 잠금·동시성·업그레이드 검증을 대신하지 않는다. `MariaDbLabJobIT`는 기본 실행에서 실제 DB에 접속하는 시험이 아니다.

## 실제 MariaDB 격리 검증

운영 DB와 다른 **폐기 가능한 전용 DB·접속 포트·실행 디렉터리**를 먼저 준비하고 확인한 상태에서만 진행한다. 이 runbook은 DB 생성·자격증명 발급·운영 접속정보 복사를 지시하지 않는다. 준비한 전용 실행 환경에 다음 환경변수 이름을 설정한다. 비밀번호나 완성된 접속정보를 문서·Git·채팅·공개 로그에 남기지 않는다.

| 환경변수 | 의미 |
| --- | --- |
| `DB_TEST_URL` | `jdbc:mariadb://127.0.0.1:<전용 숫자 포트>/platform_lab_foundation` 또는 동일 형식의 `platform_lab_foundation_fresh` |
| `DB_TEST_USERNAME` | 해당 임시 DB의 전용 사용자 |
| `DB_TEST_PASSWORD` | 해당 임시 DB의 전용 자격증명 |

시험은 `lab.database.tests=true`를 명시해야 활성화된다. `DynamicPropertySource`가 **Flyway 실행 전에** URL의 loopback host·숫자 포트·허용한 전용 DB 이름을 검사한다. 실제 connection metadata도 MariaDB인지 확인한다. 이름·URL 형식 검사만으로 해당 DB가 폐기 가능하다고 보장되지는 않으므로 운영 환경과 분리했는지 먼저 확인한다.

전용 환경변수가 준비된 `apps/api` 디렉터리에서 값 출력 없이 다음을 실행한다.

```sh
set +x
: "${DB_TEST_URL:?전용 DB_TEST_URL 필요}"
: "${DB_TEST_USERNAME:?전용 DB_TEST_USERNAME 필요}"
: "${DB_TEST_PASSWORD:?전용 DB_TEST_PASSWORD 필요}"
./mvnw -B -ntp -Dlab.database.tests=true -Dtest=MariaDbLabJobIT '-DargLine=-Duser.timezone=Asia/Seoul' test
```

해당 클래스는 `db-test`, `worker` profile을 함께 사용한다. `db-test`는 `DB_TEST_*`를 사용하며 기존 API의 H2 profile과 섞지 않는다. `worker`는 자동 bootstrap을 제외하지만 테스트 준비 코드가 `ensureSample()`을 명시적으로 호출하므로 빈 DB에서는 비교용 seed가 만들어진다. 기존 V1 seed가 있으면 그 결과·시각을 재사용해야 한다.

**시험의 정리 코드는 쓰기 작업이다.** 각 시험 전후에 `foundation-*` 테스트 job·outbox·outcomes·결과를 삭제하고 해당 작업이 점유한 슬롯을 비운다. 다른 접두어의 작업이 슬롯을 점유하면 정리를 거부한다. 이 접두어 필터를 운영 DB 실행 허가로 해석하지 않는다. 운영 seed·실제 작업이 있는 DB를 대상으로 이 시험을 실행하지 않는다.

## 남겨야 할 실제 검증 근거

다음 조건의 실제 DB 검증 결과는 [실행 근거](../evidence/db-job-foundation/README.md)에 있다. 후속 변경에서도 같은 조건을 다시 확인한다.

- 기존 V1 앱으로 만든 seed의 전체 결과·12개 outcome·자동 ID·처리 시각을 기록하고 V2 적용 후 동일함을 비교한다. V1 checksum, V2 성공 기록, 반복 시작 시 singleton·seed가 중복되지 않는지도 확인한다.
- 빈 전용 DB의 V1+V2 초기화와 V1 DB의 업그레이드를 구분한다. 현재 버전으로 빈 DB를 초기화한 결과만으로 기존 V1 업그레이드까지 검증했다고 기록하지 않는다.
- 같은 run·같은 hash 재요청, 다른 hash 충돌, seed ID·잘못된 원본·1 MiB 초과 거부에서 job·outbox·슬롯이 불필요하게 바뀌지 않는지 확인한다.
- 실제 MariaDB의 별도 connection·트랜잭션 두 개로 서로 다른 run의 동시 제출, 같은 run의 동시 재요청과 동시 완료를 확인한다. 전체 시험을 감싼 미커밋 트랜잭션으로 경쟁을 숨기지 않는다.
- source verification과 dispatch intent의 원자성, 완료 트랜잭션 실패 시 JPA 결과·JDBC 상태·export intent의 동시 rollback, 재전달 시 전체 결과·시각 불변을 비교한다.
- export pending에서 후속 작업 거부, 확인된 export 완료 또는 명시적 운영자 종료 뒤 슬롯 해제, 종료·취소가 export 성공으로 표시되지 않는지 확인한다.
- 비UTC JVM 조건에서는 테스트 JVM의 실제 기본 시간대를 확인하고 job·result 완료 시각의 SQL 값과 Instant 일치를 검증한다. UTC 환경에서의 단독 성공으로 이 조건을 대체하지 않는다.
- 기존 GET·404·POST 405·공개 실행 비활성, seed 전체 행·시각, 고정 관측 계약을 회귀 확인한다. 새 controller나 공개 job 실행 경로를 만들지 않는다.

원문 SQL·접속정보·실행 환경 상세는 비공개 기록에 남기고 공개 근거에는 source·실행 조건·시각·판정·보존 비교의 허용 요약만 연결한다. 실제 통과 건수와 보존 비교는 연결한 근거에 기록하며, 성능 수치·외부 전달 성공으로 확대하지 않는다.

## 운영 반영 전 경계

현재 foundation은 운영 V2 migration과 GitOps image 갱신 대상이 아니다. 원격 임시 검증과 검토 가능한 코드 변경으로 유지한다. 운영 반영 시에는 별도 배포 검증을 통해 기존 데이터 백업, V1→V2 업그레이드, 이전 image 재시작·Flyway validation·조회 호환성, 신규 스키마 보존·복구 범위를 확인한다.

V2는 additive DDL이지만 새 image 시작 시 Flyway가 적용할 수 있다. 내부 서비스를 호출하지 않거나 profile로 bootstrap을 제외했다고 migration까지 막히는 것은 아니다. GitOps를 이전 image로 되돌리는 작업은 V2 테이블·Flyway 이력·새 작업 데이터를 자동으로 되돌리지 않는다. 이전 image가 V2가 있는 DB를 정상 수용하는지도 격리 환경에서 실제 확인해야 하며, 운영 복구에 `Flyway clean`·이력 삭제·임의 테이블 삭제를 사용하지 않는다.

Kafka·Garage·SDK 조합과 배포 digest, 실제 S3 보관·broker 발행·offset commit·export 검증은 [4단계 계획](../plans/phase4-messaging-storage.md)의 다음 관문이다. 이 DB 기반 코드만으로 전체 처리의 exactly-once나 장애 후 외부 재처리를 완료했다고 표현하지 않는다.
