# DevDooly Platform Lab

Java 서비스 개발부터 데이터 처리, 배포와 운영까지 직접 구현하고 결과를 공개하는 개인 플랫폼 프로젝트입니다. 직접 만든 합성 센서 데이터로 처리 규칙과 오류 대응을 재현하고, [TIL](https://devdooly.github.io/TIL/)에 설계와 문제 해결 기록을 연결합니다.

[포트폴리오](https://devdooly.github.io/devdooly-platform-lab/) · [GitHub](https://github.com/DevDooly/devdooly-platform-lab) · [시작 안내](docs/START_HERE.md) · [진행 목록](docs/ROADMAP.md) · [다음 개발 계획](docs/NEXT_STEPS.md)

## 현재 상태

현재 목표는 기존 미니 PC의 서비스·자료를 보존하면서 Java·데이터 처리·배포·복구 경험과 공개 연결을 검증 기록으로 보여주는 것입니다.

| 영역 | 확인한 범위 | 근거 |
| --- | --- | --- |
| 서비스·CI/CD | Java API·worker, Kafka·Garage 배포와 같은 소스의 CI·이미지 전환·자료 보존 | [실제 배포](docs/evidence/runtime-deployment/README.md), [CI/CD](docs/evidence/cicd-gate/README.md) |
| 데이터·복구 | Cloud Spark→Trino·compaction, DB 논리 복원·Kafka/Garage PVC 격리 복원 | [Cloud](docs/evidence/cloud-lakehouse/FULL_SUCCESS.md), [DB](docs/evidence/current-db-restore/README.md), [PVC](docs/evidence/runtime-pvc-restore/README.md) |
| 보존 계획·화면 | Iceberg 실제 metadata의 KEEP 계획, 기술별 근거 탐색·합성 정책 선택 UI의 로컬 검증 | [실측 기록](docs/evidence/iceberg-capture/ATTEMPT_9.md), [합성 예제](examples/iceberg-retention-scenarios/README.md) |
| Java·AI 활용 | 합성 시간창 예제의 회귀 테스트와 Windows·Linux JMH 재현. 사람 검토는 대기 중 | [Java 예제](examples/java-window-analysis/PROVENANCE.md), [Linux 재현 결과](docs/evidence/ai-window-analysis/hosted-linux-20261018/README.md) |

최근 완료한 범위는 다음과 같습니다. 실행별 소스·수치·실패 이력과 한계는 연결한 실제 근거를 따릅니다.

- **Jenkins 인증:** [GitHub App 연결](docs/evidence/github-app-jenkins/README.md)로 수동 PAT 발급을 줄였습니다. 실제 build 151의 7개 단계·산출물·App pending→success와 같은 소스의 Actions 성공에 이어, [토큰 자연 만료 후 갱신](docs/evidence/github-app-jenkins/NATURAL_EXPIRY.md) 한 주기를 확인했습니다. 만료한 토큰의 401 → native 자격증명 접근 1회 → 새 토큰의 200·저장소 일치·유효기간 1시간을 검증했고 기존 job·설정·비밀 입력을 보존했습니다. 자격증명 사용 시의 갱신 결과이며, 접근 없이 주기적으로 미리 발급하거나 키 교체·권한 철회 복구를 검증한 결과는 아닙니다.

- **관측 자동화:** [선택적 진단 실패·DDNS 완료 시한](docs/evidence/automation-failure-boundaries/README.md)을 수정했습니다. 로컬 관측156개 통과·기존 POSIX4개 생략에 이어 같은 main의 Linux 관측160개·DDNS5개 통과·skip0와 Pages 성공을 확인했습니다. [운영 반영](docs/evidence/automation-failure-boundaries/DEPLOYED.md)에서는 두 코드 교체·DDNS 새 자연 회차 한 번과 새 관측 실행기의 Pages39526516518·공개 JSON3개 일치를 확인했습니다.

- **수집기 완료 경계:** [응답 완료 시한·OS 잠금](docs/evidence/collector-completion-boundaries/README.md)의 Linux173개·SIGKILL 후 동일 inode 재획득을 확인하고, [collector 한 파일의 운영 교체](docs/evidence/collector-completion-boundaries/DEPLOYED.md)를 20:17:53(KST)에 마쳤습니다. 이어 [20:41 자연 수집·Pages39947822996](docs/evidence/collector-completion-boundaries/NATURAL_PUBLICATION.md)에서 새 코드 pin·수집 시각·같은 run의 build/deploy와 공개 JSON3개·artifact 전체 bytes 일치를 확인했습니다. 이는 자연 회차 한 번의 결과이며 운영 SIGKILL 복구·장기 가용성 검증과 구분합니다.

- **브라우저 관측 보호:** [응답 순서·내용 충돌·본문 크기](docs/evidence/browser-observation-protection/README.md)를 보완했습니다. 플랫폼의 최신 시도·성공은 각각 유지하고, 같은 시각의 다른 내용은 거부하며 플랫폼 본문은 읽는 중16KiB 상한을 적용합니다. PR211의 UTC 동등 표기 교정은 로컬·main Linux의 웹251개·생략0·타입·빌드와 Pages·공개 HTML/JS bytes 일치를 확인했습니다. Kafka 본문 전송 오류 분류는 PR215 당시 웹262개·Astro50파일·2페이지 빌드와 main CI·Pages·공개 HTML/JS bytes 일치를 확인했으며 새 브라우저 실행·운영 장애 주입 검증과 구분합니다. 이어 API·게시본 모두 실패할 때 검증된 직전 API 객체·원 시각과 새 오류를 보존하도록 보완해 로컬 웹270개·생략0·Astro50파일 진단0·2페이지 빌드를 통과했습니다. 이 보존 후속의 main CI·Pages·공개 산출물은 대기 중입니다. 기존247개까지의 공개 정상 재조회 근거는 보존합니다. 서버 상태나 장기 가용성을 보장하는 기능은 아닙니다.

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

