# 검증된 JAR export 안의 Class-Path 참조만 허용하는 후보

현재는 C-only 소스 후보입니다. root 전체 source/test 검토 후 Windows 합성 검사 한 번을 실행해 13개 중 10개 통과, 실제 POSIX 파일 검사는 3개 건너뜀으로 기록했습니다. Linux·prep·Cloud 실행은 하지 않았습니다. 원래 archive helper와 실패 기록은 보존하며 이 후보의 코드 변경 대상은 `archive_classes.py`와 `test_archive_classes.py`뿐입니다.

두 번째 capture 실행 `38881661893`의 공개 요약은 `JAR_MANIFEST_CLASSPATH_EXPANSION_REJECTED`를 기록했습니다. 마지막 관측 명령은 자기 cold CID의 부재 확인이며 prep 정리 관측 네 값은 true입니다. 특정 JAR·manifest 값·참조 대상은 공개 기록에서 알 수 없습니다. 첫 실행의 미확인 PREP 실패를 같은 원인으로 바꾸지 않으며, 이 후보가 실제 호환성을 해결한다고 미리 주장하지 않습니다.

Java 21은 context JAR를 기준으로 manifest의 상대 참조를 해석하고 대상 JAR의 manifest 참조도 classpath에 추가합니다. 명시적 `-cp` 목록으로 바꾸는 것만으로 이 확장을 막지는 못합니다. [공식 JAR 규격](https://docs.oracle.com/en/java/javase/21/docs/specs/jar/jar.html#class-path-attribute)과 설치된 JDK 21의 `Locations.SearchPath`·`FSInfo.getJarClassPath`·`URLClassPath.JarLoader`를 대조했습니다. JAR 내용이나 manifest를 수정하는 방법은 host/runtime parity를 깨므로 사용하지 않습니다.

## 후보 경계

- 공개/default `scan_jar`는 locked Iceberg JAR를 포함해 nonempty `Class-Path`를 계속 거부합니다. 허용 boolean이나 fallback을 추가하지 않습니다.
- unpack 내부만 bounded structural/ZIP/Main·nested·multi-release shadow 검사와 manifest 문법 검사 후 참조를 수집합니다. 모든 archive member와 EOF·whole SHA·안정성이 확인된 export map이 완성된 뒤에만 대상 존재를 검사하고 반환합니다.
- 각 참조는 ASCII `.jar` 상대 token만 허용합니다. 원본 JAR의 상대 디렉터리에 그대로 연결하며 export map의 정확한 이름과 일치해야 합니다. scheme·절대 경로·`..`·`.` alias·percent·query·fragment·backslash·directory·누락 대상·대소문자 추측을 거부합니다. Unicode·tab 등 ASCII space 이외의 separator도 보수적으로 거부합니다.
- 참조는 전체 최대 4,096개입니다. 중복 edge의 순서와 개수를 유지하되 각 JAR는 한 번만 순회하므로 닫힌 cycle은 유한하게 끝납니다. export는 기존 512 JAR·각 128MiB·전체 1GiB 한도를 유지합니다. Manifest의 모든 section을 보수적으로 검사하며, 이를 실제 JVM이 모든 section을 사용한다는 관측으로 표현하지 않습니다.
- 모든 대상 JAR를 구조·shadow 검사하고 whole bytes를 확인합니다. 기존 tar·nofollow·single-link·소유자·0444·whole SHA/readback과 compiled class 경계는 유지합니다. `prep_decoder.classpath_inventory`의 base JAR 내 모든 `org/apache/iceberg` class 거부도 그대로입니다.
- host의 새 사본만 바꾸지 않습니다. 추출한 JAR bytes와 원래 image의 `/opt/spark/jars/*`는 유지하고 동일한 pinned image ID의 runtime을 사용합니다. prep·decoder·원래 producer·SQL·자원·600초 clock·정리 명령은 변경하지 않습니다.

새 고정 실패 코드는 `JAR_MANIFEST_CLASSPATH_TOKEN_REJECTED`, `JAR_MANIFEST_CLASSPATH_REFERENCE_BOUND`, `JAR_MANIFEST_CLASSPATH_EXPORT_MAP_REQUIRED`, `JAR_MANIFEST_CLASSPATH_TARGET_MISSING`, `JAR_MANIFEST_CLASSPATH_CLOSURE_BOUND`입니다. 별도 C-only CLI 후보는 이 다섯 literal만 기존 allowlist에 추가하고 모든 함수와 `UNKNOWN` 경계를 유지합니다. 원래 frozen CLI는 수정하지 않습니다. 알 수 없는 코드를 자동으로 공개하지 않으며 실제 참조가 missing/unsafe이면 여전히 실패하고 실행 단계로 넘어가지 않습니다.

## 작성한 검사와 남은 검증

기존 8개 test body는 유지하고 5개를 추가했습니다. forward/nested/folded 참조·중복과 cycle, URI/path alias·누락 target 거부, exact map/type·reference bound, default locked-JAR 거부와 모든 target shadow 검사, 실제 POSIX unpack의 forward 참조·원본 bytes·0444·실패 staging 보존을 검사합니다.

AST Python 3.10·UTF-8/LF와 기존 함수/test body의 정적 비교를 확인했습니다. 허가된 Windows archive 검사 한 번의 결과는 13개 중 10개 통과·3개 POSIX 건너뜀·실패/오류 0개이며 `offline-attempt1-result.json`과 원문 검사 로그를 보존했습니다. 다음 Linux 전체 예정 수는 67개이고 아직 실행하지 않았습니다. 이 합성 검사는 실제 offending JAR·참조를 확인하거나 새 호환성·Linux 성공·실제 metadata capture를 증명하지 않습니다.
