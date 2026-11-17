# SSH로 설치를 에이전트에게 맡기기

SSH 키로 접속할 수 있는 **새 Ubuntu 실습 VM**을 준비한 뒤, 터미널 실행 도구가 있는 에이전트에게 아래 요청을 전달합니다. 에이전트는 [설치 스크립트](../../infra/fresh-lab/install.sh)를 같은 순서로 실행하고 종료 상태와 단계별 검증 결과를 읽습니다. [전체 설치 순서와 완료 조건](fresh-lab.md)을 함께 확인합니다.

## 사용자가 준비할 것

1. 새 VM을 만들고 설치할 내부 IPv4를 고정합니다. Ubuntu 22.04·x86_64·systemd를 대상으로 하며, VM RAM은 10 GiB 이상, `/var/lib`이 있는 파일시스템의 여유 공간은 65 GiB 이상이 필요합니다. 계정에 SSH 공개키를 등록하고 VM 콘솔에서 서버 **호스트 키**의 SHA256 지문을 확인합니다. 키를 파일로 보관하는 경우 개인키는 클라이언트에 둡니다.

   ```sh
   sudo ssh-keygen -lf /etc/ssh/ssh_host_ed25519_key.pub -E sha256
   ```

2. 로컬 SSH 별칭 `platform-lab-fresh`에 서버 주소, 포트, 계정, 개인키 경로를 지정합니다. 해당 주소와 포트의 Ed25519 호스트 키를 별도 known_hosts 파일에 등록합니다. `ssh-keyscan -T 5 -p PORT -t ed25519 HOST`를 임시 파일에 저장하고 `ssh-keygen -lf FILE -E sha256`으로 확인할 수 있습니다. **VM 콘솔에서 얻은 지문과 일치할 때만** 등록합니다. 등록한 키가 바뀌면 콘솔에서 새 지문과 변경 원인을 확인한 뒤 갱신합니다. [OpenSSH 호스트 키 확인](https://man.openbsd.org/ssh-keyscan) · [OpenSSH 클라이언트 설정](https://man.openbsd.org/ssh_config)

   로컬 SSH 설정 예시입니다. 아래 경로와 자리표시자는 본인 환경에 맞게 바꿉니다.

   ```ssh-config
   Host platform-lab-fresh
       HostName HOST
       Port 22
       User LAB_USER
       IdentityFile ~/.ssh/platform-lab-fresh
       UserKnownHostsFile ~/.ssh/known_hosts.platform-lab-fresh
       HostKeyAlgorithms ssh-ed25519
       StrictHostKeyChecking yes
       BatchMode yes
       IdentitiesOnly yes
       ForwardAgent no
       ConnectTimeout 10
   ```

3. 에이전트가 사용할 SSH 클라이언트에서 `ssh -o BatchMode=yes -o StrictHostKeyChecking=yes platform-lab-fresh true`가 성공하는지 확인합니다. 개인키에 암호가 있다면 필요할 때 본인 터미널에서 `ssh-add`로 키를 엽니다. 서버의 sudo 인증이 필요한 경우 설치 명령이 실행될 터미널에서 사용자가 직접 인증합니다. 별도 SSH 실행마다 같은 sudo 인증이 적용된다고 가정하지 않습니다.

별칭과 known_hosts 파일 준비도 에이전트에게 맡길 수 있습니다. 이 경우 별칭 대신 SSH 주소·포트·계정·클라이언트의 키 경로와 VM 콘솔에서 읽은 SHA256 지문을 알려줍니다. 에이전트는 같은 지문으로 확인한 키를 등록한 뒤 접속합니다.

## 복사할 요청

승인한 저장소 커밋의 전체 SHA와 VM에 이미 할당된 내부 IPv4를 채운 뒤 보냅니다. 커밋에는 `infra/fresh-lab/install.sh`가 포함돼 있어야 합니다. 위 SSH 별칭을 쓰면 프롬프트에 개인키나 비밀번호를 넣을 필요가 없습니다.

```text
DevDooly Platform Lab 초기구성 진행해줘.

대상은 기존 서비스가 없는 새 Ubuntu 실습 VM이야.
SSH 별칭은 platform-lab-fresh, VM 내부 IPv4는 <PRIVATE_IPV4>야.
저장소는 https://github.com/DevDooly/devdooly-platform-lab.git 이고
검토한 소스 커밋은 <APPROVED_FULL_COMMIT_SHA>야.
사전 점검을 통과하면 이 VM과 커밋에 한해 실제 설치까지 진행해줘.

1. SSH 클라이언트에서 BatchMode=yes와 StrictHostKeyChecking=yes를 유지하고,
   VM의 OS, 메모리·디스크 여유, 지정 IPv4의 할당 여부를 읽기 전용으로 확인해줘.
2. 새 디렉터리에 위 저장소를 받고 해당 커밋을 checkout해줘.
   git rev-parse HEAD와 저장소 URL을 대조하고 설치 스크립트를 읽어줘.
3. 저장소 루트에서 sudo bash infra/fresh-lab/install.sh --check --node-ip <PRIVATE_IPV4>를 실행해줘.
   실패하면 첫 실패와 필요한 조치만 알려줘. 대상이나 설정을 임의로 바꾸지 마.
4. 점검이 성공하면 같은 checkout·주소에서
   sudo bash infra/fresh-lab/install.sh --apply --node-ip <PRIVATE_IPV4>를 실행해줘.
   sudo가 사용자 입력을 기다리면 내가 인증할 터미널과 명령만 알려줘.
   접속, 점검, 적용, 검증을 이어서 진행하고 설치 프로세스의 종료까지 기다려줘.
5. 스크립트가 실제로 검증한 단계, 실패와 후속 시도, 실행 시각과 소스 SHA를 기록해줘.
   상태가 준비 중이면 완료로 적지 말고 비밀 값이나 원본 서버 로그는 채팅에 넣지 마.
   Grafana에 접속할 로컬 주소와 서비스 상태·로그를 확인하는 방법을 알려줘.
```

SSH 접속은 되지만 sudo가 비밀번호를 요구하면 설치 명령을 실행할 **같은 터미널**에서 사용자가 직접 입력합니다. 에이전트와 터미널을 공유할 수 있는 경우 그 터미널에서 `sudo -v`로 인증합니다. 콘솔만 사용할 수 있는 경우 에이전트가 안내한 sudo 명령을 VM 콘솔에서 한 번 실행하고 종료 상태를 전달합니다. 호스트가 비대화형으로 좁게 권한을 부여한 경우 정해진 설치 명령만 사용합니다. VM을 잘못 고르거나 기존 데이터 경로와 충돌했다면 대상 VM을 다시 확인합니다.

설치 스크립트의 단계 결과와 서버의 root 전용 로그를 먼저 읽습니다. 재시도할 때는 이전 실패 원문을 보관하고, [설치 스크립트](../../infra/fresh-lab/install.sh)가 재개를 허용하는지 확인합니다. 공유 기록에는 실제 명령·종료 상태·관측 시각·확인한 서비스와 검증 한계만 남깁니다.

## MCP가 필요한 경우

터미널 실행이 가능한 로컬 에이전트는 기존 OpenSSH 클라이언트로 진행할 수 있습니다. 도구를 실행할 수 없는 일반 채팅에서는 터미널이 있는 에이전트로 대화를 옮기거나, 사용자가 이미 승인한 로컬 MCP 도구를 연결합니다.

로컬 브리지를 사용할 경우 실습 VM SSH 별칭 하나와 설치 점검·적용·상태 조회를 각각 고정된 도구로 제공하고 호스트 키 검증과 서버 sudo 경계를 그대로 적용합니다. 도구는 단계 상태와 비밀을 제거한 요약을 반환하게 구성합니다. 연결된 도구의 접근 범위와 적용 권한은 해당 클라이언트에서 확인합니다. [MCP 보안 모범 사례](https://modelcontextprotocol.io/docs/2025-11-25/tutorials/security/security_best_practices)

## Grafana 열기

Grafana는 서버의 루프백에 포워딩하고 클라이언트 루프백에서 SSH로 연결합니다. 에이전트에 이 두 프로세스를 시작해 달라고 요청할 수 있습니다. 서버의 SSH 세션에서 다음을 실행합니다.

```sh
sudo k3s kubectl -n platform-lab-monitoring port-forward \
  --address 127.0.0.1 svc/grafana 3000:3000
```

클라이언트의 별도 터미널에서 실행합니다.

```sh
ssh -N -o ExitOnForwardFailure=yes \
  -L 127.0.0.1:13000:127.0.0.1:3000 platform-lab-fresh
```

브라우저에서 `http://127.0.0.1:13000/d/platform-lab-services/platform-lab-services`를 열고 `admin`으로 로그인합니다. 초기 비밀번호는 사용자가 자신의 서버 터미널에서 `grafana-admin` Secret의 `admin-password`를 확인해 직접 입력합니다. 아래 출력과 로그 검색 결과는 비공개로 취급합니다. [Grafana 구성](../../infra/lab-monitoring/README.md) · [Kubernetes 포트 포워딩](https://kubernetes.io/docs/reference/kubectl/generated/kubectl_port-forward/)

```sh
sudo k3s kubectl -n platform-lab-monitoring get secret grafana-admin \
  -o jsonpath='{.data.admin-password}' | base64 -d
printf '\n'
```
