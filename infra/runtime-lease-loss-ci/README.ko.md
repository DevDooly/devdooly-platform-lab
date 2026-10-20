# 실제 named-lock 연결 손실 뒤 다음 작업 차단

MariaDB named lock을 가진 전용 connection 하나를 실제로 종료한 뒤, production 소유권 검사가 다음 publisher·receiver 호출을 막는지 확인하는 격리 실험입니다. 연결 손실 후 DB journal에 pause를 저장할 수 있다고 가정하지 않습니다. 현재는 검토 후보이며 실제 실행의 성공 근거가 아닙니다.

기존 fake lease·mock JDBC 검사와 달리 실제 DB session·named-lock owner·새 JVM·production `MariaDbRuntimeLease`/`RuntimeStateStore`/`ContinuousJobRunner`를 함께 확인합니다. 기존 API106·이전 IT/Probe/helper/manifest는 수정하지 않으며 새 test-only IT/Probe 두 파일을 fresh staging에만 추가합니다.

## 실제 fault와 관측

1. 새 schema·bucket·topic·group에서 before-Flyway/숫자 loopback/source/cluster guard, V4 migration, 빈 business·slot·source/outbox와 pristine policy를 확인합니다. fault 전 최초 group offset 준비만 최대45초의 읽기 전용 관측을 사용하며 timeout을 empty로 간주하지 않습니다.
2. 합성12건을 실제 staging과 raw PUT/전체 GET 검증으로 준비합니다. 정상 job은 `QUEUED / NOT_REQUESTED`, DISPATCH는 PENDING, slot은 점유 상태입니다. `demo_run=0`, `demo_outcome=0`, EXPORT outbox=0, Kafka read-committed end0·실제 committed 부재를 확인합니다. publish나 direct `jobs.process()`는 호출하지 않습니다.
3. 새 Probe의 DataSource 관측 wrapper는 실제 lease connection의 session ID·CURRENT_USER를 읽고 같은 connection을 production lease에 그대로 반환합니다. connection·SQL 응답·예외를 가짜로 만들거나 private field를 reflection으로 읽지 않습니다. production action은 그대로 호출합니다.
4. 실제 `exportOne()`이 pending EXPORT 없음으로 false를 반환한 직후, 얇은 action wrapper가 private 준비 marker를 쓰고 parent ACK를 기다립니다. 이 시점 실제 journal은 `RUNNING / EXPORT / code null`입니다. 이미 시작한 action을 소유권 검사와 원자적으로 묶었다고 주장하지 않습니다.
5. Java parent는 private captured positive session ID·child PID/source/run/nonce·같은 DB catalog·CURRENT_USER·server identity를 대조합니다. 같은 `runtimeit` 계정의 별도 control connection에서 현재 named-lock owner가 정확히 그 ID인지 다시 확인하고, **그 session 하나에 `KILL CONNECTION`을 한 번만 수행**합니다. 실제 owner NULL을 확인한 뒤 private ACK를 씁니다. Python은 fault pause나 ACK를 만들지 않습니다.
6. wrapper는 원래 false를 반환합니다. 다음 production PUBLISH stage의 실제 `verifyHeld()`가 손실을 감지해야 합니다. 관측 wrapper는 실제 delegate가 던진 `LeaseLostException`만 기록하고 같은 예외를 그대로 재던집니다. publisher/receiver 호출 수는 각각0이어야 합니다. 가짜 lease 예외·재연결·lock 재획득·권한 fallback은 없습니다.
7. runner의 terminal, 세 SDK 클라이언트 close·lease/context close·이전 child 종료를 확인합니다. 전체 journal은 fault 직전 값과 시각까지 동일해야 합니다. queued job의 모든 컬럼·BLOB·시각, raw/source bytes, DISPATCH PENDING 전체 행, admission policy·slot과 business/export zero도 보존되어야 합니다. 종료 뒤 다른 새 실제 lease를 획득·검증·해제하되 journal/업무는 바꾸지 않습니다.

