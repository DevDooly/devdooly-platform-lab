# Kafka 격리 CI6: Describe Group의 고정 RPC timeout 분류

2026-10-18의 [격리 CI6](https://github.com/DevDooly/devdooly-platform-lab/actions/runs/39090703716), attempt1/source `724b1ca790f4782eb936a99423e9338b129f7fe6`는 실패했다. Linux offline35·skip0 gate와 정상 API218·skip0을 요구하는 준비 단계는 통과했으나 고정 Kafka IT1 성공을 입증하지 못했다. [CI2](CI_ATTEMPT_2.md)·[CI3](CI_ATTEMPT_3.md)·[CI4](CI_ATTEMPT_4.md)·[CI5](CI_ATTEMPT_5.md)의 실패 원문과 진단을 보존한다.

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
| 고정 RPC 분류 | DESCRIBE_GROUP / RPC_TIMEOUT |
| 고정 failure 분류 | OBSERVER_KAFKA_UNAVAILABLE·testSourceLine null |
| 후속 공개 assertion 진단 | RUN642 1건 |

[공개 summary 원문](ci-attempt6.summary.json)은663 bytes·SHA-256 `6849a475889409a7713758604d9d2c0fee1550f4191957f22948e3eef2ef1c8c`다. [수집 receipt](ci-attempt6.collection.json)의 rawJobLogsRead:false는 원문 요약·허용 metadata 수집기 자체의 범위다. 후속 Root connector 진단은 공개 verify job text를 RAM에서 읽고 exact 실행 명령 group의 고정 필드만 선택했으며 그 차이를 [선택·source 검증 receipt](ci-attempt6.diagnostics.json)에 별도로 남긴다. 원문 text 저장·비공개 artifact·별도 provider stderr 수집은 하지 않았다.

이번에 추가로 선택한 `DESCRIBE_GROUP / RPC_TIMEOUT`은 공개 adapter source `b26b8ed9449b62a6cb88d5432839ebe2b9a86494dc912be5ee7d880e1f0174fe`의 정확한 test opt-in 분류다. [공개 adapter](https://github.com/DevDooly/devdooly-platform-lab/blob/724b1ca790f4782eb936a99423e9338b129f7fe6/apps/api/src/main/java/io/github/devdooly/platformlab/jobs/observation/ReadOnlyKafkaAdmin.java)는 await의 ExecutionException에서 정확한 Kafka TimeoutException class를 고정 RPC_TIMEOUT으로 매핑하고, generic Describe Consumer Groups 조회에 DESCRIBE_GROUP stage를 붙인다. Python은 owned XML의 system-out에서 stage6·kind12·정확한3필드를 재검증한 뒤 고정값만 출력한다. 실제 내부 timeout 사유·예외 메시지·coordinator/transport/권한 세부 값은 읽거나 확정하지 않았다.

고정 runner source SHA `a645f8c670c12854c4149d7ff8b45f2072f20fc01de960113fe7cb1fdad111f6`의 own classifier는 정확한 우리 ObservationFailure type/Code 쌍을 `OBSERVER_KAFKA_UNAVAILABLE`로 분류했고 test source line은 null이다. [RUN642](https://github.com/DevDooly/devdooly-platform-lab/blob/724b1ca790f4782eb936a99423e9338b129f7fe6/infra/kafka-observation-ci/run_once.py#L642)는 `status == 0`, `State.Running is False`, `State.ExitCode == 0`의 전체 predicate다. RPC → own observer → RUN assertion의 선택 순서를 보존한다. 실제 exit 값이나 하위 조건·전체 method 완료·특정 Maven 원인은 이 기록으로 판정하지 않는다.

ownedResourcesRemoved:true와 별도 cleanup success는 이 실행기의 소유·identity gate를 만족한 자기 자원 정리 결과다. 다른 서비스·자원 전체의 부재, ACL·HTTP·미니 PC 또는 전체 JVM thread 종료 검증으로 확대하지 않는다. sourceBytesUnchanged:false는 후속 불변 gate 성공 미확인이며 source 변경 확정이 아니다. XML null/verified0도 IT 미실행을 뜻하지 않는다.

다음은 공개 client의 generic group 조회와 bounded retry 설정을 읽어 최소 후보를 검토하는 단계다. retry0이 이번 timeout의 정확한 원인이라고 확정하지 않으며 새 후보의 성공도 아직 없다. group type을 보존하고 read3초·close1초·caller4초 경계 및 원래 성공·정리 gate를 유지해야 한다. CI6 collector·run·부분 자원을 재실행하지 않는다. main63의 Iceberg9 공개 성공과 이전 운영 기록을 보존하고, main 반영 전 fresh 데이터 보존 점검·현재 backup·rollback 준비와 [rollout 절차](../../runbooks/kafka-observation-rollout.md)를 유지한다.
