# 승인 간격 V4의 실제 배포

2026-10-15 기준 **API·웹 32/32, worker 35/35로 실제 전환을 검증했습니다. 고정 fixture 접수와 공개 Pages 반영은 아직 대기**입니다. 실제 배포 소스는 `202ab6806130cfb37e8829ce7d52c89990d8a54a`이며 기능 구현 소스 `9926bd2f714954bcd8d43fa9c5333e503958fd92`와 구분합니다. 이전 [격리 승인 간격 시험](../admission-cooldown/README.md)은 당시 조건을 그대로 보존합니다.

## 게시와 이미지 확인

같은 source SHA의 [Actions 검증](https://github.com/DevDooly/devdooly-platform-lab/actions/runs/38725378928)과 Jenkins build 31이 성공했습니다. Jenkins의 실제 JUnit 157개는 실패·skip 0이며 필수 JAR·웹·source metadata archive를 대조했습니다. 이어 [게시 workflow](https://github.com/DevDooly/devdooly-platform-lab/actions/runs/38726033912)의 gate·publish·draft PR 제안이 모두 성공했습니다.

| 이미지 | immutable index digest |
| --- | --- |
| API·worker | `sha256:209770d4a2ea0f9cab57f7a630ca097d45eb158efaae58f98768b1770fe7880f` |
| 웹 | `sha256:e7403272cdfaa25bd92930346abd18084a9001ad9d123436be9379b55b8fae52` |

익명 registry 조회와 K3s cache에서 index→linux/amd64 manifest→config→CRI를 실제 대조했습니다. config의 revision label도 source SHA와 일치했습니다. prefetch 4/4와 그 전후 보존 검사 각 19/19를 통과했으며 이 단계에서 Pod를 시작하거나 교체하지 않았습니다. 기존 Docker 38개와 별도 검증 후 정상 종료한 정확한 5개 컨테이너를 구분해 보존했습니다.

## API·웹 전환에서 확인한 범위

[PR #34](https://github.com/DevDooly/devdooly-platform-lab/pull/34)를 `36f00136d9851e52502d9edca261c95e1c3c01cc`로 반영한 뒤 Argo CD와 실제 OCI/CRI·DB·HTTP를 대조해 **32/32**를 통과했습니다. V4 migration과 아직 사용하지 않은 30초 승인 정책 행만 추가됐고, 기존 V1~V3 history·업무 행·7개 작업·export 정보 14개·Kafka offset 7/lag 0을 보존했습니다. 이 중간 단계의 worker는 이전 source `6c5aff94`로 계속 실행했습니다.

원본 Pod/PVC/Docker·방화벽·호스트·timer 설정과 기존 seed 결과도 검사했습니다. 이 observer는 새 작업을 접수하거나 객체에 쓰지 않았고, S3 전체 GET도 다시 수행하지 않았습니다. 앞선 21개 객체의 전체 GET·외부 암호화 checkpoint와 이번 OCI/DB/HTTP 보존 검증의 범위를 구분합니다.

## worker 전환과 첫 관측 시점

[PR #35](https://github.com/DevDooly/devdooly-platform-lab/pull/35)를 `05bd61a1fdfaa9be4cee4d7f6d97022b55c4facd`로 반영했습니다. 첫 observer는 새 Pod가 Ready가 된 직후, 새 JVM의 runtime 초기화 전 구간을 읽어 **32/35**였습니다. 당시 DB journal은 이전 worker의 `STOPPED`를 표시했습니다. 이후 읽기 전용 확인에서는 새 source의 `RUNNING`·전진하는 heartbeat·restartCount 0을 확인했습니다. 첫 실패 기록을 보존한 두 번째 전체 observer는 `2026-10-15T11:39:57.213644Z`에 **35/35**를 통과했습니다. 같은 새 process의 시작 시각은 `2026-10-15T11:36:31.023476Z`이며 기존 7개 작업·파일 정보 14개와 원본 서비스를 보존했습니다.

현재 worker chart에는 runtime 상태를 확인하는 startup/readiness probe가 없습니다. 따라서 Kubernetes Ready만으로 runtime 준비 완료를 주장하지 않습니다. 이번 관측 시점 차이를 작업 처리 기능 실패나 readiness 수정 완료로 표시하지도 않습니다. 이전 컨테이너 종료 보충 확인은 `2026-10-15T11:47:53.619821Z`에 **UNOBSERVED**였습니다. 정상 종료를 확인할 수 있는 CRI exit code가 없어 exit 0/143·TERM을 추정하지 않습니다. 이는 새 worker의 전체 전환 검증과 구분합니다.

**남은 검증:** V4의 고정 fixture 접수/거부·후속 슬롯 해제와 기존 데이터 보존, 마지막 실제 관측의 공개 Pages 반영. 이전 컨테이너 종료는 미관측으로 보존하고 준비 상태 probe 구현은 별도 후속으로 남깁니다. 공개 POST는 계속 제공하지 않습니다. 새 내부 승인 간격은 단일 슬롯을 대체하지 않으며 고가용성·공개 rate limiter·운영 SLA를 검증한 결과도 아닙니다.

[공개 요약](summary.json), [내부 실행 절차](../../runbooks/continuous-runtime.md), [승인 간격의 격리 검증](../admission-cooldown/README.md)을 함께 확인합니다.
