# PG·Garage 설정 변화 진단 기록

2026-10-16 02:43:07 UTC의 [격리 설정 진단 38841830231](https://github.com/DevDooly/devdooly-platform-lab/actions/runs/38841830231)은 **실패**했습니다. PG 시작 뒤 `HostConfig`가 이전 관측과 달라진 사실을 확인했지만, 이번 목록에 없는 어느 필드가 바뀌었는지는 확인하지 못했습니다. 전체 Spark→Trino 시험이나 compaction의 성공 기록이 아닙니다.

이 실행은 새 project·volume·internal network에서 PG와 Garage만 대상으로 했습니다. Spark·Trino·reader의 시작을 요청하지 않았고 미니 PC에 접속하지 않았습니다. 원래 5개 서비스 Compose 모델과 실행 guard를 유지하면서, 전체 설정 및 고정된 개별 필드의 변경 여부만 관측했습니다. 설정값·Env·MAC·경로·컨테이너 ID·오류 원문은 공개하지 않습니다.

| 확인 항목 | 실제 기록 |
| --- | --- |
| 실행 source / job | `3990eb9eb66017ca3747cbf4cedf52ec33c37995` / `116783453621` |
| Docker client / server / Compose | `28.0.4` / `28.0.4` / `2.38.2` |
| 준비 검사 | 고정 이미지·새 volume·internal network·initializer 종료·메모리 여유 등을 포함한 8개 모두 true |
| 단일 시작 시계 | 180초 예산, 실제 기록 361ms; 이미지 pull과 초기 준비는 제외 |
| 최초 실패 | `START_GARAGE`의 `SAME_OWN_CONTAINER_FULL_CONFIGURATION` |
| command / 관측 처리 실패 | 각각 0개; 최초 실패와 정리 실패는 guard 거부로 기록 |
| initializer 종료 | 확인 |
| 모든 자기 컨테이너 종료 | 미확인, `ownedContainersStopped=false` |

PG는 마지막 관측에서 `running=true`, `oomKilled=false`, `State.Error` 없음이었습니다. 동일한 bound identity에 대한 6개 전체 signature 중 `hostChanged`만 true였고, 당시 고정한 HostConfig 42개 필드는 모두 false였습니다. `hostConfigUnknownKeysChanged=true`이므로 목록 밖에 변화가 있었다는 범위만 확인했습니다. Config의 모든 고정 필드와 unknown 비교는 false였으며 `MacAddress`도 false였습니다. **MAC을 바꾸거나 동일성 검사에서 제외할 근거는 이 기록에 없습니다.**

Garage는 `created` 상태였습니다. 전체 canonical signature는 모두 동일했고 raw Mounts 배열은 순서만 달라졌습니다. `mountOrderOnlyChanged=true`, `mountContentChanged=false`였으며, 이번 canonical 비교에서는 `mountsChanged=false`였습니다. 이 관측은 PG의 HostConfig 변화와 구분합니다.

PG 변화는 Garage 시작 직전의 전체 동일성 검사를 통과하지 못했고 정리 단계에서도 같은 guard가 거부했습니다. 마지막 inspect command는 종료 코드 0이었지만 전체 정리가 확인됐다는 뜻은 아닙니다. PG의 정상 종료, Garage readiness, 전체 Cloud9 성공, 이전 실패들의 유일한 원인을 주장하지 않습니다.

[공개 summary](config-readback.summary.json)는 root가 받은 8,155바이트 원문 그대로입니다. 전체 SHA-256은 `bf8c9057968497bb113314dfba9bfa1ec9d4079714af16595f3d98939941299a`입니다. root의 별도 retrieval receipt와 strict validator가 실제 source·run·job 및 producer `2870124c…` 연결을 확인했으며, 검증된 record의 상태도 FAILED입니다. 검증기 통과는 산출물의 형식·연결 확인이며 진단 실행의 성공을 뜻하지 않습니다.

앞선 [세 번째 전체 실패](ATTEMPT3.md), [Mounts 진단](STARTUP_MOUNT_DIAGNOSTIC.md)과 그 이전 원문은 보존했습니다. 다음 진단은 고정 HostConfig 이름 목록을 확장해 변화를 더 좁히는 별도 후보입니다. 이번 기록을 소급해서 다른 필드의 실제 변화나 원인 증명으로 바꾸지 않습니다.
