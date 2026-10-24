# Windows에서 Jenkins·Argo CD 관리 화면 접속

관리 화면은 [외부 HTTPS 로그인 주소](service-console.md) 또는 아래 SSH 연결로 접속할 수 있습니다. 이 문서는 로컬 SSH 접속 방법을 설명합니다. [접속 도우미](../../infra/scripts/connect-admin.ps1)는 K3s의 현재 Service 주소를 읽고 Windows의 `127.0.0.1`에만 터널을 엽니다. 서버의 기존 프록시·포트·방화벽을 변경하지 않으며, NodePort·Ingress나 공유기의 관리 포트 공개가 필요하지 않습니다.

## 준비

- Windows OpenSSH 클라이언트의 `ssh.exe`와 같은 디렉터리의 `ssh-keygen.exe`가 필요합니다. Windows PowerShell 5.1 이상에서 실행합니다.
- Ubuntu 로그인 계정에 전용 공개키가 등록되어 있고 해당 계정으로 SSH 접속할 수 있어야 합니다. 개인키는 접속 PC에만 보관합니다.
- 서버 콘솔 등 신뢰할 수 있는 별도 경로로 확인한 SSH 호스트 키를 **전용 known_hosts 파일**에 준비합니다. 처음 접속하며 받은 키를 확인 없이 승인하지 않습니다.
- SSH 계정으로 `sudo -n k3s kubectl get service ... -o json` 조회가 가능해야 합니다. 불가능하면 기존 관리 권한을 확인합니다. 도우미를 위해 전체 sudo 무암호 권한을 추가하지 않습니다.
- Jenkins의 `jenkins/jenkins` Service는 TCP 8080, Argo CD의 `argocd/argocd-server` Service는 TCP 443이어야 하며 두 Service 모두 사설 IPv4 `ClusterIP`여야 합니다.

호스트 주소·계정·키 경로와 원본 점검 자료는 Git에서 제외한 `.local/`에 관리합니다. 전용 known_hosts 파일은 해당 서버의 확인된 키만 포함해야 합니다. 같은 키를 사용하는 DNS·IP 별칭과 해시된 호스트 이름은 허용하지만 다른 서버의 키, 와일드카드, 인증기관·폐기 마커는 받지 않습니다. 기본 사용자·시스템 known_hosts 파일은 도우미 입력으로 사용할 수 없습니다.

도우미는 `-F none`으로 기존 SSH 설정을 읽지 않습니다. `HostName`에는 SSH 설정의 별칭이 아닌 실제 DNS 이름이나 IPv4 주소를 지정합니다. 비밀번호 입력 없이 키로 인증하며 새로운 호스트 키를 자동 등록하거나 기존 신뢰 파일을 갱신하지 않습니다.

## 실행과 종료

저장소 루트의 PowerShell에서 실제 값을 채워 실행합니다. 모든 파일 경로는 절대 경로입니다. 공백이 있는 경로는 지원하며, SSH가 별도로 해석하는 `%`·`$`와 따옴표·제어 문자가 있는 경로는 받지 않습니다.

```powershell
.\infra\scripts\connect-admin.ps1 `
  -HostName '<Ubuntu DNS 이름 또는 IPv4>' `
  -UserName '<Ubuntu 로그인 계정>' `
  -IdentityFile '<개인 SSH 키 절대 경로>' `
  -KnownHostsFile '<확인한 전용 known_hosts 절대 경로>'
```

조직이나 PC의 PowerShell 실행 정책이 스크립트를 막으면 적용 중인 정책을 확인합니다. 도우미는 실행 정책이나 전역 SSH 설정을 변경하지 않습니다.

| 매개변수 | 기본값 | 역할 |
| --- | --- | --- |
| `Port` | `22` | Ubuntu SSH 포트 |
| `JenkinsLocalPort` | `18081` | Windows의 Jenkins 접속 포트 |
| `ArgoLocalPort` | `18443` | Windows의 Argo CD 접속 포트 |

서로 다른 1024~65535 범위의 로컬 포트를 지정할 수 있습니다. SSH 포트가 22가 아니면 전용 known_hosts에는 해당 `[호스트]:포트`의 확인된 키가 있어야 합니다.

도우미는 두 Service의 이름·namespace·사설 IPv4·TCP 포트를 검증한 뒤 포그라운드 SSH 프로세스를 실행합니다. 서버에 별도의 `kubectl port-forward` 프로세스를 띄우지 않습니다. 터미널을 연 상태에서 다음 주소로 접속합니다.

- Jenkins: `http://127.0.0.1:18081`
- Argo CD: `https://127.0.0.1:18443`

