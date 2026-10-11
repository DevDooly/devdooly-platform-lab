# 실제 미니 PC 관측 기록 계약 v1

공개 파일 `public/data/lab-observation.json`에는 미니 PC에서 실제 수집하고 검증한 기록을 담았습니다. 수집 근거는 [서버 검증 기록](../../docs/evidence/mini-pc/README.md)에서 확인할 수 있습니다. 갱신할 때마다 [JSON Schema](schemas/lab-observation.schema.json)와 실행 가능한 validator로 내용을 확인합니다.

화면의 우선순위는 **연결된 API → 검증한 미니 PC 관측 기록 → 설명용 합성 샘플**입니다. 과거 관측 기록은 ‘미니 PC에서 확인한 마지막 기록’과 실제 수집 시각·source commit을 표시합니다. API에 연결되지 않은 정적 기록을 실시간 상태로 표시하지 않습니다.

## 수집 결과 구조

| 필드 | 값 또는 출처 |
| --- | --- |
| schemaVersion | 숫자 1 |
| kind | observed |
| capturedAt | 모든 조회를 마친 실제 UTC 수집 시각 |
| provenance.environment | mini-pc |
| provenance.sourceCommit | 실제 배포 API의 40자리 소스 commit SHA. unknown 거절 |
| provenance.collectorVersion | 문자열 1 |
| provenance.evidenceUrl | 선택. 검토한 GitHub/Pages HTTPS 근거 URL. 인증정보·query string 없음 |
| data.runs | GET /api/demo/runs의 items |
| data.detail | 선택한 canonical run의 GET /api/demo/runs/synthetic-v1-seed-42 응답 |
| data.summary | GET /api/platform/summary 응답 |
| data.releases | GET /api/platform/releases의 items |
| data.observedAt | summary의 observedAt |

실제 수집한 데이터만 넣습니다. summary.sourceCommit과 API release.sourceCommit은 provenance SHA와 일치해야 합니다. 이 버전은 고정 seed 42, 12개 입력의 7성공·3실패·2중복 시나리오를 대상으로 합니다. 실행 시작·완료와 API 관측 시각은 원본을 유지하고, capturedAt으로 덮어쓰지 않습니다. 모든 관측·실행 시각은 수집 완료 시각보다 미래일 수 없습니다.

v1의 Jenkins·Argo CD·Kubernetes component는 기존 API가 반환한 연결 상태를 유지합니다. 설치되어 있다는 이유로 NOT_CONFIGURED를 RUNNING으로 바꾸지 않습니다. API 런타임과 CI/CD 배포 이력은 별개이며, 별도 collector에서 실측한 배포 증거는 후속 계약에서 연결합니다.

## 공개 전 절차

1. 사설 관리 경로에서 실제 API 응답을 모읍니다. source SHA·이미지 digest·현재 실행 환경을 별도로 확인합니다.
2. 토큰·호스트 주소·관리 URL·원본 관리자 응답을 제외하고 위의 허용 필드만 구성합니다. 알 수 없는 추가 JSON 필드는 validator가 거절합니다.
3. 외부에 공개해도 되는 값인지 검토한 파일을 Git 제외 경로에 먼저 저장합니다.
4. `npm run validate:observation -- <검증할 파일 경로>`로 계약을 검증합니다. 이 명령은 비밀값을 출력하지 않고 수집 시각·SHA·건수만 요약합니다.
5. 확인된 파일만 `public/data/lab-observation.json`으로 복사하고 Git 변경 내용을 검토한 뒤 Pages를 게시합니다.

validator의 통과는 구조·기대 결과의 일치를 뜻합니다. 원격 수집과 실배포 확인을 대신하지 않으며, 원본 파일에 현재 시각을 넣는 것만으로 관측 기록을 만들어서는 안 됩니다.

파일이 없거나 잘못된 경우 설명용 합성 샘플로 돌아갑니다. 파일 조회에는 사이트 BASE_URL을 사용하므로 GitHub Pages 하위 경로와 Nginx root 배포에 모두 대응합니다. 브라우저에는 관리자 토큰을 전달하지 않습니다.
