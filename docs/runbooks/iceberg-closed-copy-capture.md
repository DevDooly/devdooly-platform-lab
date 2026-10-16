# Iceberg closed-copy capture: 다음 실행과 증거

**다섯 번째 실행은 Linux 80개·prep·원래 main 반환 0·새 decoder 정지/CLI 회수를 확인했지만 전체 capture·normalization·inventory는 미검증입니다.** [시도5](../evidence/iceberg-capture/ATTEMPT_5.md)는 `NORMALIZE`의 `SUMMARY_NOT_VERIFIED`·`UNKNOWN` 실패입니다. decoder exit 0·유효 graph·통합 stopped actors/clock·전체 KEEP을 주장하지 않으며 관측 count는 null입니다. [첫 실행](../evidence/iceberg-capture/ATTEMPT_1.md)은 Linux 56개·skip0 이후 일반 `PREP_NOT_VERIFIED` 실패와 원인·정리 미확인을 남겼습니다. [두 번째 새 실행](../evidence/iceberg-capture/ATTEMPT_2.md)은 Linux 62개·skip0 이후 `JAR_MANIFEST_CLASSPATH_EXPANSION_REJECTED`로 prep에 실패했고, 해당 prep cold 컨테이너의 identity binding·삭제 시도·삭제 후 부재 확인을 남겼습니다. [세 번째 새 실행](../evidence/iceberg-capture/ATTEMPT_3.md)은 Linux 67개·skip0 이후 `JAR_MANIFEST_BYTES_BOUND`로 prep에 실패했고 해당 prep cold 컨테이너 제거·부재를 확인했습니다. 어떤 manifest 바이트 분기인지와 실제 Class-Path closure·prep·decoder·inventory 성공은 미확인입니다. [네 번째 새 실행](../evidence/iceberg-capture/ATTEMPT_4.md)은 Linux 73개·skip0 이후 `JAR_MANIFEST_CLASSPATH_TARGET_MISSING`으로 prep에 실패했고 해당 prep cold 컨테이너 제거·부재를 확인했습니다. 특정 JAR·token·경로와 실제 전체 closure·prep·compile·decoder·inventory 성공은 미확인입니다. 이 결과를 이전 바이트 guard 실패의 원인으로 소급하지 않습니다. 앞선 네 기록을 보존합니다. 전체 파일 트리·실제 부재·javac 전후 재검증 source의 Windows 합성 검사 32개는 24개 통과·POSIX 전용 8개 제외였고, 이후 시도5에서 Linux 80개·skip0과 prep 검증을 확인했습니다. 전체 capture는 실패로 유지합니다. 다음 [정규화 단계 진단 후보](../../infra/iceberg-retention-ci/NORMALIZATION_PHASES.md)는 시도한 guard 구간만 고정 코드로 구분하며 실제 원인·해결을 주장하지 않습니다. CLI14개+새4개는 root Windows 한 번에서 17개 통과·POSIX1개 skip·실패/오류0이며 새 Linux84·Cloud는 미실행입니다. 기존 [Cloud Spark→Trino·compaction 성공](../evidence/cloud-lakehouse/FULL_SUCCESS.md), [DB 논리 복원 기록](../evidence/current-db-restore/README.md), [순수 retention planner](iceberg-retention-dry-run.md)는 공개됐습니다. 이번 단계는 새 격리 Cloud 실행에서 실제 metadata의 닫힌 참조 graph를 수집해 계획기에 연결하는 작업입니다. 과거 성공 summary의 snapshot ID·객체 수로 새 inventory를 만들지 않습니다.

## 실행 순서

1. 다음 source·runtime manifest를 전체 SHA로 묶고 해당 source에서 검토된 전체 Linux 검사 수·UID0·skip0을 먼저 확인합니다. 기존 다섯 실행의 Linux 56개·62개·67개·73개·80개 통과는 각각의 source에만 귀속하며 미래 수정본의 통과로 채택하지 않습니다. Windows 합성 검사나 Windows에서 skip한 openat·UID·mode 검사를 Linux 성공으로 옮겨 적지 않습니다.
2. Manifest 바이트·참조 경계를 검토한 새 source에서 고정 Spark image의 새 cold container를 만들고 시작하지 않은 채 실제 JAR classpath를 export합니다. 별도 prep에서 기존 locked Iceberg JAR와 host JDK21로 decoder main만 compile합니다. 모든 JAR/class whole SHA·classpath 확장/동일 클래스 충돌·class header/mode를 확인하고, 정확한 자기 cold CID의 제거·부재까지 관측한 뒤 prep을 통과시킵니다. 앞선 네 prep 실패는 compile 성공을 확인하지 못했습니다. 시도5의 compilerPrepVerified true와 cold 정리는 해당 source의 검증 범위이며 전체 graph·capture 성공을 뜻하지 않습니다. 새 decoder의 정지·CLI 회수 확인도 원래 모든 actor의 통합 정지 또는 exit 0 증거로 확대하지 않습니다. 단순 guard 해제나 기존 JAR bytes 변경을 승인한 상태가 아닙니다. 다음 진단 source는 normalizer/composite/CLI의 유한 단계 보고만 바꾸며 기존 prep·원래 producer·SQL·600초·자원·정리 명령은 보존합니다.
3. 새 실행의 원래 producer main을 정확히 한 번 호출합니다. 기존 SQL·변환·자원 한도와 600초 workload clock을 유지합니다. Spark → Trino → final verify의 JDBC 반환 bytes 세 개를 named checkpoint로 보존하며 SQL을 추가하지 않습니다. 기존 실패 run을 재실행하거나 과거 성공 자료를 새 성공으로 채택하지 않습니다.
4. 원래 다섯 role과 initializer의 정지를 별도 관측한 뒤 approved whole-copy map만 읽습니다. 실제 named JDBC current URI와 map SHA에서 요청을 도출하며 미래 URI를 미리 입력하지 않습니다. Linux held FD·nofollow·single-link·owner/mode·EOF/size/whole SHA로 copy의 안정성을 검사합니다.
5. 새 decoder CID 하나를 network-none으로 실행합니다. 원래 `started+600` 안에서 최대60초 decode와 40초 cleanup reserve를 적용하고, 실제 container 정지·CLI 회수·writer 전후 동일 상태를 확인합니다. 별도 prep의 600초 예산과 원래 workload의 600초는 서로 다른 범위이며 총 완료 시간의 약속이 아닙니다.
6. Java가 읽은 모든 snapshot/ref와 manifest-list→manifest→data/delete→referenced-data 관계를 Python이 독립 순회해 closure와 대조합니다. 같은 실행의 실제 Spark chain·Trino aggregate·10개 SQL intent에서 VALIDATION pin을 연결합니다. 완전성·안정성·300초 freshness gate를 통과한 graph만 frozen planner의 `CAPTURED_TABLE_METADATA` 입력으로 내립니다.

