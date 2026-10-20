# 공개 GET 응답 계약 — 첫 실제 관측

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

기존19개를 유지하고 수동 GET 관측 카드1개를 추가했습니다. 웹207개·생략0, 타입47파일 오류·경고·힌트0와 프로젝트 경로 두 페이지 빌드를 통과했습니다. 로컬1280px·390px에서 GET 검색·CI/CD·GitHub Linux CI 교집합1개, 원문 문서·고정 소스 링크, 본문17px·모바일 링크44px·가로 넘침 부재를 확인했습니다. 조건 초기화 뒤 전체20개 중6개·18개·20개 표시를 확인했습니다. 공개 게시와 반영 확인은 아직 예정입니다.
