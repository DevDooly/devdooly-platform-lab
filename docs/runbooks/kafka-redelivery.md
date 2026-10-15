# Kafka ACK·DB·offset 사이의 중단과 재전달 검증

[ADR 0006](../adr/0006-explicit-kafka-dispatch.md)에 따른 내부 adapter의 격리 실행 절차다. 2026-10-15 기본 verify 78개와 실제 서비스 통합 시험 4개가 통과했다. 실제 IT는 최초와 공개 수치 표현 보강 후 최종 실행에서 각각 tests 4·failure 0·error 0·skip 0이었다. 아래 합격 기준과 뒤의 실제 수치를 구분하며, [공개 실행 근거](../evidence/kafka-redelivery/README.md)에 실제 수치·소스 지문·정리와 기존 운영 보존 최종 대조 결과를 연결한다.

## 범위

Java 21·Spring Boot 4.1.1과 BOM 관리 `kafka-clients:4.2.1`, Apache Kafka 4.3.1 JVM 단일 broker/controller를 사용한다. MariaDB·Garage·Kafka는 모두 폐기 가능한 전용 시험 자원이다. 공개 합성 시나리오 `sensor-validation-v1`의 고정 원본 12개만 사용한다. 기대 판정은 입력 12 = 성공 7 + 실패 3 + 업무상 중복 2 + 대기 0이다.

구현은 `apps/api/src/main/java/io/github/devdooly/platformlab/jobs/messaging/`의 `DispatchMessage`, `KafkaClientFactory`, `DispatchPublisher`, `DispatchWorker`와 Get-only `VerifiedSourceReader`다. 실제 시험은 같은 package의 `KafkaRedeliveryIT`, child 실행은 `KafkaCrashProbe`다. 기본 앱에 Kafka 자동 bean·HTTP 실행 endpoint·listener scheduler를 등록하지 않는다. 기본 HTTP 앱 시작은 broker 접속을 발생시키지 않으며 공개 POST 405와 운영 image·GitOps pin·기존 UI 관측값은 유지한다.

## 격리 환경 준비

운영 DB·bucket·broker를 사용하지 않는다. 기존 Docker 서비스·firewall·proxy·namespace·PVC에는 변경하지 않고 시험용 network·volume·container만 준비한다. Java는 일반 사용자로 실행하고 DB root·Garage 관리 토큰·호스트 root·운영 kubeconfig를 넘기지 않는다.

Kafka 이미지는 linux/amd64 manifest로 고정한다.

```text
apache/kafka:4.3.1@sha256:ccd1314e47ec76909e01f86308b4dcf2064f19f7c89759234322314b0e319e26
```

