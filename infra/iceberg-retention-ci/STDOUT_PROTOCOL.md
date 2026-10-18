# Closed-copy decoder stdout 전용화 제안

2026-10-18 · 공개 소스와 허용된 공개 요약만 읽은 제안이다. 구현·테스트·Java·Docker·서버·네트워크·Git 실행 결과가 아니다.

## 현재 증거와 원인 판단

실제8 실행 `39082460484`·source `e89a858d59910efc6de7ebd42baa840344c056ad`의 Linux86개는 UID0·skip0으로 통과했다. 전체 capture는 `SUMMARY_NOT_VERIFIED` / `NORMALIZE` / `NORMALIZE_DECODER_REPLY_JSON_UNVERIFIED` 실패다. 공개 summary는1,791bytes·SHA-256 `e96ca40d6bfeadfe0a8c51d73aec5c59977f418b3894470bcc4574870af2ca9e`, 공개 validation은2,485bytes·SHA-256 `e8c4738ff7a4b978259f4bbbd83e04cc5034923885d982b9ad9cb6094a0deb2c`다. 여섯 true·세 false 검증과 관측 count/정규화 hash의 null을 유지한다.

새 helper의 고정 구간은 전체 proof bytes 검증 다음의 strict_json 호출에서 실패했음을 구분한다. 이것만으로 stdout의 특정 문자·provider 메시지·오염 위치·정확한 parse 실패 분기·decoder exit·유효 graph를 특정하지 않는다. Private reply/stderr/provider 로그를 읽거나 반출하지 않았다. 이전의 거부된 private proof 반출을 재시도하거나 우회하지 않는다.

## 공개 소스의 구조적 경계

`ClosedCopyDecoder.java`의 현재 SHA는 `d7f9fbab4e1951e5364dcec7e78b8aa1b86531ba034a4c1748b47158a80399d9`다. 52–59행의 바깥 static initializer가 main 진입 전에 JsonFactory/ObjectMapper를 만든다. 527행은 마지막 JSON+LF를 전역 System.out에 쓰며, 같은 출력에 dependency가 쓸 수 없게 구분하는 경계는 없다. 직접 작성한 오류 메시지 세 곳은 System.err로 간다. Dependency가 실제로 stdout에 썼다는 증거는 아직 없다.

`decoder_lifecycle.py` `4b6a2e061d1b92d828520d0b99fb81a63f102d68ca953ee7186f6141cb553d96`는 create의 direct Java entrypoint·interactive stdin을 사용하고 tty 옵션은 추가하지 않는다. 256–263행에서 docker start attach의 stdout은 reply 전용 파일, stderr는 별도 bounded drain으로 분리한다. create CID는 앞선 별도 명령의 반환값이다. Repository 소스에서 명백한 Docker attach framing 또는 두 stream 혼합 오류를 찾지 못했다. CLI가 payload를 framing 없이 JSON으로 제공한다는 실제 wire 검증과 daemon의 동작은 이 정적 검토로 새로 입증하지 않는다.

`bounded_process.py`는 prep 자식의 stdout/stderr를 분리해 제한한다. Decoder payload 자체는 위 lifecycle의 별도 Popen 경로가 맡는다. Prep의 마지막 stdout0·return0은 decoder JSON의 내용이나 종료 코드가 아니다.

## 선택한 최소 변경

추가 고정 하위 코드로 같은 실패만 반복 분류하기보다 Java CLI의 stdout 소유권을 강화한다. 이는 구조적 취약 경계에 대한 수정이며 실제8 원인을 확정한 수정으로 표시하지 않는다.

1. 기존 Jackson factory 설정 전체를 새 private lazy holder로 옮긴다. Strict duplicate detection과 depth64·string8192·number128은 그대로다. 기존 일곱 mapper 사용 지점만 holder 참조로 바꾼다. Decode·frame·metadata·manifest·graph·reason/status·size·clock 연산과 순서는 바꾸지 않는다.
2. CLI main의 첫 동작으로 원래 System.out PrintStream을 지역 변수에 보관하고 System.out을 System.err로 돌린다. 그 뒤 argv 확인·decode·mapper 생성·serialization을 진행한다. 완성한 JSON+LF만 보관한 원래 stream에 같은 순서로 write/flush한다. 출력 stream을 닫지 않는다.
3. System.setOut은 main 안에서만 실행한다. 클래스 로드나 순수 decode 호출은 전역 stdout을 변경하지 않는다. Lazy holder는 바깥 클래스의 mapper 생성이 main보다 먼저 실행되는 경계를 제거하기 위한 것이다. 모든 JVM/provider의 선행 class loading·native 출력까지 통제한다는 보장은 하지 않는다.
4. 기존 exit0/2/3·watchdog124·stderr64KiB·reply4MiB·CPU1/512MiB/PID64·network-none·고정 classpath·original600초/cleanup40초를 유지한다. Library noise가 stderr 한도를 넘으면 기존대로 실패한다. 오류를 숨기거나 stdout에서 JSON처럼 보이는 일부만 잘라 허용하지 않는다.

