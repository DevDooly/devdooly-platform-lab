# Kafka 관측 연결 절차

현재는 [로컬 검증](../evidence/kafka-observation/README.md)까지 완료한 소스 후보다. 기존 job/worker·readiness·운영 GitOps·RBAC·host timer를 이 문서만으로 바꾸지 않는다. 새 관측을 끄는 기본값을 유지한 채 아래 단계의 실제 결과를 구분해 기록한다.

## 1. 새 격리 broker에서 의미 확인

현재 real Kafka IT는 실행하지 않았다. KafkaObservationIT는 명시적인 `lab.kafka-observation.tests=true`와 별도 시험 설정을 요구한다. 실행기부터 새 자기 broker·자원 소유권·종료와 정리 범위를 확인해야 한다. 기존 미니 PC broker를 시험 대상으로 쓰지 않는다. 이 시험의 driver는 합성 topic 생성·발행·consumer commit·transaction을 수행하므로 production 조회 API의 읽기 동작과 구분한다.

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
