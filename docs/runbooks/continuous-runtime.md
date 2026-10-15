# 상시 worker/export 실행과 작업 관측 검증

2026-10-15 KST · 기본 120개·실제 IT 4개·웹 34개와 기존 운영 보존 검증 완료. [ADR 0008](../adr/0008-continuous-runtime-observation.md)에 따라 기본 조회 API와 상시 실행 명령을 구분한다.

## 먼저 확인할 조건

API/관리 절차가 V3 `lab_runtime` migration을 성공적으로 적용해야 한다. 실행기 자체는 Flyway·SQL 초기화·schema 수정을 실행하지 않고 Hibernate validate와 V3 확인만 수행한다. 기존 V1/V2와 완료 샘플을 유지한다. 현재 연결은 숫자 loopback/SSH 터널의 전용 격리 Kafka·Garage 범위이며 운영 K8s DNS·인증·서비스 배치는 후속이다.

Java 21을 사용하며 비공개 환경 파일에서 아래 설정을 준비한다. 토큰·DB/S3 비밀번호·실제 host·포트를 채팅·Git·CI artifact·shell tracing에 옮기지 않는다.

| 설정 | 의미 |
| --- | --- |
| `DB_URL`, `DB_USERNAME`, `DB_PASSWORD` | API가 미리 V3를 적용한 전용 Lab DB |
| `SOURCE_COMMIT` | 실행 code에 대응하는 전체 40자리 Git SHA, 미상은 `unknown` |
| `LAB_ENVIRONMENT` | `isolated-lab` 등 실제 환경. 시험을 `mini-pc` 운영 기록으로 표시하지 않음 |
| `LAB_RUNTIME_KAFKA_BOOTSTRAP` | `127.0.0.1:<port>` 한 곳 |
| `LAB_RUNTIME_KAFKA_TOPIC`, `LAB_RUNTIME_KAFKA_GROUP` | partition 1/RF1으로 명시 생성한 전용 topic과 consumer group |
| `LAB_RUNTIME_S3_ENDPOINT`, `LAB_RUNTIME_S3_REGION` | 기존 Garage client가 허용하는 명시적 endpoint와 `garage` region |
| `LAB_RUNTIME_S3_BUCKET`, `LAB_RUNTIME_S3_ACCESS_KEY_ID`, `LAB_RUNTIME_S3_SECRET_ACCESS_KEY` | 전용 bucket과 필요한 read/write 권한의 key |

기본 API는 기존 `java -jar ...jar` 경로다. 실행기는 별도 프로세스로 다음처럼 시작한다. 다른 app 인자는 받지 않고 연결·profile 설정은 환경변수로 전달한다.

```sh
java -jar apps/api/target/platform-lab-api-0.1.0.jar --lab-runtime=run
```

이 명령은 sample 작업을 새로 제출하지 않는다. 기존 `SourceStagingService`의 관리자 내부 경계로 접수·원본 확인된 작업을 처리한다. 공개 POST는 계속 비활성이다. 하나의 소유 thread가 pending export → pending dispatch → 한 record poll을 반복하며 idle 대기는 500ms다. 매 단계의 DB heartbeat를 남기고 외부 Kafka/S3 IO는 DB 트랜잭션 밖에서 실행한다.

## 정지·재시작과 명시적 재개

정상 종료 요청은 `requestStop`으로 전달하고 각 단계 사이에서 요청을 확인하고 같은 thread가 client와 named lock을 닫는다. JVM 종료 hook은 이를 요청하고 최대 240초 기다리는 best effort다. 실제 격리 시험의 정상 종료는 소유 stop file을 읽은 helper가 `requestStop`을 호출한 것이며 OS signal/systemd 종료를 검증한 것은 아니다.

오류 뒤 `PAUSED_OPERATOR`는 프로세스 재시작만으로 해제되지 않는다. 원본·파일·DB/offset·실패 code를 확인하고 소유가 확인된 원인을 복구한 뒤 다음 별도 명령을 사용한다.

```sh
java -jar apps/api/target/platform-lab-api-0.1.0.jar --lab-runtime=resume
java -jar apps/api/target/platform-lab-api-0.1.0.jar --lab-runtime=run
```

resume은 같은 named lock을 확보해 정지 표시만 STOPPED로 바꾸며 Kafka/S3 작업을 실행하지 않는다. 활성 실행기가 있으면 run/resume 모두 소유권을 얻지 못한다. 원본 손상을 adapter가 자동 재Put하거나 offset을 건너뛰어 성공을 만들지 않는다. 강제 종료로 RUNNING이 남은 경우는 이전 DB session의 named lock이 해제된 뒤 새 run이 기존 outbox/offset/export 경계로 회복한다.

