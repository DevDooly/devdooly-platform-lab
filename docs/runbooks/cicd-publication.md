# Jenkins 검증과 Actions 게시 연결

현재 main에서 운영 중인 연결 절차다. 전용 Jenkins status credential을 등록했고, 같은 source SHA의 Jenkins·Actions 성공을 요구하는 Actions 단일 이미지 게시자와 draft GitOps PR 제안을 활성화했다. 정상 B 배포·실제 JUnit 실패의 게시 차단·이전 정상 A digest 복구를 모두 확인했다. [실행 근거](../evidence/cicd-gate/README.md)에 실제 결과와 한계를 구분한다.

[기술 결정](../adr/0004-jenkins-gated-actions-publication.md) · [기존 Jenkins 운영](jenkins-ci.md) · [이미지 게시](image-publication.md) · [GitOps](../../gitops/README.md)

## 전용 credential과 권한

1. GitHub에서 전용 fine-grained PAT를 만든다. Resource owner는 DevDooly, Repository access는 **Only select repositories → devdooly-platform-lab**만 선택한다. Repository permissions는 **Commit statuses: Read and write**, 필수 **Metadata: Read-only**만 사용한다. Contents·Actions·Packages·관리자 권한을 추가하지 않는다. [Fine-grained PAT 안내](https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/managing-your-personal-access-tokens)
2. 인증된 Jenkins 관리 화면에서 **Secret text** credential로 등록한다. ID는 `platform-lab-github-status`로 맞춘다. 토큰 원문은 채팅·Git·스크린샷·console에 넣지 않는다. GitHub repository variable은 `JENKINS_STATUS_ISSUER=DevDooly`로 맞춘다.

권장 첫 만료 기간은 30일이다. 운영 안내에는 원문 대신 credential ID·권한·만료일·담당자만 기록한다. 만료 전에 새 토큰을 생성해 같은 ID의 Secret을 교체하고, 실제 pending·success 전달을 확인한 뒤 이전 토큰을 폐기한다. 만료·전달 실패 시 게시를 차단하는 것이 정상이다. 기존 CLI 로그인 토큰을 복사하는 우회는 사용하지 않는다.

전용 Secret text와 issuer variable은 등록됐고 실제 pending·success·failure 전달을 확인했다. 이 성공만으로 토큰의 만료·회전까지 검증됐다고 표시하지 않는다.

현재 Pipeline은 GitHub App 설치 토큰 자동 발급을 구현하지 않았다. 추후 App을 사용할 경우 설치 저장소 한정·Commit statuses: write·단기 token 갱신을 별도로 구성하고 실제 issuer를 variable에 맞춘다.

## 코드와 문법 재검증

```sh
python3 -m unittest discover -s tests/ci -p 'test_*.py' -v
node --test tests/ci/github-commit-status.test.mjs
```

테스트는 네트워크·실제 토큰·서버를 사용하지 않는다. PR mutation 검증도 가짜 API에서 요청 대상과 draft 조건만 확인한다. Jenkins Declarative linter와 Actions 실제 실행은 별도로 확인한다.

등록 전 준비 검증에서는 Jenkins Declarative linter가 통과했고 Jenkins 성공 기록이 없는 main에서 `JENKINS_STATUS_MISSING`으로 게시를 차단했다. 이후 실제 credential을 등록해 pending·success·failure 전달, 같은 SHA의 Actions 검증, GHCR 게시와 draft GitOps PR, Argo B 배포를 확인했다. 준비 검증과 실제 운영 결과는 [근거 문서](../evidence/cicd-gate/README.md)에서 구분한다.

- Jenkins job은 기존 public repository의 main과 Jenkinsfile을 읽으며 controller executor 0·agent 1·Docker socket 없음·SA token 자동 mount 없음을 유지한다.
- Credentials Binding 기능과 Node container의 status client 실행을 확인한다.
- Jenkinsfile의 credential ID와 등록한 ID가 정확히 같아야 한다.
- 저장소 variable이 없거나 최신 status가 pending/failure이면 게시하지 않는다.
- branch의 Actions 검증은 게시용 main 성공으로 인정하지 않는다.

## 운영 연결을 재검증하는 순서

