# 신규 Ubuntu 호스트에 K3s 설치하기

[bootstrap-k3s.sh](../../infra/scripts/bootstrap-k3s.sh)는 **Ubuntu 22.04·x86_64의 신규 설치 전용**입니다. 기존 Docker·containerd와 UFW가 실행되는 호스트를 대상으로 검토했습니다. 기존 K3s·Kubernetes 설정·Lab 데이터 경로가 있으면 덮어쓰지 않고 중단합니다. 이미 설치한 호스트의 상태 점검·업그레이드 도구가 아닙니다.

2026-10-11 실제 미니 PC에서 사전 점검과 설치를 수행하고 Node Ready, CoreDNS·local-path·metrics-server Ready를 확인했습니다. 별도 Pod의 API TLS·내부 DNS·외부 DNS·HTTPS 검사도 통과했으며 UFW 규칙을 추가하지 않았습니다. Jenkins Pipeline 실행과 Argo CD Application Sync는 이 결과에 포함하지 않습니다. 상세 근거는 [미니 PC 검증 기록](../evidence/mini-pc/README.md)에 연결합니다.

## 적용 범위

- K3s v1.36.5+k3s1의 공식 amd64 바이너리·checksum 목록·고정 tag의 installer를 SHA256으로 확인합니다. [잠금 목록](../../infra/platform/versions.lock.json)에 같은 값을 기록했습니다.
- 새 데이터 경로는 /var/lib/devdooly-platform-lab/k3s, local-path 저장소는 /var/lib/devdooly-platform-lab/storage입니다.
- /etc/rancher/k3s/config.yaml과 생성되는 kubeconfig는 root 소유·0600으로 관리합니다. Secret 저장 암호화를 켭니다.
- Traefik·ServiceLB를 끄고 기존 80/443 서비스와 별도로 설치합니다. API는 입력받은 내부 IPv4에 bind하며 공인 주소나 DNS를 추가하지 않습니다.
- 기본 Pod/Service CIDR 10.42.0.0/16·10.43.0.0/16이 기존 route·Docker subnet과 겹치면 중단합니다.
- apt 업그레이드, Docker/containerd 재시작·설정 변경, UFW 규칙·default policy 변경, sudoers 변경, 기존 Helm 교체는 수행하지 않습니다.

K3s 자체는 CNI·kube-proxy의 네트워크 규칙을 생성합니다. installer의 전체 iptables 재작성 경로는 SKIP_ENABLE·SKIP_START로 건너뛰고, 새 unit 생성 후 systemctl로 K3s만 시작합니다. 기존 규칙 전체를 복원하거나 삭제하는 자동 정리 명령은 실행하지 않습니다.

## 실행 전 확인과 사전 점검

먼저 [호스트 점검](host-inventory.md)으로 기존 서비스·자원·포트·데이터와 복구 범위를 확인합니다. 스크립트를 읽고 [버전 잠금](../../infra/platform/versions.lock.json)과 비교한 다음, 서버에 실제로 할당된 내부 IPv4를 입력합니다. 아래 PRIVATE_IPV4는 실제 값이 아닌 입력 자리입니다.

    NODE_IP='PRIVATE_IPV4'
    sudo bash infra/scripts/bootstrap-k3s.sh --check --node-ip "$NODE_IP"

--check도 UFW·Docker 상태와 root 전용 경로를 읽기 위해 sudo가 필요합니다. 다운로드·백업·파일 생성은 하지 않습니다. 비대화형 sudo가 허용되지 않은 환경에서는 사용자가 서버 터미널에서 직접 sudo 인증합니다. 비밀번호를 전달하거나 NOPASSWD 설정을 추가할 필요는 없습니다.

사전 점검은 다음 조건을 요구합니다.

- Ubuntu 22.04, x86_64, systemd와 필요한 명령이 있어야 합니다.
- 기존 Docker·containerd가 active이고 UFW가 active·incoming deny여야 합니다.
- IP forwarding이 이미 켜져 있어야 합니다. 스크립트가 sysctl 설정을 변경하지 않습니다.
- /var/lib에서 50GiB 이상, 현재 사용 가능한 RAM 8GiB 이상이 있어야 합니다. 이 기준은 이 Lab의 여유 공간 기준이며 K3s 공식 최소 사양과는 다릅니다.
- 기존 Kubernetes 경로·unit·실행 파일이 없어야 하고 새 목적지 상위 경로는 symlink이거나 다른 사용자가 쓸 수 있는 경로이면 안 됩니다.
- 6443·6444·10248·10249·10250·10256·10257·10258·10259·10010/TCP와 8472/UDP가 비어 있어야 합니다.

실제 적용:

    sudo bash infra/scripts/bootstrap-k3s.sh --apply --node-ip "$NODE_IP"

--apply는 같은 사전 점검을 다시 수행합니다. 사전 조건을 우회하거나 기존 설치를 갱신하는 옵션은 없습니다. 설치 후 다시 실행하면 기존 경로 때문에 중단하는 것이 정상입니다.

## 백업·비밀정보·실패 처리

호스트 변경 전에 /var/backups/devdooly-platform-lab/YYYYMMDDTHHMMSSZ-PID에 root 전용 0700 디렉터리를 만듭니다. umask 077로 다음 자료를 보관합니다.

