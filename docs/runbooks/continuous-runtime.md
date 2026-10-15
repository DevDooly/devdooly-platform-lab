# 상시 worker/export 실행과 작업 관측 검증

이 문서는 최초 **격리 검증**의 조건·재현 절차와 이후 실제 K3s worker 정상 재시작 절차를 구분한다. 현재 K3s의 실제 상시 CLI 배포·내부 stage는 [배포 근거](../evidence/runtime-deployment/README.md), [ADR 0009](../adr/0009-mini-pc-runtime-deployment.md), [Helm bootstrap·운영 조건](../../infra/charts/platform-lab/README.md)을 따른다. 아래 loopback·시험 수치는 당시 범위로 유지한다.

최초 격리 검증: 2026-10-15 KST · 기본 120개·실제 IT 4개·웹 34개와 기존 운영 보존 검증 완료. [ADR 0008](../adr/0008-continuous-runtime-observation.md)에 따라 기본 조회 API와 상시 실행 명령을 구분한다.

## 먼저 확인할 조건

API/관리 절차가 V3 `lab_runtime` migration을 성공적으로 적용해야 한다. 실행기 자체는 Flyway·SQL 초기화·schema 수정을 실행하지 않고 Hibernate validate와 V3 확인만 수행한다. 기존 V1/V2와 완료 샘플을 유지한다. 이 격리 시험의 연결은 숫자 loopback/SSH 터널의 전용 Kafka·Garage 범위였다. 이후 운영 K3s의 전체 서비스 DNS·Secret·자원 배치는 위 별도 근거에서 검증했다.

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

실제 정상 loop 시험은 production runner/actions/resources를 test helper에서 조립해 실행했고 정상 종료는 requestStop을 호출했다. 실제 run CLI는 PAUSED 재시작/경쟁 소유권 거부, resume CLI는 정지 해제를 검증했다. 정상 CLI run 전체·OS signal·systemd 종료·K8s 상주를 위 격리 시험의 결과로 주장하지 않는다. 이후 실제 배포와 아래 정상 재시작은 별도 근거다.

## 실제 K3s worker 정상 재시작

2026-10-15에는 작업이 없는 실제 worker Pod 하나를 UID 조건으로 삭제해 정상 TERM 종료와 같은 image/source의 교체를 관측했다. [실제 시각·종료·보존 근거](../evidence/runtime-recovery/README.md)를 따른다. 기존 두 작업은 완료·EXPORTED·빈 슬롯·pending outbox 0 상태에서 시작했다. 진행 중 작업의 crash나 broker/저장소 재시작 시험은 아니다.

1. 현재 cluster·namespace와 worker Deployment/ReplicaSet/Pod의 소유 관계·UID·container ID·image/source를 확인하고 private 기준값으로 저장한다. 실행 슬롯·pending outbox와 기존 job/결과/파일/offset도 저장한다.
2. 해당 기존 Pod의 watch·로그 follow와 짧은 읽기 전용 runtime 관측을 먼저 시작한다. 출력은 private 0600으로 보관하고 자격증명이나 CRI 원문을 공개하지 않는다.
3. 정확한 Pod UID를 DeleteOptions precondition으로 사용해 기존 300초 grace를 유지하며 삭제한다. Deployment annotation·replicas를 변경하거나 강제 삭제·grace 0을 사용하지 않는다.
4. 기존 실행의 STOPPED·종료 시각과 `RUNTIME_EXIT STOPPED STOPPED NONE`을 포착한다. 정상 TERM의 실제 exit 143을 확인했고 새 Pod는 restartCount 0으로 RUNNING·새 startedAt·전진하는 heartbeat를 남겼다. exit 0만을 종료 합격 조건으로 삼지 않으며 137/OOM·grace 초과 종료와 구분한다.
5. 기존 두 작업의 SQL 전체·모든 시각·outbox와 파일 4개의 실제 Get·크기·SHA-256, Kafka offset 2·log end 2·lag 0을 다시 대조한다. worker 외 다른 Pod·기존 Docker·PVC·DB·host boot/node/firewall도 비교한다.

