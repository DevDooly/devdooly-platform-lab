# Spark 10분 제한 도달 시 진단 보완 준비본

상태는 **SOURCE_PREPARED_NOT_RUN**입니다. 기준은 실제 Cloud 5 소스 `2fe81a4a001e17b704a058897dae47cf05c51713`입니다. 해당 실행은 initializer 13개 검증·고정 vendor·컨테이너 제한·격리 네트워크 검증 뒤 `ONE_SPARK_PROCESS_DEADLINE`에서 실패했습니다. 원래 **600초** 제한은 유지합니다. 당시 bootstrap 진단·컨테이너 state·로그가 수집되지 않았으므로 마지막 처리 단계와 원인은 미관측입니다. Compose 컨테이너와 initializer 중지는 확인됐고 미니 PC에 접속하지 않았습니다. 이 실패 소스와 결과는 보존합니다.

## 이번 변경

- 기존 `advance()`가 호출될 때만 고정 milestone 진행 기록을 새 private 파일에 남깁니다. 별도 주기 thread·Spark observer·SQL은 추가하지 않습니다. 파일은 새 sequence별 O_EXCL 기록을 fsync한 뒤 같은 디렉터리에 hard link로 게시하므로 부분 쓰기를 최신 기록으로 읽지 않습니다. 이미 남긴 sequence는 덮어쓰지 않습니다.
- 파일 내용은 고정 scope·phase enum·sequence·milestones·경과 정수·`/tmp` mount enum·`completionNotProven:true`뿐입니다. `COMPLETED`라는 진행 단계도 실제 성공 결과를 대체하지 않습니다. 진행이 멈춘 시간이 장애 원인을 증명하지도 않습니다.
- 600초 deadline에 도달하면 **중지 전에** 생성 당시 고정한 전체 Spark container ID와 현재 own scope를 다시 확인하고 실제 running/exit/OOM 상태를 읽습니다. 실행 중이면 exit code는 null로 둡니다. 같은 ID를 다시 확인한 뒤만 진단을 유지합니다.
- 해당 deadline 경로의 로그는 새 읽기 전용 `docker logs --tail 200 <전체 ID>` 하위 프로세스로 받습니다. 각 stream 최대 256KiB·수집 10초 제한입니다. 초과 시 이 로컬 logs CLI만 종료하고 `TRUNCATED`로 표시합니다. 컨테이너를 강제 종료하는 기능은 추가하지 않습니다. 원문은 private 파일에만 남기며 공개 summary에는 기존 signature enum·상태·allowlist 진행 기록만 넣습니다.
- 수집 실패는 `PARTIAL` 또는 `UNOBSERVED`로 남기고 원래 deadline 실패를 유지합니다. 그 뒤 기존 독립 cleanup `finally`가 실행됩니다. 진단 실패를 성공·원인 확정으로 바꾸거나 작업을 재접수하지 않습니다.

private 진행 파일은 기존 0700 시도 디렉터리 아래의 proof mount에 위치하며, 기존 Spark UID와 host reader가 읽을 수 있도록 기존 안전 진단 파일과 같은 파일 모드를 사용합니다. 공개 artifact 경로는 기존 **`.local/spark-ci-public/summary.json` 하나**입니다. 진행 파일·raw 로그·inspect·환경·connection·JAR는 업로드하지 않습니다. 진단과 cleanup에는 기존 실행 창 이후 별도의 제한된 시간이 필요하며, 600초 작업 창을 늘렸다고 표시하지 않습니다.

## 바꾸지 않는 범위

고정 Silver 전체 bytes·fixture·실제 SQL/변환/MERGE/순차 replay·GZIP 설정·`versionAsOf` 두 경로·이미지/JAR pins·CPU/메모리·내부 네트워크·사용자·`/tmp` 실행 권한을 유지합니다. Bootstrap의 실제 `execute()` AST는 기준 후보와 정확히 같습니다. Compose와 workflow도 그대로입니다. 아래 시점 조회 변경은 **이전 후보의 이력**이며 이번 진단에서 다시 바꾸지 않습니다.

## 이전 시점 조회 후보의 변경 이력

- `infra/spark-silver/spark_silver.py`: 고정 Bronze snapshot을 읽는 `option('snapshot-id', ...)` 한 곳을 `option('versionAsOf', ...)`로 바꿉니다.
- `bootstrap_spark.py`: 두 Bronze snapshot을 시점 조회하는 동일 옵션 한 곳을 같은 값으로 바꿉니다.
- `run_ci.py`: 새 Silver 모듈의 실제 전체 SHA를 고정합니다. 옛 `189ec387…` 바이트와 동일하다고 주장하지 않습니다.

