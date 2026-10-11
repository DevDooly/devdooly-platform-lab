# 앱 Helm 배포 준비와 검증

[앱 chart](../../infra/charts/platform-lab/README.md)는 API·화면·MariaDB의 단일 노드 구성을 로컬 렌더링한 상태입니다. **이미지 게시, Secret 생성, Kubernetes 배포, PVC 연결과 Argo CD Sync는 아직 수행하지 않았습니다.** chart의 lint fixture는 배포 값으로 사용하지 않습니다.

## 먼저 충족할 조건

1. 사용자 확인을 마친 SSH 접속으로 호스트를 읽기 전용 점검합니다. 기존 서비스·데이터·포트·가용 자원과 백업 위치를 확인합니다.
2. [Linux CI에서 검증한 결과](../evidence/compose-ci/README.md)를 미니 PC의 [Compose 환경](local-compose.md)에서 재현합니다. 실제 MariaDB 연결, Flyway, 입력 12건의 결과(성공 7·실패 3·중복 2·대기 0), API 재시작 후 중복 적재가 없음을 확인합니다.
3. [플랫폼 설치](platform-install.md)와 [Jenkins CI](jenkins-ci.md)의 실제 실행을 확인합니다. K3s와 local-path provisioner가 정상이어야 합니다.
4. CI에서 검증한 Dockerfile로 배포용 API·web 이미지를 빌드해 registry에 게시하고 앱의 commit·digest를 기록합니다. 현재 Jenkinsfile은 검사·패키징까지만 하며 이미지 게시와 CD는 후속 작업입니다.
5. 별도 GitOps 저장소, namespace platform-lab과 고정 release lab을 준비합니다. 앱 배포의 소유자는 Argo CD로 정합니다.

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

앱 이미지에 사용하는 Dockerfile은 infra/containers/api.Dockerfile과 web.Dockerfile입니다. 화면은 SITE_BASE 기본값 /로 빌드하는 컨테이너용 산출물입니다. GitHub Pages의 프로젝트 경로를 적용한 정적 산출물을 그대로 대신 넣지 않습니다. Nginx는 같은 namespace의 api:8080을 사용하며 /api/만 API에 전달합니다. Actuator는 공개 Nginx 경로에 연결하지 않습니다.

## 클러스터 적용 전 검증

먼저 [chart README의 로컬 검증](../../infra/charts/platform-lab/README.md#로컬-렌더링-검증)을 재현합니다. 기본 values만 사용하면 필수 이미지·Secret 입력 누락으로 실패해야 합니다.

그 뒤 실제 환경 values를 준비하고 저장소 루트에서 **render만** 수행합니다. 아래 경로는 사용자가 준비한 환경 값의 예시 경로이며 아직 존재하는 파일이 아닙니다.

    helm lint infra/charts/platform-lab --strict --kube-version 1.36.5 --values .local/app-values.yaml
    helm template lab infra/charts/platform-lab --namespace platform-lab --kube-version 1.36.5 --values .local/app-values.yaml > .local/app-helm-render/real-values.yaml

렌더링 결과에서 다음을 확인합니다.

- 앱 이미지의 digest가 실제 registry 산출물과 일치하고 fixture의 example.invalid가 없습니다.
- api·web·db는 ClusterIP이며 Ingress·NodePort·hostPort가 없습니다.
- Secret 값과 Secret 리소스를 생성하지 않고 기존 Secret 이름·key만 참조합니다.
- DB claim은 신규 데이터 전용 local-path 10Gi이고 기존 데이터 경로를 가리키지 않습니다.
- API는 단일 replica·Recreate, startup/liveness는 liveness health, readiness는 DB를 포함한 health입니다.

접속과 namespace 준비 후 Kubernetes API server의 dry-run 검증을 수행합니다. 이 명령은 파일을 서버에서 검사할 뿐 저장하지 않으며 admission 정책·API 스키마 오류를 찾습니다. 참조 Secret의 존재, 이미지 실행, DB 연결과 PVC 동작까지 보장하지 않습니다.

    kubectl -n platform-lab apply --dry-run=server -f .local/app-helm-render/real-values.yaml

## Argo CD 적용 후 확인할 항목

Argo CD Application 생성·GitOps 연결은 후속 단계에서 실제 환경에 맞춰 수행합니다. 이 문서에는 자동 설치나 helm upgrade 실행 명령을 넣지 않습니다.

1. Argo CD의 대상 namespace와 release 이름을 고정하고, 실제 환경 values와 이 chart 버전을 연결합니다.
2. Sync 후 DB PVC Bound, DB Ready, API Ready, 화면 Ready 순서로 확인합니다. 첫 DB 초기화 전에 API가 시작되면 재시도할 수 있습니다.
3. 관리자 접근 경로는 SSH 터널을 사용합니다. 서버의 임시 포트 전달은 loopback에만 바인딩합니다.

       kubectl -n platform-lab port-forward --address 127.0.0.1 service/web 8080:8080

4. SSH 터널을 통해 화면과 /api/demo/runs, /api/platform/summary, /api/platform/releases를 확인합니다. 샘플 대체 화면과 실제 API 연결 상태를 구분합니다. 성공 7·실패 3·중복 2·대기 0과 sourceCommit/imageDigest를 확인합니다.
5. API를 순차 재시작하고 run·outcome 수가 그대로인지, 화면 조회가 돌아오는지 확인합니다. 아직 이 chart에서 실제로 수행한 검증은 아닙니다.
6. 재현 조건과 실제 결과를 증거 문서에 남긴 뒤에만 Kubernetes 배포와 Argo CD Sync를 완료로 표시합니다.

## 운영 제약

단일 replica와 Recreate는 업데이트 중 짧은 중단을 허용합니다. sample seed의 최초 동시 초기화를 지원하거나 무중단 배포를 보장하지 않습니다. DB가 실패하면 API readiness가 내려가고 liveness는 DB 상태만으로 API를 재시작하지 않도록 분리했습니다.

MariaDB 공식 entrypoint는 root로 볼륨 권한을 준비한 뒤 mysql 사용자로 전환합니다. API/web의 nonroot 설정과 구분합니다. namespace에 restricted Pod Security를 강제했다면 현재 DB 설정이 거부되므로 실행 사용자·볼륨 권한을 실제 이미지에서 검증하는 별도 설계가 필요합니다.

PVC는 StatefulSet 삭제·축소 시 유지되지만 namespace/PVC 삭제를 막는 보호 장치가 아닙니다. release·namespace 변경, 비밀번호 회전, 복구는 기존 claim·계정과의 연결을 확인한 뒤 진행합니다. local-path는 단일 노드 저장소이며 백업·고가용성이 아닙니다. MariaDB 버전 변경 시 이전 앱 이미지로 되돌리는 것만으로 DB migration을 되돌릴 수는 없습니다.