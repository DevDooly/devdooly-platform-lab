# 잘못된 Kafka 메시지에서 작업을 보호하는 실제 runtime

Kafka topic의 첫 record가 잘못된 JSON일 때 실제 worker가 `PAUSED_OPERATOR / CONSUME / INVALID_MESSAGE`를 지속하고, 뒤에 발행된 정상 작업을 처리하지 않는지 확인하는 격리 실험입니다. 일반 run 거부, 명시 resume, 같은 poison record에 따른 재중지까지 연결합니다. 현재는 검토를 위한 후보이며 실제 실행의 성공 근거가 아닙니다.

기존 `DispatchWorkerTest`의 mock consumer 검사와 달리 실제 broker ACK·새 JVM·DB journal·group committed offset을 함께 대조합니다. 기존 raw source 손상, DB commit 후 offset commit 실패, corrupt export의 실험과도 경계가 다릅니다. 생산 API106·기존 `RuntimeProcessProbe`·이전 helper/manifest를 수정하지 않습니다.

## 실험 순서와 성공 조건

1. 새 schema·bucket·one-partition topic·group에서 V4 migration, 빈 업무 테이블·source/outbox·슬롯, pristine admission policy를 확인합니다. 초기 group coordinator의 준비는 fault 전에만 최대45초 동안 실제 읽기 RPC로 확인합니다. timeout을 empty로 취급하지 않으며 각 RPC도 남은 시간 안에서 제한합니다.
2. 실제 producer로 고정 malformed JSON을 발행하여 broker ACK의 partition0·offset0을 확인합니다. 합성12건의 정상 source는 실제 staging과 raw PUT/전체 GET 검증을 거칩니다. 실제 `DispatchPublisher.publishOne()`의 broker ACK offset1과 DISPATCH ACK를 확인합니다.
3. 별도 READ_COMMITTED observer를 수동 assign하여 실제 record 두 개를 확인합니다. offset0의 malformed bytes와 offset1의 정상 DispatchMessage/queued job이 일치해야 합니다. observer는 subscribe·group join·auto-commit·명시 commit을 하지 않으며 worker 시작 전에 닫습니다. 실제 read-committed end는2입니다.
4. 원본 `exporting.RuntimeProcessProbe`를 새 JVM으로 실행합니다. 실제 daemon이 첫 JSON decode에서 `INVALID_MESSAGE`로 멈추고 DB에 pause를 남겨야 합니다. 실제 프로세스 종료·세 클라이언트 close·lease 해제를 확인한 뒤 같은 group committed offset의 부재를 관측합니다.
5. 일반 CLI run이 거부되어야 합니다. 거부 직전과 직후의 전체 journal을 비교하여 상태·stage·코드·시각이 그대로인지 확인합니다. 정상 job의 모든 컬럼/시각, source·raw bytes, DISPATCH ACK, 업무 결과 zero, EXPORT outbox zero, slot 점유도 보존되어야 합니다.
6. 원본 CLI resume이 STOPPED/STOPPED/code null을 기록한 뒤 같은 topic/group으로 fresh daemon을 실행합니다. poison record를 수정하지 않았으므로 다시 실제 INVALID_MESSAGE pause와 client close가 나타나야 합니다. 두 번째 일반 run 거부에서도 journal·정상 job·업무 결과·raw·outbox·slot은 그대로여야 합니다.
7. 마지막 실제 committed offset도 부재이고 broker end는2여야 합니다. 실제 cluster/topic UUID·partition과 source/artifact/tool/staging 불변, 단일 JUnit case의 성공, 소유한 disposable 자원의 정리까지 확인해야 전체 PASSED입니다.

정상 job은 끝까지 `QUEUED / NOT_REQUESTED`이며 slot은 점유 상태입니다. `demo_run=0`, `demo_outcome=0`, EXPORT outbox=0이어야 합니다. 따라서 PASS는 입력 보호 동작의 통과입니다. 업무 처리·export·slot 해제·복구 완료를 뜻하지 않습니다. committed offset이 없는 상태는 `NO_COMMIT / null`로 기록하며 lag2를 만들지 않습니다.

