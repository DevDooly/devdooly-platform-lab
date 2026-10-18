# Decoder 응답 검증의 제한된 세분화 후보

**현재 검토·검증 상태(2026-10-18):** runtime `bcbd7cc6…`의 source 후보 `3af4460e…`를 검토하고 Windows 집중20개 중19개 PASS·POSIX1개 skip·실패/오류0·source 전후 동일·C 사본 바인딩·D 작업 폴더 보존을 확인했습니다. 결과 SHA-256은 `fb477c02812b5eaca78bf73bc9bd394f920a798f2f28a84340a023fbc65223a1`입니다. 웹88개·타입26개 파일·Pages 빌드도 통과했고 실제7 원문은 byte-exact 보존했습니다. 새 Linux86개·Cloud capture는 미실행이며 정확한 원인·수정 성공·graph·inventory는 미확인입니다. 아래 proposal은 준비 당시의 미실행 기록으로 원문 그대로 보존합니다.

7차 실행 `39081027632`의 source `bf044`는 Linux 85개·UID0·skip0을 통과했지만 전체 capture는 `SUMMARY_NOT_VERIFIED` / `NORMALIZE` / `NORMALIZE_DECODER_REPLY_BINDING_UNVERIFIED`로 실패했습니다. 공개 원문은 1,794 bytes / SHA-256 `70d95a4be42339d4acf231528e1e92443acfaf022867cf35d22f54c4310cdc79`, validation은 2,485 bytes / SHA-256 `9056ef2443f5d7a26431cb6dc778060a410d1b2f54b802d856a77fa2d1653d85`입니다. 정확한 원인·decoder 종료 코드·유효 graph는 미확인이며 여섯 true·세 false 검증과 관측 count·정규화 hash의 null을 유지합니다.

공개 소스 비교에서 결정적인 receipt 불일치는 찾지 못했습니다. 기존 reply 구간은 전체 proof 검증과 strict JSON parse를 먼저 수행하고, 이후 raw·hash·길이·frame·descriptor·전후 actor proof 관계를 확인합니다. Java source의 출력은 JSON+LF이지만 dependency logging의 stdout 혼입은 입증하지 못했습니다. 추정한 Java 수정 대신 같은 검증을 고정 구간으로 나눕니다.

## 변경 범위

- `checked_reply_proof`는 기존 `proof_value(proof, 4*1024**2)`와 같은 순서의 `proof_bytes` → `strict_json`을 호출합니다. 경계·엄격한 parse·원래 값은 바꾸지 않습니다.
- `NORMALIZE_DECODER_REPLY_PROOF_UNVERIFIED`는 전체 proof shape·bytes·SHA 검증을 시도한 구간, `NORMALIZE_DECODER_REPLY_JSON_UNVERIFIED`는 strict JSON parse 구간, `NORMALIZE_DECODER_REPLY_LINKS_UNVERIFIED`는 기존 관계 conjunction 구간입니다. 구체적 필드·원인·원문을 공개하지 않습니다.
- helper는 모든 dependency 예외를 현재 자신의 고정 코드로 새로 감쌉니다. `checked_decoder`는 기존 `REPLY_BINDING` helper 호출 구간에서 정확한 클래스와 helper의 두 코드만 전달합니다. subclass·위조/누락 속성·다른 코드·다른 구간은 현재 caller 구간으로 다시 분류합니다. 예외 원문·args·traceback·URI·필드값·실제 종료 코드를 새로 내보내지 않습니다.
- 기존 `REPLY_BINDING` 코드는 역사적 원문과 caller의 일반 실패 분류를 위해 유지합니다. 정규화 enum은 18→21, decoder enum은 7→10입니다. CLI 일반 코드 144개와 모든 함수 본문, schema·pass/count/null 조건은 그대로입니다.
- runtime 변경은 normalizer·CLI 두 파일뿐입니다. 나머지 runtime 9개와 외부 입력 5개, Java·producer·composite·loader·자원·600초 clock·40초 reserve·snapshot/객체 삭제 금지 조건은 유지합니다. 이 폴더는 runtime manifest·workflow·UI를 조립하지 않습니다.

## 검토와 미실행 범위

기존 phase 테스트의 첫 네 메서드는 AST가 같습니다. 다섯 번째는 helper 호출을 원래 `proof_value` AST로 되돌리는 역변환과 enum 수·같은 기존 frame hash 오류의 LINKS 기대값만 바꿉니다. 새 메서드 한 개는 고정된 copy_loader 소스의 proof_value 본문과 helper의 순서·cap 동등성, 합성 proof 손상·invalid JSON·일곱 관계 불일치, dependency 예외·위조 phase의 재분류와 canary 비노출을 검사하도록 작성했습니다. 기존 checked_decoder 본문 AST fingerprint와 정상 합성 반환값 비교는 유지합니다.

현재는 Python syntax/AST와 전체 source bytes를 정적으로 확인했을 뿐 테스트를 실행하지 않았습니다. 집중 대상은 CLI 14개+phase 6개=20개이고 Windows의 POSIX 전용 1개는 skip 예상입니다. 전체 Linux 예상 수는 86개이며 결과가 없습니다. Cloud·Java·Docker·네트워크·SQL·private proof/provider 로그 읽기·D/Git 변경·자동 재시도는 수행하지 않았습니다. 이 후보는 진단 구간만 좁히며 실제 원인 수정·graph·inventory·전체 KEEP 성공을 주장하지 않습니다.