1. 전용 credential·issuer variable을 먼저 준비하고 상태 전달 권한을 확인한다. 기존 token의 원문을 출력하지 않는다.
2. 변경한 코드·단위 검증·Jenkins 문법을 검토하고 main에 반영한다. 같은 main SHA에서 Jenkins를 한 번 실행한다. 현재 pollSCM이 main 변경을 확인하며, 수동 실행과 자동 감지를 중복 요청하지 않는다.
3. 같은 main SHA의 Validate Lab containers를 실행한다. 관련 소스 변경은 자동 실행하며, 문서·GitOps-only commit은 경로 필터 때문에 필요할 때 수동 실행한다.
4. Jenkins pending → API·웹 테스트 → 필수 산출물 archive → success를 실제로 확인한다. JUnit만으로 웹 테스트 수치를 대신하지 않는다.
5. Actions의 gate 출력이 Jenkins build/status와 같은 소스 SHA·validation run을 가리키는지 확인한다.
6. 실제 GHCR digest와 게시 artifact를 확인한다. 반복 status/workflow_run 이벤트에서 기존 artifact를 확인해 중복 게시를 종료하는지도 확인한다.

main이 검증 중 바뀌면 이전 SHA는 게시하지 않는다. 새 main에서 필요한 두 검증을 다시 실행한다. 기존 성공을 새 source SHA의 성공으로 옮기지 않는다. 공개 GitHub metadata 조회의 일시적 제한·실패도 게시 성공으로 대체하지 않는다.

### 실제 확인한 중복 빌드와 재시도

실패 변경을 원복한 source SHA에서 Jenkins와 Actions 검증이 다시 성공했다. 이때 수동 실행과 pollSCM 감지가 겹쳐 같은 SHA의 Jenkins 빌드가 순차적으로 두 번 실행됐다. `disableConcurrentBuilds()`는 동시 실행을 제한하며 같은 SHA의 중복 빌드 생성까지 방지하지 않는다.

두 번째 빌드의 pending은 첫 번째 빌드의 success보다 최신 상태였다. Actions가 registry 인증 직전 gate를 다시 확인해 게시를 차단했으므로 이전 성공으로 fallback하지 않는 동작을 실제로 확인했다. 이후 최신 success 이벤트의 게시·draft 제안은 성공했다. 이 추가 제안은 이번 훈련에서 적용하지 않고 닫았으며 최종 실행 상태는 복구한 A다. 이 결과를 중복 SCM 감지가 방지됐다고 설명하지 않는다.

별도 게시 시도는 공개 GitHub metadata 조회의 HTTP 403으로 실패했다. 이 실행도 성공이나 배포 완료로 기록하지 않는다. 조회 실패 원인을 권한 확대나 오래된 결과 사용으로 우회하지 않고, 현재 main과 최신 두 CI 결과를 다시 확인한 새 이벤트·명시 재시도 결과를 따른다.

## 활성화된 draft GitOps PR 제안

현재 `LAB_GITOPS_PR_ENABLED=true`다. 사용자 승인으로 GitHub의 Actions PR 생성·승인 허용 설정을 켰으며 저장소 기본 workflow 권한은 read를 유지한다. proposer job에만 contents: write·pull-requests: write를 부여한다. 실제 draft PR 생성과 검토 후 main 반영을 확인했다. 워크플로는 자동 승인·자동 병합을 수행하지 않는다.

이후 새 source SHA를 두 CI에서 검증해 새 이미지를 게시해야 PR 생성까지 이어진다. 이미 성공한 게시 artifact가 있는 SHA에 새 workflow를 실행하면 중복 게시 방지가 publish와 proposal을 모두 건너뛴다. 기존 실행의 proposal job만 실패했다면 해당 job 재실행 경로를 사용한다. 별도 새 workflow에서 과거 artifact를 읽어 proposal만 복구하는 기능은 아직 없다.

- proposer는 단기 Actions GITHUB_TOKEN을 사용한다. Jenkins에 PR 쓰기 권한을 주지 않는다.
- 두 digest와 sourceCommit만 전용 `automation/lab-images/<전체 SHA>` branch에 반영해 draft PR을 만든다.
- 기존 열린 PR은 같은 저장소·branch의 draft이고 auto_merge가 null일 때만 재사용한다. ready PR은 자동으로 수정하지 않는다.
- 알 수 없는 mutation 결과는 즉시 반복 요청하지 않는다. 다음 명시 실행이 기존 branch/PR을 읽고 재사용한다.
- GITHUB_TOKEN이 만든 PR의 check가 실행되지 않거나 승인이 요구되면 실제 check 상태를 확인하고 필요한 검증을 명시적으로 실행한다. PR 생성 허용 설정이 모든 check의 자동 실행·자동 승인을 보장하지는 않는다.
- PR check는 **변경 범위**를 검사한다. 병합 전 두 registry digest의 실제 존재·OCI revision, Helm lint/render를 별도로 확인한다. 이 보완과 실제 PR 검증이 끝나기 전 자동 병합을 도입하지 않는다.

