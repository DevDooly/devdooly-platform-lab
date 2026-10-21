# 100개 센서 범례의 줄바꿈

2026-10-21 UTC, 입력1,000개·센서100개인 기존 결과를 선택했을 때 범례가 한 줄로 늘어나던 문제를 수정했습니다. 공개 데스크톱·모바일의100개 항목과 문서 폭을 확인했고, 기본 URL에서도 reload·실시간 조회 후 정상 폭을 확인했습니다. 첫 API 조회가 게시 기록으로 fallback한 원인은 아직 미확인입니다.

## CSS 변경과 로컬 확인

[global.css](../../../apps/lab-web/src/styles/global.css)의 `.chart-legend`에 `flex-wrap:wrap`, `min-width:0`, `max-width:100%` 세 속성만 추가했습니다. JavaScript·API·데이터·선택 처리는 바꾸지 않았습니다.

| CSS 원문 | SHA-256 |
| --- | --- |
| 수정 전 | `c7122fea619b3f1994cf76d83c8b3b6a86b7f766a65323c14e7344e6d964a867` |
| 수정 후 | `375c150ac74699d4ae2db967de3b7b4299998e8eebf28e18373ed4d4d2824711` |

프로젝트 경로의 정적2페이지 빌드와 로컬 기본2센서 결과의 데스크톱·모바일 폭1265/375px을 확인했습니다. 이 로컬 기본 결과를100개 센서의 검증으로 쓰지 않습니다. 이번 CSS 단독 확인에서 JavaScript209개 검사를 다시 실행하지 않았으며, 그 통과 기록은 [요청 ID 회귀](../run-response-identity/README.md)의 별도 결과입니다.

## 게시와 공개 측정

[PR186](https://github.com/DevDooly/devdooly-platform-lab/pull/186)은 head `066a49e6d292a5ba48048009d2d686f2102bdfa1`에서 `03:13:10Z`에 병합됐고 main은 `d52a4c32a81ab99d549c65f4b8d68325af8e14a3`입니다. [Pages39537360023](https://github.com/DevDooly/devdooly-platform-lab/actions/runs/39537360023)은 build `03:14:17Z`·deploy `03:14:30Z`, [CI39537360025](https://github.com/DevDooly/devdooly-platform-lab/actions/runs/39537360025)는 verify `03:16:28Z`·public-read-gateway `03:14:13Z`에 성공했습니다. 조건부 격리4개 job은 생략됐습니다.

첫 기본 주소 조회는 이전 `global.Bfs-HDcN.css`와 `nowrap`을 유지했고 문서 scroll 폭8446px이 client1265px을 넘었습니다. 이 실패를 이후 성공으로 덮지 않습니다. `?v=d52a4c32`를 붙인 별도 조회에서는 새 `global.NC6VDXhQ.css`와 `wrap`을 확인했습니다.

| 새 CSS를 확인한 화면 | 데스크톱 | 390px 모바일 |
| --- | ---: | ---: |
| client / scroll 폭(px) | 1265 / 1265 | 375 / 375 |
| 범례 항목 / 고유 label | 100 / 100 | 100 / 100 |
| 범례 줄 수 | 20 | 50 |
| 범례 폭(px) | 800.703125 | 303 |
| 범례 오른쪽 끝(px) | 882.203125 | 339 |

각 항목이 범례 안에 들어갔으며 입력1,000·성공500·실패300·중복200·대기0과 선택 ID를 유지했습니다. 이후 입력12개 결과로 복귀해12/7/3/2/0·범례2개·문서 폭1265px도 확인했습니다.

## 기본 URL의 재확인과 남은 진단

쿼리 없는 기본 URL은 일반 이동에서 이전 CSS를 다시 참조했습니다. reload 후에는 새 `global.NC6VDXhQ.css`가 적용됐지만, 첫 API 조회가 게시 기록으로 fallback해 선택 입력이 비활성화됐습니다. 원인은 `UNOBSERVED`이며 당시 console error는 관측하지 못했습니다.

실시간 조회 버튼을 한 번 누른 뒤 live로 회복했고, 같은 기본 URL에서 입력1,000개의100개 범례·`wrap`·client/scroll1265px을 확인했습니다. 이전 CSS 참조나 첫 조회 실패의 원인을 캐시·네트워크로 확정하거나, 원인을 수정했다고 기록하지 않습니다. 다음은 이 첫 조회 fallback의 원인 진단입니다.

기존 공개 결과를 읽은 화면 확인이며 새 작업·POST·운영 설정 변경은 하지 않았습니다. 한 회차의 화면 확인을 장기 가용성·worker 생존·외부 API 실패 원인 해결의 근거로 확대하지 않습니다. 기동 복원·토큰 교체·자원 예산 정책·PR102는 계속 보류합니다.
