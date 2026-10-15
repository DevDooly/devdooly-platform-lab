# 격리 Cloud Spark Silver 검증

[실제 시험8 증거](../evidence/spark-silver/README.md)는 GitHub-hosted Linux의 새 PostgreSQL·Garage·local Spark application 한 개 범위입니다. miniPC native7과 별개이며, 이 runbook이나 정적 DTO를 읽는 행위는 새 실행 승인이 아닙니다.

## 실행 범위

검토한 PR47 source `0552a28a0b360543c9b84be2e5c5ccc7d28c2459`의 기존 `lab-ci.yml`에서 수동 `run_spark_trial=true` job을 사용했습니다. Root가 정확한 ref로 별도 실행을 접수했으며 이전 실패 run을 재실행하지 않았습니다. 기본 verify와 격리 시험은 별도 job이며 `needs`로 실행 순서를 강제하지 않습니다. 이번 실행은 두 job의 결과를 각각 확인했습니다.

전제는 새 GitHub-hosted runner·해당 source·고정 이미지/JAR SHA입니다. Harness는 새 내부 Docker network·dedicated PostgreSQL catalog와 Garage bucket/key·자기 volume만 사용하며 host port를 publish하지 않습니다. Credential은 private runner 자료에 두고 공개 artifact는 허용된 summary만 올립니다.

Spark CPU1·memory3GiB·heap1536MiB·PID512, PostgreSQL/Garage PID256, 작업600초를 그대로 적용합니다. 실제 inspect가 역할별 PID 값과 다르면 시작을 수락하지 않습니다. PID 무제한·자동 증설·JVM 재시도는 없습니다. Kubernetes 정책이나 miniPC workload에는 접속하지 않습니다.

## 성공 경계

1. 공개 V1 fingerprint와 새 table 부재를 확인하고 Bronze에6+6행을 한 번씩 append합니다.
2. 실제 snapshot2개의 parent chain·두 시점 6/12행·원래 순서/값을 읽습니다. Spark4.1의 `versionAsOf` 경로를 사용합니다.
3. 고정 batch를 Silver에 MERGE1회 적용하고 전체12 outcomes가 7/3/2/0인지 확인합니다. 같은 batch를 순차 replay한 뒤 실제 write0·snapshot1과 원래 Bronze 보존을 확인합니다.
4. GZIP property를 정해진 시점에 확인합니다. 실제 Parquet footer·Silver write 전 codec을 검증했다고 표시하지 않습니다.
5. `spark.stop()`가 반환하고 bootstrap COMPLETED·실제 process exit0·Docker OOMfalse를 확인한 뒤에만 전체 성공을 표시합니다. 진행 기록이나 먼저 쓰인 result 파일만으로 성공을 부여하지 않습니다.
6. 자기 Compose와 initializer의 정지를 확인합니다. Raw 로그·inspect·환경·credentials를 upload하지 않습니다. Volume은 harness가 삭제하지 않으며 runner storage는 일시적입니다.

## 실패·보존

Unknown outcome·비정상 exit·deadline·OOM·부분자료는 실패로 남깁니다. 같은 run/SQL을 자동 재접수하거나 `stop()`를 건너뛰고 성공시키지 않습니다. 제한된 private 로그·cgroup 진단이 실패해도 숫자0이나 원인을 만들어 넣지 않습니다. 자기 full-ID/소유 범위를 확인한 cleanup만 수행하며 다른 서비스·volume을 정리하지 않습니다.

시험7의 PID 누적 counter와 native-thread 서명, 시험8의 정상 종료를 함께 보존합니다. PID512가 단독 해결책이라는 결론은 내리지 않습니다. 새 resource profile이나 변경된 source는 새 검토·새 실행·별도 영수증으로 다룹니다.

공개 [schema1](../evidence/spark-silver/SCHEMA.md)·[투영 코드](../../infra/spark-ci/spark_public.py)는 저장된 시험8 원본만 검증합니다. Bootstrap의24.871초는 전체 CI/빌드 시간이나 pure-transform 시간, 처리량/SLA가 아닙니다. 분산 concurrency·crash recovery·HA·운영 배포·miniPC 보존·native Trino를 확인하려면 각각 별도 실행 증거가 필요합니다.
