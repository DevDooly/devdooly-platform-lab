# 브라우저 관측 응답 보호

플랫폼·작업 관측의 늦은 응답·동시각 충돌·초과 본문이 기존 유효 기록을 덮지 않도록 보완했다. 각 변경의 소스·CI·Pages와 공개 정상 재조회를 확인했다.

| 변경·로컬 웹 검사 | 검사 소스 | Linux CI | main CI·Pages |
| --- | --- | --- | --- |
| [#202](https://github.com/DevDooly/devdooly-platform-lab/pull/202) 시도·성공 순서 / 239개 | `3705f8465511644b613cdc0cdadc1d66e591181c` | [39950117260](https://github.com/DevDooly/devdooly-platform-lab/actions/runs/39950117260) PASS | main `aa4b55878d0609159f113381018a7a02b78477ef` · [CI](https://github.com/DevDooly/devdooly-platform-lab/actions/runs/39950576977)·[Pages](https://github.com/DevDooly/devdooly-platform-lab/actions/runs/39950577839) PASS |
| [#203](https://github.com/DevDooly/devdooly-platform-lab/pull/203) 본문 크기 제한 / 243개 | `07f49f40ff56e71a456de54cda133b3a44e3d33b` | [39951079265](https://github.com/DevDooly/devdooly-platform-lab/actions/runs/39951079265) PASS | main `6ed465ea6d6caf352988caad42b44af8f8a073b1` · [CI](https://github.com/DevDooly/devdooly-platform-lab/actions/runs/39951510110)·[Pages](https://github.com/DevDooly/devdooly-platform-lab/actions/runs/39951510152) PASS |
| [#205](https://github.com/DevDooly/devdooly-platform-lab/pull/205) 작업 기록 충돌 / 247개 | `d436770a994b048c66ace85cba3f290afa3331a3` | [39952317414](https://github.com/DevDooly/devdooly-platform-lab/actions/runs/39952317414) PASS | main `cb03d8d4a84f88334b6a9166fe43430b8c155602` · [CI](https://github.com/DevDooly/devdooly-platform-lab/actions/runs/39953019329)·[Pages](https://github.com/DevDooly/devdooly-platform-lab/actions/runs/39953019203) PASS |

로컬 검사는 각각 생략0·타입49파일 진단0·base 지정 단일 빌드의 페이지2개 성공이다. 수치는 합산하지 않는다. Linux의 선택적 별도 환경 시험은 생략됐으며 기본 verify·public-read-gateway 성공과 구분한다.

- 플랫폼은 최신 실패 시도와 최신 성공을 나노초까지 각각 유지한다. 같은 시각의 다른 내용은 전체 거부하고 동일 재조회는 정상 처리한다.
- 본문은 읽는 중 플랫폼16KiB·작업128KiB 상한을 적용한다. 초과하면 취소를 요청하고 이전 기록을 보존한다. 제공자의 취소 완료를 기다리지 않는다. 별도 hard deadline을 추가한 결과는 아니다.
- 작업 관측은 같은 수집 시각에 실행 상태가 다르면 거부한다. 새 수집 시각의 정상 변화와 같은 내용 재조회는 허용한다.

로컬 합성 화면에서 플랫폼 부분 보존·동시각 오류 코드 충돌과 작업 NOT_STARTED→RUNNING 충돌 거부·새 시각 허용을 확인했다. 모바일390px Enter 재조회·문서375px 가로 넘침0도 확인했다. 운영 충돌 시험은 아니다.

공개 정상 조회·재조회에서 #202 `gVGkeXYG`·#203 `_tOxXD45` asset과 원래 플랫폼 수집 시각 `2026-10-23T11:41:15.086039Z` 유지·부분 보존 안내0을 확인했다. #205는 `JobObservationCard.WWgOd8Gt.js`로 반영됐고 작업 수집 시각이 `2026-10-23T12:26:28.883043387Z`에서 `12:26:32.565360754Z`로 전진하는 정상 재조회·충돌 안내0을 확인했다. 이는 각 확인 시점의 기록이다.

보호 범위는 한 브라우저 세션의 응답 적용이다. 서버·게시 순서·탭 간 영구 이력·운영 복구·장기 가용성은 보장하지 않는다. Pages 토큰 교체·별도 환경 기동 복원·자원 예산 정책·PR #102는 보류한다.