## 구현 패킷의 제안 범위

먼저 검토할 소스는 다음 세 파일이다. 아직 생성하거나 수정하지 않았다.

- MOD `infra/iceberg-retention-ci/src/org/apache/iceberg/ClosedCopyDecoder.java`: lazy holder·main stream 예약과 routing만 변경한다.
- NEW `infra/iceberg-retention-ci/test_decoder_stdout_source.py`: Java 실행 없는 정적 source 회귀. 허용한 holder/참조/stream 변환을 역변환한 원문이 기존 d7f9 전체 SHA와 같은지, System.setOut이 main 안에만 있고 원래 mapper/상태·size·clock 조건이 유지되는지 확인하도록 작성한다.
- NEW `infra/iceberg-retention-ci/verify_decoder_stdout_fixture.py`: 별도 명시 실행하는 합성 Java 회귀 실행기. 미리 검증한 기존 로컬 Java21·JAR classpath와 fresh 자기 임시 폴더만 사용하도록 준비한다. 기본 offline discover에서 Java를 실행하지 않는다.

후속 조립에서 runtime manifest의 Java 한 행만 바꾸고 나머지10행·외부5개·producer7/base8을 보존한다. 새 offline 파일의 literal pin·정확한 검사 수와 새로운 runtime pin을 workflow에 반영하고, 같은165개 코드의 새 exact runtime profile만 UI에 연결한다. 검사 수는 실제 동결한 테스트를 검토한 뒤 정하며 현재87개 성공처럼 적지 않는다. 공개 wire/runbook에는 stdout 전용화의 범위만 덧붙인다. 기존 실패·진단 code·공개 schema·PASS/count/null gate는 바꾸지 않는다.

## 필요한 검증과 진행 순서

첫째, 독립 소스 검토와 위의 전체 원문 역변환을 확인한다. 새 holder 한 개가 기존 컴파일 class inventory의 허용 이름·64개 상한 안에 들어가는지도 확인한다. 이는 source 보존 근거이며 동작 검증을 대신하지 않는다.

둘째, 새 고정 합성 Java 회귀를 따로 한 번 실행한다. Unmodified 후보의 CLI에 잘못된 magic의 합성 frame을 넣어 처리된 거부 JSON·exit3·strict JSON 단일 document를 확인한다. 별도 test-only copy에서는 lazy holder 초기화 직전과 decode 시작에 고정 stdout canary를 정확히 두 곳 삽입한다. 두 삽입을 제거한 bytes가 검토한 production 후보와 같아야 한다. 이 forked JVM의 stdout은 여전히 같은 JSON+LF이고 canary는 stderr에만 있어야 한다. 합성 noise 테스트이며 실제 provider가 썼다는 증거가 아니다.

같은 회귀에서 순수 library 클래스 로드·decode 전후 System.out 객체가 그대로인지 확인한다. 기존 공개 합성 Java frame/graph fixture도 이전 d7f9와 후보를 각각 fresh class 폴더에 compile하여 같은 입력·반환 JSON을 비교한다. 기존 실제 decoder metadata나 private graph를 fixture로 가져오지 않는다. 이 단계는 로컬 Java/classpath의 결과이며 Cloud image parity·실제 graph 성공을 주장하지 않는다.

셋째, 검토한 새 source의 Linux offline gate와 별도 compiler prep를 통과한 뒤 새 capture를 단 한 번 실행한다. 실제 summary에서 same-run actors/clock·graph·inventory·planner·전체 KEEP을 확인한 단계만 완료로 표시한다. 계속 JSON 단계 실패라면 소스 수정의 효과가 입증되지 않았다고 보존하고, 다른 부분을 성공으로 꾸미거나 parse guard를 완화하지 않는다.

실제 capture의 graph·inventory 연결이 목표다. 이번 제안은 그 목표를 향한 검증 가능한 stdout 경계 강화이며, 문서나 synthetic noise 통과만으로 전체 capture 완료를 선언하지 않는다.
