# 앱 Helm 배포 준비와 검증

[앱 chart](../../infra/charts/platform-lab/README.md)는 API·화면·MariaDB를 단일 노드에 배치합니다. 2026-10-11 실제 게시 digest와 기존 Secret을 참조해 배포했으며 DB PVC Bound, 앱 Pod Ready, Argo CD Synced/Healthy를 확인했습니다. **이 상태만으로 웹에서 API를 호출하는 HTTP 경로가 정상이라는 뜻은 아닙니다.** 최신 결과와 남은 문제는 [미니 PC 검증 기록](../evidence/mini-pc/README.md)을 따릅니다. chart의 lint fixture는 배포 값으로 사용하지 않습니다.

## 먼저 충족할 조건

1. 사용자 확인을 마친 SSH 접속으로 호스트를 읽기 전용 점검합니다. 기존 서비스·데이터·포트·가용 자원과 백업 위치를 확인합니다.
2. [Linux Compose CI](../evidence/compose-ci/README.md)의 빌드·MariaDB·Flyway·데이터 보존 결과를 확인합니다. [Compose](local-compose.md)는 별도 통합 검증 경로이며, 미니 PC에서는 K3s의 실제 image·PVC·API 동작을 따로 검증합니다.
3. [신규 bootstrap](k3s-bootstrap.md)과 [플랫폼 설치](platform-install.md) 결과를 확인합니다. K3s와 local-path provisioner가 정상이어야 합니다. [Jenkins 실제 CI](jenkins-ci.md)는 독립된 완료 조건으로 확인합니다.
4. CI에서 검증한 Dockerfile로 배포용 API·web 이미지를 빌드해 registry에 게시하고 앱의 commit·digest를 기록합니다. 현재 Jenkinsfile은 검사·패키징까지만 하며 Jenkins에서의 이미지 게시·GitOps 값 갱신은 후속 작업입니다.
5. [ADR 0003](../adr/0003-gitops-in-existing-repository.md)에 따라 같은 저장소의 [gitops](../../gitops/README.md)를 사용합니다. namespace platform-lab과 고정 release lab을 유지하고 앱 배포는 Argo CD가 소유합니다.

이 단계의 chart에는 public ingress, 인증 게이트웨이와 HTTPS가 없습니다. ClusterIP는 외부 노출 설정을 만들지 않는다는 뜻이며 클러스터 내부의 다른 Pod까지 격리하는 NetworkPolicy는 아직 포함하지 않습니다.

## 환경 값과 사전 준비

GitOps 환경 values에는 다음 항목의 **실제 값**을 설정합니다.

| 값 | 의미 |
| --- | --- |
| api.image.repository·digest | 빌드·게시한 API 앱 이미지와 sha256 digest |
| api.sourceCommit | 같은 빌드의 Git commit |
| web.image.repository·digest | 빌드·게시한 화면 앱 이미지와 sha256 digest |
| database.existingSecret | 해당 namespace에 별도로 준비한 DB Secret 이름 |
| database.appPasswordKey·rootPasswordKey | 기존 Secret의 앱 계정·root 비밀번호 key 이름 |
| imagePullSecrets | 필요한 경우 기존 registry 인증 Secret 이름 |

DB 이름과 앱 계정은 platform_lab로 고정했습니다. chart는 DB 비밀번호 값을 받지 않고 Secret도 생성하지 않습니다. 앱용 Secret과 registry 인증은 배포 전에 별도 경로로 준비하되 값이나 토큰을 Git, 명령 기록, 검증 출력에 남기지 않습니다. 이미 DB가 초기화된 PVC에서는 초기 비밀번호 환경 변수로 계정을 다시 설정하지 않습니다.

앱 이미지에 사용하는 Dockerfile은 infra/containers/api.Dockerfile과 web.Dockerfile입니다. 화면은 SITE_BASE 기본값 /로 빌드하는 컨테이너용 산출물입니다. GitHub Pages의 프로젝트 경로를 적용한 정적 산출물을 그대로 대신 넣지 않습니다. chart는 Nginx의 `API_UPSTREAM_HOST`에 `api.<Release.Namespace>.svc.cluster.local`을 주입하며 `/api/`만 API의 8080 포트로 전달합니다. Nginx의 동적 DNS resolver는 `/etc/resolv.conf`의 search 도메인을 확장하지 않으므로 Kubernetes에서는 짧은 `api` 대신 이 전체 이름을 사용합니다. 컨테이너의 기본값 `api`는 Compose용이며, DNS 재조회와 `/tmp`의 설정 생성은 유지합니다. Actuator는 공개 Nginx 경로에 연결하지 않습니다.

## 클러스터 적용 전 검증

