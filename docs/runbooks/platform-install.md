# K3s·Jenkins·Argo CD 설치와 확인

2026-10-11 미니 PC에서 K3s와 관리 도구를 설치했습니다. Node와 시스템 Pod Ready, 클러스터 API TLS·내부 DNS·외부 DNS·HTTPS 연결 검사를 확인했고, Argo CD 앱 Application은 Synced/Healthy입니다. 이 상태만으로 화면에서 API를 조회하는 HTTP 경로, Jenkins 실제 CI, 재부팅 복구까지 검증된 것은 아닙니다. 최신 결과와 한계는 [미니 PC 검증 기록](../evidence/mini-pc/README.md)과 [Jenkins CI 절차](jenkins-ci.md)를 따릅니다.

## 기존 호스트 보존과 설치 전 조건

1. [호스트 점검](host-inventory.md)으로 Ubuntu 버전, 기존 서비스·runtime·포트·디스크·데이터와 백업 범위를 확인합니다. 기존 K3s가 있으면 신규 bootstrap을 다시 실행하지 않습니다.
2. 호스트의 기존 80/443 서비스는 유지합니다. Kubernetes API·kubelet·Flannel 포트와 Pod CIDR 10.42.0.0/16, Service CIDR 10.43.0.0/16이 기존 listener·route·Docker subnet과 겹치지 않아야 합니다.
3. K3s 데이터는 /var/lib/devdooly-platform-lab/k3s, local-path PV는 /var/lib/devdooly-platform-lab/storage를 사용합니다. 기존 앱 데이터 경로를 재사용하지 않습니다.
4. SSH 지문·공개키를 확인하고 접속 정보·점검 원본·키는 .local에만 보관합니다. 관리 API와 관리 UI를 인터넷에 포워딩하지 않습니다. 공인 IPv6 접근도 따로 확인합니다.
5. sudo 인증이 필요한 작업은 사용자가 자신의 서버 터미널에서 수행합니다. 비밀번호를 전달하거나 전체 NOPASSWD 권한을 추가하지 않습니다.

실제 설치 후 기존 Docker 컨테이너 23개의 ID·실행 상태와 설치 이후 재시작이 없음을 확인했습니다. UFW 상태와 백업한 설정 파일 내용도 동일했습니다. 이는 모든 기존 앱의 HTTP 응답을 검증했다는 뜻은 아닙니다. Docker·containerd·UFW를 새 Lab 때문에 재시작하거나 기존 정책을 변경하지 않습니다.

## 버전과 자원

[고정 목록](../../infra/platform/versions.lock.json)은 공식 다운로드와 검증한 SHA256을 기록합니다. K3s v1.36.5+k3s1, Jenkins chart 5.9.68/core 2.580.1, Argo CD chart 10.10.2/app v3.5.4, 저장소 전용 Helm v4.3.0을 사용합니다. Jenkins 플러그인 조합은 현재 values·잠금 목록과 실제 CI 결과를 함께 확인합니다.

| 구성 | RAM 예산 | 저장공간 |
| --- | --- | --- |
| OS·K3s | 4GiB 예상 | 기존 파일시스템 여유 확인 |
| Jenkins controller·sidecar | 요청 832MiB, 제한 합계 1664MiB | local-path PVC 10GiB |
| 빌드 agent | 동시 Pod 1개, 요청 1024MiB·제한 3968MiB | emptyDir·cache |
| Argo CD 상시 4개 Pod | 요청 합계 544MiB, 제한 합계 1408MiB | PVC 없음 |
| API·화면·MariaDB | 요청 합계 832MiB, 제한 합계 2496MiB | DB local-path PVC 10GiB |

요청량은 예약값, 제한량은 상한이며 실측이 아닙니다. 32GiB 전체를 배정하지 않고 기존 서비스와 파일 cache에 여유를 남깁니다. 빌드와 Spark·Trino 실행을 겹치지 않습니다. Dex·Notifications·Redis HA는 끄고 ApplicationSet replica는 0으로 시작합니다. 단일 PC는 고가용성 구성이 아닙니다.

## 신규 K3s 설치

