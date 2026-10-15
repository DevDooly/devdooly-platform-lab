# 결과·실패 파일 export와 실행 슬롯 해제 검증

2026-10-15 KST · 기본 verify 97개·실제 IT 6개 통과, 기존 운영 보존 검증 완료. [ADR 0007](../adr/0007-verified-result-export.md)의 내부 호출을 실제 MariaDB·Garage에서 검증한다. Kafka 발행·수신의 검증은 [앞선 결과](../evidence/kafka-redelivery/README.md)와 별도다.

## 실행 전 조건

전용 폐기 가능한 MariaDB 11.8.9와 Garage 2.4.1, Java 21·Asia/Seoul을 사용한다. 새 제품·SDK 의존성은 추가하지 않고 기존 AWS SDK for Java v2와 Garage 전용 설정을 재사용한다. 이미지 manifest는 [S3 근거](../evidence/s3-source-storage/README.md)와 같은 고정값을 사용한다. DB 1 GiB·Garage 1.5 GiB는 container limit이며 실제 사용량·성능 수치가 아니다.

Docker internal network에 두 container만 두고 host published port를 만들지 않는다. 본인 SSH 연결의 숫자 loopback 터널로만 접속한다. 기존 Docker·K3s·PVC·firewall·proxy를 변경하지 않는다. SQL root와 Garage 관리자 credential은 시험 Java에 넘기지 않는다.

| 환경변수 | 허용 범위 |
| --- | --- |
| `DB_TEST_URL` | `jdbc:mariadb://127.0.0.1:<port>/platform_lab_export_it`, query 옵션 없음 |
| `DB_TEST_USERNAME`, `DB_TEST_PASSWORD` | 위 schema의 전용 시험 사용자. 실제 SQL 실패 시험에는 해당 schema의 TRIGGER 권한 필요 |
| `LAB_S3_TEST_ENDPOINT` | `http://127.0.0.1:<port>` 또는 끝 `/` 하나 |
| `LAB_S3_TEST_BUCKET` | `platform-lab-s3-test-` prefix의 전용 시험 bucket |
| `LAB_S3_TEST_ACCESS_KEY`, `LAB_S3_TEST_SECRET_KEY` | 그 bucket의 read/write 전용 key |

포트는 1~65535다. DB URL은 Flyway 전에 검사하며 실제 DB product·catalog도 확인한다. 작업·outbox·결과는 0개, singleton slot은 1개이며 비어 있어야 한다. loopback·이름 검사만으로 운영 자원 사용이 허용되는 것은 아니다. 실제 접속값은 비공개 환경 파일에 보관하고 채팅·Git·CI artifact·shell tracing에 옮기지 않는다.

## 실행 방법

먼저 `apps/api`에서 기본 verify를 실행한다. Windows는 `mvnw.cmd`를 사용한다.

```sh
./mvnw -B -ntp -DargLine=-Duser.timezone=Asia/Seoul verify
```

전용 서비스를 준비하고 환경변수를 설정한 뒤 실제 시험을 명시적으로 선택한다.

```sh
./mvnw -B -ntp -Dlab.export.tests=true \
  -Dtest=VerifiedResultExportIT \
  -DargLine=-Duser.timezone=Asia/Seoul test
```

기본 verify는 `*IT`나 외부 서비스를 자동으로 실행하지 않는다. 실제 시험은 H2가 아닌 MariaDB·Garage에 연결하며 서비스 준비·credentials 발급·SSH 터널은 별도 절차다. 운영 bucket·DB를 사용하거나 HTTP 앱을 실행해 시험을 대신하지 않는다.

## 여섯 가지 합격 기준

