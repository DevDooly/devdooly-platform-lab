> 현재 상태: [시도4](../../docs/evidence/iceberg-capture/ATTEMPT_4.md)의 a00 source는 Linux 73개·skip0 통과 후 `JAR_MANIFEST_CLASSPATH_TARGET_MISSING`으로 prep에 실패했습니다. 특정 JAR·token·경로 및 전체 closure·prep·compile·decoder·inventory 성공은 미확인입니다. 다음 [ABSENT_CLASSPATH.md](ABSENT_CLASSPATH.md)는 전체 추출 트리·실제 ENOENT·javac 전후 재검증을 묶는 새 SOURCE_ONLY_NOT_RUN 후보이며 Linux 80개는 미실행입니다. 아래 전체 원문과 이전 prefix는 당시 정책·검증 상태를 보존한 역사적 기록입니다. pending 문구는 현재 실행 상태가 아닙니다.

# 전체 export의 큰 manifest를 읽는 제한된 후보

실제 세 번째 capture 실행 `38886641237`·source `a03f87837af66fd3770063d9c712c4080e15d9fa`는 Linux 67개 검사 뒤 PREP에서 `JAR_MANIFEST_BYTES_BOUND`를 기록했습니다. 공개 요약 SHA는 `7b5cd2213e8beb6cf988932eb54465828205c81eeb979aef58044f75cd882340`입니다. 이 코드는 present manifest의 선언 크기 0·64KiB 초과·읽기 불일치를 함께 사용하므로 실제 분기는 미확인입니다. 특정 JAR·manifest 값·크기는 알 수 없으며 whole Class-Path closure 성공도 주장하지 않습니다. 원래 실행과 후보 `d591`·`aed428`·runtime `a970`는 보존합니다.

## 구현 범위

공개/default `scan_jar`는 기존 64KiB 한도와 nonempty Class-Path 거부를 유지합니다. locked Iceberg 검사도 이 경로를 사용합니다. unpack 내부만 manifest당 최대 8MiB를 읽으며, export 하나의 합은 최대 32MiB입니다. 이는 기존 64KiB × 최대 512 JAR의 이론적 전체 한도와 같습니다.

누적 counter는 새 unpack 호출 안에서 한 번 만들고 모든 JAR에 공유합니다. 중앙 entry의 전체 선언 크기를 분해·읽기 전에 먼저 예약합니다. 예약 후 읽기가 실패해도 counter를 되돌리거나 다른 모드로 재시도하지 않습니다. manifest가 없는 JAR는 counter를 쓰지 않으며 이를 manifest 검증 성공의 증거로 바꾸지 않습니다.

manifest는 최대 64KiB chunk로 선언 길이 전체를 읽고 추가 1byte 읽기로 EOF를 요구합니다. ZIP 라이브러리의 CRC 오류는 기존 고정 ZIP 오류 코드로 거부합니다. prefix만 해석하거나 `Class-Path` 앞부분만 찾지 않습니다. 전체 bytes를 확인한 뒤 UTF-8·duplicate attribute·continuation·section 검사를 적용하고 마지막 section의 참조까지 수집합니다. 모든 section의 Class-Path를 보수적으로 검사하는 기존 정책도 같습니다.

folded value는 chunk 목록을 모아 한 번만 결합합니다. 반복 `bytes +=`의 제곱 비용을 없애고, 한 manifest의 읽기·문법 검사에서 쓰는 공간과 작업은 그 제한된 bytes에 비례하도록 합니다. manifest 전체를 동시에 보관하는 것은 현재 한 개뿐이며, 이전 manifest의 본문을 export 결과에 쌓지 않습니다. 각 JAR 최대 128MiB·전체 1GiB·512개·ZIP entry 수·참조 4,096개 한도는 그대로입니다. 별도 prep budget 600초·정리 reserve 40초·기존 workload 600초·이미지와 자원은 바꾸지 않습니다.

tar EOF·whole JAR SHA·nofollow·single-link·owner/mode·shadow 검사·완성된 export map의 transitive closure는 유지합니다. manifest/JAR를 다시 쓰거나 signature 파일을 제거하지 않고 원래 image와 추출 사본 bytes의 parity를 유지합니다.

## 고정 진단 코드

unpack 확장 경로에서만 다음 코드를 구분합니다. 기본 locked 경로의 `JAR_MANIFEST_BYTES_BOUND`는 그대로입니다.

- `JAR_MANIFEST_DECLARED_EMPTY`: present manifest의 선언 길이가 0
- `JAR_MANIFEST_DECLARED_SIZE_BOUND`: 선언 타입·범위 또는 8MiB 한도 거부
- `JAR_MANIFEST_READ_MISMATCH`: 선언한 전체 길이·EOF와 실제 읽기 불일치
- `JAR_MANIFEST_AGGREGATE_BYTES_BOUND`: 공유 counter 또는 32MiB 누적 한도 거부

CRC·ZIP 형식 오류는 `VALID_BOUNDED_JAR_ZIP_REQUIRED`로 남습니다. 새 네 literal은 별도 C-only CLI 후보의 allowlist에만 추가했습니다. 네 줄을 제거하면 직전 CLI 전체 bytes와 같으며 모든 함수·class AST가 같습니다. UI·runtime manifest는 이 후보가 수정하지 않습니다. 원래 frozen CLI도 보존하며 알 수 없는 코드를 자동 공개하지 않습니다. raw 이름·크기·본문·exception은 공개하지 않습니다.

## 합성 검사와 남은 검증

기존 13개 test body를 유지하고 6개 method를 추가했습니다. 큰 signed-style per-entry section과 마지막 참조·UTF-8, 기본 64KiB 경계, 정확한 8MiB·초과·빈 manifest, 실제 CRC 손상과 불완전/추가 읽기, 전체 32MiB·추가 1byte의 읽기 전 거부, folded 문법 보존을 검사합니다. 새 POSIX method는 실제 unpack의 공유 counter·whole bytes·0444를 확인합니다.

root 전체 검토와 독립 peer 검토 뒤 Windows archive 검사 한 번을 실행했습니다. 실제 19개 중 15개 통과·4개 POSIX 건너뜀·실패/오류 0개이며 `offline-attempt1-result.json`과 원문 로그를 보존했습니다. source/test bytes는 검토한 상태 그대로이고 재실행하지 않았습니다. Linux·prep·Cloud와 CLI 검사는 실행하지 않았습니다. 전체 Linux 예정 수는 기존 67개에 새 6개를 더한 73개입니다. 이 숫자는 Linux 실행 성공을 뜻하지 않습니다.

signed-style fixture는 digest section 문법을 닮은 합성 bytes이며 실제 signer 인증을 증명하지 않습니다. [공식 Java 21 JAR 규격](https://docs.oracle.com/en/java/javase/21/docs/specs/jar/jar.html#signed-jar-file)은 signed entry별 manifest section과 digest attribute를 설명합니다. [Manifest 제한 설명](https://docs.oracle.com/en/java/javase/21/docs/specs/jar/jar.html#notes-on-manifest-and-signature-files)은 구현이 65,535-byte header value와 65,535개 header를 지원해야 한다고 설명하므로 전체 64KiB는 이 프로그램의 보수적 한도입니다. 이 근거가 실제 실패의 큰 manifest·서명·호환성 해결을 입증하지는 않습니다.
