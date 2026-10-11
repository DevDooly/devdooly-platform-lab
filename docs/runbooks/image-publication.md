# API/web 이미지 게시와 배포 입력

이 문서는 GitHub Actions의 이미지 게시 절차를 설명한다. 정의 준비 시점에는 GHCR 게시와 Kubernetes 이미지 pull을 아직 실행하지 않았다. 앞서 성공한 Linux Compose 검증과 실제 레지스트리 게시·배포는 각각 별도로 기록한다.

## 게시할 이미지

- API: `ghcr.io/devdooly/devdooly-platform-lab-api`
- web: `ghcr.io/devdooly/devdooly-platform-lab-web`
- 플랫폼: 미니 PC에 맞춘 `linux/amd64`

기존 `infra/containers/api.Dockerfile`, `infra/containers/web.Dockerfile`을 사용한다. 회사 코드나 데이터를 포함하지 않는 합성 데이터 데모다. 베이스 이미지 digest는 기존 `infra/image-lock.json`과 Dockerfile의 값을 유지한다.

`.github/workflows/publish-images.yml`은 `Validate Lab containers`가 main에서 성공하면 해당 검증의 정확한 커밋을 checkout한다. 수동 실행도 성공한 검증 run ID를 요구한다. 공개 저장소의 run 메타데이터를 읽으므로 토큰에 `actions:read` 권한을 추가하지 않는다. 저장소·브랜치·워크플로 파일·성공 상태가 맞지 않으면 게시를 중단한다.

```sh
gh workflow run publish-images.yml --ref main -f validation_run_id=38133671877
```

위 run ID는 초기 Linux Compose 검증 기록이다. 이후에는 게시하려는 커밋의 성공한 run ID를 사용한다. 새 워크플로 자체는 main에 먼저 반영되어 있어야 한다.

태그는 `sha-<전체 소스 커밋>-r<게시 run ID>-a<시도 번호>`다. 재실행마다 새 태그를 만들어 앞선 게시를 덮어쓰지 않으며 `latest`를 만들지 않는다. GHCR의 태그 변경을 서비스 차원에서 금지한 것은 아니다. 실제 배포에는 태그 대신 레지스트리에서 다시 조회한 `repository@sha256:...`를 사용한다.

성공한 게시의 artifact에는 다음 두 파일만 담는다.

- `image-manifest.json`: 검증 커밋과 run ID, 게시 run URL, 관측 시각, 두 이미지의 실제 digest
- `helm-image-values.yaml`: 기존 `infra/charts/platform-lab`의 `api.image`, `web.image`, `api.sourceCommit`에 대응하는 입력

두 파일에는 비밀번호나 토큰이 없다. `database.existingSecret`은 배포 환경에서 별도로 지정한다. 이 워크플로는 클러스터 접속, Helm 설치, GitOps 변경, SSH 명령을 수행하지 않는다.

## 서버에 PAT를 저장하지 않는 권장 방식

GHCR 패키지는 최초 게시 시 기본적으로 private이다. 저장소가 public이어도 이미지가 자동으로 public이 되지는 않는다. 공개 포트폴리오용 합성 데모인 두 패키지를 GitHub 패키지 설정에서 public으로 전환한 뒤 익명 pull을 확인하는 방식을 권장한다. 이 경우 서버에 레지스트리 토큰이나 imagePullSecret이 필요 없다. 게시 워크플로는 작업 중에만 유효한 `GITHUB_TOKEN`으로 로그인한다. ([GHCR 공식 문서](https://docs.github.com/en/packages/working-with-a-github-packages-registry/working-with-the-container-registry), [패키지 접근 설정](https://docs.github.com/en/packages/learn-github-packages/configuring-a-packages-access-control-and-visibility))

익명 검증은 Docker 로그인이 없는 환경에서 manifest의 두 `reference`를 실제 pull하고 기록한다. 인증된 Actions에서 digest를 조회한 결과만으로 익명 pull 성공을 주장하지 않는다. 변경 이력에는 게시 run URL과 소스 커밋, 실제 digest, 익명 pull 및 Pod 준비 상태를 구분해 남긴다.

private 유지가 필요하면 K3s의 지속적인 pull에 읽기 권한이 있는 별도 자격 증명이 필요하다. 짧게 유효한 Actions 토큰을 서버에 저장하는 방식은 사용하지 않는다. 초기 단일 노드 검증의 대안은 인증 가능한 실행 환경에서 정확한 digest의 이미지를 아카이브로 내보내고, 개인 관리 경로로 전달하여 K3s containerd에 import하는 것이다. 이 대안은 노드 교체·이미지 갱신마다 import가 필요하며 레지스트리 기반 지속 배포를 대체하지 않는다. ([K3s 이미지 import 문서](https://docs.k3s.io/installation/airgap))

## Jenkins와 Argo CD의 다음 단계

현재 `Jenkinsfile`에는 Java 21 API `verify`, Node 24의 의존성 설치·check·test·build, JUnit 결과와 산출물 보관이 정의되어 있다. Kubernetes Pod agent를 사용하고 컨트롤러 executor는 0, 동시 빌드는 1로 제한한다. Docker socket은 마운트하지 않는다. 현재 파일 검토만으로 Jenkins 실제 실행 완료를 기록하지 않는다.

이번 Actions 게시 작업은 클러스터에 배포 가능한 최초 이미지를 만드는 독립 절차다. Jenkins의 이미지 게시까지 구현됐다는 뜻이 아니다. 이후에는 격리한 이미지 빌더 또는 Jib 등 socket 없는 빌드 경로, 제한된 레지스트리 게시 권한, 실제 digest를 GitOps에 반영할 권한과 승인 범위를 설정한다. Argo CD는 Git에 기록한 digest를 동기화하도록 연결한다. 이 문서의 워크플로에 더미 배포 성공 단계를 추가하지 않는다.

## 정의 확인과 실제 실행의 구분

준비 단계에서 공식 action 릴리스와 SHA를 확인하고 YAML 및 포함된 Python 구문을 검사한다. 실제 GHCR 게시가 성공한 뒤에만 이미지 게시 완료로 기록한다. 첫 게시가 실패하면 패키지 이름의 기존 소유권·저장소 연결·쓰기 권한을 확인한다. 기본 private 상태에서 발생하는 K3s pull 실패는 앱 준비 완료로 처리하지 않는다.

공식 action 기준은 `infra/publication-actions.lock.json`에 기록한다. Docker action 입력과 digest 출력은 [build-push-action](https://github.com/docker/build-push-action), 레지스트리 재조회는 [Buildx imagetools inspect](https://docs.docker.com/reference/cli/docker/buildx/imagetools/inspect/), 성공 워크플로 연결은 [GitHub workflow_run](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#workflow_run)을 기준으로 한다.
