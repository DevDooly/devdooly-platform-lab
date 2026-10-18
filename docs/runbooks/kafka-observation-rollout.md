# Kafka 관측 연결 절차

[로컬 검증](../evidence/kafka-observation/README.md) 뒤 새 source의 [격리 CI7](../evidence/kafka-observation/CI_ATTEMPT_7.md)에서 고정 IT1·skip0·source 불변·자기 자원 정리를 통과했다. 미니 PC 배포·host/Pages의 신규 Kafka 연결은 별도 gate다. 기존 job/worker·readiness·GitOps·RBAC·timer와 기본 false를 이 격리 성공만으로 바꾸지 않는다.

## 현재 실행 gate · 2026-10-18

[격리 CI7](../evidence/kafka-observation/CI_ATTEMPT_7.md)은 전체/verify와 필수5단계가 success이며 verifiedTests1·skip0·sourceBytesUnchanged/ownedResourcesRemoved true다. Offline/API prepare source gate의 기대 수는35/218이다. [CI2](../evidence/kafka-observation/CI_ATTEMPT_2.md)·[CI3](../evidence/kafka-observation/CI_ATTEMPT_3.md)·[CI4](../evidence/kafka-observation/CI_ATTEMPT_4.md)·[CI5](../evidence/kafka-observation/CI_ATTEMPT_5.md)·[CI6](../evidence/kafka-observation/CI_ATTEMPT_6.md)의 실패와 미관측은 보존한다. 신규 미니 PC/HTTP·ACL·전체 JVM thread·자동 Pages 연결은 미검증이며 main 반영 전 현재 데이터 backup·보존 점검 gate는 유지한다.

PR64의 API template은 기본 false env도 추가하며 Application은 main chart를 자동 sync한다. 이미지 제안 전이라도 API Recreate가 생길 수 있으므로 **PR64 main 반영 전에** fresh 보존 점검·현재 DB backup·정상 rollback 입력을 준비한다. 같은 main SHA의 Jenkins/Actions와 실제 이미지·draft GitOps 검증 뒤 API/web만 default false로 전환하고, 별도 config opt-in→host 수집→원래30분 자연 회차를 순서대로 확인한다. 기존 worker·DB·Kafka/Garage·PVC·offset·Docker·timer unit을 보존한다.

expected cluster ID는 기존 runtime.kafka SecretKeyRef를 재사용하고 실제 값은 읽거나 Git에 넣지 않는다. sourceCommit은 게시한 API 소스, topic/group은 기존 worker 설정, namespace는 현재 platform-lab을 유지한다. api.kafkaObservation은 enabled만 지원하며 임의 expectedClusterId 값을 values에 추가하지 않는다.

## Generic group 조회와 bounded retry1

