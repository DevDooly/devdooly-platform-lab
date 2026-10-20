# Kafka consumer 종료 후 backlog 복구 — 실제 격리 검증

[GitHub-hosted 실행 39412343874](https://github.com/DevDooly/devdooly-platform-lab/actions/runs/39412343874)는 **2026-10-20 11:05:48 UTC / 20:05:48 KST**에 성공했습니다. 새 합성 broker에서 consumer를 정상 종료한 동안 backlog를 늘리고, 같은 group의 새 client가 저장된 commit 위치부터 실제 record를 읽어 따라잡는 범위입니다. [실제 유한 결과](summary.json)는 실행 URL·완료 시각과 원 summary의 전체 JSON 값을 함께 보존합니다.

## 네 단계의 관측

| 단계 | group 상태 | READ_COMMITTED LSO | committed offset | lag |
| --- | --- | ---: | ---: | ---: |
| 12개 발행 후 offset 0–3의 4개 처리·commit | STABLE | 12 | 4 | 8 |
| 첫 consumer 정상 close | EMPTY · member 0 | 12 | 4 | 8 |
| consumer가 없는 동안 6개 추가 발행 | EMPTY · member 0 | 18 | 4 | 14 |
| 같은 group의 새 consumer가 나머지 14개 처리·commit | STABLE | 18 | 18 | 0 |

첫 client는 `max.poll.records=4`로 실제 record 4개를 읽고 position 4를 commit했습니다. 새 client는 `auto.offset.reset=none`으로 시작하고 seek·reset·수동 assignment 없이 offset 4–17의 14개를 정확히 읽었습니다. record별 offset·key·value와 각각의 유일성, 최종 position 18을 검사했습니다. 숫자는 작은 합성 fixture의 결과이며 지속 처리량이나 처리 시간의 보장이 아닙니다.

같은 관측 service의 네 capture에서 target fingerprint가 같았고, 각 capture 앞뒤의 선택한 cluster·topic·group member·assignment·start/LSO/committed 상태가 같았습니다. observer owner thread 1개·비 poison과 offset을 바꾸지 않는 읽기를 확인했습니다. 처리·관측 assertions가 성공하고 consumer들이 닫힌 뒤에만 자기 topic/group을 정리했으며, runner는 소유 broker·JVM·network의 제거와 source·staging·도구·dependency 불변을 확인했습니다.

## 실행과 소스 연결

- 검증 소스: [`5e22dbec`의 KafkaLagRecoveryIT.java](https://github.com/DevDooly/devdooly-platform-lab/blob/5e22dbecfa4da458a563fd5fa1fc4c9c34a7ef17/infra/kafka-lag-recovery-ci/KafkaLagRecoveryIT.java), 메서드 `closedConsumerBacklogIsRecoveredByNewConsumerFromCommittedOffset`.
- 고정 입력: [같은 커밋의 runtime manifest](https://github.com/DevDooly/devdooly-platform-lab/blob/5e22dbecfa4da458a563fd5fa1fc4c9c34a7ef17/infra/kafka-lag-recovery-ci/runtime-manifest.json). [결과 JSON](summary.json)의 `runtimeManifestSha256`과 연결합니다.
- 실제 판정: 정확한 class/method의 JUnit XML 1개·testcase 1개·실패/오류/skip 0, 고정 성공 marker의 전체 값이 함께 맞아야 통과합니다. [실행 기록](https://github.com/DevDooly/devdooly-platform-lab/actions/runs/39412343874)과 결과의 `verifiedTests: 1`, `surefireXmlSha256`으로 연결하며 XML·JVM 로그 원문은 공개 artifact에 넣지 않았습니다.

## 범위와 남은 계획

운영 Kafka·실제 worker·업무 DB·export는 변경하거나 복구 시험에 사용하지 않았습니다. 정상 consumer close와 새 client 생성이며 프로세스 강제 종료·broker/호스트 재시작·정확히 한 번의 업무 처리·HA·성능 SLA를 입증하지 않습니다. 공개 실행 기능도 추가하지 않았습니다.

저장된 [네 단계 관측 화면](https://devdooly.github.io/devdooly-platform-lab/#kafka-lag-recovery)은 [PR127](https://github.com/DevDooly/devdooly-platform-lab/pull/127)의 main `1df9b6a30450999bb0860d206ca6eb78c9ee52ed`와 [Pages 실행 39414345653](https://github.com/DevDooly/devdooly-platform-lab/actions/runs/39414345653)으로 공개했습니다. 같은 main의 [컨테이너 CI 39414345608](https://github.com/DevDooly/devdooly-platform-lab/actions/runs/39414345608)도 통과했습니다. 이 이미지 게시 결과를 미니 PC에 배포한 것은 아닙니다.

2026-10-20 11:24–11:25 UTC에 공개 페이지의 1280px 데스크톱과 390px 모바일에서 단계 선택을 확인했습니다. 3단계의 EMPTY·end18·commit4·lag14, End 키의 4단계 STABLE·18·18·0과 모바일 ArrowRight의 2단계 EMPTY·12·4·8이 실제 기록과 맞았습니다. 페이지 전체의 가로 넘침은 없었고 모바일 단계 버튼은 2열로 표시됐습니다. 이는 저장된 기록의 표시·탐색 검증이며 새 메시지나 서버 작업을 실행하지 않습니다.

DB commit 후 Kafka offset commit 실패와 영속 pause/resume 경계는 별도 후속 계획입니다. timeout 이후 늦은 commit이 가능하므로 commit 부재를 단정하지 않는 시험을 준비합니다. 자격증명 회전과 자원 예산·PR102 접수 gate는 보류 상태를 유지합니다.
