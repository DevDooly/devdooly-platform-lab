# Jenkins CI 운영과 재검증

미니 PC의 K3s에서 API JUnit 15개와 웹 Node 테스트 13개, 필수 산출물과 SCM 커밋의 일치를 확인했습니다. 현재 전용 credential로 같은 source SHA의 pending·success·failure를 전달하고 Actions 이미지 게시 gate에 연결합니다. 정상 B 배포와 실제 main의 JUnit 실패 차단도 검증했습니다. [agent 실행 근거](../evidence/jenkins-ci/README.md)와 [연결 검증](../evidence/cicd-gate/README.md)을 함께 확인합니다.

## GitHub App 연결 확인 — 2026-10-23 UTC

Jenkins 2.580.1에 `github-branch-source:1986.v801e40614d00`과 필요한 의존성을 선택 설치했습니다. 기존 77개 집합에서 6개 추가·2개 상향으로 총 83개가 되었고, 전체 집합의 core·필수 의존성·존재하는 optional 의존성 최소 버전과 재기동 후 활성 상태를 확인했습니다. 기존 PVC, job 구성, build 150 기록과 PATv2 credential을 보존했습니다. 이전 교정 절차의 전체 플러그인 재구성을 반복한 결과와 구분합니다.

새 credential ID는 `platform-lab-github-app`이며 기존 `platform-lab-github-status`와 별개입니다. App 설치 대상은 개인 Lab 저장소 한 개로 제한하고 Commit statuses 읽기·쓰기와 필수 Metadata 읽기 범위를 사용합니다. 공개 SCM clone 방식은 유지합니다. 개인키는 Jenkins credential에 암호화 저장하며, 평문 PEM과 토큰은 전달·검증 과정의 메모리에서만 취급합니다. 원문·비밀 지문·관리 응답은 공개 근거에 넣지 않습니다.

고정 credential의 native `getPassword()` 경로와 GitHub의 installation repositories GET 한 번으로 선택한 저장소 한 개의 일치를 확인했습니다. 이는 새 토큰의 매번 발급, 실제 만료·자동 갱신, installation ID의 독립 검증이나 commit status 쓰기를 증명하지 않습니다. 기존 PATv2는 삭제하거나 덮어쓰지 않았습니다.

[Jenkinsfile](../../Jenkinsfile)의 pending·success·unsuccessful 세 바인딩은 `usernamePassword`를 사용하고, password만 기존 `GITHUB_STATUS_TOKEN` 환경 변수로 status client에 전달하도록 준비했습니다. 새 자격을 바인딩한 **새 CI build의 완료 증거는 아직 확인 전**입니다. 이후 실제 checkout SHA·새 queue/build 번호·검증 단계·필수 artifact를 연결하고, 같은 SHA와 build 번호의 pending artifact·success status ID·실제 issuer를 대조해야 합니다. 과거 PAT 기반 build 150의 성공을 App 기반 CI 성공으로 대신하지 않습니다.

이미지 게시 gate의 예상 issuer는 실제 새 status 작성자를 확인한 뒤 정확한 값으로 연결합니다. 공개 관측 수집기·DTO·브라우저의 issuer 계약도 같은 실측 작성자와 맞춰야 하며, issuer 검사를 없애거나 새 상태를 건너뛰고 과거 성공을 선택하지 않습니다. 저장소 변수 변경·이미지 게시·GitOps 반영은 이 App 조회 확인과 별도 단계입니다.

## 실행하는 작업

1. main의 Jenkinsfile을 읽고 checkout 반환값에서 40자리 source commit을 검증해 ci-build-info.txt에 build 번호와 함께 기록합니다. SHA가 없으면 빌드를 실패시킵니다.
2. 전용 commit-status credential을 필요한 단계에만 바인딩해 checkout한 정확한 SHA에 `ci/jenkins-test` pending을 전달합니다. main 이외의 branch는 이 credentialed job에서 허용하지 않습니다.
3. Java 21 container에서 apps/api의 Maven Wrapper verify를 실행합니다. Surefire XML을 성공·실패와 관계없이 JUnit 결과로 수집하며, 빈 결과를 허용하지 않습니다.
4. Node 24 container에서 npm ci, npm run check, npm test, npm run build와 status client의 음성 테스트를 실행합니다.
5. 모든 단계가 성공한 경우 API jar, 웹 dist, ci-build-info.txt와 pending 전달 기록을 필수 산출물로 확인하고 archive·fingerprint를 기록합니다.
6. 필수 산출물 보관까지 성공한 뒤 같은 SHA에 success를 전달합니다. 실패는 failure, 중단은 error로 전달하며 전달 오류를 성공으로 대신하지 않습니다.

JUnit 보고서는 API 테스트만 포함합니다. 웹 테스트 수치는 Node 테스트 출력에서 별도로 확인합니다. Jenkins는 registry 게시, GitOps PR, Helm 배포를 실행하지 않습니다.

## Kubernetes agent와 권한

controller의 built-in executor는 0입니다. Kubernetes cloud 전체와 default template의 agent 상한은 1이며, job에도 disableConcurrentBuilds()가 적용됩니다. 동시 요청을 실제로 보내는 실험은 아직 하지 않았습니다.

