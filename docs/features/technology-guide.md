# 기술을 설명하는 포트폴리오

## 목적과 읽는 순서

채용·이직 포트폴리오의 목적에 맞춰 기능 목록보다 기술의 역할과 설계 판단을 먼저 보여줍니다. 업무 경력은 홈의 경험 소개, 개인 Lab의 재현 결과는 기술별 근거로 구분합니다.

1. [기술 목차](https://devdooly.github.io/devdooly-platform-lab/technologies/)에서 8개 영역과 작업 처리·배포·격리 데이터 실험의 전체 구성을 봅니다.
2. 각 기술 페이지에서 문제 → 설계 → 실제 화면 → 설정 → 학습 순서 → 소스·검증 근거를 읽습니다.
3. [학습·재구축 안내](https://devdooly.github.io/devdooly-platform-lab/guides/rebuild/)에서 로컬 H2/API·화면을 시작하고, MariaDB Compose와 메시징·GitOps 확장 순서를 따라갑니다.

## 실제 화면과 근거

`apps/lab-web/public/images/technologies/`의 JPEG 7개는 2026-10-26(KST)에 공개 사이트에서 촬영했습니다. 그림을 생성하거나 관리 UI로 가장하지 않았습니다.

| 캡처 | 실제 공개 경로 | 읽을 때 구분할 점 |
| --- | --- | --- |
| api-guide.jpg | `/api-guide/`의 API 목차 | 캡처에서 새 GET 실행 없음 |
| java-result.jpg | `/#lab` | 공개 GET의 합성 실행 결과; 조회와 실행 시각은 다름 |
| kafka-recovery.jpg | `/#kafka-lag-recovery` | 저장된 격리 Kafka 재개 시험 |
| export-record.jpg | `/#export-integrity-runtime` | 저장된 손상·수리 시험 |
| delivery-record.jpg | `/#platform-record` | Jenkins·Argo 공개 관측; 수집 시각 2026-10-26 07:45:11 UTC |
| lakehouse-record.jpg | `/#cloud-lakehouse` | 격리 Cloud 기록; 현재 상시 서비스 상태가 아님 |
| java-case.jpg | `/#ai-window` | 개인 Java 예제와 측정 기록; 사람 검토 PENDING |

기술 페이지의 소스 링크는 설명 기준 `bb53eadf4d189ae1ff357493e194c24a91df70ad`에 고정했습니다. 스크린샷은 각자의 원 관측 시각을 유지합니다. Jenkins·Argo CD·Kafbat은 기존 로그인 링크로 연결하며 새 인증이나 권한을 추가하지 않습니다.

## 대표 설계 사례: Kafka 재전달과 결과 보존

[사례 페이지](https://devdooly.github.io/devdooly-platform-lab/cases/kafka-redelivery/)는 기술 목차·Kafka 상세에서 들어갑니다. 세 중단 지점의 DB/Kafka 상태·재개 동작·보존 조건을 선택해 비교하며, 최종 수치는 기존 `docs/evidence/kafka-redelivery/summary.json`의 해당 세 사례를 빌드 시 연결합니다. 별도 숫자 fixture나 새 장애 실행을 만들지 않습니다.

DB의 완료 재호출 보호와 업무상 센서 `DUPLICATE` 판정은 다릅니다. DB commit·offset commit·export 확인의 완료 조건을 나누고, 상시 runner의 `EXPORT → PUBLISH → CONSUME` 반복 순서를 설명합니다. Kafka offset 성공이 파일 저장 완료를 의미하거나 export가 항상 재전달 뒤에만 실행된다고 표현하지 않습니다.

공개 첫 진입에서 준비 전 radio 선택만 바뀌고 설명이 첫 기록에 남는 반례를 확인했습니다. 선택기는 초기 HTML에서 비활성화하고 화면 준비 후 활성화합니다. 첫 기록의 본문·수치는 계속 읽을 수 있으며, 이 경계의 SSR 회귀 검사와 실제 준비 후 선택 동작을 구분해 확인합니다. 원 반례와 수정 전 실패 기록은 해당 PR 근거에 보존합니다.

당시 2026-10-15 격리 시험(Windows child JVM·단일 broker/partition/RF1)의 세 강제 종료 사례이며 네 번째 원본 손상 시험·후속 export/commit 실패 복구는 원 근거로 연결합니다. 소스 설명은 `2aae197`에 고정하며 당시 소스 지문과 현재 운영 pin을 구분합니다. 이 UI는 React의 선택 상태만 바꾸고 API·서버 실행·파일 저장을 추가하지 않습니다. 변경에 맞는 진단·빌드·실제 선택/키보드/모바일·독립 검토와 같은 main의 CI/Pages·공개 확인 결과는 해당 PR에 기록합니다.

## Kafbat 로그인 안내

서비스 목차의 Kafka 카드와 Kafka 기술 페이지에서 기본 아이디 `lab-viewer`, 서버 소유자가 미니 PC의 `rudy` 계정에서 비밀번호를 확인하는 방법을 찾을 수 있습니다. 기존 [계정 확인 문서](../runbooks/service-console.md#계정-확인)를 연결하고, 그 문서의 명령을 접힌 안내로 제공합니다. 웹페이지는 파일을 읽거나 로그인 요청을 보내지 않습니다. 실제 비밀번호나 인증 파일 본문은 포함하지 않습니다.

## 재구축 안내의 범위

명령 블록은 저장소의 기존 절차와 대조했으며 복사 버튼을 제공합니다. 이번 변경에서 새 서버·컨테이너를 구성하거나 모든 명령을 새 장비에서 실행한 것은 아닙니다. 현재 Compose는 MariaDB·API·웹이고 Kafka·Garage·worker는 별도 준비가 필요합니다. chart의 단일 노드·local-path·cluster.local·Ingress 제약과 공개 API URL 허용 형식도 안내합니다.

후속 우선순위는 대표 설계 사례의 설명 깊이와 재구축 안내의 실제 이용 공백입니다. 작은 탐색 기능이나 정상 운영 점검을 근거 없이 반복해서 늘리지 않습니다. Pages 토큰, 별도 환경 기동 복원, 예산 정책, PR #102와 운영 image/source pin은 그대로 유지합니다.

## 검증 기록

로컬 기본 웹 검사 554개 통과, Astro 99파일 진단 0, 총 16페이지 정적 빌드를 확인했습니다. 새 경로 10개의 링크·앵커·소스 파일·이미지를 검사하고, 브라우저에서 홈 → 목차 → 상세 → 설정·재구축 이동과 모바일 목차·명령 복사 완료 표시를 확인했습니다. 클립보드 도구의 반환은 비어 있어 실제 클립보드 원문 일치까지 검증한 것으로 기록하지 않습니다. 같은 main의 CI·Pages와 공개 화면 확인은 이 변경의 PR 결과에 남깁니다.
