# Jenkins CI 실제 검증

2026-10-11 Ubuntu 미니 PC의 K3s에서 Jenkins를 실행하고, 동적 Kubernetes agent로 API와 웹을 빌드했습니다. **Build 3에서 API 15개·웹 13개 테스트, JUnit 수집, 산출물 9개와 소스 커밋 추적을 확인했습니다.**

- 검증 작업: `platform-lab-ci`, Build **3**, `SUCCESS`
- 소스: [`30b348c370050063a3f87c9bd00e7d2996102fbf`](https://github.com/DevDooly/devdooly-platform-lab/commit/30b348c370050063a3f87c9bd00e7d2996102fbf)
- 원본: [허용 필드만 추린 검증 결과](summary.json)
- 관측 시각: `2026-10-11T11:57:20.570559Z` (UTC)

| 확인 항목 | 실제 결과 |
| --- | --- |
| 실행 단계 | Checkout, Verify API, Verify web, Post Actions 모두 SUCCESS |
| API | Maven Wrapper verify, JUnit 15 통과 / 실패 0 / skip 0 |
| 웹 | npm ci → check → test → build, Node 테스트 13 통과 / 실패·skip·cancel 0 |
| 산출물 | API jar, 웹 dist, ci-build-info.txt 총 9개 archive |
| 소스 추적 | ci-build-info.txt의 sourceCommit이 Jenkins SCM SHA와 일치 |
| agent | 실제 Running Pod의 jnlp/maven/node 3개 container Ready 관측 |
| 권한 | Pod securityContext UID/GID/fsGroup 1000, 전용 SA, token 자동 mount 없음, Docker socket 없음 |
| controller | built-in executor 0 |

API 테스트만 Jenkins JUnit 보고서로 수집합니다. 웹 테스트 수치는 Node 테스트 출력에서 별도로 확인했습니다. JUnit 28개로 합산하지 않습니다. agent 관측은 일회 실행의 해당 시점 기록이며 지속 모니터링 결과가 아닙니다.

## 첫 실행과 교정 이력

**Build 1은 CI 성공으로 인정하지 않습니다.** Jenkins 결과는 SUCCESS였지만 단계·agent·JUnit·산출물이 없었습니다. 확인한 Jenkinsfile은 저장소 원본과 일치했습니다. controller 로그에서 Declarative model 플러그인의 버전 불일치로 model extensions/definition과 aggregator가 로드되지 않은 것을 확인했습니다. 원인은 model-api/definition `2.2218.v56d0cda_37c72`와 extensions `2.2277.v00573e73ddf1`의 조합이었습니다.

model definition/api/extensions/stage-tags-metadata 네 플러그인을 공식 `2.2293.v6e7193cec599`로 맞추고, 단계 관측용 pipeline-rest-api `2.41`을 명시했습니다. 공식 plugin manager가 필요한 종속성을 해결했고, 실제 플러그인 활성화와 5개 파일의 공식 SHA1 일치를 확인했습니다. [공식 메타데이터·실제 SHA256·종속성 관측](../../../infra/platform/jenkins-plugins.lock.json)을 함께 보관합니다.

**Build 2는 테스트가 통과했지만 산출물의 출처 기록이 부족했습니다.** API 15개와 웹 13개가 통과했고 산출물도 9개였으나, `env.GIT_COMMIT`이 없어 ci-build-info.txt가 `unknown`을 기록했습니다. 실제 SCM SHA는 `820d5c398af2b1d62a0566f9184d015ab22e9f15`였습니다. Build 3은 checkout 반환 Map의 GIT_COMMIT을 40자리 hex로 검증해 기록하도록 수정한 뒤 다시 실행했습니다.

## 데이터 보존과 확인 범위

변경 전 Helm 설정·manifest·job XML과 정지한 Jenkins home 전체를 root 전용으로 백업했습니다. PVC, 관리자 자격증명, SCM 정의, Build 1~3 이력을 유지했습니다. job XML에는 실제 Jenkinsfile 실행에 따른 BuildDiscarderProperty가 추가됐습니다. 플러그인 교정에만 initializeOnce=false / overwritePlugins=true를 사용했고, 성공 후 **initializeOnce=true / overwritePlugins=false**로 원복했습니다.

강제 실패 테스트와 동시 실행 요청 실험은 아직 하지 않았습니다. Jenkins 작업은 이미지 게시·배포를 수행하지 않습니다. 이미지 게시는 GitHub Actions의 별도 workflow이며, Argo CD 배포 결과는 별도 근거로 확인합니다. 데모 API의 Jenkins 상태 수집기는 아직 연결되지 않았습니다.

관리자 응답 원문, 콘솔 원문, 내부 주소, 자격증명, Kubernetes Secret, 백업의 실제 경로는 이 공개 기록에 포함하지 않습니다.
