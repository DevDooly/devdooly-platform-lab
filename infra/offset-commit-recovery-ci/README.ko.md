# 실제 offset commit 실패와 명시적 재개 검증

DB 처리는 끝났지만 Kafka offset commit이 실패한 경계를 격리 환경에서 검증합니다. 실제 `DispatchWorker.afterDbCommit` 직후 소유한 Kafka 프로세스만 일시 정지하고, 원래 `commitSync` 호출이 실패하도록 합니다. callback에서 예외를 만들어 실패를 대신하지 않습니다.

이 디렉터리의 새 검증은 운영 미니 PC·기존 서비스·PAT·repository secret을 사용하지 않습니다. PR에서는 순수 경계 검사와 새 Java 두 파일의 컴파일만 실행합니다. 실제 시험은 main의 첫 번째 수동 실행에서 `run_offset_commit_trial=true`를 선택해야 시작됩니다. 작성 또는 컴파일만 마친 상태는 실제 복구 성공 근거가 아닙니다.

## 검증 순서

1. 원 API106개를 새 staging에 복사하고 IT·Probe 두 파일을 추가합니다. API108개를 컴파일하고, Maven 의존성과 고정 digest 이미지 네 개를 먼저 준비합니다. 기존 API 원본과 이전 helper·manifest는 수정하지 않습니다.
2. 새 internal network 하나에 Kafka를 연결합니다. MariaDB·Garage·JVM은 그 Kafka 컨테이너의 network namespace를 공유합니다. host port·host network·별도 relay는 없습니다.
3. 합성 입력12개를 실제 DB에서 처리한 직후 Java가 private checkpoint를 기록합니다. 실행기는 같은 Kafka full ID·생성/시작 시각·image·label·mount·network를 확인한 뒤 pause하고 ACK합니다. DB·Garage·JVM은 계속 실행됩니다.
4. Java는 실제 `PAUSED_OPERATOR / CONSUME / OFFSET_COMMIT_FAILED` 지속 기록, fault child 종료·자원 닫힘·lease 해제를 확인합니다. 이 확인 전에는 Kafka를 다시 실행하지 않습니다.
5. 같은 Kafka를 unpause하고 ACK합니다. 실제 committed offset을 조회한 뒤, 일반 `run` CLI가 지속된 pause를 우회하지 못하고 명시적 `resume`이 기록되는지 확인합니다. 새 정상 실행기가 pending export와 필요한 완료 작업 재전달을 처리합니다.
6. 업무 행과 처리 시각 보존, 결과7·실패3·중복2·pending0, EXPORTED, 결과/실패 파일 두 개의 전체 내용·크기·SHA, 빈 실행 슬롯, Kafka end1·committed1·lag0을 확인합니다. 테스트 XML과 source·Maven artifact·tool·staging 불변도 확인합니다.

Kafka pause는 커널 TCP buffer를 비우지 않습니다. timeout 후 unpause 시 늦은 commit이 처리될 수 있어 첫 조회는 `NO_COMMIT/null` 또는 `OBSERVED/1`을 허용하고 실제 값을 기록합니다. offset을 reset하거나 강제로 맞추지 않습니다. 재전달0·1회는 실제 `Delivery.replay` 관측값이며 첫 offset 조회만으로 추정하지 않습니다.

## 격리 자원과 시간

| 역할 | CPU | 메모리·swap 상한 | PID | 파일시스템 |
| --- | --- | --- | --- | --- |
| Kafka | 1 | 1GiB | 256 | UID1000, data256MiB·secrets1MiB·shared config4MiB tmpfs |
| MariaDB | 1 | 1GiB | 256 | image 기본 entrypoint·user, data512MiB tmpfs와 자체 writable layer |
| Garage | 1 | 512MiB | 256 | UID1000, read-only root, meta64MiB·data128MiB·tmp32MiB tmpfs |
| JVM | 1 | 2GiB | 256 | host와 같은 numeric UID, read-only root, tmp256MiB와 해당 시험 staging/cache bind |

총 메모리 상한4.5GiB는 이번 GitHub hosted fixture의 cgroup 한도입니다. 보류한 운영 저장공간 예산·quota 정책은 적용하지 않습니다. Maven heap128MiB, parent Surefire512MiB, child256MiB이며 metaspace·native overhead를 포함한 실제 적합성은 실행에서 확인해야 합니다. DB entrypoint의 새 tmpfs 초기화와 Garage UID1000 tmpfs profile도 첫 실제 시험 전에는 검증된 것으로 취급하지 않습니다.

준비는 단일900초 안에 compile-only·의존성 준비·이미지 네 개 pull을 마칩니다. 실행에서는 새 pull 없이 캐시된 image identity를 확인합니다. 자원 생성부터 최종 XML·불변 검사까지 단일600초이며, cleanup에는 별도180초를 둡니다. workflow는 prepare16분·run15분·cleanup4분·upload2분, job45분입니다.

