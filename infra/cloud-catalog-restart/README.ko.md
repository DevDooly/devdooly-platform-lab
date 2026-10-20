# PostgreSQL JDBC catalog의 정상 stop/start와 보존

**상태: NOT EXECUTED.** 새 소스 후보를 검토하는 단계이며 실제 PostgreSQL 재시작 성공을 주장하지 않습니다. 새 hosted Cloud fixture에서 Spark가 정상 종료하고 Trino가 아직 시작되지 않은 상태로 PostgreSQL만 한 번 정상 stop/start한 뒤, fresh Trino와 전체 객체 GET으로 catalog·warehouse 보존을 확인합니다.

기존 native7와 Cloud Trino 재기동에서는 PostgreSQL 프로세스가 계속 같았습니다. 이번 범위는 조용한 catalog 프로세스의 정상 재시작 한 경계입니다. host 재부팅·진행 중 writer·crash/WAL 복구·backup restore·failover/HA·운영 가용성을 증명하지 않습니다. 과거 Cloud/native warehouse를 되살리거나 미니 PC를 변경하지 않습니다.

## 실제 실행 때 확인할 순서

1. 새 UUID project·전용 물리 volume 세 개·내부 network와 기존 고정 image/JAR를 준비합니다. 과거 volume이나 기존 출력 폴더를 재사용하지 않습니다. image pull·vendor 검증·network 없는 로컬 Spark image build는 workload 전에 끝냅니다.
2. 검토한 기존 `run_restart.prepare()` 정의로 새 Spark fixture를 만듭니다. Bronze6+6·Silver12·작은 compaction을 수행하고 `sessionStopFailed=false`·실제 exit0/non-OOM·stopped state를 확인합니다. compaction 후 전체20객체의 GET/LIST·size·SHA·private full copies와 시점별6/12/12행·snapshot3·현재 파일1개를 baseline으로 사용합니다. 이는 새 재시작 시험의 fixture 준비이며 기존 compaction 성과를 중복 계산하지 않습니다.
3. Trino/reader가 아직 생성되지 않았고 Spark가 stopped인지 확인합니다. 실제 PostgreSQL17.11·제어 함수 EXECUTE 권한·고정 catalog schema와 전체 logical rows·namespace properties·같은 database cluster identity를 읽습니다. 다른 client backend가 남거나 권한/identity가 맞지 않으면 실패하며 grant·강제 연결 정리·root fallback을 하지 않습니다.
4. 소유 PG full CID·Created·config/host/mount·data volume·PID/startTicks/StartedAt·실제 `StopSignal=SIGINT`를 다시 대조합니다. 그 CID만 정상 stop하고 실제 stopped·non-OOM·exit0·원 postmaster 소멸을 확인합니다. 불명확 종료·timeout·137을 정상 종료로 정규화하지 않습니다.
5. 같은 CID·Created·고정 config·같은 volume을 유지한 채 명시 start를 정확 한 번 수행합니다. 새 postmaster identity/StartedAt·같은 system identifier·version·database와 bounded readiness를 확인합니다. 실제 Docker RestartCount0을 확인하며 수동 start 횟수가 곧 RestartCount1이라고 가정하지 않습니다. 새 cluster 초기화·init SQL 재실행·이미지 fallback·자동 재시도는 없습니다.
6. 새 연결로 catalog 전체 logical rows·schema·namespace properties·current/previous metadata pointer가 같은지 확인합니다. `pg_isready`나 socket 성공만으로 보존을 판정하지 않습니다. 정상 checkpoint/WAL/통계 등 PostgreSQL 물리 파일이 같은 bytes여야 한다고 요구하지 않습니다.
7. fresh Trino를 처음 시작해 기존 고정 SELECT10을 실행합니다. 독립 golden과 Spark의 실제 baseline으로 Bronze 시점별6/12/12·현재12, Silver12(성공7/실패3/중복2), snapshot3·현재 data file1·row fingerprint를 대조합니다. catalog logical rows/pointer·새 PG process·Garage/Spark state도 다시 확인합니다.
8. Trino를 정상 종료하고 실제 exit0또는143·비 OOM·동일 stop target을 확인합니다. signal 전달 자체를 직접 관측했다고 주장하지 않습니다. 두 heavy JVM이 닫힌 뒤 read-only Python reader를 한 번 실행해 PG 재시작 전 Spark가 저장한 전체20객체 bytes 및 기존14객체를 다시 GET하고 stable LIST를 대조합니다. reader는 GET/LIST만 사용합니다.
9. 같은 PG post-start process·Garage process·Spark stopped state와 JDBC pointer·source/tool 불변을 마지막에 확인합니다. 검증한 자기 컨테이너와 initializer만 stopped 상태로 정리합니다. 컨테이너/volume 제거·snapshot expiration·object GC를 수행하지 않습니다. 정리·source/tool 검사까지 포함한 실제 workload clock이600초 이내여야 PASS입니다.

