# 공개 플랫폼 관측 계약 v1

`public/data/platform-observation.json`을 선택적으로 게시합니다. 이 파일은 빌드·배포·준비 상태를 수집한 **정적 관측 기록**이며 실시간 상태가 아닙니다. 기존 `lab-observation.json` v1과 조회 API의 `NOT_CONFIGURED` 값은 변경하지 않습니다. 실제 관측 JSON은 수집기를 검증한 뒤 별도로 생성합니다.

타입은 `src/lib/platform-observation.ts`, 구조 스키마는 `schemas/platform-observation.schema.json`입니다. 모든 객체는 허용 필드만 받습니다. 내부 IP·호스트·Pod 이름·관리 URL·토큰·환경 변수·원문 오류·로그를 넣을 필드가 없습니다. 알 수 없는 필드는 중첩 위치에서도 거부합니다.

## 고정 형식

최상위 필드는 `schemaVersion: 1`, `kind: "platform-observation"`, `latestAttempt`, `lastSuccess` 네 개뿐입니다.

| 객체 | 필수 필드와 값 |
| --- | --- |
| latestAttempt | `attemptedAt`: 실제 시도 완료 UTC, `status`: `success` 또는 `failure`, `errorCode`: 아래 고정 코드 |
| lastSuccess | 아직 성공한 수집이 없으면 `null`. 있으면 `capturedAt`, `collectorVersion: "1"`, `mainCommit`, `jenkins`, `argo`, `workloads`, `deploymentSourceCommit` |
| jenkins | 현 main에 확인한 Jenkins status가 없으면 `null`. 있으면 `sourceCommit`, `statusId`, `state`, `createdAt`, `buildNumber`, `issuer: "DevDooly"` |
| argo | `revision`, `sync`: `Synced/OutOfSync/Unknown`, `health`: `Healthy/Progressing/Degraded/Suspended/Missing/Unknown` |
| workloads | `api/web/database`가 각각 한 번씩인 정확히 3개. 각 항목은 `component`, `desired`, `ready`. api/web만 `image` 필수, database는 image 필드 없음 |

오류 코드는 `NONE`, `GITHUB_STATUS_UNAVAILABLE`, `ARGO_UNAVAILABLE`, `WORKLOADS_UNAVAILABLE`, `AUTHENTICATION_FAILED`, `TIMEOUT`, `INVALID_OBSERVATION`, `COLLECTION_FAILED`입니다. 성공일 때만 `NONE`이며 실패에서는 나머지 코드 중 하나를 사용합니다. HTTP 응답 본문이나 예외 문자열을 코드 대신 넣지 않습니다.

- SHA는 소문자 16진수 40자입니다. `unknown`은 허용하지 않습니다.
- `statusId`는 1~9007199254740991, `buildNumber`는 1~2147483647의 정수입니다. Jenkins `state`는 `pending/success/failure/error`입니다.
- `desired/ready`는 각각 0~10의 정수입니다. 전환 중 준비 수가 목표 수를 잠깐 넘을 수 있어 `ready <= desired`를 강제하지 않습니다.
- `desired`는 api/web Deployment와 database StatefulSet의 선언 replicas입니다. `ready`는 해당 component의 실제 Pod 중 삭제 중이 아니며 Running·Ready=True이고 모든 containerStatuses가 ready인 개수입니다. Pod 이름이나 주소는 공개하지 않습니다.
- api/web 이미지는 각각 `ghcr.io/devdooly/devdooly-platform-lab-api@sha256:<64자 소문자 hex>`, `ghcr.io/devdooly/devdooly-platform-lab-web@sha256:<64자 소문자 hex>`만 허용합니다. 태그·다른 registry·query·인증정보는 받지 않습니다.
- 시각은 `YYYY-MM-DDTHH:mm:ss[.소수 1~9자리]Z`의 실제 UTC 날짜·시각입니다. 오프셋·윤초·존재하지 않는 날짜는 받지 않습니다.
- 연도는 Python 수집기와 같은 0001~9999 범위입니다. 구조 스키마의 날짜 format 검사도 활성화해야 합니다.

## 각 출처의 의미

`mainCommit`은 수집 당시 main HEAD입니다. Jenkins status가 있으면 `jenkins.sourceCommit === mainCommit`이어야 합니다. main에 status가 없으면 Jenkins를 `null`로 표시하며 과거 성공을 현 main의 성공으로 옮기지 않습니다. 수집기는 최신 `ci/jenkins-test` status를 선택한 뒤 issuer와 상태별 고정 description을 검증해 실제 buildNumber를 추출합니다.

`argo.revision`은 Argo가 보고한 GitOps revision입니다. `deploymentSourceCommit`은 API Deployment template의 소스 annotation이며 현재 JVM에서 읽은 소스 값이 아닙니다. api/web의 `image`도 Deployment template의 **선언 이미지 digest**이며 개별 컨테이너의 실행 imageID 검증과 구분합니다. 따라서 main SHA, Jenkins 대상 SHA, Argo GitOps SHA, API 배포 선언 SHA가 다르더라도 이를 실패로 간주하거나 한 값으로 덮어쓰지 않습니다. 복구 중 이전 digest가 선언되면 그 값을 그대로 표시합니다.

## 성공·실패·오래된 기록

- 성공: `lastSuccess`가 반드시 있고 `lastSuccess.capturedAt === latestAttempt.attemptedAt`입니다. 완료한 동일 시도의 실제 UTC를 두 필드에 사용합니다.
- 실패: `latestAttempt`만 새 완료 시각과 고정 실패 코드로 갱신하고 이전 `lastSuccess`를 유지합니다. 이전 성공이 없으면 `null`입니다. `capturedAt <= attemptedAt`이어야 합니다.
- Jenkins status가 있으면 `createdAt <= lastSuccess.capturedAt`입니다.
- 마지막 성공 후 2시간이 지나면 화면에 오래된 기록으로 표시합니다. 최근 실패와 오래된 기록은 동시에 표시할 수 있습니다.
- 브라우저의 파일 HTTP·네트워크·형식 오류는 수집기의 실패와 별도입니다. 새 파일을 읽지 못하면 이미 읽은 유효 기록을 유지하고 브라우저 조회 실패라고 표시합니다.
- 브라우저 시각보다 기록이 앞서면 현재 상태로 표시하지 않고 시각 확인이 필요하다고 안내합니다.

스키마는 필드·형식·조건을 검사하며 시각 관계와 SHA 일치는 런타임 validator도 검사합니다. 수집기는 임시 파일에 검증한 envelope를 쓰고 원자적으로 교체해야 합니다. 수집 실패에서 이전 성공을 지우거나 브라우저에 관리 자격증명을 전달하지 않습니다.

## 게시 전 검사

`src/lib/platform-observation.ts`의 `validatePlatformObservation(document)`는 부작용 없는 타입 가드로, Node의 TypeScript 타입 제거 기능으로 직접 불러올 수 있습니다. `MAX_PLATFORM_OBSERVATION_BYTES`는 16 KiB입니다. 게시 도구는 이 크기 제한과 semantic validator를 모두 적용하고, 미래 시각·기존 기록과의 병합 정책도 별도로 검사해야 합니다.

파일 검사는 `node --experimental-strip-types scripts/validate-platform-observation.ts <file>`로 실행합니다. CLI는 유효 여부만 출력하며 입력 내용·원문 오류·경로를 출력하지 않습니다. 실제 공개 관측 파일은 이 구현에 포함하지 않습니다.
