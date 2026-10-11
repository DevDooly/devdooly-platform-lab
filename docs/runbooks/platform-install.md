# K3s·Jenkins·Argo CD 설치 절차

현재는 설치 설정 준비와 로컬 Helm 렌더링 단계다. SSH 접속, Ubuntu 설치, 실제 Jenkins 빌드와 Argo CD 배포는 검증하지 않았다.

## 설치 전 조건

1. [호스트 점검](host-inventory.md)으로 Ubuntu 버전, 기존 서비스·runtime·포트·디스크·백업을 확인한다. 기존 K3s가 있으면 아래 신규 설치를 실행하지 않는다.
2. 80/443·6443과 Pod CIDR 10.42.0.0/16, Service CIDR 10.43.0.0/16의 충돌을 조사한다. VPN·Docker·기존 망과 겹치면 설치 전에 별도 CIDR을 결정한다.
3. /var/lib/rancher/k3s와 local-path PV가 놓일 파일시스템의 여유 공간, DB·Jenkins·기존 데이터의 외부 백업 위치를 확정한다.
4. SSH 지문·공개키를 확인하고 접속 정보·원본 점검·키는 .local에만 보관한다. 관리 API와 관리 UI를 인터넷에 포워딩하지 않는다. 공인 IPv6 접근도 확인한다.
5. sudo -n true가 실패하면 사용자가 서버에서 아래 설치 명령을 직접 sudo로 실행한다. 비밀번호를 전달하거나 전체 NOPASSWD 권한을 추가하지 않는다.

SSH만 연결한 상태를 구축 완료로 기록하지 않는다. 설치 권한이 확인되기 전에는 사용자 권한의 소스·문서·로컬 검증을 진행한다.

## 버전과 자원

[고정 목록](../../infra/platform/versions.lock.json)은 2026-10-11 공식 자료와 다운로드를 기준으로 한다. K3s stable v1.36.5+k3s1, Jenkins chart 5.9.68/core 2.580.1, Argo CD chart 10.10.2/app v3.5.4, Helm v4.3.0이다.

| 구성 | 초기 RAM 예산 | 저장공간 |
| --- | --- | --- |
| OS·K3s | 4GiB 예상, 실측 필요 | 기존 파일시스템 확인 |
| Jenkins controller·sidecar | 요청 832MiB, 제한 합계 1664MiB | local-path PVC 10GiB |
| 빌드 agent | 동시 Pod 1개, 요청 1024MiB·제한 3968MiB | emptyDir·cache 정책 확인 |
| Argo CD 상시 4개 Pod | 요청 합계 544MiB, 제한 합계 1408MiB | PVC 없음 |
| API·화면·MariaDB | 초기 계획 약 3.5GiB, 실측 필요 | DB 별도 PVC·외부 백업 |

32GiB 전체를 배정하지 않는다. 기존 서비스와 파일 cache에 여유를 남기고 빌드와 Spark·Trino 실행을 겹치지 않는다. 요청량은 예약값, 제한량은 상한이며 실측이 아니다. Dex·Notifications·Redis HA는 끄고 ApplicationSet replica는 0으로 시작한다. 단일 PC는 고가용성 구성이 아니다.

## 신규 K3s

호스트 점검·백업·권한 확인을 마친 신규 설치에만 사용한다. 자동 root 실행 스크립트는 제공하지 않는다. 저장소 루트에서 .local 디렉터리를 준비한 뒤 installer를 확인한다.

    mkdir -p .local
    curl -fsSI https://update.k3s.io/v1-release/channels/stable
    curl -fsSL https://get.k3s.io -o .local/k3s-install.sh
    sha256sum .local/k3s-install.sh
    less .local/k3s-install.sh

stable redirect와 고정 버전을 비교한다. installer의 SHA256은 실행 원본 식별 기록이며 사전에 신뢰한 서명 검증을 의미하지 않는다. installer는 K3s 바이너리를 공식 SHA256과 비교한다.

