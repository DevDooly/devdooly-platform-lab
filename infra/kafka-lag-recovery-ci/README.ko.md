# Kafka consumer 종료 후 backlog 복구 검증

새 hosted Linux broker에서 12개를 발행하고 consumer가 offset 0–3의 4개만 처리·commit합니다. 정상 close 뒤 group EMPTY와 end 12 / committed 4 / lag 8을 관측합니다. consumer가 없는 동안 6개를 더 발행해 end 18 / committed 4 / lag 14를 확인한 뒤, 같은 group의 새 consumer가 offset 4–17의 14개를 처리하고 committed 18 / lag 0에 도달하는지 검사합니다.

숫자는 합성 시험의 독립 기대 결과입니다. 운영 Kafka, DB 처리, 업무 멱등성, export 재처리, broker 재시작·HA·지속 처리량을 검증한 결과로 확대하지 않습니다. 정상 close와 새 client 생성이며 JVM·호스트 강제 종료가 아닙니다. 아직 실제 실행 결과는 없습니다.

## 실행 경계

- 별도 `kafka-lag-recovery.yml` workflow는 PR에서 새 순수 Python 검사와 별도 fresh staging의 Java compile-only 검사를 수행합니다. PR 단계에서 테스트·broker는 실행하지 않습니다. 실제 시험은 main의 수동 입력 `run_lag_trial=true`, 최초 attempt 1에서만 허용합니다. 기본값은 false입니다.
- 기존 source manifest 109개와 새 실행기·검사·설명·Java 및 검증한 compile helper를 합친 115개를 고정합니다. workflow는 manifest SHA를 담으므로 manifest에 포함하지 않습니다. 저장소의 API106·기존 실행기·기존 manifest를 수정하지 않습니다.
- 새 private staging에 API106과 외부 `KafkaLagRecoveryIT.java` 한 파일만 복사합니다. 준비는 `test-compile`, dependency 준비와 JUnit provider 다운로드뿐입니다. 기존 API 전체 테스트·기존 Kafka 시험을 다시 실행하지 않습니다.
- 기존 고정 Kafka 4.3.1·Temurin 21 image와 Docker 소유권 검사를 재사용합니다. 다운로드는 새 자원 생성 전까지만 허용하고, 실제 JUnit은 offline Maven으로 지정한 한 메서드만 실행합니다.
- nonce·source·run label을 가진 internal network 하나와 broker/JVM 두 컨테이너만 만듭니다. 포트 게시·host network·운영 mount·SSH·PAT·repository secret·SASL은 사용하지 않습니다. 각 컨테이너는 CPU 1·memory/swap 1GiB·PID 256, 권한 제거와 제한된 tmpfs를 유지합니다.
- broker namespace의 numeric loopback만 사용합니다. image 기본 환경과 fixture 환경의 정확한 병합, image ID·network·mount·실행 identity를 검사합니다. 새 topic/group은 UUID 소유 prefix만 정리합니다.

## 결과와 정리

JUnit XML 하나·정확한 class/method 하나·실패/오류/skip 0과 고정 `KAFKA_LAG_RECOVERY_RESULT` JSON 하나가 모두 필요합니다. marker 누락·중복·다른 key·예상과 다른 수치·원문 오류를 거절합니다. 실패 진단은 정해진 phase/cause만 보존합니다. 원문 JVM 출력·XML·환경·resource ID·topic/group은 artifact로 게시하지 않습니다.

source·staging·Maven 도구·dependency 해시가 유지되고 소유 자원 삭제까지 확인돼야 PASS입니다. 정리는 원래 nonce·source·run·ID·생성 시각·image·network·mount가 일치하는 자원만 처리합니다. 알 수 없는 생성·실패·cleanup은 자동 재실행하거나 기존 상태 파일을 삭제해 우회하지 않습니다. 실패 시에도 별도 cleanup 단계가 같은 소유 상태를 확인합니다.

공개 artifact는 `.local/kafka-lag-recovery-ci-public/summary.json` 하나이며 보존 기간은 7일입니다. dispatch 입력이 true인 것만으로 실행·복구 성공으로 기록하지 않습니다. 실제 실행 전 Root의 전체 소스 검토·manifest 고정·순수 검사·새 main SHA 확인이 필요합니다.
