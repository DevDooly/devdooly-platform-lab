# heartbeat 시각 순서 표시 회귀 검증

2026-10-21(KST)에 API 계약이 허용하는 합성 입력으로 표시 오류를 재현하고 수정했습니다. DB 확인 시각보다 미래인 heartbeat를 서버는 `stale: true`로 분류합니다. 기존 화면은 브라우저 시각이 heartbeat를 지난 뒤 이 값을 모두 “heartbeat 기록 후 5분 초과”로 표시했습니다.

| 합성 입력 | 값 |
| --- | --- |
| DB 확인 시각 | `2026-10-20T10:00:00Z` |
| heartbeat | `2026-10-20T10:00:01Z` |
| 검증에 지정한 브라우저 시각 | `2026-10-20T10:00:02Z` |
| 기존 결과 | 계약 검사 통과, heartbeat 경과 1초인데 `stale-signal` |
| 수정 결과 | DB 확인과 heartbeat의 순서가 역전되어 `clock-check` 유지 |

기존 UTC nanosecond 비교 함수를 사용해 heartbeat가 해당 기록의 DB 확인 시각보다 미래인지 먼저 확인합니다. 브라우저 시각이 전진하거나 회귀해도 같은 저장 기록의 역전은 사라지지 않습니다. 화면에는 “heartbeat·DB 확인·브라우저 시각의 순서를 확인해야 합니다”를 표시합니다. 실제 시각과 원본 source SHA는 그대로 유지합니다.

## 확인한 범위

- 수정 전 기존 함수를 실행해 위 합성 DTO의 허용과 잘못된 `stale-signal`을 확인했습니다.
- 순수 회귀 검사 2개를 추가했습니다. 1ns·1초 역전, 브라우저 추월·회귀, 동률·1ns 이전과 서버가 관측한 5분+1ns 경과를 대조합니다. 기존 오류 시 마지막 유효 기록 보존 검사도 유지했습니다.
- 해당 파일의 검사 14개·전체 웹 188개, skip 0을 통과했습니다. Astro 44파일 오류·경고 0과 프로젝트 경로 빌드를 확인했습니다.
- 로컬1280px·390px의 recorded 모드에서 실제 컴포넌트와 합성 JSON을 연결했습니다. 다시 읽기 후 시각 확인 안내가 유지되고 잘못된 5분 초과·최근 신호 문구가 없으며, 본문17px·가로 넘침 부재를 확인했습니다.
- 로컬 검증용 페이지와 JSON 두 파일을 제거한 뒤 production build에 해당 경로·fixture가 없는 것을 확인했습니다.

## 공개 게시와 확인

[PR152](https://github.com/DevDooly/devdooly-platform-lab/pull/152)를 main `a7eb9926540cbfa76dced881254416047aaf6dc0`에 병합했습니다. 같은 소스의 [Pages](https://github.com/DevDooly/devdooly-platform-lab/actions/runs/39450633388)·[main CI](https://github.com/DevDooly/devdooly-platform-lab/actions/runs/39450633233)·Jenkins를 통과했습니다.

2026-10-20 15:45–15:48 UTC에 공개1280px·390px에서 실제 읽기 API와 다시 읽기, 본문17px·SHA 줄바꿈·가로 넘침 부재를 확인했습니다. 관측 시점에 따라 시각 확인 경고와 최근5분 신호를 각각 보았으며, 두 표시를 동시에 같은 기록의 결과로 취급하지 않습니다. 실행기 `74a8e988`·API `245d61a5` 소스와 작업8개·빈 슬롯 기록을 유지했습니다. 이는 그 시점의 조회 결과이며 프로세스 생존·시계 동기화·장기 가용성을 입증하지 않습니다.

## 관련 구현

- [서버의 stale 판단](../../../apps/api/src/main/java/io/github/devdooly/platformlab/jobs/observation/JobObservationService.java)
- [기존 계약과 화면 분류](../../../apps/lab-web/src/lib/job-observation.ts)
- [표시 컴포넌트](../../../apps/lab-web/src/components/JobObservationCard.tsx)
- [회귀 검사](../../../apps/lab-web/tests/job-observation.test.ts)

API·DB·worker·기록 원문은 유지했습니다. 토큰 교체·예산 정책·PR102는 계속 보류합니다.
