# Jenkins CI 정의

[Jenkinsfile](../../Jenkinsfile)은 Kubernetes plugin의 `yamlFile`로 [agent-pod.yaml](agent-pod.yaml)을 사용합니다. 현재 연결·검증 범위는 [운영 절차](../../docs/runbooks/jenkins-ci.md)를 따릅니다.

실제 [agent 실행](../../docs/evidence/jenkins-ci/README.md), [정상 배포·실패 차단·이전 이미지 복귀](../../docs/evidence/cicd-gate/README.md), [2026-10-23 GitHub App 연결](../../docs/evidence/github-app-jenkins/README.md)을 각각 기록했습니다. 로컬 검증을 Jenkins 결과로 대체하거나 이 기록을 새 환경 전체 기동 복원 성공으로 해석하지 않습니다. [대표 사례 페이지](https://devdooly.github.io/devdooly-platform-lab/cases/cicd-delivery/)에서 역할·설정·이식 방법을 함께 읽을 수 있습니다.

chart의 `default` Pod template과 `jenkins-build-agent` ServiceAccount를 전제로 합니다. controller executor 수와 cloud 전체 agent 수는 `infra/platform/`의 chart 설정에서 각각 0과 1로 맞춥니다. `disableConcurrentBuilds()`는 이 job의 중복 실행을 순서대로 대기시킵니다.

JDK 25의 jnlp는 controller 연결과 checkout을 맡고 Java 21 container가 API를 빌드합니다. Node 24 container는 화면을 검증합니다. 작업 공간은 Kubernetes plugin의 workspace volume, HOME·도구 캐시는 별도 `emptyDir`를 공유합니다. 모든 container의 UID/GID는 1000이고 fsGroup도 1000입니다. Docker socket, hostPath, privileged container, registry write credential을 사용하지 않습니다.

빌드 이미지 digest는 [image-lock.json](../image-lock.json)과 일치합니다. jnlp 이미지는 chart `default` template의 버전을 상속하므로 chart 갱신 시 controller와 agent의 Java 호환성을 함께 확인합니다.
