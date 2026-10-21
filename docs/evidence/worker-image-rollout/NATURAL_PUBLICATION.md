# worker 교체 후 저장된 Pages 관측

[worker 교체](README.md) 뒤 생성된 [Pages39523423769](https://github.com/DevDooly/devdooly-platform-lab/actions/runs/39523423769)의 build·deploy가 성공했습니다. 공개 플랫폼·작업·Kafka JSON을 각각 한 번 읽어 이 실행의 artifact와 전체 bytes가 같음을 확인했습니다. 이는 실시간 API 화면과 별도로, 저장된 관측에도 새 worker가 반영된 결과입니다.

| 항목 | 확인한 값 |
| --- | --- |
| Pages source | `6b628211fbc5b619b2900e221290b8e92e02da84`, main의 workflow_dispatch·attempt1 |
| 실행 생성 / deploy 완료(UTC) | `2026-10-21T00:47:21Z` / `2026-10-21T00:48:54Z` |
| 플랫폼 수집(UTC) | `2026-10-21T00:47:20.180215Z` |
| 작업 수집(UTC) | `2026-10-21T00:47:20.295408061Z` |
| 저장된 worker source | `6f551a16a8ed536bb126403234c41b9e9b266d43` |
| 저장된 worker 시작 / heartbeat(UTC) | `2026-10-21T00:20:05.207272Z` / `2026-10-21T00:47:19.998983Z` |
| 관측 API source | `245d61a5749760a20918ab091d9410ce6735b1c0` |

플랫폼 기록의 main·Argo revision은 Pages source와 같고 Argo는 Synced·Healthy였습니다. 작업 기록은 RUNNING·CONSUME, 빈 슬롯·공개 실행 비활성 상태입니다. 이전 공개 기록의 기존 작업8개 전체 projection은 새 기록과 같았습니다. worker의 journal 값은 프로세스나 lease 생존의 직접 증명이 아닙니다.

## artifact와 공개 파일 대조

고정 run·source·attempt와 artifact 이름·크기를 확인한 뒤 관측 artifact3개만 내려받았습니다. `github-pages` 전체 묶음은 사용하지 않았습니다. 작업·Kafka의 publication 기록은 각각 `recordPresent:true`였습니다. `00:51:27`–`00:51:28 UTC`에 읽은 아래 공개 파일3개가 대응 artifact 원문과 정확히 같았습니다.

| 파일 | bytes | SHA-256 |
| --- | ---: | --- |
| [플랫폼 JSON](https://devdooly.github.io/devdooly-platform-lab/data/platform-observation.json) | 1,355 | `e197081f7d9807acaa15d612693d019fa9aa6394d409804ecf4be62aee2c09c4` |
| [작업 JSON](https://devdooly.github.io/devdooly-platform-lab/observations/jobs.latest.json) | 5,812 | `1e6ab593a78681df8eace3aae53fba08b1ac76027cbe86c47a496820ef5dba88` |
| [Kafka JSON](https://devdooly.github.io/devdooly-platform-lab/observations/kafka.latest.json) | 562 | `120a593ea3602f3a5e5fa70fcacd6f8e2ea43835ecd542b4998db5ec1f61a6ed` |

이 주소의 파일은 이후 정상 주기에 갱신됩니다. 위 해시는 지정 시각과 실행의 원문에 대한 값이며 언제나 같은 bytes를 반환한다는 뜻이 아닙니다. Kafka의 공개 `readCommittedEndOffset`은 READ_COMMITTED 관측이며 이전 보존 점검 CLI의 log end와 구분합니다.

## 주기와 연결 범위

수동 Pages dispatch·timer 시작·주기 단축은 하지 않았습니다. systemd 메타데이터에서 timer의 `09:47:18 KST` trigger와 service의 `00:47:18`–`00:47:22 UTC`, success·exit0을 확인했습니다. unit 표시 시각은 초 단위이며 더 세밀한 시각으로 해석하지 않습니다.

별도 읽기 전용 확인에서는 전후 같은 unit invocation을 대조하고, 그 invocation·unit·Python 프로세스의 고정 결과 한 건만 검증했습니다. `2026-10-21T00:47:22.176386Z`의 결과는 `DISPATCHED`와 run `39523423769`를 가리켰습니다. 따라서 시각 일치뿐 아니라 실행기가 반환한 번호를 위 Pages 실행과 연결했습니다. systemd invocation ID·커서·원문 journal은 공개하지 않습니다.

반복 실행의 모든 회차 성공·정확히30분 간격·장기 가용성·인증서 자연 갱신·새 관측 실행기 코드의 설치를 검증한 결과는 아닙니다. 기동 복원·토큰 교체·자원 예산 정책·PR102 보류는 유지합니다.
