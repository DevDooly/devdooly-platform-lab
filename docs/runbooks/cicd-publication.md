# Jenkins 검증과 Actions 게시 연결

현재 문서는 전용 credential 등록 전의 구현 초안이다. 초기 적용은 `cicd/jenkins-publication-gate` branch의 draft PR로 준비하며, 준비되지 않은 gate를 main에 반영해 기존 게시 경로를 중단시키지 않는다.

[기술 결정](../adr/0004-jenkins-gated-actions-publication.md) · [기존 Jenkins 운영](jenkins-ci.md) · [이미지 게시](image-publication.md) · [GitOps](../../gitops/README.md)

## 먼저 준비할 두 항목

1. GitHub에서 전용 fine-grained PAT를 만든다. Resource owner는 DevDooly, Repository access는 **Only select repositories → devdooly-platform-lab**만 선택한다. Repository permissions는 **Commit statuses: Read and write**, 필수 **Metadata: Read-only**만 사용한다. Contents·Actions·Packages·관리자 권한을 추가하지 않는다. [Fine-grained PAT 안내](https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/managing-your-personal-access-tokens)
2. 인증된 Jenkins 관리 화면에서 **Secret text** credential로 등록한다. ID는 `platform-lab-github-status`로 맞춘다. 토큰 원문은 채팅·Git·스크린샷·console에 넣지 않는다. GitHub repository variable은 `JENKINS_STATUS_ISSUER=DevDooly`로 맞춘다.

권장 첫 만료 기간은 30일이다. 운영 안내에는 원문 대신 credential ID·권한·만료일·담당자만 기록한다. 만료 전에 새 토큰을 생성해 같은 ID의 Secret을 교체하고, 실제 pending·success 전달을 확인한 뒤 이전 토큰을 폐기한다. 만료·전달 실패 시 게시를 차단하는 것이 정상이다. 기존 CLI 로그인 토큰을 복사하는 우회는 사용하지 않는다.

현재 Pipeline은 GitHub App 설치 토큰 자동 발급을 구현하지 않았다. 추후 App을 사용할 경우 설치 저장소 한정·Commit statuses: write·단기 token 갱신을 별도로 구성하고 실제 issuer를 variable에 맞춘다.

## 초안에서 확인할 것

```sh
python3 -m unittest discover -s tests/ci -p 'test_*.py' -v
node --test tests/ci/github-commit-status.test.mjs
```

테스트는 네트워크·실제 토큰·서버를 사용하지 않는다. PR mutation 검증도 가짜 API에서 요청 대상과 draft 조건만 확인한다. Jenkins Declarative linter와 Actions 실제 실행은 별도로 확인한다.

2026-10-11 준비 검증에서는 Jenkins Declarative linter가 통과했다. 공개 GitHub API로 main `a8e80b7d6f500a98d29615f3dcbc10a51cc340b0`와 성공한 Validate Lab containers run `38145100877`을 확인한 gate는 `JENKINS_STATUS_MISSING`으로 게시를 차단했다. 이 확인에서는 이미지·클러스터를 변경하지 않았다. 전용 credential을 사용한 실제 pending·success 전달과 게시 성공을 증명하는 결과는 아니다.

- Jenkins job은 기존 public repository의 main과 Jenkinsfile을 읽으며 controller executor 0·agent 1·Docker socket 없음·SA token 자동 mount 없음을 유지한다.
- Credentials Binding 기능과 Node container의 status client 실행을 확인한다.
- Jenkinsfile의 credential ID와 등록한 ID가 정확히 같아야 한다.
- 저장소 variable이 없거나 최신 status가 pending/failure이면 게시하지 않는다.
- branch의 Actions 검증은 게시용 main 성공으로 인정하지 않는다.

## 활성화 순서

1. 전용 credential·issuer variable을 먼저 준비하고 상태 전달 권한을 확인한다. 기존 token의 원문을 출력하지 않는다.
2. draft PR의 코드·단위 검증·Jenkins 문법을 확인한 뒤 main에 반영한다. 새 main SHA에서 Jenkins를 한 번 실행한다. 이후 pollSCM이 main 변경을 확인한다.
3. 같은 main SHA의 Validate Lab containers를 실행한다. 관련 소스 변경은 자동 실행하며, 문서·GitOps-only commit은 경로 필터 때문에 필요할 때 수동 실행한다.
4. Jenkins pending → API·웹 테스트 → 필수 산출물 archive → success를 실제로 확인한다. JUnit만으로 웹 테스트 수치를 대신하지 않는다.
5. Actions의 gate 출력이 Jenkins build/status와 같은 소스 SHA·validation run을 가리키는지 확인한다.
6. 실제 GHCR digest와 게시 artifact를 확인한다. 반복 status/workflow_run 이벤트에서 기존 artifact를 확인해 중복 게시를 종료하는지도 확인한다.