신규 Ubuntu 22.04·x86_64 호스트에서는 [검토 가능한 bootstrap 절차](k3s-bootstrap.md)를 사용합니다. 고정 installer·바이너리·checksum 확인, root 전용 설정 백업, 기존 경로·서비스 충돌 거부와 실패 처리가 포함되어 있습니다. 이미 설치한 호스트에서 재실행하거나 기존 설정을 덮어쓰는 도구가 아닙니다.

    NODE_IP='PRIVATE_IPV4'
    sudo bash infra/scripts/bootstrap-k3s.sh --check --node-ip "$NODE_IP"
    sudo bash infra/scripts/bootstrap-k3s.sh --apply --node-ip "$NODE_IP"

PRIVATE_IPV4는 서버에 할당된 실제 내부 IPv4로 바꿉니다. --check 통과 후 --apply를 검토해 실행합니다. Traefik·ServiceLB를 끄고 API는 해당 내부 주소에 bind합니다. 127.0.0.1 TLS SAN은 SSH 터널 관리용입니다. config·kubeconfig·token·Secret 암호화 설정은 root 소유 0600이며 내용을 로그로 출력하지 않습니다.

설치 후 Node Ready, CoreDNS·local-path·metrics-server rollout과 [network-smoke.yaml](../../infra/scripts/network-smoke.yaml)을 확인합니다. 이번 호스트에서는 UFW 허용 규칙 추가가 필요하지 않았습니다. K3s가 CNI·kube-proxy 규칙을 생성하는 것과 기존 UFW 정책 보존은 구분합니다.

## 서버 Helm과 차트 원본

기존 시스템 Helm 3.17.3을 유지했습니다. 새 Helm을 /usr/local/bin이나 사용자 공용 bin에 덮어쓰거나 PATH 우선순위를 바꾸지 않습니다. 서버에서는 저장소의 .local/tools/helm-4.3.0/helm을 명시적으로 사용합니다. clone에는 이 바이너리·차트 원본이 포함되지 않습니다.

새 환경에서는 [잠금 목록](../../infra/platform/versions.lock.json)의 linux/amd64 Helm URL과 SHA256으로 archive를 검증하고, 그 안의 linux-amd64/helm만 위 전용 경로에 준비합니다. 기존 전용 파일이 있다면 먼저 출처·버전·checksum을 확인합니다. 설치에 사용할 차트 archive도 잠금 목록의 SHA256과 비교해 .local/charts에 보관합니다. 다운로드·검증 실패 시 실행하지 않습니다.

    HELM="$PWD/.local/tools/helm-4.3.0/helm"
    "$HELM" version --short
    sudo env KUBECONFIG=/etc/rancher/k3s/k3s.yaml "$HELM" list -A
    sudo k3s kubectl get namespaces

전용 archive 이름은 jenkins-5.9.68.tgz와 argo-cd-10.10.2.tgz입니다. Secret을 포함한 values·render·Helm release 출력 전체를 공개 로그에 붙이지 않습니다.

## 관리 도구 신규 설치

다음 명령은 확인한 신규 namespace·release에만 사용합니다. 기존 Jenkins 데이터나 Argo 설정이 있으면 자동 적용하지 말고 변경·백업 범위를 먼저 검토합니다.

    sudo env KUBECONFIG=/etc/rancher/k3s/k3s.yaml "$HELM" install jenkins .local/charts/jenkins-5.9.68.tgz --namespace jenkins --create-namespace --values infra/platform/jenkins-values.yaml --wait --timeout 15m
    sudo env KUBECONFIG=/etc/rancher/k3s/k3s.yaml "$HELM" install argocd .local/charts/argo-cd-10.10.2.tgz --namespace argocd --create-namespace --values infra/platform/argocd-values.yaml --wait --timeout 15m
    sudo k3s kubectl get pods,pvc,svc -n jenkins
    sudo k3s kubectl get pods,pvc,svc -n argocd

Pod Ready와 실제 기능 검증은 별도입니다. Jenkins는 플러그인이 정상 로드되고 동적 agent에서 stage·JUnit·artifact가 실행되어야 CI 성공으로 기록합니다. 실패 시 제한된 이벤트·로그부터 확인하며 PVC 삭제나 초기화를 먼저 실행하지 않습니다.

controller executor는 0이고 default template을 상속하는 빌드 agent 상한은 1입니다. agent UID/GID/fsGroup은 1000이며 API token을 자동 마운트하지 않습니다. 자세한 연결·검증은 [Jenkins CI](jenkins-ci.md)를 따릅니다.

