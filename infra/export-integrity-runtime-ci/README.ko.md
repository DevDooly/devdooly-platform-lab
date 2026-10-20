# 손상 export의 실제 런타임 pause와 명시 수리

같은 길이로 손상된 result 객체가 있을 때 실제 child 런타임이 `PAUSED_OPERATOR / EXPORT / EXPORT_FAILED`를 지속하는지 확인하는 격리 시험입니다. 일반 run 거부, 수리 없는 resume 뒤의 재실패, 시험 소유 객체 한 개의 명시 수리와 두 번째 resume 후 정상 완료를 연결합니다. 작성·컴파일만 마친 상태는 실제 복구 성공 근거가 아닙니다.

기존 `VerifiedResultExportIT`는 직접 export 호출의 손상 객체 검증을, `ContinuousRuntimeIT`는 raw source 손상의 영속 pause를 검증합니다. 이번 시험은 실제 corrupt-export와 새 JVM의 export-first loop·DB journal·운영자 재개 사이의 경계를 확인합니다. 운영 API·기존 API106개·다른 trial/helper/manifest는 바꾸지 않습니다.

## 실제 동작과 판정

1. 새 전용 schema·bucket·topic/group에서 V4 migration, 빈 업무 테이블·슬롯·journal과 초기 admission policy를 확인합니다. 첫 group offset 준비는 fault 이전의 제한된 읽기 대기이며 timeout을 empty로 간주하지 않습니다.
2. 실제 `SourceStagingService`와 raw S3 PUT/전체 GET 검증을 거칩니다. 실제 `DispatchPublisher.publishOne()`의 broker ACK 후 DISPATCH ACK를 확인하고, `jobs.process()`를 직접 호출해 COMPLETED/PENDING과 EXPORT PENDING·슬롯 점유를 준비합니다. **이는 DB/S3 직접 fixture 준비입니다. Kafka consumer가 최초 업무 처리를 했다는 증거가 아닙니다.**
3. 합성12개(성공7·실패3·중복2·pending0)의 canonical bundle result를 한 byte만 바꿔 같은 크기의 소유 result key에 저장합니다. 전체 GET에서 크기는 같고 bytes·SHA는 다른지 확인합니다. failures 객체는 없어야 합니다.
4. 첫 새 child의 실제 `JobRuntimeActions`·`ContinuousJobRunner`·`ResultExportService`·`S3ResultExportStore`를 실행합니다. delegate가 실제로 던진 `ExportVerificationException`만 고정 관측값으로 기록하고 같은 예외를 그대로 전파합니다. 가짜 storage 오류를 던지지 않습니다. child 종료·client 닫힘·lease 해제 뒤 실제 EXPORT_FAILED pause를 확인합니다.
5. 원 CLI run은 지속 pause로 거부되고 journal·업무 행/시각·객체·슬롯이 변하지 않아야 합니다. 원 CLI resume는 journal만 STOPPED로 바꿉니다. **resume 자체가 객체 수리를 검사하는 것은 아닙니다.** 수리하지 않은 새 daemon은 같은 실제 검증 실패로 다시 pause해야 합니다. 일반 run 거부도 다시 확인합니다.
6. 모든 child가 종료하고 lease가 해제된 뒤 소유 key·손상 bytes를 다시 확인합니다. 시험만 그 result 객체 한 개를 삭제하고 실제 NoSuchKey와 raw 보존을 확인합니다. 다른 객체 삭제·범용 repair API·자동 overwrite는 없습니다.
7. 다시 원 CLI resume와 새 정상 daemon을 실행합니다. 실제 adapter가 누락 result를 쓰고 결과/실패 두 파일의 전체 bytes·크기·SHA를 검증한 뒤 EXPORTED·EXPORT ACK·슬롯 해제를 확인합니다. 이미 실제 DISPATCH ACK된 완료 메시지는 재발행 없이 한 번 replay되고 Kafka end1·committed1·lag0이어야 합니다. 이 마지막 판정 전에는 export만 보고 전체 PASS로 처리하지 않습니다.

