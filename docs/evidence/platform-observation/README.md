# 공개 플랫폼 관측 수집 검증

2026-10-11~12 UTC, 2026-10-12 KST 실행 결과입니다. 제한된 ServiceAccount로 실제 클러스터를 읽고, Jenkins의 공개 commit status와 함께 허용 필드만 저장했습니다. **실제 수집·인증 실패 후 보존·Pages 게시·공개 브라우저와 게시 순서 보존을 검증했습니다. 전용 Pages 자격증명으로 수동 host cycle·실제 systemd service·timer 최초 자동 실행의 게시까지 기본 자동 운영 경로를 확인했습니다. timer는 enabled·active이며, 실제 30분 간격과 자격증명 만료·회전은 별도 운영 검증으로 남습니다.**

[공개 요약](summary.json), [플랫폼 관측 계약](../../../apps/lab-web/PLATFORM_OBSERVATION.md), [기존 앱 관측 계약](../../../apps/lab-web/OBSERVATION.md)을 구분합니다. 수집·게시·보존 절차는 [운영 안내](../../runbooks/platform-observation.md)를 따릅니다. 아래 기록은 실시간 서비스 상태나 전체 배포 이력이 아닙니다.

## 초기 실제 수집과 인증 실패·회복 검증

초기 검증에서 마지막으로 확인한 성공 수집의 완료 시각은 `2026-10-11T15:27:44.173356Z`입니다. 최초 성공은 `2026-10-11T15:27:43.555475Z`, 의도한 인증 실패는 `2026-10-11T15:27:43.705672Z`였으며, 아래 최종 기록은 정상 인증으로 회복한 결과입니다. 각각 실제 시도 완료 시각이며 게시 시각·현재 시각으로 바꾸지 않습니다.

| 출처 | 확인한 값과 범위 |
| --- | --- |
| main | `e823cb793308e79ea5b7b5a17af2d554b4091275` |
| Jenkins | 해당 main의 build 10, 공개 status `56090140506`, `success`; status 생성 시각 `2026-10-11T15:19:36Z` |
| Argo CD | revision `e823cb793308e79ea5b7b5a17af2d554b4091275`, `Synced`·`Healthy` |
| API·웹·DB | 각 실제 Pod 준비 수 1 / 선언 목표 수 1 |
| API 배포 선언 소스 | `820d5c398af2b1d62a0566f9184d015ab22e9f15` |
| API 선언 이미지 | `ghcr.io/devdooly/devdooly-platform-lab-api@sha256:1c114976aeb32e3fa1c2dda84a0a27db0b390c38a6bb59e8c5ada771c340bcf4` |
| 웹 선언 이미지 | `ghcr.io/devdooly/devdooly-platform-lab-web@sha256:e389ce9083b07c8b8fdeac334b13c1f1af9a0066fd541f46e7db78b5651b855a` |

Jenkins는 수집 당시 main의 최신 `ci/jenkins-test` status를 검증합니다. GitHub의 issuer·고정 description을 확인한 뒤 build 번호를 사용하며, 다른 main의 과거 성공을 현재 검증으로 대체하지 않습니다. 해당 main의 status가 없으면 `jenkins: null`입니다.

main·Jenkins 대상·Argo GitOps revision·API 배포 선언은 서로 다른 근거입니다. 이 초기 관측에서는 main과 Argo revision이 같고, API는 [이전 정상 A로 복구한 소스·digest](../cicd-gate/README.md)를 유지합니다. SHA 차이를 수집 실패로 간주하거나 하나의 최신 SHA로 덮어쓰지 않았습니다.

준비 수는 해당 component의 실제 Pod 중 삭제 중이 아니며 `Running`, `Ready=True`, 모든 컨테이너가 ready인 수입니다. 목표 수는 Deployment·StatefulSet의 선언 replicas입니다. api/web의 이미지와 API source annotation도 **Deployment template의 선언 값**입니다. 이 수집이 개별 실행 컨테이너의 imageID나 현재 JVM의 소스를 직접 검증했다는 뜻은 아닙니다.

