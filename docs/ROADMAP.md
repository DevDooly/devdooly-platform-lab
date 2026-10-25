# 단계별 작업과 완료 조건

## 기능 개발 우선순위 — 2026-10-25 KST

[PR259](https://github.com/DevDooly/devdooly-platform-lab/pull/259)의 [작업·export 기록 흐름](features/job-lifecycle.md), [작업 목록 탐색](features/job-list-filter.md), [PR264](https://github.com/DevDooly/devdooly-platform-lab/pull/264)의 [센서 이벤트 연결](features/sensor-outcomes.md#센서에서-이벤트로-이동), [PR267](https://github.com/DevDooly/devdooly-platform-lab/pull/267)의 센서별 A·B 비교에 이어 [PR269](https://github.com/DevDooly/devdooly-platform-lab/pull/269)의 **입력 순서별 이벤트 응답 비교**와 [PR271](https://github.com/DevDooly/devdooly-platform-lab/pull/271)의 **저장 JSON 오프라인 이벤트 비교**를 공개했습니다. 새 파일 비교의 웹490개·타입·빌드·같은 main CI/Pages·공개 실제 파일 조작/모바일은 [기능 문서](features/offline-event-comparison.md#검증-상태)에 구분했습니다. PR269의 최초 로컬 병렬 Kafka1개 실패는 원인 미확정으로 보존합니다. 완료 기능·운영 시험을 반복하거나 보류 항목을 재개하지 않습니다.

[PR274](https://github.com/DevDooly/devdooly-platform-lab/pull/274)의 **현재 조건 비교 보고서 JSON 저장**을 공개했습니다. 최종 웹505개·타입·빌드와 같은 main CI/Pages·공개 실제25/1그룹 보고서 다운로드·모바일을 확인했습니다. [보고서 검증 범위](features/offline-comparison-report.md#검증-상태)에서 로컬0그룹/잘못된 새 파일 경계·독립 검토 후 읽기 잠금 보완과 구분합니다. 보고서는 전체 일치 그룹·모든 후보와 원파일 메타데이터/화면 조건을 나누며 기존 이벤트 v1/v2·원파일 bytes·진위 인증·세션 복원과 다릅니다.

현재1은 **합성 예제 파일 두 개 받기**를 구현·검증하는 범위입니다. 파일 없는 첫 방문자가 작은 fixture·시각null의 v1/v2를 내려받아 기존 선택·비교·보고서 저장을 체험합니다. 5그룹·다섯 분류 각1개와 실제 운영 기록의 차이는 [예제 안내](features/offline-event-samples.md)를 따릅니다. 로컬·정확 source·main CI/Pages·공개 결과는 수행한 범위만 기록합니다. [현재 우선순위](AUTONOMOUS_WORK.md#다음-작업의-우선순위)의 한 기능만 진행하며 기존 온라인 조회·공유·내보내기 형식과 운영 pin·네 보류를 유지합니다.

아래 목록은 앞서 구현한 이용 기능이며 새로 재수행하는 순서가 아닙니다.

1. [두 실행 결과 비교](features/run-comparison.md): 저장된 A·B의 건수·비율·실패 사유, 공유 링크와 CSV를 제공하는 웹 기능입니다. 기존 GET만 사용하며 운영 image/source pin은 유지합니다.
2. [API 안내에서 목록 선택으로 상세 조회를 연결](features/api-run-selection.md)합니다. 목록을 불러오고 ID를 고르는 동작과 실제 상세 GET을 구분합니다.
3. [이벤트 판정 흐름 탐색](features/event-flow.md): 기존 이벤트 상세에서 응답 필드·판정 사유·결과 분류를 함께 봅니다. 원래 출처·시각을 유지하고 고정 Java 규칙 해설과 실제 단계별 trace를 구분합니다.
4. [이벤트 검색·사유 필터](features/event-search.md): 이미 읽은 최대 1,000건의 eventId·sensorId 문자 부분 검색과 원시 reason 정확 선택을 기존 status 조건과 함께 적용합니다. 표·흐름 목록은 같은 결과와 입력 순서·중복 행을 유지합니다. 웹310개·타입·빌드와 로컬 실제 검색을 확인했으며 병합 main의 CI·Pages·공개 결과는 별도 기록합니다.

현재 상태와 네 보류는 [현재 범위·다음 작업](AUTONOMOUS_WORK.md)을 따릅니다. 아래 역사적 검증·체크리스트를 재수행하는 계획이 아닙니다.

## 현재 우선순위 — 2026-10-23 KST

현재 완료·보류와 이어갈 순서는 [현재 범위·다음 작업](AUTONOMOUS_WORK.md)을, 실행별 이력은 [다음 개발 계획](NEXT_STEPS.md)을 따릅니다. 아래 단계별 체크리스트는 날짜가 다른 실행의 기록이며, 과거의 미완료 표시를 현재 할 일로 다시 실행하지 않습니다.

| 구분 | 현재 확인한 범위 |
| --- | --- |
| Jenkins App 인증 | [실제 만료 후 lazy refresh 한 주기](evidence/github-app-jenkins/NATURAL_EXPIRY.md): 기존 토큰 401 → native 접근 1회 → 새 토큰 200·저장소 일치·유효기간 1시간과 기존 job·설정·비밀 입력 보존을 확인했습니다. 선제·주기 발급·키 교체·권한 철회 복구는 미검증입니다. 원래 만료 시험은 빌드를 포함하지 않았으며, 이후 별도 Jenkins153의 App 상태 pending→success와 공개 카드 확인은 [후속 근거](evidence/github-app-jenkins/PUBLICATION.md)로 구분합니다. 상태 전달만으로 전체 CI 단계·산출물을 재검증했다고 보지 않습니다. 다음 순서는 [현재 안내](AUTONOMOUS_WORK.md)를 따릅니다. |
| 완료한 격리 검증 | Kafka backlog·offset commit 실패 복구·손상 export 수리·잘못된 메시지 보호·실행 잠금 손실 검증. 특히 [잠금 손실](evidence/runtime-lease-loss/README.md)은 stale `RUNNING / EXPORT`와 실제 종료를 구분합니다. |
| 완료한 데이터·탐색 구현 | [같은 PostgreSQL의 정상 stop/start](evidence/cloud-catalog-restart/README.md) 뒤 catalog·조회·전체 객체 보존을 확인했습니다. 근거 목록의 검색·필터·6개씩 더 보기는 웹173개 검사·타입·빌드와 같은 main의 Pages·CI, 로컬·공개 화면 확인을 마쳤습니다. |
| 사례·운영 문서 | [별도 잠금 손실 사례](https://devdooly.github.io/devdooly-platform-lab/cases/runtime-ownership/)의 공개·키보드·모바일 확인을 마쳤습니다. 장애별 판단표와 AI 소유자 검토자료를 정리했으며, 세부 근거와 다음 순서는 [최신 안내](NEXT_STEPS.md)를 따릅니다. |
| worker·공개 관측 | [PR177의 worker 교체](evidence/worker-image-rollout/README.md)는 main33c5e8c·source6f551a1·image ee713에서 Argo Synced·Healthy·새 Pod Ready를 확인했습니다. API245d61a·웹 image029c는 유지합니다. [후속 GET39521322979](evidence/public-get/README.md)의6개 HTTP200·API245d61a와 별도 공개 UI의 새 worker 소스·시작·heartbeat 관측을 구분합니다. GET artifact 자체는 worker 생존의 증명이 아닙니다. |
| 자동 게시 | 기존 약30분 timer의 [새 worker 수집·Pages39523423769 게시](evidence/worker-image-rollout/NATURAL_PUBLICATION.md)를 확인했습니다. main6b62821의 build·deploy가 성공했고 공개 관측3개가 artifact 원문과 같았습니다. API245d61a와 runtime6f551a1·원 시각을 구분하며 수동 dispatch·timer 강제 실행은 하지 않았습니다. |
| 자동화·다음 | [관측·DDNS 코드 두 개](evidence/automation-failure-boundaries/DEPLOYED.md)의 자연 회차·Pages 연결을 확인했습니다. [새 worker의 고정 입력 한 건](evidence/current-worker-fixture/README.md)은12/7/3/2/0·COMPLETED/EXPORTED, 새 객체3개 검증·기존8작업/24객체 보존과 완료된 임시 Job의 선택 정리를 확인했습니다. 원래 자연 주기의 [Pages39532314754](https://github.com/DevDooly/devdooly-platform-lab/actions/runs/39532314754) build·deploy·공개 JSON3개 일치와 새9작업 반영도 확인했습니다. [현재 공개 HTTPS 재관측](evidence/public-get/README.md)은 run39533662559에서 지정 GET6개 모두 HTTP200·DTO 검증을 통과했습니다. 실행 결과는 [ID·입력 건수와 전체 ID](evidence/run-selection/README.md)로 구분하도록 수정했고 로컬 화면 확인을 마쳤습니다. [요청·응답 ID 일치](evidence/run-response-identity/README.md) 수정의 로컬209개·타입·빌드와 공개 정상 선택을 확인했습니다. [100개 센서 범례 줄바꿈](evidence/chart-legend-wrap/README.md)도 공개 데스크톱·모바일에서 확인했고, 기본 URL은 reload·실시간 조회 후 정상 폭을 확인했습니다. 첫 조회 실패의 [유한 진단](evidence/initial-read-diagnostics/README.md)은 로컬223개·타입·빌드와 같은 main의 Pages·CI, 공개 정상 첫 조회·실행 선택 확인을 마쳤습니다. 과거 fallback 원인은 여전히 미확인입니다. 이번 후속에서 추가 운영 실행은 하지 않았으며, 실패가 다시 발생하면 유한 진단 정보를 관측합니다. |
| 보류 | 별도 격리 환경이 없어 K3s·Jenkins 실제 기동 복원을 보류합니다. Pages 토큰 교체, 자원 예산 정책, [PR102 접수 gate](https://github.com/DevDooly/devdooly-platform-lab/pull/102) 활성화도 보류합니다. 현재 공개 경로의 재부팅·인증서 자연 갱신은 미검증입니다. |

## 이전 안내 — 2026-10-18 UTC 검증 반영

현재 상태는 이 안내와 연결된 최신 근거를 우선합니다. 아래 **이전 계획과 검증 기록**은 각 수집·작성 시점의 기록이며, 당시의 “미실행·미연결”과 미완료 체크를 최신 상태로 해석하지 않습니다. 한국 시각으로 10월 19일에 해당하는 후속 검증도 포함합니다.

- **새 Cloud snapshot 만료:** [실행 39140688897의 근거](evidence/cloud-iceberg-expiration/README.md)에서 snapshot 1개 만료와 data·manifest·manifest list 각 1개 삭제, tag·공유 파일·current 18행·Silver 12행 보존을 확인했습니다. 미니 PC에 접속하지 않고 새 합성 warehouse만 사용했습니다.
- **공개 HTTPS와 live 조회:** [외부 HTTPS·공개 화면 근거](evidence/public-read-https/README.md)에서 표준 TLS·허용 GET 6개·지정 거부 3개를 확인하고, Pages의 실시간 작업 8개·Kafka 조회 연결과 시계 경고 표시·해소를 대조했습니다. 공개 POST·관리 도구·실행 기능은 제공하지 않습니다.
- **격리 Kafka ACL:** [실제 격리 시험](evidence/kafka-acl/README.md)에서 DESCRIBE 관측 profile의 조회와 선택 RPC 거부 5개·잘못된 비밀번호의 인증 실패 1개를 확인했습니다. 운영 Kafka 권한이나 TLS 기밀성 검증은 아닙니다.
- **저장된 snapshot 관측 화면:** 저장된 만료 전 4/25·만료 후 3/23(snapshot/객체 수)의 [전후 비교 화면](https://devdooly.github.io/devdooly-platform-lab/#snapshot-expiration)을 공개하고 전후 전환을 확인했습니다([PR120](https://github.com/DevDooly/devdooly-platform-lab/pull/120), [Pages 39142668759](https://github.com/DevDooly/devdooly-platform-lab/actions/runs/39142668759)).

**다음·보류:** DB와 Garage의 공유 filesystem은 읽기 전용으로 확인했지만, quota·자원 예산·실제 앱 reader·회계 연결이 미확정이므로 [PR102 접수 gate](https://github.com/DevDooly/devdooly-platform-lab/pull/102)는 미연결·보류입니다. 운영 자료의 만료/GC, 장기간 가용성·성능 SLA, 작업 진행 중 호스트 장애·HA는 미검증입니다. 휴대폰 외부망 확인·인증서 자연 갱신·자격증명 회전도 위 hosted/browser 결과와 별도 범위로 남깁니다.

## 이전 계획과 검증 기록

체크된 항목은 확인된 결과가 있는 작업입니다. 계획 단계의 기능에는 체크하지 않습니다. 현재 로컬·Linux runner 검증과 미니 PC의 K3s·Jenkins·Argo CD 실행을 확인했으며, 실제 근거와 남은 작업을 구분합니다. 각 항목은 실제 검증과 함께 갱신합니다. 우선순위와 구체적인 다음 결과물은 [다음 개발 계획](NEXT_STEPS.md)을 따릅니다.

최근 배포·보존 확인(2026-10-16 갱신): 소스 `74a8e988`의 [Actions](https://github.com/DevDooly/devdooly-platform-lab/actions/runs/38814779596)와 Jenkins 45에서 API 191개 + 독립 Java 예제 20개, 총 211개를 통과했습니다. 이어 PR #52의 API·웹과 PR #53의 worker를 실제 전환했습니다. 애플리케이션 소스는 `74a8e988`, 최종 GitOps revision은 `b63fedfa`입니다. 2026-10-15 23:12:57 UTC의 배포 후 검사에서 작업 8개·export 정보 16개, 기존 객체 24개 + native7 객체 12개의 전체 GET, PV·PVC 각 13개·Docker 60개와 Kafka offset/end 8·lag 0을 확인했습니다. [S3 전송 배포·보존 근거](evidence/s3-runtime-rollout/README.md)는 해당 시점의 기록이며 실시간 가용성을 뜻하지 않습니다.

후속 별도 JVM SDK 검증에서는 실제 배포 JAR의 factory와 Apache5로 알려진 객체 3개를 전체 GET했습니다. 3회 호출·3회 시도·추가 retry 0회, client 종료·정상 exit 0과 자기 Job·ConfigMap·Secret·읽기 전용 key의 정리·폐기를 확인했습니다. factory의 maxAttempts 3은 유지했습니다. 운영 API JVM 내부의 호출·장애 주입·PUT·SLA 검증과 구분합니다. 2026-10-16 00:02:58 UTC의 별도 읽기 검사에서 전체 객체 36개와 업무 SQL·기존 리소스 보존, 임시 SDK 자원·키 부재를 확인했습니다.

## 저장소 준비 완료

- [x] 프로젝트 이름과 로컬 저장소 위치 결정
- [x] 전체 계획과 첫 기술 결정 정리
- [x] 시작 안내, 환경 점검 절차와 검증 양식 작성
- [x] Git 초기화와 문서·디렉터리 안내의 초기 커밋
- [x] GitHub origin 연결과 main 최초 push

## 0 기존 환경 확인

- [x] Ubuntu 버전·지원 상태, CPU·메모리·디스크 확인
- [x] 기존 서비스·컨테이너·포트와 데이터 경로 조사
- [x] SSH 접속 방법과 서버 지문 확인
- [x] 백업 현황과 별도 백업 위치 결정: [외부 암호화 백업](evidence/recovery/README.md)
- [ ] 기존 DDNS·공인 IP·CGNAT 여부와 HTTPS 선택지 확인
- [x] 설치 경로·PV 경로·자원 예산·원상 복구 범위 기록

완료 조건: 기존 서비스에 미칠 영향을 설명하고, 보존할 데이터와 새로운 설치 범위를 정할 수 있습니다.

## 1 최소 서비스와 포트폴리오

- [x] Java·Spring Boot·빌드 도구·Node·Astro 버전 선택과 고정
- [x] 합성 데이터 schema, seed와 독립적인 기대 결과 정의
- [x] Spring Boot 샘플 결과 조회 API, JPA·Flyway 구현과 H2 검증
- [x] Linux runner의 MariaDB 실제 연결·컨테이너·API 교체와 멱등 검증: [근거](evidence/compose-ci/README.md)
- [x] 입력 검증·중복·시간·실패 시나리오 확인: API 테스트 15개 통과
- [x] Astro·React Lab 조회 화면과 로컬 API 연결: 테스트 13개·타입 검사·HTTP smoke 통과
- [x] 공개 포트폴리오 저장소와 Pages 주소 확인
- [x] GitHub Actions 최초 게시 성공과 외부 화면 검증: [공개 기록](evidence/web-mvp/README.md)
- [x] 소개·기술 경험·프로젝트 설명과 기존 TIL 연결
- [x] 테스트 결과와 공개 가능한 샘플 결과 기록

완료 조건: 동일 샘플의 기대 결과를 반복 검증할 수 있고, 화면에서 현재 구현 범위와 설계를 이해할 수 있습니다.

근거: [API 검증](evidence/api-mvp/README.md), [화면 검증](../apps/lab-web/VALIDATION.md), [Pages 게시](runbooks/pages.md). 1단계의 로컬·임시 Linux 컨테이너와 Pages 검증을 마쳤습니다. 미니 PC 운영 결과는 [실제 서버 근거](evidence/mini-pc/README.md)에 별도 기록합니다.

## 2 K3s와 CI 및 CD

- [x] 점검 결과에 맞춰 K3s와 namespace·자원 설정 구성
- [x] Jenkins controller executor 0, 별도 agent·테스트 pipeline 정의 작성
- [x] Jenkins 실제 Kubernetes agent·테스트·패키징 성공 확인: [근거](evidence/jenkins-ci/README.md)
- [x] 실제 JUnit 실패·failure status·Actions 검증 실패에서 이미지·PR·배포 차단과 기존 B 보존 확인: [근거](evidence/cicd-gate/README.md)
- [x] Actions 이미지 빌드·GHCR 게시·digest 기록과 서버 익명 다운로드
- [x] API·화면·MariaDB 앱 Helm chart 작성과 lint·render 검증: [근거](../infra/charts/platform-lab/ci/render-validation.json)
- [x] 기존 저장소 gitops/에 실제 image digest·환경 values·Application 연결: [결정](adr/0003-gitops-in-existing-repository.md)
- [x] 같은 source SHA의 Jenkins·Actions 검증 → Actions 단일 게시 → draft GitOps PR 연결: [절차](runbooks/cicd-publication.md)
- [x] Argo CD 동기화와 실제 서비스 버전 확인
- [x] 고정 image digest의 정상 배포와 Argo CD Synced·Healthy 확인
- [x] 정상 B 배포에서 source·OCI digest·GitOps commit·실행 이미지와 데이터 보존 연결: [근거](evidence/cicd-gate/README.md)
- [x] GitOps 값을 이전 정상 A digest·source로 복구하고 Argo Synced·Healthy, HTTP·전체 SQL·처리 시각·DB/PVC·기존 서비스 보존 검증: [근거](evidence/cicd-gate/README.md)
- [x] 재부팅 복구와 필요한 설정·데이터의 외부 백업 확보: [실제 검증](evidence/recovery/README.md)

완료 조건: 소스 commit부터 image digest, GitOps commit, 실행 버전까지 추적되고 실패·복구 결과가 남습니다.

정상 A → B 배포, 실제 main의 실패 차단, GitOps A 복구를 확인했습니다. 2단계의 세 운영 시나리오를 완료했고 3단계 관측 공개를 진행합니다. token의 실제 만료·회전, 공개 요청 빈도 제한과 K3s·Jenkins archive 전체 복원은 별도 운영 후속으로 남깁니다.

## 3 외부 공개

아래 자동 게시 11회와 실제 간격은 2026-10-12 기존 플랫폼 수집기의 검증이다. 새 job 수집 코드의 자동 게시 2회·실제 간격 1개는 4단계에 구분한다.

- [x] 관리 도구의 SSH 인증 접속과 localhost 화면 응답 검증 ([접속 안내](runbooks/admin-access.md))
- [ ] 미니 PC 공개 Lab의 HTTPS 경로와 실시간 API 연결
- [x] 공개 플랫폼 관측의 strict allowlist 계약·validator와 읽기 전용 collector 구현: [계약](../apps/lab-web/PLATFORM_OBSERVATION.md)
- [x] 전용 ServiceAccount로 지정 Deployment·DB StatefulSet·Pod 준비 상태·Argo와 main의 Jenkins status 실제 수집: [근거](evidence/platform-observation/README.md)
- [x] 실제 읽기 권한 허용·거부, 출력 0600, 인증 실패 때 마지막 성공 전체·시각 유지 및 회복 확인: [근거](evidence/platform-observation/summary.json)
- [x] collector 실패·브라우저 조회 실패·2시간 초과·출처 차이를 구분하는 UI 로컬 검증: 전체 26개 테스트·타입 검사·Pages 경로 빌드
- [x] 허용 JSON의 수동 outbound Pages 게시·HTTP 401 실패 보존과 새 플랫폼 카드 공개 1280px·390px 확인: [근거](evidence/platform-observation/README.md)
- [x] 실제 순서 역전 게시에서 발견한 seed 회귀 교정과 이전 성공 artifact·공개 JSON·브라우저 기준 재검증: [실패 발견과 교정](evidence/platform-observation/README.md)
- [x] Ubuntu collector 41개·최종 자동화 35개 root·일반 사용자 각각 통과와 비활성 설치·systemd 정적 검증: [상태](../infra/observation/AUTOMATION.md)
- [x] 전용 Pages 자격증명으로 수동 host cycle·Pages 게시와 전체 공개 JSON 일치 확인
- [x] 실제 systemd service 실행 성공·root 0600 상태 파일·임시 SA 토큰 정리 확인
- [x] timer enabled·active와 최초 자동 trigger의 Pages 게시·전체 공개 JSON·브라우저 확인
- [x] 최초 자동 실행을 포함한 11회의 Pages build·deploy success와 실제 서비스 완료 간격 검증: [실행 목록](evidence/platform-observation/README.md)
- [ ] credential 실제 만료·회전과 장기간 운영 검증
- [x] API·웹 replicas 0 중단에서 공개 홈·마지막 기록·DB·기존 서비스 보존과 같은 정상 B 복원 검증: [근거](evidence/platform-observation/README.md)
- [ ] 공개 읽기 API 구현과 실시간 연결
- [ ] 휴대폰 외부망에서 TLS·화면·API와 관리 접근 제한 확인
- [x] 검토한 실제 앱 관측 snapshot을 Pages 소스에 등록: [근거](evidence/mini-pc/README.md)
- [x] Lab 연결 실패와 합성 샘플을 표시하고 미관측 시각을 구분
- [x] 실제 관측 snapshot·수집 시각·source SHA 표시 구현과 관측 계약 검증
- [ ] 필요한 항목에 한해 Jenkins·Argo CD 실시간 요약과 배포 이력 연결

완료 조건: 방문자가 합성 데이터 결과와 배포 요약을 볼 수 있고, Lab 중단 때도 공개 홈의 프로젝트와 이전 결과를 읽을 수 있습니다. 첫 공개 목표는 여기까지입니다. 실제 수집·인증 실패·회복·공개 게시·브라우저·게시 순서 보존과 API·웹 중단 후 같은 정상 B 복원을 확인했습니다. 수동 host cycle·실제 systemd service·timer 자동 실행과 반복 게시 11회의 Pages build·deploy success까지 검증했습니다. 첫 실행의 즉시 trigger와 후속 10개 실제 간격을 구분했고, 완료 간격은 1825.569287~1875.101367초였습니다. 만료·회전의 장기 운영과 선택적인 실시간 공개 API·inbound 연결은 별도 후속입니다.

## 4 Kafka와 객체 저장소

2026-10-15 미니 PC K3s에 Kafka·Garage·상시 worker를 배포했고 이후 API·worker를 V2 지원 소스로 함께 교체했습니다. 실제 고정 1,000건 작업은 성공 500·실패 300·중복 200·대기 0으로 완료됐습니다. 기존 18개와 신규 3개 파일의 전체 GET, 슬롯 해제·Kafka offset 7/lag 0, 총 7개 작업·파일 정보 14개의 공개 JSON 일치를 확인했습니다. [이전 V2 배포·게시 근거](evidence/input-v2-deployment/README.md)는 당시 조건이며, 이전 readiness 검증의 8작업·16파일·24객체는 [후속 근거](evidence/worker-readiness/CORRECTED_IMAGE.md)에서 확인합니다. 아래 과거 격리 검증은 당시 조건의 별도 근거입니다.

- [x] V2 작업·outbox·단일 슬롯, raw 원본 hash·DB 멱등 경계 구현
- [x] 실제 MariaDB의 V1 업그레이드·빈 DB 초기화·반복 시작, 동시 제출·rollback·재전달·Asia/Seoul 시각 일치 검증
- [x] 이전 image의 Flyway V2 DB migration 호환성(시나리오 V2 전방 호환성과 별개)과 기존 운영 SQL·PVC·Docker 보존, 임시 자원 정리 확인

- [x] 명시적 Kafka publisher·worker, ACK 뒤 outbox 확인·Get-only 원본 검증·DB commit 뒤 수동 offset 구현: [ADR 0006](adr/0006-explicit-kafka-dispatch.md)
- [x] 실제 Kafka·MariaDB·Garage에서 JVM 중단 세 경계·재전달 멱등·손상 원본 fail-stop/명시적 fixture 복구, 결과 건수·offset·lag 0·기존 운영 보존: [근거](evidence/kafka-redelivery/README.md)
- [x] 결정적 결과·실패 파일 export, 전체 bytes/크기/SHA 확인 뒤 outbox·EXPORTED·슬롯 해제: [ADR 0007](adr/0007-verified-result-export.md)
- [x] 실제 MariaDB/Garage 정상·반복/다음 슬롯 보존·부분 저장·손상 거부·최종 DB rollback·JVM 중단 2개 경계와 재시도, 기존 운영 보존: [근거](evidence/result-export/README.md)
- [x] 명시적 상시 publisher/worker/export 실행기·MariaDB named lock·V3 영속 정지와 별도 resume: [ADR 0008](adr/0008-continuous-runtime-observation.md)
- [x] 실제 연속 두 작업·JVM 중단/재시작·PAUSED 재시작/경쟁 CLI 거부·resume, 작업/export HTTP 관측·기록 화면·운영 보존: [근거](evidence/continuous-runtime/README.md)
- [x] ClusterIP Kafka/Garage·별도 worker GitOps 배포, 실제 두 작업·파일 4개 검증·슬롯 해제와 기존 seed/PVC/Docker 보존: [근거](evidence/runtime-deployment/README.md)
- [x] 실제 배포 job·플랫폼 관측의 outbound Pages 게시·공개 JSON 전체 일치 확인
- [x] 새 job 관측의 실제 systemd service 성공·Pages 게시·공개 JSON 전체 일치와 private 0600·임시 SA token 정리
- [x] 기존 timer enabled·active와 30분 주기·최대 60초 임의 지연 설정 복구
- [x] 새 job 코드의 원래 timer 자동 실행·Pages 게시 2회, 완료 간격 1개(1809.371239초), unit/collector 무변경·공개 JSON 전체 일치: [근거](evidence/runtime-recovery/README.md)
- [ ] 새 job 수집의 장기간 반복 운영·실제 자격증명 만료/회전 검증
- [x] 실제 idle worker Pod의 UID 조건 정상 교체·종료 marker/STOPPED/exit 143·새 RUNNING과 기존 작업/파일/offset·다른 서비스 보존: [근거](evidence/runtime-recovery/README.md)
- [x] 교체 worker의 새 고정 fixture 처리·두 파일 실제 Get·슬롯 해제, 총 3작업/6파일·Kafka offset 3/lag 0과 원래 두 작업 전체 보존
- [x] Kafka/Garage 전용 3PVC cold copy·AES-256-GCM 외부 반환 사본의 전체 일치·새 namespace/PVC 전체 manifest 복원: [근거](evidence/runtime-pvc-restore/README.md)
- [x] 실제 정책 적용 전 원본 접근 성공·적용 후 두 회차 차단/DNS 허용, Kafka 3 record/offset 3·Garage 원본 9개 inline 객체 GET 보존
- [x] clone 전용 128KiB canary 1 PUT·물리 블록 1개, 추가 2PVC 복원·Pod 교체 전후 각 GET10
- [x] 복제 Kafka의 UID 조건 정상 TERM·새 Pod와 같은 PVC, 3 record key/value/시각·offset/lag 보존
- [x] 시험용 workload 3개 정상 종료·Pod 0·Retain PVC 5개 보관과 최종 원본 SQL/객체/PVC·6개 Ready Pod·Docker 보존 28개 검사
- [x] 별도 1,000건 작업의 부분 export 경계 SIGKILL·동일 JAR pending export 복구, 재계산 없음·기존 4작업/12객체 보존: [근거](evidence/maximum-export-crash/README.md)
- [ ] 계산 중단·진행 중 호스트 재시작 등 다른 장애 경계 복구 검증
- [ ] 다중 partition·이벤트별 전달 순서 검증이 필요할 때 별도 확장
- [x] Garage·Java SDK의 필요한 API·기본 checksum 실패와 호환성 교정 검증 후 한정 선정: [ADR 0005](adr/0005-verified-raw-source-storage.md)
- [x] 원본 전체 bytes·크기·SHA-256, 상태 전환 전 실패·재시도와 컨테이너 재생성 후 Get-only 보존: [근거](evidence/s3-source-storage/README.md)
- [x] 실제 MariaDB·Garage 결합의 정상·손상·DB statement 오류 rollback과 원본 보존·재시도, 같은 DB 반복 및 운영 보존: [근거](evidence/mariadb-s3/README.md)
- [x] 검증 백업·trial·미완료/키를 보호하는 삭제 없는 계획기와 새 합성 PVC만의 실제 정리 경계 검증: [기준](runbooks/retention-resource-budget.md)
- [x] 기존 cgroup 설정 일치·고정 입력 12개 3회의 CPU/RSS/PSS·디스크 snapshot·지연 관측: [근거](evidence/retention-resource-budget/README.md)
- [x] 격리 환경의 최대 1,000개 입력·단일 슬롯 동시 2/8개 접수·초과 입력 거부: [근거](evidence/input-concurrency-load/README.md)
- [x] 별도 Linux worker의 1 CPU·768MiB 제한에서 1,000개 작업 3회·전체 파일 GET·자원/지연 관측: [근거](evidence/input-concurrency-load/README.md)
- [x] V2 지원 API·worker 실제 배포, 1,000건 처리·기존 18개/신규 3개 객체와 7개 작업 공개 게시: [근거](evidence/input-v2-deployment/README.md)
- [x] DB에 보관하는 기본 30초의 내부 새 작업 승인 간격과 기본 157개·실제 backend 19개·외부 SQL 복원 후 이전 binary 호환 8개를 확인했습니다: [근거](evidence/admission-cooldown/README.md)
- [x] API V4 migration→worker 운영 전환과 동일 source·immutable 이미지·기존 7작업/14파일 정보를 보존했습니다: [API·웹 32/32·worker 35/35](evidence/admission-v4-deployment/README.md). 구형 stage 혼용은 금지합니다. 후속 고정 V1 fixture의 접수·charged30·idle 교체·같은 ID 읽기 전용 재시도는 [readiness 후속 근거](evidence/worker-readiness/CORRECTED_IMAGE.md)로 구분합니다.
- [x] 기존 timer의 V4 source 정기 수집·Pages 게시와 job/platform 전체 JSON 원본 일치: [후속 근거](evidence/admission-v4-deployment/PUBLICATION.md)
- [x] worker의 같은 PID1 진행 기록과 stdlib exec readiness 구현·Windows 기본 검사 176개(실행 169·POSIX skip 7): [적용 조건](runbooks/worker-readiness.md)
- [x] corrected Linux API 180개 + 독립 예제 20개, 격리 readiness 10종·OCI 출처·실제 GitOps Ready 전환과 idle worker 교체 확인: [근거](evidence/worker-readiness/CORRECTED_IMAGE.md). 이전 worker exit는 UNOBSERVED이며 처리 중 호스트 장애·장기간 비용은 후속입니다.
- [ ] 공개 진입 요청의 인증·HTTP QPS 제한 구현·검증(현재 공개 실행 없음)
- [x] 전체 운영 DB·S3 참조21개를 모두 보호하는 dry-run과 새 Garage의 합성 객체2개 자연 GC·공유 블록 보존을 검증했습니다: [근거](evidence/object-reference-gc/README.md)
- [ ] 운영 객체의 tombstone·삭제 intent·재전달/resume·백업 의존성을 조율하는 삭제 프로토콜과 metadata GC를 검증합니다.
- [ ] 과부하·운영 처리 용량과 중단/회복 한계 검증
- [ ] 제한을 검증한 뒤 공개 샘플 실행 기능 추가

완료 조건: 입력 건수가 성공·실패·중복·대기로 설명되고, 데이터 유실이나 무제한 실행 없이 결과를 확인할 수 있습니다.

새 job의 원래 timer 자동 수집·게시 2회와 완료 간격 1개(1809.371239초)를 확인했습니다. [후속 검증 근거](evidence/runtime-recovery/README.md)는 과거 플랫폼 collector 11회와 구분합니다. 공개 페이지는 약 30분 주기로 수집하는 마지막 기록이며 heartbeat 5분 경고와 구분합니다. 현재 운영판은 단일 노드·partition 1/RF1이며 내부 stage 명령의 기본 12개 V1 fixture와 선택적 고정 1,000개 V2 fixture를 지원합니다. 실제 V2 한 작업의 처리·파일·공개 관측은 [후속 배포 근거](evidence/input-v2-deployment/README.md)에서 확인했고, 정확한 1MiB 경계·동시 접수·자원 수치는 아래 별도 격리 시험 조건입니다. 공개 POST는 제공하지 않습니다. 전용 PVC의 격리 복원은 [별도 근거](evidence/runtime-pvc-restore/README.md)로 확인했습니다. 운영 PVC 덮어쓰기·진행 중 crash·과부하 용량·장기간 운영은 검증하지 않았습니다.

보존 정책은 dry-run만 제공하며 실제 백업·기존 trial은 삭제하지 않았습니다. 별도 60초 validation TTL의 새 합성 PVC만 정리했고 기존 11PVC/PV를 보존했습니다. 약 63초의 작은 작업 관측에서는 기존 6개 container/image/source와 limit을 유지했고 총 6개 EXPORTED 작업·파일 12개 전체 Get·offset 6/lag 0을 확인했습니다. 최종 25개 검사에서 기존 11PVC/PV·6개 원본 Pod·Docker 38개/실행 26개·기존 업무 SQL/객체와 timer 설정·주기를 보존했습니다. 이 작은 작업 관측은 운영 처리 용량·SLA 검증이 아닙니다. [관측 방법과 한계](runbooks/retention-resource-budget.md)를 따릅니다.

이후 격리 MariaDB·Kafka·Garage의 통합 검사 5개에서 최대 1,000개/1MiB 입력과 기존 V1 호환성, 동시 2·8개 접수 중 한 작업만 허용하는 단일 슬롯, 초과 입력의 부작용 없는 거부를 확인했습니다. 별도 Linux Docker worker의 고정 1,000개 작업 3회는 각각 성공 500·실패 300·중복 200·대기 0으로 끝났고 파일 9개 전체 GET·Kafka offset 3/end 3/lag 0을 확인했습니다. 약 74.39초·72개 샘플의 자원·지연 수치는 [격리 검증 근거](evidence/input-concurrency-load/README.md)에 기록합니다. 최종 21개 검사에서 운영 source와 기존 6개 작업·11PVC/PV·원본 Pod 6개·Docker 38개/실행 26개를 보존했습니다. 요청 빈도 제한·공개 실행·운영 용량 검증은 남아 있습니다.

## 5 LLM 개선 사례와 복구

- [x] 개인 합성 UTC 시간창 예제로 offset 오류와 O(n²) 기준 연산 정의: [예제](../examples/java-window-analysis/README.md)
- [x] AI 제안 범위·채택/제외 이유·독립 기대값·전후 테스트 기록: [출처](../examples/java-window-analysis/PROVENANCE.md)
- [ ] 저장소 소유자의 사람 검토 완료와 실제 채택 판단 기록
- [x] 고정 합성 분포·크기·Java 21·JMH 1.37·3 fork 조건의 실제 Windows 측정: [16조합·48 fork 근거와 큰 오차](evidence/ai-window-analysis/README.md)
- [x] 별도 테스트 볼륨으로 DB 복원 검증: [실제 검증](evidence/recovery/README.md)
- [x] 역사적 외부 백업 네 구성요소의 파일 복원·빈 WAL SQLite 읽기 무결성·별도256바이트 키 조립을 후속 검증(첫 restore 실패 보존): [파일 전용 근거](evidence/historical-file-restore/README.md)
- [ ] 파일·K3s·Jenkins archive 전체 복원 검증
- [x] 전후 코드·기대 결과·측정 조건과 한계를 [포트폴리오 UI](https://devdooly.github.io/devdooly-platform-lab/#ai-window) 소스에 연결: 웹 41개·check/build, 정적 fixture 선택
- [x] AI 사례를 [TIL의 UTC 구간 계산 글](https://devdooly.github.io/TIL/LLM_Development/UTC_Window_Analysis_Case/)에 연결: 문서 검사 42개·strict build 후 게시

완료 조건: 개선 전 실패·개선 후 성공과 측정 원본을 재현할 수 있고, 백업한 데이터의 복원 결과가 있습니다. 독립 예제의 Java 테스트 20개·runner 검사 3개를 통과했으며 측정 당시 sourceCommit은 null과 실제 manifest hash로 보존합니다. 큰 오차가 있는 로컬 합성 측정으로 운영 처리량·SLA를 주장하지 않습니다. TIL 연결을 마쳤으며 사람 검토와 전체 archive 복원은 남아 있습니다. [CI 연결 범위](evidence/ai-window-analysis/ci-validation.md)는 별도로 기록합니다.

## 6 데이터 플랫폼 확장

- [x] 별도 합성 실증의 PostgreSQL JDBC V1 영속 catalog·Garage backing store 선정과 실제 연결: [native7 근거](evidence/iceberg-jdbc/README.md)
- [x] Trino에서 원본 0→6→12행·초기 빈 snapshot 1개와 데이터 append 2개·세 시점 조회 검증: [실제 기록](evidence/iceberg-jdbc/summary.json)
- [x] 독립 Cloud Spark 시험 8의 Bronze 6+6행·snapshot 2개, Silver 성공 7·실패 3·중복 2와 같은 application의 순차 replay write 0회 검증: [근거](evidence/spark-silver/README.md)
- [x] 새 Cloud warehouse의 Spark→Trino 연결·6→12→12행·현재 파일 2→1 compaction·자기 컨테이너 종료: [실제 근거](evidence/cloud-lakehouse/FULL_SUCCESS.md)
- [x] 삭제 없는 순수 Iceberg retention planner 공개와 maintenance 검사 59개 통과. current/ref/pin의 모든 ancestor와 모든 객체 KEEP, apply 비활성: [범위](runbooks/iceberg-retention-dry-run.md)
- [x] 첫 closed-copy 실행의 저장소 검증·Linux 56개 통과와 `PREP_NOT_VERIFIED` 실패 원문 보존: [시도 1 근거](evidence/iceberg-capture/ATTEMPT_1.md). 준비 실패 원인·컨테이너 정리 성공은 미확인
- [x] Schema 2의 실제 Linux 62개·skip 0 통과와 새 prep 실패의 `JAR_MANIFEST_CLASSPATH_EXPANSION_REJECTED`·준비용 컨테이너 제거·부재 확인: [시도 2 근거](evidence/iceberg-capture/ATTEMPT_2.md). 첫 실패 원인으로 소급하지 않음
- [x] 세 번째 새 소스의 Linux 67개·skip 0 통과와 `JAR_MANIFEST_BYTES_BOUND` 실패·준비용 컨테이너 제거·부재 확인: [시도 3 근거](evidence/iceberg-capture/ATTEMPT_3.md). 구체적 manifest 실패 분기와 실제 Class-Path closure는 미확인
- [x] 네 번째 새 소스의 Linux 73개·skip 0 통과와 `JAR_MANIFEST_CLASSPATH_TARGET_MISSING` 실패·준비용 컨테이너 제거·부재 확인: [시도 4 근거](evidence/iceberg-capture/ATTEMPT_4.md). 정확한 JAR·token·경로와 전체 Class-Path closure·compile 성공은 미확인
- [x] 다섯 번째 새 소스의 Linux 80개·skip 0, compiler prep와 원래 main 한 번·반환 0, 새 decoder 컨테이너 정지·CLI 회수 확인: [시도 5 근거](evidence/iceberg-capture/ATTEMPT_5.md). 전체 결과는 `NORMALIZE`의 `SUMMARY_NOT_VERIFIED`·`UNKNOWN` 실패이며 정확한 원인·decoder exit 0·유효 graph는 미확인
- [x] 여섯 번째 새 소스의 Linux84·skip0과 prep·원래 main 한 번/반환0·새 decoder 정지/CLI 회수 확인: [시도6 근거](evidence/iceberg-capture/ATTEMPT_6.md). 전체 결과는 SUMMARY_NOT_VERIFIED 실패이며 NORMALIZE_DECODER_LIFECYCLE_UNVERIFIED는 시도한 검증 구간만 뜻함. 내부 원인·종료 코드·graph 성공은 미확인
- [x] 일곱 번째 새 실행의 Linux85·UID0·skip0·source 전후 동일과 prep·원래 main 한 번/반환0·새 decoder 정지/CLI 회수 확인: [시도7 근거](evidence/iceberg-capture/ATTEMPT_7.md). 전체 결과는 SUMMARY_NOT_VERIFIED 실패이며 NORMALIZE_DECODER_REPLY_BINDING_UNVERIFIED는 시도한 응답 binding 검증 구간만 뜻함. 정확한 원인·특정 hash 불일치·decoder 종료 코드·graph 성공은 미확인
- [x] 여덟 번째 새 실행의 Linux86·UID0·skip0·source 전후 동일과 prep·원래 main 한 번/반환0·새 decoder 정지/CLI 회수 확인: [시도8](evidence/iceberg-capture/ATTEMPT_8.md). 전체 capture는 SUMMARY_NOT_VERIFIED 실패이며 strict JSON 검증 구간만 미확인으로 구분; 정확한 원인·exit·graph 성공은 미확인
- [x] 9차 새 source `5862ba0c`의 Linux87·UID0·skip0·source 전후 동일과 같은 실행의 stopped actors·clock → 독립 graph closure·normalization → 완전 inventory → 순수 planner 입력 연결: [실제9](evidence/iceberg-capture/ATTEMPT_9.md). 필수 검증9개 true·DETERMINED·passed true; 스냅샷3·참조1·보호 항목1·객체20, 스냅샷 제안·객체 삭제 후보0개·전체 KEEP. 이전1–8의 실패와 null은 보존하고 삭제·만료·Parquet 해석·live 독립 검증은 미실행
- [ ] snapshot 보존·만료 정책과 운영 규모 compaction 검증
- [x] Trino만 정상 재시작한 뒤 같은 행·metadata pointer·warehouse 전체 bytes 조회 검증. PostgreSQL은 같은 프로세스를 유지했으며 재시작은 검증하지 않음: [범위](evidence/iceberg-jdbc/README.md)
- [x] 시험 PostgreSQL·Trino workload 0·Retain PVC 2개·warehouse 보관과 원래 8개 작업·객체 24개 보존: [종료·보존](evidence/iceberg-jdbc/README.md)
- [ ] 필요한 경우 Airflow DAG 추가
- [x] 이번 실증의 명시적 새 20분 예산·heavy 단계 전 CI 유휴 시점 관측·단발 detached 실행·소유 workload 종료와 실패 기록 보존 절차 작성: [runbook](runbooks/iceberg-jdbc-native.md)

완료 조건: 동일 warehouse에서 쓰기·조회·재시작·compaction이 검증되고 실행 시 자원 사용량이 남습니다. 기존 native Trino·Cloud Spark8의 별도 시험에 이어 새 Cloud의 Spark→Trino 연결·작은 compaction을 추가 완료했습니다. 2026-10-15 19:05:20 UTC의 일곱 번째 실행에서 시점 조회·Trino 정상 재시작·종료·원본 보존을 확인했습니다. 이전 실패와 완료된 DDL의 채택 관계는 [근거](evidence/iceberg-jdbc/README.md)에 보존했습니다. 새 Cloud의 2026-10-16 03:12:33 UTC 기록은 같은 Cloud 환경의 재시작·지속 부하 검증을 포함하지 않습니다.

새 Cloud의 연결·작은 compaction은 완료했고, 새 a7의 [현재 V1–V4 DB 논리 백업·격리 복원](evidence/current-db-restore/README.md)에서 8개 테이블 스키마·7개 비runtime 테이블 행·BLOB 대조와 원본 DB 보존을 확인했습니다. 원래 stop receipt는 실패로 유지하며 별도 읽기 진단의 DB 0·Pod 0·Bound/Retain 관측과 정상 exit UNOBSERVED를 구분합니다. snapshot 보존 정책·필요한 경우의 Airflow·전체 애플리케이션 복구는 남아 있습니다. 미니 PC native7의 중지된 시험 환경과 보관 자료는 유지합니다. 전체 6단계를 완료로 표시하지 않습니다. PostgreSQL 재시작·호스트 장애·HA·처리량 SLA·현재 가용성은 이번 검증 범위가 아닙니다. CI 유휴 관측은 각 확인 시점의 근거이며 전체 실행 동안의 비활성을 보장하는 잠금이 아닙니다.

단계는 의존 순서이며 기간 약속이 아닙니다. 각 단계 완료 후 다음 확장의 필요성과 자원을 다시 판단합니다.
