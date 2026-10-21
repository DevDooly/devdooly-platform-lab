# Platform Lab 다음 개발 계획

## 현재 작업 — 2026-10-21(KST)

[배포 전 Kubernetes·Argo 읽기 전용 점검](evidence/cluster-readonly/README.md)을 완료했습니다. 2026-10-20 22:25 UTC의 Argo는 main `e0f14d3`에 Synced·Healthy였고 Deployment4개·Pod7개가 Ready, PVC4개가 Bound였습니다. worker의 Pod→ReplicaSet→Deployment 소유 연결과 기존 image pin도 대조했습니다. 이 점검은 교체 전 worker74의 기록입니다. 이후 [PR177의 worker 교체](evidence/worker-image-rollout/README.md)를 `2026-10-21T00:19:02Z`에 main `33c5e8c0cf211dc3f4c622b98b40be0b48a3890b`로 반영했습니다. worker source는 `6f551a16a8ed536bb126403234c41b9e9b266d43`, image는 ee713이며 API245d61a·웹 image029c는 유지했습니다. `00:20:56 UTC`와 후속 `00:23:59 UTC`에 Argo Synced·Healthy·새 Pod Ready를 확인했습니다. [배포 준비 문서](plans/runtime-rollout-readiness.md)의 당시 조건과 실제 반영 근거를 구분합니다.

