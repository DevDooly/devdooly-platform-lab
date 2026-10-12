# DB 작업·outbox 기반 격리 검증

2026-10-12 KST. Kafka·객체 저장소를 연결하기 전, 작업·원본·결과·outbox를 MariaDB 트랜잭션으로 관리하는 내부 Java 서비스를 구현했다. **운영 image pin과 운영 DB는 갱신하지 않았다.** 공개 화면의 기존 12건 결과와 GET 계약은 유지한다.

[실행 요약](summary.json) · [재실행 절차와 신뢰 경계](../../runbooks/db-job-foundation.md) · [4단계 계획](../../plans/phase4-messaging-storage.md)

## 검증한 결과

| 조건 | 실제 결과 |
| --- | --- |
| Java 21 기본 verify, JVM Asia/Seoul | 35개 통과, 실패·오류·건너뜀 0, JAR 생성 |
| 기존 production image로 V1 seed를 만든 격리 MariaDB → V2 | 실제 MariaDB 시험 17개 통과 |
| 빈 격리 MariaDB → V1+V2 | 같은 17개 통과 |
| 이미 V2가 적용된 DB에서 다시 시작 | 같은 17개 통과, V1·V2 이력과 singleton 슬롯 중복 없음 |
| 이전 production image를 V2 DB에서 다시 시작 | 앱·Flyway 시작, 기존 seed GET, POST 405 통과 |
| 운영 보존 비교 | 전체 SQL·Flyway·저장 시각, 2개 PVC UID·바인딩, DB Pod 이미지·mount, 실행 중인 Docker 23개의 ID·시작 시각·mount 유지 |
| 임시 시험 자원 정리 | 시험용 container 2개·network·volume만 제거, 기존 Docker 전체 35개 ID 유지 |

17개 MariaDB 시험을 세 조건에서 각각 실행했다. 서로 다른 51개 시험이라는 뜻은 아니다. 이미지와 실제 DB 버전, LF 기준 검증 소스의 SHA-256은 요약에 남겼다. H2 시험과 실제 MariaDB 시험을 구분한다. SQL 원문·개별 연결 주소·자격증명·실행 로그는 공개하지 않는다.

## DB 경계

- 같은 run·같은 원본 재요청은 같은 작업을 반환하고, 다른 원본 hash와 기존 seed ID는 거부한다. 원본 NDJSON byte·잘못된 시각·업무 중복 ID를 보존한다.
- 별도 connection의 동시 제출에서 전체 슬롯은 하나만 점유한다. 같은 run의 동시 요청·동시 완료는 결과와 export intent를 한 번만 저장한다.
- source verification 상태와 dispatch intent를 함께 저장한다. 완료 처리의 JPA 결과·12개 outcomes·JDBC job 상태·export intent도 하나의 트랜잭션이다. 트랜잭션 내부 예외에서 부분 결과가 남지 않았고 재시도는 정상 완료했다.
- 완료 재전달에서 전체 결과·처리 시각이 바뀌지 않는다. 업무상 중복 2건은 작업 재전달 억제와 다른 값이다. 고정 기대 결과는 입력 12 = 성공 7 + 실패 3 + 중복 2 + 대기 0이다.
- export pending 동안 슬롯을 보유한다. 내부 완료 확인 또는 명시적 종료 뒤에만 해제하며 종료를 export 성공으로 표시하지 않는다.

수정 전 비UTC JVM에서 JDBC와 JPA의 DB 완료 시각이 달라지는 문제를 H2 SQL 비교로 재현했다. JDBC Timestamp bind/read에 UTC Calendar를 명시했고, 수정 후 서비스 Instant와 DB 두 완료 시각의 일치를 H2 및 실제 MariaDB의 Asia/Seoul JVM에서 확인했다.

기존 V1 image가 생성한 seed의 전체 run·12개 outcome·자동 ID·마이크로초 시각과 V1 migration 행을 V2 후에도 비교했다. 시험 후 두 DB 모두 성공 이력 V1·V2 각 1개, 빈 singleton 슬롯 1개, 테스트 job·outbox 0개, 기존 seed 1개·outcome 12개였다.

## 검증 범위의 한계

현재는 내부 Java 메서드만 있으며 공개 job API·관리자 CLI·worker·스케줄러는 없다. `markSourceVerified`, `acknowledgeDispatch`, `completeExport`는 미래 adapter가 외부 성공을 검증한 뒤 호출할 계약이다. 이번 시험의 호출은 DB 상태 전이를 검증했으며 S3 파일 저장·Kafka 발행 ACK·offset commit·결과 export를 증명하지 않는다.

단일 작업 슬롯과 작은 고정 12개 입력을 검증했다. 성능·대용량·고가용성·전체 처리 exactly-once를 검증한 결과가 아니다. 운영 비교의 `restored-a` phase 표기는 기존 읽기 전용 비교 도구의 분류다. 이번에는 운영 배포·롤백을 실행하지 않고 같은 기존 image를 전후 비교했다.

시험용 앱의 첫 host port readiness 조회는 실패했다. 앱·Flyway는 정상 시작한 상태였으며, 격리 Docker network의 내부 주소로 호스트에서 확인하고 SSH forwarding으로 DB 시험을 진행했다. 첫 반복 시작 시험 중 SSH 연결 reset으로 17개 중 11개가 오류로 끝났다. 이 실행은 실패로 보존했고 연결 복구 후 같은 DB의 17개를 다시 실행해 통과했다. 이전 image 호환성의 첫 API 비교는 매 요청 달라지는 `observedAt`까지 동일하다고 가정해 실패했다. 차이가 그 필드 하나임을 확인하고, 이 관측 시각만 제외한 모든 API 필드와 전체 seed SQL을 비교해 통과했다. 기존 서비스·프록시·방화벽은 변경하지 않았다. 임시 자원은 정리했고 비공개 진단 기록은 보존했다.

다음은 Garage의 Java S3 SDK 호환성을 검증해 저장소를 선정하고, 원본 저장·hash 확인 adapter와 Kafka 발행·수신·offset 경계를 연결하는 작업이다. 새 V2 DDL은 image rollback으로 자동 취소되지 않으므로 운영 반영 전 백업·스키마 복구 범위를 다시 확인한다.
