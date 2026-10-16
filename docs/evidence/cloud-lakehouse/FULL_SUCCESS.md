# 새 Cloud warehouse의 Spark → Trino와 두 파일 compaction

2026-10-16 03:12:33 UTC의 [새 격리 실행 38843953097](https://github.com/DevDooly/devdooly-platform-lab/actions/runs/38843953097)에서 Spark 적재·Silver 변환·Bronze compaction과 같은 새 warehouse의 Trino 조회를 **통과**했습니다. 기존 미니 PC native7이나 Cloud Spark8을 재실행하거나 그 저장소를 바꾼 결과가 아닙니다.

| 확인 항목 | 실제 결과 |
| --- | --- |
| source / Cloud job | `223faf71c4fe9cadfd33b5ac5a95969cf3e2b04e` / `116790713619` |
| CI | 같은 실행의 기본 verify와 Cloud job 모두 SUCCESS, 기존 Spark·S3 선택 실행은 skipped |
| Bronze 행 | 첫 append 6 → 두 번째 append 12 → compaction 뒤 12 |
| Silver | 12행: 성공 7·실패 3·중복 2·대기 0 |
| 현재 Bronze 데이터 파일 | rewrite 대상 2개 → 새 현재 파일 1개, procedure 1회 |
| Trino | Spark 정상 종료 뒤 같은 JDBC catalog·warehouse에 10개 조회 |
| 자료 보존 | compaction 전 보관 객체 14개의 전체 bytes 유지, Trino 조회 뒤 전체 객체 20개와 JDBC pointer 대조 |
| 예산 / 실제 workload 시계 | 단일 600초 / 78.955초, build·pull 준비 시간은 제외 |
| 종료 | Spark 정상 종료, Trino exit 143·비 OOM·stop 요청 종료 코드 0, initializer와 모든 자기 컨테이너 종료 확인 |

세 snapshot ID는 문자열 `8225039569250402625` → `2782914730281457112` → `3908786707027856228`입니다. 새 시험의 두 append와 rewrite snapshot을 뜻하며, 미니 PC native7의 초기 빈 snapshot을 포함한 세 개와 구분합니다. 최종 12행은 compaction 전후 및 Trino의 시점 조회에서 같았고, 최종 row SHA-256은 `9ad14362736e0ada4f44de4ca32296a2e9082e2f78227884326608952116d016`입니다.

이 시험은 새 UUID project·volume·key·bucket·warehouse만 사용했습니다. Spark가 정상 종료한 뒤 Trino를 시작하고, 둘이 종료된 뒤 Python 전용 reader로 전체 객체를 다시 읽었습니다. Spark는 CPU 1·3GiB·PID 512, Trino는 4GiB 설정을 유지했고 순차 실행의 계획상 peak는 5GiB였습니다. 시작 전 실제 MemAvailable 7GiB 조건을 확인했습니다. 이 수치는 자원 설정과 시작 gate이며 사용량 최대치 측정이나 운영 용량·처리량 SLA가 아닙니다.

Trino 종료 코드는 실제 143입니다. 같은 CID·PID/startTicks/cgroup을 확인한 stop 요청의 허용된 종료 조건이며, signal 전달 자체를 직접 관측하지 않았습니다. 모든 종료가 exit 0이었다고 표현하지 않습니다. 소스의 present null/false OomKillDisable 검사도 최종 통과했습니다. 이전 진단은 변화 bit만 남겼으므로 그때의 값·변화 방향을 소급해 증명하지 않습니다.

현재 파일이 2개에서 1개로 바뀌었어도 예전 객체를 삭제하지 않았습니다. snapshot expiration·object GC·volume 삭제는 수행하지 않았고 runner storage는 ephemeral입니다. 이 결과는 영구 보관 약속, 같은 환경의 재시작·동시 writer·호스트 장애·고가용성·Kubernetes 또는 현재 서비스 가용성을 검증하지 않습니다. Phase6 전체 완료와도 구분합니다.

[전체 성공 summary](full-success.summary.json)는 실제 3,114바이트 원문입니다. SHA-256은 `1271685e34712c96b7dacaf7e84e5f32ac52fb925875e262843002ee6ef3b78f`이며, root의 retrieval·dispatch receipt와 v4 검증기가 producer `73e22932…`, runtime manifest `c63aded0…`, reviewed packet `78b5b18a…`를 연결했습니다. 공개 DTO의 snapshot operation `append/append/replace`와 자원 제한은 이 passed 실행이 통과한 고정 소스 계약에서 가져왔습니다. 원문에 없는 측정값을 추가한 것이 아닙니다.

이전 일곱 실패 원문은 보존합니다: [첫 전체 실패](README.md), [두 번째 전체 실패](ATTEMPT2.md), [첫 시작 진단](STARTUP_DIAGNOSTIC.md), [Mounts 진단](STARTUP_MOUNT_DIAGNOSTIC.md), [세 번째 전체 실패](ATTEMPT3.md), [설정 진단](CONFIG_READBACK.md), [HostConfig 진단](HOSTCONFIG_READBACK.md). 새 성공은 다른 source의 새 실행이며 이전 실패를 재통과시키거나 자동 재시도한 결과가 아닙니다.
