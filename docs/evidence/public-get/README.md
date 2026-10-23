# 공개 GET 응답 계약 — 실제 관측 기록

## 최신 후속 관측 — 2026-10-23 UTC

[수동 실행39940801991](https://github.com/DevDooly/devdooly-platform-lab/actions/runs/39940801991)의 첫 attempt에서 `offline`·`public_gets`가 성공했습니다. `10:41:16.550Z`–`10:41:26.508Z`에 고정 GET6개가 모두 HTTP200·공개 헤더·DTO 계약을 통과했고, 공개 IPv4·표준 TLS를 확인했습니다. 검사기 소스는 `285d148638ece7b085bf3726b3344271e6e1cd08`, 응답 소스는 기존 API `245d61a5749760a20918ab091d9410ce6735b1c0`이며 두 값을 구분합니다.

[요약 원문](hosted-39940801991/summary.json) 1,635bytes와 [실행 결합 metadata](hosted-39940801991/run-metadata.json) 346bytes를 run·job·단일 artifact·ZIP entry와 대조했습니다. 요약 SHA-256은 `42f4b04ca2e77554e01494c66bbf607a65d5869924a80cbeddaf25f70e870841`, metadata SHA-256은 `93ad969da5de707f8a12a84151b8a831b4d6d8ff30504323954c7ad13aa2e669`입니다. 주소·IP·본문·자격증명은 포함하지 않습니다.

이번 후속은 고정 읽기 응답의 계약 확인입니다. POST·거부 요청·운영 설정 변경은 하지 않았으며, worker 생존·지속 가용성·인증서 자연 갱신이나 새 배포의 증명은 아닙니다. [GitHub App 만료 후 갱신](../github-app-jenkins/NATURAL_EXPIRY.md)과도 별도 실행입니다. Pages 토큰 교체·별도 환경 기동 복원·예산 정책·PR #102 보류를 유지합니다. 아래 이전 관측은 원래 출처와 함께 보존합니다.

2026-10-20 UTC의 [수동 실행39483000285](https://github.com/DevDooly/devdooly-platform-lab/actions/runs/39483000285)에서 `offline`·`public_gets` 두 job이 성공했습니다. 고정 GET6개가 모두200과 공개 DTO 검증을 통과했습니다. 이 실행은 POST나 거부 경로를 보내지 않으며, [기존 GET6·거부3 검사](../public-read-https/README.md)와 범위를 구분합니다.

| 출처 | 실제 기록 |
| --- | --- |
| 검사기 소스 | `46d099d1792f3e93125db7f1ffb2ab3e286abc17` |
| 응답에서 확인한 소스 | 6개 모두 `245d61a5749760a20918ab091d9410ce6735b1c0` |
| 수집 시작 → 완료(UTC) | `2026-10-20T19:23:35.337Z` → `2026-10-20T19:23:44.348Z` |
| 실제 job 완료(UTC) | `2026-10-20T19:23:48Z` |
| 결과 | `PASS / NONE`, 공개 IPv4·표준 TLS 확인 |
| 결과 원문 | [summary.json](hosted-39483000285/summary.json), 1,635bytes |
| 출처 metadata | [run-metadata.json](hosted-39483000285/run-metadata.json), 346bytes |

검사기 checkout과 운영 API 응답의 source는 서로 다릅니다. 응답의 source를 최신 main과 같다고 간주하거나, 이번 검사에서 운영 프로그램을 배포했다고 해석하지 않습니다.

## 지정6개 응답

아래 시각은 서버가 응답한 원래 관측 시각을 나노초 표기 그대로 보존했습니다. 모든 행의 `passed=true`, HTTP status는200입니다.

| 검사 | 응답 관측 시각(UTC) |
| --- | --- |
| SUMMARY | `2026-10-20T19:23:35.998073621Z` |
| RELEASES | `2026-10-20T19:23:37.514304052Z` |
| RUN_LIST | `2026-10-20T19:23:39.105617856Z` |
| RUN_DETAIL_EXAMPLE | `2026-10-20T19:23:40.787019157Z` |
| JOBS | `2026-10-20T19:23:42.437866782Z` |
| KAFKA | `2026-10-20T19:23:44.280587950Z` |

원문14필드와 고정6개 검사에는 주소·IP·본문·자격증명·예외 원문이 없습니다. `deniedRequestsTested=false`, `operatingConfigurationChanged=false`를 유지합니다. 단일 수집 창의 약9초는 순차 요청·대기·검증을 포함하며, 처리량·응답 지연 benchmark가 아닙니다.

## 원문과 실행 결합

GitHub의 run·job·단일 artifact와 ZIP entry를 확인한 뒤 원문 bytes를 변경 없이 보존했습니다. metadata는 run URL·source·실제 job 완료 시각·run/job conclusion·원문 SHA-256의6필드입니다.

| 파일 | 전체 bytes의 SHA-256 |
| --- | --- |
| summary.json | `af724c9a720956bd48ff09df7e4b3689f18796d03bc360d381bd70a0a67ade60` |
| run-metadata.json | `1373c0186834a033b2fda9400e9570d7a27175d47b80156f40882ef48627b75d` |

## 합성 검사와 실제 연결의 차이

로컬 Node24.19.0에서 새 GET16개·기존 full9의15개·TLS20개를 함께 실행해51개 통과·실패0·생략0을 확인했습니다. Linux PR의 [GET16개](https://github.com/DevDooly/devdooly-platform-lab/actions/runs/39482682754), [기존 full9의15개](https://github.com/DevDooly/devdooly-platform-lab/actions/runs/39482682662), [TLS20개](https://github.com/DevDooly/devdooly-platform-lab/actions/runs/39482682691)와 [main GET 오프라인 검사](https://github.com/DevDooly/devdooly-platform-lab/actions/runs/39482876316)도 성공했습니다. 이 합성 검사는 DNS·HTTPS를 mock으로 대체하므로 실제 CA·공개 응답 성공의 근거는 위 수동 실행과 별개입니다.

기존 full9는 원문 뒤 helper export만 추가했으며 원래 route·POST 격리 ACK와 동작을 유지합니다. [GET-only 실행기](../../../infra/public-https-get/README.ko.md)는 기존 URL 설정·대상 소유·main/manual/첫 attempt를 확인한 뒤 한 공개 IPv4에 고정하고 재시도 없이6개만 읽습니다. 새 토큰·SSH·별도 VM·서비스 설정 변경 없이 수행했습니다.

PASS는 당시 지정 HTTPS 응답과 DTO 계약 범위입니다. 현재 worker 프로세스의 생존·POST 차단·전체 서비스 무변경·장기간 가용성·SLA·인증서 자연 갱신을 증명하지 않습니다. 기동 복원·토큰 교체·자원 예산·PR102는 계속 보류하며, 이번 조회를 그 완료 근거로 쓰지 않습니다. 공개 화면 반영도 이 artifact만으로 완료 처리하지 않습니다.

## 근거 목록 연결

기존19개를 유지하고 수동 GET 관측 카드1개를 추가했습니다. 웹207개·생략0, 타입47파일 오류·경고·힌트0와 프로젝트 경로 두 페이지 빌드를 통과했습니다. 로컬1280px·390px에서 GET 검색·CI/CD·GitHub Linux CI 교집합1개, 원문 문서·고정 소스 링크, 본문17px·모바일 링크44px·가로 넘침 부재를 확인했습니다. 조건 초기화 뒤 전체20개 중6개·18개·20개 표시를 확인했습니다. 같은 main `bd4eb39881f7ddc85e82e75264ab3b8794c27098`의 [Pages39484421012](https://github.com/DevDooly/devdooly-platform-lab/actions/runs/39484421012) build/deploy와 [CI39484421037](https://github.com/DevDooly/devdooly-platform-lab/actions/runs/39484421037)의 verify·public-read-gateway가 성공했습니다(조건부 격리4개 job은 생략). 공개1280px·390px에서도 GET·CI/CD·GitHub Linux CI 교집합1개, 원문 문서·고정 소스 링크, 본문17px·모바일 링크44px·문서 폭1265px/375px의 가로 넘침 부재를 확인했습니다. 새 GET 재실행이나 미니 PC 배포는 하지 않았습니다.

## 후속 실제 관측 — 2026-10-21 UTC

[수동 실행39521322979](https://github.com/DevDooly/devdooly-platform-lab/actions/runs/39521322979)은 main의 첫 attempt에서 `offline`·`public_gets`가 성공했습니다. 지정 GET6개가 모두 HTTP200·`passed=true`이며 공개 DTO 검증을 통과했습니다. 위 첫 관측 원문과 당시 검증 기록은 그대로 보존합니다.

| 출처 | 후속 실제 기록 |
| --- | --- |
| 검사기 소스 | `33c5e8c0cf211dc3f4c622b98b40be0b48a3890b` |
| 응답에서 확인한 API 소스 | 6개 모두 `245d61a5749760a20918ab091d9410ce6735b1c0` |
| 수집 시작 → 완료(UTC) | `2026-10-21T00:26:48.755Z` → `2026-10-21T00:26:58.079Z` |
| 실제 job 완료(UTC) | `2026-10-21T00:27:02Z` |
| 결과 | `PASS / NONE`, 공개 IPv4·표준 TLS 확인 |
| 결과 원문 | [summary.json](hosted-39521322979/summary.json), 1,635bytes |
| 출처 metadata | [run-metadata.json](hosted-39521322979/run-metadata.json), 346bytes |
| 원문 SHA-256 | `8178a94d89d98df6e8ebb8ab01a949431880c75a9be3fb0da61963917de61e8e` |

`deniedRequestsTested=false`, `operatingConfigurationChanged=false`는 이 GET 실행의 범위입니다. POST·거부 경로·인증서 자연 갱신·worker 프로세스 생존이나 장기간 가용성을 확인한 결과가 아닙니다. 수집 구간은 단일 순차 관측이며 성능 benchmark가 아닙니다.

별도 공개 브라우저 관측에서는 작업 카드의 실시간 API 10초 조회, 실행기 소스 `6f551a16a8ed536bb126403234c41b9e9b266d43`와 관측 API 소스 `245d61a5749760a20918ab091d9410ce6735b1c0`의 구분, 새 실행 시작 `2026-10-21T00:20:05Z`, heartbeat의 `00:26:53` → `00:27:32 UTC` 전진을 확인했습니다. 이 화면 관측은 위 GET artifact가 증명한 항목과 별개입니다. GET artifact의 `JOBS.sourceCommit`은 관측 API 소스이며 실행기 소스·시작 시각·heartbeat를 담지 않습니다. DB의 RUNNING·heartbeat도 현재 프로세스나 lease 생존을 직접 확인한 값으로 해석하지 않습니다.

## 세 번째 실제 관측 — 2026-10-21 UTC

[수동 실행39533662559](https://github.com/DevDooly/devdooly-platform-lab/actions/runs/39533662559)은 main의 첫 attempt에서 `offline`·`public_gets`가 성공했습니다. 앞선 두 관측과 worker의 [신규 고정 입력 처리·자연 게시](../current-worker-fixture/README.md)를 보존하면서 현재 공개 GET 계약을 다시 확인했습니다. 이 GET artifact 자체는 신규 작업의 처리나 worker 생존을 검증하지 않습니다.

| 출처 | 세 번째 실제 기록 |
| --- | --- |
| 검사기 소스 | `0984634a5546b16df18f6d35d939d3d76e9cea2f` |
| 응답에서 확인한 API 소스 | 6개 모두 `245d61a5749760a20918ab091d9410ce6735b1c0` |
| 수집 시작 → 완료(UTC) | `2026-10-21T02:33:42.937Z` → `2026-10-21T02:33:52.437Z` |
| 실제 job 완료(UTC) | `2026-10-21T02:33:55Z` |
| 결과 | `PASS / NONE`, 공개 IPv4·표준 TLS 확인 |
| 결과 원문 | [summary.json](hosted-39533662559/summary.json), 1,635bytes |
| 출처 metadata | [run-metadata.json](hosted-39533662559/run-metadata.json), 6필드 |
| 원문 SHA-256 | `dd16fb4cf96fc4f18c901794fd971b0f763fd2a8b0d2527305fde88edbe1a815` |

아래 시각은 원문 응답의 나노초 표기를 그대로 보존했습니다. 지정6개 모두 HTTP200·`passed=true`입니다.

| 검사 | 응답 관측 시각(UTC) |
| --- | --- |
| SUMMARY | `2026-10-21T02:33:43.423330791Z` |
| RELEASES | `2026-10-21T02:33:45.103082180Z` |
| RUN_LIST | `2026-10-21T02:33:46.772267046Z` |
| RUN_DETAIL_EXAMPLE | `2026-10-21T02:33:48.491800755Z` |
| JOBS | `2026-10-21T02:33:50.204397434Z` |
| KAFKA | `2026-10-21T02:33:52.264594965Z` |

원문14필드와6개 검사, 같은 run·source의 단일 artifact를 확인해 원본 bytes를 보존했습니다. 새 토큰·SSH·별도 환경·POST·거부 경로·운영 설정 변경 없이 수행했으며, `deniedRequestsTested=false`, `operatingConfigurationChanged=false`를 유지합니다. 단일 순차 수집의9.5초는 성능 benchmark나 장기 가용성·SLA·인증서 자연 갱신의 근거가 아닙니다. 기동 복원·토큰 교체·자원 예산·PR102는 계속 보류합니다.

별도 안내 게시인 같은 main의 [Pages39533611898](https://github.com/DevDooly/devdooly-platform-lab/actions/runs/39533611898)은 build·deploy, [CI39533611971](https://github.com/DevDooly/devdooly-platform-lab/actions/runs/39533611971)은 verify·public-read-gateway가 성공했습니다. 조건부 격리4개 job은 생략됐습니다. 공개 desktop에서는 전체 근거21개 중 첫6개와 새 입력 검색1개, 근거·고정 소스 링크를 확인했습니다. 이 화면 확인은 GET6 응답 검사와 별도입니다. 이후 [실행 선택 항목의 ID·건수 표시](../run-selection/README.md)를 수정하고 로컬 화면 검증을 마쳤습니다.