단일 관측 절차는 17.808초였으며 이것을 장애 복구 SLA로 사용하지 않는다. 중간 STOPPED는 새 RUNNING이 stoppedAt을 NULL로 바꾸기 전에 별도로 포착했다. 현재 GET 응답 하나만으로 이전 종료를 증명하지 않는다.

Deployment Recreate는 template rollout 정책이며 수동 Pod 삭제 때 종료 중인 기존 Pod와 교체 생성이 잠시 겹칠 수 있다. 기존 named lock은 이전 소유자가 해제하기 전 새 실행을 거부한다. 이번 교체에서는 새 container restartCount 0을 확인했으며, 다른 회차에서 lease 거부·재시도가 생기면 이를 그대로 기록한다. named lock 강제 해제나 자동 resume으로 정상 상태를 만들지 않는다. JVM hook의 대기 240초와 Pod grace 300초를 유지한다.

재시작 후에는 내부 stage로 별도 `lab-fixture-20261015-recovery`를 접수했다. 교체 worker가 12/7/3/2/0으로 처리해 EXPORTED·슬롯 해제를 완료했고 새 파일 2개를 실제 Get·크기·SHA로 대조했다. 전체 3개 작업·파일 6개·Kafka offset 3/log end 3/lag 0을 확인했으며 원래 두 작업의 전체 SQL·시각·파일 4개는 그대로였다. 신규 허용 행을 추가한 것이므로 SQL 전체가 전후 동일하다고 표현하지 않는다. 이후 접수도 내부 고정 fixture와 별도 허용 run ID로 제한한다. Kafka/Garage PVC 전체 복원·진행 중 강제 종료·호스트 재부팅·다중 노드 HA는 이 결과에 포함하지 않는다.

## 원래 주기 job 자동 수집 검증

새 job 수집 코드로 기존 timer가 자연 실행한 두 회차를 확인했다. 중간 수동 observer 시작·timer/unit override·주기 단축 없이 unit SHA와 collector 6개 SHA/mtime·timer invocation을 대조했다. [실제 회차·Pages run·허용 필드 근거](../evidence/runtime-recovery/README.md)를 따른다.

| 자동 회차 | 실제 service 시작 → 완료 (UTC) | 실제 job capturedAt | Pages run |
| --- | --- | --- | --- |
| 첫 회차 | 2026-10-15 04:53:35.299889 → 04:53:38.863070 | 2026-10-15T04:53:37.320612517Z | [38683858607](https://github.com/DevDooly/devdooly-platform-lab/actions/runs/38683858607) |
| 둘째 회차 | 2026-10-15 05:23:43.945259 → 05:23:48.234309 | 2026-10-15T05:23:46.301898317Z | [38686554213](https://github.com/DevDooly/devdooly-platform-lab/actions/runs/38686554213) |

두 회차 모두 service·Pages build/deploy 성공과 공개 jobs/platform JSON 전체의 실제 원본 일치를 확인했다. 둘째 기록에는 재시작한 worker의 startedAt `2026-10-15T05:06:55.482287Z`, EXPORTED 작업 3개·파일 정보 6개·빈 슬롯이 포함됐으며 원래 두 작업의 HTTP 요약은 같았다. 22개 timer 검사를 통과했다.

관측한 서비스 완료 간격은 **1개·1809.371239초**이고 첫 service 비활성 뒤 다음 trigger까지는 1805.060428초였다. OnUnitInactiveSec 30분, RandomizedDelaySec 60초, AccuracySec 1분을 유지했다. service 비활성 시점·임의 지연·실행 시간과 Pages 완료 시각을 구분하며 정확히 1800초마다 게시된다고 표현하지 않는다. 두 자동 실행·한 간격을 확인한 결과이며 과거 플랫폼 collector 11회와 합산하거나 장기간 운영·자격증명 회전으로 확대하지 않는다.

다음은 Kafka/Garage metadata·data의 일관된 외부 사본과 기존 PVC를 보존하는 격리 복원, 미완료 원본의 보존/정리와 자원 한도 검증이다. 이번 재시작·정기 게시 시험을 반복하는 것보다 남은 복원 경계를 먼저 다룬다.
