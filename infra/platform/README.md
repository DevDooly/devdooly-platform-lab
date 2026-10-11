# 미니 PC 플랫폼 설치 설정

공식 차트의 로컬 렌더링을 검증했다. 미니 PC의 K3s 설치, Jenkins 실행과 Argo CD 동기화는 아직 검증하지 않았다. 앱 이미지 빌드와 MariaDB 통합은 별도의 [GitHub Actions Compose CI](../../docs/evidence/compose-ci/README.md)에서 검증했다.

| 파일 | 역할 |
| --- | --- |
| [versions.lock.json](versions.lock.json) | 선택 버전, 다운로드 주소와 확인한 체크섬 |
| [k3s-config.example.yaml](k3s-config.example.yaml) | 호스트 점검 이후 사용할 신규 단일 노드 설정 |
| [jenkins-values.yaml](jenkins-values.yaml) | controller executor 0, 빌드 Pod 1개, 별도 agent 계정 |
| [argocd-values.yaml](argocd-values.yaml) | 단일 노드 Argo CD, ClusterIP, TLS·인증 |
| [render-validation.json](render-validation.json) | 실제 Helm 렌더링 결과 |

[설치 절차](../../docs/runbooks/platform-install.md)에 따라 진행한다. Secret을 포함할 수 있는 렌더 원본은 Git 제외 .local/platform-render에만 둔다.

관리 도구는 NodePort·LoadBalancer·Ingress를 만들지 않는다. Jenkins 10Gi PVC는 local-path이며 다른 PC에 복제되는 백업이 아니다. Argo CD의 Redis와 Git cache에는 PVC를 추가하지 않는다. GitOps와 Kubernetes 설정·Secret을 별도로 백업한다.

JCasC 기본 Pod template 이름은 default다. 실제 Pipeline은 이를 상속하고 [Java21 Maven·Node agent](../jenkins/agent-pod.yaml)를 추가한다. jnlp는 JDK25이며 API의 Java21과 역할이 다르다. build agent 계정에는 Kubernetes API token을 자동 마운트하지 않는다.

주요 플러그인 버전을 명시하고 재시작마다 교체하지 않는다. 전이 의존성과 모든 실행 이미지를 digest로 고정한 custom controller image까지 검증한 것은 아니다. 업그레이드 시 PVC 백업과 플러그인 호환성을 확인한다.

## 로컬 검증 재실행

현재 검증은 Windows Helm4.3.0 공식 ZIP의 체크섬을 확인해 .local/tools/helm-4.3.0에 푼 상태에서 실행했다. 공식 두 차트는 .local/platform-render/charts에 보관한다. Git clone만으로 이 바이너리·차트 원본은 생기지 않는다.

apps/lab-web에서 npm ci를 마쳐 lockfile의 YAML parser를 준비한 뒤 저장소 루트에서 다음 명령을 실행한다.

    node infra/platform/validate-render.mjs

이 도구는 공식 고정 차트에 helm lint --strict와 helm template을 실제로 실행하고 접근 범위·JCasC·agent 상속을 확인한다. Secret 원본은 출력하지 않는다. 검증 요약과 버전 목록을 갱신하므로 변경 내용을 검토한다. Kubernetes API dry-run·Pod 기동·Pipeline linter를 대신하지 않는다.