별도 새 source 검토 후 사용할 일반 실행 형식은 다음과 같습니다. `<final-reviewed-runtime-manifest-sha256>`는 해당 새 ref의 `infra/iceberg-retention-ci/runtime-manifest.json` 전체 bytes의 SHA-256입니다. 인자 이름은 `--source-manifest-sha256`이지만 source packet의 `source-manifest.json` 해시를 넣는 것이 아닙니다. 아래 placeholder 예시는 다음 source의 최종 manifest가 정해지기 전의 형식이며, 앞선 다섯 실제 실행의 source·manifest·결과는 각각의 증거에 기록합니다.

```sh
python3 -I -B infra/iceberg-retention-ci/run_capture.py \
  --source-manifest-sha256 <final-reviewed-runtime-manifest-sha256> \
  --ack-fresh-closed-copy-capture
```

수동 `lab-ci` 입력은 `run_iceberg_capture_trial=true`이고 `run_s3_trial`, `run_spark_trial`, `run_cloud_lakehouse_trial`은 모두 false로 선택합니다. 새 source/ref에서 한 번 선택하는 실행이며 CI의 실패 job 자동 재실행이나 같은 resource 이름의 재사용은 하지 않습니다. 실행 전 source 검토·Linux 검사·현재 계정 한도를 확인합니다. **계정 잔여 한도 60%에 도달하면 새 무거운 실행을 보류**하고 이미 시작한 자기 자원의 종료와 증거를 먼저 보존합니다.

## 남겨야 할 증거와 실패 처리

| 경계 | 실제로 남길 증거 |
| --- | --- |
| 출처 | source commit, workflow run/attempt, 최종 runtime manifest·producer·decoder·planner SHA |
| Linux·prep | 실제 검사 수/실패/skip, image identity, JDK/compiler 결과, 전체 classpath·class SHA와 자기 cold container 종료 |
| 원래 실행 | 단일 producer summary 원문, 같은 실행의 Spark/reader/clock·Trino stop, named JDBC 세 raw/checkpoint, 실제 SQL intent |
| copy·decode | 실제 approved map와 전체 copy SHA, descriptor/frame/reply SHA, 참조 graph·outside-table KEEP ledger |
| 종료·정규화 | source-bound writer 전후 상태와 새 decoder stop/reap, 실제 capture UTC, inventory/plan hash, completeness와 고정 failure/reason |

원문 map·metadata·graph·내부 URI·raw 로그·자격증명은 해당 ephemeral runner의 private 영역에만 남깁니다. enclosing root0700으로 접근을 제한하고 원래 proof0777·copy 소유권과 mode는 변경하지 않으며, caller의 새 증거 파일은 0600으로 만듭니다. durable 외부 백업이 아니며 private artifact를 업로드하지 않습니다. 공개 요약은 검토된 작은 whitelist의 상태·source/hash·실제 count·종료 범위만 담습니다. 현재 `safe_summary`에는 UTC 필드가 없으며 별도로 검토한 공개 근거에서 실제 run UTC를 기록할 수 있습니다. 누락된 값을 0 또는 성공으로 보완하지 않습니다. 새 NORMALIZE_*_UNVERIFIED는 검증을 시도했으나 확인하지 못한 구간이며 내부 원인이나 graph·inventory 성공을 뜻하지 않습니다. schema2 공개 키·null count·PASS gate는 유지합니다. Prep 실패, producer 실패, decoder 실패, `UNDETERMINED` inventory와 종료 미관측을 각각 남기며 이전 근거를 덮어쓰지 않습니다. Pipeline이 예외 없이 끝났다는 사실만으로 완전 inventory 또는 producer PASS와 동등하다고 주장하지 않습니다.

현재/ref/pin의 모든 조상을 보호하는 보수적 첫 planner이므로 일반 선형 history에서 회수할 공간을 예측하지 않습니다. 모든 객체는 KEEP, objectCandidateCount0/applyEnabledfalse입니다. Snapshot 후보가 있더라도 만료를 실행했다는 뜻이 아닙니다. 이 단계에는 expiration SQL·객체 GC/삭제·snapshot 정리 스케줄러·과거 metadata 복원·Parquet 내용 해석·미니 PC 접근·실시간 가용성/SLA 검증이 없습니다.