기존 약30분 timer의 [새 worker 자동 수집·Pages 게시](evidence/worker-image-rollout/NATURAL_PUBLICATION.md)를 확인했습니다. main `6b628211fbc5b619b2900e221290b8e92e02da84`의 [Pages39523423769](https://github.com/DevDooly/devdooly-platform-lab/actions/runs/39523423769) build·deploy가 성공했고, 공개 플랫폼·작업·Kafka JSON3개가 대응 artifact 원문과 전체 bytes가 같았습니다. 저장된 작업 관측도 API245d61a와 runtime6f551a1을 구분하며 새 시작 시각과 `00:47:19.998983 UTC` heartbeat를 유지합니다. timer trigger `00:47:18 UTC`, service `00:47:18`–`00:47:22 UTC`와 실행기의 DISPATCHED 결과를 해당 Pages run에 연결했으며, 수동 Pages dispatch·timer 강제 실행·주기 단축은 하지 않았습니다.

[관측·DDNS 코드 반영](evidence/automation-failure-boundaries/DEPLOYED.md)을 마쳤습니다. DDNS 파일 검증은 `2026-10-21T01:04:43.262929Z`, 관측 파일 검증은 `01:07:03.347167Z`에 완료했습니다. DDNS는 이후 `01:05:39 UTC`에 시작한 자연 회차의 `UPDATE_ACCEPTED`·정상 종료를 확인했습니다. 새 관측 실행기는 `01:18:07 UTC`에 시작한 회차에서 Pages39526516518을 반환했고 build·deploy 성공과 공개 JSON3개·artifact 원문 일치를 확인했습니다. 원래 timer·unit·권한을 유지하고 수동 dispatch는 하지 않았습니다.

[새 worker의 고정 합성 입력 한 건](evidence/current-worker-fixture/README.md)을 실제 검증했습니다. 2026-10-21 UTC의 stage `02:02:32`–`02:02:49` 뒤 `02:03:24`–`02:03:29`에 입력12·성공7·실패3·중복2·대기0의 COMPLETED·EXPORTED와 빈 슬롯, 새 raw·export3개 전체 bytes를 확인했습니다. 기존8작업·24객체는 보존했고 Kafka CLI committed/log-end는8/8에서9/9로 전진해 lag0이었습니다. `02:15:12 UTC`에는 완료된 정확한 owned Job만 TTL controller로 정리했고, `02:15:51`–`02:15:57`의 후속 조회에서 DB·객체27개·HTTP9작업·Kafka9/9/0과 같은 worker 신원·heartbeat를 다시 대조했습니다. Deployment4·Pod7 Ready와 PVC4 Bound, Argo main9de51a5 Synced·Healthy도 확인한 시점의 기록입니다. 원래 약30분 timer의 `02:18:46`–`02:18:50 UTC` 회차는 같은 main의 [Pages39532314754](https://github.com/DevDooly/devdooly-platform-lab/actions/runs/39532314754) build·deploy에 성공했고, `02:24:36`–`02:24:37 UTC`의 공개 JSON3개가 artifact 원문과 전체 bytes가 같았습니다. 새9작업·기존8작업 projection 보존, API245와 runtime6f55의 구분·빈 슬롯·Kafka LSO9/commit9/lag0도 확인했습니다. [현재 공개 HTTPS 재관측](evidence/public-get/README.md)은 run39533662559에서 지정 GET6개 모두 HTTP200·DTO 검증을 통과했습니다. 실행 결과는 [ID·입력 건수와 전체 ID](evidence/run-selection/README.md)로 구분하도록 수정했고 로컬 화면 확인을 마쳤습니다. [요청·응답 ID 일치](evidence/run-response-identity/README.md) 수정의 로컬209개·타입·빌드와 공개 정상 선택을 확인했습니다. [100개 센서 범례 줄바꿈](evidence/chart-legend-wrap/README.md)도 공개 데스크톱·모바일에서 확인했고, 기본 URL은 reload·실시간 조회 후 정상 폭을 확인했습니다. 다음은 첫 조회가 게시 기록으로 fallback한 원인 진단이며 현재 원인은 미확인입니다. **기동 복원·토큰 교체·자원 예산 정책·PR102 접수 gate는 모두 보류**합니다.

[공개 GET 응답 관측](evidence/public-get/README.md)을 run39483000285/source46d099d에서 한 번 실행해 지정6개 응답의 HTTP200·헤더·DTO·출처·시각을 확인했습니다. 시작19:23:35.337Z·완료19:23:44.348Z의 원문1635bytes와6필드 metadata를 검증·보존했습니다. 각 응답의 운영 source245d61a는 검사기 main46d099d와 구분합니다. 로컬51개와 PR Linux 새16개·기존HTTPS15개·TLS20개, 같은 main의 오프라인 검사도 통과했습니다. POST·거부 시험·서버 설정 변경·새 토큰·SSH는 사용하지 않았습니다. 근거 카드1개를 추가해 기존19개를 유지한 총20개로 연결했습니다. 웹207개·타입47파일·프로젝트 빌드와 로컬1280px·390px의 GET·CI/CD·GitHub Linux CI 교집합1개, 출처·가독성·전체20개 순차 표시를 확인했습니다. 같은 mainbd4eb39의 Pages39484421012 build/deploy와 CI39484421037가 성공했고, 공개1280px·390px에서도 검색 교집합1개·원문/고정 소스 링크·본문17px·모바일 링크44px·가로 넘침 부재를 확인했습니다. 후속 [수동 실행39521322979](https://github.com/DevDooly/devdooly-platform-lab/actions/runs/39521322979)은 main33c5e8c의 첫 attempt에서 offline·public_gets가 성공했고, `2026-10-21T00:26:48.755Z` → `00:26:58.079Z`에 지정6개 HTTP200·DTO·API 소스245d61a를 확인했습니다. 별도 공개 UI에서는 API245d61a와 worker6f551a1을 구분하고 새 실행 시작 `00:20:05 UTC`, heartbeat `00:26:53` → `00:27:32 UTC` 전진을 확인했습니다. 이 UI 관측은 GET artifact 자체의 runtime 증명이 아닙니다. 자동 게시 후속 결과는 위 안내를 따릅니다. 현재 worker 생존·장기 가용성·인증서 자연 갱신의 검증은 아닙니다.

[두 번째 실제 TLS 관측](evidence/tls-certificate/README.md)은 run39477022262/source6f551a1에서 오프라인20검사·TLS 단계 성공, HTTP0회·기본 CA·TLS1.3·실제 close를 확인했습니다. 18:42:26.245Z의 원문911bytes와6필드 metadata를 검증·보존했고 첫 관측과 같은 대상·leaf·유효기간, 수집 당시87일임을 확인했습니다. 자연 갱신은 미검증입니다. 첫 entry를 보존한 이력에 두 번째 원문·metadata를 추가하고 마지막 성공과 같은 run의 고정 원문 링크를 선택하도록 연결했습니다. 웹207개·skip0, 타입47파일 오류·경고·힌트0와 두 페이지 빌드를 통과했습니다. 로컬1280px·390px에서 같은 인증서 표시, 마지막 수집18:42:26.245Z·87일·만료·실행/소스/고정 원문 링크, 기본 닫힘·Enter 토글과 두 실제 시각·SHA, 본문17px·가로 넘침 부재를 확인했습니다. 같은 main462fa0e의 Pages39481892187 build/deploy와 CI39481892169가 성공했고, 공개1280px·390px에서도 두 기록·출처·Enter 토글·긴 SHA와 가독성을 확인했습니다. 별도 GET6 응답 관측의 실제 결과는 위 최신 기록을 따릅니다. 이 TLS 후속에서는 HTTP 거부 시험·SSH·운영 변경·새 토큰·별도 환경을 사용하지 않았습니다.

[관측 자동화의 두 경계](evidence/automation-failure-boundaries/README.md)는 선택적 작업 진단 파일의 쓰기 실패가 유효한 플랫폼 게시를 막지 않도록 수정하고, 필수 intent 저장 실패는 계속 전송을 차단합니다. DDNS는 wait 반환 뒤20초 시한을 다시 확인합니다. 기존 코드의 실패와 나노초 검사의 첫 전체 실패를 보존했습니다. 로컬 관측156개 통과·POSIX4개 생략에 이어 PR168의 같은 main6f551a1에서 Linux 관측160개·DDNS5개 통과·skip0, API240개·Pages·gateway 성공을 확인했습니다. 이후 [운영 반영](evidence/automation-failure-boundaries/DEPLOYED.md)에서 두 코드 교체·DDNS 새 자연 회차·새 관측 코드의 Pages와 공개 결과 연결을 확인했습니다. 원래 오프라인 검증에서는 HTTP 거부 시험·미니 PC 배포·새 토큰·별도 환경을 사용하지 않았습니다.

[근거 검색의 초기 입력 보호](evidence/evidence-input-readiness/README.md)는 준비 전 SSR 사본의5개 native disabled와 카드·링크 유지, 실제 앱의 준비 후 활성화·검색·6→12→18→19개·마지막 버튼 초점·모바일 Tab 순서를 확인했고 웹207개·타입47파일·프로젝트 빌드를 통과했습니다. 임시 사본은 배포 출력에서 제거했습니다. PR166의 같은 main2f8e0af Pages·CI와 공개1280px·390px의 첫 접속 직후 검색도 확인했습니다. 별도 환경·새 토큰·운영 변경은 사용하지 않았습니다.

[결과 탭 키보드 수정](evidence/lab-keyboard/README.md)은 로컬 브라우저8가지·웹207검사·타입·프로젝트 경로 빌드와 mainf7214bd의 Pages·컨테이너CI, 공개1280px·390px 확인을 완료했습니다. 실행 오류와 직접 링크 위치 문제의 후속 결과는 아래 기록에 정리했습니다. 기존 네 항목의 보류는 유지합니다.

[실행기 Error 처리](evidence/runtime-error-cleanup/README.md)는 수정 전3개 실패를 실제 재현하고, 수정 후 관련26개·전체 API 검증을 완료했습니다. 로컬 전체233개 중222개 통과·Linux 전용11개 생략에 이어 같은 main12197d5의 Linux API233개 통과·skip0도 확인했습니다. 새 토큰·VM·운영 배포는 사용하지 않았습니다.

[초기 직접 링크 보정](evidence/initial-fragment/README.md)은 로컬390px·1280px에서 목표 제목 유지, 별도 임시 HTML에서10초·최대4회·pointer/Tab 입력 취소·hash 없음·reload 제외를 확인했습니다. 웹207개·타입47파일과 두 경로 빌드도 통과했으며 임시 HTML은 제거했습니다.

[부분 client 구성 Error](evidence/client-construction-error/README.md)는 기존 동작의 close 누락3개 실패를 재현한 뒤 수정7개·전체 API 검증을 완료했습니다. 로컬240개 중229개 통과·기존 Linux 전용11개 생략에 이어 main64be1e8의 Linux API240개 통과·skip0를 확인했습니다. [직접 링크](evidence/initial-fragment/README.md)도 mainb23b380의 Pages·CI와 공개390px·1280px 확인을 마쳤습니다.

오류 처리 사례의 근거 카드는 mainc5203cb의 기존 workflow_dispatch 실행39472209197과 공개1280px·390px 확인을 마쳤습니다. 최초 push 게시39472100508은 이력 변경 보호로 실패한 원래 결과를 유지하며, 별도 성공 실행의 관측 파일3개와 공개 파일의 전체 bytes·SHA가 같음을 확인했습니다. 일반 이미지 제안은 API·웹만 갱신하고 worker는 `runtime.yaml`의 별도 pin을 사용합니다. 이 카드 게시 당시에는 운영 반영 전 조건을 정리했으며 SSH 조회·운영 배포는 수행하지 않았습니다. 이후 실제 worker 교체는 위 PR177의 별도 근거를 따릅니다. 기동 복원·토큰 교체·예산 정책·PR102의 네 보류 항목은 유지합니다.

**추가 보류 결정:** 별도 VM·장비가 없어 사용자 결정에 따라 K3s·Jenkins 실제 기동 복원을 보류합니다. 기존 파일·무결성 검증 결과와 사전준비 문서는 유지하며, 실행 환경이 준비되면 대상·버전·자료와 정확한 시험 범위를 확인해 재개합니다.

[heartbeat 시각 순서 표시](evidence/job-heartbeat-order/README.md)의 합성 반례를 재현했습니다. DB 확인보다 미래인 heartbeat를 브라우저가 따라잡으면 “5분 초과”로 잘못 분류하던 화면을 수정했습니다. 해당 기록의 nanosecond 순서 역전은 `clock-check`로 유지하며 원 시각·source·API 계약을 보존합니다.

웹188개·skip0·타입44파일·프로젝트 경로 빌드와 로컬 데스크톱·모바일의 다시 읽기·경고·가독성을 확인했습니다. 임시 합성 페이지와 JSON은 제거했습니다. PR152의 같은 main `a7eb9926`에서 Pages·CI·Jenkins를 통과했고, 2026-10-20 15:45–15:48 UTC 공개1280px·390px의 실제 조회·다시 읽기·소스·가독성을 확인했습니다.

[인증서 첫 실제 관측](evidence/tls-certificate/README.md)은 run39452152238/source8c17642의 TLS1연결·HTTP0회·표준CA·실제close를 통과했습니다. 수집 당시87일·만료2027-01-16T13:10:02Z를 원문과 함께 보존했습니다. 첫 기록이므로 자연 갱신이나 실제 두 관측의 비교는 미검증입니다.

원문 SHA·출처·동일 대상·시간 순서와 마지막 성공 보존을 검사하는 [작은 정적 블록](https://devdooly.github.io/devdooly-platform-lab/#tls-certificate)을 공개했습니다. 순수19·전체웹207검사·타입46파일·루트/프로젝트 빌드에 이어 같은 main4362975의 Pages·컨테이너CI와 2026-10-20 16:16–16:19 UTC 공개1280px·390px의 native details·출처·가독성을 확인했습니다. Jenkins commit status는 당시 미관측이고 이미지 gate 뒤 게시·GitOps 제안은 생략됐습니다. 새 운영 배포는 하지 않았습니다.

[역사적 백업의 runtime 복원 사전준비](plans/historical-runtime-restore.md)는 문서로 정리했으며 실제 기동은 위 결정에 따라 보류합니다. 기존 파일 검증의 원래 실패와 별도 후속 통과를 보존하고, K3s API·Jenkins controller·credential·전체 애플리케이션의 서로 다른 완료 조건을 구분했습니다. 재개 시 archive에 맞는 버전·동일 시점의 자료, 실제 사본·키를 사용할 정확한 범위를 확인해야 합니다. 기존 파일 복원 실행기를 재사용하거나 현재 선언을 역사적 버전의 증명으로 취급하지 않습니다.

추가 TLS 관측은 새 기록이 필요할 때 검토한 수동 실행으로 진행하며 자동 주기·강제 갱신은 추가하지 않습니다. 인증서 자연 갱신·현재 공개 경로의 재부팅·전체 archive 기동 복원은 미검증입니다. 토큰 교체·예산 정책·PR102는 계속 보류합니다.

## 현재 작업 — 2026-10-20 15:07 UTC

기존 [실행 잠금 손실 원문](evidence/runtime-lease-loss/README.md)을 설명하는 별도 `/cases/runtime-ownership/` 페이지를 구현했습니다. `RUNNING / EXPORT`는 종료된 프로세스의 마지막 DB 기록이며, 실제 client·context·child 종료와 구분합니다. 네 단계의 상세 내용은 native 접기/펼치기이며 세 번째를 기본으로 엽니다. `NO_COMMIT / null`과 점유 슬롯 보존, 이전 child 종료 뒤 새 잠금 확인의 범위를 유지합니다.

웹186개 검사·skip0·타입 검사44파일과 루트/프로젝트 경로 빌드를 통과했습니다. 로컬1280px·390px 확인 뒤 [PR149](https://github.com/DevDooly/devdooly-platform-lab/pull/149)를 병합했고, 같은 main `40fdf6f3`의 [Pages 39444806349](https://github.com/DevDooly/devdooly-platform-lab/actions/runs/39444806349)·[CI 39444810189](https://github.com/DevDooly/devdooly-platform-lab/actions/runs/39444810189)를 통과했습니다. 2026-10-20 15:07 UTC에 공개1280px·390px에서 기본 열림·키보드 토글·표 초점·원문 링크·목록 왕복, 본문17px·긴 SHA 줄바꿈·가로 넘침 부재를 확인했습니다.

기존 런타임 문서의 [장애별 판단표](runbooks/continuous-runtime.md#실제-네-가지-장애의-판단-기준--2026-10-20-utc)에서 offset 실패·export 손상·잘못된 입력·잠금 손실의 서로 다른 저장 상태와 재개 전제를 정리했습니다. [AI 예제 소유자 검토자료](reviews/ai-window-owner-review.md)는 기존 계약·테스트·오차·주장을 읽는 질문이며 사람의 판단은 PENDING입니다. 동결된 예제16파일과 실제 원문을 유지했고 새 장애 시험·benchmark·운영 배포는 실행하지 않았습니다. 다음 운영 후속은 새 토큰 준비 뒤 실제 교체 검증, 이후 인증서 자연 갱신과 현재 공개 경로의 재부팅 검증이며 각각 필요한 입력·시점을 확인한 뒤 진행합니다. 토큰 교체·예산 정책·PR102는 계속 보류합니다.

## 최신 PostgreSQL catalog 재시작 검증 — 2026-10-20 14:32 UTC

[새 격리 환경의 첫 실제 시험](evidence/cloud-catalog-restart/README.md)을 통과했습니다. Spark 정상 종료·writer 부재·Trino 미생성 상태에서 소유 PostgreSQL을 한 번 정상 stop/start했습니다. 실제 exit0·원 postmaster 소멸·새 postmaster와 같은 full CID/config·volume·DB system identifier, 두 catalog 테이블의 전체 logical rows와 namespace property 행6개를 확인했습니다.

fresh Trino의 첫 SELECT10·시점별6/12/12·Silver12·snapshot3·현재 file1과 전체20객체 bytes·기존14객체 보존을 대조했습니다. Trino의 실제 exit143은 PG exit0과 별개로 보존했으며 source/tool 불변·자기 자원 중지를 포함한 workload106,252ms가 단일600초 조건을 통과했습니다. image 준비는 이 시간에서 제외합니다. 운영 DB 재시작·crash 복구·HA 검증은 아닙니다.

실제 기록을 연결한 공개 근거 목록의 검색·6개씩 표시를 구현했습니다. 웹173개 검사·타입·build와 로컬1280px·390px 확인에 이어, [Pages 39441997794](https://github.com/DevDooly/devdooly-platform-lab/actions/runs/39441997794)·[main CI 39441997832](https://github.com/DevDooly/devdooly-platform-lab/actions/runs/39441997832)가 같은 `7a20aa28`에서 통과했습니다. 2026-10-20 14:49–14:50 UTC에 공개1280px·390px에서 검색 정규화·기술/환경 교집합·6→12→18개·조건 초기화·키보드 초점·PG 출처·가로 넘침 부재를 확인했습니다. 다음은 기존 실행 잠금 손실 기록을 설명하는 별도 사례 페이지의 로컬 검증과 게시입니다. 토큰 교체·예산 정책·PR102는 계속 보류합니다.

## 최신 실행 잠금 손실 검증 — 2026-10-20 14:00 UTC

[실제 연결 손실 시험](evidence/runtime-lease-loss/README.md)을 통과했습니다. 실제 empty export 뒤의 경계에서 전용 named-lock 소유 연결 하나만 종료하고, 다음 production 소유권 검사가 후속 발행·수신을 모두 차단하는지 확인했습니다. 호출은 각각 0이었고 queued 작업·원본·DISPATCH PENDING·점유 슬롯을 보존했습니다. 실제 client·lease·context와 child 프로세스가 종료한 뒤 새 실제 잠금 획득·검증·해제도 통과했습니다.

DB journal은 fault 전 `RUNNING / EXPORT / failureCode null`의 전체 행과 시각이 그대로 남았습니다. 소유권을 잃어 pause 저장도 거부된 결과이며, 종료된 worker의 마지막 기록을 현재 정상 상태나 `PAUSED_OPERATOR / LEASE_LOST`로 바꾸어 표시하지 않습니다. 진행 중 I/O의 원자적 fencing·HTTP readiness·자동 복구는 시험 범위가 아닙니다. 공개 근거 목록에 연결해 Pages·동일 main CI를 통과했고, 2026-10-20 14:11–14:12 UTC에 공개 데스크톱·모바일의 Java·Cloud 필터·실제 출처·본문 17px·가로 넘침 부재를 확인했습니다.

당시 다음 과제였던 같은 격리 PostgreSQL 컨테이너·볼륨의 정상 stop/start 결과는 위 최신 기록을 따릅니다. 운영 DB 재시작·crash 복구·HA는 그 시험에도 포함하지 않았습니다. 토큰 교체·예산 정책·PR102는 계속 보류합니다.

## 최신 Kafka 입력 보호 검증 — 2026-10-20 13:40 UTC

[잘못된 메시지의 실제 보호 시험](evidence/invalid-message-runtime/README.md)을 통과했습니다. 실제 malformed record offset 0 뒤에 정상 작업을 offset 1로 발행했고, 두 새 worker 모두 `PAUSED_OPERATOR / CONSUME / INVALID_MESSAGE`로 중지했습니다. 두 일반 run 거부의 journal 불변과 명시 resume 뒤 재중지를 확인했습니다. 정상 작업은 `QUEUED / NOT_REQUESTED`·슬롯 점유, 업무·EXPORT 결과 0과 원본/ACK 보존 상태이며 두 committed offset은 실제 부재(null), end는 2입니다. 복구 완료나 lag 2로 표현하지 않습니다.

실제 원문을 [공개 근거 목록](https://devdooly.github.io/devdooly-platform-lab/#evidence)에 연결하고 Pages·main CI를 통과했습니다. 2026-10-20 13:48–13:49 UTC에 데스크톱·모바일의 Java/Kafka·Cloud 격리 필터·실제 출처·본문 17px·가로 넘침 부재를 확인했습니다. 당시 다음 경계였던 실행 잠금 연결 손실의 결과는 위 최신 기록을 따릅니다. 토큰 교체·예산 정책·PR102는 보류합니다.

## 최신 export 손상 복구 검증 — 2026-10-20 13:16 UTC

[실제 손상 export 시험](evidence/export-integrity-runtime/README.md)을 통과했습니다. 새 worker의 실제 검증 예외가 `PAUSED_OPERATOR / EXPORT / EXPORT_FAILED`로 남았고, 일반 run 거부와 수리 없는 resume 뒤 재중지를 확인했습니다. 시험 소유 손상 객체 한 개만 명시 삭제한 뒤 별도 resume에서 파일 2개의 전체 bytes·크기·SHA, `EXPORTED`·슬롯 해제·완료 메시지 replay 1회·commit/end 1·lag 0을 확인했습니다. 직접 DB fixture와 실제 마지막 consumer replay를 구분하며 원본·업무 행과 시각·소스·소유 자원 정리도 통과했습니다.

실제 기록을 [단계 화면](https://devdooly.github.io/devdooly-platform-lab/#export-integrity-runtime)에 연결해 웹 160개 검사·타입·빌드와 Pages·main CI를 통과했습니다. 2026-10-20 13:29–13:30 UTC에 공개 1280px·390px의 선택·키보드·상세 근거·가로 넘침 부재를 확인했습니다. 당시 다음 경계였던 잘못된 Kafka 입력의 결과는 위 최신 기록을 따릅니다.

## 최신 격리 런타임 검증 — 2026-10-20 12:44 UTC

[DB commit 뒤 Kafka commit 실패 복구](evidence/offset-commit-recovery/README.md)의 실제 시험을 통과했습니다. 영속 `PAUSED_OPERATOR / CONSUME / OFFSET_COMMIT_FAILED`, 일반 run 거부와 명시적 resume, 실제 완료 작업 재전달 1회·export 파일 2개·슬롯 해제·commit/end 1·lag 0을 확인했습니다. 업무 행·처리 시각·소스와 소유 자원 정리도 확인했습니다. broker 재개 직후 commit은 실제 미관측(null)이었으며 offset reset은 하지 않았습니다.

실제 기록을 [단계별 화면](https://devdooly.github.io/devdooly-platform-lab/#offset-commit-recovery)에 공개했고, 2026-10-20 13:01–13:02 UTC에 1280px·390px의 단계 전환·키보드 이동·상세 근거와 가로 넘침 부재를 확인했습니다. 당시 다음 과제였던 손상 PENDING export의 결과는 위 최신 기록을 따릅니다. 운영 복구·host/broker 재시작·HA·모든 장애의 exactly-once는 이번 결과의 범위가 아닙니다.

## 앞선 Kafka backlog 검증 — 2026-10-20 11:25 UTC 기록

[consumer 종료 후 backlog 복구](evidence/kafka-lag-recovery/README.md)를 새 hosted broker에서 확인했습니다. 실제 4개 처리·commit 뒤 정상 close로 group EMPTY를 만들고, 중단 중 6개를 추가한 뒤 같은 group의 새 client가 남은 14개를 읽었습니다. 네 단계의 LSO/commit/lag는 12/4/8 → 12/4/8 → 18/4/14 → 18/18/0이며, observer target·읽기 전후 상태와 소유 자원 정리도 확인했습니다.

저장된 [단계 관측 화면](https://devdooly.github.io/devdooly-platform-lab/#kafka-lag-recovery)은 [PR127](https://github.com/DevDooly/devdooly-platform-lab/pull/127)과 [Pages 39414345653](https://github.com/DevDooly/devdooly-platform-lab/actions/runs/39414345653)으로 공개했습니다. 2026-10-20 11:24–11:25 UTC에 1280px·390px 화면의 단계 전환·키보드 이동과 페이지 가로 넘침 부재를 확인했습니다. 현재 Kafka 검증을 실제 worker·DB·export 복구, 강제 종료·broker 재시작·HA·처리량 검증으로 확대하지 않습니다.

당시 다음 과제로 계획한 **DB commit 후 Kafka offset commit 실패 → 영속 pause → 재시작 거부 → 명시적 resume**의 후속 결과는 위 최신 기록을 따릅니다. broker process pause 중 timeout이 발생해도 unpause 뒤 늦은 commit이 처리될 수 있으므로, offset을 reset하거나 commit 부재를 가정하지 않는 설계를 유지했습니다. 토큰 회전과 자원 예산·PR102 접수 gate는 보류합니다.

## 최신 운영 재확인 — 2026-10-20 UTC

[시점별 운영 근거](evidence/public-read-https/ops-20261020/README.md)에서 선택 운영 상태·DDNS 자연 실행·표준 TLS, 외부 GET 6개와 지정 거부 3개, 공개 작업 8개·Kafka 관측을 다시 확인했습니다. 이는 수집 시점의 결과이며 장기간 가용성을 보장하지 않습니다.

토큰 2개는 각 목적의 GET 200 응답을 확인했고, 회전은 사용자 선택에 따라 보류합니다. 자원 예산·접수 gate도 보류 상태를 유지합니다. 인증서 자연 갱신은 미검증이며 현재 공개 경로의 재부팅은 수행하지 않았습니다. 아래 10월 18일 안내와 이전 기록은 각 시점의 범위로 읽습니다.

## 최신 안내 — 2026-10-18 UTC 검증 반영

현재 상태는 이 안내와 연결된 최신 근거를 우선합니다. 아래 **이전 계획과 검증 기록**은 각 수집·작성 시점의 기록이며, 당시의 “미실행·미연결”과 미완료 체크를 최신 상태로 해석하지 않습니다. 한국 시각으로 10월 19일에 해당하는 후속 검증도 포함합니다.

- **새 Cloud snapshot 만료:** [실행 39140688897의 근거](evidence/cloud-iceberg-expiration/README.md)에서 snapshot 1개 만료와 data·manifest·manifest list 각 1개 삭제, tag·공유 파일·current 18행·Silver 12행 보존을 확인했습니다. 미니 PC에 접속하지 않고 새 합성 warehouse만 사용했습니다.
- **공개 HTTPS와 live 조회:** [외부 HTTPS·공개 화면 근거](evidence/public-read-https/README.md)에서 표준 TLS·허용 GET 6개·지정 거부 3개를 확인하고, Pages의 실시간 작업 8개·Kafka 조회 연결과 시계 경고 표시·해소를 대조했습니다. 공개 POST·관리 도구·실행 기능은 제공하지 않습니다.
- **격리 Kafka ACL:** [실제 격리 시험](evidence/kafka-acl/README.md)에서 DESCRIBE 관측 profile의 조회와 선택 RPC 거부 5개·잘못된 비밀번호의 인증 실패 1개를 확인했습니다. 운영 Kafka 권한이나 TLS 기밀성 검증은 아닙니다.
- **저장된 snapshot 관측 화면:** 저장된 만료 전 4/25·만료 후 3/23(snapshot/객체 수)의 [전후 비교 화면](https://devdooly.github.io/devdooly-platform-lab/#snapshot-expiration)을 공개하고 전후 전환을 확인했습니다([PR120](https://github.com/DevDooly/devdooly-platform-lab/pull/120), [Pages 39142668759](https://github.com/DevDooly/devdooly-platform-lab/actions/runs/39142668759)).

**다음·보류:** DB와 Garage의 공유 filesystem은 읽기 전용으로 확인했지만, quota·자원 예산·실제 앱 reader·회계 연결이 미확정이므로 [PR102 접수 gate](https://github.com/DevDooly/devdooly-platform-lab/pull/102)는 미연결·보류입니다. 운영 자료의 만료/GC, 장기간 가용성·성능 SLA, 작업 진행 중 호스트 장애·HA는 미검증입니다. 휴대폰 외부망 확인·인증서 자연 갱신·자격증명 회전도 위 hosted/browser 결과와 별도 범위로 남깁니다.

## 이전 계획과 검증 기록

이전 readiness 운영 검증(2026-10-15 14:54 UTC)에서 readiness 배포·idle worker 교체·같은 ID 읽기 전용 재시도와 8작업·16파일·24객체를 확인했습니다. [전체 근거와 한계](evidence/worker-readiness/CORRECTED_IMAGE.md)를 기준으로 읽습니다. 이후 [native7의 Trino 조회·재시작](evidence/iceberg-jdbc/README.md)과 별도 [Cloud Spark 시험 8의 적재·순차 replay](evidence/spark-silver/README.md)를 검증하고 정적 기록 화면에 연결했습니다. 이후 [새 Cloud 전체 시험](evidence/cloud-lakehouse/FULL_SUCCESS.md)에서 별도 fresh warehouse의 Spark→Trino 연결·현재 파일 2→1 compaction·자기 자원 종료를 확인했습니다. [현재 DB의 a7 논리 백업·격리 복원](evidence/current-db-restore/README.md)은 8개 테이블 스키마·비runtime 7개 테이블의 행·BLOB과 원본 보존을 확인했고, 기록과 카드는 PR #61로 공개했습니다. 원래 stop receipt는 실패로 유지하며 정상 exit는 UNOBSERVED이고 전체 애플리케이션 복구는 미검증입니다. [9차 새 closed-copy capture](evidence/iceberg-capture/ATTEMPT_9.md)에서 Linux87·skip0과 같은 실행의 actors·clock·metadata graph·inventory·전체 KEEP 연결을 확인했습니다. 스냅샷3·참조1·보호 항목1·객체20인 보존 계획이며, 다음은 이 실제 요약의 화면·회귀 확인과 보존 정책·운영 규모 및 다른 장애 경계의 독립 검토입니다. Snapshot 만료·객체 삭제는 미실행이며 미니 PC native7의 중지된 시험 환경과 보관 자료는 유지합니다.

초기 계획: 2026년 10월 12일 · 최근 V4 운영 전환·독립 AI Java 예제 검증: 2026년 10월 15일

최근 배포·보존 확인(2026-10-16 갱신): 소스 `74a8e988`의 [Actions](https://github.com/DevDooly/devdooly-platform-lab/actions/runs/38814779596)와 Jenkins 45에서 API 191개 + 독립 Java 예제 20개, 총 211개를 통과했습니다. 이어 PR #52의 API·웹과 PR #53의 worker를 실제 전환했습니다. 애플리케이션 소스는 `74a8e988`, 최종 GitOps revision은 `b63fedfa`입니다. 2026-10-15 23:12:57 UTC의 배포 후 검사에서 작업 8개·export 정보 16개, 기존 객체 24개 + native7 객체 12개의 전체 GET, PV·PVC 각 13개·Docker 60개와 Kafka offset/end 8·lag 0을 확인했습니다. [S3 전송 배포·보존 근거](evidence/s3-runtime-rollout/README.md)는 해당 시점의 기록이며 실시간 가용성을 뜻하지 않습니다.

후속 별도 JVM SDK 검증에서는 실제 배포 JAR의 factory와 Apache5로 알려진 객체 3개를 전체 GET했습니다. 3회 호출·3회 시도·추가 retry 0회, client 종료·정상 exit 0과 자기 Job·ConfigMap·Secret·읽기 전용 key의 정리·폐기를 확인했습니다. factory의 maxAttempts 3은 유지했습니다. 운영 API JVM 내부의 호출·장애 주입·PUT·SLA 검증과 구분합니다. 2026-10-16 00:02:58 UTC의 별도 읽기 검사에서 전체 객체 36개와 업무 SQL·기존 리소스 보존, 임시 SDK 자원·키 부재를 확인했습니다.

Java 백엔드, 데이터 처리, 배포와 운영 경험을 방문자가 직접 확인할 수 있는 포트폴리오로 발전시킵니다. 외부 백업·격리 DB 복원·재부팅과 CI/CD의 정상 배포·실패 차단·이전 image digest 복구를 확인했습니다. **기존 플랫폼 관측의 2026-10-12 수집·실패 보존·Pages 게시·공개 화면과 자동 운영·반복 게시 11회를 검증**했습니다. 게시 순서 회귀 교정, API·웹 중단 후 같은 정상 B 복원에 이어 전용 Pages 자격증명으로 수동 host cycle·실제 systemd service·timer 자동 실행을 확인했습니다. 실제 완료 간격은 약 30~31분이었고 자격증명 만료·회전과 장기간 운영은 별도 후속입니다. Kafka·Garage·상시 worker의 최초 배포와 정상 재시작 당시 총 3작업·파일 6개·슬롯 해제를 확인했습니다. 새 job timer의 자동 게시 2회·완료 간격 1개와 전용 PVC 외부 사본의 격리 복원·clone 물리 블록 복원을 검증했습니다. 이후 보존 계획·새 합성 PVC 정리·작은 자원 관측과 최대 1,000개 입력·동시 접수 경계를 격리 검증했습니다. V2 지원 API·worker를 운영에 함께 배포하고 내부 V2 작업 한 건을 추가해 당시 총 7개 EXPORTED 작업·파일 14개를 확인했습니다. 별도 격리 worker의 export 경계 강제 종료 복구도 확인했습니다. 전체 객체 참조 보호와 별도 Garage 자연 GC, 독립 AI Java 예제도 근거와 함께 기록했습니다. 다음은 다른 장애 경계/호스트 중단·과부하 정책·장기간 운영, AI 예제의 사람 검토와 데이터 플랫폼 사례입니다.

[공개 Lab](https://devdooly.github.io/devdooly-platform-lab/) · [전체 진행 목록](ROADMAP.md) · [현재 접속 안내](START_HERE.md)

## 출발점

| 영역 | 확인한 내용 | 다음에 채울 부분 |
| --- | --- | --- |
| Java API·worker | source `74a8e988`·GitOps `b63fedfa` 실제 배포; CI 211개(API 191 + 예제 20), 8작업·16export 정보·기존24+native12객체 보존; 별도 JVM SDK GET 3회·자기 자원 정리 | 다른 장애 경계·호스트 중단·과부하 정책·장기간 관측 |
| Kafka·Garage 복구 | 외부 사본의 전용 3PVC 복원·clone 물리 블록, 보존 정책·합성 정리 검증 | 장기간 보존 운영·객체 GC·복구 절차 유지 |
| 포트폴리오 | AI 예제 선택·readiness 요약·native Trino 및 Cloud Spark의 실제 정적 기록 화면; 기존 플랫폼 11회와 job timer 2회 근거 별도 보존 | 장기간 반복 운영·자격증명 회전 |
| Jenkins·Actions | 같은 SHA의 두 CI 성공·게시·draft GitOps PR·정상 B 배포·실제 실패 차단, main의 공개 status 수집 | credential 만료·회전과 게시 이력 보존 운영 |
| Argo CD와 Helm | 정상 A → B → A GitOps 복구, Synced·Healthy·데이터 보존과 제한된 실제 상태 수집 | 주기 관측의 반복 운영과 실패 대응 |
| 운영 | 외부 암호화 백업·격리 DB 복원·호스트 재부팅, 사용자 kubectl 복구 | 초기 비밀번호 교체, 추가 장치 사본·전체 archive 복원 |

GitHub Actions를 유일한 이미지 게시자로 유지하고, 전용 Jenkins status credential과 같은 source SHA의 두 CI 성공을 게시 조건으로 활성화했습니다. 사용자 승인으로 Actions PR 설정과 draft GitOps PR 자동 제안도 켰습니다. 공개 Lab은 기존 앱의 마지막 실제 관측본을 보여줍니다. 별도 플랫폼 collector는 최소 읽기 권한으로 실제 상태를 수집했으며 새 관측본을 수동 게시했고, 게시 순서 회귀 교정 후 실제 복구·순서 보존을 재검증했습니다. 실시간 공개 API와 조회 API 내부의 플랫폼 수집은 아직 연결하지 않았습니다. Windows 외부 암호문은 인증·해시를 확인했고, DB는 서버의 새 논리 dump로 격리 복원했습니다. 이후 Kafka/Garage 전용 PVC 3개는 인증한 외부 사본에서 격리 복원했습니다. K3s·Jenkins archive 전체 복원은 별도로 남아 있습니다.

실행 근거는 [미니 PC 배포](evidence/mini-pc/README.md), [Jenkins 빌드](evidence/jenkins-ci/README.md), [후속 접속과 재기동 검증](evidence/operator-access/README.md), [앱 관측 계약](../apps/lab-web/OBSERVATION.md)에 있습니다. [플랫폼 관측 수집 검증](evidence/platform-observation/README.md)과 [허용 필드 계약](../apps/lab-web/PLATFORM_OBSERVATION.md)을 별도로 연결합니다. 완료 항목은 실제 검증 근거와 함께 표시합니다. [백업·복원·재부팅 검증](evidence/recovery/README.md)을 추가했습니다.

## 진행 순서

| 순서 | 주제 | 방문자에게 보여줄 결과 |
| --- | --- | --- |
| 1 | 운영 기준과 복구 | 백업·복원 검증과 장애 대응 기록 |
| 2 | CI/CD 연결 | 소스 SHA부터 실행 image digest까지 이어지는 배포 기록 |
| 3 | 관측 공개 | 빌드·배포·Pod 상태와 마지막 수집 시각 |
| 4 | Kafka와 객체 저장소 | 중복·역순·재시작에도 일관된 처리 결과 |
| 5 | AI를 활용한 Java 개선 | UTC 오류·동일 결과 알고리즘·실제 독립 JMH 기록, 사람 검토 대기 |
| 6 | Iceberg와 Trino | 적재부터 SQL 조회·재시작까지 재현되는 데이터 흐름 |

순서 1의 백업·격리 DB 복원·재부팅과 순서 2의 정상·실패·이전 digest 복구 검증을 마쳤습니다. 순서 3은 실제 수집·인증 실패 후 보존·회복·수동 공개 게시·브라우저를 확인했고, 게시 순서 회귀 교정 후 실제 재검증도 완료했고 API·웹 중단·같은 정상 B 복원도 확인했고 정기 운영 검증을 이어갑니다. 초기 비밀번호 교체·token 회전·추가 장치 사본·전체 archive 복원은 별도 운영 후속으로 남깁니다. AI 사례는 독립 Java 예제·실제 로컬 JMH·정적 기록 UI와 [TIL 글](https://devdooly.github.io/TIL/LLM_Development/UTC_Window_Analysis_Case/)에 연결했습니다. 저장소 소유자의 사람 검토와 실제 채택 판단은 남아 있습니다. 각 단계의 완료 조건을 통과한 뒤 확장합니다.

## 1 운영 기준과 복구

- [x] 사용 중인 클러스터 이름·CA·접속 방식과 설치·데이터 경로를 운영 안내에 정리합니다. 삭제나 정리 전에는 연결 설정과 실제 실행 대상을 함께 확인합니다.
- [x] 관리자 초기 비밀번호 변경 여부를 확인하고, 비밀값을 공개 파일과 분리합니다.
- [x] 서버 외부의 백업 위치를 정하고 K3s datastore·token, Jenkins Home, MariaDB 데이터를 각각 보관합니다.
- [x] 운영 PVC와 분리한 테스트 볼륨에 MariaDB를 복원하고, 기존 12건 결과와 중복 방지 동작을 비교합니다.
- [x] 기존 서비스의 영향을 설명할 수 있는 복구 절차를 작성한 뒤 재부팅 복구를 별도로 검증합니다.

**완료 조건:** 백업 해시·대상·시각, 실제 복원 명령과 결과, 복구 시간, 확인한 데이터가 남아 있어야 합니다. 외부 백업은 전송 후의 무결성과 접근 권한도 확인합니다. K3s는 datastore와 함께 server token을 복원해야 하므로 둘을 같은 복구 단위로 관리합니다. [K3s 백업과 복원](https://docs.k3s.io/datastore/backup-restore)

**공개 결과:** 비밀값을 제외한 복구 기록과 kubeconfig 인증서 오류의 증상·원인·교정·재확인 과정입니다.

[운영 대상 확인](runbooks/lab-operations.md)과 [재실행 명령](runbooks/lab-recovery.md)을 함께 제공합니다. 초기 관리자 비밀번호는 아직 유효합니다. 위 체크는 변경 여부와 보관 방식을 확인했다는 뜻이며 비밀번호 교체 완료를 뜻하지 않습니다. 외부 백업과 격리 DB 복원, 호스트 재부팅 결과는 [복구 검증](evidence/recovery/README.md)에 있습니다.

역사적 외부 백업의 [파일 전용 후속 검증](evidence/historical-file-restore/README.md)은 네 구성요소의 bytes·metadata, 빈 WAL SQLite 무결성과 별도256바이트 키 조립을 확인했습니다. 첫 restore 실패는 보존했고 기존 Jenkins Home은 바꾸지 않았습니다. 전체 archive·K3s/Jenkins application 복원과 credential 복호화는 위 파일 검증과 구분해 후속으로 남깁니다.

## 2 CI/CD 연결

현재 흐름은 `Jenkins 테스트 + Actions 통합 검증 → Actions 이미지 게시 → digest 기록 → draft GitOps PR → 검토 후 main 반영 → Argo CD 배포`입니다. [ADR 0004](adr/0004-jenkins-gated-actions-publication.md)에 따라 Actions를 단일 게시자로 유지하고 동일 source SHA의 Jenkins 성공을 추가 조건으로 연결했습니다. 전용 status credential과 Actions PR 설정을 활성화했고 정상 B 배포·실제 실패 차단·이전 정상 A 복구를 모두 검증했습니다. [운영·검증 절차](runbooks/cicd-publication.md)와 [실행 근거](evidence/cicd-gate/README.md)를 함께 확인합니다.

- [x] Jenkins agent에 호스트 Docker socket을 공유하지 않고, 이미지 빌드는 Actions runner에서 수행합니다. agent 권한·캐시·자원 한도를 기록했습니다.
- [x] Jenkins 전용 status credential과 job별 Actions 권한을 분리하고, 실제 pending·success·failure 전달과 draft PR 제안을 확인했습니다.
- [x] 실제 JUnit 실패에서 새 이미지·게시 artifact·GitOps PR이 생기지 않고 B의 values·Deployment·Pod·SQL·PVC·기존 Docker가 유지되는지 확인했습니다.
- [x] 성공한 빌드의 source SHA, 테스트 결과, image digest, GitOps commit, 실제 실행 버전을 정상 B 배포로 연결했습니다.
- [x] GitOps values의 API/Web digest와 sourceCommit을 이전 정상 A로 되돌리고 실제 HTTP·DB·저장 시각·PVC·기존 서비스 보존을 확인했습니다.

**완료 조건:** 정상 배포 한 번, 실패 차단 한 번, 이전 버전 복구 한 번의 실제 결과를 남깁니다. 배포 상태는 Argo CD가 관리합니다. 자동 동기화가 켜진 상태의 복구는 Git의 선언 값을 되돌려 수행하며, 별도의 Argo CD rollback 명령과 혼용하지 않습니다. [Argo CD 자동 동기화와 rollback 제약](https://argo-cd.readthedocs.io/en/stable/user-guide/auto_sync/)

**공개 결과:** 정상 배포에서는 같은 source SHA의 두 CI 성공부터 digest·GitOps·실행 이미지까지 추적했습니다. 실패 실험에서는 API 테스트 15개 중 1개가 실패했고(기대 성공 8건, 실제 7건), failure status와 Actions 검증 실패를 확인했습니다. 해당 SHA의 새 게시 결과·PR이 없었으며 기존 B의 전체 SQL·처리 시각·PVC와 기존 서비스가 유지됐습니다. 실패 변경을 원복하고 GitOps PR로 A에 복구한 뒤 Synced·Healthy, 3개 Pod Ready, 기존 SQL·Flyway·시각·PVC와 기존 Docker 보존을 확인했습니다. 과거 Jenkins의 단계 미실행·플러그인 충돌과 출처 메타데이터 교정도 설계 이유에 연결합니다.

원복 source의 두 CI 검증은 다시 성공했습니다. 실제로 수동 실행과 pollSCM이 같은 SHA의 Jenkins 빌드를 중복 생성했으며, 최신 pending을 확인한 Actions는 이전 success로 게시하지 않았습니다. GitHub metadata 조회 403으로 실패한 게시 시도도 별도로 남겼습니다. 최신 success 후 게시·draft 제안은 성공했고 이 추가 제안은 적용하지 않고 닫았습니다. 복구 PR의 변경 범위·A OCI·Helm 검증과 실제 A 실행·데이터 보존 검증은 모두 통과했습니다. token의 실제 만료·회전과 동시 요청 실험은 운영 후속이며 위 세 시나리오 완료와 구분합니다.

## 3 관측 공개

아래 11회는 2026-10-12 기존 플랫폼 수집기의 검증이며 새 job 수집 코드의 정기 실행 증거와 구분합니다.

검증한 JSON을 outbound dispatch로 Pages에 반영하고 공개 브라우저를 확인했습니다. 실제 순서 역전 게시의 seed 회귀는 교정 후 공개 JSON·브라우저·이전 artifact로 보존을 재검증했습니다. 초기 자동화 비활성 설치와 정적 검증에 이어, 전용 Pages 자격증명으로 수동 host cycle·실제 systemd service·timer 최초 자동 실행의 Pages 게시와 전체 공개 JSON 일치를 확인했습니다. 이후 최초 자동 실행을 포함한 11회가 모두 Pages build·deploy success였고 10개 실제 서비스 완료 간격은 1825.569287~1875.101367초였습니다. timer는 enabled·active입니다. 이후 실시간 조회가 필요한 항목에 한해 공개 읽기 API를 연결합니다. 이번 단계에서 새 inbound 경로를 열지 않았고, Jenkins·Argo CD 관리 화면은 인증된 관리 경로를 유지합니다.

- [x] 전용 읽기 권한으로 main의 Jenkins 공개 status, 지정 Argo CD sync·health와 실제 Lab Pod 준비 수를 수집했습니다.
- [x] main·Jenkins 대상·Argo revision·API 배포 선언 소스와 고정 image digest·관측 시각·실패 코드를 strict allowlist로 정의했습니다.
- [x] 실제 인증 실패에서 마지막 성공 전체·capturedAt이 유지되고 정상 인증 후 회복되는지 확인했습니다. 출력 0600과 지정 리소스 허용·Secrets/logs/exec/nodes·변경·다른 범위 읽기 거부도 실제 확인했습니다.
- [x] 수집 실패·브라우저 조회 실패·마지막 성공 후 2시간 초과를 구분하는 UI를 로컬 테스트했습니다. 신규 13개를 포함한 전체 26개 테스트·타입 검사·Pages 경로 빌드를 통과했습니다.
- [x] 관리 토큰·원문 로그·내부 주소·임의 오류 필드를 거부하는 schema·validator와 좁은 공개 출력 계약을 구현했습니다.
- [x] 실제 HTTP 401 실패 envelope를 수동 Pages 게시하고 이전 성공 전체·시각 보존과 공개 1280px·390px 화면을 확인했습니다.
- [x] 순서 역전 게시에서 발견한 seed 회귀를 교정하고 이전 deploy artifact·공개 JSON·브라우저 기준으로 실제 보존을 재검증했습니다.
- [x] Ubuntu collector 41개·최종 자동화 35개 root·일반 사용자 검사와 초기 비활성 설치·systemd 정적 검증을 완료했습니다.
- [x] API·웹 replicas 0의 중단에서 공개 홈·마지막 기록·DB·기존 Docker를 보존하고 같은 정상 B로 복원했습니다.
- [x] 전용 Pages 자격증명을 등록하고 수동 host cycle의 실제 Pages 게시·전체 공개 JSON 일치를 확인했습니다.
- [x] 실제 systemd service 실행 성공·상태 파일 root 0600·임시 SA 토큰 정리를 확인했습니다.
- [x] timer enabled·active와 최초 자동 trigger의 Pages 게시·전체 공개 JSON·브라우저를 확인했습니다.
- [x] 최초 자동 실행을 포함한 11회의 Pages build·deploy success와 실제 서비스 완료 간격을 검증했습니다.
- [ ] credential 실제 만료·회전과 장기간 운영을 검증합니다.
- [ ] 필요한 경우 기존 프록시·TLS를 확인한 뒤 읽기 API를 연결하고 휴대폰 외부망에서 확인합니다.

**완료 조건:** 정상 수집, collector 실패, Lab 중단 시나리오에서 표시 내용이 실제 관측 범위와 일치합니다. 공개 화면은 현재 JVM 정보와 별도 정적 관측·CI/CD 근거를 구분합니다. 실제 API·웹 replicas 0에서 공개 홈·마지막 기록 유지와 같은 정상 B 복원을 확인했습니다. 호스트·DB 전체 중단은 이 실험 범위가 아니며 오래된 기록·브라우저 조회 실패는 오프라인 UI 검증입니다.

**현재 확인한 결과:** [실제 수집·실패 후 보존·게시·브라우저와 반복 실행 11회](evidence/platform-observation/README.md)를 제공합니다. 게시 순서 회귀 교정과 API·웹 중단·같은 정상 B 복원, 수동 host cycle·실제 systemd service·timer 자동 실행을 검증했습니다. 반복 11회의 Pages build·deploy 결과와 실제 간격을 확인했으며 각 회차의 전체 공개 JSON·UI 비교를 모두 수행했다는 뜻은 아닙니다. 같은 마지막 intent 재전송 차단도 실제 확인했으며 전체 이력의 exactly-once 보장은 아닙니다. 장기간 운영과 credential 권한 범위 조회·만료·회전은 별도 확인 범위로 남깁니다.

## 4 Kafka와 객체 저장소

[최초 계획](plans/phase4-messaging-storage.md)의 DB·원본·Kafka·export 경계를 격리 검증한 뒤, 2026-10-15 미니 PC K3s에 Kafka·Garage·상시 worker를 GitOps로 처음 배포했습니다. 최초 배포 당시 내부 고정 fixture 두 작업이 각 12/7/3/2/0으로 완료됐고 결과·실패 파일 총 4개를 전체 Get·크기·SHA-256으로 확인했습니다. 실행 슬롯은 비었으며 Kafka offset 2·log end 2·lag 0을 확인했습니다. 기존 seed·V1 처리 시각·PVC와 Docker 전체 38개·실행 26개를 보존했습니다. [최초 배포·게시 근거](evidence/runtime-deployment/README.md)를 연결합니다.

이전 V2 운영 배포 당시 API·worker는 같은 source `6c5aff948770982dd44c8d44547131b3ccf6ddd9`의 지원 이미지였습니다. 별도 GitOps PR로 API·웹을 먼저 교체하고 worker를 뒤이어 교체한 뒤 내부 V2 fixture를 한 번 접수했습니다. 기존 여섯 작업을 보존한 채 V2의 입력 1,000 = 성공 500 + 실패 300 + 업무상 중복 200 + 대기 0, EXPORTED·슬롯 해제·Kafka offset 7/log end 7/lag 0을 확인했습니다. 당시 총 7작업·파일 14개이며, 실제 GET 21개는 기존 18개 객체와 새 원본·결과·실패 객체 3개를 합친 수입니다. [V2 운영 배포·공개 게시 근거](evidence/input-v2-deployment/README.md)는 당시 기록으로 보존하고, 이전 readiness 검증의 8작업·16파일·24객체는 [readiness 후속 근거](evidence/worker-readiness/CORRECTED_IMAGE.md)로 확인합니다.

이전 단계의 [DB](evidence/db-job-foundation/README.md), [원본 S3](evidence/s3-source-storage/README.md), [실제 결합](evidence/mariadb-s3/README.md), [Kafka 중단·재전달](evidence/kafka-redelivery/README.md), [export](evidence/result-export/README.md), [상시 실행기](evidence/continuous-runtime/README.md) 검증은 각각 당시 조건과 한계를 유지합니다. 최초 운영 배포 당시 기본 API 128개·웹 34개와 별도로 확인했으며, 새 수집·게시 코드는 실제 Ubuntu 검사 135개를 통과했습니다. 후속 V2 소스의 기본 API 검증은 140개이며 아래 격리 기능·자원 검증과 구분합니다.

- [x] 고정 12개 fixture의 시간 역순·잘못된 값·업무상 중복 처리와 독립 기대 결과를 명시했습니다.
- [x] 격리 Kafka·MariaDB·Garage에서 ACK 뒤·DB commit 전후 JVM 강제 종료·재전달 멱등·offset을 검증했습니다.
- [x] 실제 K3s의 별도 worker가 연속 두 작업을 처리하고 두 파일 확인 뒤 슬롯을 해제했습니다.
- [x] 별도 작업 관측에 상태·시각·입력 회계식·예상 파일 SHA/크기를 연결하고 실제 배포 기록을 Pages에 게시했습니다.
- [x] 새 job 관측의 실제 systemd service 성공·Pages 게시·공개 JSON 전체 일치, private 0600·임시 SA token 정리를 확인했습니다.
- [x] 기존 timer의 enabled·active와 30분 주기·최대 60초 임의 지연 설정을 복구했습니다.
- [x] 원래 timer의 새 job 자동 실행·Pages 게시 2회와 완료 간격 1개(1809.371239초), unit/collector 무변경·공개 JSON 전체 일치를 검증했습니다.
- [ ] 새 job 수집의 장기간 반복 운영·실제 자격증명 만료/회전을 검증합니다.
- [x] 실제 idle worker Pod를 UID 조건으로 정상 교체하고 STOPPED→새 RUNNING·정상 TERM 종료·기존 두 작업/파일/offset·다른 서비스 보존을 확인했습니다: [근거](evidence/runtime-recovery/README.md)
- [x] 교체 worker에 새 고정 fixture를 접수해 처리·EXPORTED·파일 2개 실제 Get·슬롯 해제·Kafka offset 3/lag 0을 확인하고 원래 두 작업 전체를 보존했습니다.
- [x] Kafka/Garage 전용 3PVC의 cold copy·외부 AES-256-GCM 사본 인증·반환 해시·새 PVC 전체 manifest 복원을 검증했습니다: [근거](evidence/runtime-pvc-restore/README.md)
- [x] 격리 정책의 실제 원본 접근 차단과 Kafka 3 record/offset·Garage 9개 inline 객체의 GET 일치를 확인했습니다.
- [x] clone에만 128KiB canary를 한 번 PUT해 물리 블록을 만들고, 추가 2PVC 복원·Pod 교체 전후 각 GET10을 확인했습니다.
- [x] 복제 Kafka도 정상 TERM 교체 후 같은 PVC·3개 record의 key/value/시각·offset 3·lag 0을 보존했습니다.
- [x] 최신 검증본·미완료·키를 보호하는 순수 계획기 31개 테스트·실제 dry-run 후보 0과 새 합성 PVC만의 실제 정리 경계를 검증했습니다.
- [x] 고정 12개 입력 3회에서 기존 cgroup 설정·CPU/RSS/PSS·디스크 snapshot·처리/export 지연을 관측했습니다: [근거](evidence/retention-resource-budget/README.md)
- [x] 격리 기능 IT 5개에서 정확히 1MiB인 V2 입력 3회·기존 V1, 2/8개 동시 접수의 한 슬롯 경합, 1,001개/1MiB+1 거부·재접수/충돌 경계를 검증했습니다: [근거](evidence/input-concurrency-load/README.md)
- [x] 별도 Linux Docker에서 1CPU·768MiB의 같은 candidate worker로 1,000개 입력 3회·원본/결과/실패 전체 GET 9개와 자원을 관측했습니다. 이 세 입력은 각각 99,600B이며 정확히 1MiB 검증과 구분합니다.
- [x] V2 지원 API·worker를 모두 운영에 교체한 뒤 내부 V2 한 건·기존 여섯 작업 보존·총 7작업/14파일·공개 JSON 일치를 확인했습니다: [근거](evidence/input-v2-deployment/README.md)
- [ ] 객체 tombstone/GC·과부하와 지속 부하의 한도는 별도로 검증합니다.
- [x] 별도 Linux Docker의 V2 작업에서 결과 파일 확인 후 실패 파일 PUT을 전달하기 전 worker를 한 번 강제 종료하고, 같은 jar의 새 worker가 미완료 export를 복구하는지 검증했습니다: [근거](evidence/maximum-export-crash/README.md)
- [ ] 다른 작업 경계의 중단·진행 중 호스트 재시작 범위를 별도로 검증합니다.
- [ ] 실패 데이터 재처리와 미완료 객체를 보존하는 명시적 정리 절차를 만듭니다.
- [ ] consumer lag의 자동 공개 관측·장기간 지연/자원 지표와 과부하 대응 정책을 검증합니다. 최대 1,000개와 2/8개 동시 접수 경계의 완료를 지속 처리량·rate limit 보장으로 확대하지 않습니다.

초기 실제 worker 정상 재시작 당시 관측 절차는 17.808초였고 새 Pod의 restartCount는 0입니다. 기존 두 작업의 전체 SQL·시각과 파일 4개의 전체 Get·크기·SHA, Kafka offset 2·log end 2·lag 0이 유지됐습니다. 23개 보존 검사에서 다른 5개 Pod·Docker 전체 38개/실행 26개·전체 PVC 6개/Lab 4개·호스트 상태를 확인했습니다. 이 범위는 작업이 없는 정상 TERM 교체이며 진행 중 crash·PVC 복원·고가용성 검증으로 확대하지 않습니다.

그 정상 재시작의 후속 검증 당시 교체된 worker에 별도 고정 fixture `lab-fixture-20261015-recovery`를 접수해 입력 12 = 성공 7 + 실패 3 + 업무상 중복 2 + 대기 0, EXPORTED와 슬롯 해제를 확인했습니다. 새 결과·실패 파일 2개도 실제 Get의 전체 내용·크기·SHA-256을 대조했습니다. 전체 작업은 3개·확인 파일 6개가 됐고 Kafka offset 3·log end 3·lag 0입니다. 원래 두 작업의 전체 SQL·시각·HTTP 요약과 파일 4개는 그대로 보존했습니다.

원본 전용 PVC 3개의 외부 사본 복원과 별도 clone 물리 블록 복원을 구분했습니다. 원본의 9개 객체는 모두 inline이므로, data 블록 복원은 clone 전용 128KiB canary로 별도 입증했습니다. 원본 객체 쓰기·운영 PVC 덮어쓰기는 하지 않았고 시험 대상 5PVC의 요청량은 총 29Gi입니다. 이 요청량은 실제 사용량이나 처리 용량 측정이 아닙니다. 시험용 workload 3개를 정상 종료해 Pod 0개·Retain PVC 5개를 남겼습니다. 최종 보존 검사 28개에서 원본 SQL·작업/파일 정보·PVC 6개·Ready Pod 6개와 기존 Docker 38개/실행 26개의 상태를 확인했습니다. [실행 절차](runbooks/runtime-pvc-recovery.md)를 따릅니다.

이후 고정 12개 입력의 자원 관측 당시 세 작업을 추가해 총 6개 EXPORTED 작업·파일 12개의 전체 Get·Kafka offset 6/lag 0을 확인했습니다. 약 63초·64개 샘플의 worker 작업 구간 평균 CPU는 0.04235 core, 약 1초 관측 최대는 0.66622 core였습니다. DB 생성→export 기록 평균은 1.5943초지만 cold stage 요청부터는 14.0757초로, 시작·접수 비용을 구분했습니다. 11분 디스크 snapshot의 active PVC 증가 972KiB는 heartbeat/WAL 영향을 포함합니다. [정의·조건·한계](runbooks/retention-resource-budget.md)를 함께 읽으며 처리 용량이나 SLA로 확대하지 않습니다. 최종 25개 검사에서 기존 11PVC/PV·원본 Pod 6개·Docker 38개/실행 26개·기존 업무 SQL/객체·timer 설정과 주기 보존도 확인했습니다.

격리 Linux의 V2 export 경계 검증은 12개 검사를 통과했습니다. 첫 결과 파일의 PUT·전체 GET을 확인하고 두 번째 실패 파일 PUT을 upstream에 전달하기 전에 해당 worker만 한 번 SIGKILL했습니다. exit 137·비 OOM을 확인한 뒤 같은 source/jar의 새 worker가 PENDING export를 완료했고, 처리 SQL·시각과 첫 결과 파일 전체 바이트, 기존 네 작업/12개 객체와 이전 Kafka offset을 보존했습니다. 새 작업의 offset 1/log end 1/lag 0·슬롯 해제와 소유 컨테이너의 종료를 확인했습니다. 이 검증은 독립 Docker 환경의 한 export 경계이며 운영 K3s 중단·호스트 재시작·고가용성을 입증하지 않습니다. [전체 근거](evidence/maximum-export-crash/README.md)를 연결합니다.

이전 V2 배포 후 수동 수집·Pages 게시에서도 실제 job·플랫폼 공개 JSON 전체가 수집 원본과 일치했습니다: [당시 게시 근거](evidence/input-v2-deployment/README.md). 그보다 앞선 재시작 검증에서는 새 job의 원래 timer 자동 수집·게시 2회와 완료 간격 1개(1809.371239초)를 확인했습니다. [후속 검증 근거](evidence/runtime-recovery/README.md)는 과거 플랫폼 collector 11회와 구분합니다. 공개 화면은 약 30분 주기의 마지막 기록이며 실시간 조회가 아닙니다. 5분 heartbeat 경고는 마지막 실행 신호의 나이이고 프로세스 중단 판정이 아닙니다. 공개 POST는 없고 내부 `--lab-runtime=stage`가 고정 fixture만 접수합니다.

**완료 조건:** producer ACK·DB 멱등 처리·offset·export 확인을 각각 설명하고 실제 운영 한계를 기록합니다. 단일 노드·partition 1/RF1을 고가용성이나 전체 exactly-once로 표현하지 않습니다. [Kafka producer 설정](https://kafka.apache.org/42/configuration/producer-configs/)

## 5 AI를 활용한 Java 개선

[개인 합성 Java 시간창 예제](../examples/java-window-analysis/README.md)를 구현했습니다. 회사 수율 공식·업무 데이터·운영 ETL은 사용하지 않았습니다. UTC offset을 버리는 의도적 오류를 0초와 올바른 10초로 고정하고, 동일 정규화 입력을 O(n²) 기준 구현과 O(n log n) sweep으로 계산합니다.

- [x] UTC·시계 오차·인접/중첩·clipping 경계와 독립 정수 격자 oracle 2,000사례를 포함한 Java 테스트 20개
- [x] AI에 제공한 비민감 합성 입력과 채택/제외한 설계 범위 기록: [PROVENANCE](../examples/java-window-analysis/PROVENANCE.md)
- [x] sparse/nested × 128/512/2048/4096의 닫힌 형태 기대값과 두 구현의 동일 결과 검증
- [x] 독립 JMH 1.37의 실제 Windows Java 21·3 fork·1 thread·256MiB/G1 측정: 16조합·48 fork·240 interval과 원본 hash 보존
- [x] 전후 코드, 선택한 fixture의 기대 결과·ns/op·B/op·큰 오차·측정 조건을 정적 포트폴리오에 연결: 웹 41개·check/build, [실제 근거](evidence/ai-window-analysis/README.md)
- [x] CI에 예제 verify·runner 검사와 필수 JAR guard 연결, 로컬 guard 검사 2개와 실제 Jenkins Declarative linter 확인: [검증 범위](evidence/ai-window-analysis/ci-validation.md)
- [x] [TIL의 UTC 구간 계산 사례](https://devdooly.github.io/TIL/LLM_Development/UTC_Window_Analysis_Case/)로 연결: 문서 검사 42개·strict build 후 게시
- [ ] 저장소 소유자의 사람 검토와 실제 채택 판단

**측정 한계:** UTC 파싱·정규화는 trial setup으로 제외했습니다. sparse/2048 기준 구현은 평균 11,933us에 JMH 오차 10,205us로 큰 분산이 포함됩니다. 이 짧은 로컬 합성 비교를 운영 처리량·p95·SLA·보장 개선율로 사용하지 않습니다. 측정 당시 미커밋 sourceCommit:null과 실제 source manifest/JAR/fixture/raw JSON hash를 유지하며, 사람 검토는 PENDING입니다. CI에서는 성능 benchmark를 재실행하지 않습니다.

**완료 조건:** 다른 개발자가 같은 테스트·측정 명령과 공개 근거를 확인할 수 있습니다. 구현과 측정 기록을 연결했으며 사람 검토 완료로 바꾸지 않습니다. [OpenJDK JMH 안내](https://github.com/openjdk/jmh)

## 6 Iceberg와 Trino

서로 분리한 두 작은 합성 시험을 완료했습니다. [미니 PC native7](evidence/iceberg-jdbc/README.md)은 PostgreSQL JDBC catalog·Garage와 Trino의 조회·재시작을 검증했고, [독립 Cloud Spark 시험 8](evidence/spark-silver/README.md)은 Spark 적재·Silver 변환·같은 application의 순차 replay를 검증했습니다. Spark·Trino의 상시 운영과 두 시험의 warehouse 연결은 검증하지 않았습니다.

이후 2026-10-16 03:12:33 UTC의 [새 Cloud 시험](evidence/cloud-lakehouse/FULL_SUCCESS.md)은 fresh JDBC catalog·Garage·warehouse에서 Spark→Trino와 작은 compaction을 검증했습니다. 기존 두 시험의 warehouse를 연결하거나 미니 PC를 변경한 것이 아닙니다.

- [x] native7에서 영속 JDBC catalog·객체 저장소를 연결하고 0→6→12행과 초기 빈 snapshot 1개 + 데이터 append 2개를 확인했습니다.
- [x] Trino만 정상 재시작한 뒤 같은 행·metadata pointer·warehouse bytes를 비교했습니다. PostgreSQL은 같은 프로세스를 유지했습니다.
- [x] Cloud Spark에서 Bronze 6+6행·snapshot 2개, Silver 성공 7·실패 3·중복 2와 동일 입력의 순차 replay write 0회를 확인했습니다. 재시작·동시성 검증과 구분합니다.
- [x] 새 Cloud warehouse의 Spark 결과를 Trino 10개 조회로 대조하고 6→12→12행·동일 최종 row hash를 확인했습니다: [근거](evidence/cloud-lakehouse/FULL_SUCCESS.md)
- [x] 현재 Bronze 파일 2개→1개의 rewrite procedure 1회와 기존 객체 14개 보존·Trino 뒤 객체 20개 전체 대조를 확인했습니다.
- [x] 현재 DB의 a7 논리 백업·격리 복원에서 8개 테이블 스키마·비runtime 7개 테이블의 행·BLOB과 원본 보존을 확인하고 기록·카드를 PR #61로 공개했습니다: [범위와 종료 한계](evidence/current-db-restore/README.md)
- [x] [9차 새 closed-copy capture](evidence/iceberg-capture/ATTEMPT_9.md)의 source `5862ba0c`에서 Linux87·skip0과 actors·clock 통합 검증 → graph closure·normalization → 완전 inventory → 순수 planner 입력 연결을 확인했습니다. 스냅샷3·참조1·보호 항목1·객체20을 관측했고 모든 객체 KEEP입니다. 이전1–8의 실패·null과 합성 검증은 보존하며 삭제·만료·운영 규모 검증으로 확대하지 않습니다.
- [ ] snapshot 보존·만료 정책과 운영 규모 compaction 검증을 이어갑니다.

**완료 조건:** 같은 warehouse의 적재·조회·재시작·compaction과 재실행 방법을 연결해야 합니다. 새 Cloud의 연결·작은 compaction은 완료했지만 같은 Cloud 환경의 재시작·snapshot 보존 정책·전체 6단계는 완료하지 않았습니다. 현재 DB의 a7 논리 복원은 완료했지만 원래 stop은 실패이고 정상 exit는 UNOBSERVED입니다. 별도 읽기 진단의 DB replicas 0·Pod 0·Bound/Retain 확인과 전체 애플리케이션 복구 미검증을 구분합니다. [9차 capture](evidence/iceberg-capture/ATTEMPT_9.md)의 graph·inventory와 KEEP 계획 연결은 완료했으며, 기존 native7 재시작 기록과는 별도 실행으로 구분합니다. 운영 규모·삭제·만료 검증을 완료한 것은 아닙니다. [실제 Cloud 범위](evidence/cloud-lakehouse/FULL_SUCCESS.md)

**공개 결과:** 수집부터 저장·조회까지 한 데이터의 흐름을 따라가는 설명입니다. Airflow는 실제 스케줄링과 재시도 관리가 필요해질 때 추가합니다.

## 장비 자원과 학습

미니 PC는 단일 노드이며 기존 Docker 서비스와 함께 사용합니다. 확장 전후의 메모리 여유·디스크 증가량·기존 서비스 응답을 측정해 자원 예산을 정합니다. Jenkins agent 동시 실행 1개를 유지하고 이미지·빌드 산출물·로그의 보존 상한을 둡니다. 무거운 배치 실험과 CI 이미지 빌드는 겹치지 않게 실행합니다.

CKA 학습은 Lab과 연결합니다. context·RBAC·Service와 DNS·probe·requests/limits·PV·장애 진단을 직접 실습하고 TIL에 재현 방법을 남깁니다. 시험 합격 전에는 프로필의 표기를 준비 중으로 유지합니다.

## 내부 접수 간격 후보 검증

DB의 기본 30초 승인 간격을 실제 V4 API→worker 순서로 배포했습니다. 기본 157개·격리 MariaDB/Garage 19개·복원본 이전 binary 호환 8개는 [기존 근거](evidence/admission-cooldown/README.md)에 보존합니다. source `202ab6806130cfb37e8829ce7d52c89990d8a54a`의 [실제 전환](evidence/admission-v4-deployment/README.md)은 API·웹 32/32와 worker 35/35, 기존 7작업·파일 정보 14개 보존을 확인했습니다. Kubernetes Ready와 runtime 준비는 구분하며 첫 32/35 관측·이전 exit UNOBSERVED를 남깁니다. 11:40:08.792Z의 정기 V4 수집은 [Pages 실행](https://github.com/DevDooly/devdooly-platform-lab/actions/runs/38728965840) 성공 후 공개 JSON 전체 일치를 확인했습니다: [정기 게시 후속](evidence/admission-v4-deployment/PUBLICATION.md). 후속 고정 V1 fixture 접수·charged30·슬롯 해제·자료 보존과 idle worker 교체·같은 ID 읽기 전용 재시도를 [최신 근거](evidence/worker-readiness/CORRECTED_IMAGE.md)에서 확인했습니다. 서로 다른 ID의 실제 cooldown 거부는 별도 미검증입니다. [전환·원복 절차](runbooks/admission-cooldown.md)를 따르고 구형 stage와 혼용하지 않습니다. 지속 부하·HTTP QPS 제한·처리 중 호스트 장애 복구는 별도 미검증입니다. charged cooldown 상태의 idle worker 교체는 readiness 후속 근거에서 확인했으며 이전 worker exit는 UNOBSERVED입니다.

## 이전 작업 후보 — 2026-10-18 당시

아래는 당시의 계획을 보존한 기록입니다. 현재 실행 순서와 보류 여부는 이 문서 맨앞의 최신 안내를 따릅니다.

1. **실제 metadata 보존 계획의 공개와 다음 검증 분리:** [9차 새 실행](evidence/iceberg-capture/ATTEMPT_9.md)의 Linux87·skip0·필수 검증9개와 객체20개 KEEP 결과를 화면·회귀 검사로 연결합니다. 앞선 실패와 null은 그대로 남깁니다. 이후 보존 정책·운영 규모 compaction과 다른 장애 경계를 독립적으로 검토하며 snapshot 만료·객체 삭제를 이번 capture의 완료 조건으로 확장하지 않습니다.
2. **보존 운영과 객체 GC:** 전체 운영 참조21개 KEEP·후보0과 새 Garage의 합성 객체2개 자연 GC를 확인했습니다. [객체 보호 근거](evidence/object-reference-gc/README.md)의 범위를 유지하며 운영 tombstone·삭제 intent·재전달/resume·백업 의존성을 설계합니다. 운영 삭제 실행기와 metadata DB 축소는 구현하지 않았습니다.
3. **검증 확대:** 최대 1,000개 입력·2/8개 동시 접수와 격리 Linux 3회의 관측, 한 export 경계의 worker 강제 종료 복구는 완료했습니다. 다음은 다른 장애 경계·진행 중 호스트 중단·지속 부하·과부하 거부 정책입니다. 한 슬롯 경합은 rate limiter가 아니며 작은 표본을 처리 용량·SLA로 표현하지 않습니다. 공개 실행은 열지 않습니다.
4. **장기간 수집 운영:** 원래 timer의 자동 게시 2회·실제 간격 1개는 확인했습니다. 더 긴 반복·실패 후 이전 기록 보존·자격증명 만료/회전을 이어서 검증합니다. 초기 관리자 비밀번호 교체·K3s/Jenkins archive 전체 복원도 별도 운영 후속입니다.
5. **이후 확장:** 격리 export 경계의 worker 강제 종료 복구와 기존 idle 정상 교체를 구분하고, 진행 중 호스트 재시작·고가용성은 별도 미검증으로 남깁니다. AI 개선 사례는 5단계의 독립 합성 예제로 연결합니다. 공개 실행은 내부 고정 fixture 명령으로 제한하며 새 inbound 경로는 필요성을 먼저 판단합니다.

각 결과는 소스 변경, 실행 방법, 실제 검증 결과, TIL 설명, 포트폴리오 링크로 연결합니다. 작업 완료 시 [진행 목록](ROADMAP.md)을 갱신하고 프로필에는 구현한 범위만 반영합니다.
