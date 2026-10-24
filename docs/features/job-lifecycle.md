# 작업·export 기록 흐름

[작업 관측 화면](https://devdooly.github.io/devdooly-platform-lab/#job-observation)에서 각 작업의 생성·원본 검증/대기 등록·DB 완료·저장 확인 commit 기록을 한 흐름으로 봅니다. 기존 공개 관측 응답을 표시하며 새 작업·export·저장소 검증을 실행하지 않습니다.

## 단계 읽기

| 단계 | 원래 필드 | 의미 |
| --- | --- | --- |
| 작업 생성 | createdAt | STAGING 작업을 만든 기록 |
| 원본 검증·대기 등록 | sourceVerifiedAt / queuedAt | 원본 저장·검증 후 처리 대기와 dispatch intent를 등록한 기록. 두 필드는 공개 계약상 같은 원문 시각 |
| DB 처리 완료 | completedAt | DB에 처리 완료를 기록한 시각 |
| 저장 확인 commit | exportCompletedAt | 결과·실패 파일 저장 확인을 DB에 commit한 기록 |
| 명시적 종료 | terminatedAt | 존재할 때 별도로 표시하는 종료 기록. 앞선 모든 단계의 성공을 뜻하지 않음 |

시각이 있는 단계만 **기록 있음**, null은 **미기록**으로 표시합니다. 미기록만으로 현재 대기·실행·실패를 추정하거나 진행률을 계산하지 않습니다. COMPLETED/PENDING은 DB 완료와 export 확인을 구분하며, CANCELLED는 취소와 저장 확인 미기록을 표시합니다. TERMINATED는 별도 종료 분기로 표시합니다. runtime의 마지막 DB 신호·슬롯·파일 확인 기록은 기존 관측 카드에 표시합니다. 이 기록은 현재 worker 생존을 증명하지 않습니다.

## 두 기록 간격

- **처리 대기 등록 → DB 완료 기록 간격:** queuedAt에서 completedAt까지입니다. 생성 시각부터의 간격이나 처리 시작부터의 시간이 아닙니다. Kafka 발행 확인·순수 처리/대기 시간으로 분해할 수 없습니다.
- **DB 완료 → 저장 확인 commit 기록 간격:** completedAt에서 exportCompletedAt까지입니다. 재시도·일시 정지 등이 포함될 수 있으며 S3 전송 시간이나 export 코드의 실행 시간을 뜻하지 않습니다.

두 시각 중 하나라도 없으면 **미기록**입니다. 같은 순간의 두 기록은 **0초**로 구분합니다. 기존 UTC 파서를 재사용해 최대 소수9자리의 나노초 차이를 정수로 계산하고, 부동소수 변환이나 반올림 없이 초로 표시합니다. 원시 기록의 정밀도 보존이며 시계 정확도나 측정 정밀도를 새로 보증하지 않습니다. 현재 시각과의 차이를 더하거나 실시간 경과 시간을 만들지 않습니다.

단계 카드의 시각은 UTC 초 단위 요약입니다. **원시 시각 6개 보기 · UTC**를 펼치면 createdAt·sourceVerifiedAt·queuedAt·completedAt·exportCompletedAt·terminatedAt의 원문 또는 null을 모두 확인합니다. sourceVerifiedAt과 queuedAt도 원문에서 각각 확인할 수 있습니다.

## 구현·확인 범위

`lib/job-lifecycle.ts`가 기존 JobObservation에서 단계와 간격을 만들고, `JobLifecycle.tsx`가 각 작업에 표시합니다. 기존 `job-observation.ts`는 나노초 파서의 별칭 export만 추가하며 검증·본문 읽기·이전 기록 보존·fallback·8초 제한·10초 조회를 바꾸지 않습니다. 부모의 source/capturedAt·runtime·슬롯·파일 크기/SHA 근거도 유지합니다.

STAGING·QUEUED·완료 후 PENDING/EXPORTED/CANCELLED·DB 완료 전 TERMINATED와 null/0/1ns·연도 경계의 간격, 원문 보존은 합성 모델·렌더 검사로 확인합니다. 실제 공개 응답에 없는 상태를 운영에서 실행한 것처럼 표시하지 않습니다. 웹·타입·빌드 및 실제 공개 화면의 확인 결과는 이 변경의 PR에 기록합니다.

로컬에서는 웹 테스트 388개·Astro 진단 0개·4개 페이지 빌드를 통과했습니다. 첫 전체 테스트는 기존 Kafka 테스트의 OS 임시 폴더 접근 제한으로 1개가 실패했으며, 제품 코드 변경 없이 테스트 프로세스의 임시 폴더만 허용된 작업 폴더로 지정한 뒤 전체를 통과했습니다. 실제 공개 GET을 연결한 로컬 화면에서 EXPORTED 작업 9개의 표시와 첫 작업의 기록 간격 0.830872초·0.691542초, 원시 시각 6개 및 null을 확인했습니다. 키보드 Enter로 원문을 펼쳐도 작업 ID·상태·건수·파일 크기/SHA는 유지됐습니다. 모바일 콘텐츠 폭 375px에서 가로 넘침 0·본문 17px·펼침 영역 50px 이상을 확인했습니다. 이 확인은 새 작업 실행이나 현재 저장소 검증이 아닙니다. 같은 main의 CI·Pages와 공개 사이트 확인은 PR 검증 기록에서 따로 연결합니다.

Pages 토큰 교체·별도 환경의 K3s/Jenkins 기동 복원·예산 정책·PR #102 보류와 운영 image/source pin은 유지합니다.