Argo CD는 [ADR 0003](../adr/0003-gitops-in-existing-repository.md)에 따라 같은 저장소의 [gitops](../../gitops/README.md)와 앱 Helm chart를 읽습니다. namespace·DB Secret은 관리자가 별도로 준비하고 AppProject는 해당 저장소·namespace·필요한 리소스 종류만 허용합니다. Jenkins에서 같은 앱의 helm upgrade를 중복 실행하지 않습니다.

## 관리자 접근과 로그인

Windows에서는 [관리 접속 안내](admin-access.md)의 도우미로 현재 ClusterIP를 조회하고 클라이언트 127.0.0.1에 SSH 터널을 엽니다. 기존 프록시·공유기 포트를 사용하거나 NodePort·Ingress를 추가하지 않습니다.

초기 비밀번호는 사용자의 서버 비공개 터미널에서만 확인합니다. .local/admin은 0700, 초기 비밀번호 파일은 0600으로 제한하고 로그인 후 비밀번호를 변경합니다. 비밀번호·토큰을 채팅·CI 로그·스크린샷에 출력하지 않습니다. Argo 자체 서명 인증서는 확인한 SSH 경로에서 지문·유효기간을 대조하며 전역 TLS 검증을 끄지 않습니다.

## 보존 범위와 남은 검증

K3s bootstrap의 /var/backups/devdooly-platform-lab 아래 감사 자료는 **같은 호스트의 설정·네트워크 상태 기록**입니다. 기존 앱 데이터, MariaDB, Jenkins PVC를 백업하지 않았으며 외부 백업·복원과 호스트 재부팅 복구는 아직 검증하지 않았습니다.

실제 Jenkins·DB PV의 reclaimPolicy는 Delete입니다. DB StatefulSet의 PVC Retain은 StatefulSet 삭제·축소 시 claim을 유지하는 설정이며, PVC·namespace 수동 삭제를 막지 않습니다. claim을 삭제하면 provisioner가 저장 데이터를 제거할 수 있습니다. local-path 10Gi 요청도 디스크 사용량의 강제 상한이나 복제·백업이 아닙니다.

운영 데이터를 맡기기 전에는 K3s SQLite datastore·server token·Secret 암호화 키, DB, Jenkins 설정·credentials·PV를 대상별로 나누어 외부 백업과 복원을 검증해야 합니다. 앱 image digest만 되돌려 DB migration을 복구할 수는 없습니다. 이 호스트의 기존 데이터를 대상으로 uninstall/killall·전체 방화벽 복원·PVC 삭제를 복구 시험에 사용하지 않습니다.

아래 항목은 각 결과가 있을 때만 완료로 기록합니다.

- node·시스템 Pod Ready, 전용 경로·버전·기존 서비스 보존
- Jenkins 실제 stage·JUnit·artifact, 실패 차단과 동시 빌드 상한
- Argo Synced/Healthy와 실행 image digest·source commit 일치
- 웹에서 API를 호출하는 실제 HTTP 경로와 샘플 결과, 앱 재시작 후 데이터 보존
- 이전 digest 복구, 재부팅 복구, 외부 백업·복원

[로컬 렌더링 요약](../../infra/platform/render-validation.json)은 Helm 문법·정책 검사 당시의 근거이며 서버 실행 성공 근거로 바꾸지 않습니다. 현재 서버 결과는 [미니 PC 검증 기록](../evidence/mini-pc/README.md)을 따릅니다.

## 공식 근거

- [K3s 설정](https://docs.k3s.io/installation/configuration), [서버 옵션](https://docs.k3s.io/cli/server), [백업](https://docs.k3s.io/datastore/backup-restore)
- [Jenkins 고정 차트](https://github.com/jenkinsci/helm-charts/tree/jenkins-5.9.68/charts/jenkins), [Java 지원](https://www.jenkins.io/doc/book/platform-information/support-policy-java/)
- [Argo CD 고정 차트](https://github.com/argoproj/argo-helm/tree/argo-cd-10.10.2/charts/argo-cd), [시작 안내](https://argo-cd.readthedocs.io/en/stable/getting_started/)
- [Helm v4.3.0 체크섬](https://github.com/helm/helm/releases/tag/v4.3.0)
