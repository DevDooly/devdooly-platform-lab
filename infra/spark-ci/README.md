# GitHub 실행기에서 분리해 확인하는 Spark 호환성

현재 상태는 **SOURCE_ONLY_NOT_RUN**입니다. 이 실험은 Spark·JDBC·Garage의 조합만 확인할 후보입니다. 미니 PC의 Trino 검증, Kubernetes 배포, 운영 자료 보존을 대신하지 않습니다.

기존 `lab-ci.yml`에 선택 입력 `run_spark_trial`을 추가합니다. 기본값은 `false`이며, 별도 작업은 **수동 실행이면서 입력이 true인 경우에만** 실행됩니다. 기존 verify 작업과 자동 실행 조건은 보존합니다. 권한은 `contents: read`이고 checkout 인증 정보를 유지하지 않습니다. SSH·kubeconfig·운영 Secret·GHCR 로그인/푸시·배포 단계는 없습니다.

GitHub는 수동 실행할 workflow가 기본 브랜치에 있어야 합니다. 따라서 이미 등록된 LabCI 진입점에서 검토한 브랜치를 `--ref`로 선택하는 제안입니다. 브랜치에만 있는 새 입력을 API가 거부하면 그 결과를 보존하고 정상적인 검토·통합을 기다립니다. 이벤트 스키마를 우회하지 않습니다. 실제 실행은 별도 미니 PC 검증이 종료된 뒤로 보류합니다. [GitHub 수동 실행 문서](https://docs.github.com/en/actions/how-tos/manage-workflow-runs/manually-run-a-workflow)

## 새 환경에서 수행할 내용

`run_ci.py`는 GitHub가 제공하는 Linux 실행기만 허용합니다. 새 UUID의 Docker Compose 프로젝트·네트워크·세 볼륨과 임의의 DB/RPC/S3 인증 정보를 생성합니다. 네트워크는 `internal: true`이며 호스트 포트는 하나도 열지 않습니다. 기존 코드가 사용하는 서비스 이름은 새 네트워크 안의 DNS 별칭으로만 재현합니다. 미니 PC나 Kubernetes에 접속하는 경로는 없습니다.

PostgreSQL 17.11·Garage 2.4.1·Java 21 기반 Spark 4.1.1의 전체 이미지 digest를 고정합니다. Maven Central의 세 JAR는 기존 실제 잠금 파일의 전체 크기·SHA-256·SHA-512와 일치해야 합니다. 실행 중 패키지를 다운로드하지 않습니다. 후보 Dockerfile에 CI bootstrap만 추가하고, 빌드 네트워크를 끈 채 로컬 이미지를 만듭니다. 이미지를 게시하지 않습니다.

새 PostgreSQL의 트랜잭션으로 비관리자 `iceberg_catalog` 역할과 JDBC V1 메타데이터 테이블을 생성합니다. Garage는 새 RPC 식별자·단일 노드 layout·64MiB/128객체의 새 버킷·한 버킷에만 접근하는 비소유자 key를 사용합니다. 짧은 초기화 컨테이너는 동일한 PostgreSQL 이미지로 **새 Garage 볼륨 두 개의 소유권만** 설정하며 네트워크와 호스트 경로를 연결하지 않습니다. 이름·label·CID·명령·볼륨·자원 제한을 확인하고 종료까지 별도로 관측합니다.

한 `local[1]` Spark 애플리케이션이 공개 합성 입력을 6건씩 두 번 적재합니다. PySpark의 JVM과 Python 드라이버를 합쳐 OS 프로세스 하나라고 주장하지 않습니다. 실제 두 snapshot의 부모 관계와 시점 조회를 확인한 뒤, 바이트가 같은 기존 Silver 코드를 호출합니다. 결과 12건은 성공 7·실패 3·중복 2이며, MERGE 한 번과 저장된 동일 배치의 순차 재처리 한 번을 확인합니다. 재처리는 쓰기와 새 snapshot을 만들지 않아야 합니다. 이후에도 Bronze의 전체 행과 snapshot이 같아야 합니다.

여기서 Bronze를 만든 주체는 **Spark**입니다. 이 결과를 Trino가 원본을 썼거나 미니 PC에서 재시작·원본 보존이 검증됐다는 근거로 사용하지 않습니다.

## 제한과 실패 처리

Spark는 1 CPU·3GiB, driver heap 1536MiB로 제한합니다. PostgreSQL과 Garage는 각각 0.5 CPU·512MiB입니다. 별도 executor 컨테이너나 UI 서비스를 만들지 않습니다. Spark를 시작하기 전에 실제 Docker 제한·단일 내부 네트워크·호스트 포트 부재를 검사합니다. 이 제한은 처리 용량이나 SLA 측정값이 아닙니다.

작업을 자동 재시도하지 않습니다. 준비 상태를 기다리는 반복은 읽기 전용입니다. 실패 시 이번에 만든 정확한 초기화 컨테이너와 Compose 컨테이너 ID만 중지하며, 볼륨·객체를 삭제하지 않습니다. 확인할 수 없는 초기화 결과를 종료 성공으로 바꾸지 않습니다. 자료와 비공개 로그는 일회성 GitHub VM이 폐기될 때까지 남습니다. 다시 실행하려면 새 실행기·새 프로젝트의 별도 수동 실행이 필요하며, 실패한 쓰기의 복구나 exactly-once를 뜻하지 않습니다.

업로드 대상은 **`.local/spark-ci-public/summary.json` 한 파일**입니다. 검증기는 수치·버전·해시·범위·상태의 명시된 필드만 허용합니다. Compose 파일·인증 정보·SQL 초기화문·환경 변수·Docker inspect·원시 Spark 로그·JAR 바이너리는 업로드하지 않습니다. 실패하거나 요약이 없으면 호환성 성공으로 표시하지 않습니다. 설정 계획과 실제 통과한 검사를 구분합니다.

## 실행 전 로컬 검증

```sh
python3 -B -m unittest discover -s infra/spark-ci -p 'test_*.py' -v
```

오프라인 경계 테스트 10개이며 Docker·네트워크·PySpark를 실행하지 않습니다. 기존 `infra/spark-silver/`의 소스와 미니 PC 실행 조건도 변경하지 않습니다. 실제 결과는 명시적으로 실행한 GitHub 작업이 통과한 뒤 별도 증거로 기록해야 합니다. Trino·운영/Kubernetes 보존·동시 writer·재시작/강제 종료 복구·compaction·Airflow는 범위 밖입니다.

공식 근거: [Compose 내부 네트워크](https://docs.docker.com/reference/compose-file/networks/#internal), [Spark 4.1.1 실행 방법](https://spark.apache.org/docs/4.1.1/submitting-applications.html).
