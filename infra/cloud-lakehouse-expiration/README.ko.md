# 새 격리 warehouse의 Iceberg snapshot 만료

아직 실행하지 않은 후속 실증 소스입니다. GitHub-hosted의 새 합성 warehouse에서 snapshot 하나와 불필요한 data object 하나를 만료하고, tag와 최근 snapshot이 공유하는 파일·조회 결과를 보존하는지 검증합니다. 운영 Kafka·미니 PC·Kubernetes/PVC·보관 백업·기존 native 근거와 warehouse를 입력으로 받지 않습니다.

| 단계 | 행 수 | 실제 파일 관계의 기대값 | 보존 기준 |
| --- | --- | --- | --- |
| S1 append | 6 | a1 | 새 tag `retained_first6` |
| S2 append | 12 | a1 + a2 | 이 snapshot만 만료 |
| S3 compaction | 12 | b1 | 최근 두 snapshot |
| S4 append | 18 | b1 + a3 | current 및 최근 두 snapshot |

표의 이름은 설명용 alias입니다. wrapper는 실제 Iceberg table UUID·current·4개 snapshot의 부모/commit 시각·정확한 tag/main refs와 파일 집합을 수집한 뒤 순수 계약에 전달합니다. S1 tag, S3/S4와 Silver가 참조하는 객체 및 기존 metadata JSON을 보호하고, live data의 차집합이 a2 하나일 때만 진행합니다. 같은 관측 도중 실제 catalog metadata pointer와 bytes가 달라지거나 미지원 형태·추가 ref·GC 비활성·객체 128개 초과를 발견하면 호출하지 않습니다.

`expire_snapshots`는 S3의 실제 commit 시각을 cutoff로 삼고 `retain_last=2`, `stream_results=true`로 한 번 호출합니다. `max_concurrent_deletes=1`도 전달하지만 S3FileIO의 bulk deletion에서는 무시될 수 있어 한 스레드 삭제를 보장한다고 주장하지 않습니다. 만료 후 정확히 S1/S3/S4가 남고 current와 tag가 같아야 합니다. Spark의 S1 6행·S3 12행·current 18행을 합성 원본과 대조하며, Silver 12행과 파일 bytes/hash도 보존해야 합니다. a2는 만료 전 전체 GET와 만료 후 같은 key의 `NoSuchKey`/404를 확인하고 공식 결과의 data 삭제 1개·delete/statistics 파일 0개·manifest/list 제거 수를 실제 객체 차집합과 대조합니다. 403·timeout·단순 LIST 부재는 삭제 확인이 아닙니다.

고정 버전은 Spark 4.1.1, Iceberg 1.11.0, Trino 483, Garage 2.4.1, PostgreSQL 17.11입니다. 기존 `cloud-lakehouse-ci` 7개 runtime source와 base pin 8개 및 그 manifest를 그대로 검사합니다. `make_attempt`의 5-role·image/config/mount·새 volume·소유 CID·단일 start 검사를 재사용하며 원본 전역이나 함수를 변경하지 않습니다. 기존 `bootstrap_trial9.execute`가 같은 session에서 append6→12→compaction12와 Silver를 검증한 다음 새 wrapper가 tag·append18·만료를 수행합니다. 기존 gzip 기본값도 catalog 초기화 전에 그대로 설정합니다. 새 pure는 컨테이너에서 `expiration_contract`라는 별도 이름으로 읽어 기존 `contract`와 충돌하지 않습니다.

원본 prepare는 Spark 실행과 3-snapshot 전용 후조건까지 포함하므로 통째로 호출하지 않습니다. 새 orchestrator는 필요한 이미지/고정 JAR 준비·별도 내부망·빈 PG/Garage volume·새 bucket/key 설정 구간만 명시적으로 옮겼습니다. 새 Spark/reader command는 실제 desired plan과 Docker Config.Cmd가 일치해야 합니다. 유일한 writer는 이 새 Spark process이며, Trino/reader는 그 정상 종료 뒤에만 생성·시작합니다. metadata 안정성만으로 외부 writer 부재를 추정하지 않습니다. 대신 UUID project의 사전 부재, 기존 volume 채택 거부, 실제 내부 network에 속한 소유 CID 집합, 고정 source/command와 순차 실행이 경계입니다.

