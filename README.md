# DevDooly Platform Lab

Java 서비스 개발부터 데이터 처리, 배포와 운영까지 직접 구현하고 결과를 공개하는 개인 플랫폼 프로젝트입니다. 직접 만든 합성 센서 데이터로 처리 규칙과 오류 대응을 재현하고, [TIL](https://devdooly.github.io/TIL/)에 설계와 문제 해결 기록을 연결합니다.

[포트폴리오](https://devdooly.github.io/devdooly-platform-lab/) · [GitHub](https://github.com/DevDooly/devdooly-platform-lab) · [현재 범위·다음 작업](docs/AUTONOMOUS_WORK.md) · [시작 안내](docs/START_HERE.md) · [진행 목록](docs/ROADMAP.md) · [다음 개발 계획](docs/NEXT_STEPS.md)

## 서비스 화면 바로가기

[전체 서비스 목차](https://devdooly.github.io/devdooly-platform-lab/#services) · [두 실행 결과 비교](https://devdooly.github.io/devdooly-platform-lab/runs/compare/) · [Java API 명세·직접 조회](https://devdooly.github.io/devdooly-platform-lab/api-guide/) · [Jenkins](https://jenkins.devdooly-platform-lab.duckdns.org/login) · [Argo CD](https://argocd.devdooly-platform-lab.duckdns.org/) · [Kafka · Kafbat](https://kafka.devdooly-platform-lab.duckdns.org/)

관리 UI는 외부 HTTPS에서 로그인 후 접근합니다. Kafka는 읽기 전용 Kafbat UI를 별도로 설치했고, Jenkins·Argo CD는 기존 계정을 사용합니다. [접속 방법·실제 확인·한계](docs/runbooks/service-console.md)에서 인증 범위와 설치 결과를 확인합니다.

두 실행 결과 비교에서는 목록에서 A·B를 골라 입력·성공·실패·중복·대기 건수, 입력 대비 비율과 실패 사유를 나란히 봅니다. 표시된 비교는 ID 공유 링크와 출처·조회 시각을 포함한 CSV로 저장할 수 있습니다. 기존 공개 API를 읽으며 실행을 생성하지 않습니다. [사용법과 해석 범위](docs/features/run-comparison.md)를 확인하세요.

**두 실행의 센서별 결과 비교**를 추가합니다. 전체 실패 수가 같아도 실패가 옮겨간 센서를 찾도록 원문 센서 ID별 건수·실패 비율과 B − A를 연결합니다. 한쪽 응답에 없는 센서는 0건 대신 미관측으로 구분합니다. [센서 비교 사용법·검증 범위](docs/features/sensor-comparison.md)를 따르며 기존 비교 CSV와 ID 공유 형식은 유지합니다.

**입력 순서별 이벤트 응답 비교**에서는 같은 sequence의 A·B 행을 나란히 보고 응답 입력필드 차이와 판정 차이를 구분합니다. 전체·센서별 집계가 같아도 달라진 위치를 검색·분류해 찾을 수 있습니다. 반복 eventId를 합치지 않으며 중복 sequence는 대응 모호, 한쪽에 없는 위치는 미관측으로 남깁니다. [비교 기준·사용법](docs/features/event-comparison.md)을 확인하세요. 보고 필드 일치는 같은 원본 입력이나 코드의 증명이 아닙니다.

**[저장한 이벤트 JSON 비교](https://devdooly.github.io/devdooly-platform-lab/runs/offline/)**에서는 ‘이벤트 상세 → 검색 결과 저장’의 JSON 두 개를 선택해 API 없이 저장된 행을 비교합니다. 파일은 브라우저 메모리에서 검증·처리하며 서버로 업로드하지 않습니다. 파일에 기록된 출처·필터·세 건수와 실제 저장 행의 차이를 구분합니다. [파일 형식·한도·해석 범위](docs/features/offline-event-comparison.md)를 확인하세요.

파일 비교에서 찾은 차이는 **비교 보고서 JSON 저장**으로 남깁니다. 현재 검색·분류에 맞는 전체 그룹과 양쪽 후보, 원파일 출처·조건·건수를 함께 담으며 화면의 첫20개로 자르지 않습니다. 원래 이벤트 내보내기와 다른 검토자료입니다. [보고서 형식·검증 범위](docs/features/offline-comparison-report.md)를 확인하세요.

저장 파일이 없다면 같은 화면의 **파일이 없다면 예제로 시작**에서 A·B 합성 JSON을 받아 선택합니다. 다섯 분류를 각각1개씩 확인하고 보고서 저장까지 체험할 수 있습니다. 실제 운영 기록과 구분한 [예제 내용·기대 결과](docs/features/offline-event-samples.md)를 확인하세요.

비교의 A·B 카드와 실패 사유에서 **이벤트 보기**를 누르면 해당 실행·상태·사유 조건을 상세 화면으로 이어갑니다. 도착 화면에서 조회 버튼을 눌러 새 결과를 읽으며, 비교 당시의 응답을 고정하지 않습니다. [이어 보기 사용법](docs/features/run-comparison.md#비교에서-이벤트-이어-보기)

[API 한 건 조회](https://devdooly.github.io/devdooly-platform-lab/api-guide/#api-detail)는 실행 목록을 불러와 ID를 선택한 뒤 상세 GET을 요청할 수 있습니다. ID 직접 입력도 유지하며, 선택만 바꾸었을 때는 이전 응답과 구분합니다. [목록 선택 안내](docs/features/api-run-selection.md)

[Java 처리 결과](https://devdooly.github.io/devdooly-platform-lab/#lab)의 **이벤트 상세 → 흐름 보기**에서는 이벤트 하나의 응답 필드·판정 사유·결과 분류를 세 카드로 살펴봅니다. 같은 eventId의 반복도 입력 순서로 구분하고, 보고된 최종 결과와 고정 Java 규칙의 해설을 함께 보여줍니다. [이벤트 판정 흐름 안내](docs/features/event-flow.md). 최대 1,000건에서 ID·센서를 검색하고 사유·상태를 함께 고르면 표와 흐름 목록을 같은 조건으로 좁힙니다. [이벤트 검색 안내](docs/features/event-search.md)

## 현재 상태

**공유 링크로 바로 조회하기:** 작업 카드나 비교 화면에서 받은 유효한 링크는 기본 실행을 먼저 조회하지 않습니다. `공유한 실행·조건 조회`를 누르면 요청 ID와 API 정보를 모두 확인한 뒤 실제 결과로 전환합니다. 실패하면 이전 화면을 보존합니다. [첫 조회 동작과 한계](docs/features/event-share.md#공유-링크-첫-조회-개선)

검색한 이벤트는 **이벤트 상세 → 검색 결과 저장**에서 CSV·JSON으로 내려받을 수 있습니다. 현재 조건에 맞는 행을 실행 ID·출처·원 관측 시각·필터와 함께 담고, 선택한 흐름 한 건과 구분합니다. [내보내기 형식과 해석 범위](docs/features/event-export.md)를 확인하세요.

**이벤트 상세 → 실행·검색 조건 공유**에서는 실행 ID·필터·선택 이벤트를 링크로 전달합니다. 링크를 연 화면에서 조회 버튼을 눌러 조건을 적용하며, 당시 응답을 고정하지 않습니다. 없는 이벤트와 필터 제외를 구분하고 조회 실패 시 이전 화면을 유지합니다. [공유 링크 사용법](docs/features/event-share.md)

이벤트 표는 **25·50·100행**씩 나눠 보고 처음·이전·다음·마지막으로 이동합니다. 선택한 이벤트의 페이지로 돌아갈 수 있으며, 흐름 목록·공유·CSV·JSON은 전체 검색 결과를 유지합니다. [표 페이지와 선택 안내](docs/features/event-pagination.md)

**센서별 결과** 탭에서는 응답에 나타난 센서마다 성공·실패·중복·대기와 실패 비율을 비교하고 FAILED 사유를 펼쳐 봅니다. 목록 검색·정렬은 이벤트 조건을 유지합니다. **이벤트 보기·실패 이벤트 보기**를 누르면 해당 센서 ID가 정확히 일치하는 이벤트로 이동하며, 그 조건은 공유 링크와 CSV·JSON에도 남습니다. [센서별 분포의 집계 범위](docs/features/sensor-outcomes.md)

[작업·export 관측](https://devdooly.github.io/devdooly-platform-lab/#job-observation)에서는 작업별 생성·대기 등록·DB 완료·저장 확인 기록을 이어 보고 두 기록 사이의 간격과 원시 시각을 확인합니다. 기록 간격은 순수 처리 시간이나 Kafka·S3 지연과 구분합니다. [작업 흐름과 시각의 의미](docs/features/job-lifecycle.md)

관측에서 이미 읽은 최대 20개 작업은 **작업 ID 검색·작업 상태·export 상태**로 좁혀 봅니다. 조회 목록의 전체·조건 일치 건수를 구분하고, 조건만 초기화해 다시 전체를 볼 수 있습니다. 검색 조건 변경은 추가 GET이나 새 작업을 요청하지 않으며 기존 관측 주기는 유지합니다. [작업 목록 탐색 안내](docs/features/job-list-filter.md)

완료 작업의 **전체 이벤트 보기·실패 이벤트 보기**로 해당 실행 결과를 이어 봅니다. 이동 뒤 조회 버튼을 누르면 같은 작업 ID의 이벤트를 새로 읽으며, 원 관측 시각의 응답이나 저장 파일을 고정하지 않습니다. [연결 조건·사용법](docs/features/job-event-navigation.md)

현재 목표는 기존 미니 PC의 서비스·자료를 보존하면서 Java·데이터 처리·배포·복구 경험과 공개 연결을 검증 기록으로 보여주는 것입니다.

| 영역 | 확인한 범위 | 근거 |
| --- | --- | --- |
| 서비스·CI/CD | Java API·worker, Kafka·Garage 배포와 같은 소스의 CI·이미지 전환·자료 보존 | [실제 배포](docs/evidence/runtime-deployment/README.md), [CI/CD](docs/evidence/cicd-gate/README.md) |
| 데이터·복구 | Cloud Spark→Trino·compaction, DB 논리 복원·Kafka/Garage PVC 격리 복원 | [Cloud](docs/evidence/cloud-lakehouse/FULL_SUCCESS.md), [DB](docs/evidence/current-db-restore/README.md), [PVC](docs/evidence/runtime-pvc-restore/README.md) |
| 보존 계획·화면 | Iceberg 실제 metadata의 KEEP 계획, 기술별 근거 탐색·합성 정책 선택 UI의 로컬 검증 | [실측 기록](docs/evidence/iceberg-capture/ATTEMPT_9.md), [합성 예제](examples/iceberg-retention-scenarios/README.md) |
| Java·AI 활용 | 합성 시간창 예제의 회귀 테스트와 Windows·Linux JMH 재현. 사람 검토는 대기 중 | [Java 예제](examples/java-window-analysis/PROVENANCE.md), [Linux 재현 결과](docs/evidence/ai-window-analysis/hosted-linux-20261018/README.md) |

## 처음 방문했다면

[사이트의 5단계 관람 안내](https://devdooly.github.io/devdooly-platform-lab/#tour)에서 같은 순서로 시작할 수 있습니다. 각 화면 끝의 다음 단계 링크로 이어가거나 관람 목록으로 돌아올 수 있습니다. 화면의 출처와 관측 시각을 먼저 확인하고, 저장된 시험 기록과 현재 API 조회를 구분해 읽어주세요.

| 순서 | 화면에서 해볼 것 | 확인할 근거와 범위 |
| --- | --- | --- |
| 1. Java 처리 결과 | [실행 결과](https://devdooly.github.io/devdooly-platform-lab/#lab)에서 입력 건수의 합을 확인하고, 실패 건수를 눌러 이벤트별 사유를 봅니다. | [worker 고정 입력 검증](docs/evidence/current-worker-fixture/README.md)은 특정 합성 작업의 처리·파일 저장·기존 자료 보존 기록입니다. 화면에서 선택한 실행 ID와 구분합니다. |
| 2. Kafka 재개 | [소비자 복구 기록](https://devdooly.github.io/devdooly-platform-lab/#kafka-lag-recovery)의 3·4단계를 선택해 lag 14 → 0과 committed offset을 비교합니다. | [격리 검증](docs/evidence/kafka-lag-recovery/README.md)은 consumer 정상 종료 후 새 client가 이어 읽은 결과입니다. 운영 broker 장애나 HA 검증은 아닙니다. |
| 3. CI/CD | [배포 상태](https://devdooly.github.io/devdooly-platform-lab/#platform)의 출처·시각을 확인하고, 옆 근거의 정상 배포와 실패 차단을 비교합니다. | [CI/CD 근거](docs/evidence/cicd-gate/README.md)는 같은 소스의 Jenkins·Actions, 이미지 게시·Argo 배포와 이전 이미지 복구 기록입니다. 현재 화면의 관측과 당시 배포 시험을 구분합니다. |
| 4. AI와 Java 개선 | [시간창 예제](https://devdooly.github.io/devdooly-platform-lab/#ai-window)의 수정 전후 코드를 펼치고, 분포·세션 수를 바꿔 기대값과 측정 표를 비교합니다. | [AI 활용 범위](examples/java-window-analysis/PROVENANCE.md)와 [측정 근거](docs/evidence/ai-window-analysis/README.md)를 연결합니다. 선택은 저장된 기록 조회이며 새 Java·JMH 실행이 아닙니다. 사람 검토는 PENDING입니다. |
| 5. 데이터 보존 | [Iceberg capture](https://devdooly.github.io/devdooly-platform-lab/#iceberg-capture)에서 snapshot·참조·객체 수와 KEEP 판정을 봅니다. | [9차 capture](docs/evidence/iceberg-capture/ATTEMPT_9.md)는 실제 metadata를 복사해 만든 삭제 없는 보존 계획입니다. 운영 객체의 만료·삭제를 실행한 결과는 아닙니다. |

관심 기술의 다른 사례는 [공개 근거 검색](https://devdooly.github.io/devdooly-platform-lab/#evidence)에서 찾을 수 있습니다. 현재 완료·미검증·보류는 [현재 범위·다음 작업](docs/AUTONOMOUS_WORK.md)을 따릅니다.

최근 완료한 범위는 다음과 같습니다. 실행별 소스·수치·실패 이력과 한계는 연결한 실제 근거를 따릅니다.

- **Jenkins 인증:** [GitHub App 연결](docs/evidence/github-app-jenkins/README.md)로 수동 PAT 발급을 줄였습니다. 실제 build 151의 7개 단계·산출물·App pending→success와 같은 소스의 Actions 성공에 이어, [토큰 자연 만료 후 갱신](docs/evidence/github-app-jenkins/NATURAL_EXPIRY.md) 한 주기를 확인했습니다. 만료한 토큰의 401 → native 자격증명 접근 1회 → 새 토큰의 200·저장소 일치·유효기간 1시간을 검증했고 기존 job·설정·비밀 입력을 보존했습니다. 자격증명 사용 시의 갱신 결과이며, 접근 없이 주기적으로 미리 발급하거나 키 교체·권한 철회 복구를 검증한 결과는 아닙니다.

- **관측 자동화:** [선택적 진단 실패·DDNS 완료 시한](docs/evidence/automation-failure-boundaries/README.md)을 수정했습니다. 로컬 관측156개 통과·기존 POSIX4개 생략에 이어 같은 main의 Linux 관측160개·DDNS5개 통과·skip0와 Pages 성공을 확인했습니다. [운영 반영](docs/evidence/automation-failure-boundaries/DEPLOYED.md)에서는 두 코드 교체·DDNS 새 자연 회차 한 번과 새 관측 실행기의 Pages39526516518·공개 JSON3개 일치를 확인했습니다.

- **수집기 완료 경계:** [응답 완료 시한·OS 잠금](docs/evidence/collector-completion-boundaries/README.md)의 Linux173개·SIGKILL 후 동일 inode 재획득을 확인하고, [collector 한 파일의 운영 교체](docs/evidence/collector-completion-boundaries/DEPLOYED.md)를 20:17:53(KST)에 마쳤습니다. 이어 [20:41 자연 수집·Pages39947822996](docs/evidence/collector-completion-boundaries/NATURAL_PUBLICATION.md)에서 새 코드 pin·수집 시각·같은 run의 build/deploy와 공개 JSON3개·artifact 전체 bytes 일치를 확인했습니다. 이는 자연 회차 한 번의 결과이며 운영 SIGKILL 복구·장기 가용성 검증과 구분합니다.

- **브라우저 관측 보호:** [응답 순서·내용 충돌·본문 크기](docs/evidence/browser-observation-protection/README.md)를 보완했습니다. 플랫폼의 최신 시도·성공은 각각 유지하고, 같은 시각의 다른 내용은 거부하며 플랫폼 본문은 읽는 중16KiB 상한을 적용합니다. PR211의 UTC 동등 표기 교정은 로컬·main Linux의 웹251개·생략0·타입·빌드와 Pages·공개 HTML/JS bytes 일치를 확인했습니다. Kafka 본문 전송 오류 분류는 PR215 당시 웹262개·Astro50파일·2페이지 빌드와 main CI·Pages·공개 HTML/JS bytes 일치를 확인했으며 새 브라우저 실행·운영 장애 주입 검증과 구분합니다. 이어 API·게시본 모두 실패할 때 검증된 직전 API 객체·원 시각과 새 오류를 보존하도록 보완해 로컬 웹270개·생략0·Astro50파일 진단0·2페이지 빌드를 통과했습니다. 이 보존 후속도 main Linux CI·Pages와 공개 HTML의 두 카드 참조·공통 helper 연결·JS3개 bytes 일치를 확인했으며 새 브라우저 실행 검증과 구분합니다. 기존247개까지의 공개 정상 재조회 근거는 보존합니다. 서버 상태나 장기 가용성을 보장하는 기능은 아닙니다.

- **작업 수집기 완료 시한:** [read·close 뒤 시한 검사](docs/evidence/job-response-deadline/README.md)의 Linux179개·skip0에 이어 [21:18:16(KST) 코드 한 파일 교체](docs/evidence/job-response-deadline/DEPLOYED.md)와 별도 사후 점검을 마쳤습니다. [21:42 자연 회차](docs/evidence/job-response-deadline/NATURAL_PUBLICATION.md)의 새 job 수집과 Pages39955401692 attempt1 build·deploy, 공개 JSON3개·artifact 전체 bytes 일치까지 확인했습니다. 한 회차의 결과이며 전체 처리 시한·장기 가용성 검증과 구분합니다.

- **검색 초기 입력:** [준비 전 입력 보호](docs/evidence/evidence-input-readiness/README.md)로 이벤트 연결 전에 입력이 유실될 수 있는 구간을 막았습니다. 로컬 SSR 사본·준비 후 검색·19개 순차 표시·모바일 Tab 이동과 웹207검사·타입·빌드, 같은 main의 Pages·CI·공개 첫 접속 검색을 확인했습니다.

- **키보드 탐색:** [실행 결과 탭](docs/evidence/lab-keyboard/README.md)의 양끝 방향키 순환과 Home·End 이동을 수정했습니다. 로컬 브라우저8가지·웹207검사·타입·빌드와 같은 main의 Pages·CI, 공개 데스크톱·모바일 반영을 확인했습니다.

- **직접 링크:** [초기 위치 보정](docs/evidence/initial-fragment/README.md)으로 비동기 카드 로딩 뒤 목표 제목이 밀리는 현상을 수정했습니다. 로컬 두 화면·제한 시간·횟수·입력 취소와 같은 main의 Pages·CI, 공개 데스크톱·모바일 반영을 확인했습니다.

- **실행기 오류 처리:** [합성 Error 회귀 검증](docs/evidence/runtime-error-cleanup/README.md)으로 정상 종료 오기록과 자원 정리 누락을 재현·수정했습니다. 관련26개·로컬 전체 검증과 같은 main의 Linux API233개 통과·skip0를 확인했습니다. 해당 수정의 worker 반영은 아래 별도 배포 근거를 따릅니다.

- **시작 실패 정리:** [일부 client만 구성된 뒤의 Error](docs/evidence/client-construction-error/README.md)에서도 역순 종료를 수행하도록 수정했습니다. 수정 전3개 실패·수정 후7개와 로컬 전체 검증, 같은 main의 Linux API240개 통과·skip0를 확인했습니다.

- **런타임 장애:** [offset commit 실패 복구](docs/evidence/offset-commit-recovery/README.md)와 [손상 export 수리](docs/evidence/export-integrity-runtime/README.md)를 검증했습니다. [잘못된 입력](docs/evidence/invalid-message-runtime/README.md)과 [잠금 연결 손실](docs/evidence/runtime-lease-loss/README.md)은 정상 작업 보존과 실행기 종료를 확인한 결과로, 복구 완료와 구분합니다.
- **데이터 보존:** [격리 PostgreSQL 정상 재시작](docs/evidence/cloud-catalog-restart/README.md) 뒤 catalog·조회·전체 객체 보존과 [새 합성 warehouse의 snapshot 만료](docs/evidence/cloud-iceberg-expiration/README.md)를 확인했습니다. 운영 자료의 만료·삭제 결과가 아닙니다.
- **공개 응답:** [외부 GET 관측](docs/evidence/public-get/README.md)의 첫 실행과 후속39521322979에서 지정6개 응답의 HTTP200·헤더·DTO·API 소스245d61a를 확인했습니다. 별도 공개 UI에서는 worker 소스6f551a1·새 실행 시작·heartbeat 전진을 관측했습니다. GET artifact 자체는 worker 소스·시작 시각을 담지 않으며, worker 생존·POST 차단·장기 가용성을 증명하지 않습니다.
- **worker 배포:** [PR177의 실제 worker 교체](docs/evidence/worker-image-rollout/README.md)를 main33c5e8c에서 반영했습니다. worker는 source6f551a1·image ee713으로 전환했고 Argo Synced·Healthy와 새 Pod Ready를 확인했습니다. API245d61a·웹 image029c는 유지합니다. [이전 읽기 전용 점검](docs/evidence/cluster-readonly/README.md)의 worker74 기록과 구분합니다.
- **공개 조회:** [두 번의 실제 TLS 관측](docs/evidence/tls-certificate/README.md)에서 동일 대상·leaf·유효기간과 수집 당시87일을 확인했습니다. 첫 기록의 [공개 화면](https://devdooly.github.io/devdooly-platform-lab/#tls-certificate) 검증은 완료했습니다. 두 번째 원문·이력 연결은 웹207개·타입·빌드와 로컬 확인을 마쳤으며, 같은 main의 Pages·CI와 공개 데스크톱·모바일의 두 기록·출처·접기/펼치기까지 확인했습니다. 자연 갱신·HTTP API 정상 여부·현재 가용성은 이 TLS 관측의 범위가 아닙니다.
- **공개 화면:** [근거 검색·필터·6개씩 더 보기](https://devdooly.github.io/devdooly-platform-lab/#evidence)와 [실행 잠금 사례](https://devdooly.github.io/devdooly-platform-lab/cases/runtime-ownership/)를 공개했습니다. [heartbeat 시각 표시 수정](docs/evidence/job-heartbeat-order/README.md)은 웹188개 검사·타입·프로젝트 경로 빌드와 같은 main의 Pages·CI·Jenkins, 공개 데스크톱·모바일 확인을 마쳤습니다.

[장애별 판단표](docs/runbooks/continuous-runtime.md#실제-네-가지-장애의-판단-기준--2026-10-20-utc)는 저장 상태·실제 종료·재개 전제를 구분합니다. [AI 예제 소유자 검토자료](docs/reviews/ai-window-owner-review.md)의 사람 판단은 **PENDING**입니다.

## 다음 단계와 보류

[GitHub App 갱신 카드의 공개 반영](docs/evidence/github-app-jenkins/PUBLICATION.md)에 이어 [새 수집기의 자연 수집·Pages 게시](docs/evidence/collector-completion-boundaries/NATURAL_PUBLICATION.md)와 [브라우저 관측 응답 보호](docs/evidence/browser-observation-protection/README.md)를 확인했습니다. 자연 회차 한 번의 서버 시각·출처, 같은 run의 artifact와 공개 JSON3개의 전체 bytes를 대조했고, 브라우저의 늦은 응답·같은 시각 내용 충돌·초과 본문 보호는 별도 합성 검증으로 구분했습니다. [공개 근거 목록](https://devdooly.github.io/devdooly-platform-lab/#evidence)에서 자연 수집 기록을 찾을 수 있습니다. 다음 운영 검증은 인증서 자연 갱신 시점의 재관측이며, 아직 자연 갱신 성공으로 표시하지 않습니다.

기존 약30분 timer의 [새 worker 자동 수집·Pages 게시](docs/evidence/worker-image-rollout/NATURAL_PUBLICATION.md)에 이어 [관측 코드 교체 후 자연 게시](docs/evidence/automation-failure-boundaries/DEPLOYED.md)까지 확인했습니다. [새 worker의 고정 합성 입력 한 건](docs/evidence/current-worker-fixture/README.md)은 입력12·성공7·실패3·중복2·대기0의 COMPLETED·EXPORTED, 새 객체3개 전체 bytes와 기존8작업·24객체 보존을 확인했고 완료된 임시 Job도 선택 정리했습니다. 원래 자연 주기의 [Pages39532314754](https://github.com/DevDooly/devdooly-platform-lab/actions/runs/39532314754) build·deploy와 공개 JSON3개·artifact 원문 일치, 새9작업 반영도 확인했습니다. [현재 공개 HTTPS 재관측](docs/evidence/public-get/README.md)은 run39533662559에서 지정 GET6개 모두 HTTP200·DTO 검증을 통과했습니다. 실행 결과는 [ID·입력 건수와 전체 ID](docs/evidence/run-selection/README.md)로 구분하도록 수정했고 로컬 화면 확인을 마쳤습니다. [요청·응답 ID 일치](docs/evidence/run-response-identity/README.md) 수정의 로컬209개·타입·빌드와 공개 정상 선택을 확인했습니다. [100개 센서 범례 줄바꿈](docs/evidence/chart-legend-wrap/README.md)도 공개 데스크톱·모바일에서 확인했고, 기본 URL은 reload·실시간 조회 후 정상 폭을 확인했습니다. 첫 조회 실패의 [유한 진단](docs/evidence/initial-read-diagnostics/README.md)은 로컬223개·타입·빌드와 같은 main의 Pages·CI, 공개 정상 첫 조회·실행 선택 확인을 마쳤습니다. 과거 fallback 원인은 여전히 미확인입니다. 해당 화면 진단 후속에서는 추가 운영 실행을 하지 않았으며, 실패가 다시 발생하면 유한 진단 정보를 관측합니다.

인증서 자연 갱신·현재 공개 경로의 재부팅·K3s/Jenkins 전체 archive 복원은 아직 검증하지 않았습니다. 별도 격리 환경이 없어 **K3s·Jenkins 실제 기동 복원은 보류**합니다. [복원 사전준비](docs/plans/historical-runtime-restore.md)에 파일 검증과 실제 기동, 재개 시 필요한 자료·실행 대상을 정리했습니다. 후속 순서는 [다음 개발 계획](docs/NEXT_STEPS.md)을 따릅니다. Pages 토큰 교체·자원 예산 정책·PR102 접수 gate의 보류도 유지합니다.

## 로컬 실행

Java 21과 Node 24.19.0을 사용합니다. API와 화면을 별도 터미널에서 실행합니다.

```sh
cd apps/api
./mvnw -B -ntp verify
./mvnw spring-boot:run -Dspring-boot.run.profiles=local-dev
```

Windows에서는 `mvnw.cmd`를 사용합니다. 화면은 다음과 같습니다.

```sh
cd apps/lab-web
npm ci
npm run dev
```

화면은 `http://127.0.0.1:4321/`이며 `/api`를 로컬 API에 연결합니다. 전체 DB 구성은 [MariaDB·Compose 안내](docs/runbooks/local-compose.md)를 따릅니다. H2 로컬 검증, Linux MariaDB 통합 검증과 미니 PC K3s 검증은 각각 기록합니다.

## 저장소 구성

```text
apps/api/                 Spring Boot, JPA·Flyway, 데이터·HTTP 테스트
apps/lab-web/             Astro·React 포트폴리오와 Lab 조회 화면
tests/scenarios/          합성 데이터의 독립 기대 결과
infra/containers/         API·웹 이미지와 Nginx 설정
infra/charts/             API·웹·MariaDB·Kafka·Garage·worker Helm chart
infra/jenkins/            Kubernetes CI agent 정의
infra/platform/           기반 도구의 버전과 설치 값
infra/scripts/            점검·bootstrap·관리 접속 도우미
gitops/                   Argo CD Application과 환경별 image digest
docs/                     계획, ADR, 계약, 운영·검증 근거
benchmarks/               후속 공개 예제의 전후 측정
```

회사 코드·데이터·실제 수율 알고리즘을 사용하지 않습니다. 실제 접속 주소·진단 원본·비밀값은 Git에서 제외한 `.local/`에 보관합니다. 공개 화면에는 허용한 요약만 제공합니다.

