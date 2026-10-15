# 0010 버전이 명시된 제한 크기 합성 입력

날짜: 2026-10-15

상태: 구현·기본 검증 140개·실제 격리 기능 IT 5개 통과. 검증 소스는 [`5a1495be4973d43b34dc5c169dbf66bec7459968`](https://github.com/DevDooly/devdooly-platform-lab/commit/5a1495be4973d43b34dc5c169dbf66bec7459968)이다. 이 기능 IT를 Linux worker의 자원 측정이나 운영 배포 결과로 해석하지 않는다.

## 결정

기존 `sensor-validation-v1`의 순서가 고정된 12건을 유지하고, 별도 `sensor-validation-v2`의 고정 합성 입력 1,000건을 추가한다. V2는 독립적인 센서 100개에 각 10건을 배치하며 기대 결과는 성공 500·실패 300·중복 200·대기 0이다. 임의 입력이나 임의 건수를 받는 범용 처리 API로 확장하지 않는다.

| 경계 | 제한과 의미 |
| --- | --- |
| 시나리오 | `sensor-validation-v1`과 `sensor-validation-v2`만 허용. 각각 정확히 12건과 1,000건의 공개 합성 내용·순서 |
| 원본 | UTF-8 NDJSON 전체 1 MiB(1,048,576 bytes) 이하. 각 JSON은 지정된 필드 4개만 허용 |
| Kafka | 원본을 담지 않는 버전·run ID·SHA-256 포인터. 기존 1,024-byte envelope 상한 유지 |
| 결과 | 결과·실패 JSON 각각 최대 4 MiB(4,194,304 bytes). 문서 schema와 파일 이름의 버전은 계속 v1 |
| 실행 슬롯 | 전체 진행 작업 1개. 원본 확인·처리·두 export 파일 저장 확인이 끝날 때까지 보유 |

`CanonicalSource.validate(scenarioVersion, bytes)`가 버전을 명시적으로 검증하고, 동일한 버전이 DB 작업·S3 원본 확인·Kafka 메시지·처리·export에 이어진다. 알 수 없는 버전, 잘못된 내용·순서, 1,001건, 1 MiB 초과는 DB 접수와 외부 원본 저장 전에 거부한다. 표현상 공백이나 LF/CRLF 차이를 정규화하지 않으므로 실제 bytes가 다르면 SHA-256도 다르다.

V2 이벤트 목록은 변경할 수 없는 목록으로 재사용한다. export 반복문이 매 입력마다 전체 시나리오를 다시 생성하지 않는다. export snapshot은 원본 BLOB을 읽기 전에 실제 `OCTET_LENGTH`와 저장된 크기를 대조하고, outcome 조회를 1,001개로 제한한다. 기대 개수와 다르면 실패하므로 초과 행을 1,000개로 잘라 성공으로 표시하지 않는다.

## 기본 동작과 호환성

인자가 없는 기존 `CanonicalSource.validate(bytes)`·`fixtureBytes()`와 기본 seed bootstrap은 계속 V1을 사용한다. V1 원본 bytes/SHA와 고정 시각의 export bytes/SHA·key는 변경 전 지문을 비교하는 기본 테스트로 유지한다.

내부 `--lab-runtime=stage`는 `LAB_RUNTIME_STAGE_SCENARIO`가 없으면 V1, 정확히 `sensor-validation-v2`이면 V2를 접수한다. 빈 값·그 밖의 버전·파일 경로·URL·건수는 받지 않는다. worker 실행과 API 시작만으로 V2 작업이 생성되지 않는다. 공개 실행 POST와 HTTP 관리자 명령도 추가하지 않는다.

**V2 최초 접수 전에 API와 worker 모두 이 버전을 이해하는 검증된 image로 갱신해야 한다.** V1 보존은 이전 코드가 V2를 처리한다는 뜻이 아니다. 이전 worker는 V2 envelope를 거부하고, 이전 API는 V2 완료 작업의 export 관측을 처리하지 못한다. 배포 후 V2 작업이 있으면 이전 image로 되돌리기 전에 작업·원본·outbox·파일·offset과 조회 호환성을 별도로 확인한다. 데이터나 Flyway 이력을 지워 rollback하지 않는다.

## 동시 접수와 재요청의 의미

서로 다른 run ID의 동시 접수는 기존 MariaDB 슬롯 행 잠금으로 직렬화한다. 슬롯이 계속 점유된 조건에서 실제 2개·8개 호출 중 각 1개가 접수됐고 나머지 1개·7개는 `SlotBusyException`으로 거부됐다. 거부된 run의 DB 작업·outbox·S3 원본은 생성되지 않았다. 테스트 barrier는 DB connection을 얻기 전, 승자 대기는 접수 트랜잭션이 끝난 뒤 외부 저장 경계에 두었다.

이것은 한 슬롯의 동시 접수 제어이며 요청률 제한기가 아니다. 작업이 완료돼 슬롯이 풀린 뒤의 다음 요청은 접수할 수 있다. 초당 요청 제한·HTTP rate limit·다중 worker 처리량·과부하 용량·SLA를 검증한 결과로 확대하지 않는다.

같은 run·같은 원본의 순차 재요청은 기존 작업과 시각을 보존한다. 다른 원본이나 이미 관측된 손상 객체는 충돌로 거부하며 자동 덮어쓰기를 하지 않는다. 완료된 이전 작업의 재요청·export 확인이 다음 작업의 슬롯을 풀지 않는지도 실제 검증했다. S3 adapter는 조건부 생성이나 WORM 저장소가 아니며, 동일 작업의 정당한 동시 재시도에서 같은 bytes의 PUT이 한 번만 발생한다고 보장하지 않는다.

## 확인한 근거와 남은 범위

Windows Java 21·Asia/Seoul의 테스트 드라이버와 Linux Docker의 전용 MariaDB 11.8.9·Kafka 4.3.1·Garage 2.4.1을 연결해 실제 프로세스·DB·broker·S3 경계를 검증했다. 동일 daemon에서 V1 1회와 정확히 1 MiB인 V2 3회를 처리해 outcome 3,012개·export 파일 8개·Kafka committed/log end 4/4·빈 슬롯을 확인했다. 원본과 export는 전체 GET bytes·크기·SHA-256을 대조했다.

기능 IT 5개는 최대 입력 세 번 처리, 2개·8개 동시 접수, 크기/건수/버전 불일치 거부, 재요청·충돌·후속 슬롯 보존으로 구성된다. Linux에서 동일 자원 제한을 적용한 실행과 실제 운영 서비스 보존은 별도 후속 근거로 기록한다. 이 문서에는 미실행 성능 수치나 운영 반영 성공을 넣지 않는다.

[재현 절차](../runbooks/maximum-input-concurrency.md) · [후속 실행 근거](../evidence/input-concurrency-load/README.md) · [기존 상시 실행 결정](0008-continuous-runtime-observation.md) · [운영 배포 결정](0009-mini-pc-runtime-deployment.md)
