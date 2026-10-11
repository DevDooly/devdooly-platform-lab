# Lab 조회 API v1

합성 센서 데이터의 실제 처리 결과를 조회한다. 공개 실행 POST는 제공하지 않는다. 시각은 UTC ISO-8601 문자열이며 observedAt은 조회 시각, startedAt/completedAt은 저장된 처리 시각이다.

## GET /api/demo/runs

```json
{"items":[{"id":"synthetic-v1-seed-42","name":"합성 센서 품질 검증","status":"COMPLETED","synthetic":true,"seed":42,"inputCount":12,"successCount":7,"failureCount":3,"duplicateCount":2,"pendingCount":0,"startedAt":"2026-10-11T00:00:00Z","completedAt":"2026-10-11T00:00:00Z"}],"observedAt":"2026-10-11T00:01:00Z"}
```

최근 시작 순으로 최대 20건. 입력 건수 = 성공 + 실패 + 중복 + 대기. 실제 시작/종료 시각은 최초 DB bootstrap 시각이다.

## GET /api/demo/runs/{id}

목록의 run 필드에 아래 필드를 추가한다. 없는 ID는 404.

```json
{"id":"synthetic-v1-seed-42","name":"합성 센서 품질 검증","status":"COMPLETED","synthetic":true,"seed":42,"inputCount":12,"successCount":7,"failureCount":3,"duplicateCount":2,"pendingCount":0,"startedAt":"2026-10-11T00:00:00Z","completedAt":"2026-10-11T00:00:00Z","observedAt":"2026-10-11T00:01:00Z","scenario":"sensor-validation-v1","description":"회사 데이터와 무관한 고정 seed 합성 데이터. 중복 ID, 잘못된 시간, 시간 역순, 범위 오류를 검증합니다.","outcomes":[{"sequence":1,"eventId":"evt-001","sensorId":"sensor-a","eventTime":"2026-01-01T00:00:00Z","value":21.0,"status":"SUCCESS","reason":"ACCEPTED"}],"series":[{"eventTime":"2026-01-01T00:00:00Z","sensorId":"sensor-a","value":21.0}],"failureReasons":[{"reason":"INVALID_TIMESTAMP","count":1},{"reason":"OUT_OF_ORDER","count":1},{"reason":"OUT_OF_RANGE","count":1}]}
```

outcomes는 입력 순서 12건, series는 성공한 7건의 차트 입력이다. 실패 eventTime에는 원본 문자열이 보존될 수 있으므로 파싱 전에 status를 확인한다. 잘못된 value는 null일 수 있다. reason은 ACCEPTED / DUPLICATE_EVENT_ID / INVALID_TIMESTAMP / OUT_OF_ORDER / OUT_OF_RANGE / INVALID_INPUT. 빈 eventId·sensorId, 누락 value는 INVALID_INPUT. 중복 판정은 구조 검증 후, 시간·범위 검증 전에 수행하며 최초 등장 ID를 처리 시도한 이후 동일 ID를 중복으로 간주한다. 센서별 마지막 성공 시각보다 과거인 입력은 OUT_OF_ORDER. 동일 시각은 허용한다.

## GET /api/platform/summary

```json
{"service":"devdooly-platform-lab-api","status":"UP","environment":"local","sourceCommit":"unknown","synthetic":true,"publicExecutionEnabled":false,"components":[{"name":"API","status":"RUNNING","detail":"Spring Boot 조회 API"},{"name":"DATABASE","status":"RUNNING","detail":"MariaDB"},{"name":"JENKINS","status":"NOT_CONFIGURED","detail":"실제 CI 연결 전"},{"name":"ARGO_CD","status":"NOT_CONFIGURED","detail":"실제 CD 연결 전"},{"name":"KUBERNETES","status":"NOT_CONFIGURED","detail":"서버 구성 전"},{"name":"KAFKA","status":"PLANNED","detail":"4단계"},{"name":"S3","status":"PLANNED","detail":"4단계"}],"observedAt":"2026-10-11T00:01:00Z"}
```

DATABASE 상태는 실제 SELECT 1 점검에 따라 RUNNING/UNAVAILABLE. H2 local-dev/test일 때 detail은 H2 (local validation only). sourceCommit은 SOURCE_COMMIT 환경변수로 주입하며 미설정은 unknown. 구성되지 않은 도구를 정상 배포로 표시하지 않는다.

## GET /api/platform/releases

```json
{"items":[{"service":"api","version":"0.1.0","sourceCommit":"unknown","imageDigest":null,"deploymentStatus":"LOCAL_RUNTIME","startedAt":"2026-10-11T00:00:00Z"}],"observedAt":"2026-10-11T00:01:00Z"}
```

현재 JVM 런타임의 정보이며 배포 이력을 가장하지 않는다. SOURCE_COMMIT, IMAGE_DIGEST, LAB_ENVIRONMENT 환경변수 주입 가능. 실배포 증거 수집 연결 전 Jenkins·Argo 상태는 NOT_CONFIGURED로 유지한다.

## 오류와 health

- GET /actuator/health → {"status":"UP"}, DB 장애는 DOWN 및 HTTP 503.
- 없는 run → HTTP 404, {"code":"RUN_NOT_FOUND","message":"요청한 실행 결과가 없습니다.","observedAt":"..."}.
- POST /api/demo/runs → HTTP 405. 실행 API 없음.
- 관리 토큰, 원본 관리자 응답, 서버 주소는 반환하지 않는다.

## 시나리오 기대 결과

고정 seed 42, 입력 12건: SUCCESS 7, FAILED 3, DUPLICATE 2, PENDING 0. 실패는 INVALID_TIMESTAMP, OUT_OF_ORDER, OUT_OF_RANGE 각 1건. 시나리오와 기대 결과는 tests/scenarios/sensor-validation-v1.json에 독립 정의한다. bootstrap은 고정 run ID를 한 번만 기록하고 재기동으로 중복 실행을 만들지 않는다.