사용을 마치면 터널 터미널에서 **Ctrl+C**를 누릅니다. 별도 데몬·예약 작업·상시 서비스를 만들지 않습니다. 연결이 끊기면 관리 화면에도 접속할 수 없습니다.

## 최초 로그인과 TLS 지문 확인

Jenkins 사용자 이름은 `.local/admin/jenkins-username` 파일에 있고, Argo CD 초기 사용자 이름은 `admin`입니다. 초기 비밀번호는 사용자가 자신의 Ubuntu 비공개 터미널에서 프로젝트의 `.local/admin/jenkins-initial-password`, `.local/admin/argocd-initial-password` 파일을 직접 확인합니다. 디렉터리 권한은 700, 파일 권한은 600으로 제한합니다. 도우미는 파일을 읽거나 비밀번호·토큰을 출력하지 않습니다. 채팅·CI 로그·스크린샷·Git에 옮기지 말고 로그인 후 초기 비밀번호를 변경합니다.

Argo CD의 자체 서명 TLS 인증서는 그대로 유지합니다. SSH 호스트 키를 확인한 Ubuntu 터미널에서 현재 `argocd-server`의 ClusterIP를 확인한 뒤, 그 주소의 인증서 SHA-256 지문·유효기간을 읽습니다. 아래 `<Argo ClusterIP>`는 직접 확인한 실제 주소로 바꿉니다.

```sh
sudo -n k3s kubectl get service argocd-server --namespace argocd -o json
openssl s_client -connect <Argo-ClusterIP>:443 </dev/null 2>/dev/null |
  openssl x509 -noout -fingerprint -sha256 -subject -issuer -dates
```

Windows 브라우저의 `https://127.0.0.1:18443` 인증서 정보에서 같은 SHA-256 지문인지 비교합니다. 터널 대상이 확인되고 지문과 유효기간이 일치할 때에만 **그 로컬 접속 주소에 한정해** 브라우저의 예외를 사용합니다. 인증서가 바뀌면 다시 대조합니다. 지문이 다르거나 확인할 수 없으면 로그인하지 않고 접속 경로를 점검합니다. 전역 인증서 무시, 영구적인 TLS 검증 해제, Argo CD의 `server.insecure` 설정은 사용하지 않습니다.

## 연결이 안 될 때

- 호스트 키가 없거나 달라지면 자동 승인하지 않습니다. 서버 콘솔 등으로 변경 사유와 새 지문을 대조해 전용 파일을 갱신합니다.
- 인증 또는 `sudo -n` 조회가 실패하면 도우미는 터널을 열기 전에 중단합니다. 사용자·키 등록·권한과 K3s 상태를 확인합니다.
- 로컬 포트가 사용 중이면 터널 실행이 실패합니다. 기존 프로세스를 임의로 종료하지 말고 다른 로컬 포트를 매개변수로 지정합니다.
- `ExitOnForwardFailure=yes`는 로컬 포트 바인딩 실패를 잡지만, 원격 Service의 실제 응답을 보장하지 않습니다. 화면이 열리지 않으면 Pod readiness와 서버에서 ClusterIP로의 연결을 따로 확인합니다.
- Service가 재생성되어 ClusterIP가 바뀌면 터널을 종료하고 도우미를 다시 실행해 현재 주소를 조회합니다. 기존 프록시·Docker·UFW를 우선 재시작하거나 변경하지 않습니다.

2026-10-11에 비공개 실행 파일로 실제 SSH 터널을 열어 Jenkins `/login`의 HTTP 200과 로그인 폼을 확인했습니다. Argo CD는 인증된 SSH 경로에서 `argocd/argocd-secret`의 키 이름을 확인한 뒤 공개 `tls.crt`만 읽어, 터널의 인증서 SHA-256 지문과 유효기간을 대조했습니다. 지문은 일치했고 TLS 1.3으로 연결됐습니다. 전역 TLS 설정이나 브라우저 보안 설정을 변경하지 않았으며, 확인 후 생성한 터널 프로세스와 두 로컬 리스너를 모두 정리했습니다. 상세 측정은 Git에서 제외한 `.local/admin-access-validation.json`에 보관합니다.

PowerShell 5.1 구문·입력·Service 응답 검증 48개도 통과했습니다. 실제 접속 확인 범위는 로그인 전 HTTP 응답과 인증서 대조까지이며, 비밀번호 조회·로그인과 CI·CD 실행 결과는 별도 검증으로 구분합니다.

관련 문서: [플랫폼 설치](platform-install.md), [Jenkins CI](jenkins-ci.md), [앱 배포](app-helm.md).

공식 근거: [OpenSSH ssh](https://man.openbsd.org/ssh), [ssh_config](https://man.openbsd.org/ssh_config), [ssh-keygen](https://man.openbsd.org/ssh-keygen).
