# 플랫폼 관측 기록 공개

미니 PC의 읽기 전용 수집기가 허용된 필드만 JSON으로 만들고, GitHub Actions가 검증한 기록을 Pages에 게시합니다. Jenkins·Argo CD 관리자 화면이나 Kubernetes API를 외부에 공개하지 않습니다. 기존 [합성 데이터 관측 v1](../../apps/lab-web/OBSERVATION.md)과 별도 형식입니다.

## 읽는 방법

카드는 마지막 수집 시도와 마지막 성공 기록을 구분합니다. 실패한 새 시도가 들어와도 이전 정상 기록의 내용과 시각을 유지합니다. 2시간이 지난 정상 기록은 오래된 기록으로 표시하며, 파일 조회 실패를 서비스 중단으로 판단하지 않습니다.

- Jenkins는 **수집 당시 main SHA**에 연결된 가장 최근 `ci/jenkins-test` status를 확인합니다. 이전 SHA의 성공으로 대신 채우지 않습니다.
- Argo GitOps revision과 API Deployment template의 소스 annotation을 별도로 표시합니다. 이전 이미지로 복구하면 main과 배포 소스가 달라도 정상입니다.
- Pod 준비 수는 삭제 중이 아닌 Running·Ready Pod이고 모든 컨테이너가 준비된 경우만 셉니다. 목표 수는 Deployment·StatefulSet의 선언입니다.
- API·웹 이미지 digest는 Deployment의 선언 값입니다. 실행 컨테이너의 imageID까지 검증했다는 뜻은 아닙니다.

## 수집 권한

[수집기와 실행 안내](../../infra/observation/README.md), [RBAC 선언](../../infra/observation/rbac.yaml), [공개 데이터 계약](../../apps/lab-web/PLATFORM_OBSERVATION.md)을 함께 확인합니다. 전용 ServiceAccount에는 지정된 Lab Deployment·StatefulSet·Service와 Pod, 지정된 Argo Application의 조회만 허용합니다. Secret·로그·exec·노드 조회와 리소스 변경은 허용하지 않습니다.

호스트 실행기는 짧게 유효한 ServiceAccount token을 발급해 수집기에 전달합니다. 수집기에는 관리자 인증서나 Jenkins credential을 전달하지 않습니다. 공개 파일에는 주소·사용자 정보·비밀값·원본 응답을 넣지 않습니다.

## Pages 게시 규칙

[`pages.yml`](../../.github/workflows/pages.yml)은 main의 코드 게시와 `workflow_dispatch`의 관측 JSON을 처리합니다. 관측 갱신은 Git commit을 만들지 않으므로 이미지 게시나 GitOps 배포를 반복해서 일으키지 않습니다. 실행은 하나의 대기열로 직렬화합니다.

입력은 이벤트 파일에서 읽고 16KiB, 중복 JSON 키, 엄격한 필드·타입·UTC 날짜 검증을 통과해야 합니다. 원본 입력이나 인증 토큰을 로그에 출력하지 않습니다. 정상 기록과 수집 시도의 시각은 독립적으로 비교하며, 같은 시각의 서로 다른 내용은 거부합니다.

이전 기록의 기준은 이 워크플로의 **실제 deploy job이 성공한 정확한 attempt의 artifact**입니다. CDN 응답이나 단순 workflow 성공으로 대체하지 않습니다. 저장소에는 최초 게시용 실제 수집 seed가 있습니다. 이후에는 seed와 성공 게시 기록의 시각을 비교하므로 코드 변경이 오래된 seed로 기록을 되돌리지 않습니다. 예상 artifact의 만료·누락, 불완전한 실행 이력, 조회 오류에서는 게시를 중단합니다.

실행 이력은 페이지를 끝까지 읽되 최대 10,000개로 제한합니다. 상한 도달 또는 동일 run의 10회 초과 재실행에서는 seed로 되돌아가지 않고 중단합니다. 이 규모에 가까워지기 전에 별도 영속 관측 저장소나 검증 가능한 최신 기록 색인을 도입해야 합니다. artifact 보존 기간은 90일이며, 장기간 중단 후에는 이전 기록을 확인한 뒤 게시 경로를 복구합니다.

## 자동 실행 준비

자동 게시에는 이 저장소의 `Actions: Read and write` 전용 token이 필요합니다. Jenkins commit-status token과 분리하며 token을 Git에 저장하지 않습니다. 전용 credential이 준비되기 전에는 주기 실행을 켜지 않습니다. 수동 게시·브라우저 검증과 자동 주기 활성화는 [실행 근거](../evidence/platform-observation/README.md)에 각각 기록합니다.

실제 Lab 중단 상황, 외부 실시간 조회 API와 공개 HTTPS 경로는 별도 검증 대상입니다. 인증 실패 시 기록 보존 검증을 이들 검증으로 대체하지 않습니다.
