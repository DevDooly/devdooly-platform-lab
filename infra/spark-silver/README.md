# Spark Silver 소스 제안

현재 변경본의 상태는 **SOURCE_CANDIDATE_NOT_RUN**입니다. `spark_silver.py`의 시점 조회 옵션 한 곳을 Spark 4.1용 `versionAsOf`로 바꾼 별도 후보이며, 이 변경본의 이미지 빌드·실제 SQL·Kubernetes Job은 아직 실행하지 않았습니다. 이전 격리 Cloud 실행의 부분 진행·실패는 [Cloud 준비본](../spark-ci/README.md)에 구분합니다. 미니 PC 실행은 실제 native Bronze 통과 증거가 먼저 필요합니다.

원래 `189ec387…` 모듈의 바이트와 실패 기록은 보존합니다. 새 모듈은 같은 snapshot ID를 십진 문자열로 전달하며, 변환·MERGE·순차 재처리·GZIP 설정·네트워크·권한·자원 제한을 바꾸지 않습니다. [pinned Iceberg Spark 4.1 상수](https://github.com/apache/iceberg/blob/apache-iceberg-1.11.0/spark/v4.1/spark/src/main/java/org/apache/iceberg/spark/SparkReadOptions.java#L93)와 [legacy 옵션 거절 코드](https://github.com/apache/iceberg/blob/apache-iceberg-1.11.0/spark/v4.1/spark/src/main/java/org/apache/iceberg/spark/Spark3Util.java#L509-L514)를 따르지만, 이전 실제 실패의 단일 원인을 입증했다거나 새 변경본이 호환성 검증을 통과했다는 뜻은 아닙니다.

공식 Maven Central에서 받은 세 JAR의 전체 바이트·SHA와 선택한 클래스 헤더는 별도로 확인했습니다. 그 결과를 `artifact-lock.downloaded.json`에 보존했습니다. 이 검증은 의존성 다운로드와 정적 확인이며, Spark 실행이나 Garage 호환성 검증을 대신하지 않습니다. JAR 바이너리와 비밀 값은 이 디렉터리에 포함하지 않습니다.

목표는 공개 합성 입력 12건을 Spark로 읽어 `input_sequence` 순서를 유지한 Silver 결과 12건으로 남기는 것입니다. 기대값은 성공 7건·실패 3건·중복 2건·대기 0건입니다. 실패와 중복을 버리지 않고 같은 결과 테이블에 상태·사유를 기록합니다.

## 실행 전 통과해야 할 조건

1. Trino의 실제 Bronze 12건·초기 빈 snapshot 1개와 데이터 append 2개·정상 재시작·최종 보존 결과가 모두 통과해야 합니다. 총 3개 중 실제 두 번째 **데이터 append**의 snapshot ID와 제출 증거 SHA를 사용합니다. 새 `phase6.silver` namespace·대상 테이블·Silver S3 prefix가 비어 있음을 사전 확인합니다. 코드도 namespace가 이미 있으면 재사용하지 않고 실패합니다.
2. 원래 운영 8개 작업과 24개 원본/결과 객체, 기존 Docker·PVC·서비스를 새 기준점에서 확인해야 합니다. 운영 측 원본이 늘었다면 과거 8/24 기준을 현재 전체라고 재사용하지 않습니다.
3. Trino는 정상 중지하고, 별도 Phase 6 PostgreSQL만 유지하거나 명시적으로 다시 시작합니다. Spark와 Trino를 동시에 실행하지 않습니다. 시작 시 호스트 여유 메모리 9GiB, 실행 중 4GiB, 디스크 20GiB·inode 100,000 및 OOM/swap 증가 없음, 무거운 CI 없음이 필요합니다.
4. 실제 베이스 이미지 OCI를 확인하고, 로컬에 준비한 세 JAR를 `artifact-lock.downloaded.json`과 대조한 뒤 후보 이미지를 빌드해야 합니다. `artifact-plan.json`은 체크섬이 미정이던 최초 계획이며 그대로 보존합니다. 이를 검증용 lock으로 사용하면 `validate_vendor.py`가 파일 접근 전에 실패합니다. 실행 중 `--packages`·pip·Maven 다운로드를 사용하지 않습니다.
5. 새 Spark namespace/Secret/Job과 기존 **별도 실습 PostgreSQL namespace에 추가할 좁은 ingress NetworkPolicy**를 검토해야 합니다. Job 제안은 항상 `suspend: true`이며 자동 생성·해제 실행기는 구현하지 않았습니다.

## 고정한 조합과 아직 확인하지 않은 범위

- Spark **4.1.1 / Scala 2.13 / Java 21**, Iceberg runtime **1.11.0**, Iceberg AWS bundle **1.11.0**, pgJDBC **42.7.14**를 후보로 고정합니다. Iceberg 1.11.0의 [pinned build 설정](https://github.com/apache/iceberg/blob/apache-iceberg-1.11.0/gradle/libs.versions.toml)은 Spark 4.1.1을 사용하며, [Spark 4.1 모듈](https://github.com/apache/iceberg/blob/apache-iceberg-1.11.0/spark/v4.1/build.gradle)에 해당 runtime 구성이 있습니다. 이는 실제 Garage 호환성을 보증하지 않습니다.
- 베이스 이미지는 Apache의 [4.1.1 Java 21/Python 3 amd64 descriptor](https://hub.docker.com/layers/apache/spark/4.1.1-java21-python3/images/sha256%3A0b8f5befe00d258df03b252158b3894b8654390f1958741accf98155539a662a)의 전체 digest로 고정했습니다. 이 준비에서 registry/CRI 검증이나 layer pull을 수행하지 않았습니다. [공식 Dockerfile](https://github.com/apache/spark-docker/blob/master/4.1.1/scala2.13-java21-ubuntu/Dockerfile)의 사용자 설정을 토대로 UID/GID 185를 제안했으며 실제 이미지에서 재확인해야 합니다.
- JDBC catalog 이름은 **phase6**, 기존 별도 catalog 역할은 **iceberg_catalog**입니다. Trino connector 별칭 `iceberg`를 Spark catalog 이름으로 사용하면 같은 JDBC catalog 행을 찾지 못합니다. [pinned JdbcCatalog 구현](https://github.com/apache/iceberg/blob/apache-iceberg-1.11.0/core/src/main/java/org/apache/iceberg/jdbc/JdbcCatalog.java)에 따라 이름을 맞추고 `jdbc.init-catalog-tables=false`, `jdbc.schema-version=V1`로 기존 실습 catalog를 사용합니다.
- AWS `S3FileIO`, 고정 내부 endpoint, path-style, 현재 Garage/Trino 계획과 같은 region **garage**, CRT 비활성화·단일 multipart thread를 지정했습니다. [pinned S3 설정 구현](https://github.com/apache/iceberg/blob/apache-iceberg-1.11.0/aws/src/main/java/org/apache/iceberg/aws/s3/S3FileIOProperties.java)의 지원 속성을 사용합니다. 실제 Spark의 HEAD/GET/metadata/Parquet 쓰기와 전체 바이트 재검증이 완료되기 전에는 호환 완료로 표기하지 않습니다. 12건 파일은 작으므로 multipart 처리 능력을 검증한 것으로 확대하지 않습니다.

## 한 Job에서 확인할 내용

`spark_silver.py`는 `local[1]`, CPU 1·메모리 3GiB, driver heap 1536MiB, UI·event log·speculation 비활성화로 실행할 후보입니다. Spark executor Pod나 공개 Service를 만들지 않습니다. 새 namespace의 정책은 지정한 실습 PostgreSQL·기존 Garage·DNS만 허용하며 Kubernetes API 토큰을 마운트하지 않습니다. 실습용 두 Secret의 값은 운영자가 검증하여 별도로 제공해야 합니다. 후보 파일에 비밀 값은 없습니다.

1. 실제 고정 Bronze snapshot을 읽고 `input_sequence`로 정렬한 12건이 공개 fixture와 완전히 같은지 확인합니다.
2. Spark window 연산으로 첫 event ID와 sensor별 이전 정상 시간의 최대값을 계산합니다. `silver_contract.py`의 별도 순차 oracle 및 수동 정답과 12건 전체를 비교합니다. 임의 입력이나 일반적인 잘못된 데이터 처리기를 구현한 것은 아닙니다.
3. 새 `phase6.silver.sensor_outcomes`에 `(batch_id,input_sequence)`를 키로 고정 MERGE 한 번만 실행합니다. [Iceberg Spark 쓰기 문서](https://iceberg.apache.org/docs/1.11.0/spark-writes/)의 MERGE 기능을 사용합니다. 기존 Bronze 테이블에 쓰거나 DROP/expire/GC를 수행하는 경로는 없습니다.
4. 같은 프로세스에서 같은 batch를 다시 처리할 때, 저장된 12건이 완전히 같으면 쓰기를 생략하고 rows SHA와 snapshot이 그대로인지 확인합니다. 부분 결과·다른 batch·다른 내용은 실패합니다. 이것은 **한 Job의 순차 재처리** 검증이며, Job 재시작·동시 writer·분산 exactly-once·강제 종료 복구 검증이 아닙니다.
5. 별도 관측자가 Silver의 모든 객체를 GET하여 크기/SHA와 metadata pointer를 확인하고, native Bronze 객체·초기 빈 snapshot 및 두 데이터 snapshot·기존 catalog 행·운영 자료가 그대로인지 검증합니다. 필요하면 Spark 종료 후에만 Trino를 시작해 같은 Silver 12건을 교차 조회합니다. Job 자체는 운영 보존을 검증했다고 주장하지 않습니다.

첫 실패나 응답 불명 시 Job·SQL·객체·로그를 보존하고 자동 재접수하지 않습니다. `backoffLimit=0`이며 성공한 Job/Pod 정리는 별도 UID 조건·보관 절차가 필요합니다. namespace/PVC/객체 삭제나 GC 실행기는 포함하지 않았습니다.

## 로컬에서 할 수 있는 검증

```sh
python3 -B -m unittest discover -s infra/spark-silver -p 'test_*.py' -v
```

저장소 루트에서 실행하면 오프라인 테스트 11개가 fixture·순서·판정·재처리·미정 체크섬 차단·중지된 리소스 계획만 확인합니다. PySpark 설치·실행, JAR 다운로드, 이미지 빌드, 서버 접속을 하지 않습니다. CI 제안도 이 명령만 추가합니다. 렌더링에는 미래의 실제 빌드 이미지 digest와 검증된 snapshot ID·증거 SHA가 필수입니다.

```sh
python3 infra/spark-silver/render_plan.py --image 'ghcr.io/devdooly/devdooly-platform-lab-spark-silver@sha256:<실제 digest>' --bronze-snapshot-id <실제 ID> --bronze-proof-sha256 <실제 증거 SHA> --output suspended-proposal.json
```

## JAR 잠금 파일과 로컬 확인

`artifact-plan.json`의 최초 미정 체크섬과 `artifact-lock.downloaded.json`의 실제 다운로드 결과를 구분합니다. 2026-10-15 공식 HTTPS 다운로드의 전체 크기는 **112,793,760바이트**였습니다. Iceberg 두 JAR는 공식 SHA-512 sidecar와도 일치했고, pgJDBC sidecar는 HTTP 404로 제공되지 않아 그 일치를 주장하지 않습니다. pgJDBC도 전체 Content-Length와 실제 SHA-256·SHA-512를 계산했습니다. 배포 서명 검증은 수행하지 않았습니다.

| 공식 아티팩트 | 실제 바이트 | SHA-256 |
| --- | ---: | --- |
| [Iceberg Spark runtime 1.11.0](https://repo.maven.apache.org/maven2/org/apache/iceberg/iceberg-spark-runtime-4.1_2.13/1.11.0/iceberg-spark-runtime-4.1_2.13-1.11.0.jar) | 47,959,591 | `d6ea6c5d099288daeb7d5a92061bd3d7d8f296492632b42378e5f2f0e3066242` |
| [Iceberg AWS bundle 1.11.0](https://repo.maven.apache.org/maven2/org/apache/iceberg/iceberg-aws-bundle/1.11.0/iceberg-aws-bundle-1.11.0.jar) | 63,613,165 | `38f01da7e96850cdd05e6616d758b77b43314b712a8808e3f9a824d56976162f` |
| [pgJDBC 42.7.14](https://repo.maven.apache.org/maven2/org/postgresql/postgresql/42.7.14/postgresql-42.7.14.jar) | 1,221,004 | `73914527305a40cce504b0d3d90b23caf565136912d607ae8ae7c5895512332c` |

세 파일을 Git 제외 로컬 디렉터리에 준비하고, 다음 명령의 두 로컬 경로를 지정합니다. 출력 파일은 없어야 합니다. 검증기는 전체 SHA와 `SparkCatalog`, `S3Client`, PostgreSQL `Driver`의 클래스 헤더만 확인하며, 파일로 압축을 풀거나 클래스 로딩·실행을 하지 않습니다. 나머지 클래스나 전이 의존성의 실행 호환성을 확인한 것은 아닙니다.

```sh
python3 infra/spark-silver/validate_vendor.py \
  --lock infra/spark-silver/artifact-lock.downloaded.json \
  --vendor '<로컬 JAR 디렉터리>' \
  --output '<새 vendor.sha256 경로>'
```

`Dockerfile.candidate`는 빌드 컨텍스트의 `vendor/` 안에 세 JAR와 검증된 `vendor.sha256`가 있어야 빌드됩니다. 바이너리와 실제 비밀 값을 저장소에 추가하지 말고 별도 로컬 빌드 컨텍스트에 준비합니다. 아직 베이스 이미지의 registry/CRI·layer, 후보 이미지 빌드, Spark의 class loading·SQL·S3 요청은 확인하지 않았습니다. [pgJDBC 공식 다운로드](https://jdbc.postgresql.org/download/)의 버전을 고정했지만 PostgreSQL 17.11 및 실제 작업의 연결 성공은 별도로 검증해야 합니다.