수동 실행과 pollSCM 감지가 겹쳐 같은 SHA의 빌드가 순차적으로 두 번 실행되는 경우는 실제로 관측했습니다. 위 설정은 동시 실행 상한이며 중복 빌드 자체의 제거를 보장하지 않습니다. 최신 빌드의 pending이 이전 success를 대체하면 Actions의 게시 직전 확인이 차단하고, 최신 success가 전달된 뒤 다시 검증합니다.

[Pod 정의](../../infra/jenkins/agent-pod.yaml)는 chart의 default template을 merge 방식으로 상속합니다. controller SA만 namespace 안에서 agent Pod를 관리하고, build에는 권한 없는 jenkins-build-agent SA를 사용합니다. 실제 Pod에서 token 자동 mount가 꺼져 있고 Docker socket이 없음을 관측했습니다.

jnlp는 chart 기본 JDK 25 연결용 agent를 상속합니다. API 빌드는 별도 Temurin Java 21, 웹은 Node 24.19.0 container를 사용합니다. [이미지 digest](../../infra/image-lock.json)를 고정하며, jnlp를 Java 21 빌드 이미지로 바꾸지 않습니다.

Pod securityContext는 UID/GID/fsGroup 1000입니다. 공용 emptyDir HOME과 별도 workspace에서 Maven/npm/XDG cache를 쓸 수 있도록 구성합니다. 캐시는 agent 삭제와 함께 사라집니다. RAM limit 합계는 3,968MiB, HOME emptyDir 상한은 6GiB이며 API와 웹은 순서대로 실행합니다. Maven 기본 heap 512MiB, fork JVM은 container RAM 45%, Node heap은 1GiB입니다.

Maven Wrapper 3.3.4는 공식 bin 방식입니다. 저장소의 wrapper jar와 wrapper/distribution SHA256을 사용해 Java가 Maven ZIP을 내려받고 풉니다. agent에 root 권한이나 별도 unzip 설치가 필요하지 않습니다.

## 작업 등록과 실행 확인

[플랫폼 설치 절차](platform-install.md)에 따라 Jenkins를 설치하고 인증된 관리자 경로에서 접속합니다. 공개 저장소의 main을 읽는 Pipeline from SCM job platform-lab-ci를 사용하고 Script Path는 Jenkinsfile로 지정합니다. 관리자 페이지를 외부에 공개하지 않습니다.

기존 작업이 있으면 job type, SCM URL, branch와 Script Path를 확인하고 일치하지 않을 때 중단합니다. 기존 config를 무조건 덮어쓰지 않습니다. 한 번의 수동 실행마다 queue/build 번호를 기록하고, 응답이 불확실할 때 자동으로 재시도하지 않습니다. 초기 작업 등록·실행 검증은 REST API, 세션 cookie와 crumb를 사용했으며 관리자 Groovy 콘솔은 사용하지 않았습니다. 위 App 등록·인증 확인은 고정된 관리자 스크립트를 사용한 별도 후속입니다.

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

## Actions 게시와 GitOps 연결

GitHub Actions의 publish-images workflow가 유일한 이미지 게시자입니다. 현재 main의 같은 SHA에서 Actions 통합 검증과 Jenkins의 최신 success·예상 issuer·산출물 확인 메타데이터를 모두 요구합니다. Jenkins 전용 credential은 선택한 저장소의 Commit statuses 쓰기와 필수 Metadata 읽기 범위로 준비하며 registry·PR 쓰기 권한을 추가하지 않습니다. [ADR 0004](../adr/0004-jenkins-gated-actions-publication.md)와 [연결 절차](cicd-publication.md)를 따릅니다.

사용자 승인으로 Actions PR 설정과 draft GitOps PR 제안을 활성화했습니다. Actions의 단기 token이 허용된 API/Web digest와 sourceCommit만 변경하고, 검토 후 main에 반영하면 Argo가 배포합니다. 자동 승인·자동 병합은 하지 않습니다. 테스트 → source commit → image digest → GitOps commit → Argo → 실제 서비스의 순서로 확인했으며 Jenkins가 helm upgrade를 중복 실행하지 않습니다.

실제 main의 음성 실험에서 API 테스트 15개 중 1개가 기대 8·실제 7로 실패했습니다. 해당 SHA의 failure status와 Actions 검증 실패, 새 이미지·게시 artifact·PR 없음, 기존 B의 Deployment/Pod·전체 SQL·시각·PVC와 기존 Docker 보존을 확인했습니다. 이후 실패 변경의 두 CI 검증을 다시 통과했고 GitOps PR로 이전 정상 A를 복구해 Argo Synced·Healthy·3개 Pod Ready와 데이터·기존 서비스 보존까지 확인했습니다. 추가 이미지 게시·draft 제안은 성공했으나 적용하지 않고 닫아 최종 A 배포를 유지했습니다.

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

로컬 Helm strict lint와 35개 정책 검증, 실제 Jenkins agent 실행, 실제 실패 차단은 각각 구분해 기록합니다. 동시 요청 실험과 GitHub App 설치 토큰의 실제 만료·자동 갱신은 미검증입니다. 관리자 응답·콘솔 원문·Secret·내부 주소는 공개 근거에서 제외합니다.
