# 작업·export 관측 v1

읽기 전용 `GET /api/jobs/observation`, 성공 `kind=job-observation`, `schemaVersion=1`이다. public 실행은 false이며 POST는 405다. HTTP 응답은 no-store이고 읽기 실패/유효하지 않은 DB 상태는 고정 `job-observation-error / OBSERVATION_UNAVAILABLE`의 503이다. 원문 예외를 전달하지 않는다.

허용 필드와 browser validator는 [화면 계약](../../apps/lab-web/JOB_OBSERVATION.md), 구현은 `JobObservationService`와 `job-observation.ts`를 따른다. runtime journal·슬롯·최근 작업 최대 20개를 읽기 전용 repeatable-read snapshot에서 수집한다. BLOB은 실제 byte 길이와 선언 size/1 MiB를 먼저 확인하며 outcome 조회도 제한한다. runtime의 status/stage/failure와 job/export 상태 조합을 검증한다.

`files`는 결정적인 DB snapshot에서 만든 예상 SHA-256·크기다. EXPORTED의 `fileEvidence=VERIFIED_AT_EXPORT_COMMIT`과 `exportCompletedAt`은 exporter가 두 파일을 확인한 뒤 DB에 기록한 저장 확인 근거이며, 현재 저장소 probe가 아니다. PENDING은 `EXPECTED_FROM_DB`이고 완료 전에는 파일을 만들지 않는다. 취소된 export에는 확인 파일 정보를 표시하지 않는다.

runtime heartbeat 5분과 전체 기록 capturedAt 2시간의 경고를 구분한다. RUNNING은 마지막 DB 신호이며 현재 process 생존·Kafka/S3 가용성 보장이 아니다. client 정리 실패의 `PAUSED_OPERATOR / STOPPED / RESOURCE_CLOSE_FAILED`는 유효한 조합이다.

Pages는 별도 `observations/jobs.latest.json`, container/root 화면은 same-origin API 10초 조회를 사용한다. 정적 기록은 실제 HTTP 응답을 validator로 확인해 등록하며 자동 수집/게시 기능은 아직 추가하지 않았다. 실패·오래된 응답은 이전 유효 기록과 capturedAt을 덮어쓰지 않는다. 격리 환경은 `ISOLATED_LAB`으로 표시하고 실제 운영 배포와 구분한다.

기존 `lab-observation v1`·`platform-observation v1`과 고정 seed 결과는 변경하지 않았다. 실제 [검증 수치·등록 기록·화면](../evidence/continuous-runtime/README.md)을 연결한다.