- 기존 /etc/rancher가 있으면 원본 archive, 없으면 부재 기록
- /etc/systemd/system과 UFW 설정 원본
- route·listener·iptables/ip6tables·가능한 경우 nft 상태
- 기존 Docker 실행 컨테이너 ID·상태
- 다운로드 원본과 installer 로그, 생성한 설정·unit·바이너리의 SHA256

이는 **설정·네트워크 상태의 감사 자료**입니다. 기존 앱 DB·Docker volume의 데이터 백업을 대신하지 않습니다. 전체 Docker inspect, 컨테이너 환경 변수, kubeconfig와 token 내용을 stdout으로 출력하지 않습니다. 감사 원본·접속 주소·관리 자격증명은 공개 Git에 넣지 않습니다.

시작 후 기존 Docker·containerd의 active 상태, 기존 실행 컨테이너의 유지, UFW 상태 출력의 동일 여부를 확인합니다. 실패하면 새 K3s service만 중단하고 생성 파일과 감사 자료를 보존합니다. 기존 컨테이너를 삭제하거나 K3s uninstall/killall·전체 firewall restore를 자동 실행하지 않습니다. 이 검사만으로 기존 앱의 HTTP 동작까지 보장하지 않으므로 적용 후 실제 서비스도 확인합니다.

## 설치 후 검증

상태와 packaged component rollout을 확인합니다. 출력에 포함될 수 있는 내부 주소는 공개 증거에서 제거합니다.

    sudo k3s kubectl get nodes
    sudo k3s kubectl get pods -n kube-system
    sudo k3s kubectl -n kube-system rollout status deployment/coredns --timeout=180s
    sudo k3s kubectl -n kube-system rollout status deployment/local-path-provisioner --timeout=180s
    sudo k3s kubectl -n kube-system rollout status deployment/metrics-server --timeout=180s

[network-smoke.yaml](../../infra/scripts/network-smoke.yaml)은 공개 CA만 마운트하는 일회성 Pod입니다. nonroot·읽기 전용 루트·API token 미마운트이며 [이미지 잠금](../../infra/image-lock.json)의 Node 24 이미지 digest를 사용합니다.

전용 namespace를 새로 만들고 Pod를 생성합니다. 같은 이름이 이미 있으면 먼저 용도를 확인합니다.

    sudo k3s kubectl create namespace platform-lab-netcheck
    sudo k3s kubectl create -f infra/scripts/network-smoke.yaml
    sudo k3s kubectl -n platform-lab-netcheck wait --for=jsonpath='{.status.phase}'=Succeeded pod/network-smoke --timeout=180s
    sudo k3s kubectl -n platform-lab-netcheck logs network-smoke

| 검사 | 의미 | 실제 확인 |
| --- | --- | --- |
| API_SERVICE_TLS_NO_DNS | DNS 없이 Kubernetes Service IP로 CA 검증 HTTPS | HTTP 401, TLS 검증 성공 |
| CLUSTER_DNS | kubernetes.default.svc.cluster.local 조회 | 응답 1개 |
| EXTERNAL_DNS | github.com 조회 | 응답 1개 |
| EXTERNAL_HTTPS | github.com HTTPS 연결 | HTTP 200 |

API의 401은 token 없는 요청이 API까지 도달했다는 전송 검증입니다. 인증·권한 성공을 뜻하지 않습니다. Pod의 PASSED도 HTTP 응답과 TLS 전송 상태를 나타내므로 응답 코드를 함께 확인합니다. 이번 호스트에서는 추가 UFW 허용이 필요하지 않았습니다. 다른 환경에서 실패하면 API 접근·DNS·외부 egress를 나눠 원인을 확인하고, 기존 정책을 유지하면서 필요한 범위만 별도로 검토합니다.

## 관리 접속과 다음 단계

서버 kubeconfig는 private-IP bind 주소를 사용하고 root0600 원본을 유지합니다. 원격 관리는 SSH 터널의 클라이언트 loopback 포트에서 서버의 내부 IPv4:6443으로 전달합니다. 클라이언트 전용 0600 kubeconfig 복사본의 server 항목만 터널 주소로 설정합니다. 127.0.0.1 TLS SAN은 이 용도이며 API를 loopback에만 bind하지는 않습니다. Pod도 API에 접근할 수 있어야 하기 때문입니다.

기존 시스템 Helm은 유지하고 별도 버전이 필요하면 저장소 .local/tools 아래의 고정 바이너리를 사용합니다. 이후 [플랫폼 설치](platform-install.md), [Jenkins CI](jenkins-ci.md), [앱 Helm 배포](app-helm.md)의 실제 실행을 확인합니다. 도구 Pod가 Ready인 상태와 Pipeline 성공·Application Synced는 각각 별도 완료 조건입니다.

## 공식 근거

- [K3s 서버 옵션](https://docs.k3s.io/cli/server): bind·advertise 주소, data-dir, local-path 경로, 암호화와 component disable
- [K3s 설치 요구 사항](https://docs.k3s.io/installation/requirements): 네트워크·UFW·포트 기준
- [고정 installer 원본](https://raw.githubusercontent.com/k3s-io/k3s/v1.36.5%2Bk3s1/install.sh)과 [릴리스 checksum](https://github.com/k3s-io/k3s/releases/download/v1.36.5%2Bk3s1/sha256sum-amd64.txt)

checksum은 이 문서 작성 시 공식 HTTPS 경로에서 확보한 원본을 고정하는 용도입니다. 별도의 릴리스 서명 검증을 수행했다고 주장하지 않습니다.