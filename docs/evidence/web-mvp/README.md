# 포트폴리오 최초 공개 검증

2026-10-11 GitHub Pages에 MVP를 게시했습니다. 배포한 소스는 `246743bca6368c34bd41c15292877f4ed7fad413`이며 이후 문서·인프라 커밋과 구분합니다.

- [공개 사이트](https://devdooly.github.io/devdooly-platform-lab/)
- [성공한 Actions 실행](https://github.com/DevDooly/devdooly-platform-lab/actions/runs/38133020850): npm ci, check, 테스트 4개, build, artifact 업로드와 Pages 배포
- [공개 HTTP와 브라우저 확인](public-http.json): 문서 및 연결된 JS·CSS·favicon 모두 200
- [PC 화면](desktop.jpg), [모바일 Lab 화면](mobile-lab.jpg)

공개 브라우저에서 샘플 안내, 차트 포인트 선택, 실패 필터의 3행, 미관측 실행 시각과 CI/CD 미연결 상태를 확인했습니다. 모바일 393×852 viewport에서 페이지 가로 넘침이 없었고, 이벤트 표는 내부 스크롤을 사용합니다. 테스트 후 viewport를 원래 크기로 복원했습니다.

이전 개발 PC 검증에서는 실제 local-dev API를 연결해 실시간 조회·센서 필터·실패 필터를 확인했습니다. 그 실행은 H2이며 [API 검증](../api-mvp/README.md)과 [화면 테스트](../../../apps/lab-web/VALIDATION.md)에 근거가 있습니다. 공개 Pages는 현재 합성 샘플을 제공하고 미니 PC API는 연결 전입니다. 샘플 파일 생성 시각을 실제 실행 시각으로 표시하지 않습니다.

MariaDB 컨테이너 실행, 미니 PC의 HTTPS API, Jenkins pipeline 및 Argo CD 배포는 이 기록에서 검증하지 않았습니다.