실패 구간에는 COMPLETED/PENDING, export 완료 시각 null, EXPORT PENDING·ACK 시각 null, 슬롯 점유와 손상 객체가 유지돼야 합니다. 실패 두 번 모두 새 발행·commit·failures 객체가 생기면 실패입니다. 전 구간에서 원본 raw·DB source·demo 행 전체와 처리 시각·DISPATCH 전체 행·EXPORT identity·cluster/topic UUID를 대조합니다. 허용하는 변경은 runtime journal, 최종 export 상태/시각·EXPORT ACK, 최종 슬롯 해제뿐입니다.

## 실행과 소유권

새 `ubuntu-24.04` GitHub hosted runner만 사용합니다. PR에서는 새 Python 경계 검사와 fresh API106+새 Java2(108개)의 compile-only를 수행합니다. 실제 시험은 own repository·main·첫 run attempt·기본 false의 명시적 수동 opt-in을 함께 요구합니다. SSH·운영 서비스 연결·PAT·repository secret·GHCR 게시·Argo/PVC 변경은 없습니다.

```sh
python3 -I -B infra/export-integrity-runtime-ci/run_once.py prepare \
  --source-manifest-sha256 "$EXPORT_INTEGRITY_MANIFEST_SHA256" \
  --ack-fresh-hosted-export-integrity-it
python3 -I -B infra/export-integrity-runtime-ci/run_once.py run \
  --source-manifest-sha256 "$EXPORT_INTEGRITY_MANIFEST_SHA256" \
  --ack-fresh-hosted-export-integrity-it
python3 -I -B infra/export-integrity-runtime-ci/run_once.py cleanup \
  --source-manifest-sha256 "$EXPORT_INTEGRITY_MANIFEST_SHA256" \
  --ack-fresh-hosted-export-integrity-it
```

`EXPORT_INTEGRITY_RUNTIME_OPT_IN=true`와 검토한 manifest SHA가 필요합니다. source manifest118개는 기존 observation baseline109개, 그 manifest 자체, 검토한 ACL compile helper, 새 runner/owner/순수 검사2개/README/Java2개로 고정합니다. workflow는 manifest SHA를 참조하므로 순환 hash를 피하도록 manifest 대상에서 제외하고 checkout source SHA로 묶습니다. 이전 trial을 호출하지 않고 검토한 helper의 정의만 제한적으로 재사용합니다.

새 state scope는 `ISOLATED_EXPORT_INTEGRITY_RUNTIME`, label은 `platform-lab.export-integrity`, 이름 prefix는 `platform-export-integrity-<run>-<nonce>`입니다. full ID·source/run/nonce·정확한 이름·Created/StartedAt·restart0·고정 image ID·env·user·entrypoint·mount·network·cap을 재검증한 자원만 조작합니다. 다른 scope의 state나 알 수 없는 create 결과를 채택하지 않습니다.

새 internal bridge에 Kafka만 연결하고 DB·Garage·JVM은 같은 소유 Kafka network namespace를 공유합니다. host port·host network·relay는 없습니다. Kafka를 pause하는 정상 경로는 없으며 예상하지 못한 paused 상태는 실패입니다. cleanup에서만 같은 소유 Kafka가 paused라면 방어적으로 unpause한 후 JVM→Garage→DB→Kafka→network 순서로 확인된 full ID만 제거합니다. 전역 prune·volume 삭제·다른 서비스 중지는 없습니다. 정리 미확인은 PASS가 아닙니다.

## 자원과 시간

| 역할 | CPU | 메모리·swap 상한 | PID | 파일시스템 |
| --- | --- | --- | --- | --- |
| Kafka | 1 | 1GiB | 256 | UID1000, data256MiB·secrets1MiB·shared config4MiB tmpfs |
| MariaDB | 1 | 1GiB | 256 | image 기본 entrypoint·user, data512MiB tmpfs·자체 writable layer |
| Garage | 1 | 512MiB | 256 | UID1000, read-only root, meta64MiB·data128MiB·tmp32MiB tmpfs |
| JVM | 1 | 2GiB | 256 | host와 같은 numeric UID, read-only root, tmp256MiB·소유 staging/cache bind |

