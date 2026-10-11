# API MVP 검증

2026-10-11 Windows의 Microsoft OpenJDK 21.0.9에서 Maven Wrapper 3.3.4 / Maven 3.10.0으로 실제 검증했습니다. Spring Boot는 공식 안정 버전 4.1.1을 고정했습니다.

## 통과한 결과

- `./mvnw -B -ntp verify`: 테스트 15개, 실패 0, 오류 0, 건너뜀 0, 실행 jar 생성
- 순수 처리 테스트 9개: 고정 기대 판정, 중복 ID, 잘못된 시간, UTC offset 비교, 센서별 시간 역순, 값 범위·누락·비정상 실수, 빈 입력, seed 재현
- HTTP·DB 통합 테스트 6개: 실제 랜덤 포트 Tomcat과 JPA/Flyway, 목록/상세, bootstrap 멱등, 404, POST 405, 미구성 플랫폼 상태, DB 포함 health/readiness
- 실행 jar의 `local-dev` localhost HTTP 점검: 독립 JSON 시나리오의 12개 판정과 응답을 하나씩 비교하고 성공 차트 7건 확인

기대 합계는 입력 12 = 성공 7 + 실패 3 + 중복 2 + 대기 0입니다. 실패는 INVALID_TIMESTAMP·OUT_OF_ORDER·OUT_OF_RANGE 각 1건입니다. 모든 데이터는 개인이 만든 합성 예제입니다.

[테스트 요약](test-results.json), [실제 HTTP 캡처](local-http.json), [독립 기대 결과](../../../tests/scenarios/sensor-validation-v1.json), [API 계약](../../contracts/demo-api.md)을 연결합니다. 캡처의 observedAt은 실제 조회 시각이며 처리 시각과 구분됩니다. 캡처 당시 sourceCommit은 주입하지 않아 unknown입니다.

## 재현

```sh
cd apps/api
./mvnw -B -ntp verify
./mvnw spring-boot:run -Dspring-boot.run.profiles=local-dev
curl http://127.0.0.1:8080/api/demo/runs/synthetic-v1-seed-42
```

Windows에서는 `mvnw.cmd`를 사용합니다. 기본 MariaDB 실행은 [API 안내](../../../apps/api/README.md)의 환경변수 설정을 따릅니다.

## 범위와 한계

이 기록의 DB는 H2의 test/local-dev profile입니다. MariaDB와 실제 Ubuntu·Kubernetes 배포 검증은 별도 기록으로 남깁니다. Spring Boot BOM의 H2 2.4.240에 대해 Flyway가 검증 기준 H2 2.3.232보다 새 버전이라는 경고를 출력했으며 migration과 schema validation은 통과했습니다.

동일 고정 run ID의 반복 bootstrap은 중복 데이터를 만들지 않습니다. 최초 bootstrap의 다중 인스턴스 동시 실행은 아직 지원하지 않으므로 replica 1로 시작합니다. 여러 replica로 전환하기 전 seed Job 또는 DB 잠금을 추가합니다.

Jenkins·Argo CD·Kubernetes는 연결 전이며 NOT_CONFIGURED로 반환합니다. releases는 현재 JVM 정보를 나타내며 실제 CI/CD 이력으로 표시하지 않습니다. 공개 POST, Kafka, S3, 성능 비교 수치는 이번 범위에 없습니다.

## 비루트 빌드를 위한 Wrapper 검증

공식 Maven Wrapper 3.3.4를 bin 방식으로 전환했습니다. wrapper jar의 Maven Central SHA1을 대조하고 SHA256을 별도로 고정했으며 Maven ZIP은 공식 SHA512 대조 후 SHA256을 고정했습니다. 새 MAVEN_USER_HOME 캐시에서 Java wrapper가 Maven 3.10.0을 다운로드·압축 해제하고 실행하는 것을 확인했습니다.

전환 후 전체 verify에서 15개 테스트가 통과했습니다. 첫 회귀 패키징은 실행 중이던 이 작업의 Windows local-dev jar 잠금으로 rename이 실패했으며, 해당 프로세스만 종료한 뒤 다시 실행해 jar 패키징까지 성공했습니다. 이는 Jenkins 실행 결과가 아니며 Jenkins agent 기동 검증은 별도 단계입니다.