DB/lease 자체가 끊겨 journal을 쓰지 못한 경우에는 PAUSED가 확정됐다고 기록하지 않는다. 마지막 RUNNING/heartbeat가 남을 수 있으며 화면의 오래된 실행 신호 표시와 실제 private 진단을 함께 확인한다. 이 구현은 소유권 확인과 외부 IO의 원자적 fencing이나 HA가 아니다.

## 관측 API와 화면

`GET /api/jobs/observation`은 별도 [job-observation v1](../contracts/job-observation.md) 계약이다. runtime journal·슬롯·최신 작업 최대 20개, 상태·시각·건수·파일별 예상 SHA/크기만 반환한다. 읽기 snapshot 안에서 Kafka/S3를 호출하거나 작업 row lock을 잡지 않는다. 현재 저장소 재조회·현재 프로세스 생존 보장과 구분한다.

같은 origin의 화면은 이 API를 읽고, Pages는 별도의 `observations/jobs.latest.json` 기록을 읽는다. 실제 HTTP 응답을 validator로 확인한 파일만 등록한다. 검증 환경·capturedAt·source commit·runtime heartbeat·export 저장 확인 시각을 표시한다. 조회 실패는 마지막 성공 기록을 지우지 않으며 관측 전에는 성공 샘플을 만들지 않는다. 기존 두 관측 계약과 고정 seed 결과는 유지한다.

## 실제 격리 시험

전용 MariaDB 11.8.9·Garage 2.4.1·Kafka 4.3.1과 Java 21·Asia/Seoul을 준비한다. Docker internal network와 소유 volume만 사용하고 host published port는 만들지 않는다. 기존 서비스·K3s·PVC·proxy·firewall은 변경하지 않는다.

DB URL은 Flyway 전에 정확히 `jdbc:mariadb://127.0.0.1:<port>/platform_lab_runtime_it`인지 검사한다. `DB_TEST_USERNAME/PASSWORD`, `LAB_S3_TEST_ENDPOINT/BUCKET/ACCESS_KEY/SECRET_KEY`, `LAB_KAFKA_TEST_BOOTSTRAP/CLUSTER_ID`는 이전 opt-in 시험과 같은 전용 numeric-loopback 규칙을 따른다. 실제 MariaDB product/catalog, Kafka cluster ID/node1, 빈 job/outbox/결과·singleton slot을 확인한다. 환경 이름과 `SOURCE_COMMIT`도 실제 검증 소스에 맞춰 설정한다.

```sh
cd apps/api
./mvnw -B -ntp -DargLine=-Duser.timezone=Asia/Seoul verify
./mvnw -B -ntp -Dlab.runtime.tests=true \
  -Dtest=ContinuousRuntimeIT \
  -DargLine=-Duser.timezone=Asia/Seoul test
```

Windows는 `mvnw.cmd`를 사용한다. 실제 HTTP 응답을 비공개 새 파일에 보관하려면 `-Dlab.runtime.observation.file=<본인이 준비한 새 비공개 경로>`를 추가한다. 기본 verify는 외부 IT나 broker를 자동 실행하지 않는다.

| 실제 시험 | 확인할 결과 |
| --- | --- |
| 같은 daemon의 두 작업 | 자동 발행·수신·두 파일 확인·슬롯 해제 후 다음 작업도 완료. 실제 HTTP에 NOT_STARTED→RUNNING 두 EXPORTED→STOPPED와 정확한 hash/크기 표시 |
| export 중 강제 종료·재시작 | 첫 파일 실제 검증 atomic checkpoint 뒤 Windows JVM 강제 종료. 새 실행기가 export부터 회복하고 DB 결과·시각·Kafka offset 보존 |
| 영속 정지·명시적 재개 | 손상 raw로 PAUSED_OPERATOR·슬롯/미commit offset 유지. 실제 run CLI의 재시작 거부, 시험 fixture 명시적 복구·실제 resume CLI 뒤 정상 완료 |
| 동시 실행 거부 | 실제 run CLI의 다른 daemon이 MariaDB named lock을 얻지 못하고 활성 journal을 바꾸지 않음. 소유자는 처리를 계속 완료 |

소유 UUID의 raw/export 객체·topic/group·DB 행만 정리하고 migration V1/V2/V3·빈 slot·singleton journal과 기존 운영 보존을 확인한다. actual source 지문·HTTP 기록·실제 수치·정리 결과는 [근거](../evidence/continuous-runtime/README.md)에 연결한다.

실제 정상 loop 시험은 production runner/actions/resources를 test helper에서 조립해 실행했고 정상 종료는 requestStop을 호출했다. 실제 run CLI는 PAUSED 재시작/경쟁 소유권 거부, resume CLI는 정지 해제를 검증했다. 정상 CLI run 전체·OS signal·systemd 종료·K8s 상주를 이번 실제 결과로 주장하지 않는다.
