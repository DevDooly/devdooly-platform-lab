# Jenkins·Actions·Argo CD 대표 사례

## 목적과 읽는 흐름

취업·이직 포트폴리오에서 빌드 성공과 이미지 게시·실제 배포를 구분하고 설계 판단을 설명합니다. [대표 사례](https://devdooly.github.io/devdooly-platform-lab/cases/cicd-delivery/)는 기술 선택 → 병렬 CI와 게시 gate → 정상·실패·복귀 기록 → A/B/A 관측 → 화면 → 설정 → 새 환경 이식 순서입니다. 기술 목차와 Jenkins·K3s/Argo 안내, README에서 진입합니다.

## 구현과 근거

- 정적 Astro 페이지와 native details를 사용합니다. JavaScript 준비 전에도 세 사례와 정확한 digest를 펼칠 수 있습니다. 관리 API 호출·로그인·운영 변경 기능을 추가하지 않습니다.
- `docs/evidence/cicd-gate/summary.json`의 정상 Jenkins API/웹 수치와 세 rollout 관측의 시각·소스·이미지·GitOps revision·건수를 빌드 시 직접 읽습니다. 컨테이너 빌드에도 해당 공개 summary만 COPY하고 최종 Nginx 이미지는 생성한 dist만 사용합니다.
- 사례는 2026-10-11 UTC의 정상 PR #2·양쪽 CI 실패 차단·실제 복귀 PR #3입니다. 테스트 원복 후 생성된 GitOps 초안 PR #4는 게시 회복 후 미배포 종료한 별도 기록입니다. 원 실패·HTTP403·최신 pending 차단을 보존합니다.
- 설정 설명 기준은 `05f2aab596d98f08f432b2b31e2cc382bc851c31`입니다. 10월23일 App 연결과 10월11일 PAT 실험을 구분합니다. 원 근거를 수정하지 않고 현재 운영 안내의 오래된 PAT/빌드 이력 문구만 교정합니다.
- 캡처는 기존 2026-10-26 공개 관측 화면을 사용합니다. 원 관측 07:45 UTC·관리 UI와의 차이·현재 가용성 한계를 표시합니다.
- `CicdSetupGuide.astro`는 Jenkins agent/App·게시 gate·GHCR·Argo 두 values/destination/project·sync·Secret/storage/schema 8개 설정과 새 환경 6단계를 연결합니다. repository URL 외에 status/gate/proposer의 저장소 제한과 허용 경로도 이식 대상입니다.

## 검증 상태

로컬 Astro 105파일 진단 0·Pages base의 18페이지 빌드를 통과했습니다. 진입 4페이지의 링크·anchor 236개와 원 summary의 세 관측을 대조했습니다. 실제 브라우저에서 목차→사례 진입, 정상 기본 펼침·실패 Space·복귀 Enter·정확 digest 펼침, 8개 설정·6단계, 캡처 로딩을 확인했습니다. 페이지의 script는 0개이며 390px에서 본문 17px·문서375px로 가로 넘침이 없습니다. 최초 설정 grid702px 넘침은 실제로 관측한 뒤 최소 track·내용 줄바꿈으로 수정했습니다.

독립 구현·사실 검토에서 비공개 저장소의 public-only 게시 gate 제약과 PR #4의 표현을 보완했습니다. 정확한 head의 PR 병합·같은 main CI/Pages·공개 결과는 해당 PR 완료 기록에서 확인합니다. 이 로컬 결과는 새 K3s/Jenkins 기동·운영 rollback 실행이 아닙니다.

Pages 토큰 교체·별도 환경 K3s/Jenkins 기동 복원·예산 정책·PR #102는 보류합니다. 운영 image/source pin·기존 서비스/데이터·자동 이미지 제안 PR·다른 PAUSED 자동화는 바꾸지 않습니다.
