# 저장 JSON으로 이벤트 응답 비교

[저장한 이벤트 JSON 비교](https://devdooly.github.io/devdooly-platform-lab/runs/offline/)는 API 접속이 어려워도 이미 보관한 결과를 다시 볼 수 있는 별도 페이지입니다. [이벤트 내보내기](event-export.md)의 JSON 두 개를 A·B로 선택한 뒤 비교 버튼을 누릅니다. API 안내에서 복사한 전체 응답이나 비교 요약 CSV는 지원 파일이 아닙니다.

페이지·JavaScript를 내려받은 뒤 파일 내용은 브라우저 메모리에서만 읽고 계산합니다. 파일 선택만으로 읽거나 서버에 업로드하지 않으며 API GET·새 실행·Kafka/S3 요청·localStorage 저장을 추가하지 않습니다. 사이트 자체를 네트워크 없이 설치·여는 PWA 기능은 아닙니다. 같은 파일이나 같은 runId의 서로 다른 검색 결과도 비교할 수 있습니다.

## 지원 파일과 검증

파일당 **UTF-8 1MiB(1,048,576bytes) 이하**, **저장 행 최대1,000개**를 지원합니다. 읽기 전 파일 크기를 확인하고 실제 읽은 bytes도 다시 검증합니다. 첫 BOM 한 개는 허용하며 잘못된 UTF-8, JSON 문법 오류·디코딩한 중복 object key, 다른 버전·필수 키 누락·추가 키·타입 오류는 거부합니다. 이 한도는 새 파일 소비자에만 적용하며 기존 exporter/API를 바꾸지 않습니다.

| 영역 | 지원 계약 |
| --- | --- |
| root | schemaVersion,source,filters,counts,outcomes 다섯 키. 버전1 또는2 |
| source | runId 문자열, mode=live/recorded/fixture, observedAt·capturedAt은 유효한 날짜 문자열 또는 null. 날짜를 새 시각으로 바꾸지 않음 |
| filters v1 | status=ALL/SUCCESS/FAILED/DUPLICATE/PENDING, query 문자열, reason 문자열 또는 null |
| filters v2 | 위 세 필드와 sensorId 문자열 필수. 빈 문자열도 정확 센서 조건이며 v1에 이 키를 추가하지 않음 |
| counts | reportedInputCount,availableOutcomes,matchedOutcomes는 0 이상 safe integer. matched=저장 행 수이며 matched≤available |
| outcome | sequence는 0 이상 safe integer, eventId·sensorId·eventTime·reason은 원문 문자열, value는 유한 숫자 또는 null, status는 네 분류 |

모든 저장 행이 선언된 상태·부분 검색·사유·정확 센서의 AND 조건에 맞는지도 확인합니다. reason=null은 전체 사유, reason=""는 빈 사유입니다. runId는 내보내기 형식의 문자열로 보존하며 API 주소나 링크로 사용하지 않습니다. 실패한 시각 입력도 보관할 수 있도록 **eventTime은 날짜 형식으로 검증하지 않습니다**.

reportedInputCount≥availableOutcomes, sequence의 연속성·유일성·보고 입력 수 이하 조건은 파일 계약에 없습니다. 반복 ID·sequence·원문 순서를 유지하며 [기존 순서별 비교 모델](event-comparison.md)에 전달합니다. 중복 sequence를 거부하거나 첫 행으로 치환하지 않습니다. 파일의 오류 메시지는 정해진 종류만 표시하며 본문·예외 원문을 오류에 포함하지 않습니다.

## 출처와 부분 결과

파일명·용량·schemaVersion, 원 source·filters·세 counts를 A·B별로 표시합니다. **파일에 기록된 출처는 파일의 자체 주장**입니다. mode=live도 내보낼 당시의 API 출처 표기일 뿐 현재 실시간 연결·파일 진위·서버 원문을 인증하지 않습니다. 유효한 형식의 파일도 수정됐을 수 있습니다. 원 관측·게시 시각과 null은 파일을 읽은 시각으로 대체하지 않습니다.

matchedOutcomes는 저장된 검색 결과, availableOutcomes는 내보내기 전 읽은 행 수, reportedInputCount는 실행의 보고 입력 수입니다. 세 수치가 같아도 전체 입력의 완전성이나 원본 동일성을 증명하지 않습니다. A가 FAILED만 저장되고 B가 ALL이면 한쪽 미관측이 생길 수 있습니다. 이를 삭제·처리 누락으로 해석하지 않습니다.

파일에 없는 전체 성공·실패 통계, scenario·seed·series·시작/완료 시각·GET 출처를 만들어 가짜 RunDetail로 주입하지 않습니다. 저장된 outcomes의 sequence 위치만 대응하고 보고 입력4필드와 판정2필드 차이·모호성·미관측을 구분합니다. 원본 입력·실행 코드·수정 효과를 추정하지 않습니다. null 값으로 원래 null·NaN·무한대를 복원하거나 eventTime을 정규화하지 않습니다.

## 조작 범위

검색·5분류·20개씩 더 보기는 이미 검증한 두 파일만 좁힙니다. 새 파일 선택은 준비 중인 파일과 표시 중인 이전 비교를 구분하며, 명시 비교가 모두 성공해야 새 pair로 교체하고 목록 조건을 초기화합니다. 파일 읽기·검증 실패와 선택 취소는 이전 비교·출처·조건을 바꾸지 않습니다. 준비 전·읽는 동안 입력을 잠그고 동시 비교를 하나로 제한합니다. 비우기는 파일 선택과 표시 중인 비교를 메모리에서 지웁니다.

파일 행을 API 상세 링크나 기존 온라인 공유·CSV에 연결하지 않습니다. 원 온라인 API 화면·검색·내보내기·공유 형식과 운영 image/source pin은 유지합니다.

## 검증 상태

로컬 기본 병렬 웹 검사 **490개**, Astro **85파일 진단0**, **5페이지 빌드**를 통과했습니다. 다른 채팅에서 모델 경계85사례와 원 온라인 지원 코드 보존을 독립 확인했습니다. 최초 웹 검사의 신규 메시지 정규식 불일치1개와 최초 타입 검사의 assertion 브리지 오류1개는 각각 수정했으며 원 기록을 보존합니다. PR269의 기존 Kafka 병렬 검사 실패 원인을 이번 통과로 소급 확정하지 않습니다.

실제 파일 선택에서는 합성 v1·v2의25개 sequence 그룹을 비교해 모호1·미관측2·입력 차이1·판정 차이1·필드 일치20을 확인했습니다. 선택만으로 결과를 만들지 않았고, 명시 비교·20→25개 더 보기·반복 ID 두 위치 검색·모호 후보 펼치기를 확인했습니다. 중복 key와1MiB 초과 파일은 정해진 오류로 거부하고 이전 파일·검색·분류를 유지했습니다. 유효한 새 비교는 조건을 초기화하며 같은 빈 파일의0개 결과와 비우기 후 입력 값·표시 해제를 확인했습니다.

모바일375px에서 전역 가로 넘침0·본문17px·입력/버튼 최소49px를 확인했습니다. 이는 합성 저장 파일의 UI 검증이며 운영 입력·서버 응답 진위 인증이 아닙니다. 파일 처리 코드의 업로드/API 호출 부재와 화면 동작을 확인했지만 패킷 캡처를 수행한 결과는 아닙니다. 초기 페이지·자산 연결은 필요할 수 있습니다.

[PR271](https://github.com/DevDooly/devdooly-platform-lab/pull/271)의 source `4d4906d4406de9a9117e3f8400f0352776a7d4ec`를 독립 검토하고 main `a0f761722035424bbcf04918fd8a18bccb7a2486`에 병합했습니다. 두 tree는 `3a51aef48d89e4b6e5288ef26449edde6bb4d032`로 같습니다. 같은 main의 [CI40164904336](https://github.com/DevDooly/devdooly-platform-lab/actions/runs/40164904336)은 verify·public-read-gateway 성공, 별도 환경 시험4개 skip이며 [Pages40164904335](https://github.com/DevDooly/devdooly-platform-lab/actions/runs/40164904335)는 타입·기본 웹 검사·빌드와 build/deploy 성공입니다. 별도 운영 기동·현재 가용성 검증을 뜻하지 않습니다.

2026-10-25 공개 페이지에서도 별도의 합성 v1/v2 파일을 실제 선택했습니다. 선택만 한 상태에는 비교가 없고 명시 비교 뒤25그룹의1/2/1/1/20·20→25개·공백/대소문자 무시 검색과 판정 차이1행을 확인했습니다. 중복 key 파일 거부 뒤 기존 파일·검색·분류가 남았고, 비우기 뒤 두 입력 값과 표시 비교가 해제됐습니다. 모바일375px의 넘침0·본문17px·조작 영역 최소49px도 확인했습니다. 합성 `recorded` 값은 파일 자체 주장으로 표시했으며 실제 서버 파일의 인증으로 표시하지 않았습니다. 로컬의 크기 초과·빈 파일·모호 후보 확인과 공개에서 수행한 항목을 구분합니다.

**[현재 조건의 비교 보고서 JSON 저장](offline-comparison-report.md)**을 추가하고 검증 중입니다. 원파일의 조건·메타데이터와 현재 화면 조건을 구분하고, 조건 일치 그룹 전체와 모든 모호 후보를 담는 별도 보고서입니다. 기존 이벤트 내보내기 v1/v2나 원파일 bytes·세션 복원 형식으로 취급하지 않습니다. PR271의 파일 읽기 완료 결과와 새 다운로드의 검증 범위를 구분합니다.

Pages 토큰 교체·별도 환경의 K3s/Jenkins 기동 복원·예산 정책·PR #102는 계속 보류합니다. 기존 서비스·자료·자동 이미지 제안 PR·다른 PAUSED 자동화는 바꾸지 않습니다.
