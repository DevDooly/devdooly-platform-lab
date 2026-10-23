# 작업 수집기 교체 후 자연 수집·Pages 게시 연결

2026-10-23 **21:42:49–21:42:53(KST)**의 기존 자연 회차에서 새 작업 수집기의 수집과 [Pages39955401692](https://github.com/DevDooly/devdooly-platform-lab/actions/runs/39955401692) attempt1 게시를 연결했습니다. [21:18:16(KST) 코드 교체](DEPLOYED.md) 뒤 전진한 platform·job 수집 시각과 출처, 해당 실행의 build·deploy 성공, 공개 JSON3개와 대응 artifact의 전체 bytes 일치를 확인했습니다.

## 자연 회차와 수집 출처

| 항목 | 실제 확인한 값 |
| --- | --- |
| 배포 완료 기준 | 2026-10-23T12:18:16.815632Z |
| 설치된 job 코드 | 4,147바이트, SHA-256 b5c59fc15e3d06af1b7db34b9036e4141800df4e3aa65e29f785b79721e8f120; root0600·일반 파일·단일 링크 |
| 보존·바인딩 | 다른 Python 코드7개·unit2개 pin 유지, 설정 바인딩 RAM 대조·전후 안정 확인 |
| timer 보고 trigger | 2026-10-23T12:42:49Z |
| service 보고 구간 | 2026-10-23T12:42:49Z–12:42:53Z, success·exit0 |
| 보고된 trigger→start 간격 | 0초, timer/service 연결·전후 snapshot 안정 확인 |
| platform capture | 2026-10-23T12:42:51.053209Z, 최신 시도 success·NONE와 마지막 성공 시각 일치 |
| job capture | 2026-10-23T12:42:51.188091546Z |
| Kafka capture | 2026-10-23T12:42:51.514368828Z |
| 관측 main | [571f0ba3332c4ca8cb6ae711e71010dbc300ea76](https://github.com/DevDooly/devdooly-platform-lab/commit/571f0ba3332c4ca8cb6ae711e71010dbc300ea76) |
| 배포 API 소스 | 245d61a5749760a20918ab091d9410ce6735b1c0 |
| job 관측의 runtime 소스 | 6f551a16a8ed536bb126403234c41b9e9b266d43 |

platform과 job capture는 모두 교체 이후이며 해당 service의 보고된 초 구간에 속합니다. job 시각의9자리 소수초를 유지해 state와 artifact를 대조했습니다. timer·service의 초 단위 보고 상관은 유일한 기동 원인이나 subsecond 인과관계의 증명이 아닙니다. main·API·runtime 소스와 세 관측의 원래 시각을 각각 구분합니다.

## 정확한 Pages 실행과 공개 JSON

같은 invocation의 DISPATCHED가 가리킨 [Pages39955401692](https://github.com/DevDooly/devdooly-platform-lab/actions/runs/39955401692)는 attempt1·workflow_dispatch·head571f0ba3332c4ca8cb6ae711e71010dbc300ea76이며 build·deploy가 모두 성공했습니다. **2026-10-23T12:47:15.163697Z**에 그 run/attempt의 artifact JSON3개와 공개 JSON을 strict 계약으로 검증하고 전체 bytes가 같은지 비교했습니다.

| JSON | bytes | artifact·공개 HTTP의 동일 SHA-256 | strict 계약·전체 bytes 일치 |
| --- | --- | --- | --- |
| platform | 1,377 | 68f5882a5a0299ea7f5bbe3edd441f4b1da57078c76b47b1732963134617ce0e | 통과 |
| jobs | 6,474 | e6399c7bc68451619709a030576967340a469bd95bd4532ffc046a48c39d136d | 통과 |
| Kafka | 562 | 367b96a9052dc0d96e812ae8f131766bfdcada73ce9c343e97b501fa522215b0 | 통과 |

각 입력의 검증 뒤 로컬 결속 검사도 exit0·LOCAL_JOB_NATURAL_EVIDENCE_CHAIN_MATCHED로 끝났습니다. 같은 run/attempt/main/API와 platform·job의 state/artifact 수집 시각 일치를 nanosecond 정밀도로 확인했습니다. service 구간의 비교 정밀도는 reported-seconds이며 subsecondCausalityVerified는 false입니다.

검증을 위해 서비스 제어·수동 수집·수동 dispatch·설정·timer 변경은 하지 않았습니다. 비교 helper의 요청은 GitHub GET6회·공개 JSON GET3회였고 자격증명 파일을 읽지 않았습니다. 설정 본문·개별 프로세스 식별자·원시 로그·ZIP은 공개하지 않습니다.

## 범위와 한계

이 결과는 설치된 새 작업 수집기로 한 자연 회차의 수집과 실제 게시를 연결한 기록입니다. 교체 직후 남아 있던 [이전 state projection](DEPLOYED.md#별도-읽기-전용-사후-확인)과 이번 새 capture를 구분합니다. platform 게시 성공만으로 job 성공을 대신하지 않았습니다.

[응답 read·close 완료 시한](README.md)의 합성 회귀와 이번 정상 자연 회차는 서로 다른 검증입니다. 본문 수신의 즉시 중단·파싱과 파일 저장을 포함한 전체 처리 시간의 hard deadline·운영 장애 주입·장기 가용성·재부팅·인증서 자연 갱신은 이 결과의 범위가 아닙니다. Pages 토큰 교체·별도 K3s/Jenkins 기동 복원·자원 예산 정책·PR #102 보류와 운영 이미지 pin을 유지합니다.
