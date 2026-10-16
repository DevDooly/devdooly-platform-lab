> 조립 후속 검증: 동결 source manifest `3b59cae846b2ea63f88215a6721451018d1ab2345e6e2eebe673eaf14938f430`의 CLI14개+새4개를 root가 Windows에서 한 번 실행해 18개 중 17개 PASS·POSIX 전용1개 skip·실패/오류0을 확인했습니다. 실행 전후 source bytes는 같습니다. 결과 whole SHA는 `93589b15be1b93321d779424aadd9465e47b6d2674df0f609f5c4d498068b071`입니다. Linux84·새 Cloud·실제 정규화 성공은 미확인입니다. 아래 전체 제안 원문과 테스트 미실행 문구는 source 동결 당시의 역사적 상태로 보존합니다. 진단 단계는 시도한 guard 구간이며 실제 실패 원인이나 해결을 뜻하지 않습니다.

# 정규화 검증 단계의 제한된 진단 후보

이 후보는 정규화 실패가 발생한 검증 단계를 구분합니다. 원인을 고치거나 새 실행의 성공을 증명하는 변경은 아닙니다. 실제 시험 5(`38895409421`)의 공개 요약은 `NORMALIZE` 단계의 `UNKNOWN`을 기록했습니다. 컴파일 준비, 원본 main의 1회 호출과 0 반환, 별도 decoder의 정지·CLI 회수 확인만으로 decoder 종료 코드, 그래프 완전성, inventory 생성 또는 정규화 성공을 추론하지 않습니다. 원래 실패 기록은 그대로 보존합니다.

## 변경 경계

- `normalize_graph.py`: 원래 함수 본문을 같은 순서로 실행하고, 각 검증 직전에 고정 단계만 선택합니다. 실패하면 정확한 `NormalizationFailure(ValueError)`를 발생시킵니다. 예외의 `args`와 `phaseCode`에는 아래 고정 단계만 있으며, 원래 예외를 문자열로 만들지 않습니다. `raise ... from None`으로 공개 메시지에 원래 문맥을 연결하지 않습니다.
- `composite_entry.py`: 현재 단계가 `NORMALIZE`이고 출처가 고정된 normalizer의 정확한 예외 클래스인 경우에만 고정 enum을 읽습니다. subclass, 다른 예외, 누락·잘못된 속성 및 진단 속성을 읽는 도중의 오류는 `UNKNOWN`입니다. 진단 실패가 원래 실패를 가리지 않습니다. 새 비공개 영수증 필드 `safeNormalizationFailureCode`의 기본값은 `UNKNOWN`입니다.
- `run_capture.py`: 새 영수증의 정확한 키·출처·타입을 검증한 뒤, 실패한 `NORMALIZE` 단계에서만 새 고정 필드를 공개 진단으로 옮깁니다. 먼저 잡힌 CLI 오류가 있으면 그 결과를 우선합니다. 기존 비공개 `failureCode`는 계속 무시합니다. 기존 144개 일반 리터럴 허용 목록에 이 11개 단계를 섞지 않습니다.
- 기존 CLI 테스트의 영수증 fixture에 필수 `UNKNOWN` 필드 한 개를 추가합니다. 기존 14개 테스트 메서드 본문과 공개 요약 구조는 바꾸지 않습니다. 새 순수 테스트는 4개입니다.

## 고정 코드

모든 코드는 **해당 검증을 시도했으나 확인하지 못한 단계**를 뜻합니다. 코드만으로 내부 원인이나 실패한 세부 필드를 특정하지 않습니다.

