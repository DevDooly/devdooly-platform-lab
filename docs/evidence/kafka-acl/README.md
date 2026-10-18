# 격리 Kafka SASL·ACL 검증

## 네 번째 hosted 시험 통과

[GitHub hosted 실행 39139258898](https://github.com/DevDooly/devdooly-platform-lab/actions/runs/39139258898)에서 새 Kafka와 합성 자격증명을 사용하는 IT 1개가 통과했습니다. [실제 유한 summary](attempt-4.summary.json)는 해당 실행의 원 JSON을 바이트 변경 없이 보존합니다. [고정 소스 83e141ea](https://github.com/DevDooly/devdooly-platform-lab/tree/83e141eaf2d3269920ec8599fcd49241dd8f160b/infra/kafka-acl-ci)와 runtime manifest `d6689a47`을 사용했습니다. 아래 결과는 이 격리 시험의 범위이며 운영 Kafka 권한 검증이 아닙니다.

| 항목 | 실제 확인 |
| --- | --- |
| IT | 예정 1개·검증 완료 1개, `PASSED / COMPLETE` |
| 관측 principal | cluster·선택 topic·선택 group의 DESCRIBE profile |
| 허용 조회 | 실제 관측 서비스의 start·LSO·commit·lag·그룹 상태 확인 |
| 선택 상태 보존 | 선택한 관리자 조회 상태의 전후 일치 |
| 소스·산출물 | 고정 source와 검증 artifact 보존 |
| 정리 | 실행이 소유한 컨테이너·네트워크 제거 확인 |

거부 검증은 아래 고정 요청 6건입니다. 오류 분류는 제한된 enum으로 기록하며 원 예외문이나 합성 비밀번호는 공개하지 않습니다.

| 요청 | 관측한 분류 | 결과 |
| --- | --- | --- |
| 허용 범위 밖 topic 조회 | `TOPIC_AUTH` | 거부 |
| 허용 범위 밖 group 조회 | `GROUP_AUTH` | 거부 |
| 선택 topic 설정 변경 | `TOPIC_AUTH` | 거부 |
| 선택 group offset 변경 | `GROUP_AUTH` | 거부 |
| 선택 topic produce | `TOPIC_AUTH` | 거부 |
| 잘못된 비밀번호의 관리자 조회 | `SASL_AUTH` | 거부 |

선택 RPC 거부 5개와 잘못된 비밀번호의 인증 실패 1개를 확인했습니다. 모든 API·쓰기 경로의 차단을 증명하지 않으며 `allWritesBlocked`는 false입니다. 격리 SASL_PLAINTEXT/PLAIN 구성으로 TLS 기밀성은 검증하지 않았고, 모든 JVM thread의 종료·장기간 가용성·성능 SLA도 검증하지 않았습니다. 운영 Kafka 변경과 공개 실행 활성화는 하지 않았습니다. 이 summary에는 주소·자격증명·원시 로그가 없습니다.

## 앞선 실패와 후속 결과의 구분

| 실행 | 확인한 범위 | 원 기록 |
| --- | --- | --- |
| [39136790510](https://github.com/DevDooly/devdooly-platform-lab/actions/runs/39136790510) | SETUP·UNEXPECTED, 검증 완료 0개·소유 자원 정리 확인 | [첫 실패](ATTEMPT_1.md) |
| [39137979832](https://github.com/DevDooly/devdooly-platform-lab/actions/runs/39137979832) | OTHER_GROUP_OFFSETS·TIMEOUT, 검증 완료 0개·정리 확인 | [두 번째 실패](ATTEMPT_2.md) |
| [39138559079](https://github.com/DevDooly/devdooly-platform-lab/actions/runs/39138559079) | OTHER_GROUP_DESCRIBE·TIMEOUT, 검증 완료 0개·정리 확인 | [세 번째 실패](ATTEMPT_3.md) |
| [39139258898](https://github.com/DevDooly/devdooly-platform-lab/actions/runs/39139258898) | COMPLETE·PASSED, IT 1개와 선택한 거부·보존·정리 확인 | [네 번째 summary](attempt-4.summary.json) |

각 실행은 고유한 source와 새 격리 자원을 사용했으며 앞선 실패 JSON·본문을 덮어쓰지 않았습니다. 준비 호출의 순서와 fixture 재시도 설정을 정리한 뒤 이번 실행이 통과했지만, 이 결과만으로 앞선 timeout의 정확한 내부 원인이나 classic fallback 인과를 확정하지 않습니다. 권한 확대·시간 제한 증가로 우회한 결과도 아닙니다.
