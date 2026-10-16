# 격리 Cloud Spark→Trino·compaction 첫 실행 기록

첫 실제 실행은 **실패했다**. [GitHub Actions 실행 38831221233](https://github.com/DevDooly/devdooly-platform-lab/actions/runs/38831221233)의 소스는 `8f3f4f9143096362c9dcd8c4fbcb1c135c3d7175`이며, [원문 공개 요약](summary.json)은 2026-10-16 00:48:25 UTC에 기록됐다. 요약의 전체 SHA256은 `a42f34aba82140189f08f530574b10c6911a5ae229ff13ebca63b2b82b3ffe21`, 크기는 1,492바이트다. 최초 실행과 실패 원문을 보존했으며 재실행하지 않았다.

| 실제 관측 | 기록의 의미 |
| --- | --- |
| 고정 입력·잠금 JAR·고정 이미지 검증 통과 | 준비 검증이며 Spark/Trino 쿼리 성공을 뜻하지 않는다 |
| 새 volume·내부 network·MemAvailable 7GiB 이상 검증 통과 | 이 실행의 격리 환경 준비 조건을 확인했다 |
| 단일 workload clock 시작, 경과 255ms | build/pull은 제외한 600초 예산의 clock이 시작됐다 |
| `OWN_FRESH_COMMAND_FAILED_NO_RETRY` | 명령 실패는 관측했지만 이 요약에는 실패한 명령과 stderr가 없다 |
| bootstrap diagnostic/progress는 null, 결과는 빈 객체 | Spark 계산·Trino 조회·compaction·파일 2→1 성공을 입증하지 못했다 |
| initializer 정지 확인 true, 전체 소유 container 정지 확인 false | 전체 정리 완료는 미확인이다. false를 실행 중 또는 정지 완료로 다시 해석하지 않는다 |

현재 자료로 단일 실패 원인을 확정하지 않는다. 시작 직후의 Compose 호출과 소유 container 검사 중 어느 명령이 실패했는지, 후속 정리 확인이 왜 실패했는지는 미관측이다. 공개 CI 로그에도 명령별 비공개 stderr는 포함되지 않는다. 원인 관측 개선이나 추가 시험이 필요하면 기존 실행을 재시도하지 않고 별도 작업 범위와 새 기록으로 진행한다.

계획의 범위는 새 Cloud PostgreSQL/Garage/warehouse에서 Spark가 Bronze 6+6행과 Silver 7/3/2 결과를 만들고, 작은 Bronze data file 두 개를 한 번의 compaction으로 하나로 만든 다음, Spark 종료 후 Trino가 같은 새 warehouse를 조회하는 것이다. 이 첫 실행은 그 결과를 증명하지 못했다. 준비에 성공한 조건과 완료되지 않은 계산을 분리한다.

기존 [Cloud Spark8 성공 기록](../spark-silver/README.md)과 [Mini PC native7 기록](../iceberg-jdbc/README.md)은 별도 시험이다. Native7의 빈 snapshot 포함 0/6/12와 이 계획의 append/append/replace 6/12/12를 섞지 않는다. 기존 native7 PVC·warehouse를 재사용하거나 다시 실행하지 않았으며, 이 기록으로 Mini PC 보존·Kubernetes·서비스 가용성·성능·SLA·전체 Phase6 완료를 주장하지 않는다.

공개 요약은 고정 필드만 허용한다. 원문 로그·SQL·객체 경로·자격증명·container/PID identity는 공개하지 않는다. 별도 projector는 이미 내려받은 요약의 전체 SHA와 소스, 실제 run/job 식별자를 대조하는 로컬 검증 도구다. 서비스나 시험을 실행하지 않으며 실패를 성공으로 바꾸지 않는다.
