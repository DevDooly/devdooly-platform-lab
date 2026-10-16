# 명령 관측을 추가한 두 번째 Cloud9 실행

두 번째 실제 실행도 **실패했다**. [GitHub Actions 실행 38833863253](https://github.com/DevDooly/devdooly-platform-lab/actions/runs/38833863253)은 새 소스 `d4bd48aaa5bb68154970600a5c50ac0e3fc5ee54`의 별도 실행이다. 첫 실행을 다시 실행한 것이 아니며 [첫 실패 기록](README.md)과 [첫 원문 요약](summary.json)은 그대로 보존했다.

[두 번째 원문 요약](attempt2.summary.json)은 2026-10-16 01:16:10 UTC에 기록됐다. 전체 SHA256은 `570805bc765ac6437f07f546b3b77a153c9cb91ea097c265ba91ec22d3323aac`, 크기는 2,170바이트다. 실제 run/job/source와 새 runtime manifest `d649623c…`를 묶은 strict v2 projector 검증은 통과했다. 이 검증 통과는 실패 자료의 형식·출처를 확인한 것이며 시험 성공을 뜻하지 않는다.

| 실제 관측 | 확인 범위 |
| --- | --- |
| 준비 검증·단일 clock 시작 통과, workload 경과 211ms | build/pull을 제외한 600초 예산의 clock이 시작됐다 |
| 명령 sequence28, `START_POSTGRES` / `COMPOSE_START_POSTGRES`, rc1, timeout false | 첫 PostgreSQL Compose 시작 명령이 실패했음을 식별했다 |
| 실패 event1개, truncation false | 공개 고정 명령 관측에는 이 명령 실패가 보존됐다 |
| 마지막 명령 sequence35, cleanup의 container inspect, rc0 | 마지막 조회 명령 성공을 관측했다. 전체 정리 성공을 뜻하지 않는다 |
| initializer `STOPPED_VERIFIED`, containers `FAILED_OR_UNOBSERVED` | initializer 정지만 확인했고, 전체 소유 container 정리 완료는 미확인이다 |
| bootstrap/progress null, 결과 빈 객체 | Spark 계산·Trino 조회·compaction 결과를 입증하지 못했다 |

새 관측은 **실패한 명령을 식별했으며 원인을 확정하지 않았다**. 이 공개 자료에는 원래 명령 인자·stderr·Docker 상세 응답이나 실패한 정리 검사 조건이 없다. rc1만으로 환경·권한·volume·환경 파일 문제를 단정하지 않는다. 전체 소유 container 정리 확인 false도 모두 실행 중 또는 모두 정지한 상태로 바꾸어 해석하지 않는다.

원래 실행 명령·timeout·단일 600초 clock·SQL·자원 제한·정리 동작은 바꾸지 않고 고정 enum과 숫자로만 명령·정리 관측을 추가했다. 원문 로그·자격증명·실제 경로·container/PID identity는 공개하지 않았다. 이 추가 문서는 새로운 시험이나 재실행을 시작하지 않는다.

기존 Cloud Spark8 성공과 Mini PC native7은 별도 기록으로 유지한다. 두 번째 Cloud9 실패로 Spark→Trino 연결·파일2→1·성능·SLA·Mini PC/Kubernetes 보존·현재 가용성·전체 Phase6 완료를 주장하지 않는다. UI의 기존 성공 기록을 이 자료로 대체하거나 미관측 결과를 0으로 채우지 않는다.
