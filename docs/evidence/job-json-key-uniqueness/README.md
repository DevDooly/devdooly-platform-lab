# Job 관측 JSON key 중복 거부

Job 관측의 원문 JSON에 같은 object의 key가 반복되면 브라우저의 JSON.parse가 마지막 값만 남겨 모호한 입력을 정상 기록으로 채택할 수 있었습니다. 실제 loader의 합성 반례7개에서 이를 재현했고, 같은 원문을 실제 job collector의 collect_jobs와 Pages 준비의 parse_record는 이미 거부함을 확인했습니다. 저장된 합성 입력과 가짜 응답을 사용한 오프라인 비교이며 운영에서 발생한 사건을 확인한 결과가 아닙니다.

[PR226](https://github.com/DevDooly/devdooly-platform-lab/pull/226)은 Job 수신 경계에 object별 key 유일성 검사를 추가했습니다. helper는 native JSON.parse의 문법 판정과 반환값을 그대로 사용하고 JSON escape를 해제한 key의 중복만 추가로 거부합니다. 값이 같은 중복·충돌 중복·escaped 중복은 INVALID_RECORD로 처리하며 직전 검증된 객체 identity·원 시각을 보존합니다. 단독 escaped key와 서로 다른 object의 동일 key는 허용하고 기존 DTO 검증을 유지합니다. Kafka·Platform의 정책이나 운영 수집기는 변경하지 않았습니다.

소스 head는 2ec97db1f9b3ec38b9c6873c9cec92e3d559ce61이며 병합 main은 b7b970933444f46c91c9e68304222e0cf31ee120입니다. 검증 결과는 다음과 같습니다.

- 새 loader 회귀3개는 수정 전1개 실패·2개 통과였고, helper 검사2개를 추가한 수정 후 Job27개가 통과했습니다. 별도 독립 검사5개도 통과했습니다.
- decoded-key 유일성의 수락/거부는 Python oracle1,012개(수락565·거부447)와 일치했고 문법 오류12개는 native 판정과 같았습니다. Python의 전체 숫자 해석·정밀도 계약과 일치한다는 뜻은 아닙니다.
- 로컬·[main CI39967614202](https://github.com/DevDooly/devdooly-platform-lab/actions/runs/39967614202)·[Pages39967614242](https://github.com/DevDooly/devdooly-platform-lab/actions/runs/39967614242)의 실제 검증에서 웹278개 통과·실패/생략0, Astro51파일 진단0·정적2페이지 빌드를 확인했습니다. CI verify·public-read-gateway와 Pages build·deploy는 성공했으며 별도 격리 실증4개 job은 생략했습니다.

고정 Pages HTML과 참조 JS의 GET2회에서 JobObservationCard.Dbxv1N1K.js의 전체19,613바이트·SHA-256 a6b97275369acd85f416b6d0b1b7413ce6e39a8d35115c02432968f44859e67c가 로컬 빌드의 고정값과 일치했습니다. 로컬 자산에는 guard가 포함되어 있고 별도 parser chunk는 없음을 확인했습니다. 이는 공개 정상 자산의 전달 근거이며 중복 거부 동작은 위 합성 회귀로 구분합니다. 새 브라우저 실행·API 관측·공개 중복 입력 주입·운영 발생을 검증한 결과가 아닙니다.