변경 전 [CI6](../evidence/kafka-observation/CI_ATTEMPT_6.md)의 공개 값은 DESCRIBE_GROUP/RPC_TIMEOUT, own KAFKA_UNAVAILABLE/null과 RUN642였다. 고정 client4.2.1의 [generic 조회](https://github.com/apache/kafka/blob/4.2.1/clients/src/main/java/org/apache/kafka/clients/admin/internals/DescribeConsumerGroupsHandler.java#L105)는 새 group API를 먼저 사용하며 [GROUP_ID_NOT_FOUND 처리](https://github.com/apache/kafka/blob/4.2.1/clients/src/main/java/org/apache/kafka/clients/admin/internals/DescribeConsumerGroupsHandler.java#L340)에서 CLASSIC fallback 재시도를 준비한다. [tries 검사](https://github.com/apache/kafka/blob/4.2.1/clients/src/main/java/org/apache/kafka/clients/admin/KafkaAdminClient.java#L1460)와 [enqueue 경계](https://github.com/apache/kafka/blob/4.2.1/clients/src/main/java/org/apache/kafka/clients/admin/KafkaAdminClient.java#L4711)를 근거로 retry0이 전환을 막을 수 있다는 가설을 검토했고 상한을1로 바꾼 새 source가 격리 CI7을 통과했다. 정확한 timeout 메시지·전체 원인·모든 조건의 해결까지 확인한 것은 아니다.

RETRIES_CONFIG1은 CLASSIC 전용이 아니라 observer Admin client의 요청 재시도 상한이다. 실제 요청/최대 attempt 수는 미관측이며 두 번 시도했다고 채우지 않는다. generic describeConsumerGroups와 반환 GroupType·CLASSIC/단일 member/partition/target guard를 유지한다. read3초·close1초·caller4초, request/default timeout·단일 owner·poison·cleanup·offset shape·원래 성공 gate도 보존한다. 이는 시간 예산 증가나 main/backup/미니 PC gate 해제를 뜻하지 않는다.

## 1. 새 격리 broker에서 의미 확인

고정 source의 격리 CI7에서 IT1·skip0과 자기 자원 정리를 확인했다. 후속 source 변경은 새 격리 실행으로 다시 검증한다. KafkaObservationIT는 명시적인 `lab.kafka-observation.tests=true`와 별도 시험 설정을 요구하며 기존 미니 PC broker를 시험 대상으로 쓰지 않는다. 시험 driver의 합성 topic 생성·발행·consumer commit·transaction은 production 조회 API의 읽기 동작과 구분한다.

새 격리 환경에서 NO_COMMIT의 null, 양수 lag, 관측된0 lag, 미완료 transaction과 READ_COMMITTED LSO 차이, 대상 cluster/topic/group 검증을 확인한다. 시험 종료 후 자기 자원만 회수하고 기존 데이터·offset을 보존한다. 실제 broker 결과가 없으면 합성 Service19·HTTP6을 이 단계의 증거로 쓰지 않는다.

## 2. API 소스와 배포를 연결

검토한 backend/web/host 후보의 전체 source commit을 확정하고 같은 source의 CI·게시 이미지 digest·GitOps revision·실행 API image를 연결한다. 로컬 검사와 이미지 게시·배포 성공은 서로 다른 단계다. 현재 checkout5862의 별도 Cloud capture 기록은 수정하지 않는다.

`api.kafkaObservation.enabled`와 `LAB_KAFKA_OBSERVATION_ENABLED`는 기본 false다. 먼저 읽기 전용 관측에 필요한 broker 권한과 기존 고정 대상 설정을 확인한다. 코드가 Admin 조회만 사용한다는 사실은 broker ACL의 실제 허용/거부 증거가 아니다. 활성화에는 정확한 API source40자리·mini-pc 환경·기존 worker topic/group·expected cluster ID가 필요하다. private 설정·접속 주소·secret 값은 공개 문서/요약/로그에 넣지 않는다. 공개 요청의 query/body로 대상을 바꾸지 않는다.

실제 배포 후 내부 Service의 고정 GET만 검사한다. 성공은 계약18필드/8KiB/UTC/4초 구간/offset 관계를 만족해야 하며 sourceCommit은 **관측 API** 소스다. 현재 worker 생존·source 또는 DB/broker 원자 snapshot의 증거가 아니다. 미설정/실패는 고정 오류 응답이며 가짜0 lag 성공을 만들지 않는다. 늦거나 close가 불확실하면 poison 상태를 원인 기록과 함께 운영자가 처리하고 자동 client 재생성을 기대하지 않는다.

## 3. host 수집을 별도로 켜기

host의 `kafka_enabled` 역시 기본 false다. 기존 짧은 SA로 Service ClusterIP를 검증하고 고정 `/api/kafka/observation`을 읽는 경로만 연결한다. SA token/cookie를 앱 요청에 전달하거나 새 inbound 경로를 열지 않는다. 자동 게시에는 MINI_PC/DEPLOYED_KAFKA만 허용하고 격리 결과는 별도로 남긴다.

Linux에서 아직 제외된 SIGALRM2개와 새 단계의 실제 시간 예산·정리·기존 platform/jobs dispatch를 확인한다. Windows48개 중2 skip 결과를 Linux deadline 증거로 쓰지 않는다. 전체 monotonic145초·dispatch15초 reserve와 기존 systemd150초 바깥 경계를 유지하며 커널/정리까지145초 내 끝난다는 보장은 하지 않는다. 실패·late·잘못된 응답·과거 기록·다른 target에서 이전 유효 Kafka 파일과 원래 시각을 보존하고 새 입력만 생략한다. 기존 platform/jobs 게시가 계속되는지도 실제로 확인한다.

## 4. Pages 기록과 화면 확인

검토한 Pages v3에 별도 kafka_snapshot 입력과 Kafka publication artifact를 연결한다. 최초 미관측은 recordPresent:false이며 kafka.latest.json이나 예시 성공 값을 만들지 않는다. 기존v1/v2 platform/jobs baseline 복원과 마지막 성공 기록을 보존한다.

검증된 실제 host snapshot이 생긴 뒤 전체 원문 hash·source·수집 시각·scope가 새 Pages artifact/공개 파일과 같은지 확인한다. 동일 target의 같은 시각 충돌·더 오래된 기록·잘못된 JSON은 이전 기록을 덮어쓰지 않아야 한다. mandatory 이전v3 Kafka artifact가 누락/만료/손상되면 새 Pages 배포를 멈춘다. 이를 새 capture 실패만 생략하는 조건과 구분하며 이전 공개 파일을 삭제하는 fallback을 만들지 않는다.

실제 성공·NO_COMMIT·오래된 기록·일시 실패 화면을 desktop/mobile과 keyboard로 확인한다. 현재 screenshot은 미연결 상태만 보여준다. 원래30분 주기의 새 Kafka 수집/게시를 실제 확인한 뒤에만 자동 갱신 완료로 표시하며 기존 platform/job timer의 과거 성공 횟수를 재사용하지 않는다.

## 중단과 되돌리기

새 host 수집을 끄면 새 Kafka 입력을 생략하고 검증된 과거 기록은 원래 시각 그대로 유지한다. API opt-in을 끌 때도 미관측을0으로 만들지 않는다. 실패한 배포는 검토한 이전 digest/GitOps revision으로 되돌리고 기존 SQL·worker·topic/group offset·객체·PVC·다른 서비스를 보존한다. 이 관측 경로를 위해 offset commit/reset·topic 삭제·기존 클러스터 제거를 수행하지 않는다.

각 단계에서 source/digest/revision·허용 요약 hash·범위·원래 실패·남은 미관측을 기록한다. 이 절차를 작성했다는 사실은 real Kafka/Mini PC/공개 게시의 실행 또는 성공 기록이 아니다.
