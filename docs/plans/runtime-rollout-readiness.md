# runtime 소스 차이와 배포 전 확인

비교 기준은 [`46d099d1792f3e93125db7f1ffb2ab3e286abc17`](https://github.com/DevDooly/devdooly-platform-lab/commit/46d099d1792f3e93125db7f1ffb2ab3e286abc17)이다. 아래는 공개 응답·저장소 코드와 선언의 대조이며, 새 이미지 선정이나 실제 운영 배포 완료 기록이 아니다.

## 서로 다른 source의 의미

| 구분 | 확인한 값과 의미 |
| --- | --- |
| API 응답 | [실제 GET6 기록](../evidence/public-get/README.md)의 source는 `245d61a5749760a20918ab091d9410ce6735b1c0`이다. 검사기46d와 API가 보고한 소스를 구분한다. |
| worker 마지막 DB 기록 | 공개 작업 화면에 보인 runtime source는 `74a8e98844a8fea0653951136ede0e7de0d7ac08`이다. API가 읽은 마지막 journal 값이며 현재 프로세스 생존·실제 Pod image의 증명이 아니다. |
| GitOps 선언 | [values.yaml](../../gitops/environments/home-lab/values.yaml)의 API245와 [runtime.yaml](../../gitops/environments/home-lab/runtime.yaml)의 worker74는 별도 image/source pin이다. 공개 보고값과 선언의 일치가 실제 Argo 적용 증거를 대신하지 않는다. |

자동 이미지 제안은 API·웹 값을 갱신하며 worker pin을 바꾸지 않는다. 따라서 API만 갱신하고 worker의 실행 오류 처리가 반영됐다고 판단할 수 없다.

## 코드에서 준비된 범위

API245와 비교 기준 main의 runtime production 차이는 `ContinuousJobRunner`, `RuntimeResources`, `RuntimeMain` 세 파일이다. Error를 정상 STOPPED로 덮지 않고 가능한 경우 한 번의 pause를 시도하며, 나머지 client·lease 정리와 부분 구성의 역순 종료 뒤 첫 Error를 전파한다. [실행 중 오류 근거](../evidence/runtime-error-cleanup/README.md)와 [부분 구성 실패 근거](../evidence/client-construction-error/README.md)의 관련33개 회귀·같은64be 소스 Linux API240개 통과는 코드 검증이다. 실제 OOM·현재 worker 반영·운영 복구의 증거로 확대하지 않는다.

worker74와 비교하면 Kafka 관측 클래스·application 설정도 추가된다. 관측 설정은 API 경로에 연결되고 worker의 기본값은 비활성이므로 이를 위해 worker에 관측 자격증명을 새로 켜지 않는다. 현재 CLI는 migration을 실행하지 않고 API가 미리 적용한 V3 runtime·V4 admission schema를 요구한다. [현재 코드](https://github.com/DevDooly/devdooly-platform-lab/tree/46d099d1792f3e93125db7f1ffb2ab3e286abc17/apps/api/src/main/java/io/github/devdooly/platformlab/jobs/runtime)와 [runbook](../runbooks/continuous-runtime.md#먼저-확인할-조건)을 기준으로 확인한다.

## 게시된 이미지의 읽기 전용 대조

게시 source는 `6f551a16a8ed536bb126403234c41b9e9b266d43`이다. 같은 source의 [Actions 검증39476929942](https://github.com/DevDooly/devdooly-platform-lab/actions/runs/39476929942)와 Jenkins build133의 성공 status `56819189155`, [실제 게시39477559607](https://github.com/DevDooly/devdooly-platform-lab/actions/runs/39477559607)의 gate·publish·proposal 성공을 대조했다. 게시 artifact `12289059891`의 manifest도 같은 validation run·Jenkins status/build와 API digest를 기록한다. 앞선 [39477302457](https://github.com/DevDooly/devdooly-platform-lab/actions/runs/39477302457)은 전체 success여도 publish가 skipped였으므로 게시 증거로 사용하지 않는다.

API의 게시 digest는 `sha256:ee71389be27fa484284a517a324c52a9c827cd20db21f0b306c4dcfd52147aad`이다. 2026-10-20 19:55:33–19:55:34 UTC에 사용자 자격증명을 제공하지 않는 별도 Docker 설정으로 공개 registry의 OCI index를 읽었다. [원문 index](../evidence/runtime-release-readiness/oci-index.json)는 856bytes이며 SHA-256이 이 digest와 정확히 같다. descriptor2개 중 Linux amd64의 manifest digest는 `sha256:d324a231e6e190f88556f6ab85d90763d29a50163c1724ba2d21d4962e06a834`이다. [조회 요약](../evidence/runtime-release-readiness/oci-read-summary.json)은 결과와 범위를 기록한다. 요약은 공개용 LF 직렬화이며 원문 index의 bytes는 그대로 보존했다.

사용한 [빈 자격증명 설정](../evidence/runtime-release-readiness/anonymous-client-config.json)은 관련 없는 `.invalid` 주소의 빈 auth 항목과 빈 `credsStore`·`credHelpers`만 포함한다. Docker29.8.2/build7fc2dff의 [설정 로더](https://github.com/docker/cli/blob/7fc2dff/cli/config/config.go#L155-L164)·[ContainsAuth 검사](https://github.com/docker/cli/blob/7fc2dff/cli/config/configfile/file.go#L138-L142)를 대조해 native credential helper 자동 탐색을 막았고, 인증 환경변수도 사용하지 않았다. Buildx0.37.2의 [`--raw` 처리](https://github.com/docker/buildx/blob/2d379c0c3f22da0d2759d132a0ec81ca949098f0/util/imagetools/printers.go#L62-L65)로 index만 읽었다. 앞선 빈 디렉터리·format 조회는 helper 사용 여부를 배제할 수 없어 자격증명 없는 조회의 근거에서 제외했다. 이미지 config의 source label·layer·컨테이너 실행·미니 PC pull/배포는 검사하지 않았다.

게시 source6f55와 비교 기준46d의 `apps/api` 전체 Git tree는 `36c1c8af0f1492b3d34dc6514cd6b61767ccf3ec`로 같고 API Dockerfile·`.dockerignore`도 같다. 이는 비교한 소스 입력의 일치이며 재빌드한 이미지 bytes나 실제 실행 binary의 일치를 증명하지 않는다. [PR169](https://github.com/DevDooly/devdooly-platform-lab/pull/169)은 확인 당시 API·웹 values만 바꾸는 미병합 초안이며 worker pin을 갱신하지 않는다. 게시된 후보를 배포 대상으로 선정하거나 해당 PR을 병합하지 않았다.

## 아직 확인하지 않은 배포 전제

- 위 게시 후보의 검증·게시·공개 index 자료는 확인했지만, 실제 배포 대상으로 쓸 source·API/worker 각각의 pin·현재 Pod와 이전 pin의 대응은 아직 확정하지 않았다. 새 OCI는 아직 선택하지 않았고 자동 GitOps 초안을 일괄 병합하지 않았다.
- 현재 Argo의 source revision·실제 valueFiles/override·sync 상태와 Pod의 소유 관계·image ID·readiness를 읽기 전용으로 확인해야 한다. 선언 파일만으로 현재 설치 상태를 단정하지 않는다.
- 실제 DB의 V3/V4 성공 이력·checksum·runtime 행과 새 binary 호환, 유휴·EXPORTED·빈 슬롯·pending outbox 0, 기존 SQL·파일·offset 보존 기준은 아직 대조하지 않았다.
- 기존 Recreate·종료 유예300초·hook 대기240초·exec readiness를 유지하고 이전 실행의 종료·lease 해제와 새 실행의 identity·heartbeat를 구분해야 한다. `PAUSED_OPERATOR`는 재시작으로 해제되지 않고 resume도 자료를 수리하지 않는다. DB/lease 손실로 pause·stop 기록이 남지 않을 수 있으므로 RUNNING만으로 정상 종료·생존을 판정하거나 잠금을 강제 해제하지 않는다.

SSH를 통한 현재 Argo·Pod·DB 조건 조회와 서버 변경은 아직 수행하지 않았다. 기동 복원·토큰 교체·자원 예산 정책·PR102 접수 gate의 네 보류는 유지한다. 이 문서는 새 실행 절차나 쓰기 명령을 추가하지 않는다.