## 고정 소스와 작은 adapter

새 소스는 `run_catalog_restart.py`, `catalog_lifecycle.py`, 두 pure test, 이 README의5개입니다. 새 manifest는 exact own5와 frozen18, 총23 source를 고정합니다. manifest 자체는 자기 hash 대상이 아니며 workflow는 checkout source SHA와 manifest literal로 묶습니다.

frozen18은 기존 Cloud runtime/Spark/Silver16개와 old `cloud-lakehouse-restart/run_restart.py`, 그 manifest 자체입니다. 원 Cloud manifest 지문은 `c63aded0a891bb66cb1fb2de591d67e237467681eb4a4e5a337b9d1d1b02d5e8`, old Trino restart manifest는 `6c9d7fd5e50f295aefc60191f9f3f49e745f166bb070c590f461c82dd4aed3b6`입니다. old `source_snapshot()`/`main()`을 호출하거나 `trino_lifecycle`을 import하지 않습니다. old `prepare()`/`ready()` 정의만 검증한 source bytes에서 불러옵니다. 실제 import closure가18개라는 전제는 이 범위에 한합니다.

기존 factory의 full configuration·mount·network·RestartCount0·한 역할당 최초 start guard는 변경하지 않습니다. 새 catalog adapter만 검증된 PG의 pre-stop→stopped→post-start 한 transition을 증명합니다. `started_roles`를 지우거나 generic guard를 완화하지 않습니다. Trino 전용 TERM 종료 helper를 PG에 적용하지 않으며, 새 PG proof는 private canonical bytes로 보존합니다.

이전 source/helper/manifest·증거는 수정하지 않습니다. 새 role·image/JAR·storage client·registry credential·runtime dependency를 추가하지 않습니다. PostgreSQL17.11·Garage2.4.1·Spark4.1.1/Java21·Trino483 image digest와 Iceberg runtime/aws1.11.0·PostgreSQL JDBC42.7.14 JAR bytes는 기존 고정 계약을 사용합니다.

## 실행 경계와 명령

새 `ubuntu-24.04` GitHub hosted runner·own repo·manual main·첫 attempt·기본 false opt-in 전용입니다. PR에서는 Docker/SQL 없는 pure 검사만 수행합니다. SSH·미니 PC·운영 endpoint·새 PAT·repository secret·GHCR 게시·Argo/PVC 변경은 없습니다. 내부 network만 사용하며 host port·host network·외부 writer를 허용하지 않습니다.

```sh
CLOUD_CATALOG_RESTART_OPT_IN=true python3 -B \
  infra/cloud-catalog-restart/run_catalog_restart.py \
  --source-manifest-sha256 <reviewed-runtime-manifest-sha256> \
  --ack-fresh-cloud-postgres-catalog-restart
```

실제 실행에는 정확한 `SOURCE_COMMIT`과 workflow metadata도 필요합니다. manifest literal이나 실제 결과를 이 문서에서 만들지 않습니다. 새 scope는 `FRESH_CLOUD_POSTGRES_CATALOG_NORMAL_RESTART`, 공개 경로는 `.local/cloud-catalog-restart-public/summary.json`, private root/project는 `cloud-catalog-restart-<nonce>`입니다.

