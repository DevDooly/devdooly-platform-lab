# Iceberg 공개 계획 2 — native7 교정을 반영한 준비본

상태: **PREPARED_NOT_RUN**. 초기 17개 준비 파일에서 파생한 새 계획입니다. 오프라인 생성기·검증기를 실행할 수 있지만 이 파생본으로 Kubernetes·PostgreSQL·Trino·Garage를 실행하지 않았습니다. 실제 성공은 별도의 [native7 증거](../../docs/evidence/iceberg-jdbc/README.md)입니다. 당시 private 실행 도우미·객체·실패 기록은 그대로 보존합니다.

새 범위는 `platform-lab-iceberg-plan2-20261016` namespace와 같은 이름의 새 bucket입니다. native7의 namespace·PVC·bucket·catalog를 재사용하지 않습니다. 이름이 이미 있으면 중단하며 다른 이름이 필요하면 명시적인 새 계획과 diff를 만듭니다.

## 반영한 교정

| 초기 계획 | 계획 2 |
| --- | --- |
| `s3.max-error-retries=0` | 유효 최소값 `1`: 최초 시도 1회·추가 시도 0회 |
| 데이터 append 둘만 검증 | CREATE의 빈 append 1개 + INSERT 둘, snapshot3·시점0/6/12행 |
| `summary['added-records']` | `element_at`으로 읽고 초기 key 부재는 NULL 보존 |
| CLI 끝 세미콜론을 HTTP에 전송 | 원문 보존·wire 끝 세미콜론 하나만 제거·각각 SHA/길이 기록 |
| API Service IP에 egress `ipBlock` | 실제 API Service selector와 namespace selector를 한 peer에 결합 |

