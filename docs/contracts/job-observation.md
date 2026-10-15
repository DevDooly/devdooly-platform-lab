# 작업·export 관측 v1

읽기 전용 `GET /api/jobs/observation`, 성공 `kind=job-observation`, `schemaVersion=1`이다. public 실행은 false이며 POST는 405다. HTTP 응답은 no-store이고 읽기 실패/유효하지 않은 DB 상태는 고정 `job-observation-error / OBSERVATION_UNAVAILABLE`의 503이다. 원문 예외를 전달하지 않는다.

허용 필드와 browser validator는 [화면 계약](../../apps/lab-web/JOB_OBSERVATION.md), 구현은 `JobObservationService`와 `job-observation.ts`를 따른다. runtime journal·슬롯·최근 작업 최대 20개를 읽기 전용 repeatable-read snapshot에서 수집한다. BLOB은 실제 byte 길이와 선언 size/1 MiB를 먼저 확인하며 outcome 조회도 제한한다. runtime의 status/stage/failure와 job/export 상태 조합을 검증한다.

`files`는 결정적인 DB snapshot에서 만든 예상 SHA-256·크기다. EXPORTED의 `fileEvidence=VERIFIED_AT_EXPORT_COMMIT`과 `exportCompletedAt`은 exporter가 두 파일을 확인한 뒤 DB에 기록한 저장 확인 근거이며, 현재 저장소 probe가 아니다. PENDING은 `EXPECTED_FROM_DB`이고 완료 전에는 파일을 만들지 않는다. 취소된 export에는 확인 파일 정보를 표시하지 않는다.

runtime heartbeat 5분과 전체 기록 capturedAt 2시간의 경고를 구분한다. RUNNING은 마지막 DB 신호이며 현재 process 생존·Kafka/S3 가용성 보장이 아니다. client 정리 실패의 `PAUSED_OPERATOR / STOPPED / RESOURCE_CLOSE_FAILED`는 유효한 조합이다.

runtime journal은 현재 singleton 상태다. 새 RUNNING은 startedAt을 새로 기록하고 stoppedAt을 NULL로 바꾸므로 최종 HTTP 응답만으로 이전 STOPPED를 증명할 수 없다. 실제 정상 재시작에서는 기존 startedAt의 STOPPED 뒤 새 startedAt의 RUNNING·heartbeat 전진을 별도 관측하고 기존 작업/시각/파일/offset 보존을 대조했다. [실제 worker 재시작 근거](../evidence/runtime-recovery/README.md)를 연결한다. 이어서 교체 worker가 새 fixture를 처리해 전체 3개 EXPORTED 작업·파일 정보 6개를 조회했고 원래 두 작업의 HTTP 요약 전체를 보존했다. 실제 저장소 Get 검증은 관측 API 밖에서 수행했다.

전용 PVC의 [별도 격리 복원](../evidence/runtime-pvc-restore/README.md)에서는 raw 3개·export 6개의 실제 전체 GET과 Kafka record/offset을 관측 API 밖에서 대조했다. 기존 9개 inline 객체와 clone 전용 128KiB 물리 블록 canary의 복원 결과를 구분한다. canary는 새 Lab 작업이나 공개 관측 입력이 아니며 관측 계약·3개 작업/6개 파일 정보의 의미를 바꾸지 않는다.

Pages는 별도 `observations/jobs.latest.json`, container/root 화면은 same-origin API 10초 조회를 사용한다. 정적 기록은 실제 미니 PC의 HTTP 응답을 validator로 확인하고 Pages v2의 별도 artifact에서 보존한다. 실제 수동·systemd 수집/게시와 공개 JSON 일치를 확인했고, 기존 30분 timer는 enabled·active로 복구했다. 이후 원래 timer의 자동 실행·게시 2회와 서비스 완료 간격 1개(1809.371239초)를 검증했다. 두 번째 공개 기록은 교체 worker의 새 startedAt·3개 EXPORTED 작업·파일 정보 6개·빈 슬롯을 표시하며 실제 수집 원본과 전체가 같다. 장기간 반복 운영은 별도 범위다. 실패·오래된 응답은 이전 유효 기록과 capturedAt을 덮어쓰지 않는다. 격리 환경은 `ISOLATED_LAB`으로 표시하고 실제 운영 배포와 구분한다.

기존 `lab-observation v1`·`platform-observation v1`과 고정 seed 결과는 변경하지 않았다. 현재 [미니 PC 배포·게시 근거](../evidence/runtime-deployment/README.md)와 이전 [격리 검증](../evidence/continuous-runtime/README.md)을 구분한다.
