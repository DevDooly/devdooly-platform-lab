# Kafka 격리 CI2: identity 검사 실패

2026-10-18의 [격리 CI2](https://github.com/DevDooly/devdooly-platform-lab/actions/runs/39087599550), attempt1/source `07d572fa3a32b5b0cf7183d13f56ca728c6be815`는 실패했다. 새 offline24와 API 준비 검증은 통과했으나 실제 IT 단계와 cleanup이 실패했다. Kafka 관측의 실제 broker·미니 PC·자동 Pages 연결 완료로 기록하지 않는다.

Runtime manifest는 `a414e6d39689c4656a8a68bbca0e65e6e474a32897cbbce19bcd6ae2e51d1e00`, workflow는 `b0f48e5c90e05234e12e049c9ba7474ddc699fba3191f828ec3711d762788153`이다. 고정 IT source는 `012998f6dd77c216f09fa120cc2c8d145932b922cb90a5ef1aa03efbf6ec4dc8`다.

## 확인한 결과

| 단계/허용 필드 | 실제 결과 |
| --- | --- |
| Source-pinned offline harness | success·고정24개/skip0 gate |
| Verify API | success·정상 API216개/skip0을 요구하는 prepare gate |
| Run one owned Kafka observation IT | failure |
| Confirm owned Kafka cleanup | failure |
| Public summary upload/수집 | success/COLLECTED |
| 전체 CI/verify job | failure/failure |
| 공개 summary | FAILED / RESOURCE_IDENTITY_UNVERIFIED |
| 고정 IT1 검증 | verifiedTests0·skips null·surefireXmlSha256 null |
| 후속 검증 boolean | sourceBytesUnchanged false·ownedResourcesRemoved false·testSourceAssertionsVerified false |

[공개 artifact 원문](ci-attempt2.summary.json)은683 bytes·SHA-256 `0a232896716b19f61b5bf1df0c5ec4665a4a70feb1a6bea3f757c0317d81a2d8`다. [선택 metadata와 수집 검증](ci-attempt2.collection.json)은 source/run/attempt·step conclusion과 원문의 bytes/SHA를 연결한다. 수집은 public summary와 허용 metadata만 사용했으며 private artifact·provider stderr·원시 job log는 읽지 않았다.

`sourceBytesUnchanged:false`는 실제 source가 바뀌었다는 확정 증거가 아니다. `ownedResourcesRemoved:false`도 자원 부재·완전 정리 또는 누수를 각각 확정하지 않는다. XML hash가 null이고 verified0이므로 고정 IT1 통과는 입증되지 않았다. 실제 test 실행 여부·exit·어느 identity 필드에서 실패했는지·남은 자원 상태는 이 공개 요약만으로 알 수 없다.

수집기의 local source109 전후 hash 일치는 로컬 수집 입력의 검사다. Cloud runtime의 source 불변 검증으로 옮기지 않는다. collection의 runtimeCalled:false 역시 **수집기 자체가 runtime을 실행하지 않았음**을 뜻하며 CI의 IT 실행 여부를 판정하는 값이 아니다. 미니 PC/HTTP·ACL·모든 JVM thread 검증 flag는 false다.

## 이전 실패와 다음 gate

[첫 실행](https://github.com/DevDooly/devdooly-platform-lab/actions/runs/39086780742), source `d99cca285a13784b7183dc2a682d8d4cd2246e3b`는 기존 Spark workflow assertion에서 실패했다. 새 harness/API/IT step은 skipped였고 별도 cleanup의 고정 SOURCE_CHANGED code와 공개 artifact MISSING을 보존한다. 기존 source의 wrapper properties CRLF/LF 차이와 assertion을 보정해 새 source의 CI2를 실행했으며 첫 실패를 성공으로 바꾸지 않았다.

다음은 CI2의 source/identity guard를 읽기 전용으로 진단하고 필요한 새 후보를 검토하는 단계다. 원인·수정·새 실제 IT/cleanup 성공이 확인되기 전에는 PR64 main 반영과 미니 PC rollout gate를 열지 않는다. 예전 run·once collector·부분 자원을 통째로 재실행하지 않는다.

PR64의 chart는 기본 false인 env 추가도 API Pod template을 바꿀 수 있고 Application이 main을 자동 sync한다. 따라서 main 반영 **전** fresh 보존 점검·현재 DB backup·rollback 입력을 준비한다. 이후 같은 main SHA의 Jenkins/Actions·실제 이미지 digest·GitOps·기본 false 배포·고정 Kafka API·host optional collector·자연30분 게시를 각각 검증한다. [연결 절차](../../runbooks/kafka-observation-rollout.md)를 따른다.

별도 기존 미니 PC API 읽기 성공과 main63의 Iceberg9 공개 성공은 이번 신규 Kafka 관측 전환의 성공이 아니다. 앞선 Iceberg1–8 실패·9차 PASS·로컬 합성 검증과 기존 업무 자료를 보존한다.
