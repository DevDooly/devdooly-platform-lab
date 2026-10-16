# PostgreSQL/Garage만 대상으로 한 별도 startup 진단

이 좁은 진단도 **실패했다**. [실행 38836760710](https://github.com/DevDooly/devdooly-platform-lab/actions/runs/38836760710)의 소스는 `98833225a62ca21660a94935ee0f1ab077f93be2`다. 기존 두 Cloud9 실행을 다시 실행하지 않았으며, Spark·Trino·reader 시작이나 업무 입력은 요청하지 않았다. [첫 기록](README.md)과 [두 번째 기록](ATTEMPT2.md)은 그대로 보존했다.

[원문 startup 요약](startup.summary.json)은 2026-10-16 01:45:04 UTC에 기록됐다. 전체 SHA256은 `a3b24f385c812f5a404c012d81113a88e3b851fec53ffa51eb73a7f67a4d45da`, 크기는 3,392바이트다. 실제 artifact·run/job/source를 묶은 strict validator 검증은 통과했다. 이는 실패 자료의 계약과 출처를 검증한 결과다.

| 실제 관측 | 확인 범위 |
| --- | --- |
| Docker client/server `28.0.4`, Compose `2.38.2` | 이 CI runner에서 조회한 실제 도구 버전 |
| 준비 checks8 통과 | 고정 base 이미지·새 volume·내부 network·initializer exit0·MemAvailable 7GiB 이상·full5 모델·Trino env 부재·두 base role 생성 확인 |
| startup clock 경과 147ms, readiness false | 별도 180초 startup 예산의 readiness를 확인하지 못했다 |
| `START_POSTGRES`에서 `SAME_OWN_CONTAINER_FULL_CONFIGURATION` | 검토한 소스의 Compose start 호출 전 전체 signature guard가 거부했다 |
| PostgreSQL identity/imageId/config/host/created 변경 false, mounts 변경 true | raw mounts 배열 비교만 달랐다. 순서 차이와 실제 내용 차이는 아직 구분하지 못했다 |
| PostgreSQL은 created·running false·OOM false·State.Error 부재 | 시작 실패 stderr나 OCI runtime 오류를 이 관측으로 확인한 것이 아니다 |
| Garage baseline identity 미관측, change bits null | Garage 동일성이 확인됐다고 해석하지 않는다 |
| command failures0, 마지막 container inspect rc0 | 명령 실행 실패와 guard 거부를 구분한다. 마지막 조회 성공도 전체 정리 성공은 아니다 |
| initializer 정지 확인 true, 전체 container 정지 확인 false | 같은 guard가 정리 검사에서도 거부했다. 전체 정리 완료는 미확인이다 |

원래 strict guard를 완화하거나 다른 자원을 정지해 성공으로 만들지 않았다. 공개 자료는 고정 change bit와 code만 제공하며 실제 mount 경로·container identity·환경값·원문 로그는 포함하지 않는다. 전체 mounts 배열의 비교 차이를 관측했지만 그 차이가 무엇인지, 왜 생겼는지는 이 자료만으로 확정하지 않는다.

이 진단의 guard 실패를 앞선 두 Cloud9 실행의 유일한 원인으로 소급하지 않는다. 앞선 두 번째 실행은 Compose PostgreSQL 시작 명령 rc1을 관측했고, 이번 실행은 그 명령에 도달하기 전 guard에서 거부됐다. 서로 다른 새 실행의 관측을 합쳐 하나의 원인 증명으로 만들지 않는다.

전체 다섯 서비스 Compose 모델과 의도적인 Trino env 파일 부재를 유지했지만 실제 create/start 요청은 PostgreSQL/Garage로 제한했다. JAR 읽기·bucket/key 생성·업무 입력·Mini PC 접촉은 없었다. 이 기록은 Spark/Trino 계산·compaction·현재 가용성·성능·SLA 또는 전체 Cloud9 성공을 뜻하지 않는다. 기존 Cloud Spark8과 native7의 별도 성공·보존 범위도 변경하지 않는다.