나머지 Silver 코드 전체와 bootstrap의 계산·SQL·변환·MERGE·순차 재처리는 바꾸지 않습니다. 기존 GZIP default와 Bronze 전후/Silver 후 table-property 확인, private 진단·initializer requested-bind 검증·중지 경계도 유지합니다. Compose·workflow·이미지/JAR·CPU/메모리·사용자·네트워크·`/tmp` 실행 권한은 바꾸지 않습니다. 별도 observer/proxy나 실패한 작업의 자동 재접수는 추가하지 않습니다.

## 공식 근거와 검증 범위

Iceberg 1.11.0의 Spark 4.1 모듈에서 `LEGACY_SNAPSHOT_ID`는 `snapshot-id`, `VERSION_AS_OF`는 **`versionAsOf`**입니다. `SparkScanBuilder`는 `validateNoLegacyTimeTravel`을 호출하며, 이 함수는 legacy snapshot 옵션을 거절하고 Spark 내장 옵션을 사용하도록 안내합니다. [고정 상수](https://github.com/apache/iceberg/blob/apache-iceberg-1.11.0/spark/v4.1/spark/src/main/java/org/apache/iceberg/spark/SparkReadOptions.java#L24-L25), [새 옵션 상수](https://github.com/apache/iceberg/blob/apache-iceberg-1.11.0/spark/v4.1/spark/src/main/java/org/apache/iceberg/spark/SparkReadOptions.java#L93), [검증 함수](https://github.com/apache/iceberg/blob/apache-iceberg-1.11.0/spark/v4.1/spark/src/main/java/org/apache/iceberg/spark/Spark3Util.java#L509-L514), [scan builder 호출](https://github.com/apache/iceberg/blob/apache-iceberg-1.11.0/spark/v4.1/spark/src/main/java/org/apache/iceberg/spark/source/SparkScanBuilder.java#L116)

같은 실제 snapshot ID를 십진 문자열로 전달합니다. 오프라인 테스트는 두 파일의 **실제 reader 표현식**을 inert reader로 실행해 옵션·table·field 전달과 2⁵³보다 큰 ID/최대 signed long의 문자열 보존을 확인합니다. Silver는 옵션을 되돌린 전체 파일의 SHA를 계속 검사합니다. Bootstrap은 새 진단 영역을 제외한 실제 `execute()` AST를 기준 전체 hash로 고정하고, runner는 같은 `71bd6323…` Silver 모듈을 고정합니다. 기존 파일 전체 byte 검사는 의도적으로 추가한 진단까지 거부하므로 이 두 경계를 검사하도록 좁게 갱신했습니다.

이 검증은 Spark/JAR 실행이나 실제 SQL·Garage 호환성 검증이 아닙니다. 새 GitHub-hosted Linux 수동 실행에서 실제 두 append snapshot의 6/12행 시점 조회·Silver 12행의 7/3/2 결과·순차 replay 무쓰기·own 컨테이너 중지를 모두 확인해야 완료입니다. 이 Cloud Bronze는 Spark가 새 격리 스토어에 만드는 테이블로, 미니 PC Trino의 초기 빈 snapshot을 포함한 3개 snapshot 증거와 구분합니다.

## 오프라인 검증

```sh
python3 -B -m unittest discover -s infra/spark-ci -p 'test_*.py' -v
python3 -B -m unittest discover -s infra/spark-silver -p 'test_*.py' -v
```

첫 명령은 기존 경계 26개·시점 조회 4개·새 진행/timeout 진단 11개로 **41개**입니다. 두 번째는 기존 순수 fixture·oracle·재처리·제안 검증 11개입니다. 새로운 진단 검사에는 실제 작은 Python 하위 프로세스의 출력 pipe 상한 검증이 있으며 Docker·PySpark·JAR·외부 네트워크·미니 PC는 실행하지 않습니다.

첫 로컬 검사에서 새 테스트 하나가 Windows에 없는 `os.fchmod` 때문에 실패했습니다. Linux 전용 production 경로는 그대로 두고 테스트 안에서만 해당 OS 함수와 `O_NOFOLLOW` 부재를 보완했습니다. 두 번째 40개가 통과했고, 마지막 완료 진단 JSON이 부분 기록된 경우에도 먼저 읽은 완전한 진행 기록을 보존하는 회귀를 추가해 **41개를 실패·오류·skip 없이 확인**합니다. 이 오프라인 결과는 새 Cloud 실행이 통과했다는 근거가 아닙니다. 새 수동 실행은 root가 독립 검토와 동결 후 결정하며, 이전 실패 실행을 자동 재실행하지 않습니다.
