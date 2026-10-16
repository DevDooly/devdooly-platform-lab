# 새 Cloud Spark → Trino 연결과 작은 파일 compaction 후보

## OOM killer가 활성인 표현만 비교하는 새 후보

상태: `SOURCE_ONLY_NOT_RUN`. 이 새 runtime 소스는 아직 full trial을 실행하지 않았습니다. 앞선 실제 실패는 그대로 남기며 재시도하지 않습니다. 아래 기존 시작 경계 설명과 SOURCE_ONLY 표시는 당시 작성한 소스 준비 상태도 포함하며, 이번 후보의 변경은 이 절에 따릅니다.

별도 HostConfig 진단 [38842699117](https://github.com/DevDooly/devdooly-platform-lab/actions/runs/38842699117)의 source `17d8efe52a905a97245d42b60e84b0859f61a293`, summary SHA `462615cfbf99ceba0349a4100941f8fc1704561cbdcf39224248e0f3abdf3e4d`는 2026-10-16 02:53:22 UTC에 실패했습니다. PG는 Running으로 관측됐고 전체 signature 중 HostConfig만, 알려진 71개 필드 중 **OomKillDisable만 변경**됐습니다. 다른 70개와 unknown fields·Config·Mounts 내용·ID·image·created는 변경 false였습니다. Garage는 created였고 Mounts 순서만 달랐습니다. command·진단 관측 실패는 없었고 initializer 종료는 확인했지만 모든 자기 컨테이너 종료는 미확인입니다. 공개 boolean은 **값이나 변경 방향을 기록하지 않았으므로 false→null을 실제 관측했다고 주장하지 않습니다.** 앞선 `bf8c9057`·`eebb19a8` 및 더 이전 실패도 성공으로 바꾸지 않습니다.

[Docker 28.0.4 create 경로](https://github.com/moby/moby/blob/v28.0.4/daemon/create.go#L67-L99)는 검증 뒤 기본 설정을 적용하고, [adaptContainerSettings](https://github.com/moby/moby/blob/v28.0.4/daemon/daemon_unix.go#L349-L352)는 nil을 false pointer로 채웁니다. [start 재검증](https://github.com/moby/moby/blob/v28.0.4/daemon/start.go#L56-L62)과 [미지원 OomKillDisable 처리](https://github.com/moby/moby/blob/v28.0.4/daemon/daemon_unix.go#L439-L445)는 pointer를 nil로 되돌릴 수 있습니다. 이것은 이번 좁은 호환 규칙의 코드 근거이며, 위 실제 실행에서 그 경로·방향이 발생했다는 직접 증거는 아닙니다.

새 `canonical_host`는 `OomKillDisable` key가 **존재**하고 값이 null 또는 정확한 boolean false일 때만 받습니다. 둘 다 OOM killer를 끄지 않는 표현으로 비교하며 true·0·1·문자열·다른 타입·key 누락은 거부합니다. 원본 inspect dict를 수정하지 않고 복사본의 이 값 하나만 false로 맞춘 전체 canonical JSON 문자열을 signature에 넣습니다. 다른 모든 필드·중첩 값·JSON 타입·배열 순서·중복은 그대로 비교합니다. 실제 raw HostConfig의 CPU·memory·PID·network·권한 검사와 전체 image/config/mount/CID/owner 검사는 그대로입니다. 정상·cleanup 경로 모두 이 같은 검사를 거쳐야 하며 true나 알 수 없는 표현의 대상을 stop하는 권한을 넓히지 않습니다.

다음 새 실행이 허용 표현을 **실제 검사**해야 합니다. 최종 full PASS일 때만 public `enabledOomKillerRepresentationsVerified=true`를 기록하고, 실패 시 null로 남깁니다. 개별 값·변경 방향·HostConfig 원문은 공개하지 않습니다. 기존 23개 검사의 fixture에 이 필드의 명시 false만 추가하고, 새 4개 검사로 present null/false·원본 비변경·전체 나머지 내용/타입 보존, 5개 role의 create/start/정상 Trino stop, missing/true/nonbool/unknown/다른 자원 변화의 mutation 전 거부를 확인합니다. 실행된 순수 검사 결과는 별도 source manifest에 기록합니다.

임시 `run_base_config_readback` input/job와 verify·기존 세 trial의 전용 skip 조건을 제거하여 이전 full framework로 되돌리고 full runtime manifest SHA만 새 후보로 바꿉니다. `infra/cloud-base-config-ci` probe/test는 역사 bytes 그대로 남기며 현재 full source와 pin이 달라 현재 ref에서 지원하지 않습니다. 새 full 시도는 root가 별도로 선택하며 자동 재시도·추가 좁은 진단·clock reset은 없습니다. 600초·SQL/fixture/JAR·resources·권한·Trino PID/startTicks/cgroup·normal stop 및 failure cleanup의 명령과 순서는 바꾸지 않습니다.

**첫 실제 실행 실패.** 새 GitHub 격리 실행은 준비 검사를 통과한 뒤 서비스 시작 단계에서 실패했습니다. 실패한 명령과 전체 컨테이너 종료 상태는 확인하지 못했고 Spark·Trino·compaction 결과도 입증하지 못했습니다. [첫 실행의 원문과 한계](../../docs/evidence/cloud-lakehouse/README.md)를 보존합니다. 기존 Cloud Spark8·Mini PC native7은 별도 기록이며 다시 실행하지 않았습니다. 아래 runtime manifest의 SOURCE_ONLY 상태는 검토한 소스 패킷의 작성 상태이고, 실행 결과는 별도 근거로 확인합니다.

## 시작 경계 수정 후보: SOURCE_ONLY_NOT_RUN

이 후속 소스는 아직 새 full trial을 실행하지 않았습니다. 첫 두 full-trial 실패와 별도 두 startup 실패를 성공으로 바꾸지 않습니다. 첫 startup source `98833225a62ca21660a94935ee0f1ab077f93be2`의 요약 SHA `a3b24f385c812f5a404c012d81113a88e3b851fec53ffa51eb73a7f67a4d45da`는 mount 변경만 관측했습니다. 그 다음 별도 source `f3f5c52993ceb00fd70f73c17f0ec6d2d236b26e`의 Actions `38837630164` 요약 SHA `c41ce401a46e061bb829902de97b7399cbf20288ad274612d6f8703a4ae8b07d`에서는 Garage의 **순서만 바뀐 mount**와 실제 PG Compose start의 `ENV_FILE_MISSING_SIGNATURE`를 구분했습니다. 이 시도의 signature를 과거 두 rc1 실패의 단일 원인으로 소급하지 않습니다.

수정은 두 경계와 시작 전 확인으로 제한합니다. 실제 `Mounts`는 기존 bind/named/anonymous·RO/RW·source·destination·owner·network·limits 검사를 그대로 거친 뒤, 전체 member를 canonical JSON 문자열의 정렬된 목록으로 비교합니다. 모든 알려지지 않은 필드·중첩 값·JSON 타입·중복을 유지하며 목록의 순서만 비교에서 제외합니다. mount 검사를 없애거나 필드를 일부 선택하지 않습니다. 같은 내용의 순서 변화는 허용하지만 내용 변경은 계속 실패합니다. [Moby 28.0.4의 MountPoints 순회](https://github.com/moby/moby/blob/v28.0.4/container/container_unix.go#L397-L412)는 순서 변화 가능성을 설명하며, 실제 구분은 위 별도 진단 결과에 따릅니다.

원래 Compose create로 만든 container를 새로 inspect하여 전체 구성·full CID가 bound identity와 같고, not-running·exit 0·nonOOM·PID 0·zero StartedAt인 **아직 시작하지 않은 대상**만 `docker start <verified-full-CID>`로 한 번 시작합니다. 이름 조회·새 container 생성·`docker compose start`의 전체 model 재해석을 사용하지 않습니다. 이미 외부에서 시작한 같은 CID도 거부하며 요청 전 immutable intent와 once-only 표시는 유지합니다. Compose 2.38.2의 [start project loading](https://github.com/docker/compose/blob/v2.38.2/cmd/compose/start.go)과 env-file 처리 범위를 피해 이미 검증한 container를 시작하는 변경입니다. 원래 model과 Trino env-file 작성 순서는 그대로이고 dummy env를 넣지 않습니다.

5개 role의 순차 gate, 동일 이미지/limit/mount/권한, 초기화, SQL/fixture/JAR, 단일 600초 clock과 reserve, 정상 Trino proc PID/startTicks/cgroup 확인, generic failure cleanup은 변경하지 않습니다. 추가 GET·mutation·재시도·clock reset·강제 cleanup은 없습니다. start command 진단 category는 이제 `CONTAINER_START`와 기존 stage로 표시하며 원래 Compose command의 관측 분류도 코드에 보존합니다.

임시 `run_cloud_startup_probe` input/job와 그 전용 skip 조건은 workflow에서 제거합니다. 기존 일반 verify·수동 세 trial 경로를 startup 추가 이전 bytes의 구조로 되돌리고, full-trial runtime manifest SHA 한 곳만 새 후보에 맞춥니다. 역사 `infra/cloud-startup-ci`의 source pin은 이전 `5f60`을 그대로 보존하므로 현재 ref에서 재실행하지 않습니다. 해당 README가 명시한 이전 ref의 역사 시험과 새 full-trial 후보를 구분합니다.

새 순수 검사는 기존 15개 lifecycle/SQL 계약과 4개 명령 privacy 계약을 유지하고, reader start의 정상 transport 기대만 검증한 full CID 호출로 바꿉니다. 새 4개는 전체 mount 내용·타입·중복/unknown field, 순서 변화 허용과 내용·RO·source·owner·CID·limits 거부, 5개 role의 once-only와 heavy 순서, 외부 PID/StartedAt·기존 정상 Trino stop의 PID/CID/startTicks drift 거부를 확인합니다. C-only Windows 실행에서 총 **23개 실패·오류·skip 0**입니다. Docker·Linux 시작·Spark/Trino 결과를 검증한 수치가 아닙니다.

새 GitHub-hosted Linux runner에서만 실행할 수 있다. 새 UUID Compose project·local volume·Garage bucket의 물리 identity를 확인하고, 기존 고정 Silver 코드·합성 fixture·실제 lock의 세 JAR를 그대로 사용한다. 이미지 build와 pull은 준비 단계로 별도 표시한다. 첫 PostgreSQL/Garage start 직전 단 한 번 만든 **600초 monotonic clock**을 모든 workload 단계가 공유한다. 초기화 실패나 deadline에는 같은 mutation·SQL을 재접수하지 않는다.

Spark application 한 개가 Bronze 6+6행과 기존 Silver 변환·MERGE1·같은 application의 순차 replay1/write0을 수행한다. 실제 current data file이 정확히2개·각6행·작은 파일이고 delete file이 없을 때만 `rewrite_data_files`를 한 번 호출한다. 실제 반환 rewritten2/added1/failed0과 current file2→1을 검사한다. Snapshot은 **append6 → append12 → replace12**이며 ID의 수치 크기나 시간 동률 대신 실제 parent 연결로 순서를 정한다. Snapshot expiration·orphan removal·GC는 없다. [Iceberg1.11 procedure와 실제 출력 계약](https://raw.githubusercontent.com/apache/iceberg/apache-iceberg-1.11.0/docs/docs/spark-procedures.md#L341-L419), [replace operation 소스](https://raw.githubusercontent.com/apache/iceberg/apache-iceberg-1.11.0/core/src/main/java/org/apache/iceberg/BaseRewriteFiles.java#L39-L42)

Spark `stop()` 반환·container exit0/nonOOM를 확인한 뒤 Trino483을 시작한다. 같은 새 JDBC catalog-name `phase6`·schemaV1·DB·Garage warehouse를 사용하며, 고정 SELECT10개로 버전/DOUBLE schema·세 snapshot 전체 행·current Bronze/Silver·snapshot/file metadata를 비교한다. Trino는 같은 CID·PID/startTicks를 묶어 명시적 stop30 반환0과 실제 exit0 또는143·nonOOM을 확인한다. 관측된 exit 값을 그대로 남기며 signal 전달 자체를 관측했다고 주장하지 않는다. 그 뒤에만 pinned Spark base image의 **Python-only reader**를 한 번 시작한다. 이 reader는 Java/Spark/JAR를 호출하지 않고 새 warehouse prefix의 GET/LIST만 수행한다. [Trino JDBC 연결](https://raw.githubusercontent.com/trinodb/trino/483/docs/src/main/sphinx/object-storage/metastores.md#L556-L601), [time travel](https://raw.githubusercontent.com/trinodb/trino/483/docs/src/main/sphinx/connector/iceberg.md#L1878-L1890), [이미지 내 CLI](https://raw.githubusercontent.com/trinodb/trino/483/core/docker/Dockerfile#L61-L68)

Compaction 전의 모든 warehouse 객체를 전체 복사·크기·SHA로 고정하고, compaction 후에도 기존 bytes가 보존되는지 확인한다. Trino 종료 뒤에는 compaction 후 전체 객체 집합과 전체 bytes를 다시 비교한다. JDBC metadata pointer도 Trino 전후 동일해야 한다. 같은 key 집합의 여러 GET pass와 서로 다른 객체 수를 구분한다. 2→1은 current snapshot의 논리적 파일 수이며 bucket 사용량 감소·처리 성능·SLA를 증명하지 않는다.

행 비교는 원래 응답과 column schema를 남긴 뒤 실제 DOUBLE을 확인하고 `sensor_value`의 JSON 숫자 표현만 float로 맞춘다. 값·열·input_sequence와 frozen golden을 먼저 비교하며, Cloud8의 원래 `row_sha` 직렬화와 일치해야 한다. Native7의 순서 의존 fingerprint는 변경하지 않는다. Native7의 빈 snapshot 포함0/6/12와 이 시험의6/12/12는 서로 다른 기록이다.

| 프로세스 | CPU / 메모리 / PID 제한 |
| --- | --- |
| PostgreSQL·Garage 각각 | 0.5 / 512MiB /256, 기존 Cloud8과 동일 |
| Spark | 1 /3GiB, heap1536MiB /512, 기존 Cloud8과 동일 |
| Trino | 1 /4GiB, heap2GiB /512; 기존 native 설정의 JVM/질의 제한을 재사용 |
| 후속 Python reader | 0.1 /128MiB /16; 두 heavy JVM 정상 종료 뒤에만 시작 |

root가 정한 순차 최대 계획 메모리는 **5GiB**, 시작 전 실제 `MemAvailable` 조건은 **7GiB 이상**이다. Spark와 Trino를 동시에 시작하지 않는다. 600초에는 준비 build/pull을 넣지 않지만 workload와 자기 자원 정리를 넣는다. 실패 때 bounded private 로그 수집 뒤 자기 full CID만 정지하며, 정지 결과가 미관측이거나 실제 전체 경과가600초를 넘으면 성공하지 않는다. Docker 통신 미관측으로 정지 자체를 확인할 수 없으면 unknown을 남기고 자동 재시도하지 않는다. Volume은 삭제하지 않으며 GitHub runner의 임시 저장소를 지속 백업으로 표시하지 않는다.

소스 입력은 `runtime-manifest.json`의 whole SHA와 기존8개 파일 SHA로 확인한다. `SOURCE_COMMIT`·workflow의 `GITHUB_SHA`·읽기 전용 `git rev-parse HEAD`가 같아야 한다. 다음 명령은 미래 root 승인 실행 인터페이스이며 작성 과정에서는 실행하지 않았다.

```sh
SOURCE_COMMIT=<actual-checkout-40hex> python -B infra/cloud-lakehouse-ci/run_trial9.py \
  --source-manifest-sha256 <reviewed-runtime-manifest-64hex> --ack-fresh-cloud-trial9
```

공개 artifact 후보는 `.local/cloud-trial9-public/summary.json` 하나뿐이다. Raw 로그·SQL 결과·JDBC/S3 경로·container identity·자격증명은 새 private 폴더에만 남으며 artifact 업로드 대상으로 삼지 않는다. Reader는 읽기 전용 코드지만 Spark가 사용한 새 단일 bucket read/write key를 RAM에서 재사용하므로 ACL 자체가 write를 금지한다고 주장하지 않는다. 이 새 시험의 결과를 Kubernetes·Mini PC 보존·재시작/장애 복구·동시성·현재 가용성·전체 Phase6 완료로 확대하지 않는다.

Offline 검사는 snapshot/파일·procedure 계약, 원래 Cloud hash의 정렬 roundtrip과 DOUBLE 투영, 고정10 SELECT/JSON 경계, 단일clock·heavy 순서·unknown 재시작 차단, Compose Mounts API의 실제 owned mount 검증을 대상으로 한다. 첫 실행의 test source locator1오류와 Windows의 Linux path fixture1오류는 각각 수정 이력에 남겼다. 이는 runtime 실패나 성공 기록이 아니다.

## 명령 진단을 추가한 별도 실행

첫 실행의 255ms 실패와 정리 미관측은 원문 그대로 보존합니다. 검토한 새 runner와 runtime manifest로 별도 GitHub 격리 실행을 한 번 수행해 실패 명령을 관측합니다. 첫 GitHub 실행을 다시 시작하거나 결과를 바꾸지 않습니다. 각 실행은 자기 workload의 단일 600초 예산을 사용하며, 새 실행 결과는 첫 실패와 별도 근거로 기록합니다.

새 summary schemaVersion2에 `commandDiagnostics`와 `cleanupDiagnostics`만 추가한다. 각 command event는 sequence·고정 stage/category·checkRequested·returnCode·timedOut·고정 outcome으로 제한한다. Compose start의 PostgreSQL/Garage/Spark/Trino/reader 분류도 고정 enum이며, 알려지지 않은 인자 값은 출력하지 않는다. `check=False`의 예상 가능한 nonzero는 lastCommand에 기록하되 fatal failure로 바꾸지 않는다. timeout은 check 여부와 무관하게 예외로 전파되고 고정 timeout 사실을 남긴다. Failure16개까지 첫 실패부터 보존하며, 후속 cleanup 실패가 최초 command 실패를 덮지 않는다. 초과분은 truncated로 표시한다.

인자·경로·CID·object key·stdout/stderr·exception message·TimeoutExpired.cmd는 공개 event에 넣지 않는다. 원래 non-sensitive raw 출력은 private 파일에만 남기고 credential-sensitive 출력 생략 정책은 유지한다. cleanup의 initializer/container 결과는 STOPPED_VERIFIED 또는 FAILED_OR_UNOBSERVED로만 구분하며 미관측을 성공으로 바꾸지 않는다. 실행 명령·기존 timeout/check 동작·single600s clock·SQL·자원·권한·정리 절차는 변경하지 않는다. 한 실행 안에서 추가 명령·자동 재시도·clock 초기화나 추정 원인에 따른 동작 변경은 하지 않습니다.