cleanup은 소유한 Kafka가 paused면 먼저 같은 identity를 확인해 unpause합니다. 이후 JVM→Garage→DB→Kafka→network 순서로 확인된 full ID만 stop/remove합니다. 알 수 없는 create 결과, identity 불일치, 잔여 자원은 성공으로 처리하지 않습니다. 전역 prune·volume 제거·운영 재시작은 수행하지 않습니다.

## 실행 경계와 출력

호스트는 fresh `ubuntu-24.04` GitHub Actions runner여야 합니다. 저장소·main ref·source SHA·첫 run attempt·명시적 opt-in을 함께 확인합니다. 로컬이나 운영 서버에서 직접 실행하는 절차가 아닙니다.

```sh
python3 -I -B infra/offset-commit-recovery-ci/run_once.py prepare \
  --source-manifest-sha256 "$OFFSET_COMMIT_MANIFEST_SHA256" \
  --ack-fresh-hosted-offset-commit-it
python3 -I -B infra/offset-commit-recovery-ci/run_once.py run \
  --source-manifest-sha256 "$OFFSET_COMMIT_MANIFEST_SHA256" \
  --ack-fresh-hosted-offset-commit-it
python3 -I -B infra/offset-commit-recovery-ci/run_once.py cleanup \
  --source-manifest-sha256 "$OFFSET_COMMIT_MANIFEST_SHA256" \
  --ack-fresh-hosted-offset-commit-it
```

`OFFSET_COMMIT_RUNTIME_OPT_IN=true`는 workflow의 수동 opt-in과 함께 필요합니다. 새 source manifest는 기존109개·기존 manifest·검토한 ACL compile helper·새 파일7개, 총118개의 exact path/byte/SHA를 고정합니다. workflow는 manifest SHA를 참조하므로 순환 hash를 피하도록 manifest 대상에서 제외하며 checkout source SHA에 묶습니다.

private 상태·환경 파일·phase·native log·SQL·XML은 `.local/offset-commit-recovery-ci/private` 안에만 둡니다. phase는0700 디렉터리의0600 단일 링크 일반 파일이며 source/run/nonce/고정 phase의 canonical JSON만 허용합니다. 공개 artifact는 `.local/offset-commit-recovery-ci-public/summary.json` 하나이며7일 보존합니다.

공개 결과에는 고정 상태·합성 집계·검증 bool·source/manifest/XML hash와 실제 commit/replay 관측만 남깁니다. 실패 진단은 고정 stage, `runner|owner|base`, 실제 source line만 투영하며 일반 guard의 raise 줄은 건너뜁니다. 예외 종류·본문·경로·환경·credential·실제 컨테이너 ID는 출력하지 않습니다. 준비 실패는 같은 유한 진단을 workflow stdout에 남기며 실제 복구 결과 JSON을 만들어내지 않습니다.

### JVM 조기 종료 진단

첫 실제 실행 `39417413600`은 `POST_DB_WAIT`에서 실패했습니다. 준비·고정 이미지 네 개 pull과 DB/Garage 초기화·layout·key 권한 확인은 마쳤지만, 첫 DB commit checkpoint 전에 JVM이 종료했습니다. 테스트 검증 수는0이고 원인 분류 근거가 부족하므로 이 기록을 복구 성공으로 해석하거나 원인을 추정해 기능을 수정하지 않습니다. 해당 실행의 소유 자원 정리는 확인됐습니다.

다음 진단 변경은 이미 종료한 동일 소유 JVM의 identity를 다시 확인한 뒤 exit code·OOM 여부를 기록합니다. `docker logs --tail 200`을 최대5초·합계1MiB 안에서 메모리로만 읽고 재차 같은 종료 상태를 확인합니다. 원문을 파일·artifact·stdout에 저장하지 않으며 기존 cleanup 순서를 바꾸지 않습니다.

새 `jvmFailure`는 성공 시 null입니다. 실패 시 확인 가능한 exit/OOM, native log 읽기 상태, 고정된 관측 signature enum, 엄격히 하나인 해당 JUnit testcase의0/1 집계, hash가 일치하는 공개 Java 네 파일의 최대8개 source line, 고정 Java failure phase만 투영합니다. 알려지지 않은 class·파일·message·주소·credential은 포함하지 않습니다. signature는 로그에서 그 문구를 관측했다는 뜻이며 근본 원인이 확정됐다는 뜻이 아닙니다. XML 집계도 `verifiedTests`나 테스트 성공을 대신하지 않습니다. 진단 자체가 실패하거나 JVM identity/종료가 미확인이면 null을 유지합니다.

Java 실패 marker는 정확6개 필드입니다: `schemaVersion`, `status`, `failureCode`, `failurePhase`, `failureKind`, `failureSourceLine`. `VALIDATION_FAILED`와19개 허용 phase를 유지하고, 원 Throwable에서 분류한11개 고정 kind와 원 own IT frame의 첫 source line을 추가합니다. kind는 `ASSERTION`, `INTERRUPTED`, `SQL`, `GROUP_NOT_FOUND`, `UNKNOWN_TOPIC`, `COORDINATOR_NOT_AVAILABLE`, `COORDINATOR_LOAD_IN_PROGRESS`, `NOT_COORDINATOR`, `TIMEOUT`, `KAFKA_OTHER`, `OTHER`입니다. `ExecutionException`·`CompletionException`만 최대8단계 풀며 cycle·원인 부재·한도 초과는 `OTHER`로 분류합니다. 원 exception class나 message는 출력하지 않습니다.