index는 `sha256:77e3df9054047a88b520d0cc46e16696d3b22022e1d580aeccd2632df6532837`, config ID는 `sha256:47dccc76b32761bc57462b8753144cdbb73a16b123b1d13d3eedb92bb7952b11`이다. pull과 inspect 결과를 각각 대조하며 단순 태그 조회를 기동 검증으로 기록하지 않는다. [공식 이미지 안내](https://kafka.apache.org/43/getting-started/docker/), [Hub 태그 metadata](https://hub.docker.com/v2/repositories/apache/kafka/tags/4.3.1/), [client 관리 BOM](https://repo.maven.apache.org/maven2/org/springframework/boot/spring-boot-dependencies/4.1.1/spring-boot-dependencies-4.1.1.pom)

broker는 combined KRaft 1개이며 topic은 시험마다 UUID 이름으로 partition 1·RF1을 명시 생성한다. 자동 topic 생성을 끈다. metadata와 log는 같은 전용 volume에 각각 `/var/lib/kafka/data/metadata`, `/var/lib/kafka/data/logs`로 둔다. 공식 이미지 기본 소유권으로 새 named volume을 초기화하고 default `appuser`로 기동했다. 이번 실행에서는 수동 chown이나 root helper로 소유권을 변경하지 않았다. [공식 Dockerfile](https://github.com/apache/kafka/blob/4.3.1/docker/jvm/Dockerfile)

host published port는 없으며 내부 Docker network에서만 listener를 연다. 예시 구조는 다음과 같다. 실제 cluster ID와 주소·포트는 비공개 환경 자료에 기록한다.

```text
KAFKA_PROCESS_ROLES=broker,controller
KAFKA_NODE_ID=1
KAFKA_CONTROLLER_QUORUM_VOTERS=1@kafka:9093
KAFKA_LISTENER_SECURITY_PROTOCOL_MAP=INTERNAL:PLAINTEXT,CONTROLLER:PLAINTEXT,TUNNEL:PLAINTEXT
KAFKA_LISTENERS=INTERNAL://:9092,CONTROLLER://:9093,TUNNEL://:9094
KAFKA_ADVERTISED_LISTENERS=INTERNAL://kafka:9092,TUNNEL://127.0.0.1:39092
KAFKA_INTER_BROKER_LISTENER_NAME=INTERNAL
KAFKA_CONTROLLER_LISTENER_NAMES=CONTROLLER
CLUSTER_ID=<최초 포맷에 사용한 전용 cluster ID>
```

이는 예시이며 한 줄 env만으로 충분한 전체 기동 설정은 아니다. 단일 노드용 offsets·transaction·share coordinator 내부 topic RF와 ISR도 1로 설정한다. static voters와 cluster ID는 공식 entrypoint format에 사용되며 재시작 때 유지한다. [공식 single-node 예제](https://github.com/apache/kafka/blob/4.3.1/docker/examples/docker-compose-files/single-node/plaintext/docker-compose.yml), [wrapper](https://github.com/apache/kafka/blob/4.3.1/core/src/main/scala/kafka/docker/KafkaDockerWrapper.scala)

SSH는 로컬 숫자 loopback에만 bind하고 원격 container IP의 TUNNEL listener로 연결한다. host port가 없으므로 원격 호스트 `127.0.0.1:9094`를 대상으로 삼지 않는다. 컨테이너 재생성 후 IP가 달라지면 대상과 cluster ID를 다시 확인한다.

```text
ssh -N -L 127.0.0.1:39092:<원격 Kafka container IP>:9094 <본인 SSH host alias>
```

`127.0.0.1:39092`는 설명용 예시다. 실제 bootstrap은 현재 열어 둔 전용 터널 하나여야 하고 broker metadata의 TUNNEL advertised address와 일치해야 한다. combined RF1은 고가용성·복제본·디스크 유실 복구를 제공하지 않는다.

## 필수 시험 환경변수

| 이름 | 허용 조건 |
| --- | --- |
| `DB_TEST_URL` | `jdbc:mariadb://127.0.0.1:<포트>/platform_lab_kafka_it`. 다른 schema·host·query 옵션은 거부 |
| `DB_TEST_USERNAME` | 해당 폐기 가능한 schema의 전용 사용자 |
| `DB_TEST_PASSWORD` | 해당 시험 사용자 비밀번호 |
| `LAB_S3_TEST_ENDPOINT` | `http://127.0.0.1:<포트>` 또는 끝 `/` 하나. 전용 SSH tunnel origin |
| `LAB_S3_TEST_BUCKET` | `platform-lab-s3-test-`와 소문자·숫자·하이픈 1~42자로 된 기존 전용 bucket |
| `LAB_S3_TEST_ACCESS_KEY` | 그 시험 bucket의 전용 read/write access key |
| `LAB_S3_TEST_SECRET_KEY` | 전용 key의 secret |
| `LAB_KAFKA_TEST_BOOTSTRAP` | `127.0.0.1:<포트>` 한 곳. `localhost`, 복수 bootstrap, URL scheme·path는 거부 |
| `LAB_KAFKA_TEST_CLUSTER_ID` | 최초 포맷에 사용한 전용 cluster ID. `[A-Za-z0-9_-]{16,64}` |

모든 포트는 1~65535여야 한다. DB URL 검사는 Flyway 전에 적용한다. 연결 후 실제 DB product가 MariaDB이고 catalog가 정확히 `platform_lab_kafka_it`인지 확인한다. job·outbox는 0개, singleton slot은 1개이며 비어 있어야 한다. Kafka Admin `describeCluster()`의 실제 cluster ID가 기대값과 같고 node가 정확히 1개인지 parent와 child가 각각 확인한다. loopback과 이름 검사만으로 운영 자원 사용이 허가되는 것은 아니다.

credentials와 실제 접속정보·원본 로그·child checkpoint는 Git에서 제외한 비공개 경로에 둔다. 전용 환경 파일에는 위 값을 준비하고 shell tracing·환경 전체 출력·CI artifact 등록을 하지 않는다. 다음은 본인이 작성하고 권한을 제한한 신뢰 가능한 파일을 읽는 예다.

```sh
set +x
set -a
. ../../.local/.private/kafka-redelivery/test.env
set +a
```

## 실행

Java 21의 `apps/api`에서 기본 검증을 먼저 수행한다. Windows는 `mvnw.cmd`를 사용한다.

```sh
./mvnw -B -ntp verify
```

기본 verify는 실제 외부 Kafka 시험을 자동으로 선택하거나 broker를 시작하지 않는다. 기본 test는 envelope 검증, ACK 뒤 outbox 경계, raw Get과 DB commit·수동 offset 순서, 실패 뒤 다음 poll 거부, 자동 client bean 부재 등 내부 계약을 확인한다. 기본 78개 통과는 실제 Kafka·MariaDB·Garage 시험 통과와 별도 결과다.

전용 자원·세 SSH tunnel·환경변수·빈 DB 상태를 확인한 다음 실제 시험을 명시적으로 선택한다.

```sh
./mvnw -B -ntp -Dlab.kafka.tests=true \
  -Dtest=KafkaRedeliveryIT \
  -DargLine=-Duser.timezone=Asia/Seoul test
```

JVM과 child는 Java 21·Asia/Seoul을 요구한다. 시험은 H2가 아닌 실제 MariaDB, 실제 Garage SDK와 Kafka broker에 연결한다. container 준비·자격증명 발급·터널은 테스트가 자동으로 하지 않는다. 별도 서비스가 필요하며 default app 실행으로 시험을 대신하지 않는다.

## 실제 시험 네 가지와 합격 기준

| 시험 | 실제 중단/오류 경계 | 반드시 확인할 결과 |
| --- | --- | --- |
| `killedPublisherAfterActualAckCausesTwoRecordsButOneUnchangedBusinessResult` | child가 실제 broker ACK를 받은 뒤 DB outbox acknowledge 전에 checkpoint를 확정하고 parent가 강제 kill | PENDING intent 유지. 다시 발행하면 log end 2. 두 record를 소비해도 run 1·outcome 12, 원본·outbox·완료 시각·슬롯은 최초 완료 그대로. 최종 committed offset 2·lag 0 |
| `killedWorkerAfterDbCommitRedeliversWithoutChangingCompletedRowsOrTimes` | 실제 DB commit 완료 뒤 offset commit 전에 child checkpoint 확정 후 강제 kill | kill 전 run 1·outcome 12가 다른 연결에서 보이고 group offset은 미commit. 새 consumer의 같은 offset 재전달은 완료 결과·시각을 변경하지 않음. 최종 committed offset 1·lag 0 |
| `killedWorkerInsideRealUncommittedSqlRollsBackThenRedeliveryCommitsOneBatch` | 실제 MariaDB transaction 안에서 SQL로 run 1·outcome 12 생성 후 commit 전 child checkpoint 확정 후 강제 kill | kill 뒤 다른 연결에서 QUEUED·결과 행 부재·offset 미commit. 새 worker가 처음 처리로 12개를 한 번에 확정하고 최종 committed offset 1·lag 0 |
| `corruptRawSourcePausesWithoutOffsetCommitAndFreshWorkerRecoversAfterExplicitFixtureRepair` | 시험 코드가 자기 raw 객체만 손상시킨 뒤 worker가 Get 검증 | `SOURCE_INVALID`, worker paused, 다음 receive도 poll 전에 거부. DB QUEUED·결과 부재·offset 미commit·손상 bytes 보존. 시험 코드가 자기 고정 fixture를 명시적으로 복원한 뒤 새 worker가 성공. 최종 committed offset 1·lag 0 |

위 offset 값은 각 시험의 새 UUID topic이 비어 있고 partition이 하나라는 조건의 기대값이다. 실행 근거에는 실제 log end·committed offset·lag·run/outcome 건수를 기록한다. Kafka 메시지 수와 재전달/재처리 수를 업무상 중복 입력 2건과 섞지 않는다. lag 단위도 센서 이벤트 12개가 아닌 작업 envelope record다.

## 2026-10-15 실제 시험 수치

최초 실행과 최종 실행은 각각 4개 모두 통과했고 failure·error·skip은 0이었다. 최종 실행의 수치는 다음과 같다. 공개 JSON 필드는 이름만 보고 전체 시도 수로 읽지 않도록 범위를 명시한다.

| case | forcedKills | successfulParentDeliveries | completedReplaysObserved | logEnd / committedOffset | lag | run / outcome |
| --- | --- | --- | --- | --- | --- | --- |
| `publisher-ack-kill` | 1 | 2 | 1 | 2 / 2 | 0 | 1 / 12 |
| `worker-after-db-kill` | 1 | 1 | 1 | 1 / 1 | 0 | 1 / 12 |
| `worker-before-dbcommit-kill` | 1 | 1 | 0 | 1 / 1 | 0 | 1 / 12 |
| `source-invalid-pause-recovery` | 0 | 1 | 0 | 1 / 1 | 0 | 1 / 12 |

`successfulParentDeliveries`는 parent worker가 정상 반환한 수신만 센다. 강제 종료된 child의 수신·처리나 손상 원본의 실패 시도는 포함하지 않는다. `completedReplaysObserved`는 parent가 이미 DB 완료된 작업의 재전달을 확인한 횟수다. producer 내부 retry, 네트워크 실제 전달 횟수, 전체 처리 시도 횟수와 동의어가 아니다. 최종 실행 기준 forced kill은 3회이며 최초 실행도 별도로 3회 수행했다. 손상 원본 시험은 강제 kill을 수행하지 않았다.

## checkpoint와 강제 종료 증거

첫 세 시험은 실제 child JVM을 시작한다. publisher ACK 뒤와 worker DB commit 뒤에는 package-private 생성자의 fault seam을 쓴다. DB commit 전 시험은 시험 전용 wrapper/spy로 실제 process 메서드와 MariaDB transaction을 감싸 실제 SQL이 완료된 상태에서 멈춘다. mock DB나 모의 완료 결과를 강제 종료 증거로 사용하지 않는다.

child는 새로운 비공개 `checkpoint.pending-<pid>`에 경계 정보를 쓰고 `ATOMIC_MOVE`로 `checkpoint.json`을 확정한 뒤 대기한다. parent는 mode·phase·run ID·topic·partition·해당 DB/offset 상태를 대조한 다음 `destroyForcibly()`로 종료하고 실제 종료를 확인한다. checkpoint를 보기 전에 끝난 child, timeout, atomic rename 실패는 합격이 아니다. 고정 sleep 뒤 임의 kill하거나 teardown의 잔여 child 종료를 성공한 장애 실험으로 세지 않는다.

DB SQL-before-commit checkpoint의 offset 필드는 전달 완료 경계가 아직 아니므로 sentinel `-1`을 쓴다. 이 시험의 offset 부재는 Kafka Admin으로 별도 확인한다. transaction 내부에서 확인한 행 수와 다른 연결에서 보이는 commit된 행 수를 구분한다.

checkpoint·child log는 OS 임시 디렉터리에 비공개로 남겨 실패 진단에 사용한다. 공개 근거에는 허용된 case·phase·건수·source SHA·시간대·고정 image/client만 옮기고 실제 host·IP·포트·credentials·raw error·비공개 경로를 제외한다.

## 실패 중단과 재시도 의미

publisher는 `acks=all`, idempotence, `max.in.flight=1`, `retries=3`을 사용한다. `retries=3`은 최초 이후 최대 3회 재시도이며 전체 delivery deadline에 먼저 걸릴 수도 있다. `max.block.ms` 5초는 `send()`의 metadata/buffer 대기이고 Future ACK 대기 15초와 다른 구간이다. 전체 호출이 무조건 15초 이내라고 기록하지 않는다.

S3는 기존 전체 API 30초·attempt 10초·connect 3초·read 8초, **최초 포함 maxAttempts 3회**를 유지한다. S3 Get은 DB 트랜잭션 밖에서 수행하며 원본 전체 bytes·크기·SHA를 검증한다. worker는 S3 Put·Delete를 사용하지 않는다. 검증 뒤 처리기는 동일 SHA의 DB 보관 원본을 독립 검증해 처리하므로 S3 bytes 직접 처리나 일반 S3 replay 엔진으로 설명하지 않는다.

worker는 `enable.auto.commit=false`, `max.poll.records=1`이며 DB commit 뒤 `offset+1`을 `commitSync`한다. invalid envelope·poison record·원본 오류·DB/offset/poll 실패는 paused fail-stop이다. 가능한 seek/pause가 실패해도 내부 paused 표식이 다음 poll을 차단한다. 실패 처리 코드가 오류 record를 skip하거나 offset을 reset·commit하지 않는다. 자동 DLQ 이동·무한 retry도 없다. 다만 새 group은 `auto.offset.reset=earliest`를 사용하므로 commit이 없거나 보존 범위 밖일 때 client의 earliest reset 정책이 적용된다. 기존 offset 유실·retention 만료 경계는 이번 시험 범위가 아니다.

실제 복구는 관리자 원인 확인 뒤 새 client/worker로 수행한다. 손상 fixture를 다시 쓰는 네 번째 시험은 시험 코드의 명시적 복구일 뿐 adapter 자동 복구 기능이 아니다. 운영 원본을 확인 없이 재Put·삭제하거나 offset을 앞으로 밀어 성공을 만들지 않는다.

## export와 슬롯, 정리

DB `COMPLETED`는 연산 결과 확정이다. 결과·실패 파일 export는 아직 구현하지 않았고 export outbox와 전체 실행 슬롯은 남아 있어야 한다. `completeExport`를 호출해 성공을 꾸미거나 재전달 성공만으로 슬롯을 해제하지 않는다. 따라서 이번 검증은 전체 end-to-end 완료나 exactly-once 보장이 아니다.

각 시험의 teardown은 본인이 생성한 `kafka-it-<UUID>` run, `platform-lab-kafka-test-topic-<UUID>`, `platform-lab-kafka-test-group-<UUID>`, 그 run의 raw key만 정리한다. bucket 전체·다른 prefix·다른 topic/group·운영 자원은 정리하지 않는다. DB도 소유 run 이외의 작업이 없는지 확인하고 짧은 트랜잭션에서 슬롯 해제 후 자기 outbox·outcome·run·job만 삭제한다. 이는 폐기 가능한 시험 종료 절차이며 일반 worker의 export 완료 처리와 다르다.

teardown 실패 시 반복 실행 전에 멈춘다. 실제 cluster ID·schema·bucket·소유 UUID와 살아 있는 child, DB 상태·슬롯·raw bytes·offset을 먼저 확인하고 로그를 보존한다. 소유 상태가 확인되지 않으면 포괄 삭제나 DB 초기화로 다음 시험을 통과시키지 않는다.

최종 시험 정리에서 topic·group·DB 작업/결과 행·trigger 0개, 빈 singleton slot 1개, V1·V2 migration 각각 성공 1회를 확인했다. broker는 제거 전 OOM false·restart 0이었다. trial container 3개·DB/Kafka volume 2개·network를 제거했고 보존 대상 Docker 38개 ID 일치를 확인했다. 원본 checkpoint와 child log는 비공개 진단 자료로 남기며 성공 수치 표현 보강은 실행 결과 실패나 로직 교정으로 오인하지 않도록 구분한다.

고정 전후 자료로 기존 운영 image pin·SQL 전체와 처리 시각·PVC·실행 중 Docker 26개의 ID/start time/mount·host boot·node·firewall·공개 API 저장 필드의 보존을 확인했다. [실제 결과](../evidence/kafka-redelivery/summary.json)에 Maven test/failure/error/skip, 실제 최종 offset/lag, 정리와 보존 결과를 기록했고 [소스 지문](../evidence/kafka-redelivery/source-fingerprint.json)을 연결했다. Windows child JVM 강제 종료 실험이며 Linux Pod kill로 표현하지 않는다. 작업은 `feat/kafka-redelivery` 검토 브랜치로 분리하며 PR #8 미병합 기반의 후속 변경이다. 운영 배포는 하지 않았고, 이 격리 시험으로 4단계 전체나 운영 Kafka 반영을 완료 표시하지 않는다.

처리 중 운영자 종료를 동시에 실행하는 경계는 검증하지 않았다. 최초 job 조회에서는 종료 작업을 거부하지만 S3 Get 중 이미 완료된 작업이 종료되면 기존 process가 완료 행을 반환할 수 있다. 운영자 종료와 offset commit의 원자적 상호 배제를 보장하지 않으며, 상시 worker와 영속 정지/재개를 구현할 때 이 경계를 별도 검증한다.
