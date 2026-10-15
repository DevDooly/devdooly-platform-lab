# 0006 명시적 Kafka 전달과 DB 완료 뒤 수동 offset commit

상태: 격리 시험·기존 운영 보존 검증 완료 · 2026-10-15 KST. 기본 verify 78개와 실제 MariaDB·Garage·Kafka 통합 시험 4개를 통과했다. 실제 IT는 최초와 표현 보강 후 최종 실행에서 각각 tests 4·failure 0·error 0·skip 0이었다. 이 결정은 격리 실험에 한정하며 운영 image·GitOps pin·공개 UI와 관측 계약을 바꾸지 않는다. [공개 실행 근거](../evidence/kafka-redelivery/README.md)에 최종 수치·소스 지문·정리와 보존 결과를 연결한다.

## 배경과 결정

[DB 작업·outbox 기반](../runbooks/db-job-foundation.md)과 [검증된 원본 보관](0005-verified-raw-source-storage.md)에 Kafka 전달 경계를 추가한다. 한 run의 고정 12개 합성 입력을 메시지 12개로 나누지 않고, 원본을 가리키는 작은 작업 envelope 하나로 전달한다. 기존 처리 규칙과 원본 순서를 유지하면서 ACK와 DB, offset 사이의 중단을 먼저 검증하기 위해서다.

Apache Kafka 4.3.1의 JVM 이미지, Spring Boot 4.1.1 BOM이 관리하는 `org.apache.kafka:kafka-clients:4.2.1`, Java 21을 사용한다. Kafka와 MariaDB·S3를 하나의 원자적 트랜잭션으로 묶지 않는다. 전달은 중복될 수 있으며 DB의 run·원본 hash·트랜잭션 경계를 이용해 완료 결과가 추가되거나 처리 시각이 바뀌지 않도록 한다. **시스템 전체 exactly-once 보장은 아니다.**

## 버전과 이미지 식별

