# 공개 플랫폼 관측 수집 검증

2026-10-11 UTC~2026-10-12 KST 실행 결과입니다. 제한된 ServiceAccount로 실제 클러스터를 읽고, Jenkins의 공개 commit status와 함께 허용 필드만 저장했습니다. **서버 수집과 인증 실패 후 기록 보존·회복을 확인했으며, 새 플랫폼 기록의 Pages 게시·공개 브라우저 확인·정기 실행은 아직 대기 중입니다.**

[공개 요약](summary.json), [플랫폼 관측 계약](../../../apps/lab-web/PLATFORM_OBSERVATION.md), [기존 앱 관측 계약](../../../apps/lab-web/OBSERVATION.md)을 구분합니다. 수집·게시·보존 절차는 [운영 안내](../../runbooks/platform-observation.md)를 따릅니다. 아래 기록은 실시간 서비스 상태나 전체 배포 이력이 아닙니다.

## 실제 서버에서 확인한 수집

최종 검증한 성공 수집의 완료 시각은 `2026-10-11T15:27:44.173356Z`입니다. 최초 성공은 `2026-10-11T15:27:43.555475Z`, 의도한 인증 실패는 `2026-10-11T15:27:43.705672Z`였으며, 아래 최종 기록은 정상 인증으로 회복한 결과입니다. 각각 실제 시도 완료 시각이며 게시 시각·현재 시각으로 바꾸지 않습니다.

| 출처 | 확인한 값과 범위 |
| --- | --- |
| main | `e823cb793308e79ea5b7b5a17af2d554b4091275` |
| Jenkins | 해당 main의 build 10, 공개 status `56090140506`, `success`; status 생성 시각 `2026-10-11T15:19:36Z` |
| Argo CD | revision `e823cb793308e79ea5b7b5a17af2d554b4091275`, `Synced`·`Healthy` |
| API·웹·DB | 각 실제 Pod 준비 수 1 / 선언 목표 수 1 |
| API 배포 선언 소스 | `820d5c398af2b1d62a0566f9184d015ab22e9f15` |
| API 선언 이미지 | `ghcr.io/devdooly/devdooly-platform-lab-api@sha256:1c114976aeb32e3fa1c2dda84a0a27db0b390c38a6bb59e8c5ada771c340bcf4` |
| 웹 선언 이미지 | `ghcr.io/devdooly/devdooly-platform-lab-web@sha256:e389ce9083b07c8b8fdeac334b13c1f1af9a0066fd541f46e7db78b5651b855a` |

Jenkins는 수집 당시 main의 최신 `ci/jenkins-test` status를 검증합니다. GitHub의 issuer·고정 description을 확인한 뒤 build 번호를 사용하며, 다른 main의 과거 성공을 현재 검증으로 대체하지 않습니다. 해당 main의 status가 없으면 `jenkins: null`입니다.

main·Jenkins 대상·Argo GitOps revision·API 배포 선언은 서로 다른 근거입니다. 이번 관측에서는 main과 Argo revision이 같고, API는 [이전 정상 A로 복구한 소스·digest](../cicd-gate/README.md)를 유지합니다. SHA 차이를 수집 실패로 간주하거나 하나의 최신 SHA로 덮어쓰지 않았습니다.

준비 수는 해당 component의 실제 Pod 중 삭제 중이 아니며 `Running`, `Ready=True`, 모든 컨테이너가 ready인 수입니다. 목표 수는 Deployment·StatefulSet의 선언 replicas입니다. api/web의 이미지와 API source annotation도 **Deployment template의 선언 값**입니다. 이 수집이 개별 실행 컨테이너의 imageID나 현재 JVM의 소스를 직접 검증했다는 뜻은 아닙니다.

## 권한 경계와 실패 후 보존

실제 수집 HTTP는 전용 ServiceAccount credential을 사용했습니다. 수집기에는 관리자 kubeconfig fallback이 없으며 클러스터에는 읽기 요청만 보냅니다.