DLQ·skip·offset reset·record 삭제·topic 삭제·replacement·자동 repair를 구현하거나 수행하지 않습니다. 실험 종료 뒤 disposable 컨테이너와 internal network만 제거합니다. poison record가 남아 있는 운영 환경의 후속 조치 정책을 이 실험으로 정하지 않습니다.

## 실행과 소스 고정

새 `ubuntu-24.04` GitHub hosted runner만 사용합니다. PR에서는 Python pure 경계 검사와 fresh API106 + 새 Java IT1, 총107파일의 compile-only만 수행합니다. 실제 실험은 own repository·manual main·첫 run attempt·기본 false인 명시 opt-in을 함께 요구합니다. SSH·운영 서비스 연결·PAT·repository secret·GHCR 게시·Argo/PVC 변경은 없습니다.

```sh
python3 -I -B infra/invalid-message-runtime-ci/run_once.py prepare \
  --source-manifest-sha256 "$INVALID_MESSAGE_MANIFEST_SHA256" \
  --ack-fresh-hosted-invalid-message-it
python3 -I -B infra/invalid-message-runtime-ci/run_once.py run \
  --source-manifest-sha256 "$INVALID_MESSAGE_MANIFEST_SHA256" \
  --ack-fresh-hosted-invalid-message-it
python3 -I -B infra/invalid-message-runtime-ci/run_once.py cleanup \
  --source-manifest-sha256 "$INVALID_MESSAGE_MANIFEST_SHA256" \
  --ack-fresh-hosted-invalid-message-it
```

`INVALID_MESSAGE_RUNTIME_OPT_IN=true`와 검토한 manifest SHA가 필요합니다. source manifest117개는 기존 observation baseline109개, 그 manifest 자체, 검토한 ACL compile helper, 새 runner/owner/pure 검사2개/README/Java IT1로 고정합니다. workflow는 manifest SHA를 참조하므로 순환 hash를 피하도록 대상에서 제외하고 checkout source SHA로 묶습니다. 이전 trial을 호출하지 않으며 검토한 helper의 정의만 제한적으로 재사용합니다.

새 state scope는 `ISOLATED_INVALID_MESSAGE_RUNTIME`, manifest scope는 `HOSTED_LINUX_INVALID_MESSAGE_RUNTIME_SOURCE_ONLY`입니다. label은 `platform-lab.invalid-message`, 이름 prefix는 `platform-invalid-message-<run>-<nonce>`입니다. exact full ID·source/run/nonce·이름·Created/StartedAt·restart0·고정 image ID·env·user·entrypoint·mount·network·cap을 재검증한 자원만 조작합니다. 다른 scope의 state나 ID를 모르는 create 결과를 채택하지 않습니다.

새 internal bridge에 Kafka만 연결하고 DB·Garage·JVM은 같은 소유 Kafka network namespace를 공유합니다. 숫자 loopback만 사용하며 host port·host network·relay가 없습니다. 정상 broker pause 경로도 없습니다. cleanup에서만 동일한 owned Kafka가 예외적으로 paused라면 방어적으로 unpause한 뒤 JVM→Garage→DB→Kafka→network full ID를 제거합니다. 전역 prune·volume 삭제·다른 서비스 중지는 없습니다. 정리 미확인은 PASS가 아닙니다.

## 자원과 제한 시간

| 역할 | CPU | 메모리·swap 상한 | PID | 파일시스템 |
| --- | --- | --- | --- | --- |
| Kafka | 1 | 1GiB | 256 | UID1000, data256MiB·secrets1MiB·shared config4MiB tmpfs |
| MariaDB | 1 | 1GiB | 256 | image 기본 entrypoint·user, data512MiB tmpfs·자체 writable layer |
| Garage | 1 | 512MiB | 256 | UID1000, read-only root, meta64MiB·data128MiB·tmp32MiB tmpfs |
| JVM | 1 | 2GiB | 256 | host와 같은 numeric UID, read-only root, tmp256MiB·소유 staging/cache bind |