## 권한 경계와 실패 후 보존

실제 수집 HTTP는 전용 ServiceAccount credential을 사용했습니다. 수집기에는 관리자 kubeconfig fallback이 없으며 클러스터에는 읽기 요청만 보냅니다.

| 실제 확인한 경계 | 결과 |
| --- | --- |
| 지정된 API·웹 Deployment, DB StatefulSet 읽기 | 허용 |
| Lab namespace의 Pod 목록과 지정 Argo Application 읽기 | 허용 |
| Secrets get/list, Pod logs/exec, nodes 읽기 | 거부 |
| Deployment patch | 거부 |
| 다른 namespace의 Pod 목록, 관련 없는 Argo Application 읽기 | 거부 |

RBAC의 Pod list 권한은 namespace 범위입니다. 고정 label selector는 수집기의 조회·집계 범위이며 RBAC 자체의 필드별 권한 경계로 주장하지 않습니다. 공개 출력에서는 Pod 이름·주소·관리 URL·토큰·환경 변수·원문 로그·임의 오류를 제외합니다. 구조 schema와 semantic validator가 중첩 객체의 알 수 없는 필드도 거부합니다.

의도한 인증 실패에서 `latestAttempt`만 고정 실패 코드·실제 완료 시각으로 바뀌고, 직전 `lastSuccess` **전체와 원래 capturedAt `2026-10-11T15:27:43.555475Z`가 유지**됐습니다. 올바른 인증으로 다시 수집해 `2026-10-11T15:27:44.173356Z`에 성공으로 회복되는 것도 확인했습니다. 출력 파일의 실제 POSIX 권한은 `0600`이었습니다. 초기 15:27 실패는 로컬 credential 형식 검사에서 거부된 경우이며 실제 HTTP 401 응답 검증이 아닙니다. 뒤의 15:57 실험에서는 문법적 형태만 맞는 무효 credential로 CA를 검증한 TLS 요청을 보내 실제 HTTP 401을 직접 확인했습니다. 두 실패와 API·웹 중단 실험을 구분합니다.

## Pages 수동 게시와 공개 브라우저

초기 수집 기록은 위 시각·값 그대로 보존합니다. 이후 main `c87787217e18a3d2954e61920e3b3b904706b001`에는 PR #5의 정상 B 소스 `41897dbb9d2a38537f1d06928dcd01273d64be4d`가 배포됐습니다. 초기 A 복구 검증과 현재 B 배포를 같은 결과로 덮어쓰지 않습니다.

