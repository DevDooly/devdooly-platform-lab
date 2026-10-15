# Spark Silver — 격리 Cloud 시험 8

**VERIFIED — ISOLATED_GITHUB_RUNNER_SPARK_JDBC_GARAGE**. [실제 실행 38805412935](https://github.com/DevDooly/devdooly-platform-lab/actions/runs/38805412935), source [`0552a28a0b360543c9b84be2e5c5ccc7d28c2459`](https://github.com/DevDooly/devdooly-platform-lab/commit/0552a28a0b360543c9b84be2e5c5ccc7d28c2459)의 새 Docker/PostgreSQL/Garage 범위에서 정상 종료까지 확인했습니다. miniPC나 Kubernetes에 배포한 결과는 아닙니다.

[CI summary 원본](summary.json)은 5,387 bytes, SHA256 `00068fc7a88961374e57b4964a4819d70dc51706c3c16de9b28a54d2b8920838`입니다. 공개 허용 필드로 생성된 기존 CI artifact를 byte-identical로 보존했습니다. raw 로그·inspect·환경·자격 증명은 포함하지 않습니다. [작은 site DTO](../../../apps/lab-web/public/observations/spark.latest.json)는 이 원본의 투영입니다.

## 확인한 동작

| 항목 | 실제 결과 |
| --- | --- |
| 입력 | 공개 `sensor-validation-v1`, 1,100 bytes·12행, SHA `39ba10d8c47dce790f3ccc9c9134fea593d6de31f1f3a7992ca61d9f554da3b5` |
| 엔진 | Spark4.1.1·Java21.0.9·Scala2.13.17, 고정된 Iceberg/JDBC/AWS JAR bytes |
| Bronze | 6행씩 두 append, 전체12행·snapshot2개, 두 시점의 정확한 순서/값 확인 |
| Silver | 전체12행·snapshot1개, SUCCESS7·FAILED3·DUPLICATE2·PENDING0 |
| 재접수 | 같은 batch의 순차 replay1회, MERGE1회·replay write0회, 하나의 Spark application |
| 종료 | bootstrap `COMPLETED`, `sessionStopFailed=false`, 실제 exit0·Docker OOM false, 자기 Compose와 initializer 중지 |

Bronze ID는 실행 순서대로 `5876084123105525860`, `711948836478668590`입니다. 양의 BIGINT **문자열**로 보존하며 값의 크기로 시간 순서를 판단하지 않습니다. Bronze 행 해시는 `9ad14362736e0ada4f44de4ca32296a2e9082e2f78227884326608952116d016`, Silver 행 해시는 `2c51c7447e59bf88cd41c016cf846b47e3e4c46b4257a024e9f67079b2b425eb`입니다. 이 harness는 정렬한 JSON key·공백 없는 JSON·끝 newline으로 해시를 계산합니다. native7의 이전 열 순서 기반 해시를 이 값으로 바꾸지 않습니다.

이 Cloud의 Bronze snapshot2개와 [miniPC native7](../iceberg-jdbc/README.md)의 초기 빈 snapshot을 포함한 총3개는 서로 다른 실험입니다. 이번 증거는 Trino native 경로·PG 재시작·Spark 분산 동시 실행·장애 복구를 검증하지 않습니다.

## 자원·시간의 범위

Spark는 CPU1·메모리3GiB·driver heap1536MiB·PID512, PostgreSQL/Garage PID256, 작업 제한600초, host publish0입니다. 고정 이미지와 실제 Docker HostConfig의 역할별 한도를 검사했습니다. CPU·메모리·heap·SQL·변환·네트워크·권한·600초 제한은 이전 시험과 같습니다.

`24,871ms`는 bootstrap monotonic 진행 기록의 시작부터 `COMPLETED`까지이며 session 생성·작업·정지를 포함합니다. vendor 다운로드·이미지 빌드·전체 CI 시간을 포함하지 않고, 단계별 시간·처리량·SLA를 측정하지 않습니다. 종료 후 cgroup 수집 상태는 `NOT_RUNNING`, 값은 빈 객체입니다. 이를 peak0·PID 거부0·이전 대비 개선량으로 해석하지 않습니다.

GZIP은 catalog default를 첫 catalog 접근 전에 설정하고 Bronze 전후·Silver write/replay 후 `SHOW TBLPROPERTIES`로 확인했습니다. Silver write 전 property와 실제 Parquet footer codec은 관측하지 않았습니다.

같은 실행의 기본 회귀 artifact는 Java JUnit200개·28 suites·실패/오류/skip0이었고, 기존 Compose API 교체 후 sample 보존도 별도로 감사했습니다. 이 기본 회귀를 miniPC 또는 분산 Spark 운영 증거로 확대하지 않습니다.

## 실패 기록과 해석

[시험 7](https://github.com/DevDooly/devdooly-platform-lab/actions/runs/38801841777), source `a08ef593cad6f619052a3137a1cc3bed58b4cd6f`는 600초에서 실패했습니다. `STOP_SESSION`과 native-thread OOM 서명, `pids.max=256`, 누적 `pids.events:max=16`을 관측했습니다. 당시 `pids.current=65`는 진단 shell을 포함한 한 시점 값이며 peak가 아닙니다. 이전 baseline·counter 증가량을 측정하지 않았습니다.

시험 8은 Spark PID budget만512로 제한하여 정상 종료했습니다. 이 결과가 시험 7의 유일한 원인이나 다른 자원 한도의 충분성을 입증하지는 않습니다. 이전 실패를 성공으로 덮거나 JVM을 재시도·강제 exit0으로 처리하지 않았습니다. 시험 volume은 harness가 삭제하지 않았으며 Cloud runner의 저장소 자체는 일시적입니다.

## 공개 자료 재현

[SCHEMA](SCHEMA.md)와 [실행 runbook](../../runbooks/spark-silver-cloud.md)을 참조합니다. 다음은 저장된 공개 자료만 검증·투영하며 서버·Docker·SQL에 접속하지 않습니다.

```sh
python3 -B -m unittest discover -s infra/spark-ci -p 'test_spark_public.py' -v
python3 -B infra/spark-ci/spark_public.py \
  --summary docs/evidence/spark-silver/summary.json --output /tmp/new-spark.latest.json
```

Validator는 이 고정된 실제8 기록의 key/type·provenance·정상 종료·counts·한도·제외 범위를 검사합니다. 현재 서비스 상태를 수집하거나 새로운 run의 성공을 승인하지 않습니다. 다음 run은 별도의 실제 증거와 검토가 필요합니다.
