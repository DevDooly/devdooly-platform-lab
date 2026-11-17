# Platform Lab 서비스 대시보드

새 실습용 Kubernetes 클러스터에서 Grafana가 서비스 준비 상태와 컨테이너 로그를 보여줍니다. Prometheus는 kube-state-metrics의 Deployment·StatefulSet 지표를 수집합니다. Grafana Alloy는 Kubernetes Pod 로그 API에서 컨테이너 출력을 읽어 Loki로 보냅니다.

## 설치와 확인

설치 대상 클러스터의 관리자 `kubectl` 컨텍스트를 선택하고 Lab 앱, Jenkins, Argo CD를 먼저 설치합니다. 대상 네임스페이스는 `platform-lab`, `jenkins`, `argocd`입니다. 실행에는 `kubectl`, `curl`, `python3`이 필요합니다. 실행 파일 경로를 지정하려면 `KUBECTL`, 관리자 설정 파일을 지정하려면 `KUBECONFIG`를 사용합니다.

```sh
kubectl config current-context
bash infra/lab-monitoring/install.sh --apply
bash infra/lab-monitoring/install.sh --verify
```

`--apply`는 `platform-lab-monitoring`에 Grafana·Prometheus·kube-state-metrics·Loki·Alloy를 구성하고 네 곳에 읽기 전용 Role·RoleBinding을 연결합니다. 처음 실행할 때만 임의 관리자 암호를 Secret에 저장합니다. `--verify`는 배포 상태를 기다린 뒤 임시 루프백 포워딩으로 Grafana의 대시보드, 네 네임스페이스의 준비 상태 시계열, Loki에서 조회한 Grafana 컨테이너 로그를 확인합니다. 암호나 로그 원문 대신 검증한 항목을 출력합니다.

## 브라우저에서 열기

서버 터미널에서 포워딩을 유지합니다.

```sh
kubectl -n platform-lab-monitoring port-forward --address 127.0.0.1 svc/grafana 3000:3000
```

서버에 SSH로 접속했다면 브라우저를 쓰는 컴퓨터에서 별도 터미널로 터널을 엽니다. `LAB_SSH_TARGET`은 본인의 SSH 호스트 별칭으로 지정합니다.

```sh
ssh -N -L 127.0.0.1:3000:127.0.0.1:3000 "$LAB_SSH_TARGET"
```

브라우저에서 `http://127.0.0.1:3000/d/platform-lab-services/platform-lab-services`을 열고 사용자 `admin`으로 로그인합니다. 암호는 관리자가 화면 공유와 기록을 끈 터미널에서 나중에 필요한 경우에만 조회합니다. 암호를 채팅이나 설치 근거에 붙이지 않습니다.

```sh
kubectl -n platform-lab-monitoring get secret grafana-admin -o jsonpath='{.data.admin-password}' | base64 --decode
printf '\n'
```

## 화면 읽기

- 준비 상태는 Kubernetes가 보고한 목표 복제본과 준비 복제본을 비교합니다. 하나도 준비되지 않은 상태, 일부 준비, 모두 준비, 목표가 0인 상태를 구분합니다. 워크로드가 삭제되었거나 지표 수집에 실패하면 해당 타일이 보이지 않을 수 있습니다. 옆에 표시되는 지표 스크레이프 상태를 함께 확인합니다.
- 로그는 상단 서비스 그룹, Pod 이름 또는 정규식, 컨테이너 이름 또는 정규식으로 좁힙니다. 예를 들어 Pod에 `.*garage.*`를 입력하면 이름에 `garage`가 있는 Pod의 로그가 표시됩니다. 과거 로그는 화면 시간 범위를 넓히고 자세한 조건은 Grafana Explore에서 Loki를 선택해 적용합니다.
- 대상은 네 네임스페이스의 Deployment·StatefulSet readiness와 Pod 표준 출력·표준 오류입니다. API 응답·DB 쿼리·Kafka 소비·S3 저장 검증은 프로젝트 설치 단계의 개별 검사를 사용합니다. 노드의 journal과 기존 Docker 컨테이너 로그는 수집 범위 밖입니다.

## 설정과 운영 범위

Grafana와 데이터 소스 서비스는 ClusterIP입니다. 대시보드는 로그인으로 보호하고 Ingress·NodePort를 만들지 않습니다. 모니터링 네임스페이스의 NetworkPolicy는 Grafana → Prometheus·Loki, Alloy → Loki, Prometheus → kube-state-metrics 연결만 열며, K3s의 네트워크 정책 집행이 필요합니다. Alloy는 지정된 네임스페이스의 Pod와 Pod 로그 조회 권한을 사용합니다. 호스트 로그 경로, Privileged Pod, 클러스터 전체 RBAC는 사용하지 않습니다. 컨테이너 로그에 포함된 내용은 그대로 저장되므로 서비스가 기록하는 인증 정보와 사용자 데이터를 점검합니다.

Prometheus는 48시간·300MB, Loki는 24시간 보존을 설정합니다. 각 Pod의 `emptyDir`를 사용하므로 Pod가 교체되면 그 Pod에 저장된 지표·로그·Grafana 세션이 사라집니다. 대시보드와 데이터 소스 설정은 Git 선언에서 복원되고 Grafana 관리 암호는 Kubernetes Secret에 남습니다. 다섯 구성의 메모리 요청 합계는 464MiB, 제한 합계는 1664MiB입니다. 실제 사용량은 수집량과 조회에 따라 달라집니다.

| 구성 | 고정 버전 |
| --- | --- |
| Grafana | [13.3.1](https://github.com/grafana/grafana/releases/tag/v13.3.1) |
| Prometheus | [3.16.0](https://github.com/prometheus/prometheus/releases/tag/v3.16.0) |
| kube-state-metrics | [2.20.0](https://github.com/kubernetes/kube-state-metrics/releases/tag/v2.20.0) |
| Loki | [3.7.10](https://github.com/grafana/loki/releases/tag/v3.7.10) |
| Alloy | [1.22.0](https://github.com/grafana/alloy/releases/tag/v1.22.0) |

[배포 선언](workloads.yaml)에 registry의 linux/amd64·linux/arm64를 포함한 OCI index digest를 고정합니다. 대시보드와 수집 규칙은 [설정 폴더](config/)에서 바꾸고 설치 스크립트로 다시 적용합니다. 파일 변경은 Kustomize가 생성한 ConfigMap 이름을 바꾸고 해당 Pod를 새로 만듭니다. 운영 서버에서 대시보드나 로그를 공개할 때에는 별도의 접근 정책과 보존 구성을 결정해야 합니다. [Alloy Pod 로그 수집](https://grafana.com/docs/alloy/latest/collect/logs-in-kubernetes/) · [Loki 보존](https://grafana.com/docs/loki/latest/operations/storage/retention/) · [kube-state-metrics 호환 범위](https://github.com/kubernetes/kube-state-metrics#compatibility-matrix)
