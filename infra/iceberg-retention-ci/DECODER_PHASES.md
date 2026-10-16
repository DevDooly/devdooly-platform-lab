# Decoder 검증 구간: 다음 source 후보

현재 runtime 후보는 `6b362710597d77ee7a37a59a39aef5e3d6ff59d1f509ca0103192b104a0340fc`이며 normalizer와 CLI 두 행만 바꿉니다. 나머지 runtime9개와 immutable input5개는 그대로입니다. source `10a7955d…`의 production/test와 원래 proposal은 root·독립 peer source 검토를 통과했습니다. 새 Windows 집중19개는 root의 한 번 실행에서 18개 통과·POSIX1개 skip·실패/오류0, source 전후 동일·C stage 바인딩·D HEAD902 clean 전후 동일을 확인했습니다. 결과 전체 SHA는 `3ca277971201e4be876ecfa174756440e4e40f65ce6af4f6739d5a15319f72ed`입니다. 새 Linux85개·Cloud·Java 실행은 미실행입니다. 이전 Windows18개는 17개 통과·POSIX1개 skip의 역사적 결과이고 실제6 source613의 Linux84 통과·NORMALIZE_DECODER_LIFECYCLE_UNVERIFIED 실패를 보존합니다. 새 단계는 검증 구간만 구분하며 실제 원인·decoder 종료 코드·graph·inventory 또는 수정 성공을 주장하지 않습니다.

아래는 원래 동결 proposal `13d6778a…`의 전체 본문입니다. 본문의 미실행 표시는 source 동결 당시 상태이며, 이후 독립 검증 결과는 이 헤더에서 구분합니다.

---

# Decoder lifecycle 검증 단계의 제한된 세분화

실제 6차 공개 기록은 `NORMALIZE_DECODER_LIFECYCLE_UNVERIFIED`를 기록했습니다. 이 코드는 해당 검증 구간을 시도했으나 확인하지 못했다는 뜻이며, 세부 원인이나 실제 decoder 종료 코드를 공개하지 않습니다. 원래 실패와 미관측 count를 그대로 유지합니다.

정적 소스에서 runtime classpath는 이미 `/opt/spark/jars/*`와 고정 Iceberg JAR, 자체 class 디렉터리를 포함합니다. 준비 단계도 같은 구성을 요구합니다. 따라서 Spark 제공 JAR을 누락했다는 가설을 실제 원인이나 이번 변경의 수정 효과로 쓰지 않습니다.

## 최소 변경

`checked_decoder`의 기존 연산과 조건을 같은 순서로 실행하며, 바로 앞에서 다음 고정 단계만 선택합니다. 실패하면 원래 예외를 문자열로 만들지 않고 새 정확한 `NormalizationFailure`를 발생시킵니다. 예외의 `args`와 `phaseCode`에는 선택된 고정 코드만 있습니다.

| 코드 | 원래 검증 구간 |
|---|---|
| `NORMALIZE_DECODER_BUNDLE_UNVERIFIED` | decoder bundle, 전체 바이트 증명, 영수증의 정확한 키 |
| `NORMALIZE_DECODER_SOURCE_UNVERIFIED` | source header와 composite 출처 |
| `NORMALIZE_DECODER_IDENTITY_UNVERIFIED` | 별도 decoder CID와 image identity |
| `NORMALIZE_DECODER_CLOCK_UNVERIFIED` | 원래 시계·deadline·정지·CLI 회수·허용 종료 범위 |
| `NORMALIZE_DECODER_REPLY_BINDING_UNVERIFIED` | 응답 전체 증명과 frame·descriptor·actor 관계 |
| `NORMALIZE_DECODER_WRITERS_AFTER_UNVERIFIED` | decoder 이후 정지 증명 전체 검증 |
| `NORMALIZE_DECODER_ORDER_UNVERIFIED` | 전후 roles·initializer·project·root·시각 순서 |

외부 dependency가 이 예외를 위조해 발생시켜도 `checked_decoder`는 자신이 현재 시도한 구간으로 새 예외를 만듭니다. 바깥 `normalize_graph`는 자신의 `checked_decoder` 호출 구간에서 발생한 정확한 클래스와 위의 7개 코드만 전달합니다. subclass, 알 수 없는 코드, 누락·잘못된 속성 및 다른 검증 구간의 예외는 기존 바깥 단계로 처리합니다. 원래 메시지·args·traceback·경로·응답·종료 코드를 새로 공개하지 않습니다.

normalizer와 CLI의 고정 phase enum만 11개에서 18개로 확장합니다. 기존 일반 CLI 리터럴 144개와 모든 CLI 함수 본문은 그대로입니다. composite `0ef5ca67…`는 정확한 클래스와 고정 enum을 이미 확인하므로 변경하지 않습니다. 공개 요약의 키·schemaVersion·pass/count/null 조건을 바꾸지 않습니다. 향후 UI profile에는 기존 144개 일반 코드와 18개 단계의 합집합 162개를 새 runtime 고정값에만 연결해야 합니다.

## 검증과 한계

wrapper와 단계 할당을 재귀적으로 제거한 `checked_decoder`의 AST는 기존 함수와 같습니다. 바깥 normalizer의 기존 try 본문도 그대로입니다. 기존 테스트 4개 메서드는 바꾸지 않으며, 새 메서드 1개는 실제 7개 검증 지점의 거부, 기존 본문과 합성 정상 반환값의 동등성, dependency가 제시한 단계의 재분류, subclass·위조·잘못된 구간의 전달 거부 및 비밀 canary 미노출을 검사하도록 작성했습니다. 합성 입력은 기존 `test_copy_loader`의 순수 fixture를 재사용하며 실제 비공개 증명을 읽지 않습니다.

현재 테스트 실행은 하지 않았습니다. 집중 대상은 기존 CLI 14개와 phase 테스트 5개로 총 19개이며 Windows의 기존 POSIX 검사 1개는 skip 대상입니다. 향후 전체 Linux suite의 예상 수는 85개이고 결과는 아직 없습니다. 실제 Java·Cloud·SQL·네트워크 실행, private proof·provider 로그 읽기, D·Git·원격 변경 및 자동 재시도는 하지 않았습니다. 이 후보는 원인 진단만 세분화하며, 원인을 수정했다고 주장하지 않습니다.