| 공개 코드 | 원래 수행하는 범위 |
|---|---|
| `NORMALIZE_AUTHORITY_UNVERIFIED` | 원본·named 관측·검증·정지 권한 자료의 관계 검증 |
| `NORMALIZE_DESCRIPTOR_UNVERIFIED` | 실제 capture map과 로드한 descriptor·frame의 관계 검증 |
| `NORMALIZE_DECODER_LIFECYCLE_UNVERIFIED` | decoder 정지·CLI 회수·응답 및 전후 writer 관계 검증 |
| `NORMALIZE_PLANNER_SOURCE_UNVERIFIED` | 동결한 순수 planner의 바이트 확인과 로드 |
| `NORMALIZE_REPLY_UNVERIFIED` | 제한된 엄격 JSON 응답과 descriptor 관계 검증 |
| `NORMALIZE_GRAPH_UNVERIFIED` | 그래프·파일·ref·전이 폐쇄의 독립 검증 |
| `NORMALIZE_EXIT_BINDING_UNVERIFIED` | decoder 종료 코드와 응답 상태의 관계 검증 |
| `NORMALIZE_CLOCK_UNVERIFIED` | 평가 시각 검증 |
| `NORMALIZE_INVENTORY_UNVERIFIED` | 검증 snapshot 선택과 inventory 구성 |
| `NORMALIZE_PLAN_UNVERIFIED` | 동결 planner의 계획 함수 호출 |
| `NORMALIZE_RESULT_UNVERIFIED` | 최종 결과·비공개 영수증 구성 |

normalizer가 반환된 뒤 composite의 남은 시각 검사나 영수증 저장에서 실패하면 이 wrapper의 단계 코드로 분류하지 않습니다. 그 오류는 계속 `UNKNOWN`입니다. `UNKNOWN`은 관측되지 않은 실패 구간이 남았음을 뜻하며 성공이나 오류 부재를 뜻하지 않습니다.

## 보존하는 조건

원래 검증 본문의 연산 AST는 wrapper와 단계 할당만 제거하면 동결 `8bea454b…`의 `normalize_graph`와 같습니다. 원래 검증 호출, pass gate, 결과 구성, planner 소스, 300초 신선도, 600초 workload 시계, 자원·컨테이너·정리 코드는 그대로입니다. composite도 진단 할당과 새 영수증 키만 제거하면 원래 `run` 본문 AST와 같습니다. CLI의 소스 승인 접두부, `main`, `safe_summary` 및 진단 외 함수 본문은 그대로입니다.

공개 JSON의 키와 schemaVersion 2는 유지합니다. 실패 시 관측되지 않은 다섯 count는 `null`이며, 객체 후보 0은 삭제하지 않는 정책값입니다. 예외 메시지·args·traceback·경로·원본 종료 코드·응답 데이터·argv·환경변수·표준출력·표준오류를 새로 공개하지 않습니다. 실제 decoder 종료 코드나 그래프가 확인되었다는 새 주장을 만들지 않습니다.

## 검증 상태

현재는 소스 검토용입니다. 새 테스트를 실행하지 않았습니다. Python 3.10 AST·LF와 원래 연산의 정적 역변환을 확인합니다. 새 4개 테스트는 11개 실제 wrapper 구간, 원래 함수 본문과 합성 반환값의 동등성, 정확한 클래스와 위조·속성 읽기 실패, 실제 composite 본문의 합성 실패·후속 deadline 오류, 잘못된 출처·단계·성공 영수증 거부, 먼저 잡힌 오류 우선 및 비밀 canary 미노출을 검사하도록 작성했습니다.

기존 normalizer 거부 테스트는 `ValueError` 계열과 비밀값 미노출을 검사하므로 약화할 변경이 없습니다. 기존 `strict_json` 메시지 검사는 copy loader를 직접 검사하며 바꾸지 않습니다. 승인 후 집중 실행 대상은 기존 CLI 14개와 새 4개, 총 18개입니다. Windows의 기존 실제 POSIX 메타데이터 검사 1개는 정직하게 skip해야 합니다. 향후 전체 Linux suite의 예상 메서드 수는 기존 80개와 새 4개를 합친 84개이며, 이 후보의 Linux·Cloud 실행 결과는 아직 없습니다.

이번 후보에서 실제 비공개 증명·파일·로그 읽기, Docker·Java·SQL·네트워크 실행, D 저장소·Git·원격 변경 및 새 CI 실행은 하지 않았습니다. 새 runtime manifest와 UI의 고정 코드 profile은 별도 검토 후 결합해야 합니다.
