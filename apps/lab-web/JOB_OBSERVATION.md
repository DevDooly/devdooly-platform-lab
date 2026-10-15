# 작업·export 공개 관측 v1

`GET /api/jobs/observation`은 DB에 commit된 실행기·작업·export 기록을 읽는다. 공개 작업 생성·중지·재개 API는 없다. 기존 `lab-observation`·`platform-observation` v1과 별도 계약이다.

## 수집 범위

- 단일 `lab_runtime` journal의 상태·마지막 단계·고정 오류 코드·시작/heartbeat/종료 시각·실행기 소스 SHA.
- 단일 실행 슬롯의 점유 run ID.
- 생성 시각 역순, 같은 시각이면 run ID 역순의 최근 작업 최대 20개. 작업과 export 상태, 처리 건수, DB 시각.
- 완료 작업의 결정적 DB snapshot으로 다시 계산한 두 파일의 예상 SHA-256·크기. JSON 내용·원본 입력·object key·bucket·저장소 URL·호스트·자격증명·raw 오류는 공개하지 않는다.

하나의 짧은 read-only repeatable-read transaction에서 SQL을 실행한다. `FOR UPDATE`나 외부 Kafka/S3 호출을 하지 않는다. 완료 작업의 source bytes와 outcome은 내부에서 결정적 파일을 재구성하고 검증하는 데만 사용한다. DB snapshot 또는 정해진 값의 무결성을 확인할 수 없으면 HTTP 503의 고정 `OBSERVATION_UNAVAILABLE` 오류만 반환한다. 새 성공 시각을 만들거나 불완전한 파일 정보를 게시하지 않는다.

## 상태의 의미

| 값 | 화면에서 읽는 의미 |
| --- | --- |
| `STAGING` / `QUEUED` | 원본 준비 / 처리 대기. 아직 완료 파일 정보 없음 |
| `COMPLETED` + `PENDING` | DB 처리 완료. 슬롯 유지. 두 파일 hash·크기는 **DB로 만든 예상값** |
| `COMPLETED` + `EXPORTED` | export coordinator가 저장 확인 후 commit한 기록. `exportCompletedAt`은 그 DB 시각 |
| `COMPLETED` + `CANCELLED` | 운영자가 명시적으로 종료. 검증 완료 파일로 표시하지 않음 |
| `VERIFIED_AT_EXPORT_COMMIT` | 저장 확인을 기록한 DB marker와 예상 파일 정보를 함께 표시. 현재 저장소 재조회 결과가 아님 |
| `NOT_STARTED` | journal에 아직 실행 시작 기록 없음. 기본 API는 Kafka/S3 실행기를 만들지 않음 |
| `RUNNING` | 마지막 DB signal. 현재 프로세스 생존을 직접 확인한 값이 아님 |
| `PAUSED_OPERATOR` | 고정 오류 기록 후 영속 정지. 원인 확인과 내부 명시적 재개 필요 |

`RUNNING`의 heartbeat가 확인 시각보다 5분 초과 오래되면 `stale` 경고를 붙인다. 5분은 운영 보장이나 장애 판정 시간이 아니라 오래된 신호를 구분하는 UI 기준이다. 브라우저도 현재 시각으로 다시 계산하므로, 예전 기록의 `RUNNING`을 계속 정상으로 표시하지 않는다. 기록 시각이 브라우저보다 미래면 시각 확인 안내를 표시한다. DB 확인 후 2시간 경과도 별도 경고다.

## API와 GitHub Pages

- 로컬·컨테이너의 기본 경로 `/`에서는 같은 origin의 `/api/jobs/observation`을 10초마다 조회한다. 다시 읽기 버튼도 제공한다.
- Pages의 `/devdooly-platform-lab/`에서는 `observations/jobs.latest.json`을 읽는다. 현재 공개 기록은 **실제 미니 PC K3s 배포 API의 HTTP 응답**을 검증해 outbound 게시한 `MINI_PC / DEPLOYED_RUNTIME` 관측이다. 공개 JSON 전체가 실제 수집 원본과 일치함을 확인했다. 이전 격리 seed는 자동 게시 입력으로 사용하지 않는다. 파일이 없으면 `NOT_CONFIGURED`·미관측으로 표시하며 샘플 성공 파일을 생성하지 않는다.
- 기록은 `capturedAt`, `environment`, `scope`, 관측 API·실행기 각각의 `sourceCommit`을 보존한다. `ISOLATED_LAB`은 운영 상시 배포와 구분해서 표시한다. 정적 파일 다시 읽기는 새 서버 수집을 실행하지 않는다.
- HTTP·네트워크·시간 초과·형식 실패 때 이전 유효 기록과 시각을 유지한다. 더 오래된 응답도 기존 기록을 덮어쓰지 않는다. 기록의 실패 상태와 브라우저 조회 실패를 구분한다.

