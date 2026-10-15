# 공개 플랫폼 수집기와 호스트 자동화

작업·export의 실제 배포 기록은 선택적 [작업 관측 자동화](JOBS_AUTOMATION.md)로 같은 outbound Pages 주기에 연결한다. 기존 플랫폼 관측 계약과 파일은 별도로 보존한다.

Python 표준 라이브러리만 사용하는 읽기 전용 수집기입니다. 공개 GitHub main의 Jenkins commit status와 K3s의 제한된 리소스를 읽고, platform-observation v1의 허용 필드만 저장합니다. 실제 RBAC 적용·수집·인증 실패 후 이전 성공 보존·Pages 게시를 검증했습니다. 전용 Pages 자격증명 등록 후 수동 host cycle·실제 systemd service·timer 최초 자동 실행의 게시와 전체 공개 JSON 일치도 확인했습니다. [실행 근거와 남은 범위](../../docs/evidence/platform-observation/README.md)를 함께 확인합니다.

## 통합 파일

| 역할 | 저장소 위치 |
| --- | --- |
| platform_collector.py | infra/observation/platform_collector.py |
| platform_contract.py | infra/observation/platform_contract.py |
| rbac.yaml | infra/observation/rbac.yaml |
| test_platform_collector.py | tests/observation/test_platform_collector.py |
| host_cycle.py·pages_uploader.py | infra/observation/의 호스트 수집·게시 요청 실행기 |
| platform-observation.service·timer | infra/observation/의 호스트 systemd 선언 |
| 검증 결과 | [공개 검증 요약](../../docs/evidence/platform-observation/summary.json) |

수집기 두 Python 파일은 같은 디렉터리에 둡니다. Python 3.10 이상이며 수집기 자체에는 추가 패키지나 Jenkins 관리자 credential, GitHub token, kubectl 실행, 관리자 kubeconfig fallback이 없습니다. 호스트 실행기가 관리자 설정으로 짧은 SA 토큰만 발급해 수집기에 전달하고, 별도 uploader가 Pages 전용 자격증명으로 게시를 요청합니다. UI의 [PLATFORM_OBSERVATION.md](../../apps/lab-web/PLATFORM_OBSERVATION.md), 구조 schema와 semantic validator가 같은 계약을 검증합니다. [자동화](AUTOMATION.md)와 [설치·운영 전환](INSTALL.md)에서 책임과 권한을 구분합니다.

## 출처와 정확한 의미

- mainCommit: 수집 중 두 번 읽어 동일함을 확인한 공개 저장소 main HEAD입니다.
- jenkins: 해당 main의 최신 ci/jenkins-test context입니다. 최신 항목을 고른 뒤 issuer DevDooly와 상태별 고정 description을 검사합니다. pending/success/failure/error는 실제 빌드 상태이며 수집 실패 코드와 구분합니다. 현재 main에 status가 없으면 null입니다. 과거 main의 성공을 대신 쓰지 않습니다.
- argo: 이름이 platform-lab-home인 Application의 status.sync.revision, sync, health입니다. 정상 상태가 아니어도 실제 응답을 읽었으면 수집은 성공할 수 있습니다.
- workloads.desired: API·웹 Deployment 및 DB StatefulSet의 spec.replicas입니다.
- workloads.ready: app/name=platform-lab, instance=lab, component=api/web/database의 실제 Pod 중 Running, Ready=True, 모든 containerStatuses.ready=true, 삭제 중이 아님을 만족하는 수입니다. Pod 이름·주소·환경·로그는 내보내지 않습니다.
- api/web image: Deployment template에 선언된 고정 GHCR digest입니다. 각 실행 컨테이너 imageID를 확인한 값이 아닙니다.
- deploymentSourceCommit: API Deployment template의 source-commit annotation입니다. 현재 JVM에 요청해 읽은 소스 값이 아닙니다. main·Argo revision·배포 소스 SHA는 다를 수 있습니다.

