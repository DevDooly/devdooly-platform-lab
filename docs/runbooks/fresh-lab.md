# 새 Ubuntu VM에서 Platform Lab 설치

전용 Ubuntu 22.04 LTS amd64 VM에서 K3s, Argo CD, MariaDB, Spring Boot API, Astro 웹, Kafka, Garage S3, Java worker, Jenkins, Grafana를 순서대로 준비합니다. 서비스는 VM 안에서 실행하며 브라우저 접속에는 로컬 포워딩을 사용합니다. [SSH로 에이전트에 맡기기](fresh-lab-agent.md) · [설치 관측 기록](../evidence/fresh-lab/README.md)

| 목적 | 시작점 |
| --- | --- |
| 로컬에서 코드 개발 | [README의 로컬 실행](../../README.md#로컬-실행)의 Spring Boot·H2와 Astro 개발 서버 |
| Docker로 MariaDB 연결 확인 | [Compose 설치](local-compose.md)의 MariaDB·API·웹 |
| 새 서버에 연결된 스택 준비 | 아래 설치 명령. K3s와 데이터 처리 서비스, CI 도구, 관측 화면까지 설치 |

## 시작 조건

- 새 VM의 콘솔과 관리자 계정을 준비합니다. sudo 승인은 실행하는 계정에 필요합니다. Ubuntu 설치와 SSH 주소·키, 호스트에 실제 할당한 **재부팅 후에도 같은 private IPv4**를 먼저 확인합니다.
- 이 실습에서는 amd64 VM에 vCPU 4개 이상, 메모리 12 GiB, 디스크 100 GB를 기준으로 시작합니다. 이 값은 구성 기준입니다. 사전 검사는 Linux가 보고한 메모리 10 GiB 이상과 신규 설치 시 /var/lib 파일시스템 여유 공간 65 GiB 이상을 확인합니다.
- VM에는 Bash, Python 3, Git, curl, iproute2와 systemd가 필요합니다. 최소 Ubuntu 이미지라면 누락된 기본 도구를 설치한 뒤 점검을 실행합니다.
- 서버에서 공식 릴리스, GitHub, 컨테이너 레지스트리에 HTTPS로 접속해야 합니다. 인터넷 라우팅과 방화벽은 호스트 관리자가 준비합니다. [K3s 호스트 요건](https://docs.k3s.io/installation/requirements)
- 기존 클러스터가 있는 서버는 해당 환경의 변경과 복원을 별도로 관리합니다. 신규 설치 대상에 대해 명령을 실행하고 이전에 같은 스크립트가 시작한 대상은 같은 주소와 checkout에서 재개합니다.

## 서버에서 직접 실행

설치 코드를 포함하는 검토한 커밋 전체 SHA를 준비합니다. VM에 SSH로 접속한 뒤 다음을 실행합니다. 아래 두 자리표시자는 실제 값으로 바꿉니다.

```bash
git clone https://github.com/DevDooly/devdooly-platform-lab.git
cd devdooly-platform-lab
SOURCE_SHA='<검토한 전체 SHA>'
git checkout --detach "$SOURCE_SHA"

NODE_IP='<VM에 할당된 고정 private IPv4>'
sudo bash infra/fresh-lab/install.sh --check --node-ip "$NODE_IP"
sudo bash infra/fresh-lab/install.sh --apply --node-ip "$NODE_IP"
```

`--check`의 종료 코드가 0인 경우에 적용합니다. 고정 다운로드와 이미지, chart 입력은 [기반 버전 잠금](../../infra/platform/versions.lock.json), [앱 chart](../../infra/charts/platform-lab/values.yaml)와 [설치 소스](../../infra/fresh-lab/install.sh)에서 확인할 수 있습니다. Astro 웹은 Nginx 컨테이너가 빌드된 정적 파일을 제공하고 내부 `/api`를 Spring Boot에 전달합니다.

## 설치 단계와 합격 조건

| 순서 | 설치 대상 | 넘어가기 전에 확인할 결과 |
| --- | --- | --- |
| 1 | K3s·Helm | 호스트 조건·고정 다운로드 해시 확인, 노드 Ready, CoreDNS·기본 스토리지 준비 |
| 2 | Argo CD 기반 | 컨트롤러와 Application CRD 준비, 이 서버의 앱 chart를 동기화할 전용 AppProject 준비 |
| 3 | MariaDB | 생성한 Secret 참조, StatefulSet Ready, local-path PVC Bound |
| 4 | Spring Boot API·Astro 웹 | API 시작과 Flyway 스키마 준비, 웹 정적 페이지 및 웹 경유 API 응답 |
| 5 | Kafka | 단일 broker Ready 및 worker가 사용하는 topic 초기화 확인 |
| 6 | Garage S3 | 단일 노드 layout 반영, 전용 bucket과 worker key 권한 준비 |
| 7 | Java worker | Ready 확인, 합성 작업 접수·처리·export 확인 |
| 8 | Jenkins | Jenkins 컨트롤러와 저장소 준비, 로그인 경로 확인. CI 작업 생성과 GitHub 인증은 [Jenkins 설정](jenkins-ci.md)에 따릅니다 |
| 9 | Grafana·Prometheus·kube-state-metrics·Loki·Alloy | Grafana API로 대시보드, 네 네임스페이스의 workload 상태 지표, Loki에 수집된 컨테이너 로그 검증 |
| 10 | 최종 확인 | 클러스터·앱·Kafka·Garage·worker·Jenkins·Grafana 상태 재확인과 verification.json 기록 |

설치기는 앱 chart의 데이터베이스 리소스를 먼저 적용해 준비를 확인합니다. 이어 Argo CD가 같은 리소스를 관리합니다. 설치기가 Application 설정을 바꾸면 Argo CD가 앱을 동기화합니다. Kafka와 Garage 초기화가 끝나면 worker를 활성화합니다. Jenkins는 CI를 담당합니다. 외부 GitHub 게시·토큰 설정·운영 GitOps 구성은 [이미지 게시 절차](image-publication.md)에 설명돼 있습니다. Spark·Iceberg·Trino는 별도 [데이터 플랫폼 실험](../ROADMAP.md#6-데이터-플랫폼-확장), Kafbat Kafka UI는 별도 [관리 화면 절차](service-console-kafka.md)로 이어집니다.

## Grafana에서 상태와 로그 확인

서버에서 Grafana는 ClusterIP로 제공됩니다. 로컬 컴퓨터에서 SSH 포워딩과 Grafana 포워딩을 한 연결로 엽니다. 포트가 이미 사용 중이면 왼쪽의 로컬 포트만 바꿉니다.

```bash
ssh -t -o BatchMode=yes -o StrictHostKeyChecking=yes -L 127.0.0.1:3000:127.0.0.1:3000 LAB_SSH_TARGET \
  'sudo k3s kubectl -n platform-lab-monitoring port-forward --address 127.0.0.1 svc/grafana 3000:3000'
```

로컬 브라우저에서 `http://127.0.0.1:3000`을 열고 [모니터링 사용법](../../infra/lab-monitoring/README.md)의 관리자 자격증명 조회 절차를 따릅니다. 대시보드에서 ready 사본과 기대 사본을 비교하고 namespace·Pod·container로 로그를 고릅니다. 이 상태는 배치·준비 여부를 나타냅니다. 실제 HTTP 응답, Kafka 전달 또는 S3 저장 성공은 별도의 앱 검증 결과와 대조합니다. 로그가 없는 시간 구간과 수집기가 응답하지 않는 상태도 구분합니다.

## 실패 지점에서 이어서 실행

1. 출력의 마지막 성공 단계와 실패 단계, 시작·종료 시각을 기록합니다. 단계 상태는 `/var/lib/devdooly-platform-lab/fresh-install/stages.jsonl`에 보관합니다.
2. 실패한 단계의 workload를 확인합니다. 예를 들어 `sudo k3s kubectl -n platform-lab get pods,pvc`와 `sudo k3s kubectl -n argocd get applications`로 대조합니다. 원본 로그·Secret·kubeconfig는 서버 내부에서 관리합니다.
3. 주소나 레지스트리 연결 등 원인을 고친 뒤 같은 대상·커밋으로 `--check`와 `--apply`를 다시 실행합니다. 성공 근거와 미완료 사유를 [설치 관측 기록](../evidence/fresh-lab/README.md) 양식에 남깁니다.
