# Linux·MariaDB·컨테이너 실제 통합 검증

2026-10-11 GitHub Actions의 일회성 Ubuntu 24.04 runner에서 실제 Docker 이미지를 빌드하고 MariaDB·Spring Boot·Nginx를 실행했습니다. 미니 PC나 Jenkins에서 실행한 결과와 구분합니다.

- 검증 소스: `52802ef60089514054728ed36f8ee417d2db72e1`
- [성공한 CI 실행](https://github.com/DevDooly/devdooly-platform-lab/actions/runs/38133671877)
- [검증 요약](result.json), [교체 전 공개 응답](compose-before.json), [교체 후 공개 응답](compose-after.json)
- [재현 절차](../../runbooks/lab-ci.md)

## 통과한 결과

- API 테스트 15개, 실패·오류·건너뜀 0. Node 타입 검사·테스트 4개·정적 빌드 성공
- 고정 digest의 기반 이미지로 API·화면 컨테이너 빌드 성공
- 실제 MariaDB 연결과 Flyway migration·JPA schema validation을 거쳐 공개 API 응답 확인
- 같은 origin의 Nginx 화면·API smoke 통과. 입력 12 = 성공 7 + 실패 3 + 중복 2 + 대기 0, 독립 판정 12개 일치
- API UID/GID 10001, Nginx UID/GID 101로 실행. 공개 POST 405, 실제 source commit 전달 확인
- API만 새 주소로 교체한 뒤 기존 Nginx를 재시작하지 않고 조회 복구
- DB의 기존 run 시각·12개 판정·목록 보존, 중복 seed 없음. JVM 시작 시각과 API container는 변경
- 종료·허용한 검증 artifact 수집 성공. 비밀번호 파일과 전체 환경·inspect는 artifact에 포함하지 않음

첫 [CI 실행](https://github.com/DevDooly/devdooly-platform-lab/actions/runs/38133557142)에서는 기본 메타데이터 테스트가 CI의 SOURCE_COMMIT 영향을 받아 실패했습니다. 해당 테스트의 기본값 조건을 명시적으로 고정한 뒤 재검증했습니다. 실제 컨테이너에는 검증 소스 commit을 그대로 주입했고 응답과 대조했습니다.

## 확인하지 않은 범위

이 실행은 이미지의 레지스트리 게시, 미니 PC 설치, Kubernetes Pod·PVC·Secret 적용, Jenkins pipeline, Argo CD Sync, 외부 HTTPS 검증을 포함하지 않습니다. Helm 차트의 읽기 전용 루트 설정 역시 실제 Kubernetes 실행으로 검증하지 않았습니다. GitHub Pages는 합성 샘플을 표시하며 이 임시 CI 서버에 연결하지 않습니다.

runner 원본 artifact는 7일 보관됩니다. 재현에 필요한 공개 응답과 작은 요약은 이 디렉터리에 남깁니다.