상태별 description은 정확히 Jenkins build #N: 뒤에 pending=validation in progress, success=tests and artifacts verified, failure=validation failed, error=validation aborted가 붙는 형태입니다. 임의 문구·issuer·URL·오류 원문은 출력하지 않습니다.

## 출력과 실패 처리

latestAttempt.attemptedAt과 성공의 capturedAt은 **시도 완료 UTC**이며 같은 문자열입니다. 실패에서는 완료 시각과 고정 오류 코드만 바꾸고, 이전에 검증한 lastSuccess 전체를 유지합니다. 처음부터 실패하면 lastSuccess는 null입니다. 유효하지 않거나 미래 시각인 이전 기록은 받아들이지 않으며 출력 파일을 덮어쓰지 않습니다.

HTTP timeout은 요청당 최대 6초, 전체 기본 기한은 60초입니다. GitHub status 검색은 최대 5페이지이며 모두 읽어도 항목이 없다고 확정할 수 없으면 수집 실패로 처리합니다. PodList가 잘렸으면 결과를 게시하지 않습니다. main이 수집 도중 이동해도 실패로 처리합니다.

TLS CA와 hostname 검증을 켜고 리디렉션과 환경 프록시를 사용하지 않습니다. 토큰은 파일에서만 읽으며 매 요청 다시 읽어 회전을 지원합니다. 응답은 최대 2MiB입니다. stdout에는 상태·고정 코드·완료 시각·마지막 성공 유무만 출력합니다.

출력은 같은 디렉터리의 0600 임시 파일을 fsync한 뒤 원자적으로 교체합니다. 출력별 배타 lock으로 동시 쓰기를 막고, 유효하지 않은 snapshot이나 교체 실패가 기존 파일을 지우지 않는지 테스트합니다. Ubuntu 격리 검사 41개와 실제 수집에서 POSIX 0600을 확인했습니다. 비정상 종료로 남은 lock은 실행 중 프로세스가 없는지 확인한 뒤 운영자가 처리합니다.

## 새 환경의 최초 서버 검증 순서

1. rbac.yaml의 기존 동명 SA/Role/Binding 충돌과 권한 범위를 검토합니다. namespace를 만들거나 기존 설정을 덮어쓰는 작업은 이 수집기가 하지 않습니다.
2. 관리자 권한은 RBAC 적용과 **10분 SA token 발급에만** 사용합니다. 실제 수집 HTTP는 platform-public-observer SA credential만 사용합니다. 서버 주소, CA 경로와 token 파일을 .local/ 아래에 두고 디렉터리 0700/파일 0600으로 보호합니다. 토큰을 콘솔·환경 변수·명령 인수에 넣지 않습니다.
3. 실제 토큰으로 허용 읽기를 확인하고, Secrets, Pod logs/exec, nodes, 다른 namespace, 다른 Argo Application, create/update/patch/delete가 거부되는지 확인합니다. 원문 HTTP body는 기록하지 않습니다.
4. 먼저 호스트에서 오프라인 테스트를 실행해 POSIX 파일 권한까지 확인합니다.
5. 아래 수집 명령을 한 번 실행하고 private 출력의 계약·출처·시각을 검증합니다. 아직 공개 파일을 자동 교체하지 않습니다.
6. 의도적으로 잘못된/만료된 별도 토큰 파일로 수집을 한 번 실패시켜 latestAttempt만 실패로 바뀌고 lastSuccess가 유지되는지 확인합니다. 실제 운영 토큰을 덮어쓰거나 Secret을 읽지 않습니다.
7. 웹의 구조·semantic validator도 통과한 허용 JSON만 검토 후 public/data/platform-observation.json에 별도로 복사합니다. API 응답의 NOT_CONFIGURED와 기존 lab-observation.json은 이 단계에서 바꾸지 않습니다.

관리자 발급의 예시입니다. 실제 서버/CA 값과 기존 관리자 명령의 세부 경로는 공개 문서에 넣지 않습니다.