| 실제 확인한 경계 | 결과 |
| --- | --- |
| 지정된 API·웹 Deployment, DB StatefulSet 읽기 | 허용 |
| Lab namespace의 Pod 목록과 지정 Argo Application 읽기 | 허용 |
| Secrets get/list, Pod logs/exec, nodes 읽기 | 거부 |
| Deployment patch | 거부 |
| 다른 namespace의 Pod 목록, 관련 없는 Argo Application 읽기 | 거부 |

RBAC의 Pod list 권한은 namespace 범위입니다. 고정 label selector는 수집기의 조회·집계 범위이며 RBAC 자체의 필드별 권한 경계로 주장하지 않습니다. 공개 출력에서는 Pod 이름·주소·관리 URL·토큰·환경 변수·원문 로그·임의 오류를 제외합니다. 구조 schema와 semantic validator가 중첩 객체의 알 수 없는 필드도 거부합니다.

의도한 인증 실패에서 `latestAttempt`만 고정 실패 코드·실제 완료 시각으로 바뀌고, 직전 `lastSuccess` **전체와 원래 capturedAt `2026-10-11T15:27:43.555475Z`가 유지**됐습니다. 올바른 인증으로 다시 수집해 `2026-10-11T15:27:44.173356Z`에 성공으로 회복되는 것도 확인했습니다. 출력 파일의 실제 POSIX 권한은 `0600`이었습니다. 이 실험은 수집 인증 실패이며 Lab 서비스를 중단한 실험과 다릅니다.

## 로컬 구현 검증과 남은 작업

- 웹은 신규 관측 검사 13개를 포함한 전체 26개 테스트, Astro 타입 검사, Pages 경로 빌드를 로컬에서 통과했습니다. 합성 입력과 로컬 HTTP 검증이며 공개 브라우저에서 이 새 카드를 확인한 결과는 아닙니다.
- 수집기의 Windows 오프라인 검사는 41개 중 40개 통과, POSIX 파일 권한 검사 1개 제외였습니다. 이어 Ubuntu의 격리된 임시 디렉터리에서 고정한 collector·contract와 41개 검사를 실행해 **41개 모두 통과·제외 0개**를 확인했습니다. 이 검사에는 POSIX `0600` 권한도 포함되며 실제 클러스터 수집 결과와는 별도 범위입니다.
- 수집 실패와 브라우저 파일 조회 실패를 분리했습니다. 마지막 성공 후 2시간 초과는 오래된 기록으로 표시하고, 실패한 시도의 새 시각으로 이전 성공을 최신처럼 만들지 않습니다. 이 오래된 기록·조회 실패 처리는 오프라인 UI 테스트로 확인했습니다.
- 기존 `lab-observation.json` v1과 조회 API의 플랫폼 `NOT_CONFIGURED`를 유지합니다. 현재 JVM 정보, 새 플랫폼 관측본과 CI/CD 근거를 합쳐 하나의 실시간 상태로 표시하지 않습니다.

| 아직 완료하지 않은 항목 | 상태 |
| --- | --- |
| 허용 JSON을 outbound Pages dispatch로 게시 | 준비 중 |
| 새 플랫폼 카드·수집 시각·오류 표시의 공개 브라우저 검증 | 대기 |
| 정기 수집·토큰 회전·반복 게시 운영 | 대기 |
| 실제 Lab 중단 후 공개 홈·마지막 기록 보존 검증 | 미실행 |
| 실시간 공개 읽기 API, 외부망 HTTPS 경로 | 미연결 |

이번 단계에서는 새로운 inbound 공개 경로를 열지 않았습니다. 관리 도구는 기존 인증된 접속 경로를 유지하며, 서버에서 허용한 JSON을 밖으로 전달하는 방식을 준비합니다. 기존 Pages의 앱 관측본 공개와 이번 새 플랫폼 관측본의 게시 완료를 구분합니다. 실제 접속 주소·관리 endpoint·credential·원문 진단은 이 근거에 포함하지 않습니다.