2026-10-15 공식 supported 목록은 4.3.1·4.2.2·4.1.2이고 4.3.0은 archived release다. 최초 계획의 4.3.1 JVM 기준을 유지한다. Kafka 프로젝트 라이선스는 Apache-2.0이며 이미지의 OS·JRE·부속 라이브러리에는 각각의 라이선스가 적용된다. Native 이미지는 이번 범위에서 사용하지 않는다. [지원 release](https://kafka.apache.org/community/downloads/), [JVM 이미지 안내](https://kafka.apache.org/43/getting-started/docker/), [4.3.1 LICENSE](https://github.com/apache/kafka/blob/4.3.1/LICENSE)

| 식별값 | 고정값 |
| --- | --- |
| 이미지 태그 | `apache/kafka:4.3.1` |
| OCI index | `sha256:77e3df9054047a88b520d0cc46e16696d3b22022e1d580aeccd2632df6532837` |
| linux/amd64 manifest | `sha256:ccd1314e47ec76909e01f86308b4dcf2064f19f7c89759234322314b0e319e26` |
| image config | `sha256:47dccc76b32761bc57462b8753144cdbb73a16b123b1d13d3eedb92bb7952b11` |

Docker Hub 공개 태그 API와 Registry의 index·linux/amd64 manifest 응답 식별값을 대조했다. config digest는 이미지 설정 식별값이며 pull manifest 대신 사용하지 않는다. 실제 pull·실행 이미지 대조와 통합 시험은 별도 실행 근거로 남긴다. [공식 Hub 태그](https://hub.docker.com/r/apache/kafka/tags), [태그 metadata API](https://hub.docker.com/v2/repositories/apache/kafka/tags/4.3.1/)

[Boot 4.1.1 공식 BOM](https://repo.maven.apache.org/maven2/org/springframework/boot/spring-boot-dependencies/4.1.1/spring-boot-dependencies-4.1.1.pom)에 `kafka.version=4.2.1`과 해당 client의 dependencyManagement가 명시되어 있으므로 현재 parent에서 dependency version을 생략한다. broker와 client의 버전 숫자를 억지로 맞추지 않으며 4.2.1을 최신 client라고 부르지 않는다. Java 21은 Kafka 4.2와 4.3 모두의 지원 범위다. [4.2 Java 지원](https://kafka.apache.org/42/operations/java-version/), [4.3 Java 지원](https://kafka.apache.org/43/operations/java-version/)

## 초기 계획에서 바꾼 부분

[4단계 준비 계획](../plans/phase4-messaging-storage.md)은 `spring-boot-starter-kafka`를 권장했다. 이번 구현은 plain `kafka-clients`만 추가하고 `KafkaProducer`·`KafkaConsumer`를 명시적으로 생성한다. 현재 필요한 범위가 일회 발행과 한 record 수신이며, 기본 앱 시작이 broker 접속이나 listener·scheduler 자동 실행으로 이어지지 않게 하기 위해서다.

`KafkaClientFactory`, `DispatchPublisher`, `DispatchWorker`에는 자동 등록 bean·controller·scheduler를 두지 않는다. Spring Kafka starter·`spring-kafka`를 의존성에 추가하지 않으므로 KafkaTemplate이나 자동 listener container도 만들지 않는다. 명시적 시험 호출이 없는 기본 HTTP 앱에는 새 Kafka client가 생기지 않는다. 공개 POST는 계속 비활성이며 운영 배포와 기본 상태 수집도 바꾸지 않는다. 향후 상시 worker를 배포할 때는 생성·종료·인증·재시도 정책을 별도로 결정한다.

## 격리 broker와 접속 경계

broker와 controller를 합친 단일 KRaft 노드, partition 1·RF1을 사용한다. 이는 개발 실험이며 고가용성이나 디스크 손실 복구를 제공하지 않는다. metadata와 logs는 같은 전용 named volume의 서로 다른 하위 경로에 보관한다. 공식 이미지 기본 소유권으로 전용 named volume을 초기화하고 기본 `appuser` 실행을 확인했다. 수동 chown은 수행하지 않았다. [combined mode의 범위](https://kafka.apache.org/43/operations/kraft/), [공식 Dockerfile](https://github.com/apache/kafka/blob/4.3.1/docker/jvm/Dockerfile)

Docker 내부 network만 사용하고 host published port·NodePort·Ingress를 만들지 않는다. container 간 INTERNAL listener와 SSH 시험용 TUNNEL listener를 분리한다. TUNNEL advertised address는 로컬 시험의 숫자 loopback 하나이며, SSH는 원격 Kafka container IP의 해당 listener로 전달한다. host port가 없으므로 원격 호스트 `127.0.0.1`을 무조건 forward 대상으로 쓰면 안 된다. 실제 주소·이름·터널·cluster ID와 자격증명은 비공개 경로에 보관한다.

static quorum은 `CLUSTER_ID`와 `KAFKA_CONTROLLER_QUORUM_VOTERS`를 포함한 필수 env로 구성한다. 공식 entrypoint가 wrapper를 통해 설정을 생성하고 storage를 format한다. 재시작 때 같은 node ID·cluster ID·volume을 유지한다. [공식 단일 노드 예제](https://github.com/apache/kafka/blob/4.3.1/docker/examples/docker-compose-files/single-node/plaintext/docker-compose.yml), [static voters를 유지하는 wrapper](https://github.com/apache/kafka/blob/4.3.1/core/src/main/scala/kafka/docker/KafkaDockerWrapper.scala)

## 발행과 수신 순서

1. 원본 전체를 검증해 Garage 보관을 확인한 `QUEUED` 작업과 `DISPATCH / PENDING` outbox를 사용한다. staging 경계는 ADR 0005를 따른다.
2. publisher는 DB 트랜잭션 밖에서 PENDING intent를 확인하고 `schemaVersion`, `runId`, `scenarioVersion`, `sourceSha256` 네 필드만 담은 최대 1,024 ASCII byte envelope를 partition 0에 보낸다. Kafka key는 run ID다. 임의 object key는 메시지에서 받지 않고 불변 DB 작업에서 찾는다.
3. broker ACK와 응답 topic·partition·offset을 확인한 **뒤에만** 짧은 DB 호출로 dispatch outbox를 확인 처리한다. ACK 뒤 outbox 갱신 전 중단하면 PENDING이 남으며 같은 작업이 다시 발행될 수 있다.
4. worker는 한 번에 record 하나를 poll하고 envelope·key·topic·partition·DB 작업·hash·시나리오를 대조한다. 이미 완료된 작업의 재전달도 같은 검증을 거친다.
5. DB 트랜잭션 밖에서 **Get-only** `VerifiedSourceReader`로 원본을 읽고 전체 bytes·크기·SHA-256을 검증한다. 없는 원본이나 손상 객체를 DB bytes로 자동 재Put하지 않는다. 실패 시 덮어쓰기·삭제·복구를 수행하지 않는다.
6. 검증된 S3 원본과 같은 SHA를 가진 DB 보관 원본을 기존 `jobs.process(runId, sha256)`로 처리한다. 현재 구현은 S3 bytes 자체를 처리기에 직접 넘기는 것이 아니다. DB 원본도 처리 서비스 안에서 독립 검증하며 run·12개 outcome·작업 완료·export intent를 같은 DB 트랜잭션으로 확정한다.
7. DB commit 이후 `commitSync`로 해당 partition의 **record offset + 1**만 수동 commit한다. `enable.auto.commit=false`, `max.poll.records=1`을 사용한다. DB 완료 뒤 offset commit 전 중단되면 재전달되지만 기존 결과·시각·outbox·슬롯은 달라지지 않아야 한다.

producer의 `acks=all`, idempotence와 `max.in.flight=1`은 같은 producer의 재시도 순서와 중복 억제를 돕는다. publisher 재생성·재실행이나 ACK와 DB 사이의 중복을 없애는 보장은 아니다. RF1에서 `acks=all`도 복제본 추가나 HA 보장을 뜻하지 않는다.

## 유한 대기와 실패 중단

producer `retries=3`은 최초 요청 뒤 **최대 3회 재시도**다. request timeout 5초, delivery timeout 15초, `max.block.ms=5000`을 설정한다. `send()`의 metadata/buffer 대기 최대 5초와 그 뒤 Future ACK 대기 최대 15초는 서로 다른 구간이며 전체 호출을 무조건 15초라고 설명하지 않는다. delivery deadline에 따라 3회 재시도를 모두 소진하기 전에 끝날 수도 있다.

S3의 `maxAttempts=3`은 **최초 시도를 포함한 최대 3회**다. 전체 API 30초·attempt 10초·connect 3초·read 8초와 bounded Get body는 기존 설정을 유지한다. Kafka retries와 같은 의미의 횟수로 표기하지 않는다. consumer poll은 호출당 최대 5초, offset commit은 최대 10초로 제한한다.

invalid message, 원본 손상·부재, 작업 불일치, 처리·poll·offset commit 오류는 worker를 paused 상태로 만들고 예외를 반환한다. 가능한 경우 현재 record로 seek하고 assignment를 pause한다. pause/seek가 실패해도 내부 fail-stop 표식으로 **다음 poll 자체를 거부**한다. poison record를 자동 skip하거나 offset을 앞으로 밀지 않으며 무제한 retry·자동 DLQ 이동도 구현하지 않는다. 이 paused 상태는 worker 메모리 상태이며 새 영속 DB 상태를 구현했다고 부르지 않는다.

## 중단 시험과 완료 보장의 한계

package-private fault seam은 publisher ACK 뒤와 worker DB commit 뒤의 시험 경계에만 둔다. 앱 설정·HTTP 옵션·환경변수로 장애 주입을 활성화하지 않는다. 시험용 child JVM이 실제 경계에 도달한 뒤 임시 파일을 쓰고 atomic rename으로 checkpoint를 확정하면 parent가 이를 대조한 후 JVM을 강제 종료한다. 단순 예외 주입이나 고정 sleep 뒤 kill을 같은 증거로 취급하지 않는다.

DB commit 전 시험은 실제 MariaDB SQL과 transaction을 실행한 child에서 checkpoint를 확정한다. 시험 전용 wrapper/spy가 실제 process 호출을 감싼 트랜잭션을 commit 전에 멈추며 fake 결과를 반환하지 않는다. kill 뒤 다른 연결에서 미완료 상태·결과 부재를 확인하고 재전달로 정상 완료해야 한다. [실행 절차와 네 시험의 판정 기준](../runbooks/kafka-redelivery.md)을 따른다.

결과 export worker는 아직 구현하지 않았다. `COMPLETED`는 DB 연산 완료이며 결과·실패 파일의 S3 export 완료가 아니다. export intent와 singleton 실행 슬롯을 보유하고, 시험 성공을 만들기 위해 `completeExport`를 호출하거나 다음 작업 슬롯을 자동 해제하지 않는다. 시험 teardown만 자기 UUID의 폐기 가능한 자원을 명시적으로 정리한다.

실제 시험에서는 첫 세 경계에서 JVM을 각각 한 번, 총 세 번 강제 종료했다. publisher ACK 뒤 kill은 최종 log end/committed offset 2/2, 나머지 세 시험은 각각 1/1이었다. 모든 시험의 최종 lag는 0이고 run 1·outcome 12였다. 공개 JSON의 `successfulParentDeliveries`는 성공 반환한 parent 수신만 세며 중단 child·실패 시도를 포함하지 않는다. `completedReplaysObserved`도 완료된 DB 작업을 parent가 재전달받아 관측한 횟수이지 전체 전송·재시도 수가 아니다.

teardown 뒤 시험 topic·group·DB 작업/결과 행·trigger는 0개, singleton slot은 1개이며 비어 있고 V1·V2 migration은 각각 성공 1회였다. broker는 제거 전 OOM false·restart 0이었고, 전용 trial container 3개·DB/Kafka volume 2개·network를 제거했다. 보존 대상 Docker 38개의 ID 일치를 확인했으며 고정 전후 자료로 운영 image·SQL·시각·PVC·공개 API 저장 필드·실행 중 Docker 26개의 시작 시각·host boot·node·방화벽 보존을 확인했다. 운영 배포나 롤백은 수행하지 않았다.

변경은 `feat/kafka-redelivery` 검토 브랜치로 분리하며 아직 병합되지 않은 PR #8 기반의 후속 검토다. 후속 PR 생성·병합과 운영 배포는 각각 별도 상태이며 이 문서로 완료 처리하지 않는다. source SHA·고정 image/client·시간대·checkpoint·실제 수치·정리·최종 보존 근거를 함께 연결한다. 이 한정 실험으로 운영 Kafka 배포, 상시 worker, 공개 실행, 결과 export, 다중 partition ordering이나 전체 exactly-once가 완료됐다고 표시하지 않는다.

새 시험 group은 `auto.offset.reset=earliest`다. 실패 처리 코드의 skip/reset 부재와 client의 최초 offset 선택은 구분한다. retention 밖의 기존 offset 유실·자동 reset과 처리 중 동시 운영자 종료는 미검증이며 종료 요청과 offset commit의 원자적 보장을 제공하지 않는다. 상시 worker·영속 운영자 정지/재개 단계에서 별도 설계·검증한다.