설정은 Trino 483의 [최소값](https://github.com/trinodb/trino/blob/483/lib/trino-filesystem-s3/src/main/java/io/trino/filesystem/s3/S3FileSystemConfig.java#L327-L336)과 [SDK maxAttempts 전달](https://github.com/trinodb/trino/blob/483/lib/trino-filesystem-s3/src/main/java/io/trino/filesystem/s3/S3FileSystemLoader.java#L202-L214)에 따릅니다. [Trino map 계약](https://trino.io/docs/current/functions/map.html#subscript-operator), [Iceberg summary 조건](https://github.com/apache/iceberg/blob/apache-iceberg-1.11.0/core/src/main/java/org/apache/iceberg/SnapshotSummary.java#L247-L260)도 확인했습니다. 설정 교정이 과거 startup 오류의 유일한 원인을 입증하는 것은 아닙니다.

## 오프라인 재현

Python 3.10 이상에서 다음 명령은 서버·네트워크에 접속하지 않습니다. 출력은 새 파일이어야 합니다.

```sh
python3 -B -m unittest discover -s infra/iceberg-lab/tests -p 'test_*.py' -v
python3 -B infra/iceberg-lab/render_plan.py --output /tmp/new-stopped-plan.json
python3 -B infra/iceberg-lab/sql_plan.py
python3 -B infra/iceberg-lab/http_sql.py --output /tmp/new-http-request-plan.json
python3 -B infra/iceberg-lab/network_control_plan.py \
  --api-selector-json '{"app.kubernetes.io/component":"api"}' --output /tmp/new-control-plan.json
```

| 파일 | 하는 일 |
| --- | --- |
| [render_plan.py](render_plan.py), [proposal-stopped.json](proposal-stopped.json), [binding-pods.json](binding-pods.json) | 자격증명 없는 stopped 리소스14개·optional WFFC binder |
| [sql_plan.py](sql_plan.py), [query-plan.json](query-plan.json) | 고정 DDL·INSERT 둘·초기/6/12행·3 snapshot 검사 계획 |
| [http_sql.py](http_sql.py), [http-request-plan.json](http-request-plan.json) | 원문/wire bytes·SHA와 미제출 identity. POST·query ID 생성 없음 |
| [network_control_plan.py](network_control_plan.py) | 관측 입력의 Service→Pod→Endpoint UID/port/Ready 대조와 임시 selector 정책 계획 |
| [validation_contract.py](validation_contract.py), [store-capability-plan.json](store-capability-plan.json) | 별도 실제 preflight·multipart/range·재시작 수집 결과의 순수 검사 |
| [image-lock.json](image-lock.json), [resolve_images.py](resolve_images.py) | 초기 registry index/amd64/config metadata 보존·재조회 도구. 이번 파생본에서 재조회·layer pull하지 않음 |
| [private_secrets.py](private_secrets.py), [JDBC V1 DDL](sql/initialize-jdbc-v1.sql) | root private Secret 자료 작성·새 PostgreSQL 초기화 SQL 계획 |

위 selector는 **예시**입니다. 실제 실행에서는 API Service의 전체 selector와 `target_binding()`을 사용해 같은 namespace·Service·Pod·Endpoints와 기존 ingress 비격리를 검증해야 합니다. [Kubernetes selector 결합·주소 변환 경계](https://kubernetes.io/docs/concepts/services-networking/network-policies/#behavior-of-to-and-from-selectors)에 따라 같은 API 대상의 deny→temporary allow/200→자기 정책 제거→deny를 실제 관측해야 합니다. 원래 namespace의 정책은 바꾸지 않습니다. 렌더링만으로 `liveTargetBindingVerified`를 true로 표시하지 않습니다.

## 데이터·HTTP 계약

공개 V1 fixture는 **1,100 bytes·12행**, SHA `39ba10d8c47dce790f3ccc9c9134fea593d6de31f1f3a7992ca61d9f554da3b5`를 유지했습니다. 원래 순서·잘못된 시각/값·중복 ID도 보관합니다. 초기/첫/둘째 시점의 행은 0/6/12, distinct ID는 0/5/10, sensor-a/b는 0/0·5/1·8/4입니다. Java/Silver 처리의 7/3/2 기대값과 기준이 다릅니다.

Snapshot ID는 실행 뒤 얻는 양의 signed BIGINT입니다. 과거 native7 ID를 새 계획에 고정하지 않습니다. 첫 parent는 NULL, 이후 parent는 바로 앞 ID입니다. 초기 `added_records:null`은 key 부재이며 실제 SELECT 0행과 별도로 확인합니다. `total_records`는0/6/12, 데이터 append의 `added_records`는 각각6이어야 합니다. 세 실제 ID로 time travel0/6/12를 읽어야 합니다.

행 해시는 명시한 여섯 열 순서로 계산해 저장 JSON key 정렬의 영향을 받지 않습니다. 기존 6/12행 golden hash `411dc42e…`/`1c31bc69…`는 그대로입니다. 추가 필드·행 순서/값 변경은 거절합니다.

`http_sql.prepare()`는 문자열 내부와 trailing whitespace를 유지하며 끝의 세미콜론 하나만 제거합니다. 두 개의 끝 delimiter는 거절합니다. [Trino HTTP protocol](https://github.com/trinodb/trino/blob/483/docs/src/main/sphinx/develop/client-protocol.md)에 사용할 POST 자료만 준비하며 `submitted:false/queryId:null`입니다. 미래 driver는 immutable intent→단일 POST→실제 query ID→GET pages·완료를 연결해야 합니다. Unknown outcome 뒤 DDL/INSERT를 재접수하지 않습니다. 준비 identity는 제출·성공 증거가 아닙니다.

## 실제 실행 전 남은 gate

실제 collector·guarded resource 생성/중지·S3 capability 실행기·HTTP query 제출기는 이 packet에 없습니다. 새 계획의 end-to-end 실행 완료를 표시하지 않습니다. 별도 검토된 driver가 다음을 수행해야 합니다.

1. 독립 수집한 **현재** 원본 baseline과 새 preflight를 대조합니다. `preflight(record, baseline)`은 과거 7작업/11PVC 수치를 재사용하지 않습니다. 실제 source/hash/count/volume 목록은 private baseline에 두며 입력 dict가 실제 수집을 대신하지 않습니다. Slot free·새 namespace/bucket 부재·host memory≥9GiB/disk≥20GiB/inode≥100k·무거운 CI 비활성을 확인합니다.
2. 고정 Trino483·PostgreSQL17.11의 실제 OCI/Java25/UID/cgroup·저장소 분리를 확인합니다. Trino1CPU/4GiB·PG0.5CPU/1GiB·heap2GiB·query동시1/queue0, read-only root·SA token 미마운트·ClusterIP만 유지했습니다. `/tmp` disk emptyDir의 실제 exec 여부를 확인합니다. 계획의 workload replicas는 0입니다.
3. WFFC binder의 정상 exit0 뒤 Pod phase Succeeded까지 기다립니다. `Running` 중 container exit0이 보이는 reconciliation 구간을 재생성 사유로 쓰지 않습니다. 새 PVC/PV UID/claimRef/path 분리와 Retain을 확인합니다. ConfigMap quota3은 앱2개+자동 root CA1개를 포함합니다.
4. 새 bucket/key의 read/write·nonowner/createBucket false ACL, 작은 객체와 6MiB/두 part multipart·range206·전체 GET/hash·LIST를 실제 검증합니다. 과거 Java/native7 성공이 새 계획의 증거를 대신하지 않습니다. [Trino 공식 S3 시험 범위](https://github.com/trinodb/trino/blob/483/docs/src/main/sphinx/object-storage/file-system-s3.md)는 AWS/MinIO입니다.
5. CREATE 뒤 빈 상태→미시도 INSERT1→6행 검증→INSERT2를 각각 한 번 실행합니다. 실제3snapshot·0/6/12 조회·JDBC pointer·Parquet/metadata 전체 bytes를 확인합니다. `retry-policy=NONE`·operator 재접수0이며 JDBC catalog 내부 재시도와 구분합니다.
6. 새 Trino만 정상 중지/교체하고 같은 PG·PVC/config·SQL/snapshot/pointer/warehouse bytes를 대조합니다. 원본 전체 SQL/객체/서비스 보존과 자기 workload0·Retain PVC2를 확인합니다. 종료·unknown 결과는 관측대로 기록하며 진단 실패가 exact-own 중지를 막지 않아야 합니다.

Secret materializer는 POSIX root·0600 입력·checkout 밖 root0700 출력/O_EXCL0600을 요구합니다. Password는 공개 SQL·Git·콘솔·artifact에 넣지 않습니다. bucket/PVC 정리·DROP·snapshot expiry·compaction·orphan GC는 계획에 없습니다. PG/host 재시작·HA·Spark/Silver·처리량 SLA·전체 Phase6 완료는 별도 범위입니다.

재시작 수집 계약은 PG Pod UID·PVC UID뿐 아니라 실제 `postgresContainerId`와 `/proc`의 양수 `postgresProcessStartTicks`도 전후 동일해야 합니다. 같은 Pod 안의 PG 재시작을 허용하지 않으며, 실제 whole warehouse bytes의 재대조는 별도 실행 도우미가 수행해야 합니다. 이 계약 필드는 새 계획용이며 과거 native7 영수증에 추가한 관측값이 아닙니다.

오프라인 검사 **24개**는 계획·합성 기대값·거부 경계를 검증합니다. 합성 UID/성공 bool은 실제 관측 자료가 아닙니다. 새 리소스/SQL/이미지를 실행하거나 기존 native7 증거를 다시 쓴 일은 없습니다.
