# 시작 명령 실패와 mount 순서 차이를 분리한 추가 진단

추가 진단도 **실패했다**. [실행 38837630164](https://github.com/DevDooly/devdooly-platform-lab/actions/runs/38837630164)의 소스는 `f3f5c52993ceb00fd70f73c17f0ec6d2d236b26e`다. [앞선 startup 진단](STARTUP_DIAGNOSTIC.md)과 이전 Cloud9 실패들을 재실행하거나 수정하지 않았다. 이번 기록은 새 격리 환경에서 PostgreSQL/Garage의 시작과 정리만 관측했다.

[원문 요약](startup-mount.summary.json)은 2026-10-16 01:54:47 UTC에 기록됐다. 전체 SHA256은 `c41ce401a46e061bb829902de97b7399cbf20288ad274612d6f8703a4ae8b07d`, 크기는 4,259바이트다. 실제 run/job/source·producer를 묶은 strict schema2 validator 검증을 통과했으며, 이는 실패 자료 검증의 성공이다.

| 이번 실행의 실제 관측 | 해석 범위 |
| --- | --- |
| Docker client/server 28.0.4, Compose 2.38.2, 준비 checks8 통과 | 이 runner의 버전과 준비 조건 |
| sequence29의 PostgreSQL Compose start rc1, timeout false | 실제 시작 명령이 실패했다 |
| 같은 sequence의 `ENV_FILE_MISSING_SIGNATURE` | 제한된 환경 파일 부재 문구 패턴이 stderr에서 관측됐다. 원문·파일명은 공개하지 않았다 |
| PostgreSQL signature의 모든 변경 bit false | 마지막 관측에서 PostgreSQL의 identity·image·config·host·mounts·created가 원래 baseline과 같았다 |
| Garage identityBound true, mountOrderOnlyChanged true, mountContentChanged false | mount member의 전체 내용은 같고 배열 순서만 달랐다 |
| cleanup의 `SAME_OWN_CONTAINER_FULL_CONFIGURATION` | 순서 차이를 포함한 원래 raw signature guard가 정리 확인을 거부했다 |
| initializer 정지 true, 전체 container 정지 false, 마지막 inspect rc0 | 일부 조회 성공을 전체 정리 완료로 해석하지 않는다 |
| 경과 338ms, readiness false, heavy role 시작 요청 false | 좁은 startup도 통과하지 못했고 Spark/Trino/compaction 결과는 없다 |

이번 실행에서는 **시작 명령의 환경 파일 관련 signature와 정리 시 mount 순서 비교 거부를 별개로 관측했다.** 앞선 원문에는 이 구분이 없었다. 새 결과를 앞선 실패에 소급하거나 여러 실패의 유일한 원인으로 합치지 않는다.

Docker 28.0.4 공식 소스의 `GetMountPoints`는 map을 순회해 배열을 만들며 그 배열을 정렬하지 않는다. inspect는 이 배열을 `Mounts`로 반환한다. 이는 inspect 배열의 순서를 불변 identity로 취급하기 어렵다는 소스 근거이며, 이번 Garage의 실제 order-only 관측과 일치한다. 모든 member 필드·중복·타입을 유지한 내용 비교와 배열 순서 비교를 분리했다. [GetMountPoints](https://github.com/moby/moby/blob/v28.0.4/container/container_unix.go#L397-L412), [inspect의 Mounts 반환](https://github.com/moby/moby/blob/v28.0.4/daemon/inspect.go#L42-L84)

**환경 파일 경로에 관한 설명은 추론이다.** 실제 모델은 다섯 서비스를 유지했고 선언된 미생성 환경 파일이 있었다. Compose 2.38.2의 start는 project 로딩 경로를 거치며, `ToProject`는 모델을 load한 뒤 선택 서비스 처리를 한다. 따라서 전체 모델을 불러오는 과정이 선택한 base 서비스 외의 환경 파일 선언에 영향을 받았을 가능성을 뒷받침한다. 그러나 공개 signature만으로 어느 파일을 읽으려 했는지, 이것이 모든 실패의 단일 원인인지는 확정하지 않는다. [start 경로](https://github.com/docker/compose/blob/v2.38.2/cmd/compose/start.go#L42-L52), [project 로딩·서비스 선택](https://github.com/docker/compose/blob/v2.38.2/cmd/compose/compose.go#L226-L241), [LoadProject 이후 선택 처리](https://github.com/docker/compose/blob/v2.38.2/cmd/compose/compose.go#L313-L348)

진단은 원래 raw guard를 완화하지 않았고 정리 미확인도 그대로 남겼다. 실제 경로·환경값·원문 로그·container/PID identity는 공개하지 않았다. bucket/key 생성·업무 입력·Mini PC 접촉·heavy role 시작 요청은 없었다. 기존 Cloud Spark8·native7의 별도 성공 기록, 현재 가용성·성능·SLA 또는 전체 Cloud9 완료를 이 실패 자료로 변경하지 않는다.
