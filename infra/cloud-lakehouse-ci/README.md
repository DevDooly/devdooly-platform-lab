# 새 Cloud Spark → Trino 연결과 작은 파일 compaction 후보

**첫 실제 실행 실패.** 새 GitHub 격리 실행은 준비 검사를 통과한 뒤 서비스 시작 단계에서 실패했습니다. 실패한 명령과 전체 컨테이너 종료 상태는 확인하지 못했고 Spark·Trino·compaction 결과도 입증하지 못했습니다. [첫 실행의 원문과 한계](../../docs/evidence/cloud-lakehouse/README.md)를 보존합니다. 기존 Cloud Spark8·Mini PC native7은 별도 기록이며 다시 실행하지 않았습니다. 아래 runtime manifest의 SOURCE_ONLY 상태는 검토한 소스 패킷의 작성 상태이고, 실행 결과는 별도 근거로 확인합니다.

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