Maven heap128MiB, parent Surefire512MiB, child256MiB입니다. 총4.5GiB는 이번 disposable fixture의 cgroup 상한이며 보류한 운영 저장공간 예산·quota 정책은 적용하지 않습니다. 고정 digest 네 개는 Kafka4.3.1·MariaDB11.8.9·Garage2.4.1·Temurin21입니다. 실제 native/metaspace 여유와 새 조합의 적합성은 후속 실행에서 확인해야 합니다.

준비는 단일900초 안에 compile-only·공개 Maven 의존성 준비·이미지 네 개 pull을 마칩니다. 실행은 cached image identity를 확인한 뒤 자원 생성부터 XML·source/artifact/tool/staging 불변 확인까지 단일600초입니다. JUnit420초, cleanup 별도180초를 두며 시험 전체 재시도는 없습니다. 준비 실패는 실제 복구 결과를 만들지 않습니다.

Maven 준비 실패는 API compile·Maven version·offline dependencies·Surefire provider·JUnit launcher의 고정 stage, 실제 exit code/null, 허용된 signature enum만 `preparationFailure`로 남깁니다. native 출력은 합계4MiB 안에서 메모리로만 읽고 버리며 원문·명령 인수·환경을 출력하거나 artifact에 넣지 않습니다. 알 수 없는 실패를 전송 오류로 분류하거나 재시도하지 않습니다. 이 진단은 후속 실행의 원인을 구분하기 위한 것이며 특정 네트워크·저장소 오류가 이미 확인됐다는 뜻은 아닙니다.

## 공개 근거와 순수 검사

private state·환경 파일·child 파일·XML·native log·SQL·객체 bytes는 `.local/export-integrity-runtime-ci/private` 안에만 둡니다. Java control root는0700이며 같은 실행 UID의 private 결과/stop 파일에 source/run/nonce를 묶습니다. Python에는 외부 pause/ACK phase가 없습니다.

공개 artifact는 `.local/export-integrity-runtime-ci-public/summary.json` 하나입니다. `integrityResult`는 정확29개 고정 필드의 PASS 결과만 받습니다. source/artifact/tool 불변과 XML tests1/failure0/error0/skip0, 정확한 IT method·Java21·Linux, 소유 자원 정리까지 함께 확인해야 전체 PASSED입니다. `directDatabaseFixture=true`와 `dispatchBrokerAck=true`를 구분하고 실제 완료 replay1을 별도로 기록합니다.

실패는 phase23개·kind11개와 원 own IT source line/null의6필드 marker만 허용합니다. source line은 manifest SHA가 일치하는 실제 IT의 줄 수로 다시 검사합니다. 기존 유한 Python source 진단과, 동일 소유 JVM이 실제 종료했을 때만 읽는 tail200/최대5초·1MiB의 in-memory native 진단도 유지합니다. 공개에는 고정 enum·검증 bool·집계·알려진 source line·지문만 남기며 raw exception class/message·환경·credential·주소·resource ID를 쓰지 않습니다. 실패 중 `sourceAndArtifactsUnchanged=false`는 최종 불변 확인 미완료이며 그 자체가 변조 증거는 아닙니다.

```sh
python3 -I -B -m unittest discover -s infra/export-integrity-runtime-ci -p 'test_*.py' -v
```

순수 fixture 검사는 Docker·Java·Maven·네트워크·credential 없이 marker·scope·manifest·symlink/hardlink·hash/source line·소유 자원 identity·정리 경계를 확인합니다. POSIX 검사를 Windows용으로 우회하지 않습니다. 이 시험은 운영 현재 상태·자동 수리·WORM·다중 broker HA·SLA·모든 장애에서의 exactly-once를 증명하지 않습니다.
