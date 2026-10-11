# 개인 Lab 앱 Helm chart

Spring Boot API, Nginx 정적 화면, MariaDB를 전용 namespace에 하나씩 배치하는 최소 chart입니다. Kubernetes 1.32 이상을 대상으로 하며 K3s 1.36.5 기준으로 로컬 렌더링했습니다.

API/web 이미지 빌드와 MariaDB 통합 실행은 [Linux Compose CI](../../../docs/evidence/compose-ci/README.md)에서 검증했습니다. **registry 이미지 게시와 이 chart의 Kubernetes 배포·PVC 연결·Argo CD Sync는 아직 수행하지 않았습니다.** 기본 values의 이미지 repository·digest와 database.existingSecret는 의도적으로 비어 있습니다.

## 구성과 제약

| 구성 | 설정 |
| --- | --- |
| API | Deployment 1개, replica 1, Recreate, UID/GID 10001 |
| 화면 | Deployment 1개, replica 1, Recreate, Nginx UID/GID 101 |
| DB | MariaDB 11.8.9, StatefulSet replica 1, 저장소 이미지 digest 고정 |
| 저장소 | DB 전용 ReadWriteOnce 10Gi local-path PVC |
| 통신 | api:8080, web:8080, db:3306, 모두 ClusterIP |
| 관리자 권한 | ServiceAccount 토큰 자동 마운트 안 함, RBAC 생성 안 함 |
| 공개 경로 | Ingress 지원 안 함, NodePort·LoadBalancer·hostPort 없음 |
| 비밀번호 | 기존 Secret의 app-password·root-password key 참조만 함 |

Service 이름은 api·web·db로 고정했습니다. chart는 Nginx의 `API_UPSTREAM_HOST`에 `api.<Release.Namespace>.svc.cluster.local`을 전달합니다. Nginx의 동적 resolver가 search 도메인을 확장하지 않으므로 Kubernetes에서는 전체 Service 이름을 사용하며, Compose의 기본 호스트 `api`와 구분합니다. **전용 namespace에 chart release 하나만** 설치해야 합니다. 기본 문서의 release는 lab, namespace는 platform-lab입니다. 기존 서비스·DB 경로를 재사용하지 않습니다.

API/web은 읽기 전용 루트 파일 시스템, 제한된 /tmp emptyDir, RuntimeDefault, 권한 상승 금지와 capability 제거를 적용합니다. MariaDB는 공식 entrypoint가 자체 데이터 경로의 권한을 준비한 뒤 mysql 사용자로 전환하는 방식을 유지합니다. DB 초기 프로세스까지 nonroot라고 주장하지 않으며 이 설정 그대로는 Pod Security restricted 정책을 충족하지 않습니다.

## 자원 예산

| 컨테이너 | CPU 요청 / 제한 | 메모리 요청 / 제한 |
| --- | --- | --- |
| API | 100m / 1 | 256Mi / 768Mi |
| 화면 | 25m / 250m | 64Mi / 192Mi |
| MariaDB | 100m / 1 | 512Mi / 1536Mi |
| 합계 | 225m / 2.25 | 832Mi / 2496Mi |

Jenkins·Argo CD·K3s·빌드 agent·OS 자원은 별도입니다. DB PVC는 10Gi이며 local-path 용량 요청이 디스크 사용량의 강제 상한을 보장하지는 않습니다.

## 로컬 렌더링 검증

설치된 Helm 4.3.0으로 저장소 루트에서 실행합니다.

    helm lint infra/charts/platform-lab --strict --kube-version 1.36.5 --values infra/charts/platform-lab/ci/lint-values.yaml
    helm template lab infra/charts/platform-lab --namespace platform-lab --kube-version 1.36.5 --values infra/charts/platform-lab/ci/lint-values.yaml

ci/lint-values.yaml은 존재하지 않는 example.invalid 이미지와 가짜 Secret 이름으로 **문법·정책만** 검사하는 fixture입니다. 설치, kubectl apply, Argo CD Application의 valueFiles에 사용하지 않습니다. 실행 가능한 배포 예시가 아닙니다.

