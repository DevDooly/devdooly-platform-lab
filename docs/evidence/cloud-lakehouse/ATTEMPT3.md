# 시작 경계를 수정한 세 번째 full 실행 기록

세 번째 full 실행도 **실패했다**. [실행 38839670201](https://github.com/DevDooly/devdooly-platform-lab/actions/runs/38839670201)의 소스는 `8e55f467faee38cee124690af1e80e65f69fc18c`다. 이전 [첫 실패](README.md), [두 번째 실패](ATTEMPT2.md), 두 별도 startup 진단은 그대로 보존했다. 기존 실행의 재실행이나 Mini PC/native7 재사용은 아니다.

[원문 요약](attempt3.summary.json)은 2026-10-16 02:21:05 UTC에 기록됐다. 전체 SHA256은 `eebb19a8bed2a663d8216f3583d95e7d1a9956f6e5d4d279701a615bc441357b`, 크기는 1,926바이트다. 실제 dispatch와 artifact는 새 runner `bc5d6afb…`·runtime manifest `eb15f268…`·검토 packet `589c262a…`에 연결했다. v3 projector는 기존 schema2 데이터 검증을 유지하면서 새 producer 귀속을 검증했으며, 옛 `5f60/d649` 실행 결과로 표시하지 않는다.

| 실제 관측 | 확인 범위 |
| --- | --- |
| 고정 입력·vendor·이미지·새 volume·내부 network·MemAvailable·단일 clock 준비 통과 | 계산 완료를 의미하지 않는 준비 검증 |
| workload 경과 263ms, `SAME_OWN_CONTAINER_FULL_CONFIGURATION` | 전체 소유 container 구성 guard가 거부했다 |
| command failure 배열 비어 있음 | 실패한 외부 명령이 이 배열에 기록되지는 않았다. 모든 상태·guard가 정상이라는 뜻은 아니다 |
| 마지막 sequence37 container inspect rc0 | 마지막 조회 명령의 성공이며 전체 정리 성공과 구분한다 |
| initializer `STOPPED_VERIFIED`, containers `FAILED_OR_UNOBSERVED` | 전체 소유 container 정리 완료는 미확인이다 |
| bootstrap diagnostic/progress null, 결과 빈 객체 | Spark·Trino·compaction 결과를 입증하지 못했다 |

새 runner는 raw mount의 소유·source·RO/RW 검사를 유지하고 전체 member 내용 비교에서 배열 순서만 제외했다. 이미 create된 아직 시작하지 않은 대상의 full CID·구성을 확인한 뒤 그 CID를 한 번 시작하도록 바꿨다. 단일 600초 예산·heavy 실행 순서·SQL·자원·정리 조건은 유지했다. 이 소스 변경이 실제 전체 시험의 성공을 뜻하지 않는다.

이번 원문은 거부된 구체적 역할이나 필드·당시 전체 상태를 제공하지 않는다. mount·Config·HostConfig·권한·환경 파일 중 어느 항목이 달랐는지 단정하지 않으며, 앞선 [mount/환경 파일 관측](STARTUP_MOUNT_DIAGNOSTIC.md)을 이번 실행의 원인으로 다시 사용하지 않는다. 전체 정리 false를 실행 중 또는 정지 완료로 바꾸지 않는다.

새 결과를 만들기 위해 같은 mutation·SQL을 재접수하거나 guard를 우회하지 않았다. 원문 로그·SQL·실제 경로·container/PID identity·자격증명은 공개하지 않는다. 이 실패 자료로 Spark→Trino 연결·파일2→1·운영 가용성·성능·SLA·Kubernetes/Mini PC 보존·전체 Phase6 완료를 주장하지 않으며 기존 Cloud Spark8/native7 성공 범위도 변경하지 않는다.
