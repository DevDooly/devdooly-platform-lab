# 현재 범위와 다음 작업

기준: 2026-10-24(KST). 개인 Lab에서 실제 확인한 결과와 남은 작업을 찾는 길잡이입니다. 각 근거는 실행 당시의 범위이며 현재 가용성을 보장하지 않습니다.

[프로젝트 소개](../README.md) · [시작 안내](START_HERE.md) · [상세 진행 기록](NEXT_STEPS.md) · [공개 근거 검색](https://devdooly.github.io/devdooly-platform-lab/#evidence)

## 최근 확인한 범위

| 항목 | 확인한 결과와 범위 |
| --- | --- |
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

1. **이용자 길잡이:** 완료·보류·미검증을 구분하고, README에서 실제 화면과 근거를 쉽게 찾도록 정리합니다.
2. **재현한 UI 문제:** 실제 조작에서 확인한 문제에 한해 작은 변경으로 고칩니다. 합성 재현·로컬 화면·공개 확인의 범위를 각각 기록합니다.
3. **문서와 링크 정합성:** 현재 안내와 연결된 근거의 상태·출처·상대경로를 대조합니다. 과거 실행 기록은 당시 결과로 보존합니다.

의미 있는 문제가 확인되지 않으면 새 코드나 불필요한 수정은 만들지 않습니다. 보류 작업을 후속 과제로 자동 재개하지 않습니다.

## 한 작업을 마치는 기준

구현 전 문제와 기대 동작을 확인하고, 필요한 파일만 수정해 변경에 맞는 검사를 수행합니다. 코드가 바뀌면 PR의 검증된 head를 main에 반영한 뒤 해당 main의 CI·Pages와 공개 결과를 각각 확인합니다. 문서만 바뀌면 diff와 링크를 확인하며 불필요한 CI 재실행은 추가하지 않습니다. 공개 자산의 bytes 일치와 실제 브라우저 동작 확인은 서로 다른 근거로 기록합니다.

마지막으로 소스·실행 링크·확인한 범위와 한계를 근거 문서에 남기고 길잡이를 갱신합니다. 실행하지 않은 시험이나 아직 관측하지 않은 운영 결과는 완료로 올리지 않습니다.
