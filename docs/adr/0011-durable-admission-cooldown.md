# ADR 0011: 새 작업의 승인 간격을 DB에 보관

상태: 구현·격리 검증과 외부 SQL 복원본의 이전 binary 호환 확인, 운영 V4 배포 전

## 문제

단일 실행 슬롯은 동시에 두 작업이 들어오는 것을 막지만, 빠르게 끝난 뒤 연속 접수하는 빈도는 제한하지 않습니다. 프로세스 안의 timer만 사용하면 재시작·복수 CLI에서 제한이 사라질 수 있습니다. 공개 실행 API는 아직 제공하지 않지만 내부 접수 경계부터 최소 승인 간격을 명시합니다.

## 결정

Flyway V4는 `lab_admission_policy` singleton에 기본 30초의 `cooldown_seconds`, 마지막 승인·다음 승인 시각을 보관합니다. 설정 범위는 1~3,600초입니다. JVM Clock·환경변수로 승인 시각을 우회하지 않습니다.

`prepareSource`는 입력 검증 후 기존 transaction에서 slot → 기존 run → policy 순서로 lock합니다. 같은 run·같은 원본은 기존 작업을 돌려주고, 원본 충돌과 다른 run의 slot busy는 새 승인을 소비하지 않습니다. 새 run만 policy lock을 받은 뒤 **별도 SQL statement의 DB CURRENT_TIMESTAMP(6)**로 적격 여부를 판단하고 gate·STAGING 행·slot을 함께 commit합니다. DB 실패는 모두 rollback합니다. S3 I/O는 이 commit 뒤에 수행합니다.

S3 실패 후에는 이미 승인된 STAGING 작업을 유지하며 같은 ID로만 재시도합니다. export·terminate는 슬롯을 해제하되 다음 승인 시각을 초기화하지 않습니다. 설정 변경은 이후 승인에서 계산하는 다음 시각에 적용하며 이미 저장한 대기 시각을 앞당기지 않습니다. 거부는 `ADMISSION_COOLDOWN`으로 알리고 자동 sleep·새 ID 재접수를 하지 않습니다.

## 결과와 제약

이 기능은 서로 다른 새 작업의 **승인 간격**을 제한합니다. 조회 HTTP QPS, 잘못된 입력의 호출 빈도, 같은 작업의 재시도 요청량까지 제한하지 않습니다. 공개 실행을 도입하면 인증·본문 크기·진입 요청 빈도를 별도로 설계해야 합니다.

V1~V3 migration·원본 bytes·export schema는 바꾸지 않습니다. API가 V4를 적용하고 새 run/resume/stage는 V4 이력을 요구합니다. 이전 stage binary는 정책을 모르므로 혼용하면 제한을 우회합니다. 이미지 원복 중에는 새 접수를 동결하고 policy·자료를 보존해야 합니다. additive migration만으로 구형 writer까지 DB 차원에서 차단된다고 주장하지 않습니다.

기본 157개·실제 MariaDB/Garage 19개와 별도로, 인증된 외부 archive의 V3 SQL을 새 schema에 복원해 candidate API의 V4 migration·이전 실제 5a JAR API의 7개 작업 HTTP 조회·idle worker의 heartbeat/정상 종료를 확인했습니다. 이전 5a JAR은 운영 6c와 main source·build POM이 동일하지만 6c OCI 이미지 자체를 실행한 시험은 아닙니다. 호환 성공은 구형 stage의 정책 우회 위험을 제거하지 않으며, 전체 새 RuntimeMain의 충전된 cooldown 재시작 증거로 확대하지 않습니다. 운영 schema는 아직 V3입니다.

[검증 근거](../evidence/admission-cooldown/README.md), [운영 절차](../runbooks/admission-cooldown.md)를 따릅니다. 실제 MariaDB의 [FOR UPDATE](https://mariadb.com/docs/server/reference/sql-statements/data-manipulation/selecting-data/for-update), [CURRENT_TIMESTAMP](https://mariadb.com/docs/server/reference/sql-functions/date-time-functions/now) 동작을 기준으로 lock 대기 이후의 DB 시각을 검증합니다.
