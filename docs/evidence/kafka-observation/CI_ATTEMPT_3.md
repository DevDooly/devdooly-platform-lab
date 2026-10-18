# Kafka 격리 CI3: 실패 predicate 선택

2026-10-18의 [격리 CI3](https://github.com/DevDooly/devdooly-platform-lab/actions/runs/39088277065), attempt1/source `0e694af3ed0f915dad178f816f2c9d742ca9b183`는 실패했다. Linux offline28·skip0 gate와 정상 API216·skip0을 요구하는 준비 단계는 통과했지만 IT 단계와 cleanup은 실패했다. [CI2](CI_ATTEMPT_2.md)와 이전 실패를 그대로 보존한다.

| 확인한 항목 | 실제 결과 |
| --- | --- |
| 전체 CI/verify job | failure/failure |
| Offline harness/API prepare | success/success |
| IT/cleanup/public summary upload | failure/failure/success |
| 공개 요약 | FAILED / RESOURCE_IDENTITY_UNVERIFIED |
| 고정 IT1 검증 | verifiedTests0·skips null·XML hash null |
| 후속 gate | sourceBytesUnchanged false·ownedResourcesRemoved false |
| 선택한 진단 순서 | RUN372 → CLEANUP320 → CLEANUP320 |

[공개 artifact 원문](ci-attempt3.summary.json)은683 bytes·SHA-256 `0d6af47f3089271ae2f0573dcecb5b0fcfdd80daf3db3a4a3374ba74a17d580a`다. [수집 receipt](ci-attempt3.collection.json)는 해당 원문·허용 public metadata만 수집한 기록이다. 그 수집기의 `rawJobLogsRead:false`를 별도 후속 진단에 확대하지 않는다.

## 공개 source에 연결한 진단

후속으로 Root가 별도 GitHub connector를 통해 **공개 verify job text를 RAM에서 읽고**, 정확한 run/cleanup 명령 group 아래의 kind·phase·line 3필드만 선택했다. [선택·AST 검증 receipt](ci-attempt3.diagnostics.json)는 source95372의 원문 SHA와 실제 assertion statement에 이 3records를 연결한다. 원문 text를 저장하지 않았으며 비공개 artifact·별도 provider stderr·실제 inspect 필드 값은 수집하지 않았다.

고정 source SHA는 `95372ee4700c20a42a9cdc915bfefdb110d443eea3b2de86661e40a08f1c39a3`이다. [RUN372](https://github.com/DevDooly/devdooly-platform-lab/blob/0e694af3ed0f915dad178f816f2c9d742ca9b183/infra/kafka-observation-ci/run_once.py#L372)는 선언 VOLUME이 null이거나 예상 tmpfs 경로의 부분집합인 dict인지 검사하는 predicate다. [CLEANUP320](https://github.com/DevDooly/devdooly-platform-lab/blob/0e694af3ed0f915dad178f816f2c9d742ca9b183/infra/kafka-observation-ci/run_once.py#L320)은 ledger의 createdAt 문자열과 실제 Created의 일치를 검사하며 두 번 선택됐다. 복합 조건의 어느 하위 값이 달랐는지는 이 기록으로 특정하지 않는다.

Apache Kafka [고정4.3.1 공식 Dockerfile](https://github.com/apache/kafka/blob/4.3.1/docker/jvm/Dockerfile)은 `/etc/kafka/secrets`, `/var/lib/kafka/data`, `/mnt/shared/config`를 VOLUME으로 선언한다. 기존 runner의 broker expected tmpfs는 data 한 경로만 포함한다. 이는 공식 이미지 선언 전체를 명시 tmpfs로 덮지 못하는 구성 범위를 보여주지만, 수집하지 않은 실제 Config.Volumes 값이나 전체 runtime 원인을 증명하지 않는다. 새 후보는 기존 data256MiB에 secrets/config 각1MiB의 bounded tmpfs를 추가하고 anonymous volume·bind·예상 밖 mount 거부는 유지한다. Root의 새 Windows 집중 합성2개·skip0은 통과했다. **후보의 새 Linux30·실제 Kafka IT·cleanup 성공은 아직 검증하지 않았다.**

XML null/verified0은 고정 IT1 성공 미입증이며 IT 미실행을 뜻하지 않는다. sourceBytesUnchanged false는 source 변경 확정이 아니고 ownedResourcesRemoved false는 자원 부재·누수·완전 정리를 확정하지 않는다. source109 전후 일치는 collector의 로컬 입력 검사다. 미니 PC·HTTP·ACL·전체 JVM thread 종료와 자연30분 Pages 게시도 이번 CI3에서 검증하지 않았다.

## 다음 단계와 기존 데이터 보존

main63의 Iceberg9 공개 성공과 이전 미니 PC Kafka 운영 기록은 이번 신규 관측 전환과 구분한다. 다음은 검토한 VOLUME 후보의 새 source에서 Linux30·격리 IT1·정리 gate를 확인하는 단계다. 이전 run·once collector·불확실 부분 자원을 통째로 재실행하지 않는다.

main 반영은 chart의 기본 false env만으로도 API Pod template이 바뀔 수 있으므로 fresh 보존 점검·현재 DB backup·rollback 입력을 먼저 요구한다. 현재 데이터 건수 제약 보완은 별도 **Windows 합성18개(새14+기존 SQLite4), skip0·실패0·오류0**에서 통과했다. 이는 Linux 권한·현재 서버 DB의 실제 백업·복원 성공이 아니며 기존 자료를 삭제하지 않았다. 이후 같은 main SHA의 Actions/Jenkins, 이미지 digest, 기본 false 배포와 관측 연결은 [rollout 절차](../../runbooks/kafka-observation-rollout.md)를 따른다.