기존 /etc/rancher/k3s/config.yaml이 있으면 멈추고 기존 설치를 조사한다. 아래는 기존 설정이 없는 신규 설치 전용이다.

    sudo install -d -m 0755 /etc/rancher/k3s
    sudo install -m 0600 infra/platform/k3s-config.example.yaml /etc/rancher/k3s/config.yaml
    sudo env INSTALL_K3S_VERSION=v1.36.5+k3s1 sh .local/k3s-install.sh
    sudo k3s kubectl get nodes
    sudo k3s kubectl get pods -A
    sudo k3s kubectl get storageclass

예제는 Traefik·ServiceLB를 꺼서 기존 호스트의 80/443을 보존한다. 공개 HTTPS·ingress는 별도 단계에서 구성한다. kubeconfig는 0600이며 내용이나 server token을 출력하지 않는다.

사용자 관리용 kubeconfig가 필요하면 기존 ~/.kube/config와 다른 파일을 사용한다. 대상 파일이 이미 있으면 먼저 조사한다.

    mkdir -p "$HOME/.kube"
    chmod 700 "$HOME/.kube"
    sudo install -o "$(id -u)" -g "$(id -g)" -m 0600 /etc/rancher/k3s/k3s.yaml "$HOME/.kube/devdooly-platform-lab.config"
    export KUBECONFIG="$HOME/.kube/devdooly-platform-lab.config"
    kubectl get nodes

이 kubeconfig는 cluster-admin 권한이므로 관리 계정에만 두며 Jenkins agent에 전달하지 않는다. 기본 SQLite datastore·server token·Secret 암호화 설정/키·PV는 서로 다른 백업 대상이다. 기존 경로 삭제나 uninstall을 복구 절차로 사용하지 않는다.

## 서버 Helm 준비

Ubuntu x86_64용 공식 Helm을 사용자 경로에 둔다. 아키텍처가 다르면 해당 공식 바이너리·체크섬을 새로 확인한다. 기존 ~/.local/bin/helm이 있다면 버전을 확인하고 별도 이름을 사용한다.

    mkdir -p .local/tools/helm-linux "$HOME/.local/bin"
    curl -fsSL https://get.helm.sh/helm-v4.3.0-linux-amd64.tar.gz -o .local/tools/helm-linux/helm.tar.gz
    printf '%s  %s\n' 86584a54def73570558f66f5111cc53dfed56689637ae32c1201205d494f54fb .local/tools/helm-linux/helm.tar.gz | sha256sum -c -
    tar -xzf .local/tools/helm-linux/helm.tar.gz -C .local/tools/helm-linux
    install -m 0755 .local/tools/helm-linux/linux-amd64/helm "$HOME/.local/bin/helm"
    export PATH="$HOME/.local/bin:$PATH"
    helm version --short

검증에 실패한 파일은 실행하지 않는다. 클라이언트 Windows의 실제 검증 바이너리와 SHA256도 고정 목록에 기록한다.

## 차트 설치

기존 release·namespace가 있는지 먼저 확인한다. 기존 Jenkins 데이터나 Argo 설정에 아래 values를 자동 적용하지 않는다.

    helm list -A
    kubectl get namespaces
    helm repo add jenkins https://charts.jenkins.io
    helm repo add argo https://argoproj.github.io/argo-helm
    helm repo update
    helm show chart jenkins/jenkins --version 5.9.68
    helm show chart argo/argo-cd --version 10.10.2

차트 원본은 고정 목록의 SHA256과 비교해 보관한다. Secret을 포함한 values·render 원본을 로그에 붙이지 않는다.

    helm upgrade --install jenkins jenkins/jenkins --version 5.9.68 --namespace jenkins --create-namespace --values infra/platform/jenkins-values.yaml --wait --timeout 15m
    helm upgrade --install argocd argo/argo-cd --version 10.10.2 --namespace argocd --create-namespace --values infra/platform/argocd-values.yaml --wait --timeout 15m
    kubectl get pods,pvc,svc -n jenkins
    kubectl get pods,pvc,svc -n argocd