main이 검증 중 바뀌면 이전 SHA는 게시하지 않는다. 새 main에서 필요한 두 검증을 다시 실행한다. 기존 성공을 새 source SHA의 성공으로 옮기지 않는다. 공개 GitHub metadata 조회의 일시적 제한·실패도 게시 성공으로 대체하지 않는다.

## GitOps PR 선택적 활성화

`LAB_GITOPS_PR_ENABLED`는 미등록/false 상태를 기본으로 유지한다. 이미지 게시와 상태 전달을 확인한 뒤 GitHub의 Actions PR 생성 허용 설정·선택한 권한을 확인하고 true로 바꾼다.

이후 새 source SHA를 두 CI에서 검증해 새 이미지를 게시해야 PR 생성까지 이어진다. 이미 성공한 게시 artifact가 있는 SHA에 새 workflow를 실행하면 중복 게시 방지가 publish와 proposal을 모두 건너뛴다. 기존 실행의 proposal job만 실패했다면 해당 job 재실행 경로를 사용한다. 별도 새 workflow에서 과거 artifact를 읽어 proposal만 복구하는 기능은 아직 없다.

- proposer는 단기 Actions GITHUB_TOKEN을 사용한다. Jenkins에 PR 쓰기 권한을 주지 않는다.
- 두 digest와 sourceCommit만 전용 `automation/lab-images/<전체 SHA>` branch에 반영해 draft PR을 만든다.
- 기존 열린 PR은 같은 저장소·branch의 draft이고 auto_merge가 null일 때만 재사용한다. ready PR은 자동으로 수정하지 않는다.
- 알 수 없는 mutation 결과는 즉시 반복 요청하지 않는다. 다음 명시 실행이 기존 branch/PR을 읽고 재사용한다.
- GITHUB_TOKEN이 만든 PR의 workflow에 승인이 요구되면 GitHub에서 승인한다. 자동 승인을 완료했다고 가정하지 않는다.
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

## 완료 판정에 필요한 실제 결과

### 정상 흐름

같은 소스 SHA의 Jenkins 단계·JUnit·웹 테스트·산출물, Actions validation, registry digest, GitOps PR/commit, Argo Synced·Healthy, Pod spec·imageID, 동일 origin HTTP와 기존 DB 결과를 연결한다. 공개 기록에는 허용한 요약만 넣는다.

### 테스트 실패 차단

독립적인 기대 결과를 위반하는 실제 JUnit 변경으로 Jenkins 실패를 재현한다. 실패 단계와 JUnit failure, success status 미발행, 해당 SHA의 새 게시 artifact·GitOps PR·배포 변경 없음이 확인돼야 한다. 다른 branch라서 차단된 결과만으로 테스트 실패 gate를 증명하지 않는다. branch의 음성 검증은 게시 side effect 없이 수행하고, 실제 main 경로 검증 방법과 원복은 따로 정한다.

### 이전 digest 복구

정상 버전 A → 새 버전 B → GitOps 값을 A로 되돌리는 PR을 순서대로 적용한다. API·웹은 Recreate이므로 Lab의 짧은 중단 시간을 기록한다. 자동 동기화와 별도의 Argo rollback/helm upgrade를 혼용하지 않는다. [Argo CD 자동 동기화 제약](https://argo-cd.readthedocs.io/en/stable/user-guide/auto_sync/)

Pod spec의 @digest는 선언 값과 비교한다. status.imageID가 OCI index와 다르면 linux/amd64 child manifest 관계를 확인한다. API 런타임의 env 기반 SHA/digest만으로 실행 이미지 일치를 주장하지 않는다. 실제 HTTP·성공 7/실패 3/중복 2/대기 0·기존 처리 시각·DB PVC 보존과 기존 서비스 응답을 함께 확인한다.

현재 초안의 로컬 테스트 통과는 위 세 실제 운영 시나리오의 완료가 아니다. 전용 credential 등록 전에는 단계 2 완료로 표시하지 않는다.
