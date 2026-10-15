# Spark Cloud DTO schema 1

위치: `apps/lab-web/public/observations/spark.latest.json`. 역사적 Cloud 시험8의 정적 기록입니다. native7의 Dataflow schema2와 합치거나 live 상태로 취급하지 않습니다. JSON은 2,136 bytes이며 row 본문·endpoint·bucket·PID/CID·원문 오류·환경·자격 증명을 담지 않습니다.

| 정확한 top key | 내용 |
| --- | --- |
| `schemaVersion`, `scope`, `status` | `1`, `ISOLATED_GITHUB_RUNNER_SPARK_JDBC_GARAGE`, `VERIFIED` |
| `capturedAt`, `sourceCommit` | CI summary의 UTC capture와 실제 source0552 전체 SHA |
| `run` | 숫자 문자열 `id`, 고정 GitHub run URL, 시험 계열의 순번 `attempt:8` |
| `summary` | 실제 원본 SHA256·bytes5387 |
| `fixture` | 공개 V1 이름·SHA·bytes1100·rows12 |
| `versions` | 실제 Spark·Java·Scala 버전 |
| `bronze` | rows12·snapshots2·실제 ID 문자열 둘·행 SHA |
| `silver` | rows12·snapshot1·7/3/2/0·MERGE1·순차 replay1·write0·행 SHA |
| `stop` | bootstrap 완료·session stop 실패false·실제 exit0/OOMfalse·자기 컨테이너 중지 |
| `resources` | Spark CPU1/memory3GiB/heap1536MiB/PID512, PG/Garage PID256, 제한600초, host publish0 |
| `timing` | bootstrap 시작→COMPLETED 24871ms, `BOOTSTRAP_START_WORK_AND_STOP`, 단계별/처리량 측정false |
| `exclusions` | miniPC·Trino·Kubernetes·분산 동시/장애복구·PID 단독원인·live·cgroup peak/delta 모두false |

각 중첩 객체의 정확한 허용 key와 타입은 [pure validator](../../../infra/spark-ci/spark_public.py)의 `PROFILE`입니다. 누락·추가 key·boolean을 숫자로 대체·다른 scope·부분 종료·더 큰/무제한 budget을 거부합니다. Snapshot ID는 canonical decimal string이며 `1..2^63-1`, 서로 달라야 합니다. JavaScript Number로 변환하지 않습니다.

`run.attempt`는 이 시험 계열의 순번이며 GitHub의 `GITHUB_RUN_ATTEMPT`나 workflow 재실행 횟수가 아닙니다.

이 validator는 한 실제 기록에 고정되어 source/run/원본 SHA와 각 관측값까지 대조합니다. 원본이 fail/unknown이거나 변경되었으면 DTO를 만들지 않습니다. UI는 missing·schema 불일치·검증 실패를 pending/미확인으로 보여야 하며, 고정 count만으로 가짜 PASS나 row별 실행 결과를 만들어서는 안 됩니다. 단순 그림의 단계는 결과 수의 설명이지 단계별 시간 표본이 아닙니다.

현재 실행 권한·public POST·SQL 관리자 화면·polling은 이 DTO 계약에 없습니다. 새 SQL·작업·재시작·삭제를 유발하는 입력을 받지 않습니다.
