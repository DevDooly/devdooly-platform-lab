# CI/CD 연결과 이전 이미지 복구 검증

2026-10-11 UTC~2026-10-12 KST 실행 결과입니다. **같은 소스의 Jenkins·Actions 성공 → 이미지 게시 → 자동 초안 PR → Argo CD 배포**, 실제 테스트 실패 차단, GitOps를 통한 이전 이미지 복구를 확인했습니다. [허용 필드만 담은 요약](summary.json), [활성화 전 준비 기록](preparation.json), [재실행 절차](../../runbooks/cicd-publication.md)를 구분합니다.

## 정상 배포

| 단계 | 실제 결과 |
| --- | --- |
| 소스 | `cd48da4eaf0dd5ae245f7caa890c99f5ba92db17` |
| Jenkins | build 4, API 15개·웹 13개·status client 6개 검증, 필수 산출물 11개, GitHub success status 56089229212 |
| Actions | [컨테이너·MariaDB·API 재생성 검증 38148455244](https://github.com/DevDooly/devdooly-platform-lab/actions/runs/38148455244) 성공 |
| 게시 | [38148675074](https://github.com/DevDooly/devdooly-platform-lab/actions/runs/38148675074)의 gate·publish·propose-gitops 모두 실행·성공 |
| GitOps | 자동 생성 [PR #2](https://github.com/DevDooly/devdooly-platform-lab/pull/2)의 3개 이미지 필드만 변경. 범위 check 실행 승인 후 성공, 익명 registry OCI 출처·digest·Helm strict lint/render 확인 |
| 배포 | GitOps `4c81e4ac8c266c96e8bbd40dd6142c8e622c93a9`, Argo Synced·Healthy, API·웹·DB 3 Pod Ready |

API B digest는 `sha256:aeb4c22ae93e2e34048103aab75416721c8ee11fca0fbd37b443f8e9765912a4`, 웹 B digest는 `sha256:91d3a77775fd9bc0f67a76d419b2417ecb5354fe4a382f1a3133c3c6c056d063`입니다. 단순 환경변수 비교에 그치지 않고, containerd의 OCI index·linux/amd64 child manifest·실행 CRI config를 콘텐츠 해시로 대조했습니다.

워크플로 전체 success만으로 게시 성공을 판단하지 않습니다. `38148582569`는 Jenkins 성공 전이라 `JENKINS_STATUS_MISSING`으로 publish와 proposal을 건너뛴 실행입니다.

## 실제 JUnit 실패 차단

`7710a39d5d788b58ec29ec5d746085c610a35f70`에서 `SensorProcessorTest.fixedScenarioHasIndependentExpectedOutcomes`의 성공 기대값만 7에서 8로 바꿨습니다. 실제 결과는 7이므로 Jenkins build 6과 [Actions 38149434606](https://github.com/DevDooly/devdooly-platform-lab/actions/runs/38149434606) 모두 **15개 중 1개 실패**했습니다. 운영 코드·데이터·배포 값은 바꾸지 않았습니다.

- Jenkins는 GitHub failure status `56089598137`을 기록했고 success는 기록하지 않았습니다. 웹·archive·success 단계는 콘솔에서 earlier failure로 생략됐습니다. wfapi가 이 단계를 FAILED로 표시한 것과 실제 실행 여부를 구분했습니다.
- 실패 SHA에 대한 게시 실행 3개는 publish/proposal을 건너뛰었고 artifact는 0개였습니다. 완전한 registry tag 목록에 해당 SHA 태그가 없고 자동 GitOps PR도 없음을 확인했습니다.
- GitOps values 파일의 전체 바이트·blob SHA, Deployment UID/generation/template, Pod UID·시작 시각·imageID·restart 횟수가 유지됐습니다.
- DB 전체 행·처리 시각·Flyway, PVC 바인딩·저장 경로, 기존 Docker 서비스 23개의 ID·마운트·시작 시각도 유지됐습니다.

두 CI가 동시에 실패한 검증입니다. Actions 성공·Jenkins 단독 실패를 별도로 격리한 운영 실험은 하지 않았습니다.

## 테스트 원복과 A → B → A 복구

테스트는 `c741bb7a3964bbc21e24576ca65050a7135fcc98`에서 revert했습니다. Jenkins build 7·8과 [Actions 38149626830](https://github.com/DevDooly/devdooly-platform-lab/actions/runs/38149626830)이 정상으로 돌아왔고 [게시 38149854805](https://github.com/DevDooly/devdooly-platform-lab/actions/runs/38149854805)와 자동 [초안 PR #4](https://github.com/DevDooly/devdooly-platform-lab/pull/4)가 생성됐습니다. PR #4는 재개 확인용으로 닫고 배포하지 않았습니다.

이전 정상 A를 되돌리는 [PR #3](https://github.com/DevDooly/devdooly-platform-lab/pull/3)을 registry·OCI 출처·Helm·변경 범위 검증 후 병합했습니다. GitOps 복구 커밋은 `651e5c302e269e994c00ccda2a1c347d80e1ffb9`입니다. 별도 `helm upgrade`나 Argo rollback 명령은 사용하지 않았습니다.

| 항목 | 최종 복구 A |
| --- | --- |
| API source | `820d5c398af2b1d62a0566f9184d015ab22e9f15` |
| API digest | `sha256:1c114976aeb32e3fa1c2dda84a0a27db0b390c38a6bb59e8c5ada771c340bcf4` |
| 웹 digest | `sha256:e389ce9083b07c8b8fdeac334b13c1f1af9a0066fd541f46e7db78b5651b855a` |
| Argo·Pod | Synced·Healthy, 3 Pod Ready |
| HTTP 결과 | 입력 12·성공 7·실패 3·중복 2·대기 0 |
| 보존 | SQL 전체·처리 시각·Flyway·PVC·DB Pod/마운트·기존 Docker 23개·방화벽·호스트 boot 동일 |

API·웹 Recreate 전환 중의 연속 HTTP 중단 시간은 측정하지 않았습니다. 위 결과는 각 안정화 후 관측이며 무중단 배포를 뜻하지 않습니다.

## 운영 중 확인한 제약

수동 실행과 pollSCM이 겹쳐 동일 SHA의 Jenkins build 7·8이 실행됐습니다. build 8의 pending이 build 7 성공보다 최신이어서 게시 `38149753443`은 registry 인증 직전에 차단됐습니다. build 8 성공 이벤트가 새 게시 실행을 이어갔습니다. `38149741229`는 공개 metadata HTTP 403으로 실패했고 이미지를 게시하지 않았습니다. 별도 자동 재시도 타이머는 없습니다.

전용 Jenkins status credential을 등록했고, 사용자 승인으로 Actions의 PR 생성·리뷰 승인 가능 설정을 켰습니다. 구현은 **초안 생성만** 수행하며 리뷰 승인·자동 병합을 구현하지 않았습니다. token 원문·관리자 정보·내부 주소·원문 로그는 공개하지 않습니다. token 만료일과 실제 회전은 별도로 검증해야 합니다.

K3s·Jenkins archive 전체 복원과 외부 암호문→K3s 통합 복구는 [기존 복구 검증의 한계](../recovery/README.md)로 남아 있습니다. 공개 관측 수집과 실시간 API 연결은 다음 단계입니다.