단독 값 준비/검증은 다음처럼 실행할 수 있다. 먼저 `.local` 디렉터리를 생성하고, 실제 digest와 SHA만 입력한다.

```sh
python3 infra/scripts/gitops_values.py prepare \
  --before gitops/environments/home-lab/values.yaml \
  --source-commit <검증한-40자리-SHA> \
  --api-digest sha256:<API-64자리-digest> \
  --web-digest sha256:<웹-64자리-digest> \
  --output .local/proposed-values.yaml

python3 infra/scripts/gitops_values.py validate \
  --before gitops/environments/home-lab/values.yaml \
  --after .local/proposed-values.yaml
```

이 작은 파일의 parser는 명시한 중첩 구조와 단순 값만 지원한다. YAML alias·tag·flow mapping·중복 key·예상 밖 값은 거부한다. chart 설정 확장이 필요하면 validator와 검증 범위를 먼저 수정한다.

## 실제 결과와 재검증 조건

### 정상 흐름

같은 source SHA의 Jenkins API 15개·웹 13개 테스트와 필수 산출물, Actions 통합 검증, GHCR digest, draft GitOps PR과 main 반영, Argo B의 Synced·Healthy를 실제로 연결했다. Pod spec과 OCI index의 linux/amd64 child·CRI config 관계, source revision label, 웹 경유 HTTP와 기존 DB 결과도 확인했다. 공개 기록에는 허용한 요약만 넣는다. 재검증에도 동일한 출처 연결이 필요하다.

### 테스트 실패 차단

main에서 독립 기대 성공 건수를 8로 바꾼 실제 JUnit 음성 실험을 실행했다. API 테스트 15개 중 1개가 기대 8·실제 7로 실패했고 해당 SHA에 Jenkins failure가 전달됐으며 Actions 통합 검증도 실패했다. 해당 SHA의 새 이미지·게시 artifact·GitOps PR이 생성되지 않았다. 실패 전후 정확한 main commit의 values Git blob과 모든 bytes, Deployment UID·generation·template hash, Pod UID·시작 시각·container ID·imageID·restart count가 같았다. 전체 SQL·Flyway·처리 시각·PVC/PV·DB mount와 기존 Docker도 유지됐다. Argo revision은 실패 commit으로 진행할 수 있지만 B의 선언·실행 이미지는 변하지 않았다. 실패 실험 변경은 원복했다.

이 결과는 실제 main의 실패 차단이며, branch가 달라서 차단된 준비 검증과 구분한다. 다음 실패 실험도 동일한 범위와 원복 절차를 먼저 정하고 운영 DB·이미지는 수정하지 않는다.

### 이전 digest 복구

정상 A → 새 B 배포 후 GitOps PR로 API/Web pin과 sourceCommit을 A로 되돌렸다. 복구 PR의 값 변경 범위, 실제 A registry의 OCI 관계와 Helm strict lint/render를 확인한 뒤 main에 반영했다. Argo Synced·Healthy, 3개 Pod Ready, A image/config·원본 source 일치를 확인했다. A와 B에서 확보한 동일 기준의 전체 SQL·Flyway·run/event 시각·PVC/PV binding·mount와 기존 Docker 23개의 ID·mount·시작 시각, UFW·호스트 boot ID도 유지됐다. API·웹은 Recreate이며 이 검증이 무중단 배포를 증명하지는 않는다. 자동 동기화와 별도의 Argo rollback/helm upgrade를 혼용하지 않았다. [Argo CD 자동 동기화 제약](https://argo-cd.readthedocs.io/en/stable/user-guide/auto_sync/)

Pod spec의 @digest는 선언 값과 비교한다. status.imageID가 OCI index와 다르면 linux/amd64 child manifest 관계를 확인한다. API 런타임의 env 기반 SHA/digest만으로 실행 이미지 일치를 주장하지 않는다. 실제 HTTP·성공 7/실패 3/중복 2/대기 0·기존 처리 시각·DB PVC 보존과 기존 서비스 응답을 함께 확인한다.

정상 B 배포·실제 실패 차단·이전 정상 A digest 복구의 세 시나리오를 실제로 확인했다. 게시 결과·자동 draft 제안과 main 반영·실제 배포는 서로 구분하며 최종 실행 버전은 A다. 초기 비밀번호 교체, token 만료·실제 회전, 동시 요청 실험, K3s·Jenkins archive 전체 복원, 3단계 실시간 collector와 외부 API는 별도의 미완료 범위다.