브라우저의 `job-observation.ts` validator는 모든 객체 경계를 allowlist로 닫고 상태·오류 코드·시간·hash·크기·건수·작업 수·환경/범위 조합과 export 상태의 관계를 검증한다. 요청에는 인증 정보·cookie를 보내지 않는다. 기존 두 관측 계약은 유지하며 host cycle은 job 기록을 별도 허용 입력으로 함께 게시한다. Pages v2는 배포 회차별 존재 manifest와 기록 artifact에서 마지막 유효 job 기록을 복원하고, 더 오래된 입력은 반영하지 않고 동일 시각 충돌·누락된 예상 artifact는 게시를 차단한다. 새 job의 원래 timer 자동 수집·Pages 게시 2회와 공개 JSON 전체의 원본 일치를 확인했다. 완료 간격은 1개·1809.371239초였으며 [후속 검증 근거](../../docs/evidence/runtime-recovery/README.md)는 기존 플랫폼 collector 11회와 구분한다. 장기간 반복 운영은 후속이다.

전용 PVC의 [격리 복원 근거](../../docs/evidence/runtime-pvc-restore/README.md)는 이 화면의 저장소 probe 기능이 아니다. raw 3개·export 6개의 GET과 clone 전용 128KiB data 블록 복원을 별도 관리 시험에서 확인했다. clone canary나 복원 namespace를 공개 job 수집 입력으로 연결하지 않았으며 공개 3작업·파일 정보 6개와 계약은 그대로다.

## 최상위 형식

```text
schemaVersion: 1
kind: job-observation
capturedAt: 실제 HTTP 조회의 UTC 시각
environment: LOCAL | TEST | ISOLATED_LAB | MINI_PC | UNKNOWN
scope: LOCAL_VALIDATION | ISOLATED_LAB | DEPLOYED_RUNTIME
sourceCommit: 40자리 소문자 SHA 또는 unknown
synthetic: true
publicExecutionEnabled: false
runtime: status, stage, failureCode, startedAt, heartbeatAt, stoppedAt, sourceCommit, stale
slot: occupiedRunId
jobs: 최대 20개의 공개 작업 요약
```

현재 [K3s 배포·두 작업·파일 확인·공개 게시 근거](../../docs/evidence/runtime-deployment/README.md)와 이전 [격리 실행기·중단·복구 근거](../../docs/evidence/continuous-runtime/README.md)를 구분한다. 실행은 [운영 절차](../../docs/runbooks/continuous-runtime.md), API는 [계약](../../docs/contracts/job-observation.md)에 연결한다. 공개 기록의 source commit은 실제 API/worker 이미지의 실행 소스이며 Pages 빌드 commit과 다를 수 있다. 실제 systemd 수집의 9자리 소수초 capturedAt도 변환 없이 공개 기록에 보존했으며 전체 JSON을 대조했다.

실제 작업 없는 worker의 정상 재시작에서는 기존 startedAt의 STOPPED와 종료 로그를 먼저 포착한 뒤, 같은 image/source의 새 RUNNING·새 startedAt·전진하는 heartbeat를 관측했다. 새 RUNNING은 stoppedAt을 NULL로 바꾸므로 최종 공개 JSON 하나로 이전 종료를 증명하지 않는다. 기존 두 작업의 전체 SQL·시각·파일 4개·Kafka offset 보존은 별도 [실제 재시작 근거](../../docs/evidence/runtime-recovery/README.md)를 따른다. 이 결과는 진행 중 작업의 강제 종료나 PVC 복원과 구분한다. 이후 교체 worker에 새 fixture를 접수해 총 3개 EXPORTED 작업·파일 정보 6개와 offset 3/lag 0을 확인했다. 새 파일 2개의 실제 저장소 Get 검증도 별도로 수행했으며 원래 두 작업의 HTTP 요약 전체는 그대로였다. 이어진 두 번째 원래 주기 Pages 게시에서도 새 worker startedAt·3개 EXPORTED 작업·파일 정보 6개·빈 슬롯과 수집 원본의 전체 일치를 확인했다. 이는 당시 공개 Pages에서 확인한 수집 회차의 범위다.

수집은 약 30분 주기로 구성한다. 이 주기보다 짧은 heartbeat 5분 경고 때문에 다음 수집 전에는 공개 기록에 오래된 실행 신호가 표시될 수 있다. 이는 마지막 DB 신호의 나이이며 현재 프로세스 중단이나 Kafka/S3 장애를 직접 확인한 값이 아니다. 새로고침도 정적 파일을 다시 읽는 동작이고 서버 수집을 실행하지 않는다. 공개 POST·작업 제어는 제공하지 않으며 내부 stage 명령의 고정 12개 fixture만 허용한다. 단일 노드·partition 1/RF1이며 장기간 운영·고가용성은 검증하지 않았다. 전용 PVC의 격리 복원은 별도 운영 근거로 기록한다.