| 시험 | 반드시 확인할 결과 |
| --- | --- |
| 정상 export·반복·다음 작업 | 결과 12개·실패 입력 3개와 정확한 이유, 두 파일 전체 Get bytes/hash 일치. EXPORTED·outbox 확인과 슬롯 해제 뒤 새 작업 접수. 이전 작업 재호출은 파일·기존 시각·새 작업 슬롯을 변경하지 않음 |
| 일부 파일만 확인된 상태의 오류 | 첫 파일은 실제 보관됐지만 두 번째 경계에서 실패. 연산 결과·raw·시각 보존, PENDING/outbox/슬롯 유지·다음 접수 거부. 재시도로 두 파일 확인 후 완료 |
| 손상된 기존 파일 | 같은 크기의 손상 bytes도 거부, 덮어쓰기·삭제 없음. PENDING/슬롯 유지. 시험 코드가 자기 fixture를 명시적으로 복구한 뒤 재시도 성공 |
| 실제 DB 완료 처리 오류 | 두 파일 확인 후 MariaDB trigger가 SQLSTATE 45000을 발생시켜 outbox/완료/슬롯 변경 rollback. 객체와 연산 결과 보존. trigger 제거 뒤 동일 객체 재확인으로 회복 |
| 첫 파일 확인 후 JVM 중단 | 실제 Get 확인 checkpoint와 DB PENDING/슬롯을 대조한 뒤 child 강제 종료. 새 exporter가 남은 파일과 두 파일 검증 뒤 완료 |
| 두 파일 확인 후 DB 완료 전 JVM 중단 | 실제 두 Get 확인 checkpoint와 DB PENDING/슬롯을 대조한 뒤 child 강제 종료. 새 exporter가 동일 파일을 재확인하고 DB 완료·슬롯 해제 |

강제 종료는 Windows child JVM의 atomic checkpoint를 읽은 뒤 `destroyForcibly()`로 수행하고 종료를 확인한다. 고정 sleep·예외 주입만으로 실제 kill 증거를 대신하지 않는다. 첫 파일 오류 시험의 의도적인 adapter wrapper 예외와 실제 S3/DB 오류·프로세스 종료를 구분한다. 실제 checkpoint·child log는 OS 임시 경로에 비공개로 남긴다.

## 실패와 재실행

`PENDING` 동안에는 후속 작업이 `SlotBusy`로 거부돼야 한다. `storeAndVerify` 실패를 연산 실패나 EXPORTED로 바꾸지 않는다. 객체가 일부 남는 것은 재시도 가능한 상태이며 raw·결과를 자동 삭제하지 않는다. 충돌 객체의 삭제/수정은 일반 adapter 기능이 아니라 소유가 확인된 시험 fixture의 명시적 복구다.

`completeExport`를 직접 호출해 파일 보관 성공을 꾸미지 않는다. 정상 완료는 항상 실제 coordinator를 통과해야 한다. test teardown만 자기 UUID의 raw·두 export key·DB 행·trigger를 정리하며, FK 때문에 슬롯을 해제한 다음 자기 outbox·outcome·run·job 순으로 삭제한다. 다른 작업·bucket 전체·운영 자원은 정리하지 않는다. 실패한 teardown 뒤에는 원인·소유 자원과 살아 있는 child를 확인하기 전 반복 시험을 실행하지 않는다.

## 남은 범위

운영 exporter·상시 worker Pod·public API/UI·export 관측 schema·보존 자동화는 이번 범위가 아니다. 두 파일 확인과 DB commit은 원자적 외부 트랜잭션이 아니며 확인 이후의 객체 유실·임의 외부 writer·조건부 생성·WORM·호스트/디스크 장애를 보장하지 않는다. 원본 12개 고정 시나리오를 넘어선 입력·최대 1,000개·다중 worker는 별도 확장이다.

실제 수치·실행 시각·소스 지문·임시 자원 정리와 기존 운영 보존은 [공개 근거](../evidence/result-export/README.md)에 연결한다.

실제 구현은 `jobs.exporting.ResultExportService`·`ExportBundle`·`S3ResultExportStore`다. 단일 내부 호출은 `new ResultExportService(jobs, store).export(runId, sourceSha256)`이며, 먼저 짧은 `jobs.exportSnapshot`을 읽고 DB 트랜잭션 밖에서 두 파일을 확인한다. coordinator와 S3 store 모두 ambient DB 트랜잭션을 거부한다. 각 문서는 최대 4 MiB이고 버전별 내용 hash 경로는 ADR 0007을 따른다. SDK 호출별 제한은 전체 export 제한과 다르며 EXPORTED 반복도 현재 객체를 확인한다. 현재 파일이 없는 경우 같은 DB bytes로 재저장할 수 있지만 관측한 충돌 객체는 자동 복구하지 않는다.
