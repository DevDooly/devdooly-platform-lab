# Kafka DESCRIBE 권한 격리 시험 후보

Windows JDK21/Maven3.10.0의 새 staging에서 원 IT의 offline `test-compile -DskipTests` 한 회가 통과했다. 새 IT class 생성·TEST XML0·시험방법0·source/tool/settings/cache 공개 payload 불변을 확인했다. 이후 [첫 GitHub-hosted 실행 39136790510](https://github.com/DevDooly/devdooly-platform-lab/actions/runs/39136790510)은 준비 단계가 성공했으나 runtime이 `SETUP`·`UNEXPECTED`·`IT_FAILED`로 끝났다. 검증 완료0/예정1이며 실행 소유 자원 정리만 확인했다. 원 summary와 실행을 보존하고 원인·ACL 통과·관리자 상태 또는 소스 불변을 확인했다고 주장하지 않는다. 후속 진단의 결과는 별도 실행 기록으로 구분한다. 기존 Kafka 관측 CI7, 운영 PLAINTEXT 설정과 생산 Java는 그대로 보존한다. 합성 SASL_PLAINTEXT는 ACL/인증 계약 시험이며 TLS 기밀성 검증이 아니다.

후속 변경은 고정 `SetupStep`·`SetupCause`와 실패 marker의 `setupStep`·`setupCauseKind` 두 필드 및 runner의 엄격 파싱뿐이다. SETUP에서 최초 실패의 enum만 저장하여 뒤의 close 실패가 최초 분류를 덮지 않으며, 원 예외·메시지·동적 클래스명·topic/group·자격증명은 출력하지 않는다. 공개 summary의 두 필드는 SETUP 실패에서만 유한 값이고 그 밖에는 null이다. 원 호출·권한·timeout·retries·readiness·소유 cleanup은 바꾸지 않는다. 분류는 새 실행의 첫 SETUP 실패 관측이며 과거 실행 원인의 소급 증명이 아니다.

[진단 실행 39137979832](https://github.com/DevDooly/devdooly-platform-lab/actions/runs/39137979832)은 준비 성공 뒤 `SETUP/OTHER_GROUP_OFFSETS/TIMEOUT`에서 끝났고 소유 자원 정리를 확인했다. 이 순서 보정은 원 other-group offset 초기화·조회 두 호출을 primary fixture의 join·produce·commitSync 성공 직후로 옮긴다. 고정 offsets topic은 이미 partition1/RF1이며, [그룹 분할 계산](https://github.com/apache/kafka/blob/4.3.1/group-coordinator/src/main/java/org/apache/kafka/coordinator/group/GroupCoordinatorService.java#L399-L403)상 두 그룹은 같은 partition0을 쓴다. [첫 coordinator 조회의 내부 토픽 준비 경계](https://github.com/apache/kafka/blob/4.3.1/core/src/main/scala/kafka/server/KafkaApis.scala#L1182-L1199)를 primary fixture의 실제 가입·offset commit 성공 뒤에 두려는 변경이다. 두 호출의 10초 상한, 기존 join30초, 권한·재시도·전체 예산은 유지하며 내부 토픽 생성 호출을 추가하지 않는다. 관측된 timeout의 정확한 내부 원인은 아직 확인하지 않았고 보정 결과는 별도 실행 기록으로 구분한다.

## 실제 재사용 범위

새 `KafkaObservationAclIT`는 `infra/kafka-acl-ci/KafkaObservationAclIT.java`에 두고 기존 관측 package를 선언한다. 새 runner가 fresh staged API의 해당 test package 경로에만 바이트 그대로 추가한다. package-private `KafkaAdminAdapter.properties()/verifyLibrary()`, constructor, `Deadline`, service의 4인자 Factory 주입 접점을 직접 사용한다. private 필드·메서드·reflection은 사용하지 않는다. immutable properties 복사에서 security.protocol/sasl.mechanism/sasl.jaas.config만 변경하고 기존 client ID·read3초/close1초·metrics·client retries1을 보존한다. production Factory의 짧은 constructor/참조 확보/late close 제어 흐름만 test Factory에 명시한다.

전용 runner는 원 `infra/kafka-observation-ci/run_once.py`를 source 검증 뒤에만 읽어 로드한다. `command/checked_command`, `artifact_snapshot/tool_snapshot/private_environment`, `OwnedDocker`, `image_identity`, 명시 class/method 인자를 받는 `verify_xml`을 그대로 호출한다. 원 `prepare/run/main/source_snapshot`은 호출하지 않으며 전역 변경도 없다. 기존 source manifest109개와 원 manifest 자체 및 신규 Java/runner/README를 합친 113개를 고정한다. 저장소 API source는 기존106개 그대로여서 원 CI7의 inventory 조건을 유지하고, 새 staged API만 기존106+격리 IT1의 정확107개를 허용한다. 기존 manifest는 변경하지 않는다.

새 준비는 `test-compile -DskipTests`만 수행한다. 기존 API218·관측 CI7을 재실행하지 않는다. 현재 고정 Boot4.1.1 dependencies POM의 managed Surefire/dependency plugin 버전과 실제 하나의 JUnit platform engine 버전에서 provider/launcher를 가져와 미리 준비한다. 준비가 끝나면 JAR/POM/ZIP 및 Maven 도구를 고정하고, 소유 자원이 생긴 뒤에는 이미지·의존성을 받지 않는다. 첫 hosted 준비는 성공했지만 그 뒤 SETUP에서 종료되어 시험 통과 근거는 없다.

## 한 시험의 계약

정확한 한 방법은 `KafkaObservationAclIT#describeOnlyPrincipalObservesAndRejectsSelectedRpcs`다. 별도 `lab.kafka-acl.tests=true`와 disposable 입력이 있어야 한다.

1. 새 broker 안에서 합성 관리자만 target/다른 topic·group, record3·commit1 및 observer ACL3개를 준비한다. observer는 Cluster DESCRIBE와 정확 literal Topic/Group DESCRIBE만 받는다. wildcard resource, Topic READ, Group READ, WRITE, ALTER_CONFIGS는 추가하지 않는다.
2. 관리자 classic fixture는 member1·assignment1, 즉 target partition0 한 개를 실제로 배정받는다. 빈 topic에서 준비 poll을 마친 뒤 foreground poll은 하지 않는다. pinned client의 background heartbeat와 명시 `max.poll.interval.ms=300000`을 사용하며 전체 시험의 JUnit180초보다 길다. baseline과 after 모두 CLASSIC/non-simple/STABLE·같은 member/assignment를 요구하고 변동 시 실패한다. observer 단계의 Fetch·재가입·재시도는 추가하지 않는다.
3. 원 service `capture()` 한 회에서 start0/LSO3/commit1/lag2·owner1/비 poison을 확인한다. Factory와 기존 adapter의 identity 전후 동등/소유 Admin I/O thread close 확인도 그대로 적용된다.
4. 별도 같은 observer client에서 다른 topic describe·다른 group describe·target config 변경·offset commit·비 idempotent Produce의 정확한 Topic/GroupAuthorizationException을 요구한다. 비밀번호 하나만 틀린 client는 정확한 SaslAuthenticationException을 요구한다. timeout/다른 오류/성공은 통과하지 못한다. 실패 지점은 Rpc 고정 enum과 TOPIC_AUTH/GROUP_AUTH/SASL_AUTH/TIMEOUT/OTHER/NONE만 남긴다.
5. 관리자 전후 비교는 cluster/topic UUID/partition, group type/state/simple/member/assignment, committed/start/LSO/end, 선택 retention.ms 및 ACL3개다. 준비와 종료 단계의 합성 쓰기·가입·leave는 이 불변 구간에서 제외한다. 전체 broker 상태, 모든 쓰기 API 차단, 모든 metadata 비공개 또는 모든 JVM thread 종료를 주장하지 않는다. 정상 service는 상세 예외를 고정 관측 오류로 바꾸므로 정확한 거부 주장은 직접 RPC의 원인 클래스에만 근거한다.

Kafka 4.3 ACL 표의 modern group describe 권한 표기와 pinned broker4.3.1 구현은 다르다. 최초 profile은 DESCRIBE-only로 고정하며 실제 실패 시 자동 Group READ 추가·시험 재실행을 하지 않는다. Group READ를 별도 후속으로 부여한다면 가입/heartbeat/leave 부작용 권한임을 명시해야 한다. Topic READ도 함께 주면 OffsetCommit이 가능하므로 “모든 쓰기 차단”이라고 표현하지 않는다.

## 소유권·자원·비공개 자료

원 digest broker4.3.1/JDK21, internal bridge1·broker/JVM2만 만든다. host port·외부 broker·운영 자원에 접속하지 않는다. 각 container CPU1/memory1GiB/메모리+swap 총1GiB(추가swap0)/PIDs256, cap drop ALL/no-new-privileges와 원 tmpfs/mount/user 검증을 유지한다. 양 BROKER/CONTROLLER listener는 SASL_PLAINTEXT/PLAIN, StandardAuthorizer/deny-by-default, superuser는 합성 `acl_admin` 하나뿐이다. fresh 환경의 전체 Env를 image defaults+요청 설정과 RAM에서 정확히 비교하고 auth 선언을 검증한다.

합성 비밀번호는 새 private0600 `broker.env`와 staged target의 private0600 properties에만 쓴다. broker는 Docker `--env-file`로 받아 JAAS/비밀번호를 argv에 넣지 않는다. Docker native metadata 처리와 probe가 읽는 Config.Env에는 합성 credential 값이 RAM에 존재한다. 원문·hash·부분값을 공개하지 않는다. 원 JVM mount4개를 유지하고 별도 secret bind는 추가하지 않는다. private Maven/XML/credential/상태 자료는 artifact로 올리지 않고 새 hosted 환경과 함께 폐기한다. 운영 자격증명 조회는 없다.

준비는900초, 이미지 준비는 소유 resource 생성 전, workload는300초·finally cleanup은 별도90초다. 명령 출력은 기존 bounded RAM helper로만 받고 공개 로그에 복사하지 않는다. 소유 full64 ID/Created/nonce/source/run·resource/security 검증 후 정상 stop/rm만 수행한다. unknown create는 임의 채택하지 않으며 강제삭제·volume삭제·전역 prune은 없다. 정리는 credential/인증 성공을 요구하지 않는다. 실패와 정리 결과를 분리하고 실패를 성공으로 정규화하지 않는다.

PASS는 정확 class/method1·fail0/error0/skip0/Linux/Java21 XML, 고정 성공 denial5+authentication1 enum marker, source/JAR/tool 불변과 소유 cleanup이 함께 확인될 때만 가능하다. 공개 summary는 source/manifest/XML hash·고정 phase/cause/Rpc enum·counts/bool뿐이다. topic/group/principal 값, JAAS/비밀번호/원 예외/원 XML·broker 로그는 올리지 않는다. 인증 설정 선언 검증은 모든 Kafka 내부 동작의 독립 증명이 아니며 실제 broker 통과는 앞으로 확인해야 한다.

## 전용 manual workflow

연결된 전용 workflow는 manual `workflow_dispatch`, 기본 opt-in=false, main·정확 checkout SHA·GitHub-hosted Linux X64·run_attempt1·repo identity를 요구하는 독립 job이다. runtime opt-in 환경은 `KAFKA_ACL_RUNTIME_OPT_IN=true`, `SOURCE_COMMIT`, `GITHUB_RUN_ID/GITHUB_RUN_ATTEMPT/GITHUB_WORKSPACE` 등 GitHub 기본 metadata 및 Java21이다. repository secrets/credentials는 전달하지 않는다. 현재 shell/Maven dependency 준비가 네트워크를 쓰므로 PR/push에서 이 실행기를 자동 호출하지 않는다.

Root의 구체 source 검토 이후 다음 CLI를 같은 새 hosted 환경에서 순서대로 사용할 수 있다. manifest SHA는 최종 고정값을 workflow literal로 결합한다. 단계 실패 시 run을 반복하지 않고 owned cleanup만 수행한다. upload는 `.local/kafka-acl-ci-public/summary.json` 한 파일만, absence도 실패로 처리한다.

```text
python3 infra/kafka-acl-ci/run_once.py prepare --source-manifest-sha256 <SHA> --ack-fresh-hosted-kafka-acl-it
python3 infra/kafka-acl-ci/run_once.py run --source-manifest-sha256 <SHA> --ack-fresh-hosted-kafka-acl-it
python3 infra/kafka-acl-ci/run_once.py cleanup --source-manifest-sha256 <SHA> --ack-fresh-hosted-kafka-acl-it
```

공식 근거: [broker4.3.1 DescribeConsumerGroups](https://github.com/apache/kafka/blob/4.3.1/core/src/main/scala/kafka/server/KafkaApis.scala#L2430), [client4.2.1 handler](https://github.com/apache/kafka/blob/4.2.1/clients/src/main/java/org/apache/kafka/clients/admin/internals/DescribeConsumerGroupsHandler.java#L95), [ACL 표](https://kafka.apache.org/43/security/authorization-and-acls/), [classic heartbeat](https://github.com/apache/kafka/blob/4.2.1/clients/src/main/java/org/apache/kafka/clients/consumer/internals/AbstractCoordinator.java#L1356), [max.poll.interval.ms](https://kafka.apache.org/42/configuration/consumer-configs/#max.poll.interval.ms).
