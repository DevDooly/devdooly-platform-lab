# Jenkins CI 정의

[Jenkinsfile](../../Jenkinsfile)은 Kubernetes plugin의 `yamlFile`로 [agent-pod.yaml](agent-pod.yaml)을 사용합니다. 실제 서버와 Jenkins 설치 이후 [운영 절차](../../docs/runbooks/jenkins-ci.md)에 따라 첫 실행을 검증합니다.

현재 저장소에는 CI 정의가 있으며 Jenkins 빌드 이력은 아직 없습니다. API와 화면의 실제 로컬 검증 결과를 Jenkins 실행 결과로 바꾸어 표시하지 않습니다.

chart의 `default` Pod template과 `jenkins-build-agent` ServiceAccount를 전제로 합니다. controller executor 수와 cloud 전체 agent 수는 `infra/platform/`의 chart 설정에서 각각 0과 1로 맞춥니다. `disableConcurrentBuilds()`는 이 job의 중복 실행을 순서대로 대기시킵니다.

JDK 25의 jnlp는 controller 연결과 checkout을 맡고 Java 21 container가 API를 빌드합니다. Node 24 container는 화면을 검증합니다. 작업 공간은 Kubernetes plugin의 workspace volume, HOME·도구 캐시는 별도 `emptyDir`를 공유합니다. 모든 container의 UID/GID는 1000이고 fsGroup도 1000입니다. Docker socket, hostPath, privileged container, registry write credential을 사용하지 않습니다.

빌드 이미지 digest는 [image-lock.json](../image-lock.json)과 일치합니다. jnlp 이미지는 chart `default` template의 버전을 상속하므로 chart 갱신 시 controller와 agent의 Java 호환성을 함께 확인합니다.
