# 실행 잠금 연결 손실 뒤 다음 작업 차단

2026-10-20 14:00:19 UTC, 새 hosted Linux의 [실제 시험 39435016002](https://github.com/DevDooly/devdooly-platform-lab/actions/runs/39435016002)이 통과했습니다. MariaDB named lock을 가진 전용 연결 하나를 종료한 뒤 다음 소유권 검사에서 후속 발행·수신이 차단됐습니다. queued 작업과 원본을 보존하고 실제 자원 종료·종료 후 새 잠금 획득도 확인했습니다.

## 실제 결과와 중요한 구분

| 경계 | 관측한 결과 |
| --- | --- |
| 준비 | 합성 입력 12건을 실제 stage·raw 전체 GET으로 검증. job `QUEUED / NOT_REQUESTED`, DISPATCH `PENDING`, 슬롯 점유, 업무·EXPORT 결과 0 |
| fault 위치 | 실제 empty export가 false를 반환한 직후. 다음 PUBLISH 단계에 들어가기 전 시험 전용 barrier |
| 정확한 대상 | 실제 lease connection의 ID·계정과 별도 제어 연결의 서버·catalog·named-lock owner를 재대조. 그 소유 연결 하나만 한 번 종료하고 실제 lock 부재 확인 |
| 후속 작업 | production lease의 실제 손실 예외와 다음 단계 거부. publisher 호출 0·receiver 호출 0 |
| DB journal | fault 직전 `RUNNING / EXPORT / failureCode null`의 전체 행·시각이 그대로 보존됨. pause 저장도 소유권 검사에서 거부됨 |
| 실제 종료 | runner의 terminal을 확인하고 실제 consumer·producer·S3 client, lease·Spring context가 닫힌 뒤 child 프로세스 종료 확인 |
| 종료 후 | 이전 child가 종료한 뒤 새 실제 lease의 획득·검증·해제 성공. 새 daemon이나 업무 처리는 실행하지 않음 |
| 데이터 보존 | queued job 모든 컬럼·시각/BLOB, source/raw bytes·크기·SHA·ETag·수정 시각, DISPATCH PENDING 전체 행·policy·점유 슬롯 보존 |
| Kafka | read-committed end 0, 실제 `NO_COMMIT / null`. commit 0 또는 lag 0으로 바꾸어 표시하지 않음 |

DB의 `RUNNING`은 **종료된 프로세스가 남긴 마지막 기록**입니다. 현재 worker가 살아 있거나 정상이라는 뜻이 아닙니다. 연결을 잃은 상태에서는 pause/stop 기록도 실패할 수 있어, 존재하지 않는 `PAUSED_OPERATOR / LEASE_LOST`를 만들어 표시하지 않았습니다.

시험의 범위는 지정한 empty-export 경계 뒤 다음 단계의 호출 차단입니다. 이미 진행 중인 I/O를 원자적으로 차단하는 fencing·자동 복구·HTTP readiness·HA를 검증하지 않았습니다. Probe의 not-ready 관측은 실제 runner가 호출한 시험용 `RuntimeProgress` callback이며 live API 응답과 구분합니다.

## 원문과 고정 출처

- [실제 summary 원문](summary.json), [실행 metadata](run-metadata.json)
- source: [`dd9feb81`의 실제 IT](https://github.com/DevDooly/devdooly-platform-lab/blob/dd9feb815ead4744bf4b6c80a466095e2a4bc6ac/infra/runtime-lease-loss-ci/RuntimeLeaseLossIT.java), [Probe·실행 조건](https://github.com/DevDooly/devdooly-platform-lab/blob/dd9feb815ead4744bf4b6c80a466095e2a4bc6ac/infra/runtime-lease-loss-ci/README.ko.md)
- raw summary SHA-256: `7bf8415e9fc8ca8c3d54529865a033697923ca1468e1b2d5a02fef572b2ea370`
- source manifest SHA-256: `ca10e6c10a5c29f82348dd5126afaa218d32a1c11ac49f840913ff17d8cd8d7d`
- JUnit XML SHA-256: `4b996398184c9b20410f6c9332b1e7df9db7a271f648468cc1f7e0c26f5f0c96`

유한 summary 18필드와 `leaseLossResult` 35필드의 실제 타입·값과 출처를 대조했습니다. 지정 IT 1개·실패 0·오류 0·skip 0, source/artifact/tool/staging 불변과 소유 자원 정리도 통과했습니다. `synthetic: true`는 합성 입력을 뜻합니다.

[PR143 CI 39434809106](https://github.com/DevDooly/devdooly-platform-lab/actions/runs/39434809106)의 Python 경계 검사 31개와 fresh API108 compile-only를 먼저 통과한 뒤, 병합된 main의 첫 수동 opt-in 실행 한 번을 수행했습니다.

## 실행 범위와 공개 연결

새 Kafka·MariaDB·Garage·JVM 4개와 내부 네트워크만 사용했습니다. 동일 source/run/nonce·full ID·image·mount·network와 CPU·메모리·PID·시간 한도를 검증한 소유 자원만 정리했습니다. 기존 API106·이전 시험/Probe/manifest·미니 PC 운영 서비스·자료·PVC는 변경하지 않았습니다. 토큰 교체·예산 정책·PR102는 보류합니다.

[PR144](https://github.com/DevDooly/devdooly-platform-lab/pull/144)의 source `5a68c709546636b24ed01aa071e57ca6ace96978`에서 [Pages 39436608451](https://github.com/DevDooly/devdooly-platform-lab/actions/runs/39436608451)·[main CI 39436608366](https://github.com/DevDooly/devdooly-platform-lab/actions/runs/39436608366)를 통과했습니다. 2026-10-20 14:11–14:12 UTC에 공개 1280px·390px의 기술별 근거 목록을 확인했습니다. 전체 17항목, Java·Cloud 필터 7항목 안의 새 항목과 실제 IT·근거 링크, 본문 17px·가로 넘침 부재를 대조했습니다. 운영 worker 배포나 장애 주입은 추가하지 않았습니다.

## 별도 사례 페이지

같은 실제 기록을 읽는 [프로세스 종료와 DB 상태 사례](https://devdooly.github.io/devdooly-platform-lab/cases/runtime-ownership/)를 준비했습니다. 원 summary와 metadata는 그대로 보존했고, 별도 JSON은 실제 실행 URL·완료 시각·summary만 묶었습니다. 페이지는 고정된 18/35필드·출처·실제 타입과 값을 모두 검증한 경우에만 저장 기록을 보여줍니다. native 상세 네 개 중 세 번째가 기본으로 열리며 중간 경과 시간이나 현재 건강 상태를 만들지 않습니다.

웹186개 검사·skip0·타입·루트/프로젝트 경로 빌드와 로컬1280px·390px의 진입/새로고침·목록 왕복·상세 키보드 토글·표 초점·17px·긴 SHA 줄바꿈·가로 넘침 부재를 확인했습니다. 처음 타입 검사에서 발견한 Astro 속성명 두 곳(`datetime`, `tabindex`)을 수정한 뒤 오류0을 확인했습니다. 공개 게시·공개 QA는 아직 다음 단계입니다. 실제 장애 시험을 재실행하거나 worker를 배포하지 않았습니다.
