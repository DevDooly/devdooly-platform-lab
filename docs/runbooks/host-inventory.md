# Ubuntu 호스트를 변경하기 전 점검

기존 서비스와 데이터 위치를 확인하고 새 Lab의 설치 범위와 백업 방법을 정합니다. 2026-10-11 SSH 호스트 지문·전용키 인증을 확인한 뒤 실제 미니 PC를 읽기 전용 점검했습니다. 아래 명령은 이후 변경 전에도 사용할 조회 예시입니다. 현재 설치 상태와 한계는 [미니 PC 검증 기록](../evidence/mini-pc/README.md)을 따릅니다.

## 기록 위치

접속 호스트·사용자·포트와 상세 출력은 Git 제외 경로 `.local/`에 기록합니다. 로컬 메모가 없는 clone에서는 직접 생성합니다. 공개 저장소에는 제품 버전, 사용량의 요약과 결정 이유만 정리합니다. 전체 환경 변수, 설정 파일 내용, 토큰과 private key를 출력하지 않습니다.

## 접속 전

- SSH 사용자·포트와 사용할 공개키 등록 여부를 확인합니다.
- 처음 접속할 때 별도 경로로 서버 호스트 키 지문을 확인합니다.
- 새 접속 방법을 검증하기 전 기존 접속 방법을 없애지 않습니다.
- 현재 백업 여부와 기존 서비스의 담당 경로를 확인합니다.

## 시스템과 자원 조회

```sh
cat /etc/os-release
uname -r
lscpu
free -h
df -hT
lsblk -o NAME,SIZE,TYPE,FSTYPE,MOUNTPOINTS
systemctl list-units --type=service --state=running --no-pager
ss -lnt
```

RAM·디스크 수치는 시각과 함께 기록합니다. 기존 데이터 경로를 확인한 뒤 필요한 디렉터리에 한정해 용량을 조사합니다. 전체 파일 시스템을 무작정 순회하는 점검은 피합니다.

컨테이너 도구가 이미 설치되어 있다면 기존 사용자 권한에서 해당 도구의 목록을 확인합니다. 조회 권한이 없으면 상태를 기록하고 실제 작업 때 필요한 접근을 정합니다.

```sh
if command -v docker >/dev/null 2>&1; then
  docker ps --format 'table {{.Names}}\t{{.Image}}\t{{.Ports}}\t{{.Status}}'
fi
if command -v podman >/dev/null 2>&1; then
  podman ps --format 'table {{.Names}}\t{{.Image}}\t{{.Ports}}\t{{.Status}}'
fi
```

컨테이너 inspect 전체 출력에는 인증정보가 포함될 수 있으므로 이 점검에는 사용하지 않습니다. 기존 Kubernetes가 있다면 context와 권한을 확인한 뒤 필요한 조회만 별도로 진행합니다.

## 이번 점검에서 정한 범위

- Ubuntu 22.04·x86_64에서 기존 Docker·containerd·UFW와 사용 중인 서비스·포트를 보존합니다. 기존 프록시의 80/443을 재사용하거나 중단하지 않습니다.
- K3s 데이터는 /var/lib/devdooly-platform-lab/k3s, local-path PV는 /var/lib/devdooly-platform-lab/storage를 사용합니다. 기존 앱 데이터 경로와 분리합니다.
- Pod/Service CIDR 10.42.0.0/16·10.43.0.0/16과 API·kubelet·Flannel 포트의 충돌을 확인한 뒤 [신규 bootstrap](k3s-bootstrap.md)을 수행했습니다.
- 기존 시스템 Helm은 유지하고 저장소 .local/tools/helm-4.3.0/helm을 별도로 사용합니다.
- 설치 후 기존 실행 컨테이너 23개의 ID와 실행 상태가 유지되고 감사 시각 이후 재시작이 없음을 확인했습니다. UFW 상태와 백업한 설정 파일 내용도 동일했습니다. 기존 앱 각각의 HTTP 응답까지 확인한 결과는 아닙니다.

원본 점검 자료와 설정·네트워크 감사 archive는 비공개로 보관합니다. /var/backups/devdooly-platform-lab의 기록은 같은 호스트에 있는 자료이며 앱 DB·Docker volume·Jenkins PVC의 데이터 백업을 대신하지 않습니다. 별도 장치·외부 저장소의 백업, 복원 시험과 재부팅 복구는 아직 검증하지 않았습니다.

## 사람이 확인할 항목

| 항목 | 확인할 내용 |
| --- | --- |
| 기존 서비스 | 목적, 포트, 데이터 위치, 중단 가능한 시간 |
| 디스크 | 종류, 마운트, 남은 공간, 로그와 데이터의 증가량 |
| 백업 | 대상, 위치, 최근 성공 시각, 복원 방법 |
| 회선과 DDNS | 공인 IP·CGNAT 여부, 공유기 경로, DNS 관리 권한 |
| HTTPS | 기존 80·443 사용, 사용할 인증서와 갱신 방법 |
| 설치 범위 | K3s·PV·백업 경로, 자원 예산과 원상 복구 방법 |

패키지 설치, 방화벽·공유기 설정 변경, 서비스 재시작, 데이터 삭제는 환경 조회에 포함되지 않습니다.

## 점검 완료 조건

기존 서비스와 데이터가 어디에 있는지, 새 Lab이 어떤 자원·경로·포트를 사용할지, 문제가 생기면 무엇을 복원할지 설명할 수 있어야 합니다. 설정 감사 자료, 데이터 백업과 실제 복원 검증은 서로 구분해 기록합니다. 이 결과를 기준으로 [진행 목록](../ROADMAP.md)의 0단계를 갱신합니다.
