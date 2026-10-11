# Jenkins CI 운영과 재검증

2026-10-11 미니 PC의 K3s에서 실제 Jenkins Build 3을 실행했습니다. API JUnit 15개와 웹 Node 테스트 13개가 통과했고, 산출물 9개와 SCM 커밋의 일치를 확인했습니다. [실행 근거와 한계](../evidence/jenkins-ci/README.md)를 먼저 확인합니다.

## 실행하는 작업

1. main의 Jenkinsfile을 읽고 checkout 반환값에서 40자리 source commit을 검증해 ci-build-info.txt에 build 번호와 함께 기록합니다. SHA가 없으면 빌드를 실패시킵니다.
2. Java 21 container에서 apps/api의 Maven Wrapper verify를 실행합니다. Surefire XML을 성공·실패와 관계없이 JUnit 결과로 수집하며, 빈 결과를 허용하지 않습니다.
3. Node 24 container에서 npm ci, npm run check, npm test, npm run build를 실행합니다.
4. 모든 단계가 성공한 경우 API jar, 웹 dist, ci-build-info.txt를 archive하고 fingerprint를 기록합니다.

JUnit 보고서는 API 테스트만 포함합니다. 웹 테스트 수치는 Node 테스트 출력에서 별도로 확인합니다. Jenkins는 registry 게시, GitOps PR, Helm 배포를 실행하지 않습니다.

## Kubernetes agent와 권한

controller의 built-in executor는 0입니다. Kubernetes cloud 전체와 default template의 agent 상한은 1이며, job에도 disableConcurrentBuilds()가 적용됩니다. 동시 요청을 실제로 보내는 실험은 아직 하지 않았습니다.

[Pod 정의](../../infra/jenkins/agent-pod.yaml)는 chart의 default template을 merge 방식으로 상속합니다. controller SA만 namespace 안에서 agent Pod를 관리하고, build에는 권한 없는 jenkins-build-agent SA를 사용합니다. 실제 Pod에서 token 자동 mount가 꺼져 있고 Docker socket이 없음을 관측했습니다.

jnlp는 chart 기본 JDK 25 연결용 agent를 상속합니다. API 빌드는 별도 Temurin Java 21, 웹은 Node 24.19.0 container를 사용합니다. [이미지 digest](../../infra/image-lock.json)를 고정하며, jnlp를 Java 21 빌드 이미지로 바꾸지 않습니다.

Pod securityContext는 UID/GID/fsGroup 1000입니다. 공용 emptyDir HOME과 별도 workspace에서 Maven/npm/XDG cache를 쓸 수 있도록 구성합니다. 캐시는 agent 삭제와 함께 사라집니다. RAM limit 합계는 3,968MiB, HOME emptyDir 상한은 6GiB이며 API와 웹은 순서대로 실행합니다. Maven 기본 heap 512MiB, fork JVM은 container RAM 45%, Node heap은 1GiB입니다.

Maven Wrapper 3.3.4는 공식 bin 방식입니다. 저장소의 wrapper jar와 wrapper/distribution SHA256을 사용해 Java가 Maven ZIP을 내려받고 풉니다. agent에 root 권한이나 별도 unzip 설치가 필요하지 않습니다.

## 작업 등록과 실행 확인

[플랫폼 설치 절차](platform-install.md)에 따라 Jenkins를 설치하고 인증된 관리자 경로에서 접속합니다. 공개 저장소의 main을 읽는 Pipeline from SCM job platform-lab-ci를 사용하고 Script Path는 Jenkinsfile로 지정합니다. 관리자 페이지를 외부에 공개하지 않습니다.

기존 작업이 있으면 job type, SCM URL, branch와 Script Path를 확인하고 일치하지 않을 때 중단합니다. 기존 config를 무조건 덮어쓰지 않습니다. 한 번의 수동 실행마다 queue/build 번호를 기록하고, 응답이 불확실할 때 자동으로 재시도하지 않습니다. 원격 검증은 REST API, 세션 cookie와 crumb를 사용했으며 관리자 Groovy 콘솔은 사용하지 않았습니다.

완료 판정에는 SUCCESS 문자열 외에 아래 항목이 모두 필요합니다.

- Checkout / Verify API / Verify web / Post Actions의 실제 단계 실행
- 동적 agent Pod의 준비 상태와 보안 설정
- API JUnit 결과와 웹 테스트 결과
- jar·dist·ci-build-info archive와 sourceCommit/SCM SHA 일치
- 실제 관측 시각과 공개 가능한 검증 기록

서버가 응답하거나 빌드 결과가 SUCCESS인 것만으로 테스트 실행을 인정하지 않습니다. 초기 Build 1은 플러그인 불일치로 단계 없이 끝났으므로 미실행으로 구분합니다. Build 2는 테스트가 통과했으나 메타데이터가 unknown이었고, Build 3에서 출처 추적까지 확인했습니다.

## Declarative 플러그인 교정

