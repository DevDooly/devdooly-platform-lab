# HostConfig 필드별 설정 진단 기록

2026-10-16 02:53:22 UTC의 [격리 진단 38842699117](https://github.com/DevDooly/devdooly-platform-lab/actions/runs/38842699117)은 **실패**했습니다. PG의 `HostConfig`에서 `OomKillDisable` 변경 비트만 true였고, 나머지 고정 필드 70개와 unknown 비교는 모두 false였습니다. 값 자체나 변화 방향은 이번 공개 기록에 없습니다.

[앞선 설정 진단](CONFIG_READBACK.md)은 HostConfig의 unknown 변화까지만 관측했습니다. 이번에는 [Docker 28.0.4 공식 HostConfig 및 embedded Resources 정의](https://github.com/moby/moby/blob/v28.0.4/api/types/container/hostconfig.go#L342-L444)의 JSON 이름 71개로 목록을 확장했습니다. 설정·동일성 guard·정리 권한을 변경하는 실행은 아니었습니다.

| 확인 항목 | 실제 기록 |
| --- | --- |
| 실행 source / job | `17d8efe52a905a97245d42b60e84b0859f61a293` / `116786177773` |
| Docker client / server / Compose | `28.0.4` / `28.0.4` / `2.38.2` |
| 준비 검사 | 8개 모두 true |
| 단일 시작 시계 | 180초 예산, 실제 기록 342ms; 이미지 pull과 초기 준비는 제외 |
| 최초 실패 | `START_GARAGE`의 `SAME_OWN_CONTAINER_FULL_CONFIGURATION` |
| command / 관측 처리 실패 | 각각 0개 |
| initializer 종료 | 확인 |
| 모든 자기 컨테이너 종료 | 미확인, `ownedContainersStopped=false` |

PG는 마지막 관측에서 `running=true`, `oomKilled=false`, `State.Error` 없음이었습니다. bound identity·image·created·Config·Mounts 비교는 같았고 전체 `hostChanged`만 true였습니다. Config의 모든 고정 필드와 unknown 비교는 false였으며 `MacAddress`도 false였습니다. 새 HostConfig 목록에서는 `OomKillDisable` 하나만 바뀐 것으로 관측했습니다. **이것은 OOM 발생 기록이나 실제 null↔false 값 관측이 아닙니다.** 해당 값을 공개하지 않았으므로 어떤 값에서 어떤 값으로 바뀌었는지 단정하지 않습니다.

Garage는 `created` 상태였습니다. raw Mounts 배열은 순서만 달랐고 전체 canonical 내용은 같았습니다. `mountOrderOnlyChanged=true`, `mountContentChanged=false`, `mountsChanged=false`를 PG HostConfig 변화와 구분해 기록합니다.

원래 전체 동일성 guard가 Garage 시작 직전과 정리 단계에서 거부했습니다. initializer 종료만 확인했으며 PG의 정상 종료나 전체 정리를 주장하지 않습니다. 새 project·volume·internal network의 PG·Garage만 대상으로 했고 Spark·Trino·reader 시작, business 데이터 제출, 미니 PC 접속은 요청하지 않았습니다. 전체 Cloud9·Spark→Trino·compaction의 성공이나 이전 실패들의 유일한 원인을 증명하지 않습니다.

[공개 summary](hostconfig-readback.summary.json)는 root가 받은 10,212바이트 원문 그대로입니다. 전체 SHA-256은 `462615cfbf99ceba0349a4100941f8fc1704561cbdcf39224248e0f3abdf3e4d`입니다. root가 run·job·source와 producer `32afd59d…` 연결을 확인하고 새 strict validator로 검증했으며 record 상태도 FAILED입니다. 이 형식·연결 검증을 진단 성공으로 해석하지 않습니다.

앞선 원문과 실패 상태는 보존했습니다. 후속 후보가 null·false의 의미를 다룬다면 실제 값의 타입과 나머지 전체 설정을 별도로 검증해야 합니다. 이 기록은 그런 수정의 실행이나 효과를 소급해 증명하지 않습니다.