`failureSourceLine`은 새로 던진 일반 assertion의 줄이 아니라 잡은 원 Throwable의 첫 own IT frame에서 읽습니다. 원 trace 최대64개를 보고1~10000의 실제 줄만 허용하며 해당 frame이 없으면 null입니다. runner는 정수 줄을 공개하기 전에 새 manifest에 고정한 실제 IT bytes의 SHA와 전체 줄 수를 재검증합니다. 틀린 hash·범위·타입이면 해당 Java failure 투영을 버리고 이미 확인한 exit/OOM·기존 실패 판정은 보존합니다. Spring context가 test method 진입 전에 실패하면 Java marker가 없을 수 있어 고정 native signature·해당 JUnit error 집계를 함께 확인합니다. 원래의 `selectedFailure`는 유지합니다.

두 번째 실행 `39418943100`은 실제 exit1·OOM false와 해당 JUnit testcase의 failure1/error0을 확인했고 Java phase가 `KAFKA_CREATE`였습니다. 따라서 Spring·전용 schema·서비스 guard 이후 초기 cluster/topic/offset 확인 구간의 실패라는 범위까지 좁혔습니다. 일반 assertion으로 치환하면서 원 조건·kind가 사라져 정확한 원인은 아직 모릅니다. 새6필드 진단은 그 정보를 보존하기 위한 변경이며, 검증 조건·성공23필드·phase protocol·기능 동작은 바꾸지 않습니다. 앞선 두 실패 기록과 정리 확인은 보존합니다. 실제 원인 확인 전 기능 수정이나 성공 주장을 하지 않습니다.

### 첫 group offset 관측의 준비 대기

세 번째 실행 `39420607863`은 초기 `listConsumerGroupOffsets(group)`의10초 대기에서 실제 `TIMEOUT`을 확인했습니다. 아직 입력·DB commit fault에 도달하지 않았으며 소유 자원 정리는 확인됐습니다. 이는 socket이 열렸어도 첫 group coordinator 조회가 준비됐다는 근거는 아니라는 뜻입니다. broker 내부의 정확한 지연 원인을 확정한 것은 아닙니다.

이 관측에 따라 fault 전의 첫 empty offset 확인 한 곳만 별도 준비 대기로 분리합니다. 단일 monotonic45초 안에서 같은 새 group에 실제 empty 응답이나 실제 `GROUP_NOT_FOUND`를 받아야 합니다. 각 RPC의 `ListConsumerGroupOffsetsOptions.timeoutMs`는 남은 시간과10초 중 작은 값이며 future도 남은 전체 시간 안에서만 기다립니다. 완료한 RPC의 `TIMEOUT`·세 coordinator transient만 최대250ms 간격으로 다시 관측합니다. Java future 대기가 전체 한도를 소진하면 즉시 실패하며, 완료되지 않은 future를 취소해 추가 관측과 겹치지 않게 합니다.

nonempty offset·잘못된 partition·assertion·인증/권한·unknown topic·그 외 오류는 즉시 실패하고, interruption은 복원·전파합니다. timeout을 empty로 바꾸거나 group에 join하거나 내부 topic·offset을 만들거나 초기화하지 않습니다. 입력·fault 이후의 기존 offset 조회와 엄격한 absent/1·최종 commit/lag 조건은 그대로입니다. 성공23필드·실패6필드·phase19개·JUnit420초·실행기600초도 늘리지 않습니다. 이 변경의 실제 준비/복구 성공은 새 검토 소스의 후속 실행에서 확인해야 합니다. 앞선 세 실패 기록을 보존합니다.

이 시험은 한 broker의 일시 정지와 명시적 재개 경계입니다. broker/host 재시작·다중 broker HA·운영 복구·부하 상한을 증명하지 않습니다.

## 순수 검사

Linux에서 새 모듈 두 개의 순수 fixture 검사만 실행합니다. Docker·Java·Maven·네트워크·credential 접근은 없습니다. 정상/늦은 commit 두 결과, 관측 replay0/1, 위조 marker, private phase의 소유자·mode·symlink·hardlink, manifest 경계, native 자원의 identity·mount·예상 pause 단계·정리 순서를 검사합니다.

```sh
python3 -I -B -m unittest discover -s infra/offset-commit-recovery-ci -p 'test_*.py' -v
```

Windows에 맞춰 `O_NOFOLLOW`·UID 검사 등을 우회하지 않습니다. 원 API106개의 기존 테스트를 이 runner에서 다시 실행하지 않으며, PR compile-only와 수동 isolated IT의 성공 근거를 구분합니다.
