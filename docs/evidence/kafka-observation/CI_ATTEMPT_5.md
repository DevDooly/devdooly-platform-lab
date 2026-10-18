# Kafka 격리 CI5: 고정 observer 실패 코드 확인

2026-10-18의 [격리 CI5](https://github.com/DevDooly/devdooly-platform-lab/actions/runs/39090066910), attempt1/source `f69b420e51a60ce61f0fffa708131f25524e46e6`는 실패했다. Linux offline33·skip0 gate와 정상 API216·skip0을 요구하는 준비 단계는 통과했으나 고정 Kafka IT1 성공을 입증하지 못했다. [CI2](CI_ATTEMPT_2.md)·[CI3](CI_ATTEMPT_3.md)·[CI4](CI_ATTEMPT_4.md)의 실패 원문과 진단을 보존한다.

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
| 고정 failure 분류 | OBSERVER_KAFKA_UNAVAILABLE·testSourceLine null |
| 후속 공개 assertion 진단 | RUN619 1건 |

[공개 summary 원문](ci-attempt5.summary.json)은663 bytes·SHA-256 `50922cd2128290c0644324c6b3329eb881852d470a9c69185b1a4d3e12802ec8`다. [수집 receipt](ci-attempt5.collection.json)의 rawJobLogsRead:false는 원문 요약·허용 metadata 수집기 자체의 범위다. 후속 Root connector 진단은 공개 verify job text를 RAM에서 읽고 exact 실행 명령 group의 고정 필드만 선택했으며 그 차이를 [선택·AST receipt](ci-attempt5.diagnostics.json)에 별도로 남긴다. 원문 text 저장·비공개 artifact·별도 provider stderr 수집은 하지 않았다.

고정 source SHA `187da24f9aa6163963522408807e6b64baf29c9dcbc0a2aa50d1032910ccc3d2`의 failure classifier는 owned Surefire report에서 **정확한 우리 ObservationFailure type와 Code12개 중 하나인 message의 쌍**일 때만 OBSERVER 고정 코드를 출력한다. 이번 선택값은 `OBSERVER_KAFKA_UNAVAILABLE`이고 공개 test source line은 null이다. 이는 고정 observer 코드의 분류 확인이다. Kafka의 특정 coordinator·transport·timeout·권한 오류 또는 다른 내부 예외 타입·메시지는 선택하지 않았고 원인을 확정하지 않는다. stacktrace가 없는 예외의 test line도 보완하지 않는다.

[RUN619](https://github.com/DevDooly/devdooly-platform-lab/blob/f69b420e51a60ce61f0fffa708131f25524e46e6/infra/kafka-observation-ci/run_once.py#L619)는 `status == 0`, `State.Running is False`, `State.ExitCode == 0`을 함께 요구하는 전체 predicate다. 어떤 하위 조건이 달랐는지·실제 exit 값·private stdout/stderr 내용은 선택하지 않았다. 앞선 finite failure 분류와 이 assertion 진단의 순서를 그대로 보존한다. 고정 IT1의 성공 XML gate는 통과하지 못했으며 실제 IT 미실행·전체 method 완료·특정 Maven 원인으로 확대하지 않는다.

ownedResourcesRemoved:true와 별도 cleanup success는 이 실행기의 소유·identity gate를 만족한 자기 자원 정리 결과다. 다른 서비스·자원 전체의 부재, ACL·HTTP·미니 PC 또는 전체 JVM thread 종료 검증으로 확대하지 않는다. sourceBytesUnchanged:false는 후속 불변 gate 성공 미확인이며 source 변경 확정이 아니다. XML null/verified0도 IT 미실행을 뜻하지 않는다.

다음은 고정 코드에 연결되는 공개 observer 경계를 읽고 필요한 최소 진단 후보를 검토하는 단계다. 새 후보의 Linux 검사·IT·cleanup 성공은 아직 없다. CI5 collector·run·부분 자원을 재실행하지 않는다. main63의 Iceberg9 공개 성공과 이전 운영 기록을 보존하고, main 반영 전 fresh 데이터 보존 점검·현재 backup·rollback 준비와 [rollout 절차](../../runbooks/kafka-observation-rollout.md)를 유지한다.
