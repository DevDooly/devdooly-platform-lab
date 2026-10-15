# Spark 4.1 시점 조회 옵션 보완 준비본

상태는 **SOURCE_PREPARED_NOT_RUN**입니다. 이전 Cloud 실패 소스·결과는 보존하고, 두 시점 조회 경로의 옵션만 바꾼 새 후보입니다. 최근 실제 격리 실행은 두 append 뒤 `VERIFY_BRONZE`의 `IllegalArgumentException`에서 실패했습니다. 오류 원문과 단일 원인은 아직 확정하지 않았으므로, 이번 수정이 그 실제 실패 원인을 해결했다고 표시하지 않습니다.

## 변경한 세 곳

- `infra/spark-silver/spark_silver.py`: 고정 Bronze snapshot을 읽는 `option('snapshot-id', ...)` 한 곳을 `option('versionAsOf', ...)`로 바꿉니다.
- `bootstrap_spark.py`: 두 Bronze snapshot을 시점 조회하는 동일 옵션 한 곳을 같은 값으로 바꿉니다.
- `run_ci.py`: 새 Silver 모듈의 실제 전체 SHA를 고정합니다. 옛 `189ec387…` 바이트와 동일하다고 주장하지 않습니다.

나머지 Silver 코드 전체와 bootstrap의 계산·SQL·변환·MERGE·순차 재처리는 바꾸지 않습니다. 기존 GZIP default와 Bronze 전후/Silver 후 table-property 확인, private 진단·initializer requested-bind 검증·중지 경계도 유지합니다. Compose·workflow·이미지/JAR·CPU/메모리·사용자·네트워크·`/tmp` 실행 권한은 바꾸지 않습니다. 별도 observer/proxy나 실패한 작업의 자동 재접수는 추가하지 않습니다.

## 공식 근거와 검증 범위

Iceberg 1.11.0의 Spark 4.1 모듈에서 `LEGACY_SNAPSHOT_ID`는 `snapshot-id`, `VERSION_AS_OF`는 **`versionAsOf`**입니다. `SparkScanBuilder`는 `validateNoLegacyTimeTravel`을 호출하며, 이 함수는 legacy snapshot 옵션을 거절하고 Spark 내장 옵션을 사용하도록 안내합니다. [고정 상수](https://github.com/apache/iceberg/blob/apache-iceberg-1.11.0/spark/v4.1/spark/src/main/java/org/apache/iceberg/spark/SparkReadOptions.java#L24-L25), [새 옵션 상수](https://github.com/apache/iceberg/blob/apache-iceberg-1.11.0/spark/v4.1/spark/src/main/java/org/apache/iceberg/spark/SparkReadOptions.java#L93), [검증 함수](https://github.com/apache/iceberg/blob/apache-iceberg-1.11.0/spark/v4.1/spark/src/main/java/org/apache/iceberg/spark/Spark3Util.java#L509-L514), [scan builder 호출](https://github.com/apache/iceberg/blob/apache-iceberg-1.11.0/spark/v4.1/spark/src/main/java/org/apache/iceberg/spark/source/SparkScanBuilder.java#L116)

같은 실제 snapshot ID를 십진 문자열로 전달합니다. 오프라인 테스트는 새 두 파일의 **실제 reader 표현식**을 inert reader로 실행해 옵션·table·field 전달과 2⁵³보다 큰 ID/최대 signed long의 문자열 보존을 확인합니다. 새 옵션을 원래 옵션으로 되돌린 전체 파일의 SHA가 과거 frozen 파일과 일치해야 합니다. 따라서 원래 처리와 다른 바이트 변경을 허용하지 않습니다. runner도 그 새 SHA 한 곳만 바뀌었음을 확인합니다.

이 검증은 Spark/JAR 실행이나 실제 SQL·Garage 호환성 검증이 아닙니다. 새 GitHub-hosted Linux 수동 실행에서 실제 두 append snapshot의 6/12행 시점 조회·Silver 12행의 7/3/2 결과·순차 replay 무쓰기·own 컨테이너 중지를 모두 확인해야 완료입니다. 이 Cloud Bronze는 Spark가 새 격리 스토어에 만드는 테이블로, 미니 PC Trino의 초기 빈 snapshot을 포함한 3개 snapshot 증거와 구분합니다.

## 오프라인 검증

```sh
python3 -B -m unittest discover -s infra/spark-ci -p 'test_*.py' -v
python3 -B -m unittest discover -s infra/spark-silver -p 'test_*.py' -v
```

첫 명령은 기존 경계 26개와 새 시점 조회/바이트 보존 회귀 4개, 두 번째는 기존 순수 fixture·oracle·재처리·제안 검증 11개입니다. Docker·PySpark·JAR·네트워크·미니 PC는 실행하지 않습니다. 업로드는 기존 strict public summary 하나이며 raw 로그·inspect·환경·비밀 값·JAR는 공개하지 않습니다.
