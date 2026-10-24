# 검색한 이벤트를 CSV·JSON으로 저장

기준: 2026-10-24 KST. [Java 처리 결과](https://devdooly.github.io/devdooly-platform-lab/#lab)의 **이벤트 상세 → 검색 결과 저장**에서 현재 조건에 맞는 이벤트를 파일로 준비합니다. 기존 비교 CSV는 두 실행의 집계이고 API 안내의 JSON 복사는 전체 응답입니다. 이 기능은 현재 검색한 개별 이벤트를 조건·출처와 함께 보관합니다.

## 저장하는 범위

ID·센서 검색과 상태·사유 조건에 맞는 전체 검색 결과를 담습니다. [표의 페이지](event-pagination.md)와 관계없이 모든 일치 행을 저장합니다. 흐름에서 선택한 한 건만 저장하는 기능은 아닙니다. 응답의 입력 순서와 같은 eventId의 개별 행, sequence·eventId·sensorId·eventTime·value·status·reason을 유지합니다. 다른 조건으로 판정하거나 합치지 않습니다.

출처는 live/API 조회, recorded/게시 관측, fixture/고정 샘플 기대값을 구분합니다. 실행 ID와 상세 결과의 observedAt 원문, 게시본·fixture의 capturedAt을 별도로 담습니다. 요약 API의 시각으로 상세 관측 시각을 대체하지 않으며 fixture를 운영 관측으로 표시하지 않습니다.

보고된 입력 건수(reportedInputCount), 현재 읽은 outcome 수(availableOutcomes), 검색 결과 행 수(matchedOutcomes)는 서로 다른 수치입니다. query는 입력한 공백·대소문자를 그대로 저장하고 검색할 때만 기존 검색 규칙을 적용합니다. reason=null은 전체 사유, reason=""는 빈 문자열 사유입니다.0건이면 이전 결과를 대신 담지 않고 빈 이벤트 목록과 현재 맥락만 저장합니다.

## JSON과 CSV

JSON은 schemaVersion=1,source,filters,counts,outcomes로 구성합니다. 위에 명시한 원문 필드와 숫자·문자열·null을 보존하는 형식입니다. HTTP 응답 전체나 원 응답 바이트를 그대로 보관하는 기능은 아닙니다. 그 외 응답 필드나 보이지 않는 trace를 추가하지 않습니다.

CSV는 UTF-8 BOM과 CRLF를 사용하며 모든 셀을 인용합니다. 같은 열 구조에서 recordType=context인 조회 조건 행 하나를 먼저 두고, 이어지는 recordType=event 행에 검색한 이벤트를 담습니다.0건이어도 context 행이 남습니다. 각 이벤트 행에도 출처·조건을 반복하므로 표에서 행을 따로 확인할 수 있습니다.

CSV의 null은 빈칸이며 valueIsNull과 filterReasonIsAll 열로 값 null과 전체 사유 조건을 구분합니다. 쉼표·따옴표·개행을 인용하고 수식처럼 해석될 문자열에는 작은따옴표 접두어를 붙입니다. 숫자 음수는 그대로 유지합니다. 문자열과 타입을 그대로 보관하려면 JSON을 사용합니다.

## 조작과 검증

화면 준비 전과 조회 중에는 저장 버튼을 잠급니다. 클릭 시 현재 결과를 동기적으로 파일 내용으로 만들며 새 GET·서버 작업·재판정·Kafka/S3 요청을 하지 않습니다. 파일 준비 성공과 사용자가 실제 디스크에 저장했는지는 구분합니다. 조건·실행·출처가 바뀌면 이전 준비 안내를 새 결과의 저장 안내처럼 남기지 않습니다.

모델4개를 추가해 로컬 전체 웹314개·생략0, Astro67파일 진단0·4페이지 빌드를 통과했습니다. 실제 로컬 다운로드의 JSON은 같은ID의 sequence3·4와 SUCCESS/DUPLICATE, raw 검색어·출처·상세 관측 시각을 보존했고 CSV도21열의context1행+event2행과 일치했습니다.0건 JSON에는 이전 이벤트 대신 빈 목록과 현재 조건이 담겼습니다. 키보드 다운로드, 조건·실행 변경 시 안내 해제와 조회 중 버튼 잠금, 모바일375px 가로 넘침0·17px 글자·51px 이상 버튼도 확인했습니다.

독립 검토는 별도 입력과 표준 CSV 디코더를 사용하며 로컬 전체 검사를 반복하지 않습니다. 정확한 head의 검토와 병합 main의 CI·Pages·실제 공개 파일 확인은 PR에 구분해 기록합니다. 로컬 파일 검증만으로 공개 반영이나 운영 가용성을 완료로 간주하지 않습니다.

Pages 토큰 교체·별도 기동 복원·자원 예산 정책·PR102는 보류합니다. 운영 image/source pin·기존 서비스·자료·자동 이미지 제안PR·3개 PAUSED는 유지합니다.
