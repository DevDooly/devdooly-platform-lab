# Jenkins CI 연결과 첫 실행

현재 상태는 **파이프라인 정의 작성, 실제 Jenkins 실행 전**입니다. 기존 API의 Maven 검증과 화면의 npm 검증은 각각의 로컬·컨테이너 증거를 따릅니다. Jenkins 설치, plugin 조합, 동적 agent 기동과 artifact 게시까지 통과해야 CI 검증 완료로 바꿉니다.

## 실행하는 작업

1. SCM에서 이 저장소를 checkout하고 commit과 build 번호만 `ci-build-info.txt`에 기록합니다.
2. Java 21 container에서 `apps/api/./mvnw -B -ntp verify`를 실행합니다. Surefire XML을 성공·실패 모두 JUnit 결과로 수집합니다.
3. Node 24 container에서 `npm ci`, `npm run check`, `npm test`, `npm run build`를 순서대로 실행합니다.
4. 모두 통과한 build만 API jar, 정적 화면 dist와 commit 정보를 archive하고 fingerprint를 기록합니다.

실패를 무시하거나 빌드·배포를 성공으로 반환하는 대체 stage는 없습니다. 현재 pipeline에는 registry 게시, GitOps PR, Helm 배포 단계가 없습니다.

## Jenkins와 Kubernetes 준비

- [플랫폼 설치 절차](platform-install.md)를 따라 controller를 설치하고 인증된 관리 경로로 접속합니다.
- controller의 built-in executor를 **0**, Kubernetes cloud의 전체 agent 상한과 template 상한을 **1**로 둡니다. job 단위 `disableConcurrentBuilds()`도 적용됩니다.
- chart의 Pod template 이름은 `default`, agent ServiceAccount 이름은 `jenkins-build-agent`로 맞춥니다. [Pod 정의](../../infra/jenkins/agent-pod.yaml)는 이 template을 merge 방식으로 상속합니다.
- controller ServiceAccount에는 agent Pod 생성·관찰에 필요한 namespace 범위 권한만 부여합니다. build ServiceAccount는 Kubernetes 권한을 주지 않고 토큰 자동 mount를 끕니다.
- Pipeline / Declarative Pipeline / Git / Kubernetes / JUnit / Timestamper plugin을 설치하고 검증한 버전을 chart와 함께 고정합니다. 설치된 chart의 plugin 목록에 없는 항목은 별도 추가합니다.
- cloud의 Test Connection이 성공해야 합니다. agent가 controller 주소로 연결할 수 있는지 확인하고 controller 전체를 외부 공개하지 않습니다.

처음에는 `main`을 대상으로 Pipeline from SCM job 하나를 만들고 Script Path를 `Jenkinsfile`로 설정합니다. 공개 저장소 checkout은 쓰기 자격증명 없이 시작합니다. 수동 Build Now 또는 제한된 Poll SCM으로 첫 실행을 확인합니다. fork PR은 비밀정보가 없는 검증 job만 사용하고 controller의 관리 경로·자격증명을 넘기지 않습니다.

## 비루트 agent와 자원

jnlp는 chart의 기본 JDK 25 연결용 agent를 상속합니다. API 빌드는 별도의 Temurin Java 21, 화면은 Node 24.19.0 image를 쓰며 두 digest는 [이미지 기록](../../infra/image-lock.json)에 고정되어 있습니다. jnlp를 Java 21 앱 image로 바꾸면 controller Java 요구사항과 충돌할 수 있으므로 역할을 나눕니다.

Pod와 모든 container는 UID/GID 1000, fsGroup 1000으로 동작합니다. `/home/jenkins`를 공유 `emptyDir`에 두고 HOME, Maven Wrapper·repository, npm/XDG cache가 쓰기 가능하게 합니다. `/home/jenkins/agent`에는 Kubernetes plugin의 공유 workspace가 별도로 mount됩니다. 캐시는 Pod 삭제와 함께 사라지며 credential과 함께 영구 PVC로 보존하지 않습니다.

