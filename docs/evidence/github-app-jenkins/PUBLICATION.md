# 갱신 검증 기록의 공개 반영

[PR #195](https://github.com/DevDooly/devdooly-platform-lab/pull/195)의 main `7fd71968aefd3d95d01d7d577807edc46990c088`에서 [Pages39941853780](https://github.com/DevDooly/devdooly-platform-lab/actions/runs/39941853780)의 build·deploy가 성공했습니다. [공개 갱신 카드](https://devdooly.github.io/devdooly-platform-lab/#github-app-renewal)는 실제 만료·401·자격증명 접근·200·새 만료를 KST로 표시합니다.

로컬 Node24.19.0의 웹229개 검사·생략0, Astro49파일 오류·경고·힌트0와 프로젝트 경로 두 페이지 빌드를 확인했습니다. 공개1280px·390px에서도 네 시각 `19:18:35 / 19:19:28 / 19:19:30 / 20:19:30`, 한 주기·접근 시 갱신이라는 범위, 근거 문서·공개 JSON 링크를 확인했습니다. 본문17px·링크44px, 문서 폭1265px/375px로 가로 넘침이 없었습니다. 기본 닫힘과 모바일 키보드 Enter로 펼치기·SUMMARY 초점도 확인했습니다. 새 직접 링크는 처음 연 탭에서 목표 위치를 확인했으며 reload의 기존 스크롤 복원과 구분합니다.

Pages 성공과 컨테이너 검증은 별개입니다. 같은 main의 [CI39941853833](https://github.com/DevDooly/devdooly-platform-lab/actions/runs/39941853833)은 웹 이미지에 요약 JSON이 없어 `Build container images` 단계에서 실패했습니다. 실패를 성공으로 바꾸지 않았으며 [PR #196](https://github.com/DevDooly/devdooly-platform-lab/pull/196)에서 공개 JSON 한 파일을 컨테이너의 상대 import 위치에 포함하도록 수정했습니다. 수정 소스 `686a1d37ae0fc847182cdcbc454f032444bcecbd`의 [Linux CI39942791387](https://github.com/DevDooly/devdooly-platform-lab/actions/runs/39942791387)은 실제 이미지 빌드·통합 verify·public-read-gateway를 통과했고, 이후 main `af3ecd27fb8d4bd7e86e1d1b42e7bf77e2becc3b`에 병합했습니다. 선택적 격리 실험은 실행하지 않았고 새 운영 이미지 배포도 하지 않았습니다.

별도 Jenkins build153은 위 공개 카드 main `7fd71968…`의 pending→success를 App 작성자 `devdooly-platform-lab-ops[bot]`로 기록했습니다. 실제 만료 검증 뒤의 새 CI 기록이지만, 원래 자연 만료 시험 자체의 `build=false` 범위를 소급해 바꾸지 않습니다.

별도 [공개 GET39940801991](../public-get/README.md)은 지정6개 응답의200·DTO 계약을 확인했습니다. 카드의 정적 과거 검증, 공개 Pages, 현재 API의 읽기 계약을 서로 다른 근거로 보존합니다. 새 토큰 발급·운영 배포·보류 네 항목의 재개는 하지 않았습니다.