Trino는 version·현재 Bronze 18행·DOUBLE schema·기존 Silver 12행의 고정 SELECT 4개만 수행합니다. 전후 JDBC pointer와 PG/Garage PID/process identity·initializer를 대조합니다. 두 JVM이 정상 종료한 뒤 Python reader가 만료 직후 warehouse 전체 GET bytes와 다시 대조하고 a2의 `NoSuchKey`를 확인합니다. Trino의 기본 7일 최소 만료 정책은 낮추지 않습니다. 기존 3-snapshot/원본 전부 보존 oracle도 변경하지 않습니다.

workload clock은 첫 PG/Garage 시작부터 한 번만 시작하며 600초입니다. Spark 180초, Trino 준비 90초, reader 60초 상한과 단계별 cleanup 여유 90초를 유지합니다. 90초는 단계 진입 시 남기는 여유이며 독립 cleanup 타이머가 아닙니다. 만료 호출의 Python alarm은 남은 예산 내 최대 60초이며, timeout이 JVM 작업의 즉시 중단을 증명하지는 않습니다. 최종 정리 시간까지 600초를 넘으면 전체 성공이 아닙니다. MemAvailable 7GiB·준비 disk 8GiB·계획한 순차 peak 5GiB 기준은 기존과 같습니다. 고정 JAR vendor는 기존 전체 600초, 각 image pull/build는 240초 상한이며 workload clock 밖입니다. 전체 hosted job TTL과 manual-only workflow 연결은 별도 단계입니다.

metadata commit과 객체 삭제는 서로 원자적이지 않습니다. 호출이 시작된 뒤 오류·부분 관측·timeout이면 UNKNOWN 또는 전체 FAILED 기록을 남기며 자동 만료 재호출·snapshot 복원·파일 재생성하지 않습니다. 만료의 논리적 후조건과 Spark 종료·후속 조회·cleanup의 전체 성공을 분리합니다. 이 소스의 finally는 사전에 bind된 소유 CID의 stop만 요청하고, unbound CID를 새 정리 대상으로 채택하지 않습니다. volume/network 삭제는 구현하지 않았고 `volumesDeleted:false`를 유지하며, 임시 자원의 수명은 기존 모델처럼 hosted VM 종료에 맡깁니다. prune·`remove_orphan_files`·Garage 물리 블록 GC는 없습니다. 보존한 과거 metadata JSON의 bytes가 같다는 사실도 이미 만료한 S2의 복구 가능성을 뜻하지 않습니다.

`contract.py`와 `test_contract.py`는 순수 RAM 경계입니다. 의미 있는 6개 test method가 공유 파일/tag 보호, refs/GC/identity 변경, 시각·타입·overflow, 잘못된 closure, 보존 객체 삭제/변경, commit·delete 부분 결과/잘못된 404·counter를 검증합니다. Python 3.12.14의 순수 검사 한 회는 6개 통과·실패/오류/skip 0개였고, pin 22개가 검사 전후 같았습니다. 이때 Docker·Spark·Cloud·만료는 실행하지 않았습니다. 이후 상수 참조와 Bronze 18행 collector를 바로잡은 wrapper/orchestrator도 아직 실행하지 않았습니다. 이 순수 검사 결과를 운영 GC·장기간 가용성·공간 회수 성과로 옮겨 적지 않습니다. 기존 보존 계획기의 KEEP와 `applyEnabled:false`는 그대로입니다.

공식 근거: [Iceberg 1.11.0 expire_snapshots](https://iceberg.apache.org/docs/1.11.0/spark-procedures/#expire_snapshots), [tag DDL](https://iceberg.apache.org/docs/1.11.0/spark-ddl/#alter-table-create-tag), [Spark procedure 구현](https://raw.githubusercontent.com/apache/iceberg/apache-iceberg-1.11.0/spark/v4.0/spark/src/main/java/org/apache/iceberg/spark/procedures/ExpireSnapshotsProcedure.java), [commit과 cleanup 구현](https://raw.githubusercontent.com/apache/iceberg/apache-iceberg-1.11.0/core/src/main/java/org/apache/iceberg/RemoveSnapshots.java), [Trino 483 정책](https://raw.githubusercontent.com/trinodb/trino/483/docs/src/main/sphinx/connector/iceberg.md).
