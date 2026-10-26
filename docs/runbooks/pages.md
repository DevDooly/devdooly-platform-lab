# 포트폴리오 Pages 게시

저장소의 `.github/workflows/pages.yml`은 `main`의 화면 변경을 검사하고 정적 페이지를 게시합니다. 대상 주소는 `https://devdooly.github.io/devdooly-platform-lab/`입니다. 실제 배포 성공 여부는 GitHub Actions 실행 결과로 확인합니다.

## 빌드 설정

- Node 24.19.0, npm lockfile 사용
- SITE_URL=https://devdooly.github.io
- SITE_BASE=/devdooly-platform-lab/
- check, HTTP 계약 테스트, 정적 build를 통과한 artifact만 배포
- 공식 Actions를 확인한 commit SHA로 고정

Pages의 source는 GitHub Actions로 설정합니다. 업로드와 배포는 workflow의 일회성 GITHUB_TOKEN/OIDC 권한을 사용하며 개인 토큰을 소스에 넣지 않습니다.

## 공개 API 연결

현재 포트폴리오는 공개 HTTPS API와 연결되어 있습니다. [공개 연결 근거](../evidence/public-read-https/README.md)에서 허용 GET 6개와 지정 거부 요청의 검증 범위를 확인할 수 있습니다. 이 기록은 해당 실행 시점의 결과이며 현재 가용성을 보장하지 않습니다.

새 환경에서는 저장소 변수 `LAB_PUBLIC_API_URL`에 `/api`까지 포함한 공개 HTTPS 주소를 지정합니다. Pages workflow는 이를 빌드 환경의 `PUBLIC_API_BASE_URL`로 전달하며, 주소를 변경하면 다시 빌드·게시해야 합니다. 변수가 없을 때의 기본값 `/api`는 로컬 개발의 API proxy나 같은 origin의 API 배치를 위한 값입니다. GitHub Pages 자체가 API를 제공하는 것은 아니므로, 새 Pages 사이트를 게시하는 것만으로 공개 API 연결이 완성되지는 않습니다.

그 주소는 프런트 번들에 포함되므로 인증 토큰이나 사설 접속 주소를 넣지 않습니다. API 서버는 실제 포트폴리오 origin에 필요한 CORS 정책을 설정해야 합니다. 관리자 API를 연결하지 않습니다.

## 되돌리기

문제가 생기면 마지막으로 확인한 화면 변경을 Git revert하고 다시 게시합니다. Pages artifact의 되돌리기는 API·DB·Kubernetes의 복구와 별개입니다.

공식 참고: [Astro의 GitHub Pages 배포](https://docs.astro.build/en/guides/deploy/github/), [Pages의 사용자 workflow](https://docs.github.com/en/pages/getting-started-with-github-pages/using-custom-workflows-with-github-pages).
