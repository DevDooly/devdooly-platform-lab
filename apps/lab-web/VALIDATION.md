# Lab 화면 검증 기록

검증일: 2026-10-11 (KST). 이 기록은 개발 PC의 MVP 검증이며, 미니 PC 외부 공개나 CI/CD 배포 성공을 뜻하지 않습니다.

## 환경

- Node 24.19.0, Astro 7.3.8, React 19.3.0
- Windows 개발 PC, 정적 빌드 `dist/`
- UI `127.0.0.1:4321`, Vite `/api` proxy → Spring Boot `127.0.0.1:8080`
- API는 `local-dev`의 H2 검증 환경. 화면에 `H2 (local validation only)`로 표시

## 확인한 결과

| 검증 | 결과 |
| --- | --- |
| `npm run check` | 오류 0, 경고 0, hint 0 |
| `npm test` | 테스트 4개 통과 |
| `npm run build` | 정적 페이지 1개와 React island 빌드 성공 |
| 개발 화면 HTTP | 200, 한국어 샘플 안내 포함 |
| 같은 origin API proxy와 실제 Spring Boot HTTP 연결 | 입력 12 / 성공 7 / 실패 3 / 중복 2 / 대기 0 |
| 실시간 summary | 관측 시각 반환, 공개 실행 false, Jenkins NOT_CONFIGURED |
| 런타임 정보 | LOCAL_RUNTIME, CI/CD 배포 이력으로 표시하지 않음 |

테스트는 독립 시나리오의 12개 기대 분류와 fallback 일치, 건수 보존과 잘못된 응답 거부, 실제 HTTP 요청 및 ID 인코딩, GET 전용 조회를 확인합니다. 고정 샘플에는 실행·관측 시각과 배포 이력을 넣지 않았습니다.

브라우저의 화면·상호작용 검증과 실제 MariaDB/컨테이너 검증은 저장소의 통합 검증 기록에서 별도로 확인합니다. 외부 공개·Jenkins·Argo CD·K3s 연결을 이 파일의 결과로 추정하지 않습니다.
