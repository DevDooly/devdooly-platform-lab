# 현재 범위와 다음 작업

기준: 2026-10-26(KST). 개인 Lab에서 실제 확인한 결과와 남은 작업을 찾는 길잡이입니다. 각 근거는 실행 당시의 범위이며 현재 가용성을 보장하지 않습니다.

[프로젝트 소개](../README.md) · [시작 안내](START_HERE.md) · [상세 진행 기록](NEXT_STEPS.md) · [공개 근거 검색](https://devdooly.github.io/devdooly-platform-lab/#evidence)

## 목표 재정렬 — 기술을 설명하는 포트폴리오

이 프로젝트의 우선 목표는 **취업·이직 과정에서 Java·데이터·플랫폼 기술의 이해와 설계 판단을 보여주는 것**입니다. 화면의 세부 기능 수를 늘리기보다, 어떤 문제를 해결하고 기술이 어떻게 연결되며 어디까지 검증했는지 읽을 수 있게 만듭니다. 개인 학습과 다른 시스템 이식을 위해 실제 설정 위치·변경 항목도 연결합니다.

이번 구현은 [기술 목차와 8개 안내](https://devdooly.github.io/devdooly-platform-lab/technologies/), [다른 환경에서 구성하기](https://devdooly.github.io/devdooly-platform-lab/guides/rebuild/), 첫 화면의 설명 동선입니다. 구성도는 책임과 데이터 흐름을 설명하고, 캡처는 실제 촬영한 화면에 한해 출처·범위를 표시합니다. 상시 배포·격리 시험·미검증을 하나의 완료 상태로 합치지 않습니다. 배포 확인은 이 변경의 PR 기록을 따르며, 학습 명령의 안내를 새 환경 기동 성공으로 표시하지 않습니다.

## 서비스 화면 연결

[서비스 목차](https://devdooly.github.io/devdooly-platform-lab/#services)와 [API 안내·실제 GET](https://devdooly.github.io/devdooly-platform-lab/api-guide/)를 추가했습니다. Jenkins·Argo CD는 기본 로그인, 새 Kafbat UI는 HTTPS BasicAuth를 사용합니다. 2026-10-24 09:04 KST에 외부 TLS·익명 차단과 인증 후 Kafka cluster/topic/group 조회를 확인했고 기존 workload와 라우트를 보존했습니다. 실제 확인과 첫 404 기록은 [서비스 접속 안내](runbooks/service-console.md)를 따릅니다. 네 보류와 기존 운영 pin은 유지합니다.

## 최근 확인한 범위

| 항목 | 확인한 결과와 범위 |
| --- | --- |
| 첫 방문 관람 안내 | [사이트의 5단계 안내](https://devdooly.github.io/devdooly-platform-lab/#tour)에서 Java 처리 결과→Kafka 재개→CI/CD→AI 예제→Iceberg 보존 계획을 따라갈 수 있습니다. 각 화면의 다음 단계·목록 복귀와 개별 검증 근거를 연결하며, 새 서버 작업이나 기록 재검증을 실행하지 않습니다. [README 관람 순서](../README.md#처음-방문했다면) |
| 합성 보존 정책 입력 | [PR233](https://github.com/DevDooly/devdooly-platform-lab/pull/233)에서 준비 전 선택 입력을 잠그고 준비 후 활성화합니다. 정적 사본 재현·회귀 검사, 같은 main의 CI·Pages, 공개 자산 전달과 별도 데스크톱/모바일·키보드 선택 흐름을 확인했습니다. 운영 정책·계산·삭제 기능은 변경하지 않았습니다. [실제 근거](evidence/iceberg-policy-input-readiness/README.md) |
| Job 관측 입력 | [PR226](https://github.com/DevDooly/devdooly-platform-lab/pull/226)에서 같은 JSON object의 중복 key를 거부하고 직전 검증 객체·원 시각을 보존합니다. 합성 회귀, 같은 main의 CI·Pages와 공개 JS 전달을 확인했습니다. 운영 중복 입력 발생·주입이나 새 브라우저 실행의 증명은 아닙니다. [실제 근거](evidence/job-json-key-uniqueness/README.md) · [근거 PR228](https://github.com/DevDooly/devdooly-platform-lab/pull/228) |
| AI 예제 입력 | [PR227](https://github.com/DevDooly/devdooly-platform-lab/pull/227)에서 준비 전 두 선택 입력을 잠그고 준비 후 활성화합니다. 측정 기록 로딩과 조작 준비를 분리했으며 로컬·공개 데스크톱/모바일에서 선택과 기대값을 확인했습니다. Java·benchmark·사람 검토 결과는 바꾸지 않았습니다. [실제 근거](evidence/ai-window-input-readiness/README.md) · [근거 PR229](https://github.com/DevDooly/devdooly-platform-lab/pull/229) |
| Jenkins GitHub App | 실제 토큰 자연 만료 뒤 401 → native 자격증명 접근 1회 → 새 토큰 200·저장소 일치·유효기간 1시간을 확인했습니다. 접근 시의 lazy refresh 한 주기이며 선제 발급·개인키 교체·권한 철회 복구를 검증한 결과는 아닙니다. [자연 만료 근거](evidence/github-app-jenkins/NATURAL_EXPIRY.md) · [공개 카드와 별도 CI 근거](evidence/github-app-jenkins/PUBLICATION.md) |

공개 조회와 운영 관측은 구분합니다. [공개 GET 관측](evidence/public-get/README.md)은 지정 6개 응답의 HTTP·헤더·DTO 계약을 확인합니다. [수집기 자연 회차](evidence/collector-completion-boundaries/NATURAL_PUBLICATION.md)와 [작업 수집기 자연 회차](evidence/job-response-deadline/NATURAL_PUBLICATION.md)는 각 서버 기록·같은 Pages 실행·공개 JSON의 일치를 연결합니다. 한 번의 관측이나 자산 전달 확인만으로 worker 생존·현재 상태·장기 가용성을 단정하지 않습니다.

## 보류 중인 네 작업

1. **Pages 토큰 교체:** 기존 Jenkins App 검증과 별도 작업이며 계속 보류합니다.
2. **별도 환경의 K3s·Jenkins 실제 기동 복원:** 격리 환경이 준비될 때 재개합니다. 기존 파일·무결성 검증을 기동 성공으로 표시하지 않습니다. [복원 사전준비](plans/historical-runtime-restore.md)
3. **자원 예산 정책:** Lab 상한·최소 여유 공간과 실제 적용 기준 확정을 보류합니다. [보존·자원 안내](runbooks/retention-resource-budget.md)
4. **PR #102 접수 gate:** 예산·계량 연결이 미확정이므로 활성화하지 않습니다. [PR #102](https://github.com/DevDooly/devdooly-platform-lab/pull/102)

별도로 **인증서 자연 갱신·현재 공개 경로의 재부팅은 미검증**입니다. [TLS 관측](evidence/tls-certificate/README.md)은 두 시점의 같은 인증서 기록이며 갱신 성공이 아닙니다. AI 예제의 [사람 검토는 PENDING](reviews/ai-window-owner-review.md)으로 유지합니다.

2026-10-23~24 현재 안내의 로컬 연결134회·외부 URL8개 접근과 공개 근거23개 카드의63링크를 점검했습니다. [PR232](https://github.com/DevDooly/devdooly-platform-lab/pull/232)에서는 원래 만료 시험의 `build=false`와 후속 Jenkins153의 상태 전달 기록을 구분했습니다. 링크 점검은 개별 시험 재수행이나 현재 서비스 가용성 검증이 아닙니다.

## 다음 작업의 우선순위

**사용자 피드백으로 확인한 공백:** Kafbat 로그인 계정의 확인 위치를 찾기 어려워 서비스 목차와 Kafka 기술 페이지의 로그인 링크 가까이에 기존 계정 안내를 연결했습니다. 기본 아이디·미니 PC 소유자 확인 절차만 표시하며 비밀번호 조회나 운영 변경은 하지 않습니다. [안내 범위](features/technology-guide.md#kafbat-로그인-안내)와 해당 변경 PR의 공개 결과를 따릅니다. 이 접근성 보완은 실제 피드백 한 건에 한정합니다.

이번 변경에서 **기술 목차·8개 상세 안내·전체 구성도·학습 및 재구축 안내**를 구현했습니다. [구현과 검증 범위](features/technology-guide.md)를 기준으로 공개 반영을 마무리하며, 이 안내를 매번 다시 구현하거나 검증하지 않습니다.

1. **대표 사례의 설명 깊이:** 사용자의 다음 진행 요청에 따라 [Kafka 재전달 사례](https://devdooly.github.io/devdooly-platform-lab/cases/kafka-redelivery/)를 보완합니다. 기존 안내에서 압축된 세 중단 지점·DB 완료 재호출 보호·offset과 export의 차이를 선택해 읽습니다. 기존 실제 시험 수치와 소스를 사용하며 새 운영 시험은 추가하지 않습니다. 변경의 공개 완료·검증 범위는 해당 PR 결과를 따릅니다. 이 한 범위가 끝나면 실제 이해 공백이 확인될 때만 다음 사례를 선정합니다.
2. **재구축 안내의 실제 사용 공백:** 로컬 학습이나 다른 환경으로 옮기는 과정에서 확인된 누락을 고칩니다. 별도 환경의 실제 기동 복원은 기존 보류에 따르며 안내 작성만으로 실행 성공을 주장하지 않습니다.
3. **새 기능 선택:** 취업 포트폴리오의 기술 이해나 학습을 직접 돕는 요구가 있을 때 선정합니다. 현재 안내의 반복 점검이나 세부 조회 기능 추가를 자동으로 다음 목표로 삼지 않습니다.

root는 첫 화면·기술 페이지·통합·공개 확인을, native 에이전트는 기술 내용·재구축 안내를, 다른 채팅은 기술 사실과 범위의 독립 검토를 맡습니다. 같은 checkout의 담당 파일을 겹치지 않게 나누며 검토가 끝난 변경만 반영합니다. 반복 점검이나 작은 조회 기능 추가를 기본 다음 작업으로 선택하지 않습니다. 아래 항목은 이미 완료한 기능 이력입니다.

### 이전 완료 기능 — PR #289까지

| 순서 | 기능 | 필요한 이유와 범위 |
| --- | --- | --- |
| 1 · PR285 공개 완료 | **API 상세 응답 요약과 이벤트 연결** | 상세 GET 후 긴 JSON을 읽어야 했던 동선을 줄입니다. 검증한 응답의 ID·다섯 건수·포함 행 수를 보여주고 기존 공유 링크로 이어갑니다. [동작·검증 상태](features/api-result-summary.md) |
| 2 · PR287 공개 완료 | **조회 요청 명령 복사** | API 안내에서 확인한 요청을 터미널에 옮길 때 URL·경로를 다시 조합하는 수고를 줄입니다. 공개 GET만 대상으로 하며 자동 실행은 추가하지 않습니다. [사용법·검증 범위](features/api-request-command.md) |
| 3 · PR289 공개 완료 | **이벤트 JSON 한 개 다시 보기** | 두 파일을 준비하지 않고 저장한 한 기록을 다시 탐색합니다. 기존 v1/v2 검증·출처를 재사용하며, 원필터와 현재 검색을 구분합니다. [사용법·검증 범위](features/offline-event-viewer.md). 비교 보고서 재불러오기는 포함하지 않습니다. |

[PR #289](https://github.com/DevDooly/devdooly-platform-lab/pull/289)에서 3번까지 공개 반영했습니다. 웹 검사 554개·Astro 91파일 진단 0·6페이지 빌드와 독립 검토, 같은 기능 main의 CI·Pages를 확인했습니다. 로컬 합성 v1/v2·0행·잘못된 파일로 원문·조건·페이지·오류 시 보존을, 공개 화면에서 실제 파일 열기·검색·중복 행·오류 보존·포인터 페이지 이동·375px 화면·목차 연결을 확인했습니다. 최초 파일 접근 제한과 포인터 미변경 기록은 보존하며, 합성 검증을 운영 자료나 현재 API의 인증으로 해석하지 않습니다.

root가 진입·안내·통합·Git·공개 확인을, native 에이전트가 UI·검사와 최종 근거 대조를, 다른 채팅이 독립 검토를 맡았습니다. 현재 이 파일 탐색 흐름에서 추가 필수 기능은 확인되지 않았습니다. 다음 작업은 실제 새 요구나 재현된 문제를 확인한 뒤 한 범위만 선정합니다. 완료 흐름을 반복 검사하거나 뒤 후보를 자동으로 연속 구현하거나 보류를 해제하지 않습니다. 기존 HTTP429와 이전 실패 기록은 아래에 그대로 보존합니다.

**공유 링크 첫 조회 개선:** PR281과 앞선 비교 이동의 실제 429 기록에서 기본 조회가 실패하면 공유 대상의 명시 조회까지 잠기는 동선을 확인했습니다. 유효 링크만 초기 Lab 자동 조회를 생략하고, 버튼 한 번으로 정확 ID·목록·플랫폼 응답 전체를 검증해 전환합니다. 기본 상세를 먼저 조회하지 않으며 실시간 화면의 재적용은 상세 1회입니다. root는 화면·안내·통합 검사를, native 에이전트는 API 계약·검사를 맡습니다. [변경 범위](features/event-share.md#공유-링크-첫-조회-개선)처럼 429 해소나 플랫폼 조회의 장애 독립성을 주장하지 않습니다. 기존 보류·운영 pin은 유지하며 다음 개발은 추가 이용 필요가 확인될 때 정합니다.

**우선 구현한 기능은 작업 관측→이벤트 결과 연결입니다.** 완료 카드의 실패 건수를 보고 긴 ID를 다시 찾던 동선을 줄였습니다. root가 화면·배포를, native 에이전트가 연결 계약·검사를, 다른 채팅이 독립 검토를 담당합니다. MINI_PC 배포 관측의 완료 작업만 기존 명시적 조회로 연결하며 로컬·격리 시험은 제외합니다. 로컬 웹517개·타입·빌드와 실패3건 이동·모바일을 확인했습니다. 전체 조회의 로컬429와 공개·동일 main CI/Pages 결과는 [기능 안내](features/job-event-navigation.md)의 검증 범위와 PR 완료 기록으로 구분합니다. 다음 기능은 실제 이용 공백이 확인될 때 선정하며 기존 네 보류·운영 pin은 유지합니다.

[PR259](https://github.com/DevDooly/devdooly-platform-lab/pull/259)에서 작업·export 기록 흐름을 공개해 계획했던 이용 기능을 마쳤습니다. 생성·원본 검증/대기 등록·DB 완료·저장 확인 기록과 두 기록 간격, 원시 시각 6개를 연결합니다. null은 미기록이며 취소/종료는 별도로 표시합니다. [시각의 의미·범위](features/job-lifecycle.md)를 따르며 처리 시간·Kafka/S3 지연·현재 worker 생존을 추정하지 않습니다.

**작업 ID 검색·작업/Export 상태 필터**는 길게 나열된 작업 관측 카드에서 필요한 작업을 찾는 기능입니다. 이미 읽은 최대 20개 목록에만 조건을 적용하며 조회 목록의 전체·일치 건수와 조건 초기화를 제공합니다. 자동/수동 갱신·이전 유효 기록 보존 시 조건을 유지하고 조회 구성이 바뀔 때 초기화합니다. [동작·범위](features/job-list-filter.md)를 따르며 로컬·공개 검증 결과는 해당 변경의 PR 기록에서 구분합니다. 서버 검색·새 작업·운영 설정 변경은 하지 않습니다.

[PR264](https://github.com/DevDooly/devdooly-platform-lab/pull/264)에서 **센서 분포→정확 센서 이벤트 이동**을 공개했습니다. 센서별 전체·실패 버튼, 원문 ID 정확 조건·단독 해제, 공유·CSV/JSON 조건 보존을 제공하며 센서 없는 기존 링크·형식1을 유지합니다. 로컬 웹421개·타입·빌드, 같은 main의 CI·Pages와 실제 공개10/3/1행·파일·공유·모바일을 확인했습니다. [사용법·관측 범위](features/sensor-outcomes.md#센서에서-이벤트로-이동)를 따르며 새 GET 없는 목록 이동과 공유 링크의 명시적 재조회를 구분합니다.

PR267의 **두 실행 센서별 비교**는 main과 공개 사이트에 반영했습니다. 원문 ID별 다섯 건수·실패 비율·미관측 구분, 검색·정렬·상세 이동을 제공합니다. 웹439개·같은 main의 CI·Pages와 실제 공개 비교·모바일·명시적 이벤트 재조회를 확인했으며 로컬 상세 이동의 HTTP429는 별도 실패 기록으로 유지합니다. [동작·해석 범위](features/sensor-comparison.md)와 [PR267의 공개 결과](https://github.com/DevDooly/devdooly-platform-lab/pull/267)를 따릅니다.

[PR269](https://github.com/DevDooly/devdooly-platform-lab/pull/269)의 **입력 순서별 이벤트 응답 비교**도 공개했습니다. 보고 입력4필드·판정2필드 차이와 미관측·중복 sequence 모호성을 구분합니다. 직렬 웹460개·타입·빌드, 같은 main의 Linux 기본 웹 검사·Pages·실제 공개 비교/명시적 상세 재조회를 확인했습니다. 최초 로컬 병렬 Kafka 검사1개 실패의 원인은 미확정이며 원 기록을 보존합니다.

[PR271](https://github.com/DevDooly/devdooly-platform-lab/pull/271)의 **저장 JSON 오프라인 이벤트 비교**를 공개했습니다. 웹490개·타입85파일 진단0·5페이지 빌드, source/main 같은 tree·같은 main CI/Pages와 공개 실제 파일 선택·비교·검색·더 보기·오류 시 직전 비교 보존·비우기·모바일을 확인했습니다. 합성 파일25그룹의 다섯 분류와 파일 출처·원필터·세 건수/부분 결과를 구분합니다. 초기 메시지 정규식·타입 assertion 실패와 PR269의 원인 미확정 Kafka 실패는 원 기록으로 보존하며 [실제 범위](features/offline-event-comparison.md#검증-상태)를 따릅니다.

[PR274](https://github.com/DevDooly/devdooly-platform-lab/pull/274)의 **현재 조건 비교 보고서 JSON 저장**도 공개했습니다. 최종 웹505개·타입86파일 진단0·5페이지 빌드, 읽기 잠금 경계 보완·반례, 정확 source/main·같은 main CI/Pages와 공개 실제25/1그룹 보고서 파일·모바일을 확인했습니다. 원파일의 조건·시각·세 건수와 현재 화면 조건을 나누고 전체 일치 그룹·모든 후보를 보존합니다. 로컬에서만 확인한0그룹/잘못된 새 파일 경계와 [공개 검증 범위](features/offline-comparison-report.md#검증-상태)를 구분합니다.

다음은 저장 파일이 없는 첫 방문자가 비교 기능을 체험하는 공백입니다. 아래는 필요한 이용 흐름의 우선순위이며 완료 기능을 반복 점검하는 목록이 아닙니다.

| 우선순위 | 필요한 기능 | 이번 범위와 선행 조건 |
| --- | --- | --- |
| 1 · 공개 완료 | **합성 예제 JSON 두 개 받기:** 저장 파일이 없는 첫 방문자도 파일 비교·보고서 저장을 체험합니다. | PR277·279의 fixture·시각null 예제와 명시 Blob 저장을 공개했습니다. 실제 다운로드 원문1,649/1,251bytes·5분류각1·모든 후보·보고서5,059bytes, 같은 main CI/Pages와 모바일을 확인했습니다. 원 정적 저장 실패와 한계는 [예제 검증](features/offline-event-samples.md#검증-상태)에 보존합니다. |

root는 제품·Git·브라우저를, native 에이전트는 겹치지 않는 정적 예제/테스트와 UI 파일을, 다른 채팅은 독립 계약·출처·문서·정확 head/main/CI·저장 파일 검토를 맡아 완료했습니다. 이번 파일 비교 흐름은 예제 받기→선택·검증→검색·분류·후보 확인→전체 일치 그룹 보고서 저장까지 이어집니다. 즉시 착수할 필수 후속 기능은 확인되지 않았습니다. 실제 이용 요구·반례가 확인되면 다음 한 기능을 선정하며, 보고서 재불러오기·CSV 등을 근거 없이 파생 개발하거나 아래 완료 기능·정상 운영 점검을 반복하지 않습니다. 네 보류·운영 pin·다른 PAUSED 자동화도 자동 재개하지 않습니다.

### 완료한 이용 기능

| 순서 | 기능과 필요한 이유 | 현재 범위 |
| --- | --- | --- |
| 1 | **두 실행 결과 비교:** 기존 단일 실행 화면을 오가며 계산하던 건수·비율·실패 사유 차이를 한 화면에서 확인 | [PR241](https://github.com/DevDooly/devdooly-platform-lab/pull/241) 공개 완료. [비교 화면](https://devdooly.github.io/devdooly-platform-lab/runs/compare/)의 목록 선택·두 상세 GET·공유 링크·CSV. [사용법·검증 기록](features/run-comparison.md) |
| 2 | **API 상세 조회 선택:** API 안내에서 실행 ID를 복사하지 않고 목록에서 고른 뒤 상세 조회 | [PR243](https://github.com/DevDooly/devdooly-platform-lab/pull/243) 공개 완료. [API 안내](https://devdooly.github.io/devdooly-platform-lab/api-guide/#api-detail)에서 명시적 목록 GET 후 ID를 고르고 상세 GET을 요청. 직접 입력과 선택/이전 응답 구분 유지. [사용법·검증 기록](features/api-run-selection.md) |
| 3 | **이벤트 처리 흐름 탐색:** 한 이벤트의 응답 필드·판정 사유·결과 분류를 연결해 처리 규칙을 이해 | 기존 이벤트 상세에 선택·세 카드 구현. runId·출처·sequence로 선택을 구분하고 원문·현재 참고 규칙을 함께 표시. 단계별 trace·당시 실행 코드 버전은 제공하지 않음. [사용법·검증 기록](features/event-flow.md) |
| 4 | **이벤트 검색·사유 필터:** 이미 읽은 최대 1,000건에서 ID·센서 부분 검색과 원시 사유·상태 조건을 함께 적용해 필요한 행을 찾기 | 구현·로컬 웹310개·타입·빌드, 실제 저장된 1,000건 검색과 키보드·모바일을 확인했습니다. 표/흐름의 같은 결과·중복 행과 조건 유지·선택 해제·입력 잠금을 제공합니다. 같은 main의 CI·Pages·공개 결과는 PR 검증 기록으로 구분합니다. [범위·검증](features/event-search.md) |
| 5 | **검색 결과 CSV·JSON 저장** | [PR249](https://github.com/DevDooly/devdooly-platform-lab/pull/249) 공개 완료. 필터·출처·원 관측 시각과 전체 검색 결과를 보관합니다. [형식·범위](features/event-export.md) |
| 6 | **실행·검색·선택 이벤트 공유 링크** | [PR251](https://github.com/DevDooly/devdooly-platform-lab/pull/251) 공개 완료. 명시적 재조회 후 조건·선택을 적용하며 당시 응답을 고정하지 않습니다. [공유 형식·범위](features/event-share.md) |
| 7 | **이벤트 표의 행 수·페이지 조절** | [PR253](https://github.com/DevDooly/devdooly-platform-lab/pull/253) 공개 완료. 표만 25·50·100행으로 나누며 흐름·공유·내보내기는 전체 검색 결과를 유지합니다. 성능 개선 수치는 측정하지 않았습니다. [범위·검증](features/event-pagination.md) |
| 8 | **비교 결과에서 이벤트 이어 보기** | [PR255](https://github.com/DevDooly/devdooly-platform-lab/pull/255) 공개 완료. 표시 중인 A·B의 전체·실패·사유별 링크로 상세에 이동하고 명시적 조회로 새 관측을 적용합니다. [사용법·범위](features/run-comparison.md#비교에서-이벤트-이어-보기) |
| 9 | **센서별 결과 분포 탐색** | [PR257](https://github.com/DevDooly/devdooly-platform-lab/pull/257) 공개 완료. 전체 조회 outcomes의 센서별 집계·목록 검색/정렬·FAILED 사유를 별도 탭에서 확인하며 이벤트 조건·공유·저장은 유지합니다. [집계·범위](features/sensor-outcomes.md) |
| 10 | **작업·export 기록 흐름** | [PR259](https://github.com/DevDooly/devdooly-platform-lab/pull/259) 공개 완료. [작업 관측](https://devdooly.github.io/devdooly-platform-lab/#job-observation)의 기록 단계·두 간격·원시 UTC 시각을 확인합니다. 같은 main의 CI·Pages와 공개 PC/모바일 확인을 마쳤습니다. 실제 공개 확인은 EXPORTED 9개이며, 나머지 상태·나노초 경계는 합성 검사로 구분합니다. [범위·검증](features/job-lifecycle.md) |

반복 정상 점검보다 이용자가 직접 조작하는 기능을 우선합니다. 각 기능의 변경에 필요한 검사와 실제 공개 이용 흐름만 확인하며, 완료된 운영 시험을 반복하지 않습니다.

의미 있는 문제가 확인되지 않으면 새 코드나 불필요한 수정은 만들지 않습니다. 보류 작업을 후속 과제로 자동 재개하지 않습니다.

## 한 작업을 마치는 기준

구현 전 문제와 기대 동작을 확인하고, 필요한 파일만 수정해 변경에 맞는 검사를 수행합니다. 코드가 바뀌면 PR의 검증된 head를 main에 반영한 뒤 해당 main의 CI·Pages와 공개 결과를 각각 확인합니다. 문서만 바뀌면 diff와 링크를 확인하며 불필요한 CI 재실행은 추가하지 않습니다. 공개 자산의 bytes 일치와 실제 브라우저 동작 확인은 서로 다른 근거로 기록합니다.

마지막으로 소스·실행 링크·확인한 범위와 한계를 근거 문서에 남기고 길잡이를 갱신합니다. 실행하지 않은 시험이나 아직 관측하지 않은 운영 결과는 완료로 올리지 않습니다.