Maven heap128MiB, parent Surefire512MiB, child256MiB입니다. 총4.5GiB는 disposable fixture의 cgroup 상한이며 보류한 운영 저장공간 예산·quota 정책은 적용하지 않습니다. Kafka4.3.1·MariaDB11.8.9·Garage2.4.1·Temurin21의 기존 고정 digest 네 개를 사용합니다. 실제 native/metaspace 여유와 조합 적합성은 실행 결과로 확인해야 합니다.

준비는 단일900초 안에 compile-only·공개 Maven 의존성 준비·image 네 개 pull을 마칩니다. 실제 실행은 cached image identity 확인 후 첫 자원 생성부터 XML·source/artifact/tool/staging 재검증까지 단일600초입니다. JUnit420초, cleanup 별도180초이며 실험 전체를 재시도하지 않습니다. deadline을 넘긴 최종 검사는 PASS가 될 수 없습니다.

준비 실패는 고정 stage(API compile·Maven version·offline dependencies·Surefire provider·JUnit launcher), 실제 exit code/null, 관측한 고정 signature enum만 `preparationFailure`로 남깁니다. native 출력은 합계4MiB 안에서 메모리로만 읽고 버리며 원문·명령 인수·환경을 출력하거나 artifact에 넣지 않습니다. 원인을 모르는 실패를 전송 오류로 단정하거나 재시도하지 않습니다.

## 공개 근거와 pure 경계 검사

private state·환경·child control·XML·native log·SQL·객체 bytes는 `.local/invalid-message-runtime-ci/private` 안에만 둡니다. 새 parent control root와 child별 하위 폴더는 같은 UID의0700입니다. 원본 Probe의 실제 atomic checkpoint/exit 형식을 그대로 읽으며 regular/no-symlink/nlink1·same owner·owner-only-write·bounded bytes와 exact key/value를 검사합니다. 임의 nonce 필드를 원본 Probe가 출력한다고 가정하지 않습니다. 실제 PID/종료와 DB journal·lease를 함께 대조합니다.

공개 artifact는 `.local/invalid-message-runtime-ci-public/summary.json` 하나입니다. `protectionResult`는 정확31개 고정 필드만 허용합니다. malformed/정상 실제 ACK offset0/1, 두 pause, 실제 run 거부·resume, QUEUED/NOT_REQUESTED·zero business/export·slot 점유·source/raw/DISPATCH 보존, 두 `NO_COMMIT/null`, end2, client close·target 안정, `automaticRepairPerformed=false`를 검사합니다. XML tests1/failure0/error0/skip0, 정확 IT method·Java21·Linux, source/artifact/tool 불변과 cleanup이 함께 통과해야 전체 PASSED입니다.

실패 marker는 phase16개·kind11개의 고정 enum과 원 Throwable의 own IT source line/null을 담은 정확6필드만 허용합니다. source line은 manifest SHA와 일치하는 실제 IT의 줄 수로 다시 검증합니다. Python 실패의 알려진 source line/enum과, 같은 owned JVM이 실제 종료했을 때만 읽는 tail200/최대5초·1MiB in-memory native 진단을 유지합니다. 공개에는 고정 enum·검증 bool·집계·알려진 source line·지문만 남기며 raw exception class/message·환경·credential·주소·resource ID를 싣지 않습니다. 실패 중 `sourceAndArtifactsUnchanged=false`는 최종 불변 확인 미완료이며 그 자체가 변조 증거는 아닙니다.

```sh
python3 -I -B -m unittest discover -s infra/invalid-message-runtime-ci -p 'test_*.py' -v
```

pure 검사는 Docker·Java·Maven·네트워크·credential 없이 marker의 null/type/count·잘못된 성공 주장 거부, scope·manifest·symlink/hardlink·hash/source line·소유 자원 identity·정리 경계를 확인합니다. POSIX 검사를 Windows용으로 우회하지 않습니다. 이 실험은 운영 현재 상태·HA·SLA·자동 복구·exactly-once·poison record의 skip/repair 정책을 증명하지 않습니다.
