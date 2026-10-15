# Kafka 발행·수신과 중단 후 재전달 검증

2026-10-15 KST에 실제 Apache Kafka 4.3.1·MariaDB 11.8.9·Garage 2.4.1을 격리 실행했다. Java 21·Asia/Seoul, Spring Boot 4.1.1 BOM의 `kafka-clients:4.2.1`을 사용했다. 기본 verify **78개**와 별도 실제 서비스 IT **4개**가 모두 통과했다. 실제 IT는 최초·근거 표현 보강 후 최종 실행에서 각각 4/0/0/0이었으며 **서로 다른 8개 시험이라는 뜻은 아니다.**

[허용 필드만 추린 실제 결과](summary.json) · [최종 시험 소스 지문](source-fingerprint.json) · [재실행 절차](../../runbooks/kafka-redelivery.md) · [ADR 0006](../../adr/0006-explicit-kafka-dispatch.md)

## 확인한 경계

publisher는 실제 broker ACK 뒤에만 DB dispatch intent를 확인 처리한다. worker는 Get-only 원본 검증과 DB commit을 마친 뒤 해당 record의 `offset + 1`을 수동 commit한다. 오류 시 다음 poll을 차단한다. 이미 완료된 작업을 다시 받더라도 run·12개 outcome·원본·outbox·완료 시각·슬롯을 변경하지 않는지 전체 snapshot으로 확인했다.

| 실제 시험 | 중단/오류 뒤 확인 | 최종 log end / committed offset | lag | run / outcome |
| --- | --- | --- | --- | --- |
| publisher ACK 뒤 강제 종료 | PENDING을 다시 발행해 record 2개, DB 결과는 한 번만 생성 | 2 / 2 | 0 | 1 / 12 |
| DB commit 뒤 offset 전 강제 종료 | 같은 offset 재전달, 완료 행과 처리 시각 그대로 | 1 / 1 | 0 | 1 / 12 |
| 실제 SQL 실행 뒤 DB commit 전 강제 종료 | 다른 연결에서 rollback·결과 부재 확인 후 재전달로 완료 | 1 / 1 | 0 | 1 / 12 |
| 손상 raw 원본 | paused·offset 미commit·결과 부재·손상 bytes 보존; 시험 코드의 명시적 fixture 복원 뒤 새 worker 성공 | 1 / 1 | 0 | 1 / 12 |

앞의 세 시험은 실제 경계의 atomic checkpoint와 DB/offset을 대조한 뒤 Windows child JVM을 `destroyForcibly()`로 각각 한 번 종료했다. 고정 sleep 뒤 kill이나 예외만 주입한 시험이 아니다. Linux Pod·호스트·broker 중단을 검증한 것은 아니다. 각 run의 판정은 입력 12 = 성공 7 + 실패 3 + 업무상 중복 2 + 대기 0이다. Kafka record/lag의 단위는 이 12개를 담은 작업 envelope다.

`successfulParentDeliveries`는 정상 반환한 parent 수신만 센다. 중단 child·실패 시도는 포함하지 않는다. `completedReplaysObserved`는 parent가 완료 작업의 재전달을 관측한 횟수다. 전체 broker 전송·client retry·처리 시도 수로 해석하지 않는다. 최초와 최종의 변경은 시험 helper 두 파일의 근거 표현·트랜잭션 상태 확인이며 production 코드는 같았다. 기본 verify와 최종 IT의 공통 소스 지문도 일치했다. 빌드 JAR의 Kafka client 4.2.1 포함, Spring Kafka와 장애 시험 helper 부재를 확인했다.

## 정리와 기존 운영 보존

시험 종료 뒤 자기 UUID topic/group·작업/outbox/run/outcome·trigger는 0개, 빈 singleton slot은 1개이고 V1·V2 migration은 각각 성공 1회였다. broker는 제거 전 restart 0·OOM false였다. 전용 container 3개·DB/Kafka named volume 2개·internal network 1개를 제거했다. 비공개 Garage 진단 데이터와 원본 로그·checkpoint는 진단용으로 남겼다.

고정 전후 관측을 대조해 기존 Docker **전체 38개 ID**, 그중 **실행 중 26개 ID·시작 시각·mount**, 운영 Lab Pod 3개·PVC 2개, DB 전체 SQL·Flyway·처리 시각, API 저장 필드, API/Web image pin·source, Argo revision·Synced/Healthy, host boot·node·방화벽을 보존했음을 확인했다. 과거 observer의 `restored` 명칭을 새 배포·롤백 수행으로 해석하지 않도록 공개 요약에는 `productionPinsAndSourceUnchanged`로 기록했다. 이번 작업의 운영 배포·롤백은 없었다.

## 구현 범위와 남은 작업

`feat/kafka-redelivery`는 미병합 PR #8의 DB/S3 기반 위에 분리한 후속 변경이다. 실제 접속 주소·포트·cluster ID·비밀값·원문 오류·진단 경로는 공개 자료에 옮기지 않았다. source 지문은 최종 실제 IT에 대응하며 문서 작성 commit과는 별도로 대조할 수 있다.

- 기본 HTTP 앱에는 자동 Kafka bean·listener·scheduler를 등록하지 않았다. 공개 POST·기존 UI/관측 계약과 운영 이미지 pin은 유지했다.
- 단일 combined KRaft·partition 1·RF1 실험이다. HA·broker 디스크 손실·다중 partition·시스템 전체 exactly-once 보장이 아니다.
- 원본 S3 Get 검증 뒤 같은 SHA의 DB 보관 원본을 독립 검증해 기존 처리기로 실행한다. S3 bytes를 직접 처리하는 범용 replay 엔진은 아니다.
- fail-stop은 worker 메모리 상태다. 영속 운영자 정지·자동 DLQ·상시 worker Pod는 후속이다.
- 새 시험 group은 `auto.offset.reset=earliest`로 시작한다. 실패 처리 코드가 offset을 건너뛰거나 reset하지 않는다는 뜻이며, retention 밖의 기존 commit 유실·자동 reset과 처리 중 동시 운영자 종료는 검증하지 않았다. 종료 요청과 offset commit의 원자적 보장을 제공하지 않는다.
- DB `COMPLETED` 뒤 결과/실패 파일 export는 아직 구현하지 않았다. export intent와 실행 슬롯은 유지하며, fixture teardown을 export 완료로 세지 않는다. **다음 구현은 결과·실패 export와 export 확인 후 슬롯 해제 검증**이다.