local Docker daemon만 허용하고 새 private empty Docker config를 사용합니다. Docker client와 Compose plugin의 실제 binary·경로·파일 identity·SHA 및 관련 환경을 workload 전후로 대조합니다. tool 경로·환경·실제 inspect/SQL/proof·PID/CID·DB system identifier·volume명·credential·전체 object copy는 private에만 둡니다.

## 시간·자원과 공개 판정

PG/Garage는 각각 CPU0.5·512MiB·PID256, Spark는 CPU1·3GiB·PID512, Trino는 CPU1·4GiB·PID512, reader는 CPU0.1·128MiB·PID16입니다. heavy JVM은 순차 실행하며 기존 planned peak5GiB·시작 전 MemAvailable7GiB·준비 disk8GiB gate를 유지합니다. 이 값은 ephemeral fixture 조건이며 실제 최대 RSS·성능·운영 용량이나 보류한 예산/quota 정책이 아닙니다.

준비/build/pull은 bounded workflow 안에서 workload clock 밖에 둡니다. 최초 PG/Garage start부터 기존 단일600초 clock을 유지하고 fault 전에 PG restart·Trino·reader·cleanup을 위한420초 reserve를 확인합니다. clock을 리셋하지 않습니다. PASS에는 source/tool 검사·cleanup 후 실제 monotonic 잔량도 확인하여 millisecond 절삭으로 늦은 통과가 생기지 않게 합니다. 모든 실패가600초 안에 강제 종료된다는 보장은 없으므로 workflow timeout과 bounded best-effort cleanup을 별도로 유지합니다.

공개 summary는 정확28 top-level key로 phase·유한 failureCode·selectedFailure·검사 flags·source/manifest·시간·자원 설정·정리 결과를 담습니다. `result`는 PASS일 때만 다음7개입니다: `catalogRestart`, 기존 SELECT10의 `read`, 실제 `trinoActualExitCode`, `trinoStopRequested`, `signalDeliveryDirectlyObserved`, `oldWarehouseObjects`, `wholeWarehouseObjects`.

`catalogRestart`는 actual exit0·명시 start1회·실제 RestartCount0과 같은 CID/config/volume/system identifier·새 postmaster·catalog tables2/관측한 namespace property rows2..32·logical 보존·같은 Garage·Spark stopped·fault 시 Trino 부재·CONFIGURED_SIGINT 등 정확19필드만 공개합니다. DB ID·private row나 SQL을 공개 결과로 넘기지 않습니다. `selectedFailure`도 알려진 source enum·실제 line·고정 phase만 허용하고 exception class/message·명령 인수·환경을 포함하지 않습니다. 실제 실패는 보존하고 전체 실험을 재시도하지 않습니다.

cleanup은 검증한 own full CID만 중지합니다. `ownedBoundContainersStopped`는 제거 완료가 아닙니다. unknown/unbound target은 새 정리 권한으로 채택하지 않으며, 불명확 정리·source/tool 확인·deadline 실패는 PASS가 아닙니다. source/tool unchanged=false는 확인 미완료일 수 있으며 그 자체가 변조 증거는 아닙니다. volume은 남기고 runner storage는 ephemeral입니다.

```sh
python3 -B -m unittest discover -s infra/cloud-catalog-restart -p 'test_*.py' -v
```

pure 검사는 새/기존 source closure·hash/중복 key·POSIX source file·guarded module load·opt-in·typed public projection·writer 부재·unknown cleanup·도구 지문·진단 privacy·late PASS와 catalog adapter의 실제 경계를 fixture로 검증합니다. Docker·SQL·Spark·Trino·네트워크·credential을 호출하지 않습니다. Linux 전용 file/plugin 경계는 hosted Linux에서 검사하며 Windows에서 이를 우회하는 production fallback은 없습니다.

실제 PASS 뒤 run/source/manifest/summary hash를 고정해 기존 evidence catalog 한 항목으로 연결합니다. 새 전체 UI 카드는 만들지 않습니다. 이번 소스만으로 운영 가용성·HA·host restart·동시 writer·crash recovery·장기 보관·SLA를 주장하지 않습니다. 토큰 회전·운영 예산·PR102 보류를 유지합니다.