| 실행 | 실제 확인한 범위 |
| --- | --- |
| [38152343057](https://github.com/DevDooly/devdooly-platform-lab/actions/runs/38152343057) | 새 플랫폼 관측 카드 최초 게시, workflow success |
| [38152498240](https://github.com/DevDooly/devdooly-platform-lab/actions/runs/38152498240) | 정상 관측 JSON의 수동 dispatch, workflow success. 이전 artifact 복구 검증 근거로는 사용하지 않음 |
| [38153467726](https://github.com/DevDooly/devdooly-platform-lab/actions/runs/38153467726) | 실제 HTTP 401 인증 실패 envelope의 수동 게시, workflow success |

HTTP 401 실패 게시에서는 마지막 성공 `capturedAt`이 `2026-10-11T15:57:45.192508Z`로 유지되고, 마지막 시도만 `2026-10-11T15:57:48.944192Z`·`AUTHENTICATION_FAILED`로 바뀐 것을 공개 JSON과 브라우저에서 확인했습니다. 데스크톱 폭 1280px과 모바일 폭 390px에서 카드·실패 표시를 확인했고 가로 넘침은 없었습니다. 이 인증 실패 실험은 API·웹 서비스 중단 검증과 구분합니다.

## 게시 순서 회귀 발견·교정·실제 재검증

실제 순서 역전 게시 [38154110011](https://github.com/DevDooly/devdooly-platform-lab/actions/runs/38154110011)은 workflow success였지만 공개 JSON을 초기 15:27 seed로 되돌렸습니다. 이전 게시를 찾는 코드가 API의 `run.name`을 고정 workflow 이름과 비교한 것이 원인이었습니다. `run-name`이 설정된 실행은 동적 이름을 반환해 새 버전의 성공 게시가 모두 제외됐습니다.

앞선 정상 dispatch는 seed와 값이 같아 이 결함을 드러내지 못했습니다. 따라서 그 실행을 이전 artifact 복구나 시각 후퇴 방지의 통과 근거로 사용하지 않습니다.

교정 commit [`e670837fc678e9d10ea5dec4560db644f33957ab`](https://github.com/DevDooly/devdooly-platform-lab/commit/e670837fc678e9d10ea5dec4560db644f33957ab)은 허용한 실행 이름과 고정 workflow 경로·저장소를 함께 확인하도록 수정했습니다. Pages 게시 검사 33개가 통과했고, collector·자동화·게시 검사를 합한 Windows 107개 중 105개 통과·POSIX 권한 2개 제외를 확인했습니다. 실제 GitHub API에서 이전 게시 artifact를 읽는 검증도 통과했습니다. 교정 소스의 [Lab CI 38154386379](https://github.com/DevDooly/devdooly-platform-lab/actions/runs/38154386379)와 [push Pages 38154386391](https://github.com/DevDooly/devdooly-platform-lab/actions/runs/38154386391)도 success였습니다. 이 검사 수치는 웹 UI의 26개 테스트와 별도입니다.

| 교정 후 실행 | 실제 결과 |
| --- | --- |
| [38154402207](https://github.com/DevDooly/devdooly-platform-lab/actions/runs/38154402207) | build·deploy success, 공개 브라우저의 15:57 마지막 성공·실패 시각으로 회복 확인 |
| [38154516815](https://github.com/DevDooly/devdooly-platform-lab/actions/runs/38154516815) | 고의 순서 역전 입력의 build·deploy success, 공개 브라우저와 실제 이전 artifact 재조회에서 `2026-10-11T15:57:48.944192Z` 유지 확인 |

교정 후에는 마지막 성공 `2026-10-11T15:57:45.192508Z`와 최근 실패 `2026-10-11T15:57:48.944192Z`가 함께 유지됐습니다. Workflow success만으로 판단하지 않고 공개 JSON·브라우저·정확한 이전 게시 artifact의 시각을 별도로 비교했습니다.

## API·웹 실제 중단과 동일 정상 B 복원

GitOps 중단 commit [`61d092161b078cc3beda3d12ea246eddef831fc7`](https://github.com/DevDooly/devdooly-platform-lab/commit/61d092161b078cc3beda3d12ea246eddef831fc7)에서 API·웹 replicas를 0으로 내렸습니다. Argo Synced·Healthy, API·웹 실제 Pod 0개와 DB Pod 1개를 확인했습니다. 호스트·DB·기존 Docker 전체를 중단한 실험은 아닙니다.

첫 중단 검증 도구는 16:18:09 UTC에 Endpoints의 `subsets: null` 처리 오류로 5개 검사 후 실패했습니다. 이 시도를 전체 통과로 세지 않습니다. 검증 도구의 null 처리를 고친 retry1은 `2026-10-11T16:19:17.041460Z`에 모든 검사를 통과했습니다.

- 공개 Pages 홈과 JSON은 HTTP 200이었고, 브라우저를 다시 읽어도 실패 배너와 마지막 기록을 볼 수 있었습니다.
- 마지막 성공 `2026-10-11T15:57:45.192508Z`와 마지막 실패 `2026-10-11T15:57:48.944192Z`, 이미지 pin과 과거 ready 1 기록이 유지됐습니다. 이 ready 1은 이전 수집 결과이며 중단 시점의 실제 Pod 수 0을 실시간으로 표시한 것이 아닙니다.
- DB Pod UID·전체 SQL·처리 시각·Flyway·PVC와 기존 Docker 23개의 ID·mount·시작 시각을 보존했습니다.

복원 commit [`5df664d95e051fb30cb1ca13915087d45ec9188c`](https://github.com/DevDooly/devdooly-platform-lab/commit/5df664d95e051fb30cb1ca13915087d45ec9188c) 후 `2026-10-11T16:20:20.506300Z`의 실제 runtime 검증을 통과했습니다. API·웹·DB 3개 Pod Ready, Argo Synced·Healthy, PR #5 정상 B의 동일 source `41897dbb9d2a38537f1d06928dcd01273d64be4d`와 image pin을 확인했습니다. 이번 복원은 **B 중단 → 같은 B 재가동**이며 앞 단계의 A rollback과 구분합니다.

복원 검증은 OCI index·linux/amd64 manifest·config 관계와 CRI config 일치, 합성 12건의 7/3/2/0 결과, 전체 SQL·시각·Flyway·DB Pod UID·PVC·기존 Docker 23개, host boot·node·UFW 보존을 확인했습니다. OCI·CRI 검증은 별도의 runtime 검증 도구 범위이며 읽기 전용 collector 자체가 이 검증을 수행했다고 표시하지 않습니다.

복원 후 새 정상 수집은 `2026-10-11T16:20:31.503389Z`입니다. main·Argo revision은 복원 commit, Argo는 Synced·Healthy, API·웹·DB는 각각 1/1, 배포 선언 소스는 같은 정상 B입니다. 해당 main의 Jenkins status는 없어서 `jenkins: null`로 보존했습니다. 최종 정상 관측본은 [Pages 38155062511](https://github.com/DevDooly/devdooly-platform-lab/actions/runs/38155062511)의 build·deploy success 후 공개 브라우저에서 다시 확인했습니다. 수집 완료 시각 `2026-10-11T16:20:31.503389Z`, main·Argo 복원 commit, 같은 정상 B 배포 소스와 각각 1/1이 일치했고 실패 배너도 해소됐습니다. 이는 마지막 수집 결과이며 실시간 상태 표시가 아닙니다.

## 비활성 호스트 자동화 설치

초기 Ubuntu 임시 격리 환경에서 collector 41개와 자동화 33개 검사를 각각 모두 통과했고 제외 항목은 0개였습니다. 자동화 실행 파일·root private 설정·unit을 설치하고 `systemd-analyze verify`와 `daemon-reload`까지 완료했습니다. 당시 결과는 installed·verified·inactive였고 timer는 disabled·inactive였습니다.

후속 검증에서는 일반 사용자 CI fixture를 교정하고 root 권한 정책 검사 2개를 추가했습니다. 자동화 검사 35개는 Ubuntu의 root와 일반 사용자 환경에서 각각 **35개 모두 통과·제외 0개**였습니다. 합성 fixture를 사용하는 격리 검사이며 운영 코드의 root 권한 검사는 변경하지 않았습니다. Windows 자동화 검사는 35개 중 34개 통과·POSIX 권한 1개 제외, collector 41개·자동화 35개·Pages 33개를 합한 최종 Windows 검사는 **109개 중 107개 통과·POSIX 권한 2개 제외**였습니다. 앞의 초기 33개·당시 합계 107개 기록은 실행 당시 이력으로 보존합니다. 이 결과를 실제 host cycle·systemd service 실행으로 간주하지 않습니다.

이 초기 설치 시점에는 전용 Pages 자격증명이 없었고 토큰 내용 읽기·host cycle dispatch·timer enable/start를 수행하지 않았습니다. 다음 절의 실제 실행과 구분해 이력을 보존합니다. [자동화 상태](../../../infra/observation/AUTOMATION.md)와 [설치·운영 전환 검증](../../../infra/observation/INSTALL.md)을 따릅니다.

## 전용 자격증명으로 실제 호스트 실행과 timer 활성화

2026년 10월 12일 KST에 게시 전용 자격증명을 등록한 뒤 수동 host cycle, 실제 systemd service, timer 순서로 확인했습니다. Jenkins status 자격증명과 분리했고 비밀값·원문 응답을 공개 기록에 포함하지 않습니다. `DISPATCHED` 접수와 실제 Pages 배포 결과를 각각 확인합니다.

| 실행 경로 | 수집 완료 시각 UTC | 실제 결과 |
| --- | --- | --- |
| 수동 host cycle [38192435517](https://github.com/DevDooly/devdooly-platform-lab/actions/runs/38192435517) | `2026-10-12T01:34:50.661819Z` | Pages build·deploy success, 전체 공개 JSON이 수집본과 일치 |
| 실제 systemd service [38192547419](https://github.com/DevDooly/devdooly-platform-lab/actions/runs/38192547419) | `2026-10-12T01:36:34.833215Z` | service `Result=success`·`ExecMainStatus=0`, Pages build·deploy success, 전체 공개 JSON 일치 |
| timer 최초 자동 실행 [38192680467](https://github.com/DevDooly/devdooly-platform-lab/actions/runs/38192680467) | `2026-10-12T01:38:38.790231Z` | 자체 trigger·service 성공, Pages build·deploy success, 전체 공개 JSON과 브라우저 일치 |

timer 활성화는 `2026-10-12T01:38:36.685346Z`에 확인했습니다. timer는 enabled·active였고 마지막 trigger는 10:38:36 KST, 다음 예약은 11:09:08 KST(`2026-10-12T02:09:08Z`)였습니다. 부팅 후 5분 조건이 이미 지나 활성화 직후 자동 실행된 결과입니다. **다음 예약이 있다는 사실은 실제 30분이 경과해 두 번째 주기가 실행됐다는 검증이 아닙니다.**

실제 service sandbox에서 별도 사용자 소유 게시 자격증명 읽기·짧은 SA 토큰 발급·collector 실행·게시 요청이 성공했습니다. 상태 파일 root `0600`, 임시 SA 토큰 파일 0개를 확인했고 최초 timer 실행 후 collector 잠금도 남지 않았습니다. oneshot service가 성공 후 inactive(dead)로 돌아간 것은 정상이며 timer의 active 상태와 구분합니다. 최초 자동 게시의 전체 공개 JSON 일치는 `2026-10-12T01:39:56.443645Z`에 확인했습니다. 공개 브라우저 재조회에서도 01:38:38 UTC 수집 완료·Jenkins build 16 success·Argo Synced Healthy·API 웹 DB 각각 1/1이 일치했습니다. 이는 해당 수집 시점의 기록이며 실시간 상태 보장은 아닙니다.

같은 snapshot·journal을 설치된 uploader에 다시 입력한 실제 검사에서는 `SAME_ATTEMPT_NOT_RETRIED`와 종료 코드 1을 확인했습니다. 새 run ID가 없었고 기존 journal bytes와 최초 timer 실행의 `DISPATCHED` 기록이 유지됐습니다. 이 종료 코드는 재게시를 하지 않는 의도한 결과입니다. 마지막 intent의 재전송 차단이며 전체 이력에 대한 exactly-once 보장은 아닙니다. credential의 실제 scope 조회·만료·교체, 실제 30분 간격의 반복 게시와 장기 운영은 아직 검증하지 않았습니다.

## 관측 자동화 활성화 전후 기존 서비스 보존

활성화 전후의 읽기 전용 비교를 `2026-10-12T01:46:45.030525Z`에 통과했습니다. 조회 대상 Docker 컨테이너 35개 전체의 identity·시작 시각·mount 집합·running 상태가 같았고, running 수는 23개였습니다. Lab API·웹·DB 3개 Pod의 UID와 컨테이너 선언도 같았으며 모두 Ready였습니다. 이는 관측 자동화를 켜는 동안 기존 서비스와 Lab Pod를 보존했는지 비교한 결과입니다. **이번 비교에서 SQL을 다시 검증한 것은 아닙니다.**

첫 비교 도구는 Docker `Mounts` 배열의 순서를 그대로 비교해 assertion이 실패했습니다. 조회마다 배열 순서가 달라지는 것을 확인하고 mount 집합으로 순서를 정규화한 retry1에서 전체 검사를 통과했습니다. 원래 실패 출력을 private 기록에 보존했으며 첫 시도를 통과로 세지 않습니다. 공개 요약의 `dockerRawMountOrderEqual: false`는 이 순서 차이를 나타내고, 실제 보존 조건인 `dockerMountSetsEqual`은 true입니다. 이를 mount 변경이나 서비스 장애로 해석하지 않습니다.

## 로컬 구현 검증과 남은 작업

- 웹은 신규 관측 검사 13개를 포함한 전체 26개 테스트, Astro 타입 검사, Pages 경로 빌드를 로컬에서 통과했습니다. 이 수치는 합성 입력과 로컬 HTTP 검증 범위입니다. 별도의 공개 브라우저 확인 결과는 위 게시 기록에 연결했습니다.
- 수집기의 Windows 오프라인 검사는 41개 중 40개 통과, POSIX 파일 권한 검사 1개 제외였습니다. 이어 Ubuntu의 격리된 임시 디렉터리에서 고정한 collector·contract와 41개 검사를 실행해 **41개 모두 통과·제외 0개**를 확인했습니다. 이 검사에는 POSIX `0600` 권한도 포함되며 실제 클러스터 수집 결과와는 별도 범위입니다.
- 수집 실패와 브라우저 파일 조회 실패를 분리했습니다. 마지막 성공 후 2시간 초과는 오래된 기록으로 표시하고, 실패한 시도의 새 시각으로 이전 성공을 최신처럼 만들지 않습니다. 이 오래된 기록·조회 실패 처리는 오프라인 UI 테스트로 확인했습니다.
- 기존 `lab-observation.json` v1과 조회 API의 플랫폼 `NOT_CONFIGURED`를 유지합니다. 현재 JVM 정보, 새 플랫폼 관측본과 CI/CD 근거를 합쳐 하나의 실시간 상태로 표시하지 않습니다.

| 현재 완료 범위와 남은 항목 | 상태 |
| --- | --- |
| 허용 JSON의 수동 outbound Pages dispatch | 수동 게시·복구·순서 역전 보존 재검증 완료 |
| 새 플랫폼 카드·수집 시각·오류 표시의 공개 브라우저 검증 | 1280px·390px 확인, 교정 후 공개 JSON·artifact 시각 보존 확인 |
| 수동 host cycle·실제 systemd service의 Pages 게시 | 실제 실행·build/deploy 성공·전체 공개 JSON 일치 |
| timer 활성화·최초 자동 trigger | enabled·active, 자체 실행·Pages 게시·전체 JSON·브라우저 확인 |
| 같은 마지막 intent 재전송 차단 | 실제 SAME_ATTEMPT_NOT_RETRIED, 새 run ID 없음·journal bytes 보존 |
| 실제 30분 간격 반복 게시·자격증명 만료·회전 | 미검증 |
| API·웹 replicas 0 중단 후 공개 홈·마지막 기록과 DB·기존 서비스 보존 | 실제 중단·동일 정상 B 복원 검증 완료 |
| 실시간 공개 읽기 API, 외부망 HTTPS 경로 | 미연결 |

이번 단계에서는 새로운 inbound 공개 경로를 열지 않았습니다. 관리 도구는 기존 인증된 접속 경로를 유지하며 서버에서 허용한 JSON을 밖으로 전달합니다. 기존 Pages의 앱 관측본, 새 플랫폼 관측본, 초기 수동 게시와 후속 호스트 실행을 구분합니다. 실제 접속 주소·관리 endpoint·credential·원문 진단은 이 근거에 포함하지 않습니다.
