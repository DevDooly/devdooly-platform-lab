# Platform Lab 화면

Astro 정적 페이지와 React island로 구성한 개인 플랫폼 Lab MVP입니다. 소개·기술 경험·구축 기록은 정적으로 제공하고, 결과 탐색과 플랫폼 상태는 조회 API에 연결합니다. GitHub Pages 게시와 외부 서버 공개는 별도 배포 단계입니다.

## 실행

Node 24 LTS 또는 Node 22.12 이상을 사용합니다. 실제 검증 환경은 Node 24.19.0입니다.

```sh
npm ci
npm run check
npm test
npm run build
npm run dev
```

개발 주소는 `http://127.0.0.1:4321`입니다. 개발 서버는 `/api` 요청을 `http://127.0.0.1:8080`의 Spring Boot로 전달합니다. 환경에 따라 `API_PROXY_TARGET`을 지정할 수 있습니다.

`npm run preview`는 빌드된 화면을 4321에서 제공합니다. 정적 배포 결과는 `dist/`이며, 운영 Nginx는 `/api`를 API 서비스로 proxy해야 합니다. 프런트는 관리자 도구에 직접 연결하지 않습니다.

## 공개 환경변수

`.env.example`을 참고합니다. `PUBLIC_API_BASE_URL`의 기본값은 같은 origin의 `/api`입니다. 브라우저에 공개되는 값이므로 토큰·키를 넣지 않습니다. 다른 API origin을 사용할 때는 해당 API에서 CORS를 별도로 설정해야 합니다.

## 화면 동작

- 최초 로딩과 ‘실시간 조회’에서 실행 목록·플랫폼 요약·런타임 정보를 조회한 뒤 실행 상세를 가져옵니다.
- 실행 결과 선택, 센서 필터, 차트 포인트 상세, 이벤트 상태 필터와 결과 표를 제공합니다.
- 공개 작업 실행 POST는 제공하지 않습니다. 샘플은 읽기 전용입니다.
- API 연결 실패·시간 초과·응답 형식 오류 시 **실시간 Lab 연결 불가**와 **합성 데이터 샘플**을 표시합니다.
- `src/data/snapshot.json`은 화면 검증용 고정 합성 예시입니다. `capturedAt`은 샘플 파일 생성 시각이며, 실제 실행·배포를 관측한 시각이 아닙니다. 실제 기록을 수집·게시하는 작업은 외부 공개 단계에서 추가합니다.
- 소스 commit과 image digest를 주입하지 않은 런타임에는 미관측 상태를 표시합니다. 구성되지 않은 Jenkins·Argo CD를 정상 배포로 표시하지 않습니다.

## 계약과 검증

API 계약은 [demo-api.md](../../docs/contracts/demo-api.md), 독립 기대 결과는 [sensor-validation-v1.json](../../tests/scenarios/sensor-validation-v1.json)에 있습니다. Node 테스트는 샘플과 실시간 기록 구분, 입력 건수 보존, 잘못된 응답 거부, 실제 HTTP 왕복과 GET 전용 조회를 검증합니다.

고정 직접 의존성은 `package.json`, 전이 의존성은 `package-lock.json`에 기록됩니다. Astro 7.3.8, React 19.3.0, 공식 React integration 7.0.1을 사용합니다. TypeScript는 check 도구의 지원 범위에 맞춘 5.9.3입니다. `@vitejs/plugin-react`는 integration의 oxc peer 요구와 일치하는 6.1.1로 고정합니다.

공식 참고: [Astro 설치](https://docs.astro.build/en/install-and-setup/), [React integration](https://docs.astro.build/en/guides/integrations-guide/react/).

## GitHub Pages 경로

빌드 시 `SITE_URL=https://devdooly.github.io`, `SITE_BASE=/devdooly-platform-lab/`을 지정하면 저장소 Pages 하위 경로에 맞춰 정적 asset과 favicon 경로를 생성합니다. 기본값은 root `/`로, 같은 호스트에서 Nginx로 제공하는 컨테이너 배포에 사용합니다. Pages에서도 `PUBLIC_API_BASE_URL`을 별도로 지정할 수 있으며, 미설정 또는 연결 실패 시 합성 예시를 명시해 제공합니다.

## 실제 HTTP 연결 재검증

API와 UI가 실행 중일 때 `npm run smoke -- http://127.0.0.1:4321/`로 UI 응답과 같은 origin의 API 경유 결과를 독립 시나리오에 비교합니다. 컨테이너 배포 주소도 인자로 줄 수 있습니다. 다른 API 주소는 두 번째 인자로 지정합니다. 이 검증은 실제 API가 연결되어야 통과하며, 정적 샘플만 제공하는 Pages 공개 상태의 성공을 대신하지 않습니다.