먼저 [chart README의 로컬 검증](../../infra/charts/platform-lab/README.md#로컬-렌더링-검증)을 재현합니다. 기본 values만 사용하면 필수 이미지·Secret 입력 누락으로 실패해야 합니다.

실제 환경 values는 [gitops/environments/home-lab/values.yaml](../../gitops/environments/home-lab/values.yaml)에 있습니다. 게시 digest·source commit·기존 Secret 이름을 기록하고 비밀번호는 포함하지 않습니다. 저장소 루트에서 **render만** 수행합니다.

    helm lint infra/charts/platform-lab --strict --kube-version 1.36.5 --values gitops/environments/home-lab/values.yaml
    helm template lab infra/charts/platform-lab --namespace platform-lab --kube-version 1.36.5 --values gitops/environments/home-lab/values.yaml > .local/app-helm-render/real-values.yaml

렌더링 결과에서 다음을 확인합니다.

- 앱 이미지의 digest가 실제 registry 산출물과 일치하고 fixture의 example.invalid가 없습니다.
- api·web·db는 ClusterIP이며 Ingress·NodePort·hostPort가 없습니다.
- web의 `API_UPSTREAM_HOST`는 실제 release namespace의 `api.<namespace>.svc.cluster.local`입니다. 정적 `/`의 정상 응답만으로 API proxy가 정상이라고 판단하지 않습니다.
- Secret 값과 Secret 리소스를 생성하지 않고 기존 Secret 이름·key만 참조합니다.
- DB claim은 신규 데이터 전용 local-path 10Gi이고 기존 데이터 경로를 가리키지 않습니다.
- API는 단일 replica·Recreate, startup/liveness는 liveness health, readiness는 DB를 포함한 health입니다.

접속과 namespace 준비 후 Kubernetes API server의 dry-run 검증을 수행합니다. 이 명령은 파일을 서버에서 검사할 뿐 저장하지 않으며 admission 정책·API 스키마 오류를 찾습니다. 참조 Secret의 존재, 이미지 실행, DB 연결과 PVC 동작까지 보장하지 않습니다.

    kubectl -n platform-lab apply --dry-run=server -f .local/app-helm-render/real-values.yaml

## Argo CD 적용 후 확인할 항목

[AppProject](../../gitops/bootstrap/project.yaml)와 [Application](../../gitops/bootstrap/application.yaml)은 같은 저장소 main의 chart·환경 values를 단일 source로 읽습니다. AppProject는 전용 namespace와 필요한 리소스 종류만 허용하고 자동 prune과 Application finalizer는 사용하지 않습니다. namespace와 DB Secret은 관리자가 별도로 준비하며 이 문서는 같은 앱의 helm upgrade를 별도 실행하지 않습니다.

1. Argo CD의 대상 namespace와 release 이름을 고정하고, 실제 환경 values와 이 chart 버전을 연결합니다.
2. Sync 후 DB PVC Bound, DB Ready, API Ready, 화면 Ready 순서로 확인합니다. 이번 배포에서 해당 상태와 Argo Synced/Healthy를 확인했습니다. 첫 DB 초기화 전에 API가 시작되면 재시도할 수 있으며 API의 초기 재시작은 그 원인과 이후 안정 여부를 따로 확인합니다.
3. 관리자 접근 경로는 SSH 터널을 사용합니다. 서버의 임시 포트 전달은 loopback에만 바인딩합니다.

       kubectl -n platform-lab port-forward --address 127.0.0.1 service/web 8080:8080

4. SSH 터널에서 화면을 연 뒤 같은 origin의 /api/demo/runs, /api/platform/summary, /api/platform/releases를 확인합니다. API 직접 호출 성공과 Nginx를 통한 호출 성공도 구분합니다. 502·연결 실패나 정적 샘플 대체 화면은 실제 API 성공으로 처리하지 않습니다. 입력 12건 = 성공 7·실패 3·중복 2·대기 0과 sourceCommit/imageDigest를 검증합니다.
5. API를 순차 재시작하고 run·outcome 수가 그대로인지, 화면 조회가 돌아오는지 확인합니다. 실제 완료 여부는 미니 PC 증거에 해당 검사 결과가 있을 때만 기록합니다.
6. 재현 조건과 실제 결과를 증거 문서에 남긴 뒤에만 Kubernetes 배포와 Argo CD Sync를 완료로 표시합니다.

## 운영 제약

단일 replica와 Recreate는 업데이트 중 짧은 중단을 허용합니다. sample seed의 최초 동시 초기화를 지원하거나 무중단 배포를 보장하지 않습니다. DB가 실패하면 API readiness가 내려가고 liveness는 DB 상태만으로 API를 재시작하지 않도록 분리했습니다.

MariaDB 공식 entrypoint는 root로 볼륨 권한을 준비한 뒤 mysql 사용자로 전환합니다. API/web의 nonroot 설정과 구분합니다. namespace에 restricted Pod Security를 강제했다면 현재 DB 설정이 거부되므로 실행 사용자·볼륨 권한을 실제 이미지에서 검증하는 별도 설계가 필요합니다.

DB PVC는 StatefulSet 삭제·축소 시 유지되지만 namespace/PVC 삭제를 막는 보호 장치가 아닙니다. 실제 Jenkins·DB PV의 reclaimPolicy는 Delete이므로 claim을 삭제하면 provisioner가 데이터를 제거할 수 있습니다. 전용 저장 경로는 /var/lib/devdooly-platform-lab/storage입니다. release·namespace 변경, 비밀번호 회전, 복구는 기존 claim·계정과의 연결을 확인한 뒤 진행합니다. local-path는 단일 노드 저장소이며 백업·고가용성이 아닙니다. MariaDB 버전 변경 시 이전 앱 이미지로 되돌리는 것만으로 DB migration을 되돌릴 수는 없습니다.

현재 bootstrap 감사 자료는 같은 호스트의 설정·네트워크 상태 기록입니다. MariaDB·Jenkins·K3s의 외부 데이터 백업과 복원, 호스트 재부팅 복구는 아직 검증하지 않았습니다. 데이터 보존을 주장하려면 백업 위치·대상·복원 방법과 실제 결과를 별도로 남겨야 합니다.