로컬 렌더링과 실제 설치 성공은 다르다. 이미지 다운로드·PVC 바인딩·플러그인 설치·Pod readiness가 확인되어야 설치 완료로 기록한다. 실패 시 제한된 이벤트·로그부터 확인하며 PVC 삭제나 초기화를 먼저 실행하지 않는다.

Jenkins controller는 빌드를 실행하지 않는다. default template을 상속한 Pipeline은 [Jenkins CI 절차](jenkins-ci.md)에서 연결한다. agent UID/GID/fsGroup은 1000이며 API token을 자동 마운트하지 않는다. 같은 앱에 Jenkins helm upgrade와 Argo 배포를 중복 적용하지 않는다.

Argo 설치만으로 GitOps가 구성되지는 않는다. GitOps 저장소·Application 범위·image digest·DB Secret·PVC와 읽기 권한을 별도 구성하고 실제 동기화를 검증한다.

## 관리자 접근

서버의 별도 터미널 두 개에서 localhost로만 port-forward한다.

    kubectl -n jenkins port-forward --address 127.0.0.1 svc/jenkins 8081:8080
    kubectl -n argocd port-forward --address 127.0.0.1 svc/argocd-server 8443:443

클라이언트 SSH 설정에 실제 호스트를 등록한 뒤 터널로 접속한다. NodePort·Ingress와 공유기 관리 포트 포워딩은 만들지 않는다.

    ssh -N -L 8081:127.0.0.1:8081 -L 8443:127.0.0.1:8443 platform-lab

Jenkins는 http://localhost:8081, Argo는 https://localhost:8443 이다. 초기 자체 서명 인증서는 SSH로 확인한 로컬 터널에서 지문을 확인한다. 영구적으로 TLS 검증을 해제하지 않는다.

초기 비밀번호 명령의 stdout을 채팅·CI 로그·스크린샷에 출력하지 않는다. 사용자가 서버 개인 터미널에서 0600 파일로만 받아 확인·변경한다. shell trace를 켜지 않는다.

    mkdir -p .local/admin
    chmod 700 .local/admin
    umask 077
    kubectl -n jenkins get secret jenkins -o jsonpath='{.data.jenkins-admin-password}' | base64 -d > .local/admin/jenkins-initial-password
    kubectl -n argocd get secret argocd-initial-admin-secret -o jsonpath='{.data.password}' | base64 -d > .local/admin/argocd-initial-password

비밀번호 변경·개인 비밀번호 관리 도구 보관 후 초기 파일의 보존 여부를 정리한다. 익명 조회·회원가입·UI exec는 열지 않는다.

## 완료 근거

- node Ready와 시스템 Pod, 버전·경로·서비스 충돌 없음.
- Jenkins executor 0, default template·동시 빌드 1개·agent token 미마운트 확인.
- 관리 인증과 controller 재시작 후 설정·작업 보존.
- Argo TLS·ClusterIP와 실제 Application Synced/Healthy·image digest 일치.
- 정상 빌드·테스트 실패 차단·GitOps revert 복구.
- 재부팅 복구, DB·Jenkins·K3s·Secret의 외부 백업·복원 범위.

서버의 위 조건은 현재 검증하지 않았다. [검증 요약](../../infra/platform/render-validation.json)은 로컬 Helm 렌더링만 기록한다.

## 공식 근거

- [K3s 채널](https://raw.githubusercontent.com/k3s-io/k3s/main/channel.yaml), [설정](https://docs.k3s.io/installation/configuration), [네트워크](https://docs.k3s.io/networking/networking-services), [백업](https://docs.k3s.io/datastore/backup-restore)
- [Jenkins 고정 차트](https://github.com/jenkinsci/helm-charts/tree/jenkins-5.9.68/charts/jenkins), [Java 지원](https://www.jenkins.io/doc/book/platform-information/support-policy-java/)
- [Argo CD 고정 차트](https://github.com/argoproj/argo-helm/tree/argo-cd-10.10.2/charts/argo-cd), [시작 안내](https://argo-cd.readthedocs.io/en/stable/getting_started/)
- [Helm v4.3.0 체크섬](https://github.com/helm/helm/releases/tag/v4.3.0)