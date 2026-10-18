# Kafka 격리 CI4: IT 종료 predicate 실패·정리 확인

2026-10-18의 [격리 CI4](https://github.com/DevDooly/devdooly-platform-lab/actions/runs/39089524581), attempt1/source `ff6415a6718f40d7e5f8bebb1b7b01937bbf982e`는 실패했다. Linux offline30·skip0 gate와 정상 API216·skip0을 요구하는 준비 단계는 통과했으나 고정 Kafka IT1 성공을 입증하지 못했다. [CI2](CI_ATTEMPT_2.md)와 [CI3](CI_ATTEMPT_3.md)의 실패 원문·진단을 그대로 보존한다.

| 확인한 항목 | 실제 결과 |
| --- | --- |
| 전체 CI/verify job | failure/failure |
| Offline harness/API prepare | success/success |
| IT 단계 | failure |
| 별도 cleanup/public summary upload | success/success |
| 공개 요약 | FAILED / IT_FAILED |
| 고정 IT1 검증 | verifiedTests0·skips null·XML hash null |
| source 후속 gate | sourceBytesUnchanged false |
| 자기 자원 정리 gate | ownedResourcesRemoved true |
| 별도 공개 진단 선택 | RUN549 1건 |

[공개 summary 원문](ci-attempt4.summary.json)은663 bytes·SHA-256 `bc03727edcb271385e6cb97f9792e5c0bd5da99156a12ec22ad71e09cc9dc5e2`다. [수집 receipt](ci-attempt4.collection.json)의 rawJobLogsRead:false는 원문 요약·허용 metadata 수집기 자체의 범위다. 후속 Root connector 진단은 공개 verify job text를 RAM에서 읽었으며 그 차이를 [선택·AST receipt](ci-attempt4.diagnostics.json)에 별도로 남긴다. 원문 text 저장·비공개 artifact·별도 provider stderr 수집은 하지 않았다.

고정 source SHA `2bc99f6d94c99ddf17311fbc0751a23e3329430758fd8eb360bd27dfede5d54d`의 [RUN549](https://github.com/DevDooly/devdooly-platform-lab/blob/ff6415a6718f40d7e5f8bebb1b7b01937bbf982e/infra/kafka-observation-ci/run_once.py#L549)는 `status == 0`, `State.Running is False`, `State.ExitCode == 0`을 함께 요구하는 전체 predicate다. 어떤 하위 조건이 달랐는지·실제 exit 값·private stdout/stderr 내용은 선택하지 않았다. XML 검증 전에 이 조건이 실패한 기록이며, 실제 IT 미실행·실행 완료·assertion 실패·Maven의 특정 원인을 이 한 줄로 판정하지 않는다.

새 broker의 bounded tmpfs 보완 뒤 CI3의 최초 실패 위치372 대신 이번549가 선택됐다는 차이를 기록한다. 이 결과로 전체 Kafka 관측이나 IT1 통과를 선언하지 않는다. ownedResourcesRemoved:true와 별도 cleanup success는 이 실행기의 소유·identity gate를 만족한 자기 자원 정리 결과다. 다른 서비스·자원 전체의 부재, ACL·HTTP·미니 PC 또는 전체 JVM thread 종료 검증으로 확대하지 않는다. sourceBytesUnchanged:false는 후속 불변 gate 성공 미확인이며 source 변경 확정이 아니다. XML null/verified0도 IT 미실행을 뜻하지 않는다.

다음은 공개 source의 종료 predicate와 Java/Maven 실행 경계를 읽어 새 후보를 검토하는 단계다. 새 후보의 Linux 검사·IT·cleanup 성공은 아직 없다. CI4 collector·run·부분 자원을 재실행하지 않는다. main63의 Iceberg9 공개 성공과 현재 서버의 이전 기록을 보존하고, main 반영 전 fresh 데이터 보존 점검·현재 backup·rollback 준비와 [rollout 절차](../../runbooks/kafka-observation-rollout.md)를 유지한다.