Maven Wrapper 3.3.4는 공식 **bin** 방식입니다. wrapper jar를 저장소에 포함하고 Java가 고정 Maven ZIP을 검증·압축 해제하므로 agent에서 root 권한으로 unzip을 설치할 필요가 없습니다. `wrapperSha256Sum`과 `distributionSha256Sum`을 고정합니다. Maven은 최대 heap 512MiB, fork JVM은 container RAM의 45% 범위를 기본값으로 사용하고 Node heap은 1GiB입니다. 필요하면 실제 메모리 관측으로 조정합니다.

container RAM limit 합계는 3,968MiB입니다. API와 화면은 순서대로 실행합니다. `emptyDir` HOME은 최대 6GiB이며 workspace·cache의 ephemeral-storage 사용량도 관측합니다. 실제 서버의 다른 서비스를 고려해 cloud 상한 1을 유지합니다.

## 첫 실행의 완료 조건

- [ ] controller executor 0과 cloud/template agent 상한 1 확인
- [ ] `default`를 상속한 Pod에 jnlp(JDK 25), maven(Java 21), node(Node 24)가 생성됨
- [ ] UID/GID와 HOME·workspace 쓰기 권한 확인, ServiceAccount token 및 Docker socket mount 없음
- [ ] API 테스트 수와 실패 여부가 Jenkins JUnit 화면에 보임
- [ ] 정상 build에 jar·dist·source commit이 archive됨
- [ ] 실패하는 별도 테스트 변경에서 build가 실패하고 artifact가 성공 게시되지 않음
- [ ] 연속 실행 요청이 동시에 시작하지 않고 대기함
- [ ] job 로그에 비밀정보·관리 토큰·서버 점검 원본이 포함되지 않음
- [ ] 원본 build URL, commit, 관측 시각과 확인 결과를 공개 가능한 검증 기록으로 남김

서버 설치 전에는 이 체크리스트를 완료 처리하지 않습니다. 운영 중인 다른 job이나 Jenkins 데이터를 지우며 실패 시나리오를 시험하지 않습니다.

## 이미지 게시와 GitOps 연결 후속 작업

GHCR 게시에는 해당 package에 필요한 쓰기 권한만 가진 별도 자격증명을 구성합니다. Java는 Jib 등 Docker daemon 없이 image를 만들고 게시한 digest를 확인하는 단계를 실제 검증 후 추가합니다. frontend builder도 비루트 image build 방식을 별도로 검증합니다.

GitOps 저장소를 만든 뒤 허용된 chart values만 수정하는 PR 권한을 별도로 구성합니다. 테스트 통과 → source commit의 image digest → GitOps PR → merge → Argo CD 상태 → runtime 정보 순서로 추적합니다. Jenkins에서 Argo가 관리하는 앱에 `helm upgrade`를 함께 실행하지 않습니다.

registry와 GitOps 권한은 untrusted fork PR에 제공하지 않습니다. 웹훅을 추가할 때는 서명 검증을 하는 경로를 별도로 만들고 Jenkins 관리자 화면 전체를 공개하지 않습니다. 실제 CI/CD 연결 전에는 API의 Jenkins·Argo 상태를 NOT_CONFIGURED로 유지합니다.

## 공식 근거

- [Kubernetes plugin의 yamlFile·template 상속·동일 UID 지침](https://plugins.jenkins.io/kubernetes/)
- [Jenkins Pipeline 문법과 동시 실행 제한](https://www.jenkins.io/doc/book/pipeline/syntax/)
- [controller executor 0 격리](https://www.jenkins.io/doc/book/security/controller-isolation/)
- [JUnit 결과 수집](https://www.jenkins.io/doc/pipeline/steps/junit/)
- [artifact archive와 fingerprint](https://www.jenkins.io/doc/pipeline/steps/core/)
- [공식 Maven Wrapper bin 방식과 checksum](https://maven.apache.org/tools/wrapper/)

2026-10-11 공식 문서를 확인했습니다. agent-pod.yaml은 YAML 2.9.1 파싱을 통과했고 이미지 digest를 image-lock.json과 대조했습니다. Jenkins chart 5.9.68의 Helm template·strict lint 결과에서 default template 이름, merge 전략, ServiceAccount, UID/GID/fsGroup과 agent 상한을 확인했습니다. Jenkinsfile은 공식 문법에 따라 정의를 검토했으며 Jenkins 서버의 Declarative Linter와 실제 agent 실행은 설치 이후 진행합니다.
