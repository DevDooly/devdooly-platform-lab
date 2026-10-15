# Cloud 초기화 검증 보완 준비본

상태: **SOURCE_PREPARED_NOT_RUN**. 세 번의 실제 실패를 보존하고, 다음 수동 실행을 위해 초기화 컨테이너의 요청 볼륨 검증만 보완한 새 준비본입니다. 이 새 준비본은 아직 실행하지 않았습니다. GZIP 실험의 bootstrap·원본 Silver 처리·SQL·보안 설정은 변경하지 않습니다.

첫 실행 [38778209166](https://github.com/DevDooly/devdooly-platform-lab/actions/runs/38778209166)은 `ACTUAL_SPARK_CLEAN_EXIT_WITHOUT_OOM`에서 실패했고, 당시 종료 코드/OOM 관측이 부족했습니다. 진단을 보강한 두 번째 실행 [38781736763](https://github.com/DevDooly/devdooly-platform-lab/actions/runs/38781736763)은 `APPEND_FIRST`에서 SparkException → UnsatisfiedLinkError, 종료 코드 1·Docker OOM false를 확인했습니다. own 컨테이너 중지도 확인했으며 원래 두 실패 기록과 소스는 수정하지 않습니다.

세 번째 실행 [38784547833](https://github.com/DevDooly/devdooly-platform-lab/actions/runs/38784547833)은 Spark 시작 전에 `EXACT_FRESH_INITIALIZER_IDENTITY_AND_SCOPE`에서 실패했습니다. vendor·고정 이미지·내부 네트워크 검사는 통과했지만, initializer 신원과 중지는 **미검증**입니다. Compose 컨테이너의 중지 확인과 구분하며 모두 중지됐다고 표시하지 않습니다. 세 번째 실패 원인은 아직 미확인이고, GZIP의 실제 호환성도 확인하지 못했습니다.

## 이번 검증기 보완

Docker의 `HostConfig.Binds` 목록 순서는 권한이나 연결 대상을 바꾸지 않습니다. 정확히 이번 새 프로젝트의 `garage-meta → /meta`, `garage-data → /data` 두 requested bind가 rw인지 의미로 비교합니다. 순서 변경과 기본 rw를 명시한 `:rw`만 동등하게 허용합니다. 중복·추가·다른 프로젝트/host 경로·다른 destination·`:ro`·다른 mode는 계속 거절합니다. 실제 세 번째 실패가 목록 순서 때문에 발생했다고 확정하지는 않습니다.

PostgreSQL 기반 이미지가 자동으로 만드는 `/var/lib/postgresql/data` anonymous volume 때문에 실제 `Mounts`는 요청 bind 두 개보다 많을 수 있습니다. 새 검증을 `Mounts` 개수 제한으로 확대하지 않으며, 기존 `HostConfig.Binds` 두 개의 의미만 확인합니다. image·이름·프로젝트 label·명령·network none·비특권·host port 부재·64MiB/0.1 CPU 신원 검사는 유지합니다.

공개 `initializerIdentityChecks`에는 고정된 항목의 검증 boolean만 넣습니다. false는 **확인하지 못했다**는 뜻이며, 원래 Docker 값이 false이거나 컨테이너가 없다는 뜻이 아닙니다. raw inspect·ID·이름·volume·경로·환경·credential은 노출하지 않습니다. 신원이 확인되지 않은 initializer를 강제로 중지하거나 중지 성공으로 바꾸지 않습니다. 기존 실패 기록의 진단을 나중에 채워 넣지도 않습니다.

## 유지하는 GZIP 실험 조건

수정하지 않은 `silver.session()` 직후, 첫 `phase6` catalog 접근 전에 다음 값을 설정하고 readback합니다.

```text
spark.sql.catalog.phase6.table-default.write.parquet.compression-codec=gzip
```

Iceberg의 catalog table-default는 새 테이블의 기본 속성을 지정합니다. GZIP은 지원되는 Parquet 압축 값입니다. [Iceberg 1.11 catalog 설정](https://iceberg.apache.org/docs/1.11.0/spark-configuration/#catalog-configuration), [1.11 write properties](https://iceberg.apache.org/docs/1.11.0/configuration/#write-properties)

설정 문자열만으로 성공 처리하지 않습니다. 실제 `SHOW TBLPROPERTIES` 결과가 한 행의 `write.parquet.compression-codec=gzip`인지 확인합니다.

- Bronze: CREATE 직후 첫 append 이전과 전체 Silver 처리 이후에 확인합니다.
- Silver: 원래 `silver.run()`의 쓰기와 순차 재처리가 끝난 이후에만 확인합니다. Silver 쓰기 이전을 관측했다는 표시는 하지 않습니다.
- 검증 범위는 **테이블 속성**입니다. 실제 Parquet footer의 압축 codec 검증이나 이전 오류의 단일 원인 입증은 포함하지 않습니다.

기존 `spark_silver.py`, `silver_contract.py`, 12행 fixture, Dockerfile와 그 고정 SHA, SQL·변환·순차 재처리는 바꾸지 않습니다. 별도 observer/proxy 없이 원래 `silver.run()`을 직접 호출합니다. 네트워크·CPU/메모리 제한·`/tmp` mount 옵션·사용자·파일 권한도 바꾸지 않습니다.

## 공개 진단의 범위

Python import/session과 종료를 포함한 오류 경계, 실제 full Spark CID의 종료 코드·Docker OOM 관측, 최대 200행 private 로그 보존은 유지합니다. 공개 진단에는 다음 항목만 추가합니다.

- Java cause 메시지에서 관측한 네이티브 라이브러리 분류: `zstd`, `snappy`, `lz4`, `hadoop`만 허용합니다. 원문은 일시적인 분류 입력일 뿐 공개하거나 별도 파일로 쓰지 않습니다.
- `failed to map segment` 문구를 관측했는지 나타내는 boolean. false는 원인 부재 증명이 아닙니다.
- `/proc/self/mountinfo`에서 `/tmp`를 덮는 가장 구체적인 mount를 읽은 결과: `NOEXEC`, `EXEC`, `UNOBSERVED`만 기록합니다. 경로·mount 원문·옵션 목록은 공개하지 않습니다. 읽기 실패나 모호한 결과는 UNOBSERVED로 남깁니다.

이 분류는 원인을 확정하거나 자동으로 권한을 바꾸는 기능이 아닙니다. 미확인 진단·실패한 session 종료·실패한 진단 저장을 성공으로 바꾸지 않습니다. 메시지·stack trace·native 경로·SQL·환경·인증 값은 공개 요약에 넣지 않습니다.

## 변하지 않는 격리 및 처리 범위

기존 Lab CI의 `run_spark_trial` 입력은 기본 false입니다. 수동 실행이면서 명시적으로 true인 경우에만 별도 작업을 실행합니다. GitHub-hosted Linux의 새 UUID Compose 프로젝트·내부 네트워크·새 볼륨·새 DB/버킷/key를 사용하며 host port·SSH·kubeconfig·미니 PC·GHCR 게시·배포 경로가 없습니다. 기존 verify 작업과 workflow는 이 준비본에서 변경하지 않습니다.

PostgreSQL 17.11, Garage 2.4.1, Java 21 기반 Spark 4.1.1의 이미지 digest와 실제 내려받은 JAR 3개의 전체 SHA를 유지합니다. 외부 패키지를 실행 중 내려받지 않습니다. Spark는 local[1] 애플리케이션 하나이며 OS 프로세스 하나라는 뜻은 아닙니다. Spark 1 CPU·3GiB/driver heap 1536MiB, PG와 Garage 각각 0.5 CPU·512MiB 제한을 유지합니다.

새 Bronze에 공개 12행을 6+6으로 적재하고 두 append snapshot·시점 조회를 확인합니다. 원래 Silver 코드의 결과는 성공 7·실패 3·중복 2·pending 0이며, MERGE 한 번과 저장된 동일 배치의 순차 읽기 재처리 한 번 뒤 추가 쓰기/snapshot이 없어야 합니다. Bronze 행과 snapshot도 보존되어야 합니다. 이 Bronze를 만드는 엔진은 Spark입니다. 미니 PC의 Trino 실행·Kubernetes 보존·동시 writer·장애 복구·compaction·Airflow 증거로 확대하지 않습니다.

실패 시 자동 재실행하지 않습니다. 정확히 이번 initializer와 own Compose 컨테이너만 중지하고, 볼륨·객체는 삭제하지 않습니다. 확인 불가 상태를 중지 성공으로 바꾸지 않습니다. 업로드 대상은 strict allowlist를 통과한 `.local/spark-ci-public/summary.json` 하나뿐이며 raw 로그·Compose·secret·inspect·JAR를 업로드하지 않습니다. 기존 두 실패와 다른 새 소스·새 GitHub run으로만 수동 검증합니다.

## 오프라인 검증

```sh
python3 -B -m unittest discover -s infra/spark-ci -p 'test_*.py' -v
```

26개 오프라인 테스트는 기존 21개와 requested bind의 순서/명시적 rw 동등성, 다른 연결·중복·추가·ro 거절, per-field boolean의 비공개 정보 차단, image의 anonymous volume 허용, 나머지 신원 조건 보존을 확인합니다. Docker·PySpark·JAR·원격 실행은 하지 않습니다. 실제 호환성 결과는 후속 수동 실행의 별도 증거가 필요합니다. GZIP 선택이 이전 실패의 단일 원인을 해결했다거나 네이티브 라이브러리를 쓰지 않는다는 주장은 하지 않습니다.
