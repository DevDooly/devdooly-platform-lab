# 현재 상태에서 이어서 구축하기

계획 저장소를 GitHub에 연결했고 Java API와 포트폴리오 MVP를 구현했습니다. 로컬 검증과 서버 운영은 구분해 기록합니다. 체크 항목은 [진행 목록](ROADMAP.md), 설계는 [전체 계획](PROJECT_PLAN.md)에서 확인합니다.

## 완료한 작업

- GitHub `DevDooly/devdooly-platform-lab`에 초기 계획 등록
- Java 21·Spring Boot 4.1.1·Maven 3.10.0 고정과 공식 Wrapper 구성
- 합성 센서 이벤트 12건과 독립 기대 결과 정의
- 조회 API, JPA·Flyway, H2의 실제 HTTP·DB 통합 검증: 테스트 15개 통과
- Astro 7.3.8·React 19.3.0 화면, 타입 검사와 테스트 4개 및 정적 빌드 통과
- 실제 API proxy를 통한 화면 HTTP smoke 통과
- GitHub Pages 프로젝트 사이트와 게시 workflow 구성
- MariaDB Compose·컨테이너 정의와 Jenkins CI·플랫폼 설치 설정 준비

Jenkins·Argo CD·K3s는 미니 PC에 아직 설치하지 않았습니다. MariaDB 실제 실행과 이미지 빌드도 아직 검증하지 않았습니다. 공개 Pages의 정적 샘플을 실제 서버 실행 기록으로 표시하지 않습니다.

## 미니 PC에서 다음으로 진행할 순서

1. 사용자가 서버 ED25519 지문을 대조하고 전용 공개키를 등록합니다. 개인키는 접속 PC에 보관하며 Git에 넣지 않습니다.
2. 확인한 지문과 공개키로 SSH 인증 후 [호스트 점검](runbooks/host-inventory.md)을 읽기 전용으로 수행합니다. 자동 점검 도구는 `infra/scripts/inspect-host.py`이며 결과는 `.local/`에 저장합니다.
3. 기존 서비스·포트·데이터·백업·실제 가용 자원을 확인하고 설치 경로와 복구 범위를 정합니다. 기존 설정을 먼저 백업합니다.
4. [MariaDB·Compose](runbooks/local-compose.md)로 실제 DB 연결, 컨테이너, 재시작 멱등과 화면을 확인합니다.
5. [플랫폼 설치](runbooks/platform-install.md)에 따라 K3s·Jenkins·Argo CD를 적용합니다. CI pipeline의 실제 agent 기동과 실패 차단을 확인합니다.
6. 이미지 게시와 별도 GitOps 저장소를 연결하고 [준비한 앱 Helm chart](runbooks/app-helm.md)를 Argo CD로 배포합니다. Jenkins에서 같은 앱의 `helm upgrade`를 중복 실행하지 않습니다.
7. 인증된 관리 경로와 공개 HTTPS를 구성하고 외부망에서 확인합니다. 실제 공개 API가 준비되면 [Pages 연결 설정](runbooks/pages.md)을 갱신합니다.

서버 설치에 sudo가 필요하지만 비대화형 권한이 없다면, 사용자가 직접 확인하여 실행할 설치 파일을 준비합니다. 대화에 비밀번호를 요청하거나 전체 sudo 무암호 권한을 추가하지 않습니다.

## 로컬 검증을 이어갈 때

- [API 실행·테스트](../apps/api/README.md), [API 검증 근거](evidence/api-mvp/README.md)
- [화면 실행·테스트](../apps/lab-web/README.md), [화면 검증 근거](../apps/lab-web/VALIDATION.md)
- [독립 데이터 기대 결과](../tests/scenarios/sensor-validation-v1.json)
- [Jenkins CI 정의와 첫 실행](runbooks/jenkins-ci.md)

로컬 API는 H2 profile, Compose는 MariaDB입니다. `sourceCommit=unknown`은 실제 commit을 주입하지 않은 실행이며, releases 응답은 현재 JVM 정보입니다. 이를 빌드·배포 이력으로 바꾸려면 실제 Jenkins·Argo CD 관측을 연결해야 합니다.

## 아직 결정하거나 확인할 항목

| 항목 | 확인 시점 |
| --- | --- |
| Ubuntu 세부 버전, 기존 서비스·포트·데이터 경로 | SSH 인증 직후 읽기 전용 점검 |
| 별도 백업 위치, 설치·PV 경로와 복구 범위 | 서버 변경 전 |
| DDNS·공인 IP·CGNAT·HTTPS 방식과 도메인 | 외부 공개 전 |
| 이미지 게시 권한과 GitOps 저장소의 접근 범위 | CI/CD 연결 전 |
| S3 제품과 영속 catalog | 각각 4단계와 6단계 |

실제 호스트 주소와 SSH 메모는 `.local/host.md`에 있으며 clone에는 포함되지 않습니다. 공개 사이트는 [프로젝트 Pages](https://devdooly.github.io/devdooly-platform-lab/)를 사용하고 기존 TIL 및 사용자 사이트 저장소는 유지합니다.