[values](../../infra/platform/jenkins-values.yaml)는 model definition/api/extensions/stage-tags-metadata 네 플러그인을 2.2293.v6e7193cec599로 맞춥니다. 단계 관측을 위해 pipeline-rest-api 2.41도 명시합니다. [검증 기록](../../infra/platform/jenkins-plugins.lock.json)은 공식 메타데이터, 실제 설치 파일 SHA256과 활성 종속성 버전을 보관합니다. 종속성 버전 기록은 관측한 snapshot이며, 모든 전이 종속성을 values에서 강제한 것은 아닙니다.

chart 5.9.68의 apply_config.sh 동작을 확인했습니다. initializeOnce=true이고 initialization-completed가 있으면 플러그인 초기화를 건너뜁니다. 따라서 기존 PVC에 values의 플러그인 버전만 바꿔서는 교정되지 않을 수 있습니다.

실제 수행한 교정 순서는 다음과 같습니다.

1. 진행 중 작업이 없는지 확인하고 Helm values·manifest와 job XML을 root 전용으로 백업합니다.
2. controller를 정지한 뒤 PVC의 Jenkins home 전체를 백업합니다. 백업 대상의 절대 경로, PVC UID와 claimRef를 확인합니다.
3. 기존 Helm values를 유지하면서 필요한 플러그인 pin만 추가합니다. 교정에 한해 initializeOnce=false / overwritePlugins=true를 일회 적용합니다. chart가 plugins 디렉터리를 다시 구성하지만 jobs/PVC를 삭제하지 않습니다.
4. 공식 plugin manager가 종속성을 해결하고 필요한 플러그인이 활성화되는지 확인합니다.
5. initializeOnce=true / overwritePlugins=false로 되돌려 재적용하고 controller Ready, 플러그인 활성, 기존 PVC·자격증명·SCM 정의·작업 이력을 확인합니다.
6. 이전 빌드 journal을 보존한 뒤 새 빌드를 명시적으로 한 번 실행합니다.

현재는 두 보호 값을 원복한 상태입니다. 같은 교정을 무조건 반복하거나 초기화 marker/PVC/jobs를 삭제하지 않습니다. 백업 원문에는 Secret이 포함될 수 있으므로 공개 저장소에 넣지 않습니다.

## 이미지 게시와 GitOps 후속 연결

현재 이미지 게시는 GitHub Actions의 별도 publish-images workflow가 담당합니다. 이 Jenkins 작업이 이미지를 게시하거나 배포했다고 설명하지 않습니다. Jenkins로 게시를 이전하려면 해당 package의 최소 쓰기 권한과 Docker daemon을 쓰지 않는 빌드 방식을 따로 구성·검증합니다. 이미지 게시를 성공으로 대신하는 더미 단계는 추가하지 않습니다.

GitOps 자동화는 기존 저장소의 gitops/environments/home-lab/values.yaml에서 허용된 이미지 digest만 바꾸는 PR 권한을 별도로 구성합니다. 테스트 → source commit → image digest → GitOps 변경 → Argo CD 상태 → 실제 서비스의 순서로 추적합니다. Argo가 관리하는 앱에 Jenkins가 helm upgrade를 동시에 수행하지 않습니다.

untrusted fork PR에는 registry/GitOps 권한이나 관리자 자격증명을 넘기지 않습니다. webhook을 도입할 때는 서명 검증과 제한된 수신 경로를 구성합니다. 데모 API의 Jenkins/Argo/Kubernetes 상태 수집기는 운영 설치와 별도 작업이므로 수집 전에는 NOT_CONFIGURED를 유지합니다.

## 공식 근거와 검증 한계

- [Kubernetes plugin의 yamlFile·template 상속·동일 UID 지침](https://plugins.jenkins.io/kubernetes/)
- [Pipeline 문법과 동시 실행 제한](https://www.jenkins.io/doc/book/pipeline/syntax/)
- [SCM checkout 단계](https://www.jenkins.io/doc/pipeline/steps/workflow-scm-step/)
- [controller executor 0 격리](https://www.jenkins.io/doc/book/security/controller-isolation/)
- [JUnit 수집](https://www.jenkins.io/doc/pipeline/steps/junit/)
- [artifact archive와 fingerprint](https://www.jenkins.io/doc/pipeline/steps/core/)
- [Maven Wrapper bin 방식과 checksum](https://maven.apache.org/tools/wrapper/)
- [Remote API](https://www.jenkins.io/doc/book/using/remote-access-api/) / [CSRF cookie·crumb](https://www.jenkins.io/doc/book/security/csrf-protection/)

로컬 Helm strict lint와 35개 정책 검증, 실제 Jenkins agent 실행은 각각 구분해서 기록합니다. 강제 실패 빌드와 동시 요청 실험은 미검증입니다. 관리자 응답·콘솔 원문·Secret·내부 주소는 공개 근거에서 제외합니다.
