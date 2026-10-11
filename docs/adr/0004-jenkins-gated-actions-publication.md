# 0004 Jenkins 검증을 gate로 연결하고 Actions를 유일한 이미지 게시자로 유지

상태: 채택·운영 활성화. 전용 status credential, 같은 SHA의 Jenkins·Actions gate, 단일 Actions 게시자와 draft GitOps PR 제안을 활성화했다. 정상 B 배포·실제 JUnit 실패 차단·GitOps의 이전 정상 A digest 복구를 모두 검증했다.

## 배경

Jenkins는 Kubernetes agent에서 API·웹 테스트와 패키징을 실행한다. Actions는 Linux MariaDB·Compose 검증 후 GHCR 이미지를 게시하고, Argo CD는 GitOps의 digest를 배포한다. 기존 두 CI 경로는 독립적이어서 Jenkins 실패가 Actions의 게시를 막지 못했다. 이를 같은 source SHA의 게시 조건으로 연결했다.

Jenkins로 registry 게시까지 옮기면 별도 이미지 빌더와 장기 게시 자격 증명이 필요하다. GHCR 공식 문서는 외부 인증에 PAT classic을 안내하며, Actions 안에서는 단기 GITHUB_TOKEN을 사용하도록 권장한다. 개인 서버에 넓은 registry 권한을 추가할 이유가 작다. [GHCR 인증과 권한](https://docs.github.com/en/packages/working-with-a-github-packages-registry/working-with-the-container-registry)

## 결정

Actions를 유일한 이미지 게시자로 유지하고 같은 source SHA의 Jenkins·Actions 실제 검증을 모두 요구한다.

```text
Jenkins main 테스트·필수 산출물 → ci/jenkins-test status
Actions main MariaDB·Compose 검증 → workflow run
                         ↓ 같은 SHA·현재 main·예상 issuer
                  Actions 이미지 게시와 digest 기록
                         ↓ 활성화된 자동 제안
                  이미지 값만 바꾸는 draft GitOps PR
                         ↓ 검토 후 병합
                  Argo CD와 Helm 배포
```

Jenkins에는 이 저장소만 선택한 fine-grained PAT의 Commit statuses: write와 필수 Metadata: read만 부여한다. Secret text ID는 `platform-lab-github-status`다. 기존 개발 PC의 CLI/OAuth 토큰, registry PAT, 관리자 kubeconfig를 복사하지 않는다. credential은 테스트 시작 전 pending 기록, 검증 완료 뒤 success 기록, 실패·중단 기록 단계에서만 바인딩한다. fork·PR 코드를 이 credentialed main job에서 실행하지 않는다.

Actions repository variable `JENKINS_STATUS_ISSUER=DevDooly`로 예상 발행 계정을 고정한다. App으로 전환할 때는 실제 bot login으로 바꾸고 설치 토큰 발급·갱신을 별도로 구현해야 한다. 현 구현이 App의 장기 자동 갱신까지 제공하는 것은 아니다. [Commit status 권한](https://docs.github.com/en/rest/commits/statuses#create-a-commit-status)

## 게시 gate

- workflow_run과 status 양쪽 이벤트가 같은 gate를 실행한다. 두 검증의 완료 순서에 의존하지 않는다.
- 이벤트에서 구한 SHA, GitHub의 현재 main SHA, 검증 run의 head SHA가 같아야 한다. 수동 실행도 우회하지 못한다.
- 워크플로 경로·main·동일 공개 저장소·허용 이벤트·성공한 실제 실행을 확인한다.
- 동일 SHA에 대기·실행 중인 관련 검증이 하나라도 있으면 게시하지 않는다. 완료된 실행은 attempt 시작 시각을 우선 비교하므로 이전 run ID의 나중 재실행 실패도 차단한다.
- Jenkins의 해당 context 중 최신 status를 먼저 고른 뒤 success·예상 issuer·검증 메타데이터를 확인한다. 더 오래된 성공으로 fallback하지 않는다.
- gate job에는 contents: read만 부여한다. 게시 job에서 registry 인증 전 다시 확인한다.
- 오래 걸리는 Dockerfile 작업은 cache-only로 먼저 완료하고, 게시 직전 다시 gate를 확인한 뒤 같은 Buildx cache에서 이미지를 게시한다. Docker 공식 문서의 `cacheonly` exporter를 사용하며, 실제 Actions 실행에서의 cache 재사용은 별도 확인한다. [Docker cache-only exporter](https://docs.docker.com/build/exporters/#cache-only-export)
- 성공한 같은 SHA의 게시 workflow와 만료되지 않은 게시 artifact가 있으면 중복 이벤트를 종료한다. artifact 보존 기간 이후의 영구 중복 제거는 제공하지 않는다.

GitHub와 registry를 하나의 트랜잭션으로 묶지는 않는다. 최종 확인 직후에도 상태가 바뀔 수 있고 두 이미지 중 하나만 게시되는 실패도 가능하다. 두 이미지가 검증돼야 게시 artifact를 만들며, GitOps PR 직전에도 gate를 다시 확인한다. 부분 게시를 배포 성공으로 인정하지 않는다.

실제 원복 source에서 수동 실행과 pollSCM이 같은 SHA의 Jenkins 빌드를 순차적으로 두 번 만들었다. 두 번째 pending이 이전 success를 대체했을 때 registry 인증 직전 재확인이 게시를 차단했다. agent 동시 실행 상한과 build 직렬화는 동일 SHA의 중복 생성 방지가 아니다. 별도 게시 시도의 GitHub metadata HTTP 403도 실패로 유지했으며, 최신 상태를 다시 확인하는 재시도와 구분해 기록한다.

## GitOps 권한과 검증

현재 사용자 승인으로 Actions의 PR 생성·승인 허용 설정과 `LAB_GITOPS_PR_ENABLED=true`를 활성화했다. 저장소 기본 workflow 권한은 read이며 propose-gitops job에만 contents: write·pull-requests: write를 가진 단기 Actions token을 부여해 전용 branch와 draft PR을 만든다. 실제 제안과 검토 후 main 반영을 확인했다. 워크플로는 자동 승인·자동 병합·Argo 명령·Helm 명령·SSH를 실행하지 않는다.

이미 게시 artifact가 있는 SHA는 새 workflow에서 publish와 proposal 모두 건너뛴다. 나중에 PR 기능을 켜면 새 source SHA를 두 CI로 검증해 게시하거나, 기존 실행에서 실패한 proposal job을 재실행한다. 별도 새 workflow가 과거 게시 결과를 읽어 proposal만 복구하는 기능은 구현하지 않았다.

허용 변경은 `api.image.repository/digest`, `api.sourceCommit`, `web.image.repository/digest`다. repository는 두 기존 GHCR 이름으로 고정한다. 기존 Secret 이름과 다른 Helm 값은 보존한다. 기존 branch에 다른 변경이 있거나 기존 PR이 ready·auto-merge 상태라면 수정하지 않는다. 재사용은 저장소·branch·head가 맞는 열린 draft에만 허용한다.

읽기 전용 PR workflow는 PR head의 코드를 실행하지 않고 base의 validator로 값과 변경 파일 범위만 검증한다. registry 출처와 Helm 렌더링·배포를 완료했다고 표시하지 않는다. GITHUB_TOKEN으로 생성한 PR 검증은 승인이 필요할 수 있으므로 실제 동작을 확인한다. [현행 workflow 트리거 규칙](https://docs.github.com/en/actions/how-tos/write-workflows/choose-when-workflows-run/trigger-a-workflow)

## 검증과 남은 작업

음성 테스트는 SHA·issuer·테스트 실패·미등록·실행 중 재시도·오래된 성공 fallback·중복 게시·허용 값 이외의 변경·기존 ready/auto-merge PR 재사용을 검사한다. 이 로컬 검증은 실제 credential 전달·GHCR 게시·PR 생성·이전 digest 복구 성공을 대신하지 않는다.

전용 credential 등록 후 같은 source SHA의 Jenkins API 15개·웹 13개 테스트와 필수 산출물, Actions 통합 검증, GHCR 게시, draft GitOps PR, Argo의 정상 B 배포를 확인했다. Pod spec과 OCI index → linux/amd64 manifest → CRI config 관계, source revision label과 HTTP·DB 결과를 함께 검증했다.

실제 main에서 기대 성공 건수를 바꾼 JUnit 음성 실험은 15개 중 1개가 기대 8·실제 7로 실패했다. 해당 SHA의 failure status와 Actions 검증 실패를 확인했고 새 이미지·게시 artifact·PR이 없었다. 실패 전후 values의 Git blob·모든 bytes, Deployment generation/template, Pod UID·시작 시각·imageID, 전체 SQL·시각·PVC와 기존 Docker는 그대로였다. 실패 변경은 원복했다. [실행 근거](../evidence/cicd-gate/README.md)와 [운영 절차](../runbooks/cicd-publication.md)를 연결한다.

GitOps PR로 API/Web pin과 sourceCommit을 이전 정상 A로 되돌려 Argo Synced·Healthy와 3개 Pod Ready를 확인했다. 실제 OCI/config와 source가 A였으며 전체 SQL·Flyway·run/event 시각·PVC binding·mount, 기존 Docker 23개의 ID·mount·시작 시각, UFW·boot ID는 유지됐다. 원복 source의 추가 이미지 게시·draft 제안도 성공했지만 그 제안은 적용하지 않고 닫았으며 최종 실행 상태는 A다. 정상·실패·복구의 세 운영 시나리오를 완료했고 다음은 3단계 관측 공개다. token 만료·실제 회전과 동시 요청 실험, K3s·Jenkins archive 전체 복원은 별도 남은 범위다.
