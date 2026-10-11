# 실제 미니 PC 배포와 처리 결과

관측 완료: `2026-10-11T11:50:24.807323Z` · 앱 소스: `820d5c398af2b1d62a0566f9184d015ab22e9f15` · 환경: Ubuntu 미니 PC의 K3s 단일 노드.

## 확인한 연결

| 확인 대상 | 실제 결과 |
| --- | --- |
| SSH·호스트 | 사용자 대조 지문과 전용 공개키로 인증 |
| K3s | v1.36.5+k3s1, Node Ready, CoreDNS·local-path·metrics-server 준비 |
| 클러스터 통신 | API TLS(401 인증 필요), 내부 DNS, 외부 DNS, 외부 HTTPS 모두 통과 |
| GHCR | 검증 성공 소스의 API·웹 이미지 게시, 미니 PC에서 인증 없이 digest pull |
| Argo CD | platform-lab-home Synced·Healthy, 적용 revision `ee91e5dc743b71c585680ebf36756ee71fb4a5a7` |
| 앱 | API·웹·MariaDB 3개 Pod Ready, DB PVC Bound 10Gi |
| 웹→API→DB | Nginx를 통한 실제 조회와 MariaDB SELECT 1 통과 |
| 처리 규칙 | 입력 12·성공 7·실패 3·중복 2·대기 0, 독립 기대 분류 12개 일치 |
| API 교체 | Pod를 한 번 재생성해 run ID·저장 시각·처리 결과 유지와 웹 재조회 확인 |
| 공개 동작 제한 | 실행 POST 405, 없는 run 404 |
| 기존 환경 보존 | Docker 23개 동일 ID로 Running, 설치 감사 이후 재시작 0, UFW 상태·설정 17개 동일 |

[실제 요약 JSON](summary.json), [이미지 게시 manifest](image-manifest.json), [GitOps 값](../../../gitops/environments/home-lab/values.yaml), [Jenkins 실제 빌드](../jenkins-ci/README.md)를 연결합니다. 원본 관리자 응답·접속 주소·비밀값은 공개하지 않습니다.

기존 환경 보존의 최종 점검 시각은 `2026-10-11T11:52:29.096303+00:00`입니다. SSH 관리 터널에서 Jenkins 로그인 화면 HTTP 200과 Argo CD 인증서 지문 일치를 확인했고 임시 터널을 종료했습니다. 실제 브라우저 관리자 로그인은 별도 확인이 필요합니다.

## 발견하고 교정한 문제

1. 같은 저장소에서 chart와 values의 서로 다른 revision을 조합한 초기 Argo 설정은 manifest 생성에 실패했습니다. 단일 source의 상대 values 경로와 필요한 ServiceAccount 종류 허용으로 교정했습니다. [결정](../../adr/0003-gitops-in-existing-repository.md)
2. Nginx 동적 DNS resolver가 짧은 `api`에 Kubernetes search domain을 붙이지 않아 웹 API가 502를 반환했습니다. Compose 기본 이름은 유지하고 Helm이 namespace를 포함한 Service FQDN을 주입하도록 수정한 새 이미지로 확인했습니다. 정적 `/` readiness만으로 API 연결 성공을 판단하지 않았습니다.
3. 첫 API 기동 때 DB 초기 준비 전에 연결을 시도해 재시작 2회가 있었습니다. 초기화 후 DB·API 준비와 실제 데이터 조회를 별도로 확인했습니다. 무중단 배포를 주장하지 않습니다.
4. Jenkins 첫 빌드의 플러그인 충돌과 실제 재검증은 [Jenkins 근거](../jenkins-ci/README.md)에 별도로 기록합니다.

## 공개 화면과 검증 범위

[포트폴리오](https://devdooly.github.io/devdooly-platform-lab/)는 미니 PC API에서 수집하고 계약을 검증한 [관측 파일](../../../apps/lab-web/public/data/lab-observation.json)을 읽습니다. **미니 PC에서 확인한 마지막 기록**이며 실시간 상태가 아닙니다. 표시 시각은 위 관측 완료 시각입니다. 수집 이후 서버 상태가 같다고 보장하지 않습니다.

API의 Jenkins·Argo CD·Kubernetes `NOT_CONFIGURED`는 **상태 수집 연결 전**을 뜻합니다. 설치 사실만으로 해당 값을 변경하지 않습니다. releases 응답은 현재 JVM 정보이고 CI/CD 배포 이력이 아닙니다. 현재 이미지 게시자는 Actions이며 Jenkins는 테스트와 패키징을 수행합니다.

관리 도구는 ClusterIP와 [SSH 접속](../../runbooks/admin-access.md)을 사용합니다. 기존 Docker·프록시·방화벽과 시스템 Helm을 보존했습니다. ClusterIP 자체가 클러스터 내부 접근을 격리하는 정책은 아닙니다.

설정 감사 백업과 Jenkins 변경 전 백업은 동일 서버에만 있습니다. 외부 백업·복원·재부팅 복구·이전 image digest 복구·외부망의 실시간 API는 아직 검증하지 않았습니다. PV reclaimPolicy는 Delete입니다. StatefulSet의 PVC Retain 설정이 수동 PVC·namespace 삭제를 막지는 않습니다. [앱 운영 절차](../../runbooks/app-helm.md)

## 재확인

1. [K3s bootstrap](../../runbooks/k3s-bootstrap.md)과 [플랫폼 설치](../../runbooks/platform-install.md)의 버전·전용 경로를 따릅니다. 기존 설치에 bootstrap apply를 반복하지 않습니다.
2. [GitOps 선언](../../../gitops/README.md)의 source revision·image digest와 실제 Pod 이미지·Argo 상태를 비교합니다.
3. 웹을 통해 `/api/demo/runs`, run 상세, `/api/platform/summary`, `/api/platform/releases`를 조회합니다. [독립 기대 결과](../../../tests/scenarios/sensor-validation-v1.json)와 모든 분류를 비교합니다.
4. [관측 계약](../../../apps/lab-web/OBSERVATION.md)으로 공개 허용 필드와 시각·source SHA를 검증한 파일만 게시합니다.
