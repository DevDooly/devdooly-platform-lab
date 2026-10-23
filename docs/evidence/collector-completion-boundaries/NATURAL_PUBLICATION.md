# 새 collector의 자연 수집과 Pages 게시 확인

2026-10-23 **20:41(KST)**의 기존 자연 회차에서 새 collector의 수집과 Pages 게시를 연결했습니다. [20:17:53 코드 교체](DEPLOYED.md) 뒤의 service 시작·완료, 서버의 새 수집 시각·소스, 해당 invocation의 Pages 요청을 대조했고, [Pages 39947822996 · attempt 1](https://github.com/DevDooly/devdooly-platform-lab/actions/runs/39947822996)의 build·deploy 성공과 공개 JSON 3개의 artifact 원문 일치를 확인했습니다. [공개 요약](summary.json)은 이 한 회차의 제한된 메타데이터입니다.

## 실제 연결한 시각과 소스

| 단계 | 2026-10-23 KST | UTC |
| --- | --- | --- |
| collector 한 파일 교체 완료 | 20:17:53.114686 | 11:17:53.114686 |
| timer의 마지막 trigger·service 시작 | 20:41:12 | 11:41:12 |
| platform 수집 완료 | 20:41:15.086039 | 11:41:15.086039 |
| service 정상 완료 | 20:41:17 | 11:41:17 |
| 같은 run의 build 완료 | 20:42:47 | 11:42:47 |
| 같은 run의 deploy 완료 | 20:43:01 | 11:43:01 |
| artifact·공개 JSON 대조 완료 | 20:48:01.007402 | 11:48:01.007402 |

timer·service를 전후 두 번씩 조회해 같은 메타데이터임을 확인했습니다. 보고된 trigger와 시작 시각은 같았으며 허용한 0~5초 창 안이었습니다. 이는 **systemd가 보고한 정밀도에서의 시각 상관관계**입니다. 초보다 세밀한 실제 선후관계나 timer가 유일한 기동 원인이었다는 사실을 증명하지 않습니다. 검증 과정에서 수동 cycle 호출·timer 주기 변경은 하지 않았습니다.

같은 service invocation의 제한된 공개 보고가 가리킨 run ID를 Pages 검증 입력과 대조했습니다. run·attempt·head·main branch·workflow 경로·event·저장소 신원을 확인했고 다른 run으로 대체하지 않았습니다. 관측 main과 Pages head는 `af19b912523fe00f461f07f856d3aa504bec614f`입니다. 운영 API 소스 `245d61a5749760a20918ab091d9410ce6735b1c0`과 worker 소스 `6f551a16a8ed536bb126403234c41b9e9b266d43`은 이 main과 구분합니다.

## 코드와 잠금 확인

읽기 전용 코드 점검에서 설치된 collector는 20,725바이트·SHA-256 `d87742d75e046a292615e078b279e01d22243c8d2b5d95f39258cd91945c05cf`로 유지됐습니다. service·timer 파일 pin과 root 소유·권한도 기대값과 일치했습니다.

수집 뒤 child lock 파일은 남아 있었고 root 소유·0600·regular file·단일 링크 조건을 만족했습니다. 외부 cycle lock은 상태 점검 당시 미점유였습니다. child lock 자체의 OS 잠금 소유는 별도로 조회하지 않았습니다. 파일을 유지하는 새 구현의 정상 동작과 일치하며, **운영 프로세스를 SIGKILL한 뒤 복구시킨 시험은 아닙니다**. 실제 SIGKILL 회귀는 [격리 Linux 시험](README.md)의 별도 근거입니다.

## 공개 파일과 같은 run의 artifact 대조

고정된 현재 DTO 계약으로 각각 검증한 뒤, 정확한 run/attempt 이름의 artifact와 고정 공개 HTTPS 파일의 **전체 bytes**를 비교했습니다. jobs·Kafka artifact의 publication 표식도 `recordPresent=true`였습니다. 통과한 최종 산출물 비교 실행기는 GitHub GET 6회·공개 HTTPS GET 3회를 사용했고 자동 재시도·다른 run fallback은 하지 않았습니다.

| 공개 JSON | 수집 시각(UTC) | bytes | artifact·공개 파일 공통 SHA-256 |
| --- | --- | ---: | --- |
| platform | 2026-10-23T11:41:15.086039Z | 1,377 | `f8f8c82820deb2bfde8a73296b3ea9058fd198d89791c69d33e96e9e37b36c7e` |
| jobs | 2026-10-23T11:41:15.187893980Z | 6,477 | `457a137974583c8fa8bf1f1d2930a9ea30b5ece0930e1a4162ce7ad6eae988c4` |
| Kafka | 2026-10-23T11:41:15.498797399Z | 562 | `529123464f7c8bff930e3245452a24835a05d9e2d821d831459a6d708354a70e` |

서버에서 선택해 확인한 platform 수집 시각·main/API 소스도 해당 artifact의 필드와 같았습니다. 이 대조와 공개 JSON의 전체 bytes 비교는 서로 다른 범위입니다. 서버 내부 전체 state JSON이나 모든 비공개 상태를 바이트 단위로 대조했다는 뜻은 아닙니다. ZIP 원문·관리 응답·PID·invocation 식별자·접속 정보·키·토큰은 공개 요약에 포함하지 않습니다. ZIP 전체의 메타데이터를 정제했다고 주장하지 않습니다.

첫 검증기는 API의 run 표시 이름을 workflow의 `name`과 같다고 가정해 `UNVERIFIED`로 종료했습니다. 고정 workflow의 `run-name`과 실제 event 확장값을 확인하고 비교 문자열 한 곳만 수정한 뒤 독립 검토를 거쳤습니다. 기존 실패는 그대로 보존하고 **같은 run·attempt**를 새 고유 결과 폴더에서 명시적으로 다시 GET 검증해 통과했습니다. 이는 검증기 전제의 교정이며 운영 Pages 장애나 자동 재시도가 아닙니다.

## 범위와 다음 작업

확인한 것은 **교체 뒤 자연 회차 한 번의 수집 → 해당 Pages 요청 → build/deploy → 공개 JSON 일치**입니다. 장기 가용성·운영 SIGKILL 복구·진행 중 호스트 장애·전체 wall-clock 상한·Pages 토큰 교체의 검증은 아닙니다. 공개 파일은 이후 정상 회차가 게시하면 달라질 수 있으므로 이 기록을 현재 상태의 실시간 보장으로 읽지 않습니다.

다음 웹 관측 이력의 순서 보호는 구현·검증 중이며 아직 완료로 표시하지 않습니다. Pages 토큰 교체·별도 환경의 K3s/Jenkins 기동 복원·자원 예산 정책·PR #102 보류는 유지합니다.
