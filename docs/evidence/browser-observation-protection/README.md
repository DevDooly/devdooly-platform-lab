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

UTC 동등 표기 후속 [#211](https://github.com/DevDooly/devdooly-platform-lab/pull/211)에서는 이미 폐쇄형 검증을 통과한 두 작업 DTO 사이의 시각 비교를 교정했다. 같은 순간의 UTC 소수초 자릿수만 달라도 내용 충돌로 오거절하던 경우를 기존 나노초 비교로 수락하며, 원본 객체·원문 시각과 정상 재수신의 retainedPrevious=false 정책은 유지한다. 같은 수집 시각에서 내부 시각의 실제1ns 차이·소스·상태 충돌은 계속 거부하고, 단일 DTO 내부의 sourceVerifiedAt·queuedAt 문자열 동일성 계약은 바꾸지 않았다. 새 회귀4개 중 수정 전3개 실패·수정 후4개 통과, Node24.19의 관련8개 통과를 확인했다. 로컬 전체 웹251개·생략0·타입49파일 오류/경고/힌트0·프로젝트 경로 빌드2페이지가 통과했다.

병합 main `e19c7798269d888de250bc3266b2caf32c49de81`의 [Linux CI39956949286](https://github.com/DevDooly/devdooly-platform-lab/actions/runs/39956949286)에서도 웹251개·생략0·타입49파일 진단0·2페이지 빌드와 기본 verify·public-read-gateway가 성공했다. 선택적 Spark·Iceberg·S3·Cloud 실증4개는 생략했다. [Pages39956949293](https://github.com/DevDooly/devdooly-platform-lab/actions/runs/39956949293)의 build·deploy 성공 뒤 고정 공개 경로의 GET2회로 현재 HTML이 `JobObservationCard.DuNxBdiB.js`를 참조하고, 제공된19,210바이트·SHA-256 `34ab69ef856dc0221111fb0c584e95edea29872e5cbb04131e3584e181fe6681`이 로컬 검증 빌드와 같은지 확인했다. 이 확인은 HTML 참조·JS bytes 배포 근거이며 새로운 브라우저 동작 검증과 구분한다. 위247개까지의 공개 정상 재조회 기록은 당시 근거로 보존한다.

Kafka 본문 수신 중 일반 전송 오류를 INVALID_RECORD로 오분류하던 후속도 교정했다. HTTP200 헤더·첫 JSON chunk 뒤 TypeError가 발생하면 기존 Kafka만 INVALID_RECORD, job/platform은 NETWORK_ERROR였던 반례를 재현했다. Kafka의 import와 catch만 바꿔 ABORTED를 우선하고 InvalidObservationBody는 INVALID_RECORD, 일반 전송 오류는 NETWORK_ERROR로 나눈다. 공통 helper·다른 loader·UI는 바꾸지 않았고 기존 연결 오류 안내를 재사용한다. 최초/부분 수신과 이전 기록 유무의4조합, abort 우선순위, 실제 loopback HTTP 응답의 중간 종료를 새 회귀3개로 검사했다. 수정 전 새3개 중2개 실패·수정 후 관련7개 통과를 확인했고, 이전 객체·원 수집 시각 보존과 미완성 JSON·예외 canary 비노출을 확인했다. Node24.19의 로컬 전체 웹262개·통과262·생략/실패0, Astro50파일 오류/경고/힌트0, 프로젝트 경로 빌드2페이지가 통과했다. 외부 운영 장애를 주입한 결과는 아니다.

[PR215](https://github.com/DevDooly/devdooly-platform-lab/pull/215)의 병합 main a523516342de5a20392f2aab07ffd1a42893a938에서 [Linux CI39959141358](https://github.com/DevDooly/devdooly-platform-lab/actions/runs/39959141358)의 verify·public-read-gateway가 성공했다. 실제 job 로그에서 웹262개·통과262·생략/실패0, Astro50파일 진단0·2페이지 빌드를 확인했으며 선택적 Spark/S3/Iceberg/Cloud 실증4개는 생략했다. push로 실행된 [Pages39959141505](https://github.com/DevDooly/devdooly-platform-lab/actions/runs/39959141505)의 build·deploy도 성공했다. 고정 공개 경로의 GET2회에서 현재 HTML의 KafkaObservationCard.C-s4sSuM.js 참조와 제공된9,520바이트·SHA-256 0fb64b71278da652c700caa5b763836a008e191359ec77a2384a5ce524a7c34a의 로컬 빌드 일치를 확인했고, 검사기는 exit0·PUBLIC_KAFKA_BUNDLE_MATCHED를 반환했다. 이 확인은 proxy 비사용·redirect/retry0의 HTML 참조·JS bytes 게시 근거이며 새 브라우저 실행이나 운영 장애 주입 검증과 구분한다.

보호 범위는 한 브라우저 세션의 응답 적용이다. 서버·게시 순서·탭 간 영구 이력·운영 복구·장기 가용성은 보장하지 않는다. Pages 토큰 교체·별도 환경 기동 복원·자원 예산 정책·PR #102는 보류한다.