```sh
umask 077
observer_state=.local/public-observer
mkdir -p "$observer_state"
chmod 700 "$observer_state"
sudo -n k3s kubectl -n platform-lab create token platform-public-observer --duration=10m > "$observer_state/token"
chmod 600 "$observer_state/token"
```

OBSERVER_KUBE_SERVER는 운영자가 대조한 HTTPS 주소, OBSERVER_CA_FILE은 해당 서버 CA 파일 경로입니다. 인증서 검증을 끄는 옵션은 없습니다.

```sh
python3 -B infra/observation/platform_collector.py \
  --server "$OBSERVER_KUBE_SERVER" \
  --ca-file "$OBSERVER_CA_FILE" \
  --token-file "$observer_state/token" \
  --output "$observer_state/platform-observation.json"
```

이전 성공 파일이 다른 위치에 있으면 --previous 경로를 추가합니다. 기본값은 --output의 기존 파일입니다. 성공 종료 코드는 0, 수집·검증·로컬 I/O 실패는 1입니다. 실행 후 토큰 파일을 정리하고, 원문/관리자 응답을 공개 저장소에 넣지 않습니다.

## 최소 RBAC

SA는 platform-lab namespace에 있으며 자동 token mount는 꺼져 있습니다. 두 namespace의 RoleBinding만 사용하고 ClusterRole은 없습니다.

| namespace | 리소스 | 허용 |
| --- | --- | --- |
| platform-lab | pods | get/list; 실제 요청은 고정 app/instance selector list |
| platform-lab | services | api, web, db 이름의 get |
| platform-lab | deployments | lab-platform-lab-api, lab-platform-lab-web 이름의 get |
| platform-lab | statefulsets | lab-platform-lab-db 이름의 get |
| argocd | applications | platform-lab-home 이름의 get |

get/list 외 동작, Secrets, logs, exec, nodes, 다른 Application과 namespace 권한은 정의하지 않습니다. RBAC의 Pod list는 namespace 범위이며 label selector 자체가 권한 경계는 아닙니다. 프로그램이 고정 selector와 응답 scope를 검증하고 필요한 집계만 내보냅니다.

## 오프라인 검증

저장소 루트에서 다음과 같이 실행합니다.

```sh
PYTHONPATH=infra/observation python3 -B -m unittest discover -s tests/observation -p 'test_platform_collector.py' -v
python3 -B -m unittest discover -s tests/observation -p 'test_phase3_automation.py' -v
```

합성 입력만 사용해 상태 4종, 최신 항목 신뢰 검증, 페이지 제한, main 이동, 실제 Pod 준비 조건, 허용 이미지, 출처 분리, 실패 시 이전 성공 보존, unknown 필드, 잘못된 날짜·나노초 순서, 원자적 파일 교체와 권한·리디렉션을 검증합니다. 합성 검사와 실제 서버 실행은 별도 기록합니다. 자동 수집·게시 요청은 호스트의 oneshot service와 timer로 실행하며 Kubernetes Job/CronJob은 구성하지 않았습니다. 최초 자동 실행을 포함한 11회의 Pages build·deploy success와 실제 서비스 완료 간격 1825.569287~1875.101367초를 확인했습니다. 공개 실시간 HTTP와 새 inbound 포트는 추가하지 않았습니다. 자격증명 만료·회전과 장기간 운영은 아직 검증하지 않았습니다.

## 공식 근거

- [GitHub commit statuses](https://docs.github.com/en/rest/commits/statuses?apiVersion=2022-11-28)
- [Kubernetes RBAC와 resourceNames](https://kubernetes.io/docs/reference/access-authn-authz/rbac/)
- [ServiceAccount token](https://kubernetes.io/docs/tasks/configure-pod-container/configure-service-account/)
- [Pod readiness와 lifecycle](https://kubernetes.io/docs/concepts/workloads/pods/pod-lifecycle/)
- [Python SSL certificate validation](https://docs.python.org/3/library/ssl.html#ssl.create_default_context)