[MariaDB KILL 문서](https://mariadb.com/docs/server/reference/sql-statements/administrative-sql-statements/kill)와 [IS_USED_LOCK 문서](https://mariadb.com/docs/server/reference/sql-functions/secondary-functions/miscellaneous-functions/is_used_lock)의 connection/owner 경계를 따릅니다. 같은 사용자 전용 session의 양수 ID만 허용하며 `KILL QUERY`·`KILL USER`·전체 session 종료·root fallback·추가 grant·DB 재시작은 없습니다. 실제 권한 오류나 owner 불일치는 UNVERIFIED이며 다른 방식으로 강행하지 않습니다. captured ID·DB 사용자·server identity·SQL 원문은 private에만 둡니다.

## journal과 실행 상태의 차이

소유권을 잃으면 journal의 pause/stop도 `requireOwner()`에서 거부될 수 있습니다. 따라서 마지막 DB 기록이 **stale `RUNNING / EXPORT / failureCode null`**인 것은 이 실험의 기대 관측입니다. 이는 현재 child가 살아 있거나 정상 실행 중이라는 뜻이 아닙니다. 실제 terminal·프로세스 종료·자원 close·fresh lease 획득을 따로 대조합니다. `PAUSED_OPERATOR / LEASE_LOST`가 DB에 저장됐다고 만들지 않습니다.

Probe의 not-ready 관측은 새 test-only `RuntimeProgress`가 실제 runner callback을 받은 결과입니다. live API·HTTP readiness 응답의 증거가 아닙니다. 검증 범위는 지정한 empty-export 경계 뒤 **다음 publisher/receiver 호출0**입니다. 소유권 검사와 action 사이의 모든 진행 중 I/O를 원자적으로 차단하는 fencing을 증명하지 않습니다. 후속 daemon의 자동 복구·업무 처리·HA도 실행하거나 주장하지 않습니다.

## 실행과 소스 고정

새 `ubuntu-24.04` GitHub hosted runner만 사용합니다. PR에서는 Python pure 경계 검사와 fresh API106 + 새 Java2, 총108파일 compile-only를 수행합니다. 실제 실험은 own repository·manual main·첫 run attempt·기본 false opt-in을 요구합니다. SSH·미니 PC·운영 서비스·PAT·repository secret·GHCR 게시·Argo/PVC 변경은 없습니다.

```sh
python3 -I -B infra/runtime-lease-loss-ci/run_once.py prepare \
  --source-manifest-sha256 "$RUNTIME_LEASE_LOSS_MANIFEST_SHA256" \
  --ack-fresh-hosted-runtime-lease-loss-it
python3 -I -B infra/runtime-lease-loss-ci/run_once.py run \
  --source-manifest-sha256 "$RUNTIME_LEASE_LOSS_MANIFEST_SHA256" \
  --ack-fresh-hosted-runtime-lease-loss-it
python3 -I -B infra/runtime-lease-loss-ci/run_once.py cleanup \
  --source-manifest-sha256 "$RUNTIME_LEASE_LOSS_MANIFEST_SHA256" \
  --ack-fresh-hosted-runtime-lease-loss-it
```

`RUNTIME_LEASE_LOSS_RUNTIME_OPT_IN=true`와 검토한 manifest SHA가 필요합니다. source manifest118개는 기존 observation baseline109개, 그 manifest 자체, 검토한 ACL compile helper와 새 runner/owner/pure 검사2개/README/Java2로 고정합니다. workflow는 manifest SHA를 참조하므로 순환 hash를 피하도록 대상에서 제외하고 checkout source SHA로 묶습니다. 이전 trial을 호출하지 않으며 helper의 검토한 정의만 제한적으로 재사용합니다.

state scope는 `ISOLATED_RUNTIME_LEASE_LOSS`, manifest scope는 `HOSTED_LINUX_RUNTIME_LEASE_LOSS_SOURCE_ONLY`입니다. label은 `platform-lab.runtime-lease-loss`, 이름 prefix는 `platform-runtime-lease-loss-<run>-<nonce>`입니다. full ID·source/run/nonce·정확한 이름·Created/StartedAt·restart0·고정 image ID·env·user·entrypoint·mount·network·cap을 재검증한 자원만 조작합니다. 다른 scope의 state와 ID가 확인되지 않은 create 결과를 채택하지 않습니다.

새 internal bridge에는 Kafka만 연결하고 DB·Garage·JVM은 같은 소유 Kafka namespace를 공유합니다. 숫자 loopback만 사용하며 host port·host network·relay·정상 broker pause 경로가 없습니다. cleanup에서만 동일 owned Kafka가 예외적으로 paused라면 방어적으로 unpause한 뒤 JVM→Garage→DB→Kafka→network full ID를 제거합니다. 전역 prune·volume 삭제·다른 서비스 중지는 없습니다. cleanup 미확인은 PASS가 아닙니다.

## 자원과 시간

| 역할 | CPU | 메모리·swap 상한 | PID | 파일시스템 |
| --- | --- | --- | --- | --- |
| Kafka | 1 | 1GiB | 256 | UID1000, data256MiB·secrets1MiB·shared config4MiB tmpfs |
| MariaDB | 1 | 1GiB | 256 | image 기본 entrypoint·user, data512MiB tmpfs·자체 writable layer |
| Garage | 1 | 512MiB | 256 | UID1000, read-only root, meta64MiB·data128MiB·tmp32MiB tmpfs |
| JVM | 1 | 2GiB | 256 | host와 같은 numeric UID, read-only root, tmp256MiB·소유 staging/cache bind |

Maven heap128MiB, parent Surefire512MiB, child256MiB입니다. 총4.5GiB는 disposable fixture의 cgroup 상한이며 보류한 운영 저장공간 예산·quota 정책과 별개입니다. Kafka4.3.1·MariaDB11.8.9·Garage2.4.1·Temurin21의 기존 고정 digest 네 개를 사용합니다. 실제 native/metaspace 여유와 조합 적합성은 실행 결과로 확인해야 합니다.

준비 단일900초 안에 compile-only·공개 Maven 의존성 준비·image 네 개 pull을 마칩니다. 실제 실행은 cached image identity 확인 뒤 첫 자원 생성부터 XML·source/artifact/tool/staging 재검증까지 단일600초입니다. JUnit420초, cleanup 별도180초이며 전체 실험 재시도는 없습니다. 최종 재검증도 deadline을 넘기면 PASS가 될 수 없습니다.

Maven 준비 실패는 API compile·Maven version·offline dependencies·Surefire provider·JUnit launcher의 고정 stage, 실제 exit code/null, 관측한 고정 signature enum만 `preparationFailure`로 남깁니다. native 출력은 합계4MiB 안에서 메모리로만 읽고 버리며 원문·명령 인수·환경을 출력하거나 artifact에 넣지 않습니다. 원인을 모르는 실패를 전송 오류로 단정하거나 자동 재시도하지 않습니다.

## 공개 근거와 pure 경계 검사

private state·환경·child control·XML·native log·SQL·객체 bytes는 `.local/runtime-lease-loss-ci/private` 안에만 둡니다. Java control root는 `/owned/api/target/runtime-lease-loss-control`이며 `LEASE_CONTROL_{DIR,NONCE,RUN_ID}`와 source를 결합합니다. 같은 UID의0700 디렉터리와0600 regular/nlink1/no-symlink·bounded exact control 형식을 검증합니다. parent Java만 전용 connection 종료·ACK를 수행하고 Python은 단일 JUnit 결과만 수신합니다.

공개 artifact는 `.local/runtime-lease-loss-ci-public/summary.json` 하나입니다. `leaseLossResult`는 정확35필드만 허용합니다. actual session/owner 대조·전용 연결 종료·lock 부재·실제 lease 손실·다음 stage 거부·publisher/receiver0, stale journal 전체 불변, QUEUED/NOT_REQUESTED·DISPATCH PENDING·business/export zero·slot 점유·source/raw 보존, end0·`NO_COMMIT/null`, child/context 종료·fresh lease 획득·target 안정을 확인합니다. committed 부재를 commit0 또는 lag0으로 표현하지 않습니다.

정확한 IT method의 XML tests1/failure0/error0/skip0·Java21/Linux, source/artifact/tool/staging 불변과 owned cleanup이 함께 통과해야 전체 PASSED입니다. 실패 marker는 phase17개·kind11개 enum과 원 Throwable의 own IT source line/null을 담은 정확6필드입니다. Python은 hash가 맞는 staged IT의 실제 줄 수로 source line을 재검증합니다. 알려진 Python source/line과 같은 owned JVM이 실제 종료했을 때만 읽는 tail200·최대5초/1MiB in-memory native 진단을 유지합니다. raw exception class/message·환경·credential·주소·resource ID는 공개하지 않습니다. 실패 중 `sourceAndArtifactsUnchanged=false`는 최종 확인 미완료일 수 있으며 그 자체가 변조 증거는 아닙니다.

```sh
python3 -I -B -m unittest discover -s infra/runtime-lease-loss-ci -p 'test_*.py' -v
```

pure 검사는 Docker·Java·Maven·네트워크·credential 없이 marker의 null/type/count, 가짜 durable pause·healthy journal·publish/receive·업무 완료 주장 거부, scope·manifest·symlink/hardlink·hash/source line·소유 자원 identity·cleanup 경계를 확인합니다. POSIX 검사를 Windows용으로 우회하지 않습니다. 운영 DB나 이미 실행 중인 worker의 연결을 끊지 않습니다.