화면 의존성이 설치된 Node 환경에서는 다음 명령으로 같은 검증과 15개 정책 검사, 잘못된 입력 6개의 거부를 재현합니다.

    node infra/charts/platform-lab/ci/validate-render.mjs

Helm 경로가 다르면 HELM_BINARY에 실행 파일 경로를 지정합니다. 기본 도구는 저장소 .local/tools/helm-4.3.0/windows-amd64/helm.exe이며 Helm 4.3.0 빌드를 확인합니다. 원본 manifest는 Git 제외 경로 .local/app-helm-render에만 저장하고, 공개 검증 결과는 [ci/render-validation.json](ci/render-validation.json)에 기록합니다.

2026-10-11 검증: Helm v4.3.0+gbec5b06, strict lint/render 통과, manifest 7개, 정책 15개 통과, 필수값 누락·잘못된 digest·API 복제 확대·Ingress·다른 storageClass 입력 6개 거부 확인. Kubernetes API server 검증 및 실제 실행 결과로 해석하지 않습니다.

## 실제 배포 전에 필요한 값

- api.image.repository·digest, web.image.repository·digest: 이 저장소 Dockerfile로 빌드하고 registry에 게시한 **앱 이미지**의 주소와 실제 sha256 digest입니다. infra/image-lock.json에 있는 Temurin·Nginx 기반 이미지 digest를 앱 digest로 대신 넣지 않습니다.
- api.sourceCommit: 해당 앱 이미지에 대응하는 Git commit입니다. 기본값 unknown은 아직 게시된 앱 이미지가 없다는 뜻입니다.
- database.existingSecret: 같은 namespace에 미리 준비한 Secret 이름입니다. appPasswordKey·rootPasswordKey로 지정한 두 key가 있어야 합니다. Secret의 값은 Git이나 Helm values에 넣지 않습니다.
- imagePullSecrets: registry가 비공개이면 같은 namespace의 기존 image pull Secret 이름을 지정합니다.

실제 구성은 별도 GitOps 저장소의 환경 values에서 관리하고 Argo CD가 배포를 소유합니다. Jenkins에서 같은 앱에 helm upgrade를 추가하지 않습니다. 후속 절차는 [앱 배포 안내](../../../docs/runbooks/app-helm.md)를 따릅니다.

## 초기화·보존 범위

Flyway와 합성 데이터 seed는 API 시작 시 실행됩니다. API replica 1과 Recreate는 이 Lab의 단일 초기화 프로세스 전제이며, 동시 최초 초기화를 해결하는 분산 잠금 구현이 아닙니다. 복제 확장 전에 migration/seed 실행을 별도로 설계해야 합니다. API 기동이 DB 초기화보다 빠르면 프로세스가 실패·재시도할 수 있습니다. probe가 DB 준비를 기다리는 init 단계나 의존성 순서를 대신하지 않습니다.

DB PVC는 StatefulSet 삭제·축소 시 유지됩니다. **namespace 삭제나 PVC 직접 삭제까지 막아주지는 않습니다.** release/namespace 이름을 바꾸면 기존 claim을 자동으로 재사용하지 않습니다. 보존된 PVC에 재설치할 때는 기존 계정 비밀번호를 유지해야 하며 Secret 값만 바꾸어도 DB 계정 비밀번호가 갱신되지는 않습니다. 단일 노드 local-path는 복제·백업이 아니므로 별도 백업과 복구 검증이 필요합니다.

## 공식 참고

- [Kubernetes StatefulSet PVC 보존](https://kubernetes.io/docs/concepts/workloads/controllers/statefulset/#persistentvolumeclaim-retention)
- [Spring Boot Kubernetes probes](https://docs.spring.io/spring-boot/reference/actuator/endpoints.html#actuator.endpoints.kubernetes-probes)
- [MariaDB healthcheck.sh](https://mariadb.com/docs/server/server-management/automated-mariadb-deployment-and-administration/docker-and-mariadb/using-healthcheck-sh)
- [MariaDB 공식 Dockerfile과 entrypoint](https://github.com/MariaDB/mariadb-docker)
- [Nginx 공식 Alpine Dockerfile](https://github.com/nginx/docker-nginx/blob/master/stable/alpine-slim/Dockerfile)