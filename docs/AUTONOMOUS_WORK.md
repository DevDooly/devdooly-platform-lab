# 현재 범위와 다음 작업

기준: 2026-10-24(KST). 개인 Lab에서 실제 확인한 결과와 남은 작업을 찾는 길잡이입니다. 각 근거는 실행 당시의 범위이며 현재 가용성을 보장하지 않습니다.

[프로젝트 소개](../README.md) · [시작 안내](START_HERE.md) · [상세 진행 기록](NEXT_STEPS.md) · [공개 근거 검색](https://devdooly.github.io/devdooly-platform-lab/#evidence)

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

PR247 이후에는 다음 순서로 실제 이용 기능을 개발합니다. 기존 운영 시험을 재수행하는 계획이 아닙니다.

| 순서 | 기능과 필요한 이유 | 범위 |
| --- | --- | --- |
| 1 | **검색한 이벤트 CSV·JSON 저장:** 찾은 개별 행을 필터·출처·원 관측 시각과 함께 보관 | [PR249](https://github.com/DevDooly/devdooly-platform-lab/pull/249) 공개 완료. 현재 표와 같은 조건의 결과·입력 순서·중복 행을 보존하고 0건에도 조건을 담습니다. [형식·검증 범위](features/event-export.md) |
| 2 | **실행·검색·선택 이벤트 공유 링크:** 같은 화면의 조건을 다시 찾거나 전달 | [PR251](https://github.com/DevDooly/devdooly-platform-lab/pull/251) 공개 완료. 명시적 상세 GET 후 조건·선택을 적용하고 목록 밖 ID, 없는 이벤트·필터 제외, 실패 시 이전 화면 보존을 구분합니다. [공유 형식·범위](features/event-share.md) |
| 3 | **긴 이벤트 표의 행 수 조절:** 최대 1,000행을 나눠 보기 | 이번 구현. 표를 25·50·100행으로 나누고 선택 행 이동과 상·하단 페이지 조작을 제공합니다. 흐름·공유·내보내기는 전체 검색 결과를 유지합니다. 성능 개선 수치는 측정하지 않았습니다. [범위·검증](features/event-pagination.md) |

### 완료한 이용 기능

| 순서 | 기능과 필요한 이유 | 현재 범위 |
| --- | --- | --- |
| 1 | **두 실행 결과 비교:** 기존 단일 실행 화면을 오가며 계산하던 건수·비율·실패 사유 차이를 한 화면에서 확인 | [PR241](https://github.com/DevDooly/devdooly-platform-lab/pull/241) 공개 완료. [비교 화면](https://devdooly.github.io/devdooly-platform-lab/runs/compare/)의 목록 선택·두 상세 GET·공유 링크·CSV. [사용법·검증 기록](features/run-comparison.md) |
| 2 | **API 상세 조회 선택:** API 안내에서 실행 ID를 복사하지 않고 목록에서 고른 뒤 상세 조회 | [PR243](https://github.com/DevDooly/devdooly-platform-lab/pull/243) 공개 완료. [API 안내](https://devdooly.github.io/devdooly-platform-lab/api-guide/#api-detail)에서 명시적 목록 GET 후 ID를 고르고 상세 GET을 요청. 직접 입력과 선택/이전 응답 구분 유지. [사용법·검증 기록](features/api-run-selection.md) |
| 3 | **이벤트 처리 흐름 탐색:** 한 이벤트의 응답 필드·판정 사유·결과 분류를 연결해 처리 규칙을 이해 | 기존 이벤트 상세에 선택·세 카드 구현. runId·출처·sequence로 선택을 구분하고 원문·현재 참고 규칙을 함께 표시. 단계별 trace·당시 실행 코드 버전은 제공하지 않음. [사용법·검증 기록](features/event-flow.md) |
| 4 | **이벤트 검색·사유 필터:** 이미 읽은 최대 1,000건에서 ID·센서 부분 검색과 원시 사유·상태 조건을 함께 적용해 필요한 행을 찾기 | 구현·로컬 웹310개·타입·빌드, 실제 저장된 1,000건 검색과 키보드·모바일을 확인했습니다. 표/흐름의 같은 결과·중복 행과 조건 유지·선택 해제·입력 잠금을 제공합니다. 같은 main의 CI·Pages·공개 결과는 PR 검증 기록으로 구분합니다. [범위·검증](features/event-search.md) |

반복 정상 점검보다 이용자가 직접 조작하는 기능을 우선합니다. 각 기능의 변경에 필요한 검사와 실제 공개 이용 흐름만 확인하며, 완료된 운영 시험을 반복하지 않습니다.

의미 있는 문제가 확인되지 않으면 새 코드나 불필요한 수정은 만들지 않습니다. 보류 작업을 후속 과제로 자동 재개하지 않습니다.

## 한 작업을 마치는 기준

구현 전 문제와 기대 동작을 확인하고, 필요한 파일만 수정해 변경에 맞는 검사를 수행합니다. 코드가 바뀌면 PR의 검증된 head를 main에 반영한 뒤 해당 main의 CI·Pages와 공개 결과를 각각 확인합니다. 문서만 바뀌면 diff와 링크를 확인하며 불필요한 CI 재실행은 추가하지 않습니다. 공개 자산의 bytes 일치와 실제 브라우저 동작 확인은 서로 다른 근거로 기록합니다.

마지막으로 소스·실행 링크·확인한 범위와 한계를 근거 문서에 남기고 길잡이를 갱신합니다. 실행하지 않은 시험이나 아직 관측하지 않은 운영 결과는 완료로 올리지 않습니다.
