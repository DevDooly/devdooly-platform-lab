# 실제 MariaDB·Garage 결합 검증

2026-10-15 KST. 기존 DB 기반과 Garage SDK 시험을 같은 격리 환경에서 연결했다. 원본 저장·검증 이후 DB 작업과 dispatch intent를 함께 확정하고, 실제 DB 오류에서 원본 보존과 재시도를 확인했다. 운영 image pin·DB·GitOps values와 공개 실행은 갱신하지 않았다.

[허용 필드 요약](summary.json) · [검증 소스 fingerprint](source-fingerprint.json) · [실행 절차](../../runbooks/s3-source-storage.md#실제-mariadb와-garage의-결합-검증)

## 실제 결과

| 조건 | 결과 |
| --- | --- |
| Java 21·Asia/Seoul 기본 clean verify | 54개, 실패·오류·skip 0, JAR 생성. 신규 IT는 기본 실행에서 제외 |
| 새 MariaDB·Garage 결합 시험 | 3개, 실패·오류·skip 0 |
| 같은 DB에서 새 JVM·메서드 순서 변경 | 첫 반복은 SSH reset으로 1 error. 소유 시험 데이터 정리 후 seed 15의 반복은 3개 모두 통과 |
| 실제 DB 오류 주입 | QUEUED UPDATE를 읽은 trigger가 DISPATCH INSERT에서 오류 1644·SQLSTATE 45000·고정 marker를 발생시킴 |
| rollback과 재시도 | 최초 STAGING metadata·생성 시각·DB 원본·슬롯 유지, outbox·결과 없음, 실제 Garage 원본 bytes·크기·SHA-256 보존. trigger 제거 후 같은 원본으로 QUEUED·dispatch 1개 복구 |
| 시험 종료 상태 | 빈 singleton 슬롯 1개, job·outbox·run·outcome 0개, trigger 0개, V1·V2 migration 각각 성공 1회 |
| 시험 자원 정리 | 소유 컨테이너 2개·전용 DB 볼륨·내부 network 제거, 기존 Docker 전체 38개 ID 보존 |
| 운영 전후 비교 | 실행 중 Docker 26개 ID·시작 시각·mount, 전체 SQL·Flyway·처리 시각·API 저장값, PVC 2개·DB Pod image/mount·호스트 부팅·Node·방화벽 보존 |

동일한 3개 시험을 두 번 통과한 것이며, 서로 다른 6개 시험이라는 뜻은 아니다. 기본 verify 54개와 외부 서비스의 명시적 IT를 구분한다. 공개 fingerprint는 모든 시험에서 같은 API 소스·test·설정·pom의 LF 기준 hash와 실제 파일을 대조한 결과다. 개별 연결 주소·자격증명·호스트 경로·원문 로그는 비공개로 보관한다.

## 확인한 동작

1. `SourceStagingService`의 실제 S3 I/O 전후에 DB 트랜잭션이 없고, 원본과 hash 검증 중 작업 metadata·outbox가 바뀌지 않았다. 검증 뒤 QUEUED·DISPATCH 1개가 함께 저장됐다. 같은 요청 및 COMPLETED 후 재요청에서도 결과 12개·판정·완료 시각·outbox가 유지됐다.
2. 같은 길이의 손상 원본은 덮어쓰지 않았고 STAGING·슬롯·dispatch 부재를 유지했다. 시험 코드가 자신이 만든 손상 객체만 명시적으로 제거한 뒤 재시도하여 복구했다.
3. 해당 UUID run의 DISPATCH에만 적용되는 `BEFORE INSERT` trigger를 사용했다. trigger가 같은 트랜잭션의 QUEUED를 실제 조회한 경우에만 `S3DB_IT_DISPATCH_AFTER_QUEUED`를 발생시키므로, 앞선 mark 진입 전 오류 주입과 구분된다. 실패 후 별도 조회에서 metadata 전체·DB 원본·시각·슬롯과 Garage Get을 확인했다. [MariaDB trigger의 트랜잭션 동작](https://mariadb.com/docs/server/server-usage/triggers-events/triggers/trigger-overview), [SIGNAL](https://mariadb.com/docs/server/reference/sql-statements/programmatic-compound-statements/signal)

MariaDB 11.8.9와 Garage 2.4.1은 digest 고정 이미지를 사용했다. 메모리 상한은 각각 1 GiB·1.5 GiB, CPU 각 1개이며 성능 측정치가 아니다. host published port 없이 내부 network와 기존 SSH의 숫자 loopback 터널로 연결했다. Java에는 운영 DB root·kubeconfig·Garage 관리 토큰을 전달하지 않았다. 전용 schema 사용자에게만 Flyway DDL·DML·시험 trigger 권한을 부여했다.

## 실패 기록과 복구

준비 도구가 MariaDB `SHOW GRANTS`의 이스케이프 표기를 잘못 비교하여 중단됐다. 표기 검사만 교정하고 소유권을 확인한 임시 DB에서 준비를 이어갔다.

첫 반복에서는 SSH 터널 `Connection reset`과 JDBC commit 응답·시험 teardown 오류가 관측됐다. MariaDB·Garage는 OOM·재시작 없이 계속 실행 중이었고, 별도 조회에서 시험 작업 QUEUED·DISPATCH 각 1개·점유 슬롯과 결과 0개를 확인했다. 이 상태로 commit 성공이나 자동 복구를 주장하지 않았다. SSH reset의 근본 원인은 확정하지 않았다.

해당 시험 UUID의 원본은 재Put 없이 Get으로 bytes·hash를 확인한 뒤 명시적 정리를 시작했다. 별도 정리 도우미가 슬롯 FK를 먼저 해제하지 않아 오류 1451로 DB 정리 트랜잭션이 rollback됐다. 이 실패도 보존했다. 정리 순서를 슬롯 해제→소유 outbox·job 삭제로 교정하고 이미 제거한 소유 객체의 정확한 NoSuchKey를 확인한 뒤 DB만 정리했다. 다른 UUID나 운영 자원은 정리하지 않았다. 같은 DB·소스·JVM 시간대·랜덤 순서 조건의 재실행에서 3개 모두 통과했고 최종 빈 상태와 운영 보존을 다시 확인했다. 이 임시 정리 도우미의 오류는 앱 코드나 신규 IT의 teardown 수정으로 숨기지 않았다.

## 한계와 다음 단계

이 기록은 실제 S3 성공 뒤 MariaDB statement 오류·rollback과 재시도 경계다. 실제 COMMIT ACK 유실, DB 서버·호스트 장애, 전체 exactly-once, wire 단위 Put 1회, 동시 writer·CAS·WORM·성능을 검증하지 않았다. SDK 자체 재시도는 기존 상한을 유지한다.

Kafka 발행 ACK·worker·offset, 원본 replay·결과 export와 운영 배포는 후속이다. 신규 테스트는 명시적으로 선택해야 하며 Jenkins·Actions의 기본 verify가 이 외부 IT를 자동 수행한다고 표기하지 않는다. 새 API image는 기본 Flyway에 따라 V2를 적용할 수 있으므로 코드 검토와 운영 image pin 변경을 분리하고, 배포 전 백업·migration·이전 image 호환성과 복구 절차를 확인한다.
