# Kafka 격리 CI7: 고정 IT1·소스 불변·자기 자원 정리 통과

2026-10-18 02:46:10 UTC의 [격리 CI7](https://github.com/DevDooly/devdooly-platform-lab/actions/runs/39091086684), attempt1/source `f7b5567963f9a34a34d5f201fb2ed747bdf7652a`는 전체 CI와 verify job이 success다. 고정 IT1·skip0, source 불변과 자기 자원 정리를 확인했다. [CI2](CI_ATTEMPT_2.md)·[CI3](CI_ATTEMPT_3.md)·[CI4](CI_ATTEMPT_4.md)·[CI5](CI_ATTEMPT_5.md)·[CI6](CI_ATTEMPT_6.md)의 실패·미관측·진단을 성공으로 바꾸지 않는다.

| 확인한 항목 | 실제 결과 |
| --- | --- |
| 전체 CI/verify job | success/success |
| Offline harness/API prepare | success/success; source gate 기대 수35/218 |
| 격리 IT/별도 cleanup/공개 summary upload | success/success/success |
| 공개 요약 | PASSED / failureCode null |
| 고정 IT1 검증 | verifiedTests1·skips0·source assertion 검증true |
| source/자기 자원 정리 | sourceBytesUnchanged true·ownedResourcesRemoved true |
| HTTP·미니 PC/ACL/전체 JVM threads | 각각 false |

[공개 summary 원문](ci-attempt7.summary.json)은713 bytes·SHA-256 `93378d456c9b9335285cae1a37d9680fb95cc6e0e834672b521cd4af0ea1f11e`다. XML SHA는 `575c64977083c6219d7554f75c816715f58823944fcabf46fbb45f1a80fc0b3b`이며 [수집 receipt](ci-attempt7.collection.json)는 원문 bytes/hash와 exact source/run/attempt·5개 필수 step conclusion을 연결한다. 수집기는 이 public artifact와 허용 metadata만 읽었고 job log·비공개 artifact·provider stderr를 읽지 않았다. 35/218은 고정 workflow/prepare의 기대 수이며 개별 JUnit 원문을 별도로 수집해 새 count로 기록하지 않았다.

## 통과 범위와 설정 변경

고정 [KafkaObservationIT source](https://github.com/DevDooly/devdooly-platform-lab/blob/f7b5567963f9a34a34d5f201fb2ed747bdf7652a/apps/api/src/test/java/io/github/devdooly/platformlab/jobs/observation/KafkaObservationIT.java)의 SHA는 `012998f6dd77c216f09fa120cc2c8d145932b922cb90a5ef1aa03efbf6ec4dc8`다. 단일 method의 NO_COMMIT null, commit1 이후 lag2·commit3 이후 lag0, 미완료 transaction을 포함한 READ_COMMITTED LSO3, 같은 group member·최종 commit 보존 및 observer poison false assertions가 통과한 범위다. 이 값은 고정 합성 시험 조건이며 별도 운영 관측 payload·처리량·SLA가 아니다.

이번 source는 observer Admin client의 RETRIES_CONFIG를0에서1로 바꾸고 generic group 조회·GroupType·offset shape guard와 read3초·close1초·caller4초를 유지한다. [변경 이유와 후속 gate](../../runbooks/kafka-observation-rollout.md)는 Kafka4.2.1의 CLASSIC fallback·retry 상한 흐름을 근거로 한다. CI6의 DESCRIBE_GROUP/RPC_TIMEOUT 뒤 새 source가 통과했다는 차이는 확인했으나, 실제 요청/최대 attempt 수·timeout 메시지·정확한 전체 원인 또는 모든 조건에서의 해결을 확인한 것은 아니다.

Runtime manifest는 `7e86afa4cf4c4b13459040e566cf43e876390146e49565f71751d2909d02a84c`, workflow는 `4056cefff307708e4f8362416c31593c16310b38ae9c5a9edd8e6c259401297f`다. Cloud source 불변/자기 자원 정리 gate와 collector의 로컬109 입력 전후 hash 검사는 서로 다른 검증이다. 전체 JVM thread 종료·ACL·HTTP API/미니 PC 배포·자연30분 Pages 게시는 이 결과에 없다.

main63의 Iceberg9 공개 성공은 보존한다. 다음은 PR64 main 반영 전 fresh 데이터 보존 점검·현재 DB backup·rollback 입력을 확인하는 단계다. 같은 main SHA의 Actions/Jenkins·이미지 digest·기본 false 배포·별도 API opt-in·host/Pages 연결은 각각 새 결과로 확인한다. 기존 서비스·worker·데이터·offset·PVC·timer를 이 격리 성공만으로 바꾸지 않는다.
